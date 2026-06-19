"""
Task store + background task runner.

Active tasks live in the in-memory _store (fast reads during analysis).
Completed / failed tasks are persisted to SQLite so they survive restarts.
On get_task() miss the DB is checked, giving access to historical results.

SQLite path: TASK_DB_PATH env var (default: tasks.db next to this file's
project root).  Set TASK_DB_PATH=:memory: for in-process testing.
"""
from __future__ import annotations

import atexit
import asyncio
import json
import os
import sqlite3
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import TaskStatus

_executor = ThreadPoolExecutor(
    max_workers=int(os.environ.get("ANALYSIS_MAX_WORKERS", "4"))
)
atexit.register(_executor.shutdown, wait=True)

ANALYSIS_TIMEOUT: int = int(os.environ.get("ANALYSIS_TIMEOUT", "300"))

_lock: threading.RLock = threading.RLock()

# {task_id: TaskStatus}  – active / recent tasks
_store: Dict[str, TaskStatus] = {}

# {task_id: [asyncio.Queue]}  – per-task WebSocket subscriber queues
_ws_queues: Dict[str, List[asyncio.Queue]] = {}

# {task_id: threading.Event}  – set to request cooperative cancellation of a
# running analysis (e.g. by the timeout watchdog).
_cancel_events: Dict[str, threading.Event] = {}


# ── SQLite persistence ─────────────────────────────────────────────────────────

_DB_PATH: str = os.environ.get(
    "TASK_DB_PATH",
    str(Path(__file__).resolve().parent.parent.parent / "tasks.db"),
)

_db: sqlite3.Connection | None = None
_db_lock = threading.Lock()


def _db_init() -> None:
    global _db
    path = _DB_PATH
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    _db = sqlite3.connect(path, check_same_thread=False)
    # `progress` has no CHECK(progress BETWEEN 0 AND 100) constraint here.
    # The 0-100 range is enforced at the application layer (TaskStatus's
    # Pydantic field and the clamp in _update()), so this is a missing
    # defense-in-depth guard against direct/manual SQL writes rather than
    # a reachable bug through the API today. Note that adding a CHECK
    # later wouldn't retroactively apply to an existing DB file anyway,
    # since this is CREATE TABLE IF NOT EXISTS — it would need a migration.
    _db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            task_id    TEXT PRIMARY KEY,
            status     TEXT NOT NULL,
            progress   INTEGER NOT NULL DEFAULT 0,
            message    TEXT NOT NULL DEFAULT '',
            result_json TEXT,
            error      TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        )
    """)
    _db.commit()


_db_init()


def _db_upsert(task: TaskStatus, created_at: float | None = None) -> None:
    if _db is None:
        return
    now = time.time()
    result_json = json.dumps(task.result) if task.result is not None else None
    with _db_lock:
        _db.execute(
            """
            INSERT INTO tasks
                (task_id, status, progress, message, result_json, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                status      = excluded.status,
                progress    = excluded.progress,
                message     = excluded.message,
                result_json = excluded.result_json,
                error       = excluded.error,
                updated_at  = excluded.updated_at
            """,
            (
                task.task_id, task.status, task.progress, task.message,
                result_json, task.error, created_at or now, now,
            ),
        )
        _db.commit()


def _db_fetch(task_id: str) -> TaskStatus | None:
    if _db is None:
        return None
    with _db_lock:
        row = _db.execute(
            "SELECT task_id, status, progress, message, result_json, error "
            "FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    if row is None:
        return None
    return TaskStatus(
        task_id  = row[0],
        status   = row[1],
        progress = row[2],
        message  = row[3],
        result   = json.loads(row[4]) if row[4] else None,
        error    = row[5],
    )


def _db_fetch_all() -> list[TaskStatus]:
    if _db is None:
        return []
    with _db_lock:
        rows = _db.execute(
            "SELECT task_id, status, progress, message, result_json, error "
            "FROM tasks ORDER BY updated_at DESC"
        ).fetchall()
    return [
        TaskStatus(
            task_id  = r[0],
            status   = r[1],
            progress = r[2],
            message  = r[3],
            result   = json.loads(r[4]) if r[4] else None,
            error    = r[5],
        )
        for r in rows
    ]


def _reset_db() -> None:
    """Clear all persisted tasks.  Used by tests only."""
    if _db is None:
        return
    with _db_lock:
        _db.execute("DELETE FROM tasks")
        _db.commit()


# ── Task CRUD ─────────────────────────────────────────────────────────────────

def create_task(project_path: str) -> str:
    task_id = str(uuid.uuid4())
    task = TaskStatus(task_id=task_id, status="pending", progress=0, message="Queued")
    with _lock:
        _store[task_id] = task
    _db_upsert(task, created_at=time.time())
    return task_id


def get_task(task_id: str) -> Optional[TaskStatus]:
    with _lock:
        if task_id in _store:
            return _store[task_id]
    # Active store miss — look up historical record in SQLite.
    return _db_fetch(task_id)


def list_tasks() -> List[TaskStatus]:
    # Merge: DB provides the full history; active _store entries override
    # (they carry the most up-to-date state for in-progress analyses).
    by_id: Dict[str, TaskStatus] = {t.task_id: t for t in _db_fetch_all()}
    with _lock:
        by_id.update(_store)
    return list(by_id.values())


# ── Progress updates ──────────────────────────────────────────────────────────

def _update(task_id: str, **kwargs: Any) -> None:
    if "progress" in kwargs:
        kwargs["progress"] = max(0, min(100, int(kwargs["progress"])))
    with _lock:
        task = _store.get(task_id)
        if task is None:
            return
        # Terminal-state guard: once a task is completed/failed, ignore any
        # later update. Prevents a runaway analysis that finishes *after* the
        # timeout watchdog already marked it failed from clobbering that state
        # (and re-persisting a "completed" row). First terminal status wins.
        if task.status in ("completed", "failed"):
            return
        task = TaskStatus.model_validate({**task.model_dump(), **kwargs})
        _store[task_id] = task
        terminal = task.status in ("completed", "failed")

    ws_payload: Dict[str, Any] = {
        "task_id":  task.task_id,
        "status":   task.status,
        "progress": task.progress,
        "message":  task.message,
    }
    if task.status == "failed" and task.error:
        last_line = task.error.rstrip().rsplit("\n", 1)[-1]
        ws_payload["error"] = last_line

    _push_ws(task_id, ws_payload)

    if terminal:
        # Persist completed/failed tasks so they survive server restarts.
        # Note: this happens *outside* any `_lock` hold, so a concurrent
        # reader can observe `_store` already in its terminal state while
        # `_ws_queues`/`_cancel_events` for this task_id haven't been
        # cleaned up yet (the second `with _lock` below). Not a deadlock
        # risk (locks are always taken one at a time, never nested here),
        # just a brief non-atomic window between the two `with _lock`
        # blocks in this function.
        _db_upsert(task)
        with _lock:
            _ws_queues.pop(task_id, None)
            _cancel_events.pop(task_id, None)


def _push_ws(task_id: str, payload: dict) -> None:
    with _lock:
        queues = list(_ws_queues.get(task_id, []))
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def subscribe_ws(task_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=128)
    with _lock:
        _ws_queues.setdefault(task_id, []).append(q)
    return q


def unsubscribe_ws(task_id: str, q: asyncio.Queue) -> None:
    with _lock:
        qs = _ws_queues.get(task_id, [])
        try:
            qs.remove(q)
        except ValueError:
            pass
        # Drop the now-empty list so a late subscriber on an already-terminal
        # task (which re-creates the entry after _update popped it) doesn't
        # leak an empty list per task forever.
        if not qs:
            _ws_queues.pop(task_id, None)


# ── Run analysis in background thread ────────────────────────────────────────

def start_analysis(
    task_id: str,
    project_path: str,
    ignore_dirs: list[str] | None,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """Submit the analysis job to the thread pool."""

    cancel_event = threading.Event()
    with _lock:
        _cancel_events[task_id] = cancel_event

    def _run() -> None:
        from backend.analyzer.core import analyze_project, AnalysisCancelled

        def _progress(pct: int, msg: str) -> None:
            loop.call_soon_threadsafe(
                lambda p=pct, m=msg: _update(
                    task_id, progress=p, message=m, status="processing"
                )
            )

        try:
            loop.call_soon_threadsafe(
                lambda: _update(task_id, status="processing", progress=0, message="Starting…")
            )
            result = analyze_project(
                project_path,
                ignore_dirs=set(ignore_dirs) if ignore_dirs else None,
                progress_cb=_progress,
                should_cancel=cancel_event.is_set,
            )
            loop.call_soon_threadsafe(
                lambda r=result: _update(
                    task_id, status="completed", progress=100, message="Done", result=r
                )
            )
        except AnalysisCancelled:
            # Cancellation was requested (e.g. timeout). The watchdog owns the
            # terminal state; just stop and free the worker. The terminal-state
            # guard in _update drops any stale write either way.
            return
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            loop.call_soon_threadsafe(
                lambda t=tb: _update(
                    task_id, status="failed", progress=0, message="Error", error=t
                )
            )

    future = _executor.submit(_run)

    def _watchdog() -> None:
        """Cancel + fail the task if the analysis exceeds ANALYSIS_TIMEOUT."""
        try:
            future.result(timeout=ANALYSIS_TIMEOUT)
        except FutureTimeoutError:
            # Signal the running analysis to stop at the next file boundary so
            # the worker thread is released, then mark the task failed.
            cancel_event.set()
            loop.call_soon_threadsafe(
                lambda: _update(
                    task_id, status="failed", progress=0, message="Error",
                    error=f"TimeoutError: analysis exceeded {ANALYSIS_TIMEOUT}s limit.\n"
                          f"Set ANALYSIS_TIMEOUT env var to adjust.",
                )
            )
        except Exception:
            pass

    threading.Thread(target=_watchdog, daemon=True).start()
