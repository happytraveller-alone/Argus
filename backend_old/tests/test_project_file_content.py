from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import zipfile

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.projects import get_project_file_content


class _CacheStub:
    async def get(self, *_args, **_kwargs):
        return None

    async def set(self, *_args, **_kwargs):
        return None


def _build_zip(zip_path: Path, files: dict[str, str]) -> None:
    with zipfile.ZipFile(zip_path, "w") as archive:
        for file_path, content in files.items():
            archive.writestr(file_path, content)


@pytest.mark.asyncio
async def test_get_project_file_content_reads_exact_zip_member(monkeypatch, tmp_path):
    from app.api.v1.endpoints import projects_files as projects_endpoint

    zip_path = tmp_path / "demo.zip"
    _build_zip(zip_path, {"src/discord/voice-message.ts": "console.log('ok');\n"})

    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id="project-1", source_type="zip"))

    monkeypatch.setattr(projects_endpoint, "load_project_zip", AsyncMock(return_value=str(zip_path)))
    monkeypatch.setattr(projects_endpoint, "get_zip_cache_manager", lambda: _CacheStub())

    result = await get_project_file_content(
        id="project-1",
        file_path="src/discord/voice-message.ts",
        encoding="utf-8",
        use_cache=False,
        stream=False,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.file_path == "src/discord/voice-message.ts"
    assert result.content == "console.log('ok');\n"
    assert result.is_text is True


@pytest.mark.asyncio
async def test_get_project_file_content_resolves_archive_root_prefixed_path(monkeypatch, tmp_path):
    from app.api.v1.endpoints import projects_files as projects_endpoint

    zip_path = tmp_path / "demo.zip"
    _build_zip(zip_path, {"src/discord/voice-message.ts": "console.log('ok');\n"})

    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id="project-1", source_type="zip"))

    monkeypatch.setattr(projects_endpoint, "load_project_zip", AsyncMock(return_value=str(zip_path)))
    monkeypatch.setattr(projects_endpoint, "get_zip_cache_manager", lambda: _CacheStub())

    result = await get_project_file_content(
        id="project-1",
        file_path="openclaw-2026.3.7/src/discord/voice-message.ts",
        encoding="utf-8",
        use_cache=False,
        stream=False,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert result.file_path == "src/discord/voice-message.ts"
    assert result.content == "console.log('ok');\n"
    assert result.is_text is True


@pytest.mark.asyncio
async def test_get_project_file_content_returns_404_when_zip_has_no_matching_member(
    monkeypatch,
    tmp_path,
):
    from app.api.v1.endpoints import projects_files as projects_endpoint

    zip_path = tmp_path / "demo.zip"
    _build_zip(zip_path, {"src/discord/voice-message.ts": "console.log('ok');\n"})

    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id="project-1", source_type="zip"))

    monkeypatch.setattr(projects_endpoint, "load_project_zip", AsyncMock(return_value=str(zip_path)))
    monkeypatch.setattr(projects_endpoint, "get_zip_cache_manager", lambda: _CacheStub())

    with pytest.raises(HTTPException) as exc_info:
        await get_project_file_content(
            id="project-1",
            file_path="missing-root/src/discord/missing.ts",
            encoding="utf-8",
            use_cache=False,
            stream=False,
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_project_file_content_rejects_dangerous_path(monkeypatch):
    from app.api.v1.endpoints import projects_files as projects_endpoint

    db = AsyncMock()
    db.get = AsyncMock(return_value=SimpleNamespace(id="project-1", source_type="zip"))

    monkeypatch.setattr(projects_endpoint, "load_project_zip", AsyncMock(return_value="/tmp/demo.zip"))
    monkeypatch.setattr(projects_endpoint, "get_zip_cache_manager", lambda: _CacheStub())

    with pytest.raises(HTTPException) as exc_info:
        await get_project_file_content(
            id="project-1",
            file_path="../etc/passwd",
            encoding="utf-8",
            use_cache=False,
            stream=False,
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 400
