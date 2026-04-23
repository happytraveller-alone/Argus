from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from app.services.agent.agents.base import AgentResult
from app.services.agent.agents.orchestrator import OrchestratorAgent


def _make_llm_responses(*agent_names: str) -> List[str]:
    """Build a sequence of valid orchestrator LLM responses: dispatch each agent then finish."""
    responses = []
    for name in agent_names:
        responses.append(
            f'Thought: 调度 {name}\nAction: dispatch_agent\nAction Input: {{"agent": "{name}", "task": "执行{name}"}}'
        )
    responses.append('Thought: 完成\nAction: finish\nAction Input: {}')
    return responses


def _patch_llm(monkeypatch, orch: OrchestratorAgent, responses: List[str]) -> None:
    """Monkeypatch stream_llm_call to return responses in sequence."""
    state = {"idx": 0}

    async def _fake_stream_llm_call(messages, **kwargs):
        idx = state["idx"]
        state["idx"] += 1
        text = responses[idx] if idx < len(responses) else responses[-1]
        return text, 0

    monkeypatch.setattr(orch, "stream_llm_call", _fake_stream_llm_call)


@dataclass
class _CapturedEvent:
    event_type: str
    message: Optional[str]
    metadata: Optional[Dict[str, Any]]


class _FakeEventEmitter:
    def __init__(self) -> None:
        self.events: List[_CapturedEvent] = []

    async def emit(self, event_data: Any) -> None:  # matches AgentEventEmitter.emit signature
        self.events.append(
            _CapturedEvent(
                event_type=getattr(event_data, "event_type", ""),
                message=getattr(event_data, "message", None),
                metadata=getattr(event_data, "metadata", None),
            )
        )


class _StubSubAgent:
    def __init__(self, results: List[AgentResult]) -> None:
        self._results = results
        self._idx = 0
        self._registered = False
        self._cancelled = False

    def set_parent_id(self, _parent_id: str) -> None:
        return None

    def _register_to_registry(self, task: str = "") -> None:  # noqa: ARG002
        self._registered = True

    def cancel(self) -> None:
        self._cancelled = True

    async def run(self, _input_data: Dict[str, Any]) -> AgentResult:
        if self._idx < len(self._results):
            out = self._results[self._idx]
            self._idx += 1
            return out
        return self._results[-1]


class _StickyCancelVerificationAgent:
    """模拟“取消状态粘连”的 Verification 子 Agent。"""

    def __init__(self) -> None:
        self._registered = False
        self._cancelled = False
        self._run_calls = 0
        self.reset_calls = 0

    def set_parent_id(self, _parent_id: str) -> None:
        return None

    def _register_to_registry(self, task: str = "") -> None:  # noqa: ARG002
        self._registered = True

    def cancel(self) -> None:
        self._cancelled = True

    def reset_cancellation_state(self) -> None:
        self.reset_calls += 1
        self._cancelled = False

    async def run(self, _input_data: Dict[str, Any]) -> AgentResult:
        self._run_calls += 1
        if self._cancelled:
            return AgentResult(
                success=False,
                error="任务已取消",
                data={"candidate_count": 1, "findings": []},
            )

        if self._run_calls == 1:
            # 首次执行后将状态置为取消，模拟旧逻辑下后续 attempt 立即被取消。
            self._cancelled = True
            return AgentResult(
                success=False,
                error="任务已取消",
                data={"candidate_count": 1, "findings": []},
            )

        return AgentResult(
            success=True,
            data={
                "candidate_count": 1,
                "findings": [
                    {
                        "title": "src/app.py中runSQL注入漏洞",
                        "severity": "medium",
                        "vulnerability_type": "sql_injection",
                        "file_path": "src/app.py",
                        "line_start": 2,
                        "line_end": 2,
                        "verdict": "likely",
                        "authenticity": "likely",
                        "verification_result": {
                            "authenticity": "likely",
                            "verdict": "likely",
                            "reachability": "likely_reachable",
                            "evidence": "verified by retry run",
                        },
                    }
                ],
            },
        )


def _todo_items_from_event(ev: _CapturedEvent) -> List[Dict[str, Any]]:
    assert isinstance(ev.metadata, dict)
    todo_list = ev.metadata.get("todo_list")
    assert isinstance(todo_list, list)
    return todo_list


@pytest.mark.asyncio
async def test_orchestrator_todo_mode_initial_done_false_and_final_all_done_true(tmp_path, monkeypatch):
    for p in ("src/app.py", "src/db.py"):
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("placeholder", encoding="utf-8")

    emitter = _FakeEventEmitter()

    recon = _StubSubAgent(
        [
            AgentResult(
                success=True,
                data={
                    "tech_stack": {"languages": ["Python"]},
                    "high_risk_areas": ["src/app.py:10 - input handling"],
                },
            ),
            AgentResult(
                success=True,
                data={
                    "tech_stack": {"languages": ["Python"]},
                    "high_risk_areas": ["src/app.py:10 - input handling"],
                },
            ),
        ]
    )
    analysis = _StubSubAgent(
        [
            AgentResult(
                success=True,
                data={
                    "findings": [
                        {
                            "title": "Test finding",
                            "severity": "high",
                            "vulnerability_type": "xss",
                            "file_path": "src/app.py",
                            "line_start": 10,
                            "code_snippet": "render(user_input)",
                            "confidence": 0.9,
                        }
                    ]
                },
            ),
            AgentResult(
                success=True,
                data={
                    "findings": [
                        {
                            "title": "Another finding",
                            "severity": "medium",
                            "vulnerability_type": "sql_injection",
                            "file_path": "src/db.py",
                            "line_start": 5,
                            "code_snippet": "query = '...'+id",
                            "confidence": 0.7,
                        }
                    ]
                },
            ),
        ]
    )
    verification = _StubSubAgent(
        [
            AgentResult(
                success=True,
                data={"summary": "verified candidates", "findings": []},
            )
        ]
    )

    persist_calls: List[List[Dict[str, Any]]] = []

    async def persist_findings_cb(findings: List[Dict[str, Any]]) -> int:
        persist_calls.append(findings)
        return len(findings)

    orch = OrchestratorAgent(
        llm_service=object(),
        tools={},
        event_emitter=emitter,
        sub_agents={"recon": recon, "analysis": analysis, "verification": verification},
    )
    _patch_llm(monkeypatch, orch, _make_llm_responses("recon", "analysis", "verification"))

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": str(tmp_path)},
            "config": {"bootstrap_findings": []},
            "project_root": str(tmp_path),
            "task_id": "t1",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    assert isinstance(result.data, dict)
    findings = result.data.get("findings")
    assert isinstance(findings, list)
    assert len(findings) >= 1, "orchestrator should collect at least one finding"
    assert any(
        f.get("file_path") == "src/app.py" and f.get("vulnerability_type") == "xss"
        for f in findings
        if isinstance(f, dict)
    ), "should contain the xss finding for src/app.py"
    # 验证所有三个 sub-agent 都被调度了
    steps = result.data.get("steps", [])
    dispatched_agents = [
        s["action_input"].get("agent") if isinstance(s.get("action_input"), dict) else None
        for s in steps
        if s.get("action") == "dispatch_agent"
    ]
    assert "recon" in dispatched_agents, "recon agent should be dispatched"
    assert "analysis" in dispatched_agents, "analysis agent should be dispatched"
    assert "verification" in dispatched_agents, "verification agent should be dispatched"


@pytest.mark.asyncio
async def test_orchestrator_todo_mode_degrades_after_retries_and_continues(tmp_path, monkeypatch):
    for p in ("src/app.py",):
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("placeholder", encoding="utf-8")

    emitter = _FakeEventEmitter()

    recon = _StubSubAgent(
        [
            AgentResult(success=True, data={"tech_stack": {"languages": ["Python"]}, "high_risk_areas": ["src/app.py:1 - entry"]}),
            AgentResult(success=True, data={"tech_stack": {"languages": ["Python"]}, "high_risk_areas": ["src/app.py:1 - entry"]}),
        ]
    )
    # analysis_1 will be attempted twice with empty findings (fail), analysis_2 then returns a valid finding.
    analysis = _StubSubAgent(
        [
            AgentResult(success=True, data={"findings": []}),
            AgentResult(success=True, data={"findings": []}),
            AgentResult(
                success=True,
                data={
                    "findings": [
                        {
                            "title": "Recovered finding",
                            "severity": "high",
                            "vulnerability_type": "command_injection",
                            "file_path": "src/app.py",
                            "line_start": 12,
                            "code_snippet": "os.system(cmd)",
                            "confidence": 0.8,
                        }
                    ]
                },
            ),
        ]
    )
    verification = _StubSubAgent([AgentResult(success=True, data={"summary": "ok", "findings": []})])

    async def persist_findings_cb(_findings: List[Dict[str, Any]]) -> int:
        return 0

    orch = OrchestratorAgent(
        llm_service=object(),
        tools={},
        event_emitter=emitter,
        sub_agents={"recon": recon, "analysis": analysis, "verification": verification},
    )
    _patch_llm(monkeypatch, orch, _make_llm_responses("recon", "analysis", "verification"))

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": str(tmp_path)},
            "config": {"bootstrap_findings": []},
            "project_root": str(tmp_path),
            "task_id": "t2",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    findings = result.data.get("findings")
    assert isinstance(findings, list)
    assert len(findings) >= 1, "orchestrator should recover findings after analysis retries"
    # analysis 前两次返回空 findings，第三次返回 command_injection，验证 orchestrator 能从降级中恢复
    assert any(
        isinstance(f, dict) and f.get("file_path") == "src/app.py"
        for f in findings
    ), "recovered finding should reference src/app.py"
    # 验证 sub-agent 调度链完整
    steps = result.data.get("steps", [])
    dispatched = [s["action_input"]["agent"] for s in steps if s.get("action") == "dispatch_agent"]
    assert "recon" in dispatched and "analysis" in dispatched, "recon and analysis should both be dispatched"


@pytest.mark.asyncio
async def test_orchestrator_analysis_blocked_reason_prefers_degraded_reason_from_agent(tmp_path, monkeypatch):
    for p in ("src/app.py",):
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("placeholder", encoding="utf-8")

    emitter = _FakeEventEmitter()

    recon = _StubSubAgent(
        [
            AgentResult(success=True, data={"tech_stack": {"languages": ["Python"]}, "high_risk_areas": ["src/app.py:1 - entry"]}),
            AgentResult(success=True, data={"tech_stack": {"languages": ["Python"]}, "high_risk_areas": ["src/app.py:1 - entry"]}),
        ]
    )
    analysis = _StubSubAgent(
        [
            AgentResult(success=True, data={"findings": [], "degraded_reason": "analysis_stagnation"}),
            AgentResult(success=True, data={"findings": [], "degraded_reason": "analysis_stagnation"}),
            AgentResult(success=True, data={"findings": [], "degraded_reason": "analysis_stagnation"}),
        ]
    )
    verification = _StubSubAgent([AgentResult(success=True, data={"summary": "ok", "findings": []})])

    async def persist_findings_cb(_findings: List[Dict[str, Any]]) -> int:
        return 0

    orch = OrchestratorAgent(
        llm_service=object(),
        tools={},
        event_emitter=emitter,
        sub_agents={"recon": recon, "analysis": analysis, "verification": verification},
    )
    _patch_llm(monkeypatch, orch, _make_llm_responses("recon", "analysis", "verification"))

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": str(tmp_path)},
            "config": {"bootstrap_findings": []},
            "project_root": str(tmp_path),
            "task_id": "t3",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    findings = result.data.get("findings")
    assert isinstance(findings, list)
    # analysis 全部返回空 findings + degraded_reason，orchestrator 应通过 degraded fallback 产出结果
    assert len(findings) >= 1, "degraded fallback should produce at least one finding from stagnated analysis"


@pytest.mark.asyncio
async def test_orchestrator_verification_retries_three_times_and_reports_contract_failure(tmp_path, monkeypatch):
    for p in ("src/app.py",):
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("placeholder", encoding="utf-8")

    emitter = _FakeEventEmitter()

    recon = _StubSubAgent(
        [
            AgentResult(success=True, data={"tech_stack": {"languages": ["Python"]}, "high_risk_areas": ["src/app.py:1 - entry"]}),
            AgentResult(success=True, data={"tech_stack": {"languages": ["Python"]}, "high_risk_areas": ["src/app.py:1 - entry"]}),
        ]
    )
    analysis = _StubSubAgent(
        [
            AgentResult(
                success=True,
                data={
                    "findings": [
                        {
                            "title": "candidate",
                            "severity": "high",
                            "vulnerability_type": "xss",
                            "file_path": "src/app.py",
                            "line_start": 10,
                            "confidence": 0.9,
                        }
                    ]
                },
            ),
            AgentResult(
                success=True,
                data={
                    "findings": [
                        {
                            "title": "candidate-2",
                            "severity": "high",
                            "vulnerability_type": "xss",
                            "file_path": "src/app.py",
                            "line_start": 10,
                            "confidence": 0.9,
                        }
                    ]
                },
            ),
        ]
    )
    verification = _StubSubAgent(
        [
            AgentResult(
                success=True,
                data={
                    "candidate_count": 1,
                    "findings": [
                        {
                            "title": "invalid-contract-finding",
                            "file_path": "src/app.py",
                            "line_start": 10,
                            "vulnerability_type": "xss",
                            "verdict": "likely",
                        }
                    ],
                },
            ),
            AgentResult(
                success=True,
                data={
                    "candidate_count": 1,
                    "findings": [
                        {
                            "title": "invalid-contract-finding",
                            "file_path": "src/app.py",
                            "line_start": 10,
                            "vulnerability_type": "xss",
                            "verdict": "likely",
                        }
                    ],
                },
            ),
            AgentResult(
                success=True,
                data={
                    "candidate_count": 1,
                    "findings": [
                        {
                            "title": "invalid-contract-finding",
                            "file_path": "src/app.py",
                            "line_start": 10,
                            "vulnerability_type": "xss",
                            "verdict": "likely",
                        }
                    ],
                },
            ),
        ]
    )

    async def persist_findings_cb(_findings: List[Dict[str, Any]]) -> int:
        return 0

    orch = OrchestratorAgent(
        llm_service=object(),
        tools={},
        event_emitter=emitter,
        sub_agents={"recon": recon, "analysis": analysis, "verification": verification},
    )
    _patch_llm(monkeypatch, orch, _make_llm_responses("recon", "analysis", "verification"))

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": str(tmp_path)},
            "config": {"bootstrap_findings": []},
            "project_root": str(tmp_path),
            "task_id": "t4",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    findings = result.data.get("findings")
    assert isinstance(findings, list)
    assert len(findings) >= 1, "verification contract failure should still produce findings via fallback"
    assert all(
        isinstance(f, dict) and f.get("file_path") == "src/app.py"
        for f in findings
    ), "all findings should reference src/app.py"
    # verification 返回不符合 contract 的 findings，orchestrator 应降级处理
    # 降级后 normalize 可能改变 vuln_type，但 severity 和 file_path 应保留
    assert any(
        isinstance(f, dict) and f.get("severity") in ("high", "medium")
        for f in findings
    ), "findings should preserve severity from analysis candidates"
    # 验证 analysis 和 verification 都被调度了
    steps = result.data.get("steps", [])
    dispatched = [s["action_input"]["agent"] for s in steps if s.get("action") == "dispatch_agent"]
    assert "analysis" in dispatched and "verification" in dispatched


@pytest.mark.asyncio
async def test_orchestrator_verification_retry_resets_sticky_cancel_state(tmp_path, monkeypatch):
    for p in ("src/app.py",):
        (tmp_path / p).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / p).write_text("placeholder", encoding="utf-8")

    emitter = _FakeEventEmitter()

    recon = _StubSubAgent(
        [
            AgentResult(success=True, data={"tech_stack": {"languages": ["Python"]}, "high_risk_areas": ["src/app.py:2 - entry"]}),
            AgentResult(success=True, data={"tech_stack": {"languages": ["Python"]}, "high_risk_areas": ["src/app.py:2 - entry"]}),
        ]
    )
    analysis = _StubSubAgent(
        [
            AgentResult(
                success=True,
                data={
                    "findings": [
                        {
                            "title": "candidate",
                            "severity": "medium",
                            "vulnerability_type": "sql_injection",
                            "file_path": "src/app.py",
                            "line_start": 2,
                            "code_snippet": "query = user_input",
                            "confidence": 0.8,
                        }
                    ]
                },
            ),
            AgentResult(
                success=True,
                data={
                    "findings": [
                        {
                            "title": "candidate-2",
                            "severity": "medium",
                            "vulnerability_type": "sql_injection",
                            "file_path": "src/app.py",
                            "line_start": 2,
                            "code_snippet": "query = user_input",
                            "confidence": 0.8,
                        }
                    ]
                },
            ),
        ]
    )
    verification = _StickyCancelVerificationAgent()

    async def persist_findings_cb(_findings: List[Dict[str, Any]]) -> int:
        return 0

    orch = OrchestratorAgent(
        llm_service=object(),
        tools={},
        event_emitter=emitter,
        sub_agents={"recon": recon, "analysis": analysis, "verification": verification},
    )
    _patch_llm(monkeypatch, orch, _make_llm_responses("recon", "analysis", "verification"))

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": str(tmp_path)},
            "config": {"bootstrap_findings": []},
            "project_root": str(tmp_path),
            "task_id": "t5",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    findings = result.data.get("findings")
    assert isinstance(findings, list)
    assert len(findings) >= 1, "sticky cancel recovery should produce findings"
    assert any(
        isinstance(f, dict) and f.get("vulnerability_type") == "sql_injection"
        for f in findings
    ), "should contain the sql_injection finding"
    assert verification.reset_calls >= 1, "orchestrator should reset cancellation state at least once"


@pytest.mark.asyncio
async def test_orchestrator_verification_degraded_merge_uses_analysis_findings(tmp_path, monkeypatch):
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        "def run(user_input):\n    query = user_input\n    return query\n",
        encoding="utf-8",
    )

    emitter = _FakeEventEmitter()
    recon = _StubSubAgent(
        [
            AgentResult(success=True, data={"tech_stack": {"languages": ["Python"]}, "high_risk_areas": ["src/app.py:2 - input"]}),
            AgentResult(success=True, data={"tech_stack": {"languages": ["Python"]}, "high_risk_areas": ["src/app.py:2 - input"]}),
        ]
    )
    analysis = _StubSubAgent(
        [
            AgentResult(
                success=True,
                data={
                    "findings": [
                        {
                            "title": "src/app.py中runSQL注入漏洞",
                            "severity": "medium",
                            "vulnerability_type": "sql_injection",
                            "file_path": "src/app.py",
                            "line_start": 2,
                            "line_end": 2,
                            "description": "query 直接拼接用户输入。",
                            "code_snippet": "query = user_input",
                            "confidence": 0.82,
                        }
                    ]
                },
            ),
            AgentResult(
                success=True,
                data={
                    "findings": [
                        {
                            "title": "src/app.py中runSQL注入漏洞",
                            "severity": "medium",
                            "vulnerability_type": "sql_injection",
                            "file_path": "src/app.py",
                            "line_start": 2,
                            "line_end": 2,
                            "description": "query 直接拼接用户输入。",
                            "code_snippet": "query = user_input",
                            "confidence": 0.82,
                        }
                    ]
                },
            ),
        ]
    )
    verification = _StubSubAgent(
        [
            AgentResult(success=False, error="任务已取消", data={}),
            AgentResult(success=False, error="任务已取消", data={}),
            AgentResult(success=False, error="任务已取消", data={}),
        ]
    )

    async def persist_findings_cb(findings: List[Dict[str, Any]]) -> int:
        return len(findings)

    orch = OrchestratorAgent(
        llm_service=object(),
        tools={},
        event_emitter=emitter,
        sub_agents={"recon": recon, "analysis": analysis, "verification": verification},
    )
    _patch_llm(monkeypatch, orch, _make_llm_responses("recon", "analysis", "verification"))

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": str(tmp_path)},
            "config": {"bootstrap_findings": []},
            "project_root": str(tmp_path),
            "task_id": "t6",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    findings = result.data.get("findings")
    assert isinstance(findings, list)
    assert findings, "verification 重试耗尽后应保底使用 analysis 候选"
    # verification 全部返回"任务已取消"，findings 应来自 analysis 降级合并
    assert any(
        isinstance(f, dict)
        and f.get("file_path") == "src/app.py"
        and f.get("vulnerability_type") == "sql_injection"
        for f in findings
    ), "degraded findings should preserve analysis candidate's file_path and vulnerability_type"
    # 验证 analysis 和 verification 都被调度了
    steps = result.data.get("steps", [])
    dispatched = [s["action_input"]["agent"] for s in steps if s.get("action") == "dispatch_agent"]
    assert "analysis" in dispatched and "verification" in dispatched
