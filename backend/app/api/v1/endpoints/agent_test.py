"""
Agent 单体测试 API

提供 ReconAgent、AnalysisAgent、VerificationAgent、BusinessLogicScanAgent
的独立测试接口，不依赖完整任务流水线。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.session import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────── Request Models ──────────────────────────────


class ReconTestRequest(BaseModel):
    project_path: str = Field(..., description="项目绝对路径")
    project_name: str = Field("test-project", description="项目名称")
    framework_hint: Optional[str] = Field(None, description="框架提示（如 django/fastapi/express）")
    max_iterations: int = Field(6, ge=1, le=200)


class AnalysisTestRequest(BaseModel):
    project_path: str = Field(..., description="项目绝对路径")
    project_name: str = Field("test-project", description="项目名称")
    high_risk_areas: List[str] = Field(default_factory=list, description="高风险区域列表")
    entry_points: List[str] = Field(default_factory=list, description="入口点列表")
    task_description: str = Field("", description="审计任务描述")
    max_iterations: int = Field(8, ge=1, le=200)


class VerificationTestRequest(BaseModel):
    project_path: str = Field(..., description="项目绝对路径")
    findings: List[Dict[str, Any]] = Field(..., description="待验证的漏洞列表")
    max_iterations: int = Field(6, ge=1, le=200)


class BusinessLogicTestRequest(BaseModel):
    project_path: str = Field(..., description="项目绝对路径")
    entry_points_hint: List[str] = Field(
        default_factory=list,
        description="入口点提示，格式如 ['app/api/user.py:update_profile']",
    )
    framework_hint: Optional[str] = Field(None, description="框架提示")
    max_iterations: int = Field(8, ge=1, le=200)
    quick_mode: bool = Field(False)


class BusinessLogicReconTestRequest(BaseModel):
    project_path: str = Field(..., description="项目绝对路径")
    project_name: str = Field("test-project", description="项目名称")
    framework_hint: Optional[str] = Field(None, description="框架提示（如 django/fastapi/express）")
    max_iterations: int = Field(10, ge=1, le=200)


class BusinessLogicAnalysisTestRequest(BaseModel):
    project_path: str = Field(..., description="项目绝对路径")
    risk_point: Dict[str, Any] = Field(
        ...,
        description="单个业务逻辑风险点（来自 BL Recon 阶段），需包含 file_path、line_start、description、vulnerability_type",
    )
    max_iterations: int = Field(10, ge=1, le=200)


# ─────────────────────────── Simple Event Emitter ────────────────────────

# 队列相关工具名称，调用后需要推送队列快照
_QUEUE_PUSH_TOOL_NAMES = frozenset([
    "push_risk_point_to_queue",
    "push_finding_to_queue",
    "push_bl_risk_point_to_queue",
])


class QueueEventEmitter:
    """
    将 Agent 事件推入 asyncio.Queue，供 SSE generator 消费。

    BaseAgent 内部调用路径：
      BaseAgent.emit_event()  →  self.event_emitter.emit(AgentEventData(...))

    AgentEventData 是 event_manager.py 中定义的 dataclass，
    因此 emit() 的参数是单个 AgentEventData 实例。
    """

    def __init__(
        self,
        queue: asyncio.Queue,
        vuln_queue: Any = None,
        vuln_task_id: str = "",
        recon_queue: Any = None,
        recon_task_id: str = "",
        bl_queue: Any = None,
        bl_task_id: str = "",
    ):
        self._queue = queue
        self._vuln_queue = vuln_queue
        self._vuln_task_id = vuln_task_id
        self._recon_queue = recon_queue
        self._recon_task_id = recon_task_id
        self._bl_queue = bl_queue
        self._bl_task_id = bl_task_id

    # ── 核心入口：BaseAgent 调用的唯一方法 ──────────────────────
    async def emit(self, event_data: Any) -> None:
        """
        接收 AgentEventData 实例并推入队列。
        兼容直接传 str 的旧式调用。
        """
        if hasattr(event_data, "event_type"):
            # 标准 AgentEventData 对象
            payload: Dict[str, Any] = {
                "type": event_data.event_type,
                "message": event_data.message or "",
                "ts": time.time(),
            }
            if event_data.tool_name:
                payload["tool_name"] = event_data.tool_name
            if event_data.tool_input:
                payload["tool_input"] = event_data.tool_input
            if event_data.tool_output:
                payload["tool_output"] = str(event_data.tool_output)[:2000]
            if event_data.metadata:
                payload["metadata"] = event_data.metadata
        else:
            # 降级：直接把收到的值作为消息
            payload = {"type": "info", "message": str(event_data), "ts": time.time()}

        await self._queue.put(payload)

        # 队列 push 工具调用完成后，发送队列快照
        if (
            hasattr(event_data, "event_type")
            and event_data.event_type == "tool_result"
            and event_data.tool_name in _QUEUE_PUSH_TOOL_NAMES
        ):
            await self._emit_queue_snapshot()

    async def _emit_queue_snapshot(self) -> None:
        """采集当前队列状态并推入 SSE 流。"""
        queues: Dict[str, Any] = {}

        if self._vuln_queue and self._vuln_task_id:
            try:
                size = self._vuln_queue.get_queue_size(self._vuln_task_id)
                peek = self._vuln_queue.peek_queue(self._vuln_task_id, limit=500)
                queues["vuln"] = {
                    "label": "漏洞队列",
                    "size": size,
                    "peek": [
                        {
                            "title": str(item.get("title", item.get("vulnerability_type", "unknown"))),
                            "severity": str(item.get("severity", "medium")),
                            "vulnerability_type": str(item.get("vulnerability_type", "")),
                            "file_path": str(item.get("file_path", "")),
                            "line_start": item.get("line_start"),
                            "description": str(item.get("description", ""))[:120],
                        }
                        for item in (peek or [])
                    ],
                }
            except Exception as e:
                logger.debug("Failed to snapshot vuln queue: %s", e)

        if self._recon_queue and self._recon_task_id:
            try:
                size = self._recon_queue.size(self._recon_task_id)
                peek = self._recon_queue.peek(self._recon_task_id, limit=500)
                queues["recon"] = {
                    "label": "风险点队列",
                    "size": size,
                    "peek": [
                        {
                            "title": str(item.get("description", item.get("vulnerability_type", "unknown")))[:60],
                            "severity": str(item.get("severity", "high")),
                            "vulnerability_type": str(item.get("vulnerability_type", "")),
                            "file_path": str(item.get("file_path", "")),
                            "line_start": item.get("line_start"),
                            "confidence": item.get("confidence"),
                            "description": str(item.get("description", ""))[:120],
                        }
                        for item in (peek or [])
                    ],
                }
            except Exception as e:
                logger.debug("Failed to snapshot recon queue: %s", e)

        if self._bl_queue and self._bl_task_id:
            try:
                size = self._bl_queue.size(self._bl_task_id)
                peek = self._bl_queue.peek(self._bl_task_id, limit=500)
                queues["bl_recon"] = {
                    "label": "业务逻辑风险点队列",
                    "size": size,
                    "peek": [
                        {
                            "title": str(item.get("description", item.get("vulnerability_type", "unknown")))[:60],
                            "severity": str(item.get("severity", "high")),
                            "vulnerability_type": str(item.get("vulnerability_type", "")),
                            "file_path": str(item.get("file_path", "")),
                            "line_start": item.get("line_start"),
                            "confidence": item.get("confidence"),
                            "description": str(item.get("description", ""))[:120],
                        }
                        for item in (peek or [])
                    ],
                }
            except Exception as e:
                logger.debug("Failed to snapshot BL queue: %s", e)

        if queues:
            await self._queue.put({"type": "queue_snapshot", "queues": queues, "ts": time.time()})

    # ── 便捷方法：BaseAgent 子方法有时直接调用 ───────────────────
    async def emit_event(self, event_type: str, message: str, metadata: Optional[Dict] = None):
        await self._queue.put({
            "type": event_type,
            "message": message,
            "metadata": metadata or {},
            "ts": time.time(),
        })

    async def emit_info(self, message: str, metadata: Optional[Dict] = None):
        await self.emit_event("info", message, metadata)

    async def emit_error(self, message: str, metadata: Optional[Dict] = None):
        await self.emit_event("error", message, metadata)

    async def emit_warning(self, message: str, metadata: Optional[Dict] = None):
        await self.emit_event("warning", message, metadata)

    async def emit_thinking(self, message: str, metadata: Optional[Dict] = None):
        await self.emit_event("thinking", message, metadata)

    async def emit_phase_start(self, phase: str, message: Optional[str] = None):
        await self.emit_event("phase_start", message or f"开始 {phase} 阶段")

    async def emit_phase_complete(self, phase: str, message: Optional[str] = None):
        await self.emit_event("phase_complete", message or f"{phase} 阶段完成")


# ─────────────────────────── Tool Initialization ────────────────────────


async def _init_llm_service(user_config: Optional[Dict]) -> Any:
    from app.services.llm.service import LLMService, LLMConfigError
    svc = LLMService(user_config=user_config)
    try:
        _ = svc.config
    except LLMConfigError as e:
        raise HTTPException(status_code=400, detail=f"LLM 配置错误: {e}")
    return svc


def _build_base_tools(project_root: str) -> Dict[str, Any]:
    from app.services.agent.tools import (
        CodeWindowTool,
        FileOutlineTool,
        FileSearchTool,
        FunctionSummaryTool,
        ListFilesTool,
        LocateEnclosingFunctionTool,
        SymbolBodyTool,
    )
    return {
        "list_files": ListFilesTool(project_root),
        "search_code": FileSearchTool(project_root),
        "get_code_window": CodeWindowTool(project_root),
        "get_file_outline": FileOutlineTool(project_root),
        "get_function_summary": FunctionSummaryTool(project_root),
        "get_symbol_body": SymbolBodyTool(project_root),
        "locate_enclosing_function": LocateEnclosingFunctionTool(project_root),
    }


def _build_recon_tools(
    project_root: str,
    task_id: str,
    recon_queue: Any,
) -> Dict[str, Any]:
    from app.services.agent.tools.recon_queue_tools import (
        PushRiskPointToQueueTool,
        PushRiskPointsBatchToQueueTool,
    )
    tools = _build_base_tools(project_root)
    tools["push_risk_point_to_queue"] = PushRiskPointToQueueTool(
        queue_service=recon_queue,
        task_id=task_id,
    )
    tools["push_risk_points_to_queue"] = PushRiskPointsBatchToQueueTool(
        queue_service=recon_queue,
        task_id=task_id,
    )
    return tools


def _build_analysis_tools(
    project_root: str,
    llm_service: Any,
    task_id: str = "",
    vuln_queue: Any = None,
) -> Dict[str, Any]:
    from app.services.agent.tools import (
        PatternMatchTool, DataFlowAnalysisTool,
        ControlFlowAnalysisLightTool, LogicAuthzAnalysisTool,
        SmartScanTool, QuickAuditTool,
    )
    tools = {
        **_build_base_tools(project_root),
        "smart_scan": SmartScanTool(project_root),
        "quick_audit": QuickAuditTool(project_root),
        "pattern_match": PatternMatchTool(project_root),
        "dataflow_analysis": DataFlowAnalysisTool(llm_service, project_root=project_root),
        "controlflow_analysis_light": ControlFlowAnalysisLightTool(project_root=project_root),
        "logic_authz_analysis": LogicAuthzAnalysisTool(project_root=project_root),
    }
    if vuln_queue and task_id:
        from app.services.agent.tools.queue_tools import PushFindingToQueueTool, IsFindingInQueueTool
        tools["push_finding_to_queue"] = PushFindingToQueueTool(vuln_queue, task_id)
        tools["is_finding_in_queue"] = IsFindingInQueueTool(vuln_queue, task_id)
    return tools


def _build_verification_tools(project_root: str) -> Dict[str, Any]:
    from app.services.agent.tools import (
        CreateVulnerabilityReportTool,
    )
    # 验证测试不启用沙箱工具，避免环境依赖
    return {
        **_build_base_tools(project_root),
        "create_vulnerability_report": CreateVulnerabilityReportTool(project_root),
    }


def _build_bl_recon_tools(
    project_root: str,
    task_id: str,
    bl_queue: Any,
) -> Dict[str, Any]:
    from app.services.agent.tools.business_logic_recon_queue_tools import (
        PushBLRiskPointToQueueTool,
        PushBLRiskPointsBatchToQueueTool,
        GetBLRiskQueueStatusTool,
        IsBLRiskPointInQueueTool,
    )
    tools = _build_base_tools(project_root)
    tools["push_bl_risk_point_to_queue"] = PushBLRiskPointToQueueTool(
        queue_service=bl_queue,
        task_id=task_id,
    )
    tools["push_bl_risk_points_to_queue"] = PushBLRiskPointsBatchToQueueTool(
        queue_service=bl_queue,
        task_id=task_id,
    )
    tools["get_bl_risk_queue_status"] = GetBLRiskQueueStatusTool(
        queue_service=bl_queue,
        task_id=task_id,
    )
    tools["is_bl_risk_point_in_queue"] = IsBLRiskPointInQueueTool(
        queue_service=bl_queue,
        task_id=task_id,
    )
    return tools


def _build_bl_analysis_tools(
    project_root: str,
    llm_service: Any,
    task_id: str = "",
    vuln_queue: Any = None,
) -> Dict[str, Any]:
    from app.services.agent.tools import (
        PatternMatchTool, DataFlowAnalysisTool,
        ControlFlowAnalysisLightTool,
    )
    tools = {
        **_build_base_tools(project_root),
        "pattern_match": PatternMatchTool(project_root),
        "dataflow_analysis": DataFlowAnalysisTool(llm_service, project_root=project_root),
        "controlflow_analysis_light": ControlFlowAnalysisLightTool(project_root=project_root),
    }
    if vuln_queue and task_id:
        from app.services.agent.tools.queue_tools import PushFindingToQueueTool, IsFindingInQueueTool
        tools["push_finding_to_queue"] = PushFindingToQueueTool(vuln_queue, task_id)
        tools["is_finding_in_queue"] = IsFindingInQueueTool(vuln_queue, task_id)
    return tools


# ─────────────────────────── SSE Generator ──────────────────────────────


def _sse(data: Dict) -> str:
    def _default(obj: Any) -> Any:
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)
    return f"event: {data.get('type', 'message')}\ndata: {json.dumps(data, ensure_ascii=False, default=_default)}\n\n"


async def _run_agent_streaming(
    run_coro,
    queue: asyncio.Queue,
) -> AsyncGenerator[str, None]:
    """
    并发运行 agent coroutine 和 SSE generator。
    agent 将事件 push 到 queue；generator 消费 queue 并 yield SSE。
    """
    _DONE = object()

    async def _runner():
        try:
            result = await run_coro
            # AgentResult is a dataclass — serialize via to_dict() before JSON encoding
            result_data = result.to_dict() if hasattr(result, "to_dict") else result
            await queue.put({"type": "result", "data": result_data, "ts": time.time()})
        except Exception as exc:
            await queue.put({"type": "agent_error", "message": str(exc), "ts": time.time()})
        finally:
            await queue.put(_DONE)

    task = asyncio.create_task(_runner())

    try:
        while True:
            item = await asyncio.wait_for(queue.get(), timeout=120)
            if item is _DONE:
                break
            yield _sse(item)
    except asyncio.TimeoutError:
        yield _sse({"type": "error", "message": "Agent 执行超时（120s）"})
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    yield _sse({"type": "done", "message": "执行完成"})


def _validate_project_path(path: str) -> str:
    norm = os.path.abspath(path)
    if not os.path.isdir(norm):
        raise HTTPException(status_code=400, detail=f"项目路径不存在或不是目录: {norm}")
    return norm


async def _get_user_config(db: AsyncSession, user_id: str) -> Optional[Dict]:
    try:
        from app.api.v1.endpoints.config import _load_effective_user_config

        return await _load_effective_user_config(
            db=db,
            user_id=user_id,
        )
    except Exception as e:
        logger.warning("Failed to get user config: %s", e)
    return None


# ─────────────────────────── Endpoints ──────────────────────────────────


@router.post("/recon/run")
async def test_recon_agent(
    request: ReconTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    单独测试 ReconAgent（信息收集 Agent）。
    流式返回 Agent 执行过程和最终结果。
    """
    project_root = _validate_project_path(request.project_path)
    user_config = await _get_user_config(db, str(current_user.id))
    llm_service = await _init_llm_service(user_config)

    from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue
    test_task_id = str(uuid4())
    recon_queue = InMemoryReconRiskQueue()

    queue: asyncio.Queue = asyncio.Queue()
    emitter = QueueEventEmitter(
        queue,
        recon_queue=recon_queue,
        recon_task_id=test_task_id,
    )

    from app.services.agent.agents import ReconAgent
    tools = _build_recon_tools(project_root, test_task_id, recon_queue)
    agent = ReconAgent(llm_service=llm_service, tools=tools, event_emitter=emitter)

    file_count = sum(1 for _ in os.scandir(project_root) if _.is_file())
    input_data = {
        "project_info": {
            "name": request.project_name,
            "root": project_root,
            "file_count": file_count,
        },
        "config": {
            "framework_hint": request.framework_hint,
        },
        "task": f"对项目 {request.project_name} 执行信息收集，识别技术栈、入口点和高风险区域。",
        "task_context": "",
        "max_iterations": request.max_iterations,
    }

    return StreamingResponse(
        _run_agent_streaming(agent.run(input_data), queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/analysis/run")
async def test_analysis_agent(
    request: AnalysisTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    单独测试 AnalysisAgent（漏洞分析 Agent）。
    """
    project_root = _validate_project_path(request.project_path)
    user_config = await _get_user_config(db, str(current_user.id))
    llm_service = await _init_llm_service(user_config)

    from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
    test_task_id = str(uuid4())
    vuln_queue = InMemoryVulnerabilityQueue()

    queue: asyncio.Queue = asyncio.Queue()
    emitter = QueueEventEmitter(
        queue,
        vuln_queue=vuln_queue,
        vuln_task_id=test_task_id,
    )

    from app.services.agent.agents import AnalysisAgent
    tools = _build_analysis_tools(project_root, llm_service, task_id=test_task_id, vuln_queue=vuln_queue)
    agent = AnalysisAgent(llm_service=llm_service, tools=tools, event_emitter=emitter)

    input_data = {
        "project_info": {"name": request.project_name, "root": project_root},
        "config": {},
        "plan": {"high_risk_areas": request.high_risk_areas},
        "previous_results": {
            "recon": {
                "entry_points": request.entry_points,
                "high_risk_areas": request.high_risk_areas,
                "tech_stack": {},
                "initial_findings": [],
            }
        },
        "task": request.task_description or f"对项目 {request.project_name} 执行漏洞分析。",
        "task_context": "",
        "max_iterations": request.max_iterations,
    }

    return StreamingResponse(
        _run_agent_streaming(agent.run(input_data), queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/verification/run")
async def test_verification_agent(
    request: VerificationTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    单独测试 VerificationAgent（漏洞验证 Agent）。
    """
    project_root = _validate_project_path(request.project_path)
    user_config = await _get_user_config(db, str(current_user.id))
    llm_service = await _init_llm_service(user_config)

    queue: asyncio.Queue = asyncio.Queue()
    emitter = QueueEventEmitter(queue)

    from app.services.agent.agents import VerificationAgent
    tools = _build_verification_tools(project_root)
    agent = VerificationAgent(llm_service=llm_service, tools=tools, event_emitter=emitter)

    input_data = {
        "project_info": {"root": project_root},
        "config": {},
        "previous_results": {
            "analysis": {"findings": request.findings},
        },
        "task": "验证以下漏洞的真实性，评估其可利用性。",
        "task_context": "",
        "project_root": project_root,
        "max_iterations": request.max_iterations,
    }

    return StreamingResponse(
        _run_agent_streaming(agent.run(input_data), queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/business-logic/run")
async def test_business_logic_agent(
    request: BusinessLogicTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    单独测试 BusinessLogicScanAgent（业务逻辑漏洞扫描 Agent）。
    """
    project_root = _validate_project_path(request.project_path)
    user_config = await _get_user_config(db, str(current_user.id))
    llm_service = await _init_llm_service(user_config)

    # 重置缓存，确保每次测试都重新执行
    from app.services.agent.agents import BusinessLogicScanAgent
    BusinessLogicScanAgent.reset_cache(request.entry_points_hint or None)

    queue: asyncio.Queue = asyncio.Queue()
    emitter = QueueEventEmitter(queue)

    tools = _build_analysis_tools(project_root, llm_service)
    agent = BusinessLogicScanAgent(llm_service=llm_service, tools=tools, event_emitter=emitter)

    input_data = {
        "target": project_root,
        "framework_hint": request.framework_hint,
        "entry_points_hint": request.entry_points_hint,
        "quick_mode": request.quick_mode,
        "max_iterations": request.max_iterations,
    }

    return StreamingResponse(
        _run_agent_streaming(agent.run(input_data), queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/business-logic-recon/run")
async def test_business_logic_recon_agent(
    request: BusinessLogicReconTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    单独测试 BusinessLogicReconAgent（业务逻辑风险点侦察 Agent）。
    扫描项目中的潜在业务逻辑风险点并推入 BL 风险队列。
    """
    project_root = _validate_project_path(request.project_path)
    user_config = await _get_user_config(db, str(current_user.id))
    llm_service = await _init_llm_service(user_config)

    from app.services.agent.business_logic_risk_queue import InMemoryBusinessLogicRiskQueue
    test_task_id = str(uuid4())
    bl_queue = InMemoryBusinessLogicRiskQueue()

    queue: asyncio.Queue = asyncio.Queue()
    emitter = QueueEventEmitter(
        queue,
        bl_queue=bl_queue,
        bl_task_id=test_task_id,
    )

    from app.services.agent.agents import BusinessLogicReconAgent
    tools = _build_bl_recon_tools(project_root, task_id=test_task_id, bl_queue=bl_queue)
    agent = BusinessLogicReconAgent(llm_service=llm_service, tools=tools, event_emitter=emitter)

    input_data = {
        "project_info": {"name": request.project_name, "root": project_root},
        "config": {},
        "project_root": project_root,
        "framework_hint": request.framework_hint,
        "max_iterations": request.max_iterations,
    }

    return StreamingResponse(
        _run_agent_streaming(agent.run(input_data), queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/business-logic-analysis/run")
async def test_business_logic_analysis_agent(
    request: BusinessLogicAnalysisTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    单独测试 BusinessLogicAnalysisAgent（业务逻辑漏洞深度分析 Agent）。
    对单个 BL 风险点进行深度分析并将确认漏洞推入漏洞队列。
    """
    project_root = _validate_project_path(request.project_path)
    user_config = await _get_user_config(db, str(current_user.id))
    llm_service = await _init_llm_service(user_config)

    from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
    test_task_id = str(uuid4())
    vuln_queue = InMemoryVulnerabilityQueue()

    queue: asyncio.Queue = asyncio.Queue()
    emitter = QueueEventEmitter(
        queue,
        vuln_queue=vuln_queue,
        vuln_task_id=test_task_id,
    )

    from app.services.agent.agents import BusinessLogicAnalysisAgent
    tools = _build_bl_analysis_tools(project_root, llm_service, task_id=test_task_id, vuln_queue=vuln_queue)
    agent = BusinessLogicAnalysisAgent(llm_service=llm_service, tools=tools, event_emitter=emitter)

    input_data = {
        "risk_point": request.risk_point,
        "project_root": project_root,
        "max_iterations": request.max_iterations,
    }

    return StreamingResponse(
        _run_agent_streaming(agent.run(input_data), queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
