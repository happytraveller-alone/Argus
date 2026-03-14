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
import copy
import json
import logging
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .models import WorkflowPhase, WorkflowState, WorkflowStepRecord, WorkflowConfig
from .memory_monitor import MemoryMonitor
from .parallel_executor import ParallelPhaseExecutor

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
        workflow_config: Optional[WorkflowConfig] = None,
        business_logic_queue_service: Optional[Any] = None,
    ) -> None:
        """
        Args:
            recon_queue_service: InMemoryReconRiskQueue 或 RedisReconRiskQueue 实例。
            vuln_queue_service:  InMemoryVulnerabilityQueue 或 RedisVulnerabilityQueue 实例。
            task_id:             当前审计任务 ID（队列 key 隔离）。
            orchestrator:        父 OrchestratorAgent 实例，用于调用 _dispatch_agent 等方法。
            workflow_config:     Workflow 配置（控制并行化行为）。
            business_logic_queue_service: InMemoryBusinessLogicRiskQueue 实例（可选）。
                                          若为 None，则跳过业务逻辑双轨道流程。
        """
        self.recon_queue = recon_queue_service
        self.vuln_queue = vuln_queue_service
        self.bl_queue = business_logic_queue_service
        self.task_id = task_id
        self.orchestrator = orchestrator
        self.workflow_config = workflow_config or WorkflowConfig()

        # 🔥 内存监控
        self.memory_monitor = MemoryMonitor()
        self.enable_memory_monitoring = True  # 可配置的监控开关

        # 🔥 初始化并行执行器
        self.analysis_executor = ParallelPhaseExecutor(
            orchestrator=orchestrator,
            agent_type="analysis",
            max_workers=self.workflow_config.analysis_max_workers,
            enable_parallel=self.workflow_config.should_parallelize_analysis,
        )

        self.verification_executor = ParallelPhaseExecutor(
            orchestrator=orchestrator,
            agent_type="verification",
            max_workers=self.workflow_config.verification_max_workers,
            enable_parallel=self.workflow_config.should_parallelize_verification,
        )

        self.report_executor = ParallelPhaseExecutor(
            orchestrator=orchestrator,
            agent_type="report",
            max_workers=self.workflow_config.report_max_workers,
            enable_parallel=self.workflow_config.should_parallelize_report,
        )

        # 🔥 业务逻辑分析并行执行器（仅在 bl_queue 存在时使用）
        self.bl_analysis_executor = ParallelPhaseExecutor(
            orchestrator=orchestrator,
            agent_type="business_logic_analysis",
            max_workers=self.workflow_config.bl_analysis_max_workers,
            enable_parallel=self.workflow_config.should_parallelize_bl_analysis,
        )

        logger.info(
            f"[WorkflowEngine] Initialized with parallel config: "
            f"analysis_workers={self.workflow_config.analysis_max_workers} "
            f"(enabled={self.workflow_config.should_parallelize_analysis}), "
            f"bl_analysis_workers={self.workflow_config.bl_analysis_max_workers} "
            f"(enabled={self.workflow_config.should_parallelize_bl_analysis}), "
            f"verification_workers={self.workflow_config.verification_max_workers} "
            f"(enabled={self.workflow_config.should_parallelize_verification}), "
            f"report_workers={self.workflow_config.report_max_workers} "
            f"(enabled={self.workflow_config.should_parallelize_report}), "
            f"bl_queue={'enabled' if business_logic_queue_service else 'disabled'}"
        )

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
            INIT
            → RECON（完成后）→ BUSINESS_LOGIC_RECON（顺序执行）
            → ANALYSIS + BUSINESS_LOGIC_ANALYSIS（asyncio.gather 并行，per risk point）
            → VERIFICATION（per finding）
            → REPORT（per confirmed/likely）
            → COMPLETE
        """
        state = WorkflowState()
        orc = self.orchestrator
        runtime_config = config if isinstance(config, dict) else {}
        audit_source_mode = str(runtime_config.get("audit_source_mode") or "hybrid").strip().lower()
        static_bootstrap_candidate_count = int(
            runtime_config.get("static_bootstrap_candidate_count") or 0
        )
        skip_recon_when_bootstrap_available = bool(
            runtime_config.get("skip_recon_when_bootstrap_available", True)
        )
        should_skip_recon_phase = (
            audit_source_mode == "hybrid"
            and skip_recon_when_bootstrap_available
            and static_bootstrap_candidate_count > 0
        )
        
        # 🔥 记录起始内存
        if self.enable_memory_monitoring:
            self.memory_monitor.take_snapshot(phase="init", agent_name="orchestrator")

        try:
            # ── 阶段 1: RECON ──────────────────────────────────────────────
            state.phase = WorkflowPhase.RECON
            if should_skip_recon_phase:
                seeded_count = 0
                bootstrap_findings = runtime_config.get("bootstrap_findings") or []
                for finding in bootstrap_findings:
                    if not isinstance(finding, dict):
                        continue
                    try:
                        enqueued = self.recon_queue.enqueue(task_id, finding)
                    except Exception:
                        enqueued = False
                    if enqueued:
                        seeded_count += 1

                state.recon_done = True
                state.step_records.append(
                    WorkflowStepRecord(
                        phase=WorkflowPhase.RECON,
                        agent="recon",
                        success=True,
                        error=None,
                        findings_count=len(orc._all_findings),
                        duration_ms=0,
                    )
                )
                await orc.emit_event(
                    "info",
                    (
                        "⏭️ [Workflow] 混合扫描检测到静态预扫结果，跳过 Recon 阶段，"
                        f"并注入 {seeded_count} 条候选进入 Analysis 队列"
                    ),
                )
                logger.info(
                    "[WorkflowEngine] Skip recon for hybrid mode: "
                    "static_bootstrap_candidate_count=%s seeded_to_recon_queue=%s",
                    static_bootstrap_candidate_count,
                    seeded_count,
                )
            else:
                await orc.emit_event("info", "🔎 [Workflow] 开始 Recon 阶段")
                await self._run_recon_phase(state)
            
            # 🔥 业务逻辑侦察阶段（与 Recon 相互独立，可并行；这里在 Recon 完成后启动）
            # 注意：由于 bootstrap 模式下 Recon 可能被跳过，BL Recon 不受影响，始终运行
            if self.bl_queue is not None and not orc.is_cancelled:
                has_bl_recon_agent = orc.sub_agents.get("business_logic_recon") is not None
                if has_bl_recon_agent:
                    await orc.emit_event("info", "🕵️ [Workflow] 开始 BusinessLogicRecon 阶段")
                    await self._run_business_logic_recon_phase(state, task_id)
                else:
                    logger.info("[WorkflowEngine] No business_logic_recon agent registered, skipping BL Recon phase")
                    await orc.emit_event("info", "⏭️ [Workflow] 未配置 BusinessLogicReconAgent，跳过 BL Recon 阶段")
            
            # 🔥 Recon 结束后调用 LLM 对风险点进行去重
            if state.recon_done and not orc.is_cancelled:
                await self._dedup_recon_risk_queue(self.task_id)

            # 🔥 BL Recon 结束后对业务逻辑风险点去重
            if state.bl_recon_done and not orc.is_cancelled and self.bl_queue is not None:
                await self._dedup_bl_risk_queue(self.task_id)
            
            # 🔥 记录 Recon 完成后的内存
            if self.enable_memory_monitoring:
                self.memory_monitor.take_snapshot(phase="recon_done", agent_name="recon")

            if orc.is_cancelled:
                state.phase = WorkflowPhase.CANCELLED
                return state

            # ── 阶段 2: ANALYSIS（逐条消耗 Recon 风险点队列）+ BUSINESS_LOGIC_ANALYSIS（并行）───
            state.phase = WorkflowPhase.ANALYSIS
            recon_queue_size = self.recon_queue.size(task_id)
            state.analysis_risk_points_total = recon_queue_size

            bl_queue_size = self.bl_queue.size(task_id) if self.bl_queue is not None else 0
            state.bl_risk_points_total = bl_queue_size

            has_bl_analysis = (
                self.bl_queue is not None
                and bl_queue_size > 0
                and orc.sub_agents.get("business_logic_analysis") is not None
            )

            if has_bl_analysis:
                await orc.emit_event(
                    "info",
                    f"🔍 [Workflow] 开始 Analysis + BusinessLogicAnalysis 并行阶段，"
                    f"Recon 队列 {recon_queue_size} 条，BL 队列 {bl_queue_size} 条",
                )
                gather_results = await asyncio.gather(
                    self._run_analysis_phase(state, task_id),
                    self._run_business_logic_analysis_phase(state, task_id),
                    return_exceptions=True,
                )
                for i, result in enumerate(gather_results):
                    if isinstance(result, Exception):
                        phase_name = ["Analysis", "BusinessLogicAnalysis"][i]
                        logger.error("[WorkflowEngine] %s phase raised exception: %s", phase_name, result, exc_info=result)
                        await orc.emit_event("warning", f"⚠️ [Workflow] {phase_name} 阶段异常（非关键）：{str(result)[:100]}")
            else:
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

            # 安全护栏：Analysis 已产出发现，但验证队列意外为空时，回填队列避免跳过 Verification
            if vuln_queue_size <= 0 and orc._all_findings:
                repopulated = 0
                for finding in orc._all_findings:
                    if not isinstance(finding, dict):
                        continue
                    try:
                        normalized = orc._normalize_finding(finding)
                    except Exception:
                        normalized = finding
                    if not isinstance(normalized, dict):
                        continue
                    try:
                        if self.vuln_queue.enqueue_finding(task_id, normalized):
                            repopulated += 1
                    except Exception:
                        continue

                vuln_queue_size = int(self.vuln_queue.get_queue_size(task_id))
                if repopulated > 0:
                    await orc.emit_event(
                        "warning",
                        (
                            "⚠️ [Workflow] Verification 队列为空但已存在 Analysis 发现，"
                            f"已自动回填 {vuln_queue_size} 条并继续验证"
                        ),
                    )
                    logger.warning(
                        "[WorkflowEngine] Verification queue unexpectedly empty; repopulated_from_all_findings=%s",
                        vuln_queue_size,
                    )

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

            # ── 阶段 4: REPORT（为每条 confirmed/likely 漏洞生成详情报告）──
            state.phase = WorkflowPhase.REPORT
            await orc.emit_event("info", "📝 [Workflow] 开始 Report 阶段，生成漏洞详情报告")
            await self._run_report_phase(state, project_info, config)

            # 🔥 记录 Report 完成后的内存
            if self.enable_memory_monitoring:
                self.memory_monitor.take_snapshot(phase="report_done", agent_name="report")

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

    async def _dedup_bl_risk_queue(self, task_id: str) -> None:
        """
        在 BL Recon 结束后，调用大模型对业务逻辑风险点队列进行语义级去重。
        逻辑与 _dedup_recon_risk_queue 完全相同，但操作 bl_queue。
        """
        if self.bl_queue is None:
            return
        orc = self.orchestrator

        try:
            all_risk_points = self.bl_queue.peek(task_id, limit=1000)
            if not all_risk_points or len(all_risk_points) <= 1:
                return

            queue_size = self.bl_queue.size(task_id)
            await orc.emit_event(
                "info",
                f"🤖 [Workflow] 开始 BL 风险点 LLM 去重：队列共 {queue_size} 条",
            )

            risk_points_json = json.dumps(
                [
                    {
                        "id": i,
                        "file_path": rp.get("file_path", ""),
                        "line_start": rp.get("line_start", 0),
                        "description": rp.get("description", ""),
                        "vulnerability_type": rp.get("vulnerability_type", ""),
                        "entry_function": rp.get("entry_function", ""),
                    }
                    for i, rp in enumerate(all_risk_points[:50])
                ],
                ensure_ascii=False,
                indent=2,
            )

            dedup_prompt = f"""请分析以下业务逻辑风险点列表，识别其中明确重复或基本相同的项目。

风险点列表：
{risk_points_json}

分析标准：
1. 相同文件、相同或相邻行号、相同漏洞类型 → 重复
2. 相同文件、相同入口函数、类似描述 → 可能重复
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

            messages = [{"role": "user", "content": dedup_prompt}]
            llm_response, _ = await orc.stream_llm_call(messages)
            dedup_result = self._parse_llm_dedup_response(llm_response)

            if not dedup_result or not dedup_result.get("duplicates"):
                await orc.emit_event("info", "✅ [Workflow] BL 风险点 LLM 去重：无重复项")
                return

            removed_count = await self._remove_duplicate_recon_risk_points(
                task_id, dedup_result["duplicates"], all_risk_points, queue=self.bl_queue
            )

            if removed_count > 0:
                await orc.emit_event(
                    "info",
                    f"✅ [Workflow] BL 风险点 LLM 去重完成：移除 {removed_count} 条重复项",
                )

        except Exception as exc:
            logger.warning("[WorkflowEngine] BL queue LLM dedup failed: %s", exc)

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
                current_size = int(self.vuln_queue.get_queue_size(task_id))
                await orc.emit_event(
                    "info",
                    f"✅ [Workflow] 漏洞队列 LLM 去重完成：移除 {removed_count} 条重复项，剩余 {current_size} 条",
                )
                logger.info(
                    "[WorkflowEngine] Removed %s duplicate findings, queue_size_after_dedup=%s",
                    removed_count,
                    current_size,
                )
            
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
        queue: Optional[Any] = None,
    ) -> int:
        """根据 LLM 分析结果，从风险队列中删除重复的风险点。

        Args:
            queue: 要操作的队列服务；若为 None，则使用 self.recon_queue。
        """
        target_queue = queue if queue is not None else self.recon_queue
        removed_count = 0
        ids_to_remove = set()
        total_items = len(all_risk_points)
        
        for dup_group in duplicates:
            if isinstance(dup_group, dict) and "remove_ids" in dup_group:
                for remove_id in dup_group.get("remove_ids", []):
                    try:
                        idx = int(remove_id)
                    except Exception:
                        continue
                    if 0 <= idx < total_items:
                        ids_to_remove.add(idx)

        if ids_to_remove and total_items > 0:
            kept_items = [item for i, item in enumerate(all_risk_points) if i not in ids_to_remove]

            # 安全护栏：不允许去重后将队列清空（除非原本确实只有重复且全删，但这里强制至少保留 1 条）
            if not kept_items and all_risk_points:
                logger.warning(
                    "[WorkflowEngine] Recon dedup would remove all items, keep first item as safety guard"
                )
                kept_items = [all_risk_points[0]]

            try:
                clear_func = getattr(target_queue, "clear", None)
                if callable(clear_func):
                    clear_func(task_id)
                else:
                    logger.warning("[WorkflowEngine] Queue has no clear() method, skip dedup rewrite")
                    return 0

                for item in kept_items:
                    target_queue.enqueue(task_id, item)

                removed_count = max(0, total_items - len(kept_items))
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
        total_items = len(all_findings)
        
        for dup_group in duplicates:
            if isinstance(dup_group, dict) and "remove_ids" in dup_group:
                for remove_id in dup_group.get("remove_ids", []):
                    try:
                        idx = int(remove_id)
                    except Exception:
                        continue
                    if 0 <= idx < total_items:
                        ids_to_remove.add(idx)

        if ids_to_remove and total_items > 0:
            kept_items = [item for i, item in enumerate(all_findings) if i not in ids_to_remove]

            # 安全护栏：不允许去重后队列被清空，避免 Verification 阶段被跳过
            if not kept_items and all_findings:
                logger.warning(
                    "[WorkflowEngine] Vulnerability dedup would remove all items, keep first item as safety guard"
                )
                kept_items = [all_findings[0]]

            try:
                clear_func = getattr(self.vuln_queue, "clear_queue", None)
                if callable(clear_func):
                    clear_func(task_id)
                else:
                    logger.warning("[WorkflowEngine] Vulnerability queue has no clear_queue() method, skip dedup rewrite")
                    return 0

                for item in kept_items:
                    self.vuln_queue.enqueue_finding(task_id, item)

                removed_count = max(0, total_items - len(kept_items))

                post_size = int(self.vuln_queue.get_queue_size(task_id))
                if post_size <= 0 and kept_items:
                    logger.warning(
                        "[WorkflowEngine] Vulnerability dedup rewrite produced empty queue unexpectedly; restoring snapshot"
                    )
                    clear_func(task_id)
                    for item in all_findings:
                        self.vuln_queue.enqueue_finding(task_id, item)
                    removed_count = 0
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

    async def _run_business_logic_recon_phase(self, state: WorkflowState, task_id: str) -> None:
        """
        调度 BusinessLogicReconAgent 一次，将业务逻辑风险点推入 bl_risk_queue。
        """
        orc = self.orchestrator
        step_start = time.time()

        params = {
            "agent": "business_logic_recon",
            "task": "侦查项目中的业务逻辑漏洞风险点（IDOR、权限绕过、支付逻辑、竞态条件等），将风险点推送到业务逻辑队列",
        }
        try:
            observation = await orc._dispatch_agent(params)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("[WorkflowEngine] BL Recon phase failed: %s", exc)
            observation = f"BL Recon 执行异常: {exc}"

        duration_ms = int((time.time() - step_start) * 1000)
        bl_recon_success = bool(
            orc._agent_results.get("business_logic_recon", {}).get("_run_success")
        )
        state.bl_recon_done = bl_recon_success
        state.step_records.append(
            WorkflowStepRecord(
                phase=WorkflowPhase.BUSINESS_LOGIC_RECON,
                agent="business_logic_recon",
                success=bl_recon_success,
                error=None if bl_recon_success else orc._agent_results.get("business_logic_recon", {}).get("_run_error"),
                findings_count=len(orc._all_findings),
                duration_ms=duration_ms,
            )
        )
        logger.info(
            "[WorkflowEngine] BL Recon phase done: success=%s, bl_queue_size=%s",
            bl_recon_success,
            self.bl_queue.size(task_id) if self.bl_queue else 0,
        )

        bl_recon_agent = orc.sub_agents.get("business_logic_recon")
        if bl_recon_agent and hasattr(bl_recon_agent, "reset_session_memory"):
            bl_recon_agent.reset_session_memory()

    async def _run_analysis_phase(self, state: WorkflowState, task_id: str) -> None:
        """
        从 Recon 风险点队列逐条取出风险点，调度 AnalysisAgent。

        根据配置选择并行或串行模式：
        - 并行模式：使用 ParallelPhaseExecutor 创建 worker 池（最多 analysis_max_workers 个）
        - 串行模式：降级到串行处理（fallback）
        """
        await self.analysis_executor.run_parallel_analysis(
            state=state,
            task_id=task_id,
            recon_queue=self.recon_queue,
        )

        logger.info(
            "[WorkflowEngine] Analysis phase done: %s risk point(s) processed, cumulative findings=%s",
            state.analysis_risk_points_processed,
            len(self.orchestrator._all_findings),
        )

    async def _run_business_logic_analysis_phase(self, state: WorkflowState, task_id: str) -> None:
        """
        从 BL 风险点队列逐条取出风险点，调度 BusinessLogicAnalysisAgent。

        根据配置选择并行或串行模式：
        - 并行模式：使用 ParallelPhaseExecutor 创建 worker 池（最多 bl_analysis_max_workers 个）
        - 串行模式：降级到串行处理（fallback）
        """
        bl_analysis_agent = self.orchestrator.sub_agents.get("business_logic_analysis")
        if bl_analysis_agent is None:
            logger.info("[WorkflowEngine] No business_logic_analysis agent, skipping BL Analysis phase")
            return

        await self.bl_analysis_executor.run_parallel_bl_analysis(
            state=state,
            task_id=task_id,
            bl_queue=self.bl_queue,
        )

        logger.info(
            "[WorkflowEngine] BL Analysis phase done: %s risk point(s) processed",
            state.bl_risk_points_processed,
        )

    async def _run_verification_phase(self, state: WorkflowState, task_id: str) -> None:
        """
        从漏洞验证队列逐条取出漏洞，调度 Verification Agent。

        根据配置选择并行或串行模式。
        """
        # 委托给并行执行器（内部会根据配置选择并行或串行）
        await self.verification_executor.run_parallel_verification(
            state=state,
            task_id=task_id,
            vuln_queue=self.vuln_queue,
        )

        logger.info(
            "[WorkflowEngine] Verification phase done: %s finding(s) processed, final findings=%s",
            state.vuln_queue_findings_processed,
            len(self.orchestrator._all_findings),
        )

    async def _run_report_phase(
        self,
        state: WorkflowState,
        project_info: Dict[str, Any],
        config: Dict[str, Any],
    ) -> None:
        """
        为每条 confirmed/likely 漏洞调度 Report Agent，生成结构化 Markdown 详情报告。

        报告写入：
        - finding["vulnerability_report"]（同步修改 orc._all_findings 中的对应项）
        - state.finding_reports[finding_title]（汇总）
        """
        orc = self.orchestrator
        report_agent = orc.sub_agents.get("report")

        if report_agent is None:
            logger.info("[WorkflowEngine] No report agent registered, skipping Report phase")
            await orc.emit_event("info", "⏭️ [Workflow] 未配置 Report Agent，跳过报告生成阶段")
            return

        # 只为 confirmed 或 likely 的 findings 生成报告
        valid_verdicts = {"confirmed", "likely"}
        reportable = [
            f for f in orc._all_findings
            if isinstance(f, dict) and str(f.get("verdict") or "").lower() in valid_verdicts
        ]

        if not reportable:
            await orc.emit_event(
                "info",
                "⏭️ [Workflow] 无 confirmed/likely 漏洞，跳过报告生成阶段",
            )
            logger.info("[WorkflowEngine] Report phase skipped: no reportable findings")
            return

        state.report_findings_total = len(reportable)
        await orc.emit_event(
            "info",
            f"📝 [Workflow] Report 阶段：共 {len(reportable)} 条漏洞需要生成报告",
        )

        if self.workflow_config.should_parallelize_report:
            await self._run_parallel_report_phase(
                state=state,
                reportable=reportable,
                project_info=project_info,
                config=config,
            )
        else:
            await self._run_sequential_report_phase(
                state=state,
                reportable=reportable,
                project_info=project_info,
                config=config,
            )

        await orc.emit_event(
            "info",
            f"✅ [Workflow] Report 阶段完成：{state.report_findings_processed}/{state.report_findings_total} 条报告已生成",
        )
        logger.info(
            "[WorkflowEngine] Report phase done: %s/%s reports generated",
            state.report_findings_processed,
            state.report_findings_total,
        )

    def _create_report_worker_agent(self, worker_id: int) -> Any:
        """为 Report 阶段创建独立 worker agent，避免会话状态互相污染。"""
        base_agent = self.orchestrator.sub_agents["report"]
        worker_agent = base_agent.__class__(
            llm_service=base_agent.llm_service,
            tools=base_agent.tools,
            event_emitter=base_agent.event_emitter,
        )

        worker_agent.config = copy.deepcopy(base_agent.config)
        worker_name = f"{base_agent.name}_worker_{worker_id}"
        if isinstance(worker_agent.config, dict):
            worker_agent.config["name"] = worker_name
        else:
            worker_agent.config.name = worker_name
        worker_agent.name = worker_name

        if hasattr(worker_agent, "configure_trace_logger"):
            try:
                worker_agent.configure_trace_logger(worker_agent.name)
            except Exception as exc:
                logger.warning(
                    "[WorkflowEngine] Failed to configure trace logger for report worker %s: %s",
                    worker_id,
                    exc,
                )

        worker_agent.tracer = getattr(base_agent, "tracer", None)

        if hasattr(worker_agent, "set_mcp_runtime"):
            worker_agent.set_mcp_runtime(getattr(base_agent, "_mcp_runtime", None))
        if hasattr(worker_agent, "set_write_scope_guard"):
            worker_agent.set_write_scope_guard(getattr(base_agent, "_write_scope_guard", None))

        cancel_callback = getattr(base_agent, "_cancel_callback", None)
        if cancel_callback is not None and hasattr(worker_agent, "set_cancel_callback"):
            worker_agent.set_cancel_callback(cancel_callback)

        return worker_agent

    async def _run_sequential_report_phase(
        self,
        state: WorkflowState,
        reportable: List[Dict[str, Any]],
        project_info: Dict[str, Any],
        config: Dict[str, Any],
    ) -> None:
        for idx, finding in enumerate(reportable, start=1):
            if self.orchestrator.is_cancelled:
                break
            await self._process_single_report(
                state=state,
                finding=finding,
                index=idx,
                total=len(reportable),
                project_info=project_info,
                config=config,
                worker_id=None,
                lock=None,
            )

    async def _run_parallel_report_phase(
        self,
        state: WorkflowState,
        reportable: List[Dict[str, Any]],
        project_info: Dict[str, Any],
        config: Dict[str, Any],
    ) -> None:
        worker_count = max(1, self.workflow_config.report_max_workers)
        work_queue: asyncio.Queue[tuple[int, Dict[str, Any]]] = asyncio.Queue()
        lock = asyncio.Lock()

        for idx, finding in enumerate(reportable, start=1):
            work_queue.put_nowait((idx, finding))

        async def _worker(worker_id: int) -> None:
            while not self.orchestrator.is_cancelled:
                try:
                    index, finding = work_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                try:
                    await self._process_single_report(
                        state=state,
                        finding=finding,
                        index=index,
                        total=len(reportable),
                        project_info=project_info,
                        config=config,
                        worker_id=worker_id,
                        lock=lock,
                    )
                finally:
                    work_queue.task_done()

        worker_tasks = [
            asyncio.create_task(_worker(worker_id), name=f"report_worker_{worker_id}")
            for worker_id in range(worker_count)
        ]

        try:
            results = await asyncio.gather(*worker_tasks, return_exceptions=True)
            for worker_id, result in enumerate(results):
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.error(
                        "[WorkflowEngine] Report worker %s failed: %s",
                        worker_id,
                        result,
                        exc_info=result,
                    )
        except asyncio.CancelledError:
            for task in worker_tasks:
                task.cancel()
            try:
                await asyncio.shield(asyncio.gather(*worker_tasks, return_exceptions=True))
            except asyncio.CancelledError:
                pass
            raise

    async def _process_single_report(
        self,
        state: WorkflowState,
        finding: Dict[str, Any],
        index: int,
        total: int,
        project_info: Dict[str, Any],
        config: Dict[str, Any],
        worker_id: Optional[int],
        lock: Optional[asyncio.Lock],
    ) -> None:
        orc = self.orchestrator
        title = finding.get("title") or f"漏洞 #{index}"
        worker_prefix = f"[Worker-{worker_id}] " if worker_id is not None else ""

        await orc.emit_event(
            "info",
            f"📝 [Workflow] {worker_prefix}Report [{index}/{total}]：{title}",
        )

        step_start = time.time()
        report_text = ""
        success = False
        error_msg = None

        report_agent = self._create_report_worker_agent(worker_id or 0) if worker_id is not None else orc.sub_agents["report"]
        if hasattr(report_agent, "reset_cancellation_state"):
            report_agent.reset_cancellation_state()

        try:
            result = await report_agent.run(
                {
                    "finding": finding,
                    "project_info": project_info,
                    "config": config,
                }
            )
            if result.success and result.data:
                report_text = result.data.get("vulnerability_report") or ""
                success = bool(report_text)
            else:
                error_msg = result.error or "Report Agent 返回空结果"
                logger.warning("[WorkflowEngine] Report failed for '%s': %s", title, error_msg)

            if lock is not None:
                async with lock:
                    self.orchestrator._tool_calls += int(getattr(result, "tool_calls", 0) or 0)
                    self.orchestrator._total_tokens += int(getattr(result, "tokens_used", 0) or 0)
                    self.orchestrator._iteration += int(getattr(result, "iterations", 0) or 0)
                    state.total_iterations += int(getattr(result, "iterations", 0) or 0)
                    state.total_tokens += int(getattr(result, "tokens_used", 0) or 0)
                    state.tool_calls += int(getattr(result, "tool_calls", 0) or 0)
            else:
                self.orchestrator._tool_calls += int(getattr(result, "tool_calls", 0) or 0)
                self.orchestrator._total_tokens += int(getattr(result, "tokens_used", 0) or 0)
                self.orchestrator._iteration += int(getattr(result, "iterations", 0) or 0)
                state.total_iterations += int(getattr(result, "iterations", 0) or 0)
                state.total_tokens += int(getattr(result, "tokens_used", 0) or 0)
                state.tool_calls += int(getattr(result, "tool_calls", 0) or 0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            error_msg = str(exc)
            logger.exception("[WorkflowEngine] Report phase error for '%s': %s", title, exc)
        finally:
            if worker_id is not None and hasattr(report_agent, "reset_session_memory"):
                report_agent.reset_session_memory()

        duration_ms = int((time.time() - step_start) * 1000)

        async def _update_state() -> None:
            if report_text:
                finding["vulnerability_report"] = report_text
                state.finding_reports[title] = report_text
                state.report_findings_processed += 1

            state.step_records.append(
                WorkflowStepRecord(
                    phase=WorkflowPhase.REPORT,
                    agent=f"report_worker_{worker_id}" if worker_id is not None else "report",
                    injected_context={"title": title, "verdict": finding.get("verdict")},
                    success=success,
                    error=error_msg,
                    findings_count=len(orc._all_findings),
                    duration_ms=duration_ms,
                )
            )

        if lock is not None:
            async with lock:
                await _update_state()
        else:
            await _update_state()
