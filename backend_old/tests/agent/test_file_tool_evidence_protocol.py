from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.agent.tools.file_tool import (
    CodeWindowTool,
    FileOutlineTool,
    FileSearchTool,
    ListFilesTool,
    LocateEnclosingFunctionTool,
)
from app.services.agent.tools.evidence_protocol import validate_evidence_metadata


@pytest.mark.asyncio
async def test_code_window_tool_returns_code_window_evidence_metadata(temp_project_dir):
    tool = CodeWindowTool(temp_project_dir)

    result = await tool.execute(file_path="src/sql_vuln.py", anchor_line=4, before_lines=1, after_lines=2)

    assert result.success is True
    metadata = result.metadata
    assert metadata.get("render_type") == "code_window"
    assert metadata.get("display_command")
    assert metadata.get("entries")

    entry = metadata["entries"][0]
    assert entry["file_path"] == "src/sql_vuln.py"
    assert entry["start_line"] == 3
    assert entry["end_line"] == 6
    assert entry["focus_line"] == 4
    assert [line["line_number"] for line in entry["lines"]] == [3, 4, 5, 6]
    assert entry["lines"][1]["kind"] == "focus"


@pytest.mark.asyncio
async def test_file_search_tool_returns_python_search_hits_protocol(temp_project_dir):
    tool = FileSearchTool(temp_project_dir)

    with patch("app.services.agent.tools.file_tool.shutil.which", return_value=None):
        result = await tool.execute(keyword="cursor.execute", directory="src")

    assert result.success is True
    metadata = result.metadata
    assert metadata.get("render_type") == "search_hits"
    assert metadata.get("engine") == "python"
    assert metadata.get("command_chain") == ["python"]
    assert metadata.get("entries")

    assert any(entry["file_path"] == "src/sql_vuln.py" for entry in metadata["entries"])
    first_entry = metadata["entries"][0]
    assert first_entry["match_line"] >= 1
    assert "lines" not in first_entry
    assert "window_start_line" not in first_entry
    assert "window_end_line" not in first_entry


@pytest.mark.asyncio
async def test_file_search_tool_preserves_grep_command_chain(temp_project_dir):
    tool = FileSearchTool(temp_project_dir)
    mocked_results = [
        {
            "file": "src/cmd_vuln.py",
            "line": 7,
            "match": "os.system(f\"echo {user_input}\")",
            "column": 5,
            "symbol_name": "run_command",
            "match_kind": "text",
        }
    ]

    with patch.object(
        tool,
        "_run_search_engines_sync",
        return_value=(mocked_results, 1, {"src/cmd_vuln.py": 1}, "grep"),
    ):
        result = await tool.execute(keyword="os.system", directory="src")

    assert result.success is True
    assert result.metadata.get("engine") == "grep"
    assert result.metadata.get("command_chain") == ["grep"]
    assert result.metadata["entries"][0]["match_text"] == 'os.system(f"echo {user_input}")'


@pytest.mark.asyncio
async def test_file_outline_tool_does_not_misclassify_java_file_as_express(temp_project_dir):
    java_file = Path(temp_project_dir) / "src" / "ParserConfig.java"
    java_file.write_text(
        "package com.alibaba.fastjson.parser;\n"
        "import java.util.Map;\n"
        "public class ParserConfig {\n"
        "  public String expression = \"allow fast expression\";\n"
        "}\n",
        encoding="utf-8",
    )

    tool = FileOutlineTool(temp_project_dir)
    result = await tool.execute(file_path="src/ParserConfig.java")

    assert result.success is True
    metadata = result.metadata
    assert metadata.get("render_type") == "outline_summary"
    entry = metadata["entries"][0]
    assert entry["file_path"] == "src/ParserConfig.java"
    assert "express" not in entry["framework_hints"]


def test_validate_evidence_metadata_accepts_new_render_types():
    base = {
        "command_chain": ["tool"],
        "display_command": "tool",
    }

    validate_evidence_metadata(
        render_type="file_list",
        entries=[
            {
                "directory": "src",
                "pattern": "*.py",
                "recursive": True,
                "files": ["src/sql_vuln.py"],
                "directories": ["src/nested/"],
                "file_count": 1,
                "dir_count": 1,
                "truncated": False,
                "recommended_next_directories": ["src/nested/"],
            }
        ],
        **base,
    )
    validate_evidence_metadata(
        render_type="locator_result",
        entries=[
            {
                "file_path": "src/sql_vuln.py",
                "line": 8,
                "symbol_name": "get_user",
                "start_line": 4,
                "end_line": 12,
                "signature": "def get_user(user_id):",
                "parameters": [{"name": "user_id"}],
                "return_type": None,
                "engine": "python_tree_sitter",
                "confidence": 0.95,
                "degraded": False,
            }
        ],
        **base,
    )
    validate_evidence_metadata(
        render_type="analysis_summary",
        entries=[
            {
                "title": "Analysis",
                "summary": "Found risky flows.",
                "severity_stats": {"high": 1},
                "hit_count": 1,
                "key_files": ["src/sql_vuln.py"],
                "highlights": ["Unsanitized SQL."],
                "next_actions": ["Verify exploitability."],
            }
        ],
        **base,
    )
    validate_evidence_metadata(
        render_type="flow_analysis",
        entries=[
            {
                "source_nodes": ["request.user_input"],
                "sink_nodes": ["cursor.execute"],
                "taint_steps": ["input -> sql"],
                "call_chain": ["handler -> dao"],
                "blocked_reasons": [],
                "reachability": "reachable",
                "path_found": True,
                "path_score": 0.91,
                "confidence": 0.88,
                "engine": "llm",
                "next_actions": ["Confirm at runtime."],
            }
        ],
        **base,
    )
    validate_evidence_metadata(
        render_type="verification_summary",
        entries=[
            {
                "vulnerability_type": "sqli",
                "target": "/users?id=1",
                "payload": "' OR 1=1 --",
                "verdict": "confirmed",
                "evidence": "Echoed SQL syntax error.",
                "response_status": 500,
                "runtime_status": "passed",
                "error": None,
            }
        ],
        **base,
    )
    validate_evidence_metadata(
        render_type="report_summary",
        entries=[
            {
                "report_id": "rpt-1",
                "title": "SQL Injection",
                "severity": "high",
                "vulnerability_type": "sqli",
                "location": "src/sql_vuln.py:8",
                "verified": True,
                "recommendation": "Parameterize query.",
                "confidence": 0.91,
                "cvss_score": 8.8,
            }
        ],
        **base,
    )


@pytest.mark.asyncio
async def test_list_files_tool_returns_file_list_evidence_metadata(temp_project_dir):
    tool = ListFilesTool(temp_project_dir)

    result = await tool.execute(directory="src", recursive=True, pattern="*.py")

    assert result.success is True
    metadata = result.metadata
    assert metadata.get("render_type") == "file_list"
    assert metadata.get("display_command")
    assert metadata.get("command_chain") == ["list_files"]
    assert metadata.get("entries")

    entry = metadata["entries"][0]
    assert entry["directory"] == "src"
    assert entry["pattern"] == "*.py"
    assert entry["recursive"] is True
    assert "src/sql_vuln.py" in entry["files"]
    assert isinstance(entry["directories"], list)
    assert isinstance(entry["file_count"], int)
    assert isinstance(entry["dir_count"], int)
    assert isinstance(entry["truncated"], bool)
    assert isinstance(entry["recommended_next_directories"], list)


@pytest.mark.asyncio
async def test_locate_enclosing_function_tool_returns_locator_evidence_metadata(temp_project_dir):
    tool = LocateEnclosingFunctionTool(project_root=temp_project_dir)

    result = await tool.execute(file_path="src/sql_vuln.py", line=8)

    assert result.success is True
    metadata = result.metadata
    assert metadata.get("render_type") == "locator_result"
    assert metadata.get("display_command")
    assert metadata.get("command_chain") == ["locate_enclosing_function"]
    assert metadata.get("entries")

    entry = metadata["entries"][0]
    assert entry["file_path"] == "src/sql_vuln.py"
    assert entry["line"] == 8
    assert entry["symbol_name"]
    assert isinstance(entry["start_line"], int)
    assert isinstance(entry["end_line"], int)
    assert "engine" in entry
    assert "confidence" in entry
    assert "degraded" in entry
