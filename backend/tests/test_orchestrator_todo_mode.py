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
