from unittest.mock import patch

import pytest

from app.services.agent.tools import FileReadTool, FileSearchTool


@pytest.mark.asyncio
async def test_file_read_tool_returns_code_window_evidence_metadata(temp_project_dir):
    tool = FileReadTool(temp_project_dir)

    result = await tool.execute(file_path="src/sql_vuln.py", start_line=3, end_line=6)

    assert result.success is True
    metadata = result.metadata
    assert metadata.get("render_type") == "code_window"
    assert metadata.get("display_command")
    assert metadata.get("entries")

    entry = metadata["entries"][0]
    assert entry["file_path"] == "src/sql_vuln.py"
    assert entry["start_line"] == 3
    assert entry["end_line"] == 6
    assert entry["focus_line"] == 3
    assert [line["line_number"] for line in entry["lines"]] == [3, 4, 5, 6]
    assert entry["lines"][0]["kind"] == "focus"


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

    first_entry = metadata["entries"][0]
    assert first_entry["file_path"] == "src/sql_vuln.py"
    assert first_entry["match_line"] >= 1
    assert any(line["kind"] == "match" for line in first_entry["lines"])


@pytest.mark.asyncio
async def test_file_search_tool_preserves_rg_and_sed_command_chain(temp_project_dir):
    tool = FileSearchTool(temp_project_dir)
    mocked_results = [
        {
            "file": "src/sql_vuln.py",
            "line": 8,
            "match": "cursor.execute(query)",
            "window_start_line": 7,
            "window_end_line": 9,
            "lines": [
                {"line_number": 7, "text": '    query = "..."', "kind": "context"},
                {"line_number": 8, "text": "    cursor.execute(query)", "kind": "match"},
                {"line_number": 9, "text": "    return cursor.fetchone()", "kind": "context"},
            ],
            "command_chain": ["rg", "sed"],
        }
    ]

    with patch.object(tool, "_run_search_engines_sync", return_value=(mocked_results, 1, "rg")):
        result = await tool.execute(keyword="cursor.execute", directory="src")

    assert result.success is True
    assert result.metadata.get("engine") == "rg"
    assert result.metadata.get("command_chain") == ["rg", "sed"]
    assert result.metadata["entries"][0]["lines"][1]["kind"] == "match"


@pytest.mark.asyncio
async def test_file_search_tool_preserves_grep_command_chain(temp_project_dir):
    tool = FileSearchTool(temp_project_dir)
    mocked_results = [
        {
            "file": "src/cmd_vuln.py",
            "line": 7,
            "match": "os.system(f\"echo {user_input}\")",
            "window_start_line": 6,
            "window_end_line": 8,
            "lines": [
                {"line_number": 6, "text": "    # 直接执行用户输入", "kind": "context"},
                {
                    "line_number": 7,
                    "text": '    os.system(f"echo {user_input}")',
                    "kind": "match",
                },
                {"line_number": 8, "text": "    ", "kind": "context"},
            ],
            "command_chain": ["grep"],
        }
    ]

    with patch.object(tool, "_run_search_engines_sync", return_value=(mocked_results, 1, "grep")):
        result = await tool.execute(keyword="os.system", directory="src")

    assert result.success is True
    assert result.metadata.get("engine") == "grep"
    assert result.metadata.get("command_chain") == ["grep"]
