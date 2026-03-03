"""Tools for managing the Recon risk point queue."""
import json
import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .base import AgentTool, ToolResult

logger = logging.getLogger(__name__)


class ReconRiskPointInput(BaseModel):
    file_path: str = Field(..., description="风险点文件路径")
    line_start: int = Field(..., description="风险点起始行号")
    description: str = Field(..., description="风险描述")
    severity: Optional[str] = Field("high", description="严重程度")
    confidence: Optional[float] = Field(0.6, description="置信度 0.0-1.0")
    vulnerability_type: Optional[str] = Field("potential_issue", description="漏洞类型")
    context: Optional[str] = Field(None, description="附加上下文")


class GetReconRiskQueueStatusTool(AgentTool):
    def __init__(self, queue_service, task_id: str):
        super().__init__()
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "get_recon_risk_queue_status"

    @property
    def description(self) -> str:
        return "获取 Recon 风险点队列的状态，包括待处理数量和统计信息。"

    async def _execute(self, **kwargs) -> ToolResult:
        try:
            stats = self.queue_service.stats(self.task_id)
            pending = stats.get("current_size", 0)
            response = {
                "queue_status": stats,
                "pending_count": pending,
            }
            return ToolResult(success=True, data=response)
        except Exception as exc:
            logger.error(f"[ReconQueue] Status failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class PushRiskPointToQueueTool(AgentTool):
    def __init__(self, queue_service, task_id: str):
        super().__init__()
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "push_risk_point_to_queue"

    @property
    def description(self) -> str:
        return "将 Recon 发现的风险点推送到 Recon 风险队列中，供后续 Analysis 逐条处理。"

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
    def __init__(self, queue_service, task_id: str):
        super().__init__()
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "dequeue_recon_risk_point"

    @property
    def description(self) -> str:
        return "从 Recon 风险点队列中取出第一条风险点（FIFO）。"

    async def _execute(self, **kwargs) -> ToolResult:
        try:
            risk_point = self.queue_service.dequeue(self.task_id)
            remaining = self.queue_service.size(self.task_id)
            return ToolResult(success=True, data={
                "risk_point": risk_point,
                "queue_remaining": remaining,
            })
        except Exception as exc:
            logger.error(f"[ReconQueue] Dequeue failed: {exc}")
            return ToolResult(success=False, error=str(exc), data={})


class PeekReconRiskQueueTool(AgentTool):
    class PeekInput(BaseModel):
        limit: int = Field(3, ge=1, description="预览条数")

    def __init__(self, queue_service, task_id: str):
        super().__init__()
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "peek_recon_risk_queue"

    @property
    def description(self) -> str:
        return "预览 Recon 风险点队列中的前 N 条记录。"

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
    def __init__(self, queue_service, task_id: str):
        super().__init__()
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "clear_recon_risk_queue"

    @property
    def description(self) -> str:
        return "清空 Recon 风险点队列。"

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

    def __init__(self, queue_service, task_id: str):
        super().__init__()
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "is_recon_risk_point_in_queue"

    @property
    def description(self) -> str:
        return "检查指定风险点是否仍在 Recon 风险队列中。"

    @property
    def args_schema(self):
        return self.Input

    async def _execute(self, file_path: str, line_start: int, description: str = "", **kwargs) -> ToolResult:
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
