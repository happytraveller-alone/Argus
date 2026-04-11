import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1.endpoints.projects_uploads import create_project_with_zip


def _make_upload_file(filename: str = "demo.zip", content: bytes = b"zip-data") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


@pytest.mark.asyncio
async def test_create_project_with_zip_returns_created_project(monkeypatch):
    from app.api.v1.endpoints import projects_uploads as uploads_endpoint

    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    delete_zip = AsyncMock()

    async def _fake_store_uploaded_archive_for_project(**kwargs):
        assert kwargs["commit"] is False
        kwargs["project"].description = "generated summary"
        return {"message": "ok"}

    monkeypatch.setattr(
        uploads_endpoint,
        "_store_uploaded_archive_for_project",
        _fake_store_uploaded_archive_for_project,
    )
    monkeypatch.setattr(uploads_endpoint, "delete_project_zip", delete_zip)

    project = await create_project_with_zip(
        name="Demo Project",
        description="demo",
        default_branch="main",
        programming_languages=["TypeScript"],
        file=_make_upload_file(),
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert project.name == "Demo Project"
    assert project.source_type == "zip"
    assert project.repository_url is None
    assert project.repository_type == "other"
    db.add.assert_called_once_with(project)
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(project)
    delete_zip.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_project_with_zip_rolls_back_invalid_archive(monkeypatch):
    from app.api.v1.endpoints import projects_uploads as uploads_endpoint

    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    delete_zip = AsyncMock()

    monkeypatch.setattr(
        uploads_endpoint,
        "_store_uploaded_archive_for_project",
        AsyncMock(
            side_effect=HTTPException(
                status_code=400,
                detail="不支持的文件格式: .exe。支持的格式: .zip",
            )
        ),
    )
    monkeypatch.setattr(uploads_endpoint, "delete_project_zip", delete_zip)

    with pytest.raises(HTTPException) as exc_info:
        await create_project_with_zip(
            name="Broken Archive",
            description=None,
            default_branch=None,
            programming_languages=None,
            file=_make_upload_file(filename="demo.exe"),
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 400
    db.rollback.assert_awaited_once()
    delete_zip.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_project_with_zip_propagates_duplicate_conflict(monkeypatch):
    from app.api.v1.endpoints import projects_uploads as uploads_endpoint

    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    delete_zip = AsyncMock()

    monkeypatch.setattr(
        uploads_endpoint,
        "_store_uploaded_archive_for_project",
        AsyncMock(
            side_effect=HTTPException(
                status_code=409,
                detail="检测到相同压缩包已上传到项目「Existing Project」，请勿重复上传",
            )
        ),
    )
    monkeypatch.setattr(uploads_endpoint, "delete_project_zip", delete_zip)

    with pytest.raises(HTTPException) as exc_info:
        await create_project_with_zip(
            name="Duplicate Archive",
            description=None,
            default_branch=None,
            programming_languages=None,
            file=_make_upload_file(),
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 409
    db.rollback.assert_awaited_once()
    delete_zip.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_project_with_zip_cleans_up_when_upload_pipeline_crashes(monkeypatch):
    from app.api.v1.endpoints import projects_uploads as uploads_endpoint

    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    delete_zip = AsyncMock()

    monkeypatch.setattr(
        uploads_endpoint,
        "_store_uploaded_archive_for_project",
        AsyncMock(side_effect=RuntimeError("zip pipeline exploded")),
    )
    monkeypatch.setattr(uploads_endpoint, "delete_project_zip", delete_zip)

    with pytest.raises(HTTPException) as exc_info:
        await create_project_with_zip(
            name="Crash Archive",
            description=None,
            default_branch=None,
            programming_languages=None,
            file=_make_upload_file(),
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 500
    assert "zip pipeline exploded" in str(exc_info.value.detail)
    db.rollback.assert_awaited_once()
    delete_zip.assert_awaited_once()
