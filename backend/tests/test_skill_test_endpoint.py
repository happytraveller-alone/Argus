import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import skills as skills_module


def _build_agent_event(
    event_type: str,
    *,
    message: str = "",
    tool_name: str | None = None,
    tool_input=None,
    tool_output=None,
    metadata=None,
):
    return SimpleNamespace(
        event_type=event_type,
        message=message,
        tool_name=tool_name,
        tool_input=tool_input,
        tool_output=tool_output,
        metadata=metadata,
    )


async def _collect_sse_events(response) -> list[dict]:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else str(chunk))

    payload = "".join(chunks)
    events: list[dict] = []
    for block in payload.split("\n\n"):
        if not block.strip():
            continue
        data_lines = [line[5:].strip() for line in block.splitlines() if line.startswith("data:")]
        if not data_lines:
            continue
        events.append(json.loads("\n".join(data_lines)))
    return events


def test_build_skill_test_tool_allowlist_only_allows_selected_skill():
    from app.services.agent.skill_test_runner import build_skill_test_tool_allowlist

    assert build_skill_test_tool_allowlist("get_code_window") == ("get_code_window",)


@pytest.mark.asyncio
async def test_run_skill_test_endpoint_streams_expected_events_and_result(monkeypatch):
    class _FakeRunner:
        def __init__(self, **kwargs):
            self.event_emitter = kwargs["event_emitter"]
            self.skill_id = kwargs["skill_id"]

        async def run(self):
            await self.event_emitter.emit_event(
                "project_prepare",
                "默认测试项目命中 libplist",
                {
                    "project_name": "libplist",
                    "temp_dir": "/tmp/skill-test-get_code_window-1234",
                },
            )
            await self.event_emitter.emit(
                _build_agent_event(
                    "llm_action",
                    message="Action: get_code_window",
                    metadata={"selected_skill": self.skill_id},
                )
            )
            await self.event_emitter.emit(
                _build_agent_event(
                    "tool_call",
                    tool_name="get_code_window",
                    tool_input={"file_path": "src/main.c", "anchor_line": 2},
                )
            )
            await self.event_emitter.emit(
                _build_agent_event(
                    "tool_result",
                    tool_name="get_code_window",
                    tool_output={
                        "result": "文件: src/main.c",
                        "truncated": False,
                        "metadata": {
                            "render_type": "code_window",
                            "display_command": "get_code_window",
                            "command_chain": ["get_code_window"],
                            "entries": [
                                {
                                    "file_path": "src/main.c",
                                    "start_line": 1,
                                    "end_line": 3,
                                    "focus_line": 2,
                                    "language": "c",
                                    "lines": [
                                        {"line_number": 1, "text": "int main() {", "kind": "context"},
                                        {"line_number": 2, "text": "  return 0;", "kind": "focus"},
                                        {"line_number": 3, "text": "}", "kind": "context"},
                                    ],
                                }
                            ],
                        },
                    },
                    metadata={},
                )
            )
            await self.event_emitter.emit_event(
                    "project_cleanup",
                    "临时目录清理完成",
                    {
                    "temp_dir": "/tmp/skill-test-get_code_window-1234",
                    "cleanup_success": True,
                },
            )
            return {
                "skill_id": self.skill_id,
                "final_text": "已基于 libplist 回答用户问题。",
                "project_name": "libplist",
                "cleanup": {
                    "success": True,
                    "temp_dir": "/tmp/skill-test-get_code_window-1234",
                },
            }

    monkeypatch.setattr(skills_module, "_get_user_config", AsyncMock(return_value={"llmConfig": {}}), raising=False)
    monkeypatch.setattr(skills_module, "_init_llm_service", AsyncMock(return_value=object()), raising=False)
    monkeypatch.setattr(skills_module, "SkillTestRunner", _FakeRunner, raising=False)

    response = await skills_module.run_skill_test(
        skill_id="get_code_window",
        request=skills_module.SkillTestRequest(prompt="读取 plist 解析入口", max_iterations=3),
        db=AsyncMock(),
        current_user=SimpleNamespace(id="user-1"),
    )

    events = await _collect_sse_events(response)
    event_types = [event["type"] for event in events]

    assert "project_prepare" in event_types
    assert "llm_action" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "result" in event_types
    assert "project_cleanup" in event_types
    assert event_types[-1] == "done"

    tool_result_event = next(event for event in events if event["type"] == "tool_result")
    assert tool_result_event["tool_output"]["metadata"]["display_command"] == "get_code_window"
    assert tool_result_event["tool_output"]["metadata"]["entries"][0]["file_path"] == "src/main.c"

    result_event = next(event for event in events if event["type"] == "result")
    assert result_event["data"]["final_text"] == "已基于 libplist 回答用户问题。"
    assert result_event["data"]["cleanup"]["success"] is True


@pytest.mark.asyncio
async def test_run_structured_tool_test_endpoint_streams_expected_events_and_result(monkeypatch):
    class _FakeRunner:
        def __init__(self, **kwargs):
            self.event_emitter = kwargs["event_emitter"]
            self.skill_id = kwargs["skill_id"]
            self.request_payload = kwargs["request_payload"]

        async def run(self):
            await self.event_emitter.emit_event(
                "project_prepare",
                "默认测试项目命中 libplist",
                {
                    "project_name": "libplist",
                    "temp_dir": "/tmp/structured-tool-test-1234",
                },
            )
            await self.event_emitter.emit_event(
                "runner_prepare",
                "flow parser runner 已定位目标函数",
                {
                    "runner_image": "vulhunter/flow-parser-runner-local:latest",
                    "resolved_file_path": "src/xplist.c",
                    "resolved_line_start": 42,
                    "resolved_line_end": 58,
                    "target_function": "plist_from_xml",
                },
            )
            await self.event_emitter.emit(
                _build_agent_event(
                    "tool_call",
                    tool_name=self.skill_id,
                    tool_input=self.request_payload["tool_input"],
                )
            )
            await self.event_emitter.emit(
                _build_agent_event(
                    "tool_result",
                    tool_name=self.skill_id,
                    tool_output={
                        "result": '{"summary":"ok"}',
                        "truncated": False,
                        "metadata": {
                            "render_type": "flow_analysis",
                            "display_command": self.skill_id,
                            "command_chain": [self.skill_id],
                            "entries": [
                                {
                                    "file_path": "src/xplist.c",
                                    "source_nodes": ["plist_xml"],
                                    "sink_nodes": ["xmlParseMemory"],
                                    "taint_steps": ["plist_xml -> xmlParseMemory"],
                                    "call_chain": ["plist_from_xml -> xmlParseMemory"],
                                    "blocked_reasons": [],
                                    "reachability": "reachable",
                                    "path_found": True,
                                    "path_score": 0.91,
                                    "confidence": 0.91,
                                    "engine": "rules",
                                    "next_actions": [],
                                }
                            ],
                        },
                    },
                    metadata={},
                )
            )
            await self.event_emitter.emit_event(
                "project_cleanup",
                "临时目录清理完成",
                {
                    "temp_dir": "/tmp/structured-tool-test-1234",
                    "cleanup_success": True,
                },
            )
            return {
                "tool_name": self.skill_id,
                "project_name": "libplist",
                "project_root": "/tmp/structured-tool-test-1234/libplist-2.7.0",
                "target_function": "plist_from_xml",
                "resolved_file_path": "src/xplist.c",
                "resolved_line_start": 42,
                "resolved_line_end": 58,
                "runner_image": "vulhunter/flow-parser-runner-local:latest",
                "input_payload": self.request_payload,
                "cleanup": {
                    "success": True,
                    "temp_dir": "/tmp/structured-tool-test-1234",
                    "error": None,
                },
            }

    monkeypatch.setattr(
        skills_module,
        "_get_user_config",
        AsyncMock(return_value={"llmConfig": {}}),
        raising=False,
    )
    monkeypatch.setattr(skills_module, "_init_llm_service", AsyncMock(return_value=object()), raising=False)
    monkeypatch.setattr(skills_module, "StructuredToolTestRunner", _FakeRunner, raising=False)

    response = await skills_module.run_structured_tool_test(
        skill_id="dataflow_analysis",
        request=skills_module.StructuredToolTestRequest(
            file_path="src/xplist.c",
            function_name="plist_from_xml",
            tool_input={
                "variable_name": "plist_xml",
                "sink_hints": ["xmlReadMemory", "xmlParseMemory", "xml_to_node"],
            },
        ),
        db=AsyncMock(),
        current_user=SimpleNamespace(id="user-1"),
    )

    events = await _collect_sse_events(response)
    event_types = [event["type"] for event in events]

    assert "project_prepare" in event_types
    assert "runner_prepare" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "result" in event_types
    assert "project_cleanup" in event_types
    assert event_types[-1] == "done"

    tool_result_event = next(event for event in events if event["type"] == "tool_result")
    assert tool_result_event["tool_output"]["metadata"]["display_command"] == "dataflow_analysis"
    assert tool_result_event["tool_output"]["metadata"]["entries"][0]["file_path"] == "src/xplist.c"

    result_event = next(event for event in events if event["type"] == "result")
    assert result_event["data"]["tool_name"] == "dataflow_analysis"
    assert result_event["data"]["runner_image"] == "vulhunter/flow-parser-runner-local:latest"
    assert result_event["data"]["target_function"] == "plist_from_xml"
