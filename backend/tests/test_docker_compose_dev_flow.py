from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_SERVICE_NAMES = (
    "yasa-runner",
    "opengrep-runner",
    "bandit-runner",
    "gitleaks-runner",
    "phpstan-runner",
    "pmd-runner",
    "flow-parser-runner",
)
DEFAULT_BACKEND_IMAGE = (
    "${BACKEND_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}"
    "/vulhunter-backend:${VULHUNTER_IMAGE_TAG:-latest}}"
)
DEFAULT_FRONTEND_IMAGE = (
    "${FRONTEND_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}"
    "/vulhunter-frontend:${VULHUNTER_IMAGE_TAG:-latest}}"
)
DEFAULT_SANDBOX_IMAGE = (
    "${SANDBOX_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}"
    "/vulhunter-sandbox:${VULHUNTER_IMAGE_TAG:-latest}}"
)
DEFAULT_SCANNER_PMD_IMAGE = (
    "${SCANNER_PMD_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}"
    "/vulhunter-pmd-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
)


def test_default_compose_uses_backend_managed_runner_preflight() -> None:
    compose_path = REPO_ROOT / "docker-compose.yml"
    full_overlay_path = REPO_ROOT / "docker-compose.full.yml"
    backend_dockerfile = REPO_ROOT / "docker" / "backend.Dockerfile"
    frontend_dockerfile = REPO_ROOT / "docker" / "frontend.Dockerfile"

    assert compose_path.exists()
    assert full_overlay_path.exists()
    assert not (REPO_ROOT / "docker-compose.dev.yml").exists()
    assert not (REPO_ROOT / "docker-compose.frontend-dev.yml").exists()
    assert not (REPO_ROOT / "docker-compose.override.yml").exists()
    assert not (REPO_ROOT / "docker-compose.prod.yml").exists()
    assert not (REPO_ROOT / "docker-compose.prod.cn.yml").exists()

    compose_text = compose_path.read_text(encoding="utf-8")
    assert "runner preflight / warmup" not in compose_text
    assert "一次性预热/自检容器" not in compose_text
    assert "执行完检查后按预期退出" not in compose_text
    assert 'condition: service_completed_successfully' not in compose_text
    for runner_service in RUNNER_SERVICE_NAMES:
        assert f"\n  {runner_service}:" not in compose_text
    assert f"image: {DEFAULT_BACKEND_IMAGE}" in compose_text
    assert f"image: {DEFAULT_FRONTEND_IMAGE}" in compose_text
    assert "vulhunter/backend-dev:latest" not in compose_text
    assert "vulhunter/frontend-dev:latest" not in compose_text
    assert "target: dev-runtime" not in compose_text
    assert "target: dev" not in compose_text
    assert "\n  backend:\n" in compose_text
    assert "\n  frontend:\n" in compose_text
    assert "\n  nexus-web:\n" in compose_text
    assert "\n  nexus-itemDetail:\n" in compose_text
    assert "./backend:/app" not in compose_text
    assert ".:/workspace:ro" not in compose_text
    assert "./frontend:/app" not in compose_text
    assert "./frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" not in compose_text
    assert "- /opt/backend-venv" not in compose_text
    assert "/app/.venv" not in compose_text
    assert "/root/.cache/uv" not in compose_text
    assert "/app/node_modules" not in compose_text
    assert "/pnpm/store" not in compose_text
    assert "${VULHUNTER_FRONTEND_PORT:-3000}:80" in compose_text
    assert 'FRONTEND_PUBLIC_URL: http://localhost:${VULHUNTER_FRONTEND_PORT:-3000}' not in compose_text
    assert 'BACKEND_PUBLIC_URL: http://localhost:${VULHUNTER_BACKEND_PORT:-8000}' not in compose_text
    assert "command: /app/scripts/dev-entrypoint.sh" not in compose_text
    assert "command:\n      - sh\n      - /app/scripts/dev-entrypoint.sh" not in compose_text
    assert "BACKEND_PYPI_INDEX_PRIMARY: ${BACKEND_PYPI_INDEX_PRIMARY:-}" in compose_text
    assert "BACKEND_PYPI_INDEX_FALLBACK: ${BACKEND_PYPI_INDEX_FALLBACK:-}" in compose_text
    assert "BACKEND_INSTALL_YASA" not in compose_text
    assert "YASA_VERSION:" not in compose_text
    assert "BACKEND_PYPI_INDEX_CANDIDATES: ${BACKEND_PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/" in compose_text
    assert "YASA_ENABLED: ${YASA_ENABLED:-true}" in compose_text
    assert "SCAN_WORKSPACE_ROOT: ${SCAN_WORKSPACE_ROOT:-/tmp/vulhunter/scans}" in compose_text
    assert "SCAN_WORKSPACE_VOLUME: ${SCAN_WORKSPACE_VOLUME:-vulhunter_scan_workspace}" in compose_text
    assert "GHCR_REGISTRY: ${GHCR_REGISTRY:-ghcr.io}" in compose_text
    assert "VULHUNTER_IMAGE_NAMESPACE: ${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}" in compose_text
    assert "VULHUNTER_IMAGE_TAG: ${VULHUNTER_IMAGE_TAG:-latest}" in compose_text
    assert (
        "SCANNER_YASA_IMAGE: ${SCANNER_YASA_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-yasa-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert (
        "SCANNER_OPENGREP_IMAGE: ${SCANNER_OPENGREP_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-opengrep-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert (
        "SCANNER_BANDIT_IMAGE: ${SCANNER_BANDIT_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-bandit-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert (
        "SCANNER_GITLEAKS_IMAGE: ${SCANNER_GITLEAKS_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-gitleaks-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert (
        "SCANNER_PHPSTAN_IMAGE: ${SCANNER_PHPSTAN_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-phpstan-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert f"SCANNER_PMD_IMAGE: {DEFAULT_SCANNER_PMD_IMAGE}" in compose_text
    assert (
        "FLOW_PARSER_RUNNER_IMAGE: ${FLOW_PARSER_RUNNER_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-flow-parser-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert 'FLOW_PARSER_RUNNER_ENABLED: "${FLOW_PARSER_RUNNER_ENABLED:-true}"' in compose_text
    assert 'FLOW_PARSER_RUNNER_TIMEOUT_SECONDS: "${FLOW_PARSER_RUNNER_TIMEOUT_SECONDS:-120}"' in compose_text
    assert "YASA_TIMEOUT_SECONDS: ${YASA_TIMEOUT_SECONDS:-600}" in compose_text
    assert "/tmp/vulhunter/scans:/tmp/vulhunter/scans" not in compose_text
    assert "scan_workspace:/tmp/vulhunter/scans" in compose_text
    assert "${DOCKER_SOCKET_PATH:-/var/run/docker.sock}:/var/run/docker.sock" in compose_text
    assert "RUNNER_PREFLIGHT_BUILD_CONTEXT: /opt/backend-build-context" in compose_text
    assert 'RUNNER_PREFLIGHT_STRICT: "${RUNNER_PREFLIGHT_STRICT:-true}"' in compose_text
    assert "MCP_REQUIRE_ALL_READY_ON_STARTUP" not in compose_text
    assert '/bin/sh", "-lc"' not in compose_text
    assert (
        "SANDBOX_RUNNER_IMAGE: ${SANDBOX_RUNNER_IMAGE:-${GHCR_REGISTRY:-ghcr.io}/${VULHUNTER_IMAGE_NAMESPACE:-unbengable12}/"
        "vulhunter-sandbox-runner:${VULHUNTER_IMAGE_TAG:-latest}}"
    ) in compose_text
    assert 'SANDBOX_RUNNER_ENABLED: "${SANDBOX_RUNNER_ENABLED:-true}"' in compose_text
    assert "BACKEND_NPM_REGISTRY_PRIMARY" not in compose_text
    assert "BACKEND_NPM_REGISTRY_FALLBACK" not in compose_text
    assert "BACKEND_NPM_REGISTRY_CANDIDATES" not in compose_text
    assert "BACKEND_PNPM_VERSION" not in compose_text
    assert "BACKEND_PNPM_CMD_TIMEOUT_SECONDS" not in compose_text
    assert "BACKEND_PNPM_INSTALL_OPTIONAL" not in compose_text
    assert "MCP_REQUIRED_RUNTIME_DOMAIN" not in compose_text
    assert "MCP_CODE_INDEX_ENABLED" not in compose_text
    assert "SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP" not in compose_text
    assert "CODEX_SKILLS_AUTO_INSTALL" not in compose_text
    assert 'profiles: [ "tools" ]' in compose_text
    assert "adminer:" in compose_text
    assert "image: ${NEXUS_WEB_IMAGE:-vulhunter/nexus-web-local:latest}" in compose_text
    assert 'pull_policy: ${NEXUS_WEB_PULL_POLICY:-build}' in compose_text
    assert "image: ${NEXUS_ITEM_DETAIL_IMAGE:-vulhunter/nexus-item-detail-local:latest}" in compose_text
    assert 'pull_policy: ${NEXUS_ITEM_DETAIL_PULL_POLICY:-build}' in compose_text
    assert "build:\n      context: ./nexus-web" in compose_text
    assert "build:\n      context: ./nexus-itemDetail" in compose_text
    assert "tags:\n        - ${NEXUS_WEB_LOCAL_IMAGE_ALIAS:-vulhunter/nexus-web-local:latest}" in compose_text
    assert "tags:\n        - ${NEXUS_ITEM_DETAIL_LOCAL_IMAGE_ALIAS:-vulhunter/nexus-item-detail-local:latest}" in compose_text
    assert "YASA_HOST_BIN_PATH" not in compose_text
    assert "YASA_HOST_RESOURCE_DIR" not in compose_text
    assert "YASA_BIN_PATH:" not in compose_text
    assert "YASA_RESOURCE_DIR:" not in compose_text
    assert "\n  frontend-dev:" not in compose_text

    backend_text = backend_dockerfile.read_text(encoding="utf-8")
    assert "FROM runtime-base AS dev-runtime" in backend_text
    assert 'COPY backend/scripts/package_source_selector.py /usr/local/bin/package_source_selector.py' in backend_text
    assert "BACKEND_INSTALL_YASA" not in backend_text
    assert "ARG YASA_VERSION=" not in backend_text
    assert "backend-dev-entrypoint.sh" not in backend_text
    assert 'CMD ["/bin/sh", "/usr/local/bin/backend-dev-entrypoint.sh"]' not in backend_text
    assert 'CMD ["/bin/sh", "/app/docker-entrypoint.sh"]' not in backend_text
    assert "https://github.com/antgroup/YASA-Engine/archive/refs/tags/${YASA_VERSION}.tar.gz" not in backend_text
    assert "COPY frontend/yasa-engine-overrides /tmp/yasa-engine-overrides" not in backend_text
    assert "COPY frontend/yasa-engine-overrides /opt/backend-build-context/frontend/yasa-engine-overrides" in backend_text
    assert 'best_index="$(cat /tmp/pypi-best-index)"' in backend_text
    assert 'for idx in "$@"; do \\' in backend_text
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


def test_full_overlay_restores_full_local_build_defaults() -> None:
    full_overlay_text = (REPO_ROOT / "docker-compose.full.yml").read_text(encoding="utf-8")

    assert "runner preflight / warmup" not in full_overlay_text
    assert "一次性预热/自检容器" not in full_overlay_text
    assert "执行完检查后按预期退出" not in full_overlay_text
    assert 'condition: service_completed_successfully' not in full_overlay_text
    for runner_service in RUNNER_SERVICE_NAMES:
        assert f"\n  {runner_service}:" not in full_overlay_text
    assert "vulhunter/backend-local:latest" in full_overlay_text
    assert "vulhunter/backend-dev-local:latest" not in full_overlay_text
    assert "vulhunter/frontend-local:latest" in full_overlay_text
    assert "image: ${NEXUS_WEB_IMAGE:-vulhunter/nexus-web-local:latest}" in full_overlay_text
    assert 'pull_policy: ${NEXUS_WEB_PULL_POLICY:-build}' in full_overlay_text
    assert "image: ${NEXUS_ITEM_DETAIL_IMAGE:-vulhunter/nexus-item-detail-local:latest}" in full_overlay_text
    assert 'pull_policy: ${NEXUS_ITEM_DETAIL_PULL_POLICY:-build}' in full_overlay_text
    assert "context: ." in full_overlay_text
    assert "dockerfile: docker/backend.Dockerfile" in full_overlay_text
    assert "working_dir: !reset null" in full_overlay_text
    assert "command: !reset null" in full_overlay_text
    assert "./frontend:/app" in full_overlay_text
    assert "${VULHUNTER_FRONTEND_PORT:-3000}:5173" in full_overlay_text
    assert "VITE_API_TARGET: http://backend:8000" in full_overlay_text
    assert "CODEX_SKILLS_AUTO_INSTALL" not in full_overlay_text
    assert "BACKEND_INSTALL_YASA" not in full_overlay_text
    assert "YASA_VERSION=" not in full_overlay_text
    assert "SCANNER_YASA_IMAGE: ${SCANNER_YASA_IMAGE:-vulhunter/yasa-runner-local:latest}" in full_overlay_text
    assert "SCANNER_OPENGREP_IMAGE: ${SCANNER_OPENGREP_IMAGE:-vulhunter/opengrep-runner-local:latest}" in full_overlay_text
    assert "SCANNER_BANDIT_IMAGE: ${SCANNER_BANDIT_IMAGE:-vulhunter/bandit-runner-local:latest}" in full_overlay_text
    assert "SCANNER_GITLEAKS_IMAGE: ${SCANNER_GITLEAKS_IMAGE:-vulhunter/gitleaks-runner-local:latest}" in full_overlay_text
    assert "SCANNER_PHPSTAN_IMAGE: ${SCANNER_PHPSTAN_IMAGE:-vulhunter/phpstan-runner-local:latest}" in full_overlay_text
    assert "SCANNER_PMD_IMAGE: ${SCANNER_PMD_IMAGE:-vulhunter/pmd-runner-local:latest}" in full_overlay_text
    assert "FLOW_PARSER_RUNNER_IMAGE: ${FLOW_PARSER_RUNNER_IMAGE:-vulhunter/flow-parser-runner-local:latest}" in full_overlay_text
    assert "- BACKEND_PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/" in full_overlay_text
    assert "SCAN_WORKSPACE_ROOT: ${SCAN_WORKSPACE_ROOT:-/tmp/vulhunter/scans}" in full_overlay_text
    assert "SCAN_WORKSPACE_VOLUME: ${SCAN_WORKSPACE_VOLUME:-vulhunter_scan_workspace}" in full_overlay_text
    assert "BACKEND_NPM_REGISTRY_PRIMARY" not in full_overlay_text
    assert "BACKEND_NPM_REGISTRY_FALLBACK" not in full_overlay_text
    assert "BACKEND_NPM_REGISTRY_CANDIDATES" not in full_overlay_text
    assert "BACKEND_PNPM_VERSION" not in full_overlay_text
    assert "BACKEND_PNPM_CMD_TIMEOUT_SECONDS" not in full_overlay_text
    assert "BACKEND_PNPM_INSTALL_OPTIONAL" not in full_overlay_text
    assert "MCP_REQUIRED_RUNTIME_DOMAIN" not in full_overlay_text
    assert "SANDBOX_IMAGE: ${SANDBOX_IMAGE:-vulhunter/sandbox-local:latest}" in full_overlay_text
    assert "SANDBOX_RUNNER_IMAGE: ${SANDBOX_RUNNER_IMAGE:-vulhunter/sandbox-runner-local:latest}" in full_overlay_text
    assert 'SANDBOX_RUNNER_ENABLED: "${SANDBOX_RUNNER_ENABLED:-true}"' in full_overlay_text
    assert "\n  frontend-dev:" not in full_overlay_text


def test_backend_dockerfile_builds_linux_arm64_yasa_from_source() -> None:
    backend_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "COPY frontend/yasa-engine-overrides /opt/backend-build-context/frontend/yasa-engine-overrides" in backend_text
    assert "RUNNER_PREFLIGHT_BUILD_CONTEXT=/opt/backend-build-context" in backend_text
    assert 'CMD ["python3", "-m", "app.runtime.container_startup", "prod"]' in backend_text


def test_nexus_web_dockerfile_pins_pnpm_before_nginx_runtime() -> None:
    nexus_dockerfile = (REPO_ROOT / "docker" / "nexus-web.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "FROM ${DOCKERHUB_LIBRARY_MIRROR:-docker.m.daocloud.io/library}/nginx:alpine" in nexus_dockerfile
    assert "COPY ./dist /usr/share/nginx/html" in nexus_dockerfile
    assert "COPY ./nginx.conf /etc/nginx/nginx.conf" in nexus_dockerfile
    assert "EXPOSE 5174" in nexus_dockerfile


def test_scripts_and_packaging_use_new_compose_layout() -> None:
    dev_frontend_script_path = REPO_ROOT / "scripts" / "dev-frontend.sh"
    dev_frontend_script = (
        dev_frontend_script_path.read_text(encoding="utf-8")
        if dev_frontend_script_path.exists()
        else None
    )
    frontend_exec_script = (
        REPO_ROOT / "frontend" / "scripts" / "run-in-dev-container.sh"
    ).read_text(encoding="utf-8")
    package_script_path = REPO_ROOT / "scripts" / "package-release-artifacts.sh"
    package_script = (
        package_script_path.read_text(encoding="utf-8")
        if package_script_path.exists()
        else None
    )
    deploy_script_path = REPO_ROOT / "scripts" / "deploy-release-artifacts.sh"
    deploy_script = (
        deploy_script_path.read_text(encoding="utf-8")
        if deploy_script_path.exists()
        else None
    )
    deb_build_script_path = REPO_ROOT / "packaging" / "deb" / "build_deb.sh"
    deb_build_script = (
        deb_build_script_path.read_text(encoding="utf-8")
        if deb_build_script_path.exists()
        else None
    )
    compose_wrapper_script = (
        REPO_ROOT / "scripts" / "compose-up-with-fallback.sh"
    ).read_text(encoding="utf-8")
    compose_wrapper_ps1 = (
        REPO_ROOT / "scripts" / "compose-up-with-fallback.ps1"
    ).read_text(encoding="utf-8")
    local_build_script = (
        REPO_ROOT / "scripts" / "compose-up-local-build.sh"
    ).read_text(encoding="utf-8")

    if dev_frontend_script is not None:
        assert "docker compose up -d db redis backend frontend" in dev_frontend_script
        assert "frontend-dev" not in dev_frontend_script
    assert 'COMPOSE=(docker compose -f "$REPO_ROOT/docker-compose.yml")' in frontend_exec_script
    assert 'SERVICE="frontend"' in frontend_exec_script
    assert "docker-compose.frontend-dev.yml" not in frontend_exec_script

    if package_script is not None:
        assert '-f "${ROOT_DIR}/docker-compose.full.yml"' in package_script
        assert 'cp "$ROOT_DIR/docker-compose.full.yml" "$tmp_root/"' in package_script
        assert '-f "${ROOT_DIR}/docker-compose.hybrid.yml"' in package_script
        assert 'cp "$ROOT_DIR/docker-compose.hybrid.yml" "$tmp_root/"' in package_script
        assert '-f "${ROOT_DIR}/docker-compose.self-contained.yml"' in package_script
        assert 'cp "$ROOT_DIR/docker-compose.self-contained.yml" "$tmp_root/"' in package_script
    if deploy_script is not None:
        assert '-f "${TARGET_DIR}/docker-compose.full.yml"' in deploy_script

    if deb_build_script is not None:
        assert (REPO_ROOT / "deploy" / "compose" / "docker-compose.prod.yml").exists()
        assert (REPO_ROOT / "deploy" / "compose" / "docker-compose.prod.cn.yml").exists()
        assert 'cp "$ROOT_DIR/deploy/compose/docker-compose.prod.yml"' in deb_build_script
        assert 'cp "$ROOT_DIR/deploy/compose/docker-compose.prod.cn.yml"' in deb_build_script
    assert "detect_compose_cmd() {" in compose_wrapper_script
    assert 'COMPOSE_ARGS=("$@")' in compose_wrapper_script
    assert "function Detect-ComposeCommand" in compose_wrapper_ps1
    assert "compose-up-with-fallback.ps1" in compose_wrapper_ps1
    assert '"${COMPOSE[@]}" build backend' in local_build_script
    assert '"${COMPOSE[@]}" build frontend' in local_build_script
    assert '"${COMPOSE[@]}" build nexus-web' in local_build_script
    assert '"${COMPOSE[@]}" build nexus-itemDetail' in local_build_script
    assert '"${COMPOSE[@]}" up -d' in local_build_script


def test_readmes_document_backend_managed_preflight_behavior() -> None:
    root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    root_readme_en = (REPO_ROOT / "README_EN.md").read_text(encoding="utf-8")
    compose_readme = (REPO_ROOT / "scripts" / "README-COMPOSE.md").read_text(encoding="utf-8")

    assert "docker compose up" in root_readme
    assert "docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build" in root_readme
    assert "docker-compose.full.yml" not in root_readme
    assert "docker-compose.self-contained.yml" not in root_readme
    assert "package-release-artifacts.sh" not in root_readme
    assert "scripts/README-COMPOSE.md" in root_readme
    assert "docker compose up" in root_readme_en
    assert "docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build" in root_readme_en
    assert "docker-compose.full.yml" not in root_readme_en
    assert "docker-compose.self-contained.yml" not in root_readme_en
    assert "package-release-artifacts.sh" not in root_readme_en
    assert "scripts/README-COMPOSE.md" in root_readme_en
    assert "docker compose up" in compose_readme
    assert "docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build" in compose_readme
    assert "docker-compose.full.yml" not in compose_readme
    assert "docker-compose.self-contained.yml" not in compose_readme
    assert "package-release-artifacts.sh" not in compose_readme
    assert "deploy-release-artifacts.sh" not in compose_readme
    assert "docker/env/backend/env.example" in compose_readme


def test_backend_runtime_python_tools_are_installed_via_backend_venv() -> None:
    backend_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(
        encoding="utf-8"
    )
    pyproject_text = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    yasa_runner_text = (REPO_ROOT / "docker" / "yasa-runner.Dockerfile").read_text(
        encoding="utf-8"
    )
    flow_parser_runner_text = (
        REPO_ROOT / "docker" / "flow-parser-runner.Dockerfile"
    ).read_text(encoding="utf-8")
    dev_runtime_text = backend_text.split("FROM runtime-base AS dev-runtime", maxsplit=1)[1].split(
        "FROM runtime-base AS runtime",
        maxsplit=1,
    )[0]
    runtime_text = backend_text.split("FROM runtime-base AS runtime", maxsplit=1)[1]

    assert '"code2flow>=' not in pyproject_text
    assert '"bandit>=' not in pyproject_text
    assert '"tree-sitter>=' not in pyproject_text
    assert '"tree-sitter-language-pack>=' not in pyproject_text
    assert "pip install --retries 5 --timeout 60 --disable-pip-version-check code2flow bandit" not in backend_text
    assert "install_python_helpers()" not in backend_text
    assert "gitleaks; \\" not in backend_text
    assert "ENV BACKEND_VENV_PATH=/opt/backend-venv" in backend_text
    assert 'uv venv "${BACKEND_VENV_PATH}"' in backend_text
    assert 'uv sync --active --frozen --no-dev' in backend_text
    assert "COPY --from=builder /app/.venv /opt/backend-venv" not in backend_text
    assert "COPY --from=builder /opt/backend-venv /opt/backend-venv" not in dev_runtime_text
    assert "COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv" in dev_runtime_text
    assert "mkdir -p /app /opt/backend-venv /root/.cache/uv /app/uploads/zip_files /app/data/runtime" in dev_runtime_text
    assert "COPY --from=builder /opt/backend-venv /opt/backend-venv" in runtime_text
    assert "COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv" not in runtime_text
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
    assert 'rm -rf /root/.cache/pip' in backend_text
    assert 'rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.11' in backend_text
    assert "FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim" in yasa_runner_text
    assert "AS yasa-builder" in yasa_runner_text
    assert "AS yasa-runner" in yasa_runner_text
    assert "/opt/yasa/bin/yasa" in yasa_runner_text
    assert "/opt/yasa-runtime" in yasa_runner_text
    assert "COPY frontend/yasa-engine-overrides /tmp/yasa-engine-overrides" in yasa_runner_text
    assert "COPY --from=yasa-builder /opt/yasa-runtime /opt/yasa" in yasa_runner_text
    assert "YASA runner placeholder" not in yasa_runner_text
    assert "node_modules" not in yasa_runner_text
    assert "WORKDIR /scan" in yasa_runner_text
    assert "tree-sitter-language-pack" in flow_parser_runner_text
    assert "code2flow" in flow_parser_runner_text
    assert "ARG BACKEND_PYPI_INDEX_CANDIDATES=" in flow_parser_runner_text
    assert 'ENV PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES}' in flow_parser_runner_text
    assert "COPY backend/scripts/package_source_selector.py /usr/local/bin/package_source_selector.py" in flow_parser_runner_text
    assert 'python3 /usr/local/bin/package_source_selector.py --candidates "${raw_candidates}" --kind pypi --timeout-seconds 2' in flow_parser_runner_text
    assert 'for idx in $(printf \'%s\\n\' "${ordered_pypi_indexes}"); do \\' in flow_parser_runner_text
    assert '/opt/flow-parser-venv/bin/pip install --disable-pip-version-check -i "${idx}" -r /tmp/flow-parser-runner.requirements.txt' in flow_parser_runner_text
    assert 'command -v code2flow >/dev/null 2>&1' in flow_parser_runner_text
    assert 'code2flow --help >/dev/null 2>&1' in flow_parser_runner_text
    assert "python3 /opt/flow-parser/flow_parser_runner.py --help >/dev/null 2>&1" in flow_parser_runner_text
    assert 'CMD ["python3", "/opt/flow-parser/flow_parser_runner.py", "--help"]' in flow_parser_runner_text


def test_backend_dockerfile_derives_docker_cli_image_from_selected_mirror() -> None:
    backend_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(encoding="utf-8")

    assert "ARG DOCKER_CLI_IMAGE=${DOCKERHUB_LIBRARY_MIRROR}/docker:cli" in backend_text
    assert "ARG DOCKER_CLI_IMAGE=docker.m.daocloud.io/docker:cli" not in backend_text


def test_runner_dockerfiles_exist_for_all_migrated_scanners() -> None:
    opengrep_runner_text = (
        REPO_ROOT / "docker" / "opengrep-runner.Dockerfile"
    ).read_text(encoding="utf-8")
    bandit_runner_text = (
        REPO_ROOT / "docker" / "bandit-runner.Dockerfile"
    ).read_text(encoding="utf-8")
    gitleaks_runner_text = (
        REPO_ROOT / "docker" / "gitleaks-runner.Dockerfile"
    ).read_text(encoding="utf-8")
    phpstan_runner_text = (
        REPO_ROOT / "docker" / "phpstan-runner.Dockerfile"
    ).read_text(encoding="utf-8")
    pmd_runner_text = (REPO_ROOT / "docker" / "pmd-runner.Dockerfile").read_text(
        encoding="utf-8"
    )
    flow_parser_runner_text = (
        REPO_ROOT / "docker" / "flow-parser-runner.Dockerfile"
    ).read_text(encoding="utf-8")

    runner_texts = [
        opengrep_runner_text,
        bandit_runner_text,
        gitleaks_runner_text,
        phpstan_runner_text,
        pmd_runner_text,
        flow_parser_runner_text,
    ]

    assert "WORKDIR /scan" in opengrep_runner_text
    assert "opengrep" in opengrep_runner_text
    assert "XDG_CACHE_HOME" in opengrep_runner_text
    assert "WORKDIR /scan" in bandit_runner_text
    assert "bandit" in bandit_runner_text
    assert "/opt/bandit-venv" in bandit_runner_text
    assert "WORKDIR /scan" in gitleaks_runner_text
    assert "gitleaks" in gitleaks_runner_text
    assert "download_with_fallback() {" in gitleaks_runner_text
    assert (
        "https://gh-proxy.com/https://github.com/gitleaks/gitleaks/releases/download/"
        in gitleaks_runner_text
    )
    assert (
        "https://v6.gh-proxy.org/https://github.com/gitleaks/gitleaks/releases/download/"
        in gitleaks_runner_text
    )
    assert "WORKDIR /scan" in phpstan_runner_text
    assert "phpstan" in phpstan_runner_text
    assert "download_with_fallback() {" in phpstan_runner_text
    assert (
        "https://gh-proxy.com/https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar"
        in phpstan_runner_text
    )
    assert (
        "https://v6.gh-proxy.org/https://github.com/phpstan/phpstan/releases/latest/download/phpstan.phar"
        in phpstan_runner_text
    )
    assert "WORKDIR /scan" in pmd_runner_text
    assert "pmd" in pmd_runner_text
    assert "download_with_fallback() {" in pmd_runner_text
    assert (
        "https://gh-proxy.com/https://github.com/pmd/pmd/releases/download/pmd_releases%2F"
        in pmd_runner_text
    )
    assert (
        "https://v6.gh-proxy.org/https://github.com/pmd/pmd/releases/download/pmd_releases%2F"
        in pmd_runner_text
    )
    assert "WORKDIR /scan" in flow_parser_runner_text
    assert "flow_parser_runner.py" in flow_parser_runner_text

    for runner_text in runner_texts:
        assert "FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim-trixie" in runner_text
        assert 'rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true;' in runner_text


def test_docker_publish_pushes_all_runner_images() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(
        encoding="utf-8"
    )

    assert "\n  push:\n" in workflow_text
    assert "\n    branches:\n      - main\n" in workflow_text
    assert "\n    paths:\n" in workflow_text
    assert "\non:\n  push:\n" in workflow_text
    assert "workflow_dispatch:" in workflow_text
    assert "'v*.*.*'" not in workflow_text
    assert "detect-changes:" in workflow_text
    assert "dorny/paths-filter@v3" in workflow_text
    assert "needs.detect-changes.outputs.frontend == 'true'" in workflow_text
    assert "needs.detect-changes.outputs.backend == 'true'" in workflow_text
    assert "tag:" in workflow_text
    assert "build-frontend-latest:" in workflow_text
    assert "build-backend-latest:" in workflow_text
    assert "build-manual:" in workflow_text
    assert "if: github.event_name == 'push'" in workflow_text
    assert "if: github.event_name == 'workflow_dispatch'" in workflow_text
    assert "platforms: linux/amd64" in workflow_text
    assert "build_yasa_runner" in workflow_text
    assert "build_opengrep_runner" in workflow_text
    assert "build_bandit_runner" in workflow_text
    assert "build_gitleaks_runner" in workflow_text
    assert "build_phpstan_runner" in workflow_text
    assert "build_flow_parser_runner" in workflow_text
    assert "build_sandbox_runner" in workflow_text
    assert "./docker/backend.Dockerfile" in workflow_text
    assert "./docker/frontend.Dockerfile" in workflow_text
    assert "context: ." in workflow_text
    assert "./docker/yasa-runner.Dockerfile" in workflow_text
    assert "./docker/opengrep-runner.Dockerfile" in workflow_text
    assert "./docker/bandit-runner.Dockerfile" in workflow_text
    assert "./docker/gitleaks-runner.Dockerfile" in workflow_text
    assert "./docker/phpstan-runner.Dockerfile" in workflow_text
    assert "./docker/flow-parser-runner.Dockerfile" in workflow_text
    assert "./docker/sandbox-runner.Dockerfile" in workflow_text
    assert "VULHUNTER_IMAGE_NAMESPACE" in workflow_text
    assert "GHCR_REGISTRY: ghcr.io" in workflow_text
    assert "build_nexus_web" not in workflow_text
    assert "./nexus-web/src" not in workflow_text
    assert "${{ env.GHCR_REGISTRY }}/${{ env.VULHUNTER_IMAGE_NAMESPACE }}/vulhunter-yasa-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "${{ env.GHCR_REGISTRY }}/${{ env.VULHUNTER_IMAGE_NAMESPACE }}/vulhunter-opengrep-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "${{ env.GHCR_REGISTRY }}/${{ env.VULHUNTER_IMAGE_NAMESPACE }}/vulhunter-bandit-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "${{ env.GHCR_REGISTRY }}/${{ env.VULHUNTER_IMAGE_NAMESPACE }}/vulhunter-gitleaks-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "${{ env.GHCR_REGISTRY }}/${{ env.VULHUNTER_IMAGE_NAMESPACE }}/vulhunter-phpstan-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "${{ env.GHCR_REGISTRY }}/${{ env.VULHUNTER_IMAGE_NAMESPACE }}/vulhunter-flow-parser-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "${{ env.GHCR_REGISTRY }}/${{ env.VULHUNTER_IMAGE_NAMESPACE }}/vulhunter-sandbox-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "docker logout ghcr.io || true" in workflow_text
    assert "docker manifest inspect" in workflow_text


def test_main_push_auto_builds_frontend_and_backend_latest_only() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(
        encoding="utf-8"
    )

    assert "build-frontend-latest:" in workflow_text
    assert "build-backend-latest:" in workflow_text
    assert "vulhunter-frontend:latest" in workflow_text
    assert "vulhunter-backend:latest" in workflow_text
    assert "platforms: linux/amd64" in workflow_text
    assert "platforms: linux/amd64,linux/arm64" in workflow_text
    assert "- 'frontend/**'" in workflow_text
    assert "- 'backend/**'" in workflow_text
    assert "- 'docker/frontend.Dockerfile'" in workflow_text
    assert "- 'docker/backend.Dockerfile'" in workflow_text
    assert "- '.github/workflows/docker-publish.yml'" in workflow_text
    assert "- 'frontend/yasa-engine-overrides/**'" in workflow_text


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
