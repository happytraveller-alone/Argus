from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.projects import download_project_archive


@pytest.mark.asyncio
async def test_download_project_archive_returns_name_based_filename(monkeypatch):
    from app.api.v1.endpoints import projects_crud as crud_endpoint

    project = SimpleNamespace(
        id="project-1",
        name="demo-app",
        source_type="zip",
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=project)

    monkeypatch.setattr(
        crud_endpoint,
        "load_project_zip",
        AsyncMock(return_value="/tmp/project-1.zip"),
    )
    monkeypatch.setattr(crud_endpoint.os.path, "exists", lambda _path: True)

    response = await download_project_archive(
        project_id="project-1",
        db=db,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert response.path == "/tmp/project-1.zip"
    assert response.media_type == "application/zip"
    assert response.filename == "demo-app.zip"


@pytest.mark.asyncio
async def test_download_project_archive_raises_404_when_zip_missing(monkeypatch):
    from app.api.v1.endpoints import projects_crud as crud_endpoint

    project = SimpleNamespace(
        id="project-1",
        name="demo-app",
        source_type="zip",
    )
    db = AsyncMock()
    db.get = AsyncMock(return_value=project)

    monkeypatch.setattr(
        crud_endpoint,
        "load_project_zip",
        AsyncMock(return_value=None),
    )

    with pytest.raises(HTTPException) as exc_info:
        await download_project_archive(
            project_id="project-1",
            db=db,
            current_user=SimpleNamespace(id="u-1"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "未找到项目压缩包"
