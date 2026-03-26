from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_compose_uses_local_images_by_default() -> None:
    compose_path = REPO_ROOT / "docker-compose.yml"
    full_overlay_path = REPO_ROOT / "docker-compose.full.yml"
    yasa_host_overlay_path = REPO_ROOT / "docker-compose.yasa-host.yml"
    backend_dockerfile = REPO_ROOT / "backend" / "Dockerfile"
    frontend_dockerfile = REPO_ROOT / "frontend" / "Dockerfile"
    backend_entrypoint = REPO_ROOT / "backend" / "scripts" / "dev-entrypoint.sh"

    assert compose_path.exists()
    assert full_overlay_path.exists()
    assert yasa_host_overlay_path.exists()
    assert not (REPO_ROOT / "docker-compose.dev.yml").exists()
    assert not (REPO_ROOT / "docker-compose.frontend-dev.yml").exists()
    assert not (REPO_ROOT / "docker-compose.override.yml").exists()
    assert not (REPO_ROOT / "docker-compose.prod.yml").exists()
    assert not (REPO_ROOT / "docker-compose.prod.cn.yml").exists()

    compose_text = compose_path.read_text(encoding="utf-8")
    flow_parser_compose_block = compose_text.split("\n  flow-parser-runner:\n", maxsplit=1)[1].split(
        "\n  frontend:\n",
        maxsplit=1,
    )[0]
    assert "runner preflight / warmup" in compose_text
    assert "一次性预热/自检容器" in compose_text
    assert 'restart: "no"' in compose_text
    assert "执行完检查后按预期退出" in compose_text
    assert "Docker SDK" in compose_text
    assert "动态拉起临时 runner 容器" in compose_text
    assert "image: vulhunter/backend-dev-local:latest" in compose_text
    assert "image: vulhunter/frontend-local:latest" in compose_text
    assert "vulhunter/backend-local:latest" not in compose_text
    assert "vulhunter/backend-dev:latest" not in compose_text
    assert "vulhunter/frontend-dev:latest" not in compose_text
    assert "target: dev-runtime" in compose_text
    assert "target: dev" in compose_text
    assert "./backend:/app" in compose_text
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
    assert "command:\n      - sh\n      - /app/scripts/dev-entrypoint.sh" in compose_text
    assert "- BACKEND_PYPI_INDEX_PRIMARY=${BACKEND_PYPI_INDEX_PRIMARY:-}" in compose_text
    assert "- BACKEND_PYPI_INDEX_FALLBACK=${BACKEND_PYPI_INDEX_FALLBACK:-}" in compose_text
    assert "- BACKEND_INSTALL_YASA=${BACKEND_INSTALL_YASA:-1}" in compose_text
    assert "- YASA_VERSION=${YASA_VERSION:-v0.2.33}" in compose_text
    assert (
        "${BACKEND_PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/,"
        "https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple}"
    ) in compose_text
    assert "YASA_ENABLED: ${YASA_ENABLED:-true}" in compose_text
    assert "SCAN_WORKSPACE_ROOT: ${SCAN_WORKSPACE_ROOT:-/tmp/vulhunter/scans}" in compose_text
    assert "SCANNER_YASA_IMAGE: ${SCANNER_YASA_IMAGE:-vulhunter/yasa-runner-local:latest}" in compose_text
    assert "SCANNER_OPENGREP_IMAGE: ${SCANNER_OPENGREP_IMAGE:-vulhunter/opengrep-runner-local:latest}" in compose_text
    assert "SCANNER_BANDIT_IMAGE: ${SCANNER_BANDIT_IMAGE:-vulhunter/bandit-runner-local:latest}" in compose_text
    assert "SCANNER_GITLEAKS_IMAGE: ${SCANNER_GITLEAKS_IMAGE:-vulhunter/gitleaks-runner-local:latest}" in compose_text
    assert "SCANNER_PHPSTAN_IMAGE: ${SCANNER_PHPSTAN_IMAGE:-vulhunter/phpstan-runner-local:latest}" in compose_text
    assert "FLOW_PARSER_RUNNER_IMAGE: ${FLOW_PARSER_RUNNER_IMAGE:-vulhunter/flow-parser-runner-local:latest}" in compose_text
    assert 'FLOW_PARSER_RUNNER_ENABLED: "${FLOW_PARSER_RUNNER_ENABLED:-true}"' in compose_text
    assert 'FLOW_PARSER_RUNNER_TIMEOUT_SECONDS: "${FLOW_PARSER_RUNNER_TIMEOUT_SECONDS:-120}"' in compose_text
    assert "YASA_TIMEOUT_SECONDS: ${YASA_TIMEOUT_SECONDS:-600}" in compose_text
    assert "/tmp/vulhunter/scans:/tmp/vulhunter/scans" in compose_text
    assert "/var/run/docker.sock:/var/run/docker.sock" in compose_text
    assert 'MCP_REQUIRE_ALL_READY_ON_STARTUP: "false"' in compose_text
    assert "\n  yasa-runner:" in compose_text
    assert "image: vulhunter/yasa-runner-local:latest" in compose_text
    assert "dockerfile: ./docker/yasa-runner.Dockerfile" in compose_text
    assert "\n  opengrep-runner:" in compose_text
    assert "image: vulhunter/opengrep-runner-local:latest" in compose_text
    assert "dockerfile: ./docker/opengrep-runner.Dockerfile" in compose_text
    assert "\n  bandit-runner:" in compose_text
    assert "image: vulhunter/bandit-runner-local:latest" in compose_text
    assert "dockerfile: ./docker/bandit-runner.Dockerfile" in compose_text
    assert "\n  gitleaks-runner:" in compose_text
    assert "image: vulhunter/gitleaks-runner-local:latest" in compose_text
    assert "dockerfile: ./docker/gitleaks-runner.Dockerfile" in compose_text
    assert "\n  phpstan-runner:" in compose_text
    assert "image: vulhunter/phpstan-runner-local:latest" in compose_text
    assert "dockerfile: ./docker/phpstan-runner.Dockerfile" in compose_text
    assert "\n  flow-parser-runner:" in compose_text
    assert "image: vulhunter/flow-parser-runner-local:latest" in compose_text
    assert "dockerfile: ./docker/flow-parser-runner.Dockerfile" in compose_text
    assert (
        "- BACKEND_PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES:-"
        "https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,"
        "https://pypi.org/simple}"
    ) in flow_parser_compose_block
    assert 'condition: service_completed_successfully' in compose_text
    assert "BACKEND_NPM_REGISTRY_PRIMARY" not in compose_text
    assert "BACKEND_NPM_REGISTRY_FALLBACK" not in compose_text
    assert "BACKEND_NPM_REGISTRY_CANDIDATES" not in compose_text
    assert "BACKEND_PNPM_VERSION" not in compose_text
    assert "BACKEND_PNPM_CMD_TIMEOUT_SECONDS" not in compose_text
    assert "BACKEND_PNPM_INSTALL_OPTIONAL" not in compose_text
    assert "MCP_REQUIRED_RUNTIME_DOMAIN" not in compose_text
    assert "MCP_CODE_INDEX_ENABLED" not in compose_text
    assert 'SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP: "false"' in compose_text
    assert 'CODEX_SKILLS_AUTO_INSTALL: "false"' in compose_text
    assert 'profiles: ["tools"]' in compose_text
    assert "adminer:" in compose_text
    assert "YASA_HOST_BIN_PATH" not in compose_text
    assert "YASA_HOST_RESOURCE_DIR" not in compose_text
    assert "YASA_BIN_PATH:" not in compose_text
    assert "YASA_RESOURCE_DIR:" not in compose_text
    assert "\n  frontend-dev:" not in compose_text

    backend_text = backend_dockerfile.read_text(encoding="utf-8")
    assert "FROM runtime-base AS dev-runtime" in backend_text
    assert "dev-entrypoint.sh" in backend_text
    assert 'COPY scripts/package_source_selector.py /usr/local/bin/package_source_selector.py' in backend_text
    assert "ARG BACKEND_INSTALL_YASA=1" in backend_text
    assert "ARG YASA_VERSION=v0.2.33" in backend_text
    assert "https://github.com/antgroup/YASA-Engine/archive/refs/tags/${YASA_VERSION}.tar.gz" in backend_text
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

    entrypoint_text = backend_entrypoint.read_text(encoding="utf-8")
    assert 'VENV_DIR="${BACKEND_VENV_PATH:-/opt/backend-venv}"' in entrypoint_text
    assert "uv sync --active --frozen --no-dev" in entrypoint_text
    assert 'uv venv --clear "${VENV_DIR}"' in entrypoint_text
    assert "app.main:app --reload" in entrypoint_text
    assert 'rm -rf "${VENV_DIR}"' not in entrypoint_text
    assert "select_pypi_index()" in entrypoint_text
    assert 'export UV_INDEX_URL="${selected_pypi_index}"' in entrypoint_text
    assert 'export PIP_INDEX_URL="${selected_pypi_index}"' in entrypoint_text


def test_full_overlay_restores_full_local_build_defaults() -> None:
    full_overlay_text = (REPO_ROOT / "docker-compose.full.yml").read_text(encoding="utf-8")
    flow_parser_full_overlay_block = full_overlay_text.split(
        "\n  flow-parser-runner:\n",
        maxsplit=1,
    )[1].split(
        "\n  frontend:\n",
        maxsplit=1,
    )[0]

    assert "runner preflight / warmup" in full_overlay_text
    assert "一次性预热/自检容器" in full_overlay_text
    assert "执行完检查后按预期退出" in full_overlay_text
    assert "Docker SDK" in full_overlay_text
    assert "动态拉起临时 runner 容器" in full_overlay_text
    assert "vulhunter/backend-local:latest" in full_overlay_text
    assert "vulhunter/backend-dev-local:latest" not in full_overlay_text
    assert "vulhunter/frontend-local:latest" in full_overlay_text
    assert "working_dir: !reset null" in full_overlay_text
    assert "command: !reset null" in full_overlay_text
    assert "./frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" in full_overlay_text
    assert "${VULHUNTER_FRONTEND_PORT:-3000}:80" in full_overlay_text
    assert "VITE_API_BASE_URL: /api/v1" in full_overlay_text
    assert 'CODEX_SKILLS_AUTO_INSTALL: "false"' in full_overlay_text
    assert "- BACKEND_INSTALL_YASA=${BACKEND_INSTALL_YASA:-1}" in full_overlay_text
    assert "- YASA_VERSION=${YASA_VERSION:-v0.2.33}" in full_overlay_text
    assert "\n  yasa-runner:" in full_overlay_text
    assert "image: vulhunter/yasa-runner-local:latest" in full_overlay_text
    assert "dockerfile: ./docker/yasa-runner.Dockerfile" in full_overlay_text
    assert "SCANNER_YASA_IMAGE: ${SCANNER_YASA_IMAGE:-vulhunter/yasa-runner-local:latest}" in full_overlay_text
    assert "SCANNER_OPENGREP_IMAGE: ${SCANNER_OPENGREP_IMAGE:-vulhunter/opengrep-runner-local:latest}" in full_overlay_text
    assert "SCANNER_BANDIT_IMAGE: ${SCANNER_BANDIT_IMAGE:-vulhunter/bandit-runner-local:latest}" in full_overlay_text
    assert "SCANNER_GITLEAKS_IMAGE: ${SCANNER_GITLEAKS_IMAGE:-vulhunter/gitleaks-runner-local:latest}" in full_overlay_text
    assert "SCANNER_PHPSTAN_IMAGE: ${SCANNER_PHPSTAN_IMAGE:-vulhunter/phpstan-runner-local:latest}" in full_overlay_text
    assert "FLOW_PARSER_RUNNER_IMAGE: ${FLOW_PARSER_RUNNER_IMAGE:-vulhunter/flow-parser-runner-local:latest}" in full_overlay_text
    assert "\n  opengrep-runner:" in full_overlay_text
    assert "dockerfile: ./docker/opengrep-runner.Dockerfile" in full_overlay_text
    assert "\n  bandit-runner:" in full_overlay_text
    assert "dockerfile: ./docker/bandit-runner.Dockerfile" in full_overlay_text
    assert "\n  gitleaks-runner:" in full_overlay_text
    assert "dockerfile: ./docker/gitleaks-runner.Dockerfile" in full_overlay_text
    assert "\n  phpstan-runner:" in full_overlay_text
    assert "dockerfile: ./docker/phpstan-runner.Dockerfile" in full_overlay_text
    assert "\n  flow-parser-runner:" in full_overlay_text
    assert "dockerfile: ./docker/flow-parser-runner.Dockerfile" in full_overlay_text
    assert (
        "- BACKEND_PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES:-"
        "https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,"
        "https://pypi.org/simple}"
    ) in flow_parser_full_overlay_block
    assert "SCAN_WORKSPACE_ROOT: ${SCAN_WORKSPACE_ROOT:-/tmp/vulhunter/scans}" in full_overlay_text
    assert "BACKEND_NPM_REGISTRY_PRIMARY" not in full_overlay_text
    assert "BACKEND_NPM_REGISTRY_FALLBACK" not in full_overlay_text
    assert "BACKEND_NPM_REGISTRY_CANDIDATES" not in full_overlay_text
    assert "BACKEND_PNPM_VERSION" not in full_overlay_text
    assert "BACKEND_PNPM_CMD_TIMEOUT_SECONDS" not in full_overlay_text
    assert "BACKEND_PNPM_INSTALL_OPTIONAL" not in full_overlay_text
    assert "MCP_REQUIRED_RUNTIME_DOMAIN" not in full_overlay_text
    assert "\n  frontend-dev:" not in full_overlay_text


def test_backend_dockerfile_builds_linux_arm64_yasa_from_source() -> None:
    backend_text = (REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")

    assert 'ARG YASA_UAST_VERSION=v0.2.8' in backend_text
    assert 'UAST_PLATFORM="linux-arm64"; \\' in backend_text
    assert 'YASA_UAST_BUILD_MODE="source"; \\' in backend_text
    assert 'CGO_ENABLED=0 GOOS=linux GOARCH="${YASA_GO_ARCH}"' in backend_text
    assert 'go build -o "${YASA_ENGINE_DIR}/deps/uast4go/uast4go" .' in backend_text
    assert 'python3 -m venv "${YASA_HOME}/uast4py-venv"; \\' in backend_text
    assert (
        'exec "${YASA_HOME}/uast4py-venv/bin/python" -m uast.builder "$@"'
    ) in backend_text


def test_frontend_dev_entrypoint_prints_ready_banner() -> None:
    frontend_entrypoint = (
        REPO_ROOT / "frontend" / "scripts" / "dev-entrypoint.sh"
    ).read_text(encoding="utf-8")

    assert 'export BROWSER="${BROWSER:-none}"' in frontend_entrypoint
    assert 'FRONTEND_PUBLIC_URL="${FRONTEND_PUBLIC_URL:-http://localhost:3000}"' in frontend_entrypoint
    assert 'BACKEND_PUBLIC_URL="${BACKEND_PUBLIC_URL:-http://localhost:8000}"' in frontend_entrypoint
    assert 'VITE_READY_URL="http://127.0.0.1:${FRONTEND_DEV_PORT:-5173}/"' in frontend_entrypoint
    assert 'curl -fsS "${VITE_READY_URL}"' in frontend_entrypoint
    assert 'frontend ready: ${FRONTEND_PUBLIC_URL}' in frontend_entrypoint
    assert 'backend docs: ${BACKEND_PUBLIC_URL}/docs' in frontend_entrypoint


def test_nexus_web_dockerfile_persists_runtime_pnpm() -> None:
    nexus_dockerfile = (REPO_ROOT / "nexus-web" / "dockerfile").read_text(
        encoding="utf-8"
    )

    assert 'npm install -g "pnpm@${NEXUS_WEB_PNPM_VERSION}"' in nexus_dockerfile
    assert 'if (pkg.packageManager) process.exit(0);' in nexus_dockerfile
    assert 'pkg.packageManager = `pnpm@${process.env.NEXUS_WEB_PNPM_VERSION}`;' in nexus_dockerfile
    assert 'CMD ["pnpm", "dev", "--host", "0.0.0.0"]' in nexus_dockerfile


def test_scripts_and_packaging_use_new_compose_layout() -> None:
    dev_frontend_script = (REPO_ROOT / "scripts" / "dev-frontend.sh").read_text(encoding="utf-8")
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
    assert "https://pypi.tuna.tsinghua.edu.cn/simple" in compose_wrapper_script
    assert "https://pypi.tuna.tsinghua.edu.cn/simple" in compose_wrapper_ps1


def test_readmes_document_runner_preflight_behavior() -> None:
    root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    root_readme_en = (REPO_ROOT / "README_EN.md").read_text(encoding="utf-8")
    backend_readme = (REPO_ROOT / "backend" / "README.md").read_text(encoding="utf-8")

    assert "runner 预热 / 自检容器" in root_readme
    assert "启动后退出属于预期行为" in root_readme
    assert "runner preflight / warmup containers" in root_readme_en
    assert "exiting after the check is expected" in root_readme_en
    assert "one-shot runner preflight / warmup containers" in backend_readme
    assert "Docker SDK" in backend_readme
    assert "SCANNER_*_IMAGE" in backend_readme


def test_backend_dev_entrypoint_validates_seeded_venv_before_skipping_sync() -> None:
    entrypoint_text = (
        REPO_ROOT / "backend" / "scripts" / "dev-entrypoint.sh"
    ).read_text(encoding="utf-8")

    assert 'read_venv_version()' in entrypoint_text
    assert 'venv_can_run_backend()' in entrypoint_text
    assert 'ensure_backend_venv()' in entrypoint_text
    assert 'current_version="$(read_venv_version "${VENV_DIR}"' in entrypoint_text
    assert 'expected_version="$(python3 - <<' in entrypoint_text
    assert 'import sqlalchemy, alembic, uvicorn' in entrypoint_text
    assert 'uv venv --clear "${VENV_DIR}"' in entrypoint_text


def test_backend_dev_entrypoint_runs_single_alembic_head() -> None:
    entrypoint_text = (
        REPO_ROOT / "backend" / "scripts" / "dev-entrypoint.sh"
    ).read_text(encoding="utf-8")

    assert '"${VENV_DIR}/bin/alembic" upgrade heads' not in entrypoint_text
    assert '"${VENV_DIR}/bin/alembic" upgrade head\n' in entrypoint_text


def test_backend_runtime_python_tools_are_installed_via_backend_venv() -> None:
    compose_text = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    backend_text = (REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    pyproject_text = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    entrypoint_text = (REPO_ROOT / "backend" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    yasa_runner_text = (REPO_ROOT / "backend" / "docker" / "yasa-runner.Dockerfile").read_text(
        encoding="utf-8"
    )
    flow_parser_runner_text = (
        REPO_ROOT / "backend" / "docker" / "flow-parser-runner.Dockerfile"
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
    assert "mkdir -p /app /opt/backend-venv /root/.cache/uv /app/uploads/zip_files /app/data/mcp" in dev_runtime_text
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
    assert "python3 -m pip install" not in entrypoint_text
    assert 'BACKEND_VENV_DIR="${BACKEND_VENV_PATH:-/opt/backend-venv}"' in entrypoint_text
    assert '"${BACKEND_VENV_DIR}/bin/alembic" upgrade head' in entrypoint_text
    assert ".venv/bin/alembic upgrade head" not in entrypoint_text
    assert '"${BACKEND_VENV_DIR}/bin/code2flow"' not in entrypoint_text
    assert "FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim" in yasa_runner_text
    assert "AS yasa-builder" in yasa_runner_text
    assert "AS yasa-runner" in yasa_runner_text
    assert "/opt/yasa/bin/yasa" in yasa_runner_text
    assert "/opt/yasa-runtime" in yasa_runner_text
    assert "COPY --from=yasa-builder /opt/yasa-runtime /opt/yasa" in yasa_runner_text
    assert "YASA runner placeholder" not in yasa_runner_text
    assert "node_modules" not in yasa_runner_text
    assert "WORKDIR /scan" in yasa_runner_text
    assert "tree-sitter-language-pack" in flow_parser_runner_text
    assert "code2flow" in flow_parser_runner_text
    assert "ARG BACKEND_PYPI_INDEX_CANDIDATES=" in flow_parser_runner_text
    assert 'ENV PYPI_INDEX_CANDIDATES=${BACKEND_PYPI_INDEX_CANDIDATES}' in flow_parser_runner_text
    assert "COPY scripts/package_source_selector.py /usr/local/bin/package_source_selector.py" in flow_parser_runner_text
    assert 'python3 /usr/local/bin/package_source_selector.py --candidates "${raw_candidates}" --kind pypi --timeout-seconds 2' in flow_parser_runner_text
    assert 'for idx in $(printf \'%s\\n\' "${ordered_pypi_indexes}"); do \\' in flow_parser_runner_text
    assert 'PIP_DEFAULT_TIMEOUT=60 /opt/flow-parser-venv/bin/pip install --disable-pip-version-check --no-cache-dir -i "${idx}" -r /tmp/flow-parser-runner.requirements.txt' in flow_parser_runner_text
    assert 'command -v code2flow >/dev/null 2>&1' in flow_parser_runner_text
    assert 'code2flow --help >/dev/null 2>&1' in flow_parser_runner_text
    assert "python3 /opt/flow-parser/flow_parser_runner.py --help >/dev/null 2>&1" in compose_text
    assert "command -v code2flow >/dev/null 2>&1" in compose_text
    assert "code2flow --help >/dev/null 2>&1" in compose_text


def test_runner_dockerfiles_exist_for_all_migrated_scanners() -> None:
    opengrep_runner_text = (
        REPO_ROOT / "backend" / "docker" / "opengrep-runner.Dockerfile"
    ).read_text(encoding="utf-8")
    bandit_runner_text = (
        REPO_ROOT / "backend" / "docker" / "bandit-runner.Dockerfile"
    ).read_text(encoding="utf-8")
    gitleaks_runner_text = (
        REPO_ROOT / "backend" / "docker" / "gitleaks-runner.Dockerfile"
    ).read_text(encoding="utf-8")
    phpstan_runner_text = (
        REPO_ROOT / "backend" / "docker" / "phpstan-runner.Dockerfile"
    ).read_text(encoding="utf-8")
    pmd_runner_text = (REPO_ROOT / "backend" / "docker" / "pmd-runner.Dockerfile").read_text(
        encoding="utf-8"
    )
    flow_parser_runner_text = (
        REPO_ROOT / "backend" / "docker" / "flow-parser-runner.Dockerfile"
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
    assert "WORKDIR /scan" in phpstan_runner_text
    assert "phpstan" in phpstan_runner_text
    assert "WORKDIR /scan" in pmd_runner_text
    assert "pmd" in pmd_runner_text
    assert "WORKDIR /scan" in flow_parser_runner_text
    assert "flow_parser_runner.py" in flow_parser_runner_text

    for runner_text in runner_texts:
        assert "FROM ${DOCKERHUB_LIBRARY_MIRROR}/python:3.11-slim-trixie" in runner_text
        assert 'rm -f /etc/apt/sources.list.d/debian.sources 2>/dev/null || true;' in runner_text


def test_docker_publish_pushes_all_runner_images() -> None:
    workflow_text = (REPO_ROOT / ".github" / "workflows" / "docker-publish.yml").read_text(
        encoding="utf-8"
    )

    assert "build_yasa_runner" in workflow_text
    assert "build_opengrep_runner" in workflow_text
    assert "build_bandit_runner" in workflow_text
    assert "build_gitleaks_runner" in workflow_text
    assert "build_phpstan_runner" in workflow_text
    assert "build_flow_parser_runner" in workflow_text
    assert "./backend/docker/yasa-runner.Dockerfile" in workflow_text
    assert "./backend/docker/opengrep-runner.Dockerfile" in workflow_text
    assert "./backend/docker/bandit-runner.Dockerfile" in workflow_text
    assert "./backend/docker/gitleaks-runner.Dockerfile" in workflow_text
    assert "./backend/docker/phpstan-runner.Dockerfile" in workflow_text
    assert "./backend/docker/flow-parser-runner.Dockerfile" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-yasa-runner:${{ github.event.inputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-opengrep-runner:${{ github.event.inputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-bandit-runner:${{ github.event.inputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-gitleaks-runner:${{ github.event.inputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-phpstan-runner:${{ github.event.inputs.tag }}" in workflow_text
    assert "ghcr.io/${{ github.repository_owner }}/vulhunter-flow-parser-runner:${{ github.event.inputs.tag }}" in workflow_text
