"""Gitleaks bootstrap runtime helpers."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from app.services.agent.bootstrap_findings import _parse_bootstrap_gitleaks_output


async def _prepare_scan_project_dir_async(
    project_root: str,
    project_dir: str | Path,
    *,
    copy_project_tree_to_scan_dir_fn: Optional[Callable[[str | Path, str | Path], None]] = None,
) -> None:
    if copy_project_tree_to_scan_dir_fn is None:
        from app.services.static_scan_runtime import copy_project_tree_to_scan_dir as copy_fn

        copy_project_tree_to_scan_dir_fn = copy_fn

    await asyncio.to_thread(shutil.rmtree, project_dir, True)
    await asyncio.to_thread(copy_project_tree_to_scan_dir_fn, project_root, project_dir)


async def _run_bootstrap_gitleaks_scan(
    project_root: str,
    *,
    ensure_scan_workspace_fn: Optional[Callable[[str, str], Path]] = None,
    ensure_scan_project_dir_fn: Optional[Callable[[str, str], Path]] = None,
    ensure_scan_output_dir_fn: Optional[Callable[[str, str], Path]] = None,
    ensure_scan_logs_dir_fn: Optional[Callable[[str, str], Path]] = None,
    ensure_scan_meta_dir_fn: Optional[Callable[[str, str], Path]] = None,
    prepare_scan_project_dir_async_fn: Optional[Callable[..., Any]] = None,
    run_scanner_container_fn: Optional[Callable[[Any], Any]] = None,
    cleanup_scan_workspace_fn: Optional[Callable[[str, str], None]] = None,
    scanner_run_spec_cls: Optional[type] = None,
    scanner_gitleaks_image: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if ensure_scan_workspace_fn is None:
        from app.services.static_scan_runtime import ensure_scan_workspace as ensure_fn

        ensure_scan_workspace_fn = ensure_fn
    if ensure_scan_project_dir_fn is None:
        from app.services.static_scan_runtime import ensure_scan_project_dir as ensure_fn

        ensure_scan_project_dir_fn = ensure_fn
    if ensure_scan_output_dir_fn is None:
        from app.services.static_scan_runtime import ensure_scan_output_dir as ensure_fn

        ensure_scan_output_dir_fn = ensure_fn
    if ensure_scan_logs_dir_fn is None:
        from app.services.static_scan_runtime import ensure_scan_logs_dir as ensure_fn

        ensure_scan_logs_dir_fn = ensure_fn
    if ensure_scan_meta_dir_fn is None:
        from app.services.static_scan_runtime import ensure_scan_meta_dir as ensure_fn

        ensure_scan_meta_dir_fn = ensure_fn
    if prepare_scan_project_dir_async_fn is None:
        prepare_scan_project_dir_async_fn = _prepare_scan_project_dir_async
    if run_scanner_container_fn is None:
        from app.services.scanner_runner import run_scanner_container as run_fn

        run_scanner_container_fn = run_fn
    if cleanup_scan_workspace_fn is None:
        from app.services.static_scan_runtime import cleanup_scan_workspace as cleanup_fn

        cleanup_scan_workspace_fn = cleanup_fn
    if scanner_gitleaks_image is None:
        from app.core.config import settings

        scanner_gitleaks_image = str(
            getattr(settings, "SCANNER_GITLEAKS_IMAGE", "vulhunter/gitleaks-runner:latest")
        )
    if scanner_run_spec_cls is None:
        from app.services.scanner_runner import ScannerRunSpec

        scanner_run_spec_cls = ScannerRunSpec

    task_id = f"bootstrap-{uuid4().hex}"
    workspace_dir = ensure_scan_workspace_fn("gitleaks-bootstrap", task_id)
    project_dir = ensure_scan_project_dir_fn("gitleaks-bootstrap", task_id)
    output_dir = ensure_scan_output_dir_fn("gitleaks-bootstrap", task_id)
    logs_dir = ensure_scan_logs_dir_fn("gitleaks-bootstrap", task_id)
    meta_dir = ensure_scan_meta_dir_fn("gitleaks-bootstrap", task_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "report.json"

    try:
        await prepare_scan_project_dir_async_fn(project_root, project_dir)

        cmd = [
            "gitleaks",
            "detect",
            "--source",
            "/scan/project",
            "--report-format",
            "json",
            "--report-path",
            "/scan/output/report.json",
            "--exit-code",
            "0",
            "--no-git",
        ]
        result = await run_scanner_container_fn(
            scanner_run_spec_cls(
                scanner_type="gitleaks-bootstrap",
                image=str(scanner_gitleaks_image),
                workspace_dir=str(workspace_dir),
                command=cmd,
                timeout_seconds=900,
                env={},
            )
        )
        if result.exit_code != 0:
            stderr_text = ""
            stdout_text = ""
            if result.stderr_path and Path(result.stderr_path).exists():
                stderr_text = Path(result.stderr_path).read_text(encoding="utf-8", errors="ignore")
            if result.stdout_path and Path(result.stdout_path).exists():
                stdout_text = Path(result.stdout_path).read_text(encoding="utf-8", errors="ignore")
            error_text = (stderr_text or stdout_text or result.error or "unknown error").strip()
            raise RuntimeError(f"gitleaks failed: {error_text[:300]}")

        if not report_path.exists():
            return []
        report_content = report_path.read_text(encoding="utf-8", errors="ignore")
        return _parse_bootstrap_gitleaks_output(report_content)
    finally:
        cleanup_scan_workspace_fn("gitleaks-bootstrap", task_id)
