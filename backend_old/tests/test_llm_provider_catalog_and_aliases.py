from types import SimpleNamespace

import pytest

from app.api.v1.endpoints.config import LLMFetchModelsRequest, fetch_llm_models
from app.services import llm_provider_service
from app.services.llm.types import LLMProvider


def test_llm_provider_catalog_contains_new_and_legacy_providers():
    providers = llm_provider_service.build_llm_provider_catalog()
    provider_ids = {item["id"] for item in providers}

    assert "openai" in provider_ids
    assert "openrouter" in provider_ids
    assert "anthropic" in provider_ids
    assert "azure_openai" in provider_ids
    assert "custom" in provider_ids

    # Legacy providers are still available.
    assert "gemini" in provider_ids
    assert "qwen" in provider_ids
    assert "deepseek" in provider_ids
    assert "baidu" in provider_ids

    # UI should use anthropic instead of claude.
    assert "claude" not in provider_ids


def test_provider_alias_resolution_for_runtime():
    provider_id, runtime_provider = llm_provider_service.resolve_llm_runtime_provider_alias("claude")
    assert provider_id == "anthropic"
    assert runtime_provider == LLMProvider.CLAUDE

    provider_id, runtime_provider = llm_provider_service.resolve_llm_runtime_provider_alias("anthropic")
    assert provider_id == "anthropic"
    assert runtime_provider == LLMProvider.CLAUDE

    provider_id, runtime_provider = llm_provider_service.resolve_llm_runtime_provider_alias("custom")
    assert provider_id == "custom"
    assert runtime_provider == LLMProvider.OPENAI


def test_extract_model_names_supports_openai_and_name_fields():
    payload = {
        "data": [
            {"id": "gpt-4o"},
            {"name": "gpt-4o-mini"},
            {"model": "gpt-5"},
            {"id": "gpt-4o"},
        ]
    }

    models = llm_provider_service.extract_model_names_from_payload(payload)
    assert models == ["gpt-4o", "gpt-4o-mini", "gpt-5"]


@pytest.mark.asyncio
async def test_fetch_models_falls_back_to_static_when_online_fetch_fails(monkeypatch):
    async def _raise_fetch_error(base_url: str, api_key: str):
        raise RuntimeError("network error")

    monkeypatch.setattr(
        "app.services.llm_provider_service.fetch_models_openai_compatible",
        _raise_fetch_error,
    )

    result = await fetch_llm_models(
        request=LLMFetchModelsRequest(
            provider="openai",
            apiKey="sk-test-123",
            baseUrl="https://example.com/v1",
        ),
        current_user=SimpleNamespace(id="test-user"),
    )

    assert result.success is True
    assert result.source == "fallback_static"
    assert result.models
    assert result.resolvedProvider == "openai"
    assert isinstance(result.modelMetadata, dict)
    assert result.tokenRecommendationSource in {"static_mapping", "default"}
