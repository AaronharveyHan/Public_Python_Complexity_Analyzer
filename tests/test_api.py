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
    yield
    tasks_mod._store.clear()
    tasks_mod._ws_queues.clear()
    tasks_mod._reset_db()
    main_mod._rl_store.clear()


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
