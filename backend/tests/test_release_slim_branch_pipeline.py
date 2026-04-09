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


def _assert_nexus_runtime_bundle(output_dir: Path, bundle_name: str) -> None:
    bundle_root = output_dir / bundle_name
    assert bundle_root.exists(), bundle_name
    assert (bundle_root / "dist" / "index.html").exists(), f"{bundle_name}/dist/index.html"
    assert (bundle_root / "nginx.conf").exists(), f"{bundle_name}/nginx.conf"
    assert {path.name for path in bundle_root.iterdir()} == {"dist", "nginx.conf"}
    assert not (bundle_root / "src").exists(), f"{bundle_name}/src"
    assert not (bundle_root / "node_modules").exists(), f"{bundle_name}/node_modules"
    assert not (bundle_root / "tests").exists(), f"{bundle_name}/tests"
    assert not (bundle_root / "package.json").exists(), f"{bundle_name}/package.json"


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
    assert "git checkout --orphan" in workflow_text
    assert "origin/release" not in workflow_text
    assert "git fetch origin release" not in workflow_text
    assert "git checkout -B release origin/release" not in workflow_text
    assert "git ls-remote --tags" in workflow_text
    assert "git push origin --delete" in workflow_text
    assert "release-tag-cleanup.txt" in workflow_text
    assert 'release_id=""' in workflow_text
    assert 'if release_id="$(gh api -X GET "repos/${GITHUB_REPOSITORY}/releases/tags/${tag}" --jq \'.id\' 2>/dev/null)"; then' in workflow_text
    assert '[[ "${release_id}" =~ ^[0-9]+$ ]]' in workflow_text
    assert 'releases/tags/${tag}" --jq \'.id\' 2>/dev/null || true' not in workflow_text


def test_scheduled_release_workflow_no_longer_uses_git_tags_as_release_state() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "scheduled-release.yml").read_text(
        encoding="utf-8"
    )

    assert "git describe --tags" not in workflow_text
    assert "git tag -a" not in workflow_text
    assert "git push origin ${{ steps.check.outputs.version }}" not in workflow_text
    assert "-f build_frontend=true" not in workflow_text
    assert "-f build_backend=true" not in workflow_text


def test_release_helper_script_no_longer_creates_or_pushes_git_tags() -> None:
    script_text = (REPO_ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")

    assert 'git tag -a "v$NEW_VERSION"' not in script_text
    assert 'git push origin "v$NEW_VERSION"' not in script_text
    assert "已创建本地 tag" not in script_text


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
        "docker/nexus-web.Dockerfile",
        "docker/env/backend/env.example",
        "backend/alembic.ini",
        "backend/pyproject.toml",
        "backend/requirements-heavy.txt",
        "backend/uv.lock",
        "backend/app/main.py",
        "frontend/package.json",
        "frontend/pnpm-lock.yaml",
        "frontend/vite.config.ts",
        "frontend/scripts/clean.mjs",
        "frontend/scripts/chunkObfuscatorPlugin.ts",
        "frontend/scripts/obfuscatorOptions.ts",
        "frontend/scripts/dev-launcher.mjs",
        "frontend/src/app/main.tsx",
        "frontend/yasa-engine-overrides/src/config.ts",
        "nexus-web/dist/index.html",
        "nexus-web/nginx.conf",
        "nexus-itemDetail/dist/index.html",
        "nexus-itemDetail/nginx.conf",
    ]
    for rel_path in required_paths:
        assert (output_dir / rel_path).exists(), rel_path

    forbidden_paths = [
        "NOTICE",
        ".github",
        "deploy",
        "docs",
        "docker-compose.full.yml",
        "docker-compose.self-contained.yml",
        "backend/tests",
        "frontend/tests",
        "frontend/scripts/dev-entrypoint.sh",
        "frontend/scripts/generate-cwe-catalog.mjs",
        "frontend/scripts/run-in-dev-container.sh",
        "frontend/scripts/run-node-tests.mjs",
        "frontend/scripts/setup.cjs",
        "frontend/scripts/setup.sh",
        "scripts/compose-up-local-build.sh",
        "scripts/compose-up-with-fallback.sh",
    ]
    for rel_path in forbidden_paths:
        assert not (output_dir / rel_path).exists(), rel_path

    _assert_nexus_runtime_bundle(output_dir, "nexus-web")
    _assert_nexus_runtime_bundle(output_dir, "nexus-itemDetail")


def test_release_generator_writes_sanitized_compose_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "release-tree"
    result = _run_release_generator(output_dir)
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output

    compose_text = (output_dir / "docker-compose.yml").read_text(encoding="utf-8")
    hybrid_text = (output_dir / "docker-compose.hybrid.yml").read_text(encoding="utf-8")

    assert "docker-compose.full.yml" not in compose_text
    assert "docker-compose.self-contained.yml" not in compose_text
    assert "backend:" in compose_text
    assert "frontend:" in compose_text
    assert "db:" in compose_text
    assert "redis:" in compose_text
    assert "nexus-web:" in compose_text
    assert "nexus-itemDetail:" in compose_text
    assert "context: ./nexus-web" in compose_text
    assert "context: ./nexus-itemDetail" in compose_text
    assert "dockerfile: ../docker/nexus-web.Dockerfile" in compose_text
    assert "image: ${NEXUS_WEB_IMAGE:-vulhunter/nexus-web-local:latest}" in compose_text
    assert "image: ${NEXUS_ITEM_DETAIL_IMAGE:-vulhunter/nexus-item-detail-local:latest}" in compose_text

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
        assert "nexus-web" in doc
        assert "nexus-itemDetail" in doc
