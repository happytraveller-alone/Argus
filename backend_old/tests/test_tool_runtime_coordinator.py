from pydantic import BaseModel, Field
import pytest

from app.services.agent.tools.base import AgentTool, ToolResult
from app.services.agent.tools.queue_tools import PushFindingToQueueTool
from app.services.agent.tools.runtime import ToolExecutionCoordinator
from app.services.agent.tools.runtime.hooks import ToolHook, ToolHookResult
from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue


class _EchoArgs(BaseModel):
    value: str = Field(description="echo value")


class _EchoTool(AgentTool):
    @property
    def name(self) -> str:
        return "echo_tool"

    @property
    def description(self) -> str:
        return "echo tool"

    @property
    def args_schema(self):
        return _EchoArgs

    async def _execute(self, value: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"value": value})


class _BrokenOutputTool(AgentTool):
    @property
    def name(self) -> str:
        return "locate_enclosing_function"

    @property
    def description(self) -> str:
        return "broken locator output"

    @property
    def args_schema(self):
        return _EchoArgs

    async def _execute(self, value: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"value": value})


class _FailedResultTool(AgentTool):
    @property
    def name(self) -> str:
        return "echo_tool"

    @property
    def description(self) -> str:
        return "failed result tool"

    @property
    def args_schema(self):
        return _EchoArgs

    async def _execute(self, value: str, **kwargs) -> ToolResult:
        return ToolResult(success=False, error=f"文件不存在: {value}")


class _MutatingPostExecuteHook(ToolHook):
    async def post_execute(self, *, tool, context, result):
        result.data = {"value": "mutated"}
        return ToolHookResult()


@pytest.mark.asyncio
async def test_agent_tool_rejects_unknown_fields_instead_of_dropping_them():
    tool = _EchoTool()

    result = await tool.execute(value="ok", extra="bad")

    assert result.success is False
    assert result.error == "参数校验失败"
    assert result.error_code == "unknown_field"
    assert result.metadata.get("reflection", {}).get("failure_class") == "input_contract_violation"
    assert "dropped_kwargs" not in result.metadata


@pytest.mark.asyncio
async def test_runtime_rejects_locator_outputs_that_break_public_contract():
    tool = _BrokenOutputTool()

    result = await tool.execute(value="ok")

    assert result.success is False
    assert result.error == "输出校验失败"
    assert result.error_code == "output_contract_violation"
    assert result.metadata.get("reflection", {}).get("failure_class") == "output_contract_violation"


@pytest.mark.asyncio
async def test_failed_tool_result_still_gets_structured_reflection():
    tool = _FailedResultTool()

    result = await tool.execute(value="demo.py")

    assert result.success is False
    assert result.error_code == "not_found"
    assert result.metadata.get("reflection", {}).get("stop_reason") == "not_found"
    assert result.metadata.get("reflection", {}).get("retryable") is False


@pytest.mark.asyncio
async def test_post_execute_hook_cannot_mutate_payload():
    coordinator = ToolExecutionCoordinator()
    coordinator._global_hooks.append(_MutatingPostExecuteHook())
    tool = _EchoTool()

    result = await coordinator.execute(tool, {"value": "ok"})

    assert result.success is False
    assert result.error_code == "output_contract_violation"
    assert "payload_mutated:post_execute" in result.diagnostics


@pytest.mark.asyncio
async def test_push_finding_tool_accepts_rich_payload_without_unknown_field():
    queue_service = InMemoryVulnerabilityQueue()
    tool = PushFindingToQueueTool(queue_service, "task-rich-payload")

    result = await tool.execute(
        finding={
            "file_path": "src/auth.py",
            "line": 18,
            "end_line": 21,
            "title": "src/auth.py中login函数SQL注入漏洞",
            "description": "拼接 SQL。",
            "type": "sql_injection",
            "code": "cursor.execute(query + user_input)",
            "recommendation": "使用参数化查询",
            "function_name": "login",
            "source": "request.form['username']",
            "sink": "cursor.execute",
            "attacker_flow": "POST /login -> login -> cursor.execute",
            "evidence_chain": ["代码片段", "数据流分析"],
            "custom_extra": "custom-value",
        }
    )

    assert result.success is True
    assert result.error_code is None
    queued = queue_service.dequeue_finding("task-rich-payload")
    assert queued is not None
    assert queued["line_start"] == 18
    assert queued["line_end"] == 21
    assert queued["vulnerability_type"] == "sql_injection"
    assert queued["code_snippet"] == "cursor.execute(query + user_input)"
    assert queued["suggestion"] == "使用参数化查询"
    assert queued["function_name"] == "login"
    assert queued["source"] == "request.form['username']"
    assert queued["sink"] == "cursor.execute"
    assert queued["attacker_flow"] == "POST /login -> login -> cursor.execute"
    assert queued["evidence_chain"] == ["代码片段", "数据流分析"]
    assert queued["finding_metadata"]["extra_tool_input"]["custom_extra"] == "custom-value"
