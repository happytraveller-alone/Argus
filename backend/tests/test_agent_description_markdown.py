from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints.agent_tasks import list_agent_findings
from app.models.agent_task import AgentTask
from app.models.project import Project
from app.services.agent.event_manager import AgentEventEmitter
from app.services.agent.utils.vulnerability_naming import (
    build_cn_structured_description,
    build_cn_structured_description_markdown,
)
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


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
async def test_list_agent_findings_includes_description_markdown():
    task_id = "task-description-markdown"
    now = datetime(2026, 2, 25, 9, 0, 0, tzinfo=timezone.utc)

    finding = SimpleNamespace(
        id="finding-1",
        task_id=task_id,
        vulnerability_type="xss",
        severity="high",
        title="xss finding",
        description="参数未经编码直接输出到模板上下文。",
        file_path="/tmp/workspace/src/app.py",
        line_start=10,
        line_end=12,
        code_snippet="return render(user_input)",
        code_context="def show(user_input):\n    return render(user_input)",
        function_name="show",
        is_verified=True,
        ai_confidence=0.91,
        status="verified",
        suggestion="对输出进行严格编码",
        has_poc=False,
        poc_code=None,
        poc_description=None,
        poc_steps=None,
        verification_result={
            "authenticity": "confirmed",
            "reachability": "reachable",
            "evidence": "TextContent(type='text', text='用户输入进入模板渲染')",
            "reachability_target": {
                "file_path": "/tmp/workspace/src/app.py",
                "function": "show",
                "start_line": 8,
                "end_line": 18,
            },
            "function_trigger_flow": ["router -> show", "show -> render"],
        },
        created_at=now,
    )

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(id=task_id, project_id="project-1")
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(return_value=_ScalarListResult([finding]))

    result = await list_agent_findings(
        task_id=task_id,
        include_false_positive=False,
        skip=0,
        limit=50,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert len(result) == 1
    assert result[0].description_markdown
    assert "### 定位与结论" in (result[0].description_markdown or "")


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
