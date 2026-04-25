from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RETIRED_RUNNER_SERVICE_NAMES = ("flow-parser-runner",)


def test_default_compose_uses_backend_managed_runner_preflight() -> None:
    compose_path = REPO_ROOT / "docker-compose.yml"
    backend_dockerfile = REPO_ROOT / "docker" / "backend.Dockerfile"
    frontend_dockerfile = REPO_ROOT / "docker" / "frontend.Dockerfile"

    assert compose_path.exists()
    assert not (REPO_ROOT / "docker-compose.full.yml").exists()
    assert not (REPO_ROOT / "docker-compose.hybrid.yml").exists()
    assert not (REPO_ROOT / "docker-compose.dev.yml").exists()
    assert not (REPO_ROOT / "docker-compose.frontend-dev.yml").exists()
    assert not (REPO_ROOT / "docker-compose.override.yml").exists()
    assert not (REPO_ROOT / "docker-compose.prod.yml").exists()
    assert not (REPO_ROOT / "docker-compose.prod.cn.yml").exists()

    compose_text = compose_path.read_text(encoding="utf-8")
    assert "runner preflight / warmup" not in compose_text
    assert "一次性预热/自检容器" not in compose_text
    assert "执行完检查后按预期退出" not in compose_text
    assert "\n  opengrep-runner:\n" in compose_text
    assert 'condition: service_completed_successfully' in compose_text
    assert 'image: ${SCANNER_OPENGREP_IMAGE:-vulhunter/opengrep-runner-local:latest}' in compose_text
    assert 'pull_policy: never' in compose_text
    assert "dockerfile: docker/opengrep-runner.Dockerfile" in compose_text
    assert 'command:' in compose_text
    assert '- "opengrep"' in compose_text
    assert '- "--version"' in compose_text
    assert 'restart: "no"' in compose_text
    for runner_service in RETIRED_RUNNER_SERVICE_NAMES:
        assert f"\n  {runner_service}:" not in compose_text
    assert "vulhunter/backend-dev:latest" not in compose_text
    assert "vulhunter/frontend-dev:latest" not in compose_text
    assert "\n  backend:\n" in compose_text
    assert "\n  frontend:\n" in compose_text
    assert "\n  nexus-web:\n" not in compose_text
    assert "\n  nexus-itemDetail:\n" not in compose_text
    assert "${DOCKERHUB_LIBRARY_MIRROR:-docker.m.daocloud.io/library}/postgres:18.3-alpine3.23" in compose_text
    assert "postgres_data:/var/lib/postgresql" in compose_text
    assert "postgres_data:/var/lib/postgresql/data" not in compose_text
    assert "${DOCKERHUB_LIBRARY_MIRROR:-docker.m.daocloud.io/library}/redis:8.6.2-alpine3.23" in compose_text
    assert "dockerfile: docker/backend.Dockerfile" in compose_text
    assert "target: runtime-plain" in compose_text
    assert "target: dev" in compose_text
    assert "./frontend:/app" in compose_text
    assert "${VULHUNTER_FRONTEND_PORT:-3000}:5173" in compose_text
    assert "VITE_API_TARGET: ${VITE_API_TARGET:-http://backend:8000}" in compose_text
    assert "BACKEND_PYPI_INDEX_PRIMARY: ${BACKEND_PYPI_INDEX_PRIMARY:-}" in compose_text
    assert "BACKEND_PYPI_INDEX_FALLBACK: ${BACKEND_PYPI_INDEX_FALLBACK:-}" in compose_text
    assert "BACKEND_INSTALL_YASA" not in compose_text
    assert "YASA_VERSION:" not in compose_text
    assert "BACKEND_PYPI_INDEX_CANDIDATES: ${BACKEND_PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/" in compose_text
    assert "YASA_ENABLED" not in compose_text
    assert "SCAN_WORKSPACE_ROOT: ${SCAN_WORKSPACE_ROOT:-/tmp/vulhunter/scans}" in compose_text
    assert "SCAN_WORKSPACE_VOLUME: ${SCAN_WORKSPACE_VOLUME:-vulhunter_scan_workspace}" in compose_text
    assert 'OPENGREP_SCAN_TIMEOUT_SECONDS: "${OPENGREP_SCAN_TIMEOUT_SECONDS:-0}"' in compose_text
    assert "SCANNER_OPENGREP_IMAGE: ${SCANNER_OPENGREP_IMAGE:-vulhunter/opengrep-runner-local:latest}" in compose_text
    assert "SCANNER_BANDIT_IMAGE" not in compose_text
    assert "SCANNER_GITLEAKS_IMAGE" not in compose_text
    assert "SCANNER_PHPSTAN_IMAGE" not in compose_text
    assert "SCANNER_PMD_IMAGE" not in compose_text
    assert "SCANNER_YASA_IMAGE" not in compose_text
    assert "FLOW_PARSER_RUNNER_IMAGE: ${FLOW_PARSER_RUNNER_IMAGE:-vulhunter/flow-parser-runner-local:latest}" in compose_text
    assert 'FLOW_PARSER_RUNNER_ENABLED: "${FLOW_PARSER_RUNNER_ENABLED:-true}"' in compose_text
    assert 'FLOW_PARSER_RUNNER_TIMEOUT_SECONDS: "${FLOW_PARSER_RUNNER_TIMEOUT_SECONDS:-120}"' in compose_text
    assert "YASA_TIMEOUT_SECONDS" not in compose_text
    assert "/tmp/vulhunter/scans:/tmp/vulhunter/scans" not in compose_text
    assert "scan_workspace:/tmp/vulhunter/scans" in compose_text
    assert "${DOCKER_SOCKET_PATH:-/var/run/docker.sock}:/var/run/docker.sock" in compose_text
    assert 'RUNNER_PREFLIGHT_STRICT: "${RUNNER_PREFLIGHT_STRICT:-true}"' in compose_text
    assert "mem_limit: 4g" in compose_text
    assert "pids_limit: 1024" in compose_text
    assert "mem_limit: 512m" in compose_text
    assert "pids_limit: 256" in compose_text
    assert "mem_limit: 1g" in compose_text
    assert "MCP_REQUIRE_ALL_READY_ON_STARTUP" not in compose_text
    assert "SANDBOX_RUNNER_IMAGE: ${SANDBOX_RUNNER_IMAGE:-vulhunter/sandbox-runner-local:latest}" in compose_text
    assert 'SANDBOX_RUNNER_ENABLED: "${SANDBOX_RUNNER_ENABLED:-true}"' in compose_text
    assert "BACKEND_NPM_REGISTRY_PRIMARY" not in compose_text
    assert "BACKEND_NPM_REGISTRY_FALLBACK" not in compose_text
    assert "BACKEND_NPM_REGISTRY_CANDIDATES" not in compose_text
    assert "BACKEND_PNPM_VERSION" not in compose_text
    assert "MCP_REQUIRED_RUNTIME_DOMAIN" not in compose_text
    assert "MCP_CODE_INDEX_ENABLED" not in compose_text
    assert 'profiles: [ "tools" ]' in compose_text
    assert "adminer:" in compose_text
    assert "NEXUS_WEB_IMAGE" not in compose_text

    backend_text = backend_dockerfile.read_text(encoding="utf-8")
    assert "BACKEND_INSTALL_YASA" not in backend_text
    assert "ARG YASA_VERSION=" not in backend_text
    assert "backend-dev-entrypoint.sh" not in backend_text
    assert 'CMD ["/bin/sh", "/usr/local/bin/backend-dev-entrypoint.sh"]' not in backend_text
    assert 'CMD ["/bin/sh", "/app/docker-entrypoint.sh"]' not in backend_text
    assert "https://github.com/antgroup/YASA-Engine/archive/refs/tags/${YASA_VERSION}.tar.gz" not in backend_text
    assert 'best_index="$(cat /tmp/pypi-best-index)"' not in backend_text
    assert 'sync_with_index "${BACKEND_PYPI_INDEX_PRIMARY}" || sync_with_index "${BACKEND_PYPI_INDEX_FALLBACK}"' not in backend_text
    assert "nodebase" not in backend_text
    assert "mcp-builder" not in backend_text
    assert "run_npx_from_candidates.sh" not in backend_text
    assert "/app/data/mcp/code-index" not in backend_text
    assert "FROM ${DOCKERHUB_LIBRARY_MIRROR}/node:22-slim" not in backend_text
    assert "BACKEND_NPM_REGISTRY_PRIMARY" not in backend_text
    assert "BACKEND_NPM_REGISTRY_FALLBACK" not in backend_text
    assert "BACKEND_NPM_REGISTRY_CANDIDATES" not in backend_text
    assert "BACKEND_PNPM_VERSION" not in backend_text
    assert "BACKEND_PNPM_INSTALL_OPTIONAL" not in backend_text
    assert "PNPM_HOME" not in backend_text
    assert "/pnpm" not in backend_text

    frontend_text = frontend_dockerfile.read_text(encoding="utf-8")
    assert " AS dev" in frontend_text
    assert "frontend-dev-entrypoint.sh" not in frontend_text
    assert 'CMD ["/bin/sh", "/usr/local/bin/frontend-dev-entrypoint.sh"]' not in frontend_text
    assert 'ENTRYPOINT ["/bin/sh", "/docker-entrypoint.sh"]' not in frontend_text


def test_backend_dockerfile_builds_linux_arm64_yasa_from_source() -> None:
    backend_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert 'CMD ["/usr/local/bin/backend-entrypoint.sh"]' in backend_text


def test_nexus_web_dockerfile_is_removed() -> None:
    assert not (REPO_ROOT / "docker" / "nexus-web.Dockerfile").exists()


def test_removed_compose_wrapper_scripts_are_absent() -> None:
    removed_paths = [
        REPO_ROOT / "scripts" / "README-COMPOSE.md",
        REPO_ROOT / "scripts" / "build-frontend.sh",
        REPO_ROOT / "scripts" / "compose-up-local-build.sh",
        REPO_ROOT / "scripts" / "compose-up-with-fallback.sh",
        REPO_ROOT / "scripts" / "compose-up-with-fallback.ps1",
        REPO_ROOT / "scripts" / "compose-up-with-fallback.bat",
        REPO_ROOT / "scripts" / "setup-env.sh",
        REPO_ROOT / "scripts" / "release.sh",
        REPO_ROOT / "scripts" / "lib" / "compose-env.sh",
    ]

    for path in removed_paths:
        assert not path.exists(), str(path)


def test_readmes_document_backend_managed_preflight_behavior() -> None:
    root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    root_readme_en = (REPO_ROOT / "README_EN.md").read_text(encoding="utf-8")

    assert "docker compose up --build" in root_readme
    assert "docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build" not in root_readme
    assert "docker compose -f docker-compose.yml -f docker-compose.full.yml up --build" not in root_readme
    assert "docker-compose.self-contained.yml" not in root_readme
    assert "package-release-artifacts.sh" not in root_readme
    assert "scripts/README-COMPOSE.md" not in root_readme
    assert "docker compose up --build" in root_readme_en
    assert "docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build" not in root_readme_en
    assert "docker compose -f docker-compose.yml -f docker-compose.full.yml up --build" not in root_readme_en
    assert "docker-compose.self-contained.yml" not in root_readme_en
    assert "package-release-artifacts.sh" not in root_readme_en
    assert "scripts/README-COMPOSE.md" not in root_readme_en


def test_backend_runtime_python_tools_are_installed_via_backend_venv() -> None:
    backend_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(
        encoding="utf-8"
    )
    backend_readme_text = (REPO_ROOT / "backend" / "README.md").read_text(encoding="utf-8")
    backend_start_text = (REPO_ROOT / "backend" / "start.sh").read_text(encoding="utf-8")
    flow_parser_runner_text = (
        REPO_ROOT / "docker" / "flow-parser-runner.Dockerfile"
    ).read_text(encoding="utf-8")

    assert "pip install --retries 5 --timeout 60 --disable-pip-version-check code2flow bandit" not in backend_text
    assert "install_python_helpers()" not in backend_text
    assert "gitleaks; \\" not in backend_text
    assert "requirements-heavy.txt" not in backend_text
    assert "COPY --from=builder /app/.venv /opt/backend-venv" not in backend_text
    assert "COPY --from=builder /usr/bin/gitleaks /usr/local/bin/gitleaks" not in backend_text
    assert "COPY --from=scanner-tools-base /opt/opengrep /opt/opengrep" not in backend_text
    assert "COPY --from=scanner-tools-base /opt/phpstan /opt/phpstan" not in backend_text
    assert "COPY --from=scanner-tools-base /opt/yasa /opt/yasa" not in backend_text
    assert 'ln -sf "${OPENGREP_REAL_BIN}" /usr/local/bin/opengrep.real' not in backend_text
    assert 'ln -sf "${OPENGREP_WRAPPER_BIN}" /usr/local/bin/opengrep' not in backend_text
    assert 'ln -sf "${PHPSTAN_HOME}/phpstan" /usr/local/bin/phpstan' not in backend_text
    assert "opengrep --version;" not in backend_text
    assert "phpstan --version;" not in backend_text
    assert 'if [ -x "${YASA_WRAPPER_BIN}" ]; then' not in backend_text
    assert 'ln -sfn /opt/backend-venv /app/.venv' not in backend_text
    assert not (REPO_ROOT / "docker" / "yasa-runner.Dockerfile").exists()
    assert "tree-sitter-language-pack" in flow_parser_runner_text
    assert "code2flow" in flow_parser_runner_text
    assert "COPY backend/scripts/flow_parser_runner.py /opt/flow-parser/flow_parser_runner.py" in flow_parser_runner_text
    assert "COPY backend_old/scripts/flow_parser_runner.py" not in flow_parser_runner_text
    assert "ARG BACKEND_PYPI_INDEX_CANDIDATES=" in flow_parser_runner_text
    assert 'ENV PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES}' in flow_parser_runner_text
    assert "package_source_selector.py" not in flow_parser_runner_text
    assert "tr ',' '\\n'" in flow_parser_runner_text
    assert "awk 'NF && !seen[$0]++'" in flow_parser_runner_text
    assert 'for idx in $(printf \'%s\\n\' "${ordered_pypi_indexes}"); do \\' in flow_parser_runner_text
    assert '/opt/flow-parser-venv/bin/pip install --disable-pip-version-check -i "${idx}" -r /tmp/flow-parser-runner.requirements.txt' in flow_parser_runner_text
    assert 'command -v code2flow >/dev/null 2>&1' in flow_parser_runner_text
    assert 'code2flow --help >/dev/null 2>&1' in flow_parser_runner_text
    assert "python3 /opt/flow-parser/flow_parser_runner.py --help >/dev/null 2>&1" in flow_parser_runner_text
    assert 'CMD ["python3", "/opt/flow-parser/flow_parser_runner.py", "--help"]' in flow_parser_runner_text
    assert "uvicorn app.main:app" not in backend_readme_text
    assert "cargo run --bin backend-rust" in backend_readme_text
    assert "cargo test -j 2 -- --test-threads=1" in backend_readme_text
    assert "cargo build --bin backend-rust" in backend_start_text
    assert "cargo run --bin backend-rust" in backend_start_text
    assert "uvicorn app.main:app" not in backend_start_text


def test_backend_dockerfile_derives_docker_cli_image_from_selected_mirror() -> None:
    backend_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")

    assert "ARG DOCKER_CLI_IMAGE=${DOCKERHUB_LIBRARY_MIRROR}/docker:cli" in backend_text
    assert "ARG DOCKER_CLI_IMAGE=docker.m.daocloud.io/docker:cli" not in backend_text


def test_backend_dockerfile_copies_rule_assets_into_runtime_image() -> None:
    backend_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")

    assert "COPY backend/assets ./assets" in backend_text
    assert "COPY docker/backend-entrypoint.sh /usr/local/bin/backend-entrypoint.sh" in backend_text
    assert 'CMD ["/usr/local/bin/backend-entrypoint.sh"]' in backend_text
    assert "USER appuser" not in backend_text


def test_backend_dockerfile_bootstraps_apt_sources_over_http() -> None:
    backend_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")

    builder_section = backend_text.split('99-backend-builder-network; \\\n', 1)[1].split(
        "COPY backend/Cargo.toml backend/Cargo.lock ./", 1
    )[0]
    runtime_section = backend_text.split('99-backend-runtime-network; \\\n', 1)[1].split(
        "RUN groupadd --gid 1001 appgroup", 1
    )[0]

    def assert_stage_contract(
        section: str,
        initial_install_marker: str,
        fallback_install_marker: str,
    ) -> None:
        assert "write_sources() {" in section
        assert "write_secure_sources() {" in section
        assert "printf 'deb http://%s/debian %s main\\n'" in section
        assert "printf 'deb http://%s/debian %s-updates main\\n'" in section
        assert "printf 'deb http://%s/debian-security %s-security main\\n'" in section
        assert "printf 'deb https://%s/debian %s main\\n'" in section
        assert "printf 'deb https://%s/debian %s-updates main\\n'" in section
        assert "printf 'deb https://%s/debian-security %s-security main\\n'" in section
        bootstrap_call = 'write_sources "${main_host}" "${security_host}"; \\'
        secure_call = 'write_secure_sources "${main_host}" "${security_host}"; \\'
        assert bootstrap_call in section
        assert secure_call in section
        assert section.index(bootstrap_call) < section.index(initial_install_marker)
        assert section.rindex(fallback_install_marker) < section.index(secure_call)

    assert_stage_contract(
        builder_section,
        'if ! install_build_packages; then \\',
        'install_build_packages; \\',
    )
    assert_stage_contract(
        runtime_section,
        'if ! install_runtime_packages; then \\',
        'install_runtime_packages; \\',
    )
def test_runner_dockerfiles_exist_for_all_migrated_scanners() -> None:
    opengrep_runner_text = (
        REPO_ROOT / "docker" / "opengrep-runner.Dockerfile"
    ).read_text(encoding="utf-8")
    flow_parser_runner_text = (
        REPO_ROOT / "docker" / "flow-parser-runner.Dockerfile"
    ).read_text(encoding="utf-8")

    assert not (REPO_ROOT / "docker" / "bandit-runner.Dockerfile").exists()
    assert not (REPO_ROOT / "docker" / "gitleaks-runner.Dockerfile").exists()
    assert not (REPO_ROOT / "docker" / "phpstan-runner.Dockerfile").exists()
    assert not (REPO_ROOT / "docker" / "pmd-runner.Dockerfile").exists()
    assert not (REPO_ROOT / "docker" / "backend_old.Dockerfile").exists()

    runner_texts = [
        opengrep_runner_text,
        flow_parser_runner_text,
    ]

    assert "WORKDIR /scan" in opengrep_runner_text
    assert "opengrep" in opengrep_runner_text
    assert "XDG_CACHE_HOME" in opengrep_runner_text
    assert "backend-opengrep-launcher" not in opengrep_runner_text
    assert "exec /opt/opengrep/opengrep.real \"$@\"" in opengrep_runner_text
    assert "WORKDIR /scan" in flow_parser_runner_text
    assert "flow_parser_runner.py" in flow_parser_runner_text

    backend_cargo_text = (REPO_ROOT / "backend" / "Cargo.toml").read_text(encoding="utf-8")
    assert "backend-opengrep-launcher" not in backend_cargo_text
    assert "backend-phpstan-launcher" not in backend_cargo_text

    for runner_text in runner_texts:
        assert "FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim-trixie" in runner_text
        assert 'rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true;' in runner_text


def test_docker_publish_pushes_all_runner_images() -> None:
    reusable_workflow_text = (REPO_ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(
        encoding="utf-8"
    )
    orchestrator_workflow_path = REPO_ROOT / ".github" / "workflows" / "publish-runtime-images.yml"
    orchestrator_workflow_text = orchestrator_workflow_path.read_text(encoding="utf-8")
    runners_workflow_text = (REPO_ROOT / ".github" / "workflows" / "docker-publish-runners.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_call:" in reusable_workflow_text
    assert "build-and-publish:" in reusable_workflow_text
    assert 'default: "linux/amd64,linux/arm64"' in reusable_workflow_text
    assert "docker/setup-qemu-action@v4" in reusable_workflow_text
    assert "docker/setup-buildx-action@v4" in reusable_workflow_text
    assert "docker/build-push-action@v7" in reusable_workflow_text
    assert "image_namespace:" in reusable_workflow_text
    assert "package_visibility:" in reusable_workflow_text
    assert "inputs.image_namespace != '' && inputs.image_namespace || github.repository_owner" in reusable_workflow_text
    assert "GHCR_PACKAGE_VISIBILITY: ${{ inputs.package_visibility }}" in reusable_workflow_text
    assert "GHCR_USERNAME" in reusable_workflow_text
    assert "GHCR_TOKEN" in reusable_workflow_text
    assert "Publishing to ghcr.io/${VULHUNTER_IMAGE_NAMESPACE} from repository owner ${GITHUB_REPOSITORY_OWNER} requires GHCR_USERNAME and GHCR_TOKEN secrets." in reusable_workflow_text
    assert "if: env.GHCR_PACKAGE_VISIBILITY == 'public'" in reusable_workflow_text
    assert "/orgs/${PACKAGE_OWNER}/packages/container/${PACKAGE_NAME}" in reusable_workflow_text
    assert "/users/${PACKAGE_OWNER}/packages/container/${PACKAGE_NAME}" in reusable_workflow_text
    assert 'echo "visibility=unknown" >> "$GITHUB_OUTPUT"' in reusable_workflow_text
    assert "gh api --method GET" in reusable_workflow_text
    assert "docker logout ghcr.io || true" in reusable_workflow_text
    assert "docker manifest inspect" in reusable_workflow_text
    assert "steps.package-visibility.outputs.visibility == 'public'" in reusable_workflow_text
    assert "Skipping anonymous pull validation because the workflow could not confirm that the package is public with the current GHCR credentials." in reusable_workflow_text

    assert orchestrator_workflow_path.exists()
    assert "workflow_call:" in orchestrator_workflow_text
    assert "build_backend:" in orchestrator_workflow_text
    assert "build_frontend:" in orchestrator_workflow_text
    assert "build_opengrep_runner:" in orchestrator_workflow_text
    assert "build_flow_parser_runner:" in orchestrator_workflow_text
    assert "build_sandbox_runner:" in orchestrator_workflow_text
    assert "selected_count:" in orchestrator_workflow_text
    assert "publish_summary_json:" in orchestrator_workflow_text
    assert '"schema_version": 1' in orchestrator_workflow_text
    assert '"channel": "latest"' in orchestrator_workflow_text
    assert '"selected_images": selected' in orchestrator_workflow_text
    assert '"published_images": published' in orchestrator_workflow_text
    assert 'selected_count={len(selected)}' in orchestrator_workflow_text
    assert "uses: ./.github/workflows/docker-publish.yml" in orchestrator_workflow_text
    assert "vulhunter-backend" in orchestrator_workflow_text
    assert "vulhunter-frontend" in orchestrator_workflow_text
    assert "vulhunter-opengrep-runner" in orchestrator_workflow_text
    assert "vulhunter-flow-parser-runner" in orchestrator_workflow_text
    assert "vulhunter-sandbox-runner" in orchestrator_workflow_text
    assert "./docker/opengrep-runner.Dockerfile" in orchestrator_workflow_text
    assert "./docker/flow-parser-runner.Dockerfile" in orchestrator_workflow_text
    assert "./docker/sandbox-runner.Dockerfile" in orchestrator_workflow_text
    assert "./docker/bandit-runner.Dockerfile" not in orchestrator_workflow_text
    assert "./docker/gitleaks-runner.Dockerfile" not in orchestrator_workflow_text
    assert "./docker/phpstan-runner.Dockerfile" not in orchestrator_workflow_text
    assert "./docker/pmd-runner.Dockerfile" not in orchestrator_workflow_text

    assert "\n  push:\n" in runners_workflow_text
    assert "\n    branches:\n      - main\n" in runners_workflow_text
    assert "\n    paths:\n" in runners_workflow_text
    assert ".github/workflows/publish-runtime-images.yml" in runners_workflow_text
    assert "workflow_dispatch:" not in runners_workflow_text
    assert "detect-runner-changes:" in runners_workflow_text
    assert "dorny/paths-filter@v3" in runners_workflow_text
    assert "publish-runners:" in runners_workflow_text
    assert "nothing-to-publish:" in runners_workflow_text
    assert "build_opengrep_runner" in runners_workflow_text
    assert "build_bandit_runner" not in runners_workflow_text
    assert "build_gitleaks_runner" not in runners_workflow_text
    assert "build_phpstan_runner" not in runners_workflow_text
    assert "build_flow_parser_runner" in runners_workflow_text
    assert "build_pmd_runner" not in runners_workflow_text
    assert "build_sandbox_runner" in runners_workflow_text
    assert "build_sandbox:" not in runners_workflow_text
    assert "'backend/scripts/**'" in runners_workflow_text
    assert "'backend_old/scripts/**'" not in runners_workflow_text
    assert '"backend/scripts/**"' in runners_workflow_text
    assert '"backend_old/scripts/**"' not in runners_workflow_text
    assert "uses: ./.github/workflows/publish-runtime-images.yml" in runners_workflow_text


def test_main_push_auto_builds_frontend_and_backend_latest_only() -> None:
    frontend_workflow_text = (REPO_ROOT / ".github" / "workflows" / "docker-publish-frontend.yml").read_text(
        encoding="utf-8"
    )
    backend_workflow_text = (REPO_ROOT / ".github" / "workflows" / "docker-publish-backend.yml").read_text(
        encoding="utf-8"
    )
    reusable_workflow_text = (REPO_ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(
        encoding="utf-8"
    )
    manual_entrypoint_workflow_text = (
        REPO_ROOT / ".github" / "workflows" / "docker-publish-runtime-images.yml"
    ).read_text(encoding="utf-8")

    assert "\n  push:\n" in frontend_workflow_text
    assert "- \"frontend/**\"" in frontend_workflow_text
    assert "- \"docker/frontend.Dockerfile\"" in frontend_workflow_text
    assert "- \".github/workflows/publish-runtime-images.yml\"" in frontend_workflow_text
    assert "workflow_dispatch:" not in frontend_workflow_text
    assert "uses: ./.github/workflows/publish-runtime-images.yml" in frontend_workflow_text
    assert "build_frontend: true" in frontend_workflow_text
    assert "build_backend: false" in frontend_workflow_text

    assert "\n  push:\n" in backend_workflow_text
    assert "- \"backend/**\"" in backend_workflow_text
    assert "- \"docker/backend.Dockerfile\"" in backend_workflow_text
    assert "- \".github/workflows/publish-runtime-images.yml\"" in backend_workflow_text
    assert "workflow_dispatch:" not in backend_workflow_text
    assert "uses: ./.github/workflows/publish-runtime-images.yml" in backend_workflow_text
    assert "build_backend: true" in backend_workflow_text
    assert "build_frontend: false" in backend_workflow_text

    assert "VULHUNTER_IMAGE_TAG: latest" in reusable_workflow_text
    assert 'default: "linux/amd64,linux/arm64"' in reusable_workflow_text
    assert "workflow_dispatch:" in manual_entrypoint_workflow_text
    assert "uses: ./.github/workflows/publish-runtime-images.yml" in manual_entrypoint_workflow_text
    assert "build_backend:" in manual_entrypoint_workflow_text
    assert "build_frontend:" in manual_entrypoint_workflow_text
    assert "build_opengrep_runner:" in manual_entrypoint_workflow_text
    assert "build_flow_parser_runner:" in manual_entrypoint_workflow_text
    assert "build_sandbox_runner:" in manual_entrypoint_workflow_text


def test_release_workflow_builds_slim_release_tree() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )

    assert "generate-release-branch.sh" in workflow_text
    assert "--validate" in workflow_text
    assert "docker compose config" in workflow_text
    assert "git push --force origin HEAD:release" in workflow_text
    assert "workflow_dispatch:" in workflow_text
    assert "tags:" not in workflow_text
