"""
用户配置API端点
"""

from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
import json

from app.api import deps
from app.db.session import get_db
from app.models.user_config import UserConfig
from app.models.user import User
from app.core.config import settings
from app.core.encryption import encrypt_sensitive_data, decrypt_sensitive_data
from app.services.agent.mcp.catalog import build_mcp_catalog

router = APIRouter()

# 需要加密的敏感字段列表
SENSITIVE_LLM_FIELDS = [
    'llmApiKey', 'geminiApiKey', 'openaiApiKey', 'claudeApiKey',
    'qwenApiKey', 'deepseekApiKey', 'zhipuApiKey', 'moonshotApiKey',
    'baiduApiKey', 'minimaxApiKey', 'doubaoApiKey'
]
SENSITIVE_OTHER_FIELDS = ['githubToken', 'gitlabToken']

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
            backend_enabled=bool(getattr(settings, "MCP_FILESYSTEM_ENABLED", True)),
            sandbox_enabled=bool(getattr(settings, "MCP_FILESYSTEM_SANDBOX_ENABLED", True)),
        ),
        "code_index": _entry(
            runtime_mode=str(getattr(settings, "MCP_CODE_INDEX_RUNTIME_MODE", "backend_then_sandbox")),
            backend_enabled=bool(getattr(settings, "MCP_CODE_INDEX_ENABLED", False)),
            sandbox_enabled=bool(getattr(settings, "MCP_CODE_INDEX_SANDBOX_ENABLED", False)),
        ),
        "memory": _entry(
            runtime_mode=str(getattr(settings, "MCP_MEMORY_RUNTIME_MODE", "backend_then_sandbox")),
            backend_enabled=bool(getattr(settings, "MCP_MEMORY_ENABLED", False)),
            sandbox_enabled=bool(getattr(settings, "MCP_MEMORY_SANDBOX_ENABLED", False)),
        ),
        "sequentialthinking": _entry(
            runtime_mode=str(
                getattr(settings, "MCP_SEQUENTIAL_THINKING_RUNTIME_MODE", "backend_then_sandbox")
            ),
            backend_enabled=bool(getattr(settings, "MCP_SEQUENTIAL_THINKING_ENABLED", False)),
            sandbox_enabled=bool(getattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", False)),
        ),
        "qmd": _entry(
            runtime_mode=str(getattr(settings, "MCP_QMD_RUNTIME_MODE", "backend_then_sandbox")),
            backend_enabled=bool(getattr(settings, "MCP_QMD_ENABLED", False)),
            sandbox_enabled=bool(getattr(settings, "MCP_QMD_SANDBOX_ENABLED", False)),
        ),
        "codebadger": _entry(
            runtime_mode=str(getattr(settings, "MCP_CODEBADGER_RUNTIME_MODE", "backend_only")),
            backend_enabled=bool(getattr(settings, "MCP_CODEBADGER_ENABLED", False)),
            sandbox_enabled=bool(bool(getattr(settings, "MCP_CODEBADGER_SANDBOX_URL", None))),
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
    return sanitized


def _build_mcp_runtime_persistence() -> dict:
    return {
        "backend_data_dir": "/app/data/mcp",
        "sandbox_data_dir": "/tmp/deepaudit/mcp-cache",
        "qmd_data_dir": str(getattr(settings, "QMD_DATA_DIR", "./data/qmd") or "./data/qmd"),
    }


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
    return {
        "enabled": enabled,
        "preferMcp": bool(
            candidate.get("preferMcp", getattr(settings, "MCP_PREFER", True))
        ),
        "writePolicy": _sanitize_mcp_write_policy(candidate.get("writePolicy")),
        "runtimePolicy": runtime_policy,
        "runtimePersistence": _build_mcp_runtime_persistence(),
        # Read-only catalog: always generated by backend.
        "catalog": build_mcp_catalog(
            mcp_enabled=enabled,
            runtime_policy=runtime_policy,
        ),
    }


def _sanitize_other_config(raw_other_config: Any) -> dict:
    candidate = dict(raw_other_config) if isinstance(raw_other_config, dict) else {}
    candidate["mcpConfig"] = _sanitize_mcp_config(candidate.get("mcpConfig"))
    return candidate


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

    class Config:
        from_attributes = True


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


class LLMTestRequest(BaseModel):
    """LLM测试请求"""
    provider: str
    apiKey: str
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


@router.post("/test-llm", response_model=LLMTestResponse)
async def test_llm_connection(
    request: LLMTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """测试LLM连接是否正常"""
    from app.services.llm.factory import LLMFactory, NATIVE_ONLY_PROVIDERS
    from app.services.llm.adapters import LiteLLMAdapter, BaiduAdapter, MinimaxAdapter, DoubaoAdapter
    from app.services.llm.types import LLMConfig, LLMProvider, LLMRequest, LLMMessage, DEFAULT_MODELS, DEFAULT_BASE_URLS
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
        "provider": request.provider,
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
        # 解析provider
        provider_map = {
            'gemini': LLMProvider.GEMINI,
            'openai': LLMProvider.OPENAI,
            'claude': LLMProvider.CLAUDE,
            'qwen': LLMProvider.QWEN,
            'deepseek': LLMProvider.DEEPSEEK,
            'zhipu': LLMProvider.ZHIPU,
            'moonshot': LLMProvider.MOONSHOT,
            'baidu': LLMProvider.BAIDU,
            'minimax': LLMProvider.MINIMAX,
            'doubao': LLMProvider.DOUBAO,
            'ollama': LLMProvider.OLLAMA,
        }

        provider = provider_map.get(request.provider.lower())
        if not provider:
            debug_info["error_type"] = "unsupported_provider"
            return LLMTestResponse(
                success=False,
                message=f"不支持的LLM提供商: {request.provider}",
                debug=debug_info
            )

        # 获取默认模型
        model = request.model or DEFAULT_MODELS.get(provider)
        base_url = request.baseUrl or DEFAULT_BASE_URLS.get(provider, "")

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
            api_key=request.apiKey,
            model=model,
            base_url=request.baseUrl,
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


@router.get("/llm-providers")
async def get_llm_providers() -> Any:
    """获取支持的LLM提供商列表"""
    from app.services.llm.factory import LLMFactory
    from app.services.llm.types import LLMProvider, DEFAULT_BASE_URLS
    
    providers = []
    for provider in LLMFactory.get_supported_providers():
        providers.append({
            "id": provider.value,
            "name": provider.value.upper(),
            "defaultModel": LLMFactory.get_default_model(provider),
            "models": LLMFactory.get_available_models(provider),
            "defaultBaseUrl": DEFAULT_BASE_URLS.get(provider, ""),
        })
    
    return {"providers": providers}
