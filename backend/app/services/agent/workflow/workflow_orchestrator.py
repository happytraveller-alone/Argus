"""
WorkflowOrchestratorAgent - 基于确定性 Workflow 的编排 Agent

替换原 OrchestratorAgent 中以 LLM 驱动的 ReAct 循环，
改用 AuditWorkflowEngine 按照 Recon → Analysis → Verification 顺序确定性执行，
子 Agent（Recon / Analysis / Verification）内部仍使用 LLM+ReAct 进行深度分析。

兼容性说明：
  均完整继承。
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from ..agents.orchestrator import OrchestratorAgent
from ..agents.base import AgentResult
from .engine import AuditWorkflowEngine
from .models import WorkflowPhase, WorkflowState, WorkflowConfig

logger = logging.getLogger(__name__)


class WorkflowOrchestratorAgent(OrchestratorAgent):
    """
    基于 Workflow 的审计编排 Agent。

    使用方式与 OrchestratorAgent 完全相同，额外接受两个队列服务参数::

        agent = WorkflowOrchestratorAgent(
            llm_service=llm,
            tools=orchestrator_tools,
            event_emitter=emitter,
            sub_agents={"recon": recon, "analysis": analysis, "verification": verification},
            recon_queue_service=recon_queue,
            vuln_queue_service=vuln_queue,
        )
        result = await agent.run({
            "project_info": ...,
            "config": ...,
            "project_root": ...,
            "task_id": task_id,
        })
    """

    def __init__(
        self,
        llm_service,
        tools: Dict[str, Any],
        event_emitter=None,
        sub_agents: Optional[Dict] = None,
        tracer=None,
        recon_queue_service: Optional[Any] = None,
        vuln_queue_service: Optional[Any] = None,
        workflow_config: Optional[WorkflowConfig] = None,
    ) -> None:
        """
        Args:
            llm_service:           LLM 服务实例（与 OrchestratorAgent 相同）。
            tools:                 Orchestrator 工具集（think/reflect/queue tools 等）。
            event_emitter:         事件发射器（用于前端实时推送）。
            sub_agents:            子 Agent 字典 {"recon": ..., "analysis": ..., "verification": ...}。
            tracer:                遥测 Tracer（可选）。
            recon_queue_service:   InMemoryReconRiskQueue / RedisReconRiskQueue 实例。
                                   若为 None，则回退到 LLM-driven 模式（兼容旧行为）。
            vuln_queue_service:    InMemoryVulnerabilityQueue / RedisVulnerabilityQueue 实例。
                                   若为 None，则回退到 LLM-driven 模式。
            workflow_config:       Workflow 配置（控制并行化行为）。
        """
        super().__init__(
            llm_service=llm_service,
            tools=tools,
            event_emitter=event_emitter,
            sub_agents=sub_agents,
            tracer=tracer,
        )
        self._recon_queue_service = recon_queue_service
        self._vuln_queue_service = vuln_queue_service
        self._workflow_config = workflow_config or WorkflowConfig()

    # ------------------------------------------------------------------
    # 核心入口：覆盖父类 run()
    # ------------------------------------------------------------------

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        以 Workflow 模式执行编排任务。

        若队列服务未提供，则自动降级为父类 LLM-driven ReAct 编排（保持向后兼容）。
        """
        # ── 降级检测 ────────────────────────────────────────────────────
        if self._recon_queue_service is None or self._vuln_queue_service is None:
            logger.warning(
                "[WorkflowOrchestrator] Queue service(s) not provided, "
                "falling back to LLM-driven mode."
            )
            return await super().run(input_data)

        # ── input 解包 ───────────────────────────────────────────────────
        import time as _time
        start_time = _time.time()

        project_info = input_data.get("project_info", {}) if isinstance(input_data, dict) else {}
        config = input_data.get("config", {}) if isinstance(input_data, dict) else {}
        project_root = input_data.get("project_root", project_info.get("root", "."))
        task_id: str = input_data.get("task_id", "") or ""

        # ── 初始化父类运行时状态（与父类 run() 完全相同）────────────────
        self._runtime_context = {
            "project_info": project_info,
            "config": config,
            "project_root": project_root,
            "task_id": task_id,
        }
        self._steps = []
        self._all_findings = []
        self._agent_results = {}
        self._agent_handoffs = {}
        self._dispatched_tasks = {}
        self._phase_planning_applied = {}
        self._verified_queue_fingerprints = set()
        self._recon_queue_snapshot = {}
        self._last_recon_risk_point = None
        self._iteration = 0
        self._total_tokens = 0
        self._tool_calls = 0

        await self.emit_thinking("🧠 WorkflowOrchestrator 启动，执行确定性 Workflow 模式...")

        # ── 打印初始队列状态（调试用）───────────────────────────────────
        await self._log_queue_status("启动前")

        # ── 创建并执行 Workflow 引擎 ────────────────────────────────────
        engine = AuditWorkflowEngine(
            recon_queue_service=self._recon_queue_service,
            vuln_queue_service=self._vuln_queue_service,
            task_id=task_id,
            orchestrator=self,
            workflow_config=self._workflow_config,
        )

        workflow_state: WorkflowState = await engine.run(
            project_info=project_info,
            config=config,
            project_root=project_root,
            task_id=task_id,
        )

        # 同步统计
        self._iteration = workflow_state.total_iterations

        # ── 打印最终队列状态（调试用）───────────────────────────────────
        await self._log_queue_status("完成后")

        duration_ms = int((_time.time() - start_time) * 1000)

        # ── 处理取消 ────────────────────────────────────────────────────
        if workflow_state.phase == WorkflowPhase.CANCELLED or self.is_cancelled:
            await self.emit_event(
                "info",
                f"🛑 WorkflowOrchestrator 已取消: {len(self._all_findings)} 个发现",
            )
            return AgentResult(
                success=False,
                error="任务已取消",
                data={
                    "findings": self._all_findings,
                    "workflow_state": workflow_state.to_summary(),
                },
                iterations=self._iteration,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
            )

        # ── 处理失败 ────────────────────────────────────────────────────
        if workflow_state.phase == WorkflowPhase.FAILED:
            error_msg = workflow_state.error or "Workflow 执行失败"
            await self.emit_event("error", f"❌ WorkflowOrchestrator 失败: {error_msg}")
            return AgentResult(
                success=False,
                error=error_msg,
                data={
                    "findings": self._all_findings,
                    "workflow_state": workflow_state.to_summary(),
                },
                iterations=self._iteration,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
            )

        # ── Verification 降级兜底（与父类逻辑一致）─────────────────────
        verification_payload = self._agent_results.get("verification")
        if isinstance(verification_payload, dict):
            verification_findings = verification_payload.get("findings")
            if not isinstance(verification_findings, list) or not verification_findings:
                analysis_payload = self._agent_results.get("analysis")
                analysis_candidates = (
                    analysis_payload.get("findings")
                    if isinstance(analysis_payload, dict)
                    else []
                )
                degraded_verified = self._build_degraded_verified_findings(
                    analysis_candidates if isinstance(analysis_candidates, list) else [],
                    "verification_missing_or_empty_findings",
                )
                if degraded_verified:
                    for f in degraded_verified:
                        if isinstance(f, dict):
                            self._all_findings.append(f)
                    self._all_findings = self._dedup_findings(
                        [f for f in self._all_findings if isinstance(f, dict)]
                    )
                    logger.warning(
                        "[WorkflowOrchestrator] Degraded fallback applied: %s findings",
                        len(degraded_verified),
                    )

        # ── 最终摘要 ────────────────────────────────────────────────────
        await self.emit_event(
            "info",
            f"🎯 WorkflowOrchestrator 完成: {len(self._all_findings)} 个发现, "
            f"Recon 风险点 {workflow_state.analysis_risk_points_processed} 条已分析, "
            f"漏洞验证 {workflow_state.vuln_queue_findings_processed} 条已处理",
        )
        logger.info(
            "[WorkflowOrchestrator] Final result: %s findings collected",
            len(self._all_findings),
        )

        return AgentResult(
            success=True,
            data={
                "findings": self._all_findings,
                "summary": self._generate_default_summary(),
                "workflow_state": workflow_state.to_summary(),
                "steps": [r.to_dict() for r in workflow_state.step_records],
            },
            iterations=self._iteration,
            tool_calls=self._tool_calls,
            tokens_used=self._total_tokens,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # 辅助方法:打印队列状态
    # ------------------------------------------------------------------

    async def _log_queue_status(self, stage: str) -> None:
        """
        记录当前队列状态到日志（调试用）。

        Args:
            stage: 阶段标识（如 "启动前"、"完成后"）
        """
        try:
            task_id = self._runtime_context.get("task_id", "") if self._runtime_context else ""
            if not task_id:
                logger.debug("[QueueStatus] No task_id, skip queue status logging")
                return

            # Recon 队列状态
            recon_stats = {}
            if self._recon_queue_service:
                try:
                    recon_size = self._recon_queue_service.size(task_id)
                    recon_stats = self._recon_queue_service.stats(task_id)
                    logger.info(
                        "[QueueStatus|%s] Recon队列: size=%d, enqueued=%d, dequeued=%d, deduplicated=%d",
                        stage,
                        recon_size,
                        recon_stats.get("total_enqueued", 0),
                        recon_stats.get("total_dequeued", 0),
                        recon_stats.get("total_deduplicated", 0),
                    )
                except Exception as e:
                    logger.warning("[QueueStatus|%s] Failed to get recon queue stats: %s", stage, e)

            # Vulnerability 队列状态
            vuln_stats = {}
            if self._vuln_queue_service:
                try:
                    vuln_size = self._vuln_queue_service.size(task_id)
                    vuln_stats = self._vuln_queue_service.stats(task_id)
                    logger.info(
                        "[QueueStatus|%s] Vuln队列: size=%d, enqueued=%d, dequeued=%d, deduplicated=%d",
                        stage,
                        vuln_size,
                        vuln_stats.get("total_enqueued", 0),
                        vuln_stats.get("total_dequeued", 0),
                        vuln_stats.get("total_deduplicated", 0),
                    )
                except Exception as e:
                    logger.warning("[QueueStatus|%s] Failed to get vuln queue stats: %s", stage, e)

            # 如果在完成阶段，记录剩余项（可能表示未处理完）
            if stage == "完成后":
                if recon_stats.get("total_enqueued", 0) > 0 or vuln_stats.get("total_enqueued", 0) > 0:
                    recon_remaining = recon_stats.get("total_enqueued", 0) - recon_stats.get("total_dequeued", 0)
                    vuln_remaining = vuln_stats.get("total_enqueued", 0) - vuln_stats.get("total_dequeued", 0)
                    if recon_remaining > 0 or vuln_remaining > 0:
                        logger.warning(
                            "[QueueStatus|%s] ⚠️ 队列中有未处理项: Recon剩余=%d, Vuln剩余=%d",
                            stage,
                            recon_remaining,
                            vuln_remaining,
                        )

        except Exception as e:
            logger.error("[QueueStatus|%s] Failed to log queue status: %s", stage, e)
