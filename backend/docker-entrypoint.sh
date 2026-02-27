#!/bin/bash
set -e

echo "🚀 DeepAudit 后端启动中..."

# 启动前同步 MCP 源码（持久化到数据卷，供后续验证）
if [ -x "/app/scripts/sync_mcp_sources.sh" ]; then
    /app/scripts/sync_mcp_sources.sh || true
fi

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
        echo "✅ 数据库连接成功"
        break
    fi

    retry_count=$((retry_count + 1))
    echo "   重试 $retry_count/$max_retries..."
    sleep 2
done

if [ $retry_count -eq $max_retries ]; then
    echo "❌ 无法连接到数据库，请检查 DATABASE_URL 配置"
    exit 1
fi

# 运行数据库迁移
echo "📦 执行数据库迁移..."
.venv/bin/alembic upgrade head

echo "✅ 数据库迁移完成"

# 可选：重置 opengrep_rules 表并重建规则（结构升级时使用）
if [ "${RESET_STATIC_SCAN_TABLES_ON_DEPLOY}" = "true" ] || [ "${RESET_STATIC_SCAN_TABLES_ON_DEPLOY}" = "1" ]; then
    echo "🧹 重置 opengrep_rules 表并重建规则..."
    .venv/bin/python scripts/reset_static_scan_tables.py
    echo "✅ opengrep_rules 表重置完成"
fi

# 启动 uvicorn
echo "🌐 启动 API 服务..."
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
