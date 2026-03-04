"""Tools for managing the Recon risk point queue."""

import logging
from typing import Any, Optional, Tuple

from pydantic import BaseModel, Field

from .base import AgentTool, ToolResult

logger = logging.getLogger(__name__)


def _validate_recon_queue_service_binding(
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
        "invalid_recon_queue_service_binding:"
        f"{tool_name}:missing_callable={missing_text}:task_id={task_id}"
    )
    logger.error("[ReconQueue] %s", error_token)
    raise TypeError(error_token)


class ReconRiskPointInput(BaseModel):
    file_path: str = Field(..., description="风险点文件路径")
    line_start: int = Field(..., description="风险点起始行号")
    description: str = Field(..., description="风险描述")
    severity: Optional[str] = Field("high", description="严重程度")
    confidence: Optional[float] = Field(0.6, description="置信度 0.0-1.0")
    vulnerability_type: Optional[str] = Field("potential_issue", description="漏洞类型")
    context: Optional[str] = Field(None, description="附加上下文")


class GetReconRiskQueueStatusTool(AgentTool):
    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_recon_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="get_recon_risk_queue_status",
            required_callables=("stats",),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "get_recon_risk_queue_status"

    @property
    def description(self) -> str:
        return """
    获取 Recon 风险点队列的状态，包括待处理数量和统计信息。 

    返回值格式:
    {
        "queue_status": {...},  # 详细统计（如 current_size/total_processed/last_push 等）
        "pending_count": int    # 当前待处理数量
    }

    常见用途：在持续审计过程中周期性轮询（无需输入参数），确认 Analysis Agent 是否处理完上轮的推送，同时作为数据收敛依据。"""

    async def _execute(self) -> ToolResult:
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
                        "severity": finding.get("severity", "N/A"),
                    })
            response = {
                "queue_status": stats,
                "pending_count": pending,
                "peek": peek_list,
            }
            return ToolResult(success=True, data=response)
        except Exception as exc:
            logger.error(f"[ReconQueue] Status failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class PushRiskPointToQueueTool(AgentTool):
    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_recon_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="push_risk_point_to_queue",
            required_callables=("enqueue", "size"),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "push_risk_point_to_queue"

    @property
    def description(self) -> str:
        return """将 Recon 发现的风险点推送到 Recon 风险队列中，供后续 Analysis 逐条处理。

        输入字段说明（参考 ReconRiskPointInput）：
        - file_path / line_start / description：必须提供风险位置与描述
        - severity：critical/high/medium/low/info，缺省为 high
        - vulnerability_type：比如 sql_injection、xss、command_injection 等
        - confidence：0.0-1.0，用来记录推断的置信度

        调用后会返回当前队列大小，可据此判断是否需要等待消费。"""

    @property
    def args_schema(self):
        return ReconRiskPointInput

    async def _execute(self, **kwargs) -> ToolResult:
        data = kwargs
        try:
            success = self.queue_service.enqueue(self.task_id, data)
            queue_size = self.queue_service.size(self.task_id)
            message = f"风险点已入队，当前队列大小 {queue_size}" if success else "风险点入队失败"
            return ToolResult(success=success, data={"message": message, "queue_size": queue_size})
        except Exception as exc:
            logger.error(f"[ReconQueue] Push failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class DequeueReconRiskPointTool(AgentTool):
    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_recon_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="dequeue_recon_risk_point",
            required_callables=("dequeue", "size"),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "dequeue_recon_risk_point"

    @property
    def description(self) -> str:
        return """从 Recon 风险点队列中取出第一条风险点（FIFO）。

        返回字段: risk_point（已出队的风险点结构），queue_remaining（剩余数量）。
        可用于手动或自动消费队列中的下一条记录，结合 is_recon_risk_point_in_queue 可用于保障消费一致性。"""

    async def _execute(self, **kwargs) -> ToolResult:
        try:
            risk_point = self.queue_service.dequeue(self.task_id)
            remaining = self.queue_service.size(self.task_id)
            return ToolResult(
                success=True,
                data={
                    "risk_point": risk_point,
                    "queue_remaining": remaining,
                },
            )
        except Exception as exc:
            logger.error(f"[ReconQueue] Dequeue failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class PeekReconRiskQueueTool(AgentTool):
    class PeekInput(BaseModel):
        limit: int = Field(3, ge=1, description="预览条数")

    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_recon_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="peek_recon_risk_queue",
            required_callables=("peek",),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "peek_recon_risk_queue"

    @property
    def description(self) -> str:
        return """预览 Recon 风险点队列中的前 N 条记录。

        输入: limit（最多预览的条数，最大自动限制为 20）。
        返回: {"findings": [...], "count": 实际条数}。
        使用场景：理解当前队列内容，避免重复推送，或排查未消费的风险点。"""

    @property
    def args_schema(self):
        return self.PeekInput

    async def _execute(self, limit: int = 3, **kwargs) -> ToolResult:
        try:
            items = self.queue_service.peek(self.task_id, limit=min(limit, 20))
            return ToolResult(success=True, data={"findings": items, "count": len(items)})
        except Exception as exc:
            logger.error(f"[ReconQueue] Peek failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class ClearReconRiskQueueTool(AgentTool):
    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_recon_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="clear_recon_risk_queue",
            required_callables=("clear",),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "clear_recon_risk_queue"

    @property
    def description(self) -> str:
        return """清空 Recon 风险点队列。

        作用: 重置队列状态，通常在重新规划侦查任务或出现数据异常时使用。
        返回: {"success": true/false} 指示是否成功清空。"""

    async def _execute(self, **kwargs) -> ToolResult:
        try:
            success = self.queue_service.clear(self.task_id)
            return ToolResult(success=success, data={"success": success})
        except Exception as exc:
            logger.error(f"[ReconQueue] Clear failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class IsReconRiskPointInQueueTool(AgentTool):
    class Input(BaseModel):
        file_path: str = Field(...)
        line_start: int = Field(...)
        description: Optional[str] = Field("")

    def __init__(self, *, queue_service: Any, task_id: str):
        super().__init__()
        _validate_recon_queue_service_binding(
            queue_service=queue_service,
            task_id=task_id,
            tool_name="is_recon_risk_point_in_queue",
            required_callables=("contains",),
        )
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "is_recon_risk_point_in_queue"

    @property
    def description(self) -> str:
        return """检查指定风险点是否仍在 Recon 风险队列中。

        输入字段: 文件路径、行号、可选描述（用于精确匹配）。
        返回: {"in_queue": bool}。
        场景: 结合 push/check/consume 流程，确认未消费的风险点避免重复推送。"""

    @property
    def args_schema(self):
        return self.Input

    async def _execute(
        self, file_path: str, line_start: int, description: str = "", **kwargs
    ) -> ToolResult:
        try:
            point = {
                "file_path": file_path,
                "line_start": line_start,
                "description": description,
            }
            exists = self.queue_service.contains(self.task_id, point)
            return ToolResult(success=True, data={"in_queue": exists})
        except Exception as exc:
            logger.error(f"[ReconQueue] Contains failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})
