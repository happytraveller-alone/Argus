from pathlib import Path
from types import SimpleNamespace

from app.services.agent import scanner_runner


def test_run_scanner_container_passes_mounts_env_and_command(tmp_path, monkeypatch):
    workspace_root = tmp_path / "scan-root"
    workspace_dir = workspace_root / "yasa" / "task-1"
    workspace_dir.mkdir(parents=True)
    seen = {}

    class _FakeContainer:
        id = "container-xyz"

        def wait(self, timeout=None):
            seen["wait_timeout"] = timeout
            return {"StatusCode": 0}

        def logs(self, stdout=True, stderr=False):
            if stdout and not stderr:
                return b"runner stdout"
            if stderr and not stdout:
                return b"runner stderr"
            return b""

        def remove(self, force=False):
            seen["removed"] = force

    class _FakeContainers:
        def run(self, image, command, detach, auto_remove, volumes, environment, working_dir):
            seen["image"] = image
            seen["command"] = command
            seen["detach"] = detach
            seen["auto_remove"] = auto_remove
            seen["volumes"] = volumes
            seen["environment"] = environment
            seen["working_dir"] = working_dir
            return _FakeContainer()

    monkeypatch.setattr(
        scanner_runner.docker,
        "from_env",
        lambda: SimpleNamespace(containers=_FakeContainers()),
        raising=False,
    )
    monkeypatch.setattr(scanner_runner.settings, "SCAN_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setattr(scanner_runner.settings, "SCAN_WORKSPACE_VOLUME", "vulhunter_scan_workspace")

    spec = scanner_runner.ScannerRunSpec(
        scanner_type="yasa",
        image="vulhunter/yasa-runner:latest",
        workspace_dir=str(workspace_dir),
        command=["/opt/yasa/bin/yasa", "--project", "/scan/project", "--help"],
        timeout_seconds=123,
        env={"YASA_RESOURCE_DIR": "/scan/resource"},
    )

    result = scanner_runner.run_scanner_container_sync(spec)

    assert result.success is True
    assert result.container_id == "container-xyz"
    assert result.exit_code == 0
    assert seen["image"] == "vulhunter/yasa-runner:latest"
    assert seen["command"] == [
        "/opt/yasa/bin/yasa",
        "--project",
        f"{workspace_dir}/project",
        "--help",
    ]
    assert seen["detach"] is True
    assert seen["auto_remove"] is False
    assert seen["working_dir"] == str(workspace_dir)
    assert seen["environment"] == {"YASA_RESOURCE_DIR": f"{workspace_dir}/resource"}
    assert seen["volumes"] == {
        "vulhunter_scan_workspace": {"bind": str(workspace_root), "mode": "rw"},
    }
    assert seen["wait_timeout"] == 123
    assert result.stdout_path is None
    assert result.stderr_path is None
    assert not (workspace_dir / "logs" / "stdout.log").exists()
    assert not (workspace_dir / "logs" / "stderr.log").exists()
    runner_meta = (workspace_dir / "meta" / "runner.json").read_text(encoding="utf-8")
    assert '"exit_code": 0' in runner_meta
    assert '"stdout_path": null' in runner_meta
    assert '"stderr_path": null' in runner_meta


def test_run_scanner_container_failure_keeps_truncated_error_logs(tmp_path, monkeypatch):
    workspace_root = tmp_path / "scan-root"
    workspace_dir = workspace_root / "phpstan" / "task-1"
    workspace_dir.mkdir(parents=True)

    long_stderr = "fatal stderr line " * 1200

    class _FakeContainer:
        id = "container-failed"

        def wait(self, timeout=None):
            return {"StatusCode": 2}

        def logs(self, stdout=True, stderr=False):
            if stdout and not stderr:
                return b""
            if stderr and not stdout:
                return long_stderr.encode("utf-8")
            return b""

        def remove(self, force=False):
            return None

    class _FakeContainers:
        def run(self, image, command, detach, auto_remove, volumes, environment, working_dir):
            return _FakeContainer()

    monkeypatch.setattr(
        scanner_runner.docker,
        "from_env",
        lambda: SimpleNamespace(containers=_FakeContainers()),
        raising=False,
    )
    monkeypatch.setattr(scanner_runner.settings, "SCAN_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setattr(scanner_runner.settings, "SCAN_WORKSPACE_VOLUME", "vulhunter_scan_workspace")

    spec = scanner_runner.ScannerRunSpec(
        scanner_type="phpstan",
        image="vulhunter/phpstan-runner:latest",
        workspace_dir=str(workspace_dir),
        command=["phpstan", "analyse", "/scan/project"],
        timeout_seconds=90,
        env={},
    )

    result = scanner_runner.run_scanner_container_sync(spec)

    assert result.success is False
    assert result.exit_code == 2
    assert result.stderr_path is not None
    stderr_path = Path(result.stderr_path)
    assert stderr_path.exists()
    stderr_text = stderr_path.read_text(encoding="utf-8")
    assert "fatal stderr line" in stderr_text
    assert len(stderr_text) < len(long_stderr)
    runner_meta = (workspace_dir / "meta" / "runner.json").read_text(encoding="utf-8")
    assert '"exit_code": 2' in runner_meta
    assert '"stderr_path":' in runner_meta


def test_run_scanner_container_expected_nonzero_exit_keeps_logs(tmp_path, monkeypatch):
    workspace_root = tmp_path / "scan-root"
    workspace_dir = workspace_root / "phpstan" / "task-1"
    workspace_dir.mkdir(parents=True)

    class _FakeContainer:
        id = "container-expected-nonzero"

        def wait(self, timeout=None):
            return {"StatusCode": 1}

        def logs(self, stdout=True, stderr=False):
            if stdout and not stderr:
                return b"runner stdout"
            if stderr and not stdout:
                return b"runner stderr"
            return b""

        def remove(self, force=False):
            return None

    class _FakeContainers:
        def run(self, image, command, detach, auto_remove, volumes, environment, working_dir):
            return _FakeContainer()

    monkeypatch.setattr(
        scanner_runner.docker,
        "from_env",
        lambda: SimpleNamespace(containers=_FakeContainers()),
        raising=False,
    )
    monkeypatch.setattr(scanner_runner.settings, "SCAN_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setattr(scanner_runner.settings, "SCAN_WORKSPACE_VOLUME", "vulhunter_scan_workspace")

    spec = scanner_runner.ScannerRunSpec(
        scanner_type="phpstan",
        image="vulhunter/phpstan-runner:latest",
        workspace_dir=str(workspace_dir),
        command=["phpstan", "analyse", "/scan/project"],
        timeout_seconds=90,
        env={},
        expected_exit_codes=[0, 1],
    )

    result = scanner_runner.run_scanner_container_sync(spec)

    assert result.success is True
    assert result.exit_code == 1
    assert result.stdout_path is not None
    assert result.stderr_path is not None
    assert Path(result.stdout_path).read_text(encoding="utf-8") == "runner stdout"
    assert Path(result.stderr_path).read_text(encoding="utf-8") == "runner stderr"
    runner_meta = (workspace_dir / "meta" / "runner.json").read_text(encoding="utf-8")
    assert '"success": true' in runner_meta
    assert '"log_retention": "nonzero_exit"' in runner_meta


def test_run_scanner_container_rejects_workspace_outside_shared_root(tmp_path, monkeypatch):
    workspace_root = tmp_path / "scan-root"
    workspace_root.mkdir()

    monkeypatch.setattr(scanner_runner.settings, "SCAN_WORKSPACE_ROOT", str(workspace_root))
    monkeypatch.setattr(scanner_runner.settings, "SCAN_WORKSPACE_VOLUME", "vulhunter_scan_workspace")

    spec = scanner_runner.ScannerRunSpec(
        scanner_type="phpstan",
        image="vulhunter/phpstan-runner:latest",
        workspace_dir=str(tmp_path / "elsewhere" / "task-1"),
        command=["phpstan", "analyse", "/scan/project"],
        timeout_seconds=90,
        env={},
    )

    result = scanner_runner.run_scanner_container_sync(spec)

    assert result.success is False
    assert result.error is not None
    assert "shared workspace root" in result.error


def test_stop_scan_container_handles_missing_container_gracefully(monkeypatch):
    class _FakeContainers:
        def get(self, _container_id):
            raise scanner_runner.docker.errors.NotFound("missing")

    monkeypatch.setattr(
        scanner_runner.docker,
        "errors",
        SimpleNamespace(NotFound=RuntimeError),
        raising=False,
    )
    monkeypatch.setattr(
        scanner_runner.docker,
        "from_env",
        lambda: SimpleNamespace(containers=_FakeContainers()),
        raising=False,
    )

    assert scanner_runner.stop_scanner_container_sync("missing-container") is False
