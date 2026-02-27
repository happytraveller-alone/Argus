from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import BaseModel
import pytest
from typing import Optional

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


class _SearchSchema(BaseModel):
    keyword: str
    file_pattern: Optional[str] = None
    is_regex: bool = False


class _SearchTool:
    args_schema = _SearchSchema

    async def execute(self, **kwargs):
        return SimpleNamespace(
            success=True,
            data={
                "keyword": kwargs.get("keyword"),
                "file_pattern": kwargs.get("file_pattern"),
            },
            error=None,
            metadata={},
        )


class _SearchLocationTool:
    args_schema = _SearchSchema
    name = "search_code"

    async def execute(self, **kwargs):
        return SimpleNamespace(
            success=True,
            data="src/sql_vuln.py:88\n`dangerous_call(user_input)`",
            error=None,
            metadata={},
        )


class _PatternSchema(BaseModel):
    scan_file: Optional[str] = None
    code: Optional[str] = None
    file_path: Optional[str] = None


class _PatternTool:
    args_schema = _PatternSchema
    name = "pattern_match"

    async def execute(self, **kwargs):
        return SimpleNamespace(success=True, data={"scan_file": kwargs.get("scan_file")}, error=None, metadata={})


class _ReadSchema(BaseModel):
    file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None


class _ReadTool:
    args_schema = _ReadSchema
    name = "read_file"

    async def execute(self, **kwargs):
        return SimpleNamespace(
            success=True,
            data={
                "file_path": kwargs.get("file_path"),
                "start_line": kwargs.get("start_line"),
                "end_line": kwargs.get("end_line"),
            },
            error=None,
            metadata={},
        )


def _make_agent(tools=None, metadata=None):
    emitter = SimpleNamespace(emit=AsyncMock())
    config = AgentConfig(
        name="test-agent",
        agent_type=AgentType.ANALYSIS,
        metadata=metadata or {},
    )
    selected_tools = tools or {"search_code": _SearchTool()}
    agent = _DummyAgent(
        config=config,
        llm_service=SimpleNamespace(),
        tools=selected_tools,
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
async def test_execute_tool_repairs_query_to_keyword():
    agent, emitter = _make_agent()

    output = await agent.execute_tool("search_code", {"query": "danger"})

    assert "danger" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    assert metadata.get("input_repaired") == {"query": "keyword"}


@pytest.mark.asyncio
async def test_execute_tool_repairs_items_envelope_for_search_code():
    agent, emitter = _make_agent()

    output = await agent.execute_tool(
        "search_code",
        {"items": [{"pattern": "sprintf", "glob": "src/*.c"}]},
    )

    assert "sprintf" in output
    assert "src/*.c" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("pattern") == "keyword"
    assert repaired.get("glob") == "file_pattern"


@pytest.mark.asyncio
async def test_execute_tool_repairs_search_code_from_raw_input_payload():
    agent, emitter = _make_agent()

    output = await agent.execute_tool(
        "search_code",
        {"raw_input": "{\"pattern\": \"sprintf\", \"glob\": \"src/*.c\"}"},
    )

    assert "sprintf" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__raw_input.keyword") == "keyword"


@pytest.mark.asyncio
async def test_execute_tool_blocks_virtual_alias_when_virtual_routing_disabled():
    agent, emitter = _make_agent(
        metadata={"disable_virtual_routing": True},
    )

    output = await agent.execute_tool("rag_query", {"query": "auth"})

    assert "工具名不可用" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    assert len(tool_result_events) == 1
    metadata = tool_result_events[0].metadata or {}
    assert metadata.get("alias_blocked") is True


@pytest.mark.asyncio
async def test_execute_tool_repairs_pattern_match_file_path_to_scan_file():
    agent, emitter = _make_agent(tools={"pattern_match": _PatternTool()})

    output = await agent.execute_tool("pattern_match", {"file_path": "src/demo.c"})

    assert "src/demo.c" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("file_path") == "scan_file"


@pytest.mark.asyncio
async def test_execute_tool_blocks_code_search_when_virtual_routing_disabled():
    agent, emitter = _make_agent(
        tools={
            "read_file": _ReadTool(),
            "search_code": _SearchTool(),
        },
        metadata={"disable_virtual_routing": True},
    )

    output = await agent.execute_tool("code_search", {"file_path": "src/sql_vuln.py"})

    assert "工具名不可用" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    assert len(tool_result_events) == 1
    metadata = tool_result_events[0].metadata or {}
    assert metadata.get("alias_blocked") is True


@pytest.mark.asyncio
async def test_execute_tool_repairs_read_file_from_recent_thought_context():
    agent, emitter = _make_agent(tools={"read_file": _ReadTool()})
    agent._recent_thought_texts.append("优先检查 src/time64.c:784 并确认上下文。")

    output = await agent.execute_tool("read_file", {})

    assert "src/time64.c" in output
    assert "start_line" in output
    assert "end_line" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__context.file_path") == "file_path"
    assert repaired.get("__context.line_range") == "start_line,end_line"


@pytest.mark.asyncio
async def test_execute_tool_strict_anchor_uses_file_header_fallback_when_only_file_path():
    agent, emitter = _make_agent(
        tools={"read_file": _ReadTool(), "search_code": _SearchTool()},
        metadata={"read_scope_policy": "strict_anchor"},
    )

    output = await agent.execute_tool("read_file", {"file_path": "src/sql_vuln.py"})

    assert "src/sql_vuln.py" in output
    assert "1" in output
    assert "120" in output
    tool_result_events = [
        event for event in _events_by_type(emitter, "tool_result")
        if event.tool_name == "read_file"
    ]
    assert len(tool_result_events) == 1
    metadata = tool_result_events[-1].metadata or {}
    assert metadata.get("read_scope_policy") == "strict_anchor"
    assert metadata.get("read_anchor_source") == "file_header_fallback"


@pytest.mark.asyncio
async def test_execute_tool_strict_anchor_bootstraps_read_file_via_search_code():
    agent, emitter = _make_agent(
        tools={"read_file": _ReadTool(), "search_code": _SearchLocationTool()},
        metadata={"read_scope_policy": "strict_anchor"},
    )

    output = await agent.execute_tool(
        "read_file",
        {"keyword": "dangerous_call"},
    )

    assert "src/sql_vuln.py" in output
    assert "28" in output
    assert "187" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    ordered_names = [event.tool_name for event in tool_call_events]
    assert ordered_names == ["search_code", "read_file"]


@pytest.mark.asyncio
async def test_execute_tool_repairs_read_file_from_arguments_envelope():
    agent, emitter = _make_agent(tools={"read_file": _ReadTool()})

    output = await agent.execute_tool("read_file", {"arguments": {"path": "src/time64.h"}})

    assert "src/time64.h" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("path") == "file_path"


@pytest.mark.asyncio
async def test_execute_tool_repairs_read_file_from_raw_input_payload():
    agent, emitter = _make_agent(tools={"read_file": _ReadTool()})

    output = await agent.execute_tool(
        "read_file",
        {"raw_input": "{\"file_path\": \"src/time64.h\"}"},
    )

    assert "src/time64.h" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__raw_input.file_path") == "file_path"


@pytest.mark.asyncio
async def test_execute_tool_repairs_search_code_from_recent_thought_context():
    agent, emitter = _make_agent()
    agent._recent_thought_texts.append(
        "入口函数包括 plist_from_bin、plist_from_xml、plist_from_json、plist_from_openstep。"
    )

    output = await agent.execute_tool("search_code", {})

    assert "plist_from_bin|plist_from_xml|plist_from_json|plist_from_openstep" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__context.keyword") == "keyword"
    assert repaired.get("__context.regex_hint") == "is_regex"


@pytest.mark.asyncio
async def test_execute_tool_missing_required_fields_still_fail_when_no_context_hint():
    agent, emitter = _make_agent()
    agent._recent_thought_texts.clear()

    output = await agent.execute_tool("search_code", {})

    assert "工具参数校验失败" in output
    assert "keyword" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    assert len(tool_result_events) == 1
    metadata = tool_result_events[0].metadata or {}
    assert metadata.get("mcp_used") is False
    assert metadata.get("mcp_dispatch_skipped") is True
    assert metadata.get("mcp_dispatch_skip_reason") == "validation_error"


def test_read_file_retry_guard_key_includes_window_information():
    agent, _ = _make_agent(tools={"read_file": _ReadTool()})

    key_a = agent._build_retry_guard_key(
        "read_file",
        {"file_path": "src/time64.h", "start_line": 1, "end_line": 120},
    )
    key_b = agent._build_retry_guard_key(
        "read_file",
        {"file_path": "src/time64.h", "start_line": 200, "end_line": 320},
    )

    assert key_a is not None
    assert key_b is not None
    assert key_a != key_b
