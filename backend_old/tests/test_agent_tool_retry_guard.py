from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from app.services.agent.skills.scan_core import build_scan_core_skill_availability
from app.services.agent.agents.base import (
    RETRY_GUARD_TOOLS,
    AgentConfig,
    AgentResult,
    AgentType,
    BaseAgent,
)
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _ReadSchema(BaseModel):
    file_path: str
    anchor_line: int = 1


class _DeterministicFailReadTool:
    args_schema = _ReadSchema

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(success=False, data="", error=f"文件不存在: {kwargs.get('file_path')}", metadata={})


class _SearchSchema(BaseModel):
    keyword: str


class _SuccessSearchTool:
    args_schema = _SearchSchema

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(success=True, data=f"ok: {kwargs.get('keyword')}", error=None, metadata={})


class _SuccessCacheableTool:
    args_schema = _SearchSchema

    def __init__(self):
        self.execute_calls = 0

    async def execute(self, **kwargs):
        self.execute_calls += 1
        return SimpleNamespace(success=True, data=f"cache-ok: {kwargs.get('keyword')}", error=None, metadata={})


class _StrictDeterministicRuntime:
    strict_mode = True

    def __init__(self):
        self.calls = 0

    def can_handle(self, tool_name: str) -> bool:
        return tool_name == "get_recon_risk_queue_status"

    async def execute_tool(self, *, tool_name, tool_input, agent_name=None, alias_used=None):
        self.calls += 1
        assert tool_name == "get_recon_risk_queue_status"
        return SimpleNamespace(
            handled=True,
            success=False,
            data="",
            error="'dict' object is not callable",
            metadata={
                "runtime_used": True,
                "runtime_adapter": "filesystem",
                "runtime_mode": "strict",
            },
        )


class _StrictReadFileAutoRepairRuntime:
    strict_mode = True

    def __init__(self):
        self.calls = []

    def can_handle(self, tool_name: str) -> bool:
        return tool_name in {"read_file", "search_code"}

    async def execute_tool(self, *, tool_name, tool_input, agent_name=None, alias_used=None):
        self.calls.append((tool_name, dict(tool_input or {})))
        if tool_name == "search_code":
            return SimpleNamespace(
                handled=True,
                success=True,
                data="src/main/java/top/whgojp/modules/rce/command/CommandController.java:37",
                error=None,
                metadata={
                    "runtime_used": True,
                    "runtime_adapter": "filesystem",
                    "runtime_mode": "strict",
                },
            )
        if tool_name == "read_file":
            file_path = str((tool_input or {}).get("file_path") or "")
            if file_path.endswith("CeshiController.java"):
                return SimpleNamespace(
                    handled=True,
                    success=False,
                    data="",
                    error=(
                        "tool_call_failed:ENOENT: no such file or directory, open "
                        "'/tmp/VulHunter/task/JavaSecLab-1.4/src/main/java/top/whgojp/modules/rce/command/CeshiController.java'"
                    ),
                    metadata={
                        "runtime_used": True,
                        "runtime_adapter": "filesystem",
                        "runtime_mode": "strict",
                    },
                )
            if file_path.endswith("CommandController.java"):
                return SimpleNamespace(
                    handled=True,
                    success=True,
                    data="public class CommandController { ... }",
                    error=None,
                    metadata={
                        "runtime_used": True,
                        "runtime_adapter": "filesystem",
                        "runtime_mode": "strict",
                    },
                )
        return SimpleNamespace(
            handled=True,
            success=False,
            data="",
            error="tool_unhandled_in_strict_mode",
            metadata={
                "runtime_used": True,
                "runtime_mode": "strict",
            },
        )


def _make_agent(tools):
    emitter = SimpleNamespace(emit=AsyncMock())
    config = AgentConfig(name="test-agent", agent_type=AgentType.ANALYSIS)
    agent = _DummyAgent(
        config=config,
        llm_service=SimpleNamespace(),
        tools=tools,
        event_emitter=emitter,
    )
    return agent, emitter


def _events_by_type(emitter, event_type: str):
    events = []
    for call in emitter.emit.await_args_list:
        event_data = call.args[0]
        if event_data.event_type == event_type:
            events.append(event_data)
    return events


@pytest.mark.asyncio
async def test_execute_tool_short_circuits_after_deterministic_failures():
    read_tool = _DeterministicFailReadTool()
    agent, _emitter = _make_agent({"get_code_window": read_tool})

    first = await agent.execute_tool("get_code_window", {"file_path": "src/not_found.py", "anchor_line": 12})
    second = await agent.execute_tool("get_code_window", {"file_path": "src/not_found.py", "anchor_line": 12})
    third = await agent.execute_tool("get_code_window", {"file_path": "src/not_found.py", "anchor_line": 12})

    assert ("工具执行失败" in first) or ("工具调用已短路" in first)
    assert ("工具执行失败" in second) or ("工具调用已短路" in second)
    assert "工具调用已短路" in third
    assert read_tool.execute_calls == 2


@pytest.mark.asyncio
async def test_execute_tool_reuses_cached_output_for_identical_success_calls():
    cacheable_tool = _SuccessCacheableTool()
    agent, emitter = _make_agent({"custom_cacheable_tool": cacheable_tool})

    first = await agent.execute_tool("custom_cacheable_tool", {"keyword": "danger"})
    second = await agent.execute_tool("custom_cacheable_tool", {"keyword": "danger"})
    third = await agent.execute_tool("custom_cacheable_tool", {"keyword": "danger"})
    fourth = await agent.execute_tool("custom_cacheable_tool", {"keyword": "danger"})

    assert "danger" in first
    assert "danger" in second
    assert "danger" in third
    assert "danger" in fourth
    assert cacheable_tool.execute_calls == 1

    tool_result_events = _events_by_type(emitter, "tool_result")
    cache_hits = [event for event in tool_result_events if (event.metadata or {}).get("cache_hit") is True]
    assert len(cache_hits) >= 1
    assert all((event.metadata or {}).get("cache_policy") == "same_input_success_reuse" for event in cache_hits)


def test_retry_guard_contains_queue_status_tools():
    assert "get_recon_risk_queue_status" in RETRY_GUARD_TOOLS
    assert "get_queue_status" in RETRY_GUARD_TOOLS
    assert "dequeue_recon_risk_point" in RETRY_GUARD_TOOLS
    assert "dequeue_finding" in RETRY_GUARD_TOOLS


@pytest.mark.asyncio
async def test_strict_mcp_deterministic_failure_suppresses_retry_and_short_circuits():
    runtime = _StrictDeterministicRuntime()
    agent, emitter = _make_agent(tools={})
    agent.set_mcp_runtime(runtime)

    first = await agent.execute_tool("get_recon_risk_queue_status", {})
    second = await agent.execute_tool("get_recon_risk_queue_status", {})
    third = await agent.execute_tool("get_recon_risk_queue_status", {})

    assert "'dict' object is not callable" in first
    assert "'dict' object is not callable" in second
    assert "工具调用已短路" in third
    assert runtime.calls == 2

    tool_result_events = _events_by_type(emitter, "tool_result")
    assert len(tool_result_events) >= 3

    first_metadata = tool_result_events[0].metadata or {}
    assert first_metadata.get("runtime_error") == "'dict' object is not callable"
    assert first_metadata.get("runtime_error_class") == "invalid_callable_binding"
    assert first_metadata.get("retry_suppressed") is True

    third_metadata = tool_result_events[2].metadata or {}
    assert third_metadata.get("retry_suppressed") is True


@pytest.mark.asyncio
async def test_legacy_read_file_is_downlined_before_runtime_dispatch():
    runtime = _StrictReadFileAutoRepairRuntime()
    agent, _emitter = _make_agent(tools={})
    agent.set_mcp_runtime(runtime)

    output = await agent.execute_tool(
        "read_file",
        {"file_path": "src/main/java/top/whgojp/modules/rce/command/CeshiController.java"},
    )

    assert "已下线" in output
    assert "get_code_window" in output
    assert runtime.calls == []


class _StrictNoRouteRuntime:
    strict_mode = True

    def __init__(self):
        self.calls = 0

    def can_handle(self, tool_name: str) -> bool:
        return False

    async def execute_tool(self, *, tool_name, tool_input, agent_name=None, alias_used=None):
        self.calls += 1
        return SimpleNamespace(
            handled=False,
            success=False,
            data="",
            error="tool_route_missing",
            metadata={"runtime_mode": "strict"},
        )


class _LocalQueueStatusTool:
    async def execute(self, **kwargs):
        return SimpleNamespace(
            success=True,
            data={"pending_count": 1, "queue_status": {"current_size": 1}},
            error=None,
            metadata={},
        )


class _LocalCustomTool:
    async def execute(self, **kwargs):
        return SimpleNamespace(success=True, data="local-ok", error=None, metadata={})


class _LocalEchoTool:
    def __init__(self, tool_name: str):
        self.tool_name = tool_name

    async def execute(self, **kwargs):
        return SimpleNamespace(
            success=True,
            data=f"{self.tool_name}-ok",
            error=None,
            metadata={"tool_name": self.tool_name},
        )


def _public_local_scan_core_skill_ids() -> set[str]:
    availability = build_scan_core_skill_availability(
        [
            {"id": "filesystem", "enabled": True, "startup_ready": True},
        ]
    )
    return {
        skill_id
        for skill_id, detail in availability.items()
        if detail.get("source") == "local"
    }


@pytest.mark.asyncio
async def test_strict_mcp_allows_local_recon_queue_tool_without_mcp_route():
    runtime = _StrictNoRouteRuntime()
    agent, _emitter = _make_agent({"get_recon_risk_queue_status": _LocalQueueStatusTool()})
    agent.config.metadata.update({"smart_audit_mode": True})
    agent.set_mcp_runtime(runtime)

    output = await agent.execute_tool("get_recon_risk_queue_status", {})

    assert "pending_count" in output
    assert runtime.calls == 0


@pytest.mark.asyncio
async def test_strict_mcp_still_blocks_non_whitelisted_local_tool_without_route():
    runtime = _StrictNoRouteRuntime()
    agent, _emitter = _make_agent({"custom_local_tool": _LocalCustomTool()})
    agent.config.metadata.update({"smart_audit_mode": True})
    agent.set_mcp_runtime(runtime)

    output = await agent.execute_tool("custom_local_tool", {})

    assert "标准工具链未匹配工具 custom_local_tool" in output
    assert runtime.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", sorted(_public_local_scan_core_skill_ids()))
async def test_strict_mcp_allows_public_local_scan_core_tools_without_mcp_route(tool_name: str):
    runtime = _StrictNoRouteRuntime()
    agent, _emitter = _make_agent({tool_name: _LocalEchoTool(tool_name)})
    agent.config.metadata.update({"smart_audit_mode": True})
    agent.set_mcp_runtime(runtime)

    output = await agent.execute_tool(tool_name, {})

    assert output == f"{tool_name}-ok"
    assert runtime.calls == 0
    assert "标准工具链未匹配工具" not in output


def test_strict_mcp_local_allowlist_matches_public_local_scan_core_surface():
    agent, _emitter = _make_agent({})

    public_local_skills = _public_local_scan_core_skill_ids()
    allowlist = agent._strict_mcp_local_tool_allowlist()

    assert public_local_skills <= allowlist
