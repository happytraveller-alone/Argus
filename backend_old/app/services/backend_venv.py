from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Mapping, Optional

from app.core.config import settings


def get_backend_venv_path() -> Path:
    configured = str(getattr(settings, "BACKEND_VENV_PATH", "/opt/backend-venv") or "").strip()
    return Path(configured or "/opt/backend-venv")


def get_backend_venv_bin_dir() -> Path:
    return get_backend_venv_path() / "bin"


def resolve_backend_venv_executable(
    name: str,
    *,
    required: bool = True,
) -> Optional[str]:
    candidate = get_backend_venv_bin_dir() / str(name).strip()
    if candidate.is_file():
        return str(candidate)
    if required:
        raise FileNotFoundError(
            f"backend venv executable not found: {candidate} (BACKEND_VENV_PATH={get_backend_venv_path()})"
        )
    return None


def build_backend_venv_env(
    base_env: Optional[Mapping[str, str]] = None,
) -> Dict[str, str]:
    env = dict(os.environ if base_env is None else base_env)
    venv_path = str(get_backend_venv_path())
    bin_path = str(get_backend_venv_bin_dir())
    current_path = env.get("PATH", "")

    if current_path:
        path_parts = [part for part in current_path.split(":") if part]
        if not path_parts or path_parts[0] != bin_path:
            env["PATH"] = ":".join([bin_path, *path_parts])
    else:
        env["PATH"] = bin_path

    env["VIRTUAL_ENV"] = venv_path
    env["PYTHONNOUSERSITE"] = "1"
    return env
