import zipfile
from pathlib import Path

import pytest

from app.services.agent import skill_test_runner as runner_module
from app.services.agent.tools.base import ToolResult


class _RecorderEmitter:
    def __init__(self):
        self.events: list[dict] = []

    async def emit_event(self, event_type: str, message: str, metadata=None):
        self.events.append(
            {
                "type": event_type,
                "message": message,
                "metadata": metadata or {},
            }
        )

    async def emit(self, event_data):
        self.events.append(
            {
                "type": getattr(event_data, "event_type", "info"),
                "message": getattr(event_data, "message", ""),
                "metadata": getattr(event_data, "metadata", {}) or {},
                "tool_name": getattr(event_data, "tool_name", None),
                "tool_input": getattr(event_data, "tool_input", None),
                "tool_output": getattr(event_data, "tool_output", None),
            }
        )


def _make_libplist_zip(zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_ref:
        zip_ref.writestr(
            "libplist-2.7.0/src/xplist.c",
            (
                "#include <libxml/parser.h>\n"
                "void xml_to_node(void *node, void *plist);\n\n"
                "void plist_from_xml(const char *plist_xml, unsigned int length, void *plist) {\n"
                "    xmlDocPtr plist_doc = xmlParseMemory(plist_xml, length);\n"
                "    xml_to_node(plist_doc, plist);\n"
                "}\n"
            ),
        )


@pytest.mark.asyncio
async def test_structured_tool_test_runner_resolves_function_via_flow_parser_and_cleans_temp_dir(
    monkeypatch,
    tmp_path: Path,
):
    archive_path = tmp_path / "libplist.zip"
    _make_libplist_zip(archive_path)

    emitter = _RecorderEmitter()
    seen_payload: dict[str, object] = {}

    class _FakeRunnerClient:
        image = "vulhunter/flow-parser-runner-local:latest"

        def extract_definitions_batch(self, items):
            seen_payload["definition_items"] = items
            return {
                "src/xplist.c": {
                    "file_path": "src/xplist.c",
                    "ok": True,
                    "definitions": [
                        {
                            "type": "function",
                            "name": "plist_from_xml",
                            "start_point": [3, 0],
                            "end_point": [6, 1],
                            "diagnostics": ["flow_parser_runner"],
                        }
                    ],
                    "diagnostics": ["flow_parser_runner"],
                    "error": None,
                }
            }

    class _FakeTool:
        async def execute(self, **kwargs):
            seen_payload["tool_kwargs"] = kwargs
            return ToolResult(
                success=True,
                data={"summary": "ok"},
                metadata={
                    "render_type": "flow_analysis",
                    "display_command": "dataflow_analysis",
                    "command_chain": ["dataflow_analysis"],
                    "entries": [
                        {
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
                            "file_path": "src/xplist.c",
                        }
                    ],
                },
            )

    monkeypatch.setattr(runner_module, "get_flow_parser_runner_client", lambda: _FakeRunnerClient())
    monkeypatch.setattr(runner_module, "build_structured_tool_test_tool", lambda *args, **kwargs: _FakeTool())

    runner = runner_module.StructuredToolTestRunner(
        skill_id="dataflow_analysis",
        request_payload={
            "file_path": "src/xplist.c",
            "function_name": "plist_from_xml",
            "tool_input": {
                "variable_name": "plist_xml",
                "sink_hints": ["xmlReadMemory", "xmlParseMemory", "xml_to_node"],
            },
        },
        project_name="libplist",
        zip_path=str(archive_path),
        fallback_used=False,
        event_emitter=emitter,
    )

    result = await runner.run()

    assert result["tool_name"] == "dataflow_analysis"
    assert result["project_name"] == "libplist"
    assert result["target_function"] == "plist_from_xml"
    assert result["resolved_file_path"] == "src/xplist.c"
    assert result["resolved_line_start"] == 4
    assert result["resolved_line_end"] == 7
    assert result["runner_image"] == "vulhunter/flow-parser-runner-local:latest"
    assert result["cleanup"]["success"] is True
    assert not Path(result["cleanup"]["temp_dir"]).exists()
    assert seen_payload["tool_kwargs"]["file_path"] == "src/xplist.c"
    assert seen_payload["tool_kwargs"]["start_line"] == 4
    assert seen_payload["tool_kwargs"]["end_line"] == 7
    event_types = [event["type"] for event in emitter.events]
    assert "project_prepare" in event_types
    assert "runner_prepare" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "project_cleanup" in event_types
    tool_result_event = next(event for event in emitter.events if event["type"] == "tool_result")
    assert tool_result_event["metadata"] == {}
    assert tool_result_event["tool_output"]["metadata"]["render_type"] == "flow_analysis"
    assert tool_result_event["tool_output"]["metadata"]["entries"][0]["file_path"] == "src/xplist.c"


@pytest.mark.asyncio
async def test_structured_tool_test_runner_emits_failed_tool_result_when_tool_raises(
    monkeypatch,
    tmp_path: Path,
):
    archive_path = tmp_path / "libplist.zip"
    _make_libplist_zip(archive_path)

    emitter = _RecorderEmitter()

    class _FakeRunnerClient:
        image = "vulhunter/flow-parser-runner-local:latest"

        def extract_definitions_batch(self, items):
            return {
                "src/xplist.c": {
                    "file_path": "src/xplist.c",
                    "ok": True,
                    "definitions": [
                        {
                            "type": "function",
                            "name": "plist_from_xml",
                            "start_point": [3, 0],
                            "end_point": [6, 1],
                            "diagnostics": ["flow_parser_runner"],
                        }
                    ],
                    "diagnostics": ["flow_parser_runner"],
                    "error": None,
                }
            }

    class _ExplodingTool:
        async def execute(self, **kwargs):
            raise RuntimeError("tool boom")

    monkeypatch.setattr(runner_module, "get_flow_parser_runner_client", lambda: _FakeRunnerClient())
    monkeypatch.setattr(runner_module, "build_structured_tool_test_tool", lambda *args, **kwargs: _ExplodingTool())

    runner = runner_module.StructuredToolTestRunner(
        skill_id="dataflow_analysis",
        request_payload={
            "file_path": "src/xplist.c",
            "function_name": "plist_from_xml",
            "tool_input": {
                "variable_name": "plist_xml",
                "sink_hints": ["xmlReadMemory", "xmlParseMemory"],
            },
        },
        project_name="libplist",
        zip_path=str(archive_path),
        fallback_used=False,
        event_emitter=emitter,
    )

    with pytest.raises(RuntimeError, match="tool boom"):
        await runner.run()

    tool_result_event = next(event for event in emitter.events if event["type"] == "tool_result")
    assert tool_result_event["tool_output"]["error"] == "tool boom"
    assert tool_result_event["tool_output"]["error_code"] == "RuntimeError"
