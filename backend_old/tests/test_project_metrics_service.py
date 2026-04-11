from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import get_password_hash
from app.db.base import Base
from app.models.agent_task import AgentFinding
from app.models.agent_task import AgentTask
from app.models.bandit import BanditScanTask
from app.models.gitleaks import GitleaksScanTask
from app.models.opengrep import OpengrepScanTask
from app.models.phpstan import PhpstanScanTask
from app.models.project import Project
from app.models.user import User
from app.services.project_metrics import ProjectMetricsService


def _is_sqlite_incompatible_index(index) -> bool:
    postgresql_opts = getattr(index, "dialect_options", {}).get("postgresql", {})
    if postgresql_opts.get("using") == "gin":
        return True
    expressions = getattr(index, "expressions", ()) or ()
    return any("gin_trgm_ops" in str(expr) for expr in expressions)


@pytest_asyncio.fixture
async def session_factory():
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
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    finally:
        await engine.dispose()
        for table, index in removed_indexes:
            table.indexes.add(index)


@pytest.mark.asyncio
async def test_ensure_base_metrics_creates_pending_snapshot_with_archive_meta(
    session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.project_metrics.get_project_zip_meta",
        AsyncMock(
            return_value={
                "file_size": 3072,
                "original_filename": "bootstrap.zip",
                "uploaded_at": "2026-03-18T08:00:00+00:00",
            }
        ),
    )

    async with session_factory() as session:
        user = User(
            email="pending-metrics@example.com",
            full_name="Pending Metrics",
            hashed_password=get_password_hash("password123"),
            is_active=True,
            role="admin",
        )
        session.add(user)
        await session.flush()

        project = Project(
            name="Pending Metrics Fixture",
            description="base metrics regression fixture",
            source_type="zip",
            repository_url=None,
            repository_type="other",
            default_branch="main",
            programming_languages='["python"]',
            owner_id=user.id,
            is_active=True,
        )
        session.add(project)
        await session.flush()

        metrics = await ProjectMetricsService.ensure_base_metrics(session, project.id)
        await session.commit()

    assert metrics.status == "pending"
    assert metrics.archive_size_bytes == 3072
    assert metrics.total_tasks == 0
    assert metrics.completed_tasks == 0
    assert metrics.running_tasks == 0
    assert metrics.critical == 0
    assert metrics.low == 0
    assert metrics.error_message is None


@pytest.mark.asyncio
async def test_recalc_project_uses_updated_at_for_static_scan_tasks_without_completed_at(
    session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.project_metrics.get_project_zip_meta",
        AsyncMock(
            return_value={
                "file_size": 2048,
                "original_filename": "demo.zip",
                "uploaded_at": "2026-03-17T10:00:00+00:00",
            }
        ),
    )

    base_time = datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc)

    async with session_factory() as session:
        user = User(
            email="metrics-service@example.com",
            full_name="Metrics Service",
            hashed_password=get_password_hash("password123"),
            is_active=True,
            role="admin",
        )
        session.add(user)
        await session.flush()

        project = Project(
            name="Metrics Fixture",
            description="project metrics regression fixture",
            source_type="zip",
            repository_url=None,
            repository_type="other",
            default_branch="main",
            programming_languages='["python"]',
            owner_id=user.id,
            is_active=True,
        )
        session.add(project)
        await session.flush()

        session.add_all(
            [
                OpengrepScanTask(
                    project_id=project.id,
                    name="opengrep",
                    status="completed",
                    target_path="/tmp/project",
                    total_findings=5,
                    error_count=2,
                    warning_count=1,
                    updated_at=base_time + timedelta(minutes=1),
                ),
                GitleaksScanTask(
                    project_id=project.id,
                    name="gitleaks",
                    status="completed",
                    target_path="/tmp/project",
                    total_findings=4,
                    updated_at=base_time + timedelta(minutes=2),
                ),
                BanditScanTask(
                    project_id=project.id,
                    name="bandit",
                    status="completed",
                    target_path="/tmp/project",
                    high_count=1,
                    medium_count=2,
                    low_count=3,
                    updated_at=base_time + timedelta(minutes=3),
                ),
                PhpstanScanTask(
                    project_id=project.id,
                    name="phpstan",
                    status="completed",
                    target_path="/tmp/project",
                    total_findings=6,
                    updated_at=base_time + timedelta(minutes=4),
                ),
                AgentTask(
                    project_id=project.id,
                    created_by=user.id,
                    name="[INTELLIGENT]agent",
                    status="running",
                    high_count=2,
                    medium_count=1,
                    low_count=1,
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        metrics = await ProjectMetricsService.recalc_project(session, project.id)

    assert metrics.status == "ready"
    assert metrics.archive_size_bytes == 2048
    assert metrics.total_tasks == 5
    assert metrics.completed_tasks == 4
    assert metrics.running_tasks == 1
    assert metrics.opengrep_tasks == 1
    assert metrics.gitleaks_tasks == 1
    assert metrics.bandit_tasks == 1
    assert metrics.phpstan_tasks == 1
    assert metrics.agent_tasks == 1
    assert metrics.high == 3
    assert metrics.medium == 6
    assert metrics.low == 16
    assert metrics.verified_critical == 0
    assert metrics.verified_high == 0
    assert metrics.verified_medium == 0
    assert metrics.verified_low == 0
    assert metrics.last_completed_task_at is not None
    assert metrics.last_completed_task_at.replace(tzinfo=timezone.utc) == (
        base_time + timedelta(minutes=4)
    )


@pytest.mark.asyncio
async def test_recalc_project_aggregates_verified_findings_from_intelligent_and_hybrid_tasks(
    session_factory,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.services.project_metrics.get_project_zip_meta",
        AsyncMock(return_value=None),
    )

    async with session_factory() as session:
        user = User(
            email="verified-metrics@example.com",
            full_name="Verified Metrics",
            hashed_password=get_password_hash("password123"),
            is_active=True,
            role="admin",
        )
        session.add(user)
        await session.flush()

        project = Project(
            name="Verified Metrics Fixture",
            description="verified metrics regression fixture",
            source_type="zip",
            repository_url=None,
            repository_type="other",
            default_branch="main",
            programming_languages='["python"]',
            owner_id=user.id,
            is_active=True,
        )
        session.add(project)
        await session.flush()

        intelligent_task = AgentTask(
            project_id=project.id,
            created_by=user.id,
            name="[INTELLIGENT] intelligent task",
            description="智能扫描任务",
            status="completed",
            completed_at=datetime(2026, 3, 17, 9, 0, tzinfo=timezone.utc),
            critical_count=1,
            high_count=1,
            medium_count=1,
            low_count=1,
        )
        hybrid_task = AgentTask(
            project_id=project.id,
            created_by=user.id,
            name="[HYBRID] hybrid task",
            description="混合扫描任务",
            status="completed",
            completed_at=datetime(2026, 3, 17, 10, 0, tzinfo=timezone.utc),
            high_count=1,
            medium_count=1,
        )
        session.add_all([intelligent_task, hybrid_task])
        await session.flush()

        session.add_all(
            [
                AgentFinding(
                    task_id=intelligent_task.id,
                    vulnerability_type="sql_injection",
                    severity="critical",
                    title="Verified critical",
                    status="verified",
                    is_verified=True,
                    verdict="confirmed",
                ),
                AgentFinding(
                    task_id=intelligent_task.id,
                    vulnerability_type="xss",
                    severity="high",
                    title="Verified high",
                    status="verified",
                    is_verified=True,
                    verdict="likely",
                ),
                AgentFinding(
                    task_id=hybrid_task.id,
                    vulnerability_type="idor",
                    severity="medium",
                    title="Verified medium",
                    status="verified",
                    is_verified=True,
                    verdict="confirmed",
                ),
                AgentFinding(
                    task_id=hybrid_task.id,
                    vulnerability_type="hardcoded_secret",
                    severity="low",
                    title="Verified low",
                    status="verified",
                    is_verified=True,
                    verdict="confirmed",
                ),
                AgentFinding(
                    task_id=hybrid_task.id,
                    vulnerability_type="xss",
                    severity="high",
                    title="False positive excluded",
                    status="false_positive",
                    is_verified=True,
                    verdict="false_positive",
                ),
                AgentFinding(
                    task_id=intelligent_task.id,
                    vulnerability_type="ssrf",
                    severity="medium",
                    title="Unverified excluded",
                    status="new",
                    is_verified=False,
                    verdict="uncertain",
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        metrics = await ProjectMetricsService.recalc_project(session, project.id)

    assert metrics.status == "ready"
    assert metrics.total_tasks == 2
    assert metrics.completed_tasks == 2
    assert metrics.agent_tasks == 2
    assert metrics.verified_critical == 1
    assert metrics.verified_high == 1
    assert metrics.verified_medium == 1
    assert metrics.verified_low == 1
