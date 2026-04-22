from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import BaseModel
import pytest
from typing import Any, Dict, List, Optional

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent
from app.services.agent.agents.analysis import AnalysisAgent
from app.services.agent.tools.base import AgentTool, ToolResult
import app.models.opengrep  # noqa: F401


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


class _SymbolBodySchema(BaseModel):
    file_path: str
    symbol_name: str


class _SymbolBodyTool:
    args_schema = _SymbolBodySchema
    name = "get_symbol_body"

    async def execute(self, **kwargs):
        return SimpleNamespace(
            success=True,
            data={
                "file_path": kwargs.get("file_path"),
                "symbol_name": kwargs.get("symbol_name"),
            },
            error=None,
            metadata={},
        )


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


class _ListSchema(BaseModel):
    directory: str = "."
    recursive: bool = False
    max_files: Optional[int] = None


class _ListTool:
    args_schema = _ListSchema
    name = "list_files"

    async def execute(self, **kwargs):
        return SimpleNamespace(
            success=True,
            data={
                "directory": kwargs.get("directory"),
                "recursive": kwargs.get("recursive"),
                "max_files": kwargs.get("max_files"),
            },
            error=None,
            metadata={},
        )


class _PushFindingSchema(BaseModel):
    file_path: str
    line_start: int
    line_end: Optional[int] = None
    title: str
    description: str
    vulnerability_type: str
    severity: Optional[str] = "medium"
    confidence: Optional[float] = 0.8
    function_name: Optional[str] = None
    code_snippet: Optional[str] = None
    source: Optional[str] = None
    sink: Optional[str] = None
    suggestion: Optional[str] = None
    attacker_flow: Optional[str] = None
    evidence_chain: Optional[List[str]] = None
    missing_checks: Optional[List[str]] = None
    taint_flow: Optional[List[str]] = None
    finding_metadata: Optional[Dict[str, Any]] = None


class _PushFindingTool:
    args_schema = _PushFindingSchema
    name = "push_finding_to_queue"

    async def execute(self, **kwargs):
        return SimpleNamespace(success=True, data=kwargs, error=None, metadata={})


class _PushRiskPointSchema(BaseModel):
    file_path: str
    line_start: int
    description: str
    severity: Optional[str] = "high"
    confidence: Optional[float] = 0.6
    vulnerability_type: Optional[str] = "potential_issue"


class _PushRiskPointTool:
    args_schema = _PushRiskPointSchema
    name = "push_risk_point_to_queue"

    async def execute(self, **kwargs):
        return SimpleNamespace(success=True, data=kwargs, error=None, metadata={})


class _ControlFlowSchema(BaseModel):
    file_path: str
    line_start: int
    line_end: Optional[int] = None
    call_chain_hint: Optional[List[str]] = None
    control_conditions_hint: Optional[List[str]] = None
    entry_points: Optional[List[str]] = None
    entry_points_hint: Optional[List[str]] = None


class _ControlFlowTool:
    args_schema = _ControlFlowSchema
    name = "controlflow_analysis_light"

    async def execute(self, **kwargs):
        validated = _ControlFlowSchema(**kwargs)
        return SimpleNamespace(success=True, data=validated.model_dump(), error=None, metadata={})


class _StrictControlFlowTool(AgentTool):
    @property
    def name(self) -> str:
        return "controlflow_analysis_light"

    @property
    def description(self) -> str:
        return "strict controlflow tool for input-contract testing"

    @property
    def args_schema(self):
        return _ControlFlowSchema

    async def _execute(self, **kwargs) -> ToolResult:
        validated = _ControlFlowSchema(**kwargs)
        return ToolResult(success=True, data=validated.model_dump(), metadata={})


class _DataFlowSchema(BaseModel):
    source_code: Optional[str] = None
    sink_code: Optional[str] = None
    variable_name: str = "user_input"
    file_path: str = "unknown"
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    source_hints: Optional[List[str]] = None
    sink_hints: Optional[List[str]] = None


class _DataFlowTool:
    args_schema = _DataFlowSchema
    name = "dataflow_analysis"

    async def execute(self, **kwargs):
        validated = _DataFlowSchema(**kwargs)
        return SimpleNamespace(success=True, data=validated.model_dump(), error=None, metadata={})


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
    assert (
        repaired.get("__raw_input.keyword") == "keyword"
        or repaired.get("pattern") == "keyword"
    )


@pytest.mark.asyncio
async def test_execute_tool_blocks_virtual_alias_when_virtual_routing_disabled():
    agent, emitter = _make_agent(
        metadata={"disable_virtual_routing": True},
    )

    output = await agent.execute_tool("rag_query", {"query": "auth"})

    assert "工具名不可用" in output or "工具 'rag_query' 不存在" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    if tool_result_events:
        metadata = tool_result_events[0].metadata or {}
        assert metadata.get("alias_blocked") is True


@pytest.mark.asyncio
async def test_execute_tool_resolves_list_alias_to_list_files():
    agent, emitter = _make_agent(tools={"list_files": _ListTool()})

    output = await agent.execute_tool("list", {"directory": ".", "max_files": 20})

    assert "directory" in output
    assert "max_files" in output
    assert "20" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    assert tool_call_events[0].tool_name == "list_files"
    metadata = tool_call_events[0].metadata or {}
    assert metadata.get("alias_used") == "list"


@pytest.mark.asyncio
async def test_execute_tool_blocks_list_alias_when_virtual_routing_disabled():
    agent, emitter = _make_agent(
        tools={"list_files": _ListTool()},
        metadata={"disable_virtual_routing": True},
    )

    output = await agent.execute_tool("list", {"directory": "."})

    assert "工具名不可用" in output or "工具 'list' 不存在" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    if tool_result_events:
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
async def test_execute_tool_repairs_get_symbol_body_legacy_extract_function_contract():
    agent, emitter = _make_agent(tools={"get_symbol_body": _SymbolBodyTool()})

    output = await agent.execute_tool(
        "get_symbol_body",
        {"path": "src/demo.c", "function_name": "parse_demo"},
    )

    assert "src/demo.c" in output
    assert "parse_demo" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("path") == "file_path"
    assert repaired.get("function_name") == "symbol_name"


@pytest.mark.asyncio
async def test_execute_tool_repairs_get_symbol_body_positional_items_payload():
    agent, emitter = _make_agent(tools={"get_symbol_body": _SymbolBodyTool()})

    output = await agent.execute_tool(
        "get_symbol_body",
        {"items": [["src/demo.c", "parse_demo"]]},
    )

    assert "src/demo.c" in output
    assert "parse_demo" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__items[0]") == "file_path"
    assert repaired.get("__items[1]") == "symbol_name"


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

    assert "工具名不可用" in output or "工具 'code_search' 不存在" in output
    tool_result_events = _events_by_type(emitter, "tool_result")
    if tool_result_events:
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
    tool_result_events = [
        event for event in _events_by_type(emitter, "tool_result")
        if event.tool_name == "read_file"
    ]
    assert len(tool_result_events) == 1


@pytest.mark.asyncio
async def test_execute_tool_strict_anchor_bootstraps_read_file_via_search_code():
    agent, emitter = _make_agent(
        tools={"read_file": _ReadTool(), "search_code": _SearchLocationTool()},
        metadata={"read_scope_policy": "strict_anchor"},
    )

    output = await agent.execute_tool(
        "read_file",
        {"file_path": "src/sql_vuln.py"},
    )

    assert "src/sql_vuln.py" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    ordered_names = [event.tool_name for event in tool_call_events]
    assert "read_file" in ordered_names


@pytest.mark.asyncio
async def test_execute_tool_smart_audit_allows_read_file_without_strict_anchor():
    agent, emitter = _make_agent(
        tools={"read_file": _ReadTool()},
        metadata={"smart_audit_mode": True},
    )

    output = await agent.execute_tool("read_file", {"file_path": "src/sql_vuln.py"})

    assert "src/sql_vuln.py" in output
    tool_result_events = [
        event for event in _events_by_type(emitter, "tool_result")
        if event.tool_name == "read_file"
    ]
    assert len(tool_result_events) == 1
    metadata = tool_result_events[-1].metadata or {}
    assert metadata.get("read_scope_policy") != "strict_anchor"


def test_analysis_single_scope_allows_read_and_list_file_actions():
    agent = AnalysisAgent(llm_service=SimpleNamespace(), tools={})

    list_reason = agent._is_action_out_of_single_scope(
        action="list_files",
    )
    read_reason = agent._is_action_out_of_single_scope(
        action="read_file",
    )
    blocked_reason = agent._is_action_out_of_single_scope(
        action="semgrep_scan",
    )

    assert list_reason is None
    assert read_reason is None
    assert "禁止调用全局扫描工具" in (blocked_reason or "")


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
async def test_execute_tool_does_not_force_regex_for_literal_parentheses_context():
    assert _DummyAgent._keyword_prefers_regex("foo(bar)") is False
    assert _DummyAgent._keyword_prefers_regex("plist_from_bin|plist_from_xml") is True


@pytest.mark.asyncio
async def test_execute_tool_repairs_push_finding_nested_envelope():
    agent, emitter = _make_agent(tools={"push_finding_to_queue": _PushFindingTool()})

    output = await agent.execute_tool(
        "push_finding_to_queue",
        {
            "finding": {
                "file_path": "src/auth/login.py",
                "line_start": 88,
                "title": "src/auth/login.py中login函数SQL注入漏洞",
                "description": "用户输入拼接 SQL 且未参数化。",
                "vulnerability_type": "sql_injection",
            }
        },
    )

    assert "src/auth/login.py" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__envelope.finding.file_path") == "file_path"
    assert repaired.get("__envelope.finding.line_start") == "line_start"


@pytest.mark.asyncio
async def test_execute_tool_repairs_push_finding_aliases_and_preserves_extra_metadata():
    agent, emitter = _make_agent(tools={"push_finding_to_queue": _PushFindingTool()})

    output = await agent.execute_tool(
        "push_finding_to_queue",
        {
            "finding": {
                "file_path": "src/auth/login.py",
                "line": 88,
                "end_line": 92,
                "title": "src/auth/login.py中login函数SQL注入漏洞",
                "description": "用户输入拼接 SQL 且未参数化。",
                "type": "sql_injection",
                "code": "cursor.execute(query + user_input)",
                "recommendation": "改用参数化查询",
                "attacker_flow": "POST /login -> login -> cursor.execute",
                "evidence_chain": ["代码片段", "数据流分析"],
                "function_name": "login",
                "custom_extra": "custom-value",
            }
        },
    )

    assert "src/auth/login.py" in output
    assert "cursor.execute(query + user_input)" in output
    assert "custom-value" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("line") == "line_start"
    assert repaired.get("end_line") == "line_end"
    assert repaired.get("type") == "vulnerability_type"
    assert repaired.get("code") == "code_snippet"
    assert repaired.get("recommendation") == "suggestion"
    assert repaired.get("__extra.custom_extra") == "finding_metadata.extra_tool_input.custom_extra"


@pytest.mark.asyncio
async def test_execute_tool_repairs_push_risk_point_from_risk_point_envelope():
    agent, emitter = _make_agent(tools={"push_risk_point_to_queue": _PushRiskPointTool()})

    output = await agent.execute_tool(
        "push_risk_point_to_queue",
        {
            "risk_point": {
                "file_path": "src/modules/demo.py",
                "line_start": 23,
                "description": "用户输入未经验证进入危险调用点",
            }
        },
    )

    assert "src/modules/demo.py" in output
    assert "23" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__envelope.risk_point.file_path") == "file_path"
    assert repaired.get("__envelope.risk_point.line_start") == "line_start"


@pytest.mark.asyncio
async def test_execute_tool_repairs_push_risk_point_from_raw_input_json():
    agent, emitter = _make_agent(tools={"push_risk_point_to_queue": _PushRiskPointTool()})

    output = await agent.execute_tool(
        "push_risk_point_to_queue",
        {
            "raw_input": (
                '{"risk_point":{"file_path":"src/api/rce.py","line_start":51,'
                '"description":"命令拼接执行"}}'
            )
        },
    )

    assert "src/api/rce.py" in output
    assert "51" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__raw_input.risk_point.file_path") == "file_path"
    assert repaired.get("__raw_input.risk_point.line_start") == "line_start"


@pytest.mark.asyncio
async def test_execute_tool_repairs_placeholder_push_risk_point_with_context_hints():
    agent, emitter = _make_agent(tools={"push_risk_point_to_queue": _PushRiskPointTool()})
    agent._recent_thought_texts.append("请先推送 src/rce/handler.py:88 这一条风险点。")

    output = await agent.execute_tool(
        "push_risk_point_to_queue",
        {"参数名": "参数值"},
    )

    assert "src/rce/handler.py" in output
    assert "88" in output
    assert "可疑风险点" in output or "风险点" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__placeholder_payload") == "removed"


@pytest.mark.asyncio
async def test_execute_tool_repairs_read_file_polluted_path_suffix():
    agent, emitter = _make_agent(tools={"read_file": _ReadTool()})

    output = await agent.execute_tool(
        "read_file",
        {"file_path": "src/time64.c(和其他多处)", "start_line": 780, "end_line": 820},
    )

    # The tool receives the input as-is; path sanitization no longer rewrites file_path in-place.
    assert "src/time64.c" in output
    assert "780" in output
    assert "820" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1


@pytest.mark.asyncio
async def test_execute_tool_repairs_controlflow_line_start_from_file_path_suffix():
    agent, emitter = _make_agent(tools={"controlflow_analysis_light": _ControlFlowTool()})

    output = await agent.execute_tool(
        "controlflow_analysis_light",
        {"file_path": "src/login.py:123"},
    )

    assert "src/login.py" in output
    assert "123" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__sanitize.file_path_line") in {"line_start", "line_end"}


@pytest.mark.asyncio
async def test_execute_tool_repairs_controlflow_string_hints_to_lists():
    agent, emitter = _make_agent(tools={"controlflow_analysis_light": _ControlFlowTool()})

    output = await agent.execute_tool(
        "controlflow_analysis_light",
        {
            "file_path": "src/login.py:123",
            "call_chain_hint": "ServiceLoader.load(Class serviceName line=42)",
            "control_conditions_hint": "requires authenticated user",
            "entry_points_hint": "main",
        },
    )

    assert "ServiceLoader.load(Class serviceName line=42)" in output
    assert "requires authenticated user" in output
    assert "main" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__normalize.call_chain_hint") == "call_chain_hint"
    assert repaired.get("__normalize.control_conditions_hint") == "control_conditions_hint"
    assert repaired.get("__normalize.entry_points_hint") == "entry_points_hint"


@pytest.mark.asyncio
async def test_execute_tool_repairs_controlflow_legacy_alias_fields():
    agent, emitter = _make_agent(tools={"controlflow_analysis_light": _ControlFlowTool()})

    output = await agent.execute_tool(
        "controlflow_analysis_light",
        {
            "path": "src/login.py:123",
            "entry_point": "main",
            "condition_hint": "requires authenticated user",
        },
    )

    assert "src/login.py" in output
    assert "123" in output
    assert "main" in output
    assert "requires authenticated user" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("path") == "file_path"
    assert repaired.get("entry_point") == "entry_points"
    assert repaired.get("condition_hint") == "control_conditions_hint"


@pytest.mark.asyncio
async def test_execute_tool_repairs_controlflow_single_item_envelope():
    agent, emitter = _make_agent(tools={"controlflow_analysis_light": _StrictControlFlowTool()})

    output = await agent.execute_tool(
        "controlflow_analysis_light",
        {
            "items": [
                {
                    "file_path": "src/login.py:123",
                    "entry_points_hint": "main",
                }
            ]
        },
    )

    assert "src/login.py" in output
    assert "123" in output
    assert "main" in output
    assert "参数校验失败" not in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("__envelope.items.file_path") == "file_path"
    assert repaired.get("__envelope.items.entry_points_hint") == "entry_points_hint"


@pytest.mark.asyncio
async def test_execute_tool_repairs_dataflow_legacy_alias_fields():
    agent, emitter = _make_agent(tools={"dataflow_analysis": _DataFlowTool()})

    output = await agent.execute_tool(
        "dataflow_analysis",
        {
            "code": "dangerous(user_input)",
            "sink": "eval(user_input)",
            "path": "src/login.py",
            "line": 41,
            "end": 52,
            "source_hint": "request.body",
            "sink_hint": "eval",
        },
    )

    assert "dangerous(user_input)" in output
    assert "eval(user_input)" in output
    assert "src/login.py" in output
    assert "41" in output
    assert "52" in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert repaired.get("code") == "source_code"
    assert repaired.get("sink") == "sink_code"
    assert repaired.get("path") == "file_path"
    assert repaired.get("line") == "start_line"
    assert repaired.get("end") == "end_line"
    assert repaired.get("source_hint") == "source_hints"
    assert repaired.get("sink_hint") == "sink_hints"


@pytest.mark.asyncio
async def test_execute_tool_keeps_canonical_dataflow_fields_over_aliases():
    agent, emitter = _make_agent(tools={"dataflow_analysis": _DataFlowTool()})

    output = await agent.execute_tool(
        "dataflow_analysis",
        {
            "source_code": "safe(user_input)",
            "code": "dangerous(user_input)",
            "sink_code": "exec(safe_input)",
            "sink": "eval(user_input)",
            "file_path": "src/canonical.py",
            "path": "src/legacy.py",
            "start_line": 8,
            "line": 99,
        },
    )

    assert "safe(user_input)" in output
    assert "dangerous(user_input)" not in output
    assert "exec(safe_input)" in output
    assert "eval(user_input)" not in output
    assert "src/canonical.py" in output
    assert "src/legacy.py" not in output
    assert "8" in output
    assert "99" not in output
    tool_call_events = _events_by_type(emitter, "tool_call")
    assert len(tool_call_events) == 1
    metadata = tool_call_events[0].metadata or {}
    repaired = metadata.get("input_repaired") or {}
    assert "code" not in repaired
    assert "sink" not in repaired
    assert "path" not in repaired
    assert "line" not in repaired


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
    assert metadata.get("runtime_used") is False
    assert metadata.get("runtime_dispatch_skipped") is True
    assert metadata.get("runtime_dispatch_skip_reason") == "validation_error"


def test_read_file_retry_guard_key_includes_window_information():
    agent, _ = _make_agent(tools={"read_file": _ReadTool()})

    key_a = agent._build_retry_guard_key(
        "search_code",
        {"keyword": "dangerous", "file_pattern": "src/*.py"},
    )
    key_b = agent._build_retry_guard_key(
        "search_code",
        {"keyword": "safe", "file_pattern": "src/*.py"},
    )

    assert key_a is not None
    assert key_b is not None
    assert key_a != key_b
