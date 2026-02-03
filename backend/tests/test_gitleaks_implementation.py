#!/usr/bin/env python3
"""
Gitleaks 功能测试脚本

用于测试 Gitleaks 静态检测功能的实现
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


async def test_gitleaks_models():
    """测试 Gitleaks 数据库模型是否可以正常导入"""
    try:
        from app.models.gitleaks import GitleaksScanTask, GitleaksFinding
        print("✓ Gitleaks 模型导入成功")
        print(f"  - GitleaksScanTask: {GitleaksScanTask.__tablename__}")
        print(f"  - GitleaksFinding: {GitleaksFinding.__tablename__}")
        return True
    except Exception as e:
        print(f"✗ Gitleaks 模型导入失败: {e}")
        return False


async def test_project_relationship():
    """测试 Project 模型是否正确添加了 Gitleaks 关系"""
    try:
        from app.models.project import Project
        # 检查是否有 gitleaks_scan_tasks 关系
        if hasattr(Project, 'gitleaks_scan_tasks'):
            print("✓ Project 模型已添加 gitleaks_scan_tasks 关系")
            return True
        else:
            print("✗ Project 模型缺少 gitleaks_scan_tasks 关系")
            return False
    except Exception as e:
        print(f"✗ 检查 Project 关系失败: {e}")
        return False


async def test_api_imports():
    """测试 API 端点是否可以正常导入"""
    try:
        from app.api.v1.endpoints.static_tasks import (
            GitleaksScanTaskCreate,
            GitleaksScanTaskResponse,
            GitleaksFindingResponse,
            _execute_gitleaks_scan,
        )
        print("✓ Gitleaks API 组件导入成功")
        print(f"  - GitleaksScanTaskCreate")
        print(f"  - GitleaksScanTaskResponse")
        print(f"  - GitleaksFindingResponse")
        print(f"  - _execute_gitleaks_scan")
        return True
    except Exception as e:
        print(f"✗ Gitleaks API 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_migration_file():
    """检查迁移文件是否存在"""
    migration_file = backend_dir / "alembic" / "versions" / "9d4e3f5g6h13_add_gitleaks_tables.py"
    if migration_file.exists():
        print(f"✓ 迁移文件存在: {migration_file.name}")
        return True
    else:
        print(f"✗ 迁移文件不存在: {migration_file}")
        return False


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("Gitleaks 功能测试")
    print("=" * 60)
    print()

    results = []

    print("1. 测试数据库模型")
    results.append(await test_gitleaks_models())
    print()

    print("2. 测试 Project 关系")
    results.append(await test_project_relationship())
    print()

    print("3. 测试 API 导入")
    results.append(await test_api_imports())
    print()

    print("4. 检查迁移文件")
    results.append(await test_migration_file())
    print()

    print("=" * 60)
    if all(results):
        print("✓ 所有测试通过!")
        print()
        print("下一步操作:")
        print("1. 运行数据库迁移: alembic upgrade head")
        print("2. 启动服务器: uvicorn app.main:app --reload")
        print("3. 测试 API 端点:")
        print("   - POST /api/v1/static/gitleaks/scan")
        print("   - GET /api/v1/static/gitleaks/tasks")
        print("   - GET /api/v1/static/gitleaks/tasks/{task_id}")
        print("   - GET /api/v1/static/gitleaks/tasks/{task_id}/findings")
        return 0
    else:
        print("✗ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
