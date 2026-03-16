from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import config as config_module
from app.api.v1.endpoints.config import (
    OtherConfigSchema,
    UserConfigRequest,
    get_my_config,
    update_my_config,
)
from app.models.user_config import UserConfig


class _FakeExecuteResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, existing_config=None):
        self.saved_config = existing_config

    async def execute(self, *args, **kwargs):
        return _FakeExecuteResult(self.saved_config)

    def add(self, config):
        self.saved_config = config

    async def commit(self):
        return None

    async def refresh(self, config):
        if not getattr(config, "id", None):
            config.id = "cfg-test"
        if not getattr(config, "created_at", None):
            config.created_at = datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_update_my_config_strips_frontend_mcp_payload_and_does_not_return_mcp_config(
    monkeypatch,
):
    fake_db = _FakeDB()

    response = await update_my_config(
        UserConfigRequest(
            otherConfig=OtherConfigSchema(
                maxAnalyzeFiles=12,
                mcpConfig={
                    "enabled": False,
                    "catalog": [{"id": "filesystem"}],
                    "runtimePolicy": {
                        "filesystem": {
                            "runtime_mode": "backend_only",
                            "backend_enabled": True,
                            "sandbox_enabled": False,
                        }
                    },
                },
            )
        ),
        db=fake_db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert fake_db.saved_config is not None
    stored_other = json.loads(fake_db.saved_config.other_config or "{}")
    assert "mcpConfig" not in stored_other

    assert "mcpConfig" not in response.otherConfig
    assert response.otherConfig.get("maxAnalyzeFiles") == 12


@pytest.mark.asyncio
async def test_get_my_config_strips_legacy_mcp_config_from_response(
    monkeypatch,
):
    existing = UserConfig(
        user_id="user-1",
        llm_config=json.dumps({}),
        other_config=json.dumps(
            {
                "maxAnalyzeFiles": 7,
                "mcpConfig": {
                    "enabled": False,
                    "catalog": [{"id": "frontend-fake"}],
                },
            }
        ),
    )
    existing.id = "cfg-existing"
    existing.created_at = datetime.now(timezone.utc)

    fake_db = _FakeDB(existing)

    response = await get_my_config(
        db=fake_db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.otherConfig.get("maxAnalyzeFiles") == 7
    assert "mcpConfig" not in response.otherConfig


@pytest.mark.asyncio
async def test_get_my_config_strips_legacy_git_tokens_from_other_config(
    monkeypatch,
):
    existing = UserConfig(
        user_id="user-1",
        llm_config=json.dumps({}),
        other_config=json.dumps(
            {
                "githubToken": "legacy-gh-token",
                "gitlabToken": "legacy-gl-token",
                "maxAnalyzeFiles": 9,
            }
        ),
    )
    existing.id = "cfg-existing"
    existing.created_at = datetime.now(timezone.utc)

    fake_db = _FakeDB(existing)

    response = await get_my_config(
        db=fake_db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.otherConfig.get("maxAnalyzeFiles") == 9
    assert "githubToken" not in response.otherConfig
    assert "gitlabToken" not in response.otherConfig
