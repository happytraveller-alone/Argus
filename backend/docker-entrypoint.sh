#!/bin/bash
set -e

echo "VulHunter 后端启动中..."

is_true() {
    case "${1:-}" in
        1|true|TRUE|True|yes|YES|on|ON)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

ensure_code2flow() {
    export CODE2FLOW_AUTO_INSTALL_FAILED=0
    if command -v code2flow >/dev/null 2>&1; then
        echo "code2flow 已可用"
        return 0
    fi

    echo "code2flow 缺失，尝试自动安装..."
    index_candidates="${BACKEND_PYPI_INDEX_CANDIDATES:-${PIP_INDEX_URL:-https://pypi.org/simple}}"
    install_ok=0
    old_ifs="$IFS"
    IFS=','
    for index_url in $index_candidates; do
        [ -n "$index_url" ] || continue
        if PIP_INDEX_URL="$index_url" python3 -m pip install --retries 3 --timeout 60 --disable-pip-version-check code2flow; then
            install_ok=1
            break
        fi
    done
    IFS="$old_ifs"

    if [ "$install_ok" -eq 1 ] && command -v code2flow >/dev/null 2>&1; then
        echo "code2flow 安装完成"
        return 0
    fi

    echo "code2flow 自动安装失败，控制流分析将退化为无 code2flow 模式"
    export CODE2FLOW_AUTO_INSTALL_FAILED=1
    return 0
}

# 启动前安装 Codex Skills（持久化到 mcp_data 卷）
if [ -x "/app/scripts/install_codex_skills.sh" ]; then
    /app/scripts/install_codex_skills.sh
fi

# 启动前构建统一 Skill Registry（失败不阻断启动）
if [ -f "/app/scripts/build_skill_registry.py" ] && \
   is_true "${SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP:-true}"; then
    .venv/bin/python /app/scripts/build_skill_registry.py --print-json || \
        echo "[SkillRegistry] build failed, continue startup"
fi

ensure_code2flow

# 等待 PostgreSQL 就绪
echo "⏳ 等待数据库连接..."
max_retries=30
retry_count=0

while [ $retry_count -lt $max_retries ]; do
    if .venv/bin/python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os

async def check_db():
    engine = create_async_engine(os.environ.get('DATABASE_URL', ''))
    try:
        async with engine.connect() as conn:
            await conn.execute(text('SELECT 1'))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()

from sqlalchemy import text
exit(0 if asyncio.run(check_db()) else 1)
" 2>/dev/null; then
        echo "数据库连接成功"
        break
    fi

    retry_count=$((retry_count + 1))
    echo "   重试 $retry_count/$max_retries..."
    sleep 2
done

if [ $retry_count -eq $max_retries ]; then
    echo "无法连接到数据库，请检查 DATABASE_URL 配置"
    exit 1
fi

# 运行数据库迁移
echo "执行数据库迁移..."
.venv/bin/alembic upgrade head

echo "数据库迁移完成"

# 可选：重置 opengrep_rules 表并重建规则（结构升级时使用）
if [ "${RESET_STATIC_SCAN_TABLES_ON_DEPLOY}" = "true" ] || [ "${RESET_STATIC_SCAN_TABLES_ON_DEPLOY}" = "1" ]; then
    echo "🧹 重置 opengrep_rules 表并重建规则..."
    .venv/bin/python scripts/reset_static_scan_tables.py
    echo "opengrep_rules 表重置完成"
fi

# 启动 uvicorn
echo "🌐 启动 API 服务..."
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
