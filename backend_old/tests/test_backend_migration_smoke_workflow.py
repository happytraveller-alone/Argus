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


def test_backend_local_commands_use_uv_only() -> None:
    backend_readme_text = (REPO_ROOT / "backend" / "README.md").read_text(encoding="utf-8")
    start_script_text = (REPO_ROOT / "backend" / "start.sh").read_text(encoding="utf-8")

    assert "uvicorn app.main:app" not in backend_readme_text
    assert "cargo run --bin backend-rust" in backend_readme_text
    assert "cargo test" in backend_readme_text
    assert "uv run pytest" not in backend_readme_text
    assert "cargo build --bin backend-rust" in start_script_text
    assert "cargo run --bin backend-rust" in start_script_text
    assert "uvicorn app.main:app" not in start_script_text
