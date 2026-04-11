import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.encryption import decrypt_sensitive_data, encrypt_sensitive_data
from app.models.user_config import UserConfig

SENSITIVE_LLM_FIELDS = [
    "llmApiKey",
    "geminiApiKey",
    "openaiApiKey",
    "claudeApiKey",
    "qwenApiKey",
    "deepseekApiKey",
    "zhipuApiKey",
    "moonshotApiKey",
    "baiduApiKey",
    "minimaxApiKey",
    "doubaoApiKey",
]
SENSITIVE_OTHER_FIELDS: list[str] = []


def encrypt_config(config: dict, sensitive_fields: list[str]) -> dict:
    encrypted = config.copy()
    for field in sensitive_fields:
        if field in encrypted and encrypted[field]:
            encrypted[field] = encrypt_sensitive_data(encrypted[field])
    return encrypted


def decrypt_config(config: dict, sensitive_fields: list[str]) -> dict:
    decrypted = config.copy()
    for field in sensitive_fields:
        if field in decrypted and decrypted[field]:
            decrypted[field] = decrypt_sensitive_data(decrypted[field])
    return decrypted


def sanitize_other_config(raw_other_config: Any) -> dict:
    candidate = dict(raw_other_config) if isinstance(raw_other_config, dict) else {}
    for retired_key in ("githubToken", "gitlabToken", "giteaToken", "outputLanguage"):
        candidate.pop(retired_key, None)
    candidate.pop("mcpConfig", None)
    candidate.pop("toolRuntimeConfig", None)
    return candidate


def strip_runtime_config(raw_other_config: Any) -> dict:
    candidate = dict(raw_other_config) if isinstance(raw_other_config, dict) else {}
    for retired_key in ("githubToken", "gitlabToken", "giteaToken", "outputLanguage"):
        candidate.pop(retired_key, None)
    candidate.pop("mcpConfig", None)
    candidate.pop("toolRuntimeConfig", None)
    return candidate


def get_default_user_config() -> dict:
    return {
        "llmConfig": {
            "llmProvider": settings.LLM_PROVIDER,
            "llmApiKey": "",
            "llmModel": settings.LLM_MODEL or "",
            "llmBaseUrl": settings.LLM_BASE_URL or "",
            "llmTimeout": settings.LLM_TIMEOUT * 1000,
            "llmTemperature": settings.LLM_TEMPERATURE,
            "llmMaxTokens": settings.LLM_MAX_TOKENS,
            "llmCustomHeaders": "",
            "llmFirstTokenTimeout": getattr(settings, "LLM_FIRST_TOKEN_TIMEOUT", 45),
            "llmStreamTimeout": getattr(settings, "LLM_STREAM_TIMEOUT", 120),
            "agentTimeout": settings.AGENT_TIMEOUT_SECONDS,
            "subAgentTimeout": getattr(settings, "SUB_AGENT_TIMEOUT_SECONDS", 600),
            "toolTimeout": getattr(settings, "TOOL_TIMEOUT_SECONDS", 60),
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
            "maxAnalyzeFiles": settings.MAX_ANALYZE_FILES,
            "llmConcurrency": settings.LLM_CONCURRENCY,
            "llmGapMs": settings.LLM_GAP_MS,
        },
    }


async def load_user_config_payload(
    *,
    db: AsyncSession,
    user_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    result = await db.execute(select(UserConfig).where(UserConfig.user_id == user_id))
    user_config_record = result.scalar_one_or_none()

    saved_llm_config: dict[str, Any] = {}
    saved_other_config: dict[str, Any] = {}
    if not user_config_record:
        return saved_llm_config, saved_other_config

    if user_config_record.llm_config:
        saved_llm_config = decrypt_config(
            json.loads(user_config_record.llm_config),
            SENSITIVE_LLM_FIELDS,
        )
    if user_config_record.other_config:
        saved_other_config = decrypt_config(
            json.loads(user_config_record.other_config),
            SENSITIVE_OTHER_FIELDS,
        )
    return saved_llm_config, saved_other_config


async def load_user_config_payload_with_effective_defaults(
    *,
    db: AsyncSession,
    user_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    saved_llm_config, saved_other_config = await load_user_config_payload(
        db=db,
        user_id=user_id,
    )
    default_config = get_default_user_config()
    effective_llm_config = {
        **default_config["llmConfig"],
        **saved_llm_config,
    }
    effective_other_config = sanitize_other_config(
        {
            **default_config["otherConfig"],
            **strip_runtime_config(saved_other_config),
        }
    )
    return (
        saved_llm_config,
        saved_other_config,
        effective_llm_config,
        effective_other_config,
    )


async def load_effective_user_config(
    *,
    db: AsyncSession,
    user_id: str,
) -> dict[str, dict[str, Any]]:
    (
        _saved_llm_config,
        _saved_other_config,
        effective_llm_config,
        effective_other_config,
    ) = await load_user_config_payload_with_effective_defaults(
        db=db,
        user_id=user_id,
    )
    return {
        "llmConfig": effective_llm_config,
        "otherConfig": effective_other_config,
    }
