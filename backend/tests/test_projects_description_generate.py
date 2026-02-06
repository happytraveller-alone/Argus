import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1.endpoints.projects import (
    generate_project_description_preview,
    get_project_info,
)


class _ScalarFirstResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value


def _make_upload_file(filename: str = "demo.zip", content: bytes = b"fake-data"):
    return UploadFile(filename=filename, file=io.BytesIO(content))


@pytest.mark.asyncio
async def test_generate_project_description_preview_llm_success(monkeypatch):
    from app.api.v1.endpoints import projects as projects_endpoint

    monkeypatch.setattr(
        projects_endpoint.CompressionStrategyFactory,
        "get_supported_formats",
        lambda: {".zip"},
    )
    monkeypatch.setattr(
        projects_endpoint.UploadManager,
        "validate_file",
        lambda _path: (True, None),
    )
    monkeypatch.setattr(
        projects_endpoint.UploadManager,
        "extract_file",
        AsyncMock(return_value=(True, ["src/main.py"], None)),
    )
    monkeypatch.setattr(
        projects_endpoint,
        "get_cloc_stats_from_extracted_dir",
        AsyncMock(
            return_value='{"total": 10, "total_files": 1, "languages": {"Python": {"loc_number": 10, "files_count": 1, "proportion": 1.0}}}'
        ),
    )
    monkeypatch.setattr(
        projects_endpoint,
        "build_static_project_description",
        lambda _language_info, _project_name: "static-desc",
    )
    monkeypatch.setattr(
        projects_endpoint,
        "_get_user_config",
        AsyncMock(return_value={"llmConfig": {"provider": "mock"}}),
    )
    monkeypatch.setattr(
        projects_endpoint,
        "generate_project_description_from_extracted_dir",
        AsyncMock(return_value={"project_description": "llm-desc"}),
    )

    response = await generate_project_description_preview(
        file=_make_upload_file(),
        project_name="demo",
        db=AsyncMock(),
        current_user=SimpleNamespace(id="u-1"),
    )

    assert response.source == "llm"
    assert response.description == "llm-desc"
    assert '"languages"' in response.language_info


@pytest.mark.asyncio
async def test_generate_project_description_preview_fallback_static(monkeypatch):
    from app.api.v1.endpoints import projects as projects_endpoint

    monkeypatch.setattr(
        projects_endpoint.CompressionStrategyFactory,
        "get_supported_formats",
        lambda: {".zip"},
    )
    monkeypatch.setattr(
        projects_endpoint.UploadManager,
        "validate_file",
        lambda _path: (True, None),
    )
    monkeypatch.setattr(
        projects_endpoint.UploadManager,
        "extract_file",
        AsyncMock(return_value=(True, ["src/main.py"], None)),
    )
    monkeypatch.setattr(
        projects_endpoint,
        "get_cloc_stats_from_extracted_dir",
        AsyncMock(return_value='{"total": 2, "total_files": 1, "languages": {}}'),
    )
    monkeypatch.setattr(
        projects_endpoint,
        "build_static_project_description",
        lambda _language_info, _project_name: "static-desc",
    )
    monkeypatch.setattr(
        projects_endpoint,
        "_get_user_config",
        AsyncMock(return_value={"llmConfig": {"provider": "mock"}}),
    )
    monkeypatch.setattr(
        projects_endpoint,
        "generate_project_description_from_extracted_dir",
        AsyncMock(return_value={"project_description": ""}),
    )

    response = await generate_project_description_preview(
        file=_make_upload_file(),
        project_name="demo",
        db=AsyncMock(),
        current_user=SimpleNamespace(id="u-1"),
    )

    assert response.source == "static"
    assert response.description == "static-desc"


@pytest.mark.asyncio
async def test_generate_project_description_preview_invalid_format(monkeypatch):
    from app.api.v1.endpoints import projects as projects_endpoint

    monkeypatch.setattr(
        projects_endpoint.CompressionStrategyFactory,
        "get_supported_formats",
        lambda: {".zip"},
    )

    with pytest.raises(HTTPException) as exc:
        await generate_project_description_preview(
            file=_make_upload_file(filename="demo.txt"),
            project_name="demo",
            db=AsyncMock(),
            current_user=SimpleNamespace(id="u-1"),
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_project_info_does_not_generate_description(monkeypatch):
    from app.api.v1.endpoints import projects as projects_endpoint

    project = SimpleNamespace(id="project-1", name="demo")

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarFirstResult(project),
            _ScalarFirstResult(None),
        ]
    )
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    monkeypatch.setattr(
        projects_endpoint,
        "get_cloc_stats",
        AsyncMock(return_value='{"total": 1, "total_files": 1, "languages": {}}'),
    )

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("build_static_project_description should not be called")

    monkeypatch.setattr(
        projects_endpoint,
        "build_static_project_description",
        _fail_if_called,
    )

    info = await get_project_info(
        id="project-1",
        db=db,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert info.project_id == "project-1"
    assert info.language_info == '{"total": 1, "total_files": 1, "languages": {}}'
    assert info.description == ""
    assert info.status == "completed"
