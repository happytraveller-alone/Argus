from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.api.v1.endpoints import projects, projects_crud, projects_uploads
from app.core.security import get_password_hash
from app.db.base import Base
from app.db.session import get_db
from app.models.agent_task import AgentTask
from app.models.project import Project
from app.models.project_management_metrics import ProjectManagementMetrics
from app.models.user import User


def _is_sqlite_incompatible_index(index) -> bool:
    postgresql_opts = getattr(index, "dialect_options", {}).get("postgresql", {})
    if postgresql_opts.get("using") == "gin":
        return True
    expressions = getattr(index, "expressions", ()) or ()
    return any("gin_trgm_ops" in str(expr) for expr in expressions)


async def _create_user(session_factory: async_sessionmaker[AsyncSession]) -> User:
    async with session_factory() as session:
        user = User(
            email="projects-serialization@example.com",
            full_name="Projects Serialization",
            hashed_password=get_password_hash("password123"),
            is_active=True,
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _create_project(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    owner_id: str,
    name: str = "Zip Project",
    source_type: str = "zip",
) -> Project:
    async with session_factory() as session:
        project = Project(
            name=name,
            description="serialization regression fixture",
            source_type=source_type,
            repository_url=None,
            repository_type="other",
            default_branch="main",
            programming_languages='["python"]',
            owner_id=owner_id,
            is_active=True,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project


async def _create_ready_metrics(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
) -> ProjectManagementMetrics:
    async with session_factory() as session:
        metrics = ProjectManagementMetrics(
            project_id=project_id,
            archive_size_bytes=2048,
            total_tasks=8,
            completed_tasks=5,
            running_tasks=1,
            agent_tasks=3,
            opengrep_tasks=1,
            gitleaks_tasks=1,
            bandit_tasks=1,
            phpstan_tasks=0,
            critical=1,
            high=2,
            medium=3,
            low=4,
            status="ready",
        )
        session.add(metrics)
        await session.commit()
        await session.refresh(metrics)
        return metrics


async def _create_completed_agent_task(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    project_id: str,
    created_by: str,
) -> AgentTask:
    async with session_factory() as session:
        task = AgentTask(
            project_id=project_id,
            created_by=created_by,
            name="Completed Agent Task",
            status="completed",
            high_count=1,
            medium_count=2,
            low_count=3,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return task


@pytest_asyncio.fixture
async def project_api_env(monkeypatch):
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

        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
        user = await _create_user(session_factory)

        app = FastAPI()
        app.include_router(projects.router, prefix="/api/v1/projects")

        async def override_db():
            async with session_factory() as session:
                yield session

        async def override_current_user():
            return SimpleNamespace(id=user.id)

        monkeypatch.setattr(projects_crud.project_metrics_refresher, "enqueue", lambda _id: None)
        monkeypatch.setattr(projects_uploads.project_metrics_refresher, "enqueue", lambda _id: None)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[deps.get_current_user] = override_current_user

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield SimpleNamespace(
                app=app,
                client=client,
                session_factory=session_factory,
                user=user,
            )
    finally:
        await engine.dispose()
        for table, index in removed_indexes:
            table.indexes.add(index)


@pytest.mark.asyncio
async def test_read_projects_without_metrics_returns_null_management_metrics(project_api_env):
    project = await _create_project(
        project_api_env.session_factory,
        owner_id=project_api_env.user.id,
        name="List Project",
    )
    await _create_ready_metrics(
        project_api_env.session_factory,
        project_id=project.id,
    )

    response = await project_api_env.client.get("/api/v1/projects/")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == project.id
    assert payload[0]["management_metrics"] is None
    assert payload[0]["owner"]["id"] == project_api_env.user.id


@pytest.mark.asyncio
async def test_read_projects_with_metrics_includes_loaded_metrics(project_api_env):
    project = await _create_project(
        project_api_env.session_factory,
        owner_id=project_api_env.user.id,
        name="Metrics Project",
    )
    await _create_ready_metrics(
        project_api_env.session_factory,
        project_id=project.id,
    )

    response = await project_api_env.client.get(
        "/api/v1/projects/",
        params={"include_metrics": "true"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload[0]["management_metrics"]["status"] == "ready"
    assert payload[0]["management_metrics"]["total_tasks"] == 8
    assert "audit_tasks" not in payload[0]["management_metrics"]


@pytest.mark.asyncio
async def test_read_projects_with_metrics_builds_pending_fallback_for_legacy_project(
    monkeypatch,
    project_api_env,
):
    project = await _create_project(
        project_api_env.session_factory,
        owner_id=project_api_env.user.id,
        name="Legacy Zip Project",
    )
    monkeypatch.setattr(
        "app.services.project_metrics.get_project_zip_meta",
        AsyncMock(
            return_value={
                "file_size": 4096,
                "original_filename": "legacy.zip",
                "uploaded_at": "2026-03-18T10:00:00+00:00",
            }
        ),
    )

    response = await project_api_env.client.get(
        "/api/v1/projects/",
        params={"include_metrics": "true"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload[0]["id"] == project.id
    assert payload[0]["management_metrics"]["status"] == "pending"
    assert payload[0]["management_metrics"]["archive_size_bytes"] == 4096
    assert payload[0]["management_metrics"]["completed_tasks"] == 0
    assert payload[0]["management_metrics"]["running_tasks"] == 0
    assert payload[0]["management_metrics"]["critical"] == 0
    assert payload[0]["management_metrics"]["low"] == 0


@pytest.mark.asyncio
async def test_read_projects_with_metrics_recalculates_metrics_from_task_history(
    monkeypatch,
    project_api_env,
):
    project = await _create_project(
        project_api_env.session_factory,
        owner_id=project_api_env.user.id,
        name="Legacy Project With Tasks",
    )
    await _create_completed_agent_task(
        project_api_env.session_factory,
        project_id=project.id,
        created_by=project_api_env.user.id,
    )
    monkeypatch.setattr(
        "app.services.project_metrics.get_project_zip_meta",
        AsyncMock(
            return_value={
                "file_size": 5120,
                "original_filename": "legacy-with-history.zip",
                "uploaded_at": "2026-03-18T10:30:00+00:00",
            }
        ),
    )

    response = await project_api_env.client.get(
        "/api/v1/projects/",
        params={"include_metrics": "true"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload[0]["id"] == project.id
    assert payload[0]["management_metrics"]["status"] == "ready"
    assert payload[0]["management_metrics"]["archive_size_bytes"] == 5120
    assert payload[0]["management_metrics"]["total_tasks"] == 1
    assert payload[0]["management_metrics"]["completed_tasks"] == 1
    assert payload[0]["management_metrics"]["running_tasks"] == 0
    assert payload[0]["management_metrics"]["agent_tasks"] == 1
    assert payload[0]["management_metrics"]["high"] == 1
    assert payload[0]["management_metrics"]["medium"] == 2
    assert payload[0]["management_metrics"]["low"] == 3


@pytest.mark.asyncio
async def test_read_project_detail_includes_metrics(project_api_env):
    project = await _create_project(
        project_api_env.session_factory,
        owner_id=project_api_env.user.id,
        name="Detail Project",
    )
    await _create_ready_metrics(
        project_api_env.session_factory,
        project_id=project.id,
    )

    response = await project_api_env.client.get(f"/api/v1/projects/{project.id}")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == project.id
    assert payload["management_metrics"]["status"] == "ready"


@pytest.mark.asyncio
async def test_read_project_detail_builds_pending_fallback_when_metrics_missing(
    monkeypatch,
    project_api_env,
):
    project = await _create_project(
        project_api_env.session_factory,
        owner_id=project_api_env.user.id,
        name="Detail Legacy Project",
    )
    monkeypatch.setattr(
        "app.services.project_metrics.get_project_zip_meta",
        AsyncMock(
            return_value={
                "file_size": 1024,
                "original_filename": "detail-legacy.zip",
                "uploaded_at": "2026-03-18T11:00:00+00:00",
            }
        ),
    )

    response = await project_api_env.client.get(f"/api/v1/projects/{project.id}")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["management_metrics"]["status"] == "pending"
    assert payload["management_metrics"]["archive_size_bytes"] == 1024
    assert payload["management_metrics"]["total_tasks"] == 0
    assert payload["management_metrics"]["high"] == 0


@pytest.mark.asyncio
async def test_read_project_detail_recalculates_metrics_from_task_history(
    monkeypatch,
    project_api_env,
):
    project = await _create_project(
        project_api_env.session_factory,
        owner_id=project_api_env.user.id,
        name="Detail Legacy Project With Tasks",
    )
    await _create_completed_agent_task(
        project_api_env.session_factory,
        project_id=project.id,
        created_by=project_api_env.user.id,
    )
    monkeypatch.setattr(
        "app.services.project_metrics.get_project_zip_meta",
        AsyncMock(
            return_value={
                "file_size": 1536,
                "original_filename": "detail-legacy-with-history.zip",
                "uploaded_at": "2026-03-18T11:15:00+00:00",
            }
        ),
    )

    response = await project_api_env.client.get(f"/api/v1/projects/{project.id}")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["management_metrics"]["status"] == "ready"
    assert payload["management_metrics"]["archive_size_bytes"] == 1536
    assert payload["management_metrics"]["total_tasks"] == 1
    assert payload["management_metrics"]["completed_tasks"] == 1
    assert payload["management_metrics"]["running_tasks"] == 0
    assert payload["management_metrics"]["agent_tasks"] == 1
    assert payload["management_metrics"]["high"] == 1
    assert payload["management_metrics"]["medium"] == 2
    assert payload["management_metrics"]["low"] == 3


@pytest.mark.asyncio
async def test_create_project_serializes_without_loading_metrics(project_api_env):
    response = await project_api_env.client.post(
        "/api/v1/projects/",
        json={
            "name": "Created Project",
            "source_type": "zip",
            "description": "created via api",
            "programming_languages": ["python"],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["name"] == "Created Project"
    assert payload["management_metrics"] is None


@pytest.mark.asyncio
async def test_update_project_serializes_without_loading_metrics(project_api_env):
    project = await _create_project(
        project_api_env.session_factory,
        owner_id=project_api_env.user.id,
        name="Before Update",
    )

    response = await project_api_env.client.put(
        f"/api/v1/projects/{project.id}",
        json={"name": "After Update"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["name"] == "After Update"
    assert payload["management_metrics"] is None


@pytest.mark.asyncio
async def test_create_project_with_zip_serializes_without_loading_metrics(
    monkeypatch,
    project_api_env,
):
    async def fake_store_uploaded_archive_for_project(**kwargs):
        project = kwargs["project"]
        project.programming_languages = '["python"]'
        return {"stored": True}

    monkeypatch.setattr(
        projects_uploads,
        "_store_uploaded_archive_for_project",
        fake_store_uploaded_archive_for_project,
    )

    response = await project_api_env.client.post(
        "/api/v1/projects/create-with-zip",
        data={"name": "Zip Upload Project"},
        files={"file": ("fixture.zip", BytesIO(b"zip-fixture"), "application/zip")},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["name"] == "Zip Upload Project"
    assert payload["management_metrics"] is None

    list_response = await project_api_env.client.get(
        "/api/v1/projects/",
        params={"include_metrics": "true"},
    )

    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload[0]["management_metrics"]["status"] == "pending"
    assert list_payload[0]["management_metrics"]["archive_size_bytes"] == 0
    assert list_payload[0]["management_metrics"]["total_tasks"] == 0
