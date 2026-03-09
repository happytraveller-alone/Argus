"""
Workflow 数据模型

定义审计 Workflow 的阶段、状态、记录类型，供 engine 和 WorkflowOrchestratorAgent 共用。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


@dataclass
class WorkflowConfig:
    """
    Workflow 执行配置

    控制并行化行为和 worker 数量
    """
    enable_parallel_analysis: bool = True
    enable_parallel_verification: bool = True
    analysis_max_workers: int = 5
    verification_max_workers: int = 3

    @property
    def should_parallelize_analysis(self) -> bool:
        """是否应该并行化 Analysis（workers > 1 且启用）"""
        return self.enable_parallel_analysis and self.analysis_max_workers > 1

    @property
    def should_parallelize_verification(self) -> bool:
        """是否应该并行化 Verification（workers > 1 且启用）"""
        return self.enable_parallel_verification and self.verification_max_workers > 1


class WorkflowPhase(Enum):
    """审计 Workflow 阶段"""
    INIT = "init"
    RECON = "recon"
    ANALYSIS = "analysis"
    VERIFICATION = "verification"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStepRecord:
    """单次子 Agent 调度记录（用于可审计追踪）"""
    phase: WorkflowPhase
    agent: str

    # 本次调度注入的上下文（风险点 / 漏洞 / 无）
    injected_context: Optional[Dict[str, Any]] = None

    success: bool = False
    error: Optional[str] = None
    findings_count: int = 0       # 本次调度后累积发现数
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "agent": self.agent,
            "injected_context": self.injected_context,
            "success": self.success,
            "error": self.error,
            "findings_count": self.findings_count,
            "duration_ms": self.duration_ms,
        }


@dataclass
class WorkflowState:
    """整个 Workflow 运行时状态快照"""

    phase: WorkflowPhase = WorkflowPhase.INIT

    # Recon
    recon_done: bool = False

    # Analysis（对应 Recon 风险点队列）
    analysis_risk_points_total: int = 0
    analysis_risk_points_processed: int = 0

    # Verification（对应漏洞验证队列）
    vuln_queue_findings_total: int = 0
    vuln_queue_findings_processed: int = 0

    # 已验证指纹去重集合
    verified_fingerprints: Set[str] = field(default_factory=set)

    # 所有收集到的发现
    all_findings: List[Dict[str, Any]] = field(default_factory=list)

    # 每步调度记录
    step_records: List[WorkflowStepRecord] = field(default_factory=list)

    # 错误信息（仅 FAILED 时非空）
    error: Optional[str] = None

    # 统计
    total_iterations: int = 0
    total_tokens: int = 0
    tool_calls: int = 0

    def to_summary(self) -> Dict[str, Any]:
        """生成供日志/返回值使用的摘要字典"""
        return {
            "phase": self.phase.value,
            "recon_done": self.recon_done,
            "analysis_risk_points_total": self.analysis_risk_points_total,
            "analysis_risk_points_processed": self.analysis_risk_points_processed,
            "vuln_queue_findings_total": self.vuln_queue_findings_total,
            "vuln_queue_findings_processed": self.vuln_queue_findings_processed,
            "all_findings_count": len(self.all_findings),
            "step_records": [r.to_dict() for r in self.step_records],
            "error": self.error,
            "total_iterations": self.total_iterations,
            "total_tokens": self.total_tokens,
        }
