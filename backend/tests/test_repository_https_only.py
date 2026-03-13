import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.projects import (
    ProjectCreate,
    ProjectUpdate,
    create_project,
    get_project_files,
    get_project_files_tree,
    update_project,
)
from app.api.v1.api import api_router
from app.models.project import Project


class DummyUser:
    def __init__(self, user_id: str):
        self.id = user_id


class DummyScalarResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class DummySession:
    def __init__(self, project=None, user_config=None):
        self.project = project
        self.user_config = user_config
        self.added = []
        self.committed = False
        self.refreshed = []

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.committed = True

    async def refresh(self, value):
        self.refreshed.append(value)

    async def execute(self, query):
        query_text = str(query).lower()
        if "user_config" in query_text:
            return DummyScalarResult(self.user_config)
        return DummyScalarResult(self.project)

    async def get(self, _model, _id):
        return self.project


@pytest.mark.asyncio
async def test_create_project_rejects_repository_creation_requests():
    db = DummySession()
    test_user = DummyUser("user-1")

    with pytest.raises(HTTPException) as exc_info:
        await create_project(
            db=db,
            project_in=ProjectCreate(
                name="SSH Project",
                source_type="repository",
                repository_url="git@github.com:org/repo.git",
                repository_type="github",
            ),
            current_user=test_user,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "仅支持 ZIP 项目创建"


@pytest.mark.asyncio
async def test_update_project_hides_legacy_repository_projects():
    test_user = DummyUser("user-1")
    test_project = Project(
        id="project-1",
        name="HTTPS Project",
        source_type="repository",
        repository_url="https://github.com/org/repo.git",
        repository_type="github",
        owner_id=test_user.id,
    )
    db = DummySession(project=test_project)

    with pytest.raises(HTTPException) as exc_info:
        await update_project(
            test_project.id,
            db=db,
            project_in=ProjectUpdate(repository_url="ssh://git@example.com/org/repo.git"),
            current_user=test_user,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "项目不存在"


@pytest.mark.asyncio
async def test_get_project_files_hides_legacy_repository_projects():
    test_user = DummyUser("user-1")
    project = Project(
        id="project-2",
        name="Legacy SSH Project",
        source_type="repository",
        repository_url="git@github.com:org/repo.git",
        repository_type="github",
        owner_id=test_user.id,
        is_active=True,
    )
    db = DummySession(project=project, user_config=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_project_files(
            project.id,
            db=db,
            current_user=test_user,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "项目不存在"


@pytest.mark.asyncio
async def test_get_project_files_tree_hides_legacy_repository_projects():
    test_user = DummyUser("user-1")
    project = Project(
        id="project-3",
        name="Legacy SSH Project",
        source_type="repository",
        repository_url="ssh://git@example.com/org/repo.git",
        repository_type="gitlab",
        owner_id=test_user.id,
        is_active=True,
    )
    db = DummySession(project=project, user_config=None)
    with pytest.raises(HTTPException) as exc_info:
        await get_project_files_tree(
            project.id,
            db=db,
            current_user=test_user,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "项目不存在"


def test_api_router_no_longer_exposes_ssh_key_routes():
    route_paths = {route.path for route in api_router.routes}
    assert "/ssh-keys" not in route_paths
    assert "/ssh-keys/" not in route_paths
    assert "/ssh-keys/generate" not in route_paths
