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

from ..core.state import AgentState, AgentStatus
from ..core.registry import agent_registry
from ..core.message import message_bus, MessageType, AgentMessage

logger = logging.getLogger(__name__)

MAX_EVENT_PAYLOAD_CHARS = 120000

TOOL_ALIAS_CANDIDATES: Dict[str, List[str]] = {
    "smart_scan": ["smart_scan", "quick_audit", "opengrep_scan", "pattern_match", "search_code", "read_file"],
    "quick_audit": ["quick_audit", "smart_scan", "opengrep_scan", "pattern_match", "search_code", "read_file"],
    "rag_query": ["rag_query", "security_search", "search_code"],
    "security_search": ["security_search", "rag_query", "search_code"],
}

TOOL_INPUT_REPAIR_MAP: Dict[str, str] = {
    "query": "keyword",
    "path": "file_path",
    "filepath": "file_path",
    "file": "file_path",
    "dir": "directory",
}

RETRY_GUARD_TOOLS: Set[str] = {"read_file", "search_code", "pattern_match"}
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

if TYPE_CHECKING:
    from ..mcp.runtime import MCPRuntime
    from ..mcp.write_scope import TaskWriteScopeGuard, WriteScopeDecision


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
    
    # 🔥 协作信息 - Agent 传递给下一个 Agent 的结构化信息
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
            lines.append("### ⚠️ 需要特别关注")
            for point in self.attention_points:
                lines.append(f"- {point}")
            lines.append("")
        
        if self.priority_areas:
            lines.append("### 优先分析区域")
            for area in self.priority_areas:
                lines.append(f"- {area}")
        
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
        
        # 🔥 生成唯一ID
        self._agent_id = f"agent_{uuid.uuid4().hex[:8]}"
        
        # 🔥 增强的状态管理
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

        # 获取超时配置
        self._timeout_config = self._get_timeout_config()
        
        # 🔥 协作状态
        self._incoming_handoff: Optional[TaskHandoff] = None
        self._insights: List[str] = []  # 收集的洞察
        self._work_completed: List[str] = []  # 完成的工作记录

        # 🔥 最近一次工具输出快照（用于避免 llm_observation 复写同一段 tool_result）
        self._last_tool_result_snapshot: Optional[Dict[str, Any]] = None
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
        self._recent_read_file_paths: deque[str] = deque(maxlen=12)
        self._recent_reason_dirs: deque[str] = deque(maxlen=16)
        self._recent_search_directories: deque[str] = deque(maxlen=12)
        self._mcp_runtime: Optional["MCPRuntime"] = None
        self._write_scope_guard: Optional["TaskWriteScopeGuard"] = None
        
        # 🔥 是否已注册到注册表
        self._registered = False
        
        # 🔥 加载知识模块到系统提示词
        if self.knowledge_modules:
            self._load_knowledge_modules()
    
    def _register_to_registry(self, task: Optional[str] = None) -> None:
        """注册到Agent注册表（延迟注册，在run时调用）"""
        logger.debug(f"[AgentTree] _register_to_registry 被调用: {self.config.name} (id={self._agent_id}, parent={self.parent_id}, _registered={self._registered})")
        
        if self._registered:
            logger.debug(f"[AgentTree] {self.config.name} 已注册，跳过 (id={self._agent_id})")
            return
        
        logger.debug(f"[AgentTree] 正在注册 Agent: {self.config.name} (id={self._agent_id}, parent={self.parent_id})")
        
        agent_registry.register_agent(
            agent_id=self._agent_id,
            agent_name=self.config.name,
            agent_type=self.config.agent_type.value,
            task=task or self._state.task or "Initializing",
            parent_id=self.parent_id,
            agent_instance=self,
            state=self._state,
            knowledge_modules=self.knowledge_modules,
        )
        
        # 创建消息队列
        message_bus.create_queue(self._agent_id)
        self._registered = True
        
        tree = agent_registry.get_agent_tree()
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
            from ..knowledge import knowledge_loader

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
            'llm_first_token_timeout': getattr(settings, 'LLM_FIRST_TOKEN_TIMEOUT', 90),
            'llm_stream_timeout': getattr(settings, 'LLM_STREAM_TIMEOUT', 60),
            'agent_timeout': getattr(settings, 'AGENT_TIMEOUT_SECONDS', 1800),
            'sub_agent_timeout': getattr(settings, 'SUB_AGENT_TIMEOUT_SECONDS', 600),
            'tool_timeout': getattr(settings, 'TOOL_TIMEOUT_SECONDS', 60),
        }
    
    @property
    def name(self) -> str:
        return self.config.name
    
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
    
        # 🔥 外部取消检查回调
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

    def set_mcp_runtime(self, runtime: Optional["MCPRuntime"]) -> None:
        """设置 MCP 运行时（可选）。"""
        self._mcp_runtime = runtime
        if runtime and hasattr(runtime, "get_write_scope_guard"):
            try:
                self._write_scope_guard = runtime.get_write_scope_guard()
            except Exception:
                self._write_scope_guard = None

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
            if "file_path" in normalized_input or "path" not in normalized_input:
                normalized_input["file_path"] = normalized_file
            if "path" in normalized_input:
                normalized_input["path"] = normalized_file
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
        await self.emit_event(
            "llm_start",
            f"[{self.name}] 第 {iteration} 轮迭代开始",
            metadata={"iteration": iteration}
        )
    
    async def emit_llm_thought(self, thought: str, iteration: int):
        """发射 LLM 思考内容事件 - 这是核心！展示 LLM 在想什么"""
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
        await self.emit_event(
            "llm_complete",
            f"[{self.name}] 完成: {result_summary} (消耗 {tokens_used} tokens)",
            metadata={
                "tokens_used": tokens_used,
            }
        )
    
    async def emit_llm_action(self, action: str, action_input: Dict):
        """发射 LLM 动作决策事件"""
        await self.emit_event(
            "llm_action",
            f"[{self.name}] 执行动作: {action}",
            metadata={
                "action": action,
                "action_input": action_input,
            }
        )
    
    async def emit_llm_observation(self, observation: str):
        """发射 LLM 观察事件"""
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
    ):
        """发射工具调用事件"""
        metadata: Dict[str, Any] = {}
        if tool_call_id:
            metadata["tool_call_id"] = tool_call_id
        if alias_used:
            metadata["alias_used"] = alias_used
        if input_repaired:
            metadata["input_repaired"] = input_repaired
        if validation_error:
            metadata["validation_error"] = validation_error
        await self.emit_event(
            "tool_call",
            f"[{self.name}] 调用工具: {tool_name}",
            tool_name=tool_name,
            tool_input=tool_input,
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
        extra_metadata: Optional[Dict[str, Any]] = None,
    ):
        """发射工具结果事件"""
        # 🔥 修复：确保 result 不为 None，避免显示 "None" 字符串
        safe_result = result if result and result != "None" else ""
        stored_result, truncated = _truncate_with_flag(safe_result)
        tool_output_dict = {"result": stored_result if stored_result else "", "truncated": truncated}

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

        metadata: Dict[str, Any] = {"tool_status": tool_status}
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
        verification_evidence: Optional[str] = None,
        code_snippet: Optional[str] = None,
        function_trigger_flow: Optional[List[str]] = None,
        reachability_file: Optional[str] = None,
        reachability_function: Optional[str] = None,
        reachability_function_start_line: Optional[int] = None,
        reachability_function_end_line: Optional[int] = None,
        context_start_line: Optional[int] = None,
        context_end_line: Optional[int] = None,
    ):
        """发射漏洞发现事件"""
        import uuid
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

        # 🔥 使用 EventManager.emit_finding 发送正确的事件类型
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
                cwe_id=cwe_id,
                description=description,
                verification_evidence=verification_evidence,
                code_snippet=code_snippet,
                function_trigger_flow=function_trigger_flow,
                reachability_file=reachability_file,
                reachability_function=reachability_function,
                reachability_function_start_line=normalized_reachability_start,
                reachability_function_end_line=normalized_reachability_end,
                context_start_line=normalized_context_start,
                context_end_line=normalized_context_end,
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
                    "cwe_id": cwe_id,
                    "description": description,
                    "verification_evidence": verification_evidence,
                    "code_snippet": code_snippet,
                    "function_trigger_flow": function_trigger_flow,
                    "reachability_file": reachability_file,
                    "reachability_function": reachability_function,
                    "reachability_function_start_line": normalized_reachability_start,
                    "reachability_function_end_line": normalized_reachability_end,
                    "context_start_line": normalized_context_start,
                    "context_end_line": normalized_context_end,
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
            # 🔥 不传递 temperature 和 max_tokens，让 LLMService 使用用户配置
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
    
    # ============ Memory Compression ============
    
    def compress_messages_if_needed(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 100000,
    ) -> List[Dict[str, str]]:
        """
        如果消息历史过长，自动压缩
        
        Args:
            messages: 消息列表
            max_tokens: 最大token数
            
        Returns:
            压缩后的消息列表
        """
        from ...llm.memory_compressor import MemoryCompressor
        
        compressor = MemoryCompressor(max_total_tokens=max_tokens)
        
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
        # 🔥 自动压缩过长的消息历史
        if auto_compress:
            messages = self.compress_messages_if_needed(messages)

        accumulated = ""
        total_tokens = 0

        # 🔥 在开始 LLM 调用前检查取消
        if self.is_cancelled:
            logger.info(f"[{self.name}] Cancelled before LLM call")
            return "", 0

        logger.info(f"[{self.name}] 🚀 Starting stream_llm_call, emitting thinking_start...")
        await self.emit_thinking_start()
        logger.info(f"[{self.name}] ✅ thinking_start emitted, starting LLM stream...")

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
            last_activity = time.time()

            while True:
                # 检查取消
                if self.is_cancelled:
                    logger.info(f"[{self.name}] Cancelled during LLM streaming loop")
                    break
                
                try:
                    # 🔥 使用用户配置的超时时间
                    # 第一个 token 使用首Token超时，后续 token 使用流式超时
                    first_token_timeout = float(self._timeout_config.get('llm_first_token_timeout', 90))
                    stream_timeout = float(self._timeout_config.get('llm_stream_timeout', 60))
                    timeout = first_token_timeout if not first_token_received else stream_timeout

                    chunk = await asyncio.wait_for(iterator.__anext__(), timeout=timeout)

                    last_activity = time.time()
                    
                    if chunk["type"] == "token":
                        first_token_received = True
                        token = chunk["content"]
                        # 🔥 累积 content，确保 accumulated 变量更新
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

                        await self.emit_thinking_token(token, accumulated)
                        # 🔥 CRITICAL: 让出控制权给事件循环，让 SSE 有机会发送事件
                        await asyncio.sleep(0)

                    elif chunk["type"] == "done":
                        accumulated = chunk["content"]
                        if chunk.get("usage"):
                            total_tokens = chunk["usage"].get("total_tokens", 0)
                        break

                    elif chunk["type"] == "error":
                        accumulated = chunk.get("accumulated", "")
                        error_msg = chunk.get("error", "Unknown error")
                        error_type = chunk.get("error_type", "unknown")
                        user_message = chunk.get("user_message", error_msg)
                        logger.error(f"[{self.name}] Stream error ({error_type}): {error_msg}")

                        if chunk.get("usage"):
                            total_tokens = chunk["usage"].get("total_tokens", 0)

                        # 使用特殊前缀标记 API 错误，让调用方能够识别
                        # 格式：[API_ERROR:error_type] user_message
                        if error_type in ("rate_limit", "quota_exceeded", "authentication", "connection"):
                            accumulated = f"[API_ERROR:{error_type}] {user_message}"
                        elif not accumulated:
                            accumulated = f"[系统错误: {error_msg}] 请重新思考并输出你的决策。"
                        break

                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    timeout_type = "First Token" if not first_token_received else "Stream"
                    logger.error(f"[{self.name}] LLM {timeout_type} Timeout ({timeout}s)")
                    error_msg = f"LLM 响应超时 ({timeout_type}, {timeout}s)"
                    await self.emit_event("error", error_msg)
                    if not accumulated:
                         accumulated = f"[超时错误: {timeout}s 无响应] 请尝试简化请求或重试。"
                    break
                    
        except asyncio.CancelledError:
            logger.info(f"[{self.name}] LLM call cancelled")
            raise
        except Exception as e:
            # 🔥 增强异常处理，避免吞掉错误
            logger.error(f"[{self.name}] Unexpected error in stream_llm_call: {e}", exc_info=True)
            await self.emit_event("error", f"LLM 调用错误: {str(e)}")
            accumulated = f"[LLM调用错误: {str(e)}] 请重试。"
        finally:
            await self.emit_thinking_end(accumulated)
        
        # 🔥 记录空响应警告，帮助调试
        if not accumulated or not accumulated.strip():
            logger.warning(f"[{self.name}] Empty LLM response returned (total_tokens: {total_tokens})")
        
        return accumulated, total_tokens

    def _resolve_tool_name(self, requested_tool_name: str) -> Tuple[str, Optional[str]]:
        """Resolve unknown tool names using conservative alias candidates."""
        if requested_tool_name in self.tools:
            return requested_tool_name, None

        normalized = str(requested_tool_name or "").strip().lower()
        candidates = TOOL_ALIAS_CANDIDATES.get(normalized, [])
        for candidate in candidates:
            if candidate in self.tools:
                return candidate, requested_tool_name
        return requested_tool_name, None

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
            self._append_recent_unique(self._recent_read_file_paths, value)
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

        candidates.extend(list(self._recent_read_file_paths))
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
        if tool_name == "read_file":
            for value in (tool_metadata.get("file_path"), tool_input.get("file_path")):
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
        runtime = self._mcp_runtime
        if runtime and hasattr(runtime, "register_evidence_path"):
            try:
                runtime.register_evidence_path(file_path)
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
            "read_file",
            "extract_function",
            "controlflow_analysis_light",
            "locate_enclosing_function",
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
                cleaned_path = raw_path.strip("`'\"()[]{}<>，,。！？；;")
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
        return any(token in text for token in ("|", "(", r"\s"))

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
                target_name = "read_file"
            elif any(key in input_dict for key in search_keys):
                target_name = "search_code"

            if target_name in self.tools:
                return target_name, requested_tool_name
            return requested_tool_name, None

        if normalized == "verify_reachability":
            dataflow_keys = {"source_hints", "sink_hints", "variable_name", "max_hops"}
            controlflow_keys = {
                "file_path",
                "line_start",
                "line_end",
                "function_name",
                "vulnerability_type",
                "call_chain_hint",
                "control_conditions_hint",
                "entry_points_hint",
            }

            if "dataflow_analysis" in self.tools and any(key in input_dict for key in dataflow_keys):
                return "dataflow_analysis", requested_tool_name

            if "controlflow_analysis_light" in self.tools and any(
                key in input_dict for key in controlflow_keys
            ):
                return "controlflow_analysis_light", requested_tool_name

            if "extract_function" in self.tools and any(
                key in input_dict for key in {"function_name", "file_path", "path"}
            ):
                return "extract_function", requested_tool_name

            if "read_file" in self.tools:
                return "read_file", requested_tool_name

        if normalized == "locate_enclosing_function":
            return "locate_enclosing_function", requested_tool_name

        return requested_tool_name, None

    def _build_retry_guard_key(self, tool_name: str, tool_input: Dict[str, Any]) -> Optional[str]:
        if tool_name not in RETRY_GUARD_TOOLS:
            return None

        if tool_name == "read_file":
            file_path = self._normalize_path_key(tool_input.get("file_path"))
            return f"{tool_name}|{file_path}" if file_path else None

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

        context_texts = [text for text in self._recent_thought_texts if isinstance(text, str) and text.strip()]
        if tool_name == "read_file" and "file_path" in schema_fields:
            file_hint: Dict[str, Any] = {}
            file_path = str(repaired.get("file_path") or "").strip()
            if not file_path:
                file_hint = self._extract_file_hint_from_context(context_texts)
                hinted_path = str(file_hint.get("file_path") or "").strip()
                if hinted_path:
                    repaired["file_path"] = hinted_path
                    repaired_changes["__context.file_path"] = "file_path"
                    if "start_line" in schema_fields and repaired.get("start_line") in (None, "") and file_hint.get("start_line") is not None:
                        repaired["start_line"] = int(file_hint["start_line"])
                        if "end_line" in schema_fields and repaired.get("end_line") in (None, "") and file_hint.get("end_line") is not None:
                            repaired["end_line"] = int(file_hint["end_line"])
                            repaired_changes["__context.line_range"] = "start_line,end_line"
            else:
                file_hint = {"file_path": file_path}

            if "reason_paths" in schema_fields and not repaired.get("reason_paths"):
                reason_paths = self._collect_reason_paths_for_read(file_hint)
                if reason_paths:
                    repaired["reason_paths"] = reason_paths
                    repaired_changes["__context.reason_paths"] = "reason_paths"
            if "project_scope" in schema_fields and "project_scope" not in repaired:
                repaired["project_scope"] = True
                repaired_changes["__context.project_scope"] = "project_scope"

        if tool_name == "search_code" and "keyword" in schema_fields:
            keyword = str(repaired.get("keyword") or "").strip()
            if not keyword:
                hinted_keyword = self._extract_keyword_hint_from_context(context_texts)
                if hinted_keyword:
                    repaired["keyword"] = hinted_keyword
                    repaired_changes["__context.keyword"] = "keyword"
                    if "is_regex" in schema_fields and "is_regex" not in repaired and self._keyword_prefers_regex(hinted_keyword):
                        repaired["is_regex"] = True
                        repaired_changes["__context.regex_hint"] = "is_regex"

        missing_required: List[str] = []
        for name in sorted(required_fields):
            value = repaired.get(name, None)
            if value is None or value == "" or value == []:
                missing_required.append(name)

        return repaired, repaired_changes, missing_required, sorted(schema_fields)
    
    async def execute_tool(self, tool_name: str, tool_input: Dict) -> str:
        """
        统一的工具执行方法 - 支持取消和超时

        Args:
            tool_name: 工具名称
            tool_input: 工具参数

        Returns:
            工具执行结果字符串
        """
        # 🔥 在执行工具前检查取消
        if self.is_cancelled:
            return "⚠️ 任务已取消"

        requested_tool_name = str(tool_name or "").strip()
        raw_tool_input = tool_input if isinstance(tool_input, dict) else {}

        virtual_resolved_name, virtual_alias = self._resolve_virtual_tool_name(
            requested_tool_name,
            raw_tool_input,
        )
        resolved_tool_name, alias_used = self._resolve_tool_name(virtual_resolved_name)
        if virtual_alias:
            alias_used = virtual_alias

        tool = self.tools.get(resolved_tool_name)
        local_tool_available = bool(tool and hasattr(tool, "execute"))

        mcp_runtime = self._mcp_runtime
        mcp_can_handle = bool(
            mcp_runtime
            and hasattr(mcp_runtime, "can_handle")
            and mcp_runtime.can_handle(resolved_tool_name)
        )

        if not local_tool_available and not mcp_can_handle:
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

        repaired_input, write_scope_metadata, write_scope_error = self._enforce_write_scope(
            resolved_tool_name,
            repaired_input,
        )
        is_write_tool = self._is_write_tool(resolved_tool_name)

        serialized_input = json.dumps(repaired_input, ensure_ascii=False, sort_keys=True)
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
                return (
                    "⚠️ 写入策略校验失败\n\n"
                    f"**请求工具**: {requested_tool_name}\n"
                    f"**实际工具**: {resolved_tool_name}\n"
                    f"**原因**: {write_scope_error}\n"
                    "请改用证据绑定的文件并缩小写入范围。"
                )

            cached_output = self._tool_success_cache.get(tool_call_key)
            if not is_write_tool and call_count >= 2 and cached_output is not None:
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
                await self.emit_tool_result(
                    resolved_tool_name,
                    short_circuit_msg,
                    0,
                    tool_call_id=tool_call_id,
                    tool_status="failed",
                    alias_used=alias_used,
                    input_repaired=repaired_changes or None,
                    extra_metadata=write_scope_metadata or None,
                )
                return (
                    "⚠️ 工具调用已短路\n\n"
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
                await self.emit_tool_result(
                    resolved_tool_name,
                    validation_error,
                    0,
                    tool_call_id=tool_call_id,
                    tool_status="failed",
                    alias_used=alias_used,
                    input_repaired=repaired_changes or None,
                    validation_error=validation_error,
                    extra_metadata=write_scope_metadata or None,
                )
                example_fields = ", ".join(f'"{name}": "..."' for name in missing_required)
                return (
                    "⚠️ 工具参数校验失败\n\n"
                    f"**请求工具**: {requested_tool_name}\n"
                    f"**实际执行工具**: {resolved_tool_name}\n"
                    f"**缺失必填字段**: {', '.join(missing_required)}\n"
                    f"**建议示例**: {{{example_fields}}}\n"
                    "请补齐参数后重试。"
                )

            use_mcp_first = bool(
                mcp_can_handle
                and mcp_runtime
                and (
                    not local_tool_available
                    or (
                        hasattr(mcp_runtime, "should_prefer_mcp")
                        and mcp_runtime.should_prefer_mcp()
                    )
                )
            )
            mcp_fallback_metadata: Dict[str, Any] = {}
            if use_mcp_first and mcp_runtime:
                mcp_result = await mcp_runtime.execute_tool(
                    tool_name=resolved_tool_name,
                    tool_input=repaired_input,
                    agent_name=self.name,
                    alias_used=alias_used,
                )
                mcp_result_meta = (
                    dict(mcp_result.metadata)
                    if isinstance(mcp_result.metadata, dict)
                    else {}
                )
                merged_meta = {**write_scope_metadata, **mcp_result_meta}

                if mcp_result.handled:
                    mcp_output = str(mcp_result.data or mcp_result.error or "")
                    if mcp_result.success:
                        await self.emit_tool_result(
                            resolved_tool_name,
                            mcp_output,
                            0,
                            tool_call_id=tool_call_id,
                            tool_status="completed",
                            alias_used=alias_used,
                            input_repaired=repaired_changes or None,
                            extra_metadata=merged_meta or None,
                        )
                        self._record_tool_context(
                            tool_name=resolved_tool_name,
                            tool_input=repaired_input,
                            tool_metadata=mcp_result_meta,
                        )
                        if not is_write_tool:
                            self._tool_success_cache[tool_call_key] = mcp_output
                            if len(self._tool_success_cache) > 500:
                                oldest_key = next(iter(self._tool_success_cache))
                                self._tool_success_cache.pop(oldest_key, None)
                        return mcp_output

                    if mcp_result.should_fallback and local_tool_available:
                        mcp_fallback_metadata = {
                            **merged_meta,
                            "mcp_fallback_used": True,
                            "mcp_fallback_error": mcp_result.error or "unknown",
                            "mcp_runtime_fallback_used": True,
                            "mcp_runtime_fallback_from": mcp_result_meta.get("mcp_runtime_domain"),
                        }
                    elif not mcp_result.should_fallback:
                        await self.emit_tool_result(
                            resolved_tool_name,
                            mcp_output,
                            0,
                            tool_call_id=tool_call_id,
                            tool_status="failed",
                            alias_used=alias_used,
                            input_repaired=repaired_changes or None,
                            extra_metadata=merged_meta or None,
                        )
                        return (
                            "⚠️ MCP 工具执行失败\n\n"
                            f"**请求工具**: {requested_tool_name}\n"
                            f"**实际工具**: {resolved_tool_name}\n"
                            f"**错误**: {mcp_result.error or 'unknown'}\n"
                            "请调整参数后重试。"
                        )

                    elif not local_tool_available:
                        await self.emit_tool_result(
                            resolved_tool_name,
                            mcp_output,
                            0,
                            tool_call_id=tool_call_id,
                            tool_status="failed",
                            alias_used=alias_used,
                            input_repaired=repaired_changes or None,
                            extra_metadata=merged_meta or None,
                        )
                        return (
                            "⚠️ MCP 工具执行失败且无本地回退\n\n"
                            f"**请求工具**: {requested_tool_name}\n"
                            f"**实际工具**: {resolved_tool_name}\n"
                            f"**错误**: {mcp_result.error or 'unknown'}"
                        )

            if not local_tool_available:
                return (
                    "⚠️ 工具不可用\n\n"
                    f"**请求工具**: {requested_tool_name}\n"
                    f"**实际工具**: {resolved_tool_name}\n"
                    "MCP 未处理且本地工具不可用。"
                )

            import time
            start = time.time()

            # 🔥 根据工具类型设置不同的超时时间
            tool_timeouts = {
                "opengrep_scan": 120,      # 外部扫描工具需要更长时间
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
            # 🔥 使用用户配置的默认工具超时时间
            default_tool_timeout = self._timeout_config.get('tool_timeout', 60)
            timeout = tool_timeouts.get(resolved_tool_name, default_tool_timeout)

            # 🔥 使用 asyncio.wait_for 添加超时控制，同时支持取消
            async def execute_with_cancel_check():
                """包装工具执行，定期检查取消状态"""
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
                    extra_metadata=(
                        {**write_scope_metadata, **mcp_fallback_metadata}
                        if (write_scope_metadata or mcp_fallback_metadata)
                        else None
                    ),
                )
                return (
                    f"⚠️ 工具 '{resolved_tool_name}' 执行超时 ({timeout}秒)，"
                    "请尝试其他方法或减小操作范围。"
                )
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
                    extra_metadata=(
                        {**write_scope_metadata, **mcp_fallback_metadata}
                        if (write_scope_metadata or mcp_fallback_metadata)
                        else None
                    ),
                )
                return "⚠️ 任务已取消"

            duration_ms = int((time.time() - start) * 1000)
            # 🔥 修复：确保传递有意义的结果字符串，避免 "None"
            result_preview = str(result.data) if result.data is not None else (result.error if result.error else "")
            await self.emit_tool_result(
                resolved_tool_name,
                result_preview,
                duration_ms,
                tool_call_id=tool_call_id,
                tool_status="completed" if result.success else "failed",
                alias_used=alias_used,
                input_repaired=repaired_changes or None,
                extra_metadata=(
                    {**write_scope_metadata, **mcp_fallback_metadata}
                    if (write_scope_metadata or mcp_fallback_metadata)
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

            # 🔥 工具执行后再次检查取消
            if self.is_cancelled:
                return "⚠️ 任务已取消"

            if result.success:
                metadata_dict = dict(result.metadata) if isinstance(result.metadata, dict) else {}
                self._record_tool_context(
                    tool_name=resolved_tool_name,
                    tool_input=repaired_input,
                    tool_metadata=metadata_dict,
                )
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
                if not is_write_tool:
                    self._tool_success_cache[tool_call_key] = output
                    if len(self._tool_success_cache) > 500:
                        oldest_key = next(iter(self._tool_success_cache))
                        self._tool_success_cache.pop(oldest_key, None)
                return output
            else:
                # 🔥 输出详细的错误信息，包括原始错误
                guard_hint = ""
                if retry_guard_key and self._deterministic_failure_counts.get(retry_guard_key, 0) >= 2:
                    guard_hint = (
                        "\n\n同一输入已连续出现确定性失败。"
                        "后续相同输入将被系统短路，请修改参数或改用其他工具。"
                    )
                error_msg = f"""⚠️ 工具执行失败

**请求工具**: {requested_tool_name}
**实际工具**: {resolved_tool_name}
**参数**: {json.dumps(repaired_input, ensure_ascii=False, indent=2) if repaired_input else '无'}
**错误**: {result.error}

请根据错误信息调整参数或尝试其他方法。{guard_hint}"""
                return error_msg

        except asyncio.CancelledError:
            logger.info(f"[{self.name}] Tool '{resolved_tool_name}' execution cancelled")
            return "⚠️ 任务已取消"
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
                    extra_metadata=(
                        {**write_scope_metadata, **mcp_fallback_metadata}
                        if (write_scope_metadata or mcp_fallback_metadata)
                        else None
                    ),
                )
            # 🔥 输出完整的原始错误信息，包括堆栈跟踪
            error_msg = f"""❌ 工具执行异常

**请求工具**: {requested_tool_name}
**实际工具**: {resolved_tool_name}
**参数**: {json.dumps(repaired_input, ensure_ascii=False, indent=2) if repaired_input else '无'}
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
