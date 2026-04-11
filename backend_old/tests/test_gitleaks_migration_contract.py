from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import ProgrammingError

from app.api.v1.endpoints import static_tasks
from app.db import init_db as init_db_module
from app.services import gitleaks_rules_seed


class _NestedContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FailingDb:
    def begin_nested(self):
        return _NestedContext()

    async def execute(self, *_args, **_kwargs):
        raise ProgrammingError(
            "SELECT * FROM gitleaks_rules",
            {},
            Exception('relation "gitleaks_rules" does not exist'),
        )


@pytest.mark.asyncio
async def test_gitleaks_config_builder_requires_migrated_rules_table():
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        await static_tasks._build_effective_gitleaks_config_toml(
            _FailingDb(),
            {"customConfigToml": ""},
        )


@pytest.mark.asyncio
async def test_list_gitleaks_rules_returns_explicit_migration_error_when_table_missing():
    with pytest.raises(HTTPException) as exc_info:
        await static_tasks.list_gitleaks_rules(
            db=_FailingDb(),
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 500
    assert "alembic upgrade head" in str(exc_info.value.detail)


def test_init_db_no_longer_exports_runtime_schema_fixer():
    assert not hasattr(init_db_module, "ensure_project_zip_hash_schema")


def test_gitleaks_builtin_seed_path_prefers_rust_asset_root():
    assert gitleaks_rules_seed._BUILTIN_TOML_PATH == (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "assets"
        / "scan_rule_assets"
        / "gitleaks_builtin"
        / "gitleaks-default.toml"
    )
