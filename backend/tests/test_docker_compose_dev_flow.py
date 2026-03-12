from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_compose_is_dev_first_layout() -> None:
    compose_path = REPO_ROOT / "docker-compose.yml"
    full_overlay_path = REPO_ROOT / "docker-compose.full.yml"
    backend_dockerfile = REPO_ROOT / "backend" / "Dockerfile"
    frontend_dockerfile = REPO_ROOT / "frontend" / "Dockerfile"
    backend_entrypoint = REPO_ROOT / "backend" / "scripts" / "dev-entrypoint.sh"

    assert compose_path.exists()
    assert full_overlay_path.exists()
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
    assert "- BACKEND_PYPI_INDEX_PRIMARY=${BACKEND_PYPI_INDEX_PRIMARY:-}" in compose_text
    assert "- BACKEND_PYPI_INDEX_FALLBACK=${BACKEND_PYPI_INDEX_FALLBACK:-}" in compose_text
    assert (
        "${BACKEND_PYPI_INDEX_CANDIDATES:-https://mirrors.aliyun.com/pypi/simple/,"
        "https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple}"
    ) in compose_text
    assert 'MCP_REQUIRE_ALL_READY_ON_STARTUP: "false"' in compose_text
    assert 'SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP: "false"' in compose_text
    assert 'CODEX_SKILLS_AUTO_INSTALL: "false"' in compose_text
    assert 'profiles: ["tools"]' in compose_text
    assert "adminer:" in compose_text
    assert "\n  frontend-dev:" not in compose_text

    backend_text = backend_dockerfile.read_text(encoding="utf-8")
    assert "FROM runtime-base AS dev-runtime" in backend_text
    assert "dev-entrypoint.sh" in backend_text
    assert 'COPY scripts/package_source_selector.py /usr/local/bin/package_source_selector.py' in backend_text
    assert 'ordered_indexes="$(order_indexes "${pypi_index_candidates}")"' in backend_text
    assert 'while IFS= read -r index_url; do' in backend_text
    assert 'sync_with_index "${BACKEND_PYPI_INDEX_PRIMARY}" || sync_with_index "${BACKEND_PYPI_INDEX_FALLBACK}"' not in backend_text

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
    assert "\n  frontend-dev:" not in full_overlay_text


def test_scripts_and_packaging_use_new_compose_layout() -> None:
    dev_frontend_script = (REPO_ROOT / "scripts" / "dev-frontend.sh").read_text(encoding="utf-8")
    frontend_exec_script = (
        REPO_ROOT / "frontend" / "scripts" / "run-in-dev-container.sh"
    ).read_text(encoding="utf-8")
    package_script = (REPO_ROOT / "scripts" / "package-release-artifacts.sh").read_text(
        encoding="utf-8"
    )
    deploy_script = (REPO_ROOT / "scripts" / "deploy-release-artifacts.sh").read_text(
        encoding="utf-8"
    )
    deb_build_script = (REPO_ROOT / "packaging" / "deb" / "build_deb.sh").read_text(
        encoding="utf-8"
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

    assert '-f "${ROOT_DIR}/docker-compose.full.yml"' in package_script
    assert 'cp "$ROOT_DIR/docker-compose.full.yml" "$tmp_root/"' in package_script
    assert '-f "${TARGET_DIR}/docker-compose.full.yml"' in deploy_script

    assert (REPO_ROOT / "deploy" / "compose" / "docker-compose.prod.yml").exists()
    assert (REPO_ROOT / "deploy" / "compose" / "docker-compose.prod.cn.yml").exists()
    assert 'cp "$ROOT_DIR/deploy/compose/docker-compose.prod.yml"' in deb_build_script
    assert 'cp "$ROOT_DIR/deploy/compose/docker-compose.prod.cn.yml"' in deb_build_script
    assert "https://pypi.tuna.tsinghua.edu.cn/simple" in compose_wrapper_script
    assert "https://pypi.tuna.tsinghua.edu.cn/simple" in compose_wrapper_ps1
