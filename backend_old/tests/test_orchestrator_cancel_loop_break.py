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

    async def emit(self, event_data: Any) -> None:
        self.events.append(
            _CapturedEvent(
                event_type=getattr(event_data, "event_type", ""),
                message=getattr(event_data, "message", None),
                metadata=getattr(event_data, "metadata", None),
            )
        )


@pytest.mark.asyncio
async def test_orchestrator_todo_cancel_breaks_current_retry_loop(monkeypatch):
    emitter = _FakeEventEmitter()
    orch = OrchestratorAgent(
        llm_service=object(),
        tools={},
        event_emitter=emitter,
        sub_agents={"recon": object(), "analysis": object(), "verification": object()},
    )

    dispatch_calls = {"count": 0}

    async def _fake_dispatch(_params):
        dispatch_calls["count"] += 1
        orch.cancel()
        return "任务已取消"

    monkeypatch.setattr(orch, "_dispatch_agent", _fake_dispatch)

    result = await orch.run(
        {
            "project_info": {"name": "demo", "root": "/tmp/demo"},
            "config": {},
            "project_root": "/tmp/demo",
            "task_id": "cancel-loop-break",
            "persist_findings": lambda _findings: 0,
        }
    )

    assert result.success is False
    assert result.error == "任务已取消"
    # 关键断言：同一 todo item 不会在取消后继续进行下一次 attempt。
    assert dispatch_calls["count"] == 1
