"""Tools for managing the Business Logic risk point queue."""

import logging
from typing import Any, List, Optional, Tuple

from pydantic import BaseModel, Field

from .base import AgentTool, ToolResult

logger = logging.getLogger(__name__)


def _validate_bl_queue_service_binding(
    *,
    queue_service: Any,
    task_id: str,
    tool_name: str,
    required_callables: Tuple[str, ...],
) -> None:
    missing = [
        method_name
        for method_name in required_callables
        if not callable(getattr(queue_service, method_name, None))
    ]
    if not missing:
        return
    missing_text = ",".join(missing)
    error_token = (
        "invalid_bl_queue_service_binding:"
        f"{tool_name}:missing_callable={missing_text}:task_id={task_id}"
    )
    logger.error("[BLRiskQueue] %s", error_token)
    raise TypeError(error_token)


class BLRiskPointInput(BaseModel):
    file_path: str = Field(..., description="风险点文件路径（相对于项目根目录）")
    line_start: int = Field(..., description="风险点起始行号")
    description: str = Field(..., description="业务逻辑风险描述")
    severity: Optional[str] = Field("high", description="严重程度：critical/high/medium/low")
    confidence: Optional[float] = Field(0.6, description="置信度 0.0-1.0")
    vulnerability_type: Optional[str] = Field("business_logic", description="业务逻辑漏洞类型：idor/privilege_escalation/amount_tampering/race_condition/auth_bypass/state_machine_bypass/etc.")
    entry_function: Optional[str] = Field(None, description="涉及的入口函数名（如 update_order, create_payment）")
    context: Optional[str] = Field(None, description="附加上下文（如 HTTP 方法、路由、相关表名）")
    route: Optional[str] = Field(None, description="入口路由或业务入口标识（HTTP/Webhook/RPC 等）")
    http_method: Optional[str] = Field(None, description="入口方法，如 GET/POST/WEBHOOK/RPC")
    auth_context: Optional[str] = Field(None, description="认证鉴权上下文，如 login_required、tenant middleware、service guard")
    related_symbols: Optional[List[str]] = Field(None, description="关联符号，如 handler/service/model/guard 名称")
    object_type: Optional[str] = Field(None, description="业务对象类型，如 order/user/payment/tenant")
    sensitive_action: Optional[str] = Field(None, description="敏感动作，如 update/refund/approve/export/share")
    evidence_refs: Optional[List[str]] = Field(None, description="证据锚点列表，如 file.py:42、OrderService.cancel")


class BLRiskPointsBatchInput(BaseModel):
    risk_points: List[BLRiskPointInput] = Field(
        ...,
        description="批量业务逻辑风险点列表，每项结构与 push_bl_risk_point_to_queue 相同",
    )


class GetBLRiskQueueStatusTool(AgentTool):
    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_bl_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="get_bl_risk_queue_status",
            required_callables=("stats",),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "get_bl_risk_queue_status"

    @property
    def description(self) -> str:
        return """
    获取业务逻辑风险点队列的状态，包括待处理数量和统计信息。

    返回值格式:
    {
        "queue_status": {...},
        "pending_count": int,
        "peek": [...]
    }

    用于在侦查过程中周期性查看当前队列状态，确认是否有重复推送等问题。"""

    async def _execute(self, **kwargs) -> ToolResult:
        try:
            stats = self.queue_service.stats(self.task_id)
            pending = stats.get("current_size", 0)
            peek_findings = self.queue_service.peek(self.task_id, limit=3)
            peek_list = []
            for finding in peek_findings:
                if isinstance(finding, dict):
                    peek_list.append({
                        "file_path": finding.get("file_path", "N/A"),
                        "line": finding.get("line_start", "N/A"),
                        "description": finding.get("description", "N/A"),
                        "vulnerability_type": finding.get("vulnerability_type", "N/A"),
                    })
            return ToolResult(success=True, data={
                "queue_status": stats,
                "pending_count": pending,
                "peek": peek_list,
            })
        except Exception as exc:
            logger.error(f"[BLRiskQueue] Status failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class PushBLRiskPointToQueueTool(AgentTool):
    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_bl_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="push_bl_risk_point_to_queue",
            required_callables=("enqueue", "size"),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "push_bl_risk_point_to_queue"

    @property
    def description(self) -> str:
        return """将业务逻辑侦查发现的风险点推送到业务逻辑风险队列，供 BusinessLogicAnalysisAgent 逐条深度分析。

        输入字段说明：
        - file_path / line_start / description：必须提供风险位置与描述
        - vulnerability_type：idor / privilege_escalation / amount_tampering / race_condition / auth_bypass / state_machine_bypass / mass_assignment / replay_attack / business_flow_bypass
        - entry_function：该风险点所在的入口函数名（如 update_order、create_payment）
        - severity：critical/high/medium/low
        - confidence：0.0-1.0
        - context：附加上下文（如 HTTP 路由、相关参数）

        调用后返回当前队列大小。"""

    @property
    def args_schema(self):
        return BLRiskPointInput

    async def _execute(self, **kwargs) -> ToolResult:
        data = kwargs
        try:
            success = self.queue_service.enqueue(self.task_id, data)
            queue_size = self.queue_service.size(self.task_id)
            message = f"业务逻辑风险点已入队，当前队列大小 {queue_size}" if success else "入队失败"
            return ToolResult(success=success, data={"message": message, "queue_size": queue_size})
        except Exception as exc:
            logger.error(f"[BLRiskQueue] Push failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class DequeueBLRiskPointTool(AgentTool):
    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_bl_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="dequeue_bl_risk_point",
            required_callables=("dequeue", "size"),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "dequeue_bl_risk_point"

    @property
    def description(self) -> str:
        return """从业务逻辑风险队列取出第一条风险点（FIFO）。

        返回字段: risk_point（已出队的风险点），queue_remaining（剩余数量）。"""

    async def _execute(self, **kwargs) -> ToolResult:
        try:
            risk_point = self.queue_service.dequeue(self.task_id)
            remaining = self.queue_service.size(self.task_id)
            return ToolResult(success=True, data={
                "risk_point": risk_point,
                "queue_remaining": remaining,
            })
        except Exception as exc:
            logger.error(f"[BLRiskQueue] Dequeue failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class PeekBLRiskQueueTool(AgentTool):
    class PeekInput(BaseModel):
        limit: int = Field(3, ge=1, description="预览条数")

    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_bl_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="peek_bl_risk_queue",
            required_callables=("peek",),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "peek_bl_risk_queue"

    @property
    def description(self) -> str:
        return """预览业务逻辑风险队列中的前 N 条记录（不出队）。

        返回: {"findings": [...], "count": 条数}。"""

    @property
    def args_schema(self):
        return self.PeekInput

    async def _execute(self, limit: int = 3, **kwargs) -> ToolResult:
        try:
            items = self.queue_service.peek(self.task_id, limit=min(limit, 20))
            return ToolResult(success=True, data={"findings": items, "count": len(items)})
        except Exception as exc:
            logger.error(f"[BLRiskQueue] Peek failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class ClearBLRiskQueueTool(AgentTool):
    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_bl_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="clear_bl_risk_queue",
            required_callables=("clear",),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "clear_bl_risk_queue"

    @property
    def description(self) -> str:
        return """清空业务逻辑风险点队列。

        返回: {"success": true/false}。"""

    async def _execute(self, **kwargs) -> ToolResult:
        try:
            success = self.queue_service.clear(self.task_id)
            return ToolResult(success=success, data={"success": success})
        except Exception as exc:
            logger.error(f"[BLRiskQueue] Clear failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class PushBLRiskPointsBatchToQueueTool(AgentTool):
    """一次调用将多个业务逻辑风险点批量推入队列。"""

    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_bl_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="push_bl_risk_points_to_queue",
            required_callables=("enqueue_batch", "size"),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "push_bl_risk_points_to_queue"

    @property
    def description(self) -> str:
        return """批量将多个业务逻辑风险点一次性推入队列。适合在同一接口/模块中发现多个业务逻辑风险时一次提交，减少工具调用轮次。

        输入格式：
        {
            "risk_points": [
                {
                    "file_path": "app/api/orders.py",
                    "line_start": 42,
                    "description": "update_order 未验证订单归属，存在 IDOR 风险",
                    "severity": "high",
                    "vulnerability_type": "idor",
                    "confidence": 0.85,
                    "entry_function": "update_order",
                    "context": "PUT /api/orders/<order_id>"
                },
                { ... }
            ]
        }

        每条风险点的字段与 push_bl_risk_point_to_queue 相同。
        返回成功入队的数量和当前队列大小。"""

    @property
    def args_schema(self):
        return BLRiskPointsBatchInput

    async def _execute(self, risk_points: list, **kwargs) -> ToolResult:
        if not isinstance(risk_points, list):
            return ToolResult(success=False, error="risk_points 必须是列表", data={})
        data_list = [
            rp.model_dump() if hasattr(rp, "model_dump") else (
                rp.dict() if hasattr(rp, "dict") else rp
            )
            for rp in risk_points
        ]
        try:
            count = self.queue_service.enqueue_batch(self.task_id, data_list)
            queue_size = self.queue_service.size(self.task_id)
            message = f"批量入队 {count}/{len(data_list)} 个业务逻辑风险点，当前队列大小 {queue_size}"
            return ToolResult(success=True, data={"message": message, "enqueued": count, "queue_size": queue_size})
        except Exception as exc:
            logger.error(f"[BLRiskQueue] Batch push failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class IsBLRiskPointInQueueTool(AgentTool):
    class Input(BaseModel):
        file_path: str = Field(...)
        line_start: int = Field(...)
        vulnerability_type: Optional[str] = Field("")

    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_bl_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="is_bl_risk_point_in_queue",
            required_callables=("contains",),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "is_bl_risk_point_in_queue"

    @property
    def description(self) -> str:
        return """检查指定业务逻辑风险点是否已在队列中（避免重复推送）。

        输入: file_path、line_start、vulnerability_type。
        返回: {"in_queue": bool}。"""

    @property
    def args_schema(self):
        return self.Input

    async def _execute(
        self, file_path: str, line_start: int, vulnerability_type: str = "", **kwargs
    ) -> ToolResult:
        try:
            point = {
                "file_path": file_path,
                "line_start": line_start,
                "vulnerability_type": vulnerability_type,
            }
            exists = self.queue_service.contains(self.task_id, point)
            return ToolResult(success=True, data={"in_queue": exists})
        except Exception as exc:
            logger.error(f"[BLRiskQueue] Contains failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})
