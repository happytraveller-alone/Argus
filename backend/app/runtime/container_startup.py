from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_PYPI_INDEX_CANDIDATES = (
    "https://mirrors.aliyun.com/pypi/simple/,"
    "https://pypi.tuna.tsinghua.edu.cn/simple,"
    "https://pypi.mirrors.ustc.edu.cn/simple/,"
    "https://pypi.org/simple"
)


def _is_true(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _venv_bin(name: str) -> str:
    venv_dir = os.environ.get("BACKEND_VENV_PATH", "/opt/backend-venv")
    return str(Path(venv_dir) / "bin" / name)


def _read_venv_version(venv_dir: Path) -> str:
    cfg_file = venv_dir / "pyvenv.cfg"
    if not cfg_file.exists():
        return ""
    for line in cfg_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("version_info = "):
            return line.split("=", 1)[1].strip()
    return ""


def _venv_can_run_backend(venv_dir: Path) -> bool:
    python_bin = venv_dir / "bin" / "python"
    if not python_bin.exists():
        return False
    result = subprocess.run(
        [str(python_bin), "-c", "import sqlalchemy, alembic, uvicorn"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _ensure_backend_venv() -> None:
    venv_dir = Path(os.environ.get("BACKEND_VENV_PATH", "/opt/backend-venv"))
    current_version = _read_venv_version(venv_dir)
    expected_version = ".".join(str(part) for part in sys.version_info[:3])
    if current_version and current_version == expected_version and _venv_can_run_backend(venv_dir):
        return

    if current_version:
        print(f"Recreating backend virtualenv in {venv_dir} (current={current_version}, expected={expected_version})...")
    else:
        print(f"Creating backend virtualenv in {venv_dir}...")

    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["uv", "venv", "--clear", str(venv_dir)], check=True)


def _compute_lock_hash(app_root: Path) -> str:
    pyproject = app_root / "pyproject.toml"
    lock_file = app_root / "uv.lock"
    if not pyproject.exists() or not lock_file.exists():
        return ""
    digest = hashlib.sha256()
    digest.update(pyproject.read_bytes())
    digest.update(lock_file.read_bytes())
    return digest.hexdigest()


def _get_ordered_pypi_candidates() -> list[str]:
    """Return an ordered list of PyPI indexes to try.

    If UV_INDEX_URL / PIP_INDEX_URL is explicitly set, that single index is used as-is.
    Otherwise, all candidates from PYPI_INDEX_CANDIDATES are ranked by latency via
    package_source_selector.py and returned in order so the caller can fall back on failure.
    """
    explicit = os.environ.get("UV_INDEX_URL") or os.environ.get("PIP_INDEX_URL")
    if explicit:
        return [explicit.strip()]

    raw = os.environ.get("PYPI_INDEX_CANDIDATES", DEFAULT_PYPI_INDEX_CANDIDATES)
    all_candidates = [c.strip() for c in raw.split(",") if c.strip()]

    selector = Path("/usr/local/bin/package_source_selector.py")
    if selector.exists():
        result = subprocess.run(
            [
                "python3",
                str(selector),
                "--candidates",
                raw,
                "--kind",
                "pypi",
                "--timeout-seconds",
                "2",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        ranked = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
        if ranked:
            # Append any candidate not returned by the selector (keep full coverage)
            seen = set(ranked)
            for c in all_candidates:
                if c not in seen:
                    ranked.append(c)
            return ranked

    return all_candidates


def _sync_backend_env_if_needed(app_root: Path) -> None:
    venv_dir = Path(os.environ.get("BACKEND_VENV_PATH", "/opt/backend-venv"))
    stamp_file = venv_dir / ".vulhunter-dev-lock.sha256"

    os.environ["VIRTUAL_ENV"] = str(venv_dir)
    os.environ["PATH"] = f"{venv_dir / 'bin'}:{os.environ.get('PATH', '')}"
    _ensure_backend_venv()

    current_hash = _compute_lock_hash(app_root)
    previous_hash = stamp_file.read_text(encoding="utf-8").strip() if stamp_file.exists() else ""
    if current_hash and current_hash == previous_hash:
        print("Python lockfile unchanged, skip uv sync")
        return

    print("Syncing backend dependencies with uv...")
    Path("/root/.cache/uv").mkdir(parents=True, exist_ok=True)

    candidates = _get_ordered_pypi_candidates()
    print(f"PyPI index candidates: {candidates}")

    for index_url in candidates:
        print(f"uv sync via {index_url} ...")
        env = {**os.environ, "UV_INDEX_URL": index_url, "PIP_INDEX_URL": index_url}
        result = subprocess.run(
            ["uv", "sync", "--active", "--frozen", "--no-dev"],
            cwd=str(app_root),
            env=env,
        )
        if result.returncode == 0:
            # Propagate the successful index for any subsequent pip/uv calls in this process
            os.environ["UV_INDEX_URL"] = index_url
            os.environ["PIP_INDEX_URL"] = index_url
            if current_hash:
                stamp_file.write_text(f"{current_hash}\n", encoding="utf-8")
            return
        print(f"uv sync failed via {index_url} (exit {result.returncode}), trying next index...")

    raise RuntimeError(
        f"uv sync failed on all {len(candidates)} PyPI indexes: {candidates}"
    )


def _wait_for_db(max_retries: int = 30, sleep_seconds: int = 2) -> None:
    print("Waiting for PostgreSQL...")
    script = (
        "import asyncio, os\n"
        "from sqlalchemy import text\n"
        "from sqlalchemy.ext.asyncio import create_async_engine\n"
        "async def check_db():\n"
        "    engine = create_async_engine(os.environ.get('DATABASE_URL', ''))\n"
        "    try:\n"
        "        async with engine.connect() as conn:\n"
        "            await conn.execute(text('SELECT 1'))\n"
        "        return True\n"
        "    except Exception:\n"
        "        return False\n"
        "    finally:\n"
        "        await engine.dispose()\n"
        "raise SystemExit(0 if asyncio.run(check_db()) else 1)\n"
    )
    python_bin = _venv_bin("python")
    for retry in range(max_retries):
        result = subprocess.run([python_bin, "-c", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            print("Database connection ready")
            return
        print(f"Retry {retry + 1}/{max_retries}...")
        time.sleep(sleep_seconds)
    raise RuntimeError("Failed to connect to database")


def _run_database_migrations(app_root: Path) -> None:
    print("Running database migrations...")
    subprocess.run([_venv_bin("alembic"), "upgrade", "head"], cwd=str(app_root), check=True)


def _run_optional_resets(app_root: Path) -> None:
    if _is_true(os.environ.get("RESET_STATIC_SCAN_TABLES_ON_DEPLOY")):
        print("Resetting static scan tables...")
        subprocess.run([_venv_bin("python"), str(app_root / "scripts" / "reset_static_scan_tables.py")], check=True)


def _exec_uvicorn(reload_enabled: bool) -> None:
    args = [_venv_bin("uvicorn"), "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    if reload_enabled:
        args.insert(2, "--reload")
    os.execv(args[0], args)


def run(mode: str) -> None:
    app_root = Path(os.environ.get("BACKEND_APP_ROOT", "/app"))
    os.chdir(app_root)

    if mode == "dev":
        print("Starting VulHunter backend dev container...")
        _sync_backend_env_if_needed(app_root)
    else:
        print("VulHunter 后端启动中...")

    _wait_for_db()
    _run_database_migrations(app_root)
    _run_optional_resets(app_root)
    print("Starting uvicorn...")
    _exec_uvicorn(reload_enabled=(mode == "dev"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("dev", "prod"))
    args = parser.parse_args()
    run(args.mode)


if __name__ == "__main__":
    main()
