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
    enable_parallel_report: bool = True
    analysis_max_workers: int = 3
    verification_max_workers: int = 3
    report_max_workers: int = 3
    bl_analysis_max_workers: int = 3

    @property
    def should_parallelize_analysis(self) -> bool:
        """是否应该并行化 Analysis（workers > 1 且启用）"""
        return self.enable_parallel_analysis and self.analysis_max_workers > 1

    @property
    def should_parallelize_verification(self) -> bool:
        """是否应该并行化 Verification（workers > 1 且启用）"""
        return self.enable_parallel_verification and self.verification_max_workers > 1

    @property
    def should_parallelize_report(self) -> bool:
        """是否应该并行化 Report（workers > 1 且启用）"""
        return self.enable_parallel_report and self.report_max_workers > 1

    @property
    def should_parallelize_bl_analysis(self) -> bool:
        """是否应该并行化 BusinessLogicAnalysis（workers > 1 且启用）"""
        return self.enable_parallel_analysis and self.bl_analysis_max_workers > 1


class WorkflowPhase(Enum):
    """审计 Workflow 阶段"""
    INIT = "init"
    RECON = "recon"
    BUSINESS_LOGIC_RECON = "business_logic_recon"
    ANALYSIS = "analysis"
    BUSINESS_LOGIC_ANALYSIS = "business_logic_analysis"
    VERIFICATION = "verification"
    REPORT = "report"
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

    # BusinessLogicRecon
    bl_recon_done: bool = False
    bl_risk_points_generated: int = 0
    bl_risk_points_deduped: int = 0

    # Analysis（对应 Recon 风险点队列）
    analysis_risk_points_total: int = 0
    analysis_risk_points_processed: int = 0

    # BusinessLogicAnalysis（对应 BL 风险点队列）
    bl_risk_points_total: int = 0
    bl_risk_points_processed: int = 0
    bl_analysis_confirmed_count: int = 0
    bl_analysis_false_positive_suspects: int = 0
    bl_findings_with_complete_evidence: int = 0
    bl_analysis_with_evidence: int = 0

    # Verification（对应漏洞验证队列）
    vuln_queue_findings_total: int = 0
    vuln_queue_findings_processed: int = 0

    # 已验证指纹去重集合
    verified_fingerprints: Set[str] = field(default_factory=set)

    # 所有收集到的发现
    all_findings: List[Dict[str, Any]] = field(default_factory=list)

    # Report 阶段：每条已验证漏洞的详情报告（finding_identity 或 title -> Markdown 报告内容）
    finding_reports: Dict[str, str] = field(default_factory=dict)

    # Report 阶段统计
    report_findings_total: int = 0
    report_findings_processed: int = 0

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
            "bl_recon_done": self.bl_recon_done,
            "bl_risk_points_generated": self.bl_risk_points_generated,
            "bl_risk_points_deduped": self.bl_risk_points_deduped,
            "analysis_risk_points_total": self.analysis_risk_points_total,
            "analysis_risk_points_processed": self.analysis_risk_points_processed,
            "bl_risk_points_total": self.bl_risk_points_total,
            "bl_risk_points_processed": self.bl_risk_points_processed,
            "bl_analysis_confirmed_count": self.bl_analysis_confirmed_count,
            "bl_analysis_false_positive_suspects": self.bl_analysis_false_positive_suspects,
            "bl_findings_with_complete_evidence": self.bl_findings_with_complete_evidence,
            "bl_analysis_with_evidence": self.bl_analysis_with_evidence,
            "vuln_queue_findings_total": self.vuln_queue_findings_total,
            "vuln_queue_findings_processed": self.vuln_queue_findings_processed,
            "all_findings_count": len(self.all_findings),
            "report_findings_total": self.report_findings_total,
            "report_findings_processed": self.report_findings_processed,
            "step_records": [r.to_dict() for r in self.step_records],
            "error": self.error,
            "total_iterations": self.total_iterations,
            "total_tokens": self.total_tokens,
        }
