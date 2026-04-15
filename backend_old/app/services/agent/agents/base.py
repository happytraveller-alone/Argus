"""
Agent 基类
定义 Agent 的基本接口和通用功能

核心原则：
1. LLM 是 Agent 的大脑，全程参与决策
2. Agent 之间通过 TaskHandoff 传递结构化上下文
3. 事件分为流式事件（前端展示）和持久化事件（数据库记录）
4. 支持动态Agent树和专业知识模块
5. 完整的状态管理和Agent间通信
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple, Set, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from datetime import datetime, timezone
import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
import copy
import ast
import threading
import tempfile
from pathlib import Path

from app.services.agent.json_safe import dump_json_safe, normalize_json_safe

from ..core.state import AgentState, AgentStatus
from ..core.registry import agent_registry
from ..core.message import message_bus, MessageType, AgentMessage
from ..flow.lightweight.function_locator_payload import (
    parse_locator_payload,
    select_locator_function,
)
from ..utils.vulnerability_naming import (
    build_cn_structured_description_markdown,
    normalize_cwe_id,
)
from ..skills.scan_core import SCAN_CORE_LOCAL_SKILL_IDS
from ..push_finding_payload import normalize_push_finding_payload

logger = logging.getLogger(__name__)

_AGENT_TRACE_HANDLER_LOCK = threading.Lock()

MAX_EVENT_PAYLOAD_CHARS = 120000

TOOL_ALIAS_CANDIDATES: Dict[str, List[str]] = {
    "list": ["list_files"],
    "smart_scan": ["smart_scan", "quick_audit", "pattern_match", "search_code", "get_code_window"],
    "quick_audit": ["quick_audit", "smart_scan", "pattern_match", "search_code", "get_code_window"],
    "save_verification_results": ["save_verification_result"],
}
VIRTUAL_TOOL_NAMES: Set[str] = set()

DOWNLINED_TOOL_MESSAGES: Dict[str, str] = {
    "read_file": "工具 `read_file` 已下线。请改用 `get_code_window` 获取代码窗口，`get_file_outline` 获取文件概览，或 `get_function_summary` 获取函数语义总结。",
    "extract_function": "工具 `extract_function` 已下线。请改用 `get_symbol_body` 提取函数/符号主体源码。",
}

TOOL_INPUT_REPAIR_MAP: Dict[str, str] = {
    "query": "keyword",
    "pattern": "keyword",
    "glob": "file_pattern",
    "path": "file_path",
    "function_name": "symbol_name",
    "filepath": "file_path",
    "file": "file_path",
    "dir": "directory",
}

RETRY_GUARD_TOOLS: Set[str] = {
    "get_code_window",
    "search_code",
    "pattern_match",
    "get_recon_risk_queue_status",
    "get_queue_status",
    "dequeue_recon_risk_point",
    "dequeue_finding",
    "get_bl_risk_queue_status",
}
NON_CACHEABLE_TOOL_NAMES: Set[str] = {
    "push_finding_to_queue",
    "get_queue_status",
    "dequeue_finding",
    "push_risk_point_to_queue",
    "push_risk_points_to_queue",
    "get_recon_risk_queue_status",
    "dequeue_recon_risk_point",
    "peek_recon_risk_queue",
    "clear_recon_risk_queue",
    "is_recon_risk_point_in_queue",
    "update_recon_file_tree",
    "is_finding_in_queue",
    "push_bl_risk_point_to_queue",
    "push_bl_risk_points_to_queue",
    "get_bl_risk_queue_status",
    "dequeue_bl_risk_point",
    "peek_bl_risk_queue",
    "clear_bl_risk_queue",
    "is_bl_risk_point_in_queue",
}
STRICT_MODE_LOCAL_ONLY_TOOL_NAMES: Set[str] = {
    "push_risk_point_to_queue",
    "push_risk_points_to_queue",
    "get_recon_risk_queue_status",
    "dequeue_recon_risk_point",
    "peek_recon_risk_queue",
    "clear_recon_risk_queue",
    "is_recon_risk_point_in_queue",
    "update_recon_file_tree",
    "push_finding_to_queue",
    "get_queue_status",
    "dequeue_finding",
    "is_finding_in_queue",
    "save_verification_result",
    "push_bl_risk_point_to_queue",
    "push_bl_risk_points_to_queue",
    "get_bl_risk_queue_status",
    "dequeue_bl_risk_point",
    "peek_bl_risk_queue",
    "clear_bl_risk_queue",
    "is_bl_risk_point_in_queue",
}
WRITE_TOOL_GUARD_NAMES: Set[str] = {"edit_file", "write_file", "move_file", "create_directory"}
DETERMINISTIC_ERROR_HINTS: Tuple[str, ...] = (
    "文件不存在",
    "不是文件",
    "目录不存在",
    "安全错误",
    "无效的搜索模式",
    "必须提供",
    "参数校验失败",
    "工具参数缺失",
)
STRICT_MODE_TRANSIENT_ERROR_HINTS: Tuple[str, ...] = (
    "timeout",
    "timed out",
    "temporarily unavailable",
    "connection reset",
    "connection refused",
    "network",
)
if TYPE_CHECKING:
    from ..tool_runtime.runtime import ToolRuntime
    from ..tool_runtime.write_scope import TaskWriteScopeGuard, WriteScopeDecision


def _truncate_with_flag(text: str, max_chars: int = MAX_EVENT_PAYLOAD_CHARS) -> Tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


class AgentType(Enum):
    """Agent 类型"""
    ORCHESTRATOR = "orchestrator"
    RECON = "recon"
    ANALYSIS = "analysis"
    VERIFICATION = "verification"
    REPORT = "report"


class AgentPattern(Enum):
    """Agent 运行模式"""
    REACT = "react"                    # 反应式：思考-行动-观察循环
    PLAN_AND_EXECUTE = "plan_execute"  # 计划执行：先规划后执行


@dataclass
class AgentConfig:
    """Agent 配置"""
    name: str
    agent_type: AgentType
    pattern: AgentPattern = AgentPattern.REACT
    
    # LLM 配置
    model: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 8192
    
    # 执行限制
    max_iterations: int = 20
    timeout_seconds: int = 600
    
    # 工具配置
    tools: List[str] = field(default_factory=list)
    
    # 系统提示词
    system_prompt: Optional[str] = None
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Agent 执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    
    # 执行统计
    iterations: int = 0
    tool_calls: int = 0
    tokens_used: int = 0
    duration_ms: int = 0
    
    # 中间结果
    intermediate_steps: List[Dict[str, Any]] = field(default_factory=list)
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    #  协作信息 - Agent 传递给下一个 Agent 的结构化信息
    handoff: Optional["TaskHandoff"] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "iterations": self.iterations,
            "tool_calls": self.tool_calls,
            "tokens_used": self.tokens_used,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "handoff": self.handoff.to_dict() if self.handoff else None,
        }


@dataclass
class TaskHandoff:
    """
    任务交接协议 - Agent 之间传递的结构化信息
    
    设计原则：
    1. 包含足够的上下文让下一个 Agent 理解前序工作
    2. 提供明确的建议和关注点
    3. 可直接转换为 LLM 可理解的 prompt
    """
    # 基本信息
    from_agent: str
    to_agent: str
    
    # 工作摘要
    summary: str
    work_completed: List[str] = field(default_factory=list)
    
    # 关键发现和洞察
    key_findings: List[Dict[str, Any]] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    
    # 建议和关注点
    suggested_actions: List[Dict[str, Any]] = field(default_factory=list)
    attention_points: List[str] = field(default_factory=list)
    priority_areas: List[str] = field(default_factory=list)
    
    # 上下文数据
    context_data: Dict[str, Any] = field(default_factory=dict)
    
    # 置信度
    confidence: float = 0.8
    
    # 时间戳
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "summary": self.summary,
            "work_completed": self.work_completed,
            "key_findings": self.key_findings,
            "insights": self.insights,
            "suggested_actions": self.suggested_actions,
            "attention_points": self.attention_points,
            "priority_areas": self.priority_areas,
            "context_data": self.context_data,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskHandoff":
        return cls(
            from_agent=data.get("from_agent", ""),
            to_agent=data.get("to_agent", ""),
            summary=data.get("summary", ""),
            work_completed=data.get("work_completed", []),
            key_findings=data.get("key_findings", []),
            insights=data.get("insights", []),
            suggested_actions=data.get("suggested_actions", []),
            attention_points=data.get("attention_points", []),
            priority_areas=data.get("priority_areas", []),
            context_data=data.get("context_data", {}),
            confidence=data.get("confidence", 0.8),
        )
    
    def to_prompt_context(self) -> str:
        """
        转换为 LLM 可理解的上下文格式
        这是关键！让 LLM 能够理解前序 Agent 的工作
        """
        def _truncate_context_value(value: Any, *, limit: int = 600) -> str:
            try:
                rendered = json.dumps(value, ensure_ascii=False, indent=2)
            except Exception:
                rendered = str(value)
            rendered = rendered.strip()
            if len(rendered) > limit:
                return rendered[: limit - 3] + "..."
            return rendered

        lines = [
            f"## 来自 {self.from_agent} Agent 的任务交接",
            "",
            f"### 工作摘要",
            self.summary,
            "",
        ]
        
        if self.work_completed:
            lines.append("### 已完成的工作")
            for work in self.work_completed:
                lines.append(f"- {work}")
            lines.append("")
        
        if self.key_findings:
            lines.append("### 关键发现")
            for i, finding in enumerate(self.key_findings[:15], 1):
                severity = finding.get("severity", "medium")
                title = finding.get("title", "Unknown")
                file_path = finding.get("file_path", "")
                lines.append(f"{i}. [{severity.upper()}] {title}")
                if file_path:
                    lines.append(f"   位置: {file_path}:{finding.get('line_start', '')}")
                if finding.get("description"):
                    lines.append(f"   描述: {finding['description'][:100]}")
            lines.append("")
        
        if self.insights:
            lines.append("### 洞察和分析")
            for insight in self.insights:
                lines.append(f"- {insight}")
            lines.append("")
        
        if self.suggested_actions:
            lines.append("### 建议的下一步行动")
            for action in self.suggested_actions:
                action_type = action.get("type", "general")
                description = action.get("description", "")
                priority = action.get("priority", "medium")
                lines.append(f"- [{priority.upper()}] {action_type}: {description}")
            lines.append("")
        
        if self.attention_points:
            lines.append("### 需要特别关注")
            for point in self.attention_points:
                lines.append(f"- {point}")
            lines.append("")
        
        if self.priority_areas:
            lines.append("### 优先分析区域")
            for area in self.priority_areas:
                lines.append(f"- {area}")
            lines.append("")

        if self.context_data:
            lines.append("### 结构化上下文")
            for key in sorted(self.context_data.keys()):
                value = self.context_data.get(key)
                if value in (None, "", [], {}, ()):
                    continue
                lines.append(f"- {key}:")
                lines.append(_truncate_context_value(value))

        return "\n".join(lines)


class BaseAgent(ABC):
    """
    Agent 基类
    
    核心原则：
    1. LLM 是 Agent 的大脑，全程参与决策
    2. 所有日志应该反映 LLM 的思考过程
    3. 工具调用是 LLM 的决策结果
    
    协作原则：
    1. 通过 TaskHandoff 接收前序 Agent 的上下文
    2. 执行完成后生成 TaskHandoff 传递给下一个 Agent
    3. 洞察和发现应该结构化记录
    
    动态Agent树：
    1. 支持动态创建子Agent
    2. Agent间通过消息总线通信
    3. 完整的状态管理和生命周期
    """
    
    def __init__(
        self,
        config: AgentConfig,
        llm_service,
        tools: Dict[str, Any],
        event_emitter=None,
        parent_id: Optional[str] = None,
        knowledge_modules: Optional[List[str]] = None,
    ):
        """
        初始化 Agent
        
        Args:
            config: Agent 配置
            llm_service: LLM 服务
            tools: 可用工具字典
            event_emitter: 事件发射器
            parent_id: 父Agent ID（用于动态Agent树）
            knowledge_modules: 要加载的知识模块
        """
        self.config = config
        self.llm_service = llm_service
        self.tools = tools
        self.event_emitter = event_emitter
        self.parent_id = parent_id
        self.knowledge_modules = knowledge_modules or []
        
        #  生成唯一ID
        self._agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        
        #  增强的状态管理
        self._state = AgentState(
            agent_id=self._agent_id,
            agent_name=config.name,
            agent_type=config.agent_type.value,
            parent_id=parent_id,
            max_iterations=config.max_iterations,
            knowledge_modules=self.knowledge_modules,
        )
        
        # 运行状态（保持向后兼容）
        self._iteration = 0
        self._total_tokens = 0
        self._tool_calls = 0
        self._cancelled = False
        self._task_id: Optional[str] = None

        # 获取超时配置
        self._timeout_config = self._get_timeout_config()
        
        #  协作状态
        self._incoming_handoff: Optional[TaskHandoff] = None
        self._insights: List[str] = []  # 收集的洞察
        self._work_completed: List[str] = []  # 完成的工作记录

        #  最近一次工具输出快照（用于避免 llm_observation 复写同一段 tool_result）
        self._last_tool_result_snapshot: Optional[Dict[str, Any]] = None
        self._last_tool_result_payload: Optional[Dict[str, Any]] = None
        self._last_successful_tool_context: Optional[Dict[str, Any]] = None
        self._last_llm_stream_meta: Dict[str, Any] = {}
        self._thinking_push_mode: str = "stream"
        self._last_llm_thought_digest: Optional[str] = None
        self._llm_thought_repeat_count: int = 0
        self._llm_thought_suppressed_count: int = 0
        self._llm_thought_repeat_suppress_threshold: int = 2
        self._llm_thought_repeat_summary_interval: int = 5
        self._tool_repeat_call_counts: Dict[str, int] = {}
        self._deterministic_failure_counts: Dict[str, int] = {}
        self._deterministic_failure_last_error: Dict[str, str] = {}
        self._recent_thought_texts: deque[str] = deque(maxlen=6)
        self._tool_success_cache: Dict[str, str] = {}
        self._recent_reason_dirs: deque[str] = deque(maxlen=16)
        self._recent_search_directories: deque[str] = deque(maxlen=12)
        self._tool_runtime: Optional["ToolRuntime"] = None
        self._write_scope_guard: Optional["TaskWriteScopeGuard"] = None
        self._max_history_observation_chars: int = 12000
        
        #  兜底机制：追踪关键工具调用（push/save）
        self._critical_tool_called: bool = False  # 是否调用了关键工具
        self._critical_tool_name: Optional[str] = None  # 调用的关键工具名称
        self._critical_tool_calls: List[Dict[str, Any]] = []  # 所有关键工具调用记录
        try:
            from app.services.agent.config import get_agent_config

            agent_cfg = get_agent_config()
            configured_value = int(getattr(agent_cfg, "max_history_observation_chars", 12000) or 12000)
            self._max_history_observation_chars = max(200, configured_value)
        except Exception:
            self._max_history_observation_chars = 12000
        
        #  是否已注册到注册表
        self._registered = False

        self._trace_logger: Optional[logging.Logger] = None
        self._trace_log_path: Optional[str] = None
        self.configure_trace_logger(identity=self.name, task_id=None)
        self._trace("agent_initialized", agent_type=self.config.agent_type.value)

        self._trace_logger: Optional[logging.Logger] = None
        self._trace_log_path: Optional[str] = None
        self.configure_trace_logger(identity=self.name, task_id=None)
        self._trace("agent_initialized", agent_type=self.config.agent_type.value)
        
        #  加载知识模块到系统提示词
        if self.knowledge_modules:
            self._load_knowledge_modules()

    @staticmethod
    def _sanitize_log_token(value: Optional[str], default: str) -> str:
        raw = str(value or "").strip().lower()
        safe = re.sub(r"[^a-z0-9._-]+", "_", raw)
        return safe or default

    @classmethod
    def _resolve_task_log_dir(cls, task_id: Optional[str]) -> Path:
        safe_task_id = cls._sanitize_log_token(task_id, "no_task")
        log_dir = Path(__file__).resolve().parents[4] / "log" / "agent_runs" / safe_task_id
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    @classmethod
    def _resolve_trace_log_path(cls, identity: str, task_id: Optional[str]) -> str:
        safe_identity = cls._sanitize_log_token(identity, "agent")
        log_dir = cls._resolve_task_log_dir(task_id)
        return str(log_dir / f"{safe_identity}.log")

    @classmethod
    def _build_trace_logger(cls, identity: str, task_id: Optional[str]) -> tuple[logging.Logger, str]:
        safe_identity = cls._sanitize_log_token(identity, "agent")
        safe_task = cls._sanitize_log_token(task_id, "no_task")
        logger_name = f"{__name__}.trace.{safe_task}.{safe_identity}"
        trace_logger = logging.getLogger(logger_name)
        trace_logger.setLevel(logging.INFO)
        trace_logger.propagate = False
        target_file = cls._resolve_trace_log_path(identity, task_id)

        with _AGENT_TRACE_HANDLER_LOCK:
            has_handler = False
            for handler in trace_logger.handlers:
                if isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", "") == target_file:
                    has_handler = True
                    break
            if not has_handler:
                try:
                    file_handler = logging.FileHandler(target_file, encoding="utf-8")
                except PermissionError:
                    fallback_dir = Path(tempfile.gettempdir()) / "audittool-agent-runs" / safe_task
                    fallback_dir.mkdir(parents=True, exist_ok=True)
                    target_file = str(fallback_dir / f"{safe_identity}.log")
                    file_handler = logging.FileHandler(target_file, encoding="utf-8")
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(
                    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
                )
                trace_logger.addHandler(file_handler)

        return trace_logger, target_file

    def configure_trace_logger(
        self,
        identity: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """配置当前 Agent 的 trace 日志输出目录，按 task_id 归档。"""
        final_identity = str(identity or self.name or "agent").strip() or "agent"
        final_task_id = str(task_id or self._task_id or "").strip() or None
        self._task_id = final_task_id
        trace_logger, trace_path = self._build_trace_logger(final_identity, final_task_id)
        self._trace_logger = trace_logger
        self._trace_log_path = trace_path
        self._trace(
            "trace_logger_configured",
            identity=final_identity,
            task_id=final_task_id or "no_task",
            trace_log_path=trace_path,
        )
        return trace_path

    def _trace(self, message: str, **fields: Any) -> None:
        trace_logger = getattr(self, "_trace_logger", None)
        if trace_logger is None:
            return
        details: List[str] = []
        for key, value in fields.items():
            if value is None:
                continue
            text = str(value)
            if len(text) > 500:
                text = text[:500] + "..."
            details.append(f"{key}={text}")
        suffix = f" | {'; '.join(details)}" if details else ""
        trace_logger.info(f"[{self.name}] {message}{suffix}")
    
    def _register_to_registry(self, task: Optional[str] = None) -> None:
        """注册到Agent注册表（延迟注册，在run时调用）"""
        logger.debug(f"[AgentTree] _register_to_registry 被调用: {self.config.name} (id={self._agent_id}, parent={self.parent_id}, _registered={self._registered})")
        
        if self._registered:
            logger.debug(f"[AgentTree] {self.config.name} 已注册，跳过 (id={self._agent_id})")
            return
        
        logger.debug(f"[AgentTree] 正在注册 Agent: {self.config.name} (id={self._agent_id}, parent={self.parent_id})")
        task_id = str(getattr(self, "_task_id", "") or "").strip() or None
        if task_id:
            self._state.task_context["task_id"] = task_id

        agent_registry.register_agent(
            agent_id=self._agent_id,
            agent_name=self.config.name,
            agent_type=self.config.agent_type.value,
            task=task or self._state.task or "Initializing",
            parent_id=self.parent_id,
            agent_instance=self,
            state=self._state,
            knowledge_modules=self.knowledge_modules,
            task_id=task_id,
        )
        
        # 创建消息队列
        message_bus.create_queue(self._agent_id)
        self._registered = True
        
        tree = agent_registry.get_agent_tree(task_id=task_id)
        logger.debug(f"[AgentTree] Agent 注册完成: {self.config.name}, 当前树节点数: {len(tree['nodes'])}")
    
    def set_parent_id(self, parent_id: str) -> None:
        """设置父Agent ID（在调度时调用）"""
        self.parent_id = parent_id
        self._state.parent_id = parent_id
    
    def _load_knowledge_modules(self) -> None:
        """加载知识模块到系统提示词"""
        if not self.knowledge_modules:
            return

        try:
            from ..knowledge.loader import knowledge_loader

            enhanced_prompt = knowledge_loader.build_system_prompt_with_modules(
                self.config.system_prompt or "",
                self.knowledge_modules,
            )
            self.config.system_prompt = enhanced_prompt

            logger.info(f"[{self.name}] Loaded knowledge modules: {self.knowledge_modules}")
        except Exception as e:
            logger.warning(f"Failed to load knowledge modules: {e}")

    def _get_timeout_config(self) -> Dict[str, int]:
        """
        获取超时配置（秒）

        优先级：用户配置 > 环境变量默认值

        Returns:
            包含各种超时配置的字典
        """
        from app.core.config import settings

        # 尝试从 llm_service 获取用户配置的超时值
        if hasattr(self.llm_service, 'get_agent_timeout_config'):
            return self.llm_service.get_agent_timeout_config()

        # 回退到环境变量默认值
        return {
            'llm_first_token_timeout': getattr(settings, 'LLM_FIRST_TOKEN_TIMEOUT', 45),
            'llm_stream_timeout': getattr(settings, 'LLM_STREAM_TIMEOUT', 120),
            'agent_timeout': getattr(settings, 'AGENT_TIMEOUT_SECONDS', 1800),
            'sub_agent_timeout': getattr(settings, 'SUB_AGENT_TIMEOUT_SECONDS', 600),
            'tool_timeout': getattr(settings, 'TOOL_TIMEOUT_SECONDS', 60),
        }
    
    @property
    def name(self) -> str:
        return self.config.name

    @name.setter
    def name(self, value: str) -> None:
        self.config.name = value

    @property
    def agent_id(self) -> str:
        return self._agent_id
    
    @property
    def state(self) -> AgentState:
        return self._state
    
    @property
    def agent_type(self) -> AgentType:
        return self.config.agent_type
    
    # ============ Agent间消息处理 ============
    
    def check_messages(self) -> List[AgentMessage]:
        """
        检查并处理收到的消息
        
        Returns:
            未读消息列表
        """
        messages = message_bus.get_messages(
            self._agent_id,
            unread_only=True,
            mark_as_read=True,
        )
        
        for msg in messages:
            # 处理消息
            if msg.from_agent == "user":
                # 用户消息直接添加到对话历史
                self._state.add_message("user", msg.content)
            else:
                # Agent间消息使用XML格式
                self._state.add_message("user", msg.to_xml())
            
            # 如果在等待状态，恢复执行
            if self._state.is_waiting_for_input():
                self._state.resume_from_waiting()
                agent_registry.update_agent_status(self._agent_id, "running")
        
        return messages
    
    def has_pending_messages(self) -> bool:
        """检查是否有待处理的消息"""
        return message_bus.has_unread_messages(self._agent_id)
    
    def send_message_to_parent(
        self,
        content: str,
        message_type: MessageType = MessageType.INFORMATION,
    ) -> None:
        """向父Agent发送消息"""
        if self.parent_id:
            message_bus.send_message(
                from_agent=self._agent_id,
                to_agent=self.parent_id,
                content=content,
                message_type=message_type,
            )
    
    def send_message_to_agent(
        self,
        target_id: str,
        content: str,
        message_type: MessageType = MessageType.INFORMATION,
    ) -> None:
        """向指定Agent发送消息"""
        message_bus.send_message(
            from_agent=self._agent_id,
            to_agent=target_id,
            content=content,
            message_type=message_type,
        )
    
    # ============ 生命周期管理 ============
    
    def on_start(self) -> None:
        """Agent开始执行时调用"""
        self._state.start()
        agent_registry.update_agent_status(self._agent_id, "running")
    
    def on_complete(self, result: Dict[str, Any]) -> None:
        """Agent完成时调用"""
        self._state.set_completed(result)
        agent_registry.update_agent_status(self._agent_id, "completed", result)
        
        # 向父Agent报告完成
        if self.parent_id:
            message_bus.send_completion_report(
                from_agent=self._agent_id,
                to_agent=self.parent_id,
                summary=result.get("summary", "Task completed"),
                findings=result.get("findings", []),
                success=True,
            )
    
    def on_error(self, error: str) -> None:
        """Agent出错时调用"""
        self._state.set_failed(error)
        agent_registry.update_agent_status(self._agent_id, "failed", {"error": error})
    
    @abstractmethod
    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        执行 Agent 任务
        
        Args:
            input_data: 输入数据
            
        Returns:
            Agent 执行结果
        """
        pass
    
    def cancel(self):
        """取消执行"""
        self._cancelled = True
        logger.info(f"[{self.name}] Cancel requested")
    
        #  外部取消检查回调
        self._cancel_callback = None

    def reset_cancellation_state(self) -> None:
        """
        重置取消状态（用于同一 Agent 实例的重试场景）。

        仅重置内部 `_cancelled` 标志，不重置统计字段，确保任务级统计连续。
        """
        if self._cancelled:
            logger.info(f"[{self.name}] Reset cancellation state for retry")
        self._cancelled = False

    def set_cancel_callback(self, callback) -> None:
        """设置外部取消检查回调"""
        self._cancel_callback = callback

    @property
    def is_cancelled(self) -> bool:
        """检查是否已取消（包含内部标志和外部回调）"""
        if self._cancelled:
            return True
        # 检查外部回调
        cancel_callback = getattr(self, "_cancel_callback", None)
        if cancel_callback and cancel_callback():
            self._cancelled = True
            logger.info(f"[{self.name}] Detected cancellation from callback")
            return True
        return False

    def set_tool_runtime(self, runtime: Optional["ToolRuntime"]) -> None:
        """设置工具运行时（可选）。"""
        self._tool_runtime = runtime
        if runtime and hasattr(runtime, "get_write_scope_guard"):
            try:
                self._write_scope_guard = runtime.get_write_scope_guard()
            except Exception:
                self._write_scope_guard = None

    def set_write_scope_guard(self, guard: Optional["TaskWriteScopeGuard"]) -> None:
        """设置写入范围守卫。"""
        self._write_scope_guard = guard

    @staticmethod
    def _is_strict_mode(runtime: Optional["ToolRuntime"]) -> bool:
        if not runtime:
            return False
        return bool(getattr(runtime, "strict_mode", False))

    def _allow_local_tool_in_strict_mode(
        self,
        *,
        runtime: Optional["ToolRuntime"],
        tool_name: str,
        local_tool_available: bool,
    ) -> bool:
        if not runtime:
            return False
        return self._is_strict_local_tool_allowed(
            tool_name=tool_name,
            local_tool_available=local_tool_available,
            runtime_can_handle=False,
        )

    def _runtime_metadata(self) -> Dict[str, Any]:
        metadata = getattr(self.config, "metadata", None)
        if isinstance(metadata, dict):
            return metadata
        return {}

    @staticmethod
    def _metadata_bool(metadata: Dict[str, Any], key: str, default: bool = False) -> bool:
        value = metadata.get(key)
        if isinstance(value, bool):
            return value
        return bool(default)

    def _is_smart_audit_mode(self) -> bool:
        metadata = self._runtime_metadata()
        if self._metadata_bool(metadata, "smart_audit_mode", False):
            return True
        mode = str(metadata.get("audit_mode") or "").strip().lower()
        return mode in {"smart_audit", "agent_audit"}

    def _disable_virtual_routing(self) -> bool:
        metadata = self._runtime_metadata()
        return self._metadata_bool(
            metadata,
            "disable_virtual_routing",
            default=self._is_smart_audit_mode(),
        )

    def _strict_local_tool_allowlist(self) -> Set[str]:
        allowlist = set(STRICT_MODE_LOCAL_ONLY_TOOL_NAMES)
        allowlist.update(SCAN_CORE_LOCAL_SKILL_IDS)
        metadata = self._runtime_metadata()
        extra_tools = metadata.get("strict_local_tools_allowed")
        if isinstance(extra_tools, list):
            allowlist.update(
                str(item or "").strip().lower()
                for item in extra_tools
                if str(item or "").strip()
            )
        return allowlist

    def _is_strict_local_tool_allowed(
        self,
        *,
        tool_name: str,
        local_tool_available: bool,
        runtime_can_handle: bool,
    ) -> bool:
        if not local_tool_available or runtime_can_handle:
            return False
        normalized = str(tool_name or "").strip().lower()
        if not normalized:
            return False
        return normalized in self._strict_local_tool_allowlist()

    def _read_scope_policy(self) -> str:
        metadata = self._runtime_metadata()
        value = str(metadata.get("read_scope_policy") or "").strip().lower()
        if value:
            return value
        if self._is_smart_audit_mode():
            return "project_scope"
        return ""

    def set_write_scope_guard(self, guard: Optional["TaskWriteScopeGuard"]) -> None:
        """单独设置写入作用域守卫。"""
        self._write_scope_guard = guard

    @staticmethod
    def _build_write_scope_error(reason: str) -> str:
        normalized = str(reason or "").strip()
        if normalized == "write_scope_limit_reached":
            return "写入被拒绝：当前任务可写文件数已达上限，请仅修改已授权文件。"
        if normalized == "write_scope_path_forbidden":
            return "写入被拒绝：不允许目录级/通配/越界/敏感目录写入。"
        return "写入被拒绝：目标文件不在证据绑定白名单中，请提供 finding_id/todo_id/reason。"

    def _is_write_tool(self, tool_name: str) -> bool:
        normalized = str(tool_name or "").strip().lower()
        if normalized in WRITE_TOOL_GUARD_NAMES:
            return True
        guard = self._write_scope_guard
        if guard and hasattr(guard, "is_write_tool"):
            try:
                return bool(guard.is_write_tool(normalized))
            except Exception:
                return normalized in WRITE_TOOL_GUARD_NAMES
        return False

    def _enforce_write_scope(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Optional[str]]:
        """执行写入作用域校验，并返回规范化后的输入与事件 metadata。"""
        normalized_input = dict(tool_input or {})
        guard = self._write_scope_guard
        if not guard:
            return normalized_input, {}, None

        if not self._is_write_tool(tool_name):
            return normalized_input, {}, None

        if not hasattr(guard, "evaluate_write_request"):
            return normalized_input, {}, None

        try:
            decision = guard.evaluate_write_request(tool_name=tool_name, tool_input=normalized_input)
        except Exception as exc:
            logger.warning("[%s] write scope guard evaluation failed: %s", self.name, exc)
            return normalized_input, {}, None

        metadata: Dict[str, Any] = {}
        if hasattr(guard, "decision_metadata"):
            try:
                metadata = dict(guard.decision_metadata(decision))  # type: ignore[arg-type]
            except Exception:
                metadata = {}
        if not metadata:
            metadata = {
                "write_scope_allowed": bool(getattr(decision, "allowed", False)),
                "write_scope_reason": str(getattr(decision, "reason", "") or ""),
                "write_scope_file": getattr(decision, "file_path", None),
                "write_scope_total_files": int(getattr(decision, "total_files", 0) or 0),
            }

        normalized_file = getattr(decision, "file_path", None)
        if bool(getattr(decision, "allowed", False)) and isinstance(normalized_file, str) and normalized_file:
            #  修复：不修改大模型输出的原始路径，只记录规范化路径到 metadata
            metadata["write_scope_normalized_path"] = normalized_file
            return normalized_input, metadata, None

        reason = str(getattr(decision, "reason", "") or "write_scope_not_allowed")
        return normalized_input, metadata, self._build_write_scope_error(reason)
    
    # ============ 协作方法 ============
    
    def receive_handoff(self, handoff: TaskHandoff):
        """
        接收来自前序 Agent 的任务交接
        
        Args:
            handoff: 任务交接对象
        """
        self._incoming_handoff = handoff
        logger.info(
            f"[{self.name}] Received handoff from {handoff.from_agent}: "
            f"{handoff.summary[:50]}..."
        )
    
    def get_handoff_context(self) -> str:
        """
        获取交接上下文（用于构建 LLM prompt）
        
        Returns:
            格式化的上下文字符串
        """
        if not self._incoming_handoff:
            return ""
        return self._incoming_handoff.to_prompt_context()
    
    def add_insight(self, insight: str):
        """记录洞察"""
        self._insights.append(insight)
    
    def record_work(self, work: str):
        """记录完成的工作"""
        self._work_completed.append(work)
    
    def create_handoff(
        self,
        to_agent: str,
        summary: str,
        key_findings: List[Dict[str, Any]] = None,
        suggested_actions: List[Dict[str, Any]] = None,
        attention_points: List[str] = None,
        priority_areas: List[str] = None,
        context_data: Dict[str, Any] = None,
    ) -> TaskHandoff:
        """
        创建任务交接
        
        Args:
            to_agent: 目标 Agent
            summary: 工作摘要
            key_findings: 关键发现
            suggested_actions: 建议的行动
            attention_points: 需要关注的点
            priority_areas: 优先分析区域
            context_data: 上下文数据
            
        Returns:
            TaskHandoff 对象
        """
        return TaskHandoff(
            from_agent=self.name,
            to_agent=to_agent,
            summary=summary,
            work_completed=self._work_completed.copy(),
            key_findings=key_findings or [],
            insights=self._insights.copy(),
            suggested_actions=suggested_actions or [],
            attention_points=attention_points or [],
            priority_areas=priority_areas or [],
            context_data=context_data or {},
        )
    
    def build_prompt_with_handoff(self, base_prompt: str) -> str:
        """
        构建包含交接上下文的 prompt
        
        Args:
            base_prompt: 基础 prompt
            
        Returns:
            增强后的 prompt
        """
        handoff_context = self.get_handoff_context()
        if not handoff_context:
            return base_prompt
        
        return f"""{base_prompt}

---
## 前序 Agent 交接信息

{handoff_context}

---
请基于以上来自前序 Agent 的信息，结合你的专业能力开展工作。
"""
    
    def reset_session_memory(self) -> None:
        """
        重置会话级内存（任务级隔离）
        
        在 Workflow 中每个任务/轮次完成后调用，确保：
        - _insights 和 _work_completed 被清除
        - _incoming_handoff 被重置
        
        这样可以完全隔离任务，防止跨任务的内存污染。
        
        使用场景：
        - Analysis 处理完一个风险点，清理内存
        - Verification 验证完一个漏洞，清理内存
        - 在 Workflow 引擎每个循环后调用
        """
        self._insights.clear()
        self._work_completed.clear()
        self._incoming_handoff = None
        
        logger.debug(
            f"[{self.name}] Session memory reset: insights cleared, work_completed cleared, handoff cleared"
        )
    
    # ============ 核心事件发射方法 ============
    
    async def emit_event(
        self,
        event_type: str,
        message: str,
        **kwargs
    ):
        """发射事件"""
        if self.event_emitter:
            from ..event_manager import AgentEventData
            
            # 准备 metadata
            metadata = kwargs.get("metadata", {}) or {}
            if "agent_name" not in metadata:
                metadata["agent_name"] = self.name
            
            # 分离已知字段和未知字段
            known_fields = {
                "phase", "tool_name", "tool_input", "tool_output", 
                "tool_duration_ms", "finding_id", "tokens_used"
            }
            
            event_kwargs = {}
            for k, v in kwargs.items():
                if k in known_fields:
                    event_kwargs[k] = v
                elif k != "metadata":
                    # 将未知字段放入 metadata
                    metadata[k] = v
            
            await self.event_emitter.emit(AgentEventData(
                event_type=event_type,
                message=message,
                metadata=metadata,
                **event_kwargs
            ))
    
    # ============ LLM 思考相关事件 ============
    
    async def emit_thinking(self, message: str):
        """发射 LLM 思考事件"""
        await self.emit_event("thinking", message)
    
    async def emit_llm_start(self, iteration: int):
        """发射 LLM 开始思考事件"""
        self._trace("llm_start", iteration=iteration)
        await self.emit_event(
            "llm_start",
            f"[{self.name}] 第 {iteration} 轮迭代开始",
            metadata={"iteration": iteration}
        )
    
    async def emit_llm_thought(self, thought: str, iteration: int):
        """发射 LLM 思考内容事件 - 这是核心！展示 LLM 在想什么"""
        self._trace("llm_thought", iteration=iteration, thought_preview=(str(thought or "")[:300]))
        thought_text = str(thought or "").strip()
        if thought_text:
            self._recent_thought_texts.append(thought_text)
            hint = self._extract_file_hint_from_context([thought_text])
            hinted_path = str(hint.get("file_path") or "").strip()
            if hinted_path:
                self._remember_reason_path(hinted_path)

        normalized = re.sub(r"\s+", " ", (thought or "").strip())
        thought_digest = hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest() if normalized else ""

        if thought_digest and thought_digest == self._last_llm_thought_digest:
            self._llm_thought_repeat_count += 1
        else:
            self._last_llm_thought_digest = thought_digest or None
            self._llm_thought_repeat_count = 0
            self._llm_thought_suppressed_count = 0

        if self._llm_thought_repeat_count >= self._llm_thought_repeat_suppress_threshold:
            self._llm_thought_suppressed_count += 1
            if self._llm_thought_suppressed_count % self._llm_thought_repeat_summary_interval == 0:
                await self.emit_event(
                    "llm_thought",
                    f"[{self.name}] 思考重复已抑制 {self._llm_thought_suppressed_count} 条",
                    metadata={
                        "thought": thought,
                        "iteration": iteration,
                        "suppressed_repeat_count": self._llm_thought_suppressed_count,
                    },
                )
            return

        # 截断过长的思考内容
        display_thought = thought[:500] + "..." if len(thought) > 500 else thought
        await self.emit_event(
            "llm_thought",
            f"[{self.name}] 思考: {display_thought}",
            metadata={
                "thought": thought,
                "iteration": iteration,
                "suppressed_repeat_count": self._llm_thought_suppressed_count,
            }
        )
    
    async def emit_thinking_start(self):
        """发射开始思考事件（流式输出用）"""
        await self.emit_event("thinking_start", "开始思考...")
    
    async def emit_thinking_token(self, token: str, accumulated: str):
        """发射思考 token 事件（流式输出用）"""
        await self.emit_event(
            "thinking_token",
            "",  # 不需要 message，前端从 metadata 获取
            metadata={
                "token": token,
                "accumulated": accumulated,
            }
        )
    
    async def emit_thinking_end(self, full_response: str):
        """发射思考结束事件（流式输出用）"""
        await self.emit_event(
            "thinking_end",
            "思考完成",
            metadata={"accumulated": full_response}
        )
    
    async def emit_llm_decision(self, decision: str, reason: str = ""):
        """发射 LLM 决策事件 - 展示 LLM 做了什么决定"""
        self._trace("llm_decision", decision=decision, reason=(reason or "")[:300])
        await self.emit_event(
            "llm_decision",
            f"[{self.name}] 决策: {decision}" + (f" ({reason})" if reason else ""),
            metadata={
                "decision": decision,
                "reason": reason,
            }
        )
    
    async def emit_llm_complete(self, result_summary: str, tokens_used: int):
        """发射 LLM 完成事件"""
        self._trace("llm_complete", result_summary=(result_summary or "")[:300], tokens_used=tokens_used)
        await self.emit_event(
            "llm_complete",
            f"[{self.name}] 完成: {result_summary} (消耗 {tokens_used} tokens)",
            metadata={
                "tokens_used": tokens_used,
            }
        )
    
    async def emit_llm_action(self, action: str, action_input: Dict):
        """发射 LLM 动作决策事件"""
        safe_action_input = normalize_json_safe(action_input or {})
        self._trace(
            "llm_action",
            action=action,
            action_input=dump_json_safe(safe_action_input, ensure_ascii=False)[:500],
        )
        await self.emit_event(
            "llm_action",
            f"[{self.name}] 执行动作: {action}",
            metadata={
                "action": action,
                "action_input": safe_action_input,
            }
        )
    
    async def emit_llm_observation(self, observation: str):
        """发射 LLM 观察事件"""
        self._trace("llm_observation", observation_preview=(str(observation or "")[:500]))
        obs_text = observation or ""

        # If the observation mostly repeats the latest tool_result output, avoid logging it twice.
        snapshot = self._last_tool_result_snapshot if isinstance(self._last_tool_result_snapshot, dict) else None
        deduped = False
        observation_ref: Optional[Dict[str, Any]] = None
        if snapshot and isinstance(obs_text, str) and obs_text.strip():
            snap_prefix = str(snapshot.get("prefix") or "")
            # Heuristic: if the tool output prefix shows up inside observation, treat as duplicate.
            if snap_prefix and len(snap_prefix) >= 80 and snap_prefix in obs_text:
                deduped = True
                observation_ref = {
                    "tool_call_id": snapshot.get("tool_call_id"),
                    "tool_name": snapshot.get("tool_name"),
                    "digest": snapshot.get("digest"),
                }
                obs_text = obs_text[:300] + "...(omitted duplicate tool output)" if len(obs_text) > 300 else obs_text

        # 截断过长的观察结果
        display_obs = obs_text[:300] + "..." if len(obs_text) > 300 else obs_text
        safe_observation, truncated = _truncate_with_flag(obs_text)
        await self.emit_event(
            "llm_observation",
            f"[{self.name}] 观察结果: {display_obs}",
            metadata={
                "observation": safe_observation,
                "truncated": truncated,
                "deduped": bool(deduped),
                "observation_ref": observation_ref,
            }
        )
    
    # ============ 工具调用相关事件 ============
    
    async def emit_tool_call(
        self,
        tool_name: str,
        tool_input: Dict,
        tool_call_id: Optional[str] = None,
        alias_used: Optional[str] = None,
        input_repaired: Optional[Dict[str, str]] = None,
        validation_error: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ):
        """发射工具调用事件"""
        safe_tool_input = normalize_json_safe(tool_input or {})
        self._trace(
            "tool_call",
            tool_name=tool_name,
            tool_input=dump_json_safe(safe_tool_input, ensure_ascii=False)[:500],
            tool_call_id=tool_call_id,
            alias_used=alias_used,
        )
        metadata: Dict[str, Any] = {}
        if tool_call_id:
            metadata["tool_call_id"] = tool_call_id
        if alias_used:
            metadata["alias_used"] = alias_used
        if input_repaired:
            metadata["input_repaired"] = input_repaired
        if validation_error:
            metadata["validation_error"] = validation_error
        if isinstance(extra_metadata, dict):
            metadata.update(extra_metadata)
        await self.emit_event(
            "tool_call",
            f"[{self.name}] 调用工具: {tool_name}",
            tool_name=tool_name,
            tool_input=safe_tool_input,
            metadata=metadata,
        )
    
    async def emit_tool_result(
        self,
        tool_name: str,
        result: str,
        duration_ms: int,
        tool_call_id: Optional[str] = None,
        tool_status: str = "completed",
        alias_used: Optional[str] = None,
        input_repaired: Optional[Dict[str, str]] = None,
        validation_error: Optional[str] = None,
        cache_hit: Optional[bool] = None,
        cache_key: Optional[str] = None,
        cache_policy: Optional[str] = None,
        evidence_metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        error_code: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ):
        """发射工具结果事件"""
        self._trace(
            "tool_result",
            tool_name=tool_name,
            duration_ms=duration_ms,
            tool_status=tool_status,
            tool_call_id=tool_call_id,
            result_preview=(str(result or "")[:500]),
        )
        #  修复：确保 result 不为 None，避免显示 "None" 字符串
        safe_result = result if result and result != "None" else ""
        stored_result, truncated = _truncate_with_flag(safe_result)
        tool_output_dict = {"result": stored_result if stored_result else "", "truncated": truncated}
        if isinstance(evidence_metadata, dict) and evidence_metadata:
            tool_output_dict["metadata"] = dict(evidence_metadata)
        if error:
            tool_output_dict["error"] = str(error)
        if error_code:
            tool_output_dict["error_code"] = str(error_code)

        # Snapshot the latest tool output so llm_observation can avoid duplicating it.
        try:
            digest = hashlib.sha1(stored_result.encode("utf-8", errors="ignore")).hexdigest() if stored_result else ""
        except Exception:
            digest = ""
        self._last_tool_result_snapshot = {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "digest": digest,
            "prefix": stored_result[:256] if isinstance(stored_result, str) else "",
        }
        self._last_tool_result_payload = {
            "tool_name": tool_name,
            "tool_output": dict(tool_output_dict),
        }

        metadata: Dict[str, Any] = {
            "tool_status": tool_status,
            "runtime_used": False,
        }
        if tool_call_id:
            metadata["tool_call_id"] = tool_call_id
        if alias_used:
            metadata["alias_used"] = alias_used
        if input_repaired:
            metadata["input_repaired"] = input_repaired
        if validation_error:
            metadata["validation_error"] = validation_error
        if cache_hit is not None:
            metadata["cache_hit"] = bool(cache_hit)
        if cache_key:
            metadata["cache_key"] = cache_key
        if cache_policy:
            metadata["cache_policy"] = cache_policy
        if isinstance(extra_metadata, dict):
            metadata.update(extra_metadata)
        await self.emit_event(
            "tool_result",
            f"[{self.name}] 工具 {tool_name} 完成 ({duration_ms}ms)",
            tool_name=tool_name,
            tool_output=tool_output_dict,
            tool_duration_ms=duration_ms,
            metadata=metadata,
        )
    
    # ============ 发现相关事件 ============

    async def emit_finding(
        self,
        title: str,
        severity: str,
        vuln_type: str,
        file_path: str = "",
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        is_verified: bool = False,
        display_title: Optional[str] = None,
        cwe_id: Optional[str] = None,
        description: Optional[str] = None,
        description_markdown: Optional[str] = None,
        verification_evidence: Optional[str] = None,
        code_snippet: Optional[str] = None,
        code_context: Optional[str] = None,
        function_trigger_flow: Optional[List[str]] = None,
        reachability_file: Optional[str] = None,
        reachability_function: Optional[str] = None,
        reachability_function_start_line: Optional[int] = None,
        reachability_function_end_line: Optional[int] = None,
        context_start_line: Optional[int] = None,
        context_end_line: Optional[int] = None,
        finding_scope: Optional[str] = None,
        verification_todo_id: Optional[str] = None,
        verification_fingerprint: Optional[str] = None,
        verification_status: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ):
        """发射漏洞发现事件"""
        finding_id = str(uuid.uuid4())

        normalized_line_start: Optional[int] = None
        if line_start is not None:
            try:
                normalized_line_start = int(line_start)
            except Exception:
                normalized_line_start = None
        normalized_line_end: Optional[int] = None
        if line_end is not None:
            try:
                normalized_line_end = int(line_end)
            except Exception:
                normalized_line_end = None
        normalized_reachability_start: Optional[int] = None
        if reachability_function_start_line is not None:
            try:
                normalized_reachability_start = int(reachability_function_start_line)
            except Exception:
                normalized_reachability_start = None
        normalized_reachability_end: Optional[int] = None
        if reachability_function_end_line is not None:
            try:
                normalized_reachability_end = int(reachability_function_end_line)
            except Exception:
                normalized_reachability_end = None
        normalized_context_start: Optional[int] = None
        if context_start_line is not None:
            try:
                normalized_context_start = int(context_start_line)
            except Exception:
                normalized_context_start = None
        normalized_context_end: Optional[int] = None
        if context_end_line is not None:
            try:
                normalized_context_end = int(context_end_line)
            except Exception:
                normalized_context_end = None

        normalized_cwe_id = normalize_cwe_id(cwe_id)
        generated_description_markdown: Optional[str] = (
            str(description_markdown).strip()
            if description_markdown is not None and str(description_markdown).strip()
            else None
        )
        if not generated_description_markdown:
            try:
                generated_description_markdown = build_cn_structured_description_markdown(
                    file_path=file_path or reachability_file,
                    function_name=reachability_function,
                    vulnerability_type=vuln_type,
                    title=display_title or title,
                    description=description,
                    code_snippet=code_snippet,
                    code_context=code_context,
                    cwe_id=normalized_cwe_id,
                    raw_description=description,
                    line_start=normalized_line_start,
                    line_end=normalized_line_end,
                    verification_evidence=verification_evidence,
                    function_trigger_flow=function_trigger_flow,
                )
            except Exception:
                generated_description_markdown = None

        #  使用 EventManager.emit_finding 发送正确的事件类型
        if self.event_emitter and hasattr(self.event_emitter, 'emit_finding'):
            await self.event_emitter.emit_finding(
                finding_id=finding_id,
                title=title,
                severity=severity,
                vulnerability_type=vuln_type,
                file_path=file_path or None,
                line_start=normalized_line_start,
                line_end=normalized_line_end,
                is_verified=is_verified,
                display_title=display_title,
                cwe_id=normalized_cwe_id,
                description=description,
                description_markdown=generated_description_markdown,
                verification_evidence=verification_evidence,
                code_snippet=code_snippet,
                function_trigger_flow=function_trigger_flow,
                reachability_file=reachability_file,
                reachability_function=reachability_function,
                reachability_function_start_line=normalized_reachability_start,
                reachability_function_end_line=normalized_reachability_end,
                context_start_line=normalized_context_start,
                context_end_line=normalized_context_end,
                finding_scope=finding_scope,
                verification_todo_id=verification_todo_id,
                verification_fingerprint=verification_fingerprint,
                verification_status=verification_status,
                extra_metadata=extra_metadata,
            )
        else:
            # 回退：使用通用事件发射
            severity_emoji = {
                "critical": "🔴",
                "high": "🟠",
                "medium": "🟡",
                "low": "🟢",
            }.get(severity.lower(), "⚪")

            event_type = "finding_verified" if is_verified else "finding_new"
            await self.emit_event(
                event_type,
                f"{severity_emoji} [{self.name}] 发现漏洞: [{severity.upper()}] {title}\n   类型: {vuln_type}\n   位置: {file_path}",
                metadata={
                    "id": finding_id,
                    "title": title,
                    "severity": severity,
                    "vulnerability_type": vuln_type,
                    "file_path": file_path,
                    "line_start": normalized_line_start,
                    "line_end": normalized_line_end,
                    "is_verified": is_verified,
                    "display_title": display_title,
                    "cwe_id": normalized_cwe_id,
                    "description": description,
                    "description_markdown": generated_description_markdown,
                    "verification_evidence": verification_evidence,
                    "code_snippet": code_snippet,
                    "function_trigger_flow": function_trigger_flow,
                    "reachability_file": reachability_file,
                    "reachability_function": reachability_function,
                    "reachability_function_start_line": normalized_reachability_start,
                    "reachability_function_end_line": normalized_reachability_end,
                    "context_start_line": normalized_context_start,
                    "context_end_line": normalized_context_end,
                    "finding_scope": finding_scope,
                    "verification_todo_id": verification_todo_id,
                    "verification_fingerprint": verification_fingerprint,
                    "verification_status": verification_status,
                    **(extra_metadata if isinstance(extra_metadata, dict) else {}),
                }
            )
    
    # ============ 通用工具方法 ============
    
    async def call_tool(self, tool_name: str, **kwargs) -> Any:
        """
        调用工具
        
        Args:
            tool_name: 工具名称
            **kwargs: 工具参数
            
        Returns:
            工具执行结果
        """
        tool = self.tools.get(tool_name)
        if not tool:
            logger.warning(f"Tool not found: {tool_name}")
            return None
        
        self._tool_calls += 1
        tool_call_id = str(uuid.uuid4())
        await self.emit_tool_call(tool_name, kwargs, tool_call_id=tool_call_id)
        
        import time
        start = time.time()
        
        result = await tool.execute(**kwargs)
        
        duration_ms = int((time.time() - start) * 1000)
        await self.emit_tool_result(
            tool_name,
            str(result.data),
            duration_ms,
            tool_call_id=tool_call_id,
            tool_status="completed" if result.success else "failed",
        )
        
        return result
    
    async def call_llm(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        调用 LLM
        
        Args:
            messages: 消息列表
            tools: 可用工具描述

        Returns:
            LLM 响应
        """
        self._iteration += 1

        try:
            #  不传递 temperature 和 max_tokens，让 LLMService 使用用户配置
            response = await self.llm_service.chat_completion(
                messages=messages,
                tools=tools,
            )

            if response.get("usage"):
                self._total_tokens += response["usage"].get("total_tokens", 0)

            return response

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def get_tool_descriptions(self) -> List[Dict[str, Any]]:
        """获取工具描述（用于 LLM）"""
        descriptions = []
        
        for name, tool in self.tools.items():
            if name.startswith("_"):
                continue
            
            desc = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.description,
                }
            }
            
            # 添加参数 schema
            if hasattr(tool, 'args_schema') and tool.args_schema:
                desc["function"]["parameters"] = tool.args_schema.schema()
            
            descriptions.append(desc)
        
        return descriptions
    
    def get_stats(self) -> Dict[str, Any]:
        """获取执行统计"""
        return {
            "agent": self.name,
            "type": self.agent_type.value,
            "iterations": self._iteration,
            "tool_calls": self._tool_calls,
            "tokens_used": self._total_tokens,
        }

    def _prepare_observation_for_history(
        self,
        observation: str,
        max_chars: Optional[int] = None,
    ) -> str:
        """
        Prepare observation text for conversation history.

        Keep event output intact, but cap history payload to reduce context bloat.
        """
        text = str(observation or "")
        limit = int(max_chars or self._max_history_observation_chars or 12000)
        limit = max(200, limit)
        if len(text) <= limit:
            return text

        marker = (
            f"\n\n...[Observation 已裁剪，原始长度 {len(text)} 字符]...\n\n"
        )
        keep = max(200, limit - len(marker))
        head_keep = int(keep * 0.7)
        tail_keep = keep - head_keep
        return f"{text[:head_keep]}{marker}{text[-tail_keep:]}"

    @staticmethod
    def _estimate_conversation_tokens(messages: List[Dict[str, Any]]) -> int:
        """A lightweight token estimate for diagnostics."""
        total_chars = 0
        for msg in messages or []:
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            total_chars += len(str(content or ""))
        return max(0, total_chars // 4)
    
    # ============ Memory Compression ============
    
    def compress_messages_if_needed(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
    ) -> List[Dict[str, str]]:
        """
        如果消息历史过长，自动压缩
        
        Args:
            messages: 消息列表
            max_tokens: 最大token数（None 时自动按模型窗口动态计算）
            
        Returns:
            压缩后的消息列表
        """
        from ...llm.memory_compressor import MemoryCompressor

        effective_max_tokens = max_tokens
        if effective_max_tokens is None:
            model_budget = int((self.config.max_tokens or 4096) * 4)
            effective_max_tokens = max(6000, min(24000, model_budget))
        
        compressor = MemoryCompressor(max_total_tokens=effective_max_tokens)
        
        if compressor.should_compress(messages):
            logger.info(f"[{self.name}] Compressing conversation history...")
            compressed = compressor.compress_history(messages)
            logger.info(f"[{self.name}] Compressed {len(messages)} -> {len(compressed)} messages")
            return compressed
        
        return messages
    
    # ============ 统一的流式 LLM 调用 ============

    async def stream_llm_call(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        auto_compress: bool = True,
    ) -> Tuple[str, int]:
        """
        统一的流式 LLM 调用方法

        所有 Agent 共用此方法，避免重复代码

        Args:
            messages: 消息列表
            temperature: 温度（None 时使用用户配置）
            max_tokens: 最大 token 数（None 时使用用户配置）
            auto_compress: 是否自动压缩过长的消息历史

        Returns:
            (完整响应内容, token数量)
        """
        thinking_push_mode = str(getattr(self, "_thinking_push_mode", "stream") or "stream").strip().lower()
        if thinking_push_mode not in {"stream", "final_only"}:
            thinking_push_mode = "stream"
        emit_stream_thinking = thinking_push_mode != "final_only"

        #  自动压缩过长的消息历史
        if auto_compress:
            messages = self.compress_messages_if_needed(messages)

        accumulated = ""
        total_tokens = 0
        chunk_count = 0
        self._last_llm_stream_meta = {
            "chunk_count": 0,
            "finish_reason": None,
            "empty_reason": None,
            "error_type": None,
            "error": None,
            "timeout_stage": None,
            "token_estimate_ms": 0.0,
            "llm_request_start_ts": None,
            "first_token_latency_ms": None,
            "max_chunk_gap_ms": 0.0,
            "usage_source": "none",
        }
        self._trace("llm_stream_started", message_count=len(messages or []))

        #  在开始 LLM 调用前检查取消
        if self.is_cancelled:
            logger.info(f"[{self.name}] Cancelled before LLM call")
            return "", 0

        if emit_stream_thinking:
            logger.info(f"[{self.name}] Starting stream_llm_call, emitting thinking_start...")
            await self.emit_thinking_start()
            logger.info(f"[{self.name}] thinking_start emitted, starting LLM stream...")
        else:
            logger.info(f"[{self.name}] Starting stream_llm_call with final_only thinking mode...")

        try:
            # 获取流式迭代器（传入 None 时使用用户配置）
            stream = self.llm_service.chat_completion_stream(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # 兼容不同版本的 python async generator
            iterator = stream.__aiter__()

            import time
            first_token_received = False
            request_started_perf = time.perf_counter()
            last_chunk_at = request_started_perf
            self._last_llm_stream_meta["llm_request_start_ts"] = datetime.now(timezone.utc).isoformat()

            def _merge_stream_diagnostics(chunk: Dict[str, Any]) -> None:
                diagnostics = chunk.get("diagnostics") if isinstance(chunk, dict) else None
                if not isinstance(diagnostics, dict):
                    return
                if "token_estimate_ms" in diagnostics:
                    self._last_llm_stream_meta["token_estimate_ms"] = diagnostics.get("token_estimate_ms")
                if diagnostics.get("usage_source"):
                    self._last_llm_stream_meta["usage_source"] = diagnostics.get("usage_source")

            while True:
                # 检查取消
                if self.is_cancelled:
                    logger.info(f"[{self.name}] Cancelled during LLM streaming loop")
                    break
                
                try:
                    #  使用用户配置的超时时间
                    # 第一个 token 使用首Token超时，后续 token 使用流式超时
                    first_token_timeout = float(self._timeout_config.get('llm_first_token_timeout', 90))
                    stream_timeout = float(self._timeout_config.get('llm_stream_timeout', 60))
                    timeout = first_token_timeout if not first_token_received else stream_timeout

                    chunk = await asyncio.wait_for(iterator.__anext__(), timeout=timeout)
                    chunk_received_at = time.perf_counter()
                    gap_ms = max(0.0, (chunk_received_at - last_chunk_at) * 1000)
                    if chunk_count > 0:
                        self._last_llm_stream_meta["max_chunk_gap_ms"] = max(
                            float(self._last_llm_stream_meta.get("max_chunk_gap_ms") or 0.0),
                            round(gap_ms, 3),
                        )
                    last_chunk_at = chunk_received_at
                    chunk_count += 1
                    self._last_llm_stream_meta["chunk_count"] = chunk_count
                    _merge_stream_diagnostics(chunk)
                    
                    if chunk["type"] == "token":
                        if not first_token_received:
                            self._last_llm_stream_meta["first_token_latency_ms"] = round(
                                (chunk_received_at - request_started_perf) * 1000,
                                3,
                            )
                        first_token_received = True
                        token = chunk["content"]
                        #  累积 content，确保 accumulated 变量更新
                        # 注意：某些 adapter 返回的 chunk["accumulated"] 可能已经包含了累积值，
                        # 但为了安全起见，如果不一致，我们自己累积
                        if "accumulated" in chunk:
                            accumulated = chunk["accumulated"]
                        else:
                            # 如果 adapter 没返回 accumulated，我们自己拼
                            # 注意：如果是 token 类型，content 是增量
                            # 如果 accumulated 被覆盖了，需要小心。
                            # 实际上 service.py 中 chat_completion_stream 保证了 accumulated 存在
                            # 这里我们信任 service 层的 accumulated
                            pass

                        # Double check if accumulated is empty but we have token
                        if not accumulated and token:
                            accumulated += token # Fallback

                        if emit_stream_thinking:
                            await self.emit_thinking_token(token, accumulated)
                        #  CRITICAL: 让出控制权给事件循环，让 SSE 有机会发送事件
                        await asyncio.sleep(0)

                    elif chunk["type"] == "done":
                        accumulated = chunk["content"]
                        self._last_llm_stream_meta["finish_reason"] = chunk.get("finish_reason")
                        if chunk.get("usage"):
                            total_tokens = chunk["usage"].get("total_tokens", 0)
                        if not str(accumulated or "").strip():
                            self._last_llm_stream_meta["empty_reason"] = "empty_done"
                        break

                    elif chunk["type"] == "error":
                        accumulated = chunk.get("accumulated", "")
                        error_msg = chunk.get("error", "Unknown error")
                        error_type = chunk.get("error_type", "unknown")
                        user_message = chunk.get("user_message", error_msg)
                        self._last_llm_stream_meta.update(
                            {
                                "finish_reason": chunk.get("finish_reason"),
                                "empty_reason": error_type if error_type in ("empty_response", "empty_stream") else None,
                                "error_type": error_type,
                                "error": error_msg,
                            }
                        )
                        logger.error(f"[{self.name}] Stream error ({error_type}): {error_msg}")

                        if chunk.get("usage"):
                            total_tokens = chunk["usage"].get("total_tokens", 0)

                        # 使用特殊前缀标记 API 错误，让调用方能够识别
                        # 格式：[API_ERROR:error_type] user_message
                        if error_type in ("rate_limit", "quota_exceeded", "authentication", "connection"):
                            accumulated = f"[API_ERROR:{error_type}] {user_message}"
                        elif error_type in ("empty_response", "empty_stream"):
                            finish_reason = chunk.get("finish_reason")
                            finish_hint = f", finish_reason={finish_reason}" if finish_reason else ""
                            accumulated = (
                                f"[API_ERROR:{error_type}] {user_message}"
                                f" (chunks={chunk_count}{finish_hint})"
                            )
                        elif not accumulated:
                            accumulated = f"[系统错误: {error_msg}] 请重新思考并输出你的决策。"
                        break

                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    timeout_type = "First Token" if not first_token_received else "Stream"
                    timeout_stage = "preflight_timeout" if not first_token_received else "stream_idle_timeout"
                    logger.error(f"[{self.name}] LLM {timeout_type} Timeout ({timeout}s)")
                    error_msg = f"LLM 响应超时 ({timeout_type}, {timeout}s)"
                    await self.emit_event(
                        "error",
                        error_msg,
                        metadata={
                            "timeout_stage": timeout_stage,
                            "llm_request_start_ts": self._last_llm_stream_meta.get("llm_request_start_ts"),
                            "first_token_latency_ms": self._last_llm_stream_meta.get("first_token_latency_ms"),
                            "max_chunk_gap_ms": self._last_llm_stream_meta.get("max_chunk_gap_ms"),
                            "usage_source": self._last_llm_stream_meta.get("usage_source"),
                            "token_estimate_ms": self._last_llm_stream_meta.get("token_estimate_ms"),
                        },
                    )
                    self._last_llm_stream_meta.update(
                        {
                            "finish_reason": None,
                            "empty_reason": "timeout",
                            "error_type": timeout_stage,
                            "timeout_stage": timeout_stage,
                            "error": error_msg,
                            "chunk_count": chunk_count,
                        }
                    )
                    if not accumulated:
                         accumulated = f"[超时错误: {timeout}s 无响应] 请尝试简化请求或重试。"
                    break
                    
        except asyncio.CancelledError:
            logger.info(f"[{self.name}] LLM call cancelled")
            raise
        except Exception as e:
            #  增强异常处理，避免吞掉错误
            logger.error(f"[{self.name}] Unexpected error in stream_llm_call: {e}", exc_info=True)
            await self.emit_event("error", f"LLM 调用错误: {str(e)}")
            self._last_llm_stream_meta.update(
                {
                    "finish_reason": None,
                    "empty_reason": "exception",
                    "error_type": "exception",
                    "error": str(e),
                    "chunk_count": chunk_count,
                }
            )
            accumulated = f"[LLM调用错误: {str(e)}] 请重试。"
        finally:
            if emit_stream_thinking:
                await self.emit_thinking_end(accumulated)
            else:
                final_text = str(accumulated or "").strip()
                if final_text:
                    await self.emit_event(
                        "thinking",
                        "思考完成",
                        metadata={
                            "thought": final_text,
                            "final_only": True,
                        },
                    )
            self._trace(
                "llm_stream_finished",
                chunk_count=chunk_count,
                total_tokens=total_tokens,
                finish_reason=self._last_llm_stream_meta.get("finish_reason"),
                empty_reason=self._last_llm_stream_meta.get("empty_reason"),
            )
        
        #  记录空响应警告，帮助调试
        if not accumulated or not accumulated.strip():
            finish_reason = self._last_llm_stream_meta.get("finish_reason")
            empty_reason = self._last_llm_stream_meta.get("empty_reason")
            logger.warning(
                f"[{self.name}] Empty LLM response returned "
                f"(total_tokens: {total_tokens}, finish_reason: {finish_reason}, empty_reason: {empty_reason}, chunks: {chunk_count})"
            )
            # Ensure caller does not receive a silent empty string.
            if empty_reason in ("empty_response", "empty_stream", "empty_done"):
                finish_hint = f", finish_reason={finish_reason}" if finish_reason else ""
                accumulated = (
                    f"[API_ERROR:empty_response] 模型返回空响应"
                    f" (chunks={chunk_count}{finish_hint})"
                )
            elif empty_reason == "timeout":
                accumulated = "[API_ERROR:timeout] 模型超时未返回有效内容"
            elif self._last_llm_stream_meta.get("error_type"):
                err = self._last_llm_stream_meta.get("error_type")
                accumulated = f"[API_ERROR:{err}] 模型返回空响应"
        
        return accumulated, total_tokens

    def _resolve_tool_name(self, requested_tool_name: str) -> Tuple[str, Optional[str]]:
        """Resolve unknown tool names using conservative alias candidates."""
        if requested_tool_name in self.tools:
            return requested_tool_name, None

        if self._disable_virtual_routing():
            return requested_tool_name, None

        normalized = str(requested_tool_name or "").strip().lower()
        candidates = TOOL_ALIAS_CANDIDATES.get(normalized, [])
        for candidate in candidates:
            if candidate in self.tools:
                return candidate, requested_tool_name
        return requested_tool_name, None

    @staticmethod
    def _looks_like_tool_failure_output(output: str) -> bool:
        text = str(output or "").strip()
        if not text:
            return True
        lowered = text.lower()
        if lowered.startswith(("", "", "错误:", "error:", "failed:", "失败")):
            return True
        failure_hints = (
            "工具执行失败",
            "工具参数校验失败",
            "工具参数缺失",
            "工具不可用",
            "写入策略校验失败",
            "工具运行时执行失败",
            "无本地回退",
        )
        return any(hint in text for hint in failure_hints)

    @staticmethod
    def _infer_search_keyword_from_input(tool_input: Dict[str, Any]) -> str:
        direct = str(tool_input.get("keyword") or "").strip()
        if direct:
            return direct

        query = str(tool_input.get("query") or "").strip()
        if query:
            return query

        searches = tool_input.get("searches")
        if isinstance(searches, list):
            for item in searches:
                if isinstance(item, dict):
                    candidate = str(item.get("query") or item.get("text") or "").strip()
                    if candidate:
                        return candidate

        vuln_type = str(
            tool_input.get("vulnerability_type")
            or tool_input.get("type")
            or tool_input.get("doc_id")
            or ""
        ).strip()
        return vuln_type

    def _build_proxy_fallback_requests(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_obj: Optional[Any] = None,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        fallback_names: List[str] = []
        configured_fallbacks = getattr(tool_obj, "runtime_fallback_tools", None) if tool_obj is not None else None
        if isinstance(configured_fallbacks, list):
            fallback_names.extend(
                [
                    str(item).strip()
                    for item in configured_fallbacks
                    if str(item).strip()
                ]
            )

        normalized_tool = str(tool_name or "").strip().lower()
        if not fallback_names:
            fallback_map: Dict[str, List[str]] = {
                "query_security_knowledge": ["search_code"],
                "get_vulnerability_knowledge": ["search_code", "get_code_window"],
            }
            fallback_names.extend(fallback_map.get(normalized_tool, []))

        fallback_requests: List[Tuple[str, Dict[str, Any]]] = []
        source_input = dict(tool_input or {})
        for candidate in fallback_names:
            if candidate == normalized_tool:
                continue
            payload = copy.deepcopy(source_input)
            if candidate == "search_code":
                keyword = self._infer_search_keyword_from_input(source_input)
                if not keyword:
                    continue
                payload = {"keyword": keyword}
                directory = str(
                    source_input.get("directory")
                    or source_input.get("path")
                    or source_input.get("file_path")
                    or ""
                ).strip()
                if directory:
                    payload["directory"] = directory
            elif candidate == "get_code_window":
                file_path = str(
                    source_input.get("file_path")
                    or source_input.get("path")
                    or ""
                ).strip()
                if not file_path:
                    continue
                anchor_line = source_input.get("line_start") or source_input.get("line") or 1
                payload = {
                    "file_path": file_path,
                    "anchor_line": anchor_line,
                }
                if source_input.get("before_lines") is not None:
                    payload["before_lines"] = source_input.get("before_lines")
                if source_input.get("after_lines") is not None:
                    payload["after_lines"] = source_input.get("after_lines")
            elif candidate == "locate_enclosing_function":
                file_path = str(
                    source_input.get("file_path")
                    or source_input.get("path")
                    or ""
                ).strip()
                if not file_path:
                    continue
                payload = {
                    "file_path": file_path,
                }
                line_start = source_input.get("line_start") or source_input.get("line")
                if line_start is not None:
                    payload["line_start"] = line_start
            elif candidate == "get_symbol_body":
                file_path = str(
                    source_input.get("path")
                    or source_input.get("file_path")
                    or ""
                ).strip()
                symbol_name = str(
                    source_input.get("symbol_name")
                    or source_input.get("function_name")
                    or ""
                ).strip()
                if not file_path or not symbol_name:
                    continue
                payload = {"file_path": file_path, "symbol_name": symbol_name}
            fallback_requests.append((candidate, payload))
        return fallback_requests

    async def _execute_soft_fallback(
        self,
        *,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_obj: Optional[Any],
        fallback_depth: int,
    ) -> Optional[Tuple[str, str, Optional[Dict[str, Any]]]]:
        if fallback_depth >= 2:
            return None

        fallback_requests = self._build_proxy_fallback_requests(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_obj=tool_obj,
        )
        if not fallback_requests:
            return None

        for fallback_tool_name, fallback_input in fallback_requests:
            if fallback_tool_name == tool_name:
                continue
            try:
                fallback_output = await self.execute_tool(
                    fallback_tool_name,
                    fallback_input,
                    _fallback_depth=fallback_depth + 1,
                )
            except Exception:
                continue
            if not self._looks_like_tool_failure_output(fallback_output):
                fallback_evidence_metadata: Optional[Dict[str, Any]] = None
                payload = self._last_tool_result_payload if isinstance(self._last_tool_result_payload, dict) else None
                if payload and payload.get("tool_name") == fallback_tool_name:
                    tool_output_payload = payload.get("tool_output")
                    if isinstance(tool_output_payload, dict) and isinstance(tool_output_payload.get("metadata"), dict):
                        fallback_evidence_metadata = dict(tool_output_payload["metadata"])
                return fallback_tool_name, fallback_output, fallback_evidence_metadata
        return None

    @staticmethod
    def _split_multi_patterns(raw_value: Any) -> List[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        text = str(raw_value).strip()
        if not text:
            return []
        parts = [item.strip() for item in re.split(r"[|,;]", text) if item.strip()]
        return parts or [text]

    @staticmethod
    def _normalize_pattern_types(raw_value: Any) -> List[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, list):
            return sorted({str(item).strip() for item in raw_value if str(item).strip()})
        text = str(raw_value).strip()
        if not text:
            return []
        parts = [item.strip() for item in re.split(r"[|,;]", text) if item.strip()]
        return sorted(set(parts))

    @staticmethod
    def _normalize_path_key(path: Any) -> str:
        value = str(path or "").strip().replace("\\", "/")
        while value.startswith("./"):
            value = value[2:]
        while "//" in value:
            value = value.replace("//", "/")
        return value

    @staticmethod
    def _sanitize_file_path_text(raw_value: Any) -> str:
        text = str(raw_value or "").strip()
        if not text:
            return ""

        text = text.strip().strip("`'\"")
        text = text.replace("\\", "/")

        path_candidate_pattern = re.compile(
            r"(?P<path>[A-Za-z0-9_./-]+\.[A-Za-z0-9_+-]+(?:[:#]\d+(?:-\d+)?)?)"
        )
        matched = path_candidate_pattern.search(text)
        if matched:
            text = str(matched.group("path") or "").strip()
        else:
            text = text.splitlines()[0].strip()
            text = re.split(r"[，,;；]\s*", text, maxsplit=1)[0].strip()

        text = re.sub(
            r"[（(][^()（）]{0,120}(?:和其他|and\s+other|others?|等)[^()（）]{0,120}[)）]\s*$",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s*(?:和其他|等)\S*\s*$",
            "",
            text,
            flags=re.IGNORECASE,
        )

        return text.strip().strip("`'\"()[]{}<>，,。！？；;")

    @staticmethod
    def _looks_like_line_suffix(value: str) -> bool:
        return bool(re.fullmatch(r"\d+(?:-\d+)?", str(value or "")))

    def _append_recent_unique(self, queue: deque[str], value: str) -> None:
        normalized = self._normalize_path_key(value).strip("/")
        if not normalized:
            return
        try:
            queue.remove(normalized)
        except ValueError:
            pass
        queue.appendleft(normalized)

    def _remember_reason_path(self, raw_value: Any) -> None:
        value = self._normalize_path_key(raw_value)
        if not value:
            return
        if ":" in value:
            maybe_path, maybe_line = value.rsplit(":", 1)
            if maybe_path and self._looks_like_line_suffix(maybe_line):
                value = maybe_path
        value = value.strip("/")
        if not value:
            return

        basename = os.path.basename(value)
        if "." in basename:
            dir_part = os.path.dirname(value)
            self._append_recent_unique(self._recent_reason_dirs, dir_part or ".")
            return
        self._append_recent_unique(self._recent_reason_dirs, value)

    def _remember_search_directory(self, raw_value: Any) -> None:
        value = self._normalize_path_key(raw_value)
        if not value:
            return
        value = value.strip("/")
        if not value:
            value = "."
        self._append_recent_unique(self._recent_search_directories, value)
        self._append_recent_unique(self._recent_reason_dirs, value)

    def _collect_reason_paths_for_read(self, file_hint: Dict[str, Any]) -> List[str]:
        candidates: List[str] = []
        hinted_path = str(file_hint.get("file_path") or "").strip()
        if hinted_path:
            self._remember_reason_path(hinted_path)
            candidates.append(hinted_path)

        candidates.extend(list(self._recent_reason_dirs))
        candidates.extend(list(self._recent_search_directories))

        deduped: List[str] = []
        seen: Set[str] = set()
        for item in candidates:
            normalized = self._normalize_path_key(item).strip("/")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
            if len(deduped) >= 12:
                break
        return deduped

    def _record_tool_context(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_metadata: Dict[str, Any],
    ) -> None:
        self._record_evidence_paths_from_tool_context(tool_name, tool_input, tool_metadata)
        if tool_name in {"get_code_window", "get_file_outline", "get_function_summary", "get_symbol_body"}:
            for value in (tool_metadata.get("file_path"), tool_input.get("file_path"), tool_input.get("path")):
                self._remember_reason_path(value)
            return
        if tool_name == "search_code":
            for value in (
                tool_metadata.get("effective_directory"),
                tool_input.get("directory"),
                tool_metadata.get("original_directory"),
            ):
                self._remember_search_directory(value)

    def _register_evidence_path(self, file_path: Any) -> None:
        guard = self._write_scope_guard
        if guard and hasattr(guard, "register_evidence_path"):
            try:
                guard.register_evidence_path(file_path)
            except Exception:
                pass

    def _record_evidence_paths_from_tool_context(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_metadata: Dict[str, Any],
    ) -> None:
        normalized_tool = str(tool_name or "").strip().lower()
        candidates: List[Any] = []

        if normalized_tool in {
            "get_code_window",
            "get_file_outline",
            "get_function_summary",
            "get_symbol_body",
            "controlflow_analysis_light",
            "locate_enclosing_function",
            "verify_reachability",
        }:
            candidates.extend(
                [
                    tool_metadata.get("file_path"),
                    tool_metadata.get("resolved_file_path"),
                    tool_input.get("file_path"),
                    tool_input.get("path"),
                ]
            )

        if normalized_tool == "search_code":
            candidates.extend(
                [
                    tool_input.get("directory"),
                    tool_metadata.get("effective_directory"),
                    tool_metadata.get("original_directory"),
                ]
            )
            raw_results = tool_metadata.get("results")
            if isinstance(raw_results, list):
                for item in raw_results[:30]:
                    if isinstance(item, dict):
                        candidates.append(item.get("file"))
                        candidates.append(item.get("file_path"))

        if normalized_tool == "pattern_match":
            candidates.extend([tool_input.get("scan_file"), tool_metadata.get("scan_file")])
            matched_files = tool_metadata.get("matched_files")
            if isinstance(matched_files, list):
                candidates.extend(matched_files[:30])

        if normalized_tool in {"dataflow_analysis", "logic_authz_analysis"}:
            candidates.extend(
                [
                    tool_input.get("file_path"),
                    tool_metadata.get("file_path"),
                    tool_metadata.get("reachability_file"),
                ]
            )
            evidence_lines = tool_metadata.get("evidence_lines")
            if isinstance(evidence_lines, list):
                for item in evidence_lines[:20]:
                    if isinstance(item, dict):
                        candidates.append(item.get("file_path"))
                    elif isinstance(item, str):
                        candidates.append(item.split(":", 1)[0])

        for value in candidates:
            self._register_evidence_path(value)

    def _extract_file_hint_from_context(self, texts: List[str]) -> Dict[str, Any]:
        if not texts:
            return {}

        pattern = re.compile(
            r"(?P<path>[A-Za-z0-9_./-]+\.(?:c|h|cc|cpp|cxx|hpp|hh|py|js|ts|java|go|rs|php|rb|swift))"
            r"(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?"
        )
        fallback: Dict[str, Any] = {}
        for text in reversed(texts):
            for match in pattern.finditer(str(text or "")):
                raw_path = str(match.group("path") or "").strip()
                cleaned_path = self._sanitize_file_path_text(raw_path)
                if not cleaned_path:
                    continue
                start_raw = match.group("start")
                end_raw = match.group("end")
                start_line = int(start_raw) if start_raw else None
                end_line = int(end_raw) if end_raw else (start_line if start_line is not None else None)
                if start_line and end_line and end_line < start_line:
                    start_line, end_line = end_line, start_line
                candidate = {
                    "file_path": cleaned_path,
                    "start_line": start_line,
                    "end_line": end_line,
                }
                if start_line is not None:
                    return candidate
                if not fallback:
                    fallback = candidate
        return fallback

    @staticmethod
    def _normalize_keyword_candidate(candidate: Any) -> Optional[str]:
        text = str(candidate or "").strip().strip("`'\"")
        text = text.strip("，,。！？；;")
        if not text:
            return None
        if len(text) < 2 or len(text) > 220:
            return None
        if "\n" in text:
            return None
        if not re.search(r"[A-Za-z_]", text):
            return None
        if text.count(" ") > 4:
            return None
        return text

    def _extract_keyword_hint_from_context(self, texts: List[str]) -> Optional[str]:
        if not texts:
            return None

        quoted_pipe_patterns = (
            r'"([^"\n]{1,220}\|[^"\n]{1,220})"',
            r"'([^'\n]{1,220}\|[^'\n]{1,220})'",
            r"`([^`\n]{1,220}\|[^`\n]{1,220})`",
        )
        plain_pipe_pattern = r"\b[A-Za-z_][A-Za-z0-9_]*(?:\|[A-Za-z_][A-Za-z0-9_]*)+\b"
        chinese_list_pattern = r"([A-Za-z_][A-Za-z0-9_]*(?:、[A-Za-z_][A-Za-z0-9_]*){2,})"
        quoted_candidate_patterns = (
            r'"([A-Za-z0-9_\\|()\[\]{}*+.\-\s]{2,220})"',
            r"'([A-Za-z0-9_\\|()\[\]{}*+.\-\s]{2,220})'",
            r"`([A-Za-z0-9_\\|()\[\]{}*+.\-\s]{2,220})`",
        )

        for text in reversed(texts):
            text_value = str(text or "")
            for pattern in quoted_pipe_patterns:
                for candidate in re.findall(pattern, text_value):
                    normalized = self._normalize_keyword_candidate(candidate)
                    if normalized:
                        return normalized
            for candidate in re.findall(plain_pipe_pattern, text_value):
                normalized = self._normalize_keyword_candidate(candidate)
                if normalized:
                    return normalized
            for candidate in re.findall(chinese_list_pattern, text_value):
                normalized = self._normalize_keyword_candidate(str(candidate).replace("、", "|"))
                if normalized:
                    return normalized
            for pattern in quoted_candidate_patterns:
                for candidate in re.findall(pattern, text_value):
                    normalized = self._normalize_keyword_candidate(candidate)
                    if normalized:
                        return normalized

        return None

    @staticmethod
    def _keyword_prefers_regex(keyword: str) -> bool:
        text = str(keyword or "")
        if not text:
            return False
        if "|" in text:
            return True
        if re.search(r"\\[AbBdDsSwWZfnrtv]", text):
            return True
        if any(token in text for token in ("(?:", "(?=", "(?!", "(?<=", "(?<!")):
            return True
        if "[" in text and "]" in text:
            return True
        if text.startswith("^") or text.endswith("$"):
            return True
        if any(token in text for token in (".*", ".+")):
            return True
        return bool(re.search(r"\{\d+(?:,\d*)?\}", text))

    def _resolve_tool_timeout(self, resolved_tool_name: str) -> int:
        default_tool_timeout = int(self._timeout_config.get('tool_timeout', 60) or 60)
        normalized_tool_name = str(resolved_tool_name or "").strip().lower()
        if normalized_tool_name == "dataflow_analysis":
            return max(default_tool_timeout, 150)
        tool_timeouts = {
            "opengrep_scan": 120,
            "bandit_scan": 90,
            "gitleaks_scan": 60,
            "npm_audit": 90,
            "safety_scan": 60,
            "kunlun_scan": 180,
            "osv_scanner": 60,
            "trufflehog_scan": 90,
            "sandbox_exec": 60,
            "php_test": 30,
            "command_injection_test": 30,
            "sql_injection_test": 30,
            "xss_test": 30,
        }
        return tool_timeouts.get(normalized_tool_name, default_tool_timeout)

    @staticmethod
    def _coerce_positive_int(value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except Exception:
            return None
        if parsed <= 0:
            return None
        return parsed

    @staticmethod
    def _normalize_hint_list(raw_value: Any) -> List[str]:
        if raw_value is None:
            return []
        if isinstance(raw_value, list):
            return [
                str(item).strip()
                for item in raw_value
                if str(item).strip()
            ][:8]
        text = str(raw_value).strip()
        if not text:
            return []
        return [text[:240]]

    def _normalize_verify_reachability_input(
        self,
        tool_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload = dict(tool_input or {})
        file_path = str(payload.get("file_path") or payload.get("path") or "").strip()
        line_start = self._coerce_positive_int(payload.get("line_start") or payload.get("line"))
        line_end = self._coerce_positive_int(payload.get("line_end") or payload.get("end_line"))
        if line_start is not None and line_end is None:
            line_end = line_start
        if line_start is not None and line_end is not None and line_end < line_start:
            line_end = line_start

        function_name = str(payload.get("function_name") or "").strip() or None
        source_hints = self._normalize_hint_list(payload.get("source_hints"))
        sink_hints = self._normalize_hint_list(payload.get("sink_hints"))
        vulnerability_type = str(payload.get("vulnerability_type") or "").strip() or None
        call_chain_hint = self._normalize_hint_list(payload.get("call_chain_hint"))
        control_conditions_hint = self._normalize_hint_list(payload.get("control_conditions_hint"))

        return {
            "file_path": file_path,
            "line_start": line_start,
            "line_end": line_end,
            "function_name": function_name,
            "source_hints": source_hints,
            "sink_hints": sink_hints,
            "vulnerability_type": vulnerability_type,
            "call_chain_hint": call_chain_hint,
            "control_conditions_hint": control_conditions_hint,
        }

    def _build_verify_reachability_keyword(self, payload: Dict[str, Any]) -> Optional[str]:
        for candidate in (
            payload.get("function_name"),
            payload.get("vulnerability_type"),
            (payload.get("sink_hints") or [None])[0],
            (payload.get("source_hints") or [None])[0],
        ):
            text = str(candidate or "").strip()
            if text:
                return text[:120]
        return None

    @staticmethod
    def _extract_jsonish_dict(text: str) -> Optional[Dict[str, Any]]:
        raw_text = str(text or "").strip()
        if not raw_text:
            return None
        candidate = raw_text
        if "{" in raw_text and "}" in raw_text:
            start = raw_text.find("{")
            end = raw_text.rfind("}")
            if end > start:
                candidate = raw_text[start : end + 1]
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(candidate)  # type: ignore[arg-type]
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    def _extract_location_from_search_output(
        self,
        output: str,
    ) -> Tuple[Optional[str], Optional[int]]:
        text = str(output or "")
        path_line_patterns = (
            re.compile(
                r"(?P<path>[A-Za-z0-9_./\\-]+\.[A-Za-z0-9_]+):(?P<line>\d+)(?::\d+)?"
            ),
            re.compile(
                r"(?P<path>[A-Za-z0-9_./\\-]+\.[A-Za-z0-9_]+)\s*\(\s*line\s*(?P<line>\d+)\s*\)",
                re.IGNORECASE,
            ),
        )
        for pattern in path_line_patterns:
            for match in pattern.finditer(text):
                file_path = str(match.group("path") or "").strip()
                line_start = self._coerce_positive_int(match.group("line"))
                if file_path and line_start is not None:
                    return file_path, line_start

        payload = self._extract_jsonish_dict(text)
        if isinstance(payload, dict):
            search_lists: List[Any] = []
            for key in ("results", "matches", "items"):
                if isinstance(payload.get(key), list):
                    search_lists.append(payload.get(key))
            nested_data = payload.get("data")
            if isinstance(nested_data, dict):
                for key in ("results", "matches", "items"):
                    if isinstance(nested_data.get(key), list):
                        search_lists.append(nested_data.get(key))
            for raw_list in search_lists:
                for item in raw_list:
                    location = self._extract_search_location_from_item(item)
                    if location:
                        return location
        return None, None

    def _extract_search_location_from_item(
        self,
        item: Any,
    ) -> Optional[Tuple[str, int]]:
        if isinstance(item, str):
            return self._extract_location_from_search_output(item)
        if not isinstance(item, dict):
            return None

        file_path = str(
            item.get("file")
            or item.get("file_path")
            or item.get("path")
            or item.get("filename")
            or ""
        ).strip()
        line_start = self._coerce_positive_int(
            item.get("line")
            or item.get("line_start")
            or item.get("lineNumber")
            or item.get("startLine")
        )
        if file_path and line_start is not None:
            return file_path, int(line_start)

        location = item.get("location")
        if isinstance(location, dict):
            nested_path = str(
                location.get("file")
                or location.get("file_path")
                or location.get("path")
                or ""
            ).strip()
            nested_line = self._coerce_positive_int(
                location.get("line")
                or location.get("line_start")
                or location.get("lineNumber")
                or location.get("startLine")
            )
            if nested_path and nested_line is not None:
                return nested_path, int(nested_line)
        return None

    def _estimate_search_hit_count(
        self,
        output: str,
    ) -> int:
        text = str(output or "").strip()
        if not text:
            return 0
        lowered = text.lower()
        if "no matches found" in lowered or "没有找到匹配" in text:
            return 0

        payload = self._extract_jsonish_dict(text)
        if isinstance(payload, dict):
            for key in ("results", "matches", "items"):
                raw_list = payload.get(key)
                if isinstance(raw_list, list):
                    return len(raw_list)
            nested_data = payload.get("data")
            if isinstance(nested_data, dict):
                for key in ("results", "matches", "items"):
                    raw_list = nested_data.get(key)
                    if isinstance(raw_list, list):
                        return len(raw_list)

        match_count = len(
            re.findall(r"[A-Za-z0-9_./\\-]+\.[A-Za-z0-9_]+:\d+(?::\d+)?", text)
        )
        if match_count > 0:
            return match_count
        return 1

    def _extract_function_locator_result(
        self,
        output: str,
        *,
        target_line: Optional[int] = None,
    ) -> Dict[str, Any]:
        payload = parse_locator_payload(output)
        selected = (
            select_locator_function(payload, line_start=target_line)
            if isinstance(payload, dict)
            else None
        )

        best_name: Optional[str] = None
        best_start: Optional[int] = None
        best_end: Optional[int] = None
        if isinstance(selected, dict):
            best_name = str(selected.get("function") or "").strip() or None
            best_start = self._coerce_positive_int(selected.get("start_line"))
            best_end = self._coerce_positive_int(selected.get("end_line"))

        if best_name is None:
            match = re.search(
                r"(?:function|函数)\s*[:=]\s*([A-Za-z_][A-Za-z0-9_$]*)",
                str(output or ""),
                re.IGNORECASE,
            )
            if match:
                best_name = str(match.group(1) or "").strip() or None

        if best_start is not None and best_end is not None and best_end < best_start:
            best_end = best_start
        return {
            "function_name": best_name,
            "function_start_line": best_start,
            "function_end_line": best_end,
        }

    @staticmethod
    def _classify_flow_observation(text: str) -> str:
        lowered = str(text or "").lower()
        positive_markers = (
            '"path_found": true',
            '"path_found":true',
            "'path_found': true",
            "'path_found':true",
            "likely_reachable",
            "reachable",
            "可达",
            "path_found=true",
        )
        negative_markers = (
            '"path_found": false',
            '"path_found":false',
            "'path_found': false",
            "'path_found':false",
            "unreachable",
            "不可达",
            "no_flow",
            "path_found=false",
            "not reachable",
        )
        has_positive = any(marker in lowered for marker in positive_markers)
        has_negative = any(marker in lowered for marker in negative_markers)
        if has_negative and not has_positive:
            return "negative"
        if has_positive and not has_negative:
            return "positive"
        if has_negative and has_positive:
            if "unreachable" in lowered or "不可达" in lowered:
                return "negative"
            return "positive"
        return "unknown"

    @staticmethod
    def _classify_verify_blocked_reason(output: str) -> Optional[str]:
        text = str(output or "")
        lowered = text.lower()
        if not text.strip():
            return "insufficient_flow_evidence"
        tool_unavailable_hints = (
            "tool_call_failed:",
            "tool_adapter_unavailable:",
            "adapter_disabled_after_failures",
            "server disconnected without sending a response",
            "remoteprotocolerror",
            "connecterror",
            "readtimeout",
            "connect timeout",
            "connection reset",
            "connection refused",
            "healthcheck_failed",
            "status_502",
            "status_503",
            "status_504",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
        )
        if any(hint in lowered for hint in tool_unavailable_hints):
            return "tool_unavailable"
        if "runtime 未就绪" in text or "router 未匹配" in text:
            return "tool_unavailable"
        if "工具未成功处理" in text or "tool route" in lowered:
            return "tool_unavailable"
        if "工具未处理且本地工具不可用" in text:
            return "tool_unavailable"
        if "verify_pipeline_blocked_reason" in lowered and "tool_unavailable" in lowered:
            return "tool_unavailable"
        if "missing_location" in lowered or "missing_file_or_line" in lowered:
            return "missing_location"
        if "read_budget_exhausted" in lowered:
            return "read_budget_exhausted"
        if "insufficient_flow_evidence" in lowered:
            return "insufficient_flow_evidence"
        if "任务已取消" in text or "cancel" in lowered:
            return "cancelled"
        if "参数校验失败" in text or "工具参数缺失" in text:
            return "insufficient_flow_evidence"
        return None

    async def _execute_verify_reachability_pipeline(
        self,
        *,
        raw_tool_input: Dict[str, Any],
        fallback_depth: int = 0,
    ) -> str:
        normalized_input = self._normalize_verify_reachability_input(raw_tool_input)
        tool_call_id = str(uuid.uuid4())
        self._tool_calls += 1
        await self.emit_tool_call(
            "verify_reachability",
            normalized_input,
            tool_call_id=tool_call_id,
        )

        import time

        started_at = time.time()
        max_rounds = 2
        max_lines_per_read = 160
        max_total_read_lines = 600
        rounds_executed = 0
        pipeline_steps: List[str] = []
        flow_tools_used: List[str] = []
        read_scope_lines_total = 0
        read_scope_ranges: List[Dict[str, int]] = []
        blocked_reason: Optional[str] = None
        blocked_stage: Optional[str] = None
        reachability = "likely_reachable"
        authenticity_hint = "likely"
        location_source = "input"
        file_path = str(normalized_input.get("file_path") or "").strip()
        line_start = self._coerce_positive_int(normalized_input.get("line_start"))
        line_end = self._coerce_positive_int(normalized_input.get("line_end")) or line_start
        function_name = str(normalized_input.get("function_name") or "").strip() or None
        function_start_line: Optional[int] = None
        function_end_line: Optional[int] = None
        flow_observation_text = ""
        round_success = False
        runtime_failures: List[Dict[str, Any]] = []

        def _record_runtime_failure(stage: str, observation: str) -> None:
            if len(runtime_failures) >= 12:
                return
            runtime_failures.append(
                {
                    "stage": stage,
                    "reason": "tool_unavailable",
                    "observation_excerpt": str(observation or "")[:260],
                }
            )

        for round_index in range(1, max_rounds + 1):
            if self.is_cancelled:
                blocked_reason = "cancelled"
                break
            rounds_executed = round_index

            if not file_path or line_start is None:
                keyword = self._build_verify_reachability_keyword(normalized_input)
                if not keyword:
                    blocked_reason = "missing_location"
                    break
                location_source = "search_code"
                search_input: Dict[str, Any] = {"keyword": keyword, "max_results": 10}
                directory_hint = str(file_path or "").strip()
                if directory_hint and "/" in directory_hint:
                    search_input["directory"] = os.path.dirname(directory_hint) or "."
                pipeline_steps.append("search_code")
                search_output = await self.execute_tool(
                    "search_code",
                    search_input,
                    _fallback_depth=fallback_depth + 1,
                )
                if self._looks_like_tool_failure_output(search_output):
                    blocked_reason = self._classify_verify_blocked_reason(search_output) or "missing_location"
                    blocked_stage = "search_code"
                    if blocked_reason == "tool_unavailable":
                        _record_runtime_failure("search_code", search_output)
                    break
                located_file, located_line = self._extract_location_from_search_output(search_output)
                if located_file:
                    file_path = located_file
                if located_line is not None:
                    line_start = located_line
                    line_end = line_start if line_end is None else max(line_start, line_end)
                if not file_path or line_start is None:
                    blocked_reason = "missing_location"
                    break

            if line_end is None:
                line_end = line_start

            remaining_budget = max_total_read_lines - read_scope_lines_total
            if remaining_budget <= 0:
                blocked_reason = "read_budget_exhausted"
                break

            if (
                function_start_line is not None
                and function_end_line is not None
                and function_end_line >= function_start_line
                and (function_end_line - function_start_line + 1) <= max_lines_per_read
            ):
                read_start = function_start_line
                read_end = function_end_line
            else:
                before_radius = 40 if round_index == 1 else 70
                read_start = max(1, int(line_start) - before_radius)
                read_end = max(int(line_end or line_start), int(line_start)) + 119

            if read_end < read_start:
                read_end = read_start

            desired_span = read_end - read_start + 1
            bounded_span = min(max_lines_per_read, remaining_budget, desired_span)
            if bounded_span <= 0:
                blocked_reason = "read_budget_exhausted"
                break
            read_end = read_start + bounded_span - 1
            read_scope_lines_total += bounded_span
            read_scope_ranges.append(
                {
                    "round": int(round_index),
                    "start_line": int(read_start),
                    "end_line": int(read_end),
                    "max_lines": int(bounded_span),
                }
            )

            anchor_line = max(read_start, min(line_start, read_end))
            read_input = {
                "file_path": file_path,
                "anchor_line": int(anchor_line),
                "before_lines": int(max(0, anchor_line - read_start)),
                "after_lines": int(max(0, read_end - anchor_line)),
            }
            pipeline_steps.append("get_code_window")
            read_output = await self.execute_tool(
                "get_code_window",
                read_input,
                _fallback_depth=fallback_depth + 1,
            )
            if self._looks_like_tool_failure_output(read_output):
                blocked_reason = self._classify_verify_blocked_reason(read_output)
                if blocked_reason is None:
                    blocked_reason = "missing_location"
                blocked_stage = "get_code_window"
                if blocked_reason == "tool_unavailable":
                    _record_runtime_failure("get_code_window", read_output)
                break

            locate_input = {
                "file_path": file_path,
                "line_start": int(line_start),
            }
            pipeline_steps.append("locate_enclosing_function")
            locate_output = await self.execute_tool(
                "locate_enclosing_function",
                locate_input,
                _fallback_depth=fallback_depth + 1,
            )
            if self._looks_like_tool_failure_output(locate_output):
                locate_blocked = self._classify_verify_blocked_reason(locate_output)
                if locate_blocked == "tool_unavailable":
                    blocked_reason = locate_blocked
                    blocked_stage = "locate_enclosing_function"
                    _record_runtime_failure("locate_enclosing_function", locate_output)
                    break
            else:
                located_function = self._extract_function_locator_result(
                    locate_output,
                    target_line=line_start,
                )
                if str(located_function.get("function_name") or "").strip():
                    function_name = str(located_function["function_name"]).strip()
                function_start_line = self._coerce_positive_int(
                    located_function.get("function_start_line")
                ) or function_start_line
                function_end_line = self._coerce_positive_int(
                    located_function.get("function_end_line")
                ) or function_end_line
                if function_name:
                    extract_input = {
                        "file_path": file_path,
                        "symbol_name": function_name,
                    }
                    pipeline_steps.append("get_symbol_body")
                    extract_output = await self.execute_tool(
                        "get_symbol_body",
                        extract_input,
                        _fallback_depth=fallback_depth + 1,
                    )
                    if self._looks_like_tool_failure_output(extract_output):
                        extract_blocked = self._classify_verify_blocked_reason(extract_output)
                        if extract_blocked == "tool_unavailable":
                            blocked_reason = extract_blocked
                            blocked_stage = "get_symbol_body"
                            _record_runtime_failure("get_symbol_body", extract_output)
                            break

            analysis_start_line = (
                function_start_line
                if function_start_line is not None
                else int(read_start)
            )
            analysis_end_line = (
                function_end_line
                if function_end_line is not None
                else int(read_end)
            )
            if analysis_end_line < analysis_start_line:
                analysis_end_line = analysis_start_line

            dataflow_input = {
                "file_path": file_path,
                "start_line": int(analysis_start_line),
                "end_line": int(analysis_end_line),
                "source_hints": normalized_input.get("source_hints") or [],
                "sink_hints": normalized_input.get("sink_hints") or [],
                "variable_name": function_name or "user_input",
                "max_hops": 8,
            }
            pipeline_steps.append("dataflow_analysis")
            flow_tools_used.append("dataflow_analysis")
            dataflow_output = await self.execute_tool(
                "dataflow_analysis",
                dataflow_input,
                _fallback_depth=fallback_depth + 1,
            )
            if self._looks_like_tool_failure_output(dataflow_output):
                dataflow_blocked = self._classify_verify_blocked_reason(dataflow_output)
                if dataflow_blocked in {"tool_unavailable", "cancelled"}:
                    blocked_reason = dataflow_blocked
                    blocked_stage = "dataflow_analysis"
                    if dataflow_blocked == "tool_unavailable":
                        _record_runtime_failure("dataflow_analysis", dataflow_output)
                    break
            else:
                flow_observation_text = (
                    f"{flow_observation_text}\n\n[dataflow_analysis]\n{str(dataflow_output or '')}"
                ).strip()

            controlflow_input = {
                "file_path": file_path,
                "line_start": int(line_start),
                "line_end": int(line_end or line_start),
                "function_name": function_name,
                "vulnerability_type": normalized_input.get("vulnerability_type"),
                "call_chain_hint": normalized_input.get("call_chain_hint") or [],
                "control_conditions_hint": normalized_input.get("control_conditions_hint") or [],
            }
            pipeline_steps.append("controlflow_analysis_light")
            flow_tools_used.append("controlflow_analysis_light")
            controlflow_output = await self.execute_tool(
                "controlflow_analysis_light",
                controlflow_input,
                _fallback_depth=fallback_depth + 1,
            )
            if self._looks_like_tool_failure_output(controlflow_output):
                controlflow_blocked = self._classify_verify_blocked_reason(controlflow_output)
                if controlflow_blocked in {"tool_unavailable", "cancelled"}:
                    blocked_reason = controlflow_blocked
                    blocked_stage = "controlflow_analysis_light"
                    if controlflow_blocked == "tool_unavailable":
                        _record_runtime_failure("controlflow_analysis_light", controlflow_output)
                    break
            else:
                flow_observation_text = (
                    f"{flow_observation_text}\n\n[controlflow_analysis_light]\n{str(controlflow_output or '')}"
                ).strip()

            flow_state = self._classify_flow_observation(flow_observation_text)
            if flow_state == "negative":
                reachability = "unreachable"
                authenticity_hint = "false_positive"
                round_success = True
                break
            if flow_state == "positive":
                reachability = "reachable"
                authenticity_hint = "likely"
                round_success = True
                break

            blocked_reason = "insufficient_flow_evidence"
            if round_index < max_rounds:
                blocked_reason = None
                continue
            blocked_stage = "controlflow_analysis_light"
            break

        if not round_success and blocked_reason is None:
            blocked_reason = "insufficient_flow_evidence"
            blocked_stage = "flow_conclusion"

        unique_flow_tools: List[str] = []
        for item in flow_tools_used:
            normalized = str(item or "").strip()
            if normalized and normalized not in unique_flow_tools:
                unique_flow_tools.append(normalized)
        flow_tools_used = unique_flow_tools

        pipeline_metadata: Dict[str, Any] = {
            "verify_pipeline_steps": list(pipeline_steps),
            "verify_pipeline_rounds": int(rounds_executed),
            "read_scope_lines_total": int(read_scope_lines_total),
            "read_scope_ranges": list(read_scope_ranges),
            "flow_tools_used": list(flow_tools_used),
            "location_source": location_source,
            "runtime_failures": list(runtime_failures),
        }
        if blocked_reason:
            pipeline_metadata["verify_pipeline_blocked_reason"] = blocked_reason
        if blocked_stage:
            pipeline_metadata["verify_pipeline_blocked_stage"] = blocked_stage

        payload = {
            "reachability": reachability,
            "authenticity_hint": authenticity_hint,
            "file_path": file_path,
            "line_start": line_start,
            "line_end": line_end,
            "function_name": function_name,
            "verify_pipeline_steps": pipeline_metadata["verify_pipeline_steps"],
            "verify_pipeline_rounds": pipeline_metadata["verify_pipeline_rounds"],
            "verify_pipeline_blocked_reason": blocked_reason,
            "verify_pipeline_blocked_stage": blocked_stage,
            "read_scope_lines_total": pipeline_metadata["read_scope_lines_total"],
            "read_scope_ranges": pipeline_metadata["read_scope_ranges"],
            "flow_tools_used": pipeline_metadata["flow_tools_used"],
            "location_source": location_source,
            "runtime_failures": pipeline_metadata["runtime_failures"],
        }

        if blocked_reason:
            output_lines = [
                "verify_reachability 执行错误",
                f"blocked_reason: {blocked_reason}",
                f"location: {file_path or 'unknown'}:{line_start or 'unknown'}",
                "verify_pipeline_json:",
                json.dumps(payload, ensure_ascii=False),
            ]
            final_output = "\n".join(output_lines)
            duration_ms = int((time.time() - started_at) * 1000)
            await self.emit_tool_result(
                "verify_reachability",
                final_output,
                duration_ms,
                tool_call_id=tool_call_id,
                tool_status="failed",
                extra_metadata=pipeline_metadata,
            )
            return final_output

        if reachability not in {"reachable", "likely_reachable", "unreachable"}:
            reachability = "likely_reachable"

        output_lines = [
            "verify_reachability pipeline completed",
            f"reachability: {reachability}",
            f"authenticity_hint: {authenticity_hint}",
            f"location: {file_path}:{line_start}",
            "verify_pipeline_json:",
            json.dumps(payload, ensure_ascii=False),
        ]
        if flow_observation_text:
            output_lines.append("flow_observation_excerpt:")
            output_lines.append(flow_observation_text[:1200])
        final_output = "\n".join(output_lines)

        duration_ms = int((time.time() - started_at) * 1000)
        await self.emit_tool_result(
            "verify_reachability",
            final_output,
            duration_ms,
            tool_call_id=tool_call_id,
            tool_status="completed",
            extra_metadata=pipeline_metadata,
        )
        self._record_tool_context(
            tool_name="verify_reachability",
            tool_input=normalized_input,
            tool_metadata={
                "file_path": file_path,
                "resolved_file_path": file_path,
                "line_start": line_start,
                "line_end": line_end,
                **pipeline_metadata,
            },
        )
        return final_output

    def _resolve_virtual_tool_name(
        self,
        requested_tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Tuple[str, Optional[str]]:
        normalized = str(requested_tool_name or "").strip().lower()
        input_dict = tool_input if isinstance(tool_input, dict) else {}

        if normalized == "code_search":
            read_keys = {"file_path", "path", "start_line", "end_line", "max_lines"}
            search_keys = {"keyword", "query", "is_regex", "file_pattern", "directory", "case_sensitive"}

            target_name = "list_files"
            if any(key in input_dict for key in read_keys):
                target_name = "get_code_window"
            elif any(key in input_dict for key in search_keys):
                target_name = "search_code"

            if target_name in self.tools:
                return target_name, requested_tool_name
            return requested_tool_name, None

        if normalized == "locate_enclosing_function":
            return "locate_enclosing_function", requested_tool_name

        return requested_tool_name, None

    def _build_route_metadata(
        self,
        *,
        tool_name: str,
        tool_input: Dict[str, Any],
    ) -> Dict[str, Any]:
        """已废弃：不再使用路由元数据。"""
        return {}

    @staticmethod
    def _compact_retry_input(raw_input: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in dict(raw_input or {}).items():
            if value is None:
                continue
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    continue
                normalized[str(key)] = text
                continue
            if isinstance(value, (list, dict)) and not value:
                continue
            normalized[str(key)] = value
        return normalized

    def _build_retry_guard_key(self, tool_name: str, tool_input: Dict[str, Any]) -> Optional[str]:
        if tool_name not in RETRY_GUARD_TOOLS:
            return None

        if tool_name == "get_code_window":
            file_path = self._normalize_path_key(tool_input.get("file_path"))
            if not file_path:
                return None
            anchor_line = self._coerce_positive_int(
                tool_input.get("anchor_line") or tool_input.get("line") or tool_input.get("line_start")
            ) or 0
            before_lines = self._coerce_positive_int(tool_input.get("before_lines")) or 0
            after_lines = self._coerce_positive_int(tool_input.get("after_lines")) or 0
            fingerprint_payload = {
                "file": file_path,
                "anchor_line": int(anchor_line),
                "before_lines": int(before_lines),
                "after_lines": int(after_lines),
            }
            fingerprint = hashlib.sha1(
                json.dumps(
                    fingerprint_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                ).encode("utf-8", errors="ignore")
            ).hexdigest()[:12]
            return f"{tool_name}|{file_path}|{anchor_line}|{before_lines}|{after_lines}|{fingerprint}"

        if tool_name == "search_code":
            keyword = str(tool_input.get("keyword") or "").strip()
            directory = self._normalize_path_key(tool_input.get("directory"))
            patterns = ",".join(sorted(self._split_multi_patterns(tool_input.get("file_pattern"))))
            if not keyword:
                return None
            return f"{tool_name}|{keyword}|{directory}|{patterns}"

        if tool_name == "pattern_match":
            scan_file = self._normalize_path_key(tool_input.get("scan_file"))
            pattern_types = ",".join(self._normalize_pattern_types(tool_input.get("pattern_types")))
            if not scan_file:
                return None
            return f"{tool_name}|{scan_file}|{pattern_types}"

        return None

    @staticmethod
    def _is_deterministic_error_message(error_text: str) -> bool:
        text = str(error_text or "")
        return any(hint in text for hint in DETERMINISTIC_ERROR_HINTS)

    @staticmethod
    def _classify_strict_error(error_text: str) -> str:
        normalized = str(error_text or "").strip()
        lowered = normalized.lower()
        if not normalized:
            return "runtime_unknown_error"
        if normalized.startswith("invalid_recon_queue_service_binding"):
            return "invalid_recon_queue_service_binding"
        if normalized.startswith("tool_runtime_unavailable") or normalized.startswith("runtime_unavailable"):
            return "tool_runtime_unavailable"
        if normalized.startswith("tool_route_missing") or normalized.startswith("route_missing"):
            return "tool_route_missing"
        if normalized.startswith("tool_adapter_unavailable") or normalized.startswith("adapter_unavailable"):
            return "tool_adapter_unavailable"
        if normalized.startswith("skill_not_ready"):
            return "skill_not_ready"
        if "object is not callable" in lowered:
            return "invalid_callable_binding"
        if normalized.startswith("tool_unhandled_in_strict_mode") or normalized.startswith("unhandled_in_strict_mode"):
            return "tool_unhandled_in_strict_mode"
        if any(hint in lowered for hint in STRICT_MODE_TRANSIENT_ERROR_HINTS):
            return "runtime_transient_error"
        return "runtime_non_transient_error"

    @staticmethod
    def _is_non_transient_runtime_error_class(error_class: str) -> bool:
        return str(error_class or "") not in {"runtime_transient_error"}

    @staticmethod
    def _is_read_file_path_not_found_error(error_text: str) -> bool:
        lowered = str(error_text or "").lower()
        if not lowered:
            return False
        path_not_found_hints = (
            "enoent",
            "no such file or directory",
            "parent directory does not exist",
            "文件不存在",
            "not a file",
            "不是文件",
        )
        return any(hint in lowered for hint in path_not_found_hints)

    @staticmethod
    def _extract_path_from_error_text(error_text: str) -> Optional[str]:
        text = str(error_text or "").strip()
        if not text:
            return None
        for pattern in (
            re.compile(r"['\"](?P<path>[^'\"]+\.[A-Za-z0-9_+-]+)['\"]"),
            re.compile(r"(?P<path>[A-Za-z0-9_./\\-]+\.[A-Za-z0-9_+-]+)"),
        ):
            match = pattern.search(text)
            if not match:
                continue
            candidate = str(match.group("path") or "").strip().replace("\\", "/")
            if candidate:
                return candidate
        return None

    @staticmethod
    def _get_schema_fields(args_schema: Any) -> Tuple[Set[str], Set[str]]:
        fields: Set[str] = set()
        required_fields: Set[str] = set()
        if not args_schema:
            return fields, required_fields

        model_fields = getattr(args_schema, "model_fields", None)
        if isinstance(model_fields, dict):
            for name, info in model_fields.items():
                fields.add(str(name))
                is_required = False
                checker = getattr(info, "is_required", None)
                if callable(checker):
                    try:
                        is_required = bool(checker())
                    except Exception:
                        is_required = False
                elif isinstance(checker, bool):
                    is_required = checker
                if is_required:
                    required_fields.add(str(name))
            return fields, required_fields

        legacy_fields = getattr(args_schema, "__fields__", None)
        if isinstance(legacy_fields, dict):
            for name, info in legacy_fields.items():
                fields.add(str(name))
                if bool(getattr(info, "required", False)):
                    required_fields.add(str(name))
        return fields, required_fields

    @staticmethod
    def _extract_raw_input_text(
        tool_input: Dict[str, Any],
        repaired_input: Dict[str, Any],
    ) -> str:
        for source in (repaired_input, tool_input):
            if not isinstance(source, dict):
                continue
            for key in ("raw_input", "raw", "input"):
                candidate = source.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
        return ""

    @staticmethod
    def _looks_like_placeholder_key(raw_key: Any) -> bool:
        key = str(raw_key or "").strip().lower()
        if not key:
            return False
        if re.fullmatch(r"(参数|参数名|参数\d*|字段|字段名|key|name|param|params|parameter|value)\d*", key):
            return True
        return key in {"arg", "args", "input", "raw_input", "raw"}

    @staticmethod
    def _looks_like_placeholder_value(raw_value: Any) -> bool:
        value = str(raw_value or "").strip().lower()
        if not value:
            return True
        if re.fullmatch(r"(值|参数值|value|xxx|todo|待补充|待填写|example|示例)\d*", value):
            return True
        if value in {"...", "……", "n/a", "none", "null"}:
            return True
        return False

    @classmethod
    def _is_placeholder_payload(cls, payload: Any) -> bool:
        if not isinstance(payload, dict) or not payload:
            return False
        meaningful_items = [
            (str(key or "").strip(), value)
            for key, value in payload.items()
            if str(key or "").strip() and not str(key).startswith("__")
        ]
        if not meaningful_items:
            return False
        if len(meaningful_items) == 1:
            only_key, only_value = meaningful_items[0]
            return cls._looks_like_placeholder_key(only_key) and cls._looks_like_placeholder_value(only_value)
        return all(
            cls._looks_like_placeholder_key(item_key) and cls._looks_like_placeholder_value(item_value)
            for item_key, item_value in meaningful_items
        )

    @staticmethod
    def _parse_raw_input_payload(raw_input_text: str) -> Dict[str, Any]:
        text = str(raw_input_text or "").strip()
        if not text:
            return {}

        candidates = [text]
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}")
            if end > start:
                candidates.append(text[start : end + 1])

        for candidate in candidates:
            candidate = str(candidate or "").strip()
            if not candidate:
                continue
            for loader in (json.loads, ast.literal_eval):
                try:
                    parsed = loader(candidate)  # type: ignore[arg-type]
                except Exception:
                    continue
                if isinstance(parsed, dict):
                    return dict(parsed)
        return {}

    def _extract_keyword_from_raw_input(self, raw_input_text: str) -> Optional[str]:
        text = str(raw_input_text or "").strip()
        if not text:
            return None

        for key in ("keyword", "pattern", "query"):
            pattern = rf'["\']{re.escape(key)}["\']\s*:\s*["\']([^"\']{{1,220}})["\']'
            for candidate in re.findall(pattern, text):
                normalized = self._normalize_keyword_candidate(candidate)
                if normalized:
                    return normalized

        return self._extract_keyword_hint_from_context([text])

    def _extract_file_hint_from_raw_input(self, raw_input_text: str) -> Dict[str, Any]:
        text = str(raw_input_text or "").strip()
        if not text:
            return {}

        for key in ("file_path", "path", "file", "filepath"):
            pattern = rf'["\']{re.escape(key)}["\']\s*:\s*["\']([^"\']{{1,500}})["\']'
            for candidate in re.findall(pattern, text):
                normalized_path = str(candidate or "").strip().strip("`'\"")
                if not normalized_path:
                    continue
                hint = self._extract_file_hint_from_context([normalized_path])
                if hint:
                    return hint
                if "\n" not in normalized_path:
                    return {"file_path": normalized_path}

        return self._extract_file_hint_from_context([text])

    def _repair_tool_input(
        self,
        tool: Any,
        tool_input: Dict[str, Any],
        resolved_tool_name: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, str], List[str], List[str]]:
        args_schema = getattr(tool, "args_schema", None)
        schema_fields, required_fields = self._get_schema_fields(args_schema)
        if not schema_fields:
            return dict(tool_input), {}, [], []

        repaired = dict(tool_input)
        repaired_changes: Dict[str, str] = {}
        envelope_sources: List[Tuple[str, Dict[str, Any]]] = []
        arguments_payload = tool_input.get("arguments")
        if isinstance(arguments_payload, dict):
            envelope_sources.append(("arguments", arguments_payload))
        finding_payload = tool_input.get("finding")
        if isinstance(finding_payload, dict):
            envelope_sources.append(("finding", finding_payload))
        risk_point_payload = tool_input.get("risk_point")
        if isinstance(risk_point_payload, dict):
            envelope_sources.append(("risk_point", risk_point_payload))
        items_payload = tool_input.get("items")
        if isinstance(items_payload, list):
            first_item = next((item for item in items_payload if isinstance(item, dict)), None)
            if isinstance(first_item, dict):
                envelope_sources.append(("items", first_item))

        for source_name, source_payload in envelope_sources:
            for source_key, source_value in source_payload.items():
                if source_key in repaired:
                    continue
                repaired[source_key] = source_value
                repaired_changes[f"__envelope.{source_name}.{source_key}"] = source_key

        for envelope_key in ("arguments", "finding", "risk_point", "items"):
            if envelope_key in repaired and envelope_key not in schema_fields:
                repaired.pop(envelope_key, None)
                repaired_changes[f"__envelope.{envelope_key}"] = "removed"

        if self._is_placeholder_payload(repaired):
            keys_to_remove = [key for key in list(repaired.keys()) if not str(key).startswith("__")]
            for key in keys_to_remove:
                repaired.pop(key, None)
            repaired_changes["__placeholder_payload"] = "removed"

        for source_key, target_key in TOOL_INPUT_REPAIR_MAP.items():
            if source_key in repaired and target_key not in repaired and target_key in schema_fields:
                repaired[target_key] = repaired[source_key]
                repaired_changes[source_key] = target_key

        raw_input_text = self._extract_raw_input_text(tool_input, repaired)
        raw_input_payload = self._parse_raw_input_payload(raw_input_text)
        if self._is_placeholder_payload(raw_input_payload):
            raw_input_payload = {}
            repaired_changes["__raw_input.placeholder"] = "ignored"

        raw_input_sources: List[Tuple[str, Dict[str, Any]]] = []
        if raw_input_payload:
            raw_input_sources.append(("raw_input", raw_input_payload))
            for nested_key in ("arguments", "finding", "risk_point"):
                nested_payload = raw_input_payload.get(nested_key)
                if isinstance(nested_payload, dict):
                    raw_input_sources.append((f"raw_input.{nested_key}", nested_payload))

        for source_name, source_payload in raw_input_sources:
            for source_key, source_value in source_payload.items():
                if source_key in {"arguments", "finding", "risk_point"}:
                    continue
                if source_key in repaired:
                    continue
                if source_key in schema_fields or source_key in TOOL_INPUT_REPAIR_MAP:
                    repaired[source_key] = source_value
                    repaired_changes[f"__{source_name}.{source_key}"] = source_key

        for source_key, target_key in TOOL_INPUT_REPAIR_MAP.items():
            if source_key in repaired and target_key not in repaired and target_key in schema_fields:
                repaired[target_key] = repaired[source_key]
                repaired_changes[source_key] = target_key

        tool_name = str(getattr(tool, "name", "") or resolved_tool_name or "")
        if tool_name == "pattern_match":
            has_code = bool(str(repaired.get("code") or "").strip())
            scan_file = str(repaired.get("scan_file") or "").strip()
            if not has_code and not scan_file and "scan_file" in schema_fields:
                for source_key in ("file_path", "path", "file", "filepath"):
                    candidate = str(repaired.get(source_key) or "").strip()
                    if candidate and candidate != "unknown":
                        repaired["scan_file"] = candidate
                        repaired_changes[source_key] = "scan_file"
                        break

            if "pattern_types" in repaired and isinstance(repaired.get("pattern_types"), str):
                normalized_pattern_types = [
                    item.strip()
                    for item in re.split(r"[|,;]", str(repaired["pattern_types"]))
                    if item.strip()
                ]
                repaired["pattern_types"] = normalized_pattern_types
                repaired_changes["pattern_types"] = "pattern_types(normalized)"

        if tool_name == "get_symbol_body":
            positional_items: List[Any] = []
            if isinstance(items_payload, list):
                if len(items_payload) == 1 and isinstance(items_payload[0], (list, tuple)):
                    positional_items = list(items_payload[0])
                elif items_payload and all(not isinstance(item, dict) for item in items_payload):
                    positional_items = list(items_payload)

            positional_targets = ("file_path", "symbol_name")
            for index, target_key in enumerate(positional_targets):
                if target_key not in schema_fields:
                    continue
                if repaired.get(target_key) not in (None, "", []):
                    continue
                if index >= len(positional_items):
                    continue
                candidate_value = positional_items[index]
                if candidate_value in (None, "", []):
                    continue
                repaired[target_key] = candidate_value
                repaired_changes[f"__items[{index}]"] = target_key

        context_texts = [text for text in self._recent_thought_texts if isinstance(text, str) and text.strip()]
        if tool_name == "read_file" and "file_path" in schema_fields:
            def _safe_positive_int(value: Any) -> Optional[int]:
                try:
                    parsed = int(value)
                except Exception:
                    return None
                return parsed if parsed > 0 else None

            file_hint: Dict[str, Any] = {}
            file_path = str(repaired.get("file_path") or "").strip()
            if not file_path:
                used_raw_input_hint = False
                file_hint = self._extract_file_hint_from_context(context_texts)
                hinted_path = str(file_hint.get("file_path") or "").strip()
                if not hinted_path and raw_input_text:
                    file_hint = self._extract_file_hint_from_raw_input(raw_input_text)
                    hinted_path = str(file_hint.get("file_path") or "").strip()
                    used_raw_input_hint = bool(hinted_path)
                if hinted_path:
                    repaired["file_path"] = hinted_path
                    source_label = "__raw_input.file_path" if used_raw_input_hint else "__context.file_path"
                    repaired_changes[source_label] = "file_path"
                    if "start_line" in schema_fields and repaired.get("start_line") in (None, "") and file_hint.get("start_line") is not None:
                        repaired["start_line"] = int(file_hint["start_line"])
                        if "end_line" in schema_fields and repaired.get("end_line") in (None, "") and file_hint.get("end_line") is not None:
                            repaired["end_line"] = int(file_hint["end_line"])
                            line_source_label = "__raw_input.line_range" if used_raw_input_hint else "__context.line_range"
                            repaired_changes[line_source_label] = "start_line,end_line"
            else:
                explicit_hint = self._extract_file_hint_from_context([file_path])
                sanitized_path = str(explicit_hint.get("file_path") or "").strip()
                if not sanitized_path:
                    sanitized_path = self._sanitize_file_path_text(file_path)
                if sanitized_path:
                    file_hint = {
                        "file_path": sanitized_path,
                        "start_line": explicit_hint.get("start_line"),
                        "end_line": explicit_hint.get("end_line"),
                    }
                    #  修复：不修改大模型输出的原始路径，只用于提取行号信息
                    # 原来的逻辑：if sanitized_path != file_path: repaired["file_path"] = sanitized_path
                else:
                    file_hint = {"file_path": file_path}

                if "start_line" in schema_fields and repaired.get("start_line") in (None, "") and file_hint.get("start_line") is not None:
                    repaired["start_line"] = int(file_hint["start_line"])
                    repaired_changes.setdefault("__sanitize.line_range", "start_line,end_line")
                if "end_line" in schema_fields and repaired.get("end_line") in (None, "") and file_hint.get("end_line") is not None:
                    repaired["end_line"] = int(file_hint["end_line"])
                    repaired_changes.setdefault("__sanitize.line_range", "start_line,end_line")

            if "reason_paths" in schema_fields and not repaired.get("reason_paths"):
                reason_paths = self._collect_reason_paths_for_read(file_hint)
                if reason_paths:
                    repaired["reason_paths"] = reason_paths
                    repaired_changes["__context.reason_paths"] = "reason_paths"
            if "project_scope" in schema_fields and "project_scope" not in repaired:
                repaired["project_scope"] = True
                repaired_changes["__context.project_scope"] = "project_scope"

            start_value = _safe_positive_int(repaired.get("start_line"))
            end_value = _safe_positive_int(repaired.get("end_line"))
            if start_value is None and end_value is None:
                hint_start = _safe_positive_int(file_hint.get("start_line"))
                hint_end = _safe_positive_int(file_hint.get("end_line"))
                if hint_start is not None:
                    start_value = hint_start
                if hint_end is not None:
                    end_value = hint_end

            if start_value is not None and end_value is None:
                window_start = max(1, start_value - 80)
                window_end = max(start_value, start_value + 119)
                if window_end - window_start + 1 > 200:
                    window_end = window_start + 199
                start_value, end_value = window_start, window_end
                repaired_changes.setdefault("__read_scope.single_line_window", "start_line,end_line")
            elif start_value is not None and end_value is not None and start_value == end_value:
                window_start = max(1, start_value - 80)
                window_end = max(start_value, start_value + 119)
                if window_end - window_start + 1 > 200:
                    window_end = window_start + 199
                start_value, end_value = window_start, window_end
                repaired_changes.setdefault("__read_scope.single_point_expand", "start_line,end_line")
            elif start_value is None and end_value is not None:
                start_value = max(1, end_value - 199)
                repaired_changes.setdefault("__read_scope.infer_start_from_end", "start_line")

            if start_value is not None and end_value is not None and end_value < start_value:
                end_value = start_value
            if start_value is not None and end_value is not None and (end_value - start_value + 1) > 200:
                end_value = start_value + 199
                repaired_changes.setdefault("__read_scope.clamp_span", "end_line")

            if "start_line" in schema_fields and start_value is not None:
                repaired["start_line"] = int(start_value)
            if "end_line" in schema_fields and end_value is not None:
                repaired["end_line"] = int(end_value)

            if "max_lines" in schema_fields:
                max_lines_value = _safe_positive_int(repaired.get("max_lines")) or 200
                if max_lines_value > 200:
                    max_lines_value = 200
                    repaired_changes.setdefault("__read_scope.max_lines_clamped", "max_lines")
                repaired["max_lines"] = int(max_lines_value)

        if tool_name == "controlflow_analysis_light":
            for source_key, target_key in (
                ("path", "file_path"),
                ("entry_point", "entry_points"),
                ("condition_hint", "control_conditions_hint"),
                ("condition_hints", "control_conditions_hint"),
            ):
                if target_key not in schema_fields:
                    continue
                if repaired.get(target_key) not in (None, "", []):
                    continue
                source_value = repaired.get(source_key)
                if source_value in (None, "", []):
                    continue
                repaired[target_key] = source_value
                repaired_changes[source_key] = target_key

            for hint_field in (
                "call_chain_hint",
                "control_conditions_hint",
                "entry_points",
                "entry_points_hint",
            ):
                if hint_field not in schema_fields or hint_field not in repaired:
                    continue
                raw_hint_value = repaired.get(hint_field)
                if isinstance(raw_hint_value, list):
                    continue
                if raw_hint_value in (None, ""):
                    repaired[hint_field] = []
                else:
                    repaired[hint_field] = self._normalize_hint_list(raw_hint_value)
                repaired_changes[f"__normalize.{hint_field}"] = hint_field

            if "line_start" in schema_fields and repaired.get("line_start") in (None, ""):
                line_value = repaired.get("line")
                if line_value in (None, ""):
                    line_value = repaired.get("start_line")
                if line_value not in (None, ""):
                    try:
                        repaired["line_start"] = int(line_value)
                        repaired_changes["line"] = "line_start"
                    except Exception:
                        pass

            if "line_end" in schema_fields and repaired.get("line_end") in (None, ""):
                line_end_value = repaired.get("end_line")
                if line_end_value not in (None, ""):
                    try:
                        repaired["line_end"] = int(line_end_value)
                        repaired_changes["end_line"] = "line_end"
                    except Exception:
                        pass

            file_path_candidate = str(
                repaired.get("file_path")
                or repaired.get("path")
                or ""
            ).strip()
            if file_path_candidate:
                controlflow_hint = self._extract_file_hint_from_context([file_path_candidate])
                normalized_file_path = str(controlflow_hint.get("file_path") or "").strip()
                if not normalized_file_path:
                    normalized_file_path = self._sanitize_file_path_text(file_path_candidate)
                #  修复：不修改大模型输出的原始路径
                # 原来的逻辑：if normalized_file_path and repaired.get("file_path") != normalized_file_path: 
                #           repaired["file_path"] = normalized_file_path
                if "line_start" in schema_fields and repaired.get("line_start") in (None, "") and controlflow_hint.get("start_line") is not None:
                    repaired["line_start"] = int(controlflow_hint["start_line"])
                    repaired_changes["__sanitize.file_path_line"] = "line_start"
                if "line_end" in schema_fields and repaired.get("line_end") in (None, "") and controlflow_hint.get("end_line") is not None:
                    repaired["line_end"] = int(controlflow_hint["end_line"])
                    repaired_changes["__sanitize.file_path_line"] = "line_end"

        if tool_name == "dataflow_analysis":
            for source_key, target_key in (
                ("code", "source_code"),
                ("source", "source_code"),
                ("code_snippet", "source_code"),
                ("sink", "sink_code"),
                ("sink_snippet", "sink_code"),
                ("path", "file_path"),
                ("line", "start_line"),
                ("line_start", "start_line"),
                ("end", "end_line"),
                ("line_end", "end_line"),
                ("source_hint", "source_hints"),
                ("sink_hint", "sink_hints"),
            ):
                if target_key not in schema_fields:
                    continue
                if repaired.get(target_key) not in (None, "", []):
                    continue
                source_value = repaired.get(source_key)
                if source_value in (None, "", []):
                    continue
                repaired[target_key] = source_value
                repaired_changes[source_key] = target_key

            for hint_field in ("source_hints", "sink_hints"):
                if hint_field not in schema_fields or hint_field not in repaired:
                    continue
                raw_hint_value = repaired.get(hint_field)
                if isinstance(raw_hint_value, list):
                    continue
                if raw_hint_value in (None, ""):
                    repaired[hint_field] = []
                else:
                    repaired[hint_field] = self._normalize_hint_list(raw_hint_value)
                repaired_changes[f"__normalize.{hint_field}"] = hint_field

        if tool_name == "search_code" and "keyword" in schema_fields:
            keyword = str(repaired.get("keyword") or "").strip()
            if not keyword:
                hinted_keyword = self._extract_keyword_hint_from_context(context_texts)
                source_label = "__context.keyword"
                if not hinted_keyword and raw_input_text:
                    hinted_keyword = self._extract_keyword_from_raw_input(raw_input_text)
                    source_label = "__raw_input.keyword"
                if hinted_keyword:
                    repaired["keyword"] = hinted_keyword
                    repaired_changes[source_label] = "keyword"
                    if "is_regex" in schema_fields and "is_regex" not in repaired and self._keyword_prefers_regex(hinted_keyword):
                        repaired["is_regex"] = True
                        regex_label = "__context.regex_hint" if source_label == "__context.keyword" else "__raw_input.regex_hint"
                        repaired_changes[regex_label] = "is_regex"

        if tool_name == "push_finding_to_queue":
            normalized_push_payload, push_repair_map = normalize_push_finding_payload(repaired)
            repaired = normalized_push_payload
            repaired_changes.update(push_repair_map)

        if tool_name == "push_risk_point_to_queue":
            def _safe_positive_int(value: Any) -> Optional[int]:
                try:
                    parsed = int(value)
                except Exception:
                    return None
                return parsed if parsed > 0 else None

            file_path = str(repaired.get("file_path") or "").strip()
            file_hint: Dict[str, Any] = {}
            if not file_path:
                file_hint = self._extract_file_hint_from_context(context_texts)
                hinted_path = str(file_hint.get("file_path") or "").strip()
                if not hinted_path and raw_input_text:
                    file_hint = self._extract_file_hint_from_raw_input(raw_input_text)
                    hinted_path = str(file_hint.get("file_path") or "").strip()
                if hinted_path:
                    repaired["file_path"] = hinted_path
                    repaired_changes["__context_or_raw.file_path"] = "file_path"
            #  修复：不清理大模型已经提供的路径
            # 原来的逻辑：else: sanitized_path = self._sanitize_file_path_text(file_path)
            #           if sanitized_path and sanitized_path != file_path: repaired["file_path"] = sanitized_path

            line_start = _safe_positive_int(repaired.get("line_start"))
            if line_start is None:
                for candidate in (
                    repaired.get("line"),
                    repaired.get("start_line"),
                    raw_input_payload.get("line_start") if isinstance(raw_input_payload, dict) else None,
                    raw_input_payload.get("line") if isinstance(raw_input_payload, dict) else None,
                    file_hint.get("start_line") if isinstance(file_hint, dict) else None,
                ):
                    parsed = _safe_positive_int(candidate)
                    if parsed is not None:
                        line_start = parsed
                        repaired_changes["__context_or_raw.line_start"] = "line_start"
                        break
            if line_start is not None:
                repaired["line_start"] = int(line_start)

            description = str(repaired.get("description") or "").strip()
            if self._looks_like_placeholder_value(description):
                description = ""
            if not description:
                description = str(repaired.get("context") or "").strip()
            if self._looks_like_placeholder_value(description):
                description = ""
            if not description:
                description = str(repaired.get("title") or "").strip()
            if self._looks_like_placeholder_value(description):
                description = ""
            if not description and raw_input_text and "{" not in raw_input_text:
                description = str(raw_input_text).strip()
            if not description:
                fallback_path = str(repaired.get("file_path") or "unknown_file").strip()
                fallback_line = int(repaired.get("line_start") or 1)
                description = f"可疑风险点，需进一步验证（{fallback_path}:{fallback_line}）"
            repaired["description"] = description[:500]
            if "description" not in repaired_changes:
                repaired_changes["__auto_fill.description"] = "description"

        missing_required: List[str] = []
        for name in sorted(required_fields):
            value = repaired.get(name, None)
            if value is None or value == "" or value == []:
                missing_required.append(name)

        return repaired, repaired_changes, missing_required, sorted(schema_fields)

    @staticmethod
    def _strict_read_window(line_number: int) -> Tuple[int, int, int]:
        safe_line = max(1, int(line_number))
        start_line = max(1, safe_line - 60)
        end_line = max(safe_line, safe_line + 99)
        if (end_line - start_line + 1) > 200:
            end_line = start_line + 199
        max_lines = end_line - start_line + 1
        return start_line, end_line, max_lines

    def _extract_read_anchor_keyword(
        self,
        repaired_input: Dict[str, Any],
        raw_input_text: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        for field in ("keyword", "pattern", "query"):
            candidate = self._normalize_keyword_candidate(repaired_input.get(field))
            if candidate:
                return candidate, "input"

        if raw_input_text:
            candidate = self._extract_keyword_from_raw_input(raw_input_text)
            if candidate:
                return candidate, "raw_input"

        context_texts = [text for text in self._recent_thought_texts if isinstance(text, str) and text.strip()]
        if context_texts:
            candidate = self._extract_keyword_hint_from_context(context_texts)
            if candidate:
                return candidate, "context"
        return None, None

    @staticmethod
    def _build_include_guard_hint(file_path: str) -> Optional[str]:
        basename = os.path.basename(str(file_path or "").strip())
        stem = os.path.splitext(basename)[0]
        normalized = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
        if not normalized:
            return None
        guard = f"{normalized}_H".upper()
        return guard if len(guard) >= 4 else None

    def _build_read_anchor_candidates(
        self,
        repaired_input: Dict[str, Any],
        raw_input_text: str,
    ) -> List[Tuple[str, str]]:
        candidates: List[Tuple[str, str]] = []
        seen: Set[str] = set()

        def _append(raw_value: Any, source: str) -> None:
            normalized = self._normalize_keyword_candidate(raw_value)
            if not normalized:
                return
            key = normalized.lower()
            if key in seen:
                return
            seen.add(key)
            candidates.append((normalized, source))

        for field in ("keyword", "pattern", "query"):
            _append(repaired_input.get(field), "input")

        if raw_input_text:
            _append(self._extract_keyword_from_raw_input(raw_input_text), "raw_input")

        file_path = str(repaired_input.get("file_path") or repaired_input.get("path") or "").strip()
        if file_path:
            stem = os.path.splitext(os.path.basename(file_path))[0]
            _append(stem, "file_path_stem")
            _append(self._build_include_guard_hint(file_path), "file_path_guard")

        context_texts = [text for text in self._recent_thought_texts if isinstance(text, str) and text.strip()]
        if context_texts:
            _append(self._extract_keyword_hint_from_context(context_texts), "context")

        return candidates

    @staticmethod
    def _coerce_read_line(value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except Exception:
            return None
        if parsed <= 0:
            return None
        return parsed

    def _infer_search_directory_for_read(self, repaired_input: Dict[str, Any]) -> Optional[str]:
        file_path = str(repaired_input.get("file_path") or repaired_input.get("path") or "").strip()
        if file_path and "/" in file_path:
            directory = os.path.dirname(file_path).strip()
            if directory:
                return directory

        reason_paths = repaired_input.get("reason_paths")
        if isinstance(reason_paths, list):
            for item in reason_paths:
                candidate = str(item or "").strip().replace("\\", "/").strip("/")
                if not candidate:
                    continue
                if "." in os.path.basename(candidate):
                    candidate = os.path.dirname(candidate)
                candidate = candidate.strip("/")
                if candidate:
                    return candidate
        return None

    async def _apply_strict_read_scope_policy(
        self,
        *,
        requested_tool_name: str,
        repaired_input: Dict[str, Any],
        repaired_changes: Dict[str, str],
        raw_input_text: str,
        fallback_depth: int,
    ) -> Tuple[Dict[str, Any], Dict[str, str], Optional[str], Dict[str, Any]]:
        policy = self._read_scope_policy()
        if policy != "strict_anchor":
            return repaired_input, repaired_changes, None, {}

        normalized_tool = str(requested_tool_name or "").strip().lower()
        if normalized_tool != "read_file":
            return repaired_input, repaired_changes, None, {}

        output_input = dict(repaired_input)
        output_changes = dict(repaired_changes)
        metadata: Dict[str, Any] = {"read_scope_policy": "strict_anchor"}
        output_input["strict_anchor"] = True

        start_line = self._coerce_read_line(output_input.get("start_line"))
        end_line = self._coerce_read_line(output_input.get("end_line"))

        if start_line is None and end_line is None:
            file_path_hint = str(output_input.get("file_path") or output_input.get("path") or "").strip()
            search_directory = self._infer_search_directory_for_read(output_input)
            file_pattern_hint = ""
            if file_path_hint:
                basename = os.path.basename(file_path_hint).strip()
                if basename:
                    file_pattern_hint = basename
                if not search_directory:
                    directory = os.path.dirname(file_path_hint).strip()
                    if directory:
                        search_directory = directory

            search_candidates = self._build_read_anchor_candidates(output_input, raw_input_text)
            search_candidates = search_candidates[:5]

            located_file: Optional[str] = None
            located_line: Optional[int] = None
            last_search_failure: Optional[str] = None
            if search_candidates:
                for keyword, source in search_candidates:
                    search_payload: Dict[str, Any] = {
                        "keyword": keyword,
                        "max_results": int(output_input.get("max_results") or 8),
                    }
                    if search_directory:
                        search_payload["directory"] = search_directory
                    if file_pattern_hint:
                        search_payload["file_pattern"] = file_pattern_hint

                    metadata["strict_anchor_search_payload"] = dict(search_payload)
                    search_output = await self.execute_tool(
                        "search_code",
                        search_payload,
                        _fallback_depth=fallback_depth + 1,
                    )
                    metadata["strict_anchor_search_hit_count"] = self._estimate_search_hit_count(search_output)
                    if self._looks_like_tool_failure_output(search_output):
                        last_search_failure = (
                            "read_file 严格锚点模式：无法通过 search_code 定位目标代码，请先提供明确 file_path:line。"
                        )
                        continue

                    located_file, located_line = self._extract_location_from_search_output(search_output)
                    if located_line:
                        metadata["read_anchor_keyword_source"] = source
                        break

                if located_line:
                    if located_file and not str(output_input.get("file_path") or "").strip():
                        output_input["file_path"] = located_file
                        output_changes.setdefault("__strict_anchor.search.file_path", "file_path")

                    start_line, end_line, max_lines = self._strict_read_window(located_line)
                    output_input["start_line"] = int(start_line)
                    output_input["end_line"] = int(end_line)
                    output_input["max_lines"] = int(max_lines)
                    output_changes.setdefault("__strict_anchor.search.window", "start_line,end_line,max_lines")
                    metadata["read_anchor_source"] = "search_code"
                    return output_input, output_changes, None, metadata

            if file_path_hint:
                fallback_start, fallback_end, fallback_max = 1, 120, 120
                output_input["start_line"] = fallback_start
                output_input["end_line"] = fallback_end
                output_input["max_lines"] = fallback_max
                output_input["allow_file_header_fallback"] = True
                output_changes.setdefault(
                    "__strict_anchor.file_header_fallback",
                    "start_line,end_line,max_lines,allow_file_header_fallback",
                )
                metadata["read_anchor_source"] = "file_header_fallback"
                metadata.setdefault("strict_anchor_search_hit_count", 0)
                return output_input, output_changes, None, metadata

            if last_search_failure:
                return output_input, output_changes, last_search_failure, metadata

            return (
                output_input,
                output_changes,
                "read_file 严格锚点模式：缺少行号/锚点。请先使用 search_code 定位后再 read_file。",
                metadata,
            )

        if start_line is None and end_line is not None:
            start_line = max(1, int(end_line) - 199)
        if start_line is not None and end_line is None:
            end_line = start_line
        if start_line is None:
            return (
                output_input,
                output_changes,
                "read_file 严格锚点模式：必须提供有效行号。",
                metadata,
            )
        if end_line is None:
            end_line = start_line

        if end_line < start_line:
            end_line = start_line
        if (end_line - start_line + 1) > 200:
            end_line = start_line + 199
            output_changes.setdefault("__strict_anchor.span_clamped", "end_line")

        max_lines = end_line - start_line + 1
        output_input["start_line"] = int(start_line)
        output_input["end_line"] = int(end_line)
        output_input["max_lines"] = int(max_lines)
        output_changes.setdefault("__strict_anchor.window", "start_line,end_line,max_lines")

        anchor_source = "input"
        if "__raw_input.line_range" in output_changes:
            anchor_source = "raw_input"
        elif "__context.line_range" in output_changes:
            anchor_source = "context"
        metadata["read_anchor_source"] = anchor_source
        return output_input, output_changes, None, metadata
    
    async def execute_tool(
        self,
        tool_name: str,
        tool_input: Dict,
        _fallback_depth: int = 0,
    ) -> str:
        """
        统一的工具执行方法 - 支持取消和超时

        Args:
            tool_name: 工具名称
            tool_input: 工具参数

        Returns:
            工具执行结果字符串
        """
        #  在执行工具前检查取消
        if self.is_cancelled:
            return "任务已取消"

        requested_tool_name = str(tool_name or "").strip()
        if requested_tool_name in DOWNLINED_TOOL_MESSAGES and requested_tool_name not in self.tools:
            return f"{DOWNLINED_TOOL_MESSAGES[requested_tool_name]}"
        raw_tool_input = tool_input if isinstance(tool_input, dict) else {}
        raw_input_text = self._extract_raw_input_text(raw_tool_input, raw_tool_input)

        disable_virtual_routing = self._disable_virtual_routing()
        runtime_policy_metadata: Dict[str, Any] = {}

        if str(requested_tool_name).strip().lower() == "verify_reachability":
            return await self._execute_verify_reachability_pipeline(
                raw_tool_input=raw_tool_input,
                fallback_depth=_fallback_depth,
            )

        alias_used: Optional[str] = None
        if disable_virtual_routing:
            resolved_tool_name = requested_tool_name
        else:
            virtual_resolved_name, virtual_alias = self._resolve_virtual_tool_name(
                requested_tool_name,
                raw_tool_input,
            )
            resolved_tool_name, alias_used = self._resolve_tool_name(virtual_resolved_name)
            if virtual_alias:
                alias_used = virtual_alias

        tool = self.tools.get(resolved_tool_name)
        local_tool_available = bool(tool and hasattr(tool, "execute"))

        tool_runtime = self._tool_runtime
        strict_mode = self._is_strict_mode(tool_runtime)
        route_registered = bool(
            tool_runtime
            and hasattr(tool_runtime, "router")
            and getattr(tool_runtime, "router", None)
            and hasattr(getattr(tool_runtime, "router", None), "can_route")
            and getattr(tool_runtime, "router").can_route(resolved_tool_name)
        )
        runtime_can_handle = bool(
            tool_runtime
            and hasattr(tool_runtime, "can_handle")
            and tool_runtime.can_handle(resolved_tool_name)
        )
        strict_local_fallback_allowed = self._allow_local_tool_in_strict_mode(
            runtime=tool_runtime,
            tool_name=resolved_tool_name,
            local_tool_available=local_tool_available,
        )

        normalized_requested_tool = str(requested_tool_name or "").strip().lower()
        alias_blocked = bool(
            disable_virtual_routing
            and normalized_requested_tool in VIRTUAL_TOOL_NAMES
            and not local_tool_available
            and not runtime_can_handle
        )
        if alias_blocked:
            tool_call_id = str(uuid.uuid4())
            blocked_message = (
                "工具名不可用（需标准名）\n\n"
                f"**请求工具**: {requested_tool_name}\n"
                "请改用当前支持的标准工具名（如 search_code、get_code_window、locate_enclosing_function）。"
            )
            await self.emit_tool_call(
                requested_tool_name,
                raw_tool_input,
                tool_call_id=tool_call_id,
                alias_used=None,
            )
            await self.emit_tool_result(
                requested_tool_name,
                blocked_message,
                0,
                tool_call_id=tool_call_id,
                tool_status="failed",
                extra_metadata={
                    **runtime_policy_metadata,
                    "alias_blocked": True,
                },
            )
            return blocked_message

        if not local_tool_available and not runtime_can_handle:
            if requested_tool_name in DOWNLINED_TOOL_MESSAGES:
                return f"{DOWNLINED_TOOL_MESSAGES[requested_tool_name]}"
            return (
                f"错误: 工具 '{requested_tool_name}' 不存在。"
                f"可用工具: {list(self.tools.keys())}"
            )

        if local_tool_available:
            repaired_input, repaired_changes, missing_required, schema_fields = self._repair_tool_input(
                tool,
                raw_tool_input,
                resolved_tool_name=resolved_tool_name,
            )
        else:
            repaired_input = dict(raw_tool_input)
            repaired_changes = {}
            missing_required = []
            schema_fields = []

        auto_retry_once = bool(repaired_input.pop("__auto_retry_once", False))
        auto_repaired_file_path = str(repaired_input.pop("__auto_repaired_file_path", "") or "").strip()
        if auto_retry_once:
            runtime_policy_metadata["auto_retry_once"] = True
        if auto_repaired_file_path:
            runtime_policy_metadata["auto_repaired_file_path"] = auto_repaired_file_path

        if local_tool_available and missing_required:
            missing_required = [
                name
                for name in missing_required
                if repaired_input.get(name) in (None, "", [])
            ]

        repaired_input, write_scope_metadata, write_scope_error = self._enforce_write_scope(
            resolved_tool_name,
            repaired_input,
        )
        route_metadata = self._build_route_metadata(
            tool_name=resolved_tool_name,
            tool_input=repaired_input,
        )
        if route_metadata:
            runtime_policy_metadata = {**runtime_policy_metadata, **route_metadata}
        if runtime_policy_metadata:
            write_scope_metadata = {**runtime_policy_metadata, **write_scope_metadata}
        is_write_tool = self._is_write_tool(resolved_tool_name)

        serialized_input = dump_json_safe(
            repaired_input,
            ensure_ascii=False,
            sort_keys=True,
        )
        tool_call_key = f"{resolved_tool_name}:{serialized_input}"
        call_count = self._tool_repeat_call_counts.get(tool_call_key, 0) + 1
        self._tool_repeat_call_counts[tool_call_key] = call_count

        retry_guard_key = self._build_retry_guard_key(resolved_tool_name, repaired_input)
        if retry_guard_key is None and resolved_tool_name in RETRY_GUARD_TOOLS:
            retry_guard_key = f"{resolved_tool_name}:{serialized_input}"
        deterministic_fail_count = (
            self._deterministic_failure_counts.get(retry_guard_key, 0)
            if retry_guard_key
            else 0
        )

        validation_error: Optional[str] = None
        if missing_required:
            validation_error = (
                f"工具参数缺失，必填字段: {', '.join(missing_required)}。"
                f" schema字段: {', '.join(schema_fields) if schema_fields else '未知'}"
            )

        tool_call_id = str(uuid.uuid4())
        start = None
        try:
            self._tool_calls += 1
            await self.emit_tool_call(
                resolved_tool_name,
                repaired_input,
                tool_call_id=tool_call_id,
                alias_used=alias_used,
                input_repaired=repaired_changes or None,
                validation_error=validation_error,
                extra_metadata=route_metadata or None,
            )

            if write_scope_error:
                await self.emit_tool_result(
                    resolved_tool_name,
                    write_scope_error,
                    0,
                    tool_call_id=tool_call_id,
                    tool_status="failed",
                    alias_used=alias_used,
                    input_repaired=repaired_changes or None,
                    extra_metadata=write_scope_metadata or None,
                )
                failure_output = (
                    "写入策略校验失败\n\n"
                    f"**请求工具**: {requested_tool_name}\n"
                    f"**实际工具**: {resolved_tool_name}\n"
                    f"**原因**: {write_scope_error}\n"
                    "请改用证据绑定的文件并缩小写入范围。"
                )
                return failure_output

            normalized_resolved_tool_name = str(resolved_tool_name or "").strip().lower()
            cached_output = self._tool_success_cache.get(tool_call_key)
            runtime_cache_priority = normalized_resolved_tool_name in {
                "get_code_window",
                "search_code",
            }
            cache_bypass = normalized_resolved_tool_name in NON_CACHEABLE_TOOL_NAMES
            if (
                not is_write_tool
                and not cache_bypass
                and call_count >= 2
                and cached_output is not None
                and not runtime_cache_priority
            ):
                await self.emit_tool_result(
                    resolved_tool_name,
                    cached_output,
                    0,
                    tool_call_id=tool_call_id,
                    tool_status="completed",
                    alias_used=alias_used,
                    input_repaired=repaired_changes or None,
                    cache_hit=True,
                    cache_key=tool_call_key,
                    cache_policy="same_input_success_reuse",
                    extra_metadata=write_scope_metadata or None,
                )
                return cached_output

            if retry_guard_key and deterministic_fail_count >= 2:
                last_error = self._deterministic_failure_last_error.get(retry_guard_key, "")
                short_circuit_msg = (
                    "同一输入已出现至少 2 次确定性失败，系统已短路以避免无效重试。"
                )
                if last_error:
                    short_circuit_msg += f" 最近错误: {last_error}"
                short_circuit_metadata: Dict[str, Any] = {
                    **(write_scope_metadata or {}),
                    "retry_suppressed": True,
                    "deterministic_failure_count": deterministic_fail_count,
                }
                if strict_mode:
                    short_circuit_metadata["runtime_error"] = (
                        str(last_error or "deterministic_short_circuit")
                    )
                    short_circuit_metadata["runtime_error_class"] = self._classify_strict_error(
                        str(last_error or "")
                    )
                await self.emit_tool_result(
                    resolved_tool_name,
                    short_circuit_msg,
                    0,
                    tool_call_id=tool_call_id,
                    tool_status="failed",
                    alias_used=alias_used,
                    input_repaired=repaired_changes or None,
                    extra_metadata=short_circuit_metadata or None,
                )
                return (
                    "工具调用已短路\n\n"
                    f"**请求工具**: {requested_tool_name}\n"
                    f"**实际工具**: {resolved_tool_name}\n"
                    f"**原因**: {short_circuit_msg}\n"
                    "请更换参数或改用其他工具。"
                )

            if validation_error:
                if retry_guard_key:
                    self._deterministic_failure_counts[retry_guard_key] = (
                        self._deterministic_failure_counts.get(retry_guard_key, 0) + 1
                    )
                    self._deterministic_failure_last_error[retry_guard_key] = validation_error
                validation_metadata = {
                    **(write_scope_metadata or {}),
                    "runtime_used": False,
                    "runtime_dispatch_skipped": True,
                    "runtime_dispatch_skip_reason": "validation_error",
                }
                await self.emit_tool_result(
                    resolved_tool_name,
                    validation_error,
                    0,
                    tool_call_id=tool_call_id,
                    tool_status="failed",
                    alias_used=alias_used,
                    input_repaired=repaired_changes or None,
                    validation_error=validation_error,
                    extra_metadata=validation_metadata or None,
                )
                #  为缺失字段生成更详细的示例
                example_dict: Dict[str, Any] = {}
                
                # 特殊处理 save_verification_result 工具
                if str(resolved_tool_name or "").strip().lower() == "save_verification_result":
                    example_dict = {
                        "file_path": "<相对路径，如 src/main.py>",
                        "line_start": "<起始行号，如 10>",
                        "line_end": "<结束行号，如 20>",
                        "function_name": "<函数名，必填>",
                        "title": "<漏洞标题，5-200字符>",
                        "vulnerability_type": "<漏洞类型，如 sql_injection>",
                        "severity": "<critical|high|medium|low|info>",
                        "verdict": "<confirmed|likely|uncertain|false_positive>",
                        "confidence": "<0.0-1.0 浮点数>",
                        "reachability": "<reachable|likely_reachable|unknown|unreachable>",
                        "verification_evidence": "<验证证据，至少10字符>",
                        "cwe_id": "<CWE编号，如 CWE-89，可选>",
                        "suggestion": "<修复建议，可选>",
                    }
                elif str(resolved_tool_name or "").strip().lower() == "update_vulnerability_finding":
                    example_dict = {
                        "finding_identity": "<稳定身份标识，如 fid:...>",
                        "fields_to_update": {
                            "line_start": 123,
                            "function_name": "target_func",
                            "verification_result.localization_status": "success",
                        },
                        "update_reason": "<修正原因，如 Report阶段核对源码后修正定位>",
                    }
                elif local_tool_available and tool:
                    # 尝试从工具的 args_schema 获取字段类型和描述
                    args_schema = getattr(tool, "args_schema", None)
                    model_fields = getattr(args_schema, "model_fields", None)
                    
                    if isinstance(model_fields, dict):
                        # Pydantic v2
                        for field_name in missing_required:
                            field_info = model_fields.get(field_name)
                            if field_info:
                                annotation = getattr(field_info, "annotation", None)
                                description = getattr(field_info, "description", "")
                                
                                # 生成类型提示的示例值
                                type_name = getattr(annotation, "__name__", None) or str(annotation)
                                if "List" in str(annotation) or "list" in type_name.lower():
                                    example_val = "[]"
                                elif "Dict" in str(annotation) or "dict" in type_name.lower():
                                    example_val = "{}"
                                elif "int" in type_name.lower():
                                    example_val = "1"
                                elif "float" in type_name.lower():
                                    example_val = "0.5"
                                elif "bool" in type_name.lower():
                                    example_val = "true"
                                else:
                                    example_val = f"<{type_name}>"
                                
                                # 如果有描述，添加注释
                                if description and len(description) < 80:
                                    example_dict[field_name] = f'{example_val}  # {description[:80]}'
                                else:
                                    example_dict[field_name] = example_val
                            else:
                                example_dict[field_name] = "<value>"
                    else:
                        # Pydantic v1 回退或无 schema
                        legacy_fields = getattr(args_schema, "__fields__", None)
                        if isinstance(legacy_fields, dict):
                            for field_name in missing_required:
                                field_info = legacy_fields.get(field_name)
                                if field_info:
                                    type_name = getattr(field_info.outer_type_, "__name__", "value")
                                    example_dict[field_name] = f"<{type_name}>"
                                else:
                                    example_dict[field_name] = "<value>"
                        else:
                            # 没有 schema，使用简单占位符
                            for field_name in missing_required:
                                example_dict[field_name] = "<value>"
                else:
                    # 无工具对象，使用简单占位符
                    for field_name in missing_required:
                        example_dict[field_name] = "<value>"
                
                # 格式化示例
                if example_dict:
                    example_json = json.dumps(example_dict, ensure_ascii=False, indent=2)
                    example_str = f"\n```json\n{example_json}\n```"
                else:
                    example_fields = ", ".join(f'"{name}": "..."' for name in missing_required)
                    example_str = f"{{{example_fields}}}"
                
                failure_output = (
                    "工具参数校验失败\n\n"
                    f"**请求工具**: {requested_tool_name}\n"
                    f"**实际执行工具**: {resolved_tool_name}\n"
                    f"**缺失必填字段**: {', '.join(missing_required)}\n"
                    f"**建议示例**: {example_str}\n"
                    "请补齐参数后重试。"
                )
                return failure_output

            strict_local_fallback_metadata: Dict[str, Any] = {}
            if strict_mode:
                strict_metadata = {
                    **write_scope_metadata,
                    "runtime_strict_mode": True,
                }

                def _build_strict_failure_metadata(
                    *,
                    strict_error: str,
                    base_metadata: Optional[Dict[str, Any]] = None,
                ) -> Dict[str, Any]:
                    error_class = self._classify_strict_error(strict_error)
                    non_transient = self._is_non_transient_runtime_error_class(error_class)
                    current_count = 0
                    if retry_guard_key and non_transient:
                        self._deterministic_failure_counts[retry_guard_key] = (
                            self._deterministic_failure_counts.get(retry_guard_key, 0) + 1
                        )
                        self._deterministic_failure_last_error[retry_guard_key] = str(strict_error or "")
                        current_count = self._deterministic_failure_counts.get(retry_guard_key, 0)
                    retry_suppressed = bool(
                        non_transient
                        or (retry_guard_key and current_count >= 2)
                    )
                    merged_failure_meta = {
                        **(base_metadata or {}),
                        "runtime_error": str(strict_error or ""),
                        "runtime_error_class": error_class,
                        "retry_suppressed": retry_suppressed,
                    }
                    if retry_guard_key:
                        merged_failure_meta["deterministic_failure_count"] = int(current_count)
                    return merged_failure_meta

                if not tool_runtime:
                    strict_error = "工具运行时未就绪，无法执行工具。"
                    strict_failure_metadata = _build_strict_failure_metadata(
                        strict_error=strict_error,
                        base_metadata=strict_metadata,
                    )
                    await self.emit_tool_result(
                        resolved_tool_name,
                        strict_error,
                        0,
                        tool_call_id=tool_call_id,
                        tool_status="failed",
                        alias_used=alias_used,
                        input_repaired=repaired_changes or None,
                        extra_metadata=strict_failure_metadata or None,
                    )
                    return strict_error

                if not runtime_can_handle:
                    if strict_local_fallback_allowed:
                        strict_local_fallback_metadata = {
                            **strict_metadata,
                            "runtime_local_whitelist_bypass": True,
                            "runtime_route_registered": bool(route_registered),
                            "runtime_local_tool": str(resolved_tool_name or "").strip().lower(),
                        }
                    else:
                        strict_error = (
                            f"标准工具链已匹配工具 {resolved_tool_name}，但当前运行时无可用 adapter，无法执行。"
                            if route_registered
                            else f"标准工具链未匹配工具 {resolved_tool_name}，无法执行。"
                        )
                        strict_failure_metadata = _build_strict_failure_metadata(
                            strict_error=strict_error,
                            base_metadata={
                                **strict_metadata,
                                "runtime_route_registered": bool(route_registered),
                            },
                        )
                        await self.emit_tool_result(
                            resolved_tool_name,
                            strict_error,
                            0,
                            tool_call_id=tool_call_id,
                            tool_status="failed",
                            alias_used=alias_used,
                            input_repaired=repaired_changes or None,
                            extra_metadata=strict_failure_metadata or None,
                        )
                        return strict_error

                if not strict_local_fallback_allowed:
                    runtime_result = await tool_runtime.execute_tool(
                        tool_name=resolved_tool_name,
                        tool_input=repaired_input,
                        agent_name=self.name,
                        alias_used=alias_used,
                    )
                    runtime_result_meta = (
                        dict(runtime_result.metadata)
                        if isinstance(runtime_result.metadata, dict)
                        else {}
                    )
                    runtime_meta = {**strict_metadata, "runtime_used": True}
                    runtime_output = str(runtime_result.data or runtime_result.error or "")

                    if runtime_result.handled and runtime_result.success:
                        await self.emit_tool_result(
                            resolved_tool_name,
                            runtime_output,
                            0,
                            tool_call_id=tool_call_id,
                            tool_status="completed",
                            alias_used=alias_used,
                            input_repaired=repaired_changes or None,
                            evidence_metadata=runtime_result_meta or None,
                            extra_metadata=runtime_meta or None,
                        )
                        if retry_guard_key:
                            self._deterministic_failure_counts.pop(retry_guard_key, None)
                            self._deterministic_failure_last_error.pop(retry_guard_key, None)
                        self._record_tool_context(
                            tool_name=resolved_tool_name,
                            tool_input=repaired_input,
                            tool_metadata=runtime_result_meta,
                        )
                        if not is_write_tool and not cache_bypass:
                            self._tool_success_cache[tool_call_key] = runtime_output
                            if len(self._tool_success_cache) > 500:
                                oldest_key = next(iter(self._tool_success_cache))
                                self._tool_success_cache.pop(oldest_key, None)
                        return runtime_output

                    strict_error = runtime_result.error or "tool_unhandled_in_strict_mode"
                    strict_failure_metadata = _build_strict_failure_metadata(
                        strict_error=strict_error,
                        base_metadata=runtime_meta,
                    )
                    await self.emit_tool_result(
                        resolved_tool_name,
                        runtime_output or strict_error,
                        0,
                        tool_call_id=tool_call_id,
                        tool_status="failed",
                        alias_used=alias_used,
                        input_repaired=repaired_changes or None,
                        evidence_metadata=runtime_result_meta or None,
                        error=strict_error,
                        error_code="strict_mode_failure",
                        extra_metadata=strict_failure_metadata or None,
                    )
                    # 直接返回错误信息给模型，而不是封装成"阻断"消息
                    failure_output = runtime_output or strict_error
                    #  修复：移除自动重试提示，因为不再自动修复路径
                    if strict_failure_metadata.get("auto_suggested_path"):
                        failure_output += f"\n\n提示：在 {strict_failure_metadata['auto_suggested_path']} 找到相似文件，请检查路径是否正确。"
                    return failure_output

            is_runtime_proxy_tool = bool(local_tool_available and getattr(tool, "runtime_proxy_only", False))
            if is_runtime_proxy_tool and not runtime_can_handle:
                fallback_hit = await self._execute_soft_fallback(
                    tool_name=resolved_tool_name,
                    tool_input=repaired_input,
                    tool_obj=tool,
                    fallback_depth=_fallback_depth,
                )
                if fallback_hit:
                    fallback_tool_name, fallback_output, fallback_evidence_metadata = fallback_hit
                    proxy_metadata = {
                        **write_scope_metadata,
                        "runtime_soft_fallback": True,
                        "runtime_soft_fallback_target": fallback_tool_name,
                        "skill_not_ready": True,
                        "runtime_used": True,
                    }
                    await self.emit_tool_result(
                        resolved_tool_name,
                        fallback_output,
                        0,
                        tool_call_id=tool_call_id,
                        tool_status="completed",
                        alias_used=alias_used,
                        input_repaired=repaired_changes or None,
                        evidence_metadata=fallback_evidence_metadata,
                        extra_metadata=proxy_metadata,
                    )
                    if not is_write_tool and not cache_bypass:
                        self._tool_success_cache[tool_call_key] = fallback_output
                        if len(self._tool_success_cache) > 500:
                            oldest_key = next(iter(self._tool_success_cache))
                            self._tool_success_cache.pop(oldest_key, None)
                    return fallback_output

                not_ready_message = f"skill_not_ready:{resolved_tool_name}"
                await self.emit_tool_result(
                    resolved_tool_name,
                    not_ready_message,
                    0,
                    tool_call_id=tool_call_id,
                    tool_status="failed",
                    alias_used=alias_used,
                    input_repaired=repaired_changes or None,
                    extra_metadata={
                        **write_scope_metadata,
                        "skill_not_ready": True,
                    }
                    or None,
                )
                return (
                    "工具不可用\n\n"
                    f"**请求工具**: {requested_tool_name}\n"
                    f"**实际工具**: {resolved_tool_name}\n"
                    "工具运行时未就绪，且未命中本地回退。"
                )

            use_runtime_first = bool(
                runtime_can_handle
                and tool_runtime
                and (
                    not local_tool_available
                    or (
                        hasattr(tool_runtime, "should_prefer_runtime")
                        and tool_runtime.should_prefer_runtime()
                    )
                )
            )
            runtime_fallback_metadata: Dict[str, Any] = dict(strict_local_fallback_metadata)
            if use_runtime_first and tool_runtime:
                runtime_result = await tool_runtime.execute_tool(
                    tool_name=resolved_tool_name,
                    tool_input=repaired_input,
                    agent_name=self.name,
                    alias_used=alias_used,
                )
                runtime_result_meta = (
                    dict(runtime_result.metadata)
                    if isinstance(runtime_result.metadata, dict)
                    else {}
                )
                runtime_meta = {**write_scope_metadata, "runtime_used": True}

                if runtime_result.handled:
                    runtime_output = str(runtime_result.data or runtime_result.error or "")
                    if runtime_result.success:
                        await self.emit_tool_result(
                            resolved_tool_name,
                            runtime_output,
                            0,
                            tool_call_id=tool_call_id,
                            tool_status="completed",
                            alias_used=alias_used,
                            input_repaired=repaired_changes or None,
                            evidence_metadata=runtime_result_meta or None,
                            extra_metadata=runtime_meta or None,
                        )
                        self._record_tool_context(
                            tool_name=resolved_tool_name,
                            tool_input=repaired_input,
                            tool_metadata=runtime_result_meta,
                        )
                        
                        #  工具运行时成功执行后追踪关键工具调用
                        critical_tools = {"push_finding_to_queue", "save_verification_result", "update_vulnerability_finding"}
                        if resolved_tool_name in critical_tools:
                            self._critical_tool_called = True
                            self._critical_tool_name = resolved_tool_name
                            self._critical_tool_calls.append({
                                "tool_name": resolved_tool_name,
                                "tool_input": repaired_input,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "success": True,
                                "via": "runtime",
                            })
                            logger.info(f"[{self.name}] 关键工具成功执行 (runtime): {resolved_tool_name}")
                        
                        if not is_write_tool and not cache_bypass:
                            self._tool_success_cache[tool_call_key] = runtime_output
                            if len(self._tool_success_cache) > 500:
                                oldest_key = next(iter(self._tool_success_cache))
                                self._tool_success_cache.pop(oldest_key, None)
                        return runtime_output

                    fallback_hit = await self._execute_soft_fallback(
                        tool_name=resolved_tool_name,
                        tool_input=repaired_input,
                        tool_obj=tool if local_tool_available else None,
                        fallback_depth=_fallback_depth,
                    )
                    if fallback_hit and runtime_result.should_fallback:
                        fallback_tool_name, fallback_output, fallback_evidence_metadata = fallback_hit
                        merged_fallback_metadata = {
                            **runtime_meta,
                            "runtime_fallback_used": True,
                            "runtime_fallback_error": runtime_result.error or "unknown",
                            "runtime_fallback_from": runtime_result_meta.get("runtime_domain"),
                            "runtime_soft_fallback": True,
                            "runtime_soft_fallback_target": fallback_tool_name,
                        }
                        await self.emit_tool_result(
                            resolved_tool_name,
                            fallback_output,
                            0,
                            tool_call_id=tool_call_id,
                            tool_status="completed",
                            alias_used=alias_used,
                            input_repaired=repaired_changes or None,
                            evidence_metadata=fallback_evidence_metadata,
                            extra_metadata=merged_fallback_metadata or None,
                        )
                        
                        #  工具运行时 fallback 成功执行后追踪关键工具调用
                        critical_tools = {"push_finding_to_queue", "save_verification_result", "update_vulnerability_finding"}
                        if resolved_tool_name in critical_tools:
                            self._critical_tool_called = True
                            self._critical_tool_name = resolved_tool_name
                            self._critical_tool_calls.append({
                                "tool_name": resolved_tool_name,
                                "tool_input": repaired_input,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "success": True,
                                "via": "runtime_fallback",
                            })
                            logger.info(f"[{self.name}] 关键工具成功执行 (runtime fallback): {resolved_tool_name}")
                        
                        if not is_write_tool and not cache_bypass:
                            self._tool_success_cache[tool_call_key] = fallback_output
                            if len(self._tool_success_cache) > 500:
                                oldest_key = next(iter(self._tool_success_cache))
                                self._tool_success_cache.pop(oldest_key, None)
                        return fallback_output

                    if runtime_result.should_fallback and local_tool_available:
                        runtime_fallback_metadata = {
                            **runtime_meta,
                            "runtime_fallback_used": True,
                            "runtime_fallback_error": runtime_result.error or "unknown",
                            "runtime_fallback_from": runtime_result_meta.get("runtime_domain"),
                        }
                    elif not runtime_result.should_fallback:
                        await self.emit_tool_result(
                            resolved_tool_name,
                            runtime_output,
                            0,
                            tool_call_id=tool_call_id,
                            tool_status="failed",
                            alias_used=alias_used,
                            input_repaired=repaired_changes or None,
                            evidence_metadata=runtime_result_meta or None,
                            error=runtime_result.error or "unknown",
                            error_code="runtime_execution_failed",
                            extra_metadata=runtime_meta or None,
                        )
                        failure_output = (
                            "工具运行时执行失败\n\n"
                            f"**请求工具**: {requested_tool_name}\n"
                            f"**实际工具**: {resolved_tool_name}\n"
                            f"**错误**: {runtime_result.error or 'unknown'}\n"
                            "请调整参数后重试。"
                        )
                        return failure_output

                    elif not local_tool_available:
                        await self.emit_tool_result(
                            resolved_tool_name,
                            runtime_output,
                            0,
                            tool_call_id=tool_call_id,
                            tool_status="failed",
                            alias_used=alias_used,
                            input_repaired=repaired_changes or None,
                            evidence_metadata=runtime_result_meta or None,
                            error=runtime_result.error or "unknown",
                            error_code="runtime_no_local_fallback",
                            extra_metadata=runtime_meta or None,
                        )
                        failure_output = (
                            "工具运行时执行失败且无本地回退\n\n"
                            f"**请求工具**: {requested_tool_name}\n"
                            f"**实际工具**: {resolved_tool_name}\n"
                            f"**错误**: {runtime_result.error or 'unknown'}"
                        )
                        return failure_output

            if not local_tool_available:
                return (
                    "工具不可用\n\n"
                    f"**请求工具**: {requested_tool_name}\n"
                    f"**实际工具**: {resolved_tool_name}\n"
                    "标准工具链未处理且本地工具不可用。"
                )

            import time
            start = time.time()

            #  根据工具类型设置不同的超时时间
            timeout = self._resolve_tool_timeout(resolved_tool_name)

            #  使用 asyncio.wait_for 添加超时控制，同时支持取消
            async def execute_with_cancel_check():
                """包装工具执行，定期检查取消状态"""
                if hasattr(tool, "set_runtime_context"):
                    try:
                        tool.set_runtime_context(
                            requested_tool_name=requested_tool_name,
                            phase=str(getattr(self.config.agent_type, "value", "") or ""),
                            agent_type=str(getattr(self.config.agent_type, "value", "") or ""),
                            caller=self.name,
                            attempt=int(_fallback_depth or 0) + 1,
                            trace_id=tool_call_id,
                            runtime_policy={
                                "route_metadata": dict(route_metadata or {}),
                                "write_scope_metadata": dict(write_scope_metadata or {}),
                            },
                        )
                    except Exception:
                        pass
                # 创建工具执行任务
                execute_task = asyncio.create_task(tool.execute(**repaired_input))

                try:
                    # 使用循环定期检查取消状态
                    while not execute_task.done():
                        if self.is_cancelled:
                            execute_task.cancel()
                            try:
                                await execute_task
                            except asyncio.CancelledError:
                                pass
                            raise asyncio.CancelledError("任务已取消")

                        # 等待任务完成或超时检查间隔
                        try:
                            return await asyncio.wait_for(
                                asyncio.shield(execute_task),
                                timeout=0.5  # 每0.5秒检查一次取消状态
                            )
                        except asyncio.TimeoutError:
                            continue  # 继续循环检查

                    return await execute_task
                except asyncio.CancelledError:
                    if not execute_task.done():
                        execute_task.cancel()
                    raise
                finally:
                    if hasattr(tool, "clear_runtime_context"):
                        try:
                            tool.clear_runtime_context()
                        except Exception:
                            pass

            try:
                result = await asyncio.wait_for(
                    execute_with_cancel_check(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                duration_ms = int((time.time() - start) * 1000)
                await self.emit_tool_result(
                    resolved_tool_name,
                    f"超时 ({timeout}s)",
                    duration_ms,
                    tool_call_id=tool_call_id,
                    tool_status="failed",
                    alias_used=alias_used,
                    input_repaired=repaired_changes or None,
                    error=f"超时 ({timeout}s)",
                    error_code="timeout",
                    extra_metadata=(
                        {**write_scope_metadata, **runtime_fallback_metadata}
                        if (write_scope_metadata or runtime_fallback_metadata)
                        else None
                    ),
                )
                failure_output = (
                    f"工具 '{resolved_tool_name}' 执行超时 ({timeout}秒)，"
                    "请尝试其他方法或减小操作范围。"
                )
                return failure_output
            except asyncio.CancelledError:
                duration_ms = int((time.time() - start) * 1000)
                await self.emit_tool_result(
                    resolved_tool_name,
                    "已取消",
                    duration_ms,
                    tool_call_id=tool_call_id,
                    tool_status="cancelled",
                    alias_used=alias_used,
                    input_repaired=repaired_changes or None,
                    error="已取消",
                    error_code="cancelled",
                    extra_metadata=(
                        {**write_scope_metadata, **runtime_fallback_metadata}
                        if (write_scope_metadata or runtime_fallback_metadata)
                        else None
                    ),
                )
                return "任务已取消"

            duration_ms = int((time.time() - start) * 1000)
            #  修复：确保传递有意义的结果字符串，避免 "None"
            result_preview = str(result.data) if result.data is not None else (result.error if result.error else "")
            result_metadata = dict(result.metadata) if isinstance(result.metadata, dict) else {}
            await self.emit_tool_result(
                resolved_tool_name,
                result_preview,
                duration_ms,
                tool_call_id=tool_call_id,
                tool_status="completed" if result.success else "failed",
                alias_used=alias_used,
                input_repaired=repaired_changes or None,
                evidence_metadata=result_metadata or None,
                error=str(result.error or "") or None,
                error_code=str(getattr(result, "error_code", "") or "") or None,
                extra_metadata=(
                    {**write_scope_metadata, **runtime_fallback_metadata}
                    if (write_scope_metadata or runtime_fallback_metadata)
                    else None
                    ),
            )

            if retry_guard_key:
                if result.success:
                    self._deterministic_failure_counts.pop(retry_guard_key, None)
                    self._deterministic_failure_last_error.pop(retry_guard_key, None)
                elif self._is_deterministic_error_message(str(result.error or "")):
                    self._deterministic_failure_counts[retry_guard_key] = (
                        self._deterministic_failure_counts.get(retry_guard_key, 0) + 1
                    )
                    self._deterministic_failure_last_error[retry_guard_key] = str(result.error or "")

            #  工具执行后再次检查取消
            if self.is_cancelled:
                return "任务已取消"

            if result.success:
                metadata_dict = dict(result.metadata) if isinstance(result.metadata, dict) else {}
                self._last_successful_tool_context = {
                    "tool_name": resolved_tool_name,
                    "tool_input": dict(repaired_input),
                    "tool_metadata": dict(metadata_dict),
                }
                self._record_tool_context(
                    tool_name=resolved_tool_name,
                    tool_input=repaired_input,
                    tool_metadata=metadata_dict,
                )
                
                #  仅在工具成功执行后才追踪关键工具调用（push/save）
                critical_tools = {"push_finding_to_queue", "save_verification_result", "update_vulnerability_finding"}
                if resolved_tool_name in critical_tools:
                    self._critical_tool_called = True
                    self._critical_tool_name = resolved_tool_name
                    self._critical_tool_calls.append({
                        "tool_name": resolved_tool_name,
                        "tool_input": repaired_input,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "success": True,
                    })
                    logger.info(f"[{self.name}] 关键工具成功执行: {resolved_tool_name}")
                
                if hasattr(result, "to_string") and callable(getattr(result, "to_string")):
                    output = result.to_string(max_length=MAX_EVENT_PAYLOAD_CHARS)
                else:
                    output = str(result.data)

                # 包含 metadata 中的额外信息
                if result.metadata:
                    if "issues" in result.metadata:
                        output += f"\n\n发现的问题:\n{json.dumps(result.metadata['issues'], ensure_ascii=False, indent=2)}"
                    if "findings" in result.metadata:
                        output += f"\n\n发现:\n{json.dumps(result.metadata['findings'][:10], ensure_ascii=False, indent=2)}"

                # 超大输出保护（保持完整性优先）
                if len(output) > MAX_EVENT_PAYLOAD_CHARS:
                    output = (
                        output[:MAX_EVENT_PAYLOAD_CHARS]
                        + f"\n\n... [输出已截断，共 {len(str(result.data))} 字符]"
                    )
                if not is_write_tool and not cache_bypass:
                    self._tool_success_cache[tool_call_key] = output
                    if len(self._tool_success_cache) > 500:
                        oldest_key = next(iter(self._tool_success_cache))
                        self._tool_success_cache.pop(oldest_key, None)
                return output
            else:
                reflection = (
                    dict(result.metadata.get("reflection"))
                    if isinstance(result.metadata, dict) and isinstance(result.metadata.get("reflection"), dict)
                    else {}
                )
                if reflection:
                    try:
                        await self.emit_thinking(
                            "工具失败反思: "
                            f"{reflection.get('failure_class') or 'tool_execution_failure'} / "
                            f"{reflection.get('stop_reason') or result.error_code or 'unknown'}"
                        )
                    except Exception:
                        pass
                #  输出详细的错误信息，包括原始错误和完整输出
                guard_hint = ""
                if retry_guard_key and self._deterministic_failure_counts.get(retry_guard_key, 0) >= 2:
                    guard_hint = (
                        "\n\n同一输入已连续出现确定性失败。"
                        "后续相同输入将被系统短路，请修改参数或改用其他工具。"
                    )
                
                # 构建错误消息，优先显示完整的 data（包含格式化的输出）
                error_details = []
                if result.data:
                    # data 字段通常包含格式化的完整输出（stdout + stderr）
                    error_details.append(str(result.data))
                
                # 如果 error 字段有额外信息且不在 data 中，也添加
                if result.error and (not result.data or str(result.error) not in str(result.data)):
                    error_details.append(f"\n**错误详情**: {result.error}")
                
                error_output = "\n".join(error_details) if error_details else "未知错误"
                
                error_msg = f"""工具执行失败

**请求工具**: {requested_tool_name}
**实际工具**: {resolved_tool_name}

{error_output}

请根据错误信息调整参数或尝试其他方法。{guard_hint}"""
                return error_msg

        except asyncio.CancelledError:
            logger.info(f"[{self.name}] Tool '{resolved_tool_name}' execution cancelled")
            return "任务已取消"
        except Exception as e:
            import traceback
            logger.error(f"Tool execution error: {e}")
            if start is not None:
                duration_ms = int((time.time() - start) * 1000)
                await self.emit_tool_result(
                    resolved_tool_name,
                    f"异常: {type(e).__name__}: {str(e)}",
                    duration_ms,
                    tool_call_id=tool_call_id,
                    tool_status="failed",
                    alias_used=alias_used,
                    input_repaired=repaired_changes or None,
                    error=str(e),
                    error_code=type(e).__name__,
                    extra_metadata=(
                        {**write_scope_metadata, **runtime_fallback_metadata}
                        if (write_scope_metadata or runtime_fallback_metadata)
                        else None
                    ),
                )
            #  输出完整的原始错误信息，包括堆栈跟踪
            error_msg = f"""工具执行异常

**请求工具**: {requested_tool_name}
**实际工具**: {resolved_tool_name}
**参数**: {dump_json_safe(repaired_input, ensure_ascii=False, indent=2) if repaired_input else '无'}
**错误类型**: {type(e).__name__}
**错误信息**: {str(e)}
**堆栈跟踪**:
```
{traceback.format_exc()}
```

请分析错误原因，可能需要：
1. 检查参数格式是否正确
2. 尝试使用其他工具
3. 如果是权限或资源问题，跳过该操作"""
            return error_msg
    
    def get_tools_description(self) -> str:
        """生成工具描述文本（用于 prompt）"""
        tools_info = []
        for name, tool in self.tools.items():
            if name.startswith("_"):
                continue
            desc = f"- {name}: {getattr(tool, 'description', 'No description')}"
            tools_info.append(desc)
        return "\n".join(tools_info)
    
    async def _fallback_check_and_save(
        self,
        conversation_history: List[Dict[str, str]],
        expected_tool: str,
        agent_type: str,
    ) -> Optional[Dict[str, Any]]:
        """
        兜底机制：使用 LLM 分析对话记录，判断是否需要补救性保存
        
        Args:
            conversation_history: 对话记录
            expected_tool: 预期的工具名称 (push_finding_to_queue | save_verification_result)
            agent_type: Agent 类型 (analysis | verification)
        
        Returns:
            如果补救成功返回结果，否则返回 None
        """
        if self._critical_tool_called:
            logger.info(f"[{self.name}] 已调用关键工具 {self._critical_tool_name}，无需兜底")
            return None
        
        logger.warning(f"[{self.name}] 未检测到 {expected_tool} 成功调用，启动兜底分析...")
        
        # 根据 agent_type 构建不同的输出格式示例
        if agent_type == "analysis":
            output_example = """{{
    "needs_fallback": true,
    "reason": "发现2个XSS漏洞但未成功调用push_finding_to_queue",
    "findings": [
        {{
            "file_path": "vulnerability/xss/xss.go",
            "line_start": 31,
            "line_end": 35,
            "vulnerability_type": "xss",
            "title": "漏洞标题",
            "description": "详细描述...",
            "severity": "high",
            "confidence": 0.85,
            "code_snippet": "相关代码",
            "suggestion": "修复建议"
        }}
    ]
}}"""
            negative_example = """{{
    "needs_fallback": false,
    "reason": "对话中未发现任何结构化的漏洞数据",
    "findings": []
}}"""
        else:  # verification
            output_example = """{{
    "needs_fallback": true,
    "reason": "完成1个漏洞验证但未成功调用save_verification_result",
    "verification_results": {{
        "findings": [
            {{
                "file_path": "src/auth.py",
                "line_start": 42,
                "line_end": 45,
                "title": "漏洞标题",
                "cwe_id": "CWE-89",
                "suggestion": "修复建议",
                "verification_result": {{
                    "verdict": "confirmed",
                    "confidence": 0.9,
                    "reachability": "reachable",
                    "verification_evidence": "验证证据"
                }}
            }}
        ],
        "summary": "验证摘要"
    }}
}}"""
            negative_example = """{{
    "needs_fallback": false,
    "reason": "对话中未发现任何验证结果数据",
    "verification_results": {{
        "findings": []
    }}
}}"""
        
        # 构建分析提示词
        analysis_prompt = f"""你是一个严格的对话分析助手。请分析以下对话记录，判断 {agent_type} Agent 是否发现了需要保存的结果但未成功调用 `{expected_tool}` 工具。

## 对话记录（最后 20 轮）
{self._format_conversation_for_analysis(conversation_history[-20:])}

## 分析方法

### 第一步：检查对话中是否存在有效的结果数据

**对于 Analysis Agent**：
查找对话中是否包含**结构化的漏洞发现数据**，关键特征：
- 包含 `file_path` 或 `"file_path":` 字样
- 包含 `vulnerability_type` 或 `漏洞类型` 关键词（如 sql_injection, xss, command_injection 等）
- 包含 `line_start` 或行号信息
- 包含漏洞描述（`description`）
- 通常出现在 assistant 的最后几条消息中，或者以 JSON/对象形式呈现

**重要**：即使对话中有"占位分析"、"进行中"等字样，只要存在上述结构化数据（file_path + vulnerability_type + description），就应该认为发现了漏洞。

**对于 Verification Agent**：
查找对话中是否包含**验证结果数据**，关键特征：
- 包含 `verdict` 字段（confirmed/likely/false_positive/uncertain）
- 包含 `verification_result` 或 `verification_evidence` 或 `verification_details`
- 包含 `confidence` 评分（通常是 0.0-1.0 的浮点数）
- 包含 `reachability` 字段（reachable/unreachable/unknown）
- 包含最终的判定结论或验证证据描述
- 通常出现在 assistant 的最后几条消息中，或以包含 findings 数组的 JSON 形式呈现

**重要**：只要对话中出现了包含上述字段的结构化验证数据，就应该认为完成了验证。

### 第二步：检查是否成功调用了保存工具

查找对话中是否有以下模式之一：
- `Action: {expected_tool}` 后面紧跟 `Observation: ` 或 `成功` 或 `已入队` 或 `已保存`
- `Action: {expected_tool}` 后面的 Observation 没有包含错误信息（如"失败"、"错误"、"Error"）

**如果只看到 `Action: {expected_tool}` 但 Observation 显示失败，则视为未成功调用。**

### 第三步：综合判断

- 如果**存在有效结果数据** 且 **未成功调用保存工具**，则 `needs_fallback = true`
- 否则 `needs_fallback = false`

## 输出格式

请严格按照以下 JSON 格式输出，**不要有任何额外文本，不要使用 markdown 代码块标记**：

**正例（需要兜底）：**
{output_example}

**反例（不需要兜底）：**
{negative_example}

## 示例场景

### 需要兜底的情况（{agent_type}）
```
assistant: {"分析发现以下漏洞：" if agent_type == "analysis" else "验证完成，结果："}
{{"findings": [{{"file_path": "src/auth.py", "vulnerability_type": "sql_injection"}}]}}
```
→ `needs_fallback = true`（有数据但未调用工具）

### 不需要兜底的情况
```
assistant: 正在分析代码...
assistant: 继续深入查看...
```
→ `needs_fallback = false`（无结构化数据）

### 不需要兜底的情况（已成功调用）
```
assistant: Action: {expected_tool}
user: Observation: {"漏洞已成功入队" if agent_type == "analysis" else "验证结果已保存"}
```
→ `needs_fallback = false`（已成功调用工具）

### 需要兜底的情况（调用失败）
```
assistant: Action: {expected_tool}
user: Observation: 数据库连接失败
```
→ `needs_fallback = true`（调用失败，需要补救）

**请现在开始分析，严格输出 JSON 格式，不要有任何额外文本。**
"""
        
        try:
            # 调用 LLM 分析
            analysis_history = [
                {"role": "system", "content": "你是一个严格的对话分析助手，专门判断是否需要补救性工具调用。"},
                {"role": "user", "content": analysis_prompt}
            ]
            
            logger.info(f"[{self.name}] 正在调用 LLM 进行兜底分析...")
            llm_response, tokens = await self.stream_llm_call(
                analysis_history,
                # 使用较低的 temperature 确保一致性
            )
            
            if not llm_response or not llm_response.strip():
                logger.warning(f"[{self.name}] LLM 兜底分析返回空响应")
                return None
            
            # 解析 LLM 响应
            analysis_result = self._parse_fallback_analysis(llm_response)
            
            if not analysis_result or not analysis_result.get("needs_fallback"):
                logger.info(f"[{self.name}] LLM 判断不需要兜底: {analysis_result.get('reason', '未提供理由')}")
                return None
            
            logger.warning(f"[{self.name}] LLM 判断需要兜底保存: {analysis_result.get('reason')}")
            
            # 执行补救操作
            fallback_result = await self._execute_fallback_save(
                analysis_result,
                expected_tool,
                agent_type,
            )
            
            return fallback_result
            
        except Exception as e:
            logger.error(f"[{self.name}] 兜底分析失败: {e}", exc_info=True)
            return None
    
    def _format_conversation_for_analysis(self, conversation: List[Dict[str, str]]) -> str:
        """格式化对话记录用于分析"""
        formatted = []
        for i, msg in enumerate(conversation):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            # 截断过长的内容
            if len(content) > 2000:
                content = content[:2000] + "\n... [内容已截断]"
            
            formatted.append(f"### 轮次 {i + 1} - {role.upper()}\n{content}\n")
        
        return "\n".join(formatted)
    
    def _parse_fallback_analysis(self, llm_response: str) -> Optional[Dict[str, Any]]:
        """解析 LLM 的兜底分析结果"""
        try:
            # 移除可能的 markdown 代码块标记
            cleaned = llm_response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            # 解析 JSON
            result = json.loads(cleaned)
            
            if not isinstance(result, dict):
                logger.warning(f"[{self.name}] 兜底分析结果不是字典: {type(result)}")
                return None
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"[{self.name}] 无法解析兜底分析 JSON: {e}")
            logger.debug(f"原始响应: {llm_response[:500]}")
            return None
        except Exception as e:
            logger.error(f"[{self.name}] 解析兜底分析失败: {e}")
            return None
    
    async def _execute_fallback_save(
        self,
        analysis_result: Dict[str, Any],
        expected_tool: str,
        agent_type: str,
    ) -> Optional[Dict[str, Any]]:
        """执行补救性保存操作"""
        try:
            if agent_type == "analysis" and expected_tool == "push_finding_to_queue":
                # Analysis Agent: 逐个推送 findings
                findings = analysis_result.get("findings", [])
                if not findings:
                    logger.warning(f"[{self.name}] 兜底分析未提取到 findings")
                    return None
                
                logger.info(f"[{self.name}] 开始补救推送 {len(findings)} 个 findings")
                await self.emit_event(
                    "info",
                    f"兜底机制启动：开始补救推送 {len(findings)} 个漏洞到队列",
                    metadata={"agent_type": agent_type, "total_findings": len(findings)},
                )
                pushed_count = 0
                
                for finding in findings:
                    try:
                        result = await self.execute_tool("push_finding_to_queue", finding)
                        if "成功" in result or "已入队" in result:
                            pushed_count += 1
                            logger.info(f"[{self.name}] 补救推送成功: {finding.get('title', 'N/A')}")
                    except Exception as e:
                        logger.error(f"[{self.name}] 补救推送失败: {e}")
                
                await self.emit_event(
                    "success" if pushed_count > 0 else "warning",
                    f"兜底机制完成：成功补救推送 {pushed_count}/{len(findings)} 个漏洞",
                    metadata={
                        "agent_type": agent_type,
                        "tool": expected_tool,
                        "pushed_count": pushed_count,
                        "total_findings": len(findings),
                        "success_rate": f"{pushed_count}/{len(findings)}",
                    },
                )
                
                return {
                    "fallback_executed": True,
                    "tool": expected_tool,
                    "pushed_count": pushed_count,
                    "total_findings": len(findings),
                }
            
            elif agent_type == "verification" and expected_tool == "save_verification_result":
                # Verification Agent: 保存验证结果（逐个保存）
                verification_results = analysis_result.get("verification_results", {})
                findings = verification_results.get("findings", [])
                if not findings:
                    logger.warning(f"[{self.name}] 兜底分析未提取到 verification findings")
                    return None
                
                logger.info(f"[{self.name}] 开始补救保存验证结果（共 {len(findings)} 条）")
                await self.emit_event(
                    "info",
                    f"兜底机制启动：开始补救保存 {len(findings)} 个验证结果",
                    metadata={"agent_type": agent_type, "total_findings": len(findings)},
                )
                
                saved_count = 0
                for idx, finding in enumerate(findings):
                    try:
                        # 构造单个 finding 的参数（flat 格式，与 _execute 签名一致）
                        vr = finding.get("verification_result", {})
                        if not isinstance(vr, dict):
                            vr = {}
                        params = {
                            "file_path": finding.get("file_path"),
                            "line_start": finding.get("line_start"),
                            "line_end": finding.get("line_end"),
                            "function_name": finding.get("function_name"),
                            "title": finding.get("title"),
                            "vulnerability_type": finding.get("vulnerability_type"),
                            "severity": finding.get("severity"),
                            "description": finding.get("description"),
                            "source": finding.get("source"),
                            "sink": finding.get("sink"),
                            "dataflow_path": finding.get("dataflow_path"),
                            "status": vr.get("status") or finding.get("status"),
                            "is_verified": finding.get("is_verified"),
                            "poc_code": finding.get("poc_code"),
                            "cvss_score": finding.get("cvss_score"),
                            "cvss_vector": finding.get("cvss_vector"),
                            "code_snippet": vr.get("code_snippet") or finding.get("code_snippet"),
                            "code_context": vr.get("code_context") or finding.get("code_context"),
                            "report": finding.get("report") or finding.get("vulnerability_report"),
                            "verdict": vr.get("verdict") or finding.get("verdict"),
                            "confidence": vr.get("confidence") or finding.get("confidence"),
                            "reachability": vr.get("reachability") or finding.get("reachability"),
                            "verification_evidence": vr.get("verification_evidence") or finding.get("verification_evidence"),
                            "cwe_id": finding.get("cwe_id"),
                            "suggestion": finding.get("suggestion"),
                        }
                        result = await self.execute_tool("save_verification_result", params)
                        result_str = str(result)
                        # 成功判断：工具未返回错误，且有"已保存"/"成功"/"buffered"等成功标志
                        tool_succeeded = (
                            result
                            and not result_str.startswith("Error:")
                            and not result_str.startswith("错误:")
                            and (
                                "已保存" in result_str
                                or "成功" in result_str
                                or "'saved': True" in result_str
                                or "buffered" in result_str
                            )
                        )
                        if tool_succeeded:
                            saved_count += 1
                            logger.info(f"[{self.name}] 补救保存第 {idx+1}/{len(findings)} 条验证结果成功")
                        else:
                            logger.warning(f"[{self.name}] 补救保存第 {idx+1}/{len(findings)} 条结果未能确认成功: {result_str[:100]}")
                    except Exception as e:
                        logger.error(f"[{self.name}] 补救保存第 {idx+1} 条验证结果失败: {e}")
                
                if saved_count > 0:
                    logger.info(f"[{self.name}] 补救保存完成：{saved_count}/{len(findings)} 条成功")
                    await self.emit_event(
                        "success",
                        f"兜底机制完成：成功补救保存 {saved_count}/{len(findings)} 个验证结果",
                        metadata={
                            "agent_type": agent_type,
                            "tool": expected_tool,
                            "saved_count": saved_count,
                            "total_findings": len(findings),
                            "success_rate": f"{saved_count}/{len(findings)}",
                        },
                    )
                    return {
                        "fallback_executed": True,
                        "tool": expected_tool,
                        "saved_count": saved_count,
                        "total_findings": len(findings),
                    }
                else:
                    await self.emit_event(
                        "error",
                        f"兜底机制失败：未能补救保存任何验证结果（共 {len(findings)} 条）",
                        metadata={"agent_type": agent_type, "total_findings": len(findings)},
                    )
                    return None
            
            else:
                logger.warning(f"[{self.name}] 不支持的兜底类型: {agent_type}/{expected_tool}")
                await self.emit_event(
                    "warning",
                    f"兜底机制：不支持的类型 {agent_type}/{expected_tool}",
                    metadata={"agent_type": agent_type, "expected_tool": expected_tool},
                )
                return None
                
        except Exception as e:
            logger.error(f"[{self.name}] 执行补救保存失败: {e}", exc_info=True)
            await self.emit_event(
                "error",
                f"兜底机制异常：{str(e)[:100]}",
                metadata={"agent_type": agent_type, "error": str(e)},
            )
            return None
