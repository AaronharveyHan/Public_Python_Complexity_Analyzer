"""
FastAPI application.

Endpoints:
  POST /analyze            – submit a project for analysis
  GET  /result/{task_id}   – poll full result
  GET  /tasks              – list all tasks
  WS   /ws/{task_id}       – real-time progress stream
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict

from fastapi import (
    Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Make the project root importable when running from any working directory
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from backend.api.models import AnalyzeRequest, TaskStatus
from backend.api.report import generate_html_report
from backend.api.tasks  import (
    create_task, get_task, list_tasks,
    start_analysis, subscribe_ws, unsubscribe_ws,
)

# ── Path traversal guard ──────────────────────────────────────────────────────
# Only paths under this directory may be analysed.
# Default is the current working directory (the project you launched from),
# NOT the whole home directory — this keeps the analysable scope narrow.
# Override via the ALLOWED_BASE_DIR environment variable to widen it.
_ALLOWED_BASE: Path = Path(
    os.environ.get("ALLOWED_BASE_DIR", os.getcwd())
).resolve()


def _assert_safe_path(path: Path) -> None:
    """Raise 403 if *path* escapes the allowed base directory."""
    try:
        path.relative_to(_ALLOWED_BASE)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Access denied: path must be inside {_ALLOWED_BASE}. "
                "Set the ALLOWED_BASE_DIR environment variable to change the allowed root."
            ),
        )

app = FastAPI(
    title="Python Complexity Analyzer",
    description="Lightweight SonarQube-like complexity analysis for Python projects.",
    version="1.0.0",
)

# Default: allow common local dev origins only.
# Override with a comma-separated list, e.g.:
#   ALLOWED_ORIGINS="https://example.com,https://app.example.com"
_default_origins = ["http://localhost:5173", "http://localhost:4173", "http://localhost:3000",
                    "http://127.0.0.1:5173", "http://127.0.0.1:4173", "http://127.0.0.1:3000"]
_env_origins = os.environ.get("ALLOWED_ORIGINS", "")
_origins = (
    [o.strip() for o in _env_origins.split(",") if o.strip()]
    if _env_origins else _default_origins
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ── Rate limiter (sliding window, no external deps) ──────────────────────────
_RL_WINDOW:  int = 60   # seconds
_RL_MAX:     int = int(os.environ.get("ANALYZE_RATE_LIMIT", "10"))  # per window per IP
# Hard cap on tracked client IPs so a flood of distinct/spoofed source IPs can't
# grow the store without bound (memory-exhaustion guard).
_RL_MAX_CLIENTS: int = int(os.environ.get("RATE_LIMIT_MAX_CLIENTS", "10000"))
_rl_store:   Dict[str, Deque[float]] = {}
_rl_lock:    threading.Lock = threading.Lock()
_rl_last_sweep: float = 0.0


def _rl_sweep(now: float) -> None:
    """Drop IPs whose whole window has expired. Caller must hold _rl_lock."""
    cutoff = now - _RL_WINDOW
    stale = []
    for ip, dq in _rl_store.items():
        while dq and dq[0] < cutoff:
            dq.popleft()
        if not dq:
            stale.append(ip)
    for ip in stale:
        del _rl_store[ip]


def _rate_limit_check(client_ip: str) -> None:
    """Raise 429 if the client has exceeded the request quota.

    The store self-cleans: IPs whose window has fully expired are evicted on a
    periodic sweep (and whenever the hard client cap is hit), so silent clients
    no longer leak entries forever.
    """
    now = time.monotonic()
    global _rl_last_sweep
    with _rl_lock:
        # Time-based sweep, at most once per window.
        if now - _rl_last_sweep > _RL_WINDOW:
            _rl_sweep(now)
            _rl_last_sweep = now

        dq = _rl_store.get(client_ip)
        if dq is None:
            # New IP: enforce the hard cap before inserting. A forced sweep
            # reclaims any stale entries first; only genuinely-active IPs remain.
            if len(_rl_store) >= _RL_MAX_CLIENTS:
                _rl_sweep(now)
                _rl_last_sweep = now
            dq = deque()
            _rl_store[client_ip] = dq

        cutoff = now - _RL_WINDOW
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= _RL_MAX:
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests — max {_RL_MAX} analyses per {_RL_WINDOW}s. "
                       "Override with ANALYZE_RATE_LIMIT env var.",
            )
        dq.append(now)


# ── Authentication (opt-in bearer token) ─────────────────────────────────────
# Set the API_TOKEN environment variable to require an
#   Authorization: Bearer <token>
# header on every data endpoint.  When API_TOKEN is unset, auth is disabled
# (convenient for purely local use); set it whenever the server is reachable
# from the network.
_API_TOKEN: str = os.environ.get("API_TOKEN", "")


def _token_matches(token: str) -> bool:
    # constant-time compare to avoid leaking the token via timing
    import hmac
    return hmac.compare_digest(token, _API_TOKEN)


def require_auth(request: Request) -> None:
    """Reject requests lacking a valid bearer token (no-op when API_TOKEN unset)."""
    if not _API_TOKEN:
        return
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not _token_matches(token):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: provide 'Authorization: Bearer <API_TOKEN>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    """Health check.  Also returns a suggested project path for the UI."""
    cwd = os.getcwd()
    return {
        "status": "ok",
        "suggested_path": cwd,
        "allowed_base": str(_ALLOWED_BASE),
        "python_version": sys.version.split()[0],
    }


@app.post("/analyze", response_model=TaskStatus, status_code=202,
          dependencies=[Depends(require_auth)])
async def analyze(req: AnalyzeRequest, request: Request) -> TaskStatus:
    """Submit a project path for analysis.  Returns task_id immediately."""
    _rate_limit_check(request.client.host if request.client else "unknown")
    path = Path(req.project_path).expanduser().resolve()
    _assert_safe_path(path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not path.is_dir():
        raise HTTPException(status_code=400, detail="project_path must be a directory")

    task_id = create_task(str(path))
    loop = asyncio.get_running_loop()
    start_analysis(task_id, str(path), req.ignore_dirs, loop)
    task = get_task(task_id)
    return task


@app.get("/result/{task_id}", response_model=TaskStatus,
         dependencies=[Depends(require_auth)])
async def get_result(task_id: str) -> TaskStatus:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/tasks", response_model=list[TaskStatus],
         dependencies=[Depends(require_auth)])
async def get_tasks() -> list[TaskStatus]:
    return list_tasks()


@app.get("/report/{task_id}", response_class=HTMLResponse,
         dependencies=[Depends(require_auth)])
async def get_report(task_id: str) -> HTMLResponse:
    """Download a self-contained HTML report for a completed analysis task."""
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status != "completed" or task.result is None:
        raise HTTPException(
            status_code=400,
            detail=f"Task is not completed yet (status: {task.status})",
        )
    html_content = generate_html_report(task.result)
    project_name = task.result.get("project_name", "project")
    # Restrict to ASCII alphanumerics + safe punctuation to avoid Unicode
    # characters or control codes in the Content-Disposition header.
    safe_name = "".join(
        c if c.isascii() and (c.isalnum() or c in "-_.") else "_"
        for c in project_name
    ).strip("_") or "project"
    filename = f"report-{safe_name}.html"
    return HTMLResponse(
        content=html_content,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── WebSocket – real-time progress ────────────────────────────────────────────

@app.websocket("/ws/{task_id}")
async def ws_progress(websocket: WebSocket, task_id: str) -> None:
    """Subscribe to real-time progress for a task."""
    # Browsers cannot set Authorization headers on a WebSocket handshake, so
    # accept the token via a query parameter:  /ws/{id}?token=<API_TOKEN>
    if _API_TOKEN and not _token_matches(websocket.query_params.get("token", "")):
        await websocket.close(code=1008)  # policy violation
        return
    await websocket.accept()

    task = get_task(task_id)
    if task is None:
        await websocket.send_json({"error": "Task not found"})
        await websocket.close()
        return

    # Send current state immediately (slim payload — full result via REST)
    slim_state = {
        "task_id":  task.task_id,
        "status":   task.status,
        "progress": task.progress,
        "message":  task.message,
    }
    await websocket.send_json(slim_state)
    if task.status in ("completed", "failed"):
        await websocket.close()
        return

    queue = subscribe_ws(task_id)
    try:
        # Re-check after subscribing to close a race: the task may have reached
        # a terminal state in the window between the snapshot above and
        # subscribe_ws(). In that case its terminal event was pushed to the
        # subscriber list *before* our queue existed (and the list was then
        # discarded), so the event never lands in our queue and we would block
        # forever on heartbeats. Surfacing the final state here covers the gap;
        # if the task is still running, the live event stream takes over below.
        task = get_task(task_id)
        if task is not None and task.status in ("completed", "failed"):
            final_state = {
                "task_id":  task.task_id,
                "status":   task.status,
                "progress": task.progress,
                "message":  task.message,
            }
            if task.status == "failed" and task.error:
                final_state["error"] = task.error.rstrip().rsplit("\n", 1)[-1]
            await websocket.send_json(final_state)
            return
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_json(payload)
                if payload.get("status") in ("completed", "failed"):
                    break
            except asyncio.TimeoutError:
                # heartbeat
                await websocket.send_json({"heartbeat": True})
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe_ws(task_id, queue)
        await websocket.close()
