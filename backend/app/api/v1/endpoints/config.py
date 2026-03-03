"""
用户配置API端点
"""

import asyncio
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, ConfigDict, Field
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
import zipfile
import httpx
import uuid
import base64

from app.api import deps
from app.db.session import get_db
from app.models.user_config import UserConfig
from app.models.user import User
from app.models.project import Project
from app.core.config import settings
from app.core.encryption import encrypt_sensitive_data, decrypt_sensitive_data
from app.services.agent.mcp.catalog import build_mcp_catalog
from app.services.agent.mcp.protocol_verify import (
    normalize_listed_tools,
    run_protocol_verification,
)
from app.services.llm.factory import LLMFactory
from app.services.llm.types import DEFAULT_BASE_URLS, LLMProvider
from app.services.zip_storage import load_project_zip

router = APIRouter()

# 需要加密的敏感字段列表
SENSITIVE_LLM_FIELDS = [
    'llmApiKey', 'geminiApiKey', 'openaiApiKey', 'claudeApiKey',
    'qwenApiKey', 'deepseekApiKey', 'zhipuApiKey', 'moonshotApiKey',
    'baiduApiKey', 'minimaxApiKey', 'doubaoApiKey'
]
SENSITIVE_OTHER_FIELDS = ['githubToken', 'gitlabToken']

# LLM provider aliases for backward compatibility and new UI labels.
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
    "openai": {
        "name": "OpenAI (兼容)",
        "description": "OpenAI 官方及 OpenAI 兼容接口。",
        "defaultBaseUrl": "https://api.openai.com/v1",
        "fetchStyle": "openai_compatible",
    },
    "openrouter": {
        "name": "OpenRouter",
        "description": "OpenRouter 聚合网关（OpenAI 兼容）。",
        "defaultBaseUrl": "https://openrouter.ai/api/v1",
        "fetchStyle": "openai_compatible",
    },
    "anthropic": {
        "name": "Anthropic",
        "description": "Anthropic Claude 官方接口。",
        "defaultBaseUrl": "https://api.anthropic.com/v1",
        "fetchStyle": "anthropic",
    },
    "azure_openai": {
        "name": "Azure OpenAI",
        "description": "Azure 托管 OpenAI 接口。",
        "defaultBaseUrl": "https://{resource}.openai.azure.com/openai/v1",
        "fetchStyle": "azure_openai",
    },
    "custom": {
        "name": "Custom",
        "description": "自定义模型网关（OpenAI 兼容）。",
        "defaultBaseUrl": "",
        "requiresApiKey": True,
        "fetchStyle": "openai_compatible",
    },
}


def _normalize_llm_provider_id(provider: Any) -> str:
    normalized = str(provider or "").strip().lower()
    if not normalized:
        return ""
    return LLM_PROVIDER_ALIASES.get(normalized, normalized)


def _resolve_llm_runtime_provider(provider: Any) -> tuple[str, Optional[LLMProvider]]:
    provider_id = _normalize_llm_provider_id(provider)
    return provider_id, LLM_PROVIDER_RUNTIME_MAP.get(provider_id)


def _get_provider_default_model(provider_id: str, runtime_provider: Optional[LLMProvider]) -> str:
    if not runtime_provider:
        return ""
    return LLMFactory.get_default_model(runtime_provider)


def _get_provider_default_base_url(provider_id: str, runtime_provider: Optional[LLMProvider]) -> str:
    override = LLM_PROVIDER_META_OVERRIDES.get(provider_id, {}).get("defaultBaseUrl")
    if isinstance(override, str):
        return override
    if not runtime_provider:
        return ""
    return DEFAULT_BASE_URLS.get(runtime_provider, "")


def _get_provider_static_models(provider_id: str, runtime_provider: Optional[LLMProvider]) -> list[str]:
    if not runtime_provider:
        return []
    return LLMFactory.get_available_models(runtime_provider)


def _build_llm_provider_catalog() -> list[dict[str, Any]]:
    providers: list[dict[str, Any]] = []
    seen: set[str] = set()

    # Preserve existing providers from LLMFactory.
    for provider in LLMFactory.get_supported_providers():
        provider_id = _normalize_llm_provider_id(provider.value)
        if not provider_id or provider_id in seen:
            continue
        seen.add(provider_id)
        runtime_provider = LLM_PROVIDER_RUNTIME_MAP.get(provider_id)
        models = _get_provider_static_models(provider_id, runtime_provider)
        default_model = _get_provider_default_model(provider_id, runtime_provider)
        override = LLM_PROVIDER_META_OVERRIDES.get(provider_id, {})
        requires_api_key = (
            bool(override["requiresApiKey"])
            if "requiresApiKey" in override
            else runtime_provider != LLMProvider.OLLAMA
        )
        providers.append(
            {
                "id": provider_id,
                "name": override.get("name", provider_id.upper()),
                "description": override.get("description", f"{provider_id} 模型服务"),
                "defaultModel": default_model,
                "models": models,
                "defaultBaseUrl": _get_provider_default_base_url(provider_id, runtime_provider),
                "requiresApiKey": requires_api_key,
                "supportsModelFetch": True,
                "fetchStyle": override.get("fetchStyle", "openai_compatible"),
            }
        )

    # Add extra OpenAI-compatible providers for UI.
    for provider_id in ("openrouter", "azure_openai", "custom"):
        if provider_id in seen:
            continue
        runtime_provider = LLM_PROVIDER_RUNTIME_MAP.get(provider_id)
        models = _get_provider_static_models(provider_id, runtime_provider)
        default_model = _get_provider_default_model(provider_id, runtime_provider)
        override = LLM_PROVIDER_META_OVERRIDES.get(provider_id, {})
        providers.append(
            {
                "id": provider_id,
                "name": override.get("name", provider_id.upper()),
                "description": override.get("description", f"{provider_id} 模型服务"),
                "defaultModel": default_model,
                "models": models,
                "defaultBaseUrl": _get_provider_default_base_url(provider_id, runtime_provider),
                "requiresApiKey": bool(override.get("requiresApiKey", True)),
                "supportsModelFetch": True,
                "fetchStyle": override.get("fetchStyle", "openai_compatible"),
            }
        )

    preferred_order = {
        "openai": 0,
        "openrouter": 1,
        "anthropic": 2,
        "azure_openai": 3,
        "custom": 4,
    }
    providers.sort(key=lambda item: (preferred_order.get(item["id"], 100), item["id"]))
    return providers


def _extract_model_names_from_payload(payload: Any) -> list[str]:
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
                candidates.extend(_extract_model_names_from_payload(value))

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


def _recommend_tokens_from_static_map(model_name: str) -> Optional[int]:
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


def _extract_model_metadata_from_payload(payload: Any) -> dict[str, dict[str, Optional[int] | str]]:
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
            else _recommend_tokens_from_static_map(model_id)
        )
        source = "online_metadata" if max_output_tokens is not None else "static_mapping"
        metadata[model_id] = {
            "contextWindow": context_window,
            "maxOutputTokens": max_output_tokens,
            "recommendedMaxTokens": recommended,
            "source": source,
        }
    return metadata


def _build_static_model_metadata(models: list[str]) -> dict[str, dict[str, Optional[int] | str]]:
    metadata: dict[str, dict[str, Optional[int] | str]] = {}
    for model in models:
        model_name = str(model or "").strip()
        if not model_name:
            continue
        recommended = _recommend_tokens_from_static_map(model_name)
        metadata[model_name] = {
            "contextWindow": None,
            "maxOutputTokens": None,
            "recommendedMaxTokens": recommended,
            "source": "static_mapping",
        }
    return metadata


async def _fetch_models_openai_compatible(
    base_url: str,
    api_key: str,
) -> tuple[list[str], dict[str, dict[str, Optional[int] | str]]]:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
        payload = response.json()
        return _extract_model_names_from_payload(payload), _extract_model_metadata_from_payload(payload)


async def _fetch_models_anthropic(
    base_url: str,
    api_key: str,
) -> tuple[list[str], dict[str, dict[str, Optional[int] | str]]]:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
        payload = response.json()
        return _extract_model_names_from_payload(payload), _extract_model_metadata_from_payload(payload)


async def _fetch_models_azure_openai(
    base_url: str,
    api_key: str,
) -> tuple[list[str], dict[str, dict[str, Optional[int] | str]]]:
    api_version = "2024-10-21"
    clean_base = base_url.rstrip("/")
    attempt_urls = [
        f"{clean_base}/models?api-version={api_version}",
        f"{clean_base}/openai/models?api-version={api_version}",
    ]
    unique_attempt_urls = list(dict.fromkeys(attempt_urls))
    headers = {"api-key": api_key}

    async with httpx.AsyncClient(timeout=15) as client:
        last_error: Optional[Exception] = None
        for url in unique_attempt_urls:
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                payload = response.json()
                models = _extract_model_names_from_payload(payload)
                if models:
                    return models, _extract_model_metadata_from_payload(payload)
            except Exception as exc:
                last_error = exc
                continue
    if last_error:
        raise last_error
    return [], {}

_VALID_MCP_RUNTIME_MODES = {
    "backend_only",
    "sandbox_only",
    "prefer_backend",
    "prefer_sandbox",
    "backend_then_sandbox",
    "sandbox_then_backend",
}


def _default_mcp_write_policy() -> dict:
    hard_limit = max(1, int(getattr(settings, "MCP_WRITE_HARD_LIMIT", 50)))
    default_limit = int(
        getattr(settings, "MCP_DEFAULT_MAX_WRITABLE_FILES_PER_TASK", hard_limit)
    )
    default_limit = max(1, min(default_limit, hard_limit))
    return {
        "all_agents_writable": bool(getattr(settings, "MCP_ALL_AGENTS_WRITABLE", True)),
        "max_writable_files_per_task": default_limit,
        "require_evidence_binding": bool(
            getattr(settings, "MCP_REQUIRE_EVIDENCE_BINDING", True)
        ),
        "forbid_project_wide_writes": bool(
            getattr(settings, "MCP_FORBID_PROJECT_WIDE_WRITES", True)
        ),
    }


def _default_mcp_runtime_policy() -> dict:
    def _entry(
        *,
        runtime_mode: str,
        backend_enabled: bool,
        sandbox_enabled: bool,
    ) -> dict:
        return {
            "runtime_mode": runtime_mode,
            "backend_enabled": bool(backend_enabled),
            "sandbox_enabled": bool(sandbox_enabled),
        }

    return {
        "default_mode": str(
            getattr(settings, "MCP_RUNTIME_MODE_DEFAULT", "backend_then_sandbox")
            or "backend_then_sandbox"
        ),
        "filesystem": _entry(
            runtime_mode=str(getattr(settings, "MCP_FILESYSTEM_RUNTIME_MODE", "backend_then_sandbox")),
            backend_enabled=bool(getattr(settings, "MCP_FILESYSTEM_ENABLED", False)),
            sandbox_enabled=bool(getattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", False)),
        ),
        "code_index": _entry(
            runtime_mode=str(getattr(settings, "MCP_CODE_INDEX_RUNTIME_MODE", "backend_then_sandbox")),
            backend_enabled=bool(getattr(settings, "MCP_CODE_INDEX_ENABLED", False)),
            sandbox_enabled=bool(getattr(settings, "MCP_CODE_INDEX_SANDBOX_ENABLED", False)),
        ),
        "sequentialthinking": _entry(
            runtime_mode=str(
                getattr(settings, "MCP_SEQUENTIAL_THINKING_RUNTIME_MODE", "backend_then_sandbox")
            ),
            backend_enabled=bool(getattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", False)),
            sandbox_enabled=bool(getattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", False)),
        ),
    }


def _sanitize_runtime_mode(raw_mode: Any, default_mode: str) -> str:
    mode = str(raw_mode or "").strip().lower()
    if mode in _VALID_MCP_RUNTIME_MODES:
        return mode
    fallback = str(default_mode or "").strip().lower()
    if fallback in _VALID_MCP_RUNTIME_MODES:
        return fallback
    return "backend_then_sandbox"


def _sanitize_mcp_runtime_policy(raw_policy: Any) -> dict:
    default_policy = _default_mcp_runtime_policy()
    candidate = raw_policy if isinstance(raw_policy, dict) else {}
    default_mode = _sanitize_runtime_mode(
        candidate.get("default_mode"),
        default_policy.get("default_mode", "backend_then_sandbox"),
    )

    sanitized: dict = {"default_mode": default_mode}
    for mcp_name, mcp_default in default_policy.items():
        if mcp_name == "default_mode":
            continue
        custom = candidate.get(mcp_name) if isinstance(candidate.get(mcp_name), dict) else {}
        sanitized[mcp_name] = {
            "runtime_mode": _sanitize_runtime_mode(
                custom.get("runtime_mode"),
                mcp_default.get("runtime_mode", default_mode),
            ),
            "backend_enabled": bool(
                custom.get("backend_enabled", mcp_default.get("backend_enabled", False))
            ),
            "sandbox_enabled": bool(
                custom.get("sandbox_enabled", mcp_default.get("sandbox_enabled", False))
            ),
        }

    filesystem_policy = sanitized.get("filesystem")
    if isinstance(filesystem_policy, dict):
        filesystem_policy["runtime_mode"] = "sandbox_only"
        filesystem_policy["backend_enabled"] = False
        filesystem_policy["sandbox_enabled"] = True
    return sanitized


def _build_mcp_runtime_persistence() -> dict:
    return {
        "backend_data_dir": "/app/data/mcp",
        "sandbox_data_dir": "/tmp/deepaudit/mcp-cache",
        "qmd_data_dir": str(getattr(settings, "QMD_DATA_DIR", "./data/qmd") or "./data/qmd"),
        "xdg_config_home": str(
            getattr(settings, "XDG_CONFIG_HOME", "/app/data/mcp/xdg-config")
            or "/app/data/mcp/xdg-config"
        ),
        "daemon_log_dir": str(
            getattr(settings, "MCP_DAEMON_LOG_DIR", "/tmp/deepaudit/mcp-daemons")
            or "/tmp/deepaudit/mcp-daemons"
        ),
    }


def _build_skill_availability(catalog: list[dict]) -> dict:
    availability: dict[str, dict] = {}
    for item in catalog:
        if not isinstance(item, dict):
            continue
        source_type = str(item.get("type") or "").strip().lower()
        enabled = bool(item.get("enabled"))
        startup_ready = bool(item.get("startup_ready", True))
        runtime_ready = enabled and startup_ready
        reason = str(item.get("startup_error") or "").strip() or (
            "ready" if runtime_ready else "mcp_not_ready"
        )
        source = "mcp" if source_type == "mcp-server" else "hybrid"
        for skill_name in item.get("includedSkills") or []:
            skill_key = str(skill_name or "").strip()
            if not skill_key:
                continue
            availability[skill_key] = {
                "enabled": runtime_ready,
                "startup_ready": startup_ready,
                "runtime_ready": runtime_ready,
                "reason": reason,
                "source": source,
            }

    # Local fallback skills should remain available regardless of MCP readiness.
    for local_skill in ("think", "reflect", "read_file", "search_code", "list_files"):
        availability.setdefault(
            local_skill,
            {
                "enabled": True,
                "startup_ready": True,
                "runtime_ready": True,
                "reason": "local_tool",
                "source": "local",
            },
        )
    return availability


def _sanitize_mcp_write_policy(raw_policy: Any) -> dict:
    default_policy = _default_mcp_write_policy()
    candidate = raw_policy if isinstance(raw_policy, dict) else {}
    hard_limit = max(1, int(getattr(settings, "MCP_WRITE_HARD_LIMIT", 50)))

    raw_max = candidate.get(
        "max_writable_files_per_task",
        default_policy["max_writable_files_per_task"],
    )
    try:
        max_value = int(raw_max)
    except Exception:
        max_value = int(default_policy["max_writable_files_per_task"])
    max_value = max(1, min(max_value, hard_limit))

    return {
        # Hard lock: all agents keep write entrypoint enabled.
        "all_agents_writable": True,
        "max_writable_files_per_task": max_value,
        "require_evidence_binding": bool(
            candidate.get(
                "require_evidence_binding",
                default_policy["require_evidence_binding"],
            )
        ),
        # Hard lock: project-wide writes are permanently forbidden.
        "forbid_project_wide_writes": True,
    }


def _sanitize_mcp_config(raw_mcp_config: Any) -> dict:
    candidate = raw_mcp_config if isinstance(raw_mcp_config, dict) else {}
    enabled = bool(candidate.get("enabled", getattr(settings, "MCP_ENABLED", True)))
    runtime_policy = _sanitize_mcp_runtime_policy(candidate.get("runtimePolicy"))
    catalog = build_mcp_catalog(
        mcp_enabled=enabled,
        runtime_policy=runtime_policy,
    )
    return {
        "enabled": enabled,
        "preferMcp": bool(
            candidate.get("preferMcp", getattr(settings, "MCP_PREFER", True))
        ),
        "writePolicy": _sanitize_mcp_write_policy(candidate.get("writePolicy")),
        "runtimePolicy": runtime_policy,
        "runtimePersistence": _build_mcp_runtime_persistence(),
        # Read-only catalog: always generated by backend.
        "catalog": catalog,
        "skillAvailability": _build_skill_availability(catalog),
    }


def _sanitize_other_config(raw_other_config: Any) -> dict:
    candidate = dict(raw_other_config) if isinstance(raw_other_config, dict) else {}
    candidate["mcpConfig"] = _sanitize_mcp_config(candidate.get("mcpConfig"))
    return candidate


_VERIFY_DEFAULT_PROJECT_NAME = "libplist"
_VERIFY_SUPPORTED_MCP_IDS = {
    "filesystem",
    "code_index",
    "sequentialthinking",
}
_MCP_INTERNAL_TOOLS = {
    "set_project_path",
    "configure_file_watcher",
    "refresh_index",
    "build_deep_index",
}


def _normalize_extracted_project_root(base_path: str) -> str:
    candidates = [
        item
        for item in os.listdir(base_path)
        if not str(item).startswith("__") and not str(item).startswith(".")
    ]
    if len(candidates) != 1:
        return base_path
    nested = os.path.join(base_path, candidates[0])
    if os.path.isdir(nested):
        return nested
    return base_path


def _is_mcp_infra_failure(*, handled: bool, error_text: str, metadata: dict[str, Any]) -> bool:
    normalized_error = str(error_text or "").strip()
    skip_reason = str(metadata.get("mcp_skip_reason") or "").strip()
    return (
        not bool(handled)
        or normalized_error.startswith("mcp_call_failed:")
        or normalized_error.startswith("mcp_adapter_unavailable:")
        or skip_reason
        in {
            "adapter_unavailable",
            "adapter_disabled_after_failures",
            "domain_adapter_missing",
            "command_not_found",
        }
    )


def _prepare_code_probe_file(project_root: str) -> dict[str, Any]:
    probe_rel_path = "tmp/.mcp_verify_code_probe.c"
    probe_abs_path = os.path.normpath(os.path.join(project_root, probe_rel_path))
    if not probe_abs_path.startswith(os.path.normpath(project_root)):
        raise RuntimeError("code_probe_outside_project_root")
    os.makedirs(os.path.dirname(probe_abs_path), exist_ok=True)
    probe_content = (
        "#include <stdio.h>\n"
        "int mcp_probe_sum(int a, int b) {\n"
        "    return a + b;\n"
        "}\n"
        "int mcp_probe_main(void) {\n"
        "    return mcp_probe_sum(1, 2);\n"
        "}\n"
    )
    with open(probe_abs_path, "w", encoding="utf-8") as handle:
        handle.write(probe_content)
    return {
        "file_path": probe_rel_path,
        "function_name": "mcp_probe_sum",
        "line_start": 2,
    }



async def _resolve_verify_project(
    *,
    db: AsyncSession,
    current_user: User,
) -> tuple[Project, str, bool]:
    preferred_stmt = (
        select(Project)
        .where(
            Project.owner_id == current_user.id,
            Project.is_active == True,
            Project.source_type == "zip",
            Project.name == _VERIFY_DEFAULT_PROJECT_NAME,
        )
        .order_by(Project.created_at.desc())
    )
    preferred_result = await db.execute(preferred_stmt)
    preferred_candidates = list(preferred_result.scalars().all())

    fallback_used = False
    selected_project: Optional[Project] = None
    selected_zip_path: Optional[str] = None

    async def _first_usable_zip(projects: list[Project]) -> tuple[Optional[Project], Optional[str]]:
        for project in projects:
            zip_path = await load_project_zip(project.id)
            if not zip_path or not os.path.exists(zip_path):
                continue
            try:
                with zipfile.ZipFile(zip_path, "r") as zip_ref:
                    if not zip_ref.namelist():
                        continue
                return project, zip_path
            except Exception:
                continue
        return None, None

    selected_project, selected_zip_path = await _first_usable_zip(preferred_candidates)

    if not selected_project or not selected_zip_path:
        fallback_stmt = (
            select(Project)
            .where(
                Project.owner_id == current_user.id,
                Project.is_active == True,
                Project.source_type == "zip",
            )
            .order_by(Project.created_at.desc())
        )
        fallback_result = await db.execute(fallback_stmt)
        fallback_candidates = [
            project
            for project in fallback_result.scalars().all()
            if str(project.name or "").strip() != _VERIFY_DEFAULT_PROJECT_NAME
        ]
        selected_project, selected_zip_path = await _first_usable_zip(fallback_candidates)
        fallback_used = bool(selected_project and selected_zip_path)

    if not selected_project or not selected_zip_path:
        raise HTTPException(
            status_code=400,
            detail="未找到可用于 MCP 验证的 ZIP 项目，请先上传 ZIP 项目或修复默认 libplist 资源。",
        )

    return selected_project, selected_zip_path, fallback_used


def encrypt_config(config: dict, sensitive_fields: list) -> dict:
    """加密配置中的敏感字段"""
    encrypted = config.copy()
    for field in sensitive_fields:
        if field in encrypted and encrypted[field]:
            encrypted[field] = encrypt_sensitive_data(encrypted[field])
    return encrypted


def decrypt_config(config: dict, sensitive_fields: list) -> dict:
    """解密配置中的敏感字段"""
    decrypted = config.copy()
    for field in sensitive_fields:
        if field in decrypted and decrypted[field]:
            decrypted[field] = decrypt_sensitive_data(decrypted[field])
    return decrypted


class LLMConfigSchema(BaseModel):
    """LLM配置Schema"""
    llmProvider: Optional[str] = None
    llmApiKey: Optional[str] = None
    llmModel: Optional[str] = None
    llmBaseUrl: Optional[str] = None
    llmTimeout: Optional[int] = None
    llmTemperature: Optional[float] = None
    llmMaxTokens: Optional[int] = None
    llmCustomHeaders: Optional[str] = None

    # Agent超时配置
    llmFirstTokenTimeout: Optional[int] = None  # 首Token超时（秒）
    llmStreamTimeout: Optional[int] = None  # 流式超时（秒）
    agentTimeout: Optional[int] = None  # Agent总超时（秒）
    subAgentTimeout: Optional[int] = None  # 子Agent超时（秒）
    toolTimeout: Optional[int] = None  # 工具执行超时（秒）

    # 平台专用配置
    geminiApiKey: Optional[str] = None
    openaiApiKey: Optional[str] = None
    claudeApiKey: Optional[str] = None
    qwenApiKey: Optional[str] = None
    deepseekApiKey: Optional[str] = None
    zhipuApiKey: Optional[str] = None
    moonshotApiKey: Optional[str] = None
    baiduApiKey: Optional[str] = None
    minimaxApiKey: Optional[str] = None
    doubaoApiKey: Optional[str] = None
    ollamaBaseUrl: Optional[str] = None


class OtherConfigSchema(BaseModel):
    """其他配置Schema"""
    githubToken: Optional[str] = None
    gitlabToken: Optional[str] = None
    maxAnalyzeFiles: Optional[int] = None
    llmConcurrency: Optional[int] = None
    llmGapMs: Optional[int] = None
    outputLanguage: Optional[str] = None
    mcpConfig: Optional[dict] = None


class UserConfigRequest(BaseModel):
    """用户配置请求"""
    llmConfig: Optional[LLMConfigSchema] = None
    otherConfig: Optional[OtherConfigSchema] = None


class UserConfigResponse(BaseModel):
    """用户配置响应"""
    id: str
    user_id: str
    llmConfig: dict
    otherConfig: dict
    created_at: str
    updated_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MCPVerifyRequest(BaseModel):
    mcp_id: str


class MCPVerifyCheck(BaseModel):
    step: str
    action: str
    success: bool
    tool: Optional[str] = None
    runtime_domain: Optional[str] = None
    duration_ms: int
    error: Optional[str] = None


class MCPVerifyResponse(BaseModel):
    success: bool
    mcp_id: str
    checks: list[MCPVerifyCheck]
    verification_tools: list[str]
    project_context: dict[str, Any]
    discovered_tools: list[dict[str, Any]]
    protocol_summary: dict[str, Any]


class MCPToolsListRequest(BaseModel):
    mcp_ids: Optional[list[str]] = None
    include_internal: bool = False


class MCPToolsListTool(BaseModel):
    name: str
    description: str
    inputSchema: dict[str, Any]


class MCPToolsListItem(BaseModel):
    mcp_id: str
    success: bool
    tools: list[MCPToolsListTool]
    error: Optional[str] = None
    runtime_domain: Optional[str] = None
    listed_count: int
    visible_count: int


class MCPToolsListResponse(BaseModel):
    results: list[MCPToolsListItem]


class MCPToolsCallRequest(BaseModel):
    mcp_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    include_internal: bool = False


class MCPToolsCallResponse(BaseModel):
    success: bool
    handled: bool
    mcp_id: str
    tool_name: str
    data: Optional[str] = None
    error: Optional[str] = None
    runtime_domain: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class QmdCliCheckResult(BaseModel):
    name: str
    success: bool
    command: list[str]
    exit_code: Optional[int] = None
    duration_ms: int
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None


class QmdCliTestResponse(BaseModel):
    success: bool
    checks: list[QmdCliCheckResult]
    command_base: list[str]


def _resolve_target_mcp_ids(
    requested_ids: Optional[list[str]],
    *,
    mcp_catalog: Any,
) -> list[str]:
    if isinstance(requested_ids, list) and requested_ids:
        return [
            mcp_id
            for mcp_id in dict.fromkeys(
                str(item or "").strip().lower() for item in requested_ids
            )
            if mcp_id
        ]

    target_ids: list[str] = []
    for item in mcp_catalog if isinstance(mcp_catalog, list) else []:
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "mcp-server":
            continue
        mcp_id = str(item.get("id") or "").strip().lower()
        if mcp_id:
            target_ids.append(mcp_id)
    return list(dict.fromkeys(target_ids))


def _filter_internal_tools(
    tools: list[dict[str, Any]],
    *,
    include_internal: bool,
) -> list[dict[str, Any]]:
    if include_internal:
        return list(tools)
    visible: list[dict[str, Any]] = []
    for tool in tools:
        name = str(tool.get("name") or "").strip()
        if not name or name in _MCP_INTERNAL_TOOLS:
            continue
        visible.append(tool)
    return visible


def _split_qmd_cli_command(raw_command: Any) -> list[str]:
    fallback = "qmd"
    text = str(raw_command or "").strip() or fallback
    try:
        parts = shlex.split(text)
    except Exception:
        parts = []
    if not parts:
        parts = shlex.split(fallback)
    return [str(item) for item in parts if str(item).strip()]


def _truncate_output_text(raw: Any, limit: int = 2000) -> str:
    text = str(raw or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...[truncated]"


def _run_qmd_cli_check(
    *,
    name: str,
    command: list[str],
    timeout_seconds: int,
    cwd: Optional[str] = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd or None,
            text=True,
            capture_output=True,
            timeout=max(5, int(timeout_seconds)),
            check=False,
            shell=False,
        )
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        return {
            "name": name,
            "success": completed.returncode == 0,
            "command": command,
            "exit_code": int(completed.returncode),
            "duration_ms": duration_ms,
            "stdout": _truncate_output_text(completed.stdout),
            "stderr": _truncate_output_text(completed.stderr),
            "error": None,
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        return {
            "name": name,
            "success": False,
            "command": command,
            "exit_code": None,
            "duration_ms": duration_ms,
            "stdout": _truncate_output_text(exc.stdout),
            "stderr": _truncate_output_text(exc.stderr),
            "error": f"timeout:{max(5, int(timeout_seconds))}s",
        }
    except FileNotFoundError:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        return {
            "name": name,
            "success": False,
            "command": command,
            "exit_code": None,
            "duration_ms": duration_ms,
            "stdout": "",
            "stderr": "",
            "error": "command_not_found",
        }
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        return {
            "name": name,
            "success": False,
            "command": command,
            "exit_code": None,
            "duration_ms": duration_ms,
            "stdout": "",
            "stderr": "",
            "error": f"execution_failed:{exc.__class__.__name__}:{exc}",
        }


def get_default_config() -> dict:
    """获取系统默认配置"""
    return {
        "llmConfig": {
            "llmProvider": settings.LLM_PROVIDER,
            "llmApiKey": "",
            "llmModel": settings.LLM_MODEL or "",
            "llmBaseUrl": settings.LLM_BASE_URL or "",
            "llmTimeout": settings.LLM_TIMEOUT * 1000,  # 转换为毫秒
            "llmTemperature": settings.LLM_TEMPERATURE,
            "llmMaxTokens": settings.LLM_MAX_TOKENS,
            "llmCustomHeaders": "",
            # Agent超时配置（秒）
            "llmFirstTokenTimeout": getattr(settings, 'LLM_FIRST_TOKEN_TIMEOUT', 90),
            "llmStreamTimeout": getattr(settings, 'LLM_STREAM_TIMEOUT', 60),
            "agentTimeout": settings.AGENT_TIMEOUT_SECONDS,
            "subAgentTimeout": getattr(settings, 'SUB_AGENT_TIMEOUT_SECONDS', 600),
            "toolTimeout": getattr(settings, 'TOOL_TIMEOUT_SECONDS', 60),
            # 平台专用配置
            "geminiApiKey": settings.GEMINI_API_KEY or "",
            "openaiApiKey": settings.OPENAI_API_KEY or "",
            "claudeApiKey": settings.CLAUDE_API_KEY or "",
            "qwenApiKey": settings.QWEN_API_KEY or "",
            "deepseekApiKey": settings.DEEPSEEK_API_KEY or "",
            "zhipuApiKey": settings.ZHIPU_API_KEY or "",
            "moonshotApiKey": settings.MOONSHOT_API_KEY or "",
            "baiduApiKey": settings.BAIDU_API_KEY or "",
            "minimaxApiKey": settings.MINIMAX_API_KEY or "",
            "doubaoApiKey": settings.DOUBAO_API_KEY or "",
            "ollamaBaseUrl": settings.OLLAMA_BASE_URL or "http://localhost:11434/v1",
        },
        "otherConfig": {
            "githubToken": settings.GITHUB_TOKEN or "",
            "gitlabToken": settings.GITLAB_TOKEN or "",
            "maxAnalyzeFiles": settings.MAX_ANALYZE_FILES,
            "llmConcurrency": settings.LLM_CONCURRENCY,
            "llmGapMs": settings.LLM_GAP_MS,
            "outputLanguage": settings.OUTPUT_LANGUAGE,
            "mcpConfig": _sanitize_mcp_config({}),
        }
    }


@router.get("/defaults")
async def get_default_config_endpoint() -> Any:
    """获取系统默认配置（无需认证）"""
    return get_default_config()


@router.get("/me", response_model=UserConfigResponse)
async def get_my_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """获取当前用户的配置（合并用户配置和系统默认配置）"""
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    
    # 获取系统默认配置
    default_config = get_default_config()
    
    if not config:
        print(f"[Config] 用户 {current_user.id} 没有保存的配置，返回默认配置")
        # 返回系统默认配置
        return UserConfigResponse(
            id="",
            user_id=current_user.id,
            llmConfig=default_config["llmConfig"],
            otherConfig=default_config["otherConfig"],
            created_at="",
        )
    
    # 合并用户配置和默认配置（用户配置优先）
    user_llm_config = json.loads(config.llm_config) if config.llm_config else {}
    user_other_config = json.loads(config.other_config) if config.other_config else {}
    
    # 解密敏感字段
    user_llm_config = decrypt_config(user_llm_config, SENSITIVE_LLM_FIELDS)
    user_other_config = decrypt_config(user_other_config, SENSITIVE_OTHER_FIELDS)
    
    print(f"[Config] 用户 {current_user.id} 的保存配置:")
    print(f"  - llmProvider: {user_llm_config.get('llmProvider')}")
    print(f"  - llmApiKey: {'***' + user_llm_config.get('llmApiKey', '')[-4:] if user_llm_config.get('llmApiKey') else '(空)'}")
    print(f"  - llmModel: {user_llm_config.get('llmModel')}")
    
    merged_llm_config = {**default_config["llmConfig"], **user_llm_config}
    merged_other_config = _sanitize_other_config(
        {**default_config["otherConfig"], **user_other_config}
    )
    
    return UserConfigResponse(
        id=config.id,
        user_id=config.user_id,
        llmConfig=merged_llm_config,
        otherConfig=merged_other_config,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


@router.put("/me", response_model=UserConfigResponse)
async def update_my_config(
    config_in: UserConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """更新当前用户的配置"""
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    
    # 准备要保存的配置数据（加密敏感字段）
    llm_data = config_in.llmConfig.dict(exclude_none=True) if config_in.llmConfig else {}
    other_data = config_in.otherConfig.dict(exclude_none=True) if config_in.otherConfig else {}
    if other_data:
        other_data = _sanitize_other_config(other_data)
        if isinstance(other_data.get("mcpConfig"), dict):
            # Prevent frontend overrides for read-only catalog.
            other_data["mcpConfig"].pop("catalog", None)
    
    # 加密敏感字段
    llm_data_encrypted = encrypt_config(llm_data, SENSITIVE_LLM_FIELDS)
    other_data_encrypted = encrypt_config(other_data, SENSITIVE_OTHER_FIELDS)
    
    if not config:
        # 创建新配置
        config = UserConfig(
            user_id=current_user.id,
            llm_config=json.dumps(llm_data_encrypted),
            other_config=json.dumps(other_data_encrypted),
        )
        db.add(config)
    else:
        # 更新现有配置
        if config_in.llmConfig:
            existing_llm = json.loads(config.llm_config) if config.llm_config else {}
            # 先解密现有数据，再合并新数据，最后加密
            existing_llm = decrypt_config(existing_llm, SENSITIVE_LLM_FIELDS)
            existing_llm.update(llm_data)  # 使用未加密的新数据合并
            config.llm_config = json.dumps(encrypt_config(existing_llm, SENSITIVE_LLM_FIELDS))
        
        if config_in.otherConfig:
            existing_other = json.loads(config.other_config) if config.other_config else {}
            # 先解密现有数据，再合并新数据，最后加密
            existing_other = decrypt_config(existing_other, SENSITIVE_OTHER_FIELDS)
            if isinstance(existing_other.get("mcpConfig"), dict):
                existing_other["mcpConfig"].pop("catalog", None)
            existing_other.update(other_data)  # 使用未加密的新数据合并
            existing_other = _sanitize_other_config(existing_other)
            config.other_config = json.dumps(encrypt_config(existing_other, SENSITIVE_OTHER_FIELDS))
    
    await db.commit()
    await db.refresh(config)
    
    # 获取系统默认配置并合并（与 get_my_config 保持一致）
    default_config = get_default_config()
    user_llm_config = json.loads(config.llm_config) if config.llm_config else {}
    user_other_config = json.loads(config.other_config) if config.other_config else {}
    
    # 解密后返回给前端
    user_llm_config = decrypt_config(user_llm_config, SENSITIVE_LLM_FIELDS)
    user_other_config = decrypt_config(user_other_config, SENSITIVE_OTHER_FIELDS)
    
    merged_llm_config = {**default_config["llmConfig"], **user_llm_config}
    merged_other_config = _sanitize_other_config(
        {**default_config["otherConfig"], **user_other_config}
    )
    
    return UserConfigResponse(
        id=config.id,
        user_id=config.user_id,
        llmConfig=merged_llm_config,
        otherConfig=merged_other_config,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


@router.delete("/me")
async def delete_my_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """删除当前用户的配置（恢复为默认）"""
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == current_user.id)
    )
    config = result.scalar_one_or_none()
    
    if config:
        await db.delete(config)
        await db.commit()
    
    return {"message": "配置已删除"}


@router.post("/mcp/verify", response_model=MCPVerifyResponse)
async def verify_mcp_runtime(
    request: MCPVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    mcp_id = str(request.mcp_id or "").strip().lower()
    if mcp_id not in _VERIFY_SUPPORTED_MCP_IDS:
        raise HTTPException(status_code=400, detail=f"不支持的 MCP: {request.mcp_id}")

    default_config = get_default_config()
    result = await db.execute(select(UserConfig).where(UserConfig.user_id == current_user.id))
    saved_config = result.scalar_one_or_none()

    user_other_config = {}
    if saved_config and saved_config.other_config:
        user_other_config = decrypt_config(
            json.loads(saved_config.other_config),
            SENSITIVE_OTHER_FIELDS,
        )

    merged_other_config = _sanitize_other_config(
        {**default_config["otherConfig"], **user_other_config}
    )
    effective_user_config = {"otherConfig": merged_other_config}

    project, zip_path, fallback_used = await _resolve_verify_project(
        db=db,
        current_user=current_user,
    )

    extracted_dir = tempfile.mkdtemp(prefix=f"mcp-verify-{mcp_id}-")
    checks: list[MCPVerifyCheck] = []
    project_root = extracted_dir
    try:
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(extracted_dir)
        project_root = _normalize_extracted_project_root(extracted_dir)
        code_probe_context = _prepare_code_probe_file(project_root)
        filesystem_probe_path: Optional[str] = None
        filesystem_media_probe_path: Optional[str] = None
        verify_target_files: list[str] = []
        if mcp_id == "filesystem":
            filesystem_probe_path = f"tmp/.mcp_verify_filesystem_probe_{uuid.uuid4().hex}.txt"
            filesystem_media_probe_path = f"tmp/.mcp_verify_filesystem_probe_{uuid.uuid4().hex}.png"
            verify_target_files = [filesystem_probe_path, filesystem_media_probe_path]
            filesystem_probe_abs = os.path.join(project_root, filesystem_probe_path)
            filesystem_media_probe_abs = os.path.join(project_root, filesystem_media_probe_path)
            os.makedirs(os.path.dirname(filesystem_probe_abs), exist_ok=True)
            with open(filesystem_probe_abs, "w", encoding="utf-8") as handle:
                handle.write("mcp verify filesystem probe\n")
            one_pixel_png = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7+WQ0AAAAASUVORK5CYII="
            )
            with open(filesystem_media_probe_abs, "wb") as handle:
                handle.write(one_pixel_png)

        from app.api.v1.endpoints.agent_tasks import _build_task_mcp_runtime

        runtime = _build_task_mcp_runtime(
            project_root=project_root,
            user_config=effective_user_config,
            target_files=verify_target_files,
            project_id=project.id,
            prefer_stdio_when_http_unavailable=True,
            active_mcp_ids=[mcp_id],
        )
        protocol_result = await run_protocol_verification(
            runtime=runtime,
            mcp_id=mcp_id,
            project_root=project_root,
            filesystem_probe_file=filesystem_probe_path,
            filesystem_media_probe_file=filesystem_media_probe_path,
            code_probe_file=code_probe_context["file_path"],
            code_probe_function=code_probe_context["function_name"],
            code_probe_line=code_probe_context["line_start"],
        )
        checks = [MCPVerifyCheck(**item) for item in protocol_result.get("checks", [])]

        return MCPVerifyResponse(
            success=bool(protocol_result.get("success")),
            mcp_id=mcp_id,
            checks=checks,
            verification_tools=list(protocol_result.get("verification_tools", [])),
            project_context={
                "project_id": project.id,
                "project_name": project.name,
                "source_type": project.source_type,
                "project_root": project_root,
                "fallback_used": fallback_used,
            },
            discovered_tools=list(protocol_result.get("discovered_tools", [])),
            protocol_summary=dict(protocol_result.get("protocol_summary", {})),
        )
    finally:
        shutil.rmtree(extracted_dir, ignore_errors=True)


@router.post("/mcp/tools/list", response_model=MCPToolsListResponse)
async def list_mcp_tools_runtime(
    request: MCPToolsListRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    default_config = get_default_config()
    result = await db.execute(select(UserConfig).where(UserConfig.user_id == current_user.id))
    saved_config = result.scalar_one_or_none()

    user_other_config = {}
    if saved_config and saved_config.other_config:
        user_other_config = decrypt_config(
            json.loads(saved_config.other_config),
            SENSITIVE_OTHER_FIELDS,
        )

    merged_other_config = _sanitize_other_config(
        {**default_config["otherConfig"], **user_other_config}
    )
    effective_user_config = {"otherConfig": merged_other_config}
    mcp_config = (
        merged_other_config.get("mcpConfig")
        if isinstance(merged_other_config.get("mcpConfig"), dict)
        else {}
    )
    target_mcp_ids = _resolve_target_mcp_ids(
        request.mcp_ids,
        mcp_catalog=mcp_config.get("catalog"),
    )
    if not target_mcp_ids:
        return MCPToolsListResponse(results=[])

    temp_project_root = tempfile.mkdtemp(prefix="mcp-tools-list-")
    os.makedirs(os.path.join(temp_project_root, "tmp"), exist_ok=True)

    try:
        from app.api.v1.endpoints.agent_tasks import _build_task_mcp_runtime

        runtime = _build_task_mcp_runtime(
            project_root=temp_project_root,
            user_config=effective_user_config,
            target_files=[],
            prefer_stdio_when_http_unavailable=True,
            active_mcp_ids=target_mcp_ids,
        )
        results: list[MCPToolsListItem] = []
        for mcp_id in target_mcp_ids:
            try:
                list_result = await runtime.list_mcp_tools(mcp_id)
            except Exception as exc:
                list_result = {
                    "success": False,
                    "tools": [],
                    "error": f"tools_list_failed:{exc}",
                    "metadata": {},
                }

            normalized_tools = normalize_listed_tools(list_result.get("tools"))
            visible_tools = _filter_internal_tools(
                normalized_tools,
                include_internal=bool(request.include_internal),
            )
            metadata = list_result.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            runtime_domain = str(metadata.get("mcp_runtime_domain") or "").strip() or None
            success = bool(list_result.get("success"))
            error = str(list_result.get("error") or "").strip() or None
            results.append(
                MCPToolsListItem(
                    mcp_id=mcp_id,
                    success=success,
                    tools=[
                        MCPToolsListTool(
                            name=str(tool.get("name") or "").strip(),
                            description=str(tool.get("description") or "").strip(),
                            inputSchema=(
                                dict(tool.get("inputSchema"))
                                if isinstance(tool.get("inputSchema"), dict)
                                else {}
                            ),
                        )
                        for tool in visible_tools
                    ],
                    error=error,
                    runtime_domain=runtime_domain,
                    listed_count=len(normalized_tools),
                    visible_count=len(visible_tools),
                )
            )
        return MCPToolsListResponse(results=results)
    finally:
        shutil.rmtree(temp_project_root, ignore_errors=True)


@router.post("/mcp/tools/call", response_model=MCPToolsCallResponse)
async def call_mcp_tool_runtime(
    request: MCPToolsCallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    default_config = get_default_config()
    result = await db.execute(select(UserConfig).where(UserConfig.user_id == current_user.id))
    saved_config = result.scalar_one_or_none()

    user_other_config = {}
    if saved_config and saved_config.other_config:
        user_other_config = decrypt_config(
            json.loads(saved_config.other_config),
            SENSITIVE_OTHER_FIELDS,
        )

    merged_other_config = _sanitize_other_config(
        {**default_config["otherConfig"], **user_other_config}
    )
    effective_user_config = {"otherConfig": merged_other_config}

    mcp_id = str(request.mcp_id or "").strip().lower()
    tool_name = str(request.tool_name or "").strip()
    if not mcp_id or not tool_name:
        raise HTTPException(status_code=400, detail="mcp_id and tool_name are required")
    if not bool(request.include_internal) and tool_name in _MCP_INTERNAL_TOOLS:
        raise HTTPException(status_code=400, detail=f"internal tool blocked: {tool_name}")

    temp_project_root = tempfile.mkdtemp(prefix="mcp-tools-call-")
    os.makedirs(os.path.join(temp_project_root, "tmp"), exist_ok=True)
    try:
        from app.api.v1.endpoints.agent_tasks import _build_task_mcp_runtime

        runtime = _build_task_mcp_runtime(
            project_root=temp_project_root,
            user_config=effective_user_config,
            target_files=[],
            prefer_stdio_when_http_unavailable=True,
            active_mcp_ids=[mcp_id],
        )
        call_result = await runtime.call_mcp_tool(
            mcp_name=mcp_id,
            tool_name=tool_name,
            arguments=dict(request.arguments or {}),
            agent_name="mcp_tools_call_api",
        )
        metadata = dict(call_result.metadata) if isinstance(call_result.metadata, dict) else {}
        runtime_domain = str(metadata.get("mcp_runtime_domain") or "").strip() or None
        return MCPToolsCallResponse(
            success=bool(call_result.success),
            handled=bool(call_result.handled),
            mcp_id=mcp_id,
            tool_name=tool_name,
            data=str(call_result.data or "") or None,
            error=str(call_result.error or "").strip() or None,
            runtime_domain=runtime_domain,
            metadata=metadata,
        )
    finally:
        shutil.rmtree(temp_project_root, ignore_errors=True)


@router.post("/qmd/cli/test", response_model=QmdCliTestResponse)
async def verify_qmd_cli_runtime(
    _current_user: User = Depends(deps.get_current_user),
) -> Any:
    command_base = _split_qmd_cli_command(getattr(settings, "QMD_CLI_COMMAND", "qmd"))
    timeout_seconds = int(getattr(settings, "QMD_CLI_TIMEOUT_SECONDS", 120) or 120)
    checks_to_run = [
        ("help", [*command_base, "--help"]),
        ("status", [*command_base, "status"]),
        ("collection_list", [*command_base, "collection", "list"]),
    ]
    check_payloads = await asyncio.gather(
        *[
            asyncio.to_thread(
                _run_qmd_cli_check,
                name=check_name,
                command=command_args,
                timeout_seconds=timeout_seconds,
            )
            for check_name, command_args in checks_to_run
        ]
    )
    checks = [QmdCliCheckResult(**item) for item in check_payloads]
    return QmdCliTestResponse(
        success=all(item.success for item in checks),
        checks=checks,
        command_base=command_base,
    )


class LLMTestRequest(BaseModel):
    """LLM测试请求"""
    provider: str
    apiKey: Optional[str] = None
    model: Optional[str] = None
    baseUrl: Optional[str] = None


class LLMTestResponse(BaseModel):
    """LLM测试响应"""
    success: bool
    message: str
    model: Optional[str] = None
    response: Optional[str] = None
    # 调试信息
    debug: Optional[dict] = None


class LLMFetchModelsRequest(BaseModel):
    """按提供商拉取模型列表请求"""
    provider: str
    apiKey: str
    baseUrl: Optional[str] = None


class LLMFetchModelsResponse(BaseModel):
    """按提供商拉取模型列表响应"""
    success: bool
    message: str
    provider: str
    resolvedProvider: str
    models: list[str]
    defaultModel: str
    source: str
    baseUrlUsed: Optional[str] = None
    modelMetadata: Optional[dict[str, dict[str, Optional[int] | str]]] = None
    tokenRecommendationSource: Optional[str] = None


@router.post("/test-llm", response_model=LLMTestResponse)
async def test_llm_connection(
    request: LLMTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """测试LLM连接是否正常"""
    from app.services.llm.factory import NATIVE_ONLY_PROVIDERS
    from app.services.llm.adapters import LiteLLMAdapter, BaiduAdapter, MinimaxAdapter, DoubaoAdapter
    from app.services.llm.types import LLMConfig, LLMProvider, LLMRequest, LLMMessage
    import traceback
    import time

    start_time = time.time()

    # 获取用户保存的配置
    result = await db.execute(
        select(UserConfig).where(UserConfig.user_id == current_user.id)
    )
    user_config_record = result.scalar_one_or_none()

    # 解析用户配置
    saved_llm_config = {}
    saved_other_config = {}
    if user_config_record:
        if user_config_record.llm_config:
            saved_llm_config = decrypt_config(
                json.loads(user_config_record.llm_config),
                SENSITIVE_LLM_FIELDS
            )
        if user_config_record.other_config:
            saved_other_config = decrypt_config(
                json.loads(user_config_record.other_config),
                SENSITIVE_OTHER_FIELDS
            )

    # 从保存的配置中获取参数（用于调试显示）
    saved_timeout_ms = saved_llm_config.get('llmTimeout', settings.LLM_TIMEOUT * 1000)
    saved_temperature = saved_llm_config.get('llmTemperature', settings.LLM_TEMPERATURE)
    saved_max_tokens = saved_llm_config.get('llmMaxTokens', settings.LLM_MAX_TOKENS)
    saved_concurrency = saved_other_config.get('llmConcurrency', settings.LLM_CONCURRENCY)
    saved_gap_ms = saved_other_config.get('llmGapMs', settings.LLM_GAP_MS)
    saved_max_files = saved_other_config.get('maxAnalyzeFiles', settings.MAX_ANALYZE_FILES)
    saved_output_lang = saved_other_config.get('outputLanguage', settings.OUTPUT_LANGUAGE)

    debug_info = {
        "provider_requested": request.provider,
        "model_requested": request.model,
        "base_url_requested": request.baseUrl,
        "api_key_length": len(request.apiKey) if request.apiKey else 0,
        "api_key_prefix": request.apiKey[:8] + "..." if request.apiKey and len(request.apiKey) > 8 else "(empty)",
        # 用户保存的配置参数
        "saved_config": {
            "timeout_ms": saved_timeout_ms,
            "temperature": saved_temperature,
            "max_tokens": saved_max_tokens,
            "concurrency": saved_concurrency,
            "gap_ms": saved_gap_ms,
            "max_analyze_files": saved_max_files,
            "output_language": saved_output_lang,
        },
    }

    try:
        resolved_provider_id, provider = _resolve_llm_runtime_provider(request.provider)
        if not provider:
            debug_info["error_type"] = "unsupported_provider"
            return LLMTestResponse(
                success=False,
                message=f"不支持的LLM提供商: {request.provider}",
                debug=debug_info
            )
        debug_info["provider_resolved"] = resolved_provider_id
        debug_info["provider_runtime"] = provider.value

        model = str(request.model or "").strip()
        base_url = str(request.baseUrl or "").strip()
        api_key = str(request.apiKey or "").strip()

        if not model:
            raise HTTPException(status_code=400, detail="LLM 配置缺失：`model` 必填。")
        if not base_url:
            raise HTTPException(status_code=400, detail="LLM 配置缺失：`baseUrl` 必填。")
        if provider != LLMProvider.OLLAMA and not api_key:
            raise HTTPException(
                status_code=400,
                detail=f"LLM 配置缺失：提供商 `{resolved_provider_id}` 必须提供 `apiKey`。",
            )
        if provider == LLMProvider.OLLAMA and not api_key:
            # 兼容基类 validate_config 的 API Key 必填校验
            api_key = "ollama"

        # 测试时使用用户保存的所有配置参数
        test_timeout = int(saved_timeout_ms / 1000) if saved_timeout_ms else settings.LLM_TIMEOUT
        test_temperature = saved_temperature if saved_temperature is not None else settings.LLM_TEMPERATURE
        test_max_tokens = saved_max_tokens if saved_max_tokens else settings.LLM_MAX_TOKENS

        debug_info["model_used"] = model
        debug_info["base_url_used"] = base_url
        debug_info["is_native_adapter"] = provider in NATIVE_ONLY_PROVIDERS
        debug_info["test_params"] = {
            "timeout": test_timeout,
            "temperature": test_temperature,
            "max_tokens": test_max_tokens,
        }

        print(f"[LLM Test] 开始测试: provider={provider.value}, model={model}, base_url={base_url}, temperature={test_temperature}, timeout={test_timeout}s, max_tokens={test_max_tokens}")

        # 创建配置
        config = LLMConfig(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url or None,
            timeout=test_timeout,
            temperature=test_temperature,
            max_tokens=test_max_tokens,
        )

        # 直接创建新的适配器实例（不使用缓存），确保使用最新的配置
        if provider in NATIVE_ONLY_PROVIDERS:
            native_adapter_map = {
                LLMProvider.BAIDU: BaiduAdapter,
                LLMProvider.MINIMAX: MinimaxAdapter,
                LLMProvider.DOUBAO: DoubaoAdapter,
            }
            adapter = native_adapter_map[provider](config)
            debug_info["adapter_type"] = type(adapter).__name__
        else:
            adapter = LiteLLMAdapter(config)
            debug_info["adapter_type"] = "LiteLLMAdapter"
            # 获取 LiteLLM 实际使用的模型名
            debug_info["litellm_model"] = getattr(adapter, '_get_litellm_model', lambda: model)() if hasattr(adapter, '_get_litellm_model') else model

        test_request = LLMRequest(
            messages=[
                LLMMessage(role="user", content="Say 'Hello' in one word.")
            ],
            temperature=test_temperature,
            max_tokens=test_max_tokens,
        )

        print(f"[LLM Test] 发送测试请求...")
        response = await adapter.complete(test_request)

        elapsed_time = time.time() - start_time
        debug_info["elapsed_time_ms"] = round(elapsed_time * 1000, 2)

        # 验证响应内容
        if not response or not response.content:
            debug_info["error_type"] = "empty_response"
            debug_info["raw_response"] = str(response) if response else None
            print(f"[LLM Test] 空响应: {response}")
            return LLMTestResponse(
                success=False,
                message="LLM 返回空响应，请检查 API Key 和配置",
                debug=debug_info
            )

        debug_info["response_length"] = len(response.content)
        debug_info["usage"] = {
            "prompt_tokens": getattr(response, 'prompt_tokens', None),
            "completion_tokens": getattr(response, 'completion_tokens', None),
            "total_tokens": getattr(response, 'total_tokens', None),
        }

        print(f"[LLM Test] 成功! 响应: {response.content[:50]}... 耗时: {elapsed_time:.2f}s")

        return LLMTestResponse(
            success=True,
            message=f"连接成功 ({elapsed_time:.2f}s)",
            model=model,
            response=response.content[:100] if response.content else None,
            debug=debug_info
        )

    except HTTPException:
        raise
    except Exception as e:
        elapsed_time = time.time() - start_time
        error_msg = str(e)
        error_type = type(e).__name__

        debug_info["elapsed_time_ms"] = round(elapsed_time * 1000, 2)
        debug_info["error_type"] = error_type
        debug_info["error_message"] = error_msg
        debug_info["traceback"] = traceback.format_exc()

        # 提取 LLMError 中的 api_response
        if hasattr(e, 'api_response') and e.api_response:
            debug_info["api_response"] = e.api_response
        if hasattr(e, 'status_code') and e.status_code:
            debug_info["status_code"] = e.status_code

        print(f"[LLM Test] 失败: {error_type}: {error_msg}")
        print(f"[LLM Test] Traceback:\n{traceback.format_exc()}")

        # 提供更友好的错误信息
        friendly_message = error_msg

        # 优先检查余额不足（因为某些 API 用 429 表示余额不足）
        if any(keyword in error_msg for keyword in ["余额不足", "资源包", "充值", "quota", "insufficient", "balance", "402"]):
            friendly_message = "账户余额不足或配额已用尽，请充值后重试"
            debug_info["error_category"] = "insufficient_balance"
        elif "401" in error_msg or "invalid_api_key" in error_msg.lower() or "incorrect api key" in error_msg.lower():
            friendly_message = "API Key 无效或已过期，请检查后重试"
            debug_info["error_category"] = "auth_invalid_key"
        elif "authentication" in error_msg.lower():
            friendly_message = "认证失败，请检查 API Key 是否正确"
            debug_info["error_category"] = "auth_failed"
        elif "timeout" in error_msg.lower():
            friendly_message = "连接超时，请检查网络或 API 地址是否正确"
            debug_info["error_category"] = "timeout"
        elif "connection" in error_msg.lower() or "connect" in error_msg.lower():
            friendly_message = "无法连接到 API 服务，请检查网络或 API 地址"
            debug_info["error_category"] = "connection"
        elif "rate" in error_msg.lower() and "limit" in error_msg.lower():
            friendly_message = "API 请求频率超限，请稍后重试"
            debug_info["error_category"] = "rate_limit"
        elif "model" in error_msg.lower() and ("not found" in error_msg.lower() or "does not exist" in error_msg.lower()):
            friendly_message = f"模型 '{debug_info.get('model_used', 'unknown')}' 不存在或无权访问"
            debug_info["error_category"] = "model_not_found"
        else:
            debug_info["error_category"] = "unknown"

        return LLMTestResponse(
            success=False,
            message=friendly_message,
            debug=debug_info
        )


@router.post("/fetch-llm-models", response_model=LLMFetchModelsResponse)
async def fetch_llm_models(
    request: LLMFetchModelsRequest,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """按当前 provider 拉取模型列表（优先在线，失败回退静态列表）。"""
    _ = current_user  # endpoint requires auth but does not need user data now.

    provider_catalog = _build_llm_provider_catalog()
    provider_map = {item["id"]: item for item in provider_catalog}

    resolved_provider_id, runtime_provider = _resolve_llm_runtime_provider(request.provider)
    provider_info = provider_map.get(resolved_provider_id)
    if not runtime_provider or not provider_info:
        return LLMFetchModelsResponse(
            success=False,
            message=f"不支持的LLM提供商: {request.provider}",
            provider=request.provider,
            resolvedProvider=resolved_provider_id or "",
            models=[],
            defaultModel="",
            source="fallback_static",
            baseUrlUsed=request.baseUrl,
            modelMetadata={},
            tokenRecommendationSource="default",
        )

    requires_api_key = bool(provider_info.get("requiresApiKey", True))
    if requires_api_key and not request.apiKey:
        return LLMFetchModelsResponse(
            success=False,
            message=f"{resolved_provider_id} 需要 API Key",
            provider=request.provider,
            resolvedProvider=resolved_provider_id,
            models=[],
            defaultModel=str(provider_info.get("defaultModel") or ""),
            source="fallback_static",
            baseUrlUsed=request.baseUrl,
            modelMetadata={},
            tokenRecommendationSource="default",
        )

    static_models = list(provider_info.get("models") or [])
    default_model = str(provider_info.get("defaultModel") or "")
    fetch_style = str(provider_info.get("fetchStyle") or "openai_compatible")
    base_url = (request.baseUrl or str(provider_info.get("defaultBaseUrl") or "")).strip()
    static_model_metadata = _build_static_model_metadata(static_models)
    if default_model and default_model not in static_model_metadata:
        static_model_metadata[default_model] = {
            "contextWindow": None,
            "maxOutputTokens": None,
            "recommendedMaxTokens": _recommend_tokens_from_static_map(default_model),
            "source": "static_mapping",
        }

    if not base_url:
        return LLMFetchModelsResponse(
            success=bool(static_models),
            message="未配置可用的 API Base URL，已回退内置模型列表",
            provider=request.provider,
            resolvedProvider=resolved_provider_id,
            models=sorted({m for m in static_models if isinstance(m, str) and m.strip()}, key=str.lower),
            defaultModel=default_model,
            source="fallback_static",
            baseUrlUsed=base_url,
            modelMetadata=static_model_metadata,
            tokenRecommendationSource="static_mapping",
        )

    try:
        if fetch_style == "anthropic":
            online_models, online_model_metadata = await _fetch_models_anthropic(base_url, request.apiKey)
        elif fetch_style == "azure_openai":
            online_models, online_model_metadata = await _fetch_models_azure_openai(base_url, request.apiKey)
        else:
            online_models, online_model_metadata = await _fetch_models_openai_compatible(base_url, request.apiKey)

        if online_models:
            merged_metadata = dict(static_model_metadata)
            merged_metadata.update(online_model_metadata or {})
            return LLMFetchModelsResponse(
                success=True,
                message=f"已拉取 {len(online_models)} 个模型",
                provider=request.provider,
                resolvedProvider=resolved_provider_id,
                models=online_models,
                defaultModel=default_model,
                source="online",
                baseUrlUsed=base_url,
                modelMetadata=merged_metadata,
                tokenRecommendationSource=(
                    str((merged_metadata.get(default_model) or {}).get("source"))
                    if default_model and isinstance(merged_metadata.get(default_model), dict)
                    else "online_metadata"
                ),
            )
    except Exception as exc:
        if static_models:
            return LLMFetchModelsResponse(
                success=True,
                message=f"在线拉取失败，已回退内置模型列表（{exc}）",
                provider=request.provider,
                resolvedProvider=resolved_provider_id,
                models=sorted(
                    {m for m in static_models if isinstance(m, str) and m.strip()},
                    key=str.lower,
                ),
                defaultModel=default_model,
                source="fallback_static",
                baseUrlUsed=base_url,
                modelMetadata=static_model_metadata,
                tokenRecommendationSource="static_mapping",
            )
        return LLMFetchModelsResponse(
            success=False,
            message=f"在线拉取失败且无内置模型可回退：{exc}",
            provider=request.provider,
            resolvedProvider=resolved_provider_id,
            models=[],
            defaultModel=default_model,
            source="fallback_static",
            baseUrlUsed=base_url,
            modelMetadata={},
            tokenRecommendationSource="default",
        )

    return LLMFetchModelsResponse(
        success=bool(static_models),
        message="在线接口未返回模型，已回退内置模型列表",
        provider=request.provider,
        resolvedProvider=resolved_provider_id,
        models=sorted({m for m in static_models if isinstance(m, str) and m.strip()}, key=str.lower),
        defaultModel=default_model,
        source="fallback_static",
        baseUrlUsed=base_url,
        modelMetadata=static_model_metadata,
        tokenRecommendationSource="static_mapping",
    )


@router.get("/llm-providers")
async def get_llm_providers() -> Any:
    """获取支持的LLM提供商列表"""
    return {"providers": _build_llm_provider_catalog()}
