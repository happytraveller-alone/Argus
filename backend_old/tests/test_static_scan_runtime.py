import sys
import types
import subprocess
import threading
import time
from pathlib import Path

import pytest

docker_stub = types.ModuleType("docker")
docker_stub.from_env = lambda: None
docker_stub.errors = types.SimpleNamespace(
    DockerException=RuntimeError,
    ImageNotFound=type("ImageNotFound", (Exception,), {}),
)
sys.modules.setdefault("docker", docker_stub)

from app.services.agent import scan_tracking, scan_workspace

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_static_scan_runtime_shell_has_been_retired():
    assert not (PROJECT_ROOT / "app/services/static_scan_runtime.py").exists()


def test_ensure_scan_workspace_under_configured_root(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_workspace.settings, "SCAN_WORKSPACE_ROOT", str(tmp_path))

    workspace = scan_workspace.ensure_scan_workspace("phpstan", "task-123")

    assert workspace == tmp_path / "phpstan" / "task-123"
    assert workspace.is_dir()


def test_ensure_scan_project_and_output_dirs_are_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_workspace.settings, "SCAN_WORKSPACE_ROOT", str(tmp_path))

    project_dir = scan_workspace.ensure_scan_project_dir("phpstan", "task-456")
    output_dir = scan_workspace.ensure_scan_output_dir("phpstan", "task-456")
    logs_dir = scan_workspace.ensure_scan_logs_dir("phpstan", "task-456")
    meta_dir = scan_workspace.ensure_scan_meta_dir("phpstan", "task-456")

    assert project_dir == tmp_path / "phpstan" / "task-456" / "project"
    assert output_dir == tmp_path / "phpstan" / "task-456" / "output"
    assert logs_dir == tmp_path / "phpstan" / "task-456" / "logs"
    assert meta_dir == tmp_path / "phpstan" / "task-456" / "meta"
    assert project_dir.is_dir()
    assert output_dir.is_dir()
    assert logs_dir.is_dir()
    assert meta_dir.is_dir()


def test_cleanup_scan_workspace_removes_task_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(scan_workspace.settings, "SCAN_WORKSPACE_ROOT", str(tmp_path))

    workspace = scan_workspace.ensure_scan_workspace("phpstan", "task-cleanup")
    marker = workspace / "output" / "report.sarif"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}", encoding="utf-8")

    scan_workspace.cleanup_scan_workspace("phpstan", "task-cleanup")

    assert not workspace.exists()


def test_copy_project_tree_to_scan_dir_ignores_nested_destination(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "src").mkdir()
    (project_root / "src" / "app.py").write_text("dangerous()\n", encoding="utf-8")
    nested_scan_dir = project_root / "scans" / "opengrep" / "task-1" / "project"

    scan_workspace.copy_project_tree_to_scan_dir(project_root, nested_scan_dir)

    assert (nested_scan_dir / "src" / "app.py").read_text(encoding="utf-8") == "dangerous()\n"
    assert not (nested_scan_dir / "scans").exists()


def test_scan_container_registry_tracks_container_id():
    scan_tracking._static_running_scan_containers.clear()

    scan_tracking._register_scan_container("phpstan", "task-container", "container-123")

    assert (
        scan_tracking._static_running_scan_containers[
            scan_tracking._scan_task_key("phpstan", "task-container")
        ]
        == "container-123"
    )
    assert scan_tracking._pop_scan_container("phpstan", "task-container") == "container-123"


def test_scan_process_active_and_cancel_uses_shared_tracking():
    task_id = "shared-cancel-1"
    result_holder: dict[str, object] = {}

    def _runner():
        result_holder["result"] = scan_tracking._run_subprocess_with_tracking(
            "phpstan",
            task_id,
            ["bash", "-lc", "sleep 5"],
            timeout=10,
        )

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    time.sleep(0.2)

    assert scan_tracking._is_scan_process_active("phpstan", task_id) is True
    assert scan_tracking._request_scan_task_cancel("phpstan", task_id) is True

    worker.join(timeout=5)
    assert worker.is_alive() is False
    assert scan_tracking._is_scan_process_active("phpstan", task_id) is False
    assert "result" in result_holder
    completed = result_holder["result"]
    assert isinstance(completed, subprocess.CompletedProcess)
    assert completed.returncode != 0


def test_scan_process_timeout_cleans_tracking_state():
    task_id = "shared-timeout-1"
    with pytest.raises(subprocess.TimeoutExpired):
        scan_tracking._run_subprocess_with_tracking(
            "phpstan",
            task_id,
            ["bash", "-lc", "sleep 3"],
            timeout=1,
        )

    assert scan_tracking._is_scan_process_active("phpstan", task_id) is False
