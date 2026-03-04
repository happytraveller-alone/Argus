"""
AuditWorkflowEngine - 确定性审计工作流引擎

将 Recon → Analysis（逐条处理 Recon 风险点队列）→ Verification（逐条处理漏洞验证队列）
改写为显式 Workflow 驱动，消除 LLM 对调度顺序的不确定性。

设计要点：
- 不替换各子 Agent 内部的 LLM ReAct 推理，只替换"Orchestrator 决定下一步"的部分。
- 直接操作队列服务（InMemoryReconRiskQueue / InMemoryVulnerabilityQueue），而非通过工具接口。
- 通过 orchestrator 引用调用 _dispatch_agent / _normalize_finding 等现有方法，保持行为一致。
- Verification 阶段以队列为权威（queue-authoritative），不跳过任何已入队漏洞。
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .models import WorkflowPhase, WorkflowState, WorkflowStepRecord

if TYPE_CHECKING:
    from ..agents.orchestrator import OrchestratorAgent

logger = logging.getLogger(__name__)


class AuditWorkflowEngine:
    """
    确定性审计工作流引擎。

    调用方式::

        engine = AuditWorkflowEngine(
            recon_queue_service=recon_queue,
            vuln_queue_service=vuln_queue,
            task_id=task_id,
            orchestrator=orchestrator_agent_instance,
        )
        state = await engine.run(project_info, config, project_root, task_id)

    引擎会依次执行三个阶段，每个阶段结束后更新 WorkflowState。
    """

    def __init__(
        self,
        recon_queue_service: Any,
        vuln_queue_service: Any,
        task_id: str,
        orchestrator: "OrchestratorAgent",
    ) -> None:
        """
        Args:
            recon_queue_service: InMemoryReconRiskQueue 或 RedisReconRiskQueue 实例。
            vuln_queue_service:  InMemoryVulnerabilityQueue 或 RedisVulnerabilityQueue 实例。
            task_id:             当前审计任务 ID（队列 key 隔离）。
            orchestrator:        父 OrchestratorAgent 实例，用于调用 _dispatch_agent 等方法。
        """
        self.recon_queue = recon_queue_service
        self.vuln_queue = vuln_queue_service
        self.task_id = task_id
        self.orchestrator = orchestrator

    # ─────────────────────────────────────────────────────────────────────────
    # 公开入口
    # ─────────────────────────────────────────────────────────────────────────

    async def run(
        self,
        project_info: Dict[str, Any],
        config: Dict[str, Any],
        project_root: str,
        task_id: str,
    ) -> WorkflowState:
        """
        执行完整审计 Workflow，返回最终 WorkflowState。

        Workflow 阶段顺序：
            INIT → RECON → ANALYSIS（per risk point）→ VERIFICATION（per finding）→ COMPLETE
        """
        state = WorkflowState()
        orc = self.orchestrator

        try:
            # ── 阶段 1: RECON ──────────────────────────────────────────────
            state.phase = WorkflowPhase.RECON
            await orc.emit_event("info", "🔎 [Workflow] 开始 Recon 阶段")
            await self._run_recon_phase(state)

            if orc.is_cancelled:
                state.phase = WorkflowPhase.CANCELLED
                return state

            # ── 阶段 2: ANALYSIS（逐条消耗 Recon 风险点队列）───────────────
            state.phase = WorkflowPhase.ANALYSIS
            recon_queue_size = self.recon_queue.size(task_id)
            state.analysis_risk_points_total = recon_queue_size
            await orc.emit_event(
                "info",
                f"🔍 [Workflow] 开始 Analysis 阶段，Recon 队列共 {recon_queue_size} 条风险点",
            )
            await self._run_analysis_phase(state, task_id)

            if orc.is_cancelled:
                state.phase = WorkflowPhase.CANCELLED
                return state

            # ── 阶段 3: VERIFICATION（逐条消耗漏洞验证队列）────────────────
            state.phase = WorkflowPhase.VERIFICATION
            vuln_queue_size = self.vuln_queue.get_queue_size(task_id)
            state.vuln_queue_findings_total = vuln_queue_size
            await orc.emit_event(
                "info",
                f"🛡️ [Workflow] 开始 Verification 阶段，漏洞队列共 {vuln_queue_size} 条",
            )
            await self._run_verification_phase(state, task_id)

            if orc.is_cancelled:
                state.phase = WorkflowPhase.CANCELLED
                return state

            # ── 完成 ──────────────────────────────────────────────────────
            state.phase = WorkflowPhase.COMPLETE
            state.all_findings = list(orc._all_findings)  # 同步最终发现
            await orc.emit_event(
                "info",
                f"✅ [Workflow] 所有阶段完成，共收集 {len(state.all_findings)} 个发现",
            )

        except asyncio.CancelledError:
            state.phase = WorkflowPhase.CANCELLED
            state.all_findings = list(orc._all_findings)
            logger.info("[WorkflowEngine] Workflow cancelled")

        except Exception as exc:
            logger.exception("[WorkflowEngine] Unexpected error: %s", exc)
            state.phase = WorkflowPhase.FAILED
            state.error = str(exc)
            state.all_findings = list(orc._all_findings)

        return state

    # ─────────────────────────────────────────────────────────────────────────
    # 阶段实现
    # ─────────────────────────────────────────────────────────────────────────

    async def _run_recon_phase(self, state: WorkflowState) -> None:
        """调度 Recon Agent 一次（Recon Agent 内部会将风险点推送到 recon_risk_queue）。"""
        orc = self.orchestrator
        step_start = time.time()

        params = {
            "agent": "recon",
            "task": "收集项目信息、识别技术栈与高风险区域，并将风险点推送到 Recon 队列",
        }
        try:
            observation = await orc._dispatch_agent(params)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[WorkflowEngine] Recon phase failed: %s", exc)
            observation = f"Recon 执行异常: {exc}"

        duration_ms = int((time.time() - step_start) * 1000)
        recon_success = bool(
            orc._agent_results.get("recon", {}).get("_run_success")
        )
        state.recon_done = recon_success
        state.step_records.append(
            WorkflowStepRecord(
                phase=WorkflowPhase.RECON,
                agent="recon",
                success=recon_success,
                error=None if recon_success else orc._agent_results.get("recon", {}).get("_run_error"),
                findings_count=len(orc._all_findings),
                duration_ms=duration_ms,
            )
        )
        logger.info(
            "[WorkflowEngine] Recon phase done: success=%s, all_findings_so_far=%s",
            recon_success,
            len(orc._all_findings),
        )

    async def _run_analysis_phase(self, state: WorkflowState, task_id: str) -> None:
        """
        从 Recon 风险点队列逐条取出风险点，每取一条就调度一次 Analysis Agent。
        队列取空后退出。
        """
        orc = self.orchestrator
        iteration = 0

        while True:
            if orc.is_cancelled:
                break

            risk_point = self.recon_queue.dequeue(task_id)
            if risk_point is None:
                logger.info(
                    "[WorkflowEngine] Recon risk queue drained at iteration %s", iteration
                )
                break

            iteration += 1
            state.analysis_risk_points_processed += 1
            state.total_iterations += 1

            fp_repr = (
                f"{risk_point.get('file_path', '')}:{risk_point.get('line_start', '')}"
            )
            await orc.emit_event(
                "info",
                f"🔍 [Workflow] Analysis 第 {iteration} 轮：风险点 {fp_repr}",
            )

            step_start = time.time()
            params = {
                "agent": "analysis",
                "task": f"针对风险点 {fp_repr} 进行深度代码审计",
                "risk_point": risk_point,
                "context": json.dumps(risk_point, ensure_ascii=False),
            }

            # 通知 orchestrator 当前注入的风险点（用于其内部 injection 逻辑）
            orc._last_recon_risk_point = risk_point

            try:
                await orc._dispatch_agent(params)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "[WorkflowEngine] Analysis dispatch failed for %s: %s", fp_repr, exc
                )
            finally:
                orc._last_recon_risk_point = None

            duration_ms = int((time.time() - step_start) * 1000)
            analysis_result = orc._agent_results.get("analysis", {})
            analysis_success = bool(analysis_result.get("_run_success"))

            state.step_records.append(
                WorkflowStepRecord(
                    phase=WorkflowPhase.ANALYSIS,
                    agent="analysis",
                    injected_context=risk_point,
                    success=analysis_success,
                    error=None if analysis_success else analysis_result.get("_run_error"),
                    findings_count=len(orc._all_findings),
                    duration_ms=duration_ms,
                )
            )
            logger.info(
                "[WorkflowEngine] Analysis iteration %s done: risk_point=%s, success=%s, cumulative_findings=%s",
                iteration,
                fp_repr,
                analysis_success,
                len(orc._all_findings),
            )

        logger.info(
            "[WorkflowEngine] Analysis phase done: %s risk point(s) processed, cumulative findings=%s",
            state.analysis_risk_points_processed,
            len(orc._all_findings),
        )

    async def _run_verification_phase(self, state: WorkflowState, task_id: str) -> None:
        """
        从漏洞验证队列（VulnerabilityQueue）逐条取出漏洞，每取一条调度 Verification Agent。
        遵循「队列权威」规则：队列中所有漏洞必须被验证，不得跳过。
        """
        orc = self.orchestrator
        iteration = 0

        while True:
            if orc.is_cancelled:
                break

            finding = self.vuln_queue.dequeue_finding(task_id)
            if finding is None:
                logger.info(
                    "[WorkflowEngine] Vulnerability queue drained at iteration %s", iteration
                )
                break

            iteration += 1
            state.vuln_queue_findings_processed += 1
            state.total_iterations += 1

            # 指纹去重：已验证过的跳过
            fingerprint = orc._build_queue_fingerprint(finding)
            if fingerprint and fingerprint in orc._verified_queue_fingerprints:
                await orc.emit_event(
                    "info",
                    f"⏭️ [Workflow] Verification 跳过重复指纹: {fingerprint[:60]}",
                )
                state.step_records.append(
                    WorkflowStepRecord(
                        phase=WorkflowPhase.VERIFICATION,
                        agent="verification",
                        injected_context=finding,
                        success=True,
                        error=None,
                        findings_count=len(orc._all_findings),
                        duration_ms=0,
                    )
                )
                continue

            title_repr = finding.get("title") or finding.get("file_path", "unknown")
            await orc.emit_event(
                "info",
                f"🛡️ [Workflow] Verification 第 {iteration} 轮：{title_repr}",
            )

            step_start = time.time()
            params = {
                "agent": "verification",
                "task": f"验证漏洞：{title_repr}",
                "finding": finding,
                "context": json.dumps(finding, ensure_ascii=False),
            }

            try:
                await orc._dispatch_agent(params)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(
                    "[WorkflowEngine] Verification dispatch failed for %s: %s",
                    title_repr,
                    exc,
                )

            duration_ms = int((time.time() - step_start) * 1000)
            verification_result = orc._agent_results.get("verification", {})
            verification_success = bool(verification_result.get("_run_success"))

            # 验证成功后记录指纹，避免重复验证
            if verification_success and fingerprint:
                orc._verified_queue_fingerprints.add(fingerprint)

            state.step_records.append(
                WorkflowStepRecord(
                    phase=WorkflowPhase.VERIFICATION,
                    agent="verification",
                    injected_context=finding,
                    success=verification_success,
                    error=None if verification_success else verification_result.get("_run_error"),
                    findings_count=len(orc._all_findings),
                    duration_ms=duration_ms,
                )
            )
            logger.info(
                "[WorkflowEngine] Verification iteration %s done: finding=%s, success=%s, cumulative_findings=%s",
                iteration,
                title_repr,
                verification_success,
                len(orc._all_findings),
            )

        logger.info(
            "[WorkflowEngine] Verification phase done: %s finding(s) processed, final findings=%s",
            state.vuln_queue_findings_processed,
            len(orc._all_findings),
        )
