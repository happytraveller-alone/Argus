from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401
from app.services.agent.agents.verification import VerificationAgent
from app.services.agent.tools.base import ToolResult


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
    description = "flow verify"

    async def execute(self, **kwargs):
        return ToolResult(
            success=True,
            data='{"path_found": true, "path_score": 0.83, "call_chain": ["entry", "sink"]}',
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


def _todo_updates_by_scope(events: List[Any], scope: str) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    for ev in events:
        if getattr(ev, "event_type", "") != "todo_update":
            continue
        metadata = getattr(ev, "metadata", None) or {}
        if metadata.get("todo_scope") == scope:
            output.append(metadata)
    return output


@pytest.mark.asyncio
async def test_verification_finding_table_context_loop_and_summary():
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
                    }
                ]
            },
            "task": "verify",
        }
    )

    assert result.success is True
    data = result.data or {}
    finding_table_summary = data.get("finding_table_summary") or {}
    assert finding_table_summary.get("total", 0) >= 1
    assert "context_ready" in finding_table_summary
    assert "verify_unverified" in finding_table_summary
    todo_summary = data.get("verification_todo_summary") or {}
    assert todo_summary.get("total", 0) >= 1
    assert todo_summary.get("pending", 0) == 0
    compact_items = todo_summary.get("per_item_compact") or []
    assert compact_items
    assert all(
        str(item.get("status") or "").strip().lower()
        in {"verified", "false_positive", "blocked"}
        for item in compact_items
        if isinstance(item, dict)
    )

    finding_table_updates = _todo_updates_by_scope(emitter.events, "finding_table")
    assert finding_table_updates, "应发出 finding_table todo_update 事件"
    final_update = finding_table_updates[-1]
    assert final_update.get("total", 0) >= 1
    assert "context_pending" in final_update
    assert "context_ready" in final_update
    assert "verified" in final_update
    assert "false_positive" in final_update
