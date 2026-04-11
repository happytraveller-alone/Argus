import sys
import types
import subprocess
import threading
import time
from datetime import datetime, timezone

import pytest

docker_stub = types.ModuleType("docker")
docker_stub.from_env = lambda: None
docker_stub.errors = types.SimpleNamespace(
    DockerException=RuntimeError,
    ImageNotFound=type("ImageNotFound", (Exception,), {}),
)
sys.modules.setdefault("docker", docker_stub)

from app.api.v1.endpoints import static_tasks_shared


def test_ensure_scan_workspace_under_configured_root(tmp_path, monkeypatch):
    monkeypatch.setattr(static_tasks_shared.settings, "SCAN_WORKSPACE_ROOT", str(tmp_path))

    workspace = static_tasks_shared.ensure_scan_workspace("phpstan", "task-123")

    assert workspace == tmp_path / "phpstan" / "task-123"
    assert workspace.is_dir()


def test_ensure_scan_project_and_output_dirs_are_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(static_tasks_shared.settings, "SCAN_WORKSPACE_ROOT", str(tmp_path))

    project_dir = static_tasks_shared.ensure_scan_project_dir("phpstan", "task-456")
    output_dir = static_tasks_shared.ensure_scan_output_dir("phpstan", "task-456")
    logs_dir = static_tasks_shared.ensure_scan_logs_dir("phpstan", "task-456")
    meta_dir = static_tasks_shared.ensure_scan_meta_dir("phpstan", "task-456")

    assert project_dir == tmp_path / "phpstan" / "task-456" / "project"
    assert output_dir == tmp_path / "phpstan" / "task-456" / "output"
    assert logs_dir == tmp_path / "phpstan" / "task-456" / "logs"
    assert meta_dir == tmp_path / "phpstan" / "task-456" / "meta"
    assert project_dir.is_dir()
    assert output_dir.is_dir()
    assert logs_dir.is_dir()
    assert meta_dir.is_dir()


def test_cleanup_scan_workspace_removes_task_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(static_tasks_shared.settings, "SCAN_WORKSPACE_ROOT", str(tmp_path))

    workspace = static_tasks_shared.ensure_scan_workspace("phpstan", "task-cleanup")
    marker = workspace / "output" / "report.sarif"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}", encoding="utf-8")

    static_tasks_shared.cleanup_scan_workspace("phpstan", "task-cleanup")

    assert not workspace.exists()


def test_copy_project_tree_to_scan_dir_ignores_nested_destination(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "src").mkdir()
    (project_root / "src" / "app.py").write_text("dangerous()\n", encoding="utf-8")
    nested_scan_dir = project_root / "scans" / "opengrep" / "task-1" / "project"

    static_tasks_shared.copy_project_tree_to_scan_dir(project_root, nested_scan_dir)

    assert (nested_scan_dir / "src" / "app.py").read_text(encoding="utf-8") == "dangerous()\n"
    assert not (nested_scan_dir / "scans").exists()


def test_build_backend_venv_env_prefixes_backend_venv_bin(monkeypatch):
    monkeypatch.setattr(static_tasks_shared.settings, "BACKEND_VENV_PATH", "/opt/backend-venv")

    env = static_tasks_shared._build_backend_venv_env({"PATH": "/usr/local/bin:/usr/bin"})

    assert env["VIRTUAL_ENV"] == "/opt/backend-venv"
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PATH"].startswith("/opt/backend-venv/bin:")


def test_resolve_backend_venv_executable_uses_configured_dir(tmp_path, monkeypatch):
    venv_dir = tmp_path / "backend-venv"
    bin_dir = venv_dir / "bin"
    bin_dir.mkdir(parents=True)
    bandit_bin = bin_dir / "bandit"
    bandit_bin.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(static_tasks_shared.settings, "BACKEND_VENV_PATH", str(venv_dir))

    resolved = static_tasks_shared._resolve_backend_venv_executable("bandit")

    assert resolved == str(bandit_bin)


def test_scan_container_registry_tracks_container_id():
    static_tasks_shared._static_running_scan_containers.clear()

    static_tasks_shared._register_scan_container("phpstan", "task-container", "container-123")

    assert (
        static_tasks_shared._static_running_scan_containers[
            static_tasks_shared._scan_task_key("phpstan", "task-container")
        ]
        == "container-123"
    )
    assert static_tasks_shared._pop_scan_container("phpstan", "task-container") == "container-123"


def test_record_scan_progress_initializes_shared_store():
    task_id = "task-progress-1"
    static_tasks_shared._scan_progress_store.clear()

    static_tasks_shared._record_scan_progress(
        task_id,
        status="pending",
        progress=5,
        stage="pending",
        message="queued",
    )

    state = static_tasks_shared._scan_progress_store[task_id]
    assert state["status"] == "pending"
    assert state["progress"] == 5
    assert state["current_stage"] == "pending"
    assert state["message"] == "queued"
    assert len(state["logs"]) == 1


def test_record_scan_progress_clears_terminal_state():
    task_id = "task-progress-terminal"
    static_tasks_shared._scan_progress_store.clear()

    static_tasks_shared._record_scan_progress(
        task_id,
        status="running",
        progress=42,
        stage="scan",
        message="scanning",
    )

    static_tasks_shared._record_scan_progress(
        task_id,
        status="completed",
        progress=100,
        stage="completed",
        message="done",
    )

    assert task_id not in static_tasks_shared._scan_progress_store


def test_prune_scan_progress_store_removes_expired_entries():
    static_tasks_shared._scan_progress_store.clear()
    now = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
    static_tasks_shared._scan_progress_store.update(
        {
            "expired-task": {
                "task_id": "expired-task",
                "status": "running",
                "progress": 50,
                "current_stage": "scan",
                "message": "old",
                "started_at": "2026-04-10T10:00:00Z",
                "updated_at": "2026-04-10T10:00:00Z",
                "logs": [],
            },
            "fresh-task": {
                "task_id": "fresh-task",
                "status": "running",
                "progress": 10,
                "current_stage": "init",
                "message": "fresh",
                "started_at": "2026-04-10T11:59:45Z",
                "updated_at": "2026-04-10T11:59:45Z",
                "logs": [],
            },
        }
    )

    removed = static_tasks_shared.prune_scan_progress_store(ttl_seconds=60, now=now)

    assert removed == 1
    assert "expired-task" not in static_tasks_shared._scan_progress_store
    assert "fresh-task" in static_tasks_shared._scan_progress_store


def test_scan_process_active_and_cancel_uses_shared_tracking():
    task_id = "shared-cancel-1"
    result_holder: dict[str, object] = {}

    def _runner():
        result_holder["result"] = static_tasks_shared._run_subprocess_with_tracking(
            "phpstan",
            task_id,
            ["bash", "-lc", "sleep 5"],
            timeout=10,
        )

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    time.sleep(0.2)

    assert static_tasks_shared._is_scan_process_active("phpstan", task_id) is True
    assert static_tasks_shared._request_scan_task_cancel("phpstan", task_id) is True

    worker.join(timeout=5)
    assert worker.is_alive() is False
    assert static_tasks_shared._is_scan_process_active("phpstan", task_id) is False
    assert "result" in result_holder
    completed = result_holder["result"]
    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0


def test_scan_process_timeout_cleans_tracking_state():
    task_id = "shared-timeout-1"
    with pytest.raises(subprocess.TimeoutExpired):
        static_tasks_shared._run_subprocess_with_tracking(
            "phpstan",
            task_id,
            ["bash", "-lc", "sleep 3"],
            timeout=1,
        )

    assert static_tasks_shared._is_scan_process_active("phpstan", task_id) is False
