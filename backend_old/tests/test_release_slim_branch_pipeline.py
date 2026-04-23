import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_FILTER_INCLUDE_PATHS = [
    "backend/**",
    "frontend/**",
    "docker/frontend.Dockerfile",
    "docker/env/backend/env.example",
    "docker/env/frontend/.env.example",
    "LICENSE",
    "scripts/generate-release-branch.sh",
    "scripts/release-allowlist.txt",
    "scripts/release-templates/**",
]
RELEASE_FILTER_EXCLUDE_PATHS = [
    "backend/tests/**",
    "backend/docs/**",
    "backend/.venv/**",
    "backend/.pytest_cache/**",
    "backend/.mypy_cache/**",
    "backend/target/**",
    "backend/uploads/**",
    "backend/log/**",
    "backend/data/**",
    "backend/.env",
    "backend/README.md",
    "backend/SANDBOX_RUNNER_MIGRATION.md",
    "frontend/tests/**",
    "frontend/docs/**",
    "frontend/dist/**",
    "frontend/node_modules/**",
    "frontend/scripts/dev-entrypoint.sh",
    "frontend/scripts/generate-cwe-catalog.mjs",
    "frontend/scripts/run-in-dev-container.sh",
    "frontend/scripts/run-node-tests.mjs",
    "frontend/scripts/setup.cjs",
    "frontend/scripts/setup.sh",
]


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
    generator_text = (REPO_ROOT / "scripts" / "generate-release-branch.sh").read_text(
        encoding="utf-8"
    )

    generator_path = REPO_ROOT / "scripts" / "generate-release-branch.sh"
    assert generator_path.exists()
    assert "branches:" in workflow_text
    assert "- main" in workflow_text
    assert "workflow_dispatch:" in workflow_text
    assert "workflow_call:" in workflow_text
    assert "source_sha:" in workflow_text
    assert "publish_summary_json" not in workflow_text
    assert "build_sandbox" not in workflow_text
    assert "gh workflow run" not in workflow_text
    assert "detect-release-carrying-changes:" in workflow_text
    assert "dorny/paths-filter@v3" in workflow_text
    for rel_path in RELEASE_FILTER_INCLUDE_PATHS:
        assert rel_path in workflow_text
    for rel_path in RELEASE_FILTER_EXCLUDE_PATHS:
        assert rel_path in workflow_text
    assert "cp \"$TEMPLATE_DIR/docker-compose.release-slim.yml\" \"$OUTPUT_DIR/docker-compose.yml\"" in generator_text
    assert "cp \"$TEMPLATE_DIR/backend.Dockerfile\" \"$OUTPUT_DIR/docker/backend.Dockerfile\"" in generator_text
    assert "scripts/release-templates/**" in workflow_text
    assert "'docker/backend.Dockerfile'" not in workflow_text
    assert "'docker-compose.yml'" not in workflow_text
    assert "generate-release-branch.sh" in workflow_text
    assert "--output" in workflow_text
    assert "--validate" in workflow_text
    assert "docker compose config >/dev/null" in workflow_text
    assert "docker compose -f docker-compose.yml -f docker-compose.full.yml config >/dev/null" not in workflow_text
    assert "docker compose -f docker-compose.yml -f docker-compose.hybrid.yml config >/dev/null" not in workflow_text
    validate_marker = "- name: Validate compose entrypoints"
    assert validate_marker in workflow_text
    validate_start = workflow_text.index(validate_marker)
    next_step_idx = workflow_text.find("\n      - name:", validate_start + len(validate_marker))
    validate_block = workflow_text[validate_start:next_step_idx].strip()
    run_marker = "run: |"
    run_idx = validate_block.index(run_marker) + len(run_marker)
    run_body_lines = [
        line.strip() for line in validate_block[run_idx:].splitlines()
        if line.strip()
    ]
    assert run_body_lines == ["docker compose config >/dev/null"], (
        f"Validate step run block should contain exactly one command, got: {run_body_lines}"
    )
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

    assert "uses: ./.github/workflows/publish-runtime-images.yml" in workflow_text
    assert "gh workflow run" not in workflow_text
    assert "build_backend: false" in workflow_text
    assert "build_frontend: false" in workflow_text
    assert "build_opengrep_runner: true" in workflow_text
    assert "build_flow_parser_runner: true" in workflow_text
    assert "build_sandbox_runner: true" in workflow_text
    assert "build_sandbox:" not in workflow_text
    assert "git describe --tags" not in workflow_text
    assert "git tag -a" not in workflow_text
    assert "git push origin ${{ steps.check.outputs.version }}" not in workflow_text
    assert "-f build_frontend=true" not in workflow_text
    assert "-f build_backend=true" not in workflow_text
    assert "-f build_yasa_runner=true" not in workflow_text


def test_legacy_release_helper_script_is_removed() -> None:
    assert not (REPO_ROOT / "scripts" / "release.sh").exists()


def test_release_generator_emits_latest_only_slim_tree(tmp_path: Path) -> None:
    output_dir = tmp_path / "release-tree"
    result = _run_release_generator(output_dir)
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output

    required_paths = [
        "README.md",
        "README_EN.md",
        "docker-compose.yml",
        "docker/backend.Dockerfile",
        "docker/frontend.Dockerfile",
        "docker/env/backend/env.example",
        "backend/Cargo.toml",
        "backend/Cargo.lock",
        "backend/src/main.rs",
        "backend/src/lib.rs",
        "backend/src/bootstrap/preflight.rs",
        "backend/migrations/0001_system_configs.sql",
        "frontend/package.json",
        "frontend/pnpm-lock.yaml",
        "frontend/vite.config.ts",
        "frontend/scripts/clean.mjs",
        "frontend/scripts/chunkObfuscatorPlugin.ts",
        "frontend/scripts/obfuscatorOptions.ts",
        "frontend/scripts/dev-launcher.mjs",
        "frontend/src/app/main.tsx",
    ]
    for rel_path in required_paths:
        assert (output_dir / rel_path).exists(), rel_path

    forbidden_paths = [
        "NOTICE",
        ".github",
        "deploy",
        "docs",
        "docker-compose.self-contained.yml",
        "docker-compose.hybrid.yml",
        "docker-compose.full.yml",
        "backend/tests",
        "frontend/tests",
        "frontend/scripts/dev-entrypoint.sh",
        "frontend/scripts/generate-cwe-catalog.mjs",
        "frontend/scripts/run-in-dev-container.sh",
        "frontend/scripts/run-node-tests.mjs",
        "frontend/scripts/setup.cjs",
        "frontend/scripts/setup.sh",
        "scripts",
    ]
    for rel_path in forbidden_paths:
        assert not (output_dir / rel_path).exists(), rel_path

    assert not (output_dir / "nexus-web").exists()
    assert not (output_dir / "nexus-itemDetail").exists()
    assert not (output_dir / "backend" / "requirements-heavy.txt").exists()
    assert not (output_dir / "backend" / "get-pip.py").exists()


def test_release_generator_writes_sanitized_compose_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "release-tree"
    result = _run_release_generator(output_dir)
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output

    compose_text = (output_dir / "docker-compose.yml").read_text(encoding="utf-8")

    assert not (output_dir / "docker-compose.hybrid.yml").exists()
    assert not (output_dir / "docker-compose.full.yml").exists()
    assert "docker-compose.self-contained.yml" not in compose_text
    assert "backend:" in compose_text
    assert "frontend:" in compose_text
    assert "db:" in compose_text
    assert "redis:" in compose_text
    assert "nexus-web:" not in compose_text
    assert "nexus-itemDetail:" not in compose_text
    assert "NEXUS_WEB_IMAGE" not in compose_text
    assert "NEXUS_ITEM_DETAIL_IMAGE" not in compose_text
    assert "SCANNER_BANDIT_IMAGE" not in compose_text
    assert "SCANNER_GITLEAKS_IMAGE" not in compose_text
    assert "SCANNER_PHPSTAN_IMAGE" not in compose_text
    assert "SCANNER_PMD_IMAGE" not in compose_text
    assert "SCANNER_OPENGREP_IMAGE" in compose_text
    assert "FLOW_PARSER_RUNNER_IMAGE" in compose_text
    assert "SANDBOX_RUNNER_IMAGE" in compose_text


def test_release_backend_template_no_longer_copies_removed_backend_static_tree() -> None:
    template_text = (REPO_ROOT / "scripts" / "release-templates" / "backend.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "COPY backend/static /app/static" not in template_text


def test_generated_release_docs_only_publish_three_supported_commands(tmp_path: Path) -> None:
    output_dir = tmp_path / "release-tree"
    result = _run_release_generator(output_dir)
    combined_output = "\n".join(part for part in [result.stdout, result.stderr] if part)

    assert result.returncode == 0, combined_output

    docs = (
        (output_dir / "README.md").read_text(encoding="utf-8"),
        (output_dir / "README_EN.md").read_text(encoding="utf-8"),
    )
    for doc in docs:
        assert "docker compose up --build" in doc
        assert "docker compose -f docker-compose.yml -f docker-compose.hybrid.yml" not in doc
        assert "docker compose -f docker-compose.yml -f docker-compose.full.yml" not in doc
        assert "docker-compose.self-contained.yml" not in doc
        assert "package-release-artifacts.sh" not in doc
        assert "deploy-release-artifacts.sh" not in doc
        assert "docker-compose.release-static-frontend.yml" not in doc
        assert "docker/env/backend/env.example" in doc
        assert "docker/env/backend/.env" in doc
        assert "LLM_API_KEY" in doc
        assert "nexus-web" not in doc
        assert "nexus-itemDetail" not in doc
