from typing import Any

from app.services import llm_provider_service
from app.services.llm.config_utils import normalize_llm_base_url


def resolve_effective_llm_api_key(provider_id: str, llm_config: dict[str, Any]) -> str:
    direct_key = str(llm_config.get("llmApiKey") or "").strip()
    if direct_key:
        return direct_key
    provider_key_field = llm_provider_service.provider_api_key_field(
        llm_provider_service.normalize_llm_provider_id(provider_id)
    )
    if not provider_key_field:
        return ""
    return str(llm_config.get(provider_key_field) or "").strip()


def has_saved_llm_connection_config(
    llm_config: dict[str, Any],
    config_keys: tuple[str, ...],
) -> bool:
    for key in config_keys:
        if str(llm_config.get(key) or "").strip():
            return True
    return False


def build_llm_quick_config_snapshot(llm_config: dict[str, Any]) -> dict[str, str]:
    provider = llm_provider_service.normalize_llm_provider_id(llm_config.get("llmProvider"))
    base_url = normalize_llm_base_url(
        llm_config.get("llmBaseUrl") or llm_config.get("ollamaBaseUrl")
    )
    return {
        "provider": provider,
        "model": str(llm_config.get("llmModel") or "").strip(),
        "baseUrl": base_url,
        "apiKey": resolve_effective_llm_api_key(provider, llm_config),
    }


def collect_preflight_missing_fields(snapshot: Any) -> list[str]:
    if isinstance(snapshot, dict):
        provider = str(snapshot.get("provider") or "").strip()
        model = str(snapshot.get("model") or "").strip()
        base_url = str(snapshot.get("baseUrl") or "").strip()
        api_key = str(snapshot.get("apiKey") or "").strip()
    else:
        provider = str(getattr(snapshot, "provider", "") or "").strip()
        model = str(getattr(snapshot, "model", "") or "").strip()
        base_url = str(getattr(snapshot, "baseUrl", "") or "").strip()
        api_key = str(getattr(snapshot, "apiKey", "") or "").strip()

    missing_fields: list[str] = []
    if not model:
        missing_fields.append("llmModel")
    if not base_url:
        missing_fields.append("llmBaseUrl")
    if provider != "ollama" and not api_key:
        missing_fields.append("llmApiKey")
    return missing_fields


def format_missing_fields_message(missing_fields: list[str]) -> str:
    field_label_map = {
        "llmModel": "模型（llmModel）",
        "llmBaseUrl": "Base URL（llmBaseUrl）",
        "llmApiKey": "API Key（llmApiKey）",
    }
    return "、".join(
        field_label_map[field]
        for field in missing_fields
        if field in field_label_map
    )
