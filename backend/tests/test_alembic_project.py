import os
import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _alembic_command() -> list[str]:
    venv_alembic = BACKEND_ROOT / ".venv" / "bin" / "alembic"
    if venv_alembic.exists():
        return [str(venv_alembic)]
    return [sys.executable, "-m", "alembic"]


def test_alembic_history_runs_from_backend_root():
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{BACKEND_ROOT}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(BACKEND_ROOT)
    )

    result = subprocess.run(
        [*_alembic_command(), "history"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    assert result.returncode == 0, combined_output


def test_alembic_has_a_single_head_revision():
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{BACKEND_ROOT}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(BACKEND_ROOT)
    )

    result = subprocess.run(
        [*_alembic_command(), "heads"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    assert result.returncode == 0, combined_output

    head_lines = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and "(head)" in line
    ]
    assert len(head_lines) == 1, f"Expected a single Alembic head, got {len(head_lines)}: {head_lines}"


def test_alembic_versions_directory_is_squashed_to_baseline_and_bridge():
    versions_dir = BACKEND_ROOT / "alembic" / "versions"
    version_files = sorted(path.name for path in versions_dir.glob("*.py"))

    assert version_files == [
        "5b0f3c9a6d7e_squashed_baseline.py",
        "6c8d9e0f1a2b_finalize_projects_zip_file_hash.py",
        "7f8e9d0c1b2a_normalize_static_finding_paths.py",
    ]


def test_bridge_downgrade_keeps_zip_file_hash_baseline_contract():
    bridge_file = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "6c8d9e0f1a2b_finalize_projects_zip_file_hash.py"
    )
    bridge_source = bridge_file.read_text(encoding="utf-8")

    assert "DROP COLUMN IF EXISTS zip_file_hash" not in bridge_source
    assert "DROP INDEX IF EXISTS ix_projects_zip_file_hash" not in bridge_source


def test_static_finding_path_migration_downgrade_keeps_data_normalization_contract():
    migration_file = (
        BACKEND_ROOT
        / "alembic"
        / "versions"
        / "7f8e9d0c1b2a_normalize_static_finding_paths.py"
    )
    migration_source = migration_file.read_text(encoding="utf-8")

    assert "bandit_findings" in migration_source
    assert "opengrep_findings" in migration_source
    assert "downgrade" in migration_source
    assert "UPDATE bandit_findings" not in migration_source.split("def downgrade", 1)[1]
    assert "UPDATE opengrep_findings" not in migration_source.split("def downgrade", 1)[1]
