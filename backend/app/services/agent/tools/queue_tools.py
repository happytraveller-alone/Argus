"""
Orchestrator 漏洞队列管理工具
"""

import logging
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from .base import AgentTool, ToolResult

logger = logging.getLogger(__name__)


class GetQueueStatusInput(BaseModel):
    """获取队列状态输入参数（无参数）"""
    pass


class GetQueueStatusTool(AgentTool):
    """获取队列中待验证漏洞数量"""

    def __init__(self, queue_service, task_id: str):
        """
        Args:
            queue_service: VulnerabilityQueue 实例
            task_id: 审计任务 ID
        """
        super().__init__()
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "get_queue_status"

    @property
    def description(self) -> str:
        return """获取当前待验证漏洞队列的状态信息。

返回信息包括：
- current_size: 当前队列大小
- total_enqueued: 总入队数
- total_dequeued: 总出队数
- last_enqueue_time: 最后入队时间
- last_dequeue_time: 最后出队时间
- peek: 队列前3条漏洞预览

用于监控队列状态和待验证漏洞数量。"""

    @property
    def args_schema(self):
        return GetQueueStatusInput

    async def _execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        try:
            stats = self.queue_service.get_queue_stats(self.task_id)
            
            # 获取队列前几项预览
            peek_findings = self.queue_service.peek_queue(self.task_id, limit=3)
            peek_list = []
            for finding in peek_findings:
                if isinstance(finding, dict):
                    peek_list.append({
                        "file_path": finding.get("file_path", "N/A"),
                        "line": finding.get("line_start", "N/A"),
                        "title": finding.get("title", "N/A"),
                        "severity": finding.get("severity", "N/A"),
                    })
            
            result_data = {
                "queue_status": {
                    "current_size": stats.get("current_size", 0),
                    "total_enqueued": stats.get("total_enqueued", 0),
                    "total_dequeued": stats.get("total_dequeued", 0),
                    "last_enqueue_time": stats.get("last_enqueue_time"),
                    "last_dequeue_time": stats.get("last_dequeue_time"),
                },
                "pending_count": stats.get("current_size", 0),
                "peek": peek_list,
            }
            
            logger.info(
                f"[Queue] Status check for task {self.task_id}: "
                f"{result_data['pending_count']} pending findings"
            )
            
            return ToolResult(success=True, data=result_data)
        
        except Exception as e:
            logger.error(f"[Queue] Failed to get queue status: {e}")
            return ToolResult(
                success=False,
                error=str(e),
                data={"pending_count": 0}
            )


class DequeueFindingInput(BaseModel):
    """出队漏洞输入参数（无参数）"""
    pass


class DequeueFindingTool(AgentTool):
    """从队列中取出一条漏洞进行验证"""

    def __init__(self, queue_service, task_id: str):
        """
        Args:
            queue_service: VulnerabilityQueue 实例
            task_id: 审计任务 ID
        """
        super().__init__()
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "dequeue_finding"

    @property
    def description(self) -> str:
        return """从待验证漏洞队列中取出第一条漏洞。

该漏洞应当被立即传递给 Verification Agent 进行验证。
若队列为空，返回 null。

返回信息包括：
- finding: 漏洞详细信息
- queue_remaining: 队列剩余数量
- file_path: 文件路径
- line_start: 起始行号
- title: 漏洞标题
- severity: 严重程度"""

    @property
    def args_schema(self):
        return DequeueFindingInput

    async def _execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        try:
            finding = self.queue_service.dequeue_finding(self.task_id)
            
            if finding is None:
                result_data = {
                    "finding": None,
                    "queue_remaining": 0,
                }
                logger.info(f"[Queue] Queue empty for task {self.task_id}")
            else:
                remaining = self.queue_service.get_queue_size(self.task_id)
                result_data = {
                    "finding": finding,
                    "queue_remaining": remaining,
                    "file_path": finding.get("file_path"),
                    "line_start": finding.get("line_start"),
                    "title": finding.get("title"),
                    "severity": finding.get("severity"),
                }
                logger.info(
                    f"[Queue] Dequeued finding from task {self.task_id}: "
                    f"{finding.get('file_path')} (remaining: {remaining})"
                )
            
            return ToolResult(success=True, data=result_data)
        
        except Exception as e:
            logger.error(f"[Queue] Failed to dequeue finding: {e}")
            return ToolResult(
                success=False,
                error=str(e),
                data={"finding": None, "queue_remaining": 0}
            )


class IsFindingInQueueInput(BaseModel):
    """查询漏洞是否在队列中"""
    file_path: str = Field(..., description="漏洞文件路径")
    line_start: int = Field(..., description="漏洞起始行号")
    vulnerability_type: Optional[str] = Field(default="", description="漏洞类型")
    title: Optional[str] = Field(default="", description="漏洞标题")


class IsFindingInQueueTool(AgentTool):
    """检查给定漏洞是否仍在待验证队列中"""

    def __init__(self, queue_service, task_id: str):
        super().__init__()
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "is_finding_in_queue"

    @property
    def description(self) -> str:
        return """检查指定漏洞是否在当前任务的待验证队列中（pending）。

输入字段：file_path、line_start（必填），vulnerability_type、title（可选）。
返回：
- in_queue: 是否在队列中
- queue_size: 当前队列大小
- task_id: 任务ID"""

    @property
    def args_schema(self):
        return IsFindingInQueueInput

    async def _execute(
        self,
        file_path: str,
        line_start: int,
        vulnerability_type: str = "",
        title: str = "",
        **kwargs,
    ) -> ToolResult:
        try:
            finding = {
                "file_path": file_path,
                "line_start": line_start,
                "vulnerability_type": vulnerability_type,
                "title": title,
            }
            in_queue = bool(self.queue_service.contains_finding(self.task_id, finding))
            queue_size = int(self.queue_service.get_queue_size(self.task_id))
            return ToolResult(
                success=True,
                data={
                    "in_queue": in_queue,
                    "queue_size": queue_size,
                    "task_id": self.task_id,
                },
            )
        except Exception as e:
            logger.error(f"[Queue] Failed to check finding in queue: {e}")
            return ToolResult(
                success=False,
                error=str(e),
                data={"in_queue": False},
            )


class PushFindingToQueueInput(BaseModel):
    """推送漏洞到队列输入参数"""
    file_path: str = Field(..., description="漏洞所在文件路径")
    line_start: int = Field(..., description="起始行号")
    line_end: Optional[int] = Field(default=None, description="结束行号")
    title: str = Field(..., description="漏洞标题")
    description: str = Field(..., description="漏洞描述")
    vulnerability_type: str = Field(..., description="漏洞类型")
    severity: str = Field(
        default="medium",
        description="严重程度: critical, high, medium, low, info"
    )
    confidence: float = Field(
        default=0.8,
        description="置信度 0.0-1.0"
    )


class PushFindingToQueueTool(AgentTool):
    """Analysis Agent 使用：将发现的漏洞推送到队列"""

    def __init__(self, queue_service, task_id: str):
        """
        Args:
            queue_service: VulnerabilityQueue 实例
            task_id: 审计任务 ID
        """
        super().__init__()
        self.queue_service = queue_service
        self.task_id = task_id

    @property
    def name(self) -> str:
        return "push_finding_to_queue"

    @property
    def description(self) -> str:
        return """将 Analysis Agent 发现的漏洞推送到全局队列。

推送的漏洞将由 Orchestrator 调度 Verification Agent 进行验证。

必需参数:
- file_path: 文件路径
- line_start: 起始行号
- title: 漏洞标题
- description: 漏洞描述
- vulnerability_type: 漏洞类型

可选参数:
- line_end: 结束行号
- severity: 严重程度 (默认: medium)
- confidence: 置信度 (默认: 0.8)

返回队列当前大小。"""

    @property
    def args_schema(self):
        return PushFindingToQueueInput

    async def _execute(
        self,
        file_path: str,
        line_start: int,
        title: str,
        description: str,
        vulnerability_type: str,
        line_end: Optional[int] = None,
        severity: str = "medium",
        confidence: float = 0.8,
        **kwargs
    ) -> ToolResult:
        """执行工具"""
        try:
            # 构造漏洞信息
            finding = {
                "file_path": file_path,
                "line_start": line_start,
                "line_end": line_end,
                "title": title,
                "description": description,
                "vulnerability_type": vulnerability_type,
                "severity": severity,
                "confidence": confidence,
            }
            
            success = self.queue_service.enqueue_finding(self.task_id, finding)
            
            if success:
                queue_size = self.queue_service.get_queue_size(self.task_id)
                logger.info(
                    f"[Queue] Finding enqueued for task {self.task_id}: "
                    f"{file_path} (queue size: {queue_size})"
                )
                return ToolResult(
                    success=True,
                    data={
                        "message": f"漏洞已入队，当前队列大小: {queue_size}",
                        "queue_size": queue_size,
                    }
                )
            else:
                logger.error(f"[Queue] Failed to enqueue finding for task {self.task_id}")
                return ToolResult(
                    success=False,
                    error="Failed to enqueue finding"
                )
        
        except Exception as e:
            logger.error(f"[Queue] Failed to push finding: {e}")
            return ToolResult(
                success=False,
                error=str(e)
            )
