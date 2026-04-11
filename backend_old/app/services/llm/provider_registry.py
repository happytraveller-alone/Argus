"""
LLM provider registry helpers.
"""

from typing import Any, Optional

from .factory import LLMFactory, NATIVE_ONLY_PROVIDERS
from .types import DEFAULT_BASE_URLS, LLMProvider


LLM_PROVIDER_ALIASES: dict[str, str] = {
    "gemini": "gemini",
    "openai": "openai",
    "claude": "anthropic",
    "anthropic": "anthropic",
    "qwen": "qwen",
    "deepseek": "deepseek",
    "zhipu": "zhipu",
    "moonshot": "moonshot",
    "baidu": "baidu",
    "minimax": "minimax",
    "doubao": "doubao",
    "ollama": "ollama",
    "openrouter": "openrouter",
    "azure_openai": "azure_openai",
    "custom": "custom",
    "openai_compatible": "custom",
}

LLM_PROVIDER_RUNTIME_MAP: dict[str, LLMProvider] = {
    "gemini": LLMProvider.GEMINI,
    "openai": LLMProvider.OPENAI,
    "anthropic": LLMProvider.CLAUDE,
    "qwen": LLMProvider.QWEN,
    "deepseek": LLMProvider.DEEPSEEK,
    "zhipu": LLMProvider.ZHIPU,
    "moonshot": LLMProvider.MOONSHOT,
    "baidu": LLMProvider.BAIDU,
    "minimax": LLMProvider.MINIMAX,
    "doubao": LLMProvider.DOUBAO,
    "ollama": LLMProvider.OLLAMA,
    "openrouter": LLMProvider.OPENAI,
    "azure_openai": LLMProvider.OPENAI,
    "custom": LLMProvider.OPENAI,
}

LLM_PROVIDER_META_OVERRIDES: dict[str, dict[str, Any]] = {
    "custom": {
        "name": "OpenAI Compatible",
        "description": "适用于 OpenAI 兼容站点、中转服务和自建网关。",
        "defaultBaseUrl": "",
        "requiresApiKey": True,
        "fetchStyle": "openai_compatible",
        "exampleBaseUrls": [
            "https://api.openai.com/v1",
            "https://api.moonshot.cn/v1",
            "http://localhost:11434/v1",
        ],
        "supportsCustomHeaders": True,
    },
    "openai": {
        "name": "OpenAI",
        "description": "OpenAI 官方接口。",
        "defaultBaseUrl": "https://api.openai.com/v1",
        "fetchStyle": "openai_compatible",
        "exampleBaseUrls": ["https://api.openai.com/v1"],
        "supportsCustomHeaders": True,
    },
    "openrouter": {
        "name": "OpenRouter",
        "description": "OpenRouter 聚合网关（OpenAI 兼容）。",
        "defaultBaseUrl": "https://openrouter.ai/api/v1",
        "fetchStyle": "openai_compatible",
        "exampleBaseUrls": ["https://openrouter.ai/api/v1"],
        "supportsCustomHeaders": True,
    },
    "anthropic": {
        "name": "Anthropic",
        "description": "Anthropic Claude 官方接口。",
        "defaultBaseUrl": "https://api.anthropic.com/v1",
        "fetchStyle": "anthropic",
        "exampleBaseUrls": ["https://api.anthropic.com/v1"],
        "supportsCustomHeaders": True,
    },
    "azure_openai": {
        "name": "Azure OpenAI",
        "description": "Azure 托管 OpenAI 接口。",
        "defaultBaseUrl": "https://{resource}.openai.azure.com/openai/v1",
        "fetchStyle": "azure_openai",
        "exampleBaseUrls": ["https://{resource}.openai.azure.com/openai/v1"],
        "supportsCustomHeaders": True,
    },
    "moonshot": {
        "name": "Moonshot / Kimi",
        "description": "Moonshot Kimi 官方接口（OpenAI 兼容）。",
        "defaultBaseUrl": "https://api.moonshot.cn/v1",
        "fetchStyle": "openai_compatible",
        "exampleBaseUrls": ["https://api.moonshot.cn/v1"],
        "supportsCustomHeaders": True,
    },
    "ollama": {
        "name": "Ollama",
        "description": "本地部署 LLM（OpenAI 兼容，无需 API Key）。",
        "defaultBaseUrl": "http://localhost:11434/v1",
        "fetchStyle": "openai_compatible",
        "exampleBaseUrls": ["http://localhost:11434/v1"],
        "supportsCustomHeaders": True,
        "requiresApiKey": False,
    },
    "baidu": {
        "fetchStyle": "native_static",
        "supportsModelFetch": False,
        "supportsCustomHeaders": True,
    },
    "minimax": {
        "fetchStyle": "native_static",
        "supportsModelFetch": False,
        "supportsCustomHeaders": True,
    },
    "doubao": {
        "fetchStyle": "native_static",
        "supportsModelFetch": False,
        "supportsCustomHeaders": True,
    },
}


def normalize_llm_provider_id(provider: Any) -> str:
    normalized = str(provider or "").strip().lower()
    if not normalized:
        return ""
    return LLM_PROVIDER_ALIASES.get(normalized, normalized)


def resolve_llm_runtime_provider(provider: Any) -> tuple[str, Optional[LLMProvider]]:
    provider_id = normalize_llm_provider_id(provider)
    return provider_id, LLM_PROVIDER_RUNTIME_MAP.get(provider_id)


def _get_provider_default_model(
    provider_id: str,
    runtime_provider: Optional[LLMProvider],
) -> str:
    override = LLM_PROVIDER_META_OVERRIDES.get(provider_id, {})
    if "defaultModel" in override:
        return str(override.get("defaultModel") or "")
    if not runtime_provider:
        return ""
    return LLMFactory.get_default_model(runtime_provider)


def _get_provider_default_base_url(
    provider_id: str,
    runtime_provider: Optional[LLMProvider],
) -> str:
    override = LLM_PROVIDER_META_OVERRIDES.get(provider_id, {}).get("defaultBaseUrl")
    if isinstance(override, str):
        return override
    if not runtime_provider:
        return ""
    return DEFAULT_BASE_URLS.get(runtime_provider, "")


def _get_provider_static_models(
    provider_id: str,
    runtime_provider: Optional[LLMProvider],
) -> list[str]:
    override = LLM_PROVIDER_META_OVERRIDES.get(provider_id, {})
    if "models" in override and isinstance(override.get("models"), list):
        return list(override["models"])
    if not runtime_provider:
        return []
    return LLMFactory.get_available_models(runtime_provider)


def build_llm_provider_catalog() -> list[dict[str, Any]]:
    providers: list[dict[str, Any]] = []
    seen: set[str] = set()

    for provider in LLMFactory.get_supported_providers():
        provider_id = normalize_llm_provider_id(provider.value)
        if not provider_id or provider_id in seen:
            continue
        seen.add(provider_id)
        runtime_provider = LLM_PROVIDER_RUNTIME_MAP.get(provider_id)
        override = LLM_PROVIDER_META_OVERRIDES.get(provider_id, {})
        models = _get_provider_static_models(provider_id, runtime_provider)
        requires_api_key = (
            bool(override["requiresApiKey"])
            if "requiresApiKey" in override
            else runtime_provider != LLMProvider.OLLAMA
        )
        supports_model_fetch = (
            bool(override["supportsModelFetch"])
            if "supportsModelFetch" in override
            else provider not in NATIVE_ONLY_PROVIDERS
        )
        providers.append(
            {
                "id": provider_id,
                "name": override.get("name", provider_id.upper()),
                "description": override.get("description", f"{provider_id} 模型服务"),
                "defaultModel": _get_provider_default_model(provider_id, runtime_provider),
                "models": models,
                "defaultBaseUrl": _get_provider_default_base_url(
                    provider_id, runtime_provider
                ),
                "requiresApiKey": requires_api_key,
                "supportsModelFetch": supports_model_fetch,
                "fetchStyle": override.get(
                    "fetchStyle",
                    "native_static" if provider in NATIVE_ONLY_PROVIDERS else "openai_compatible",
                ),
                "exampleBaseUrls": list(override.get("exampleBaseUrls", [])),
                "supportsCustomHeaders": bool(
                    override.get("supportsCustomHeaders", True)
                ),
            }
        )

    for provider_id in ("custom", "openrouter", "azure_openai"):
        if provider_id in seen:
            continue
        runtime_provider = LLM_PROVIDER_RUNTIME_MAP.get(provider_id)
        override = LLM_PROVIDER_META_OVERRIDES.get(provider_id, {})
        providers.append(
            {
                "id": provider_id,
                "name": override.get("name", provider_id.upper()),
                "description": override.get("description", f"{provider_id} 模型服务"),
                "defaultModel": _get_provider_default_model(provider_id, runtime_provider),
                "models": _get_provider_static_models(provider_id, runtime_provider),
                "defaultBaseUrl": _get_provider_default_base_url(
                    provider_id, runtime_provider
                ),
                "requiresApiKey": bool(override.get("requiresApiKey", True)),
                "supportsModelFetch": bool(override.get("supportsModelFetch", True)),
                "fetchStyle": override.get("fetchStyle", "openai_compatible"),
                "exampleBaseUrls": list(override.get("exampleBaseUrls", [])),
                "supportsCustomHeaders": bool(
                    override.get("supportsCustomHeaders", True)
                ),
            }
        )

    preferred_order = {
        "custom": 0,
        "openai": 1,
        "openrouter": 2,
        "anthropic": 3,
        "azure_openai": 4,
        "moonshot": 5,
        "ollama": 6,
    }
    providers.sort(key=lambda item: (preferred_order.get(item["id"], 100), item["id"]))
    return providers
