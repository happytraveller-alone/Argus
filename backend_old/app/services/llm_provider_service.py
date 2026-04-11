from typing import Any, Optional

import httpx

from app.services.llm.provider_registry import (
    build_llm_provider_catalog as build_provider_catalog,
    resolve_llm_runtime_provider as resolve_provider_runtime,
)
from app.services.llm.types import LLMProvider


def resolve_llm_runtime_provider_alias(provider: Any) -> tuple[str, Optional[LLMProvider]]:
    return resolve_provider_runtime(provider)


def build_llm_provider_catalog() -> list[dict[str, Any]]:
    return build_provider_catalog()


def normalize_llm_provider_id(provider: Any) -> str:
    resolved_provider_id, _ = resolve_llm_runtime_provider_alias(provider)
    normalized = str(resolved_provider_id or provider or "").strip().lower()
    if not normalized:
        return "openai"
    return normalized


def provider_api_key_field(provider: str) -> Optional[str]:
    field_map = {
        "custom": "openaiApiKey",
        "openai": "openaiApiKey",
        "openrouter": "openaiApiKey",
        "azure_openai": "openaiApiKey",
        "anthropic": "claudeApiKey",
        "claude": "claudeApiKey",
        "gemini": "geminiApiKey",
        "qwen": "qwenApiKey",
        "deepseek": "deepseekApiKey",
        "zhipu": "zhipuApiKey",
        "moonshot": "moonshotApiKey",
        "baidu": "baiduApiKey",
        "minimax": "minimaxApiKey",
        "doubao": "doubaoApiKey",
    }
    return field_map.get(provider)


def extract_model_names_from_payload(payload: Any) -> list[str]:
    candidates: list[str] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, dict):
                model_name = item.get("id") or item.get("name") or item.get("model")
                if isinstance(model_name, str):
                    candidates.append(model_name)
    elif isinstance(payload, dict):
        for key in ("data", "models"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend(extract_model_names_from_payload(value))

    normalized = sorted(
        {str(item).strip() for item in candidates if str(item).strip()},
        key=str.lower,
    )
    return normalized


def _iter_model_items_from_payload(payload: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                items.append(item)
    elif isinstance(payload, dict):
        for key in ("data", "models"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        items.append(item)
    return items


def _parse_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(float(value))
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _extract_int_from_paths(payload: dict[str, Any], paths: list[tuple[str, ...]]) -> Optional[int]:
    for path in paths:
        cursor: Any = payload
        ok = True
        for key in path:
            if not isinstance(cursor, dict):
                ok = False
                break
            cursor = cursor.get(key)
        if not ok:
            continue
        parsed = _parse_positive_int(cursor)
        if parsed is not None:
            return parsed
    return None


def recommend_tokens_from_static_map(model_name: str) -> Optional[int]:
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return None

    high_reasoning_hints = (
        "gpt-5",
        "o3",
        "o4",
        "claude-opus",
        "claude-sonnet",
        "deepseek-r1",
        "deepseek-v3",
        "qwen3-max",
        "qwen3-235b",
        "kimi-k2",
        "glm-4.6",
        "ernie-4.5",
        "minimax-m2",
        "doubao-1.6",
        "llama3.3-70b",
    )
    medium_hints = (
        "mini",
        "haiku",
        "flash",
        "small",
        "3.5",
        "qwen3-4b",
        "qwen3-8b",
        "gemma",
    )

    if any(hint in normalized for hint in high_reasoning_hints):
        return 16384
    if any(hint in normalized for hint in medium_hints):
        return 8192
    return None


def extract_model_metadata_from_payload(payload: Any) -> dict[str, dict[str, Optional[int] | str]]:
    metadata: dict[str, dict[str, Optional[int] | str]] = {}
    items = _iter_model_items_from_payload(payload)
    for item in items:
        model_name = item.get("id") or item.get("name") or item.get("model")
        if not isinstance(model_name, str):
            continue
        model_id = model_name.strip()
        if not model_id:
            continue

        context_window = _extract_int_from_paths(
            item,
            [
                ("context_window",),
                ("contextWindow",),
                ("context_length",),
                ("contextLength",),
                ("context",),
                ("max_context_tokens",),
                ("input_token_limit",),
                ("limits", "context_window"),
                ("limits", "contextWindow"),
                ("limits", "context_length"),
                ("limits", "max_context_tokens"),
                ("capabilities", "context_window"),
                ("capabilities", "contextWindow"),
            ],
        )
        max_output_tokens = _extract_int_from_paths(
            item,
            [
                ("max_output_tokens",),
                ("maxOutputTokens",),
                ("output_token_limit",),
                ("completion_token_limit",),
                ("limits", "max_output_tokens"),
                ("limits", "maxOutputTokens"),
                ("limits", "output_token_limit"),
                ("limits", "completion_token_limit"),
                ("capabilities", "max_output_tokens"),
                ("capabilities", "maxOutputTokens"),
            ],
        )
        recommended = (
            max_output_tokens
            if max_output_tokens is not None
            else recommend_tokens_from_static_map(model_id)
        )
        source = "online_metadata" if max_output_tokens is not None else "static_mapping"
        metadata[model_id] = {
            "contextWindow": context_window,
            "maxOutputTokens": max_output_tokens,
            "recommendedMaxTokens": recommended,
            "source": source,
        }
    return metadata


def build_static_model_metadata(models: list[str]) -> dict[str, dict[str, Optional[int] | str]]:
    metadata: dict[str, dict[str, Optional[int] | str]] = {}
    for model in models:
        model_name = str(model or "").strip()
        if not model_name:
            continue
        recommended = recommend_tokens_from_static_map(model_name)
        metadata[model_name] = {
            "contextWindow": None,
            "maxOutputTokens": None,
            "recommendedMaxTokens": recommended,
            "source": "static_mapping",
        }
    return metadata


def _merge_http_headers(
    default_headers: dict[str, str],
    custom_headers: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    merged = {key: value for key, value in default_headers.items() if value}
    if custom_headers:
        merged.update(custom_headers)
    return merged


async def fetch_models_openai_compatible(
    base_url: str,
    api_key: str,
    custom_headers: Optional[dict[str, str]] = None,
) -> tuple[list[str], dict[str, dict[str, Optional[int] | str]]]:
    headers = _merge_http_headers(
        {"Authorization": f"Bearer {api_key}" if api_key else ""},
        custom_headers,
    )
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
        payload = response.json()
        return extract_model_names_from_payload(payload), extract_model_metadata_from_payload(payload)


async def fetch_models_anthropic(
    base_url: str,
    api_key: str,
    custom_headers: Optional[dict[str, str]] = None,
) -> tuple[list[str], dict[str, dict[str, Optional[int] | str]]]:
    headers = _merge_http_headers(
        {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        custom_headers,
    )
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
        payload = response.json()
        return extract_model_names_from_payload(payload), extract_model_metadata_from_payload(payload)


async def fetch_models_azure_openai(
    base_url: str,
    api_key: str,
    custom_headers: Optional[dict[str, str]] = None,
) -> tuple[list[str], dict[str, dict[str, Optional[int] | str]]]:
    api_version = "2024-10-21"
    clean_base = base_url.rstrip("/")
    attempt_urls = [
        f"{clean_base}/models?api-version={api_version}",
        f"{clean_base}/openai/models?api-version={api_version}",
    ]
    unique_attempt_urls = list(dict.fromkeys(attempt_urls))
    headers = _merge_http_headers({"api-key": api_key}, custom_headers)

    async with httpx.AsyncClient(timeout=15) as client:
        last_error: Optional[Exception] = None
        for url in unique_attempt_urls:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
                models = extract_model_names_from_payload(payload)
                if models:
                    return models, extract_model_metadata_from_payload(payload)
            except Exception as exc:
                last_error = exc
                continue
    if last_error:
        raise last_error
    return [], {}
