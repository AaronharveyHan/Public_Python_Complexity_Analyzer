"""Tests for the FastAPI application endpoints."""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

import backend.api.main as main_mod
import backend.api.tasks as tasks_mod
from backend.api.main import app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_task_store():
    """Wipe in-memory task store, SQLite DB, and rate-limiter before/after every test."""
    tasks_mod._store.clear()
    tasks_mod._ws_queues.clear()
    tasks_mod._reset_db()
    main_mod._rl_store.clear()
    main_mod._rl_last_sweep = 0.0
    yield
    tasks_mod._store.clear()
    tasks_mod._ws_queues.clear()
    tasks_mod._reset_db()
    main_mod._rl_store.clear()
    main_mod._rl_last_sweep = 0.0


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient whose ALLOWED_BASE is scoped to tmp_path."""
    monkeypatch.setattr(main_mod, "_ALLOWED_BASE", tmp_path.resolve())
    return TestClient(app)


@pytest.fixture
def project_dir(tmp_path):
    """A minimal Python project living under tmp_path."""
    (tmp_path / "app.py").write_text("def hello():\n    pass")
    return tmp_path


@pytest.fixture
def no_start(monkeypatch):
    """Prevent actual background analysis from running."""
    monkeypatch.setattr(main_mod, "start_analysis", lambda *a, **kw: None)


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealthEndpoint:
    def test_returns_200(self, client):
        assert client.get("/health").status_code == 200

    def test_status_ok(self, client):
        assert client.get("/health").json()["status"] == "ok"

    def test_includes_python_version(self, client):
        assert "python_version" in client.get("/health").json()

    def test_includes_suggested_path(self, client):
        assert "suggested_path" in client.get("/health").json()

    def test_includes_allowed_base(self, client):
        assert "allowed_base" in client.get("/health").json()


# ── POST /analyze ─────────────────────────────────────────────────────────────

class TestAnalyzeEndpoint:
    def test_valid_path_returns_202(self, client, project_dir, no_start):
        resp = client.post("/analyze", json={"project_path": str(project_dir)})
        assert resp.status_code == 202

    def test_response_contains_task_id(self, client, project_dir, no_start):
        resp = client.post("/analyze", json={"project_path": str(project_dir)})
        assert "task_id" in resp.json()

    def test_initial_status_is_pending_or_processing(self, client, project_dir, no_start):
        resp = client.post("/analyze", json={"project_path": str(project_dir)})
        assert resp.json()["status"] in ("pending", "processing")

    def test_nonexistent_path_returns_404(self, client, tmp_path):
        missing = str(tmp_path / "does_not_exist")
        assert client.post("/analyze", json={"project_path": missing}).status_code == 404

    def test_path_outside_allowed_returns_403(self, client):
        # /etc is almost certainly outside tmp_path
        assert client.post("/analyze", json={"project_path": "/etc"}).status_code == 403

    def test_file_path_returns_400(self, client, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("x = 1")
        assert client.post("/analyze", json={"project_path": str(f)}).status_code == 400

    def test_ignore_dirs_accepted(self, client, project_dir, no_start):
        resp = client.post(
            "/analyze",
            json={"project_path": str(project_dir), "ignore_dirs": ["tests", "docs"]},
        )
        assert resp.status_code == 202

    def test_task_stored_after_submit(self, client, project_dir, no_start):
        resp = client.post("/analyze", json={"project_path": str(project_dir)})
        task_id = resp.json()["task_id"]
        assert task_id in tasks_mod._store


# ── GET /result/{task_id} ─────────────────────────────────────────────────────

class TestResultEndpoint:
    def test_unknown_task_returns_404(self, client):
        assert client.get("/result/nonexistent-id").status_code == 404

    def test_known_task_returns_200(self, client, project_dir, no_start):
        task_id = client.post(
            "/analyze", json={"project_path": str(project_dir)}
        ).json()["task_id"]
        assert client.get(f"/result/{task_id}").status_code == 200

    def test_result_has_expected_fields(self, client, project_dir, no_start):
        task_id = client.post(
            "/analyze", json={"project_path": str(project_dir)}
        ).json()["task_id"]
        data = client.get(f"/result/{task_id}").json()
        assert data["task_id"] == task_id
        assert "status" in data
        assert "progress" in data
        assert "message" in data

    def test_status_is_valid_literal(self, client, project_dir, no_start):
        task_id = client.post(
            "/analyze", json={"project_path": str(project_dir)}
        ).json()["task_id"]
        status = client.get(f"/result/{task_id}").json()["status"]
        assert status in ("pending", "processing", "completed", "failed")

    def test_progress_in_0_to_100(self, client, project_dir, no_start):
        task_id = client.post(
            "/analyze", json={"project_path": str(project_dir)}
        ).json()["task_id"]
        progress = client.get(f"/result/{task_id}").json()["progress"]
        assert 0 <= progress <= 100


# ── GET /tasks ────────────────────────────────────────────────────────────────

class TestTasksEndpoint:
    def test_empty_when_no_tasks(self, client):
        resp = client.get("/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_lists_submitted_tasks(self, client, project_dir, no_start):
        client.post("/analyze", json={"project_path": str(project_dir)})
        tasks = client.get("/tasks").json()
        assert len(tasks) == 1

    def test_multiple_tasks_listed(self, client, project_dir, no_start):
        client.post("/analyze", json={"project_path": str(project_dir)})
        client.post("/analyze", json={"project_path": str(project_dir)})
        tasks = client.get("/tasks").json()
        assert len(tasks) == 2

    def test_each_task_has_task_id(self, client, project_dir, no_start):
        client.post("/analyze", json={"project_path": str(project_dir)})
        for task in client.get("/tasks").json():
            assert "task_id" in task


# ── Authentication (opt-in bearer token) ──────────────────────────────────────

class TestAuth:
    @pytest.fixture
    def auth_client(self, tmp_path, monkeypatch):
        """TestClient with API_TOKEN enforcement enabled."""
        monkeypatch.setattr(main_mod, "_ALLOWED_BASE", tmp_path.resolve())
        monkeypatch.setattr(main_mod, "_API_TOKEN", "s3cret")
        return TestClient(app)

    def test_no_token_rejected_401(self, auth_client, project_dir, no_start):
        resp = auth_client.post("/analyze", json={"project_path": str(project_dir)})
        assert resp.status_code == 401

    def test_wrong_token_rejected_401(self, auth_client, project_dir, no_start):
        resp = auth_client.post(
            "/analyze",
            json={"project_path": str(project_dir)},
            headers={"Authorization": "Bearer wrong"},
        )
        assert resp.status_code == 401

    def test_valid_token_accepted(self, auth_client, project_dir, no_start):
        resp = auth_client.post(
            "/analyze",
            json={"project_path": str(project_dir)},
            headers={"Authorization": "Bearer s3cret"},
        )
        assert resp.status_code == 202

    def test_tasks_requires_token(self, auth_client):
        assert auth_client.get("/tasks").status_code == 401
        assert auth_client.get(
            "/tasks", headers={"Authorization": "Bearer s3cret"}
        ).status_code == 200

    def test_health_is_public(self, auth_client):
        # health stays unauthenticated even when a token is configured
        assert auth_client.get("/health").status_code == 200

    def test_disabled_when_token_unset(self, client, project_dir, no_start):
        # default client has _API_TOKEN == "" → auth is a no-op
        resp = client.post("/analyze", json={"project_path": str(project_dir)})
        assert resp.status_code == 202


# ── Timeout / terminal-state guard (audit C-4) ────────────────────────────────

class TestTerminalStateGuard:
    """Once a task is terminal, late updates must not clobber it."""

    def _seed(self, task_id, status="processing"):
        from backend.api.models import TaskStatus
        with tasks_mod._lock:
            tasks_mod._store[task_id] = TaskStatus(
                task_id=task_id, status=status, progress=10, message="working"
            )

    def test_late_completion_does_not_overwrite_timeout_failure(self):
        tid = "guard-1"
        self._seed(tid)
        # watchdog marks it failed (timeout)
        tasks_mod._update(tid, status="failed", progress=0,
                          message="Error", error="TimeoutError: ...")
        assert tasks_mod._store[tid].status == "failed"
        # runaway analysis finishes late and tries to mark completed
        tasks_mod._update(tid, status="completed", progress=100,
                          message="Done", result={"summary": {}})
        assert tasks_mod._store[tid].status == "failed"      # not clobbered
        assert tasks_mod._store[tid].result is None

    def test_completed_not_flipped_to_failed(self):
        tid = "guard-2"
        self._seed(tid)
        tasks_mod._update(tid, status="completed", progress=100,
                          message="Done", result={"summary": {}})
        assert tasks_mod._store[tid].status == "completed"
        tasks_mod._update(tid, status="failed", progress=0, message="late error")
        assert tasks_mod._store[tid].status == "completed"   # first terminal wins

    def test_progress_update_before_terminal_still_applies(self):
        tid = "guard-3"
        self._seed(tid)
        tasks_mod._update(tid, progress=50, message="half", status="processing")
        assert tasks_mod._store[tid].progress == 50
        assert tasks_mod._store[tid].status == "processing"


class TestTimeoutCancellation:
    """A timed-out analysis is cancelled and reported as failed (not completed)."""

    def test_timeout_cancels_and_marks_failed(self, client, project_dir, monkeypatch):
        import threading
        # Force an immediate timeout so the watchdog fires right away.
        monkeypatch.setattr(tasks_mod, "ANALYSIS_TIMEOUT", 0)

        started = threading.Event()
        release = threading.Event()

        import backend.analyzer.core as core_mod

        def slow_analyze(*args, should_cancel=None, **kwargs):
            started.set()
            # simulate a long analysis that honours cooperative cancellation
            for _ in range(200):
                if should_cancel and should_cancel():
                    raise core_mod.AnalysisCancelled()
                release.wait(timeout=0.05)
            return {"summary": {}}

        monkeypatch.setattr(core_mod, "analyze_project", slow_analyze)

        resp = client.post("/analyze", json={"project_path": str(project_dir)})
        task_id = resp.json()["task_id"]
        assert started.wait(timeout=5)

        # Poll until the watchdog has marked it failed.
        import time as _t
        deadline = _t.time() + 5
        status = None
        while _t.time() < deadline:
            status = client.get(f"/result/{task_id}").json()["status"]
            if status == "failed":
                break
            _t.sleep(0.05)
        assert status == "failed"
        assert "Timeout" in (client.get(f"/result/{task_id}").json().get("error") or "")


# ── Rate limiter eviction / bounding (audit H-3) ──────────────────────────────

class TestRateLimiter:
    from collections import deque as _deque

    def test_returns_429_after_max(self, monkeypatch):
        monkeypatch.setattr(main_mod, "_RL_MAX", 3)
        for _ in range(3):
            main_mod._rate_limit_check("1.2.3.4")  # 3 allowed
        with pytest.raises(Exception) as exc:
            main_mod._rate_limit_check("1.2.3.4")  # 4th rejected
        assert getattr(exc.value, "status_code", None) == 429

    def test_distinct_ips_tracked_separately(self, monkeypatch):
        monkeypatch.setattr(main_mod, "_RL_MAX", 1)
        main_mod._rate_limit_check("a")
        main_mod._rate_limit_check("b")  # different IP, own quota — no raise
        assert set(main_mod._rl_store) >= {"a", "b"}

    def test_sweep_evicts_fully_expired_ip(self):
        from collections import deque
        old = 100.0
        main_mod._rl_store["stale"] = deque([old])
        # sweep at a time past the window — the IP's only entry has expired
        main_mod._rl_sweep(old + main_mod._RL_WINDOW + 1)
        assert "stale" not in main_mod._rl_store

    def test_sweep_keeps_active_ip(self):
        from collections import deque
        now = 1000.0
        main_mod._rl_store["active"] = deque([now])
        main_mod._rl_sweep(now + 1)  # entry still within window
        assert "active" in main_mod._rl_store

    def test_silent_client_evicted_on_next_periodic_sweep(self, monkeypatch):
        """A client that stops sending requests must not linger forever."""
        from collections import deque
        # Seed a stale IP with an old timestamp and force the periodic sweep path.
        main_mod._rl_store["ghost"] = deque([0.0])
        main_mod._rl_last_sweep = 0.0  # ensure now - last_sweep > window triggers sweep
        # A fresh request from a different IP triggers the time-based sweep.
        main_mod._rate_limit_check("fresh")
        assert "ghost" not in main_mod._rl_store
        assert "fresh" in main_mod._rl_store

    def test_hard_cap_forces_sweep_for_new_ip(self, monkeypatch):
        from collections import deque
        monkeypatch.setattr(main_mod, "_RL_MAX_CLIENTS", 2)
        # Fill the store to the cap with stale entries, and disable the
        # time-based sweep so only the cap path can clean up.
        main_mod._rl_store.clear()
        main_mod._rl_store["s1"] = deque([0.0])
        main_mod._rl_store["s2"] = deque([0.0])
        main_mod._rl_last_sweep = main_mod.time.monotonic()  # skip periodic sweep
        main_mod._rate_limit_check("newcomer")  # hits cap → forced sweep clears stale
        assert "newcomer" in main_mod._rl_store
        assert len(main_mod._rl_store) <= main_mod._RL_MAX_CLIENTS
