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
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
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
# Override via the ALLOWED_BASE_DIR environment variable.
_ALLOWED_BASE: Path = Path(
    os.environ.get("ALLOWED_BASE_DIR", Path.home())
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
_rl_store:   Dict[str, Deque[float]] = {}


def _rate_limit_check(client_ip: str) -> None:
    """Raise 429 if the client has exceeded the request quota."""
    now = time.monotonic()
    if client_ip not in _rl_store:
        _rl_store[client_ip] = deque()
    dq = _rl_store[client_ip]
    while dq and dq[0] < now - _RL_WINDOW:
        dq.popleft()
    if len(dq) >= _RL_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests — max {_RL_MAX} analyses per {_RL_WINDOW}s. "
                   "Override with ANALYZE_RATE_LIMIT env var.",
        )
    dq.append(now)


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


@app.post("/analyze", response_model=TaskStatus, status_code=202)
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


@app.get("/result/{task_id}", response_model=TaskStatus)
async def get_result(task_id: str) -> TaskStatus:
    task = get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.get("/tasks", response_model=list[TaskStatus])
async def get_tasks() -> list[TaskStatus]:
    return list_tasks()


@app.get("/report/{task_id}", response_class=HTMLResponse)
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
