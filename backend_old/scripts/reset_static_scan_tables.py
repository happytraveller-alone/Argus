#!/usr/bin/env python3
"""
仅重置 opengrep_rules 表，并重新导入规则。

用途：
- Docker Compose 部署时，规则表结构变更后清理旧规则
- 保持其他扫描任务/结果表不受影响
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# 确保 ORM 关系引用字符串在 mapper 初始化前完成注册
import app.models  # noqa: F401,E402
from app.models.project_info import ProjectInfo  # noqa: F401,E402
from app.db.init_db import (  # noqa: E402
    create_internal_opengrep_rules,
    create_patch_opengrep_rules,
)
from app.db.session import AsyncSessionLocal  # noqa: E402

logger = logging.getLogger("reset_static_scan_tables")
logging.basicConfig(level=logging.INFO)

TARGET_TABLE = "opengrep_rules"


async def reset_static_scan_tables() -> None:
    async with AsyncSessionLocal() as db:
        logger.info("开始清理规则表（仅 %s）...", TARGET_TABLE)
        await db.execute(text(f'DELETE FROM "{TARGET_TABLE}"'))
        logger.info("  - 已删除表数据: %s", TARGET_TABLE)
        await db.commit()

        logger.info("开始重新导入静态规则...")
        await create_internal_opengrep_rules(db)
        await create_patch_opengrep_rules(db)
        await db.commit()
        logger.info("静态规则重建完成")


async def main() -> None:
    enabled = (
        os.getenv("RESET_STATIC_SCAN_TABLES_ON_DEPLOY", "true").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if not enabled:
        logger.info("RESET_STATIC_SCAN_TABLES_ON_DEPLOY=false，跳过静态表重置")
        return

    await reset_static_scan_tables()


if __name__ == "__main__":
    asyncio.run(main())
