from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import agent_tasks_bootstrap


@pytest.mark.asyncio
async def test_resolve_embedded_yasa_settings_prefers_rule_config(monkeypatch):
    class _FakeScalarResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(
                id="custom-yasa-1",
                is_active=True,
                language="javascript",
            )

    class _FakeDb:
        async def execute(self, _query):
            return _FakeScalarResult()

    settings = await agent_tasks_bootstrap._resolve_embedded_yasa_settings(
        db=_FakeDb(),
        programming_languages=["python"],
        yasa_language="auto",
        yasa_rule_config_id="custom-yasa-1",
    )

    assert settings["resolved_language"] == "javascript"
    assert settings["rule_config_id"] == "custom-yasa-1"


@pytest.mark.asyncio
async def test_resolve_embedded_yasa_settings_rejects_disabled_rule_config():
    class _FakeScalarResult:
        def scalar_one_or_none(self):
            return SimpleNamespace(
                id="custom-yasa-1",
                is_active=False,
                language="javascript",
            )

    class _FakeDb:
        async def execute(self, _query):
            return _FakeScalarResult()

    with pytest.raises(RuntimeError, match="已禁用"):
        await agent_tasks_bootstrap._resolve_embedded_yasa_settings(
            db=_FakeDb(),
            programming_languages=["python"],
            yasa_language="auto",
            yasa_rule_config_id="custom-yasa-1",
        )
