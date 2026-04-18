#!/bin/sh
set -eu

echo "Starting VulHunter backend dev container..."

APP_ROOT="/app"
VENV_DIR="${BACKEND_VENV_PATH:-/opt/backend-venv}"
STAMP_FILE="${VENV_DIR}/.vulhunter-dev-lock.sha256"
DEFAULT_PYPI_INDEX_CANDIDATES="https://mirrors.aliyun.com/pypi/simple/,https://pypi.tuna.tsinghua.edu.cn/simple,https://pypi.org/simple"

read_venv_version() {
    venv_dir="$1"
    cfg_file="${venv_dir}/pyvenv.cfg"

    if [ ! -f "${cfg_file}" ]; then
        return 1
    fi

    sed -n 's/^version_info = //p' "${cfg_file}" | sed -n '1p'
}

venv_can_run_backend() {
    venv_dir="$1"

    if [ ! -x "${venv_dir}/bin/python" ]; then
        return 1
    fi

    "${venv_dir}/bin/python" - <<'PY' >/dev/null 2>&1
import sqlalchemy, alembic, uvicorn
PY
}

ensure_backend_venv() {
    current_version="$(read_venv_version "${VENV_DIR}" 2>/dev/null || true)"
    expected_version="$(python3 - <<'PY'
import sys
print(".".join(str(part) for part in sys.version_info[:3]))
PY
)"

    if [ -n "${current_version}" ] && [ "${current_version}" = "${expected_version}" ] && venv_can_run_backend "${VENV_DIR}"; then
        return 0
    fi

    if [ -z "${current_version}" ]; then
        echo "Creating backend virtualenv in ${VENV_DIR}..."
    else
        echo "Recreating backend virtualenv in ${VENV_DIR} (current=${current_version}, expected=${expected_version})..."
    fi

    mkdir -p "$(dirname "${VENV_DIR}")"
    uv venv --clear "${VENV_DIR}"
}

compute_lock_hash() {
    if [ ! -f "${APP_ROOT}/pyproject.toml" ] || [ ! -f "${APP_ROOT}/uv.lock" ]; then
        return 1
    fi

    sha256sum "${APP_ROOT}/pyproject.toml" "${APP_ROOT}/uv.lock" | sha256sum | awk '{print $1}'
}

select_pypi_index() {
    if [ -n "${UV_INDEX_URL:-}" ]; then
        printf '%s\n' "${UV_INDEX_URL}"
        return 0
    fi

    if [ -n "${PIP_INDEX_URL:-}" ]; then
        printf '%s\n' "${PIP_INDEX_URL}"
        return 0
    fi

    pypi_index_candidates="${PYPI_INDEX_CANDIDATES:-${DEFAULT_PYPI_INDEX_CANDIDATES}}"
    selected_pypi_index="$(
        printf '%s\n' "${pypi_index_candidates}" \
            | tr ',' '\n' \
            | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' \
            | awk 'NF && !seen[$0]++ { print; exit }'
    )"

    if [ -z "${selected_pypi_index}" ]; then
        selected_pypi_index="$(
            printf '%s' "${pypi_index_candidates}" | tr ',' '\n' | sed -n '1{s/^[[:space:]]*//;s/[[:space:]]*$//;p;}'
        )"
    fi

    printf '%s\n' "${selected_pypi_index}"
}

sync_python_env_if_needed() {
    export VIRTUAL_ENV="${VENV_DIR}"
    export PATH="${VENV_DIR}/bin:${PATH}"
    ensure_backend_venv

    current_hash=""
    previous_hash=""
    if current_hash="$(compute_lock_hash 2>/dev/null)"; then
        previous_hash="$(cat "${STAMP_FILE}" 2>/dev/null || true)"
    fi

    if [ -n "${current_hash}" ] && [ "${current_hash}" = "${previous_hash}" ]; then
        echo "Python lockfile unchanged, skip uv sync"
        return 0
    fi

    echo "Syncing backend dependencies with uv..."
    mkdir -p /root/.cache/uv
    selected_pypi_index="$(select_pypi_index)"
    if [ -n "${selected_pypi_index}" ]; then
        export UV_INDEX_URL="${selected_pypi_index}"
        export PIP_INDEX_URL="${selected_pypi_index}"
        echo "Selected PyPI index: ${selected_pypi_index}"
    fi
    uv sync --active --frozen --no-dev

    if [ -n "${current_hash}" ]; then
        printf '%s\n' "${current_hash}" > "${STAMP_FILE}"
    fi
}

wait_for_db() {
    echo "Waiting for PostgreSQL..."
    max_retries=30
    retry_count=0

    while [ "${retry_count}" -lt "${max_retries}" ]; do
        if "${VENV_DIR}/bin/python" -c "
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def check_db():
    database_url = (
        os.environ.get('PYTHON_DATABASE_URL')
        or os.environ.get('DATABASE_URL')
        or ''
    )
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text('SELECT 1'))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()

raise SystemExit(0 if asyncio.run(check_db()) else 1)
" 2>/dev/null; then
            echo "Database connection ready"
            return 0
        fi

        retry_count=$((retry_count + 1))
        echo "Retry ${retry_count}/${max_retries}..."
        sleep 2
    done

    echo "Failed to connect to database"
    exit 1
}

run_optional_resets() {
    if [ "${RESET_STATIC_SCAN_TABLES_ON_DEPLOY:-false}" = "true" ] || [ "${RESET_STATIC_SCAN_TABLES_ON_DEPLOY:-0}" = "1" ]; then
        echo "Skipping legacy static scan table reset script; Rust rule bootstrap is authoritative."
    fi
}

sync_python_env_if_needed
wait_for_db

python_alembic_enabled() {
    value="${PYTHON_ALEMBIC_ENABLED:-true}"
    value="$(printf "%s" "$value" | tr '[:upper:]' '[:lower:]' | xargs)"
    case "$value" in
        0|false|off|no)
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}

echo "Running database migrations ..."
if python_alembic_enabled; then
    "${VENV_DIR}/bin/alembic" upgrade head
else
    echo "Skipping alembic upgrade (PYTHON_ALEMBIC_ENABLED=${PYTHON_ALEMBIC_ENABLED:-false})"
fi

run_optional_resets

echo "Delegating dev startup to Rust backend runtime..."
exec /usr/local/bin/backend-runtime-startup dev
