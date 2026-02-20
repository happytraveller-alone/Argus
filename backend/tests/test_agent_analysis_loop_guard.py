from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.agent.agents.analysis import AnalysisAgent
from app.services.agent.tools.base import ToolResult
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _DummyReadFileTool:
    description = "dummy read file"

    async def execute(self, **kwargs):
        return ToolResult(success=True, data=f"read ok: {kwargs.get('file_path', 'unknown')}")


@pytest.mark.asyncio
async def test_analysis_loop_guard_degrades_after_repeated_no_action(monkeypatch):
    agent = AnalysisAgent(
        llm_service=SimpleNamespace(),
        tools={"read_file": _DummyReadFileTool()},
        event_emitter=None,
    )

    repeated_no_action_output = (
        "Thought: 我现在立即执行 Action 来读取高风险文件的代码证据，"
        "但我先继续思考，不输出可执行格式。"
    )
    monkeypatch.setattr(
        agent,
        "stream_llm_call",
        AsyncMock(side_effect=[(repeated_no_action_output, 10)] * 12),
    )

    result = await agent.run(
        {
            "project_info": {"name": "demo", "root": "/tmp/demo"},
            "config": {"target_files": ["src/time64.c"]},
            "previous_results": {"bootstrap_findings": []},
            "task": "analysis",
        }
    )

    assert result.success is True
    assert isinstance(result.data, dict)
    assert result.data.get("degraded_reason") == "analysis_stagnation"
    assert result.tool_calls >= 1
