#!/bin/bash
# 使用 uv 启动后端服务

set -e

python_alembic_enabled() {
    local value
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

echo "启动 VulHunter 后端服务..."

# 检查 uv 是否安装
if ! command -v uv &> /dev/null; then
    echo "未找到 uv，请先安装："
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# 同步依赖
echo "同步后端依赖..."
uv sync --frozen

# 运行数据库迁移（可选）
if python_alembic_enabled; then
    echo "🔄 运行数据库迁移..."
    uv run alembic upgrade head
else
    echo "跳过数据库迁移（PYTHON_ALEMBIC_ENABLED=${PYTHON_ALEMBIC_ENABLED:-false}）"
fi

# 启动服务
echo "启动后端服务..."
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --no-access-log
