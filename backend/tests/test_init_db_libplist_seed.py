import json
import logging
import sys
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

    def all(self):
        if self._value is None:
            return []
        if isinstance(self._value, list):
            return self._value
        return [self._value]


def _make_db(existing_project=None):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarFirstResult(existing_project))
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.add = Mock()
    return db


def _libplist_seed():
    return next(
        seed
        for seed in init_db_module._build_default_seed_projects()
        if seed.name == init_db_module.DEFAULT_LIBPLIST_NAME
    )


@pytest.mark.asyncio
async def test_remote_seed_success(monkeypatch, tmp_path: Path):
    db = _make_db(existing_project=None)

    async def _refresh(instance):
        if isinstance(instance, Project) and not instance.id:
            instance.id = "project-1"

    db.refresh.side_effect = _refresh

    seed_zip = tmp_path / init_db_module.DEFAULT_LIBPLIST_ARCHIVE_NAME
    with zipfile.ZipFile(seed_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("libplist-2.7.0/src/main.c", "int main() { return 0; }\n")

    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=False))
    save_mock = AsyncMock()
    monkeypatch.setattr(init_db_module, "save_project_zip", save_mock)
    download_mock = AsyncMock(return_value=str(seed_zip))
    monkeypatch.setattr(init_db_module, "download_seed_archive", download_mock)
    monkeypatch.setattr(
        init_db_module,
        "detect_languages_from_paths",
        lambda _paths: ["C"],
    )

    await init_db_module._ensure_default_zip_seed_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
        seed=_libplist_seed(),
    )

    created_project = db.add.call_args[0][0]
    assert created_project.description == init_db_module.DEFAULT_LIBPLIST_DESCRIPTION
    assert created_project.source_type == "zip"
    assert created_project.repository_url is None
    assert json.loads(created_project.programming_languages) == ["C"]
    assert created_project.zip_file_hash
    download_mock.assert_awaited_once()
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

    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=True))

    await init_db_module._ensure_default_zip_seed_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
        seed=_libplist_seed(),
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

    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=True))

    await init_db_module._ensure_default_zip_seed_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
        seed=_libplist_seed(),
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

    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=True))

    await init_db_module._ensure_default_zip_seed_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
        seed=_libplist_seed(),
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

    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=False))
    save_mock = AsyncMock()
    monkeypatch.setattr(init_db_module, "save_project_zip", save_mock)
    monkeypatch.setattr(
        init_db_module,
        "download_seed_archive",
        AsyncMock(side_effect=RuntimeError("mirror and origin all failed")),
    )

    caplog.set_level(logging.WARNING)
    await init_db_module._ensure_default_zip_seed_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
        seed=_libplist_seed(),
    )

    save_mock.assert_not_awaited()
    assert any("下载失败" in record.message for record in caplog.records)


def test_build_default_remote_seed_projects():
    seeds = init_db_module._build_default_seed_projects()
    seed_by_name = {seed.name: seed for seed in seeds}

    assert set(seed_by_name) == {
        "libplist",
        "DVWA",
        "DSVW",
        "WebGoat",
        "JavaSecLab",
        "govwa",
        "fastjson",
    }
    assert seed_by_name["libplist"].owner == "libimobiledevice"
    assert seed_by_name["libplist"].repo == "libplist"
    assert seed_by_name["libplist"].ref_type == "tag"
    assert seed_by_name["JavaSecLab"].ref == "V1.4"
    assert seed_by_name["DVWA"].ref_type == "commit"


@pytest.mark.asyncio
async def test_ensure_default_seed_projects(monkeypatch):
    db = _make_db(existing_project=[])
    user = SimpleNamespace(id="user-1")
    seeds = [
        init_db_module.DefaultZipSeedProject(
            name="seed-a",
            description="A",
            archive_name="a.zip",
            owner="owner-a",
            repo="repo-a",
            ref_type="commit",
            ref="sha-a",
            fallback_languages=["Python"],
        ),
        init_db_module.DefaultZipSeedProject(
            name="seed-b",
            description="B",
            archive_name="b.zip",
            owner="owner-b",
            repo="repo-b",
            ref_type="tag",
            ref="v1.0.0",
            fallback_languages=["Go"],
        ),
    ]

    monkeypatch.setattr(
        init_db_module,
        "_build_default_seed_projects",
        lambda: seeds,
    )
    ensure_mock = AsyncMock()
    monkeypatch.setattr(init_db_module, "_ensure_default_zip_seed_project", ensure_mock)

    await init_db_module.ensure_default_seed_projects(db=db, user=user)

    assert ensure_mock.await_count == 2
    called_names = [call.kwargs["seed"].name for call in ensure_mock.await_args_list]
    assert called_names == ["seed-a", "seed-b"]


@pytest.mark.asyncio
async def test_ensure_default_seed_projects_discards_legacy_demo_projects(monkeypatch):
    legacy_projects = [
        Project(
            id="legacy-1",
            owner_id="user-1",
            name="电商平台后端",
            description="legacy",
            source_type="zip",
            repository_url=None,
            repository_type="other",
            default_branch="main",
            programming_languages="[]",
            is_active=True,
        ),
        Project(
            id="legacy-2",
            owner_id="user-1",
            name="移动端 App",
            description="legacy",
            source_type="zip",
            repository_url=None,
            repository_type="other",
            default_branch="main",
            programming_languages="[]",
            is_active=True,
        ),
    ]
    db = _make_db(existing_project=legacy_projects)
    db.delete = AsyncMock()
    user = SimpleNamespace(id="user-1")
    seeds = [
        init_db_module.DefaultZipSeedProject(
            name="seed-a",
            description="A",
            archive_name="a.zip",
            owner="owner-a",
            repo="repo-a",
            ref_type="commit",
            ref="sha-a",
            fallback_languages=["Python"],
        ),
    ]

    monkeypatch.setattr(init_db_module, "_build_default_seed_projects", lambda: seeds)
    delete_project_zip_mock = AsyncMock()
    monkeypatch.setattr(init_db_module, "delete_project_zip", delete_project_zip_mock)
    ensure_mock = AsyncMock()
    monkeypatch.setattr(init_db_module, "_ensure_default_zip_seed_project", ensure_mock)

    await init_db_module.ensure_default_seed_projects(db=db, user=user)

    delete_project_zip_mock.assert_any_await("legacy-1")
    delete_project_zip_mock.assert_any_await("legacy-2")
    assert db.delete.await_count == 2
    db.commit.assert_awaited_once()
    ensure_mock.assert_awaited_once_with(db=db, user=user, seed=seeds[0])


@pytest.mark.asyncio
async def test_existing_stored_zip_skips_download(monkeypatch):
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

    monkeypatch.setattr(init_db_module, "has_project_zip", AsyncMock(return_value=True))
    download_mock = AsyncMock()
    monkeypatch.setattr(init_db_module, "download_seed_archive", download_mock)

    await init_db_module._ensure_default_zip_seed_project(
        db=db,
        user=SimpleNamespace(id="user-1"),
        seed=_libplist_seed(),
    )

    download_mock.assert_not_awaited()


def test_init_db_module_no_longer_exports_legacy_demo_helpers():
    assert not hasattr(init_db_module, "cleanup_legacy_default_projects")
    assert not hasattr(init_db_module, "ensure_default_libplist_project")
    assert not hasattr(init_db_module, "ensure_default_test_resource_projects")
    assert not hasattr(init_db_module, "create_demo_data")


@pytest.mark.asyncio
async def test_init_db_uses_seed_project_initializer(monkeypatch):
    db = AsyncMock()
    user = SimpleNamespace(id="user-1")
    create_demo_user_mock = AsyncMock(return_value=user)
    ensure_default_seed_projects_mock = AsyncMock()
    create_internal_rules_mock = AsyncMock()
    create_patch_rules_mock = AsyncMock()
    ensure_builtin_gitleaks_rules_mock = AsyncMock()
    init_templates_mock = AsyncMock()

    monkeypatch.setattr(init_db_module, "create_demo_user", create_demo_user_mock)
    monkeypatch.setattr(init_db_module, "ensure_default_seed_projects", ensure_default_seed_projects_mock)
    monkeypatch.setattr(init_db_module, "create_internal_opengrep_rules", create_internal_rules_mock)
    monkeypatch.setattr(init_db_module, "create_patch_opengrep_rules", create_patch_rules_mock)
    monkeypatch.setattr(init_db_module, "ensure_builtin_gitleaks_rules", ensure_builtin_gitleaks_rules_mock)
    monkeypatch.setitem(
        sys.modules,
        "app.services.init_templates",
        SimpleNamespace(init_templates_and_rules=init_templates_mock),
    )

    await init_db_module.init_db(db)

    create_demo_user_mock.assert_awaited_once_with(db)
    ensure_default_seed_projects_mock.assert_awaited_once_with(db, user)
    create_internal_rules_mock.assert_awaited_once_with(db)
    create_patch_rules_mock.assert_awaited_once_with(db)
    ensure_builtin_gitleaks_rules_mock.assert_awaited_once_with(db)
    init_templates_mock.assert_awaited_once_with(db)
