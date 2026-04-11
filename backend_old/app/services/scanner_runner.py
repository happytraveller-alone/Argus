from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional

import docker

from app.core.config import settings


SCANNER_MOUNT_PATH = "/scan"
MAX_RETAINED_LOG_CHARS = 12000
DOCKER_EXCEPTION = getattr(getattr(docker, "errors", None), "DockerException", Exception)
DOCKER_NOT_FOUND = getattr(getattr(docker, "errors", None), "NotFound", Exception)


@dataclass
class ScannerRunSpec:
    scanner_type: str
    image: str
    workspace_dir: str
    command: list[str]
    timeout_seconds: int
    env: Dict[str, str]
    expected_exit_codes: list[int] = field(default_factory=lambda: [0])
    artifact_paths: list[str] = field(default_factory=list)
    capture_stdout_path: str | None = None
    capture_stderr_path: str | None = None


@dataclass
class ScannerRunResult:
    success: bool
    container_id: str | None
    exit_code: int
    stdout_path: str | None
    stderr_path: str | None
    error: str | None


def _truncate_log_text(text: str, *, max_chars: int = MAX_RETAINED_LOG_CHARS) -> str:
    normalized = str(text or "")
    if len(normalized) <= max_chars:
        return normalized

    tail_chars = max(0, max_chars - 64)
    omitted_chars = len(normalized) - tail_chars
    return f"[truncated {omitted_chars} chars]\n{normalized[-tail_chars:]}"


def _write_retained_log(path: Path, text: str) -> str | None:
    content = _truncate_log_text(text)
    if not content.strip():
        return None

    path.write_text(content, encoding="utf-8")
    return str(path)


def _write_full_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or ""), encoding="utf-8")
    return str(path)


def _ensure_workspace_artifacts(workspace_dir: str) -> tuple[Path, Path, Path]:
    workspace = Path(workspace_dir)
    logs_dir = workspace / "logs"
    meta_dir = workspace / "meta"
    logs_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    return workspace, logs_dir, meta_dir


def _scan_workspace_root() -> Path:
    configured = str(getattr(settings, "SCAN_WORKSPACE_ROOT", "/tmp/vulhunter/scans") or "").strip()
    return Path(configured or "/tmp/vulhunter/scans")


def _scan_workspace_volume() -> str:
    configured = str(getattr(settings, "SCAN_WORKSPACE_VOLUME", "vulhunter_scan_workspace") or "").strip()
    return configured or "vulhunter_scan_workspace"


def _resolve_shared_workspace(workspace: Path) -> tuple[Path, Path]:
    workspace_root = _scan_workspace_root()
    resolved_workspace = workspace.resolve()
    resolved_root = workspace_root.resolve()
    try:
        resolved_workspace.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(
            f"workspace_dir must stay inside shared workspace root: workspace={resolved_workspace} root={resolved_root}"
        ) from exc
    return resolved_root, resolved_workspace


def _rewrite_mount_path(value: str, workspace: Path) -> str:
    if value == SCANNER_MOUNT_PATH:
        return str(workspace)
    if value.startswith(f"{SCANNER_MOUNT_PATH}/"):
        return str(workspace / value[len(f'{SCANNER_MOUNT_PATH}/'):])
    return value


def _rewrite_runner_command(command: list[str], workspace: Path) -> list[str]:
    return [_rewrite_mount_path(part, workspace) for part in command]


def _rewrite_runner_env(env: Dict[str, str], workspace: Path) -> Dict[str, str]:
    return {key: _rewrite_mount_path(str(value), workspace) for key, value in dict(env).items()}


def run_scanner_container_sync(
    spec: ScannerRunSpec,
    *,
    on_container_started: Callable[[str], None] | None = None,
) -> ScannerRunResult:
    workspace, logs_dir, meta_dir = _ensure_workspace_artifacts(spec.workspace_dir)
    stdout_log_path = logs_dir / "stdout.log"
    stderr_log_path = logs_dir / "stderr.log"
    runner_meta_path = meta_dir / "runner.json"
    container = None
    container_id: Optional[str] = None
    expected_exit_codes = {int(code) for code in (spec.expected_exit_codes or [0])}

    try:
        workspace_root, runner_workspace = _resolve_shared_workspace(workspace)
        rewritten_command = _rewrite_runner_command(spec.command, runner_workspace)
        rewritten_env = _rewrite_runner_env(spec.env, runner_workspace)
        workspace_volume = _scan_workspace_volume()
        client = docker.from_env()
        container = client.containers.run(
            spec.image,
            rewritten_command,
            detach=True,
            auto_remove=False,
            volumes={workspace_volume: {"bind": str(workspace_root), "mode": "rw"}},
            environment=rewritten_env,
            working_dir=str(runner_workspace),
        )
        container_id = getattr(container, "id", None)
        if container_id and on_container_started is not None:
            on_container_started(container_id)
        wait_result = container.wait(timeout=max(1, int(spec.timeout_seconds)))
        exit_code = int((wait_result or {}).get("StatusCode", 1))
        stdout_text = ""
        stderr_text = ""
        if spec.capture_stdout_path is not None or exit_code != 0:
            stdout_text = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        if spec.capture_stderr_path is not None or exit_code != 0:
            stderr_text = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
        retained_stdout_path: str | None = None
        retained_stderr_path: str | None = None
        captured_stdout_path: str | None = None
        captured_stderr_path: str | None = None
        if spec.capture_stdout_path:
            captured_stdout_path = _write_full_text(workspace / spec.capture_stdout_path, stdout_text)
        if spec.capture_stderr_path:
            captured_stderr_path = _write_full_text(workspace / spec.capture_stderr_path, stderr_text)
        keep_logs = exit_code != 0
        if keep_logs:
            retained_stdout_path = _write_retained_log(stdout_log_path, stdout_text)
            retained_stderr_path = _write_retained_log(stderr_log_path, stderr_text)
        log_retention = "nonzero_exit" if keep_logs else "dropped"
        runner_meta_path.write_text(
            json.dumps(
                {
                    "spec": asdict(spec),
                    "runner_command": rewritten_command,
                    "runner_environment": rewritten_env,
                    "workspace_volume": workspace_volume,
                    "workspace_root": str(workspace_root),
                    "container_id": container_id,
                    "exit_code": exit_code,
                    "success": exit_code in expected_exit_codes,
                    "stdout_path": captured_stdout_path or retained_stdout_path,
                    "stderr_path": captured_stderr_path or retained_stderr_path,
                    "log_retention": log_retention,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return ScannerRunResult(
            success=exit_code in expected_exit_codes,
            container_id=container_id,
            exit_code=exit_code,
            stdout_path=captured_stdout_path or retained_stdout_path,
            stderr_path=captured_stderr_path or retained_stderr_path,
            error=None if exit_code in expected_exit_codes else f"scanner container exited with code {exit_code}",
        )
    except DOCKER_EXCEPTION as exc:
        retained_stderr_path = _write_retained_log(stderr_log_path, str(exc))
        runner_meta_path.write_text(
            json.dumps(
                {
                    "spec": asdict(spec),
                    "workspace_volume": _scan_workspace_volume(),
                    "container_id": container_id,
                    "error": str(exc),
                    "success": False,
                    "stdout_path": None,
                    "stderr_path": retained_stderr_path,
                    "log_retention": "failure_only",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return ScannerRunResult(
            success=False,
            container_id=container_id,
            exit_code=1,
            stdout_path=None,
            stderr_path=retained_stderr_path,
            error=str(exc),
        )
    except ValueError as exc:
        retained_stderr_path = _write_retained_log(stderr_log_path, str(exc))
        runner_meta_path.write_text(
            json.dumps(
                {
                    "spec": asdict(spec),
                    "workspace_volume": _scan_workspace_volume(),
                    "error": str(exc),
                    "success": False,
                    "stdout_path": None,
                    "stderr_path": retained_stderr_path,
                    "log_retention": "failure_only",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return ScannerRunResult(
            success=False,
            container_id=None,
            exit_code=1,
            stdout_path=None,
            stderr_path=retained_stderr_path,
            error=str(exc),
        )
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except DOCKER_EXCEPTION:
                pass


async def run_scanner_container(
    spec: ScannerRunSpec,
    *,
    on_container_started: Callable[[str], None] | None = None,
) -> ScannerRunResult:
    return await asyncio.to_thread(
        run_scanner_container_sync,
        spec,
        on_container_started=on_container_started,
    )


def stop_scanner_container_sync(container_id: str) -> bool:
    try:
        client = docker.from_env()
        container = client.containers.get(container_id)
    except DOCKER_NOT_FOUND:
        return False

    container.stop(timeout=2)
    container.remove(force=True)
    return True


async def stop_scanner_container(container_id: str) -> bool:
    return await asyncio.to_thread(stop_scanner_container_sync, container_id)
