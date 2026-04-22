"""
Orchestrator 漏洞队列管理工具
"""

import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from ..finding_payload_runtime import normalize_push_finding_payload
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
    function_name: Optional[str] = Field(default=None, description="函数名")
    code_snippet: Optional[str] = Field(default=None, description="漏洞代码片段")
    source: Optional[str] = Field(default=None, description="污点源或攻击入口")
    sink: Optional[str] = Field(default=None, description="危险点或敏感操作")
    suggestion: Optional[str] = Field(default=None, description="修复建议")
    evidence_chain: Optional[List[str]] = Field(default=None, description="证据链列表")
    attacker_flow: Optional[str] = Field(default=None, description="攻击路径描述")
    missing_checks: Optional[List[str]] = Field(default=None, description="缺失校验列表")
    taint_flow: Optional[List[str]] = Field(default=None, description="污点传播链路")
    finding_metadata: Optional[Dict[str, Any]] = Field(default=None, description="附加元数据")


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
- function_name/code_snippet/source/sink/suggestion: 富证据字段
- evidence_chain/attacker_flow/missing_checks/taint_flow: 证据与路径字段
- finding_metadata: 额外元数据

返回队列当前大小。"""

    @property
    def args_schema(self):
        return PushFindingToQueueInput

    @staticmethod
    def _flatten_finding_payload(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(kwargs or {})
        nested = payload.get("finding")
        if isinstance(nested, dict):
            for key, value in nested.items():
                payload.setdefault(str(key), value)
        payload.pop("finding", None)
        return payload

    async def _execute(
        self,
        file_path: Optional[str] = None,
        line_start: Optional[int] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        vulnerability_type: Optional[str] = None,
        line_end: Optional[int] = None,
        severity: str = "medium",
        confidence: float = 0.8,
        function_name: Optional[str] = None,
        code_snippet: Optional[str] = None,
        source: Optional[str] = None,
        sink: Optional[str] = None,
        suggestion: Optional[str] = None,
        evidence_chain: Optional[List[str]] = None,
        attacker_flow: Optional[str] = None,
        missing_checks: Optional[List[str]] = None,
        taint_flow: Optional[List[str]] = None,
        finding_metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> ToolResult:
        """执行工具"""
        normalized_kwargs, _ = normalize_push_finding_payload(
            {
                "file_path": file_path,
                "line_start": line_start,
                "line_end": line_end,
                "title": title,
                "description": description,
                "vulnerability_type": vulnerability_type,
                "severity": severity,
                "confidence": confidence,
                "function_name": function_name,
                "code_snippet": code_snippet,
                "source": source,
                "sink": sink,
                "suggestion": suggestion,
                "evidence_chain": evidence_chain,
                "attacker_flow": attacker_flow,
                "missing_checks": missing_checks,
                "taint_flow": taint_flow,
                "finding_metadata": finding_metadata,
                **self._flatten_finding_payload(kwargs),
            }
        )
        if file_path in (None, ""):
            file_path = normalized_kwargs.get("file_path")
        if line_start in (None, ""):
            line_start = normalized_kwargs.get("line_start")
        if line_end in (None, ""):
            line_end = normalized_kwargs.get("line_end")
        if title in (None, ""):
            title = normalized_kwargs.get("title")
        if description in (None, ""):
            description = normalized_kwargs.get("description")
        if vulnerability_type in (None, ""):
            vulnerability_type = normalized_kwargs.get("vulnerability_type")
        if str(severity or "").strip() in {"", "medium"}:
            severity = str(normalized_kwargs.get("severity") or severity or "medium")
        if "confidence" in normalized_kwargs:
            confidence = normalized_kwargs.get("confidence")
        function_name = str(normalized_kwargs.get("function_name") or function_name or "").strip() or None
        code_snippet = str(normalized_kwargs.get("code_snippet") or code_snippet or "").strip() or None
        source = str(normalized_kwargs.get("source") or source or "").strip() or None
        sink = str(normalized_kwargs.get("sink") or sink or "").strip() or None
        suggestion = str(normalized_kwargs.get("suggestion") or suggestion or "").strip() or None
        attacker_flow = str(normalized_kwargs.get("attacker_flow") or attacker_flow or "").strip() or None
        evidence_chain = list(normalized_kwargs.get("evidence_chain") or evidence_chain or [])
        missing_checks = list(normalized_kwargs.get("missing_checks") or missing_checks or [])
        taint_flow = list(normalized_kwargs.get("taint_flow") or taint_flow or [])
        metadata_payload = normalized_kwargs.get("finding_metadata")
        finding_metadata = dict(metadata_payload) if isinstance(metadata_payload, dict) else None

        file_path = str(file_path or "").strip()
        title = str(title or "").strip()
        description = str(description or "").strip()
        vulnerability_type = str(vulnerability_type or "").strip()
        severity = str(severity or "medium").strip().lower()

        try:
            line_start = int(line_start) if line_start is not None else 0
        except Exception:
            line_start = 0
        try:
            line_end = int(line_end) if line_end is not None else None
        except Exception:
            line_end = None
        try:
            confidence = float(confidence)
        except Exception:
            confidence = -1.0

        # 简单参数校验，确保必填字段有值，并给出正确参数示例
        errors = []
        if not file_path or not file_path.strip():
            errors.append("file_path 不能为空")
        if line_start <= 0:
            errors.append("line_start 必须为正整数")
        if not title or not title.strip():
            errors.append("title 不能为空")
        if not description or not description.strip():
            errors.append("description 不能为空")
        if not vulnerability_type or not vulnerability_type.strip():
            errors.append("vulnerability_type 不能为空")
        allowed_severities = {"critical", "high", "medium", "low", "info"}
        if severity not in allowed_severities:
            errors.append(f"severity 必须是 {sorted(allowed_severities)} 之一")
        if not (0.0 <= confidence <= 1.0):
            errors.append("confidence 必须在 0.0 到 1.0 之间")

        if errors:
            expected_args = {
                "file_path": "path/to/file.py",
                "line_start": 123,
                "line_end": 130,
                "title": "path/to/file.py中foo函数XX漏洞",
                "description": "请用简体中文描述漏洞的影响、输入和代码位置",
                "vulnerability_type": "sql_injection",
                "severity": "high",
                "confidence": 0.85,
                "function_name": "foo",
                "code_snippet": "dangerous_call(user_input)",
                "source": "request.form['id']",
                "sink": "cursor.execute",
                "suggestion": "改用参数化查询",
                "evidence_chain": ["代码片段", "数据流分析"],
                "attacker_flow": "HTTP 请求 -> login -> cursor.execute",
            }
            error_msg = "; ".join(errors)
            logger.warning(f"[Queue] 参数校验失败: {error_msg}")
            return ToolResult(
                success=False,
                error="参数校验失败",
                data={
                    "message": error_msg,
                    "expected_args": expected_args,
                },
            )

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
            if function_name:
                finding["function_name"] = function_name
            if code_snippet:
                finding["code_snippet"] = code_snippet
            if source:
                finding["source"] = source
            if sink:
                finding["sink"] = sink
            if suggestion:
                finding["suggestion"] = suggestion
            if attacker_flow:
                finding["attacker_flow"] = attacker_flow
            if evidence_chain:
                finding["evidence_chain"] = evidence_chain
            if missing_checks:
                finding["missing_checks"] = missing_checks
            if taint_flow:
                finding["taint_flow"] = taint_flow
            if finding_metadata:
                finding["finding_metadata"] = finding_metadata

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
