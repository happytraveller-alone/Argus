"""
DeepAudit Agent 审计任务 API
基于 LangGraph 的 Agent 审计
"""

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, List, Optional, Dict, Set, Tuple
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import case, func
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, ConfigDict, Field
import yaml

from app.api import deps
from app.db.session import get_db, async_session_factory
from app.models.agent_task import (
    AgentTask, AgentEvent, AgentFinding,
    AgentTaskStatus, AgentTaskPhase, AgentEventType,
    VulnerabilitySeverity, FindingStatus,
)
from app.models.project import Project
from app.models.opengrep import OpengrepRule
from app.models.user import User
from app.models.user_config import UserConfig
from app.services.agent.event_manager import EventManager
from app.services.agent.streaming import StreamHandler, StreamEvent, StreamEventType
from app.services.agent.utils.vulnerability_naming import (
    build_cn_structured_description,
    build_cn_structured_description_markdown,
    build_cn_structured_title,
    infer_code_fence_language,
    normalize_cwe_id as normalize_cwe_id_util,
    resolve_cwe_id as resolve_cwe_id_util,
    resolve_vulnerability_profile as resolve_vulnerability_profile_util,
)
from app.services.agent.mcp import (
    HARD_MAX_WRITABLE_FILES_PER_TASK,
    FastMCPHttpAdapter,
    FastMCPStdioAdapter,
    MCPRuntime,
    MCPDeprecatedTool,
    MCPVirtualReadTool,
    QmdLazyIndexAdapter,
    TaskWriteScopeGuard,
    build_mcp_catalog,
)
from app.services.agent.mcp.daemon_manager import (
    MCPDaemonManager,
    normalize_qmd_loopback_url,
    resolve_code_index_backend_url,
    resolve_filesystem_backend_url,
    resolve_qmd_backend_url,
    resolve_sequential_backend_url,
)
from app.services.agent.mcp.protocol_verify import (
    build_tool_args as build_mcp_probe_tool_args,
    normalize_listed_tools as normalize_mcp_listed_tools,
)
from app.services.git_mirror import get_mirror_candidates
from app.services.git_ssh_service import GitSSHOperations
from app.core.encryption import decrypt_sensitive_data

logger = logging.getLogger(__name__)
router = APIRouter()

# 运行中的任务（兼容旧接口）
_running_tasks: Dict[str, Any] = {}

# 🔥 运行中的 asyncio Tasks（用于强制取消）
_running_asyncio_tasks: Dict[str, asyncio.Task] = {}

# 运行中的漏洞队列服务（供任务内工具与队列 API 共享）
_running_queue_services: Dict[str, Any] = {}
_running_recon_queue_services: Dict[str, Any] = {}

_VALID_TASK_STATUS_VALUES: Set[str] = {
    AgentTaskStatus.PENDING,
    AgentTaskStatus.INITIALIZING,
    AgentTaskStatus.RUNNING,
    AgentTaskStatus.PLANNING,
    AgentTaskStatus.INDEXING,
    AgentTaskStatus.ANALYZING,
    AgentTaskStatus.VERIFYING,
    AgentTaskStatus.REPORTING,
    AgentTaskStatus.COMPLETED,
    AgentTaskStatus.FAILED,
    AgentTaskStatus.CANCELLED,
    AgentTaskStatus.PAUSED,
}

_VALID_SEVERITY_VALUES: Set[str] = {
    VulnerabilitySeverity.CRITICAL,
    VulnerabilitySeverity.HIGH,
    VulnerabilitySeverity.MEDIUM,
    VulnerabilitySeverity.LOW,
    VulnerabilitySeverity.INFO,
}


# ============ Schemas ============

class AgentTaskCreate(BaseModel):
    """创建 Agent 任务请求"""
    project_id: str = Field(..., description="项目 ID")
    name: Optional[str] = Field(None, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    
    # 审计配置
    audit_scope: Optional[dict] = Field(None, description="审计范围")
    target_vulnerabilities: Optional[List[str]] = Field(
        default=["sql_injection", "xss", "command_injection", "path_traversal", "ssrf"],
        description="目标漏洞类型"
    )
    verification_level: Optional[str] = Field(
        "analysis_with_poc_plan",
        description="验证级别（统一语义）: analysis_with_poc_plan"
    )
    authorization_confirmed: Optional[bool] = Field(
        False,
        description="兼容字段：保留请求结构，不再作为强制门禁",
    )
    
    # 分支
    branch_name: Optional[str] = Field(None, description="分支名称")
    
    # 排除模式
    exclude_patterns: Optional[List[str]] = Field(
        default=["node_modules", "__pycache__", ".git", "*.min.js"],
        description="排除模式"
    )
    
    # 文件范围
    target_files: Optional[List[str]] = Field(None, description="指定扫描的文件")
    
    # Agent 配置
    max_iterations: int = Field(50, ge=1, le=200, description="最大迭代次数")
    timeout_seconds: int = Field(1800, ge=60, le=7200, description="超时时间（秒）")


class AgentTaskResponse(BaseModel):
    """Agent 任务响应 - 包含所有前端需要的字段"""
    id: str
    project_id: str
    name: Optional[str]
    description: Optional[str]
    task_type: str = "agent_audit"
    status: str
    current_phase: Optional[str]
    current_step: Optional[str] = None
    
    # 进度统计
    total_files: int = 0
    indexed_files: int = 0
    analyzed_files: int = 0
    total_chunks: int = 0
    
    # Agent 统计
    total_iterations: int = 0
    tool_calls_count: int = 0
    tokens_used: int = 0
    
    # 发现统计（兼容两种命名）
    findings_count: int = 0
    total_findings: int = 0  # 兼容字段
    verified_count: int = 0
    verified_findings: int = 0  # 兼容字段
    false_positive_count: int = 0
    
    # 严重程度统计
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    
    # 评分
    quality_score: float = 0.0
    security_score: Optional[float] = None
    
    # 进度百分比
    progress_percentage: float = 0.0
    
    # 时间
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 配置
    audit_scope: Optional[dict] = None
    target_vulnerabilities: Optional[List[str]] = None
    verification_level: Optional[str] = None
    exclude_patterns: Optional[List[str]] = None
    target_files: Optional[List[str]] = None
    
    # 错误信息
    error_message: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class AgentEventResponse(BaseModel):
    """Agent 事件响应"""
    id: str
    task_id: str
    event_type: str
    phase: Optional[str]
    message: Optional[str] = None
    sequence: int
    # 🔥 ORM 字段名是 created_at，序列化为 timestamp
    created_at: datetime = Field(serialization_alias="timestamp")

    # 工具相关字段
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Dict[str, Any]] = None
    tool_duration_ms: Optional[int] = None

    # 其他字段
    progress_percent: Optional[float] = None
    finding_id: Optional[str] = None
    tokens_used: Optional[int] = None
    # 🔥 ORM 字段名是 event_metadata，序列化为 metadata
    event_metadata: Optional[Dict[str, Any]] = Field(default=None, serialization_alias="metadata")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        by_alias=True,  # 🔥 关键：确保序列化时使用别名
    )


class AgentFindingResponse(BaseModel):
    """Agent 发现响应"""
    id: str
    task_id: str
    vulnerability_type: str
    severity: str
    title: str
    display_title: Optional[str] = None
    description: Optional[str]
    description_markdown: Optional[str] = None
    file_path: Optional[str]
    line_start: Optional[int]
    line_end: Optional[int]
    code_snippet: Optional[str]
    code_context: Optional[str] = None
    cwe_id: Optional[str] = None
    cwe_name: Optional[str] = None
    context_start_line: Optional[int] = None
    context_end_line: Optional[int] = None
    
    is_verified: bool
    # 🔥 FIX: Map from ai_confidence in ORM, make Optional with default
    confidence: Optional[float] = Field(
        default=0.5,
        validation_alias="ai_confidence",
    )
    reachability: Optional[str] = None
    authenticity: Optional[str] = None
    verification_evidence: Optional[str] = None
    flow_path_score: Optional[float] = None
    flow_call_chain: Optional[List[str]] = None
    function_trigger_flow: Optional[List[str]] = None
    flow_control_conditions: Optional[List[str]] = None
    logic_authz_evidence: Optional[List[str]] = None
    reachability_file: Optional[str] = None
    reachability_function: Optional[str] = None
    reachability_function_start_line: Optional[int] = None
    reachability_function_end_line: Optional[int] = None
    trigger_flow: Optional[dict] = None
    poc_trigger_chain: Optional[dict] = None
    status: str
    
    suggestion: Optional[str] = None
    fix_code: Optional[str] = None
    fix_description: Optional[str] = None
    has_poc: bool = False
    poc_code: Optional[str] = None
    poc_description: Optional[str] = None
    poc_steps: Optional[List[str]] = None
    poc: Optional[dict] = None
    
    created_at: datetime
    
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,  # Allow both 'confidence' and 'ai_confidence'
    )


class TaskSummaryResponse(BaseModel):
    """任务摘要响应"""
    task_id: str
    status: str
    security_score: Optional[int]
    
    total_findings: int
    verified_findings: int
    
    severity_distribution: Dict[str, int]
    vulnerability_types: Dict[str, int]
    
    duration_seconds: Optional[int]
    phases_completed: List[str]


# ============ 后台任务执行 ============

# 运行中的动态执行器
_running_orchestrators: Dict[str, Any] = {}
# 运行中的事件管理器（用于 SSE 流）
_running_event_managers: Dict[str, EventManager] = {}
# 🔥 已取消的任务集合（用于前置操作的取消检查）
_cancelled_tasks: Set[str] = set()
TOOL_DRAIN_TIMEOUT_SECONDS = 180


def is_task_cancelled(task_id: str) -> bool:
    """检查任务是否已被取消"""
    return task_id in _cancelled_tasks


def _build_tool_drain_metadata(drain_result: Dict[str, Any]) -> Dict[str, Any]:
    pending_calls = drain_result.get("pending_tool_calls")
    if not isinstance(pending_calls, list):
        pending_calls = []
    return {
        "tool_drain_wait_ms": int(drain_result.get("elapsed_ms") or 0),
        "tool_drain_timeout": bool(drain_result.get("timed_out", False)),
        "pending_tool_calls": pending_calls[:50],
    }


def _compute_verification_pending_gate(
    verification_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    candidate_count = 0
    pending_count = 0
    pending_examples: List[Dict[str, Any]] = []
    payload = verification_payload if isinstance(verification_payload, dict) else {}
    todo_summary = (
        payload.get("verification_todo_summary")
        if isinstance(payload.get("verification_todo_summary"), dict)
        else {}
    )

    candidate_raw = payload.get("candidate_count")
    if candidate_raw is None and isinstance(todo_summary, dict):
        candidate_raw = todo_summary.get("total")
    if candidate_raw is None:
        findings_snapshot = payload.get("findings")
        if isinstance(findings_snapshot, list):
            candidate_raw = len(findings_snapshot)
    try:
        candidate_count = max(0, int(candidate_raw or 0))
    except Exception:
        candidate_count = 0

    pending_raw = (
        todo_summary.get("pending")
        if isinstance(todo_summary, dict)
        else None
    )
    try:
        pending_count = max(0, int(pending_raw or 0))
    except Exception:
        pending_count = 0

    compact_items = (
        todo_summary.get("per_item_compact")
        if isinstance(todo_summary, dict)
        else None
    )
    if not isinstance(compact_items, list):
        compact_items = payload.get("todo_list")
    if isinstance(compact_items, list):
        for item in compact_items:
            if not isinstance(item, dict):
                continue
            status_text = str(item.get("status") or "").strip().lower()
            if status_text not in {"pending", "running", "unverified", "verifying"}:
                continue
            pending_examples.append(
                {
                    "id": str(item.get("id") or ""),
                    "status": status_text,
                    "title": str(item.get("title") or "")[:200],
                }
            )
        if pending_count <= 0:
            pending_count = len(pending_examples)
    if pending_examples:
        pending_examples = pending_examples[:5]

    triggered = candidate_count > 0 and pending_count > 0
    message = ""
    if triggered:
        message = (
            "verification_pending_gate:"
            f"candidate_count={candidate_count},"
            f"pending_count={pending_count}"
        )
    return {
        "triggered": triggered,
        "message": message,
        "candidate_count": candidate_count,
        "pending_count": pending_count,
        "pending_examples": pending_examples,
    }


async def _wait_for_terminal_tool_drain(
    *,
    event_manager: Optional[EventManager],
    task_id: str,
    skip_wait: bool = False,
    timeout_seconds: int = TOOL_DRAIN_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    if skip_wait:
        return {
            "ready": True,
            "timed_out": False,
            "elapsed_ms": 0,
            "pending_tool_calls": [],
        }
    if not event_manager:
        return {
            "ready": True,
            "timed_out": False,
            "elapsed_ms": 0,
            "pending_tool_calls": [],
        }
    try:
        return await event_manager.wait_for_tool_drain(
            task_id,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        logger.warning("[TaskDrain] wait_for_tool_drain failed for %s: %s", task_id, exc)
        return {
            "ready": False,
            "timed_out": True,
            "elapsed_ms": 0,
            "pending_tool_calls": [],
        }


class StepRetryExceededError(RuntimeError):
    """关键步骤重试耗尽"""

    def __init__(
        self,
        step_name: str,
        attempts: int,
        last_error: Exception,
        *,
        max_attempts: int,
    ):
        self.step_name = step_name
        self.attempts = attempts
        self.max_attempts = max_attempts
        self.last_error = last_error
        self.final_message = (
            f"[{step_name}] 第 {attempts}/{max_attempts} 次失败: "
            f"{_safe_retry_error(last_error)}; 已中止任务"
        )
        super().__init__(self.final_message)


def _safe_retry_error(error: Exception, limit: int = 320) -> str:
    text = str(error or "").strip() or error.__class__.__name__
    return text[:limit]


def _build_retry_message(
    step_name: str,
    attempt: int,
    max_attempts: int,
    error: Exception,
    *,
    is_terminal: bool,
) -> str:
    suffix = "已中止任务" if is_terminal else "准备重试"
    return (
        f"[{step_name}] 第 {attempt}/{max_attempts} 次失败: "
        f"{_safe_retry_error(error)}; {suffix}"
    )


def _classify_retry_error(exc_or_text: Any) -> Dict[str, Any]:
    text = str(exc_or_text or "").strip()
    lowered = text.lower()

    def _contains(*tokens: str) -> bool:
        return any(token in lowered for token in tokens if token)

    if _contains(
        "schema",
        "jsonschema",
        "validationerror",
        "pydantic",
        "type_error",
        "is not of type",
        "extra fields not permitted",
        "unexpected field",
    ):
        return {
            "code": "schema_hard_error",
            "category": "schema_validation",
            "retryable": False,
        }

    if _contains(
        "permission denied",
        "forbidden",
        "路径不在允许范围",
        "安全错误",
        "outside allowed scope",
        "write_scope_path_forbidden",
        "write_scope_not_allowed",
    ):
        return {
            "code": "permission_or_scope_error",
            "category": "permission",
            "retryable": False,
        }

    if _contains("timeout", "timed out", "超时", "deadline exceeded"):
        return {
            "code": "timeout_error",
            "category": "timeout",
            "retryable": True,
        }

    if _contains(
        "mcp",
        "adapter_unavailable",
        "domain_adapter_missing",
        "command_not_found",
        "mcp_tool_failed",
        "missing_mcp_stdio_command",
    ):
        return {
            "code": "mcp_runtime_error",
            "category": "mcp",
            "retryable": True,
        }

    if _contains(
        "connection reset",
        "connection aborted",
        "temporary failure",
        "network",
        "dns",
        "503",
        "502",
        "429",
        "too many requests",
        "rate limit",
    ):
        return {
            "code": "network_transient_error",
            "category": "network",
            "retryable": True,
        }

    if _contains(
        "参数校验失败",
        "必须提供",
        "missing required",
        "required field",
        "工具参数缺失",
        "missing parameter",
        "input_repaired",
    ):
        return {
            "code": "repairable_validation_error",
            "category": "validation_repairable",
            "retryable": True,
        }

    return {
        "code": "unknown_error",
        "category": "unknown",
        "retryable": True,
    }


def _detect_cancel_origin(task_id: str, error: Optional[BaseException] = None) -> str:
    # task_cancel 事件会先写入 _cancelled_tasks，优先视为用户取消。
    if is_task_cancelled(task_id):
        return "user"
    lowered = str(error or "").strip().lower()
    if "system_cancelled" in lowered or "cancel_origin=system" in lowered:
        return "system"
    # 无明确系统取消标识时，按用户取消处理，避免误重试。
    return "user"


_VERIFICATION_LEVEL_ALIASES = {
    "analysis_with_poc_plan": "analysis_with_poc_plan",
    "analysis_only": "analysis_with_poc_plan",
    "sandbox": "analysis_with_poc_plan",
    "generate_poc": "analysis_with_poc_plan",
    "poc_plan": "analysis_with_poc_plan",
}

HYBRID_TASK_NAME_MARKER = "[HYBRID]"
INTELLIGENT_TASK_NAME_MARKER = "[INTELLIGENT]"


def _normalize_verification_level(value: Optional[str]) -> str:
    raw_value = str(value or "").strip().lower()
    if not raw_value:
        return "analysis_with_poc_plan"
    return _VERIFICATION_LEVEL_ALIASES.get(raw_value, "analysis_with_poc_plan")


def _resolve_agent_task_source_mode(
    name: Optional[str],
    description: Optional[str],
) -> str:
    normalized_name = str(name or "").strip().lower()
    normalized_description = str(description or "").strip().lower()
    normalized_combined = f"{normalized_name} {normalized_description}"
    if (
        HYBRID_TASK_NAME_MARKER.lower() in normalized_combined
        or "混合扫描" in normalized_combined
    ):
        return "hybrid"
    if INTELLIGENT_TASK_NAME_MARKER.lower() in normalized_combined:
        return "intelligent"
    # 历史无 marker 任务，默认迁移为 hybrid。
    return "hybrid"


def _resolve_static_bootstrap_config(
    task: AgentTask,
    source_mode: str,
) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {
        "mode": "disabled",
        "opengrep_enabled": False,
        "gitleaks_enabled": False,
    }
    if source_mode == "hybrid":
        defaults = {
            "mode": "embedded",
            "opengrep_enabled": True,
            "gitleaks_enabled": False,
        }

    audit_scope = task.audit_scope if isinstance(task.audit_scope, dict) else {}
    static_bootstrap = (
        audit_scope.get("static_bootstrap")
        if isinstance(audit_scope.get("static_bootstrap"), dict)
        else {}
    )

    raw_mode = str(static_bootstrap.get("mode") or defaults["mode"]).strip().lower()
    mode = "embedded" if raw_mode == "embedded" else "disabled"
    if source_mode != "hybrid":
        mode = "disabled"

    opengrep_enabled = bool(
        static_bootstrap.get("opengrep_enabled", defaults["opengrep_enabled"])
    )
    gitleaks_enabled = bool(
        static_bootstrap.get("gitleaks_enabled", defaults["gitleaks_enabled"])
    )
    if mode == "disabled":
        opengrep_enabled = False
        gitleaks_enabled = False

    return {
        "mode": mode,
        "opengrep_enabled": opengrep_enabled,
        "gitleaks_enabled": gitleaks_enabled,
    }


def _parse_mcp_args(raw_args: Any) -> List[str]:
    if isinstance(raw_args, list):
        return [str(item) for item in raw_args if str(item).strip()]
    text = str(raw_args or "").strip()
    if not text:
        return []
    try:
        return [str(item) for item in shlex.split(text) if str(item).strip()]
    except Exception:
        return [item for item in text.split(" ") if item]


def _build_task_mcp_runtime(
    *,
    project_root: str,
    user_config: Optional[Dict[str, Any]],
    target_files: Optional[List[str]],
    bootstrap_findings: Optional[List[Dict[str, Any]]] = None,
    project_id: Optional[str] = None,
    prefer_stdio_when_http_unavailable: bool = False,
    active_mcp_ids: Optional[List[str]] = None,
    enforce_mcp_only: bool = False,
) -> MCPRuntime:
    from app.core.config import settings

    user_other_config = (user_config or {}).get("otherConfig", {})
    mcp_config = user_other_config.get("mcpConfig") if isinstance(user_other_config, dict) else {}
    if not isinstance(mcp_config, dict):
        mcp_config = {}
    write_policy = mcp_config.get("writePolicy") if isinstance(mcp_config.get("writePolicy"), dict) else {}
    if not isinstance(write_policy, dict):
        write_policy = {}

    hard_limit = max(1, int(getattr(settings, "MCP_WRITE_HARD_LIMIT", HARD_MAX_WRITABLE_FILES_PER_TASK)))
    configured_max = write_policy.get(
        "max_writable_files_per_task",
        getattr(settings, "MCP_DEFAULT_MAX_WRITABLE_FILES_PER_TASK", hard_limit),
    )
    try:
        max_writable_files = int(configured_max)
    except Exception:
        max_writable_files = int(getattr(settings, "MCP_DEFAULT_MAX_WRITABLE_FILES_PER_TASK", hard_limit))
    max_writable_files = max(1, min(max_writable_files, hard_limit))

    write_guard = TaskWriteScopeGuard(
        project_root=project_root,
        max_writable_files_per_task=max_writable_files,
        require_evidence_binding=bool(
            write_policy.get(
                "require_evidence_binding",
                getattr(settings, "MCP_REQUIRE_EVIDENCE_BINDING", True),
            )
        ),
        # hard lock: always forbid project-wide writes
        forbid_project_wide_writes=True,
    )
    write_guard.seed_from_task_inputs(
        target_files=target_files,
        findings=bootstrap_findings or [],
    )

    runtime_policy = mcp_config.get("runtimePolicy") if isinstance(mcp_config.get("runtimePolicy"), dict) else {}
    if not isinstance(runtime_policy, dict):
        runtime_policy = {}

    def _policy_for(name: str) -> Dict[str, Any]:
        candidate = runtime_policy.get(name)
        if isinstance(candidate, dict):
            return candidate
        return {}

    def _runtime_mode(name: str, setting_name: str, default: str = "backend_then_sandbox") -> str:
        policy_value = _policy_for(name).get("runtime_mode")
        if isinstance(policy_value, str) and policy_value.strip():
            return policy_value.strip()
        setting_value = getattr(settings, setting_name, default)
        return str(setting_value or default).strip() or default

    def _domain_enabled(
        name: str,
        domain: str,
        default_setting_name: str,
    ) -> bool:
        policy_value = _policy_for(name).get(f"{domain}_enabled")
        if isinstance(policy_value, bool):
            return policy_value
        return bool(getattr(settings, default_setting_name, False))

    def _ensure_writable_dir(path_value: Any, *, label: str) -> str:
        raw = str(path_value or "").strip()
        if not raw:
            raise RuntimeError(f"{label} 未配置持久化目录")
        candidate = raw
        if not os.path.isabs(candidate):
            candidate = os.path.normpath(os.path.join(project_root, candidate))
        try:
            os.makedirs(candidate, exist_ok=True)
        except Exception as exc:
            can_fallback = (
                os.path.isabs(candidate)
                and candidate.startswith("/app/")
                and not os.path.exists("/.dockerenv")
            )
            if not can_fallback:
                raise RuntimeError(f"{label} 创建目录失败: {candidate} ({exc})") from exc
            fallback_path = os.path.normpath(
                os.path.join(
                    project_root,
                    ".mcp_data",
                    candidate.lstrip("/"),
                )
            )
            try:
                os.makedirs(fallback_path, exist_ok=True)
            except Exception as fallback_exc:
                raise RuntimeError(
                    f"{label} 创建目录失败: {candidate} (fallback={fallback_path}, err={fallback_exc})"
                ) from fallback_exc
            candidate = fallback_path
        if not os.path.isdir(candidate):
            raise RuntimeError(f"{label} 不是目录: {candidate}")
        if not os.access(candidate, os.W_OK):
            raise RuntimeError(f"{label} 目录不可写: {candidate}")
        return candidate

    def _extract_indexer_path(args: List[str]) -> Optional[str]:
        for idx, item in enumerate(args):
            text = str(item or "").strip()
            if not text:
                continue
            if text.startswith("--indexer-path="):
                value = text.split("=", 1)[1].strip()
                return value or None
            if text == "--indexer-path" and idx + 1 < len(args):
                value = str(args[idx + 1] or "").strip()
                return value or None
        return None

    def _upsert_indexer_path(args: List[str], indexer_path: str) -> List[str]:
        updated = [str(item) for item in (args or [])]
        path_value = str(indexer_path or "").strip()
        if not path_value:
            return updated
        for idx, item in enumerate(updated):
            text = str(item or "").strip()
            if text.startswith("--indexer-path="):
                updated[idx] = f"--indexer-path={path_value}"
                return updated
            if text == "--indexer-path":
                if idx + 1 < len(updated):
                    updated[idx + 1] = path_value
                else:
                    updated.append(path_value)
                return updated
        updated.extend(["--indexer-path", path_value])
        return updated

    def _build_filesystem_args(raw_args: Any) -> List[str]:
        parsed = _parse_mcp_args(raw_args)
        if not parsed:
            parsed = ["dlx", "@modelcontextprotocol/server-filesystem"]
        last = str(parsed[-1] or "").strip() if parsed else ""
        looks_like_package_name = bool(last.startswith("@") and "/" in last)
        looks_like_mount_path = bool(
            last
            and not looks_like_package_name
            and not last.startswith("-")
            and (
                last in {".", "..", "./", "../"}
                or "/" in last
                or "\\" in last
                or last.startswith("~")
            )
        )
        if looks_like_mount_path:
            parsed = parsed[:-1]
        return [*parsed, str(project_root)]

    adapters: Dict[str, Any] = {}
    domain_adapters: Dict[str, Dict[str, Any]] = {}
    runtime_modes: Dict[str, str] = {}
    required_mcps: List[str] = []
    active_mcp_filter = {
        str(item).strip().lower()
        for item in (active_mcp_ids or [])
        if str(item).strip()
    }

    def _is_active_mcp(mcp_name: str) -> bool:
        if not active_mcp_filter:
            return True
        return str(mcp_name or "").strip().lower() in active_mcp_filter

    def _register_domain_adapter(name: str, domain: str, adapter: Any) -> None:
        domain_map = domain_adapters.setdefault(name, {})
        domain_map[domain] = adapter
        # Backward-compatible adapter map exposure for tests and diagnostics.
        if domain == "backend" or name not in adapters:
            adapters[name] = adapter

    def _choose_http_or_stdio_adapter(
        *,
        mcp_name: str,
        domain: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        stdio_command: str,
        stdio_args: List[str],
        allow_stdio_fallback: bool = True,
    ) -> Any:
        endpoint = str(url or "").strip()
        if endpoint:
            http_adapter = FastMCPHttpAdapter(
                url=endpoint,
                timeout=int(getattr(settings, "MCP_TIMEOUT_SECONDS", 30)),
                runtime_domain=domain,
                headers=headers,
            )
            if not allow_stdio_fallback:
                return http_adapter
            if (not prefer_stdio_when_http_unavailable) or http_adapter.is_available():
                return http_adapter
            logger.warning(
                "MCP endpoint unavailable; fallback to stdio (%s/%s -> %s)",
                mcp_name,
                domain,
                endpoint,
            )
        if not allow_stdio_fallback:
            return FastMCPHttpAdapter(
                url=endpoint,
                timeout=int(getattr(settings, "MCP_TIMEOUT_SECONDS", 30)),
                runtime_domain=domain,
                headers=headers,
            )
        return FastMCPStdioAdapter(
            command=str(stdio_command or "").strip(),
            args=[str(item) for item in (stdio_args or [])],
            cwd=project_root,
            timeout=int(getattr(settings, "MCP_TIMEOUT_SECONDS", 30)),
            runtime_domain=domain,
        )

    # ============ filesystem ============
    filesystem_backend_enabled = _domain_enabled("filesystem", "backend", "MCP_FILESYSTEM_ENABLED")
    filesystem_sandbox_enabled = _domain_enabled(
        "filesystem",
        "sandbox",
        "MCP_FILESYSTEM_SANDBOX_ENABLED",
    )
    if _is_active_mcp("filesystem") and (filesystem_backend_enabled or filesystem_sandbox_enabled):
        filesystem_force_stdio = bool(getattr(settings, "MCP_FILESYSTEM_FORCE_STDIO", True))
        filesystem_backend_url = "" if filesystem_force_stdio else resolve_filesystem_backend_url(settings)
        filesystem_sandbox_url = "" if filesystem_force_stdio else str(
            getattr(settings, "MCP_FILESYSTEM_SANDBOX_URL", "") or ""
        ).strip()
        if (not filesystem_force_stdio) and (not filesystem_sandbox_url):
            filesystem_sandbox_url = filesystem_backend_url
        if filesystem_backend_enabled:
            _register_domain_adapter(
                "filesystem",
                "backend",
                _choose_http_or_stdio_adapter(
                    mcp_name="filesystem",
                    domain="backend",
                    url=filesystem_backend_url,
                    stdio_command=str(getattr(settings, "MCP_FILESYSTEM_COMMAND", "pnpm") or "pnpm"),
                    stdio_args=_build_filesystem_args(
                        getattr(
                            settings,
                            "MCP_FILESYSTEM_ARGS",
                            "dlx @modelcontextprotocol/server-filesystem",
                        )
                    ),
                ),
            )
        if filesystem_sandbox_enabled:
            _register_domain_adapter(
                "filesystem",
                "sandbox",
                _choose_http_or_stdio_adapter(
                    mcp_name="filesystem",
                    domain="sandbox",
                    url=filesystem_sandbox_url,
                    stdio_command=str(getattr(settings, "MCP_FILESYSTEM_SANDBOX_COMMAND", "pnpm") or "pnpm"),
                    stdio_args=_build_filesystem_args(
                        getattr(
                            settings,
                            "MCP_FILESYSTEM_SANDBOX_ARGS",
                            "dlx @modelcontextprotocol/server-filesystem",
                        )
                    ),
                ),
            )
        runtime_modes["filesystem"] = _runtime_mode(
            "filesystem",
            "MCP_FILESYSTEM_RUNTIME_MODE",
        )

    # ============ code_index ============
    code_index_backend_enabled = _domain_enabled("code_index", "backend", "MCP_CODE_INDEX_ENABLED")
    code_index_sandbox_enabled = _domain_enabled(
        "code_index",
        "sandbox",
        "MCP_CODE_INDEX_SANDBOX_ENABLED",
    )
    if _is_active_mcp("code_index") and (code_index_backend_enabled or code_index_sandbox_enabled):
        code_index_backend_url = resolve_code_index_backend_url(settings)
        code_index_sandbox_url = str(getattr(settings, "MCP_CODE_INDEX_SANDBOX_URL", "") or "").strip()
        if not code_index_sandbox_url:
            code_index_sandbox_url = code_index_backend_url
        code_index_headers = (
            {"Mcp-Project-Path": str(project_root)}
            if str(project_root or "").strip()
            else {}
        )

        backend_code_index_args = _parse_mcp_args(
            getattr(settings, "MCP_CODE_INDEX_ARGS", "--indexer-path /app/data/mcp/code-index")
        )
        sandbox_code_index_args = _parse_mcp_args(
            getattr(settings, "MCP_CODE_INDEX_SANDBOX_ARGS", "--indexer-path /app/data/mcp/code-index")
        )
        if code_index_backend_enabled:
            backend_index_path = _extract_indexer_path(backend_code_index_args)
            ensured_backend_path = _ensure_writable_dir(
                backend_index_path or "/app/data/mcp/code-index",
                label="MCP_CODE_INDEX_ARGS.indexer_path",
            )
            backend_code_index_args = _upsert_indexer_path(backend_code_index_args, ensured_backend_path)
        if code_index_sandbox_enabled:
            sandbox_index_path = _extract_indexer_path(sandbox_code_index_args)
            ensured_sandbox_path = _ensure_writable_dir(
                sandbox_index_path or "/app/data/mcp/code-index",
                label="MCP_CODE_INDEX_SANDBOX_ARGS.indexer_path",
            )
            sandbox_code_index_args = _upsert_indexer_path(sandbox_code_index_args, ensured_sandbox_path)
        if code_index_backend_enabled:
            _register_domain_adapter(
                "code_index",
                "backend",
                _choose_http_or_stdio_adapter(
                    mcp_name="code_index",
                    domain="backend",
                    url=code_index_backend_url,
                    headers=code_index_headers,
                    stdio_command=str(getattr(settings, "MCP_CODE_INDEX_COMMAND", "code-index-mcp") or "code-index-mcp"),
                    stdio_args=backend_code_index_args,
                ),
            )
        if code_index_sandbox_enabled:
            _register_domain_adapter(
                "code_index",
                "sandbox",
                _choose_http_or_stdio_adapter(
                    mcp_name="code_index",
                    domain="sandbox",
                    url=code_index_sandbox_url,
                    headers=code_index_headers,
                    stdio_command=str(
                        getattr(settings, "MCP_CODE_INDEX_SANDBOX_COMMAND", "code-index-mcp") or "code-index-mcp"
                    ),
                    stdio_args=sandbox_code_index_args,
                ),
            )
        runtime_modes["code_index"] = _runtime_mode(
            "code_index",
            "MCP_CODE_INDEX_RUNTIME_MODE",
        )

    # ============ sequentialthinking ============
    sequential_backend_enabled = _domain_enabled(
        "sequentialthinking",
        "backend",
        "MCP_SEQUENTIAL_THINKING_ENABLED",
    )
    sequential_sandbox_enabled = _domain_enabled(
        "sequentialthinking",
        "sandbox",
        "MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED",
    )
    if _is_active_mcp("sequentialthinking") and (sequential_backend_enabled or sequential_sandbox_enabled):
        sequential_force_stdio = bool(
            getattr(settings, "MCP_SEQUENTIAL_THINKING_FORCE_STDIO", True)
        )
        sequential_backend_url = (
            ""
            if sequential_force_stdio
            else resolve_sequential_backend_url(settings)
        )
        sequential_sandbox_url = ""
        if not sequential_force_stdio:
            sequential_sandbox_url = str(
                getattr(settings, "MCP_SEQUENTIAL_THINKING_SANDBOX_URL", "") or ""
            ).strip()
            if not sequential_sandbox_url:
                sequential_sandbox_url = sequential_backend_url
        if sequential_backend_enabled:
            _register_domain_adapter(
                "sequentialthinking",
                "backend",
                _choose_http_or_stdio_adapter(
                    mcp_name="sequentialthinking",
                    domain="backend",
                    url=sequential_backend_url,
                    stdio_command=str(
                        getattr(
                            settings,
                            "MCP_SEQUENTIAL_THINKING_COMMAND",
                            "mcp-server-sequential-thinking",
                        )
                        or "mcp-server-sequential-thinking"
                    ),
                    stdio_args=_parse_mcp_args(
                        getattr(
                            settings,
                            "MCP_SEQUENTIAL_THINKING_ARGS",
                            "",
                        )
                    ),
                ),
            )
        if sequential_sandbox_enabled:
            _register_domain_adapter(
                "sequentialthinking",
                "sandbox",
                _choose_http_or_stdio_adapter(
                    mcp_name="sequentialthinking",
                    domain="sandbox",
                    url=sequential_sandbox_url,
                    stdio_command=str(
                        getattr(
                            settings,
                            "MCP_SEQUENTIAL_THINKING_SANDBOX_COMMAND",
                            "mcp-server-sequential-thinking",
                        )
                        or "mcp-server-sequential-thinking"
                    ),
                    stdio_args=_parse_mcp_args(
                        getattr(
                            settings,
                            "MCP_SEQUENTIAL_THINKING_SANDBOX_ARGS",
                            "",
                        )
                    ),
                ),
            )
        runtime_modes["sequentialthinking"] = _runtime_mode(
            "sequentialthinking",
            "MCP_SEQUENTIAL_THINKING_RUNTIME_MODE",
        )

    # ============ qmd ============
    qmd_backend_enabled = _domain_enabled("qmd", "backend", "MCP_QMD_ENABLED")
    qmd_sandbox_enabled = _domain_enabled("qmd", "sandbox", "MCP_QMD_SANDBOX_ENABLED")
    if _is_active_mcp("qmd") and (qmd_backend_enabled or qmd_sandbox_enabled):
        qmd_project_id = str(project_id or "default")
        qmd_prefix = str(getattr(settings, "QMD_COLLECTION_PREFIX", "project") or "project")
        qmd_glob = str(getattr(settings, "QMD_INDEX_GLOB", "**/*") or "**/*")
        qmd_lazy = bool(getattr(settings, "QMD_LAZY_INDEX_ENABLED", True))
        qmd_auto_embed = bool(getattr(settings, "QMD_AUTO_EMBED_ON_FIRST_USE", False))
        _ensure_writable_dir(
            getattr(settings, "QMD_DATA_DIR", "./data/qmd"),
            label="QMD_DATA_DIR",
        )
        qmd_backend_url = normalize_qmd_loopback_url(resolve_qmd_backend_url(settings))
        qmd_sandbox_url = normalize_qmd_loopback_url(
            str(getattr(settings, "MCP_QMD_SANDBOX_URL", "") or "").strip()
        )
        if not qmd_sandbox_url:
            qmd_sandbox_url = qmd_backend_url

        if qmd_backend_enabled:
            backend_qmd = _choose_http_or_stdio_adapter(
                mcp_name="qmd",
                domain="backend",
                url=qmd_backend_url,
                stdio_command=str(getattr(settings, "MCP_QMD_COMMAND", "qmd") or "qmd"),
                stdio_args=_parse_mcp_args(getattr(settings, "MCP_QMD_ARGS", "mcp")),
                allow_stdio_fallback=True,
            )
            _register_domain_adapter(
                "qmd",
                "backend",
                QmdLazyIndexAdapter(
                    adapter=backend_qmd,
                    project_root=project_root,
                    project_id=qmd_project_id,
                    command=str(getattr(settings, "MCP_QMD_COMMAND", "qmd") or "qmd"),
                    collection_prefix=qmd_prefix,
                    index_glob=qmd_glob,
                    lazy_enabled=qmd_lazy,
                    auto_embed_on_first_use=qmd_auto_embed,
                ),
            )
        if qmd_sandbox_enabled:
            sandbox_qmd = _choose_http_or_stdio_adapter(
                mcp_name="qmd",
                domain="sandbox",
                url=qmd_sandbox_url,
                stdio_command=str(getattr(settings, "MCP_QMD_SANDBOX_COMMAND", "qmd") or "qmd"),
                stdio_args=_parse_mcp_args(getattr(settings, "MCP_QMD_SANDBOX_ARGS", "mcp")),
                allow_stdio_fallback=True,
            )
            _register_domain_adapter(
                "qmd",
                "sandbox",
                QmdLazyIndexAdapter(
                    adapter=sandbox_qmd,
                    project_root=project_root,
                    project_id=qmd_project_id,
                    command=str(getattr(settings, "MCP_QMD_SANDBOX_COMMAND", "qmd") or "qmd"),
                    collection_prefix=qmd_prefix,
                    index_glob=qmd_glob,
                    lazy_enabled=qmd_lazy,
                    auto_embed_on_first_use=qmd_auto_embed,
                ),
            )
        runtime_modes["qmd"] = _runtime_mode("qmd", "MCP_QMD_RUNTIME_MODE")

    required_gate_mcps = ["filesystem", "code_index"]
    required_mcps = []
    for name in required_gate_mcps:
        normalized_name = str(name).strip()
        if not normalized_name or not _is_active_mcp(normalized_name):
            continue
        if normalized_name in domain_adapters or normalized_name in adapters:
            required_mcps.append(normalized_name)

    return MCPRuntime(
        enabled=bool(mcp_config.get("enabled", getattr(settings, "MCP_ENABLED", True))),
        prefer_mcp=(
            True
            if enforce_mcp_only
            else bool(mcp_config.get("preferMcp", getattr(settings, "MCP_PREFER", True)))
        ),
        adapters=adapters,
        domain_adapters=domain_adapters,
        runtime_modes=runtime_modes,
        required_mcps=required_mcps,
        write_scope_guard=write_guard,
        allow_filesystem_writes=False,
        default_runtime_mode=str(
            runtime_policy.get("default_mode", getattr(settings, "MCP_RUNTIME_MODE_DEFAULT", "backend_then_sandbox"))
            if isinstance(runtime_policy, dict)
            else getattr(settings, "MCP_RUNTIME_MODE_DEFAULT", "backend_then_sandbox")
        ),
        strict_mode=bool(
            True
            if enforce_mcp_only
            else mcp_config.get("strictMode", getattr(settings, "MCP_STRICT_MODE", True))
        ),
        project_root=project_root,
    )


async def _probe_required_mcp_runtime(
    runtime: MCPRuntime,
    *,
    runtime_domain: str = "all",
) -> Dict[str, Any]:
    INTERNAL_TOOLS = {
        "set_project_path",
        "configure_file_watcher",
        "refresh_index",
        "build_deep_index",
    }
    WRITE_TOOL_PREFIXES = ("write", "edit", "create", "move", "delete")
    CALL_RETRY_COUNT = 2
    CALL_BACKOFF_SECONDS = 0.3

    def _prepare_probe_context() -> Dict[str, Any]:
        project_root = str(getattr(runtime, "project_root", "") or "").strip()
        if not project_root:
            return {
                "project_root": "",
                "filesystem_probe_file": "README.md",
                "filesystem_media_probe_file": "tmp/.mcp_required_media_probe.png",
                "qmd_probe_file": "tmp/.mcp_required_qmd_probe.md",
                "code_probe_file": "tmp/.mcp_required_code_probe.c",
                "code_probe_function": "mcp_required_probe_sum",
                "code_probe_line": 2,
            }
        probe_dir = os.path.join(project_root, "tmp")
        os.makedirs(probe_dir, exist_ok=True)
        filesystem_probe_abs = os.path.join(probe_dir, ".mcp_required_filesystem_probe.txt")
        filesystem_media_abs = os.path.join(probe_dir, ".mcp_required_media_probe.png")
        code_probe_abs = os.path.join(probe_dir, ".mcp_required_code_probe.c")
        qmd_probe_abs = os.path.join(probe_dir, ".mcp_required_qmd_probe.md")
        try:
            with open(filesystem_probe_abs, "w", encoding="utf-8") as handle:
                handle.write("mcp required filesystem probe\n")
        except Exception:
            pass
        try:
            with open(filesystem_media_abs, "wb") as handle:
                handle.write(b"PNG")
        except Exception:
            pass
        try:
            with open(code_probe_abs, "w", encoding="utf-8") as handle:
                handle.write(
                    "#include <stdio.h>\n"
                    "int mcp_required_probe_sum(int a, int b) {\n"
                    "    return a + b;\n"
                    "}\n"
                )
        except Exception:
            pass
        try:
            with open(qmd_probe_abs, "w", encoding="utf-8") as handle:
                handle.write("# mcp required qmd probe\n")
        except Exception:
            pass
        return {
            "project_root": project_root,
            "filesystem_probe_file": os.path.relpath(filesystem_probe_abs, project_root).replace("\\", "/"),
            "filesystem_media_probe_file": os.path.relpath(filesystem_media_abs, project_root).replace("\\", "/"),
            "qmd_probe_file": os.path.relpath(qmd_probe_abs, project_root).replace("\\", "/"),
            "code_probe_file": os.path.relpath(code_probe_abs, project_root).replace("\\", "/"),
            "code_probe_function": "mcp_required_probe_sum",
            "code_probe_line": 2,
        }

    def _is_write_tool(tool_name: str) -> bool:
        normalized = str(tool_name or "").strip().lower()
        if not normalized:
            return True
        if normalized in INTERNAL_TOOLS:
            return True
        return normalized.startswith(WRITE_TOOL_PREFIXES)

    def _tool_priority(tool_name: str) -> int:
        normalized = str(tool_name or "").strip().lower()
        if not normalized:
            return -999
        if _is_write_tool(normalized):
            return -500
        score = 0
        if normalized.startswith(("search", "list", "read", "get", "status", "sequential")):
            score += 100
        if "summary" in normalized or "info" in normalized:
            score += 20
        if "media" in normalized:
            score -= 20
        return score

    required_mcps: List[str] = []
    if hasattr(runtime, "_required_mcp_names"):
        try:
            required_mcps = list(runtime._required_mcp_names())  # type: ignore[attr-defined]
        except Exception:
            required_mcps = []
    if not required_mcps:
        required_mcps = list(getattr(runtime, "required_mcps", []) or [])

    not_ready: List[Dict[str, Any]] = []
    details: Dict[str, Dict[str, Any]] = {}
    domain_value = str(runtime_domain or "all").strip().lower() or "all"
    probe_context = _prepare_probe_context()

    probe_runtime = runtime
    try:
        adapter_failure_threshold = max(
            6,
            int(getattr(runtime, "adapter_failure_threshold", 2) or 2) + 2,
        )
        probe_runtime = MCPRuntime(
            enabled=bool(getattr(runtime, "enabled", True)),
            prefer_mcp=bool(getattr(runtime, "prefer_mcp", True)),
            adapters=dict(getattr(runtime, "adapters", {}) or {}),
            domain_adapters=dict(getattr(runtime, "domain_adapters", {}) or {}),
            runtime_modes=dict(getattr(runtime, "runtime_modes", {}) or {}),
            required_mcps=list(getattr(runtime, "required_mcps", []) or []),
            write_scope_guard=getattr(runtime, "write_scope_guard", None),
            default_runtime_mode=str(
                getattr(runtime, "default_runtime_mode", "backend_then_sandbox")
                or "backend_then_sandbox"
            ),
            strict_mode=bool(getattr(runtime, "strict_mode", True)),
            adapter_failure_threshold=adapter_failure_threshold,
            project_root=probe_context.get("project_root"),
        )
    except Exception:
        probe_runtime = runtime

    for mcp_name in required_mcps:
        normalized_mcp = str(mcp_name or "").strip().lower()
        if not normalized_mcp:
            continue

        mcp_detail: Dict[str, Any] = {
            "probe_ready": False,
            "reason": "probe_not_started",
            "tools_list_success": False,
            "tools_call_success": False,
            "call_retry_count": CALL_RETRY_COUNT,
            "call_backoff_seconds": CALL_BACKOFF_SECONDS,
        }

        list_started = time.perf_counter()
        try:
            list_result = await probe_runtime.list_mcp_tools(normalized_mcp)
        except Exception as exc:
            list_result = {
                "success": False,
                "tools": [],
                "error": f"mcp_list_tools_failed:{exc}",
                "metadata": {},
            }
        list_duration_ms = int((time.perf_counter() - list_started) * 1000)

        list_metadata = list_result.get("metadata")
        if not isinstance(list_metadata, dict):
            list_metadata = {}
        list_runtime_domain = str(list_metadata.get("mcp_runtime_domain") or "").strip() or None
        discovered_tools = normalize_mcp_listed_tools(list_result.get("tools"))
        visible_tools = [
            tool
            for tool in discovered_tools
            if not _is_write_tool(str(tool.get("name") or ""))
        ]

        if not bool(list_result.get("success")):
            reason = str(list_result.get("error") or "mcp_tools_list_failed")
            mcp_detail.update(
                {
                    "probe_ready": False,
                    "reason": reason,
                    "tools_list_success": False,
                    "tools_list_duration_ms": list_duration_ms,
                    "mcp_runtime_domain": list_runtime_domain,
                }
            )
            details[normalized_mcp] = mcp_detail
            not_ready.append(
                {
                    "mcp": normalized_mcp,
                    "runtime_domain": list_runtime_domain or domain_value,
                    "reason": reason,
                    "step": "tools/list",
                }
            )
            continue

        mcp_detail["tools_list_success"] = True
        mcp_detail["tools_list_duration_ms"] = list_duration_ms
        mcp_detail["discovered_tools"] = [str(item.get("name") or "") for item in discovered_tools]

        if not visible_tools:
            reason = "mcp_probe_tool_unavailable"
            mcp_detail.update(
                {
                    "probe_ready": False,
                    "reason": reason,
                    "mcp_runtime_domain": list_runtime_domain,
                }
            )
            details[normalized_mcp] = mcp_detail
            not_ready.append(
                {
                    "mcp": normalized_mcp,
                    "runtime_domain": list_runtime_domain or domain_value,
                    "reason": reason,
                    "step": "tools/select",
                }
            )
            continue

        selected_tool = sorted(
            visible_tools,
            key=lambda item: _tool_priority(str(item.get("name") or "")),
            reverse=True,
        )[0]
        selected_tool_name = str(selected_tool.get("name") or "").strip()
        selected_input_schema = (
            dict(selected_tool.get("inputSchema"))
            if isinstance(selected_tool.get("inputSchema"), dict)
            else {}
        )

        tool_args, args_error = build_mcp_probe_tool_args(
            mcp_id=normalized_mcp,
            tool_name=selected_tool_name,
            input_schema=selected_input_schema,
            project_root=str(probe_context.get("project_root") or ""),
            filesystem_probe_file=str(probe_context.get("filesystem_probe_file") or "README.md"),
            filesystem_media_probe_file=str(
                probe_context.get("filesystem_media_probe_file") or "tmp/.mcp_required_media_probe.png"
            ),
            qmd_probe_file=str(probe_context.get("qmd_probe_file") or "tmp/.mcp_required_qmd_probe.md"),
            code_probe_file=str(probe_context.get("code_probe_file") or "tmp/.mcp_required_code_probe.c"),
            code_probe_function=str(probe_context.get("code_probe_function") or "mcp_required_probe_sum"),
            code_probe_line=int(probe_context.get("code_probe_line") or 2),
        )
        if args_error is not None or not isinstance(tool_args, dict):
            reason = str(args_error or "mcp_probe_arg_generation_failed")
            mcp_detail.update(
                {
                    "probe_ready": False,
                    "reason": reason,
                    "selected_tool": selected_tool_name,
                    "mcp_runtime_domain": list_runtime_domain,
                }
            )
            details[normalized_mcp] = mcp_detail
            not_ready.append(
                {
                    "mcp": normalized_mcp,
                    "runtime_domain": list_runtime_domain or domain_value,
                    "reason": reason,
                    "step": "tools/call",
                    "tool_name": selected_tool_name,
                }
            )
            continue

        total_attempts = 1 + int(CALL_RETRY_COUNT)
        last_error = "mcp_probe_call_failed"
        last_runtime_domain = list_runtime_domain
        call_ok = False
        for attempt in range(1, total_attempts + 1):
            call_started = time.perf_counter()
            try:
                call_result = await probe_runtime.call_mcp_tool(
                    mcp_name=normalized_mcp,
                    tool_name=selected_tool_name,
                    arguments=dict(tool_args),
                    agent_name="MCP_RUNTIME_PROBE",
                    alias_used=f"startup_probe:{selected_tool_name}",
                )
            except Exception as exc:
                call_result = None
                call_duration_ms = int((time.perf_counter() - call_started) * 1000)
                last_error = f"mcp_call_exception:{exc.__class__.__name__}"
                mcp_detail["tools_call_duration_ms"] = call_duration_ms
                if attempt < total_attempts:
                    await asyncio.sleep(CALL_BACKOFF_SECONDS)
                    continue
                break

            call_duration_ms = int((time.perf_counter() - call_started) * 1000)
            call_metadata = dict(call_result.metadata) if isinstance(call_result.metadata, dict) else {}
            call_runtime_domain = str(call_metadata.get("mcp_runtime_domain") or "").strip() or list_runtime_domain
            last_runtime_domain = call_runtime_domain
            if bool(call_result.handled and call_result.success):
                mcp_detail.update(
                    {
                        "probe_ready": True,
                        "reason": "probe_ok",
                        "tools_call_success": True,
                        "tools_call_duration_ms": call_duration_ms,
                        "selected_tool": selected_tool_name,
                        "mcp_runtime_domain": call_runtime_domain,
                        "attempt": attempt,
                        "max_attempts": total_attempts,
                    }
                )
                call_ok = True
                break

            last_error = str(call_result.error or "mcp_call_failed")
            mcp_detail.update(
                {
                    "tools_call_duration_ms": call_duration_ms,
                    "selected_tool": selected_tool_name,
                    "mcp_runtime_domain": call_runtime_domain,
                    "attempt": attempt,
                    "max_attempts": total_attempts,
                }
            )
            if attempt < total_attempts:
                await asyncio.sleep(CALL_BACKOFF_SECONDS)

        if call_ok:
            details[normalized_mcp] = mcp_detail
            continue

        mcp_detail.update(
            {
                "probe_ready": False,
                "reason": last_error,
                "tools_call_success": False,
            }
        )
        details[normalized_mcp] = mcp_detail
        not_ready.append(
            {
                "mcp": normalized_mcp,
                "runtime_domain": last_runtime_domain or domain_value,
                "reason": last_error,
                "step": "tools/call",
                "tool_name": selected_tool_name,
            }
        )

    return {
        "ready": len(not_ready) == 0,
        "runtime_domain": domain_value,
        "required_mcps": required_mcps,
        "not_ready": not_ready,
        "details": details,
    }


async def _run_with_retries(
    step_name: str,
    task_id: str,
    event_emitter: Any,
    func: Callable[[], Any],
    *,
    max_attempts: int = 3,
    retryable_predicate: Optional[Callable[[Exception], bool]] = None,
):
    """执行关键步骤并在失败时重试，重试耗尽后抛出 StepRetryExceededError。"""
    safe_attempts = max(1, int(max_attempts))

    for attempt in range(1, safe_attempts + 1):
        try:
            return await func()
        except asyncio.CancelledError as exc:
            cancel_origin = _detect_cancel_origin(task_id, exc)
            classification = {
                "code": "cancelled_user" if cancel_origin == "user" else "cancelled_system",
                "category": "cancel",
                "retryable": cancel_origin == "system",
            }
            retryable = bool(classification["retryable"])
            is_terminal = cancel_origin == "user" or attempt >= safe_attempts or not retryable
            message = (
                f"[{step_name}] 第 {attempt}/{safe_attempts} 次取消: "
                f"origin={cancel_origin}; {'已中止任务' if is_terminal else '准备重试'}"
            )
            metadata = {
                "task_id": task_id,
                "step_name": step_name,
                "attempt": attempt,
                "retry_attempt": attempt,
                "max_attempts": safe_attempts,
                "is_terminal": is_terminal,
                "retry_error_class": classification["code"],
                "retryable": retryable,
                "cancel_origin": cancel_origin,
            }
            if event_emitter:
                if is_terminal:
                    await event_emitter.emit_error(message, metadata=metadata)
                else:
                    await event_emitter.emit_warning(message, metadata=metadata)

            # 用户主动取消不做重试，直接中断。
            if cancel_origin == "user":
                raise

            if is_terminal:
                raise StepRetryExceededError(
                    step_name,
                    attempt,
                    RuntimeError("系统取消后重试耗尽"),
                    max_attempts=safe_attempts,
                ) from exc
            await asyncio.sleep(min(2, attempt))
            continue
        except Exception as exc:
            classification = _classify_retry_error(exc)
            retryable = bool(classification["retryable"])
            if retryable_predicate is not None:
                retryable = bool(retryable_predicate(exc)) and retryable
            is_terminal = attempt >= safe_attempts or not retryable
            message = _build_retry_message(
                step_name,
                attempt,
                safe_attempts,
                exc,
                is_terminal=is_terminal,
            )
            metadata = {
                "task_id": task_id,
                "step_name": step_name,
                "attempt": attempt,
                "retry_attempt": attempt,
                "max_attempts": safe_attempts,
                "is_terminal": is_terminal,
                "retry_error_class": classification["code"],
                "retryable": retryable,
                "cancel_origin": "none",
            }
            if event_emitter:
                if is_terminal:
                    await event_emitter.emit_error(message, metadata=metadata)
                else:
                    await event_emitter.emit_warning(message, metadata=metadata)
            if is_terminal:
                raise StepRetryExceededError(
                    step_name,
                    attempt,
                    exc,
                    max_attempts=safe_attempts,
                ) from exc
            await asyncio.sleep(min(2, attempt))

def _normalize_bootstrap_confidence(confidence: Any) -> Optional[str]:
    normalized = str(confidence or "").strip().upper()
    if normalized in {"HIGH", "MEDIUM", "LOW"}:
        return normalized
    return None


def _extract_bootstrap_rule_lookup_keys(check_id: Any) -> List[str]:
    raw_check_id = str(check_id or "").strip()
    if not raw_check_id:
        return []

    keys: List[str] = []

    def _append(value: str) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in keys:
            keys.append(normalized)

    _append(raw_check_id)
    if "." in raw_check_id:
        _append(raw_check_id.rsplit(".", 1)[-1])
    return keys


def _extract_bootstrap_payload_confidence(rule_data: Any) -> Optional[str]:
    if not isinstance(rule_data, dict):
        return None

    direct_confidence = _normalize_bootstrap_confidence(rule_data.get("confidence"))
    if direct_confidence:
        return direct_confidence

    extra = rule_data.get("extra")
    if isinstance(extra, dict):
        extra_confidence = _normalize_bootstrap_confidence(extra.get("confidence"))
        if extra_confidence:
            return extra_confidence

        extra_metadata = extra.get("metadata")
        if isinstance(extra_metadata, dict):
            metadata_confidence = _normalize_bootstrap_confidence(
                extra_metadata.get("confidence")
            )
            if metadata_confidence:
                return metadata_confidence

    metadata = rule_data.get("metadata")
    if isinstance(metadata, dict):
        metadata_confidence = _normalize_bootstrap_confidence(metadata.get("confidence"))
        if metadata_confidence:
            return metadata_confidence

    return None


def _parse_bootstrap_opengrep_output(stdout: str) -> List[Dict[str, Any]]:
    if not stdout or not stdout.strip():
        return []

    output = json.loads(stdout)
    if isinstance(output, dict):
        results = output.get("results", [])
    elif isinstance(output, list):
        results = output
    else:
        raise ValueError("Unexpected opengrep output type")

    if not isinstance(results, list):
        raise ValueError("Invalid opengrep results format")

    parsed: List[Dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            parsed.append(item)
    return parsed


def _build_bootstrap_confidence_map_from_rules(
    rules: List[OpengrepRule],
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for rule in rules:
        normalized_confidence = _normalize_bootstrap_confidence(
            getattr(rule, "confidence", None)
        )
        if not normalized_confidence:
            continue
        lookup_values = [getattr(rule, "id", None), getattr(rule, "name", None)]
        for raw_value in lookup_values:
            for key in _extract_bootstrap_rule_lookup_keys(raw_value):
                mapping[key] = normalized_confidence
    return mapping


def _normalize_bootstrap_finding_from_opengrep_payload(
    finding: Dict[str, Any],
    confidence_map: Dict[str, str],
    index: int,
) -> Dict[str, Any]:
    rule_data = finding if isinstance(finding, dict) else {}
    check_id = rule_data.get("check_id") or rule_data.get("id")

    confidence = _extract_bootstrap_payload_confidence(rule_data)
    if confidence is None:
        for key in _extract_bootstrap_rule_lookup_keys(check_id):
            mapped = confidence_map.get(key)
            if mapped:
                confidence = mapped
                break

    extra = rule_data.get("extra") if isinstance(rule_data.get("extra"), dict) else {}
    title = extra.get("message") or str(check_id or "OpenGrep 发现")
    description = extra.get("message") or ""
    file_path = str(rule_data.get("path") or "").strip()
    start_obj = rule_data.get("start")
    end_obj = rule_data.get("end")
    start_line = int(start_obj.get("line") or 0) if isinstance(start_obj, dict) else 0
    end_line = (
        int(end_obj.get("line") or start_line)
        if isinstance(end_obj, dict)
        else start_line
    )
    severity_text = str(extra.get("severity") or "INFO").strip().upper()
    code_snippet = extra.get("lines")

    return {
        "id": str(check_id or f"opengrep-{index}"),
        "title": str(title),
        "description": description,
        "file_path": file_path,
        "line_start": start_line or None,
        "line_end": end_line or None,
        "code_snippet": code_snippet,
        "severity": severity_text,
        "confidence": confidence,
        "vulnerability_type": str(check_id or "opengrep_rule"),
        "source": "opengrep_bootstrap",
    }


def _normalize_bootstrap_finding_from_gitleaks_payload(
    finding: Dict[str, Any],
    index: int,
) -> Dict[str, Any]:
    rule_id = str(finding.get("RuleID") or "gitleaks_secret").strip()
    description = str(finding.get("Description") or "Gitleaks 密钥泄露候选").strip()
    file_path = str(finding.get("File") or "").strip()
    start_line = int(finding.get("StartLine") or 0)
    end_line = int(finding.get("EndLine") or start_line)
    code_snippet = finding.get("Match") or finding.get("Secret")
    title = f"Gitleaks: {rule_id}" if rule_id else "Gitleaks 密钥泄露候选"

    return {
        "id": f"gitleaks-{index}",
        "title": title,
        "description": description,
        "file_path": file_path,
        "line_start": start_line or None,
        "line_end": end_line or None,
        "code_snippet": code_snippet,
        "severity": "ERROR",
        "confidence": "HIGH",
        "vulnerability_type": rule_id or "gitleaks_secret",
        "source": "gitleaks_bootstrap",
    }


def _filter_bootstrap_findings(
    normalized_findings: List[Dict[str, Any]],
    exclude_patterns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in normalized_findings:
        file_path = str(item.get("file_path") or "").strip()
        if file_path and _is_core_ignored_path(file_path, exclude_patterns):
            continue
        severity_value = str(item.get("severity") or "").upper()
        confidence_value = _normalize_bootstrap_confidence(item.get("confidence"))
        if severity_value != "ERROR":
            continue
        if confidence_value not in {"HIGH", "MEDIUM"}:
            continue
        copied = dict(item)
        copied["confidence"] = confidence_value
        filtered.append(copied)
    return filtered


async def _run_bootstrap_opengrep_scan(
    project_root: str,
    active_rules: List[OpengrepRule],
) -> List[Dict[str, Any]]:
    merged_rules: List[Dict[str, Any]] = []
    for rule in active_rules:
        try:
            parsed_yaml = yaml.safe_load(rule.pattern_yaml)
        except Exception:
            continue
        if not isinstance(parsed_yaml, dict):
            continue
        rule_items = parsed_yaml.get("rules")
        if not isinstance(rule_items, list):
            continue
        for item in rule_items:
            if isinstance(item, dict):
                merged_rules.append(item)

    if not merged_rules:
        raise ValueError("No executable opengrep rules found")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tf:
        yaml.dump({"rules": merged_rules}, tf, sort_keys=False, default_flow_style=False)
        merged_rule_path = tf.name

    try:
        cmd = ["opengrep", "--config", merged_rule_path, "--json", project_root]
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
        )
        findings = _parse_bootstrap_opengrep_output(result.stdout or "")
        if result.returncode != 0 and not findings:
            stderr_text = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"opengrep failed: {stderr_text[:300]}")
        return findings
    finally:
        try:
            os.unlink(merged_rule_path)
        except Exception:
            pass


def _parse_bootstrap_gitleaks_output(stdout: str) -> List[Dict[str, Any]]:
    if not stdout or not stdout.strip():
        return []
    output = json.loads(stdout)
    if isinstance(output, list):
        return [item for item in output if isinstance(item, dict)]
    if isinstance(output, dict):
        nested = output.get("findings")
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
    raise ValueError("Unexpected gitleaks output type")


async def _run_bootstrap_gitleaks_scan(
    project_root: str,
) -> List[Dict[str, Any]]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
        report_path = tf.name

    try:
        cmd = [
            "gitleaks",
            "detect",
            "--source",
            project_root,
            "--report-format",
            "json",
            "--report-path",
            report_path,
            "--exit-code",
            "0",
            "--no-git",
        ]
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
        )
        if result.returncode != 0:
            stderr_text = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"gitleaks failed: {stderr_text[:300]}")

        if not os.path.exists(report_path):
            return []
        with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
            report_content = f.read()
        return _parse_bootstrap_gitleaks_output(report_content)
    finally:
        try:
            os.unlink(report_path)
        except Exception:
            pass


def _dedupe_bootstrap_findings(
    findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    deduped: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, int, str, str]] = set()
    for item in findings:
        file_path = str(item.get("file_path") or "").strip()
        line_start = int(item.get("line_start") or 0)
        vuln_type = str(item.get("vulnerability_type") or "").strip()
        source = str(item.get("source") or "").strip()
        key = (file_path, line_start, vuln_type, source)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


async def _prepare_embedded_bootstrap_findings(
    db: AsyncSession,
    project_root: str,
    event_emitter: Any,
    exclude_patterns: Optional[List[str]] = None,
    opengrep_enabled: bool = True,
    gitleaks_enabled: bool = False,
) -> Tuple[List[Dict[str, Any]], Optional[str], str]:
    opengrep_candidates: List[Dict[str, Any]] = []
    gitleaks_candidates: List[Dict[str, Any]] = []
    opengrep_total_findings = 0
    gitleaks_total_findings = 0

    if not opengrep_enabled and not gitleaks_enabled:
        if event_emitter:
            await event_emitter.emit_info(
                "⏭️ 静态预扫未启用：返回空候选，继续后续流程",
                metadata={
                    "bootstrap": True,
                    "bootstrap_task_id": None,
                    "bootstrap_source": "disabled_empty_seed",
                    "bootstrap_total_findings": 0,
                    "bootstrap_candidate_count": 0,
                },
            )
        return [], None, "disabled_empty_seed"

    if opengrep_enabled:
        active_rules_result = await db.execute(
            select(OpengrepRule).where(OpengrepRule.is_active == True)
        )
        active_rules = active_rules_result.scalars().all()
        if not active_rules:
            if event_emitter:
                await event_emitter.emit_error(
                    "❌ OpenGrep 预处理失败：当前没有启用规则，无法继续智能审计"
                )
            raise RuntimeError("OpenGrep 预处理失败：当前没有启用规则")

        if event_emitter:
            await event_emitter.emit_info(
                "🧪 OpenGrep 内嵌预扫开始",
                metadata={
                    "bootstrap": True,
                    "bootstrap_task_id": None,
                    "bootstrap_source": "embedded_opengrep",
                    "bootstrap_total_findings": 0,
                    "bootstrap_candidate_count": 0,
                },
            )
        try:
            parsed_opengrep_findings = await _run_bootstrap_opengrep_scan(
                project_root,
                active_rules,
            )
        except FileNotFoundError as exc:
            if event_emitter:
                await event_emitter.emit_error("❌ OpenGrep 预处理失败：未安装 opengrep")
            raise RuntimeError("OpenGrep 预处理失败：未安装 opengrep") from exc
        except Exception as exc:
            if event_emitter:
                await event_emitter.emit_error(f"❌ OpenGrep 预处理失败：{str(exc)[:160]}")
            raise RuntimeError(f"OpenGrep 预处理失败：{str(exc)[:200]}") from exc

        opengrep_total_findings = len(parsed_opengrep_findings)
        confidence_map = _build_bootstrap_confidence_map_from_rules(active_rules)
        normalized_opengrep_findings = [
            _normalize_bootstrap_finding_from_opengrep_payload(
                finding,
                confidence_map,
                index,
            )
            for index, finding in enumerate(parsed_opengrep_findings)
            if isinstance(finding, dict)
        ]
        opengrep_candidates = _filter_bootstrap_findings(
            normalized_opengrep_findings,
            exclude_patterns=exclude_patterns,
        )

    if gitleaks_enabled:
        if event_emitter:
            await event_emitter.emit_info(
                "🧪 Gitleaks 内嵌预扫开始",
                metadata={
                    "bootstrap": True,
                    "bootstrap_task_id": None,
                    "bootstrap_source": "embedded_gitleaks",
                    "bootstrap_total_findings": 0,
                    "bootstrap_candidate_count": 0,
                },
            )
        try:
            parsed_gitleaks_findings = await _run_bootstrap_gitleaks_scan(project_root)
        except FileNotFoundError as exc:
            if event_emitter:
                await event_emitter.emit_error("❌ Gitleaks 预处理失败：未安装 gitleaks")
            raise RuntimeError("Gitleaks 预处理失败：未安装 gitleaks") from exc
        except Exception as exc:
            if event_emitter:
                await event_emitter.emit_error(f"❌ Gitleaks 预处理失败：{str(exc)[:160]}")
            raise RuntimeError(f"Gitleaks 预处理失败：{str(exc)[:200]}") from exc

        gitleaks_total_findings = len(parsed_gitleaks_findings)
        normalized_gitleaks_findings = [
            _normalize_bootstrap_finding_from_gitleaks_payload(finding, index)
            for index, finding in enumerate(parsed_gitleaks_findings)
            if isinstance(finding, dict)
        ]
        gitleaks_candidates = _filter_bootstrap_findings(
            normalized_gitleaks_findings,
            exclude_patterns=exclude_patterns,
        )

    merged_candidates = _dedupe_bootstrap_findings(
        [*opengrep_candidates, *gitleaks_candidates]
    )
    total_findings = opengrep_total_findings + gitleaks_total_findings

    if opengrep_enabled and gitleaks_enabled:
        bootstrap_source = "embedded_opengrep_gitleaks"
    elif opengrep_enabled:
        bootstrap_source = "embedded_opengrep"
    else:
        bootstrap_source = "embedded_gitleaks"

    if event_emitter:
        await event_emitter.emit_info(
            "✅ 内嵌静态预扫完成",
            metadata={
                "bootstrap": True,
                "bootstrap_task_id": None,
                "bootstrap_source": bootstrap_source,
                "bootstrap_total_findings": total_findings,
                "bootstrap_candidate_count": len(merged_candidates),
                "bootstrap_opengrep_total_findings": opengrep_total_findings,
                "bootstrap_opengrep_candidate_count": len(opengrep_candidates),
                "bootstrap_gitleaks_total_findings": gitleaks_total_findings,
                "bootstrap_gitleaks_candidate_count": len(gitleaks_candidates),
            },
        )
    return merged_candidates, None, bootstrap_source


MAX_SEED_FINDINGS = 25

_CORE_AUDIT_EXCLUDE_PATTERNS: List[str] = [
    "test/**",
    "tests/**",
    "**/test/**",
    "**/tests/**",
    ".*/**",
    "**/.*/**",
    "*config*.*",
    "**/*config*.*",
    "*settings*.*",
    "**/*settings*.*",
    ".env*",
    "**/.env*",
    "*.yml",
    "**/*.yml",
    "*.yaml",
    "**/*.yaml",
    "*.json",
    "**/*.json",
    "*.ini",
    "**/*.ini",
    "*.conf",
    "**/*.conf",
    "*.toml",
    "**/*.toml",
    "*.properties",
    "**/*.properties",
    "*.plist",
    "**/*.plist",
    "*.xml",
    "**/*.xml",
]


def _build_core_audit_exclude_patterns(
    user_patterns: Optional[List[str]],
) -> List[str]:
    merged: List[str] = []
    seen: Set[str] = set()
    raw_patterns = list(user_patterns or []) + _CORE_AUDIT_EXCLUDE_PATTERNS
    for raw in raw_patterns:
        if not isinstance(raw, str):
            continue
        normalized = raw.strip().replace("\\", "/")
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        merged.append(normalized)
    return merged


def _normalize_scan_path(path: str) -> str:
    normalized = str(path or "").replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while normalized.startswith("/"):
        normalized = normalized[1:]
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _path_components(path: str) -> List[str]:
    normalized = _normalize_scan_path(path)
    if not normalized:
        return []
    return [part for part in normalized.split("/") if part not in {"", ".", ".."}]


def _match_exclude_patterns(path: str, patterns: Optional[List[str]]) -> bool:
    import fnmatch

    normalized = _normalize_scan_path(path)
    basename = os.path.basename(normalized)
    for pattern in patterns or []:
        if not isinstance(pattern, str):
            continue
        candidate = pattern.strip().replace("\\", "/")
        if not candidate:
            continue
        if fnmatch.fnmatch(normalized, candidate) or fnmatch.fnmatch(basename, candidate):
            return True
    return False


def _is_core_ignored_path(
    path: str,
    exclude_patterns: Optional[List[str]] = None,
) -> bool:
    normalized = _normalize_scan_path(path)
    if not normalized:
        return False

    parts = _path_components(normalized)
    for part in parts[:-1]:
        lowered = part.lower()
        if lowered in {"test", "tests"}:
            return True
        if part.startswith("."):
            return True

    if parts:
        last = parts[-1]
        if last.lower() in {"test", "tests"}:
            return True
        if last.startswith("."):
            return True

    effective_patterns = _build_core_audit_exclude_patterns(exclude_patterns)
    if _match_exclude_patterns(normalized, effective_patterns):
        return True

    return False


def _normalize_seed_from_opengrep(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将 OpenGrep bootstrap 候选统一转换为 fixed-first 的 seed findings 格式。"""

    def map_severity(value: Any) -> str:
        raw = str(value or "").strip().upper()
        if raw == "ERROR":
            return "high"
        if raw == "WARNING":
            return "medium"
        if raw == "INFO":
            return "low"
        return "medium"

    def map_confidence(value: Any) -> float:
        if isinstance(value, (int, float)):
            return max(0.0, min(float(value), 1.0))
        raw = str(value or "").strip().upper()
        if raw == "HIGH":
            return 0.8
        if raw == "MEDIUM":
            return 0.7
        if raw == "LOW":
            return 0.4
        try:
            return max(0.0, min(float(raw), 1.0))
        except Exception:
            return 0.5

    seeds: List[Dict[str, Any]] = []
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file_path") or item.get("path") or "").strip()
        line_start = _to_int(item.get("line_start")) or _to_int(item.get("line")) or 1
        line_end = _to_int(item.get("line_end")) or line_start
        vuln_type = str(item.get("vulnerability_type") or item.get("check_id") or "opengrep_rule").strip()

        title = item.get("title") or item.get("description") or "OpenGrep 发现"
        description = item.get("description") or ""
        code_snippet = item.get("code_snippet") or item.get("code") or ""

        raw_severity = item.get("severity") or item.get("extra", {}).get("severity")
        raw_confidence = item.get("confidence")

        seeds.append(
            {
                "id": item.get("id"),
                "title": str(title).strip() if title is not None else "OpenGrep 发现",
                "description": str(description).strip(),
                "file_path": file_path,
                "line_start": int(line_start),
                "line_end": int(line_end),
                "code_snippet": str(code_snippet)[:2000],
                "severity": map_severity(raw_severity),
                "confidence": map_confidence(raw_confidence),
                "vulnerability_type": vuln_type or "opengrep_rule",
                "source": str(item.get("source") or "opengrep_bootstrap"),
                "needs_verification": True,
                # 保留原始 OpenGrep 标记，便于溯源
                "bootstrap_severity": str(raw_severity or "").strip(),
                "bootstrap_confidence": str(raw_confidence or "").strip(),
            }
        )

    # 去重与截断（按 file+line+type）
    seen: Set[Tuple[str, int, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for seed in seeds:
        key = (
            str(seed.get("file_path") or ""),
            int(seed.get("line_start") or 0),
            str(seed.get("vulnerability_type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(seed)

    deduped.sort(key=lambda s: (-float(s.get("confidence") or 0.0), str(s.get("file_path") or "")))
    return deduped[:MAX_SEED_FINDINGS]


def _discover_entry_points_deterministic(
    project_root: str,
    target_files: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """在 OpenGrep 候选为空时，确定性发现入口点（grep-like + AST 兜底）。"""
    import re

    root = Path(project_root)
    effective_exclude_patterns = _build_core_audit_exclude_patterns(exclude_patterns)

    include_set = (
        {_normalize_scan_path(path) for path in target_files if isinstance(path, str)}
        if target_files
        else None
    )

    code_exts = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".go",
        ".php",
        ".rb",
        ".rs",
        ".c",
        ".cc",
        ".cpp",
        ".h",
        ".hpp",
    }

    patterns: List[Tuple[str, re.Pattern[str]]] = [
        ("python_fastapi_route", re.compile(r"^\s*@(?:app|router)\.(get|post|put|delete|patch)\b", re.I)),
        ("python_flask_route", re.compile(r"^\s*@app\.route\b", re.I)),
        ("python_main", re.compile(r"__name__\s*==\s*[\"']__main__[\"']")),
        ("django_urlpatterns", re.compile(r"\burlpatterns\s*=")),
        ("express_route", re.compile(r"\b(app|router)\.(get|post|put|delete|patch)\s*\(", re.I)),
        ("node_listen", re.compile(r"\bapp\.listen\s*\(", re.I)),
        ("spring_mapping", re.compile(r"@\s*(RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\b")),
        ("spring_controller", re.compile(r"@\s*(RestController|Controller)\b")),
        ("go_http_handle", re.compile(r"\bhttp\.HandleFunc\s*\(", re.I)),
        ("laravel_route", re.compile(r"\bRoute::(get|post|put|delete|patch)\s*\(", re.I)),
    ]

    entry_points: List[Dict[str, Any]] = []
    entry_files: List[str] = []

    def consider_file(rel_path: str) -> bool:
        if include_set is not None and rel_path not in include_set:
            return False
        if _is_core_ignored_path(rel_path, effective_exclude_patterns):
            return False
        return True

    # 1) grep-like 入口点扫描（有限扫描，避免大仓库拖慢）
    max_scan_files = 600
    scanned = 0
    for dirpath, dirnames, filenames in os.walk(project_root):
        rel_dir = os.path.relpath(dirpath, project_root).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""
        dirnames[:] = [
            d
            for d in dirnames
            if not _is_core_ignored_path(
                f"{rel_dir}/{d}" if rel_dir else d,
                effective_exclude_patterns,
            )
        ]
        for name in filenames:
            ext = Path(name).suffix.lower()
            if ext not in code_exts:
                continue
            abs_path = Path(dirpath) / name
            try:
                rel = abs_path.relative_to(root).as_posix()
            except Exception:
                continue
            if _is_core_ignored_path(rel, effective_exclude_patterns):
                continue
            if not consider_file(_normalize_scan_path(rel)):
                continue
            scanned += 1
            if scanned > max_scan_files:
                break
            try:
                text = abs_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                for typ, pat in patterns:
                    m = pat.search(line)
                    if not m:
                        continue
                    method = None
                    if m.lastindex:
                        # best-effort: common patterns capture method in group(1) or group(2)
                        for gi in range(1, m.lastindex + 1):
                            g = m.group(gi)
                            if isinstance(g, str) and g.strip() and g.strip().lower() in {
                                "get",
                                "post",
                                "put",
                                "delete",
                                "patch",
                                "head",
                                "options",
                            }:
                                method = g.strip().lower()
                                break
                    entry_points.append(
                        {
                            "type": typ,
                            "file": rel,
                            "line": idx,
                            "method": method or "",
                            "evidence": stripped[:240],
                        }
                    )
                    if rel not in entry_files:
                        entry_files.append(rel)
                    if len(entry_points) >= 80:
                        break
                if len(entry_points) >= 80:
                    break
            if len(entry_points) >= 80:
                break
        if len(entry_points) >= 80 or scanned > max_scan_files:
            break

    # 2) AST 推断入口函数名（用于 flow pipeline 入口约束）
    entry_function_names: List[str] = []
    try:
        from app.services.agent.flow.lightweight.ast_index import ASTCallIndex

        ast_target_files = entry_files or (target_files or None)
        ast_index = ASTCallIndex(
            project_root=project_root,
            target_files=ast_target_files if isinstance(ast_target_files, list) else None,
        )
        inferred = ast_index.infer_entry_points()
        for sym in inferred or []:
            name = str(getattr(sym, "name", "")).strip()
            if name and name not in entry_function_names:
                entry_function_names.append(name)
            if len(entry_function_names) >= 80:
                break
    except Exception as exc:
        logger.debug("[EntryPoints] AST inference failed: %s", exc)

    return {
        "entry_points": entry_points,
        "entry_function_names": entry_function_names,
    }


async def _build_seed_from_entrypoints(
    project_root: str,
    target_vulns: Optional[List[str]],
    entry_function_names: List[str],
    exclude_patterns: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """基于入口点提示，使用 SmartScanTool 生成固定数量的 seed findings。"""
    from app.services.agent.tools import SmartScanTool

    severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    confidence_by_severity = {"critical": 0.9, "high": 0.8, "medium": 0.6, "low": 0.4, "info": 0.3}

    tool = SmartScanTool(project_root, exclude_patterns=exclude_patterns or [])
    result = await tool.execute(
        target=".",
        quick_mode=True,
        max_files=200,
        focus_vulnerabilities=target_vulns or None,
    )
    raw_findings = []
    if isinstance(result, object) and getattr(result, "success", False):
        metadata = getattr(result, "metadata", {}) or {}
        raw_findings = metadata.get("findings") if isinstance(metadata, dict) else []
    if not isinstance(raw_findings, list):
        raw_findings = []

    seeds: List[Dict[str, Any]] = []
    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        file_path = str(item.get("file_path") or "").strip()
        line_no = _to_int(item.get("line_number")) or 1
        vuln_type = str(item.get("vulnerability_type") or "potential_issue").strip() or "potential_issue"
        severity = str(item.get("severity") or "medium").strip().lower()
        if severity not in severity_weight:
            severity = "medium"
        confidence = float(confidence_by_severity.get(severity, 0.5))

        matched_line = str(item.get("matched_line") or "").strip()
        context = str(item.get("context") or "").strip()
        code_snippet = matched_line or context

        title = f"{vuln_type} 可疑点（入口点回退扫描）"
        description = f"SmartScan 模式匹配：{item.get('pattern_name') or ''}".strip()
        if context:
            description = f"{description}\n上下文：\n{context}".strip()

        seeds.append(
            {
                "title": title,
                "description": description[:1200],
                "file_path": file_path,
                "line_start": int(line_no),
                "line_end": int(line_no),
                "code_snippet": str(code_snippet)[:2000],
                "severity": severity,
                "confidence": confidence,
                "vulnerability_type": vuln_type,
                "source": "fallback_entrypoints_smart_scan",
                "needs_verification": True,
                # 🔥 flow pipeline 入口约束（函数名列表）
                "entry_points": list(entry_function_names[:20]),
            }
        )

    # 去重与截断（按严重度+置信度）
    seen: Set[Tuple[str, int, str]] = set()
    deduped: List[Dict[str, Any]] = []
    for seed in seeds:
        key = (
            str(seed.get("file_path") or ""),
            int(seed.get("line_start") or 0),
            str(seed.get("vulnerability_type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(seed)

    deduped.sort(
        key=lambda s: (
            -severity_weight.get(str(s.get("severity") or "medium").strip().lower(), 2),
            -float(s.get("confidence") or 0.0),
        )
    )
    return deduped[:MAX_SEED_FINDINGS]


def _merge_seed_and_agent_findings(
    seed_findings: List[Dict[str, Any]],
    agent_findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """合并 seed 与 agent findings。

    严格门禁模式下，不再将未匹配 seed 兜底入库，避免未验证候选泄漏到最终结果。
    """
    seed_findings = [f for f in (seed_findings or []) if isinstance(f, dict)]
    agent_findings = [f for f in (agent_findings or []) if isinstance(f, dict)]

    def key_for(f: Dict[str, Any]) -> Tuple[str, int, str]:
        file_path = str(f.get("file_path") or "").replace("\\", "/").strip()
        line_start = _to_int(f.get("line_start")) or _to_int(f.get("line")) or 0
        vuln_type = str(f.get("vulnerability_type") or "").strip().lower()
        title = str(f.get("title") or "").strip().lower()
        if file_path and line_start and vuln_type:
            return (file_path, int(line_start), vuln_type)
        return (file_path, int(line_start), title)

    seed_by_key: Dict[Tuple[str, int, str], Dict[str, Any]] = {key_for(f): f for f in seed_findings}
    used: Set[Tuple[str, int, str]] = set()

    merged: List[Dict[str, Any]] = []
    for f in agent_findings:
        k = key_for(f)
        seed = seed_by_key.get(k)
        if seed:
            used.add(k)
            merged.append({**seed, **f})  # LLM/Agent 输出覆盖 seed 的默认字段
        else:
            merged.append(f)

    # 最终去重（防止 agent_findings 内部重复）
    out: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, int, str]] = set()
    for f in merged:
        k = key_for(f)
        if k in seen:
            continue
        seen.add(k)
        out.append(f)
    return out


async def _execute_agent_task(task_id: str):
    """
    在后台执行 Agent 任务 - 使用动态 Agent 树架构
    
    架构：OrchestratorAgent 作为大脑，动态调度子 Agent
    """
    from app.services.agent.agents import OrchestratorAgent, ReconAgent, AnalysisAgent, VerificationAgent
    from app.services.agent.workflow import WorkflowOrchestratorAgent
    from app.services.agent.event_manager import EventManager, AgentEventEmitter
    from app.services.llm.service import LLMService, LLMConfigError
    from app.services.agent.core import agent_registry
    from app.services.agent.tools import SandboxManager
    from app.core.config import settings
    import time
    
    # 🔥 在任务最开始就初始化 Docker 沙箱管理器
    # 这样可以确保整个任务生命周期内使用同一个管理器，并且尽早发现 Docker 问题
    logger.info(f"🚀 Starting execution for task {task_id}")
    sandbox_manager = SandboxManager()
    await sandbox_manager.initialize()
    logger.info(f"🐳 Global Sandbox Manager initialized (Available: {sandbox_manager.is_available})")

    # 🔥 提前创建事件管理器，以便在克隆仓库和索引时发送实时日志
    from app.services.agent.event_manager import EventManager, AgentEventEmitter
    event_manager = EventManager(db_session_factory=async_session_factory)
    event_manager.create_queue(task_id)
    event_emitter = AgentEventEmitter(task_id, event_manager)
    _running_event_managers[task_id] = event_manager

    async with async_session_factory() as db:
        orchestrator = None
        mcp_runtime: Optional[MCPRuntime] = None
        memory_store = None
        markdown_memory: Dict[str, str] = {}
        qmd_task_kb = None
        start_time = time.time()

        async def _qmd_upsert_json(relative_path: str, payload: Any) -> bool:
            del relative_path, payload
            return False

        async def _qmd_upsert_text(relative_path: str, text: str) -> bool:
            del relative_path, text
            return False

        async def _qmd_update_index(force: bool = False) -> bool:
            del force
            return False

        try:
            # 获取任务
            task = await db.get(AgentTask, task_id, options=[selectinload(AgentTask.project)])
            if not task:
                logger.error(f"Task {task_id} not found")
                return

            # 获取项目
            project = task.project
            if not project:
                logger.error(f"Project not found for task {task_id}")
                return

            # 🔥 发送任务开始事件 - 使用 phase_start 让前端知道进入准备阶段
            await event_emitter.emit_phase_start("preparation", f"🚀 任务开始执行: {project.name}")

            # 更新任务阶段为准备中
            task.status = AgentTaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            task.current_phase = AgentTaskPhase.PLANNING  # preparation 对应 PLANNING
            await db.commit()

            # 获取用户配置（需要在获取项目根目录之前，以便传递 token）
            user_config = await _get_user_config(db, task.created_by)

            # 从用户配置中提取 token和SSH密钥（用于私有仓库克隆）
            other_config = (user_config or {}).get('otherConfig', {})
            github_token = other_config.get('githubToken') or settings.GITHUB_TOKEN
            gitlab_token = other_config.get('gitlabToken') or settings.GITLAB_TOKEN
            gitea_token = other_config.get('giteaToken') or settings.GITEA_TOKEN

            # 解密SSH私钥
            ssh_private_key = None
            if 'sshPrivateKey' in other_config:
                try:
                    encrypted_key = other_config['sshPrivateKey']
                    ssh_private_key = decrypt_sensitive_data(encrypted_key)
                    logger.info("成功解密SSH私钥")
                except Exception as e:
                    logger.warning(f"解密SSH私钥失败: {e}")

            # 获取项目根目录（传递任务指定的分支和认证 token/SSH密钥）
            # 🔥 传递 event_emitter 以发送克隆进度
            async def _prepare_project_root_once():
                return await _get_project_root(
                    project,
                    task_id,
                    task.branch_name,
                    github_token=github_token,
                    gitlab_token=gitlab_token,
                    gitea_token=gitea_token,  # 🔥 新增
                    ssh_private_key=ssh_private_key,  # 🔥 新增SSH密钥
                    event_emitter=event_emitter,  # 🔥 新增
                )

            project_root = await _run_with_retries(
                "PROJECT_PREPARATION",
                task_id,
                event_emitter,
                _prepare_project_root_once,
            )

            # 🔥 自动修正 target_files 路径
            # 如果发生了目录调整（例如 ZIP 解压后只有一层目录，root 被下移），
            # 原有的 target_files (如 "Prefix/file.php") 可能无法匹配。
            # 我们需要检测并移除这些无效的前缀。
            if task.target_files and len(task.target_files) > 0:
                # 1. 检查是否存在不匹配的文件
                all_exist = True
                for tf in task.target_files:
                    if not os.path.exists(os.path.join(project_root, tf)):
                        all_exist = False
                        break
                
                if not all_exist:
                    logger.info(f"Target files path mismatch detected in {project_root}")
                    # 尝试通过路径匹配来修复
                    # 获取当前根目录的名称
                    root_name = os.path.basename(project_root)
                    
                    new_target_files = []
                    fixed_count = 0
                    
                    for tf in task.target_files:
                        # 检查文件是否以 root_name 开头（例如 "PHP-Project/index.php" 而 root 是 ".../PHP-Project"）
                        if tf.startswith(root_name + "/"):
                            fixed_path = tf[len(root_name)+1:]
                            if os.path.exists(os.path.join(project_root, fixed_path)):
                                new_target_files.append(fixed_path)
                                fixed_count += 1
                                continue
                        
                        # 如果上面的没匹配，尝试暴力搜索（只针对未找到的文件）
                        # 这种情况比较少见，先保留原样或标记为丢失
                        if os.path.exists(os.path.join(project_root, tf)):
                            new_target_files.append(tf)
                        else:
                            # 尝试查看 tf 的 basename 是否在根目录直接存在（针对常见的最简情况）
                            basename = os.path.basename(tf)
                            if os.path.exists(os.path.join(project_root, basename)):
                                new_target_files.append(basename)
                                fixed_count += 1
                            else:
                                # 实在找不到，保留原样，让后续流程报错或忽略
                                new_target_files.append(tf)
                    
                    if fixed_count > 0:
                        logger.info(f"🔧 Auto-fixed {fixed_count} target file paths")
                        await event_emitter.emit_info(f"🔧 自动修正了 {fixed_count} 个目标文件的路径")
                        task.target_files = new_target_files
                        
            # 🔥 重新验证修正后的文件
            valid_target_files = []
            if task.target_files:
                for tf in task.target_files:
                    if os.path.exists(os.path.join(project_root, tf)):
                        valid_target_files.append(tf)
                    else:
                        logger.warning(f"⚠️ Target file not found: {tf}")
                
                if not valid_target_files:
                    logger.warning("❌ No valid target files found after adjustment!")
                    await event_emitter.emit_warning("⚠️ 警告：无法找到指定的目标文件，将扫描所有文件")
                    task.target_files = None  # 回退到全量扫描
                elif len(valid_target_files) < len(task.target_files):
                    logger.warning(f"⚠️ Partial target files missing. Found {len(valid_target_files)}/{len(task.target_files)}")
                    task.target_files = valid_target_files

            logger.info(f"🚀 Task {task_id} started with Dynamic Agent Tree architecture")

            # 🔥 获取项目根目录后检查取消
            if is_task_cancelled(task_id):
                logger.info(f"[Cancel] Task {task_id} cancelled after project preparation")
                raise asyncio.CancelledError("任务已取消")

            async def _qmd_upsert_json(relative_path: str, payload: Any) -> bool:
                if qmd_task_kb is None:
                    return False
                try:
                    return bool(
                        await asyncio.to_thread(
                            qmd_task_kb.upsert_json,
                            relative_path,
                            payload,
                        )
                    )
                except Exception as exc:
                    logger.warning("[QMD TaskKB] upsert_json failed (%s): %s", relative_path, exc)
                    return False

            async def _qmd_upsert_text(relative_path: str, text: str) -> bool:
                if qmd_task_kb is None:
                    return False
                try:
                    return bool(
                        await asyncio.to_thread(
                            qmd_task_kb.upsert_text,
                            relative_path,
                            text,
                        )
                    )
                except Exception as exc:
                    logger.warning("[QMD TaskKB] upsert_text failed (%s): %s", relative_path, exc)
                    return False

            async def _qmd_update_index(force: bool = False) -> bool:
                if qmd_task_kb is None:
                    return False
                try:
                    result = await asyncio.to_thread(qmd_task_kb.update_index, force=bool(force))
                except Exception as exc:
                    logger.warning("[QMD TaskKB] update_index failed: %s", exc)
                    return False
                if not bool(result.get("success")):
                    logger.warning("[QMD TaskKB] update_index unsuccessful: %s", result.get("error"))
                    return False
                return bool(result.get("updated")) or bool(force)

            if bool(getattr(settings, "QMD_TASK_KB_ENABLED", True)):
                try:
                    from app.services.agent.qmd.task_kb import QmdTaskKnowledgeBase

                    qmd_task_kb = QmdTaskKnowledgeBase(
                        project_root=project_root,
                        task_id=task_id,
                        command=str(
                            getattr(settings, "QMD_CLI_COMMAND", "qmd") or "qmd"
                        ),
                        task_root_rel=str(getattr(settings, "QMD_TASK_ROOT_REL", ".deepaudit/qmd") or ".deepaudit/qmd"),
                        collection_prefix=str(getattr(settings, "QMD_TASK_COLLECTION_PREFIX", "task") or "task"),
                        doc_glob=str(
                            getattr(
                                settings,
                                "QMD_TASK_DOC_GLOB",
                                "**/*.{md,txt,json,yml,yaml}",
                            )
                            or "**/*.{md,txt,json,yml,yaml}"
                        ),
                        auto_embed=bool(getattr(settings, "QMD_TASK_AUTO_EMBED", False)),
                        query_cache=bool(getattr(settings, "QMD_TASK_QUERY_CACHE", True)),
                        timeout_seconds=int(getattr(settings, "QMD_CLI_TIMEOUT_SECONDS", 120) or 120),
                    )
                    qmd_ready_result = await asyncio.to_thread(qmd_task_kb.ensure_ready)
                    if bool(qmd_ready_result.get("success")):
                        await event_emitter.emit_info(
                            f"🧠 QMD 任务知识库已启用: {qmd_task_kb.task_root}"
                        )
                        await _qmd_upsert_json(
                            "artifacts/task_context.json",
                            {
                                "task_id": task_id,
                                "project_id": str(project.id),
                                "project_name": project.name,
                                "project_root": project_root,
                                "target_files_count": len(task.target_files or []),
                            },
                        )
                        await _qmd_update_index(force=False)
                    else:
                        qmd_task_kb = None
                        await event_emitter.emit_warning(
                            "⚠️ QMD 任务知识库初始化失败，已降级为普通审计流程"
                        )
                        logger.warning(
                            "[QMD TaskKB] ensure_ready failed: %s",
                            qmd_ready_result.get("error"),
                        )
                except Exception as exc:
                    qmd_task_kb = None
                    logger.warning("[QMD TaskKB] initialize failed: %s", exc)
                    await event_emitter.emit_warning(
                        "⚠️ QMD 任务知识库初始化失败，已降级为普通审计流程"
                    )

            # 创建 LLM 服务
            llm_service = LLMService(user_config=user_config)
            try:
                _ = llm_service.config
            except LLMConfigError as cfg_exc:
                cfg_message = f"LLM配置校验失败：{cfg_exc}"
                await event_emitter.emit_error(
                    cfg_message,
                    metadata={
                        "step_name": "LLM_CONFIG_VALIDATION",
                        "is_terminal": True,
                    },
                )
                raise RuntimeError(cfg_message) from cfg_exc

            # 初始化工具集 - 传递排除模式和目标文件以及预初始化的 sandbox_manager
            # 🔥 传递 event_emitter 以发送索引进度，传递 task_id 以支持取消
            task.current_phase = AgentTaskPhase.INDEXING
            await db.commit()

            # 🔥 创建漏洞队列服务
            from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
            from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue
            queue_service = InMemoryVulnerabilityQueue()
            recon_queue_service = InMemoryReconRiskQueue()
            _running_queue_services[task_id] = queue_service
            _running_recon_queue_services[task_id] = recon_queue_service
            logger.info(f"[Queue] Created InMemoryVulnerabilityQueue for task {task_id}")
            logger.info(f"[ReconQueue] Created InMemoryReconRiskQueue for task {task_id}")
            await event_emitter.emit_info("🔄 漏洞队列服务已初始化（内存模式）")
            await event_emitter.emit_info("🔎 Recon 风险点队列已初始化（内存模式）")

            async def _initialize_tools_once():
                return await _initialize_tools(
                    project_root,
                    llm_service,
                    user_config,
                    sandbox_manager=sandbox_manager,
                    verification_level=task.verification_level or "analysis_with_poc_plan",
                    exclude_patterns=task.exclude_patterns,
                    target_files=task.target_files,
                    project_id=str(project.id),  # 🔥 传递 project_id 用于 RAG
                    event_emitter=event_emitter,  # 🔥 新增
                    task_id=task_id,  # 🔥 新增：用于取消检查
                    qmd_task_kb=qmd_task_kb,
                    queue_service=queue_service,  # 🔥 新增：漏洞队列服务
                    recon_queue_service=recon_queue_service,  # 🔥 新增：Recon 风险队列服务
                )

            tools = await _run_with_retries(
                "RAG_INDEX_AND_TOOLS_INIT",
                task_id,
                event_emitter,
                _initialize_tools_once,
            )
            task.current_step = "索引已完成，进入分析阶段"
            await db.commit()

            mcp_runtime = _build_task_mcp_runtime(
                project_root=project_root,
                user_config=user_config,
                target_files=task.target_files,
                bootstrap_findings=None,
                project_id=str(project.id),
                prefer_stdio_when_http_unavailable=True,
                enforce_mcp_only=True,
            )

            if mcp_runtime and hasattr(mcp_runtime, "register_local_tools"):
                local_proxy_registry: Dict[str, Any] = {}
                for bucket_name in ("recon", "analysis", "verification", "orchestrator"):
                    bucket_tools = tools.get(bucket_name)
                    if not isinstance(bucket_tools, dict):
                        continue
                    for tool_name, tool_obj in bucket_tools.items():
                        normalized_name = str(tool_name or "").strip()
                        if not normalized_name or not hasattr(tool_obj, "execute"):
                            continue
                        local_proxy_registry[normalized_name] = tool_obj
                registered_local_tools = mcp_runtime.register_local_tools(local_proxy_registry)
                await event_emitter.emit_info(
                    f"🧩 MCP Local-Proxy 已注册 {registered_local_tools} 个本地工具"
                )

            if mcp_runtime:
                adapter_entries: List[str] = []
                domain_adapters = getattr(mcp_runtime, "domain_adapters", {}) or {}
                if isinstance(domain_adapters, dict):
                    for mcp_name, domain_map in sorted(domain_adapters.items()):
                        if not isinstance(domain_map, dict) or not domain_map:
                            continue
                        domains = ",".join(sorted(str(domain).strip() for domain in domain_map.keys() if str(domain).strip()))
                        if domains:
                            adapter_entries.append(f"{mcp_name}[{domains}]")
                if not adapter_entries:
                    flat_adapters = getattr(mcp_runtime, "adapters", {}) or {}
                    if isinstance(flat_adapters, dict):
                        adapter_entries = sorted(str(name).strip() for name in flat_adapters.keys() if str(name).strip())
                adapters_text = ", ".join(adapter_entries) if adapter_entries else "(none)"
                await event_emitter.emit_info(
                    "🛰️ MCP Runtime 已就绪: "
                    f"strict_mode={bool(getattr(mcp_runtime, 'strict_mode', False))}, "
                    f"prefer_mcp={bool(getattr(mcp_runtime, 'prefer_mcp', True))}, "
                    f"adapters={adapters_text}"
                )

            # MCP 启动门禁：默认可启动，仅 required MCP 明确未就绪时阻断。
            if (
                mcp_runtime
                and bool(getattr(settings, "MCP_REQUIRE_ALL_READY_ON_STARTUP", True))
            ):
                required_gate_mcps = [
                    str(item).strip()
                    for item in (getattr(mcp_runtime, "required_mcps", []) or [])
                    if str(item).strip()
                ]
                if bool(getattr(settings, "MCP_DAEMON_AUTOSTART", False)) and required_gate_mcps:
                    daemon_manager = MCPDaemonManager()
                    daemon_specs = {
                        spec.name: spec
                        for spec in daemon_manager.build_specs(
                            settings,
                            project_root=project_root,
                        )
                    }
                    prewarm_not_ready: list[str] = []
                    for daemon_name in required_gate_mcps:
                        if (
                            daemon_name == "filesystem"
                            and bool(getattr(settings, "MCP_FILESYSTEM_FORCE_STDIO", True))
                        ):
                            continue
                        spec = daemon_specs.get(daemon_name)
                        if spec is None:
                            prewarm_not_ready.append(f"{daemon_name}:spec_missing")
                            continue
                        timeout_seconds = max(
                            5,
                            int(getattr(spec, "startup_timeout_seconds", 10) or 10) + 2,
                        )
                        try:
                            launch_result = await asyncio.wait_for(
                                asyncio.to_thread(daemon_manager.ensure_daemon, spec),
                                timeout=timeout_seconds,
                            )
                        except asyncio.TimeoutError:
                            prewarm_not_ready.append(f"{daemon_name}:prewarm_timeout")
                            continue
                        if not bool(getattr(launch_result, "ready", False)):
                            reason = str(getattr(launch_result, "reason", "") or "prewarm_failed")
                            prewarm_not_ready.append(f"{daemon_name}:{reason}")
                    if prewarm_not_ready:
                        await event_emitter.emit_warning(
                            "⚠️ required MCP 预热未全部就绪: "
                            + "; ".join(prewarm_not_ready[:8])
                        )
                    else:
                        await event_emitter.emit_info(
                            "✅ required MCP daemon 预热完成"
                        )

                required_domain = str(
                    getattr(settings, "MCP_REQUIRED_RUNTIME_DOMAIN", "all") or "all"
                ).strip().lower()
                readiness = mcp_runtime.ensure_all_mcp_ready(required_domain)
                if not bool(readiness.get("ready")):
                    not_ready = readiness.get("not_ready") or []
                    detail = "; ".join(
                        f"{item.get('mcp')}@{item.get('runtime_domain')}:{item.get('reason')}"
                        for item in not_ready[:10]
                        if isinstance(item, dict)
                    )
                    message = (
                        "MCP 启动检查失败：required MCP 未就绪，任务已阻断。"
                        + (f" 明细: {detail}" if detail else "")
                    )
                    await event_emitter.emit_error(
                        message,
                        metadata={
                            "mcp_ready": False,
                            "mcp_required_unavailable": True,
                            "mcp_required_domain": required_domain,
                            "mcp_not_ready": not_ready,
                            "required": readiness.get("required_mcps") or [],
                            "runtime_domain": required_domain,
                        },
                    )
                    raise RuntimeError(message)

                probe_result = await _probe_required_mcp_runtime(
                    mcp_runtime,
                    runtime_domain=required_domain,
                )
                if not bool(probe_result.get("ready")):
                    probe_not_ready = probe_result.get("not_ready") or []
                    probe_detail = "; ".join(
                        f"{item.get('mcp')}@{item.get('runtime_domain')}:{item.get('reason')}"
                        for item in probe_not_ready[:10]
                        if isinstance(item, dict)
                    )
                    probe_message = (
                        "MCP 运行时自检失败：required MCP probe 不可用，任务已阻断。"
                        + (f" 明细: {probe_detail}" if probe_detail else "")
                    )
                    await event_emitter.emit_error(
                        probe_message,
                        metadata={
                            "mcp_probe_ready": False,
                            "mcp_probe_not_ready": probe_not_ready,
                            "mcp_probe_details": probe_result.get("details") or {},
                            "required": probe_result.get("required_mcps") or [],
                            "runtime_domain": required_domain,
                        },
                    )
                    raise RuntimeError(probe_message)
                await event_emitter.emit_info("✅ MCP 启动检查与运行时自检通过")

            # 🔥 初始化工具后检查取消
            if is_task_cancelled(task_id):
                logger.info(f"[Cancel] Task {task_id} cancelled after tools initialization")
                raise asyncio.CancelledError("任务已取消")

            # 创建子 Agent
            recon_agent = ReconAgent(
                llm_service=llm_service,
                tools=tools.get("recon", {}),
                event_emitter=event_emitter,
            )

            analysis_agent = AnalysisAgent(
                llm_service=llm_service,
                tools=tools.get("analysis", {}),
                event_emitter=event_emitter,
            )

            verification_agent = VerificationAgent(
                llm_service=llm_service,
                tools=tools.get("verification", {}),
                event_emitter=event_emitter,
            )

            audit_runtime_metadata = {
                "smart_audit_mode": True,
                "audit_mode": "smart_audit",
                "disable_virtual_routing": True,
                "mcp_only_enforced": True,
                "read_scope_policy": "strict_anchor",
            }

            for agent in (recon_agent, analysis_agent, verification_agent):
                if isinstance(getattr(agent.config, "metadata", None), dict):
                    agent.config.metadata.update(audit_runtime_metadata)
                if hasattr(agent, "set_mcp_runtime"):
                    agent.set_mcp_runtime(mcp_runtime)

            # 创建 Orchestrator Agent（使用确定性 Workflow 版本，注入两个队列服务）
            orchestrator = WorkflowOrchestratorAgent(
                llm_service=llm_service,
                tools=tools.get("orchestrator", {}),
                event_emitter=event_emitter,
                sub_agents={
                    "recon": recon_agent,
                    "analysis": analysis_agent,
                    "verification": verification_agent,
                },
                recon_queue_service=recon_queue_service,
                vuln_queue_service=queue_service,
            )
            if isinstance(getattr(orchestrator.config, "metadata", None), dict):
                orchestrator.config.metadata.update(audit_runtime_metadata)
            if hasattr(orchestrator, "set_mcp_runtime"):
                orchestrator.set_mcp_runtime(mcp_runtime)

            # 🔥 设置外部取消检查回调
            # 这确保即使 runner.cancel() 失败，Agent 也能通过 checking 全局标志感知取消
            def check_global_cancel():
                return is_task_cancelled(task_id)

            orchestrator.set_cancel_callback(check_global_cancel)
            # 同时也为子 Agent 设置（虽然 Orchestrator 会传播）
            recon_agent.set_cancel_callback(check_global_cancel)
            analysis_agent.set_cancel_callback(check_global_cancel)
            verification_agent.set_cancel_callback(check_global_cancel)

            # 注册到全局
            _running_orchestrators[task_id] = orchestrator
            _running_tasks[task_id] = orchestrator  # 兼容旧的取消逻辑
            _running_event_managers[task_id] = event_manager  # 用于 SSE 流
            
            # 🔥 清理旧的 Agent 注册表，避免显示多个树
            from app.services.agent.core import agent_registry
            agent_registry.clear()
            
            # 注册 Orchestrator 到 Agent Registry（使用其内置方法）
            orchestrator._register_to_registry(task="Root orchestrator for security audit")
            
            await event_emitter.emit_info("🧠 动态 Agent 树架构启动")
            await event_emitter.emit_info(f"📁 项目路径: {project_root}")
            
            # 收集项目信息 - 传递排除模式和目标文件
            project_info = await _collect_project_info(
                project_root, 
                project.name,
                exclude_patterns=task.exclude_patterns,
                target_files=task.target_files,
            )
            task.current_phase = AgentTaskPhase.RECONNAISSANCE
            await db.commit()

            bootstrap_findings: List[Dict[str, Any]] = []
            bootstrap_task_id: Optional[str] = None
            bootstrap_source = "disabled"
            source_mode = _resolve_agent_task_source_mode(task.name, task.description)
            static_bootstrap_config = _resolve_static_bootstrap_config(task, source_mode)

            if static_bootstrap_config["mode"] == "embedded":
                async def _prepare_bootstrap_once():
                    return await _prepare_embedded_bootstrap_findings(
                        db=db,
                        project_root=project_root,
                        event_emitter=event_emitter,
                        exclude_patterns=task.exclude_patterns,
                        opengrep_enabled=bool(
                            static_bootstrap_config.get("opengrep_enabled")
                        ),
                        gitleaks_enabled=bool(
                            static_bootstrap_config.get("gitleaks_enabled")
                        ),
                    )

                (
                    bootstrap_findings,
                    bootstrap_task_id,
                    bootstrap_source,
                ) = await _run_with_retries(
                    "STATIC_BOOTSTRAP",
                    task_id,
                    event_emitter,
                    _prepare_bootstrap_once,
                )
            else:
                await event_emitter.emit_info(
                    "ℹ️ 当前任务未启用静态预扫，直接进入入口点回退流程",
                    metadata={
                        "bootstrap": True,
                        "bootstrap_task_id": None,
                        "bootstrap_source": "disabled",
                        "bootstrap_total_findings": 0,
                        "bootstrap_candidate_count": 0,
                    },
                )

            # ============ 🔥 Fixed-First: 生成种子候选（OpenGrep 优先，空则入口点回退） ============
            seed_findings: List[Dict[str, Any]] = []
            entry_points_payload: List[Dict[str, Any]] = []
            entry_function_names: List[str] = []

            if bootstrap_findings:
                seed_findings = _normalize_seed_from_opengrep(bootstrap_findings)
                await event_emitter.emit_info(
                    f"🌱 固定种子候选已生成（静态预扫）：{len(seed_findings)} 条"
                )
            else:
                if bootstrap_source == "disabled":
                    await event_emitter.emit_info(
                        "ℹ️ 静态预扫未启用，启动入口点回退流程"
                    )
                else:
                    await event_emitter.emit_warning(
                        "⚠️ 静态预扫未筛选出 ERROR + HIGH/MEDIUM 候选，启动入口点回退流程"
                    )
                entry = _discover_entry_points_deterministic(
                    project_root=project_root,
                    target_files=task.target_files,
                    exclude_patterns=task.exclude_patterns,
                )
                entry_points_payload = (
                    entry.get("entry_points") if isinstance(entry, dict) else []
                ) or []
                entry_function_names = (
                    entry.get("entry_function_names") if isinstance(entry, dict) else []
                ) or []

                seed_findings = await _build_seed_from_entrypoints(
                    project_root=project_root,
                    target_vulns=task.target_vulnerabilities or [],
                    entry_function_names=entry_function_names,
                    exclude_patterns=task.exclude_patterns or [],
                )

                bootstrap_source = "fallback_entrypoints"
                await event_emitter.emit_info(
                    f"🌱 固定种子候选已生成（入口点回退）：entry_points={len(entry_points_payload)}，"
                    f"entry_funcs={len(entry_function_names)}，seeds={len(seed_findings)}"
                )

            await _qmd_upsert_json("artifacts/project_info.json", project_info)
            await _qmd_upsert_json(
                "artifacts/bootstrap_seed.json",
                {
                    "bootstrap_source": bootstrap_source,
                    "bootstrap_task_id": bootstrap_task_id,
                    "bootstrap_findings_count": len(bootstrap_findings or []),
                    "seed_findings_count": len(seed_findings or []),
                    "entry_points_count": len(entry_points_payload or []),
                    "entry_function_names_count": len(entry_function_names or []),
                    "target_vulnerabilities": list(task.target_vulnerabilities or []),
                },
            )
            await _qmd_update_index(force=False)

            if mcp_runtime:
                seed_paths: List[str] = []
                for item in seed_findings:
                    if isinstance(item, dict):
                        file_path = item.get("file_path")
                        if isinstance(file_path, str) and file_path.strip():
                            seed_paths.append(file_path.strip())
                mcp_runtime.register_evidence_paths(seed_paths)

            # ============ 🔥 Markdown 长期记忆（不依赖 embedding/RAG） ============
            try:
                from app.services.agent.memory.markdown_memory import MarkdownMemoryStore
                from app.core.config import settings

                memory_store = MarkdownMemoryStore(project_id=str(project.id))
                memory_store.ensure()
                if bool(getattr(settings, "TOOL_DOC_SYNC_ENABLED", True)):
                    _sync_tool_catalog_to_memory(
                        memory_store=memory_store,
                        task_id=task_id,
                        max_chars=int(getattr(settings, "TOOL_DOC_SYNC_MAX_CHARS", 8000)),
                    )
                    _sync_mcp_tool_playbook_to_memory(
                        memory_store=memory_store,
                        task_id=task_id,
                        max_chars=int(getattr(settings, "TOOL_DOC_SYNC_MAX_CHARS", 8000)),
                    )
                    _sync_tool_skills_to_memory(
                        memory_store=memory_store,
                        task_id=task_id,
                        max_chars=int(getattr(settings, "TOOL_DOC_SYNC_MAX_CHARS", 8000)),
                    )
                markdown_memory = memory_store.load_bundle(
                    max_chars=8000,
                    skills_max_lines=int(getattr(settings, "TOOL_SKILLS_MAX_LINES", 180)),
                )
            except Exception as exc:
                logger.warning("[MarkdownMemory] init/load failed: %s", exc)
                markdown_memory = {}

            if markdown_memory:
                await _qmd_upsert_json("artifacts/markdown_memory_bundle.json", markdown_memory)
                await _qmd_update_index(force=False)
            
            # 更新任务文件统计
            task.total_files = project_info.get("file_count", 0)
            await db.commit()
            
            # 构建输入数据
            input_data = {
                "project_info": project_info,
                "config": {
                    "target_vulnerabilities": task.target_vulnerabilities or [],
                    "verification_level": task.verification_level or "analysis_with_poc_plan",
                    "exclude_patterns": task.exclude_patterns or [],
                    "target_files": task.target_files or [],
                    "single_risk_mode": True,
                    "max_iterations": task.max_iterations or 50,
                    # 🔥 seed_findings（继续使用 bootstrap_findings 字段承载：固定优先候选种子）
                    "bootstrap_findings": seed_findings,
                    "bootstrap_source": bootstrap_source,
                    "bootstrap_task_id": bootstrap_task_id,
                    # 🔥 入口点信息（回退时注入，便于 Agent 展示与 flow pipeline 约束）
                    "entry_points": entry_points_payload,
                    "entry_function_names": entry_function_names,
                    # 🔥 项目级 Markdown 记忆（shared + per-agent + skills 规范）
                    "markdown_memory": markdown_memory,
                },
                "project_root": project_root,
                "task_id": task_id,
            }

            await _qmd_upsert_json(
                "artifacts/task_input.json",
                {
                    "project_root": project_root,
                    "task_id": task_id,
                    "project_info": project_info,
                    "config": input_data["config"],
                },
            )
            await _qmd_update_index(force=False)

            # Provide deterministic persistence callback for Orchestrator TODO mode.
            # The callback is idempotent per task run to avoid double inserts on retries.
            finding_save_diagnostics: Dict[str, Any] = {}
            persist_state: Dict[str, Any] = {"saved_count": None}

            async def _persist_findings_callback(findings_payload: Any) -> int:
                if persist_state.get("saved_count") is not None:
                    return int(persist_state["saved_count"])
                findings_list = findings_payload if isinstance(findings_payload, list) else []
                saved = await _save_findings(
                    db,
                    task_id,
                    findings_list,
                    project_root=project_root,
                    save_diagnostics=finding_save_diagnostics,
                )
                persist_state["saved_count"] = int(saved)
                return int(saved)

            input_data["persist_findings"] = _persist_findings_callback

            # 🔥 将持久化回调注入到已初始化的 Verification 保存工具
            # （工具在 _initialize_tools 时以 save_callback=None 创建，此处补注入）
            _save_tool_instance = (
                tools.get("verification", {}).get("save_verification_results")
                if isinstance(tools, dict)
                else None
            )
            if _save_tool_instance is not None and hasattr(_save_tool_instance, "_save_callback"):
                _save_tool_instance._save_callback = _persist_findings_callback
                logger.info("[Task] Injected persist_findings_callback into save_verification_results tool")

            # 执行 Orchestrator
            await event_emitter.emit_phase_start("orchestration", "🎯 Orchestrator 开始编排审计流程")
            task.current_phase = AgentTaskPhase.ANALYSIS
            task.current_step = "分析阶段进行中"
            await db.commit()

            async def _run_orchestrator_once():
                # 🔥 将 orchestrator.run() 包装在 asyncio.Task 中，以便可以强制取消
                run_task = asyncio.create_task(orchestrator.run(input_data))
                _running_asyncio_tasks[task_id] = run_task
                try:
                    run_result = await run_task
                finally:
                    _running_asyncio_tasks.pop(task_id, None)

                if not run_result.success and run_result.error != "任务已取消":
                    raise RuntimeError(run_result.error or "Orchestrator returned unsuccessful result")
                return run_result

            result = await _run_with_retries(
                "ORCHESTRATOR_RUN",
                task_id,
                event_emitter,
                _run_orchestrator_once,
            )
            
            # 处理结果
            duration_ms = int((time.time() - start_time) * 1000)
            
            await db.refresh(task)
            
            if result.success:
                # 🔥 CRITICAL FIX: Log and save findings with detailed debugging
                findings = result.data.get("findings", [])
                if not isinstance(findings, list):
                    findings = []
                if not findings:
                    fallback_findings = getattr(orchestrator, "_all_findings", None)
                    if isinstance(fallback_findings, list) and fallback_findings:
                        findings = fallback_findings
                        logger.warning(
                            "[AgentTask] result.data.findings is empty, fallback to orchestrator._all_findings (%s)",
                            len(findings),
                        )

                single_risk_mode = bool((input_data.get("config") or {}).get("single_risk_mode", False))
                if single_risk_mode:
                    logger.info(
                        "[AgentTask] single_risk_mode=true，跳过 seed 与 agent findings 合并，使用实际分析结果"
                    )
                else:
                    # 🔥 Fixed-First 合并：确保 seed_findings 不会因 LLM 空输出而丢失
                    findings = _merge_seed_and_agent_findings(seed_findings, findings)

                # Best-effort dedup to avoid double inserts when seeds overlap with agent findings.
                # Key: (file_path, line_start, vulnerability_type)
                deduped: List[Dict[str, Any]] = []
                seen: Set[Tuple[str, int, str]] = set()
                for f in findings:
                    if not isinstance(f, dict):
                        continue
                    fp = str(f.get("file_path") or "").strip()
                    vt = str(f.get("vulnerability_type") or "").strip()
                    try:
                        ln = int(f.get("line_start") or 0)
                    except Exception:
                        ln = 0
                    key = (fp, ln, vt)
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(f)
                findings = deduped
                logger.info(
                    "[AgentTask] Task %s completed: merged_findings=%s (seeds=%s, orchestrator=%s)",
                    task_id,
                    len(findings),
                    len(seed_findings),
                    len(result.data.get("findings", []) or []) if isinstance(result.data, dict) else 0,
                )

                # 🔥 Debug: Log each finding for verification
                for i, f in enumerate(findings[:5]):  # Log first 5
                    if isinstance(f, dict):
                        logger.debug(f"[AgentTask] Finding {i+1}: {f.get('title', 'N/A')[:50]} - {f.get('severity', 'N/A')}")

                # Smart audit policy: disable automatic flow enrichment / evidence generation.
                flow_summary: Dict[str, Any] = {
                    "enabled": False,
                    "blocked_reason": "disabled_by_policy",
                }
                logger.info(
                    "[AgentTask] Flow enrichment summary (disabled): %s",
                    json.dumps(flow_summary, ensure_ascii=False),
                )

                task.current_phase = AgentTaskPhase.VERIFICATION
                task.current_step = "验证与结果归档中"
                await db.commit()

                # 检查 save_verification_results 工具是否已由 Agent 主动持久化
                _tool_saved_count: Optional[int] = None
                if (
                    _save_tool_instance is not None
                    and hasattr(_save_tool_instance, "is_saved")
                    and _save_tool_instance.is_saved
                ):
                    _tool_saved_count = _save_tool_instance.saved_count
                    logger.info(
                        "[AgentTask] save_verification_results 工具已由 Verification Agent 主动保存: saved_count=%s",
                        _tool_saved_count,
                    )
                elif (
                    _save_tool_instance is not None
                    and hasattr(_save_tool_instance, "buffered_findings")
                    and _save_tool_instance.buffered_findings
                    and not findings
                ):
                    # 工具缓冲了结果但未持久化（无回调），用缓冲的 findings 作为来源
                    findings = _save_tool_instance.buffered_findings
                    logger.info(
                        "[AgentTask] 从 save_verification_results 工具缓冲读取 %d 条 findings",
                        len(findings),
                    )

                if _tool_saved_count is not None:
                    saved_count = _tool_saved_count
                    logger.info(
                        "[AgentTask] 跳过重复持久化（工具已保存 %s 条）",
                        saved_count,
                    )
                elif persist_state.get("saved_count") is not None:
                    saved_count = int(persist_state["saved_count"])
                    logger.info(
                        "[AgentTask] Findings were already persisted by Orchestrator TODO step: saved_count=%s",
                        saved_count,
                    )
                else:
                    async def _persist_findings_once():
                        return await _save_findings(
                            db,
                            task_id,
                            findings,
                            project_root=project_root,
                            save_diagnostics=finding_save_diagnostics,
                        )

                    saved_count = await _run_with_retries(
                        "PERSIST_FINDINGS",
                        task_id,
                        event_emitter,
                        _persist_findings_once,
                    )
                logger.info(f"[AgentTask] Saved {saved_count}/{len(findings)} findings (filtered {len(findings) - saved_count} hallucinations)")

                persisted_findings_result = await db.execute(
                    select(AgentFinding).where(AgentFinding.task_id == task_id)
                )
                persisted_findings = persisted_findings_result.scalars().all()
                effective_findings = [
                    item for item in persisted_findings
                    if str(item.status) != FindingStatus.FALSE_POSITIVE and bool(item.is_verified)
                ]
                false_positive_findings = [
                    item for item in persisted_findings
                    if str(item.status) == FindingStatus.FALSE_POSITIVE
                ]
                filtered_reasons = (
                    finding_save_diagnostics.get("filtered_reasons")
                    if isinstance(finding_save_diagnostics, dict)
                    else {}
                )
                false_positive_discarded_count = (
                    int(filtered_reasons.get("false_positive_discarded", 0))
                    if isinstance(filtered_reasons, dict)
                    else 0
                )
                false_positive_count = max(
                    len(false_positive_findings),
                    false_positive_discarded_count,
                )
                agent_payloads: Dict[str, Any] = {}

                # ============ 🔥 Markdown 长期记忆写入（shared + per-agent） ============
                try:
                    if memory_store:
                        # Shared: 本次任务统计 + top findings
                        top_items = []
                        for item in effective_findings[:10]:
                            try:
                                top_items.append(
                                    {
                                        "title": str(item.title)[:120] if getattr(item, "title", None) else "",
                                        "severity": str(item.severity) if getattr(item, "severity", None) else "",
                                        "vulnerability_type": str(item.vulnerability_type) if getattr(item, "vulnerability_type", None) else "",
                                        "file_path": str(item.file_path) if getattr(item, "file_path", None) else "",
                                        "line_start": int(item.line_start) if getattr(item, "line_start", None) else 0,
                                    }
                                )
                            except Exception:
                                continue

                        memory_store.append_entry(
                            "shared",
                            task_id=task_id,
                            source=str(bootstrap_source or "agent_task"),
                            title="任务摘要",
                            summary=(
                                f"bootstrap_source={bootstrap_source} "
                                f"seeds={len(seed_findings)} "
                                f"orchestrator_findings={len(findings)} "
                                f"persisted_effective={len(effective_findings)} "
                                f"false_positive={false_positive_count}"
                            ),
                            payload={
                                "bootstrap": {
                                    "bootstrap_source": bootstrap_source,
                                    "bootstrap_task_id": bootstrap_task_id,
                                    "seed_count": len(seed_findings),
                                    "entry_points_count": len(entry_points_payload or []),
                                    "entry_function_names_count": len(entry_function_names or []),
                                },
                                "persistence": {
                                    "orchestrator_findings_count": len(findings),
                                    "saved_count": int(saved_count),
                                    "effective_findings_count": len(effective_findings),
                                    "false_positive_count": false_positive_count,
                                },
                                "top_findings": top_items,
                            },
                        )

                        # Per-agent: best-effort final answer summaries
                        if orchestrator and hasattr(orchestrator, "_agent_results"):
                            agent_payloads = getattr(orchestrator, "_agent_results") or {}

                        # Orchestrator
                        memory_store.append_entry(
                            "orchestrator",
                            task_id=task_id,
                            source="orchestrator",
                            title="Final Answer 摘要",
                            payload={
                                "result_keys": list(result.data.keys()) if isinstance(result.data, dict) else [],
                                "findings_count": len(findings),
                            },
                        )

                        # Sub agents
                        for agent_key in ("recon", "analysis", "verification"):
                            data = agent_payloads.get(agent_key)
                            if not isinstance(data, dict):
                                continue
                            summary_text = data.get("summary") or data.get("note") or ""
                            findings_list = data.get("findings")
                            if not isinstance(findings_list, list):
                                findings_list = data.get("initial_findings")
                            if not isinstance(findings_list, list):
                                findings_list = []
                            memory_store.append_entry(
                                agent_key,
                                task_id=task_id,
                                source=agent_key,
                                title="Final Answer 摘要",
                                summary=str(summary_text)[:8000] if summary_text else None,
                                payload={
                                    "keys": list(data.keys()),
                                    "findings_count": len([f for f in findings_list if isinstance(f, dict)]),
                                },
                            )
                except Exception as exc:
                    logger.warning("[MarkdownMemory] append failed: %s", exc)

                await _qmd_upsert_json(
                    "artifacts/final_summary.json",
                    {
                        "task_id": task_id,
                        "bootstrap_source": bootstrap_source,
                        "seed_findings_count": len(seed_findings or []),
                        "orchestrator_findings_count": len(findings or []),
                        "persisted_effective_findings_count": len(effective_findings or []),
                        "false_positive_count": false_positive_count,
                        "filtered_reasons": filtered_reasons or {},
                    },
                )
                await _qmd_upsert_json(
                    "agents/orchestrator.json",
                    {
                        "result_keys": list(result.data.keys()) if isinstance(result.data, dict) else [],
                        "findings_count": len(findings or []),
                    },
                )
                for agent_key in ("recon", "analysis", "verification"):
                    payload = agent_payloads.get(agent_key)
                    if not isinstance(payload, dict):
                        continue
                    await _qmd_upsert_json(f"agents/{agent_key}.json", payload)
                    summary_text = str(payload.get("summary") or payload.get("note") or "").strip()
                    if summary_text:
                        await _qmd_upsert_text(f"agents/{agent_key}.md", summary_text + "\n")
                await _qmd_update_index(force=False)

                # 更新任务统计
                # 🔥 CRITICAL FIX: 在设置完成前再次检查取消状态
                # 避免 "取消后后端继续运行并最终标记为完成" 的问题
                verification_pending_gate_triggered = False
                verification_pending_gate_message = ""
                verification_pending_gate_metadata: Dict[str, Any] = {}

                verification_payload: Dict[str, Any] = {}
                if orchestrator and hasattr(orchestrator, "_agent_results"):
                    agent_results = getattr(orchestrator, "_agent_results", {})
                    if isinstance(agent_results, dict):
                        verification_candidate = agent_results.get("verification")
                        if isinstance(verification_candidate, dict):
                            verification_payload = dict(verification_candidate)
                if not verification_payload and isinstance(result.data, dict):
                    verification_candidate = result.data.get("verification")
                    if isinstance(verification_candidate, dict):
                        verification_payload = dict(verification_candidate)

                gate_stats = _compute_verification_pending_gate(verification_payload)
                verification_pending_gate_triggered = bool(gate_stats.get("triggered"))
                verification_pending_gate_message = str(gate_stats.get("message") or "")
                verification_pending_gate_metadata = {
                    "candidate_count": int(gate_stats.get("candidate_count") or 0),
                    "pending_count": int(gate_stats.get("pending_count") or 0),
                    "pending_examples": gate_stats.get("pending_examples") or [],
                }

                if is_task_cancelled(task_id):
                    logger.info(f"[AgentTask] Task {task_id} was cancelled, overriding success result")
                    task.status = AgentTaskStatus.CANCELLED
                    task.error_message = None
                elif verification_pending_gate_triggered:
                    task.status = AgentTaskStatus.FAILED
                    task.error_message = verification_pending_gate_message
                else:
                    task.status = AgentTaskStatus.COMPLETED
                    task.error_message = None
                task.completed_at = datetime.now(timezone.utc)
                task.current_phase = AgentTaskPhase.REPORTING
                task.findings_count = len(effective_findings)
                task.false_positive_count = false_positive_count
                orchestrator_findings_count = len(findings)
                persisted_findings_count = len(effective_findings)
                filtered_findings_count = max(
                    orchestrator_findings_count - persisted_findings_count,
                    0,
                )
                filter_reason_text = ""
                if isinstance(filtered_reasons, dict) and filtered_reasons:
                    sorted_reasons = sorted(
                        filtered_reasons.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )[:3]
                    filter_reason_text = "，".join(
                        [f"{key}:{value}" for key, value in sorted_reasons]
                    )
                task.current_step = (
                    f"编排发现 {orchestrator_findings_count} / 入库 {persisted_findings_count} / "
                    f"过滤 {filtered_findings_count}"
                )
                if filter_reason_text:
                    task.current_step += f"（主要过滤原因：{filter_reason_text}）"

                runtime_snapshot = _snapshot_runtime_stats_to_task(task, orchestrator)
                task.total_iterations = max(
                    int(task.total_iterations or 0),
                    int(result.iterations or 0),
                    int(runtime_snapshot["iterations"]),
                )
                task.tool_calls_count = max(
                    int(task.tool_calls_count or 0),
                    int(result.tool_calls or 0),
                    int(runtime_snapshot["tool_calls"]),
                )
                task.tokens_used = max(
                    int(task.tokens_used or 0),
                    int(result.tokens_used or 0),
                    int(runtime_snapshot["tokens_used"]),
                )

                # 🔥 统计文件数量
                # analyzed_files = 实际扫描过的文件数（任务完成时等于 total_files）
                # files_with_findings = 有漏洞发现的唯一文件数
                task.analyzed_files = task.total_files  # Agent 扫描了所有符合条件的文件

                files_with_findings_set = set()
                for finding_item in effective_findings:
                    if finding_item.file_path:
                        files_with_findings_set.add(finding_item.file_path)
                task.files_with_findings = len(files_with_findings_set)

                # 统计严重程度和验证状态
                task.critical_count = 0
                task.high_count = 0
                task.medium_count = 0
                task.low_count = 0
                task.verified_count = 0
                for finding_item in effective_findings:
                    severity_value = str(finding_item.severity).lower()
                    if severity_value == "critical":
                        task.critical_count += 1
                    elif severity_value == "high":
                        task.high_count += 1
                    elif severity_value == "medium":
                        task.medium_count += 1
                    elif severity_value == "low":
                        task.low_count += 1
                    if finding_item.is_verified:
                        task.verified_count += 1
                
                # 计算安全评分
                task.security_score = _calculate_security_score(
                    [{"severity": str(item.severity).lower()} for item in effective_findings]
                )
                # 🔥 注意: progress_percentage 是计算属性，不需要手动设置
                # 当 status = COMPLETED 时会自动返回 100.0
                
                async def _commit_summary_once():
                    await db.commit()

                await _run_with_retries(
                    "PERSIST_TASK_SUMMARY",
                    task_id,
                    event_emitter,
                    _commit_summary_once,
                )

                drain_result = await _wait_for_terminal_tool_drain(
                    event_manager=event_manager,
                    task_id=task_id,
                    skip_wait=bool(task.status == AgentTaskStatus.CANCELLED or is_task_cancelled(task_id)),
                    timeout_seconds=TOOL_DRAIN_TIMEOUT_SECONDS,
                )
                drain_metadata = _build_tool_drain_metadata(drain_result)

                terminal_failure_message: Optional[str] = None
                terminal_failure_metadata: Dict[str, Any] = {}
                if bool(drain_result.get("timed_out")):
                    timeout_message = (
                        "终态收敛超时：存在未完成工具调用，已将任务标记为失败。"
                    )
                    task.status = AgentTaskStatus.FAILED
                    task.error_message = timeout_message
                    task.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    terminal_failure_message = timeout_message
                    terminal_failure_metadata = {
                        "step_name": "TERMINAL_TOOL_DRAIN",
                        "attempt": 1,
                        "retry_attempt": 1,
                        "max_attempts": 1,
                        "is_terminal": True,
                        "retry_error_class": "tool_drain_timeout",
                        "retryable": False,
                        "cancel_origin": "none",
                        **drain_metadata,
                    }
                elif verification_pending_gate_triggered:
                    terminal_failure_message = (
                        "终态门禁阻断：verification 队列仍有待验证候选，任务已标记失败。"
                    )
                    terminal_failure_metadata = {
                        "step_name": "VERIFICATION_PENDING_GATE",
                        "attempt": 1,
                        "retry_attempt": 1,
                        "max_attempts": 1,
                        "is_terminal": True,
                        "retry_error_class": "verification_pending_gate",
                        "retryable": False,
                        "cancel_origin": "none",
                        **verification_pending_gate_metadata,
                        **drain_metadata,
                    }
                if terminal_failure_message:
                    await event_emitter.emit_task_error(
                        terminal_failure_message,
                        message=f"❌ 任务失败: {terminal_failure_message}",
                        metadata=terminal_failure_metadata,
                    )
                    await event_emitter.emit_error(
                        terminal_failure_message,
                        metadata=terminal_failure_metadata,
                    )
                else:
                    await event_emitter.emit_task_complete(
                        findings_count=persisted_findings_count,
                        duration_ms=duration_ms,
                        message=(
                            f"✅ 审计完成：编排发现 {orchestrator_findings_count}，"
                            f"入库 {persisted_findings_count}，过滤 {filtered_findings_count}，"
                            f"耗时 {duration_ms/1000:.1f} 秒"
                        ),
                        extra_metadata={
                            "orchestrator_findings_count": orchestrator_findings_count,
                            "persisted_findings_count": persisted_findings_count,
                            "filtered_findings_count": filtered_findings_count,
                            "filtered_reasons": filtered_reasons or {},
                            **drain_metadata,
                        },
                    )
                if orchestrator_findings_count > 0 and persisted_findings_count == 0:
                    await event_emitter.emit_warning(
                        "⚠️ 编排阶段识别到漏洞，但入库结果为 0，疑似全部被门禁过滤",
                        metadata={
                            "orchestrator_findings_count": orchestrator_findings_count,
                            "persisted_findings_count": persisted_findings_count,
                            "filtered_findings_count": filtered_findings_count,
                            "filtered_reasons": filtered_reasons or {},
                            **drain_metadata,
                            "is_terminal": True,
                        },
                    )
                
                if bool(drain_result.get("timed_out")):
                    logger.error(
                        "[TaskDrain] Task %s failed due to tool drain timeout: pending=%s",
                        task_id,
                        len(drain_metadata.get("pending_tool_calls", [])),
                    )
                elif verification_pending_gate_triggered:
                    logger.error(
                        "[VerificationGate] Task %s blocked: candidate=%s pending=%s",
                        task_id,
                        verification_pending_gate_metadata.get("candidate_count", 0),
                        verification_pending_gate_metadata.get("pending_count", 0),
                    )
                else:
                    logger.info(
                        f"✅ Task {task_id} completed: "
                        f"effective={len(effective_findings)}, false_positive={false_positive_count}, "
                        f"saved={saved_count}, duration={duration_ms}ms"
                    )
            else:
                # 🔥 检查是否是取消导致的失败
                if result.error == "任务已取消":
                    # 状态可能已经被 cancel API 更新，只需确保一致性
                    _snapshot_runtime_stats_to_task(task, orchestrator)
                    if task.status != AgentTaskStatus.CANCELLED:
                        task.status = AgentTaskStatus.CANCELLED
                        task.completed_at = datetime.now(timezone.utc)
                        await db.commit()
                    await _qmd_upsert_json(
                        "artifacts/task_terminal_state.json",
                        {
                            "task_id": task_id,
                            "status": "cancelled",
                            "error": result.error,
                        },
                    )
                    await _qmd_update_index(force=False)
                    logger.info(f"🛑 Task {task_id} cancelled")
                else:
                    _snapshot_runtime_stats_to_task(task, orchestrator)
                    task.status = AgentTaskStatus.FAILED
                    task.error_message = result.error or "Unknown error"
                    task.completed_at = datetime.now(timezone.utc)
                    await db.commit()

                    failure_message = task.error_message
                    retry_diag = _classify_retry_error(failure_message)
                    failure_metadata = {
                        "step_name": "ORCHESTRATOR_RUN",
                        "attempt": 1,
                        "retry_attempt": 1,
                        "max_attempts": 1,
                        "is_terminal": True,
                        "retry_error_class": retry_diag["code"],
                        "retryable": bool(retry_diag["retryable"]),
                        "cancel_origin": "none",
                    }
                    drain_result = await _wait_for_terminal_tool_drain(
                        event_manager=event_manager,
                        task_id=task_id,
                        skip_wait=bool(is_task_cancelled(task_id)),
                        timeout_seconds=TOOL_DRAIN_TIMEOUT_SECONDS,
                    )
                    failure_metadata.update(_build_tool_drain_metadata(drain_result))
                    await event_emitter.emit_task_error(
                        failure_message,
                        message=f"❌ 任务失败: {failure_message}",
                        metadata=failure_metadata,
                    )
                    await event_emitter.emit_error(
                        failure_message,
                        metadata=failure_metadata,
                    )
                    await _qmd_upsert_json(
                        "artifacts/task_terminal_state.json",
                        {
                            "task_id": task_id,
                            "status": "failed",
                            "error": failure_message,
                            "metadata": failure_metadata,
                        },
                    )
                    await _qmd_update_index(force=False)
                    logger.error(f"❌ Task {task_id} failed: {result.error}")
            
        except asyncio.CancelledError:
            logger.info(f"Task {task_id} cancelled")
            try:
                task = await db.get(AgentTask, task_id)
                if task:
                    _snapshot_runtime_stats_to_task(task, _running_orchestrators.get(task_id))
                    task.status = AgentTaskStatus.CANCELLED
                    task.completed_at = datetime.now(timezone.utc)
                    await db.commit()
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            retry_diag = _classify_retry_error(e)
            failure_metadata = {
                "step_name": "UNKNOWN",
                "attempt": 1,
                "retry_attempt": 1,
                "max_attempts": 1,
                "is_terminal": True,
                "retry_error_class": retry_diag["code"],
                "retryable": bool(retry_diag["retryable"]),
                "cancel_origin": "none",
            }
            failure_message = str(e)[:1000]
            if isinstance(e, StepRetryExceededError):
                final_diag = _classify_retry_error(e.last_error)
                failure_metadata = {
                    "step_name": e.step_name,
                    "attempt": e.attempts,
                    "retry_attempt": e.attempts,
                    "max_attempts": e.max_attempts,
                    "is_terminal": True,
                    "retry_error_class": final_diag["code"],
                    "retryable": bool(final_diag["retryable"]),
                    "cancel_origin": (
                        "user"
                        if "cancelled_user" in str(final_diag.get("code"))
                        else "none"
                    ),
                }
                failure_message = e.final_message[:1000]

            try:
                task = await db.get(AgentTask, task_id)
                if task:
                    _snapshot_runtime_stats_to_task(task, _running_orchestrators.get(task_id))
                    task.status = AgentTaskStatus.FAILED
                    task.error_message = failure_message
                    task.completed_at = datetime.now(timezone.utc)
                    await db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update task status: {db_error}")

            try:
                skip_drain_wait = bool(
                    is_task_cancelled(task_id)
                    or str(failure_metadata.get("cancel_origin") or "").strip().lower() == "user"
                )
                drain_result = await _wait_for_terminal_tool_drain(
                    event_manager=event_manager,
                    task_id=task_id,
                    skip_wait=skip_drain_wait,
                    timeout_seconds=TOOL_DRAIN_TIMEOUT_SECONDS,
                )
                failure_metadata.update(_build_tool_drain_metadata(drain_result))
                await event_emitter.emit_task_error(
                    failure_message,
                    message=f"❌ 任务失败: {failure_message}",
                    metadata=failure_metadata,
                )
                await event_emitter.emit_error(
                    failure_message,
                    metadata=failure_metadata,
                )
            except Exception as emit_error:
                logger.warning(f"Failed to emit terminal task error event: {emit_error}")
            try:
                await _qmd_upsert_json(
                    "artifacts/task_terminal_state.json",
                    {
                        "task_id": task_id,
                        "status": "failed",
                        "error": failure_message,
                        "metadata": failure_metadata,
                    },
                )
                await _qmd_update_index(force=False)
            except Exception as qmd_error:
                logger.debug("[QMD TaskKB] failed to persist terminal state: %s", qmd_error)
        
        finally:
            # 🔥 在清理之前保存 Agent 树到数据库
            try:
                async with async_session_factory() as save_db:
                    await _save_agent_tree(save_db, task_id)
            except Exception as save_error:
                logger.error(f"Failed to save agent tree: {save_error}")

            # 清理
            _running_orchestrators.pop(task_id, None)
            _running_tasks.pop(task_id, None)
            _running_event_managers.pop(task_id, None)
            _running_asyncio_tasks.pop(task_id, None)  # 🔥 清理 asyncio task
            _running_queue_services.pop(task_id, None)
            _running_recon_queue_services.pop(task_id, None)
            _cancelled_tasks.discard(task_id)  # 🔥 清理取消标志

            # 🔥 清理整个 Agent 注册表（包括所有子 Agent）
            agent_registry.clear()

            logger.debug(f"Task {task_id} cleaned up")


async def _get_user_config(db: AsyncSession, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """获取用户配置"""
    if not user_id:
        return None
    
    try:
        from app.api.v1.endpoints.config import (
            decrypt_config, 
            SENSITIVE_LLM_FIELDS, SENSITIVE_OTHER_FIELDS,
            _sanitize_other_config,
        )
        
        result = await db.execute(
            select(UserConfig).where(UserConfig.user_id == user_id)
        )
        config = result.scalar_one_or_none()
        
        if config and config.llm_config:
            user_llm_config = json.loads(config.llm_config) if config.llm_config else {}
            user_other_config = json.loads(config.other_config) if config.other_config else {}
            
            user_llm_config = decrypt_config(user_llm_config, SENSITIVE_LLM_FIELDS)
            user_other_config = decrypt_config(user_other_config, SENSITIVE_OTHER_FIELDS)
            user_other_config = _sanitize_other_config(user_other_config)
            
            return {
                "llmConfig": user_llm_config,
                "otherConfig": user_other_config,
            }
    except Exception as e:
        logger.warning(f"Failed to get user config: {e}")
    
    return None


def _sync_tool_catalog_to_memory(
    *,
    memory_store: Any,
    task_id: str,
    max_chars: int,
) -> None:
    """同步共享工具目录到 Markdown memory shared.md（追加式，保留历史）。"""
    catalog_path = Path(__file__).resolve().parents[4] / "docs" / "agent-tools" / "TOOL_SHARED_CATALOG.md"
    if not catalog_path.exists():
        return

    try:
        content = catalog_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("[ToolDocSync] read catalog failed: %s", exc)
        return

    clipped = content[: max(0, int(max_chars))]
    if not clipped.strip():
        return

    try:
        memory_store.append_entry(
            "shared",
            task_id=task_id,
            source="tool_catalog_sync",
            title="工具共享目录同步",
            summary="将 TOOL_SHARED_CATALOG.md 摘要同步到 shared memory，供各 Agent 提示词检出。",
            payload={
                "catalog_path": str(catalog_path),
                "max_chars": int(max_chars),
                "content": clipped,
            },
        )
    except Exception as exc:
        logger.warning("[ToolDocSync] append shared entry failed: %s", exc)


def _load_mcp_tool_playbook(*, max_chars: int) -> Tuple[Optional[Path], str]:
    docs_root = Path(__file__).resolve().parents[4] / "docs" / "agent-tools"
    playbook_path = docs_root / "MCP_TOOL_PLAYBOOK.md"
    if not playbook_path.exists():
        return None, ""
    try:
        content = playbook_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("[ToolDocSync] read MCP tool playbook failed: %s", exc)
        return playbook_path, ""
    clipped = content[: max(0, int(max_chars))]
    return playbook_path, clipped


def _sync_mcp_tool_playbook_to_memory(
    *,
    memory_store: Any,
    task_id: str,
    max_chars: int,
) -> None:
    playbook_path, playbook_content = _load_mcp_tool_playbook(max_chars=max_chars)
    if not playbook_path or not playbook_content.strip():
        return
    try:
        memory_store.append_entry(
            "shared",
            task_id=task_id,
            source="mcp_tool_playbook_sync",
            title="MCP 工具说明同步",
            summary="将 MCP_TOOL_PLAYBOOK.md 同步到 shared memory，供各 Agent 快速检索标准工具调用方式。",
            payload={
                "playbook_path": str(playbook_path),
                "max_chars": int(max_chars),
                "content": playbook_content,
            },
        )
    except Exception as exc:
        logger.warning("[ToolDocSync] append MCP playbook failed: %s", exc)


def _build_tool_skills_snapshot(*, max_chars: int) -> str:
    docs_root = Path(__file__).resolve().parents[4] / "docs" / "agent-tools"
    index_path = docs_root / "SKILLS_INDEX.md"
    skills_dir = docs_root / "skills"
    preferred_skill_order = [
        "mcp_reliability_workflow.skill.md",
        "push_finding_to_queue.skill.md",
        "get_recon_risk_queue_status.skill.md",
        "read_file.skill.md",
        "search_code.skill.md",
        "list_files.skill.md",
        "extract_function.skill.md",
        "locate_enclosing_function.skill.md",
        "function_context.skill.md",
    ]

    fragments: List[str] = []
    if index_path.exists():
        try:
            fragments.append(index_path.read_text(encoding="utf-8", errors="replace").strip())
        except Exception as exc:
            logger.warning("[ToolDocSync] read skills index failed: %s", exc)

    if skills_dir.exists():
        all_skill_docs = {doc.name: doc for doc in skills_dir.glob("*.skill.md")}
        ordered_skill_docs: List[Path] = []
        for preferred_name in preferred_skill_order:
            preferred_doc = all_skill_docs.pop(preferred_name, None)
            if preferred_doc is not None:
                ordered_skill_docs.append(preferred_doc)
        ordered_skill_docs.extend(all_skill_docs[name] for name in sorted(all_skill_docs.keys()))

        for skill_doc in ordered_skill_docs:
            try:
                fragments.append(skill_doc.read_text(encoding="utf-8", errors="replace").strip())
            except Exception as exc:
                logger.warning("[ToolDocSync] read skill doc failed (%s): %s", skill_doc, exc)

    _playbook_path, playbook_content = _load_mcp_tool_playbook(max_chars=max_chars)
    if playbook_content.strip():
        fragments.append(playbook_content.strip())

    snapshot = "\n\n---\n\n".join(item for item in fragments if str(item or "").strip())
    if not snapshot.strip():
        return ""
    return snapshot[: max(0, int(max_chars))]


def _sync_tool_skills_to_memory(
    *,
    memory_store: Any,
    task_id: str,
    max_chars: int,
) -> None:
    skill_snapshot = _build_tool_skills_snapshot(max_chars=max_chars)
    if not skill_snapshot:
        return

    if hasattr(memory_store, "write_skills_snapshot"):
        try:
            memory_store.write_skills_snapshot(
                skill_snapshot,
                source="tool_skill_sync",
                task_id=task_id,
            )
            return
        except Exception as exc:
            logger.warning("[ToolDocSync] write skills snapshot failed: %s", exc)

    # Backward-compatible fallback.
    try:
        memory_store.append_entry(
            "skills",
            task_id=task_id,
            source="tool_skill_sync",
            title="工具 skill 规范同步",
            summary="将文件读取相关 skill 文档同步到 skills memory。",
            payload={"content": skill_snapshot},
        )
    except Exception as exc:
        logger.warning("[ToolDocSync] append skills entry failed: %s", exc)


async def _initialize_tools(
    project_root: str,
    llm_service,
    user_config: Optional[Dict[str, Any]],
    sandbox_manager: Any, # 传递预初始化的 SandboxManager
    rag_enabled: bool = False,
    verification_level: str = "analysis_with_poc_plan",
    exclude_patterns: Optional[List[str]] = None,
    target_files: Optional[List[str]] = None,
    project_id: Optional[str] = None,  # 🔥 用于 RAG collection_name
    event_emitter: Optional[Any] = None,  # 🔥 新增：用于发送实时日志
    task_id: Optional[str] = None,  # 🔥 新增：用于取消检查
    qmd_task_kb: Optional[Any] = None,
    queue_service: Optional[Any] = None,  # 🔥 新增：漏洞队列服务
    recon_queue_service: Optional[Any] = None,  # 🔥 新增：Recon 风险队列服务
    save_callback: Optional[Any] = None,  # 🔥 新增：验证结果持久化回调 async (findings) -> int
) -> Dict[str, Dict[str, Any]]:
    """初始化工具集

    Args:
        project_root: 项目根目录
        llm_service: LLM 服务
        user_config: 用户配置
        sandbox_manager: 沙箱管理器
        verification_level: 验证级别（统一为 analysis_with_poc_plan）
        exclude_patterns: 排除模式列表
        target_files: 目标文件列表
        project_id: 项目 ID（用于 RAG collection_name）
        event_emitter: 事件发送器（用于发送实时日志）
        task_id: 任务 ID（用于取消检查）
        qmd_task_kb: 任务级 QMD 知识库实例（可选）
    """
    from app.services.agent.tools import (
        FileReadTool,
        FileSearchTool,
        ListFilesTool,
        PatternMatchTool,
        DataFlowAnalysisTool,
        ThinkTool,
        ReflectTool,
        SkillLookupTool,
        CreateVulnerabilityReportTool,
        ControlFlowAnalysisLightTool,
        JoernReachabilityVerifyTool,
        LogicAuthzAnalysisTool,
        ExtractFunctionTool,
        OpengrepTool, BanditTool, GitleaksTool,
        NpmAuditTool, SafetyTool, TruffleHogTool, OSVScannerTool,
        PMDTool,PHPStanTool,
    )
    from app.services.agent.tools.queue_tools import (
        GetQueueStatusTool, DequeueFindingTool, PushFindingToQueueTool, IsFindingInQueueTool
    )
    from app.services.agent.tools.recon_queue_tools import (
        GetReconRiskQueueStatusTool,
        PushRiskPointToQueueTool,
        DequeueReconRiskPointTool,
        PeekReconRiskQueueTool,
        ClearReconRiskQueueTool,
        IsReconRiskPointInQueueTool,
    )
    from app.services.agent.vulnerability_queue import (
        RedisVulnerabilityQueue, InMemoryVulnerabilityQueue
    )
    from app.services.agent.tools.qmd_cli_tools import (
        QmdGetTool,
        QmdMultiGetTool,
        QmdQueryTool,
        QmdStatusTool,
    )
    # 🔥 RAG 相关导入
    from app.services.rag import CodeIndexer, CodeRetriever, EmbeddingService, IndexUpdateMode
    from app.core.config import settings

    # 辅助函数：发送事件
    async def emit(message: str, level: str = "info"):
        if event_emitter:
            logger.debug(f"[EMIT-TOOLS] Sending {level}: {message[:60]}...")
            if level == "info":
                await event_emitter.emit_info(message)
            elif level == "warning":
                await event_emitter.emit_warning(message)
            elif level == "error":
                await event_emitter.emit_error(message)
        else:
            logger.warning(f"[EMIT-TOOLS] No event_emitter, skipping: {message[:60]}...")

    # ============ 🔥 初始化 RAG 系统 ============
    retriever = None
    effective_rag_enabled = bool(rag_enabled) or bool(getattr(settings, "RAG_ENABLED", False))
    if not effective_rag_enabled:
        # 智能审计默认不依赖 embedding/RAG；保留接口，后续按开关启用。
        pass
    else:
        try:
            await emit("🔍 正在初始化 RAG 系统...")

            # 从用户配置中获取 embedding 配置
            user_llm_config = (user_config or {}).get("llmConfig", {})
            user_other_config = (user_config or {}).get("otherConfig", {})
            user_embedding_config = user_other_config.get("embedding_config", {})

            # Embedding Provider/Model 优先级：用户嵌入配置 > 环境变量
            embedding_provider = user_embedding_config.get("provider") or getattr(
                settings, "EMBEDDING_PROVIDER", "openai"
            )
            embedding_model = user_embedding_config.get("model") or getattr(
                settings, "EMBEDDING_MODEL", "text-embedding-3-small"
            )

            # API Key 优先级：用户嵌入配置 > 环境变量 EMBEDDING_API_KEY > 用户 LLM 配置 > 环境变量 LLM_API_KEY
            embedding_api_key = (
                user_embedding_config.get("api_key")
                or getattr(settings, "EMBEDDING_API_KEY", None)
                or user_llm_config.get("llmApiKey")
                or getattr(settings, "LLM_API_KEY", "")
                or ""
            )

            # Base URL 优先级：用户嵌入配置 > 环境变量 EMBEDDING_BASE_URL > None（使用提供商默认地址）
            embedding_base_url = (
                user_embedding_config.get("base_url")
                or getattr(settings, "EMBEDDING_BASE_URL", None)
                or None
            )

            logger.info(
                "RAG 配置: provider=%s, model=%s, base_url=%s",
                embedding_provider,
                embedding_model,
                embedding_base_url or "(使用默认)",
            )
            await emit(f"📊 Embedding 配置: {embedding_provider}/{embedding_model}")

            # 创建 Embedding 服务
            embedding_service = EmbeddingService(
                provider=embedding_provider,
                model=embedding_model,
                api_key=embedding_api_key,
                base_url=embedding_base_url,
            )

            # 创建 collection_name（基于 project_id）
            collection_name = f"project_{project_id}" if project_id else "default_project"

            # 创建 CodeIndexer 并进行智能索引（增量更新）
            indexer = CodeIndexer(
                collection_name=collection_name,
                embedding_service=embedding_service,
                persist_directory=settings.VECTOR_DB_PATH,
            )

            logger.info("📝 开始智能索引项目: %s", project_root)
            await emit("📝 正在构建代码向量索引...")

            index_progress = None
            last_progress_update = 0
            last_embedding_progress = [0]  # 使用列表以便在闭包中修改
            embedding_total = [0]  # 记录总数

            # 🔥 嵌入进度回调函数（同步，但会调度异步任务）
            def on_embedding_progress(processed: int, total: int):
                embedding_total[0] = total
                # 每处理 50 个或完成时更新
                if processed - last_embedding_progress[0] >= 50 or processed == total:
                    last_embedding_progress[0] = processed
                    percentage = (processed / total * 100) if total > 0 else 0
                    msg = f"🔢 嵌入进度: {processed}/{total} ({percentage:.0f}%)"
                    logger.info(msg)
                    # 使用 asyncio.create_task 调度异步 emit
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(emit(msg))
                    except Exception as exc:
                        logger.warning("Failed to emit embedding progress: %s", exc)

            # 🔥 创建取消检查函数，用于在嵌入批处理中检查取消状态
            def check_cancelled() -> bool:
                return task_id is not None and is_task_cancelled(task_id)

            async for progress in indexer.smart_index_directory(
                directory=project_root,
                exclude_patterns=exclude_patterns or [],
                include_patterns=target_files,  # 🔥 传递 target_files 限制索引范围
                update_mode=IndexUpdateMode.SMART,
                embedding_progress_callback=on_embedding_progress,
                cancel_check=check_cancelled,  # 🔥 传递取消检查函数
            ):
                # 🔥 在索引过程中检查取消状态
                if check_cancelled():
                    logger.info("[Cancel] RAG indexing cancelled for task %s", task_id)
                    raise asyncio.CancelledError("任务已取消")

                index_progress = progress
                # 每处理 10 个文件或完成时发送进度更新
                if (
                    progress.processed_files - last_progress_update >= 10
                    or progress.processed_files == progress.total_files
                ):
                    if progress.total_files > 0:
                        await emit(
                            f"📝 索引进度: {progress.processed_files}/{progress.total_files} 文件 "
                            f"({progress.progress_percentage:.0f}%)"
                        )
                    last_progress_update = progress.processed_files

                # 发送状态消息（如嵌入向量生成进度）
                if progress.status_message:
                    await emit(progress.status_message)
                    progress.status_message = ""  # 清空已发送的消息

            if index_progress:
                summary = (
                    f"✅ 索引完成: 模式={index_progress.update_mode}, "
                    f"新增={index_progress.added_files}, "
                    f"更新={index_progress.updated_files}, "
                    f"删除={index_progress.deleted_files}, "
                    f"代码块={index_progress.indexed_chunks}"
                )
                logger.info(summary)
                await emit(summary)
                await emit("✅ 索引已完成，进入分析阶段")

            # 创建 CodeRetriever（用于搜索）
            retriever = CodeRetriever(
                collection_name=collection_name,
                embedding_service=embedding_service,
                persist_directory=settings.VECTOR_DB_PATH,
                api_key=embedding_api_key,  # 🔥 传递 api_key 以支持自动切换 embedding
            )

            logger.info("✅ RAG 系统初始化成功: collection=%s", collection_name)
            await emit("✅ RAG 系统初始化成功")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            # 🔥 降级继续：RAG 初始化失败不再阻塞智能审计任务
            logger.error("❌ RAG 系统初始化失败（已降级继续）: %s", e)
            await emit(f"⚠️ RAG 系统初始化失败（已降级继续）：{e}", "warning")
            import traceback

            logger.debug("RAG 初始化异常详情:\n%s", traceback.format_exc())
            retriever = None

    # 基础工具 - 传递排除模式和目标文件
    base_tools = {
        "read_file": FileReadTool(
            project_root,
            exclude_patterns,
            target_files,
            strict_anchor_mode=True,
        ),
        "list_files": ListFilesTool(project_root, exclude_patterns, target_files),
        "search_code": FileSearchTool(project_root, exclude_patterns, target_files),
        "think": ThinkTool(),
        "reflect": ReflectTool(),
        "skill_lookup": SkillLookupTool(),
    }

    user_other_config = (user_config or {}).get("otherConfig", {})
    mcp_config = user_other_config.get("mcpConfig") if isinstance(user_other_config, dict) else {}
    if not isinstance(mcp_config, dict):
        mcp_config = {}
    runtime_policy = mcp_config.get("runtimePolicy") if isinstance(mcp_config.get("runtimePolicy"), dict) else {}
    catalog_items = build_mcp_catalog(
        mcp_enabled=bool(mcp_config.get("enabled", getattr(settings, "MCP_ENABLED", True))),
        runtime_policy=runtime_policy if isinstance(runtime_policy, dict) else None,
    )
    catalog_by_id: Dict[str, Dict[str, Any]] = {
        str(item.get("id")): item
        for item in catalog_items
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }

    def _mcp_ready(mcp_id: str) -> bool:
        item = catalog_by_id.get(mcp_id, {})
        return bool(item.get("enabled")) and bool(item.get("startup_ready"))

    qmd_ready = _mcp_ready("qmd")
    code_index_ready = _mcp_ready("code_index")
    sequential_ready = _mcp_ready("sequentialthinking")

    # 智能审计场景强制 Filesystem 只读：不向 Agent 暴露 MCP 写入入口。
    mcp_write_tools: Dict[str, Any] = {}

    mcp_read_tools: Dict[str, Any] = {}
    qmd_cli_enabled = bool(getattr(settings, "QMD_TASK_KB_ENABLED", True))
    if qmd_cli_enabled and qmd_task_kb is not None:
        mcp_read_tools.update(
            {
                "qmd_query": QmdQueryTool(qmd_task_kb),
                "qmd_get": QmdGetTool(qmd_task_kb),
                "qmd_multi_get": QmdMultiGetTool(qmd_task_kb),
                "qmd_status": QmdStatusTool(qmd_task_kb),
            }
        )
    elif qmd_ready:
        mcp_read_tools.update(
            {
                "qmd_query": MCPVirtualReadTool(
                    name="qmd_query",
                    description="通过 QMD MCP 执行语义检索。",
                ),
                "qmd_get": MCPVirtualReadTool(
                    name="qmd_get",
                    description="通过 QMD MCP 获取文档详情。",
                ),
                "qmd_multi_get": MCPVirtualReadTool(
                    name="qmd_multi_get",
                    description="通过 QMD MCP 批量获取文档。",
                ),
                "qmd_status": MCPVirtualReadTool(
                    name="qmd_status",
                    description="查询 QMD 集合状态。",
                ),
            }
        )

    if code_index_ready:
        mcp_read_tools.update(
            {
                "locate_enclosing_function": MCPVirtualReadTool(
                    name="locate_enclosing_function",
                    description="通过 Code Index MCP 定位命中代码所属函数。",
                ),
            }
        )

    if sequential_ready:
        mcp_read_tools.update(
            {
                "sequential_thinking": MCPVirtualReadTool(
                    name="sequential_thinking",
                    description="通过 SequentialThinking MCP 执行分步推理。",
                ),
                "reasoning_trace": MCPVirtualReadTool(
                    name="reasoning_trace",
                    description="通过 SequentialThinking MCP 生成推理轨迹。",
                ),
            }
        )

    deprecated_skill_tools: Dict[str, Any] = {
        # skill_name: MCPDeprecatedTool(name=skill_name, message="该 skill 已下线，请改用 verify_reachability + flow 证据链。")
        # for skill_name in [
        #     "test_command_injection",
        #     "test_deserialization",
        #     "test_path_traversal",
        #     "test_sql_injection",
        #     "test_ssti",
        #     "test_xss",
        #     "universal_vuln_test",
        # ]
    }
    
    # Recon 工具
    recon_tools = {
        **base_tools,
        **mcp_read_tools,
        **mcp_write_tools,
        **deprecated_skill_tools,
        # 🔥 外部侦察工具 (Recon 阶段也需要使用这些工具来收集初步信息)
        # "opengrep_scan": OpengrepTool(project_root, sandbox_manager),
        # "bandit_scan": BanditTool(project_root, sandbox_manager),
        # NOTE: Smart audit policy: gitleaks_scan is disabled in orchestrated audit flow.
        # Keep the tool implementation for other entrypoints / manual usage.
        # "gitleaks_scan": GitleaksTool(project_root, sandbox_manager),
        # "npm_audit": NpmAuditTool(project_root, sandbox_manager),
        # "safety_scan": SafetyTool(project_root, sandbox_manager),
        # "trufflehog_scan": TruffleHogTool(project_root, sandbox_manager),
        # "osv_scan": OSVScannerTool(project_root, sandbox_manager),
        # "pmd_scan": PMDTool(project_root, sandbox_manager),
        # "phpstan_scan": PHPStanTool(project_root, sandbox_manager),
    }
    if recon_queue_service and task_id:
        recon_tools["push_risk_point_to_queue"] = PushRiskPointToQueueTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        recon_tools["get_recon_risk_queue_status"] = GetReconRiskQueueStatusTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        logger.info(f"[Tools] Added Recon risk queue tools for task {task_id}")

    # Analysis 工具
    # 🔥 导入智能扫描工具
    from app.services.agent.tools import SmartScanTool, QuickAuditTool, BusinessLogicScanTool, ExtractFunctionTool, PatternMatchTool
    
    # 🔥 业务逻辑扫描核心工具集
    # BusinessLogicScanAgent 5 个阶段需要的分析工具
    # Phase 1 (HTTP 入口发现): search_code, read_file, extract_function
    # Phase 2 (入口分析): read_file, extract_function, logic_authz_analysis
    # Phase 3 (敏感操作): read_file, search_code, pattern_match
    # Phase 4 (污点分析): dataflow_analysis, controlflow_analysis_light, read_file
    # Phase 5 (漏洞确认): read_file, 综合前4阶段结果
    business_logic_scan_core_tools = {
        **base_tools,
        **mcp_read_tools,
    }
    
    analysis_tools = {
        **base_tools,
        **mcp_read_tools,
        **mcp_write_tools,
        **deprecated_skill_tools,
        # 🔥 智能扫描工具（推荐首先使用）
        "smart_scan": SmartScanTool(project_root, exclude_patterns=exclude_patterns or []),
        "quick_audit": QuickAuditTool(project_root),
        "business_logic_scan": BusinessLogicScanTool(
            project_root=project_root,
            llm_service=llm_service,
            tools_registry=business_logic_scan_core_tools,
            event_emitter=event_emitter,
        ),
        # 模式匹配工具（增强版）
        "pattern_match": PatternMatchTool(project_root),
        # 函数提取工具（用于业务逻辑扫描等分析任务）
        "extract_function": ExtractFunctionTool(project_root=project_root),
        # 数据流分析
        "dataflow_analysis": DataFlowAnalysisTool(llm_service, project_root=project_root),
        # 三轨流分析主链
        "controlflow_analysis_light": ControlFlowAnalysisLightTool(
            project_root=project_root,
            target_files=target_files,
        ),
        "logic_authz_analysis": LogicAuthzAnalysisTool(
            project_root=project_root,
            target_files=target_files,
        ),
        # 外部安全工具 (传入共享的 sandbox_manager)
        # "opengrep_scan": OpengrepTool(project_root, sandbox_manager),
        # "bandit_scan": BanditTool(project_root, sandbox_manager),
        # NOTE: Smart audit policy: gitleaks_scan is disabled in orchestrated audit flow.
        # "gitleaks_scan": GitleaksTool(project_root, sandbox_manager),
        # "npm_audit": NpmAuditTool(project_root, sandbox_manager),
        # "safety_scan": SafetyTool(project_root, sandbox_manager),
        # "trufflehog_scan": TruffleHogTool(project_root, sandbox_manager),
        # "osv_scan": OSVScannerTool(project_root, sandbox_manager),
        # "pmd_scan": PMDTool(project_root, sandbox_manager),
        # "phpstan_scan": PHPStanTool(project_root, sandbox_manager),
    }
    
    # 🔥 完成工具集构建后，补充完整工具集给 business_logic_scan
    # 这确保 Sub Agent 有足够的工具在各个分析阶段使用
    business_logic_scan_core_tools.update({
        "extract_function": analysis_tools["extract_function"],
        "pattern_match": analysis_tools["pattern_match"],
        "dataflow_analysis": analysis_tools["dataflow_analysis"],
        "controlflow_analysis_light": analysis_tools["controlflow_analysis_light"],
        "logic_authz_analysis": analysis_tools["logic_authz_analysis"],
    })
    analysis_tools["business_logic_scan"].tools_registry = business_logic_scan_core_tools
    logger.info(
        "[Tools] Business Logic Scanner enabled with %d tools: %s",
        len(business_logic_scan_core_tools),
        project_root,
    )
    # 🔥 导入沙箱工具
    from app.services.agent.tools import (
        SandboxTool, SandboxHttpTool, VulnerabilityVerifyTool,
        # 多语言代码测试工具
        PhpTestTool, PythonTestTool, JavaScriptTestTool, JavaTestTool,
        GoTestTool, RubyTestTool, ShellTestTool, UniversalCodeTestTool,
        # 漏洞验证专用工具
        CommandInjectionTestTool, SqlInjectionTestTool, XssTestTool,
        PathTraversalTestTool, SstiTestTool, DeserializationTestTool,
        UniversalVulnTestTool,
        # 🔥 新增：通用代码执行工具 (LLM 驱动的 Fuzzing Harness)
        RunCodeTool, ExtractFunctionTool,
    )
    # Verification 工具
    verification_tools = {
        **base_tools,
        **mcp_read_tools,
        **mcp_write_tools,
        # 🔥 沙箱验证工具
        "sandbox_exec": SandboxTool(sandbox_manager),
        "sandbox_http": SandboxHttpTool(sandbox_manager),
        "verify_vulnerability": VulnerabilityVerifyTool(sandbox_manager),

        # 🔥 多语言代码测试工具
        "php_test": PhpTestTool(sandbox_manager, project_root),
        "python_test": PythonTestTool(sandbox_manager, project_root),
        "javascript_test": JavaScriptTestTool(sandbox_manager, project_root),
        "java_test": JavaTestTool(sandbox_manager, project_root),
        "go_test": GoTestTool(sandbox_manager, project_root),
        "ruby_test": RubyTestTool(sandbox_manager, project_root),
        "shell_test": ShellTestTool(sandbox_manager, project_root),
        "universal_code_test": UniversalCodeTestTool(sandbox_manager, project_root),
        
        # 🔥 漏洞验证专用工具
        "test_command_injection": CommandInjectionTestTool(sandbox_manager, project_root),
        "test_sql_injection": SqlInjectionTestTool(sandbox_manager, project_root),
        "test_xss": XssTestTool(sandbox_manager, project_root),
        "test_path_traversal": PathTraversalTestTool(sandbox_manager, project_root),
        "test_ssti": SstiTestTool(sandbox_manager, project_root),
        "test_deserialization": DeserializationTestTool(sandbox_manager, project_root),
        "universal_vuln_test": UniversalVulnTestTool(sandbox_manager, project_root),
        
        "run_code": RunCodeTool(sandbox_manager, project_root),
        "extract_function": ExtractFunctionTool(project_root),
        
        # !!! 存在问题，改用大模型判断
        # "dataflow_analysis": DataFlowAnalysisTool(llm_service, project_root=project_root),
        # "controlflow_analysis_light": ControlFlowAnalysisLightTool(
        #     project_root=project_root,
        #     target_files=target_files,
        # ),
        # "joern_reachability_verify": JoernReachabilityVerifyTool(
        #     project_root=project_root,
        #     enabled=bool(getattr(settings, "FLOW_JOERN_ENABLED", True)),
        #     timeout_sec=int(getattr(settings, "FLOW_JOERN_TIMEOUT_SEC", 45)),
        # ),
        # "logic_authz_analysis": LogicAuthzAnalysisTool(
        #     project_root=project_root,
        #     target_files=target_files,
        # ),

        # 报告工具 - 🔥 v2.1: 传递 project_root 用于文件验证
        "create_vulnerability_report": CreateVulnerabilityReportTool(project_root),
    }
    verification_tools.update(deprecated_skill_tools)

    # 🔥 验证结果保存工具（与 Analysis 队列工具相同的注入模式）
    if task_id:
        from app.services.agent.tools.verification_result_tools import SaveVerificationResultsTool
        _save_tool = SaveVerificationResultsTool(
            task_id=task_id,
            save_callback=save_callback,  # 可为 None，工具仍会缓存结果
        )
        verification_tools["save_verification_results"] = _save_tool
        logger.info("[Tools] Added save_verification_results tool for task %s", task_id)

    # Orchestrator 工具（主要是思考工具）
    orchestrator_tools = {
        "think": ThinkTool(),
        "reflect": ReflectTool(),
        **mcp_read_tools,
        **mcp_write_tools,
        **deprecated_skill_tools,
    }
    
    # 🔥 为 Orchestrator 添加队列管理工具
    if queue_service and task_id:
        orchestrator_tools["get_queue_status"] = GetQueueStatusTool(queue_service, task_id)
        orchestrator_tools["dequeue_finding"] = DequeueFindingTool(queue_service, task_id)
        logger.info(f"[Tools] Added queue management tools for task {task_id}")
    
    # 🔥 为 Analysis 添加队列工具
    if queue_service and task_id:
        analysis_tools["push_finding_to_queue"] = PushFindingToQueueTool(queue_service, task_id)
        analysis_tools["is_finding_in_queue"] = IsFindingInQueueTool(queue_service, task_id)
        logger.info(f"[Tools] Added analysis queue tools for task {task_id}")

    if recon_queue_service and task_id:
        orchestrator_tools["get_recon_risk_queue_status"] = GetReconRiskQueueStatusTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["dequeue_recon_risk_point"] = DequeueReconRiskPointTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["peek_recon_risk_queue"] = PeekReconRiskQueueTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["clear_recon_risk_queue"] = ClearReconRiskQueueTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["is_recon_risk_point_in_queue"] = IsReconRiskPointInQueueTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        logger.info(f"[Tools] Added Recon queue tools for task {task_id}")
    
    return {
        "recon": recon_tools,
        "analysis": analysis_tools,
        "verification": verification_tools,
        "orchestrator": orchestrator_tools,
    }


async def _collect_project_info(
    project_root: str, 
    project_name: str,
    exclude_patterns: Optional[List[str]] = None,
    target_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """收集项目信息
    
    Args:
        project_root: 项目根目录
        project_name: 项目名称
        exclude_patterns: 排除模式列表
        target_files: 目标文件列表
    
    🔥 重要：当指定了 target_files 时，返回的项目结构应该只包含目标文件相关的信息，
    以确保 Orchestrator 和子 Agent 看到的是一致的、过滤后的视图。
    """
    effective_exclude_patterns = _build_core_audit_exclude_patterns(exclude_patterns)

    info = {
        "name": project_name,
        "root": project_root,
        "languages": [],
        "file_count": 0,
        "structure": {},
    }
    
    try:
        # 目标文件集合
        target_files_set = (
            {_normalize_scan_path(path) for path in target_files if isinstance(path, str)}
            if target_files
            else None
        )
        
        lang_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".java": "Java", ".go": "Go", ".php": "PHP",
            ".rb": "Ruby", ".rs": "Rust", ".c": "C", ".cpp": "C++",
        }
        
        # 🔥 收集过滤后的文件列表
        filtered_files = []
        filtered_dirs = set()
        
        for root, dirs, files in os.walk(project_root):
            rel_dir = os.path.relpath(root, project_root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            dirs[:] = [
                d
                for d in dirs
                if not _is_core_ignored_path(
                    f"{rel_dir}/{d}" if rel_dir else d,
                    effective_exclude_patterns,
                )
            ]
            
            for f in files:
                relative_path = os.path.relpath(os.path.join(root, f), project_root)
                relative_path = relative_path.replace("\\", "/")
                
                # 检查是否在目标文件列表中
                if target_files_set and _normalize_scan_path(relative_path) not in target_files_set:
                    continue
                if _is_core_ignored_path(relative_path, effective_exclude_patterns):
                    continue
                
                info["file_count"] += 1
                filtered_files.append(relative_path)
                
                # 🔥 收集文件所在的目录
                dir_path = os.path.dirname(relative_path)
                if dir_path:
                    # 添加目录及其父目录
                    parts = dir_path.split(os.sep)
                    for i in range(len(parts)):
                        filtered_dirs.add(os.sep.join(parts[:i+1]))
                
                ext = os.path.splitext(f)[1].lower()
                if ext in lang_map and lang_map[ext] not in info["languages"]:
                    info["languages"].append(lang_map[ext])
        
        # 🔥 根据是否有目标文件限制，生成不同的结构信息
        if target_files_set:
            # 当指定了目标文件时，只显示目标文件和相关目录
            info["structure"] = {
                "directories": sorted(list(filtered_dirs))[:20],
                "files": filtered_files[:30],
                "scope_limited": True,  # 🔥 标记这是限定范围的视图
                "scope_message": f"审计范围限定为 {len(filtered_files)} 个指定文件",
            }
        else:
            # 全项目审计时，显示顶层目录结构
            try:
                top_items = os.listdir(project_root)
                info["structure"] = {
                    "directories": [
                        d
                        for d in top_items
                        if os.path.isdir(os.path.join(project_root, d))
                        and not _is_core_ignored_path(d, effective_exclude_patterns)
                    ],
                    "files": [
                        f
                        for f in top_items
                        if os.path.isfile(os.path.join(project_root, f))
                        and not _is_core_ignored_path(f, effective_exclude_patterns)
                    ][:20],
                    "scope_limited": False,
                }
            except Exception:
                pass
            
    except Exception as e:
        logger.warning(f"Failed to collect project info: {e}")
    
    return info


def _safe_text(value: Any) -> str:
    """将任意结构安全转换为文本，避免保存时意外截断或类型错误。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)
    return str(value)


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _normalize_optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = _safe_text(value).strip()
    return text or None


def _normalize_relative_file_path(path_value: str, project_root: Optional[str]) -> str:
    normalized = path_value.replace("\\", "/").strip()
    if not normalized:
        return normalized
    if not project_root:
        if os.path.isabs(normalized):
            return os.path.basename(normalized)
        while normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized
    try:
        rel = os.path.relpath(normalized, project_root)
        if not rel.startswith(".."):
            return rel.replace("\\", "/")
    except Exception:
        pass
    if os.path.isabs(normalized):
        return os.path.basename(normalized)
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


_ABS_PATH_IN_TEXT_RE = re.compile(r"(?P<path>(?:[A-Za-z]:[\\/]|/)[^\s:]+)")


def _sanitize_text_paths(value: Any, project_root: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    if not text.strip():
        return None
    normalized_text = text.replace("\\", "/")

    def _replace(match: re.Match[str]) -> str:
        matched_path = str(match.group("path") or "")
        if not matched_path:
            return match.group(0)
        return _normalize_relative_file_path(matched_path, project_root)

    return _ABS_PATH_IN_TEXT_RE.sub(_replace, normalized_text)


def _resolve_finding_file_path(
    raw_file_path: Optional[str],
    project_root: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    if not raw_file_path:
        return None, None

    candidate = raw_file_path.strip()
    candidate = re.sub(r":\d+(?:-\d+)?\s*$", "", candidate).strip()
    if not candidate:
        return None, None

    candidate = candidate.replace("\\", "/")
    path_candidates: List[Path] = []
    raw_path = Path(candidate)
    path_candidates.append(raw_path)

    if project_root:
        root_path = Path(project_root)
        path_candidates.append(root_path / candidate)
        if candidate.startswith("./"):
            path_candidates.append(root_path / candidate[2:])

    for path_obj in path_candidates:
        try:
            resolved = path_obj.resolve()
        except Exception:
            continue
        if resolved.is_file():
            stored = _normalize_relative_file_path(str(resolved), project_root)
            return stored, str(resolved)

    # Fallback: 尝试按后缀路径或 basename 在项目根目录中匹配，降低模型路径漂移导致的全量过滤
    if project_root:
        try:
            root_path = Path(project_root).resolve()
            normalized_candidate = candidate.lstrip("./")
            candidate_parts = [part for part in normalized_candidate.split("/") if part]

            # 1) 逐级裁剪前缀，按 suffix 尝试匹配
            for idx in range(len(candidate_parts)):
                suffix_candidate = root_path.joinpath(*candidate_parts[idx:])
                if suffix_candidate.is_file():
                    resolved = suffix_candidate.resolve()
                    stored = _normalize_relative_file_path(str(resolved), project_root)
                    return stored, str(resolved)

            # 2) basename 唯一匹配兜底（限制匹配数量避免大仓库扫描过慢）
            if candidate_parts:
                basename = candidate_parts[-1]
                matches: List[Path] = []
                for matched in root_path.rglob(basename):
                    if matched.is_file():
                        matches.append(matched)
                    if len(matches) > 8:
                        break

                if len(matches) == 1:
                    resolved = matches[0].resolve()
                    stored = _normalize_relative_file_path(str(resolved), project_root)
                    return stored, str(resolved)

                if len(matches) > 1:
                    suffix_text = "/".join(candidate_parts[-3:]) if len(candidate_parts) >= 3 else normalized_candidate
                    normalized_suffix = suffix_text.replace("\\", "/")
                    for matched in matches:
                        matched_posix = matched.as_posix()
                        if matched_posix.endswith(normalized_suffix):
                            resolved = matched.resolve()
                            stored = _normalize_relative_file_path(str(resolved), project_root)
                            return stored, str(resolved)
        except Exception:
            pass

    return None, None


def _infer_line_range_from_snippet(
    file_lines: List[str],
    snippet: Optional[str],
) -> Tuple[Optional[int], Optional[int]]:
    if not snippet:
        return None, None

    snippet_text = snippet.strip("\n")
    if not snippet_text:
        return None, None

    file_text = "\n".join(file_lines)
    first_index = file_text.find(snippet_text)
    if first_index < 0:
        return None, None
    if file_text.find(snippet_text, first_index + 1) >= 0:
        return None, None

    line_start = file_text.count("\n", 0, first_index) + 1
    line_count = max(1, snippet_text.count("\n") + 1)
    line_end = line_start + line_count - 1
    return line_start, line_end


def _extract_location_parts(finding: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    location = finding.get("location")
    if not location or not isinstance(location, str):
        return None, None
    location = location.strip()
    if not location:
        return None, None

    if ":" not in location:
        return location, None

    file_part, line_part = location.split(":", 1)
    line_num = _to_int(line_part.split("-", 1)[0].strip())
    return file_part.strip(), line_num


def _build_code_windows(
    file_lines: List[str],
    line_start: int,
    line_end: int,
    radius: int = 3,
) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[int]]:
    if not file_lines:
        return None, None, None, None

    total_lines = len(file_lines)
    safe_start = max(1, min(line_start, total_lines))
    safe_end = max(safe_start, min(line_end, total_lines))

    snippet_start_idx = safe_start - 1
    snippet_end_idx = safe_end
    snippet = "\n".join(file_lines[snippet_start_idx:snippet_end_idx]).strip("\n")

    context_start = max(1, safe_start - radius)
    context_end = min(total_lines, safe_end + radius)
    context_start_idx = context_start - 1
    context_end_idx = context_end
    context = "\n".join(file_lines[context_start_idx:context_end_idx]).strip("\n")

    if not context:
        return None, None, None, None
    if not snippet:
        snippet = context

    return snippet, context, context_start, context_end


def _normalize_authenticity_verdict(
    finding: Dict[str, Any],
    confidence: float,
) -> Optional[str]:
    verdict = finding.get("authenticity") or finding.get("verdict")
    if isinstance(verdict, str):
        verdict = verdict.strip().lower()
    else:
        verdict = None

    allowed = {"confirmed", "likely", "false_positive"}
    if verdict in allowed:
        return verdict

    if finding.get("is_verified") is True:
        return "confirmed"
    source_value = str(finding.get("source") or "").lower()
    if source_value in {"verification", "verification_agent", "agent_verification"}:
        return "confirmed"
    if source_value in {"analysis", "analysis_agent", "recon_high_risk", "bootstrap"}:
        return "likely"
    if confidence >= 0.85:
        return "likely"
    if confidence <= 0.2:
        return "false_positive"
    return "likely"


def _normalize_reachability(
    finding: Dict[str, Any],
    verdict: str,
) -> Optional[str]:
    value = finding.get("reachability")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"reachable", "likely_reachable", "unreachable"}:
            return normalized

    if verdict == "confirmed":
        return "reachable"
    if verdict == "likely":
        return "likely_reachable"
    if verdict == "false_positive":
        return "unreachable"
    return "likely_reachable"


def _normalize_cwe_id(value: Any) -> Optional[str]:
    return normalize_cwe_id_util(value)


def _extract_cwe_from_references(references: Any) -> Optional[str]:
    if references is None:
        return None
    if isinstance(references, list):
        for item in references:
            normalized = _normalize_cwe_id(item)
            if normalized:
                return normalized
        return None
    return _normalize_cwe_id(references)


def _resolve_vulnerability_profile(
    vulnerability_type: Optional[str],
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    code_snippet: Optional[str] = None,
) -> Dict[str, str]:
    return resolve_vulnerability_profile_util(
        vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
    )


def _resolve_cwe_id(
    explicit_cwe: Any,
    vulnerability_type: Optional[str],
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    code_snippet: Optional[str] = None,
) -> Optional[str]:
    return resolve_cwe_id_util(
        explicit_cwe,
        vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
    )


def _build_structured_cn_description(
    *,
    file_path: Optional[str],
    function_name: Optional[str],
    vulnerability_type: Optional[str],
    title: Optional[str],
    description: Optional[str],
    code_snippet: Optional[str],
    cwe_id: Optional[str],
    raw_description: Optional[str],
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
    verification_evidence: Optional[str] = None,
    function_trigger_flow: Optional[List[str]] = None,
    code_context: Optional[str] = None,
) -> str:
    return build_cn_structured_description(
        file_path=file_path,
        function_name=function_name,
        vulnerability_type=vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
        cwe_id=cwe_id,
        raw_description=raw_description,
        line_start=line_start,
        line_end=line_end,
        verification_evidence=verification_evidence,
        function_trigger_flow=function_trigger_flow,
        code_context=code_context,
    )


def _build_structured_cn_description_markdown(
    *,
    file_path: Optional[str],
    function_name: Optional[str],
    vulnerability_type: Optional[str],
    title: Optional[str],
    description: Optional[str],
    code_snippet: Optional[str],
    code_context: Optional[str],
    cwe_id: Optional[str],
    raw_description: Optional[str],
    line_start: Optional[int] = None,
    line_end: Optional[int] = None,
    verification_evidence: Optional[str] = None,
    function_trigger_flow: Optional[List[str]] = None,
) -> str:
    return build_cn_structured_description_markdown(
        file_path=file_path,
        function_name=function_name,
        vulnerability_type=vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
        code_context=code_context,
        cwe_id=cwe_id,
        raw_description=raw_description,
        line_start=line_start,
        line_end=line_end,
        verification_evidence=verification_evidence,
        function_trigger_flow=function_trigger_flow,
    )


def _build_structured_cn_display_title(
    *,
    file_path: Optional[str],
    function_name: Optional[str],
    vulnerability_type: Optional[str],
    title: Optional[str],
    description: Optional[str],
    code_snippet: Optional[str],
) -> str:
    return build_cn_structured_title(
        file_path=file_path,
        function_name=function_name,
        vulnerability_type=vulnerability_type,
        title=title,
        description=description,
        code_snippet=code_snippet,
    )


def _extract_flow_call_chain(
    verification_payload: Dict[str, Any],
    dataflow_path: Optional[List[str]],
) -> List[str]:
    if isinstance(verification_payload, dict):
        flow_payload = verification_payload.get("flow")
        if isinstance(flow_payload, dict):
            raw_chain = flow_payload.get("call_chain")
            if isinstance(raw_chain, list):
                chain = [str(item).strip() for item in raw_chain if str(item).strip()]
                if chain:
                    return chain
    if isinstance(dataflow_path, list):
        chain = [str(item).strip() for item in dataflow_path if str(item).strip()]
        if chain:
            return chain
    return []


def _build_function_trigger_flow(
    *,
    call_chain: List[str],
    function_name: Optional[str],
    file_path: Optional[str],
    line_start: Optional[int],
    line_end: Optional[int],
) -> List[str]:
    filtered: List[str] = []
    if call_chain:
        if function_name:
            needle = function_name.lower()
            hit_index = -1
            for idx, step in enumerate(call_chain):
                if needle and needle in step.lower():
                    hit_index = idx
                    break
            if hit_index >= 0:
                filtered = call_chain[: hit_index + 1]
            else:
                filtered = call_chain[: min(3, len(call_chain))]
        else:
            filtered = call_chain[: min(3, len(call_chain))]

    location_text = file_path or "未知路径"
    if line_start is not None:
        if line_end is not None and line_end != line_start:
            location_text = f"{location_text}:{line_start}-{line_end}"
        else:
            location_text = f"{location_text}:{line_start}"

    terminal = (
        f"命中函数：{function_name}（{location_text}）"
        if function_name
        else f"命中位置：{location_text}"
    )
    if not filtered or filtered[-1] != terminal:
        filtered.append(terminal)
    return filtered


def _build_default_remediation(vuln_type: str) -> Tuple[str, str]:
    normalized = (vuln_type or "").lower()
    mapping: Dict[str, Tuple[str, str]] = {
        "sql_injection": (
            "使用参数化查询并对输入进行严格校验，避免字符串拼接 SQL。",
            'query = "SELECT * FROM users WHERE id = %s"\ncursor.execute(query, (user_id,))',
        ),
        "xss": (
            "对输出到页面的用户输入进行转义或使用安全模板 API。",
            "safe_output = html.escape(user_input)\nrender(safe_output)",
        ),
        "command_injection": (
            "禁止将用户输入直接拼接命令；改用白名单参数与安全 API。",
            "subprocess.run([\"cmd\", safe_arg], check=True)",
        ),
        "path_traversal": (
            "规范化并校验路径，限制访问在允许目录内。",
            "resolved = (base_dir / user_path).resolve()\nif not str(resolved).startswith(str(base_dir.resolve())):\n    raise ValueError(\"invalid path\")",
        ),
        "ssrf": (
            "对目标地址做白名单校验并阻断内网地址访问。",
            "if not is_allowed_url(target_url):\n    raise ValueError(\"blocked url\")",
        ),
    }
    if normalized in mapping:
        return mapping[normalized]
    return (
        "补充输入校验与边界检查，移除危险调用并增加安全防护。",
        "// TODO: apply secure validation and safe API usage here",
    )


async def _enrich_findings_with_flow_and_logic(
    findings: List[Dict[str, Any]],
    *,
    project_root: Optional[str],
    target_files: Optional[List[str]],
    llm_service: Optional[Any] = None,
    event_emitter: Optional[Any] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """三轨流分析增强（Smart Audit 已禁用）。

    Smart audit policy disables the whole "flow enrichment / evidence generation" stage:
    - do not auto-run flow enrichment at the end of the audit
    - do not auto-generate trigger_flow / poc_trigger_chain evidence

    This function is kept as a stable API surface for backward compatibility, but always
    returns the input findings unchanged with a disabled summary.
    """
    _ = (project_root, target_files, llm_service, event_emitter)  # keep signature stable
    summary: Dict[str, Any] = {
        "total": len(findings or []),
        "enabled": False,
        "blocked_reason": "disabled_by_policy",
    }
    return findings, summary


async def _save_findings(
    db: AsyncSession,
    task_id: str,
    findings: List[Dict],
    project_root: Optional[str] = None,
    save_diagnostics: Optional[Dict[str, Any]] = None,
) -> int:
    """
    保存发现到数据库

    严格门禁版：
    - normalize -> enrich -> validate -> persist
    - 无文件定位、无可用上下文、无合法真实性/可达性的发现不入库

    Args:
        db: 数据库会话
        task_id: 任务ID
        findings: 发现列表
        project_root: 项目根目录（用于验证文件路径）

    Returns:
        int: 实际保存的发现数量
    """
    from app.models.agent_task import VulnerabilityType

    logger.info(f"[SaveFindings] Starting to save {len(findings)} findings for task {task_id}")

    if not findings:
        logger.warning(f"[SaveFindings] No findings to save for task {task_id}")
        return 0

    # 🔥 Case-insensitive mapping preparation
    severity_map = {
        "critical": VulnerabilitySeverity.CRITICAL,
        "high": VulnerabilitySeverity.HIGH,
        "medium": VulnerabilitySeverity.MEDIUM,
        "low": VulnerabilitySeverity.LOW,
        "info": VulnerabilitySeverity.INFO,
    }

    type_map = {
        "sql_injection": VulnerabilityType.SQL_INJECTION,
        "nosql_injection": VulnerabilityType.NOSQL_INJECTION,
        "xss": VulnerabilityType.XSS,
        "command_injection": VulnerabilityType.COMMAND_INJECTION,
        "code_injection": VulnerabilityType.CODE_INJECTION,
        "path_traversal": VulnerabilityType.PATH_TRAVERSAL,
        "ssrf": VulnerabilityType.SSRF,
        "xxe": VulnerabilityType.XXE,
        "auth_bypass": VulnerabilityType.AUTH_BYPASS,
        "idor": VulnerabilityType.IDOR,
        "sensitive_data_exposure": VulnerabilityType.SENSITIVE_DATA_EXPOSURE,
        "hardcoded_secret": VulnerabilityType.HARDCODED_SECRET,
        "deserialization": VulnerabilityType.DESERIALIZATION,
        "weak_crypto": VulnerabilityType.WEAK_CRYPTO,
        "file_inclusion": VulnerabilityType.FILE_INCLUSION,
        "race_condition": VulnerabilityType.RACE_CONDITION,
        "business_logic": VulnerabilityType.BUSINESS_LOGIC,
        "memory_corruption": VulnerabilityType.MEMORY_CORRUPTION,
    }

    saved_count = 0
    filtered_reasons: Dict[str, int] = {}
    logger.info(f"Saving {len(findings)} findings for task {task_id}")

    function_locator = None
    if project_root:
        try:
            from app.services.agent.flow.lightweight.function_locator import EnclosingFunctionLocator

            function_locator = EnclosingFunctionLocator(project_root=project_root)
        except Exception as exc:
            logger.warning("[SaveFindings] Function locator init failed: %s", exc)
            function_locator = None

    def mark_filtered(reason: str, payload: Optional[Dict[str, Any]] = None) -> None:
        filtered_reasons[reason] = filtered_reasons.get(reason, 0) + 1
        if payload:
            logger.warning(
                f"[SaveFindings] 🚫 Filtered finding ({reason}): "
                f"title={str(payload.get('title', 'N/A'))[:80]}"
            )

    for finding in findings:
        if not isinstance(finding, dict):
            logger.debug(f"[SaveFindings] Skipping non-dict finding: {type(finding)}")
            continue

        try:
            # 1) normalize severity
            raw_severity = str(
                finding.get("severity") or
                finding.get("risk") or
                "medium"
            ).lower().strip()
            severity_enum = severity_map.get(raw_severity, VulnerabilitySeverity.MEDIUM)

            # 2) normalize vulnerability type
            raw_type = str(
                finding.get("vulnerability_type") or
                finding.get("type") or
                finding.get("vuln_type") or
                "other"
            ).lower().strip().replace(" ", "_").replace("-", "_")
            type_profile = resolve_vulnerability_profile_util(
                raw_type,
                title=str(finding.get("title") or ""),
                description=str(finding.get("description") or ""),
                code_snippet=str(finding.get("code_snippet") or ""),
            )
            raw_type = str(type_profile.get("key") or raw_type)

            type_enum = type_map.get(raw_type, VulnerabilityType.OTHER)

            # 🔥 Additional fallback for common Agent output variations
            if "sqli" in raw_type or "sql" in raw_type:
                type_enum = VulnerabilityType.SQL_INJECTION
            if "xss" in raw_type:
                type_enum = VulnerabilityType.XSS
            if "rce" in raw_type or "command" in raw_type or "cmd" in raw_type:
                type_enum = VulnerabilityType.COMMAND_INJECTION
            if "traversal" in raw_type or "lfi" in raw_type or "rfi" in raw_type:
                type_enum = VulnerabilityType.PATH_TRAVERSAL
            if "ssrf" in raw_type:
                type_enum = VulnerabilityType.SSRF
            if "xxe" in raw_type:
                type_enum = VulnerabilityType.XXE
            if "auth" in raw_type:
                type_enum = VulnerabilityType.AUTH_BYPASS
            if "secret" in raw_type or "credential" in raw_type or "password" in raw_type:
                type_enum = VulnerabilityType.HARDCODED_SECRET
            if "deserial" in raw_type:
                type_enum = VulnerabilityType.DESERIALIZATION
            if raw_type in {
                "buffer_overflow",
                "stack_overflow",
                "heap_overflow",
                "use_after_free",
                "double_free",
                "out_of_bounds",
                "integer_overflow",
                "format_string",
                "null_pointer_deref",
            }:
                type_enum = VulnerabilityType.MEMORY_CORRUPTION

            # 3) normalize confidence
            confidence = finding.get("confidence") or finding.get("ai_confidence") or 0.5
            if isinstance(confidence, str):
                try:
                    confidence = float(confidence)
                except ValueError:
                    confidence = 0.5
            confidence = max(0.0, min(float(confidence), 1.0))

            verification_result_payload_input = finding.get("verification_result")
            if not isinstance(verification_result_payload_input, dict):
                mark_filtered("missing_verification_result", finding)
                continue

            # 4) strict verification gate
            authenticity_raw = (
                finding.get("authenticity")
                or finding.get("verdict")
                or verification_result_payload_input.get("authenticity")
                or verification_result_payload_input.get("verdict")
            )
            reachability_raw = (
                finding.get("reachability")
                or verification_result_payload_input.get("reachability")
            )
            evidence_raw = (
                finding.get("verification_details")
                or finding.get("verification_evidence")
                or verification_result_payload_input.get("verification_details")
                or verification_result_payload_input.get("verification_evidence")
                or verification_result_payload_input.get("evidence")
            )
            if not authenticity_raw or not reachability_raw or not evidence_raw:
                mark_filtered("missing_verification_result", finding)
                continue

            authenticity = str(authenticity_raw).strip().lower()
            if authenticity not in {"confirmed", "likely", "false_positive"}:
                mark_filtered("missing_verification_result", finding)
                continue
            if authenticity == "false_positive":
                mark_filtered("false_positive_discarded", finding)
                continue

            reachability = str(reachability_raw).strip().lower()
            if reachability not in {"reachable", "likely_reachable", "unreachable"}:
                mark_filtered("missing_verification_result", finding)
                continue
            verification_details_text = _normalize_optional_text(evidence_raw)
            if not verification_details_text:
                mark_filtered("missing_verification_result", finding)
                continue

            # 5) normalize file location
            location_file, location_line = _extract_location_parts(finding)
            raw_file_path = finding.get("file_path") or finding.get("file") or location_file
            stored_file_path, full_file_path = _resolve_finding_file_path(
                str(raw_file_path) if raw_file_path else None,
                project_root,
            )
            if not stored_file_path or not full_file_path:
                mark_filtered("missing_or_invalid_file_path", finding)
                continue
            if _is_core_ignored_path(stored_file_path):
                mark_filtered("ignored_scope_path", finding)
                continue

            try:
                file_content = Path(full_file_path).read_text(encoding="utf-8", errors="replace")
            except Exception:
                mark_filtered("file_read_failed", finding)
                continue

            file_lines = file_content.splitlines()
            if not file_lines:
                mark_filtered("empty_file_content", finding)
                continue

            # 6) normalize line range
            line_start = _to_int(finding.get("line_start")) or _to_int(finding.get("line")) or location_line
            line_end = _to_int(finding.get("line_end"))

            # 7) normalize snippets
            code_snippet = (
                finding.get("code_snippet") or
                finding.get("code") or
                finding.get("vulnerable_code")
            )
            code_snippet_text = _normalize_optional_text(code_snippet)

            if line_start is None:
                inferred_start, inferred_end = _infer_line_range_from_snippet(file_lines, code_snippet_text)
                line_start = inferred_start
                if inferred_end is not None:
                    line_end = inferred_end

            if line_start is None:
                mark_filtered("missing_line_start", finding)
                continue
            if line_end is None:
                line_end = line_start

            total_lines = len(file_lines)
            line_start = max(1, min(line_start, total_lines))
            line_end = max(line_start, min(line_end, total_lines))

            snippet_text, context_text, context_start_line, context_end_line = _build_code_windows(
                file_lines=file_lines,
                line_start=line_start,
                line_end=line_end,
                radius=12,
            )
            if not context_text or context_start_line is None or context_end_line is None:
                mark_filtered("missing_code_context", finding)
                continue
            if not snippet_text:
                snippet_text = code_snippet_text
            if not snippet_text:
                snippet_text = "\n".join(file_lines[line_start - 1 : line_end]).strip()

            # 7.5) enforce enclosing function evidence (file + function)
            reachability_target_function = None
            reachability_target_start_line = None
            reachability_target_end_line = None
            locator_language = None
            locator_resolution_engine = None
            locator_diagnostics = None
            locator_resolution_method = None

            if function_locator:
                located = function_locator.locate(
                    full_file_path=full_file_path,
                    line_start=line_start,
                    relative_file_path=stored_file_path,
                    file_lines=file_lines,
                )
                func_name = located.get("function")
                if isinstance(func_name, str) and func_name.strip():
                    reachability_target_function = func_name.strip()
                    reachability_target_start_line = _to_int(located.get("start_line"))
                    reachability_target_end_line = _to_int(located.get("end_line"))
                locator_language = located.get("language")
                locator_resolution_engine = located.get("resolution_engine")
                locator_resolution_method = located.get("resolution_method")
                locator_diagnostics = located.get("diagnostics")

            if not reachability_target_function:
                mark_filtered("missing_enclosing_function", finding)
                continue

            # 8) title/description/suggestion
            title = finding.get("title")
            if not title:
                type_display = raw_type.replace("_", " ").title()
                if stored_file_path:
                    title = f"{type_display} in {os.path.basename(stored_file_path)}"
                else:
                    title = f"{type_display} Vulnerability"
            title_text = str(title).strip() if title is not None else "Unknown Vulnerability"
            if not title_text:
                title_text = "Unknown Vulnerability"

            description = (
                finding.get("description") or
                finding.get("details") or
                finding.get("explanation") or
                finding.get("impact") or
                ""
            )
            description_text = _safe_text(description)

            suggestion = (
                finding.get("suggestion") or
                finding.get("recommendation") or
                finding.get("remediation") or
                finding.get("fix")
            )
            suggestion_text = _safe_text(suggestion) if suggestion is not None else None
            fix_code_text = _normalize_optional_text(
                finding.get("fix_code")
                or finding.get("patch")
                or finding.get("patch_snippet")
            )
            fix_description_text = _normalize_optional_text(
                finding.get("fix_description")
                or finding.get("fix_explanation")
                or finding.get("remediation_details")
            )

            if not suggestion_text or not fix_code_text:
                default_suggestion, default_fix_code = _build_default_remediation(raw_type)
                if not suggestion_text:
                    suggestion_text = default_suggestion
                if not fix_code_text:
                    fix_code_text = default_fix_code
                if not fix_description_text:
                    fix_description_text = "基于漏洞类型自动补全修复建议，请结合业务逻辑复核。"

            # 9) verification metadata
            is_verified = authenticity in {"confirmed", "likely"}
            verification_method_text = _normalize_optional_text(finding.get("verification_method"))
            if not verification_method_text:
                verification_method_text = "agent_verification"

            verification_result_payload = dict(verification_result_payload_input)
            existing_reachability_target = (
                verification_result_payload_input.get("reachability_target")
                if isinstance(verification_result_payload_input, dict)
                else None
            )
            if not isinstance(existing_reachability_target, dict):
                existing_reachability_target = {}
            verification_result_payload.update(
                {
                    "reachability": reachability,
                    "authenticity": authenticity,
                    "evidence": verification_details_text,
                    "context_start_line": context_start_line,
                    "context_end_line": context_end_line,
                    "reachability_target": {
                        "file_path": stored_file_path,
                        "function": reachability_target_function,
                        "start_line": reachability_target_start_line,
                        "end_line": reachability_target_end_line,
                        "resolution_method": (
                            locator_resolution_method
                            or existing_reachability_target.get("resolution_method")
                        ),
                        "language": locator_language or existing_reachability_target.get("language"),
                        "resolution_engine": locator_resolution_engine or existing_reachability_target.get("resolution_engine"),
                        "diagnostics": locator_diagnostics or existing_reachability_target.get("diagnostics"),
                    },
                }
            )

            # 9.5) Smart audit policy: do not require trigger_flow evidence as a persistence gate.

            dataflow_path = finding.get("dataflow_path")
            if not isinstance(dataflow_path, list):
                flow_payload = verification_result_payload.get("flow")
                if isinstance(flow_payload, dict):
                    chain = flow_payload.get("call_chain")
                    if isinstance(chain, list):
                        dataflow_path = [str(item) for item in chain if str(item).strip()]
            if not isinstance(dataflow_path, list):
                dataflow_path = None
            flow_chain = _extract_flow_call_chain(
                verification_payload=verification_result_payload,
                dataflow_path=dataflow_path,
            )
            function_trigger_flow = _build_function_trigger_flow(
                call_chain=flow_chain,
                function_name=reachability_target_function,
                file_path=stored_file_path,
                line_start=line_start,
                line_end=line_end,
            )
            verification_result_payload["function_trigger_flow"] = function_trigger_flow
            dataflow_path = function_trigger_flow if function_trigger_flow else dataflow_path
            source_text = _normalize_optional_text(finding.get("source"))
            sink_text = _normalize_optional_text(finding.get("sink"))

            # 10) PoC info
            poc_data = finding.get("poc", {})
            has_poc = bool(poc_data)
            poc_code = None
            poc_description = None
            poc_steps = None

            if isinstance(poc_data, dict):
                poc_description = poc_data.get("description")
                poc_steps = poc_data.get("steps")
                poc_code = poc_data.get("payload") or poc_data.get("code")
            elif isinstance(poc_data, str):
                poc_description = poc_data

            allow_poc = authenticity == "confirmed" and str(severity_enum).lower() in {"critical", "high"}
            if not allow_poc:
                has_poc = False
                poc_code = None
                poc_description = None
                poc_steps = None

    # 11) optional CVSS/CWE
            cwe_id = _resolve_cwe_id(
                finding.get("cwe_id") or finding.get("cwe"),
                raw_type,
                title=title_text,
                description=description_text,
                code_snippet=snippet_text,
            )
            cvss_score = finding.get("cvss_score") or finding.get("cvss")
            if isinstance(cvss_score, str):
                try:
                    cvss_score = float(cvss_score)
                except ValueError:
                    cvss_score = None

            # 12) Deduplication and Persistence
            # Logic: If a finding with same fingerprint exists for this task, update it.
            # fingerprint components: type, file_path, line_start, function_name, code_snippet(prefix)
            temp_finding = AgentFinding(
                vulnerability_type=type_enum,
                file_path=stored_file_path,
                line_start=line_start,
                function_name=reachability_target_function,
                code_snippet=snippet_text,
            )
            fingerprint = temp_finding.generate_fingerprint()

            # Find existing finding in current task
            existing_finding_stmt = select(AgentFinding).where(
                AgentFinding.task_id == task_id,
                AgentFinding.fingerprint == fingerprint
            )
            existing_finding_result = await db.execute(existing_finding_stmt)
            db_finding = existing_finding_result.scalar_one_or_none()

            if db_finding:
                logger.info(f"[SaveFindings] Updating existing finding {db_finding.id} (fingerprint: {fingerprint})")
                # Update fields
                db_finding.severity = severity_enum
                db_finding.title = title_text
                db_finding.description = description_text
                db_finding.line_end = line_end
                db_finding.code_context = context_text
                db_finding.source = source_text
                db_finding.sink = sink_text
                db_finding.dataflow_path = dataflow_path
                db_finding.suggestion = suggestion_text
                db_finding.fix_code = fix_code_text
                db_finding.fix_description = fix_description_text
                db_finding.is_verified = is_verified
                db_finding.ai_confidence = confidence
                db_finding.status = FindingStatus.FALSE_POSITIVE if authenticity == "false_positive" else FindingStatus.VERIFIED
                db_finding.has_poc = has_poc
                db_finding.poc_code = poc_code
                db_finding.poc_description = poc_description
                db_finding.poc_steps = poc_steps
                db_finding.verification_method = verification_method_text
                db_finding.verification_result = verification_result_payload
                db_finding.cvss_score = cvss_score
                db_finding.references = [{"cwe": cwe_id}] if cwe_id else None
                db_finding.updated_at = func.now()
            else:
                db_finding = AgentFinding(
                    id=str(uuid4()),
                    task_id=task_id,
                    vulnerability_type=type_enum,
                    severity=severity_enum,
                    title=title_text,
                    description=description_text,
                    file_path=stored_file_path,
                    line_start=line_start,
                    line_end=line_end,
                    code_snippet=snippet_text,
                    code_context=context_text,
                    function_name=reachability_target_function,
                    source=source_text,
                    sink=sink_text,
                    dataflow_path=dataflow_path,
                    suggestion=suggestion_text,
                    fix_code=fix_code_text,
                    fix_description=fix_description_text,
                    is_verified=is_verified,
                    ai_confidence=confidence,
                    status=FindingStatus.FALSE_POSITIVE if authenticity == "false_positive" else FindingStatus.VERIFIED,
                    has_poc=has_poc,
                    poc_code=poc_code,
                    poc_description=poc_description,
                    poc_steps=poc_steps,
                    verification_method=verification_method_text,
                    verification_result=verification_result_payload,
                    cvss_score=cvss_score,
                    references=[{"cwe": cwe_id}] if cwe_id else None,
                    fingerprint=fingerprint,
                )
                db.add(db_finding)
            
            saved_count += 1
            logger.debug(f"[SaveFindings] Prepared finding: {title_text[:50]}... ({severity_enum})")

        except Exception as e:
            logger.warning(f"Failed to save finding: {e}, data: {finding}")
            import traceback
            logger.debug(f"[SaveFindings] Traceback: {traceback.format_exc()}")

    logger.info(f"Successfully prepared {saved_count} findings for commit")
    if filtered_reasons:
        logger.info(
            "[SaveFindings] Filter summary for task %s: %s",
            task_id,
            json.dumps(filtered_reasons, ensure_ascii=False),
        )
    if isinstance(save_diagnostics, dict):
        save_diagnostics.clear()
        save_diagnostics.update(
            {
                "input_count": len(findings),
                "saved_count": saved_count,
                "filtered_count": sum(filtered_reasons.values()),
                "filtered_reasons": dict(filtered_reasons),
            }
        )

    try:
        await db.commit()
        logger.info(f"[SaveFindings] Successfully committed {saved_count} findings to database")
    except Exception as e:
        logger.error(f"Failed to commit findings: {e}")
        await db.rollback()
        if isinstance(save_diagnostics, dict):
            save_diagnostics["commit_failed"] = True
        return 0

    return saved_count


def _calculate_security_score(findings: List[Dict]) -> float:
    """计算安全评分"""
    if not findings:
        return 100.0

    # 基于发现的严重程度计算扣分
    deductions = {
        "critical": 25,
        "high": 15,
        "medium": 8,
        "low": 3,
        "info": 1,
    }

    total_deduction = 0
    for f in findings:
        if isinstance(f, dict):
            sev = f.get("severity", "low")
            total_deduction += deductions.get(sev, 3)

    score = max(0, 100 - total_deduction)
    return float(score)


def _collect_orchestrator_stats(orchestrator: Any) -> Dict[str, int]:
    """
    收集 orchestrator + sub agents 统计快照。

    返回字段：
    - iterations
    - tool_calls
    - tokens_used
    """
    totals = {
        "iterations": 0,
        "tool_calls": 0,
        "tokens_used": 0,
    }
    if not orchestrator or not hasattr(orchestrator, "get_stats"):
        return totals

    try:
        stats = orchestrator.get_stats() or {}
    except Exception:
        stats = {}

    totals["iterations"] = int(stats.get("iterations") or 0)
    totals["tool_calls"] = int(stats.get("tool_calls") or 0)
    totals["tokens_used"] = int(stats.get("tokens_used") or 0)

    if hasattr(orchestrator, "sub_agents"):
        for agent in (getattr(orchestrator, "sub_agents", {}) or {}).values():
            if not hasattr(agent, "get_stats"):
                continue
            try:
                sub_stats = agent.get_stats() or {}
            except Exception:
                continue
            totals["iterations"] += int(sub_stats.get("iterations") or 0)
            totals["tool_calls"] += int(sub_stats.get("tool_calls") or 0)
            totals["tokens_used"] += int(sub_stats.get("tokens_used") or 0)

    return totals


def _snapshot_runtime_stats_to_task(task: AgentTask, orchestrator: Any) -> Dict[str, int]:
    """
    将运行时统计快照写入 task，并使用 max 保留历史更大值。
    """
    snapshot = _collect_orchestrator_stats(orchestrator)

    task.total_iterations = max(int(task.total_iterations or 0), int(snapshot["iterations"]))
    task.tool_calls_count = max(int(task.tool_calls_count or 0), int(snapshot["tool_calls"]))
    task.tokens_used = max(int(task.tokens_used or 0), int(snapshot["tokens_used"]))
    return snapshot


async def _save_agent_tree(db: AsyncSession, task_id: str) -> None:
    """
    保存 Agent 树到数据库

    🔥 在任务完成前调用，将内存中的 Agent 树持久化到数据库
    """
    from app.models.agent_task import AgentTreeNode
    from app.services.agent.core import agent_registry

    try:
        tree = agent_registry.get_agent_tree()
        nodes = tree.get("nodes", {})

        if not nodes:
            logger.warning(f"[SaveAgentTree] No agent nodes to save for task {task_id}")
            return

        logger.info(f"[SaveAgentTree] Saving {len(nodes)} agent nodes for task {task_id}")

        # 计算每个节点的深度
        def get_depth(agent_id: str, visited: set = None) -> int:
            if visited is None:
                visited = set()
            if agent_id in visited:
                return 0
            visited.add(agent_id)
            node = nodes.get(agent_id)
            if not node:
                return 0
            parent_id = node.get("parent_id")
            if not parent_id:
                return 0
            return 1 + get_depth(parent_id, visited)

        saved_count = 0
        for agent_id, node_data in nodes.items():
            # 获取 Agent 实例的统计数据
            agent_instance = agent_registry.get_agent(agent_id)
            iterations = 0
            tool_calls = 0
            tokens_used = 0

            if agent_instance and hasattr(agent_instance, 'get_stats'):
                stats = agent_instance.get_stats()
                iterations = stats.get("iterations", 0)
                tool_calls = stats.get("tool_calls", 0)
                tokens_used = stats.get("tokens_used", 0)

            # 从结果中获取发现数量
            findings_count = 0
            result_summary = None
            if node_data.get("result"):
                result = node_data.get("result", {})
                if isinstance(result, dict):
                    findings_count = len(result.get("findings", []))
                    if result.get("summary"):
                        result_summary = str(result.get("summary"))[:2000]

            tree_node = AgentTreeNode(
                id=str(uuid4()),
                task_id=task_id,
                agent_id=agent_id,
                agent_name=node_data.get("name", "Unknown"),
                agent_type=node_data.get("type", "unknown"),
                parent_agent_id=node_data.get("parent_id"),
                depth=get_depth(agent_id),
                task_description=node_data.get("task"),
                knowledge_modules=node_data.get("knowledge_modules"),
                status=node_data.get("status", "unknown"),
                result_summary=result_summary,
                findings_count=findings_count,
                iterations=iterations,
                tool_calls=tool_calls,
                tokens_used=tokens_used,
            )
            db.add(tree_node)
            saved_count += 1

        await db.commit()
        logger.info(f"[SaveAgentTree] Successfully saved {saved_count} agent nodes to database")

    except Exception as e:
        logger.error(f"[SaveAgentTree] Failed to save agent tree: {e}", exc_info=True)
        await db.rollback()


# ============ API Endpoints ============

@router.post("/", response_model=AgentTaskResponse)
async def create_agent_task(
    request: AgentTaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    创建并启动 Agent 审计任务
    """
    # 验证项目
    project = await db.get(Project, request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    verification_level = _normalize_verification_level(request.verification_level)
    normalized_target_files = [
        item.strip()
        for item in (request.target_files or [])
        if isinstance(item, str) and item.strip()
    ]
    merged_exclude_patterns = _build_core_audit_exclude_patterns(request.exclude_patterns)
    normalized_audit_scope = (
        request.audit_scope if isinstance(request.audit_scope, dict) else None
    )
    
    # 创建任务
    task = AgentTask(
        id=str(uuid4()),
        project_id=project.id,
        name=request.name or f"Agent Audit - {datetime.now().strftime('%Y%m%d_%H%M%S')}",
        description=request.description,
        status=AgentTaskStatus.PENDING,
        current_phase=AgentTaskPhase.PLANNING,
        audit_scope=normalized_audit_scope,
        target_vulnerabilities=request.target_vulnerabilities,
        verification_level=verification_level,
        branch_name=request.branch_name,  # 保存用户选择的分支
        exclude_patterns=merged_exclude_patterns,
        target_files=normalized_target_files or None,
        agent_config={
            "authorization_confirmed": bool(request.authorization_confirmed),
        },
        max_iterations=request.max_iterations or 50,
        timeout_seconds=request.timeout_seconds or 1800,
        created_by=current_user.id,
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # 在后台启动任务（项目根目录在任务内部获取）
    background_tasks.add_task(_execute_agent_task, task.id)
    
    logger.info(f"Created agent task {task.id} for project {project.name}")
    
    return task


@router.get("/", response_model=List[AgentTaskResponse])
async def list_agent_tasks(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取 Agent 任务列表
    """
    # 获取用户的项目
    projects_result = await db.execute(
        select(Project.id)
    )
    user_project_ids = [p[0] for p in projects_result.fetchall()]
    
    if not user_project_ids:
        return []
    
    # 构建查询
    query = select(AgentTask).where(AgentTask.project_id.in_(user_project_ids))
    
    if project_id:
        query = query.where(AgentTask.project_id == project_id)
    
    if status:
        normalized_status = str(status).strip().lower()
        if normalized_status in _VALID_TASK_STATUS_VALUES:
            query = query.where(AgentTask.status == normalized_status)
    
    query = query.order_by(AgentTask.created_at.desc())
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    tasks = result.scalars().all()

    for task in tasks:
        task.verification_level = _normalize_verification_level(task.verification_level)

    return tasks


@router.get("/{task_id}", response_model=AgentTaskResponse)
async def get_agent_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取 Agent 任务详情
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 检查权限
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 构建响应，确保所有字段都包含
    try:
        # 计算进度百分比（由模型属性统一计算，终态不强制归零）
        progress = float(task.progress_percentage) if hasattr(task, "progress_percentage") else 0.0

        # 任务统计：DB 持久值 + 运行时值取 max，避免中断瞬间出现统计回退
        total_iterations = int(task.total_iterations or 0)
        tool_calls_count = int(task.tool_calls_count or 0)
        tokens_used = int(task.tokens_used or 0)

        orchestrator = _running_orchestrators.get(task_id)
        if orchestrator and task.status in (
            AgentTaskStatus.RUNNING,
            AgentTaskStatus.CANCELLED,
            AgentTaskStatus.FAILED,
        ):
            runtime_stats = _collect_orchestrator_stats(orchestrator)
            total_iterations = max(total_iterations, int(runtime_stats["iterations"]))
            tool_calls_count = max(tool_calls_count, int(runtime_stats["tool_calls"]))
            tokens_used = max(tokens_used, int(runtime_stats["tokens_used"]))
        
        # 手动构建响应数据
        response_data = {
            "id": task.id,
            "project_id": task.project_id,
            "name": task.name,
            "description": task.description,
            "task_type": task.task_type or "agent_audit",
            "status": task.status,
            "current_phase": task.current_phase,
            "current_step": task.current_step,
            "total_files": task.total_files or 0,
            "indexed_files": task.indexed_files or 0,
            "analyzed_files": task.analyzed_files or 0,
            "total_chunks": task.total_chunks or 0,
            "total_iterations": total_iterations,
            "tool_calls_count": tool_calls_count,
            "tokens_used": tokens_used,
            "findings_count": task.findings_count or 0,
            "total_findings": task.findings_count or 0,  # 兼容字段
            "verified_count": task.verified_count or 0,
            "verified_findings": task.verified_count or 0,  # 兼容字段
            "false_positive_count": task.false_positive_count or 0,
            "critical_count": task.critical_count or 0,
            "high_count": task.high_count or 0,
            "medium_count": task.medium_count or 0,
            "low_count": task.low_count or 0,
            "quality_score": float(task.quality_score or 0.0),
            "security_score": float(task.security_score) if task.security_score is not None else None,
            "progress_percentage": progress,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error_message": task.error_message,
            "audit_scope": task.audit_scope,
            "target_vulnerabilities": task.target_vulnerabilities,
            "verification_level": _normalize_verification_level(task.verification_level),
            "exclude_patterns": task.exclude_patterns,
            "target_files": task.target_files,
        }
        
        return AgentTaskResponse(**response_data)
    except Exception as e:
        logger.error(f"Error serializing task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"序列化任务数据失败: {str(e)}")


@router.post("/{task_id}/cancel")
async def cancel_agent_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    取消 Agent 任务
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权操作此任务")

    if task.status in [AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="任务已结束，无法取消")

    # 🔥 0. 立即标记任务为已取消（用于前置操作的取消检查）
    _cancelled_tasks.add(task_id)
    logger.info(f"[Cancel] Added task {task_id} to cancelled set")

    # 🔥 1. 设置 Agent 的取消标志
    runner = _running_tasks.get(task_id)
    if runner:
        runner.cancel()
        logger.info(f"[Cancel] Set cancel flag for task {task_id}")

    # 🔥 2. 通过 agent_registry 取消所有子 Agent
    from app.services.agent.core import agent_registry
    from app.services.agent.core.graph_controller import stop_all_agents
    try:
        # 停止所有 Agent（包括子 Agent）
        stop_result = stop_all_agents(exclude_root=False)
        logger.info(f"[Cancel] Stopped all agents: {stop_result}")
    except Exception as e:
        logger.warning(f"[Cancel] Failed to stop agents via registry: {e}")

    # 🔥 3. 强制取消 asyncio Task（立即中断 LLM 调用）
    asyncio_task = _running_asyncio_tasks.get(task_id)
    if asyncio_task and not asyncio_task.done():
        asyncio_task.cancel()
        logger.info(f"[Cancel] Cancelled asyncio task for {task_id}")

    # 取消前固化运行时统计，避免中断后查询显示归零
    orchestrator = _running_orchestrators.get(task_id)
    _snapshot_runtime_stats_to_task(task, orchestrator)

    # 更新状态
    task.status = AgentTaskStatus.CANCELLED
    task.completed_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(f"[Cancel] Task {task_id} cancelled successfully")
    return {"message": "任务已取消", "task_id": task_id}


@router.get("/{task_id}/events")
async def stream_agent_events(
    task_id: str,
    after_sequence: int = Query(0, ge=0, description="从哪个序号之后开始"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    获取 Agent 事件流 (SSE)
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    async def event_generator():
        """生成 SSE 事件流"""
        last_sequence = after_sequence
        poll_interval = 0.5
        max_idle = 300  # 5 分钟无事件后关闭
        idle_time = 0
        
        while True:
            # 查询新事件
            async with async_session_factory() as session:
                result = await session.execute(
                    select(AgentEvent)
                    .where(AgentEvent.task_id == task_id)
                    .where(AgentEvent.sequence > last_sequence)
                    .order_by(AgentEvent.sequence)
                    .limit(50)
                )
                events = result.scalars().all()
                
                # 获取任务状态
                current_task = await session.get(AgentTask, task_id)
                task_status = current_task.status if current_task else None
            
            if events:
                idle_time = 0
                for event in events:
                    last_sequence = event.sequence
                    # event_type 已经是字符串，不需要 .value
                    event_type_str = str(event.event_type)
                    phase_str = str(event.phase) if event.phase else None
                    
                    data = {
                        "id": event.id,
                        "type": event_type_str,
                        "phase": phase_str,
                        "message": event.message,
                        "sequence": event.sequence,
                        "timestamp": event.created_at.isoformat() if event.created_at else None,
                        "progress_percent": event.progress_percent,
                        "tool_name": event.tool_name,
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            else:
                idle_time += poll_interval
            
            # 检查任务是否结束
            if task_status:
                # task_status 可能是字符串或枚举，统一转换为字符串
                status_str = str(task_status)
                if status_str in ["completed", "failed", "cancelled"]:
                    yield f"data: {json.dumps({'type': 'task_end', 'status': status_str})}\n\n"
                    break
            
            # 检查空闲超时
            if idle_time >= max_idle:
                yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
                break
            
            await asyncio.sleep(poll_interval)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/{task_id}/stream")
async def stream_agent_with_thinking(
    task_id: str,
    include_thinking: bool = Query(True, description="是否包含 LLM 思考过程"),
    include_tool_calls: bool = Query(True, description="是否包含工具调用详情"),
    after_sequence: int = Query(0, ge=0, description="从哪个序号之后开始"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    增强版事件流 (SSE)
    
    支持:
    - LLM 思考过程的 Token 级流式输出 (仅运行时)
    - 工具调用的详细输入/输出
    - 节点执行状态
    - 发现事件
    
    优先使用内存中的事件队列 (支持 thinking_token)，
    如果任务未在运行，则回退到数据库轮询 (不支持 thinking_token 复盘)。
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 定义 SSE 格式化函数
    def format_sse_event(event_data: Dict[str, Any]) -> str:
        """格式化为 SSE 事件"""
        event_type = event_data.get("event_type") or event_data.get("type")
        
        # 统一字段
        if "type" not in event_data:
            event_data["type"] = event_type
            
        return f"event: {event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

    async def enhanced_event_generator():
        """生成增强版 SSE 事件流"""
        # 1. 检查任务是否在运行中 (内存)
        event_manager = _running_event_managers.get(task_id)
        
        if event_manager:
            logger.debug(f"Stream {task_id}: Using in-memory event manager")
            try:
                # 使用 EventManager 的流式接口
                # 过滤选项
                skip_types = set()
                if not include_thinking:
                    skip_types.update(["thinking_start", "thinking_token", "thinking_end"])
                if not include_tool_calls:
                    skip_types.update(["tool_call_start", "tool_call_input", "tool_call_output", "tool_call_end"])
                
                async for event in event_manager.stream_events(task_id, after_sequence=after_sequence):
                    event_type = event.get("event_type")
                    
                    if event_type in skip_types:
                        continue
                    
                    # 🔥 Debug: 记录 thinking_token 事件
                    if event_type == "thinking_token":
                        token = event.get("metadata", {}).get("token", "")[:20]
                        logger.debug(f"Stream {task_id}: Sending thinking_token: '{token}...'")
                        
                    # 格式化并 yield
                    yield format_sse_event(event)
                    
                    # 🔥 CRITICAL: 为 thinking_token 添加微小延迟
                    # 确保事件在不同的 TCP 包中发送，让前端能够逐个处理
                    # 没有这个延迟，所有 token 会在一次 read() 中被接收，导致 React 批量更新
                    if event_type == "thinking_token":
                        await asyncio.sleep(0.01)  # 10ms 延迟
                    
            except Exception as e:
                logger.error(f"In-memory stream error: {e}")
                err_data = {"type": "error", "message": str(e)}
                yield format_sse_event(err_data)
                
        else:
            logger.debug(f"Stream {task_id}: Task not running, falling back to DB polling")
            # 2. 回退到数据库轮询 (无法获取 thinking_token)
            last_sequence = after_sequence
            poll_interval = 2.0  # 完成的任务轮询可以慢一点
            heartbeat_interval = 15
            max_idle = 60  # 1分钟无事件关闭
            idle_time = 0
            last_heartbeat = 0
            
            skip_types = set()
            if not include_thinking:
                skip_types.update(["thinking_start", "thinking_token", "thinking_end"])
            
            while True:
                try:
                    async with async_session_factory() as session:
                        # 查询新事件
                        result = await session.execute(
                            select(AgentEvent)
                            .where(AgentEvent.task_id == task_id)
                            .where(AgentEvent.sequence > last_sequence)
                            .order_by(AgentEvent.sequence)
                            .limit(100)
                        )
                        events = result.scalars().all()
                        
                        # 获取任务状态
                        current_task = await session.get(AgentTask, task_id)
                        task_status = current_task.status if current_task else None
                    
                    if events:
                        idle_time = 0
                        for event in events:
                            last_sequence = event.sequence
                            event_type = str(event.event_type)
                            
                            if event_type in skip_types:
                                continue
                            
                            # 构建数据
                            data = {
                                "id": event.id,
                                "type": event_type,
                                "phase": str(event.phase) if event.phase else None,
                                "message": event.message,
                                "sequence": event.sequence,
                                "timestamp": event.created_at.isoformat() if event.created_at else None,
                            }
                            
                            # 添加详情
                            if include_tool_calls and event.tool_name:
                                data["tool"] = {
                                    "name": event.tool_name,
                                    "input": event.tool_input,
                                    "output": event.tool_output,
                                    "duration_ms": event.tool_duration_ms,
                                }
                                
                            if event.event_metadata:
                                data["metadata"] = event.event_metadata
                                
                            if event.tokens_used:
                                data["tokens_used"] = event.tokens_used
                            
                            yield format_sse_event(data)
                    else:
                        idle_time += poll_interval
                        
                        # 检查是否应该结束
                        if task_status:
                            status_str = str(task_status)
                            # 如果任务已完成且没有新事件，结束流
                            if status_str in ["completed", "failed", "cancelled"]:
                                end_data = {
                                    "type": "task_end",
                                    "status": status_str,
                                    "message": f"任务已{status_str}"
                                }
                                yield format_sse_event(end_data)
                                break
                    
                    # 心跳
                    last_heartbeat += poll_interval
                    if last_heartbeat >= heartbeat_interval:
                        last_heartbeat = 0
                        yield format_sse_event({"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()})
                    
                    # 超时
                    if idle_time >= max_idle:
                        break
                    
                    await asyncio.sleep(poll_interval)
                    
                except Exception as e:
                    logger.error(f"DB poll stream error: {e}")
                    yield format_sse_event({"type": "error", "message": str(e)})
                    break
    
    return StreamingResponse(
        enhanced_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8",
        }
    )


@router.get("/{task_id}/events/list", response_model=List[AgentEventResponse])
async def list_agent_events(
    task_id: str,
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取 Agent 事件列表
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.task_id == task_id)
        .where(AgentEvent.sequence > after_sequence)
        .order_by(AgentEvent.sequence)
        .limit(limit)
    )
    events = result.scalars().all()

    # 🔥 Debug logging
    logger.debug(f"[EventsList] Task {task_id}: returning {len(events)} events (after_sequence={after_sequence})")
    if events:
        logger.debug(f"[EventsList] First event: type={events[0].event_type}, seq={events[0].sequence}")
        if len(events) > 1:
            logger.debug(f"[EventsList] Last event: type={events[-1].event_type}, seq={events[-1].sequence}")

    return events


def _serialize_agent_findings(
    findings: List[AgentFinding],
    *,
    include_false_positive: bool,
) -> List[AgentFindingResponse]:
    responses: List[AgentFindingResponse] = []
    for item in findings:
        verification_payload = (
            item.verification_result
            if isinstance(item.verification_result, dict)
            else {}
        )
        normalized_item_file_path = _normalize_relative_file_path(
            str(item.file_path or ""),
            None,
        )
        authenticity = verification_payload.get("authenticity")
        if not authenticity:
            authenticity = (
                "false_positive"
                if str(item.status) == FindingStatus.FALSE_POSITIVE
                else ("confirmed" if item.is_verified else "likely")
            )
        authenticity = str(authenticity).lower()

        if not include_false_positive and authenticity == "false_positive":
            continue

        reachability = verification_payload.get("reachability")
        verification_evidence = (
            verification_payload.get("evidence") or verification_payload.get("details")
        )
        context_start_line = _to_int(verification_payload.get("context_start_line"))
        context_end_line = _to_int(verification_payload.get("context_end_line"))
        reachability_file = None
        reachability_function = None
        reachability_function_start_line = None
        reachability_function_end_line = None
        reachability_target = (
            verification_payload.get("reachability_target")
            if isinstance(verification_payload, dict)
            else None
        )
        if isinstance(reachability_target, dict):
            file_value = reachability_target.get("file_path")
            func_value = reachability_target.get("function")
            if isinstance(file_value, str) and file_value.strip():
                reachability_file = _normalize_relative_file_path(
                    file_value.strip(),
                    None,
                )
            if isinstance(func_value, str) and func_value.strip():
                reachability_function = func_value.strip()
            reachability_function_start_line = _to_int(
                reachability_target.get("start_line")
            )
            reachability_function_end_line = _to_int(
                reachability_target.get("end_line")
            )
        if not reachability_function:
            raw_function_name = getattr(item, "function_name", None)
            if isinstance(raw_function_name, str) and raw_function_name.strip():
                reachability_function = raw_function_name.strip()
        if not reachability_file and normalized_item_file_path:
            reachability_file = normalized_item_file_path
        flow_payload = (
            verification_payload.get("flow")
            if isinstance(verification_payload, dict)
            else None
        )
        flow_path_score = None
        flow_call_chain = None
        function_trigger_flow = None
        flow_control_conditions = None
        if isinstance(flow_payload, dict):
            try:
                flow_path_score = (
                    float(flow_payload.get("path_score"))
                    if flow_payload.get("path_score") is not None
                    else None
                )
            except Exception:
                flow_path_score = None
            raw_chain = flow_payload.get("call_chain")
            if isinstance(raw_chain, list):
                flow_call_chain = [
                    _sanitize_text_paths(step, None) or ""
                    for step in raw_chain
                    if str(step).strip()
                ]
                flow_call_chain = [step for step in flow_call_chain if step]
            raw_function_chain = flow_payload.get("function_trigger_flow")
            if isinstance(raw_function_chain, list):
                function_trigger_flow = [
                    _sanitize_text_paths(step, None) or ""
                    for step in raw_function_chain
                    if str(step).strip()
                ]
                function_trigger_flow = [
                    step for step in function_trigger_flow if step
                ]
            raw_controls = flow_payload.get("control_conditions")
            if isinstance(raw_controls, list):
                flow_control_conditions = [
                    _sanitize_text_paths(ctrl, None) or ""
                    for ctrl in raw_controls
                    if str(ctrl).strip()
                ]
                flow_control_conditions = [
                    ctrl for ctrl in flow_control_conditions if ctrl
                ]
        if not function_trigger_flow:
            raw_function_chain = verification_payload.get("function_trigger_flow")
            if isinstance(raw_function_chain, list):
                function_trigger_flow = [
                    _sanitize_text_paths(step, None) or ""
                    for step in raw_function_chain
                    if str(step).strip()
                ]
                function_trigger_flow = [
                    step for step in function_trigger_flow if step
                ]
        if not function_trigger_flow:
            function_trigger_flow = _build_function_trigger_flow(
                call_chain=flow_call_chain or [],
                function_name=reachability_function,
                file_path=reachability_file or normalized_item_file_path,
                line_start=item.line_start,
                line_end=item.line_end,
            )
        function_trigger_flow = [
            _sanitize_text_paths(step, None) or ""
            for step in (function_trigger_flow or [])
            if str(step).strip()
        ]
        function_trigger_flow = [step for step in function_trigger_flow if step]
        if function_trigger_flow:
            flow_call_chain = function_trigger_flow

        logic_payload = (
            verification_payload.get("logic_authz")
            if isinstance(verification_payload, dict)
            else None
        )
        logic_authz_evidence = None
        if isinstance(logic_payload, dict):
            raw_logic_evidence = logic_payload.get("evidence")
            if isinstance(raw_logic_evidence, list):
                logic_authz_evidence = [
                    str(raw_item)
                    for raw_item in raw_logic_evidence
                    if str(raw_item).strip()
                ]
            elif isinstance(raw_logic_evidence, str) and raw_logic_evidence.strip():
                logic_authz_evidence = [raw_logic_evidence.strip()]

        cwe_id = _extract_cwe_from_references(getattr(item, "references", None))
        if not cwe_id:
            cwe_id = _resolve_cwe_id(
                verification_payload.get("cwe_id") or verification_payload.get("cwe"),
                item.vulnerability_type,
                title=item.title,
                description=item.description,
                code_snippet=item.code_snippet,
            )
        profile = _resolve_vulnerability_profile(
            item.vulnerability_type,
            title=item.title,
            description=item.description,
            code_snippet=item.code_snippet,
        )
        structured_description = _build_structured_cn_description(
            file_path=normalized_item_file_path,
            function_name=reachability_function,
            vulnerability_type=profile["key"],
            title=item.title,
            description=item.description,
            code_snippet=item.code_snippet,
            code_context=item.code_context,
            cwe_id=cwe_id,
            raw_description=item.description,
            line_start=item.line_start,
            line_end=item.line_end,
            verification_evidence=verification_evidence,
            function_trigger_flow=function_trigger_flow,
        )
        structured_description_markdown = _build_structured_cn_description_markdown(
            file_path=normalized_item_file_path,
            function_name=reachability_function,
            vulnerability_type=profile["key"],
            title=item.title,
            description=item.description,
            code_snippet=item.code_snippet,
            code_context=item.code_context,
            cwe_id=cwe_id,
            raw_description=item.description,
            line_start=item.line_start,
            line_end=item.line_end,
            verification_evidence=verification_evidence,
            function_trigger_flow=function_trigger_flow,
        )
        display_title = _build_structured_cn_display_title(
            file_path=normalized_item_file_path,
            function_name=reachability_function,
            vulnerability_type=profile["key"],
            title=item.title,
            description=item.description,
            code_snippet=item.code_snippet,
        )

        responses.append(
            AgentFindingResponse.model_validate(
                {
                    "id": item.id,
                    "task_id": item.task_id,
                    "vulnerability_type": profile["key"],
                    "severity": item.severity,
                    "title": item.title,
                    "display_title": display_title,
                    "description": structured_description,
                    "description_markdown": structured_description_markdown,
                    "file_path": normalized_item_file_path,
                    "line_start": item.line_start,
                    "line_end": item.line_end,
                    "code_snippet": item.code_snippet,
                    "code_context": item.code_context,
                    "cwe_id": cwe_id,
                    "cwe_name": profile["name"],
                    "context_start_line": context_start_line,
                    "context_end_line": context_end_line,
                    "is_verified": item.is_verified,
                    "confidence": (
                        item.ai_confidence if item.ai_confidence is not None else 0.5
                    ),
                    "reachability": reachability,
                    "authenticity": authenticity,
                    "verification_evidence": verification_evidence,
                    "flow_path_score": flow_path_score,
                    "flow_call_chain": flow_call_chain,
                    "function_trigger_flow": function_trigger_flow,
                    "flow_control_conditions": flow_control_conditions,
                    "logic_authz_evidence": logic_authz_evidence,
                    "reachability_file": reachability_file,
                    "reachability_function": reachability_function,
                    "reachability_function_start_line": reachability_function_start_line,
                    "reachability_function_end_line": reachability_function_end_line,
                    "trigger_flow": (
                        verification_payload.get("trigger_flow")
                        if isinstance(verification_payload, dict)
                        else None
                    ),
                    "poc_trigger_chain": (
                        verification_payload.get("poc_trigger_chain")
                        if isinstance(verification_payload, dict)
                        else None
                    ),
                    "status": item.status,
                    "suggestion": item.suggestion,
                    # Backward-compatible for test stubs / older schemas.
                    "fix_code": getattr(item, "fix_code", None),
                    "fix_description": getattr(item, "fix_description", None),
                    "has_poc": bool(item.has_poc),
                    "poc_code": item.poc_code,
                    "poc_description": item.poc_description,
                    "poc_steps": (
                        item.poc_steps if isinstance(item.poc_steps, list) else None
                    ),
                    "poc": (
                        {
                            "code": item.poc_code,
                            "description": item.poc_description,
                            "steps": item.poc_steps,
                        }
                        if item.has_poc
                        else None
                    ),
                    "created_at": item.created_at,
                }
            )
        )
    return responses


@router.get("/{task_id}/findings", response_model=List[AgentFindingResponse])
async def list_agent_findings(
    task_id: str,
    severity: Optional[str] = None,
    verified_only: bool = False,
    include_false_positive: bool = Query(False, description="是否包含 false_positive 结果"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取 Agent 发现列表
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    query = select(AgentFinding).where(AgentFinding.task_id == task_id)
    if not include_false_positive:
        query = query.where(AgentFinding.status != FindingStatus.FALSE_POSITIVE)
    
    if severity:
        normalized_severity = str(severity).strip().lower()
        if normalized_severity in _VALID_SEVERITY_VALUES:
            query = query.where(AgentFinding.severity == normalized_severity)
    
    if verified_only:
        query = query.where(AgentFinding.is_verified == True)
    
    # 按严重程度排序
    severity_order = {
        VulnerabilitySeverity.CRITICAL: 0,
        VulnerabilitySeverity.HIGH: 1,
        VulnerabilitySeverity.MEDIUM: 2,
        VulnerabilitySeverity.LOW: 3,
        VulnerabilitySeverity.INFO: 4,
    }
    
    query = query.order_by(
        case(
            (AgentFinding.severity == VulnerabilitySeverity.CRITICAL, 0),
            (AgentFinding.severity == VulnerabilitySeverity.HIGH, 1),
            (AgentFinding.severity == VulnerabilitySeverity.MEDIUM, 2),
            (AgentFinding.severity == VulnerabilitySeverity.LOW, 3),
            (AgentFinding.severity == VulnerabilitySeverity.INFO, 4),
            else_=5,
        ),
        AgentFinding.created_at.desc(),
    )
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    findings = result.scalars().all()
    return _serialize_agent_findings(
        findings,
        include_false_positive=include_false_positive,
    )

@router.get("/{task_id}/findings/{finding_id}", response_model=AgentFindingResponse)
async def get_agent_finding(
    task_id: str,
    finding_id: str,
    include_false_positive: bool = Query(
        True,
        description="是否包含 false_positive 结果",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """获取 Agent 单条发现详情。"""
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    result = await db.execute(
        select(AgentFinding).where(
            (AgentFinding.task_id == task_id)
            & (AgentFinding.id == finding_id)
        )
    )
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="发现不存在")

    serialized = _serialize_agent_findings(
        [finding],
        include_false_positive=include_false_positive,
    )
    if not serialized:
        raise HTTPException(status_code=404, detail="发现不存在")
    return serialized[0]


@router.get("/{task_id}/summary", response_model=TaskSummaryResponse)
async def get_task_summary(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取任务摘要
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 获取所有发现
    result = await db.execute(
        select(AgentFinding).where(AgentFinding.task_id == task_id)
    )
    findings = result.scalars().all()
    
    # 统计
    severity_distribution = {}
    vulnerability_types = {}
    verified_count = 0
    
    for f in findings:
        # severity 和 vulnerability_type 已经是字符串
        sev = str(f.severity)
        vtype = str(f.vulnerability_type)
        
        severity_distribution[sev] = severity_distribution.get(sev, 0) + 1
        vulnerability_types[vtype] = vulnerability_types.get(vtype, 0) + 1
        
        if f.is_verified:
            verified_count += 1
    
    # 计算持续时间
    duration = None
    if task.started_at and task.completed_at:
        duration = int((task.completed_at - task.started_at).total_seconds())
    
    # 获取已完成的阶段
    phases_result = await db.execute(
        select(AgentEvent.phase)
        .where(AgentEvent.task_id == task_id)
        .where(AgentEvent.event_type == AgentEventType.PHASE_COMPLETE)
        .distinct()
    )
    phases = [str(p[0]) for p in phases_result.fetchall() if p[0]]
    
    return TaskSummaryResponse(
        task_id=task_id,
        status=str(task.status),  # status 已经是字符串
        security_score=task.security_score,
        total_findings=len(findings),
        verified_findings=verified_count,
        severity_distribution=severity_distribution,
        vulnerability_types=vulnerability_types,
        duration_seconds=duration,
        phases_completed=phases,
    )


@router.patch("/{task_id}/findings/{finding_id}/status")
async def update_finding_status(
    task_id: str,
    finding_id: str,
    status: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    更新发现状态
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权操作")
    
    finding = await db.get(AgentFinding, finding_id)
    if not finding or finding.task_id != task_id:
        raise HTTPException(status_code=404, detail="发现不存在")
    
    try:
        finding.status = FindingStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的状态: {status}")
    
    await db.commit()
    
    return {"message": "状态已更新", "finding_id": finding_id, "status": status}


# ============ Helper Functions ============

async def _get_project_root(
    project: Project,
    task_id: str,
    branch_name: Optional[str] = None,
    github_token: Optional[str] = None,
    gitlab_token: Optional[str] = None,
    gitea_token: Optional[str] = None,  # 🔥 新增
    ssh_private_key: Optional[str] = None,  # 🔥 新增：SSH私钥（用于SSH认证）
    event_emitter: Optional[Any] = None,  # 🔥 新增：用于发送实时日志
) -> str:
    """
    获取项目根目录

    支持两种项目类型：
    - ZIP 项目：解压 ZIP 文件到临时目录
    - 仓库项目：克隆仓库到临时目录

    Args:
        project: 项目对象
        task_id: 任务ID
        branch_name: 分支名称（仓库项目使用，优先于 project.default_branch）
        github_token: GitHub 访问令牌（用于私有仓库）
        gitlab_token: GitLab 访问令牌（用于私有仓库）
        gitea_token: Gitea 访问令牌（用于私有仓库）
        ssh_private_key: SSH私钥（用于SSH认证）
        event_emitter: 事件发送器（用于发送实时日志）

    Returns:
        项目根目录路径

    Raises:
        RuntimeError: 当项目文件获取失败时
    """
    import zipfile
    import subprocess
    import shutil
    from urllib.parse import urlparse, urlunparse

    # 辅助函数：发送事件
    async def emit(message: str, level: str = "info"):
        if event_emitter:
            if level == "info":
                await event_emitter.emit_info(message)
            elif level == "warning":
                await event_emitter.emit_warning(message)
            elif level == "error":
                await event_emitter.emit_error(message)

    # 🔥 辅助函数：检查取消状态
    def check_cancelled():
        if is_task_cancelled(task_id):
            raise asyncio.CancelledError("任务已取消")

    base_path = f"/tmp/deepaudit/{task_id}"

    # 确保目录存在且为空
    if os.path.exists(base_path):
        shutil.rmtree(base_path)
    os.makedirs(base_path, exist_ok=True)

    # 🔥 在开始任何操作前检查取消
    check_cancelled()

    # 根据项目类型处理
    if project.source_type == "zip":
        # 🔥 ZIP 项目：解压 ZIP 文件
        check_cancelled()  # 🔥 解压前检查
        await emit(f"📦 正在解压项目文件...")
        from app.services.zip_storage import load_project_zip

        zip_path = await load_project_zip(project.id)

        if zip_path and os.path.exists(zip_path):
            try:
                check_cancelled()  # 🔥 解压前再次检查
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # 🔥 逐个文件解压，支持取消检查
                    file_list = zip_ref.namelist()
                    for i, file_name in enumerate(file_list):
                        if i % 50 == 0:  # 每50个文件检查一次
                            check_cancelled()
                        zip_ref.extract(file_name, base_path)
                logger.info(f"✅ Extracted ZIP project {project.id} to {base_path}")
                await emit(f"✅ ZIP 文件解压完成")
            except Exception as e:
                logger.error(f"Failed to extract ZIP {zip_path}: {e}")
                await emit(f"❌ 解压失败: {e}", "error")
                raise RuntimeError(f"无法解压项目文件: {e}")
        else:
            logger.warning(f"⚠️ ZIP file not found for project {project.id}")
            await emit(f"❌ ZIP 文件不存在", "error")
            raise RuntimeError(f"项目 ZIP 文件不存在: {project.id}")

    elif project.source_type == "repository" and project.repository_url:
        # 🔥 仓库项目：优先使用 ZIP 下载（更快更稳定），git clone 作为回退
        repo_url = project.repository_url
        repo_type = project.repository_type or "other"

        await emit(f"🔄 正在获取仓库: {repo_url}")

        # 检测是否为SSH URL（SSH链接不支持ZIP下载）
        is_ssh_url = GitSSHOperations.is_ssh_url(repo_url)

        # 解析仓库 URL 获取 owner/repo
        parsed = urlparse(repo_url)
        path_parts = parsed.path.strip('/').replace('.git', '').split('/')
        if len(path_parts) >= 2:
            owner, repo = path_parts[0], path_parts[1]
        else:
            owner, repo = None, None

        # 构建分支尝试顺序
        branches_to_try = []
        if branch_name:
            branches_to_try.append(branch_name)
        if project.default_branch and project.default_branch not in branches_to_try:
            branches_to_try.append(project.default_branch)
        for common_branch in ["main", "master"]:
            if common_branch not in branches_to_try:
                branches_to_try.append(common_branch)

        download_success = False
        last_error = ""

        # ============ 方案1: 优先使用 ZIP 下载（更快更稳定）============
        # SSH链接直接跳过ZIP下载，使用git clone
        if is_ssh_url:
            logger.info(f"检测到SSH URL，跳过ZIP下载，直接使用Git克隆")
            await emit(f"🔑 检测到SSH认证，使用Git克隆...")

        if owner and repo and not is_ssh_url:
            import httpx

            for branch in branches_to_try:
                check_cancelled()

                # 清理目录
                if os.path.exists(base_path) and os.listdir(base_path):
                    shutil.rmtree(base_path)
                os.makedirs(base_path, exist_ok=True)

                # 构建 ZIP 下载 URL
                if repo_type == "github" or "github.com" in repo_url:
                    # GitHub ZIP 下载 URL
                    zip_url = f"https://gh-proxy.org/https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
                    headers = {}
                    if github_token:
                        headers["Authorization"] = f"token {github_token}"
                elif repo_type == "gitlab" or "gitlab" in repo_url:
                    # GitLab ZIP 下载 URL（需要对 owner/repo 进行 URL 编码）
                    import urllib.parse
                    project_path = urllib.parse.quote(f"{owner}/{repo}", safe='')
                    gitlab_host = parsed.netloc
                    zip_url = f"https://{gitlab_host}/api/v4/projects/{project_path}/repository/archive.zip?sha={branch}"
                    headers = {}
                    if gitlab_token:
                        headers["PRIVATE-TOKEN"] = gitlab_token
                else:
                    # 其他平台，跳过 ZIP 下载
                    break

                zip_url_candidates = get_mirror_candidates(
                    zip_url,
                    enabled=getattr(settings, "GIT_MIRROR_ENABLED", True),
                    mirror_prefix=getattr(settings, "GIT_MIRROR_PREFIX", "https://gh-proxy.org"),
                    mirror_prefixes=getattr(
                        settings, "GIT_MIRROR_PREFIXES", "https://gh-proxy.org,https://v6.gh-proxy.org"
                    ),
                    allow_hosts=getattr(settings, "GIT_MIRROR_HOSTS", "github.com"),
                    allow_auth_url=getattr(settings, "GIT_MIRROR_ALLOW_AUTH_URL", False),
                    fallback_to_origin=getattr(settings, "GIT_MIRROR_FALLBACK_TO_ORIGIN", False),
                )
                zip_has_origin_url = zip_url in zip_url_candidates

                logger.info(f"📦 尝试下载 ZIP 归档 (分支: {branch})...")
                await emit(f"📦 尝试下载 ZIP 归档 (分支: {branch})")

                try:
                    zip_temp_path = f"/tmp/repo_{task_id}_{branch}.zip"
                    success = False
                    error = None

                    for idx, candidate_zip_url in enumerate(zip_url_candidates):
                        using_mirror = candidate_zip_url != zip_url

                        async def download_zip():
                            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                                resp = await client.get(candidate_zip_url, headers=headers)
                                if resp.status_code == 200:
                                    with open(zip_temp_path, "wb") as f:
                                        f.write(resp.content)
                                    return True, None
                                return False, f"HTTP {resp.status_code}"

                        # 使用取消检查循环
                        download_task = asyncio.create_task(download_zip())
                        while not download_task.done():
                            check_cancelled()
                            try:
                                success, error = await asyncio.wait_for(
                                    asyncio.shield(download_task),
                                    timeout=1.0,
                                )
                                break
                            except asyncio.TimeoutError:
                                continue

                        if download_task.done():
                            success, error = download_task.result()

                        if success:
                            break
                        if using_mirror:
                            if idx < len(zip_url_candidates) - 1:
                                next_candidate = zip_url_candidates[idx + 1]
                                if next_candidate == zip_url:
                                    logger.warning(
                                        "ZIP 镜像下载失败，原因: %s，回源重试: %s",
                                        error,
                                        next_candidate,
                                    )
                                else:
                                    logger.warning(
                                        "ZIP 镜像下载失败，原因: %s，切换候选重试: %s",
                                        error,
                                        next_candidate,
                                    )
                            elif not zip_has_origin_url:
                                logger.warning("ZIP 镜像全部失败，已按策略终止当前候选（未启用回源）")

                    if success and os.path.exists(zip_temp_path):
                        # 解压 ZIP
                        check_cancelled()
                        with zipfile.ZipFile(zip_temp_path, 'r') as zip_ref:
                            # ZIP 内通常有一个根目录如 repo-branch/
                            file_list = zip_ref.namelist()
                            # 找到公共前缀
                            if file_list:
                                common_prefix = file_list[0].split('/')[0] + '/'
                                for i, file_name in enumerate(file_list):
                                    if i % 50 == 0:
                                        check_cancelled()
                                    # 去掉公共前缀
                                    if file_name.startswith(common_prefix):
                                        target_path = file_name[len(common_prefix):]
                                        if target_path:  # 跳过空路径（根目录本身）
                                            full_target = os.path.join(base_path, target_path)
                                            if file_name.endswith('/'):
                                                os.makedirs(full_target, exist_ok=True)
                                            else:
                                                os.makedirs(os.path.dirname(full_target), exist_ok=True)
                                                with zip_ref.open(file_name) as src, open(full_target, 'wb') as dst:
                                                    dst.write(src.read())

                        # 清理临时文件
                        os.remove(zip_temp_path)
                        logger.info(f"✅ ZIP 下载成功 (分支: {branch})")
                        await emit(f"✅ 仓库获取成功 (ZIP下载, 分支: {branch})")
                        download_success = True
                        break
                    else:
                        last_error = error or "下载失败"
                        logger.warning(f"ZIP 下载失败 (分支 {branch}): {last_error}")
                        await emit(f"⚠️ ZIP 下载失败，尝试其他分支...", "warning")
                        # 清理临时文件
                        if os.path.exists(zip_temp_path):
                            os.remove(zip_temp_path)

                except asyncio.CancelledError:
                    logger.info(f"[Cancel] ZIP download cancelled for task {task_id}")
                    raise
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"ZIP 下载异常 (分支 {branch}): {e}")
                    await emit(f"⚠️ ZIP 下载异常: {str(e)[:50]}...", "warning")

        # ============ 方案2: 回退到 git clone ============
        if not download_success:
            if is_ssh_url:
                # SSH链接直接使用git clone，不是"失败"
                pass  # 已在上面输出提示
            else:
                await emit(f"🔄 ZIP 下载失败，回退到 Git 克隆...")
                logger.info("ZIP download failed, falling back to git clone")

            # 检查 git 是否可用
            try:
                git_check = subprocess.run(
                    ["git", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if git_check.returncode != 0:
                    await emit(f"❌ Git 未安装", "error")
                    raise RuntimeError("Git 未安装，无法克隆仓库。")
            except FileNotFoundError:
                await emit(f"❌ Git 未安装", "error")
                raise RuntimeError("Git 未安装，无法克隆仓库。")
            except subprocess.TimeoutExpired:
                await emit(f"❌ Git 检测超时", "error")
                raise RuntimeError("Git 检测超时")

            # 构建带认证的 URL
            auth_url = repo_url
            if repo_type == "github" and github_token:
                auth_url = urlunparse((
                    parsed.scheme,
                    f"{github_token}@{parsed.netloc}",
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment
                ))
                await emit(f"🔐 使用 GitHub Token 认证")
            elif repo_type == "gitlab" and gitlab_token:
                auth_url = urlunparse((
                    parsed.scheme,
                    f"oauth2:{gitlab_token}@{parsed.netloc}",
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment
                ))
                await emit(f"🔐 使用 GitLab Token 认证")
            elif repo_type == "gitea" and gitea_token:
                auth_url = urlunparse((
                    parsed.scheme,
                    f"{gitea_token}@{parsed.netloc}",
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment
                ))
                await emit(f"🔐 使用 Gitea Token 认证")
            elif is_ssh_url and ssh_private_key:
                await emit(f"🔐 使用 SSH Key 认证")

            clone_url_candidates = [auth_url] if is_ssh_url else get_mirror_candidates(
                auth_url,
                enabled=getattr(settings, "GIT_MIRROR_ENABLED", True),
                mirror_prefix=getattr(settings, "GIT_MIRROR_PREFIX", "https://gh-proxy.org"),
                mirror_prefixes=getattr(
                    settings, "GIT_MIRROR_PREFIXES", "https://gh-proxy.org,https://v6.gh-proxy.org"
                ),
                allow_hosts=getattr(settings, "GIT_MIRROR_HOSTS", "github.com"),
                allow_auth_url=getattr(settings, "GIT_MIRROR_ALLOW_AUTH_URL", False),
                fallback_to_origin=getattr(settings, "GIT_MIRROR_FALLBACK_TO_ORIGIN", False),
            )
            clone_has_origin_url = auth_url in clone_url_candidates

            for branch in branches_to_try:
                check_cancelled()

                if os.path.exists(base_path) and os.listdir(base_path):
                    shutil.rmtree(base_path)
                    os.makedirs(base_path, exist_ok=True)

                logger.info(f"🔄 尝试克隆分支: {branch}")
                await emit(f"🔄 尝试克隆分支: {branch}")

                try:
                    # SSH URL使用GitSSHOperations（支持SSH密钥认证）
                    if is_ssh_url and ssh_private_key:
                        async def run_ssh_clone():
                            return await asyncio.to_thread(
                                GitSSHOperations.clone_repo_with_ssh,
                                repo_url, ssh_private_key, base_path, branch
                            )

                        clone_task = asyncio.create_task(run_ssh_clone())
                        while not clone_task.done():
                            check_cancelled()
                            try:
                                result = await asyncio.wait_for(asyncio.shield(clone_task), timeout=1.0)
                                break
                            except asyncio.TimeoutError:
                                continue

                        if clone_task.done():
                            result = clone_task.result()

                        # GitSSHOperations返回字典格式
                        if result.get('success'):
                            logger.info(f"✅ Git 克隆成功 (SSH, 分支: {branch})")
                            await emit(f"✅ 仓库获取成功 (SSH克隆, 分支: {branch})")
                            download_success = True
                            break
                        else:
                            last_error = result.get('message', '未知错误')
                            logger.warning(f"SSH克隆失败 (分支 {branch}): {last_error[:200]}")
                            await emit(f"⚠️ 分支 {branch} SSH克隆失败...", "warning")
                    else:
                        result = None
                        for idx, candidate_clone_url in enumerate(clone_url_candidates):
                            using_mirror = candidate_clone_url != auth_url

                            async def run_clone():
                                return await asyncio.to_thread(
                                    subprocess.run,
                                    ["git", "clone", "--depth", "1", "--branch", branch, candidate_clone_url, base_path],
                                    capture_output=True,
                                    text=True,
                                    timeout=120,
                                )

                            clone_task = asyncio.create_task(run_clone())
                            while not clone_task.done():
                                check_cancelled()
                                try:
                                    result = await asyncio.wait_for(asyncio.shield(clone_task), timeout=1.0)
                                    break
                                except asyncio.TimeoutError:
                                    continue

                            if clone_task.done():
                                result = clone_task.result()

                            if result.returncode == 0:
                                break

                            last_error = result.stderr
                            if using_mirror:
                                if idx < len(clone_url_candidates) - 1:
                                    next_candidate = clone_url_candidates[idx + 1]
                                    if next_candidate == auth_url:
                                        logger.warning(
                                            "Git 镜像 clone 失败 (分支 %s): %s，回源重试: %s",
                                            branch,
                                            (last_error or "")[:200],
                                            next_candidate,
                                        )
                                    else:
                                        logger.warning(
                                            "Git 镜像 clone 失败 (分支 %s): %s，切换候选重试: %s",
                                            branch,
                                            (last_error or "")[:200],
                                            next_candidate,
                                        )
                                elif not clone_has_origin_url:
                                    logger.warning("Git 镜像全部失败，已按策略终止当前候选（未启用回源）")

                        if result is not None and result.returncode == 0:
                            logger.info(f"✅ Git 克隆成功 (分支: {branch})")
                            await emit(f"✅ 仓库获取成功 (Git克隆, 分支: {branch})")
                            download_success = True
                            break

                        logger.warning(f"克隆失败 (分支 {branch}): {str(last_error or '')[:200]}")
                        await emit(f"⚠️ 分支 {branch} 克隆失败...", "warning")
                except subprocess.TimeoutExpired:
                    last_error = f"克隆分支 {branch} 超时"
                    logger.warning(last_error)
                    await emit(f"⚠️ 分支 {branch} 克隆超时...", "warning")
                except asyncio.CancelledError:
                    logger.info(f"[Cancel] Git clone cancelled for task {task_id}")
                    raise

            # 尝试默认分支
            if not download_success:
                check_cancelled()
                await emit(f"🔄 尝试使用仓库默认分支...")

                if os.path.exists(base_path) and os.listdir(base_path):
                    shutil.rmtree(base_path)
                    os.makedirs(base_path, exist_ok=True)

                try:
                    # SSH URL使用GitSSHOperations（不指定分支）
                    if is_ssh_url and ssh_private_key:
                        async def run_default_ssh_clone():
                            return await asyncio.to_thread(
                                GitSSHOperations.clone_repo_with_ssh,
                                repo_url, ssh_private_key, base_path, branch
                            )

                        clone_task = asyncio.create_task(run_default_ssh_clone())
                        while not clone_task.done():
                            check_cancelled()
                            try:
                                result = await asyncio.wait_for(asyncio.shield(clone_task), timeout=1.0)
                                break
                            except asyncio.TimeoutError:
                                continue

                        if clone_task.done():
                            result = clone_task.result()

                        if result.get('success'):
                            logger.info(f"✅ Git 克隆成功 (SSH, 默认分支)")
                            await emit(f"✅ 仓库获取成功 (SSH克隆, 默认分支)")
                            download_success = True
                        else:
                            last_error = result.get('message', '未知错误')
                    else:
                        result = None
                        for idx, candidate_clone_url in enumerate(clone_url_candidates):
                            using_mirror = candidate_clone_url != auth_url

                            async def run_default_clone():
                                return await asyncio.to_thread(
                                    subprocess.run,
                                    ["git", "clone", "--depth", "1", candidate_clone_url, base_path],
                                    capture_output=True,
                                    text=True,
                                    timeout=120,
                                )

                            clone_task = asyncio.create_task(run_default_clone())
                            while not clone_task.done():
                                check_cancelled()
                                try:
                                    result = await asyncio.wait_for(asyncio.shield(clone_task), timeout=1.0)
                                    break
                                except asyncio.TimeoutError:
                                    continue

                            if clone_task.done():
                                result = clone_task.result()

                            if result.returncode == 0:
                                break

                            last_error = result.stderr
                            if using_mirror:
                                if idx < len(clone_url_candidates) - 1:
                                    next_candidate = clone_url_candidates[idx + 1]
                                    if next_candidate == auth_url:
                                        logger.warning(
                                            "Git 镜像默认分支 clone 失败: %s，回源重试: %s",
                                            (last_error or "")[:200],
                                            next_candidate,
                                        )
                                    else:
                                        logger.warning(
                                            "Git 镜像默认分支 clone 失败: %s，切换候选重试: %s",
                                            (last_error or "")[:200],
                                            next_candidate,
                                        )
                                elif not clone_has_origin_url:
                                    logger.warning("Git 镜像全部失败，已按策略终止当前候选（未启用回源）")

                        if result is not None and result.returncode == 0:
                            logger.info(f"✅ Git 克隆成功 (默认分支)")
                            await emit(f"✅ 仓库获取成功 (Git克隆, 默认分支)")
                            download_success = True
                        else:
                            last_error = str(last_error or "")
                except subprocess.TimeoutExpired:
                    last_error = "克隆超时"
                except asyncio.CancelledError:
                    logger.info(f"[Cancel] Git clone cancelled for task {task_id}")
                    raise

        if not download_success:
            # 分析错误原因
            error_msg = "克隆仓库失败"
            if "Authentication failed" in last_error or "401" in last_error:
                error_msg = "认证失败，请检查 GitHub/GitLab Token 配置"
            elif "not found" in last_error.lower() or "404" in last_error:
                error_msg = "仓库不存在或无访问权限"
            elif "Could not resolve host" in last_error:
                error_msg = "无法解析主机名，请检查网络连接"
            elif "Permission denied" in last_error or "403" in last_error:
                error_msg = "无访问权限，请检查仓库权限或 Token"
            else:
                error_msg = f"克隆仓库失败: {last_error[:200]}"

            logger.error(f"❌ {error_msg}")
            await emit(f"❌ {error_msg}", "error")
            raise RuntimeError(error_msg)

    # 验证目录不为空
    if not os.listdir(base_path):
        await emit(f"❌ 项目目录为空", "error")
        raise RuntimeError(f"项目目录为空，可能是克隆/解压失败: {base_path}")

    # 🔥 智能检测：如果解压后只有一个子目录（常见于 ZIP 文件），
    # 则使用那个子目录作为真正的项目根目录
    # 例如：/tmp/deepaudit/UUID/PHP-Project/ -> 返回 /tmp/deepaudit/UUID/PHP-Project
    items = os.listdir(base_path)
    # 过滤掉 macOS 产生的 __MACOSX 目录和隐藏文件
    real_items = [item for item in items if not item.startswith('__') and not item.startswith('.')]
    
    if len(real_items) == 1:
        single_item_path = os.path.join(base_path, real_items[0])
        if os.path.isdir(single_item_path):
            logger.info(f"🔍 检测到单层嵌套目录，自动调整项目根目录: {base_path} -> {single_item_path}")
            await emit(f"🔍 检测到嵌套目录，自动调整为: {real_items[0]}")
            base_path = single_item_path

    await emit(f"📁 项目准备完成: {base_path}")
    return base_path


# ============ Agent Tree API ============

class AgentTreeNodeResponse(BaseModel):
    """Agent 树节点响应"""
    id: str
    agent_id: str
    agent_name: str
    agent_type: str
    parent_agent_id: Optional[str] = None
    depth: int = 0
    task_description: Optional[str] = None
    knowledge_modules: Optional[List[str]] = None
    status: str = "created"
    result_summary: Optional[str] = None
    findings_count: int = 0
    iterations: int = 0
    tokens_used: int = 0
    tool_calls: int = 0
    duration_ms: Optional[int] = None
    children: List["AgentTreeNodeResponse"] = []
    
    model_config = ConfigDict(from_attributes=True)


class AgentTreeResponse(BaseModel):
    """Agent 树响应"""
    task_id: str
    root_agent_id: Optional[str] = None
    total_agents: int = 0
    running_agents: int = 0
    completed_agents: int = 0
    failed_agents: int = 0
    total_findings: int = 0
    nodes: List[AgentTreeNodeResponse] = []


@router.get("/{task_id}/agent-tree", response_model=AgentTreeResponse)
async def get_agent_tree(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取任务的 Agent 树结构
    
    返回动态 Agent 树的完整结构，包括：
    - 所有 Agent 节点
    - 父子关系
    - 执行状态
    - 发现统计
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 尝试从内存中获取 Agent 树（运行中的任务）
    runner = _running_tasks.get(task_id)
    logger.debug(f"[AgentTree API] task_id={task_id}, runner exists={runner is not None}")
    
    if runner:
        from app.services.agent.core import agent_registry
        
        tree = agent_registry.get_agent_tree()
        stats = agent_registry.get_statistics()
        logger.debug(f"[AgentTree API] tree nodes={len(tree.get('nodes', {}))}, root={tree.get('root_agent_id')}")
        logger.debug(f"[AgentTree API] 节点详情: {list(tree.get('nodes', {}).keys())}")
        
        # 🔥 获取 root agent ID，用于判断是否是 Orchestrator
        root_agent_id = tree.get("root_agent_id")
        
        # 构建节点列表
        nodes = []
        for agent_id, node_data in tree.get("nodes", {}).items():
            # 🔥 从 Agent 实例获取实时统计数据
            iterations = 0
            tool_calls = 0
            tokens_used = 0
            findings_count = 0
            
            agent_instance = agent_registry.get_agent(agent_id)
            if agent_instance and hasattr(agent_instance, 'get_stats'):
                agent_stats = agent_instance.get_stats()
                iterations = agent_stats.get("iterations", 0)
                tool_calls = agent_stats.get("tool_calls", 0)
                tokens_used = agent_stats.get("tokens_used", 0)
            
            # 🔥 FIX: 对于 Orchestrator (root agent)，使用 task 的 findings_count
            # 这确保了正确显示聚合的 findings 总数
            if agent_id == root_agent_id:
                findings_count = task.findings_count or 0
            else:
                # 从结果中获取发现数量（对于子 agent）
                if node_data.get("result"):
                    result = node_data.get("result", {})
                    findings_count = len(result.get("findings", []))
            
            nodes.append(AgentTreeNodeResponse(
                id=node_data.get("id", agent_id),
                agent_id=agent_id,
                agent_name=node_data.get("name", "Unknown"),
                agent_type=node_data.get("type", "unknown"),
                parent_agent_id=node_data.get("parent_id"),
                task_description=node_data.get("task"),
                knowledge_modules=node_data.get("knowledge_modules", []),
                status=node_data.get("status", "unknown"),
                findings_count=findings_count,
                iterations=iterations,
                tool_calls=tool_calls,
                tokens_used=tokens_used,
                children=[],
            ))
        
        # 🔥 使用 task.findings_count 作为 total_findings，确保一致性
        return AgentTreeResponse(
            task_id=task_id,
            root_agent_id=root_agent_id,
            total_agents=stats.get("total", 0),
            running_agents=stats.get("running", 0),
            completed_agents=stats.get("completed", 0),
            failed_agents=stats.get("failed", 0),
            total_findings=task.findings_count or 0,
            nodes=nodes,
        )
    
    # 从数据库获取（已完成的任务）
    from app.models.agent_task import AgentTreeNode
    
    result = await db.execute(
        select(AgentTreeNode)
        .where(AgentTreeNode.task_id == task_id)
        .order_by(AgentTreeNode.depth, AgentTreeNode.created_at)
    )
    db_nodes = result.scalars().all()
    
    if not db_nodes:
        return AgentTreeResponse(
            task_id=task_id,
            nodes=[],
        )
    
    # 构建响应
    nodes = []
    root_id = None
    running = 0
    completed = 0
    failed = 0
    
    for node in db_nodes:
        if node.parent_agent_id is None:
            root_id = node.agent_id
        
        if node.status == "running":
            running += 1
        elif node.status == "completed":
            completed += 1
        elif node.status == "failed":
            failed += 1
        
        # 🔥 FIX: 对于 Orchestrator (root agent)，使用 task 的 findings_count
        # 这确保了正确显示聚合的 findings 总数
        if node.parent_agent_id is None:
            # Root agent uses task's total findings
            node_findings_count = task.findings_count or 0
        else:
            node_findings_count = node.findings_count or 0
        
        nodes.append(AgentTreeNodeResponse(
            id=node.id,
            agent_id=node.agent_id,
            agent_name=node.agent_name,
            agent_type=node.agent_type,
            parent_agent_id=node.parent_agent_id,
            depth=node.depth,
            task_description=node.task_description,
            knowledge_modules=node.knowledge_modules,
            status=node.status,
            result_summary=node.result_summary,
            findings_count=node_findings_count,
            iterations=node.iterations or 0,
            tokens_used=node.tokens_used or 0,
            tool_calls=node.tool_calls or 0,
            duration_ms=node.duration_ms,
            children=[],
        ))
    
    # 🔥 使用 task.findings_count 作为 total_findings，确保一致性
    return AgentTreeResponse(
        task_id=task_id,
        root_agent_id=root_id,
        total_agents=len(nodes),
        running_agents=running,
        completed_agents=completed,
        failed_agents=failed,
        total_findings=task.findings_count or 0,
        nodes=nodes,
    )


# ============ Checkpoint API ============

class CheckpointResponse(BaseModel):
    """检查点响应"""
    id: str
    agent_id: str
    agent_name: str
    agent_type: str
    iteration: int
    status: str
    total_tokens: int = 0
    tool_calls: int = 0
    findings_count: int = 0
    checkpoint_type: str = "auto"
    checkpoint_name: Optional[str] = None
    created_at: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


@router.get("/{task_id}/checkpoints", response_model=List[CheckpointResponse])
async def list_checkpoints(
    task_id: str,
    agent_id: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取任务的检查点列表
    
    用于：
    - 查看执行历史
    - 状态恢复
    - 调试分析
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    from app.models.agent_task import AgentCheckpoint
    
    query = select(AgentCheckpoint).where(AgentCheckpoint.task_id == task_id)
    
    if agent_id:
        query = query.where(AgentCheckpoint.agent_id == agent_id)
    
    query = query.order_by(AgentCheckpoint.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    checkpoints = result.scalars().all()
    
    return [
        CheckpointResponse(
            id=cp.id,
            agent_id=cp.agent_id,
            agent_name=cp.agent_name,
            agent_type=cp.agent_type,
            iteration=cp.iteration,
            status=cp.status,
            total_tokens=cp.total_tokens or 0,
            tool_calls=cp.tool_calls or 0,
            findings_count=cp.findings_count or 0,
            checkpoint_type=cp.checkpoint_type or "auto",
            checkpoint_name=cp.checkpoint_name,
            created_at=cp.created_at.isoformat() if cp.created_at else None,
        )
        for cp in checkpoints
    ]


@router.get("/{task_id}/checkpoints/{checkpoint_id}")
async def get_checkpoint_detail(
    task_id: str,
    checkpoint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取检查点详情
    
    返回完整的 Agent 状态数据
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    from app.models.agent_task import AgentCheckpoint
    
    checkpoint = await db.get(AgentCheckpoint, checkpoint_id)
    if not checkpoint or checkpoint.task_id != task_id:
        raise HTTPException(status_code=404, detail="检查点不存在")
    
    # 解析状态数据
    state_data = {}
    if checkpoint.state_data:
        try:
            state_data = json.loads(checkpoint.state_data)
        except json.JSONDecodeError:
            pass
    
    return {
        "id": checkpoint.id,
        "task_id": checkpoint.task_id,
        "agent_id": checkpoint.agent_id,
        "agent_name": checkpoint.agent_name,
        "agent_type": checkpoint.agent_type,
        "parent_agent_id": checkpoint.parent_agent_id,
        "iteration": checkpoint.iteration,
        "status": checkpoint.status,
        "total_tokens": checkpoint.total_tokens,
        "tool_calls": checkpoint.tool_calls,
        "findings_count": checkpoint.findings_count,
        "checkpoint_type": checkpoint.checkpoint_type,
        "checkpoint_name": checkpoint.checkpoint_name,
        "state_data": state_data,
        "metadata": checkpoint.checkpoint_metadata,
        "created_at": checkpoint.created_at.isoformat() if checkpoint.created_at else None,
    }


# ============ Report Generation API ============


def _escape_markdown_inline(text: Optional[str]) -> str:
    """转义 Markdown 行内特殊字符，避免标题/位置等结构被破坏。"""
    if text is None:
        return ""
    escaped = str(text).replace("\\", "\\\\")
    for char in ("`", "*", "_", "[", "]", "(", ")", "#", "+", "-", "!", "|", ">"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def _escape_markdown_table_cell(text: Optional[str]) -> str:
    return _escape_markdown_inline(text).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")


@router.get("/{task_id}/report")
async def generate_audit_report(
    task_id: str,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    生成审计报告
    
    支持 Markdown 和 JSON 格式
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 获取此任务的所有发现
    findings = await db.execute(
        select(AgentFinding)
        .where(AgentFinding.task_id == task_id)
        .order_by(
            case(
                (AgentFinding.severity == 'critical', 1),
                (AgentFinding.severity == 'high', 2),
                (AgentFinding.severity == 'medium', 3),
                (AgentFinding.severity == 'low', 4),
                else_=5
            ),
            AgentFinding.created_at.desc()
        )
    )
    findings = findings.scalars().all()
    
    # 🔥 Helper function to normalize severity for comparison (case-insensitive)
    def normalize_severity(sev: str) -> str:
        return str(sev).lower().strip() if sev else ""
    
    # Log findings for debugging
    logger.info(f"[Report] Task {task_id}: Found {len(findings)} findings from database")
    if findings:
        for i, f in enumerate(findings[:3]):  # Log first 3
            logger.debug(f"[Report] Finding {i+1}: severity='{f.severity}', title='{f.title[:50] if f.title else 'N/A'}'")

    def _build_report_descriptions(
        finding_row: AgentFinding,
    ) -> Tuple[Optional[str], Optional[str]]:
        verification_payload = (
            finding_row.verification_result
            if isinstance(finding_row.verification_result, dict)
            else {}
        )
        verification_evidence = (
            verification_payload.get("evidence")
            or verification_payload.get("verification_evidence")
            or verification_payload.get("verification_details")
            or verification_payload.get("details")
        )
        flow_payload = verification_payload.get("flow") if isinstance(verification_payload, dict) else None
        function_trigger_flow: Optional[List[str]] = None
        if isinstance(flow_payload, dict):
            raw_flow = flow_payload.get("function_trigger_flow")
            if isinstance(raw_flow, list):
                function_trigger_flow = [
                    str(step).strip()
                    for step in raw_flow
                    if isinstance(step, str) and str(step).strip()
                ]
            if not function_trigger_flow:
                raw_chain = flow_payload.get("call_chain")
                if isinstance(raw_chain, list):
                    function_trigger_flow = [
                        str(step).strip()
                        for step in raw_chain
                        if isinstance(step, str) and str(step).strip()
                    ]
        if not function_trigger_flow:
            raw_flow = verification_payload.get("function_trigger_flow")
            if isinstance(raw_flow, list):
                function_trigger_flow = [
                    str(step).strip()
                    for step in raw_flow
                    if isinstance(step, str) and str(step).strip()
                ]

        normalized_file_path = _normalize_relative_file_path(
            str(finding_row.file_path or ""),
            None,
        )
        cwe_id = _extract_cwe_from_references(getattr(finding_row, "references", None))
        if not cwe_id:
            cwe_id = _resolve_cwe_id(
                verification_payload.get("cwe_id") or verification_payload.get("cwe"),
                finding_row.vulnerability_type,
                title=finding_row.title,
                description=finding_row.description,
                code_snippet=finding_row.code_snippet,
            )
        profile = _resolve_vulnerability_profile(
            finding_row.vulnerability_type,
            title=finding_row.title,
            description=finding_row.description,
            code_snippet=finding_row.code_snippet,
        )
        function_name = (
            str(verification_payload.get("function") or "").strip()
            or str(getattr(finding_row, "function_name", "") or "").strip()
            or None
        )
        structured_text = _build_structured_cn_description(
            file_path=normalized_file_path,
            function_name=function_name,
            vulnerability_type=profile["key"],
            title=finding_row.title,
            description=finding_row.description,
            code_snippet=finding_row.code_snippet,
            code_context=finding_row.code_context,
            cwe_id=cwe_id,
            raw_description=finding_row.description,
            line_start=finding_row.line_start,
            line_end=finding_row.line_end,
            verification_evidence=verification_evidence,
            function_trigger_flow=function_trigger_flow,
        )
        structured_markdown = _build_structured_cn_description_markdown(
            file_path=normalized_file_path,
            function_name=function_name,
            vulnerability_type=profile["key"],
            title=finding_row.title,
            description=finding_row.description,
            code_snippet=finding_row.code_snippet,
            code_context=finding_row.code_context,
            cwe_id=cwe_id,
            raw_description=finding_row.description,
            line_start=finding_row.line_start,
            line_end=finding_row.line_end,
            verification_evidence=verification_evidence,
            function_trigger_flow=function_trigger_flow,
        )
        return structured_text, structured_markdown

    report_descriptions: Dict[str, Dict[str, Optional[str]]] = {}
    for finding_row in findings:
        structured_text, structured_markdown = _build_report_descriptions(finding_row)
        report_descriptions[str(finding_row.id)] = {
            "description": structured_text,
            "description_markdown": structured_markdown,
        }
    
    if format == "json":
        # Enhanced JSON report with full metadata
        return {
            "report_metadata": {
                "task_id": task.id,
                "project_id": task.project_id,
                "project_name": project.name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "task_status": task.status,
                "duration_seconds": int((task.completed_at - task.started_at).total_seconds()) if task.completed_at and task.started_at else None,
            },
            "summary": {
                "security_score": task.security_score,
                "total_files_analyzed": task.analyzed_files,
                "total_findings": len(findings),
                "verified_findings": sum(1 for f in findings if f.is_verified),
                "severity_distribution": {
                    "critical": sum(1 for f in findings if normalize_severity(f.severity) == 'critical'),
                    "high": sum(1 for f in findings if normalize_severity(f.severity) == 'high'),
                    "medium": sum(1 for f in findings if normalize_severity(f.severity) == 'medium'),
                    "low": sum(1 for f in findings if normalize_severity(f.severity) == 'low'),
                },
                "agent_metrics": {
                    "total_iterations": task.total_iterations,
                    "tool_calls": task.tool_calls_count,
                    "tokens_used": task.tokens_used,
                }
            },
            "findings": [
                {
                    "id": f.id,
                    "title": f.title,
                    "severity": f.severity,
                    "vulnerability_type": f.vulnerability_type,
                    "description": f.description,
                    "description_markdown": report_descriptions.get(str(f.id), {}).get("description_markdown"),
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "code_snippet": f.code_snippet,
                    "is_verified": f.is_verified,
                    "has_poc": f.has_poc,
                    "poc_code": f.poc_code,
                    "poc_description": f.poc_description,
                    "poc_steps": f.poc_steps,
                    "confidence": f.ai_confidence,
                    "suggestion": f.suggestion,
                    "fix_code": f.fix_code,
                    "verification_result": (
                        getattr(f, "verification_result", None)
                        if isinstance(getattr(f, "verification_result", None), dict)
                        else None
                    ),
                    "flow": (
                        getattr(f, "verification_result", {}).get("flow")
                        if isinstance(getattr(f, "verification_result", None), dict)
                        else None
                    ),
                    "logic_authz": (
                        getattr(f, "verification_result", {}).get("logic_authz")
                        if isinstance(getattr(f, "verification_result", None), dict)
                        else None
                    ),
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                } for f in findings
            ]
        }

    # Generate Enhanced Markdown Report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Calculate statistics
    total = len(findings)
    critical = sum(1 for f in findings if normalize_severity(f.severity) == 'critical')
    high = sum(1 for f in findings if normalize_severity(f.severity) == 'high')
    medium = sum(1 for f in findings if normalize_severity(f.severity) == 'medium')
    low = sum(1 for f in findings if normalize_severity(f.severity) == 'low')
    verified = sum(1 for f in findings if f.is_verified)
    with_poc = sum(1 for f in findings if f.has_poc)

    # Calculate duration
    duration_str = "N/A"
    if task.completed_at and task.started_at:
        duration = (task.completed_at - task.started_at).total_seconds()
        if duration >= 3600:
            duration_str = f"{duration / 3600:.1f} 小时"
        elif duration >= 60:
            duration_str = f"{duration / 60:.1f} 分钟"
        else:
            duration_str = f"{int(duration)} 秒"

    md_lines = []

    # Header
    md_lines.append("# 安全审计报告")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # Report Info
    md_lines.append("## 报告信息")
    md_lines.append("")
    md_lines.append(f"| 属性 | 内容 |")
    md_lines.append(f"|----------|-------|")
    md_lines.append(f"| **项目名称** | {_escape_markdown_table_cell(project.name)} |")
    md_lines.append(f"| **任务 ID** | `{task.id[:8]}...` |")
    md_lines.append(f"| **生成时间** | {timestamp} |")
    md_lines.append(f"| **任务状态** | {_escape_markdown_table_cell(str(task.status).upper())} |")
    md_lines.append(f"| **耗时** | {duration_str} |")
    md_lines.append("")

    # Executive Summary
    md_lines.append("## 执行摘要")
    md_lines.append("")

    score = task.security_score
    if score is not None:
        if score >= 80:
            score_assessment = "良好 - 建议进行少量优化"
            score_icon = "通过"
        elif score >= 60:
            score_assessment = "中等 - 存在若干问题需要关注"
            score_icon = "警告"
        else:
            score_assessment = "严重 - 需要立即进行修复"
            score_icon = "未通过"
        md_lines.append(f"**安全评分: {int(score)}/100** [{score_icon}]")
        md_lines.append(f"*{score_assessment}*")
    else:
        md_lines.append("**安全评分:** 未计算")
    md_lines.append("")

    # Findings Summary
    md_lines.append("### 漏洞发现概览")
    md_lines.append("")
    md_lines.append(f"| 严重程度 | 数量 | 已验证 |")
    md_lines.append(f"|----------|-------|----------|")
    if critical > 0:
        md_lines.append(f"| **严重 (CRITICAL)** | {critical} | {sum(1 for f in findings if normalize_severity(f.severity) == 'critical' and f.is_verified)} |")
    if high > 0:
        md_lines.append(f"| **高危 (HIGH)** | {high} | {sum(1 for f in findings if normalize_severity(f.severity) == 'high' and f.is_verified)} |")
    if medium > 0:
        md_lines.append(f"| **中危 (MEDIUM)** | {medium} | {sum(1 for f in findings if normalize_severity(f.severity) == 'medium' and f.is_verified)} |")
    if low > 0:
        md_lines.append(f"| **低危 (LOW)** | {low} | {sum(1 for f in findings if normalize_severity(f.severity) == 'low' and f.is_verified)} |")
    md_lines.append(f"| **总计** | {total} | {verified} |")
    md_lines.append("")

    # Audit Metrics
    md_lines.append("### 审计指标")
    md_lines.append("")
    md_lines.append(f"- **分析文件数:** {task.analyzed_files} / {task.total_files}")
    md_lines.append(f"- **Agent 迭代次数:** {task.total_iterations}")
    md_lines.append(f"- **工具调用次数:** {task.tool_calls_count}")
    md_lines.append(f"- **Token 消耗:** {task.tokens_used:,}")
    if with_poc > 0:
        md_lines.append(f"- **生成的 PoC:** {with_poc}")
    md_lines.append("")

    # Detailed Findings
    if not findings:
        md_lines.append("## 漏洞详情")
        md_lines.append("")
        md_lines.append("*本次审计未发现安全漏洞。*")
        md_lines.append("")
    else:
        # Group findings by severity
        severity_map = {
            'critical': '严重 (Critical)',
            'high': '高危 (High)',
            'medium': '中危 (Medium)',
            'low': '低危 (Low)'
        }
        
        for severity_level, severity_name in severity_map.items():
            severity_findings = [f for f in findings if normalize_severity(f.severity) == severity_level]
            if not severity_findings:
                continue

            md_lines.append(f"## {severity_name} 漏洞")
            md_lines.append("")

            for i, f in enumerate(severity_findings, 1):
                verified_badge = "[已验证]" if f.is_verified else "[未验证]"
                poc_badge = " [含 PoC]" if f.has_poc else ""

                md_lines.append(
                    f"### {severity_level.upper()}-{i}: {_escape_markdown_inline(f.title)}"
                )
                md_lines.append("")
                md_lines.append(
                    f"**{verified_badge}**{poc_badge} | 类型: `{_escape_markdown_inline(f.vulnerability_type)}`"
                )
                md_lines.append("")

                if f.file_path:
                    location = _escape_markdown_inline(f.file_path)
                    if f.line_start:
                        location += f":{f.line_start}"
                        if f.line_end and f.line_end != f.line_start:
                            location += f"-{f.line_end}"
                    md_lines.append(f"**位置:** {location}")
                    md_lines.append("")

                if f.ai_confidence:
                    md_lines.append(f"**AI 置信度:** {int(f.ai_confidence * 100)}%")
                    md_lines.append("")

                verification_result = getattr(f, "verification_result", None)
                if isinstance(verification_result, dict):
                    flow_payload = verification_result.get("flow")
                    if isinstance(flow_payload, dict):
                        flow_score = flow_payload.get("path_score")
                        chain = flow_payload.get("call_chain")
                        if flow_score is not None:
                            try:
                                md_lines.append(f"**可达性评分:** {float(flow_score) * 100:.1f}%")
                            except Exception:
                                md_lines.append(f"**可达性评分:** {flow_score}")
                            md_lines.append("")
                        if isinstance(chain, list) and chain:
                            md_lines.append("**可达性调用链:**")
                            md_lines.append("")
                            for call_item in chain[:12]:
                                md_lines.append(f"- `{_escape_markdown_inline(str(call_item))}`")
                            md_lines.append("")

                    logic_payload = verification_result.get("logic_authz")
                    if isinstance(logic_payload, dict):
                        evidence = logic_payload.get("evidence")
                        if isinstance(evidence, list) and evidence:
                            md_lines.append("**逻辑漏洞证据:**")
                            md_lines.append("")
                            for evidence_item in evidence[:10]:
                                md_lines.append(f"- {_escape_markdown_inline(str(evidence_item))}")
                            md_lines.append("")

                finding_markdown = (
                    report_descriptions.get(str(f.id), {}).get("description_markdown")
                    or report_descriptions.get(str(f.id), {}).get("description")
                    or f.description
                )
                if finding_markdown:
                    md_lines.append("**漏洞描述:**")
                    md_lines.append("")
                    md_lines.append(str(finding_markdown))
                    md_lines.append("")

                lang = infer_code_fence_language(f.file_path)
                if f.code_snippet:
                    md_lines.append("**漏洞代码:**")
                    md_lines.append("")
                    md_lines.append(f"```{lang}")
                    md_lines.append(f.code_snippet.strip())
                    md_lines.append("```")
                    md_lines.append("")

                if f.suggestion:
                    md_lines.append("**修复建议:**")
                    md_lines.append("")
                    md_lines.append(f.suggestion)
                    md_lines.append("")

                if f.fix_code:
                    md_lines.append("**参考修复代码:**")
                    md_lines.append("")
                    md_lines.append(f"```{lang if f.file_path else 'text'}")
                    md_lines.append(f.fix_code.strip())
                    md_lines.append("```")
                    md_lines.append("")

                # 🔥 添加 PoC 详情
                if f.has_poc:
                    md_lines.append("**概念验证 (PoC):**")
                    md_lines.append("")

                    if f.poc_description:
                        md_lines.append(f"*{f.poc_description}*")
                        md_lines.append("")

                    if f.poc_steps:
                        md_lines.append("**复现步骤:**")
                        md_lines.append("")
                        for step_idx, step in enumerate(f.poc_steps, 1):
                            md_lines.append(f"{step_idx}. {step}")
                        md_lines.append("")

                    if f.poc_code:
                        md_lines.append("**PoC 代码:**")
                        md_lines.append("")
                        md_lines.append("```")
                        md_lines.append(f.poc_code.strip())
                        md_lines.append("```")
                        md_lines.append("")

                md_lines.append("---")
                md_lines.append("")

    # Remediation Priority
    if critical > 0 or high > 0:
        md_lines.append("## 修复优先级建议")
        md_lines.append("")
        md_lines.append("基于已发现的漏洞，我们建议按以下优先级进行修复：")
        md_lines.append("")
        priority_idx = 1
        if critical > 0:
            md_lines.append(f"{priority_idx}. **立即修复:** 处理 {critical} 个严重漏洞 - 可能造成严重影响")
            priority_idx += 1
        if high > 0:
            md_lines.append(f"{priority_idx}. **高优先级:** 在 1 周内修复 {high} 个高危漏洞")
            priority_idx += 1
        if medium > 0:
            md_lines.append(f"{priority_idx}. **中优先级:** 在 2-4 周内修复 {medium} 个中危漏洞")
            priority_idx += 1
        if low > 0:
            md_lines.append(f"{priority_idx}. **低优先级:** 在日常维护中处理 {low} 个低危漏洞")
            priority_idx += 1
        md_lines.append("")

    # Footer
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("*本报告由自动化安全审计系统生成*")
    md_lines.append("")
    content = "\n".join(md_lines)
    
    filename = f"audit_report_{task.id[:8]}_{datetime.now().strftime('%Y%m%d')}.md"
    
    from fastapi.responses import Response
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


# ==================== 🔥 漏洞队列管理 API ====================

@router.get("/tasks/{task_id}/vulnerability_queue/status", response_model=Dict[str, Any])
async def get_vulnerability_queue_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    获取任务的漏洞队列状态
    
    返回队列中待验证漏洞的数量和统计信息
    """
    from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
    
    # 检查任务是否存在
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = await db.get(Project, task.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # 复用运行中的队列服务，避免新实例导致状态丢失
    queue_service = _running_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryVulnerabilityQueue()
    
    # 获取队列统计
    stats = queue_service.get_queue_stats(task_id)
    
    return {
        "success": True,
        "task_id": task_id,
        "queue_stats": stats,
    }


@router.get("/tasks/{task_id}/vulnerability_queue/peek", response_model=Dict[str, Any])
async def peek_vulnerability_queue(
    task_id: str,
    limit: int = 3,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    查看任务漏洞队列的前N条记录
    
    不会移除队列中的项目，仅用于预览
    """
    from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
    
    # 检查任务是否存在
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = await db.get(Project, task.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # 复用运行中的队列服务，避免新实例导致状态丢失
    queue_service = _running_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryVulnerabilityQueue()
    
    # 查看队列前几项
    findings = queue_service.peek_queue(task_id, limit=min(limit, 10))
    
    return {
        "success": True,
        "task_id": task_id,
        "findings": findings,
        "count": len(findings),
    }


@router.delete("/tasks/{task_id}/vulnerability_queue", response_model=Dict[str, Any])
async def clear_vulnerability_queue(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    清空任务的漏洞队列
    
    用于手动清理或重置队列状态
    """
    from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
    
    # 检查任务是否存在
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = await db.get(Project, task.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # 复用运行中的队列服务，避免新实例导致状态丢失
    queue_service = _running_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryVulnerabilityQueue()
    
    # 清空队列
    success = queue_service.clear_queue(task_id)
    
    return {
        "success": success,
        "task_id": task_id,
        "message": "队列已清空" if success else "清空队列失败",
    }


@router.get("/tasks/{task_id}/recon_risk_queue/status", response_model=Dict[str, Any])
async def get_recon_risk_queue_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue

    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await db.get(Project, task.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    queue_service = _running_recon_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryReconRiskQueue()

    stats = queue_service.stats(task_id)

    return {
        "success": True,
        "task_id": task_id,
        "queue_stats": stats,
    }


@router.get("/tasks/{task_id}/recon_risk_queue/peek", response_model=Dict[str, Any])
async def peek_recon_risk_queue(
    task_id: str,
    limit: int = 3,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue

    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await db.get(Project, task.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    queue_service = _running_recon_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryReconRiskQueue()

    findings = queue_service.peek(task_id, limit=min(limit, 10))

    return {
        "success": True,
        "task_id": task_id,
        "findings": findings,
        "count": len(findings),
    }


@router.delete("/tasks/{task_id}/recon_risk_queue", response_model=Dict[str, Any])
async def clear_recon_risk_queue(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue

    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await db.get(Project, task.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    queue_service = _running_recon_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryReconRiskQueue()

    success = queue_service.clear(task_id)

    return {
        "success": success,
        "task_id": task_id,
        "message": "Recon 队列已清空" if success else "清空 Recon 队列失败",
    }
