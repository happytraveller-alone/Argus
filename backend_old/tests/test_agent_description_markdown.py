import pytest

from app.services.agent.event_manager import AgentEventEmitter
from app.services.agent.utils.vulnerability_naming import (
    build_cn_structured_description,
    build_cn_structured_description_markdown,
)
import app.models.opengrep  # noqa: F401


@pytest.mark.asyncio
async def test_structured_description_denoises_tool_wrapper_and_enforces_length():
    noisy_evidence = (
        "CallToolResult(content=[TextContent(type='text', "
        "text='漏洞详情：用户输入在未约束情况下拼接进入 system(cmd) 调用，"
        "且分支中缺少白名单校验。')], isError=False)"
    )
    description = build_cn_structured_description(
        file_path="src/command.c",
        function_name="run_command",
        vulnerability_type="command_injection",
        title="src/command.c中run_command命令注入漏洞",
        description="根因待确认",
        code_snippet='system(cmd);',
        raw_description=noisy_evidence,
        verification_evidence=noisy_evidence,
        line_start=41,
        line_end=44,
        function_trigger_flow=["api_handler", "run_command"],
    )

    assert "CallToolResult" not in description
    assert "TextContent" not in description
    assert "该漏洞位于src/command.c:41-44的run_command函数中" in description
    assert 120 <= len(description) <= 300


@pytest.mark.asyncio
async def test_structured_description_markdown_contains_required_sections_and_code_fence():
    markdown = build_cn_structured_description_markdown(
        file_path="src/handler.go",
        function_name="HandleRequest",
        vulnerability_type="sql_injection",
        title="src/handler.go中HandleRequest SQL注入漏洞",
        description="请求参数直接拼接 SQL 语句并执行，攻击者可注入条件绕过业务约束。",
        code_context='query := "SELECT * FROM users WHERE id = " + userInput',
        cwe_id="CWE-89",
        line_start=87,
        line_end=91,
        function_trigger_flow=["router -> HandleRequest", "HandleRequest -> db.Query"],
    )

    assert "### 定位与结论" in markdown
    assert "### 根因解释" in markdown
    assert "### 代码说明" in markdown
    assert "### 触发路径" in markdown
    assert "```go" in markdown
    assert "```" in markdown


@pytest.mark.asyncio
async def test_structured_description_markdown_filters_verifier_prefix_from_root_cause():
    markdown = build_cn_structured_description_markdown(
        file_path="src/delegate.c",
        function_name="run_delegate",
        vulnerability_type="command_injection",
        title="delegate command injection",
        description="命令参数进入危险调用点。",
        code_snippet='system(sanitize_command);',
        verification_evidence=(
            "verifier=security-path-checker\n"
            "用户可控参数在缺少白名单校验时进入 system 调用。"
        ),
        line_start=439,
        line_end=443,
    )

    assert "verifier=" not in markdown
    assert "用户可控参数在缺少白名单校验时进入 system 调用。" in markdown


@pytest.mark.asyncio
async def test_event_emitter_finding_events_include_description_markdown_metadata():
    class _DummyEventManager:
        def __init__(self):
            self.events = []

        async def add_event(self, **kwargs):
            self.events.append(kwargs)

    manager = _DummyEventManager()
    emitter = AgentEventEmitter(task_id="task-1", event_manager=manager)

    await emitter.emit_finding(
        title="new finding",
        severity="high",
        vulnerability_type="xss",
        file_path="src/app.py",
        line_start=12,
        line_end=12,
        description="描述",
        description_markdown="### 定位与结论\nnew",
        is_verified=False,
    )
    await emitter.emit_finding(
        title="verified finding",
        severity="high",
        vulnerability_type="xss",
        file_path="src/app.py",
        line_start=12,
        line_end=12,
        description="描述",
        description_markdown="### 定位与结论\nverified",
        is_verified=True,
    )

    assert len(manager.events) == 2
    assert manager.events[0]["event_type"] == "finding_new"
    assert manager.events[0]["metadata"]["description_markdown"]
    assert manager.events[1]["event_type"] == "finding_verified"
    assert manager.events[1]["metadata"]["description_markdown"]
