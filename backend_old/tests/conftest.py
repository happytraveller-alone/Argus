"""
搜索功能测试配置和 Fixtures
"""

import sys
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.base import Base
from app.models.agent_task import AgentTask, AgentTaskStatus
from tests.support.legacy_orm_models import (
    OpengrepFinding,
    OpengrepRule,
    OpengrepScanTask,
    Project,
    User,
)

import tests.support.legacy_orm_models as legacy_orm_models


sys.modules.setdefault("app.models.user", legacy_orm_models)
sys.modules.setdefault("app.models.project", legacy_orm_models)
sys.modules.setdefault("app.models.opengrep", legacy_orm_models)


TEST_USER_PASSWORD_HASH = (
    "$2b$12$Avv3EVtio0wVYVLZqmSypu4bOipIqCSyXkZK0nMit/hMZ4ZRiT7YW"
)


def _is_sqlite_incompatible_index(index) -> bool:
    postgresql_opts = getattr(index, "dialect_options", {}).get("postgresql", {})
    if postgresql_opts.get("using") == "gin":
        return True
    expressions = getattr(index, "expressions", ()) or ()
    return any("gin_trgm_ops" in str(expr) for expr in expressions)


# 配置异步事件循环
@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
async def db():
    """
    创建内存 SQLite 数据库用于测试
    """
    # 创建异步引擎（使用内存数据库）
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    removed_indexes = []
    for table in Base.metadata.tables.values():
        incompatible_indexes = [
            index for index in list(table.indexes) if _is_sqlite_incompatible_index(index)
        ]
        for index in incompatible_indexes:
            table.indexes.remove(index)
            removed_indexes.append((table, index))

    try:
        # 创建所有表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # 创建会话工厂
        async_session = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        # 创建并返回会话
        async with async_session() as session:
            yield session
            await session.rollback()

        # 清理
        await engine.dispose()
    finally:
        for table, index in removed_indexes:
            table.indexes.add(index)


@pytest.fixture
async def test_user(db: AsyncSession):
    """
    创建测试用户
    """
    user = User(
        email="test@example.com",
        full_name="Test User",
        hashed_password=TEST_USER_PASSWORD_HASH,
        is_active=True,
        role="admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def test_project(db: AsyncSession, test_user: User):
    """
    创建测试项目
    """
    project = Project(
        name="Test Project",
        description="This is a test project",
        source_type="repository",
        repository_url="https://github.com/test/test-project",
        repository_type="github",
        owner_id=test_user.id,
        is_active=True,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@pytest.fixture
async def test_agent_task(db: AsyncSession, test_project: Project, test_user: User):
    """
    创建测试 Agent 任务
    """
    task = AgentTask(
        project_id=test_project.id,
        created_by=test_user.id,
        name="Test Agent Audit",
        description="This is a test audit task",
        task_type="agent_audit",
        status=AgentTaskStatus.COMPLETED,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


# 配置 pytest-asyncio
pytest_plugins = ("pytest_asyncio",)
