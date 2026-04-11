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
from app.services.agent.skills.scan_core import build_scan_core_skill_availability
from app.services.llm.config_utils import (
    normalize_llm_base_url,
    parse_llm_custom_headers,
)
from app.services.llm.provider_registry import (
    build_llm_provider_catalog as build_provider_catalog,
    resolve_llm_runtime_provider as resolve_provider_runtime,
)
from app.services.llm.types import LLMProvider
from app.services import user_config_service
from app.services.zip_storage import load_project_zip

router = APIRouter()

# 需要加密的敏感字段列表
SENSITIVE_LLM_FIELDS = [
    'llmApiKey', 'geminiApiKey', 'openaiApiKey', 'claudeApiKey',
    'qwenApiKey', 'deepseekApiKey', 'zhipuApiKey', 'moonshotApiKey',
    'baiduApiKey', 'minimaxApiKey', 'doubaoApiKey'
]
SENSITIVE_OTHER_FIELDS: list[str] = []
LLM_PROVIDER_API_KEY_FIELD_MAP = {
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
LLM_CONNECTION_CONFIG_KEYS = (
    "llmProvider",
    "llmApiKey",
    "llmModel",
    "llmBaseUrl",
    "ollamaBaseUrl",
    *tuple(LLM_PROVIDER_API_KEY_FIELD_MAP.values()),
)
AGENT_TASK_PREFLIGHT_TIMEOUT_SECONDS = 10


def _resolve_llm_runtime_provider(provider: Any) -> tuple[str, Optional[LLMProvider]]:
    return resolve_provider_runtime(provider)


def _build_llm_provider_catalog() -> list[dict[str, Any]]:
    return build_provider_catalog()


def _normalize_llm_provider_id(provider: Any) -> str:
    resolved_provider_id, _ = _resolve_llm_runtime_provider(provider)
    normalized = str(resolved_provider_id or provider or "").strip().lower()
    if not normalized:
        return "openai"
    return normalized


def _resolve_effective_llm_api_key(provider_id: str, llm_config: dict[str, Any]) -> str:
    direct_key = str(llm_config.get("llmApiKey") or "").strip()
    if direct_key:
        return direct_key
    provider_key_field = LLM_PROVIDER_API_KEY_FIELD_MAP.get(
        _normalize_llm_provider_id(provider_id)
    )
    if not provider_key_field:
        return ""
    return str(llm_config.get(provider_key_field) or "").strip()


def _has_saved_llm_connection_config(llm_config: dict[str, Any]) -> bool:
    for key in LLM_CONNECTION_CONFIG_KEYS:
        if str(llm_config.get(key) or "").strip():
            return True
    return False


def _build_llm_quick_config_snapshot(
    llm_config: dict[str, Any],
) -> "LLMQuickConfigSnapshot":
    provider = _normalize_llm_provider_id(llm_config.get("llmProvider"))
    base_url = normalize_llm_base_url(
        llm_config.get("llmBaseUrl") or llm_config.get("ollamaBaseUrl")
    )
    return LLMQuickConfigSnapshot(
        provider=provider,
        model=str(llm_config.get("llmModel") or "").strip(),
        baseUrl=base_url,
        apiKey=_resolve_effective_llm_api_key(provider, llm_config),
    )


def _collect_preflight_missing_fields(
    snapshot: "LLMQuickConfigSnapshot",
) -> list[str]:
    missing_fields: list[str] = []
    if not snapshot.model:
        missing_fields.append("llmModel")
    if not snapshot.baseUrl:
        missing_fields.append("llmBaseUrl")
    if snapshot.provider != "ollama" and not snapshot.apiKey:
        missing_fields.append("llmApiKey")
    return missing_fields


def _format_missing_fields_message(missing_fields: list[str]) -> str:
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


async def _load_user_config_payload(
    *,
    db: AsyncSession,
    user_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    return await user_config_service.load_user_config_payload(db=db, user_id=user_id)


async def _load_user_config_payload_with_effective_defaults(
    *,
    db: AsyncSession,
    user_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    saved_llm_config, saved_other_config = await _load_user_config_payload(
        db=db,
        user_id=user_id,
    )
    default_config = get_default_config()
    effective_llm_config = {
        **default_config["llmConfig"],
        **saved_llm_config,
    }
    effective_other_config = _sanitize_other_config(
        {
            **default_config["otherConfig"],
            **_strip_runtime_config(saved_other_config),
        }
    )
    return (
        saved_llm_config,
        saved_other_config,
        effective_llm_config,
        effective_other_config,
    )


async def _load_effective_user_config(
    *,
    db: AsyncSession,
    user_id: str,
) -> dict[str, dict[str, Any]]:
    (
        _saved_llm_config,
        _saved_other_config,
        effective_llm_config,
        effective_other_config,
    ) = await _load_user_config_payload_with_effective_defaults(
        db=db,
        user_id=user_id,
    )
    return {
        "llmConfig": effective_llm_config,
        "otherConfig": effective_other_config,
    }

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

def _merge_http_headers(
    default_headers: dict[str, str],
    custom_headers: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    merged = {key: value for key, value in default_headers.items() if value}
    if custom_headers:
        merged.update(custom_headers)
    return merged

async def _fetch_models_openai_compatible(
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
        return _extract_model_names_from_payload(payload), _extract_model_metadata_from_payload(payload)

async def _fetch_models_anthropic(
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
        return _extract_model_names_from_payload(payload), _extract_model_metadata_from_payload(payload)

async def _fetch_models_azure_openai(
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
                models = _extract_model_names_from_payload(payload)
                if models:
                    return models, _extract_model_metadata_from_payload(payload)
            except Exception as exc:
                last_error = exc
                continue
    if last_error:
        raise last_error
    return [], {}

def _sanitize_other_config(raw_other_config: Any) -> dict:
    return user_config_service.sanitize_other_config(raw_other_config)

def _strip_runtime_config(raw_other_config: Any) -> dict:
    return user_config_service.strip_runtime_config(raw_other_config)

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


_VERIFY_DEFAULT_PROJECT_NAME = "libplist"


async def _resolve_verify_project(
    *,
    db: AsyncSession,
    current_user: User,
) -> tuple[Project, str, bool]:
    preferred_stmt = (
        select(Project)
        .where(
            Project.owner_id == current_user.id,
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
            detail="未找到可用于技能测试的 ZIP 项目，请先上传 ZIP 项目或修复默认 libplist 资源。",
        )

    return selected_project, selected_zip_path, fallback_used


def encrypt_config(config: dict, sensitive_fields: list) -> dict:
    """加密配置中的敏感字段"""
    return user_config_service.encrypt_config(config, sensitive_fields)

def decrypt_config(config: dict, sensitive_fields: list) -> dict:
    """解密配置中的敏感字段"""
    return user_config_service.decrypt_config(config, sensitive_fields)

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
    maxAnalyzeFiles: Optional[int] = None
    llmConcurrency: Optional[int] = None
    llmGapMs: Optional[int] = None

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

def get_default_config() -> dict:
    """获取系统默认配置"""
    return user_config_service.get_default_user_config()

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
    
    if not config:
        default_config = get_default_config()
        print(f"[Config] 用户 {current_user.id} 没有保存的配置，返回默认配置")
        # 返回系统默认配置
        return UserConfigResponse(
            id="",
            user_id=current_user.id,
            llmConfig=default_config["llmConfig"],
            otherConfig=default_config["otherConfig"],
            created_at="",
        )
    
    (
        user_llm_config,
        user_other_config,
        merged_llm_config,
        merged_other_config,
    ) = await _load_user_config_payload_with_effective_defaults(
        db=db,
        user_id=current_user.id,
    )
    
    print(f"[Config] 用户 {current_user.id} 的保存配置:")
    print(f"  - llmProvider: {user_llm_config.get('llmProvider')}")
    print(f"  - llmApiKey: {'***' + user_llm_config.get('llmApiKey', '')[-4:] if user_llm_config.get('llmApiKey') else '(空)'}")
    print(f"  - llmModel: {user_llm_config.get('llmModel')}")

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
    if llm_data:
        if "llmProvider" in llm_data:
            provider_id, _ = _resolve_llm_runtime_provider(llm_data.get("llmProvider"))
            llm_data["llmProvider"] = provider_id or str(llm_data.get("llmProvider") or "").strip()
        if "llmBaseUrl" in llm_data:
            llm_data["llmBaseUrl"] = normalize_llm_base_url(llm_data.get("llmBaseUrl"))
        if "ollamaBaseUrl" in llm_data:
            llm_data["ollamaBaseUrl"] = normalize_llm_base_url(llm_data.get("ollamaBaseUrl"))
        if "llmCustomHeaders" in llm_data:
            try:
                parsed_headers = parse_llm_custom_headers(llm_data.get("llmCustomHeaders"))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            llm_data["llmCustomHeaders"] = (
                json.dumps(parsed_headers, ensure_ascii=False, sort_keys=True)
                if parsed_headers
                else ""
            )
    if other_data:
        # Tool runtime config is server-controlled; ignore frontend payload.
        other_data = _strip_runtime_config(other_data)
    
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
            existing_other = _strip_runtime_config(existing_other)
            existing_other.update(other_data)  # 使用未加密的新数据合并
            existing_other = _strip_runtime_config(existing_other)
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
    user_other_config = _strip_runtime_config(user_other_config)
    
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

class LLMTestRequest(BaseModel):
    """LLM测试请求"""
    provider: str
    apiKey: Optional[str] = None
    model: Optional[str] = None
    baseUrl: Optional[str] = None
    customHeaders: Optional[str] = None

class LLMTestResponse(BaseModel):
    """LLM测试响应"""
    success: bool
    message: str
    model: Optional[str] = None
    response: Optional[str] = None
    # 调试信息
    debug: Optional[dict] = None


class LLMQuickConfigSnapshot(BaseModel):
    provider: str
    model: str
    baseUrl: str
    apiKey: str


class AgentTaskLLMPreflightResponse(BaseModel):
    ok: bool
    stage: Optional[str] = None
    message: str
    reasonCode: Optional[str] = None
    missingFields: Optional[list[str]] = None
    effectiveConfig: LLMQuickConfigSnapshot
    savedConfig: Optional[LLMQuickConfigSnapshot] = None

class LLMFetchModelsRequest(BaseModel):
    """按提供商拉取模型列表请求"""
    provider: str
    apiKey: str
    baseUrl: Optional[str] = None
    customHeaders: Optional[str] = None

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


async def _execute_llm_test_request(
    request: LLMTestRequest,
    *,
    saved_llm_config: Optional[dict[str, Any]] = None,
    saved_other_config: Optional[dict[str, Any]] = None,
) -> LLMTestResponse:
    from app.services.llm.factory import NATIVE_ONLY_PROVIDERS
    from app.services.llm.adapters import LiteLLMAdapter, BaiduAdapter, MinimaxAdapter, DoubaoAdapter
    from app.services.llm.types import LLMConfig, LLMProvider, LLMRequest, LLMMessage
    import traceback

    start_time = time.time()
    saved_llm_config = saved_llm_config or {}
    saved_other_config = saved_other_config or {}

    saved_timeout_ms = saved_llm_config.get('llmTimeout', settings.LLM_TIMEOUT * 1000)
    saved_temperature = saved_llm_config.get('llmTemperature', settings.LLM_TEMPERATURE)
    saved_max_tokens = saved_llm_config.get('llmMaxTokens', settings.LLM_MAX_TOKENS)
    saved_concurrency = saved_other_config.get('llmConcurrency', settings.LLM_CONCURRENCY)
    saved_gap_ms = saved_other_config.get('llmGapMs', settings.LLM_GAP_MS)
    saved_max_files = saved_other_config.get('maxAnalyzeFiles', settings.MAX_ANALYZE_FILES)

    debug_info = {
        "provider_requested": request.provider,
        "model_requested": request.model,
        "base_url_requested": request.baseUrl,
        "api_key_length": len(request.apiKey) if request.apiKey else 0,
        "api_key_prefix": request.apiKey[:8] + "..." if request.apiKey and len(request.apiKey) > 8 else "(empty)",
        "saved_config": {
            "timeout_ms": saved_timeout_ms,
            "temperature": saved_temperature,
            "max_tokens": saved_max_tokens,
            "concurrency": saved_concurrency,
            "gap_ms": saved_gap_ms,
            "max_analyze_files": saved_max_files,
        },
    }

    try:
        resolved_provider_id, provider = _resolve_llm_runtime_provider(request.provider)
        if not provider:
            debug_info["error_type"] = "unsupported_provider"
            return LLMTestResponse(
                success=False,
                message=f"不支持的LLM提供商: {request.provider}",
                debug=debug_info,
            )
        debug_info["provider_resolved"] = resolved_provider_id
        debug_info["provider_runtime"] = provider.value

        model = str(request.model or "").strip()
        base_url = normalize_llm_base_url(request.baseUrl)
        api_key = str(request.apiKey or "").strip()
        try:
            custom_headers = parse_llm_custom_headers(request.customHeaders)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
            api_key = "ollama"

        test_timeout = int(saved_timeout_ms / 1000) if saved_timeout_ms else settings.LLM_TIMEOUT
        test_temperature = saved_temperature if saved_temperature is not None else settings.LLM_TEMPERATURE
        test_max_tokens = saved_max_tokens if saved_max_tokens else settings.LLM_MAX_TOKENS

        debug_info["model_used"] = model
        debug_info["base_url_used"] = base_url
        debug_info["custom_headers_count"] = len(custom_headers)
        debug_info["is_native_adapter"] = provider in NATIVE_ONLY_PROVIDERS
        debug_info["test_params"] = {
            "timeout": test_timeout,
            "temperature": test_temperature,
            "max_tokens": test_max_tokens,
        }

        print(
            "[LLM Test] 开始测试: "
            f"provider={provider.value}, model={model}, base_url={base_url}, "
            f"temperature={test_temperature}, timeout={test_timeout}s, "
            f"max_tokens={test_max_tokens}"
        )

        config = LLMConfig(
            provider=provider,
            api_key=api_key,
            model=model,
            base_url=base_url or None,
            timeout=test_timeout,
            temperature=test_temperature,
            max_tokens=test_max_tokens,
            custom_headers=custom_headers,
        )

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
            debug_info["litellm_model"] = (
                getattr(adapter, '_get_litellm_model', lambda: model)()
                if hasattr(adapter, '_get_litellm_model')
                else model
            )

        test_request = LLMRequest(
            messages=[LLMMessage(role="user", content="Say 'Hello' in one word.")],
            temperature=test_temperature,
            max_tokens=test_max_tokens,
        )

        print("[LLM Test] 发送测试请求...")
        response = await adapter.complete(test_request)

        elapsed_time = time.time() - start_time
        debug_info["elapsed_time_ms"] = round(elapsed_time * 1000, 2)

        if not response or not response.content:
            debug_info["error_type"] = "empty_response"
            debug_info["raw_response"] = str(response) if response else None
            print(f"[LLM Test] 空响应: {response}")
            return LLMTestResponse(
                success=False,
                message="LLM 返回空响应，请检查 API Key 和配置",
                debug=debug_info,
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
            debug=debug_info,
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

        if hasattr(e, 'api_response') and e.api_response:
            debug_info["api_response"] = e.api_response
        if hasattr(e, 'status_code') and e.status_code:
            debug_info["status_code"] = e.status_code

        print(f"[LLM Test] 失败: {error_type}: {error_msg}")
        print(f"[LLM Test] Traceback:\n{traceback.format_exc()}")

        friendly_message = error_msg
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
            debug=debug_info,
        )


@router.post("/test-llm", response_model=LLMTestResponse)
async def test_llm_connection(
    request: LLMTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """测试LLM连接是否正常"""
    saved_llm_config, saved_other_config = await _load_user_config_payload(
        db=db,
        user_id=current_user.id,
    )
    return await _execute_llm_test_request(
        request,
        saved_llm_config=saved_llm_config,
        saved_other_config=saved_other_config,
    )


@router.post("/agent-task-preflight", response_model=AgentTaskLLMPreflightResponse)
async def agent_task_llm_preflight(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    (
        saved_llm_config,
        saved_other_config,
        effective_llm_config,
        _effective_other_config,
    ) = await _load_user_config_payload_with_effective_defaults(
        db=db,
        user_id=current_user.id,
    )
    effective_snapshot = _build_llm_quick_config_snapshot(effective_llm_config)

    if not _has_saved_llm_connection_config(saved_llm_config):
        return AgentTaskLLMPreflightResponse(
            ok=False,
            stage="llm_config",
            reasonCode="default_config",
            message="检测到当前仍在使用默认 LLM 配置，请先保存并测试专属 LLM 配置。",
            effectiveConfig=effective_snapshot,
            savedConfig=None,
        )

    saved_snapshot = _build_llm_quick_config_snapshot(saved_llm_config)
    missing_fields = _collect_preflight_missing_fields(saved_snapshot)
    if missing_fields:
        return AgentTaskLLMPreflightResponse(
            ok=False,
            stage="llm_config",
            reasonCode="missing_fields",
            missingFields=missing_fields,
            message=(
                "智能扫描初始化失败：LLM 缺少必填配置 "
                f"{_format_missing_fields_message(missing_fields)}，请先补全并保存。"
            ),
            effectiveConfig=effective_snapshot,
            savedConfig=saved_snapshot,
        )

    test_request = LLMTestRequest(
        provider=saved_snapshot.provider,
        apiKey=saved_snapshot.apiKey,
        model=saved_snapshot.model,
        baseUrl=saved_snapshot.baseUrl,
        customHeaders=str(saved_llm_config.get("llmCustomHeaders") or ""),
    )

    try:
        llm_result = await asyncio.wait_for(
            _execute_llm_test_request(
                test_request,
                saved_llm_config=saved_llm_config,
                saved_other_config=saved_other_config,
            ),
            timeout=AGENT_TASK_PREFLIGHT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return AgentTaskLLMPreflightResponse(
            ok=False,
            stage="llm_test",
            reasonCode="llm_test_timeout",
            message=(
                f"智能扫描初始化失败：LLM 测试超时（>{AGENT_TASK_PREFLIGHT_TIMEOUT_SECONDS}s），"
                "请检查网络、模型服务或改用更稳定的配置。"
            ),
            effectiveConfig=effective_snapshot,
            savedConfig=saved_snapshot,
        )
    except HTTPException as exc:
        detail = str(exc.detail or "未知错误").strip() or "未知错误"
        return AgentTaskLLMPreflightResponse(
            ok=False,
            stage="llm_test",
            reasonCode="llm_test_exception",
            message=f"智能扫描初始化失败：{detail}",
            effectiveConfig=effective_snapshot,
            savedConfig=saved_snapshot,
        )
    except Exception as exc:
        return AgentTaskLLMPreflightResponse(
            ok=False,
            stage="llm_test",
            reasonCode="llm_test_exception",
            message=f"智能扫描初始化失败：LLM 测试异常（{exc}）。",
            effectiveConfig=effective_snapshot,
            savedConfig=saved_snapshot,
        )

    if not llm_result.success:
        return AgentTaskLLMPreflightResponse(
            ok=False,
            stage="llm_test",
            reasonCode="llm_test_failed",
            message=f"智能扫描初始化失败：LLM 测试未通过（{llm_result.message or '未知错误'}）。",
            effectiveConfig=effective_snapshot,
            savedConfig=saved_snapshot,
        )

    return AgentTaskLLMPreflightResponse(
        ok=True,
        message="LLM 配置测试通过。",
        effectiveConfig=effective_snapshot,
        savedConfig=saved_snapshot,
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
    base_url = normalize_llm_base_url(
        request.baseUrl or str(provider_info.get("defaultBaseUrl") or "")
    )
    try:
        custom_headers = parse_llm_custom_headers(request.customHeaders)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
            online_models, online_model_metadata = await _fetch_models_anthropic(
                base_url,
                request.apiKey,
                custom_headers,
            )
        elif fetch_style == "azure_openai":
            online_models, online_model_metadata = await _fetch_models_azure_openai(
                base_url,
                request.apiKey,
                custom_headers,
            )
        elif fetch_style == "native_static":
            online_models, online_model_metadata = [], {}
        else:
            online_models, online_model_metadata = await _fetch_models_openai_compatible(
                base_url,
                request.apiKey,
                custom_headers,
            )

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
