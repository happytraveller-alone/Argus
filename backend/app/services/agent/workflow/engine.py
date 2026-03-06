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
from .memory_monitor import MemoryMonitor

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
        
        # 🔥 内存监控
        self.memory_monitor = MemoryMonitor()
        self.enable_memory_monitoring = True  # 可配置的监控开关

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
        
        # 🔥 记录起始内存
        if self.enable_memory_monitoring:
            self.memory_monitor.take_snapshot(phase="init", agent_name="orchestrator")

        try:
            # ── 阶段 1: RECON ──────────────────────────────────────────────
            state.phase = WorkflowPhase.RECON
            await orc.emit_event("info", "🔎 [Workflow] 开始 Recon 阶段")
            await self._run_recon_phase(state)
            
            # 🔥 Recon 结束后调用 LLM 对风险点进行去重
            if state.recon_done and not orc.is_cancelled:
                await self._dedup_recon_risk_queue(self.task_id)
            
            # 🔥 记录 Recon 完成后的内存
            if self.enable_memory_monitoring:
                self.memory_monitor.take_snapshot(phase="recon_done", agent_name="recon")

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
            
            # 🔥 Analysis 阶段结束后调用 LLM 对漏洞进行去重
            if not orc.is_cancelled:
                await self._dedup_vuln_queue(self.task_id)
            
            # 🔥 记录 Analysis 完成后的内存
            if self.enable_memory_monitoring:
                self.memory_monitor.take_snapshot(phase="analysis_done", agent_name="analysis")

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
            
            # 🔥 记录 Verification 完成后的内存
            if self.enable_memory_monitoring:
                self.memory_monitor.take_snapshot(phase="verification_done", agent_name="verification")

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
            
            # 🔥 记录最终内存
            if self.enable_memory_monitoring:
                self.memory_monitor.take_snapshot(phase="complete", agent_name="orchestrator")
                self.memory_monitor.log_summary()


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
    # 去重方法
    # ─────────────────────────────────────────────────────────────────────────

    async def _dedup_recon_risk_queue(self, task_id: str) -> None:
        """
        在 Recon 结束后，调用大模型对队列中可能重复的风险项进行语义级去重。
        
        过程：
        1. 从队列中预览所有风险点
        2. 构建 prompt 让 LLM 识别重复项
        3. 根据 LLM 分析结果从队列中删除重复的项
        """
        orc = self.orchestrator
        
        try:
            # 获取队列中的所有风险点
            all_risk_points = self.recon_queue.peek(task_id, limit=1000)
            
            if not all_risk_points or len(all_risk_points) <= 1:
                logger.info("[WorkflowEngine] Recon queue has ≤1 items, skipping LLM dedup")
                return
            
            queue_size = self.recon_queue.size(task_id)
            await orc.emit_event(
                "info",
                f"🤖 [Workflow] 开始 Recon 风险点 LLM 去重：队列共 {queue_size} 条",
            )
            
            # 构建 prompt 让 LLM 分析可能重复的风险点
            risk_points_json = json.dumps(
                [
                    {
                        "id": i,
                        "file_path": rp.get("file_path", ""),
                        "line_start": rp.get("line_start", 0),
                        "description": rp.get("description", ""),
                        "severity": rp.get("severity", ""),
                        "vulnerability_type": rp.get("vulnerability_type", ""),
                    }
                    for i, rp in enumerate(all_risk_points[:50])  # 限制数量避免 token 过多
                ],
                ensure_ascii=False,
                indent=2,
            )
            
            dedup_prompt = f"""请分析以下风险点列表，识别其中**明确重复或基本相同**的项目。

风险点列表：
{risk_points_json}

分析标准：
1. 相同文件、相同或相邻行号、相同漏洞类型 → 重复
2. 相同文件、类似描述、相同漏洞类型 → 可能重复
3. 不同文件 → 即使描述相似也不算重复

请输出：
{{
  "duplicates": [
    {{"keep_id": 0, "remove_ids": [1, 2]}},
    ...
  ],
  "explanation": "简要说明去重原因"
}}

仅输出 JSON，不要其他内容。"""

            messages = [
                {
                    "role": "user",
                    "content": dedup_prompt,
                }
            ]
            
            # 调用 LLM
            logger.info("[WorkflowEngine] Calling LLM for Recon risk queue dedup...")
            llm_response, _ = await orc.stream_llm_call(messages)
            
            # 解析 LLM 响应
            dedup_result = self._parse_llm_dedup_response(llm_response)
            
            if not dedup_result or not dedup_result.get("duplicates"):
                logger.info("[WorkflowEngine] No duplicates identified by LLM")
                await orc.emit_event("info", "✅ [Workflow] Recon 风险点 LLM 去重：无重复项")
                return
            
            # 根据 LLM 分析结果删除重复的风险点
            removed_count = await self._remove_duplicate_recon_risk_points(
                task_id, dedup_result["duplicates"], all_risk_points
            )
            
            if removed_count > 0:
                await orc.emit_event(
                    "info",
                    f"✅ [Workflow] Recon 风险点 LLM 去重完成：移除 {removed_count} 条重复项",
                )
                logger.info("[WorkflowEngine] Removed %s duplicate recon risk points", removed_count)
            
        except Exception as exc:
            logger.warning("[WorkflowEngine] Recon queue LLM dedup failed: %s", exc)
            await orc.emit_event(
                "warning",
                f"⚠️ [Workflow] Recon 风险点 LLM 去重失败（非关键）：{str(exc)[:100]}",
            )

    async def _dedup_vuln_queue(self, task_id: str) -> None:
        """
        在 Analysis 阶段总体结束后，调用大模型对队列中可能重复的漏洞项进行语义级去重。
        
        过程：
        1. 从队列中预览所有漏洞
        2. 构建 prompt 让 LLM 识别重复漏洞
        3. 根据 LLM 分析结果从队列中删除重复的漏洞
        """
        orc = self.orchestrator
        
        try:
            # 获取队列中的所有漏洞
            all_findings = self.vuln_queue.peek_queue(task_id, limit=1000)
            
            if not all_findings or len(all_findings) <= 1:
                logger.info("[WorkflowEngine] Vuln queue has ≤1 items, skipping LLM dedup")
                return
            
            queue_size = self.vuln_queue.get_queue_size(task_id)
            await orc.emit_event(
                "info",
                f"🤖 [Workflow] 开始漏洞队列 LLM 去重：队列共 {queue_size} 条",
            )
            
            # 构建 prompt 让 LLM 分析可能重复的漏洞
            findings_json = json.dumps(
                [
                    {
                        "id": i,
                        "title": f.get("title", ""),
                        "file_path": f.get("file_path", ""),
                        "line_start": f.get("line_start", 0),
                        "vulnerability_type": f.get("vulnerability_type", ""),
                        "severity": f.get("severity", ""),
                        "description": (f.get("description", "")[:100]),  # 截断长描述
                    }
                    for i, f in enumerate(all_findings[:50])  # 限制数量避免 token 过多
                ],
                ensure_ascii=False,
                indent=2,
            )
            
            dedup_prompt = f"""请分析以下漏洞列表，识别其中**明确重复或基本相同**的项目。

漏洞列表：
{findings_json}

分析标准：
1. 相同文件、相同或相邻行号、相同漏洞类型、相同标题 → 重复
2. 相同文件、相同漏洞类型、相似标题和描述 → 可能重复
3. 不同文件但相同漏洞类型和标题 → 需要判断是否为同一根本原因
4. 即使描述稍有不同，如果是同一漏洞就认为重复

请输出：
{{
  "duplicates": [
    {{"keep_id": 0, "remove_ids": [1, 2]}},
    ...
  ],
  "explanation": "简要说明去重原因"
}}

仅输出 JSON，不要其他内容。"""

            messages = [
                {
                    "role": "user",
                    "content": dedup_prompt,
                }
            ]
            
            # 调用 LLM
            logger.info("[WorkflowEngine] Calling LLM for vulnerability queue dedup...")
            llm_response, _ = await orc.stream_llm_call(messages)
            
            # 解析 LLM 响应
            dedup_result = self._parse_llm_dedup_response(llm_response)
            
            if not dedup_result or not dedup_result.get("duplicates"):
                logger.info("[WorkflowEngine] No duplicates identified by LLM")
                await orc.emit_event("info", "✅ [Workflow] 漏洞队列 LLM 去重：无重复项")
                return
            
            # 根据 LLM 分析结果删除重复的漏洞
            removed_count = await self._remove_duplicate_findings(
                task_id, dedup_result["duplicates"], all_findings
            )
            
            if removed_count > 0:
                await orc.emit_event(
                    "info",
                    f"✅ [Workflow] 漏洞队列 LLM 去重完成：移除 {removed_count} 条重复项",
                )
                logger.info("[WorkflowEngine] Removed %s duplicate findings", removed_count)
            
        except Exception as exc:
            logger.warning("[WorkflowEngine] Vuln queue LLM dedup failed: %s", exc)
            await orc.emit_event(
                "warning",
                f"⚠️ [Workflow] 漏洞队列 LLM 去重失败（非关键）：{str(exc)[:100]}",
            )

    @staticmethod
    def _parse_llm_dedup_response(response: str) -> Optional[Dict[str, Any]]:
        """从 LLM 响应中解析去重结果"""
        try:
            # 尝试直接解析 JSON
            text = response.strip()
            # 如果响应有 markdown 代码块，提取 JSON 部分
            if "```" in text:
                import re
                json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
                if json_match:
                    text = json_match.group(1)
            
            result = json.loads(text)
            return result if isinstance(result, dict) else None
        except Exception as exc:
            logger.warning("[WorkflowEngine] Failed to parse LLM dedup response: %s", exc)
            return None

    async def _remove_duplicate_recon_risk_points(
        self,
        task_id: str,
        duplicates: List[Dict[str, Any]],
        all_risk_points: List[Dict[str, Any]],
    ) -> int:
        """根据 LLM 分析结果，从 Recon 风险队列中删除重复的风险点"""
        removed_count = 0
        ids_to_remove = set()
        
        for dup_group in duplicates:
            if isinstance(dup_group, dict) and "remove_ids" in dup_group:
                for remove_id in dup_group.get("remove_ids", []):
                    ids_to_remove.add(remove_id)
        
        # 由于队列的 peek 返回的是副本，我们需要重建队列
        # 这里的策略是：重新清空队列，然后只添加非重复的项
        if ids_to_remove:
            try:
                # 获取当前队列的所有项
                current_items = []
                while True:
                    item = self.recon_queue.dequeue(task_id)
                    if item is None:
                        break
                    current_items.append(item)
                
                # 根据原始 peek 结果中的 ID 确定哪些要保留
                # 这里假设 current_items 的顺序与 all_risk_points 相同
                kept_items = []
                for i, item in enumerate(current_items[:len(all_risk_points)]):
                    if i not in ids_to_remove:
                        kept_items.append(item)
                    else:
                        removed_count += 1
                
                # 重新加入保留的项
                for item in kept_items:
                    self.recon_queue.enqueue(task_id, item)
                
            except Exception as exc:
                logger.error("[WorkflowEngine] Failed to remove duplicate recon risk points: %s", exc)
        
        return removed_count

    async def _remove_duplicate_findings(
        self,
        task_id: str,
        duplicates: List[Dict[str, Any]],
        all_findings: List[Dict[str, Any]],
    ) -> int:
        """根据 LLM 分析结果，从漏洞队列中删除重复的漏洞"""
        removed_count = 0
        ids_to_remove = set()
        
        for dup_group in duplicates:
            if isinstance(dup_group, dict) and "remove_ids" in dup_group:
                for remove_id in dup_group.get("remove_ids", []):
                    ids_to_remove.add(remove_id)
        
        # 从漏洞队列中删除重复的项
        if ids_to_remove:
            try:
                # 获取当前队列的所有项
                current_items = []
                while True:
                    item = self.vuln_queue.dequeue_finding(task_id)
                    if item is None:
                        break
                    current_items.append(item)
                
                # 根据原始 peek 结果中的 ID 确定哪些要保留
                kept_items = []
                for i, item in enumerate(current_items[:len(all_findings)]):
                    if i not in ids_to_remove:
                        kept_items.append(item)
                    else:
                        removed_count += 1
                
                # 重新加入保留的项
                for item in kept_items:
                    self.vuln_queue.enqueue_finding(task_id, item)
                
            except Exception as exc:
                logger.error("[WorkflowEngine] Failed to remove duplicate findings: %s", exc)
        
        return removed_count

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
        
        # 🔥 清理 Recon Agent 的会话内存
        recon_agent = orc.sub_agents.get("recon")
        if recon_agent:
            recon_agent.reset_session_memory()
            logger.debug("[WorkflowEngine] Recon Agent session memory reset after phase completed")

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
            
            # 🔥 记录 Analysis 迭代前的内存
            if self.enable_memory_monitoring:
                self.memory_monitor.take_snapshot(phase="analysis", iteration=iteration, agent_name="analysis")

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
            
            # 🔥 清理 Analysis Agent 的会话内存，实现任务级隔离
            analysis_agent = orc.sub_agents.get("analysis")
            if analysis_agent:
                analysis_agent.reset_session_memory()
                logger.debug(
                    "[WorkflowEngine] Analysis Agent session memory reset after iteration %s",
                    iteration,
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
            
            # 🔥 记录 Verification 迭代前的内存
            if self.enable_memory_monitoring:
                self.memory_monitor.take_snapshot(phase="verification", iteration=iteration, agent_name="verification")

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
            
            # 🔥 清理 Verification Agent 的会话内存，实现任务级隔离
            verification_agent = orc.sub_agents.get("verification")
            if verification_agent:
                verification_agent.reset_session_memory()
                logger.debug(
                    "[WorkflowEngine] Verification Agent session memory reset after iteration %s",
                    iteration,
                )

        logger.info(
            "[WorkflowEngine] Verification phase done: %s finding(s) processed, final findings=%s",
            state.vuln_queue_findings_processed,
            len(orc._all_findings),
        )
