from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.projects import (
    ProjectCreate,
    create_project,
    get_project_files,
    get_project_files_tree,
    read_deleted_projects,
    read_project,
    read_projects,
)
from app.models.project import Project


class _ScalarResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self._values)

    def first(self):
        return self._values[0] if self._values else None


@pytest.mark.asyncio
async def test_create_project_defaults_to_zip_when_source_type_missing():
    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    project = await create_project(
        db=db,
        project_in=ProjectCreate(name="demo", programming_languages=["TypeScript"]),
        current_user=SimpleNamespace(id="user-1"),
    )

    assert project.source_type == "zip"
    assert project.repository_url is None
    assert project.repository_type == "other"
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_create_project_rejects_repository_source_type():
    db = AsyncMock()
    db.add = Mock()

    with pytest.raises(HTTPException, match="仅支持 ZIP"):
        await create_project(
            db=db,
            project_in=ProjectCreate(
                name="demo",
                source_type="repository",
                repository_url="https://github.com/example/demo",
                repository_type="github",
                programming_languages=[],
            ),
            current_user=SimpleNamespace(id="user-1"),
        )

    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_read_projects_hides_repository_projects():
    zip_project = Project(
        id="zip-1",
        name="zip project",
        source_type="zip",
        owner_id="user-1",
        is_active=True,
    )
    repo_project = Project(
        id="repo-1",
        name="repo project",
        source_type="repository",
        repository_url="https://github.com/example/repo",
        owner_id="user-1",
        is_active=True,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult([zip_project, repo_project]))

    projects = await read_projects(db=db, current_user=SimpleNamespace(id="user-1"))

    assert [project.id for project in projects] == ["zip-1"]


@pytest.mark.asyncio
async def test_read_deleted_projects_hides_repository_projects():
    zip_project = Project(
        id="zip-1",
        name="zip project",
        source_type="zip",
        owner_id="user-1",
        is_active=False,
    )
    repo_project = Project(
        id="repo-1",
        name="repo project",
        source_type="repository",
        repository_url="https://github.com/example/repo",
        owner_id="user-1",
        is_active=False,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult([zip_project, repo_project]))

    projects = await read_deleted_projects(
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert [project.id for project in projects] == ["zip-1"]


@pytest.mark.asyncio
async def test_read_project_returns_404_for_repository_project():
    repo_project = Project(
        id="repo-1",
        name="repo project",
        source_type="repository",
        repository_url="https://github.com/example/repo",
        owner_id="user-1",
        is_active=True,
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarResult([repo_project]))

    with pytest.raises(HTTPException, match="项目不存在"):
        await read_project(
            id="repo-1",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )


@pytest.mark.asyncio
async def test_get_project_files_returns_404_for_repository_project():
    repo_project = Project(
        id="repo-1",
        name="repo project",
        source_type="repository",
        repository_url="https://github.com/example/repo",
        repository_type="github",
        owner_id="user-1",
        is_active=True,
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=repo_project)

    with pytest.raises(HTTPException, match="项目不存在"):
        await get_project_files(
            id="repo-1",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )


@pytest.mark.asyncio
async def test_get_project_files_tree_returns_404_for_repository_project():
    repo_project = Project(
        id="repo-1",
        name="repo project",
        source_type="repository",
        repository_url="https://github.com/example/repo",
        repository_type="github",
        owner_id="user-1",
        is_active=True,
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=repo_project)

    with pytest.raises(HTTPException, match="项目不存在"):
        await get_project_files_tree(
            id="repo-1",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )
