from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional

import docker


SCANNER_MOUNT_PATH = "/scan"
MAX_RETAINED_LOG_CHARS = 12000


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


def _ensure_workspace_artifacts(workspace_dir: str) -> tuple[Path, Path, Path]:
    workspace = Path(workspace_dir)
    logs_dir = workspace / "logs"
    meta_dir = workspace / "meta"
    logs_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    return workspace, logs_dir, meta_dir


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
        client = docker.from_env()
        container = client.containers.run(
            spec.image,
            spec.command,
            detach=True,
            auto_remove=False,
            volumes={str(workspace): {"bind": SCANNER_MOUNT_PATH, "mode": "rw"}},
            environment=dict(spec.env),
            working_dir=SCANNER_MOUNT_PATH,
        )
        container_id = getattr(container, "id", None)
        if container_id and on_container_started is not None:
            on_container_started(container_id)
        wait_result = container.wait(timeout=max(1, int(spec.timeout_seconds)))
        exit_code = int((wait_result or {}).get("StatusCode", 1))
        retained_stdout_path: str | None = None
        retained_stderr_path: str | None = None
        keep_logs = exit_code != 0
        if keep_logs:
            stdout_text = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr_text = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            retained_stdout_path = _write_retained_log(stdout_log_path, stdout_text)
            retained_stderr_path = _write_retained_log(stderr_log_path, stderr_text)
        log_retention = "nonzero_exit" if keep_logs else "dropped"
        runner_meta_path.write_text(
            json.dumps(
                {
                    "spec": asdict(spec),
                    "container_id": container_id,
                    "exit_code": exit_code,
                    "success": exit_code in expected_exit_codes,
                    "stdout_path": retained_stdout_path,
                    "stderr_path": retained_stderr_path,
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
            stdout_path=retained_stdout_path,
            stderr_path=retained_stderr_path,
            error=None if exit_code in expected_exit_codes else f"scanner container exited with code {exit_code}",
        )
    except docker.errors.DockerException as exc:
        retained_stderr_path = _write_retained_log(stderr_log_path, str(exc))
        runner_meta_path.write_text(
            json.dumps(
                {
                    "spec": asdict(spec),
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
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except docker.errors.DockerException:
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
    except docker.errors.NotFound:
        return False

    container.stop(timeout=2)
    container.remove(force=True)
    return True


async def stop_scanner_container(container_id: str) -> bool:
    return await asyncio.to_thread(stop_scanner_container_sync, container_id)
