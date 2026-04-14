from __future__ import annotations

import shutil
from pathlib import Path

from app.core.config import settings


def _scan_workspace_root() -> Path:
    configured = str(getattr(settings, "SCAN_WORKSPACE_ROOT", "/tmp/vulhunter/scans") or "").strip()
    return Path(configured or "/tmp/vulhunter/scans")


def ensure_scan_workspace(scan_type: str, task_id: str) -> Path:
    workspace = _scan_workspace_root() / str(scan_type).strip() / str(task_id).strip()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _ensure_scan_subdir(scan_type: str, task_id: str, name: str) -> Path:
    path = ensure_scan_workspace(scan_type, task_id) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_scan_project_dir(scan_type: str, task_id: str) -> Path:
    return _ensure_scan_subdir(scan_type, task_id, "project")


def ensure_scan_output_dir(scan_type: str, task_id: str) -> Path:
    return _ensure_scan_subdir(scan_type, task_id, "output")


def ensure_scan_logs_dir(scan_type: str, task_id: str) -> Path:
    return _ensure_scan_subdir(scan_type, task_id, "logs")


def ensure_scan_meta_dir(scan_type: str, task_id: str) -> Path:
    return _ensure_scan_subdir(scan_type, task_id, "meta")


def cleanup_scan_workspace(scan_type: str, task_id: str) -> None:
    workspace = _scan_workspace_root() / str(scan_type).strip() / str(task_id).strip()
    shutil.rmtree(workspace, ignore_errors=True)


def copy_project_tree_to_scan_dir(project_root: str | Path, project_dir: str | Path) -> None:
    src_root = Path(project_root).resolve()
    dst_root = Path(project_dir).resolve()

    if src_root == dst_root:
        raise ValueError("project_dir must differ from project_root")

    dst_root.parent.mkdir(parents=True, exist_ok=True)

    def _should_ignore(candidate: Path) -> bool:
        resolved = candidate.resolve()
        try:
            dst_root.relative_to(resolved)
            return True
        except ValueError:
            return False

    def _ignore(_current_dir: str, names: list[str]) -> set[str]:
        current = Path(_current_dir).resolve()
        ignored: set[str] = set()
        for name in names:
            if _should_ignore(current / name):
                ignored.add(name)
        return ignored

    shutil.copytree(src_root, dst_root, dirs_exist_ok=True, ignore=_ignore)
