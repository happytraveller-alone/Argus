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

import app.services.agent.scan_tracking as scan_tracking

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_static_scan_runtime_shell_has_been_retired():
    assert not (PROJECT_ROOT / "app/services/static_scan_runtime.py").exists()


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
