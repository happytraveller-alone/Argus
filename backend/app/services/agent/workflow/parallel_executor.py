"""
并行执行器 - 支持 Analysis 和 Verification 阶段的并行处理

核心功能：
1. Worker 池管理（创建、调度、清理）
2. Agent 实例克隆（每个 worker 独立的会话内存）
3. 并发控制（Semaphore 限制并发数，Lock 保护共享状态）
4. 降级支持（可回退到串行模式）
"""

import asyncio
import copy
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from .models import WorkflowPhase, WorkflowState, WorkflowStepRecord

if TYPE_CHECKING:
    from ..agents.base import BaseAgent
    from ..agents.orchestrator import OrchestratorAgent

logger = logging.getLogger(__name__)


class ParallelPhaseExecutor:
    """
    并行阶段执行器

    使用 worker 池并行处理队列项（风险点或漏洞），每个 worker 拥有独立的 agent 实例。
    """

    def __init__(
        self,
        orchestrator: "OrchestratorAgent",
        agent_type: str,  # "analysis" or "verification"
        max_workers: int,
        enable_parallel: bool = True,
    ):
        """
        初始化并行执行器

        Args:
            orchestrator: Orchestrator agent 实例
            agent_type: Agent 类型（"analysis" 或 "verification"）
            max_workers: 最大 worker 数量
            enable_parallel: 是否启用并行（False 则降级到串行）
        """
        self.orchestrator = orchestrator
        self.agent_type = agent_type
        self.max_workers = max_workers
        self.enable_parallel = enable_parallel
        self.semaphore = asyncio.Semaphore(max_workers)
        self.worker_agents: dict[int, BaseAgent] = {}
        self.active_workers: set[int] = set()
        self.lock = asyncio.Lock()  # 保护共享状态

    def _create_worker_agent(self, worker_id: int) -> "BaseAgent":
        """
        克隆 agent 实例，创建独立的会话内存

        关键点：
        - 复用 LLM service（factory 每次创建新 adapter）
        - 复用 tools（无状态或线程安全）
        - 复用 event_emitter（内部使用 async queue）
        - 创建新的 session memory（_insights, _work_completed, _incoming_handoff）

        Args:
            worker_id: Worker ID

        Returns:
            克隆的 agent 实例
        """
        base_agent = self.orchestrator.sub_agents[self.agent_type]

        # 创建 worker agent（使用相同的构造参数）
        worker_agent = base_agent.__class__(
            llm_service=base_agent.llm_service,
            tools=base_agent.tools,
            event_emitter=base_agent.event_emitter,
        )

        # 深拷贝并修改 config（config 在 deepcopy 后变成字典）
        worker_agent.config = copy.deepcopy(base_agent.config)
        worker_name = f"{base_agent.name}_worker_{worker_id}"
        if isinstance(worker_agent.config, dict):
            worker_agent.config["name"] = worker_name
        else:
            # 如果 config 是对象，尝试设置属性
            worker_agent.config.name = worker_name
        worker_agent.name = worker_name

        if hasattr(worker_agent, "configure_trace_logger"):
            try:
                worker_agent.configure_trace_logger(worker_agent.name)
            except Exception as exc:
                logger.warning(
                    "[ParallelExecutor] Failed to configure trace logger for worker %s: %s",
                    worker_id,
                    exc,
                )
        worker_agent.tracer = getattr(base_agent, "tracer", None)

        if hasattr(worker_agent, "set_mcp_runtime"):
            worker_agent.set_mcp_runtime(getattr(base_agent, "_mcp_runtime", None))
        if hasattr(worker_agent, "set_write_scope_guard"):
            worker_agent.set_write_scope_guard(
                getattr(base_agent, "_write_scope_guard", None)
            )
        # 传播取消回调，确保 worker 能感知全局取消标志
        cancel_callback = getattr(base_agent, "_cancel_callback", None)
        if cancel_callback is not None and hasattr(worker_agent, "set_cancel_callback"):
            worker_agent.set_cancel_callback(cancel_callback)

        logger.info(f"[ParallelExecutor] Created worker agent: {worker_agent.name}")
        return worker_agent

    def _build_previous_results(self) -> dict[str, Any]:
        previous_results: dict[str, Any] = {
            "findings": list(getattr(self.orchestrator, "_all_findings", [])),
        }
        runtime_context = getattr(self.orchestrator, "_runtime_context", {})
        runtime_config = (
            runtime_context.get("config", {})
            if isinstance(runtime_context, dict)
            else {}
        )
        bootstrap_findings = runtime_config.get("bootstrap_findings", [])
        if bootstrap_findings:
            previous_results["bootstrap_findings"] = list(bootstrap_findings)
            previous_results["bootstrap_source"] = runtime_config.get("bootstrap_source")
            previous_results["bootstrap_task_id"] = runtime_config.get("bootstrap_task_id")

        for prev_agent, prev_data in getattr(self.orchestrator, "_agent_results", {}).items():
            if isinstance(prev_data, dict):
                previous_results[prev_agent] = {"data": copy.deepcopy(prev_data)}
        return previous_results

    def _build_worker_input(self, params: dict[str, Any]) -> dict[str, Any]:
        task_description = str(params.get("task", "") or "")
        context = str(params.get("context", "") or "")
        runtime_context = getattr(self.orchestrator, "_runtime_context", {})
        task_id = params.get("task_id") or (
            runtime_context.get("task_id") if isinstance(runtime_context, dict) else None
        )
        project_info = (
            dict(runtime_context.get("project_info", {}))
            if isinstance(runtime_context, dict)
            and isinstance(runtime_context.get("project_info"), dict)
            else {}
        )
        if "root" not in project_info:
            project_info["root"] = (
                runtime_context.get("project_root", ".")
                if isinstance(runtime_context, dict)
                else "."
            )

        runtime_config = (
            dict(runtime_context.get("config", {}))
            if isinstance(runtime_context, dict)
            and isinstance(runtime_context.get("config"), dict)
            else {}
        )
        previous_results = self._build_previous_results()

        handoff = None
        if hasattr(self.orchestrator, "_build_handoff_for_agent"):
            handoff = self.orchestrator._build_handoff_for_agent(
                self.agent_type,
                task_description,
                context,
            )

        if self.agent_type == "analysis":
            extract_risk_point = getattr(
                self.orchestrator,
                "_extract_single_risk_point_for_analysis",
                None,
            )
            single_risk_point = None
            if callable(extract_risk_point):
                single_risk_point = extract_risk_point(
                    params=params,
                    context=context,
                    runtime_config=runtime_config,
                    handoff=handoff,
                )
            else:
                single_risk_point = params.get("single_risk_point") or params.get("risk_point")

            runtime_config["single_risk_mode"] = True
            if isinstance(single_risk_point, dict):
                runtime_config["single_risk_point"] = single_risk_point
                runtime_config["target_files"] = [single_risk_point.get("file_path", "")]
                previous_results["bootstrap_findings"] = [single_risk_point]
                if handoff and hasattr(handoff, "context_data"):
                    if not isinstance(handoff.context_data, dict):
                        handoff.context_data = {}
                    handoff.context_data["single_risk_point"] = single_risk_point

        queue_finding = params.get("finding") or params.get("queue_finding")
        if isinstance(queue_finding, dict):
            runtime_config["queue_finding"] = queue_finding

        file_planning = runtime_config.get("file_planning")
        if not isinstance(file_planning, dict):
            file_planning = None

        single_risk_point = runtime_config.get("single_risk_point")
        if not isinstance(single_risk_point, dict):
            single_risk_point = None

        return {
            "task": task_description,
            "context": context,
            "task_context": context,
            "risk_point": single_risk_point,
            "single_risk_point": single_risk_point,
            "finding": queue_finding if isinstance(queue_finding, dict) else None,
            "project_info": project_info,
            "config": runtime_config,
            "task_id": task_id,
            "project_root": (
                runtime_context.get("project_root", ".")
                if isinstance(runtime_context, dict)
                else "."
            ),
            "previous_results": previous_results,
            "handoff": handoff.to_dict() if handoff else None,
            "file_planning": file_planning,
        }

    @staticmethod
    def _merge_list_field(existing: Any, incoming: Any) -> list[Any]:
        merged: list[Any] = []
        for source in (existing, incoming):
            if not isinstance(source, list):
                continue
            for item in source:
                if item not in merged:
                    merged.append(item)
        return merged

    @classmethod
    def _merge_verification_todo_summary(
        cls,
        existing: Any,
        incoming: Any,
    ) -> dict[str, Any]:
        merged = dict(existing) if isinstance(existing, dict) else {}
        if not isinstance(incoming, dict):
            return merged

        for counter in ("total", "verified", "false_positive", "blocked", "pending"):
            merged[counter] = int(merged.get(counter) or 0) + int(incoming.get(counter) or 0)

        merged["blocked_reasons_top"] = cls._merge_list_field(
            merged.get("blocked_reasons_top"),
            incoming.get("blocked_reasons_top"),
        )
        merged["per_item_compact"] = cls._merge_list_field(
            merged.get("per_item_compact"),
            incoming.get("per_item_compact"),
        )
        return merged

    def _merge_phase_result(
        self,
        worker_result: dict[str, Any],
        handoff: Any | None = None,
    ) -> dict[str, Any]:
        current = self.orchestrator._agent_results.get(self.agent_type, {})
        merged = dict(current) if isinstance(current, dict) else {}

        merged["_run_success"] = bool(merged.get("_run_success", True)) and bool(
            worker_result.get("_run_success", False)
        )

        worker_error = worker_result.get("_run_error")
        if worker_error:
            previous_error = str(merged.get("_run_error") or "").strip()
            error_text = str(worker_error)
            merged["_run_error"] = (
                error_text if not previous_error else f"{previous_error}; {error_text}"
            )

        merged["findings"] = self._merge_list_field(
            merged.get("findings"),
            worker_result.get("findings"),
        )
        merged["steps"] = self._merge_list_field(
            merged.get("steps"),
            worker_result.get("steps"),
        )

        for counter in (
            "verified_count",
            "likely_count",
            "false_positive_count",
            "candidate_count",
        ):
            merged[counter] = int(merged.get(counter) or 0) + int(worker_result.get(counter) or 0)

        todo_summary = self._merge_verification_todo_summary(
            merged.get("verification_todo_summary"),
            worker_result.get("verification_todo_summary"),
        )
        if todo_summary:
            merged["verification_todo_summary"] = todo_summary

        for key in ("degraded_reason", "note", "summary"):
            if worker_result.get(key):
                merged[key] = worker_result[key]

        self.orchestrator._agent_results[self.agent_type] = merged
        if handoff is not None:
            self.orchestrator._agent_handoffs[self.agent_type] = handoff
        return merged

    def _merge_findings_into_all_findings(self, findings: Any) -> None:
        if not isinstance(findings, list):
            return

        for finding in findings:
            if not isinstance(finding, dict):
                continue
            try:
                normalized = self.orchestrator._normalize_finding(finding)
            except Exception as exc:
                logger.warning("[ParallelExecutor] Failed to normalize finding: %s", exc)
                continue

            if not isinstance(normalized, dict):
                continue

            new_fingerprint = None
            if hasattr(self.orchestrator, "_build_queue_fingerprint"):
                new_fingerprint = self.orchestrator._build_queue_fingerprint(normalized)

            merged_existing = False
            for index, existing in enumerate(self.orchestrator._all_findings):
                if not isinstance(existing, dict):
                    continue
                existing_fingerprint = None
                if hasattr(self.orchestrator, "_build_queue_fingerprint"):
                    existing_fingerprint = self.orchestrator._build_queue_fingerprint(existing)
                if new_fingerprint and existing_fingerprint == new_fingerprint:
                    merged = dict(existing)
                    for key, value in normalized.items():
                        if value not in (None, "", 0, [], {}):
                            merged[key] = value
                    self.orchestrator._all_findings[index] = merged
                    merged_existing = True
                    break
                if normalized == existing:
                    merged_existing = True
                    break

            if not merged_existing:
                self.orchestrator._all_findings.append(normalized)

    async def run_parallel_analysis(
        self,
        state: WorkflowState,
        task_id: str,
        recon_queue: Any,
    ) -> None:
        """
        并行处理 Recon 风险队列

        流程：
        1. 检查是否启用并行（否则降级到串行）
        2. 初始化 worker 池（创建 N 个 agent 实例）
        3. 启动 N 个 worker 协程，竞争队列项
        4. 每个 worker：dequeue → dispatch → 更新状态 → reset_memory
        5. 等待所有 worker 完成（队列耗尽）
        6. 清理 worker agents

        Args:
            state: Workflow 状态
            task_id: 任务 ID
            recon_queue: Recon 风险队列服务
        """
        if not self.enable_parallel or self.max_workers <= 1:
            logger.info("[ParallelExecutor] Parallel disabled or max_workers=1, using sequential mode")
            return await self._run_sequential_analysis(state, task_id, recon_queue)

        logger.info(f"[ParallelExecutor] Starting parallel analysis with {self.max_workers} workers")

        # 启动 worker 任务
        worker_tasks = [
            asyncio.create_task(
                self._analysis_worker(worker_id, state, task_id, recon_queue),
                name=f"analysis_worker_{worker_id}"
            )
            for worker_id in range(self.max_workers)
        ]

        try:
            # 等待所有 worker 完成
            results = await asyncio.gather(*worker_tasks, return_exceptions=True)

            # 处理 worker 错误（不阻塞其他 worker，忽略正常取消）
            for i, result in enumerate(results):
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.error(f"[ParallelExecutor] Worker {i} failed: {result}", exc_info=result)

        except asyncio.CancelledError:
            # 确保所有 worker task 收到取消信号
            for task in worker_tasks:
                task.cancel()
            # Python 3.12+: _num_cancels_requested > 0 会立即取消下一个 await，
            # 用 asyncio.shield 保护清理 gather，防止被二次取消打断。
            # Worker task 被 cancel() 后会在各自的下一个 await 点收到 CancelledError，
            # 通过 shield 确保 gather 不被立即取消，让 worker 有机会完成清理。
            try:
                await asyncio.shield(asyncio.gather(*worker_tasks, return_exceptions=True))
            except asyncio.CancelledError:
                pass
            raise
        finally:
            # 清理
            self.worker_agents.clear()
            logger.info("[ParallelExecutor] Parallel analysis completed")

    async def _analysis_worker(
        self,
        worker_id: int,
        state: WorkflowState,
        task_id: str,
        recon_queue: Any,
    ) -> None:
        """
        Analysis worker 协程：从队列取风险点并处理

        并发控制：
        - Semaphore 限制活跃 worker 数
        - Lock 保护共享状态修改
        - 队列操作原子性（Redis lpop/rpush）

        Args:
            worker_id: Worker ID
            state: Workflow 状态
            task_id: 任务 ID
            recon_queue: Recon 风险队列服务
        """
        iteration = 0

        logger.info(f"[Worker-{worker_id}] Analysis worker started")

        while True:
            # 检查取消
            if self.orchestrator.is_cancelled:
                logger.info(f"[Worker-{worker_id}] Cancelled, exiting")
                break

            # 获取 semaphore 槽位
            async with self.semaphore:
                # 原子出队（线程安全）
                risk_point = recon_queue.dequeue(task_id)
                if risk_point is None:
                    logger.info(f"[Worker-{worker_id}] Queue drained, exiting")
                    break  # 队列耗尽

                iteration += 1

                # 更新共享状态（加锁）
                async with self.lock:
                    self.active_workers.add(worker_id)
                    state.analysis_risk_points_processed += 1
                    state.total_iterations += 1

                fp_repr = f"{risk_point.get('file_path', '')}:{risk_point.get('line_start', '')}"
                await self.orchestrator.emit_event(
                    "info",
                    f" [Worker-{worker_id}] Analysis 第 {iteration} 轮：{fp_repr}",
                )

                step_start = time.time()

                # 调度到 worker agent（隔离实例）
                params = {
                    "agent": self.agent_type,
                    "task": f"针对风险点 {fp_repr} 进行深度代码审计",
                    "risk_point": risk_point,
                    "context": json.dumps(risk_point, ensure_ascii=False),
                    "task_id": task_id,
                }

                # 严格隔离：每个风险点创建全新 agent 实例，避免跨任务上下文/缓存复用。
                worker_agent = self._create_worker_agent(worker_id)

                # 注入当前风险点（仅供 orchestrator 内部提取使用，并发时以各 worker 自身 params 为准）
                self.orchestrator._last_recon_risk_point = risk_point

                try:
                    await self._dispatch_to_worker_agent(worker_agent, params)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(f"[Worker-{worker_id}] Dispatch failed: {exc}", exc_info=True)
                finally:
                    self.orchestrator._last_recon_risk_point = None

                duration_ms = int((time.time() - step_start) * 1000)

                # 合并 worker 结果到 orchestrator（加锁）
                async with self.lock:
                    worker_result = getattr(worker_agent, '_agent_results', {}).get(self.agent_type, {})
                    analysis_success = bool(worker_result.get("_run_success"))
                    self.orchestrator._tool_calls += int(worker_result.get("_worker_tool_calls", 0) or 0)
                    self.orchestrator._total_tokens += int(
                        worker_result.get("_worker_tokens_used", 0) or 0
                    )
                    self.orchestrator._iteration += int(worker_result.get("_worker_iterations", 0) or 0)

                    if worker_result:
                        self._merge_phase_result(
                            worker_result,
                            handoff=getattr(worker_agent, "_latest_handoff", None),
                        )

                    worker_findings = worker_result.get("findings", [])
                    self._merge_findings_into_all_findings(worker_findings)

                    state.step_records.append(
                        WorkflowStepRecord(
                            phase=WorkflowPhase.ANALYSIS,
                            agent=f"{self.agent_type}_worker_{worker_id}",
                            injected_context=risk_point,
                            success=analysis_success,
                            error=None if analysis_success else worker_result.get("_run_error"),
                            findings_count=len(self.orchestrator._all_findings),
                            duration_ms=duration_ms,
                        )
                    )

                    logger.info(
                        f"[Worker-{worker_id}] Analysis iteration {iteration} done: "
                        f"risk_point={fp_repr}, success={analysis_success}, "
                        f"cumulative_findings={len(self.orchestrator._all_findings)}"
                    )

                # 重置 worker agent 内存（任务隔离）
                worker_agent.reset_session_memory()

                # 标记 worker 为空闲（finally 确保取消时也能清理）
                async with self.lock:
                    self.active_workers.discard(worker_id)

        logger.info(f"[Worker-{worker_id}] Analysis worker completed {iteration} iterations")

    async def _dispatch_to_worker_agent(
        self,
        worker_agent: "BaseAgent",
        params: dict[str, Any],
    ) -> Any:
        """
        调度任务到 worker agent

        复用 orchestrator 的子 Agent 输入契约，但使用独立的 worker agent 实例。

        Args:
            worker_agent: Worker agent 实例
            params: 调度参数
        """
        agent_input = self._build_worker_input(params)

        if hasattr(worker_agent, "configure_trace_logger"):
            try:
                worker_agent.configure_trace_logger(worker_agent.name, agent_input.get("task_id"))
            except Exception as exc:
                logger.warning(
                    "[ParallelExecutor] Failed to bind task trace logger for %s: %s",
                    worker_agent.name,
                    exc,
                )

        if hasattr(worker_agent, "reset_cancellation_state"):
            worker_agent.reset_cancellation_state()

        result = await worker_agent.run(agent_input)

        # 优先使用 agent 内部聚合结果，避免被 result.data 的空结构覆盖
        existing_payload = {}
        existing_results = getattr(worker_agent, "_agent_results", {})
        if isinstance(existing_results, dict):
            maybe_existing = existing_results.get(self.agent_type, {})
            if isinstance(maybe_existing, dict):
                existing_payload = dict(maybe_existing)

        worker_payload: dict[str, Any] = dict(existing_payload)
        if isinstance(getattr(result, "data", None), dict):
            for key, value in result.data.items():
                if key not in worker_payload:
                    worker_payload[key] = value
                elif value not in (None, "", [], {}):
                    worker_payload[key] = value
        result_findings = getattr(result, "findings", None)
        if isinstance(result_findings, list):
            worker_payload["findings"] = list(result_findings)
        worker_payload["_run_success"] = bool(result.success)
        if result.error:
            worker_payload["_run_error"] = str(result.error)
        worker_payload["_worker_tool_calls"] = int(getattr(result, "tool_calls", 0) or 0)
        worker_payload["_worker_tokens_used"] = int(getattr(result, "tokens_used", 0) or 0)
        worker_payload["_worker_iterations"] = int(getattr(result, "iterations", 0) or 0)

        if not hasattr(worker_agent, '_agent_results'):
            worker_agent._agent_results = {}
        worker_agent._agent_results[self.agent_type] = worker_payload
        worker_agent._latest_handoff = getattr(result, "handoff", None)
        return result

    async def run_parallel_verification(
        self,
        state: WorkflowState,
        task_id: str,
        vuln_queue: Any,
    ) -> None:
        """
        并行处理漏洞验证队列

        流程与 run_parallel_analysis 类似，区别在于处理 vuln_queue

        Args:
            state: Workflow 状态
            task_id: 任务 ID
            vuln_queue: 漏洞队列服务
        """
        if not self.enable_parallel or self.max_workers <= 1:
            logger.info("[ParallelExecutor] Parallel disabled or max_workers=1, using sequential mode")
            return await self._run_sequential_verification(state, task_id, vuln_queue)

        logger.info(f"[ParallelExecutor] Starting parallel verification with {self.max_workers} workers")

        # 启动 worker 任务
        worker_tasks = [
            asyncio.create_task(
                self._verification_worker(worker_id, state, task_id, vuln_queue),
                name=f"verification_worker_{worker_id}"
            )
            for worker_id in range(self.max_workers)
        ]

        try:
            # 等待所有 worker 完成
            results = await asyncio.gather(*worker_tasks, return_exceptions=True)

            # 处理 worker 错误（忽略正常取消）
            for i, result in enumerate(results):
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.error(f"[ParallelExecutor] Worker {i} failed: {result}", exc_info=result)

        except asyncio.CancelledError:
            for task in worker_tasks:
                task.cancel()
            try:
                await asyncio.shield(asyncio.gather(*worker_tasks, return_exceptions=True))
            except asyncio.CancelledError:
                pass
            raise
        finally:
            # 清理
            self.worker_agents.clear()
            logger.info("[ParallelExecutor] Parallel verification completed")

    async def _verification_worker(
        self,
        worker_id: int,
        state: WorkflowState,
        task_id: str,
        vuln_queue: Any,
    ) -> None:
        """
        Verification worker 协程：从队列取漏洞并验证

        额外处理：
        - 指纹去重（_verified_queue_fingerprints）
        - 沙箱执行（Docker 容器隔离，天然支持并发）

        Args:
            worker_id: Worker ID
            state: Workflow 状态
            task_id: 任务 ID
            vuln_queue: 漏洞队列服务
        """
        iteration = 0

        logger.info(f"[Worker-{worker_id}] Verification worker started")

        while True:
            if self.orchestrator.is_cancelled:
                logger.info(f"[Worker-{worker_id}] Cancelled, exiting")
                break

            async with self.semaphore:
                # 原子出队
                finding = vuln_queue.dequeue_finding(task_id)
                if finding is None:
                    logger.info(f"[Worker-{worker_id}] Queue drained, exiting")
                    break

                iteration += 1

                # 更新共享状态（加锁）
                async with self.lock:
                    self.active_workers.add(worker_id)
                    state.vuln_queue_findings_processed += 1
                    state.total_iterations += 1

                fingerprint = self.orchestrator._build_queue_fingerprint(finding)
                skip_duplicate = False
                if fingerprint:
                    async with self.lock:
                        if fingerprint in self.orchestrator._verified_queue_fingerprints:
                            skip_duplicate = True

                if skip_duplicate:
                    await self.orchestrator.emit_event(
                        "info",
                        f"⏭️ [Worker-{worker_id}] Verification 跳过重复指纹: {fingerprint[:60]}",
                    )
                    async with self.lock:
                        state.step_records.append(
                            WorkflowStepRecord(
                                phase=WorkflowPhase.VERIFICATION,
                                agent=f"{self.agent_type}_worker_{worker_id}",
                                injected_context=finding,
                                success=True,
                                error=None,
                                findings_count=len(self.orchestrator._all_findings),
                                duration_ms=0,
                            )
                        )
                        self.active_workers.discard(worker_id)
                    continue

                title_repr = finding.get("title") or finding.get("file_path", "unknown")
                await self.orchestrator.emit_event(
                    "info",
                    f"🛡️ [Worker-{worker_id}] Verification 第 {iteration} 轮：{title_repr}",
                )

                step_start = time.time()

                # 调度到 worker agent
                params = {
                    "agent": self.agent_type,
                    "task": f"验证漏洞：{title_repr}",
                    "finding": finding,
                    "context": json.dumps(finding, ensure_ascii=False),
                    "task_id": task_id,
                }

                # 严格隔离：每个漏洞创建全新 agent 实例，避免跨任务上下文/缓存复用。
                worker_agent = self._create_worker_agent(worker_id)

                try:
                    await self._dispatch_to_worker_agent(worker_agent, params)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(f"[Worker-{worker_id}] Dispatch failed: {exc}", exc_info=True)
                finally:
                    # 确保取消时也能清理 active_workers
                    async with self.lock:
                        self.active_workers.discard(worker_id)

                duration_ms = int((time.time() - step_start) * 1000)

                # 合并结果（加锁）
                async with self.lock:
                    worker_result = getattr(worker_agent, '_agent_results', {}).get(self.agent_type, {})
                    verification_success = bool(worker_result.get("_run_success"))
                    self.orchestrator._tool_calls += int(worker_result.get("_worker_tool_calls", 0) or 0)
                    self.orchestrator._total_tokens += int(
                        worker_result.get("_worker_tokens_used", 0) or 0
                    )
                    self.orchestrator._iteration += int(worker_result.get("_worker_iterations", 0) or 0)

                    if worker_result:
                        self._merge_phase_result(
                            worker_result,
                            handoff=getattr(worker_agent, "_latest_handoff", None),
                        )

                    self._merge_findings_into_all_findings(worker_result.get("findings", []))

                    if verification_success and fingerprint:
                        self.orchestrator._verified_queue_fingerprints.add(fingerprint)

                    state.step_records.append(
                        WorkflowStepRecord(
                            phase=WorkflowPhase.VERIFICATION,
                            agent=f"{self.agent_type}_worker_{worker_id}",
                            injected_context=finding,
                            success=verification_success,
                            error=None if verification_success else worker_result.get("_run_error"),
                            findings_count=len(self.orchestrator._all_findings),
                            duration_ms=duration_ms,
                        )
                    )

                    logger.info(
                        f"[Worker-{worker_id}] Verification iteration {iteration} done: "
                        f"finding={title_repr}, success={verification_success}, "
                        f"cumulative_findings={len(self.orchestrator._all_findings)}"
                    )

                # 重置内存
                worker_agent.reset_session_memory()

        logger.info(f"[Worker-{worker_id}] Verification worker completed {iteration} iterations")

    async def _run_sequential_analysis(
        self,
        state: WorkflowState,
        task_id: str,
        recon_queue: Any,
    ) -> None:
        """
        降级到串行模式（复用原有 engine._run_analysis_phase 逻辑）

        这是 fallback 实现，保持向后兼容
        """
        orc = self.orchestrator
        iteration = 0

        logger.info("[ParallelExecutor] Running sequential analysis (fallback mode)")

        while True:
            if orc.is_cancelled:
                break

            risk_point = recon_queue.dequeue(task_id)
            if risk_point is None:
                logger.info(f"[ParallelExecutor] Recon risk queue drained at iteration {iteration}")
                break

            iteration += 1
            state.analysis_risk_points_processed += 1
            state.total_iterations += 1

            fp_repr = f"{risk_point.get('file_path', '')}:{risk_point.get('line_start', '')}"
            await orc.emit_event("info", f" [Workflow] Analysis 第 {iteration} 轮：风险点 {fp_repr}")

            step_start = time.time()
            params = {
                "agent": "analysis",
                "task": f"针对风险点 {fp_repr} 进行深度代码审计",
                "risk_point": risk_point,
                "context": json.dumps(risk_point, ensure_ascii=False),
                "task_id": task_id,
            }

            orc._last_recon_risk_point = risk_point

            try:
                await orc._dispatch_agent(params)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"[ParallelExecutor] Analysis dispatch failed for {fp_repr}: {exc}")
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

            # 清理 Analysis Agent 的会话内存
            analysis_agent = orc.sub_agents.get("analysis")
            if analysis_agent:
                analysis_agent.reset_session_memory()

        logger.info(f"[ParallelExecutor] Sequential analysis done: {iteration} risk points processed")

    async def _run_sequential_verification(
        self,
        state: WorkflowState,
        task_id: str,
        vuln_queue: Any,
    ) -> None:
        """
        降级到串行模式（复用原有 engine._run_verification_phase 逻辑）
        """
        orc = self.orchestrator
        iteration = 0

        logger.info("[ParallelExecutor] Running sequential verification (fallback mode)")

        while True:
            if orc.is_cancelled:
                break

            finding = vuln_queue.dequeue_finding(task_id)
            if finding is None:
                logger.info(f"[ParallelExecutor] Vulnerability queue drained at iteration {iteration}")
                break

            iteration += 1
            state.vuln_queue_findings_processed += 1
            state.total_iterations += 1

            # 指纹去重
            fingerprint = orc._build_queue_fingerprint(finding)
            if fingerprint and fingerprint in orc._verified_queue_fingerprints:
                await orc.emit_event("info", f"⏭️ [Workflow] Verification 跳过重复指纹: {fingerprint[:60]}")
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
            await orc.emit_event("info", f"🛡️ [Workflow] Verification 第 {iteration} 轮：{title_repr}")

            step_start = time.time()
            params = {
                "agent": "verification",
                "task": f"验证漏洞：{title_repr}",
                "finding": finding,
                "context": json.dumps(finding, ensure_ascii=False),
                "task_id": task_id,
            }

            try:
                await orc._dispatch_agent(params)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"[ParallelExecutor] Verification dispatch failed for {title_repr}: {exc}")

            duration_ms = int((time.time() - step_start) * 1000)
            verification_result = orc._agent_results.get("verification", {})
            verification_success = bool(verification_result.get("_run_success"))

            # 验证成功后记录指纹
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

            # 清理 Verification Agent 的会话内存
            verification_agent = orc.sub_agents.get("verification")
            if verification_agent:
                verification_agent.reset_session_memory()

        logger.info(f"[ParallelExecutor] Sequential verification done: {iteration} findings processed")

    async def run_parallel_bl_analysis(
        self,
        state: WorkflowState,
        task_id: str,
        bl_queue: Any,
    ) -> None:
        """
        并行处理业务逻辑风险队列

        流程与 run_parallel_analysis 类似，区别在于处理 bl_queue 和 BL 相关状态字段。

        Args:
            state: Workflow 状态
            task_id: 任务 ID
            bl_queue: 业务逻辑风险队列服务
        """
        if not self.enable_parallel or self.max_workers <= 1:
            logger.info("[ParallelExecutor] Parallel disabled or max_workers=1, using sequential BL analysis")
            return await self._run_sequential_bl_analysis(state, task_id, bl_queue)

        logger.info(f"[ParallelExecutor] Starting parallel BL analysis with {self.max_workers} workers")

        # 启动 worker 任务
        worker_tasks = [
            asyncio.create_task(
                self._bl_analysis_worker(worker_id, state, task_id, bl_queue),
                name=f"bl_analysis_worker_{worker_id}"
            )
            for worker_id in range(self.max_workers)
        ]

        try:
            # 等待所有 worker 完成
            results = await asyncio.gather(*worker_tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    logger.error(f"[ParallelExecutor] BL Worker {i} failed: {result}", exc_info=result)

        except asyncio.CancelledError:
            for task in worker_tasks:
                task.cancel()
            try:
                await asyncio.shield(asyncio.gather(*worker_tasks, return_exceptions=True))
            except asyncio.CancelledError:
                pass
            raise
        finally:
            self.worker_agents.clear()
            logger.info("[ParallelExecutor] Parallel BL analysis completed")

    async def _bl_analysis_worker(
        self,
        worker_id: int,
        state: WorkflowState,
        task_id: str,
        bl_queue: Any,
    ) -> None:
        """
        BusinessLogicAnalysis worker 协程：从 BL 风险队列取风险点并处理

        Args:
            worker_id: Worker ID
            state: Workflow 状态
            task_id: 任务 ID
            bl_queue: 业务逻辑风险队列服务
        """
        iteration = 0

        logger.info(f"[BLWorker-{worker_id}] BL analysis worker started")

        while True:
            if self.orchestrator.is_cancelled:
                logger.info(f"[BLWorker-{worker_id}] Cancelled, exiting")
                break

            async with self.semaphore:
                risk_point = bl_queue.dequeue(task_id)
                if risk_point is None:
                    logger.info(f"[BLWorker-{worker_id}] BL queue drained, exiting")
                    break

                iteration += 1

                async with self.lock:
                    self.active_workers.add(worker_id)
                    state.bl_risk_points_processed += 1
                    state.total_iterations += 1

                fp_repr = f"{risk_point.get('file_path', '')}:{risk_point.get('line_start', '')}"
                await self.orchestrator.emit_event(
                    "info",
                    f" [BLWorker-{worker_id}] BLAnalysis 第 {iteration} 轮：{fp_repr}",
                )

                step_start = time.time()

                params = {
                    "agent": self.agent_type,
                    "task": f"深度分析业务逻辑风险点 {fp_repr}",
                    "risk_point": risk_point,
                    "context": json.dumps(risk_point, ensure_ascii=False),
                    "task_id": task_id,
                }

                # 严格隔离：每个业务逻辑风险点创建全新 agent 实例。
                worker_agent = self._create_worker_agent(worker_id)

                try:
                    await self._dispatch_to_worker_agent(worker_agent, params)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.error(f"[BLWorker-{worker_id}] Dispatch failed: {exc}", exc_info=True)
                finally:
                    # 确保取消时也能清理 active_workers
                    async with self.lock:
                        self.active_workers.discard(worker_id)

                duration_ms = int((time.time() - step_start) * 1000)

                async with self.lock:
                    worker_result = getattr(worker_agent, '_agent_results', {}).get(self.agent_type, {})
                    bl_success = bool(worker_result.get("_run_success"))
                    self.orchestrator._tool_calls += int(worker_result.get("_worker_tool_calls", 0) or 0)
                    self.orchestrator._total_tokens += int(
                        worker_result.get("_worker_tokens_used", 0) or 0
                    )
                    self.orchestrator._iteration += int(worker_result.get("_worker_iterations", 0) or 0)

                    if worker_result:
                        self._merge_phase_result(
                            worker_result,
                            handoff=getattr(worker_agent, "_latest_handoff", None),
                        )

                    worker_findings = worker_result.get("findings", [])
                    self._merge_findings_into_all_findings(worker_findings)

                    state.step_records.append(
                        WorkflowStepRecord(
                            phase=WorkflowPhase.BUSINESS_LOGIC_ANALYSIS,
                            agent=f"{self.agent_type}_worker_{worker_id}",
                            injected_context=risk_point,
                            success=bl_success,
                            error=None if bl_success else worker_result.get("_run_error"),
                            findings_count=len(self.orchestrator._all_findings),
                            duration_ms=duration_ms,
                        )
                    )

                    logger.info(
                        f"[BLWorker-{worker_id}] BL analysis iteration {iteration} done: "
                        f"risk_point={fp_repr}, success={bl_success}, "
                        f"cumulative_findings={len(self.orchestrator._all_findings)}"
                    )

                worker_agent.reset_session_memory()

        logger.info(f"[BLWorker-{worker_id}] BL analysis worker completed {iteration} iterations")

    async def _run_sequential_bl_analysis(
        self,
        state: WorkflowState,
        task_id: str,
        bl_queue: Any,
    ) -> None:
        """
        降级到串行模式处理业务逻辑风险点（fallback）
        """
        orc = self.orchestrator
        iteration = 0

        logger.info("[ParallelExecutor] Running sequential BL analysis (fallback mode)")

        while True:
            if orc.is_cancelled:
                break

            risk_point = bl_queue.dequeue(task_id)
            if risk_point is None:
                logger.info(f"[ParallelExecutor] BL risk queue drained at iteration {iteration}")
                break

            iteration += 1
            state.bl_risk_points_processed += 1
            state.total_iterations += 1

            fp_repr = f"{risk_point.get('file_path', '')}:{risk_point.get('line_start', '')}"
            await orc.emit_event("info", f" [Workflow] BLAnalysis 第 {iteration} 轮：{fp_repr}")

            step_start = time.time()
            params = {
                "agent": "business_logic_analysis",
                "task": f"深度分析业务逻辑风险点 {fp_repr}",
                "risk_point": risk_point,
                "task_id": task_id,
                "context": json.dumps(risk_point, ensure_ascii=False),
            }

            try:
                await orc._dispatch_agent(params)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"[ParallelExecutor] BL analysis dispatch failed for {fp_repr}: {exc}")

            duration_ms = int((time.time() - step_start) * 1000)
            bl_result = orc._agent_results.get("business_logic_analysis", {})
            bl_success = bool(bl_result.get("_run_success"))

            state.step_records.append(
                WorkflowStepRecord(
                    phase=WorkflowPhase.BUSINESS_LOGIC_ANALYSIS,
                    agent="business_logic_analysis",
                    injected_context=risk_point,
                    success=bl_success,
                    error=None if bl_success else bl_result.get("_run_error"),
                    findings_count=len(orc._all_findings),
                    duration_ms=duration_ms,
                )
            )

            bl_agent = orc.sub_agents.get("business_logic_analysis")
            if bl_agent and hasattr(bl_agent, "reset_session_memory"):
                bl_agent.reset_session_memory()

        logger.info(f"[ParallelExecutor] Sequential BL analysis done: {iteration} risk points processed")
