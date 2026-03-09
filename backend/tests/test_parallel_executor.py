"""
并行执行器单元测试

覆盖重点：
1. worker 创建与隔离
2. 并行 worker 输入契约
3. AgentResult.data 聚合
4. Verification 指纹只在成功后记录
"""

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent.agents.base import AgentResult
from app.services.agent.workflow.models import WorkflowState
from app.services.agent.workflow.parallel_executor import ParallelPhaseExecutor


class MockAgent:
    """模拟 Analysis / Verification Agent。"""

    def __init__(self, llm_service=None, tools: dict[str, Any] | None = None, event_emitter=None):
        self.llm_service = llm_service or MagicMock()
        if not hasattr(self.llm_service, "inputs"):
            self.llm_service.inputs = []
        if not hasattr(self.llm_service, "attempts"):
            self.llm_service.attempts = {}
        self.tools = tools or {}
        self.event_emitter = event_emitter
        self.tracer = None
        self.config = {"agent_type": self.tools.get("__kind__", "analysis")}
        self.kind = str(self.tools.get("__kind__") or "analysis")
        self.name = self.kind
        self._agent_results = {}

    async def run(self, input_data: dict[str, Any]) -> AgentResult:
        self.llm_service.inputs.append(input_data)
        await asyncio.sleep(0.01)

        if self.kind == "analysis":
            config = input_data.get("config", {}) if isinstance(input_data, dict) else {}
            risk_point = config.get("single_risk_point") if isinstance(config, dict) else None
            has_contract = bool(input_data.get("task_context")) and isinstance(risk_point, dict)
            findings = []
            if has_contract:
                findings = [
                    {
                        "title": f"Issue in {risk_point.get('file_path', 'unknown')}",
                        "file_path": risk_point.get("file_path", ""),
                        "line_start": risk_point.get("line_start", 1),
                        "vulnerability_type": "test_issue",
                        "description": "analysis result",
                    }
                ]
            return AgentResult(
                success=True,
                data={
                    "findings": findings,
                    "steps": [],
                    **(
                        {}
                        if has_contract
                        else {"degraded_reason": "missing_single_risk_point"}
                    ),
                },
            )

        config = input_data.get("config", {}) if isinstance(input_data, dict) else {}
        finding = config.get("queue_finding") if isinstance(config, dict) else None
        if not isinstance(finding, dict) or not input_data.get("task_context"):
            return AgentResult(
                success=True,
                data={
                    "findings": [],
                    "verified_count": 0,
                    "likely_count": 0,
                    "false_positive_count": 0,
                    "candidate_count": 0,
                    "verification_todo_summary": {
                        "total": 0,
                        "verified": 0,
                        "false_positive": 0,
                        "blocked": 0,
                        "pending": 0,
                        "blocked_reasons_top": [],
                        "per_item_compact": [],
                    },
                    "note": "missing queue finding",
                },
            )

        fingerprint = f"{finding.get('file_path', '')}:{finding.get('line_start', '')}"
        attempts = self.llm_service.attempts
        attempts[fingerprint] = attempts.get(fingerprint, 0) + 1
        should_fail = bool(finding.get("fail_first")) and attempts[fingerprint] == 1

        if should_fail:
            return AgentResult(
                success=False,
                error="verification_failed",
                data={
                    "findings": [],
                    "verified_count": 0,
                    "likely_count": 0,
                    "false_positive_count": 0,
                    "candidate_count": 1,
                    "verification_todo_summary": {
                        "total": 1,
                        "verified": 0,
                        "false_positive": 0,
                        "blocked": 0,
                        "pending": 1,
                        "blocked_reasons_top": [],
                        "per_item_compact": [
                            {
                                "id": fingerprint,
                                "status": "pending",
                                "title": finding.get("title", ""),
                            }
                        ],
                    },
                },
            )

        verified_finding = {
            **finding,
            "is_verified": True,
            "vulnerability_type": finding.get("vulnerability_type", "test_issue"),
            "description": finding.get("description", "verified result"),
        }
        return AgentResult(
            success=True,
            data={
                "findings": [verified_finding],
                "verified_count": 1,
                "likely_count": 0,
                "false_positive_count": 0,
                "candidate_count": 1,
                "verification_todo_summary": {
                    "total": 1,
                    "verified": 1,
                    "false_positive": 0,
                    "blocked": 0,
                    "pending": 0,
                    "blocked_reasons_top": [],
                    "per_item_compact": [
                        {
                            "id": fingerprint,
                            "status": "verified",
                            "title": finding.get("title", ""),
                        }
                    ],
                },
            },
        )

    def reset_session_memory(self):
        pass


class MockOrchestrator:
    """模拟 Orchestrator。"""

    def __init__(self):
        analysis_llm = MagicMock()
        analysis_llm.inputs = []
        analysis_llm.attempts = {}

        verification_llm = MagicMock()
        verification_llm.inputs = []
        verification_llm.attempts = {}

        self.sub_agents = {
            "analysis": MockAgent(analysis_llm, {"__kind__": "analysis"}),
            "verification": MockAgent(verification_llm, {"__kind__": "verification"}),
        }
        self.sub_agents["analysis"].name = "analysis"
        self.sub_agents["verification"].name = "verification"

        self.is_cancelled = False
        self._all_findings = []
        self._agent_results = {}
        self._agent_handoffs = {}
        self._verified_queue_fingerprints = set()
        self._last_recon_risk_point = None
        self._runtime_context = {
            "project_info": {"name": "demo", "root": "/repo"},
            "config": {},
            "project_root": "/repo",
            "task_id": "test_task",
        }

    async def emit_event(self, event_type: str, message: str):
        return None

    def _normalize_finding(self, finding: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(finding)
        normalized.setdefault("title", "issue")
        normalized.setdefault("description", "desc")
        normalized.setdefault("vulnerability_type", "test_issue")
        normalized.setdefault("line_start", 1)
        return normalized

    def _build_queue_fingerprint(self, finding: dict[str, Any]) -> str:
        return f"{finding.get('file_path', '')}:{finding.get('line_start', '')}"

    def _build_handoff_for_agent(self, target_agent: str, task: str, context: str):
        return None

    def _extract_single_risk_point_for_analysis(
        self,
        *,
        params: dict[str, Any],
        context: str,
        runtime_config: dict[str, Any],
        handoff,
    ):
        return params.get("single_risk_point") or params.get("risk_point")

    async def _dispatch_agent(self, params: dict[str, Any]):
        agent_name = str(params.get("agent") or "")
        agent = self.sub_agents[agent_name]
        runtime_config: dict[str, Any] = {}
        if agent_name == "analysis":
            risk_point = params.get("risk_point") or {}
            runtime_config = {
                "single_risk_mode": True,
                "single_risk_point": risk_point,
                "target_files": [risk_point.get("file_path", "")],
            }
        elif agent_name == "verification":
            runtime_config = {
                "queue_finding": params.get("finding") or {},
            }

        result = await agent.run(
            {
                "task": params.get("task", ""),
                "task_context": params.get("context", ""),
                "project_info": self._runtime_context["project_info"],
                "config": runtime_config,
                "project_root": self._runtime_context["project_root"],
                "previous_results": {"findings": list(self._all_findings)},
            }
        )

        payload = dict(result.data) if isinstance(result.data, dict) else {}
        payload["_run_success"] = bool(result.success)
        if result.error:
            payload["_run_error"] = str(result.error)
        self._agent_results[agent_name] = payload

        for finding in payload.get("findings", []):
            normalized = self._normalize_finding(finding)
            if normalized not in self._all_findings:
                self._all_findings.append(normalized)
        return "ok"


class MockQueue:
    """模拟队列服务。"""

    def __init__(self, items):
        self.items = list(items)
        self.index = 0

    def dequeue(self, task_id: str):
        if self.index >= len(self.items):
            return None
        item = self.items[self.index]
        self.index += 1
        return item

    def dequeue_finding(self, task_id: str):
        return self.dequeue(task_id)


@pytest.mark.asyncio
async def test_parallel_analysis_uses_dispatch_contract_and_aggregates_findings():
    orchestrator = MockOrchestrator()
    risk_points = [
        {"file_path": "test1.py", "line_start": 10},
        {"file_path": "test2.py", "line_start": 20},
        {"file_path": "test3.py", "line_start": 30},
    ]
    queue = MockQueue(risk_points)
    executor = ParallelPhaseExecutor(orchestrator, "analysis", max_workers=2, enable_parallel=True)
    state = WorkflowState()

    await executor.run_parallel_analysis(state=state, task_id="test_task", recon_queue=queue)

    assert state.analysis_risk_points_processed == 3
    assert state.total_iterations == 3
    assert len(orchestrator._all_findings) == 3
    assert len(orchestrator._agent_results["analysis"]["findings"]) == 3

    recorded_inputs = orchestrator.sub_agents["analysis"].llm_service.inputs
    assert len(recorded_inputs) == 3
    assert all("task_context" in item for item in recorded_inputs)
    assert all(item.get("project_root") == "/repo" for item in recorded_inputs)
    assert all(item.get("config", {}).get("single_risk_point") for item in recorded_inputs)


@pytest.mark.asyncio
async def test_parallel_verification_uses_dispatch_contract_and_keeps_metadata():
    orchestrator = MockOrchestrator()
    findings = [
        {"file_path": "test1.py", "line_start": 10, "title": "SQL Injection"},
        {"file_path": "test2.py", "line_start": 20, "title": "XSS"},
        {"file_path": "test3.py", "line_start": 30, "title": "CSRF"},
    ]
    queue = MockQueue(findings)
    executor = ParallelPhaseExecutor(
        orchestrator,
        "verification",
        max_workers=2,
        enable_parallel=True,
    )
    state = WorkflowState()

    await executor.run_parallel_verification(state=state, task_id="test_task", vuln_queue=queue)

    assert state.vuln_queue_findings_processed == 3
    assert state.total_iterations == 3
    verification_result = orchestrator._agent_results["verification"]
    assert verification_result["candidate_count"] == 3
    assert verification_result["verified_count"] == 3
    assert len(verification_result["findings"]) == 3
    assert verification_result["verification_todo_summary"]["total"] == 3
    assert verification_result["verification_todo_summary"]["pending"] == 0

    recorded_inputs = orchestrator.sub_agents["verification"].llm_service.inputs
    assert len(recorded_inputs) == 3
    assert all("task_context" in item for item in recorded_inputs)
    assert all(item.get("config", {}).get("queue_finding") for item in recorded_inputs)
    assert all(item.get("project_root") == "/repo" for item in recorded_inputs)


@pytest.mark.asyncio
async def test_sequential_fallback():
    orchestrator = MockOrchestrator()
    risk_points = [
        {"file_path": "test1.py", "line_start": 10},
        {"file_path": "test2.py", "line_start": 20},
    ]
    queue = MockQueue(risk_points)
    executor = ParallelPhaseExecutor(orchestrator, "analysis", max_workers=1, enable_parallel=True)
    state = WorkflowState()

    await executor.run_parallel_analysis(state=state, task_id="test_task", recon_queue=queue)

    assert state.analysis_risk_points_processed == 2
    assert len(orchestrator._all_findings) == 2


@pytest.mark.asyncio
async def test_worker_isolation():
    orchestrator = MockOrchestrator()
    executor = ParallelPhaseExecutor(orchestrator, "analysis", max_workers=3, enable_parallel=True)

    worker_agents = [executor._create_worker_agent(i) for i in range(3)]

    assert len({id(agent) for agent in worker_agents}) == 3
    assert len({agent.name for agent in worker_agents}) == 3
    assert all("worker" in agent.name for agent in worker_agents)


@pytest.mark.asyncio
async def test_parallel_verification_retries_duplicate_after_failed_attempt():
    orchestrator = MockOrchestrator()
    findings = [
        {
            "file_path": "dup.py",
            "line_start": 10,
            "title": "SQL Injection",
            "fail_first": True,
        },
        {
            "file_path": "dup.py",
            "line_start": 10,
            "title": "SQL Injection",
            "fail_first": True,
        },
    ]
    queue = MockQueue(findings)
    executor = ParallelPhaseExecutor(
        orchestrator,
        "verification",
        max_workers=2,
        enable_parallel=True,
    )
    state = WorkflowState()

    await executor.run_parallel_verification(state=state, task_id="test_task", vuln_queue=queue)

    recorded_inputs = orchestrator.sub_agents["verification"].llm_service.inputs
    assert len(recorded_inputs) == 2
    assert "dup.py:10" in orchestrator._verified_queue_fingerprints
    assert orchestrator._agent_results["verification"]["verified_count"] == 1
    assert orchestrator._agent_results["verification"]["candidate_count"] == 2


@pytest.mark.asyncio
async def test_cancellation():
    orchestrator = MockOrchestrator()
    risk_points = [{"file_path": f"test{i}.py", "line_start": i * 10} for i in range(10)]
    queue = MockQueue(risk_points)
    executor = ParallelPhaseExecutor(orchestrator, "analysis", max_workers=2, enable_parallel=True)
    state = WorkflowState()

    async def cancel_after_delay():
        await asyncio.sleep(0.015)
        orchestrator.is_cancelled = True

    cancel_task = asyncio.create_task(cancel_after_delay())
    await executor.run_parallel_analysis(state=state, task_id="test_task", recon_queue=queue)
    await cancel_task

    assert state.analysis_risk_points_processed < 10


@pytest.mark.asyncio
async def test_empty_queue():
    orchestrator = MockOrchestrator()
    queue = MockQueue([])
    executor = ParallelPhaseExecutor(orchestrator, "analysis", max_workers=2, enable_parallel=True)
    state = WorkflowState()

    await executor.run_parallel_analysis(state=state, task_id="test_task", recon_queue=queue)

    assert state.analysis_risk_points_processed == 0


@pytest.mark.asyncio
async def test_concurrent_limit():
    orchestrator = MockOrchestrator()
    queue = MockQueue(
        [{"file_path": f"test{i}.py", "line_start": i * 10} for i in range(10)]
    )
    executor = ParallelPhaseExecutor(orchestrator, "analysis", max_workers=2, enable_parallel=True)
    state = WorkflowState()
    max_active = 0

    async def tracked_worker(*args, **kwargs):
        nonlocal max_active
        async with executor.semaphore:
            current_active = executor.max_workers - executor.semaphore._value
            max_active = max(max_active, current_active)
            await asyncio.sleep(0.01)

    with patch.object(executor, "_analysis_worker", side_effect=tracked_worker):
        await executor.run_parallel_analysis(state=state, task_id="test_task", recon_queue=queue)

    assert max_active <= 2
