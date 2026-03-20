from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.agent.tools import CodeWindowTool, FileOutlineTool, FileSearchTool


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

    with patch.object(tool, "_run_search_engines_sync", return_value=(mocked_results, 1, "grep")):
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
