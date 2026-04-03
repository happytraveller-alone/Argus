"""
Test suite for AuditWorkflowEngine and WorkflowOrchestratorAgent.

验证确定性 Workflow 的核心行为：
1. WorkflowState 阶段转换正确性
2. Recon 阶段在队列为空时有限重试，已有风险点时不重复调度
3. Analysis 阶段按 Recon 队列条目数调度（一风险点一次）
4. Verification 阶段按漏洞队列条目数调度（一漏洞一次）
5. 重复指纹自动跳过（幂等）
6. 取消信号正确传播
7. Verification 为空时触发降级兜底
8. 未提供队列服务时回退到 LLM-driven 模式
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.agents.base import AgentResult
from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue
from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
from app.services.agent.workflow import (
    AuditWorkflowEngine,
    WorkflowOrchestratorAgent,
    WorkflowPhase,
    WorkflowState,
    WorkflowStepRecord,
)
from app.services.agent.workflow.models import WorkflowConfig


# ──────────────────────────────────────────────────────────────────────────────
# 通用假对象
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class _FakeEvent:
    event_type: str
    message: Optional[str]
    metadata: Optional[Dict[str, Any]] = None


class _FakeEventEmitter:
    def __init__(self) -> None:
        self.events: List[_FakeEvent] = []

    async def emit(self, event_data: Any) -> None:
        self.events.append(
            _FakeEvent(
                event_type=getattr(event_data, "event_type", ""),
                message=getattr(event_data, "message", None),
                metadata=getattr(event_data, "metadata", None),
            )
        )


def _make_finding(title: str, file_path: str = "app.py", line_start: int = 10) -> Dict[str, Any]:
    return {
        "title": title,
        "file_path": file_path,
        "line_start": line_start,
        "vulnerability_type": "sql_injection",
        "severity": "high",
        "description": f"Test finding: {title}",
    }


def _make_risk_point(file_path: str = "app.py", line_start: int = 10) -> Dict[str, Any]:
    return {
        "file_path": file_path,
        "line_start": line_start,
        "description": f"Risk at {file_path}:{line_start}",
    }


def _build_orchestrator(
    recon_queue: InMemoryReconRiskQueue,
    vuln_queue: InMemoryVulnerabilityQueue,
    event_emitter: Optional[_FakeEventEmitter] = None,
) -> WorkflowOrchestratorAgent:
    """构建 WorkflowOrchestratorAgent，使用假 LLM 服务。"""
    llm_service = MagicMock()
    llm_service.get_agent_timeout_config = MagicMock(
        return_value={
            "sub_agent_timeout": 60,
            "tool_timeout": 30,
            "llm_first_token_timeout": 30,
            "llm_stream_timeout": 30,
        }
    )
    emitter = event_emitter or _FakeEventEmitter()
    agent = WorkflowOrchestratorAgent(
        llm_service=llm_service,
        tools={},
        event_emitter=emitter,
        sub_agents={"recon": MagicMock(), "analysis": MagicMock(), "verification": MagicMock()},
        recon_queue_service=recon_queue,
        vuln_queue_service=vuln_queue,
        workflow_config=WorkflowConfig(
            enable_parallel_analysis=False,
            enable_parallel_verification=False,
            enable_parallel_report=False,
        ),
    )
    return agent


# ──────────────────────────────────────────────────────────────────────────────
# WorkflowState 单元测试
# ──────────────────────────────────────────────────────────────────────────────

class TestWorkflowState:
    def test_initial_phase_is_init(self):
        state = WorkflowState()
        assert state.phase == WorkflowPhase.INIT

    def test_to_summary_keys(self):
        state = WorkflowState()
        state.phase = WorkflowPhase.ANALYSIS
        state.all_findings = [_make_finding("F1")]
        summary = state.to_summary()
        assert summary["phase"] == "analysis"
        assert summary["all_findings_count"] == 1

    def test_step_record_serialization(self):
        record = WorkflowStepRecord(
            phase=WorkflowPhase.RECON,
            agent="recon",
            success=True,
            findings_count=3,
            duration_ms=500,
        )
        d = record.to_dict()
        assert d["phase"] == "recon"
        assert d["success"] is True
        assert d["findings_count"] == 3


# ──────────────────────────────────────────────────────────────────────────────
# AuditWorkflowEngine 单元测试
# ──────────────────────────────────────────────────────────────────────────────

TASK_ID = "test-task-001"


@pytest.fixture
def fresh_queues():
    return InMemoryReconRiskQueue(), InMemoryVulnerabilityQueue()


@pytest.fixture
def orchestrator_with_queues(fresh_queues):
    recon_q, vuln_q = fresh_queues
    orch = _build_orchestrator(recon_q, vuln_q)
    return orch, recon_q, vuln_q


# ───── 辅助：装配 _dispatch_agent mock ─────

def _install_dispatch_mock(orch, vuln_queue, findings_to_push: Optional[List] = None):
    """
    替换 _dispatch_agent，模拟各子 Agent 行为：
    - recon: 向 recon_queue push 风险点（调用者在测试前预置）
    - analysis: 向 vuln_queue push findings，设置 _agent_results["analysis"]
    - verification: 设置 _agent_results["verification"]，追加 _all_findings
    """
    calls: List[Dict] = []
    dispatched_for_analysis = [0]

    async def mock_dispatch(params: Dict) -> str:
        agent_name = str(params.get("agent", "")).lower()
        calls.append(params)

        if agent_name == "recon":
            orch._agent_results["recon"] = {"_run_success": True, "high_risk_areas": []}
            return "Recon 完成"

        if agent_name == "analysis":
            idx = dispatched_for_analysis[0]
            dispatched_for_analysis[0] += 1
            flist = (findings_to_push or [])
            finding = flist[idx] if idx < len(flist) else _make_finding(f"Finding-{idx}")
            # 模拟 Analysis 向漏洞队列 push
            vuln_queue.enqueue_finding(TASK_ID, finding)
            orch._agent_results["analysis"] = {
                "_run_success": True,
                "findings": [finding],
            }
            return "Analysis 完成"

        if agent_name == "verification":
            finding_from_params = params.get("finding") or {}
            orch._agent_results["verification"] = {
                "_run_success": True,
                "findings": [finding_from_params],
            }
            if isinstance(finding_from_params, dict) and finding_from_params:
                normalized = orch._normalize_finding(finding_from_params)
                if normalized:
                    orch._all_findings.append(normalized)
            return "Verification 完成"

        return "未知 Agent"

    orch._dispatch_agent = mock_dispatch
    return calls


class TestAuditWorkflowEnginePhases:
    @pytest.mark.asyncio
    async def test_full_workflow_phases(self, orchestrator_with_queues):
        """完整路径：Recon → Analysis（1 风险点）→ Verification（1 漏洞）→ COMPLETE"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        # 预置 1 条 recon 风险点
        recon_q.enqueue(TASK_ID, _make_risk_point("app.py", 10))
        calls = _install_dispatch_mock(orch, vuln_q)

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        assert state.phase == WorkflowPhase.COMPLETE
        # recon: 1 次；analysis: 1 次；verification: 1 次
        dispatched_agents = [c["agent"] for c in calls]
        assert dispatched_agents.count("recon") == 1
        assert dispatched_agents.count("analysis") == 1
        assert dispatched_agents.count("verification") == 1

    @pytest.mark.asyncio
    async def test_recon_only_once(self, orchestrator_with_queues):
        """Recon 队列已有风险点时，只调度一次 Recon"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        recon_q.enqueue(TASK_ID, _make_risk_point("seed.py", 12))
        calls = _install_dispatch_mock(orch, vuln_q)

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        await engine.run({}, {}, "/tmp", TASK_ID)

        recon_calls = [c for c in calls if c["agent"] == "recon"]
        assert len(recon_calls) == 1

    @pytest.mark.asyncio
    async def test_hybrid_with_bootstrap_candidates_skips_recon(self, orchestrator_with_queues):
        """混合扫描且静态预扫有候选时：跳过 Recon，直接进入 Analysis。"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        calls = _install_dispatch_mock(orch, vuln_q)
        config = {
            "audit_source_mode": "hybrid",
            "skip_recon_when_bootstrap_available": True,
            "static_bootstrap_candidate_count": 1,
            "bootstrap_findings": [_make_risk_point("seed.py", 88)],
        }

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, config, "/tmp", TASK_ID)

        recon_calls = [c for c in calls if c["agent"] == "recon"]
        analysis_calls = [c for c in calls if c["agent"] == "analysis"]
        assert len(recon_calls) == 0
        assert len(analysis_calls) >= 1
        assert state.recon_done is True

    @pytest.mark.asyncio
    async def test_intelligent_mode_does_not_skip_recon_even_with_bootstrap_candidates(
        self, orchestrator_with_queues
    ):
        """智能审计模式下不启用跳过 Recon 逻辑。"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        recon_q.enqueue(TASK_ID, _make_risk_point("intelligent.py", 31))
        calls = _install_dispatch_mock(orch, vuln_q)
        config = {
            "audit_source_mode": "intelligent",
            "skip_recon_when_bootstrap_available": True,
            "static_bootstrap_candidate_count": 2,
            "bootstrap_findings": [_make_risk_point("seed.py", 99)],
        }

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        await engine.run({}, config, "/tmp", TASK_ID)

        recon_calls = [c for c in calls if c["agent"] == "recon"]
        assert len(recon_calls) == 1

    @pytest.mark.asyncio
    async def test_recon_retries_until_queue_receives_risk_point(self, orchestrator_with_queues):
        """首轮 Recon 未产出风险点时，应继续 Recon，直到队列有结果。"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        calls: List[Dict[str, Any]] = []
        recon_attempts = [0]

        async def mock_dispatch(params: Dict) -> str:
            calls.append(dict(params))
            agent_name = str(params.get("agent", "")).lower()

            if agent_name == "recon":
                recon_attempts[0] += 1
                if recon_attempts[0] == 2:
                    recon_q.enqueue(TASK_ID, _make_risk_point("retry.py", 88))
                orch._agent_results["recon"] = {"_run_success": True, "high_risk_areas": []}
                return "Recon 完成"

            if agent_name == "analysis":
                risk_point = params.get("risk_point") or {}
                finding = _make_finding(
                    "Retry finding",
                    file_path=risk_point.get("file_path", "retry.py"),
                    line_start=risk_point.get("line_start", 88),
                )
                vuln_q.enqueue_finding(TASK_ID, finding)
                orch._agent_results["analysis"] = {
                    "_run_success": True,
                    "findings": [finding],
                }
                return "Analysis 完成"

            if agent_name == "verification":
                finding_from_params = params.get("finding") or {}
                orch._agent_results["verification"] = {
                    "_run_success": True,
                    "findings": [finding_from_params],
                }
                if isinstance(finding_from_params, dict) and finding_from_params:
                    orch._all_findings.append(orch._normalize_finding(finding_from_params))
                return "Verification 完成"

            return "未知 Agent"

        orch._dispatch_agent = mock_dispatch

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        recon_calls = [c for c in calls if c["agent"] == "recon"]
        analysis_calls = [c for c in calls if c["agent"] == "analysis"]

        assert len(recon_calls) == 2
        assert "上一轮 Recon 未向 Recon 队列产出任何风险点" in recon_calls[1]["context"]
        assert len(analysis_calls) == 1
        assert state.analysis_risk_points_total == 1

    @pytest.mark.asyncio
    async def test_recon_stops_retrying_after_max_empty_attempts(self, orchestrator_with_queues):
        """Recon 连续空队列时，应在上限后停止重试，避免死循环。"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        calls: List[Dict[str, Any]] = []

        async def mock_dispatch(params: Dict) -> str:
            calls.append(dict(params))
            agent_name = str(params.get("agent", "")).lower()

            if agent_name == "recon":
                orch._agent_results["recon"] = {"_run_success": True, "high_risk_areas": []}
                return "Recon 完成"

            if agent_name == "analysis":
                orch._agent_results["analysis"] = {"_run_success": True, "findings": []}
                return "Analysis 完成"

            if agent_name == "verification":
                orch._agent_results["verification"] = {"_run_success": True, "findings": []}
                return "Verification 完成"

            return "未知 Agent"

        orch._dispatch_agent = mock_dispatch

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        recon_calls = [c for c in calls if c["agent"] == "recon"]
        analysis_calls = [c for c in calls if c["agent"] == "analysis"]

        assert len(recon_calls) == engine.RECON_EMPTY_QUEUE_MAX_ATTEMPTS
        assert len(analysis_calls) == 0
        assert state.analysis_risk_points_total == 0
        assert state.phase == WorkflowPhase.COMPLETE

    @pytest.mark.asyncio
    async def test_analysis_called_per_risk_point(self, orchestrator_with_queues):
        """Analysis 被调度次数 == Recon 队列风险点数量"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        n_risk_points = 3
        for i in range(n_risk_points):
            recon_q.enqueue(TASK_ID, _make_risk_point(f"file_{i}.py", i + 1))
        calls = _install_dispatch_mock(
            orch, vuln_q, [_make_finding(f"F{i}") for i in range(n_risk_points)]
        )

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        analysis_calls = [c for c in calls if c["agent"] == "analysis"]
        assert len(analysis_calls) == n_risk_points
        assert state.analysis_risk_points_processed == n_risk_points

    @pytest.mark.asyncio
    async def test_verification_called_per_finding(self, orchestrator_with_queues):
        """Verification 被调度次数 == 漏洞队列 finding 数量"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        n_findings = 4
        for i in range(n_findings):
            vuln_q.enqueue_finding(TASK_ID, _make_finding(f"Vuln-{i}", line_start=i + 100))
        # Recon 队列为空，Analysis 阶段跳过
        calls = _install_dispatch_mock(orch, vuln_q)
        # recon 需要手动完成，否则 _agent_results["recon"] 不存在
        orch._agent_results["recon"] = {"_run_success": True}

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        # recon: 1 次；analysis: 0 次（队列空）；verification: n_findings 次
        verify_calls = [c for c in calls if c["agent"] == "verification"]
        assert len(verify_calls) == n_findings
        assert state.vuln_queue_findings_processed == n_findings

    @pytest.mark.asyncio
    async def test_recon_queue_fully_drained(self, orchestrator_with_queues):
        """analysis 阶段结束后，Recon 风险点队列为空"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        for i in range(3):
            recon_q.enqueue(TASK_ID, _make_risk_point(f"f{i}.py", i))
        _install_dispatch_mock(orch, vuln_q)

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        await engine.run({}, {}, "/tmp", TASK_ID)

        assert recon_q.size(TASK_ID) == 0

    @pytest.mark.asyncio
    async def test_vuln_queue_fully_drained(self, orchestrator_with_queues):
        """verification 阶段结束后，漏洞队列为空"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        recon_q.enqueue(TASK_ID, _make_risk_point())
        calls = _install_dispatch_mock(orch, vuln_q, [_make_finding("F1")])

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        await engine.run({}, {}, "/tmp", TASK_ID)

        assert vuln_q.get_queue_size(TASK_ID) == 0

    @pytest.mark.asyncio
    async def test_risk_point_injected_into_analysis_params(self, orchestrator_with_queues):
        """analysis 调度时，risk_point 被注入到 params"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        rp = _make_risk_point("auth.py", 42)
        recon_q.enqueue(TASK_ID, rp)
        calls = _install_dispatch_mock(orch, vuln_q, [_make_finding("F1")])

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        await engine.run({}, {}, "/tmp", TASK_ID)

        analysis_call = next(c for c in calls if c["agent"] == "analysis")
        assert analysis_call["risk_point"]["file_path"] == "auth.py"
        assert analysis_call["risk_point"]["line_start"] == 42

    @pytest.mark.asyncio
    async def test_finding_injected_into_verification_params(self, orchestrator_with_queues):
        """verification 调度时，finding 被注入到 params"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        finding_to_verify = _make_finding("SQL注入", "db.py", 55)
        vuln_q.enqueue_finding(TASK_ID, finding_to_verify)
        # 跳过 recon/analysis（预置结果）
        orch._agent_results["recon"] = {"_run_success": True}
        calls = _install_dispatch_mock(orch, vuln_q)

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        await engine.run({}, {}, "/tmp", TASK_ID)

        verify_call = next(c for c in calls if c["agent"] == "verification")
        assert verify_call["finding"]["file_path"] == "db.py"
        assert verify_call["finding"]["line_start"] == 55


class TestDuplicateFingerprintSkipping:
    @pytest.mark.asyncio
    async def test_duplicate_fingerprint_skipped(self, orchestrator_with_queues):
        """同一 fingerprint 的 finding 只被验证一次"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        finding = _make_finding("XSS", "view.py", 10)
        # 入队两次（相同指纹）
        vuln_q.enqueue_finding(TASK_ID, finding)
        # 第二次因去重不会再入，但直接操作内部队列强制测试
        vuln_q.queues[TASK_ID].append(finding)  # bypass dedup to force duplicate

        orch._agent_results["recon"] = {"_run_success": True}
        calls = _install_dispatch_mock(orch, vuln_q)

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        # 第二次相同指纹应被幂等跳过
        verify_calls = [c for c in calls if c["agent"] == "verification"]
        # 第一次正常验证，第二次由于指纹已在 _verified_queue_fingerprints，应跳过
        assert len(verify_calls) == 1
        assert state.vuln_queue_findings_processed == 2  # processed (counted) 但只 dispatch 1 次

    @pytest.mark.asyncio
    async def test_verified_fingerprints_accumulated(self, orchestrator_with_queues):
        """所有成功验证的 fingerprint 都应加入 _verified_queue_fingerprints"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        findings = [_make_finding(f"F{i}", line_start=i + 1) for i in range(3)]
        for f in findings:
            vuln_q.enqueue_finding(TASK_ID, f)
        orch._agent_results["recon"] = {"_run_success": True}
        _install_dispatch_mock(orch, vuln_q)

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        await engine.run({}, {}, "/tmp", TASK_ID)

        assert len(orch._verified_queue_fingerprints) == 3


class TestCancellation:
    @pytest.mark.asyncio
    async def test_cancel_before_analysis_stops_workflow(self, orchestrator_with_queues):
        """Recon 完成后如果取消，不应进入 Analysis 阶段"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        recon_q.enqueue(TASK_ID, _make_risk_point())
        calls: List[Dict] = []

        async def mock_dispatch(params: Dict) -> str:
            calls.append(params)
            if params.get("agent") == "recon":
                orch._agent_results["recon"] = {"_run_success": True}
                # 在 Recon 完成后立即取消
                orch._cancelled = True
            return "ok"

        orch._dispatch_agent = mock_dispatch

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        assert state.phase == WorkflowPhase.CANCELLED
        analysis_calls = [c for c in calls if c["agent"] == "analysis"]
        assert len(analysis_calls) == 0

    @pytest.mark.asyncio
    async def test_cancel_during_analysis_stops_verification(self, orchestrator_with_queues):
        """Analysis 第二轮取消后，Verification 不再执行"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        for i in range(3):
            recon_q.enqueue(TASK_ID, _make_risk_point(f"f{i}.py", i))
        calls: List[Dict] = []
        analysis_count = [0]

        async def mock_dispatch(params: Dict) -> str:
            calls.append(params)
            agent = params.get("agent", "")
            if agent == "recon":
                orch._agent_results["recon"] = {"_run_success": True}
            elif agent == "analysis":
                analysis_count[0] += 1
                f = _make_finding(f"F{analysis_count[0]}")
                vuln_q.enqueue_finding(TASK_ID, f)
                orch._agent_results["analysis"] = {"_run_success": True, "findings": [f]}
                if analysis_count[0] >= 2:
                    orch._cancelled = True
            return "ok"

        orch._dispatch_agent = mock_dispatch

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        verify_calls = [c for c in calls if c["agent"] == "verification"]
        assert len(verify_calls) == 0
        assert state.phase == WorkflowPhase.CANCELLED


class TestStepRecords:
    @pytest.mark.asyncio
    async def test_step_records_count(self, orchestrator_with_queues):
        """step_records 数量 == Recon(1) + Analysis(N) + Verification(M)"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        n_risk = 2
        for i in range(n_risk):
            recon_q.enqueue(TASK_ID, _make_risk_point(f"f{i}.py", i))
        _install_dispatch_mock(orch, vuln_q, [_make_finding(f"F{i}") for i in range(n_risk)])

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        # 1 recon + n_risk analysis + n_risk verification = 1 + 2 + 2 = 5
        assert len(state.step_records) == 1 + n_risk + n_risk

    @pytest.mark.asyncio
    async def test_step_records_phases(self, orchestrator_with_queues):
        """step_records 应按 RECON → ANALYSIS → VERIFICATION 顺序排列"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        recon_q.enqueue(TASK_ID, _make_risk_point())
        _install_dispatch_mock(orch, vuln_q, [_make_finding("F1")])

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        phases = [r.phase for r in state.step_records]
        assert phases == [WorkflowPhase.RECON, WorkflowPhase.ANALYSIS, WorkflowPhase.VERIFICATION]


class TestReportCorrectionFlow:
    @pytest.mark.asyncio
    async def test_report_phase_merges_updated_finding_into_all_findings(self, orchestrator_with_queues):
        orch, recon_q, vuln_q = orchestrator_with_queues
        vuln_q.enqueue_finding(
            TASK_ID,
            {
                "finding_identity": "fid:test-report",
                "title": "wrong title",
                "file_path": "app.py",
                "line_start": 99,
                "vulnerability_type": "sql_injection",
                "severity": "high",
            },
        )

        async def mock_dispatch(params: Dict) -> str:
            if params.get("agent") == "verification":
                finding_from_params = dict(params.get("finding") or {})
                finding_from_params.update(
                    {
                        "verdict": "confirmed",
                        "confidence": 0.9,
                        "finding_identity": "fid:test-report",
                    }
                )
                orch._agent_results["verification"] = {
                    "_run_success": True,
                    "findings": [finding_from_params],
                }
                orch._all_findings.append(dict(finding_from_params))
                return "Verification 完成"
            return "ok"

        class _FakeReportAgent:
            async def run(self, input_data: Dict[str, Any]) -> AgentResult:
                finding = dict(input_data.get("finding") or {})
                finding.update(
                    {
                        "title": "app.py中correct_func函数SQL注入漏洞",
                        "line_start": 10,
                        "line_end": 11,
                        "function_name": "correct_func",
                    }
                )
                return AgentResult(
                    success=True,
                    data={
                        "vulnerability_report": "# corrected report",
                        "updated_finding": finding,
                    },
                    iterations=1,
                    tool_calls=1,
                    tokens_used=10,
                )

            def reset_cancellation_state(self) -> None:
                return None

        orch._dispatch_agent = mock_dispatch
        orch.sub_agents["report"] = _FakeReportAgent()
        orch._agent_results["recon"] = {"_run_success": True}

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        assert state.phase == WorkflowPhase.COMPLETE
        assert orch._all_findings
        final_finding = orch._all_findings[0]
        assert final_finding["finding_identity"] == "fid:test-report"
        assert final_finding["line_start"] == 10
        assert final_finding["function_name"] == "correct_func"
        assert final_finding["vulnerability_report"] == "# corrected report"

    @pytest.mark.asyncio
    async def test_report_phase_generates_project_risk_report(self, orchestrator_with_queues):
        orch, recon_q, vuln_q = orchestrator_with_queues
        vuln_q.enqueue_finding(
            TASK_ID,
            {
                "finding_identity": "fid:project-report",
                "title": "project risk seed",
                "file_path": "svc.py",
                "line_start": 20,
                "vulnerability_type": "sql_injection",
                "severity": "high",
            },
        )

        async def mock_dispatch(params: Dict) -> str:
            if params.get("agent") == "verification":
                finding_from_params = dict(params.get("finding") or {})
                finding_from_params.update(
                    {
                        "verdict": "confirmed",
                        "confidence": 0.9,
                        "finding_identity": "fid:project-report",
                    }
                )
                orch._agent_results["verification"] = {
                    "_run_success": True,
                    "findings": [finding_from_params],
                }
                orch._all_findings.append(dict(finding_from_params))
                return "Verification 完成"
            return "ok"

        class _ProjectAwareReportAgent:
            supports_project_risk_report = True

            async def run(self, input_data: Dict[str, Any]) -> AgentResult:
                if str(input_data.get("report_mode") or "").strip().lower() == "project":
                    return AgentResult(
                        success=True,
                        data={"project_risk_report": "# project risk report"},
                        iterations=1,
                        tool_calls=0,
                        tokens_used=8,
                    )
                finding = dict(input_data.get("finding") or {})
                return AgentResult(
                    success=True,
                    data={
                        "vulnerability_report": "# per finding report",
                        "updated_finding": finding,
                    },
                    iterations=1,
                    tool_calls=1,
                    tokens_used=10,
                )

            def reset_cancellation_state(self) -> None:
                return None

        orch._dispatch_agent = mock_dispatch
        orch.sub_agents["report"] = _ProjectAwareReportAgent()
        orch._agent_results["recon"] = {"_run_success": True}

        engine = AuditWorkflowEngine(recon_q, vuln_q, TASK_ID, orch)
        state = await engine.run({}, {}, "/tmp", TASK_ID)

        assert state.phase == WorkflowPhase.COMPLETE
        assert state.project_report_generated is True
        assert state.project_risk_report == "# project risk report"
        assert orch._agent_results["report"]["project_risk_report"] == "# project risk report"


# ──────────────────────────────────────────────────────────────────────────────
# WorkflowOrchestratorAgent 集成测试
# ──────────────────────────────────────────────────────────────────────────────

class TestWorkflowOrchestratorAgent:
    @pytest.mark.asyncio
    async def test_run_returns_agent_result(self, orchestrator_with_queues):
        """run() 应返回 AgentResult 对象"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        recon_q.enqueue(TASK_ID, _make_risk_point())
        _install_dispatch_mock(orch, vuln_q, [_make_finding("F1")])

        result = await orch.run({
            "project_info": {"name": "demo", "root": "/tmp"},
            "config": {},
            "project_root": "/tmp",
            "task_id": TASK_ID,
        })

        assert isinstance(result, AgentResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_workflow_state_in_result_data(self, orchestrator_with_queues):
        """返回的 data 字典中应包含 workflow_state 摘要"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        _install_dispatch_mock(orch, vuln_q)

        result = await orch.run({
            "project_info": {},
            "config": {},
            "project_root": "/tmp",
            "task_id": TASK_ID,
        })

        assert "workflow_state" in result.data
        assert result.data["workflow_state"]["phase"] == "complete"

    @pytest.mark.asyncio
    async def test_findings_in_result(self, orchestrator_with_queues, monkeypatch):
        """run() 结果中 findings 数量与实际发现一致（绕过文件存在性检查）"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        # 绕过 _validate_file_path，避免测试假路径被过滤
        monkeypatch.setattr(orch, "_validate_file_path", lambda path: True)
        recon_q.enqueue(TASK_ID, _make_risk_point())
        n_findings = 2
        _install_dispatch_mock(
            orch, vuln_q, [_make_finding(f"Vuln-{i}", line_start=i + 1) for i in range(n_findings)]
        )

        result = await orch.run({
            "project_info": {"name": "app", "root": "/tmp"},
            "config": {},
            "project_root": "/tmp",
            "task_id": TASK_ID,
        })

        # findings 数量 >= 1（Analysis pushes → Verification confirms）
        assert len(result.data.get("findings", [])) >= 1

    @pytest.mark.asyncio
    async def test_fallback_to_llm_mode_when_no_queues(self):
        """未提供队列服务时，应回退到父类 LLM-driven run()"""
        llm_service = MagicMock()
        llm_service.get_agent_timeout_config = MagicMock(return_value={})
        agent = WorkflowOrchestratorAgent(
            llm_service=llm_service,
            tools={},
            event_emitter=_FakeEventEmitter(),
            sub_agents={},
            recon_queue_service=None,  # 未提供
            vuln_queue_service=None,
        )

        # 父类 run() 会直接进入 LLM 循环，但因为没有子 Agent 且 LLM 不可用，
        # 应该很快返回（迭代中 LLM 返回空或错误）。
        # 我们 patch 父类 run() 来确认它被调用了。
        parent_run_called = [False]

        async def _fake_parent_run(self_arg, input_data):
            parent_run_called[0] = True
            return AgentResult(success=False, error="mocked LLM mode")

        with patch.object(
            agent.__class__.__bases__[0], "run", new=_fake_parent_run
        ):
            result = await agent.run({"project_info": {}, "config": {}, "task_id": "test"})

        assert parent_run_called[0] is True

    @pytest.mark.asyncio
    async def test_cancel_propagation(self, orchestrator_with_queues):
        """调用 cancel() 后 run() 应返回 success=False"""
        orch, recon_q, vuln_q = orchestrator_with_queues

        async def mock_dispatch(params: Dict) -> str:
            orch.cancel()
            orch._agent_results["recon"] = {"_run_success": True}
            return "cancelled"

        orch._dispatch_agent = mock_dispatch

        result = await orch.run({
            "project_info": {},
            "config": {},
            "project_root": "/tmp",
            "task_id": TASK_ID,
        })

        assert result.success is False
        assert "取消" in str(result.error)

    @pytest.mark.asyncio
    async def test_degraded_fallback_applied(self, orchestrator_with_queues, monkeypatch):
        """verification 无结果时，应从 analysis 候选生成降级 findings"""
        orch, recon_q, vuln_q = orchestrator_with_queues
        # 绕过文件存在性检查，使降级 finding 不被过滤
        monkeypatch.setattr(orch, "_validate_file_path", lambda path: True)
        recon_q.enqueue(TASK_ID, _make_risk_point())
        analysis_finding = _make_finding("SQL注入", "db.py", 20)

        async def mock_dispatch(params: Dict) -> str:
            agent = params.get("agent", "")
            if agent == "recon":
                orch._agent_results["recon"] = {"_run_success": True}
            elif agent == "analysis":
                vuln_q.enqueue_finding(TASK_ID, analysis_finding)
                orch._agent_results["analysis"] = {
                    "_run_success": True,
                    "findings": [analysis_finding],
                }
            elif agent == "verification":
                # Verification 返回 success 但 findings 为空（触发降级）
                orch._agent_results["verification"] = {
                    "_run_success": True,
                    "findings": [],           # 空列表 → 触发降级
                }
            return "ok"

        orch._dispatch_agent = mock_dispatch

        result = await orch.run({
            "project_info": {"name": "app", "root": "/tmp"},
            "config": {},
            "project_root": "/tmp",
            "task_id": TASK_ID,
        })

        # 降级兜底后，findings 中应出现 db.py 的降级发现
        findings = result.data.get("findings", [])
        assert any(f.get("file_path") == "db.py" for f in findings), (
            f"Expected degraded finding from db.py, got: {findings}"
        )
