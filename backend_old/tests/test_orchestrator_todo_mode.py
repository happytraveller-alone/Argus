from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from app.services.agent.agents.base import AgentResult
from app.services.agent.agents.orchestrator import OrchestratorAgent


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
async def test_orchestrator_todo_mode_initial_done_false_and_final_all_done_true():
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

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": "/tmp/demo"},
            "config": {"bootstrap_findings": []},
            "project_root": "/tmp/demo",
            "task_id": "t1",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    assert isinstance(result.data, dict)
    assert isinstance(result.data.get("todo_list"), list)
    assert all(item.get("done") is True for item in result.data["todo_list"])
    assert persist_calls, "persist callback should be called once"

    todo_events = [e for e in emitter.events if e.event_type == "todo_update"]
    assert todo_events, "should emit todo_update events"

    init_ev = todo_events[0]
    init_items = _todo_items_from_event(init_ev)
    assert init_items, "todo_list should be present in metadata"
    assert all(item.get("done") is False for item in init_items), "initial todo items must start done=false"

    final_ev = todo_events[-1]
    final_items = _todo_items_from_event(final_ev)
    assert all(item.get("done") is True for item in final_items)


@pytest.mark.asyncio
async def test_orchestrator_todo_mode_degrades_after_retries_and_continues():
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

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": "/tmp/demo"},
            "config": {"bootstrap_findings": []},
            "project_root": "/tmp/demo",
            "task_id": "t2",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    todo_list = result.data.get("todo_list")
    assert isinstance(todo_list, list)

    analysis_1 = next((t for t in todo_list if t.get("id") == "analysis_1"), None)
    assert isinstance(analysis_1, dict)
    assert analysis_1.get("done") is True
    assert analysis_1.get("blocked_reason") == "degraded_after_retries"


@pytest.mark.asyncio
async def test_orchestrator_analysis_blocked_reason_prefers_degraded_reason_from_agent():
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

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": "/tmp/demo"},
            "config": {"bootstrap_findings": []},
            "project_root": "/tmp/demo",
            "task_id": "t3",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    todo_list = result.data.get("todo_list")
    assert isinstance(todo_list, list)

    analysis_1 = next((t for t in todo_list if t.get("id") == "analysis_1"), None)
    assert isinstance(analysis_1, dict)
    assert analysis_1.get("done") is True
    assert analysis_1.get("blocked_reason") == "analysis_stagnation"


@pytest.mark.asyncio
async def test_orchestrator_verification_retries_three_times_and_reports_contract_failure():
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

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": "/tmp/demo"},
            "config": {"bootstrap_findings": []},
            "project_root": "/tmp/demo",
            "task_id": "t4",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    todo_list = result.data.get("todo_list")
    assert isinstance(todo_list, list)
    verification_item = next((t for t in todo_list if t.get("id") == "verification_1"), None)
    assert isinstance(verification_item, dict)
    assert verification_item.get("done") is True
    assert verification_item.get("attempts") == 3
    assert str(verification_item.get("blocked_reason") or "").startswith(
        "verification_failed_after_retries:verification_missing_contract"
    )


@pytest.mark.asyncio
async def test_orchestrator_verification_retry_resets_sticky_cancel_state():
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

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": "/tmp/demo"},
            "config": {"bootstrap_findings": []},
            "project_root": "/tmp/demo",
            "task_id": "t5",
            "persist_findings": persist_findings_cb,
        }
    )

    assert result.success is True
    todo_list = result.data.get("todo_list")
    assert isinstance(todo_list, list)
    verification_item = next((t for t in todo_list if t.get("id") == "verification_1"), None)
    assert isinstance(verification_item, dict)
    assert verification_item.get("attempts") == 2
    assert verification_item.get("blocked_reason") in (None, "")
    assert verification.reset_calls >= 2


@pytest.mark.asyncio
async def test_orchestrator_verification_degraded_merge_uses_analysis_findings(tmp_path):
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
    degraded_items = [
        item for item in findings
        if isinstance(item, dict)
        and isinstance(item.get("verification_result"), dict)
        and item["verification_result"].get("degraded") is True
    ]
    assert degraded_items
    verification_item = next((t for t in result.data.get("todo_list", []) if t.get("id") == "verification_1"), None)
    assert isinstance(verification_item, dict)
    assert str(verification_item.get("blocked_reason") or "").startswith(
        "verification_failed_after_retries:verification_cancelled"
    )
    assert "unknown" not in str(verification_item.get("blocked_reason") or "")
