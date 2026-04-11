import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import agent_tasks as agent_tasks_module
from app.api.v1.endpoints import config as config_module
from app.api.v1.endpoints.config import (
    LLMTestRequest,
    agent_task_llm_preflight,
    get_default_config,
    test_llm_connection as llm_connection_endpoint,
)
from app.models.user_config import UserConfig
from app.services import user_config_service
from app.services.llm.factory import LLMFactory
from app.services.llm.service import LLMConfigError, LLMService
from app.services.llm.types import LLMConfig, LLMProvider


class _DummyResult:
    def scalar_one_or_none(self):
        return None


class _DummyDB:
    async def execute(self, *_args, **_kwargs):
        return _DummyResult()


class _ConfigExecuteResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ConfigDB:
    def __init__(self, saved_config=None):
        self.saved_config = saved_config

    async def execute(self, *_args, **_kwargs):
        return _ConfigExecuteResult(self.saved_config)


def _build_saved_user_config(llm_config: dict | None):
    config = UserConfig(
        user_id="test-user",
        llm_config=json.dumps(llm_config or {}),
        other_config=json.dumps({}),
    )
    config.id = "cfg-test"
    config.created_at = datetime.now(timezone.utc)
    return config


def test_llm_service_requires_base_url():
    service = LLMService(
        user_config={
            "llmConfig": {
                "llmProvider": "openai",
                "llmApiKey": "sk-test",
                "llmModel": "gpt-5",
            }
        }
    )

    with pytest.raises(LLMConfigError, match="llmBaseUrl"):
        _ = service.config


def test_llm_service_uses_provider_specific_key_when_generic_missing():
    service = LLMService(
        user_config={
            "llmConfig": {
                "llmProvider": "openai",
                "openaiApiKey": "sk-provider-specific",
                "llmModel": "gpt-5",
                "llmBaseUrl": "https://api.openai.com/v1",
            }
        }
    )

    config = service.config
    assert config.api_key == "sk-provider-specific"
    assert config.model == "gpt-5"
    assert config.base_url == "https://api.openai.com/v1"


def test_llm_service_allows_ollama_without_api_key():
    service = LLMService(
        user_config={
            "llmConfig": {
                "llmProvider": "ollama",
                "llmModel": "llama3.3",
                "llmBaseUrl": "http://localhost:11434/v1",
            }
        }
    )

    config = service.config
    assert config.provider == LLMProvider.OLLAMA
    assert config.api_key == "ollama"


def test_llm_factory_create_adapter_does_not_reuse_cache(monkeypatch):
    config = LLMConfig(
        provider=LLMProvider.OPENAI,
        api_key="sk-test",
        model="gpt-5",
        base_url="https://api.openai.com/v1",
    )

    def _fake_instantiate(cls, _config):
        return object()

    monkeypatch.setattr(LLMFactory, "_instantiate_adapter", classmethod(_fake_instantiate))

    first = LLMFactory.create_adapter(config)
    second = LLMFactory.create_adapter(config)
    assert first is not second


def test_default_config_uses_updated_agent_stream_timeouts():
    config = get_default_config()

    assert config["llmConfig"]["llmFirstTokenTimeout"] == 45
    assert config["llmConfig"]["llmStreamTimeout"] == 120


@pytest.mark.asyncio
async def test_test_llm_connection_requires_model_for_ollama():
    with pytest.raises(HTTPException) as exc_info:
        await llm_connection_endpoint(
            request=LLMTestRequest(
                provider="ollama",
                apiKey="",
                model="",
                baseUrl="http://localhost:11434/v1",
            ),
            db=_DummyDB(),
            current_user=SimpleNamespace(id="test-user"),
        )

    assert exc_info.value.status_code == 400
    assert "model" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_test_llm_connection_requires_api_key_for_non_ollama():
    with pytest.raises(HTTPException) as exc_info:
        await llm_connection_endpoint(
            request=LLMTestRequest(
                provider="openai",
                apiKey="",
                model="gpt-5",
                baseUrl="https://api.openai.com/v1",
            ),
            db=_DummyDB(),
            current_user=SimpleNamespace(id="test-user"),
        )

    assert exc_info.value.status_code == 400
    assert "apiKey" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_agent_task_llm_preflight_returns_default_config_when_user_never_saved_llm(
    monkeypatch,
):
    monkeypatch.setattr(
        config_module,
        "get_default_config",
        lambda: {
            "llmConfig": {
                "llmProvider": "openai",
                "llmApiKey": "",
                "llmModel": "gpt-5",
                "llmBaseUrl": "https://api.openai.com/v1",
                "openaiApiKey": "",
            },
            "otherConfig": {},
        },
    )

    response = await agent_task_llm_preflight(
        db=_ConfigDB(),
        current_user=SimpleNamespace(id="test-user"),
    )

    assert response.ok is False
    assert response.reasonCode == "default_config"
    assert response.savedConfig is None
    assert response.effectiveConfig.provider == "openai"
    assert response.effectiveConfig.model == "gpt-5"
    assert response.effectiveConfig.baseUrl == "https://api.openai.com/v1"


@pytest.mark.asyncio
async def test_agent_task_llm_preflight_returns_missing_fields_for_partial_saved_config(
    monkeypatch,
):
    monkeypatch.setattr(
        config_module,
        "get_default_config",
        lambda: {
            "llmConfig": {
                "llmProvider": "openai",
                "llmApiKey": "",
                "llmModel": "gpt-5-default",
                "llmBaseUrl": "https://default.example.com/v1",
                "openaiApiKey": "",
            },
            "otherConfig": {},
        },
    )

    response = await agent_task_llm_preflight(
        db=_ConfigDB(
            _build_saved_user_config(
                {
                    "llmProvider": "openai",
                    "llmModel": "gpt-5-user",
                }
            )
        ),
        current_user=SimpleNamespace(id="test-user"),
    )

    assert response.ok is False
    assert response.reasonCode == "missing_fields"
    assert response.missingFields == ["llmBaseUrl", "llmApiKey"]
    assert response.savedConfig is not None
    assert response.savedConfig.model == "gpt-5-user"
    assert response.savedConfig.baseUrl == ""
    assert response.savedConfig.apiKey == ""
    assert response.effectiveConfig.model == "gpt-5-user"
    assert response.effectiveConfig.baseUrl == "https://default.example.com/v1"


@pytest.mark.asyncio
async def test_agent_task_llm_preflight_uses_provider_specific_api_key_and_passes(
    monkeypatch,
):
    llm_test_mock = AsyncMock(
        return_value=config_module.LLMTestResponse(
            success=True,
            message="ok",
            model="gpt-5",
        )
    )
    monkeypatch.setattr(
        config_module,
        "_execute_llm_test_request",
        llm_test_mock,
        raising=False,
    )

    response = await agent_task_llm_preflight(
        db=_ConfigDB(
            _build_saved_user_config(
                {
                    "llmProvider": "openai",
                    "openaiApiKey": "sk-provider-specific",
                    "llmModel": "gpt-5",
                    "llmBaseUrl": "https://api.openai.com/v1",
                }
            )
        ),
        current_user=SimpleNamespace(id="test-user"),
    )

    assert response.ok is True
    assert response.reasonCode is None
    assert response.savedConfig is not None
    assert response.savedConfig.apiKey == "sk-provider-specific"
    assert llm_test_mock.await_count == 1


@pytest.mark.asyncio
async def test_agent_task_llm_preflight_reports_timeout(monkeypatch):
    async def _raise_timeout(_awaitable, timeout):
        close = getattr(_awaitable, "close", None)
        if callable(close):
            close()
        raise asyncio.TimeoutError()

    monkeypatch.setattr(config_module.asyncio, "wait_for", _raise_timeout)
    monkeypatch.setattr(
        config_module,
        "_execute_llm_test_request",
        AsyncMock(),
        raising=False,
    )

    response = await agent_task_llm_preflight(
        db=_ConfigDB(
            _build_saved_user_config(
                {
                    "llmProvider": "openai",
                    "llmApiKey": "sk-test",
                    "llmModel": "gpt-5",
                    "llmBaseUrl": "https://api.openai.com/v1",
                }
            )
        ),
        current_user=SimpleNamespace(id="test-user"),
    )

    assert response.ok is False
    assert response.reasonCode == "llm_test_timeout"
    assert response.stage == "llm_test"


@pytest.mark.asyncio
async def test_load_user_config_payload_with_effective_defaults_merges_env_values(
    monkeypatch,
):
    monkeypatch.setattr(
        config_module,
        "get_default_config",
        lambda: {
            "llmConfig": {
                "llmProvider": "openai",
                "llmApiKey": "",
                "llmModel": "gpt-5-default",
                "llmBaseUrl": "https://default.example.com/v1",
                "openaiApiKey": "sk-default-provider",
                "llmTimeout": 150000,
            },
            "otherConfig": {
                "llmConcurrency": 2,
            },
        },
    )

    saved_llm_config, saved_other_config, effective_llm_config, effective_other_config = (
        await config_module._load_user_config_payload_with_effective_defaults(
            db=_ConfigDB(
                _build_saved_user_config(
                    {
                        "llmProvider": "openai",
                        "llmModel": "gpt-5-user",
                    }
                )
            ),
            user_id="test-user",
        )
    )

    assert saved_llm_config == {
        "llmProvider": "openai",
        "llmModel": "gpt-5-user",
    }
    assert saved_other_config == {}
    assert effective_llm_config["llmProvider"] == "openai"
    assert effective_llm_config["llmModel"] == "gpt-5-user"
    assert effective_llm_config["llmBaseUrl"] == "https://default.example.com/v1"
    assert effective_llm_config["openaiApiKey"] == "sk-default-provider"
    assert effective_llm_config["llmTimeout"] == 150000
    assert effective_other_config["llmConcurrency"] == 2


@pytest.mark.asyncio
async def test_agent_tasks_runtime_user_config_uses_effective_defaults(monkeypatch):
    monkeypatch.setattr(
        user_config_service,
        "get_default_user_config",
        lambda: {
            "llmConfig": {
                "llmProvider": "openai",
                "llmApiKey": "",
                "llmModel": "gpt-5-default",
                "llmBaseUrl": "https://default.example.com/v1",
                "openaiApiKey": "sk-default-provider",
            },
            "otherConfig": {
                "llmConcurrency": 3,
            },
        },
    )

    runtime_user_config = await agent_tasks_module._get_user_config(
        db=_ConfigDB(
            _build_saved_user_config(
                {
                    "llmProvider": "openai",
                    "llmModel": "gpt-5-user",
                }
            )
        ),
        user_id="test-user",
    )

    assert runtime_user_config is not None
    assert runtime_user_config["llmConfig"]["llmModel"] == "gpt-5-user"
    assert (
        runtime_user_config["llmConfig"]["llmBaseUrl"]
        == "https://default.example.com/v1"
    )
    assert runtime_user_config["llmConfig"]["openaiApiKey"] == "sk-default-provider"

    service = LLMService(user_config=runtime_user_config)
    config = service.config
    assert config.base_url == "https://default.example.com/v1"
    assert config.api_key == "sk-default-provider"
