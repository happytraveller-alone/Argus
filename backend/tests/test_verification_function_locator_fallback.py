import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.agent.agents.verification import VerificationAgent


class _DummyLocatorMiss:
    def locate(self, **kwargs):
        return {
            "function": None,
            "start_line": None,
            "end_line": None,
            "resolution_method": "python_tree_sitter",
            "resolution_engine": "python_tree_sitter",
            "language": "c",
            "diagnostics": ["tree_sitter_miss"],
        }


@pytest.mark.asyncio
async def test_enrich_function_metadata_with_mcp_symbol_index(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    target = src_dir / "time64.c"
    target.write_text(
        "int helper(void) { return 0; }\n"
        "char *asctime64_r(const struct tm *tm, char *buf) {\n"
        "  return buf;\n"
        "}\n",
        encoding="utf-8",
    )

    agent = VerificationAgent(
        llm_service=SimpleNamespace(),
        tools={},
        event_emitter=SimpleNamespace(),
    )

    async def _fake_execute_tool(tool_name: str, tool_input: dict):
        assert tool_name == "locate_enclosing_function"
        assert tool_input.get("file_path") == "src/time64.c"
        return json.dumps(
            {
                "symbols": [
                    {
                        "name": "asctime64_r",
                        "kind": "function",
                        "start_line": 2,
                        "end_line": 4,
                    }
                ]
            },
            ensure_ascii=False,
        )

    agent.execute_tool = _fake_execute_tool  # type: ignore[method-assign]
    finding = {"file_path": "src/time64.c", "line_start": 3}
    await agent._enrich_function_metadata_with_locator([finding], str(tmp_path))

    assert finding.get("function_name") == "asctime64_r"
    assert finding.get("function_start_line") == 2
    assert finding.get("function_end_line") == 4
    assert finding.get("function_resolution_engine") == "mcp_symbol_index"


def test_resolve_function_metadata_uses_regex_fallback_when_tree_sitter_misses(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    target = src_dir / "time64.c"
    target.write_text(
        "static int helper() { return 0; }\n\n"
        "char *asctime64_r(const struct tm *tm, char *buf) {\n"
        "  if (!buf) return 0;\n"
        "  return buf;\n"
        "}\n",
        encoding="utf-8",
    )

    agent = VerificationAgent(
        llm_service=SimpleNamespace(),
        tools={},
        event_emitter=SimpleNamespace(),
    )

    finding = {"file_path": "src/time64.c", "line_start": 4}
    resolved = agent._resolve_function_metadata(
        finding=finding,
        project_root=str(tmp_path),
        ast_cache={},
        file_cache={},
        locator=_DummyLocatorMiss(),
    )

    assert resolved.get("function") == "asctime64_r"
    assert resolved.get("resolution_engine") == "regex_fallback"
    assert resolved.get("start_line") == 3
    assert resolved.get("end_line") >= 5


def test_resolve_function_metadata_reports_missing_when_all_fallbacks_fail(tmp_path: Path):
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    target = src_dir / "time64.c"
    target.write_text(
        "int x = 0;\n"
        "int y = x + 1;\n",
        encoding="utf-8",
    )

    agent = VerificationAgent(
        llm_service=SimpleNamespace(),
        tools={},
        event_emitter=SimpleNamespace(),
    )

    finding = {"file_path": "src/time64.c", "line_start": 1}
    resolved = agent._resolve_function_metadata(
        finding=finding,
        project_root=str(tmp_path),
        ast_cache={},
        file_cache={},
        locator=_DummyLocatorMiss(),
    )

    assert resolved.get("function") is None
    assert resolved.get("resolution_engine") == "missing_enclosing_function"
    assert resolved.get("diagnostics") is not None
