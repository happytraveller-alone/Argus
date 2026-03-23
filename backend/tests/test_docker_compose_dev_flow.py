from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_compose_is_dev_first_layout() -> None:
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
    assert "target: dev-runtime" in compose_text
    assert "target: dev" in compose_text
    assert "./backend:/app" in compose_text
    assert "./frontend:/app" in compose_text
    assert "/app/.venv" in compose_text
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
    assert "YASA_BIN_PATH: ${YASA_BIN_PATH:-/opt/yasa/bin/yasa}" in compose_text
    assert "YASA_RESOURCE_DIR: ${YASA_RESOURCE_DIR:-/opt/yasa/resource}" in compose_text
    assert "YASA_TIMEOUT_SECONDS: ${YASA_TIMEOUT_SECONDS:-600}" in compose_text
    assert 'MCP_REQUIRE_ALL_READY_ON_STARTUP: "false"' in compose_text
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
    assert "\n  frontend-dev:" not in compose_text

    backend_text = backend_dockerfile.read_text(encoding="utf-8")
    assert "FROM runtime-base AS dev-runtime" in backend_text
    assert "dev-entrypoint.sh" in backend_text
    assert 'COPY scripts/package_source_selector.py /usr/local/bin/package_source_selector.py' in backend_text
    assert "ARG BACKEND_INSTALL_YASA=1" in backend_text
    assert "ARG YASA_VERSION=v0.2.33" in backend_text
    assert "https://github.com/antgroup/YASA-Engine/archive/refs/tags/${YASA_VERSION}.tar.gz" in backend_text
    assert "/opt/yasa/bin/yasa" in backend_text
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
    assert "uv sync --frozen --no-dev" in entrypoint_text
    assert "app.main:app --reload" in entrypoint_text
    assert 'rm -rf "${VENV_DIR}"' not in entrypoint_text
    assert 'find "${VENV_DIR}" -mindepth 1 -maxdepth 1' in entrypoint_text
    assert "select_pypi_index()" in entrypoint_text
    assert 'export UV_INDEX_URL="${selected_pypi_index}"' in entrypoint_text
    assert 'export PIP_INDEX_URL="${selected_pypi_index}"' in entrypoint_text


def test_full_overlay_restores_full_local_build_defaults() -> None:
    full_overlay_text = (REPO_ROOT / "docker-compose.full.yml").read_text(encoding="utf-8")

    assert "vulhunter/backend-local:latest" in full_overlay_text
    assert "vulhunter/frontend-local:latest" in full_overlay_text
    assert "working_dir: !reset null" in full_overlay_text
    assert "command: !reset null" in full_overlay_text
    assert "./frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro" in full_overlay_text
    assert "${VULHUNTER_FRONTEND_PORT:-3000}:80" in full_overlay_text
    assert "VITE_API_BASE_URL: /api/v1" in full_overlay_text
    assert 'CODEX_SKILLS_AUTO_INSTALL: "false"' in full_overlay_text
    assert "- BACKEND_INSTALL_YASA=${BACKEND_INSTALL_YASA:-1}" in full_overlay_text
    assert "- YASA_VERSION=${YASA_VERSION:-v0.2.33}" in full_overlay_text
    assert "YASA_BIN_PATH: ${YASA_BIN_PATH:-/opt/yasa/bin/yasa}" in full_overlay_text
    assert "YASA_RESOURCE_DIR: ${YASA_RESOURCE_DIR:-/opt/yasa/resource}" in full_overlay_text
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


def test_backend_dev_entrypoint_validates_seeded_venv_before_skipping_sync() -> None:
    entrypoint_text = (
        REPO_ROOT / "backend" / "scripts" / "dev-entrypoint.sh"
    ).read_text(encoding="utf-8")

    assert 'read_venv_version()' in entrypoint_text
    assert 'venv_can_run_backend()' in entrypoint_text
    assert 'seed_version="$(read_venv_version "${SEED_VENV_DIR}"' in entrypoint_text
    assert 'current_version="$(read_venv_version "${VENV_DIR}"' in entrypoint_text
    assert 'if [ -z "${current_version}" ] || [ "${current_version}" != "${seed_version}" ]; then' in entrypoint_text
    assert 'import sqlalchemy, alembic, uvicorn' in entrypoint_text
