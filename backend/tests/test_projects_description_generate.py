import io
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, UploadFile

from app.api.v1.endpoints.projects import (
    generate_project_description_preview,
    get_project_info,
    upload_project_zip,
)
from app.services.upload.project_stats import ProjectDescriptionAnalyzer


class _ScalarFirstResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


def _make_upload_file(filename: str = "demo.zip", content: bytes = b"fake-data"):
    return UploadFile(filename=filename, file=io.BytesIO(content))


@pytest.mark.asyncio
async def test_project_description_analyzer_uses_single_llm_summary_call(tmp_path):
    project_dir = tmp_path / "demo-app"
    project_dir.mkdir()
    (project_dir / "package.json").write_text(
        '{"name":"demo-app","scripts":{"dev":"vite"},"dependencies":{"react":"18.0.0"}}',
        encoding="utf-8",
    )
    src_dir = project_dir / "src"
    src_dir.mkdir()
    (src_dir / "main.tsx").write_text(
        "import React from 'react';\nexport function App() { return <div>Hello</div>; }\n",
        encoding="utf-8",
    )

    analyzer = ProjectDescriptionAnalyzer(user_config={"llmConfig": {"provider": "mock"}})
    llm_mock = AsyncMock(
        return_value={
            "content": "这是一个用于前端后台联动演示的 React 项目，适合快速搭建管理后台原型。"
        }
    )
    analyzer.llm_service = SimpleNamespace(chat_completion=llm_mock)

    result = await analyzer.analyze_project(str(project_dir))

    assert llm_mock.await_count == 1
    assert result["project_description"] == (
        "这是一个用于前端后台联动演示的 React 项目，适合快速搭建管理后台原型。"
    )


@pytest.mark.asyncio
async def test_upload_project_zip_generates_and_persists_project_description(monkeypatch):
    from app.api.v1.endpoints import projects as projects_endpoint

    project = SimpleNamespace(
        id="project-1",
        name="demo-app",
        source_type="zip",
        zip_file_hash=None,
        programming_languages="[]",
        description="",
    )
    added_objects = []
    db = AsyncMock()
    db.get = AsyncMock(return_value=project)
    db.execute = AsyncMock(return_value=_ScalarFirstResult(None))
    db.add = Mock(side_effect=lambda obj: added_objects.append(obj))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()

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
        AsyncMock(return_value=(True, ["src/main.ts", "package.json"], None)),
    )
    monkeypatch.setattr(
        projects_endpoint.UploadManager,
        "get_file_list_preview",
        lambda _path, limit=100: (True, ["src/main.ts", "package.json"], None),
    )
    monkeypatch.setattr(projects_endpoint, "create_zip_with_exclusions", lambda _src, _dst: None)
    monkeypatch.setattr(
        projects_endpoint,
        "save_project_zip",
        AsyncMock(
            return_value={
                "original_filename": "project-1.zip",
                "file_size": 128,
                "uploaded_at": "2026-03-07T00:00:00Z",
            }
        ),
    )
    monkeypatch.setattr(projects_endpoint, "calculate_file_sha256", lambda _path: "hash-1")
    monkeypatch.setattr(
        projects_endpoint,
        "find_duplicate_zip_project",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        projects_endpoint,
        "detect_languages_from_paths",
        lambda _paths: ["TypeScript"],
    )
    monkeypatch.setattr(
        projects_endpoint,
        "get_cloc_stats_from_extracted_dir",
        AsyncMock(
            return_value='{"total": 42, "total_files": 2, "languages": {"TypeScript": {"loc_number": 42, "files_count": 2, "proportion": 1.0}}}'
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
        AsyncMock(return_value={"project_description": "智能简介"}),
    )

    response = await upload_project_zip(
        id="project-1",
        file=_make_upload_file(),
        db=db,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert response["message"] == "文件上传成功（已转换为 ZIP 格式）"
    assert project.description == "智能简介"
    project_info = next(
        obj for obj in added_objects if getattr(obj, "project_id", None) == "project-1"
    )
    assert project_info.description == "智能简介"
    assert project_info.status == "completed"
    assert project_info.language_info == (
        '{"total": 42, "total_files": 2, "languages": {"TypeScript": {"loc_number": 42, "files_count": 2, "proportion": 1.0}}}'
    )


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

    project = SimpleNamespace(id="project-1", name="demo", source_type="zip")

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


@pytest.mark.asyncio
async def test_get_project_info_repository_is_hidden(monkeypatch):
    from app.api.v1.endpoints import projects as projects_endpoint

    project = SimpleNamespace(
        id="project-1",
        name="demo",
        source_type="repository",
    )

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

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("get_cloc_stats should not be called for repository projects")

    monkeypatch.setattr(projects_endpoint, "get_cloc_stats", _fail_if_called)

    with pytest.raises(HTTPException) as exc_info:
        await get_project_info(
            id="project-1",
            db=db,
            current_user=SimpleNamespace(id="u-1"),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "项目不存在"


@pytest.mark.asyncio
async def test_get_project_info_pending_returns_pending_payload():
    project = SimpleNamespace(
        id="project-1",
        name="demo",
        source_type="zip",
    )
    existing_info = SimpleNamespace(
        id="info-1",
        project_id="project-1",
        language_info=None,
        description=None,
        status="pending",
        created_at="2026-01-01T00:00:00Z",
    )

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarFirstResult(project),
            _ScalarFirstResult(existing_info),
        ]
    )

    info = await get_project_info(
        id="project-1",
        db=db,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert info.status == "pending"
    assert info.language_info == '{"total": 0, "total_files": 0, "languages": {}}'
    assert info.description == ""
