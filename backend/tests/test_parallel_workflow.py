import ast
import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from app.services.agent.agents.base import AgentResult
from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue
from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
from app.services.agent.workflow import (
    AuditWorkflowEngine,
    WorkflowOrchestratorAgent,
    WorkflowPhase,
)
from app.services.agent.workflow.models import WorkflowConfig

TEST_TASK_ID = "parallel-workflow-task"
THIS_FILE = Path(__file__).resolve()
BACKEND_ROOT = THIS_FILE.parent.parent
REPO_ROOT = BACKEND_ROOT if (BACKEND_ROOT / "test_projects").exists() else BACKEND_ROOT.parent
VULNERABLE_FILE = REPO_ROOT / "test_projects" / "minimal_test" / "vulnerable.py"
EXPECTED_FINDINGS = 4


class _RecordingEventEmitter:
    def __init__(self) -> None:
        self.events: List[Any] = []

    async def emit(self, event: Any) -> None:
        self.events.append(event)


class _FakeLLMService:
    def get_agent_timeout_config(self) -> Dict[str, int]:
        return {
            "sub_agent_timeout": 60,
            "tool_timeout": 30,
            "llm_first_token_timeout": 30,
            "llm_stream_timeout": 30,
        }


class ParallelStubAgent:
    """Minimal Agent stub that can be cloned by ParallelPhaseExecutor."""

    def __init__(self, llm_service=None, tools=None, event_emitter=None, tracer=None):
        self.llm_service = llm_service
        self.tools = tools or {}
        self.event_emitter = event_emitter
        self.tracer = tracer
        ctx = self.tools.get("_stub_ctx", {})
        self.config = {"metadata": {"agent_type": ctx.get("agent_type", "stub")}}
        self.name = ctx.get("name", ctx.get("agent_type", "stub"))
        self._run_impl = ctx.get("run_impl")
        self._reset_hook = ctx.get("on_reset")
        self._registered = True
        self._agent_id = f"{self.name}-{id(self)}"
        self.parent_id = None

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        if callable(self._run_impl):
            return await self._run_impl(self, input_data)
        return AgentResult(success=True)

    def reset_session_memory(self) -> None:
        if callable(self._reset_hook):
            self._reset_hook(self)

    def set_parent_id(self, parent_id: Any) -> None:
        self.parent_id = parent_id

    def _register_to_registry(self, task: str = "") -> None:  # noqa: D401 - test stub
        self._registered = True


def _load_vulnerable_points() -> List[Dict[str, Any]]:
    source = VULNERABLE_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(VULNERABLE_FILE))
    points: List[Dict[str, Any]] = []
    severity_map = {
        "sql_injection": "critical",
        "command_injection": "high",
        "path_traversal": "high",
        "xss": "medium",
    }
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.endswith("_vuln"):
            vuln_type = node.name.replace("_vuln", "")
            doc = ast.get_docstring(node) or f"Potential issue in {node.name}"
            points.append(
                {
                    "id": node.name,
                    "file_path": str(VULNERABLE_FILE),
                    "line_start": node.lineno,
                    "description": doc,
                    "function_name": node.name,
                    "vulnerability_type": vuln_type,
                    "severity": severity_map.get(vuln_type, "medium"),
                }
            )
    assert len(points) == EXPECTED_FINDINGS, "minimal test project should expose four risk points"
    return points


def _extract_worker_index(worker_name: str) -> int:
    if "_worker_" in worker_name:
        try:
            return int(worker_name.rsplit("_", 1)[-1])
        except ValueError:
            return 0
    return 0


def _build_recon_run(ctx: Dict[str, Any]):
    async def _run(agent: ParallelStubAgent, _input_data: Dict[str, Any]) -> AgentResult:
        queue: InMemoryReconRiskQueue = ctx["recon_queue"]
        task_id: str = ctx["task_id"]
        queue.clear(task_id)
        for risk_point in ctx["risk_points"]:
            queue.enqueue(task_id, risk_point)
        result = AgentResult(success=True, data={"risk_points": len(ctx["risk_points"])})
        result.findings = []  # type: ignore[attr-defined]
        return result

    return _run


def _build_analysis_run(ctx: Dict[str, Any]):
    async def _run(agent: ParallelStubAgent, agent_input: Dict[str, Any]) -> AgentResult:
        risk_point = agent_input.get("risk_point")
        if not risk_point:
            risk_point = json.loads(agent_input.get("context", "{}"))
        worker_name = agent.name
        start = time.perf_counter()
        event = {
            "worker": worker_name,
            "start": start,
            "subject": risk_point.get("function_name"),
        }
        ctx["analysis_events"].append(event)
        idx = _extract_worker_index(worker_name)
        await asyncio.sleep(0.02 + idx * 0.005)
        finding = {
            "title": f"{risk_point['function_name']} confirmed",
            "file_path": risk_point["file_path"],
            "line_start": risk_point["line_start"],
            "vulnerability_type": risk_point["vulnerability_type"],
            "severity": risk_point["severity"],
            "description": risk_point["description"],
        }
        ctx["vuln_queue"].enqueue_finding(ctx["task_id"], finding)
        event["end"] = time.perf_counter()
        event["finding_title"] = finding["title"]
        result = AgentResult(success=True, data={"finding": finding})
        result.findings = [finding]  # type: ignore[attr-defined]
        return result

    return _run


def _build_verification_run(ctx: Dict[str, Any]):
    async def _run(agent: ParallelStubAgent, agent_input: Dict[str, Any]) -> AgentResult:
        finding_payload = json.loads(agent_input.get("context", "{}"))
        worker_name = agent.name
        start = time.perf_counter()
        event = {
            "worker": worker_name,
            "start": start,
            "title": finding_payload.get("title"),
        }
        ctx["verification_events"].append(event)
        idx = _extract_worker_index(worker_name)
        await asyncio.sleep(0.015 + idx * 0.003)
        event["end"] = time.perf_counter()
        result = AgentResult(success=True, data={"verified": True})
        result.findings = [finding_payload]  # type: ignore[attr-defined]
        return result

    return _run


def _build_report_run(ctx: Dict[str, Any]):
    async def _run(agent: ParallelStubAgent, input_data: Dict[str, Any]) -> AgentResult:
        finding = input_data.get("finding") or {}
        worker_name = agent.name
        start = time.perf_counter()
        event = {
            "worker": worker_name,
            "start": start,
            "title": finding.get("title"),
        }
        ctx["report_events"].append(event)
        idx = _extract_worker_index(worker_name)
        await asyncio.sleep(0.02 + idx * 0.004)
        event["end"] = time.perf_counter()
        result = AgentResult(
            success=True,
            data={"vulnerability_report": f"# Report for {finding.get('title', 'unknown')}"},
            iterations=1,
            tool_calls=1,
            tokens_used=42,
        )
        return result

    return _run


def _max_parallelism(events: List[Dict[str, Any]]) -> int:
    timeline: List[tuple[float, int]] = []
    for event in events:
        start = event.get("start")
        end = event.get("end")
        if start is None or end is None:
            continue
        timeline.append((start, 1))
        timeline.append((end, -1))
    timeline.sort(key=lambda x: x[0])
    concurrent = 0
    max_concurrent = 0
    for _, delta in timeline:
        concurrent += delta
        max_concurrent = max(max_concurrent, concurrent)
    return max_concurrent


@pytest.fixture
def instrumentation() -> Dict[str, List[Dict[str, Any]]]:
    return {"analysis_events": [], "verification_events": [], "report_events": []}


@pytest.fixture
def workflow_harness(instrumentation):
    recon_queue = InMemoryReconRiskQueue()
    vuln_queue = InMemoryVulnerabilityQueue()
    llm_service = _FakeLLMService()
    event_emitter = _RecordingEventEmitter()
    workflow_config = WorkflowConfig(
        enable_parallel_analysis=True,
        analysis_max_workers=3,
        enable_parallel_verification=True,
        verification_max_workers=2,
        enable_parallel_report=True,
        report_max_workers=2,
    )
    risk_points = _load_vulnerable_points()

    recon_ctx = {
        "agent_type": "recon",
        "name": "recon_parallel_stub",
        "task_id": TEST_TASK_ID,
        "recon_queue": recon_queue,
        "risk_points": risk_points,
    }
    recon_ctx["run_impl"] = _build_recon_run(recon_ctx)

    analysis_ctx = {
        "agent_type": "analysis",
        "name": "analysis_parallel_stub",
        "task_id": TEST_TASK_ID,
        "vuln_queue": vuln_queue,
        "analysis_events": instrumentation["analysis_events"],
    }
    analysis_ctx["run_impl"] = _build_analysis_run(analysis_ctx)

    verification_ctx = {
        "agent_type": "verification",
        "name": "verification_parallel_stub",
        "task_id": TEST_TASK_ID,
        "verification_events": instrumentation["verification_events"],
    }
    verification_ctx["run_impl"] = _build_verification_run(verification_ctx)

    report_ctx = {
        "agent_type": "report",
        "name": "report_parallel_stub",
        "task_id": TEST_TASK_ID,
        "report_events": instrumentation["report_events"],
    }
    report_ctx["run_impl"] = _build_report_run(report_ctx)

    sub_agents = {
        "recon": ParallelStubAgent(llm_service, {"_stub_ctx": recon_ctx}, event_emitter),
        "analysis": ParallelStubAgent(llm_service, {"_stub_ctx": analysis_ctx}, event_emitter),
        "verification": ParallelStubAgent(llm_service, {"_stub_ctx": verification_ctx}, event_emitter),
        "report": ParallelStubAgent(llm_service, {"_stub_ctx": report_ctx}, event_emitter),
    }

    orchestrator = WorkflowOrchestratorAgent(
        llm_service=llm_service,
        tools={},
        event_emitter=event_emitter,
        sub_agents=sub_agents,
        recon_queue_service=recon_queue,
        vuln_queue_service=vuln_queue,
        workflow_config=workflow_config,
    )
    orchestrator.stream_llm_call = AsyncMock(return_value=("{\"duplicates\": []}", 0))

    yield {
        "orchestrator": orchestrator,
        "recon_queue": recon_queue,
        "vuln_queue": vuln_queue,
        "workflow_config": workflow_config,
    }


@pytest.mark.asyncio
async def test_parallel_workflow_end_to_end(workflow_harness, instrumentation):
    orchestrator = workflow_harness["orchestrator"]
    recon_queue = workflow_harness["recon_queue"]
    vuln_queue = workflow_harness["vuln_queue"]
    workflow_config = workflow_harness["workflow_config"]

    assert orchestrator._workflow_config.analysis_max_workers == workflow_config.analysis_max_workers
    assert orchestrator._workflow_config.verification_max_workers == workflow_config.verification_max_workers
    assert orchestrator._workflow_config.report_max_workers == workflow_config.report_max_workers

    engine = AuditWorkflowEngine(
        recon_queue_service=recon_queue,
        vuln_queue_service=vuln_queue,
        task_id=TEST_TASK_ID,
        orchestrator=orchestrator,
        workflow_config=workflow_config,
    )

    assert engine.analysis_executor.max_workers == workflow_config.analysis_max_workers
    assert engine.verification_executor.max_workers == workflow_config.verification_max_workers
    assert engine.report_executor.max_workers == workflow_config.report_max_workers
    assert engine.analysis_executor.enable_parallel is True
    assert engine.verification_executor.enable_parallel is True
    assert engine.report_executor.enable_parallel is True

    start = time.perf_counter()
    state = await engine.run(
        project_info={"root": str(REPO_ROOT)},
        config={},
        project_root=str(REPO_ROOT),
        task_id=TEST_TASK_ID,
    )
    elapsed = time.perf_counter() - start

    assert elapsed < 30, "parallel workflow test should finish quickly"
    assert state.phase == WorkflowPhase.COMPLETE
    assert state.analysis_risk_points_processed == EXPECTED_FINDINGS
    assert state.vuln_queue_findings_processed == EXPECTED_FINDINGS

    assert len(state.all_findings) == EXPECTED_FINDINGS
    unique_titles = {finding.get("title") for finding in state.all_findings}
    assert len(unique_titles) == EXPECTED_FINDINGS

    analysis_events = instrumentation["analysis_events"]
    verification_events = instrumentation["verification_events"]

    analysis_workers = {evt["worker"] for evt in analysis_events}
    verification_workers = {evt["worker"] for evt in verification_events}
    assert len(analysis_workers) == workflow_config.analysis_max_workers
    assert len(verification_workers) == workflow_config.verification_max_workers

    analysis_parallelism = _max_parallelism(analysis_events)
    verification_parallelism = _max_parallelism(verification_events)
    assert analysis_parallelism >= 2
    assert verification_parallelism >= 2
    assert analysis_parallelism <= workflow_config.analysis_max_workers
    assert verification_parallelism <= workflow_config.verification_max_workers

    findings_by_title = {finding["title"]: finding for finding in state.all_findings}
    worker_lookup = {evt.get("finding_title"): evt["worker"] for evt in analysis_events if evt.get("finding_title")}

    report = {
        "duration_s": round(elapsed, 3),
        "analysis_workers_configured": workflow_config.analysis_max_workers,
        "analysis_workers_observed": sorted(analysis_workers),
        "analysis_max_parallelism": analysis_parallelism,
        "verification_workers_configured": workflow_config.verification_max_workers,
        "verification_workers_observed": sorted(verification_workers),
        "verification_max_parallelism": verification_parallelism,
        "findings": [
            {
                "title": title,
                "worker": worker_lookup.get(title, "unknown"),
                "severity": findings_by_title[title].get("severity"),
            }
            for title in sorted(findings_by_title.keys())
        ],
    }
    print("Parallel Workflow Report:\n" + json.dumps(report, ensure_ascii=False, indent=2))


@pytest.mark.asyncio
async def test_report_phase_runs_in_parallel(workflow_harness, instrumentation):
    orchestrator = workflow_harness["orchestrator"]
    recon_queue = workflow_harness["recon_queue"]
    vuln_queue = workflow_harness["vuln_queue"]
    workflow_config = workflow_harness["workflow_config"]

    orchestrator._all_findings = [
        {
            "title": f"confirmed finding {idx}",
            "verdict": "confirmed",
            "file_path": str(VULNERABLE_FILE),
            "line_start": idx,
        }
        for idx in range(1, 5)
    ]

    engine = AuditWorkflowEngine(
        recon_queue_service=recon_queue,
        vuln_queue_service=vuln_queue,
        task_id=TEST_TASK_ID,
        orchestrator=orchestrator,
        workflow_config=workflow_config,
    )

    state = await engine.run(
        project_info={"root": str(REPO_ROOT), "name": "parallel-report-test"},
        config={},
        project_root=str(REPO_ROOT),
        task_id=TEST_TASK_ID,
    )

    assert state.phase == WorkflowPhase.COMPLETE
    assert state.report_findings_total == 4
    assert state.report_findings_processed == 4
    assert len(state.finding_reports) == 4
    reportable_findings = [
        finding
        for finding in orchestrator._all_findings
        if str(finding.get("verdict") or "").lower() in {"confirmed", "likely"}
    ]
    assert reportable_findings
    assert all(finding.get("vulnerability_report") for finding in reportable_findings)

    report_events = instrumentation["report_events"]
    report_workers = {evt["worker"] for evt in report_events}
    report_parallelism = _max_parallelism(report_events)

    assert len(report_workers) == workflow_config.report_max_workers
    assert report_parallelism >= 2
    assert report_parallelism <= workflow_config.report_max_workers
