import json
import logging
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.db import init_db as init_db_module
from app.models.project import Project


class _ScalarFirstResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return self

    def first(self):
        return self._value


def _make_db(existing_project=None):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarFirstResult(existing_project))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.add = Mock()
    return db


@pytest.mark.asyncio
async def test_offline_seed_success(monkeypatch, tmp_path: Path):
    db = _make_db(existing_project=None)

    async def _refresh(instance):
        if isinstance(instance, Project) and not instance.id:
            instance.id = "project-1"

    db.refresh.side_effect = _refresh

    seed_zip = tmp_path / init_db_module.DEFAULT_LIBPLIST_ARCHIVE_NAME
    with zipfile.ZipFile(seed_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("libplist-2.7.0/src/main.c", "int main() { return 0; }\n")

    monkeypatch.setattr(
        init_db_module,
        "cleanup_legacy_default_projects",
        AsyncMock(),
    )
    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=False))
    save_mock = AsyncMock()
    monkeypatch.setattr(init_db_module, "save_project_zip", save_mock)
    monkeypatch.setattr(
        init_db_module,
        "detect_languages_from_paths",
        lambda _paths: ["C"],
    )
    monkeypatch.setattr(init_db_module, "DEFAULT_LIBPLIST_LOCAL_ZIP_PATH", str(seed_zip))

    await init_db_module.ensure_default_libplist_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
    )

    created_project = db.add.call_args[0][0]
    assert created_project.description == init_db_module.DEFAULT_LIBPLIST_DESCRIPTION
    assert created_project.source_type == "zip"
    assert created_project.repository_url is None
    assert json.loads(created_project.programming_languages) == ["C"]
    assert created_project.zip_file_hash
    save_mock.assert_awaited_once_with(
        "project-1",
        str(seed_zip),
        init_db_module.DEFAULT_LIBPLIST_ARCHIVE_NAME,
    )


@pytest.mark.asyncio
async def test_description_default_on_create(monkeypatch):
    db = _make_db(existing_project=None)

    async def _refresh(instance):
        if isinstance(instance, Project) and not instance.id:
            instance.id = "project-1"

    db.refresh.side_effect = _refresh

    monkeypatch.setattr(
        init_db_module,
        "cleanup_legacy_default_projects",
        AsyncMock(),
    )
    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=True))

    await init_db_module.ensure_default_libplist_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
    )

    created_project = db.add.call_args[0][0]
    assert created_project.description == init_db_module.DEFAULT_LIBPLIST_DESCRIPTION
    assert created_project.source_type == "zip"
    assert created_project.repository_url is None


@pytest.mark.asyncio
async def test_description_upgrade_legacy(monkeypatch):
    legacy_project = Project(
        id="project-1",
        owner_id="user-1",
        name=init_db_module.DEFAULT_LIBPLIST_NAME,
        description=init_db_module.DEFAULT_LIBPLIST_LEGACY_DESCRIPTION,
        source_type="zip",
        repository_url=init_db_module.DEFAULT_LIBPLIST_LEGACY_ZIP_URL,
        repository_type="other",
        default_branch="main",
        programming_languages="[]",
        is_active=True,
    )
    db = _make_db(existing_project=legacy_project)

    monkeypatch.setattr(
        init_db_module,
        "cleanup_legacy_default_projects",
        AsyncMock(),
    )
    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=True))

    await init_db_module.ensure_default_libplist_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
    )

    assert legacy_project.description == init_db_module.DEFAULT_LIBPLIST_DESCRIPTION
    assert legacy_project.repository_url is None


@pytest.mark.asyncio
async def test_description_keep_user_edited(monkeypatch):
    custom_description = "用户自定义描述"
    project = Project(
        id="project-1",
        owner_id="user-1",
        name=init_db_module.DEFAULT_LIBPLIST_NAME,
        description=custom_description,
        source_type="zip",
        repository_url=None,
        repository_type="other",
        default_branch="main",
        programming_languages="[]",
        is_active=True,
    )
    db = _make_db(existing_project=project)

    monkeypatch.setattr(
        init_db_module,
        "cleanup_legacy_default_projects",
        AsyncMock(),
    )
    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=True))

    await init_db_module.ensure_default_libplist_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
    )

    assert project.description == custom_description
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_seed_asset_missing(monkeypatch, tmp_path: Path, caplog):
    project = Project(
        id="project-1",
        owner_id="user-1",
        name=init_db_module.DEFAULT_LIBPLIST_NAME,
        description=init_db_module.DEFAULT_LIBPLIST_DESCRIPTION,
        source_type="zip",
        repository_url=None,
        repository_type="other",
        default_branch="main",
        programming_languages="[]",
        is_active=True,
    )
    db = _make_db(existing_project=project)

    monkeypatch.setattr(
        init_db_module,
        "cleanup_legacy_default_projects",
        AsyncMock(),
    )
    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=False))
    save_mock = AsyncMock()
    monkeypatch.setattr(init_db_module, "save_project_zip", save_mock)
    missing_zip = tmp_path / "missing-libplist.zip"
    monkeypatch.setattr(init_db_module, "DEFAULT_LIBPLIST_LOCAL_ZIP_PATH", str(missing_zip))

    caplog.set_level(logging.WARNING)
    await init_db_module.ensure_default_libplist_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
    )

    save_mock.assert_not_awaited()
    assert any("本地资源缺失" in record.message for record in caplog.records)
