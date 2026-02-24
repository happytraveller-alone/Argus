from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from app.services.agent.agents.verification import VerificationAgent
from app.services.agent.tools.base import ToolResult
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _CapturedEmitter:
    def __init__(self) -> None:
        self.events: List[Any] = []

    async def emit(self, event_data: Any) -> None:
        self.events.append(event_data)


class _ReadTool:
    description = "read source"

    async def execute(self, **kwargs):
        file_path = kwargs.get("file_path", "")
        return ToolResult(success=True, data=f"read ok: {file_path}")


class _FlowTool:
    description = "control flow"

    async def execute(self, **kwargs):
        target = kwargs.get("file_path", "")
        return ToolResult(
            success=True,
            data=(
                '{"path_found": true, "path_score": 0.91, '
                f'"call_chain": ["entry", "{target}"]}}'
            ),
        )


def _make_agent(emitter: _CapturedEmitter) -> VerificationAgent:
    return VerificationAgent(
        llm_service=SimpleNamespace(),
        tools={
            "read_file": _ReadTool(),
            "controlflow_analysis_light": _FlowTool(),
        },
        event_emitter=emitter,
    )


@pytest.mark.asyncio
async def test_verification_todo_state_machine_initial_pending_and_final_transition():
    emitter = _CapturedEmitter()
    agent = _make_agent(emitter)

    result = await agent.run(
        {
            "config": {},
            "previous_results": {
                "bootstrap_findings": [
                    {
                        "title": "src/time64.c中asctime64_r栈溢出漏洞",
                        "severity": "high",
                        "confidence": 0.9,
                        "vulnerability_type": "stack_overflow",
                        "file_path": "src/time64.c",
                        "line_start": 168,
                        "line_end": 172,
                        "function_name": "asctime64_r",
                        "description": "sprintf 写入固定大小栈缓冲区",
                        "code_snippet": 'sprintf(result, "%s", input);',
                    },
                    {
                        "title": "src/net.c中parse_request命令注入漏洞",
                        "severity": "medium",
                        "confidence": 0.78,
                        "vulnerability_type": "command_injection",
                        "file_path": "src/net.c",
                        "line_start": 55,
                        "line_end": 61,
                        "function_name": "parse_request",
                        "description": "未对命令参数进行约束",
                        "code_snippet": "system(cmd);",
                    },
                ]
            },
            "task": "verify",
        }
    )

    assert result.success is True
    assert result.data.get("candidate_count") == 2
    findings = result.data.get("findings")
    assert isinstance(findings, list)
    assert len(findings) == 2

    todo_summary = result.data.get("verification_todo_summary") or {}
    assert todo_summary.get("total") == 2
    assert todo_summary.get("pending") == 0
    assert todo_summary.get("verified", 0) >= 1

    todo_updates = [ev for ev in emitter.events if getattr(ev, "event_type", "") == "todo_update"]
    assert todo_updates

    init_todo = (getattr(todo_updates[0], "metadata", {}) or {}).get("todo_list") or []
    assert init_todo
    assert all(str(item.get("status")) == "pending" for item in init_todo)

    final_todo = (getattr(todo_updates[-1], "metadata", {}) or {}).get("todo_list") or []
    assert final_todo
    assert all(str(item.get("status")) in {"verified", "false_positive"} for item in final_todo)

    finding_new_events = [ev for ev in emitter.events if getattr(ev, "event_type", "") == "finding_new"]
    assert len(finding_new_events) >= 2

    finding_verified_events = [
        ev for ev in emitter.events if getattr(ev, "event_type", "") == "finding_verified"
    ]
    assert finding_verified_events
