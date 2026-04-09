import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_release_generator(output_dir: Path) -> subprocess.CompletedProcess[str]:
    script_path = REPO_ROOT / "scripts" / "generate-release-branch.sh"
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"/usr/bin:/bin:{env['PATH']}"

    return subprocess.run(
        [str(script_path), "--output", str(output_dir)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_release_workflow_generates_validates_and_force_pushes_release_branch() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    generator_path = REPO_ROOT / "scripts" / "generate-release-branch.sh"
    assert generator_path.exists()
    assert "branches:" in workflow_text
    assert "- main" in workflow_text
    assert "workflow_dispatch:" in workflow_text
    assert "generate-release-branch.sh" in workflow_text
    assert "--output" in workflow_text
    assert "--validate" in workflow_text
    assert "git push --force origin HEAD:release" in workflow_text
    assert "fetch-depth: 0" in workflow_text


def test_release_generator_emits_latest_only_slim_tree(tmp_path: Path) -> None:
    output_dir = tmp_path / "release-tree"
    result = _run_release_generator(output_dir)
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output

    required_paths = [
        "README.md",
        "README_EN.md",
        "docker-compose.yml",
        "docker-compose.hybrid.yml",
        "scripts/README-COMPOSE.md",
        "docker/backend.Dockerfile",
        "docker/frontend.Dockerfile",
        "docker/env/backend/env.example",
        "backend/alembic.ini",
        "backend/pyproject.toml",
        "backend/requirements-heavy.txt",
        "backend/uv.lock",
        "backend/app/main.py",
        "frontend/package.json",
        "frontend/pnpm-lock.yaml",
        "frontend/vite.config.ts",
        "frontend/src/app/main.tsx",
        "frontend/yasa-engine-overrides/src/config.ts",
    ]
    for rel_path in required_paths:
        assert (output_dir / rel_path).exists(), rel_path

    forbidden_paths = [
        ".github",
        "deploy",
        "docs",
        "docker-compose.full.yml",
        "docker-compose.self-contained.yml",
        "backend/tests",
        "frontend/tests",
        "nexus-web",
        "nexus-itemDetail",
        "scripts/compose-up-local-build.sh",
        "scripts/compose-up-with-fallback.sh",
    ]
    for rel_path in forbidden_paths:
        assert not (output_dir / rel_path).exists(), rel_path


def test_release_generator_writes_sanitized_compose_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "release-tree"
    result = _run_release_generator(output_dir)
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output

    compose_text = (output_dir / "docker-compose.yml").read_text(encoding="utf-8")
    hybrid_text = (output_dir / "docker-compose.hybrid.yml").read_text(encoding="utf-8")

    assert "docker-compose.full.yml" not in compose_text
    assert "docker-compose.self-contained.yml" not in compose_text
    assert "nexus-web" not in compose_text
    assert "nexus-itemDetail" not in compose_text
    assert "\n    build:\n" not in compose_text
    assert "backend:" in compose_text
    assert "frontend:" in compose_text
    assert "db:" in compose_text
    assert "redis:" in compose_text

    assert "docker-compose.full.yml" not in hybrid_text
    assert "docker-compose.self-contained.yml" not in hybrid_text
    assert "nexus-web" not in hybrid_text
    assert "nexus-itemDetail" not in hybrid_text
    assert "image: vulhunter/backend-local:latest" in hybrid_text
    assert "image: vulhunter/frontend-local:latest" in hybrid_text
    assert "context: ." in hybrid_text
    assert "context: ./frontend" in hybrid_text
    assert "target: runtime-release" in hybrid_text
    assert "RUNNER_PREFLIGHT_BUILD_CONTEXT" not in hybrid_text


def test_generated_release_docs_only_publish_two_supported_commands(tmp_path: Path) -> None:
    output_dir = tmp_path / "release-tree"
    result = _run_release_generator(output_dir)
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output

    docs = (
        (output_dir / "README.md").read_text(encoding="utf-8"),
        (output_dir / "README_EN.md").read_text(encoding="utf-8"),
        (output_dir / "scripts" / "README-COMPOSE.md").read_text(encoding="utf-8"),
    )
    for doc in docs:
        assert "docker compose up" in doc
        assert "docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build" in doc
        assert "docker-compose.full.yml" not in doc
        assert "docker-compose.self-contained.yml" not in doc
        assert "package-release-artifacts.sh" not in doc
        assert "deploy-release-artifacts.sh" not in doc
        assert "docker-compose.release-static-frontend.yml" not in doc
        assert "docker/env/backend/env.example" in doc
        assert "docker/env/backend/.env" in doc
        assert "LLM_API_KEY" in doc
