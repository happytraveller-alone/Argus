"""
Agent Workflow 包

提供确定性 Recon → Analysis → Verification 审计工作流。

用法示例::

    from app.services.agent.workflow import WorkflowOrchestratorAgent, AuditWorkflowEngine
    from app.services.agent.workflow.models import WorkflowPhase, WorkflowState

主要导出：
- ``WorkflowOrchestratorAgent`` - 替换 OrchestratorAgent 的确定性编排 Agent。
- ``AuditWorkflowEngine``        - 独立可复用的三阶段引擎（Recon/Analysis/Verification）。
- ``WorkflowPhase``              - 阶段枚举（INIT / RECON / ANALYSIS / VERIFICATION / COMPLETE / FAILED / CANCELLED）。
- ``WorkflowState``              - 运行时状态数据类。
- ``WorkflowStepRecord``         - 单步调度记录数据类。
"""

from .engine import AuditWorkflowEngine
from .models import WorkflowPhase, WorkflowState, WorkflowStepRecord
from .workflow_orchestrator import WorkflowOrchestratorAgent

__all__ = [
    "AuditWorkflowEngine",
    "WorkflowOrchestratorAgent",
    "WorkflowPhase",
    "WorkflowState",
    "WorkflowStepRecord",
]
