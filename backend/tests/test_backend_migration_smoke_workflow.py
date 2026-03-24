from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_backend_migration_smoke_workflow_uses_locked_uv_environment() -> None:
    workflow_text = (
        REPO_ROOT / ".github" / "workflows" / "backend-migration-smoke.yml"
    ).read_text(encoding="utf-8")

    assert "uses: astral-sh/setup-uv@" in workflow_text
    assert "working-directory: backend" in workflow_text
    assert "uv sync --frozen --no-dev" in workflow_text
    assert "pip install -r backend/requirements.txt" not in workflow_text
    assert "uv run alembic upgrade head" in workflow_text
    assert "uv run python - <<'PY'" in workflow_text
