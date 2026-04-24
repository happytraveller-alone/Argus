from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_backend_migration_smoke_workflow_runs_rust_bootstrap_only() -> None:
    workflow_text = (
        REPO_ROOT / ".github" / "workflows" / "backend-migration-smoke.yml"
    ).read_text(encoding="utf-8")

    assert "uses: dtolnay/rust-toolchain@stable" in workflow_text
    assert "working-directory: backend" in workflow_text
    assert "cargo test -j 2 -- --test-threads=1 --nocapture" in workflow_text
    assert "cargo test -- --nocapture" not in workflow_text
    assert "DATABASE_URL: postgres://postgres:postgres@127.0.0.1:5432/vulhunter" in workflow_text
    assert "pip install -r backend/requirements.txt" not in workflow_text
    assert "uv sync --frozen --no-dev" not in workflow_text
    assert "uv run alembic upgrade head" not in workflow_text
    assert "uv run python - <<'PY'" not in workflow_text


def test_backend_local_commands_use_uv_only() -> None:
    backend_readme_text = (REPO_ROOT / "backend" / "README.md").read_text(encoding="utf-8")
    start_script_text = (REPO_ROOT / "backend" / "start.sh").read_text(encoding="utf-8")

    assert "uvicorn app.main:app" not in backend_readme_text
    assert "cargo run --bin backend-rust" in backend_readme_text
    assert "cargo test -j 2 -- --test-threads=1" in backend_readme_text
    assert "uv run pytest" not in backend_readme_text
    assert "cargo build --bin backend-rust" in start_script_text
    assert "cargo run --bin backend-rust" in start_script_text
    assert "uvicorn app.main:app" not in start_script_text
