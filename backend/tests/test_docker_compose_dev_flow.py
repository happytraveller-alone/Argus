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


def test_default_compose_uses_backend_managed_runner_preflight() -> None:
    compose_path = REPO_ROOT / "docker-compose.yml"
    full_overlay_path = REPO_ROOT / "docker-compose.full.yml"
    yasa_host_overlay_path = REPO_ROOT / "docker-compose.yasa-host.yml"
    backend_dockerfile = REPO_ROOT / "docker" / "backend.Dockerfile"
    frontend_dockerfile = REPO_ROOT / "docker" / "frontend.Dockerfile"

    assert compose_path.exists()
    assert full_overlay_path.exists()
    assert yasa_host_overlay_path.exists()
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
    assert "ghcr.io/vulhunter/vulhunter-backend:latest" in compose_text
    assert "ghcr.io/vulhunter/vulhunter-frontend:latest" in compose_text
    assert "vulhunter/backend-dev:latest" not in compose_text
    assert "vulhunter/frontend-dev:latest" not in compose_text
    assert "target: dev-runtime" not in compose_text
    assert "target: dev" not in compose_text
    assert "build:" not in compose_text
    assert "dockerfile:" not in compose_text
    assert "./backend:/app" in compose_text
    assert ".:/workspace:ro" in compose_text
    assert "./frontend:/app" in compose_text
    assert "/opt/backend-venv" in compose_text
    assert "/app/.venv" not in compose_text
    assert "/root/.cache/uv" in compose_text
    assert "/app/node_modules" in compose_text
    assert "/pnpm/store" in compose_text
    assert "${VULHUNTER_FRONTEND_PORT:-3000}:5173" in compose_text
    assert 'FRONTEND_PUBLIC_URL: http://localhost:${VULHUNTER_FRONTEND_PORT:-3000}' in compose_text
    assert 'BACKEND_PUBLIC_URL: http://localhost:${VULHUNTER_BACKEND_PORT:-8000}' in compose_text
    assert "command: /app/scripts/dev-entrypoint.sh" not in compose_text
    assert "command:\n      - sh\n      - /app/scripts/dev-entrypoint.sh" not in compose_text
    assert "BACKEND_PYPI_INDEX_PRIMARY: ${BACKEND_PYPI_INDEX_PRIMARY:-}" in compose_text
    assert "BACKEND_PYPI_INDEX_FALLBACK: ${BACKEND_PYPI_INDEX_FALLBACK:-}" in compose_text
    assert "BACKEND_INSTALL_YASA: ${BACKEND_INSTALL_YASA:-1}" in compose_text
    assert "YASA_VERSION: ${YASA_VERSION:-v0.2.33}" in compose_text
    assert (
        "BACKEND_PYPI_INDEX_CANDIDATES: ${BACKEND_PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/,"
        "https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple}"
    ) in compose_text
    assert "YASA_ENABLED: ${YASA_ENABLED:-true}" in compose_text
    assert "SCAN_WORKSPACE_ROOT: ${SCAN_WORKSPACE_ROOT:-/tmp/vulhunter/scans}" in compose_text
    assert "SCAN_WORKSPACE_VOLUME: ${SCAN_WORKSPACE_VOLUME:-vulhunter_scan_workspace}" in compose_text
    assert "SCANNER_YASA_IMAGE: ${SCANNER_YASA_IMAGE:-ghcr.io/vulhunter/vulhunter-yasa-runner:latest}" in compose_text
    assert "SCANNER_OPENGREP_IMAGE: ${SCANNER_OPENGREP_IMAGE:-ghcr.io/vulhunter/vulhunter-opengrep-runner:latest}" in compose_text
    assert "SCANNER_BANDIT_IMAGE: ${SCANNER_BANDIT_IMAGE:-ghcr.io/vulhunter/vulhunter-bandit-runner:latest}" in compose_text
    assert "SCANNER_GITLEAKS_IMAGE: ${SCANNER_GITLEAKS_IMAGE:-ghcr.io/vulhunter/vulhunter-gitleaks-runner:latest}" in compose_text
    assert "SCANNER_PHPSTAN_IMAGE: ${SCANNER_PHPSTAN_IMAGE:-ghcr.io/vulhunter/vulhunter-phpstan-runner:latest}" in compose_text
    assert "SCANNER_PMD_IMAGE: ${SCANNER_PMD_IMAGE:-ghcr.io/vulhunter/vulhunter-pmd-runner:latest}" in compose_text
    assert "FLOW_PARSER_RUNNER_IMAGE: ${FLOW_PARSER_RUNNER_IMAGE:-ghcr.io/vulhunter/vulhunter-flow-parser-runner:latest}" in compose_text
    assert 'FLOW_PARSER_RUNNER_ENABLED: "${FLOW_PARSER_RUNNER_ENABLED:-true}"' in compose_text
    assert 'FLOW_PARSER_RUNNER_TIMEOUT_SECONDS: "${FLOW_PARSER_RUNNER_TIMEOUT_SECONDS:-120}"' in compose_text
    assert "YASA_TIMEOUT_SECONDS: ${YASA_TIMEOUT_SECONDS:-600}" in compose_text
    assert "/tmp/vulhunter/scans:/tmp/vulhunter/scans" not in compose_text
    assert "scan_workspace:/tmp/vulhunter/scans" in compose_text
    assert "/var/run/docker.sock:/var/run/docker.sock" in compose_text
    assert "RUNNER_PREFLIGHT_BUILD_CONTEXT: /workspace" in compose_text
    assert "MCP_REQUIRE_ALL_READY_ON_STARTUP" not in compose_text
    assert '/bin/sh", "-lc"' not in compose_text
    assert "SANDBOX_RUNNER_IMAGE: ${SANDBOX_RUNNER_IMAGE:-ghcr.io/vulhunter/vulhunter-sandbox-runner:latest}" in compose_text
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
    assert 'profiles: ["tools"]' in compose_text
    assert "adminer:" in compose_text
    assert "YASA_HOST_BIN_PATH" not in compose_text
    assert "YASA_HOST_RESOURCE_DIR" not in compose_text
    assert "YASA_BIN_PATH:" not in compose_text
    assert "YASA_RESOURCE_DIR:" not in compose_text
    assert "\n  frontend-dev:" not in compose_text

    backend_text = backend_dockerfile.read_text(encoding="utf-8")
    assert "FROM runtime-base AS dev-runtime" in backend_text
    assert 'COPY backend/scripts/package_source_selector.py /usr/local/bin/package_source_selector.py' in backend_text
    assert "ARG BACKEND_INSTALL_YASA=1" in backend_text
    assert "ARG YASA_VERSION=v0.2.33" in backend_text
    assert "backend-dev-entrypoint.sh" not in backend_text
    assert 'CMD ["/bin/sh", "/usr/local/bin/backend-dev-entrypoint.sh"]' not in backend_text
    assert 'CMD ["/bin/sh", "/app/docker-entrypoint.sh"]' not in backend_text
    assert "https://github.com/antgroup/YASA-Engine/archive/refs/tags/${YASA_VERSION}.tar.gz" in backend_text
    assert "COPY frontend/yasa-engine-overrides /tmp/yasa-engine-overrides" in backend_text
    assert "COPY frontend/yasa-engine-overrides /opt/backend-build-context/frontend/yasa-engine-overrides" in backend_text
    assert 'ordered_indexes="$(order_indexes "${pypi_index_candidates}")"' in backend_text
    assert 'while IFS= read -r index_url; do' in backend_text
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
    assert "context: ." in full_overlay_text
    assert "dockerfile: docker/backend.Dockerfile" in full_overlay_text
    assert "working_dir: !reset null" in full_overlay_text
    assert "command: !reset null" in full_overlay_text
    assert "./frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" in full_overlay_text
    assert "${VULHUNTER_FRONTEND_PORT:-3000}:80" in full_overlay_text
    assert "VITE_API_BASE_URL: /api/v1" in full_overlay_text
    assert "CODEX_SKILLS_AUTO_INSTALL" not in full_overlay_text
    assert "- BACKEND_INSTALL_YASA=${BACKEND_INSTALL_YASA:-1}" in full_overlay_text
    assert "- YASA_VERSION=${YASA_VERSION:-v0.2.33}" in full_overlay_text
    assert "SCANNER_YASA_IMAGE: ${SCANNER_YASA_IMAGE:-vulhunter/yasa-runner-local:latest}" in full_overlay_text
    assert "SCANNER_OPENGREP_IMAGE: ${SCANNER_OPENGREP_IMAGE:-vulhunter/opengrep-runner-local:latest}" in full_overlay_text
    assert "SCANNER_BANDIT_IMAGE: ${SCANNER_BANDIT_IMAGE:-vulhunter/bandit-runner-local:latest}" in full_overlay_text
    assert "SCANNER_GITLEAKS_IMAGE: ${SCANNER_GITLEAKS_IMAGE:-vulhunter/gitleaks-runner-local:latest}" in full_overlay_text
    assert "SCANNER_PHPSTAN_IMAGE: ${SCANNER_PHPSTAN_IMAGE:-vulhunter/phpstan-runner-local:latest}" in full_overlay_text
    assert "SCANNER_PMD_IMAGE: ${SCANNER_PMD_IMAGE:-vulhunter/pmd-runner-local:latest}" in full_overlay_text
    assert "FLOW_PARSER_RUNNER_IMAGE: ${FLOW_PARSER_RUNNER_IMAGE:-vulhunter/flow-parser-runner-local:latest}" in full_overlay_text
    assert (
        "- BACKEND_PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES:-"
        "https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,"
        "https://pypi.org/simple}"
    ) in full_overlay_text
    assert "SCAN_WORKSPACE_ROOT: ${SCAN_WORKSPACE_ROOT:-/tmp/vulhunter/scans}" in full_overlay_text
    assert "SCAN_WORKSPACE_VOLUME: ${SCAN_WORKSPACE_VOLUME:-vulhunter_scan_workspace}" in full_overlay_text
    assert "BACKEND_NPM_REGISTRY_PRIMARY" not in full_overlay_text
    assert "BACKEND_NPM_REGISTRY_FALLBACK" not in full_overlay_text
    assert "BACKEND_NPM_REGISTRY_CANDIDATES" not in full_overlay_text
    assert "BACKEND_PNPM_VERSION" not in full_overlay_text
    assert "BACKEND_PNPM_CMD_TIMEOUT_SECONDS" not in full_overlay_text
    assert "BACKEND_PNPM_INSTALL_OPTIONAL" not in full_overlay_text
    assert "MCP_REQUIRED_RUNTIME_DOMAIN" not in full_overlay_text
    assert "  sandbox:" in full_overlay_text
    assert "vulhunter/sandbox-local:latest" in full_overlay_text
    assert "docker/sandbox.Dockerfile" in full_overlay_text
    assert "SANDBOX_IMAGE: ${SANDBOX_IMAGE:-vulhunter/sandbox-local:latest}" in full_overlay_text
    assert "SANDBOX_RUNNER_IMAGE: ${SANDBOX_RUNNER_IMAGE:-vulhunter/sandbox-runner-local:latest}" in full_overlay_text
    assert 'SANDBOX_RUNNER_ENABLED: "${SANDBOX_RUNNER_ENABLED:-true}"' in full_overlay_text
    assert "\n  frontend-dev:" not in full_overlay_text


def test_backend_dockerfile_builds_linux_arm64_yasa_from_source() -> None:
    backend_text = (REPO_ROOT / "docker" / "backend.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert 'ARG YASA_UAST_VERSION=v0.2.8' in backend_text
    assert 'UAST_PLATFORM="linux-arm64"; \\' in backend_text
    assert 'YASA_UAST_BUILD_MODE="source"; \\' in backend_text
    assert 'CGO_ENABLED=0 GOOS=linux GOARCH="${YASA_GO_ARCH}"' in backend_text
    assert 'go build -o "${YASA_ENGINE_DIR}/deps/uast4go/uast4go" .' in backend_text
    assert 'python3 -m venv "${YASA_HOME}/uast4py-venv"; \\' in backend_text
    assert 'COPY --chmod=755 backend/app/runtime/launchers/yasa_uast4py_launcher.py /tmp/yasa-launchers/uast4py' in backend_text
    assert 'cp /tmp/yasa-launchers/uast4py "${YASA_ENGINE_DIR}/deps/uast4py/uast4py"; \\' in backend_text


def test_nexus_web_dockerfile_pins_pnpm_before_nginx_runtime() -> None:
    nexus_dockerfile = (REPO_ROOT / "docker" / "nexus-web.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert 'corepack prepare "pnpm@${NEXUS_WEB_PNPM_VERSION}" --activate' in nexus_dockerfile
    assert 'if (pkg.packageManager) process.exit(0);' in nexus_dockerfile
    assert 'pkg.packageManager = `pnpm@${process.env.NEXUS_WEB_PNPM_VERSION}`;' in nexus_dockerfile
    assert "FROM ${DOCKERHUB_LIBRARY_MIRROR}/nginx:1.27-alpine AS runtime" in nexus_dockerfile
    assert 'CMD ["nginx", "-g", "daemon off;"]' in nexus_dockerfile


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

    if dev_frontend_script is not None:
        assert "docker compose up -d db redis backend frontend" in dev_frontend_script
        assert "frontend-dev" not in dev_frontend_script
    assert 'COMPOSE=(docker compose -f "$REPO_ROOT/docker-compose.yml")' in frontend_exec_script
    assert 'SERVICE="frontend"' in frontend_exec_script
    assert "docker-compose.frontend-dev.yml" not in frontend_exec_script

    if package_script is not None:
        assert '-f "${ROOT_DIR}/docker-compose.full.yml"' in package_script
        assert 'cp "$ROOT_DIR/docker-compose.full.yml" "$tmp_root/"' in package_script
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


def test_readmes_document_backend_managed_preflight_behavior() -> None:
    root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    root_readme_en = (REPO_ROOT / "README_EN.md").read_text(encoding="utf-8")
    backend_readme = (REPO_ROOT / "backend" / "README.md").read_text(encoding="utf-8")
    compose_readme = (REPO_ROOT / "scripts" / "README-COMPOSE.md").read_text(encoding="utf-8")

    assert "backend 启动时会自行执行 runner preflight" in root_readme
    assert "compose 不再声明一次性 runner 预热 / 自检服务" in root_readme
    assert "docker compose up --build" in root_readme
    assert "默认推荐直接使用 Docker Compose" in root_readme
    assert "scripts/README-COMPOSE.md" in root_readme
    assert "backend runs runner preflight during startup" in root_readme_en
    assert "no longer declares one-shot compose runner warmup services" in root_readme_en
    assert "docker compose up --build" in root_readme_en
    assert "The default recommended entrypoint is plain Docker Compose" in root_readme_en
    assert "scripts/README-COMPOSE.md" in root_readme_en
    assert "backend runs the configured runner preflight during startup" in backend_readme
    assert "default compose startup now only brings up the long-lived services" in backend_readme
    assert "Docker SDK" in backend_readme
    assert "SCANNER_*_IMAGE" in backend_readme
    assert "backend 启动时托管执行 runner preflight" in compose_readme
    assert "默认启动只拉起常驻 compose 服务" in compose_readme
    assert "docker compose up --build" in compose_readme
    assert "docker-compose.full.yml" in compose_readme
    assert "Docker Desktop + Linux containers" in compose_readme
    assert "runner 预热 / 自检容器" not in compose_readme
    assert "runner preflight / warmup" not in root_readme_en


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
    assert '"bandit>=' in pyproject_text
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
    assert 'PIP_DEFAULT_TIMEOUT=60 /opt/flow-parser-venv/bin/pip install --disable-pip-version-check --no-cache-dir -i "${idx}" -r /tmp/flow-parser-runner.requirements.txt' in flow_parser_runner_text
    assert 'command -v code2flow >/dev/null 2>&1' in flow_parser_runner_text
    assert 'code2flow --help >/dev/null 2>&1' in flow_parser_runner_text
    assert "python3 /opt/flow-parser/flow_parser_runner.py --help >/dev/null 2>&1" in flow_parser_runner_text
    assert 'CMD ["python3", "/opt/flow-parser/flow_parser_runner.py", "--help"]' in flow_parser_runner_text


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

    assert "push:" in workflow_text
    assert "'v*.*.*'" in workflow_text
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
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-yasa-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-opengrep-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-bandit-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-gitleaks-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-phpstan-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-flow-parser-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-sandbox-runner:${{ steps.image-tag.outputs.tag }}" in workflow_text


def test_release_workflow_packages_yasa_override_assets() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    package_script = (REPO_ROOT / "deploy" / "package-release-artifacts.sh").read_text(
        encoding="utf-8"
    )

    assert ".dockerignore" in workflow_text
    assert "frontend/yasa-engine-overrides/" in workflow_text
    assert 'cp -R "$ROOT_DIR/docker" "$tmp_root/"' in package_script
    assert 'cp -R "$ROOT_DIR/frontend/yasa-engine-overrides" "$tmp_root/frontend/"' in package_script
