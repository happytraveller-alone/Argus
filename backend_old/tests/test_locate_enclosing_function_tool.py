import pytest

from app.services.agent.tools.file_tool import LocateEnclosingFunctionTool


@pytest.mark.asyncio
async def test_locate_enclosing_function_tool_returns_covering_function(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text(
        "def outer():\n"
        "    safe = 1\n"
        "\n"
        "def target(value):\n"
        "    return value + 1\n",
        encoding="utf-8",
    )

    tool = LocateEnclosingFunctionTool(project_root=str(tmp_path))
    result = await tool.execute(file_path="demo.py", line=5)

    assert result.success is True
    assert result.error_code is None
    assert result.data["file_path"] == "demo.py"
    assert result.data["line"] == 5
    assert result.data["symbol"]["name"] == "target"
    assert result.data["symbol"]["start_line"] == 4
    assert result.data["symbol"]["end_line"] == 5
    assert result.data["symbol"]["signature"] == "def target(value):"
    assert result.data["symbol"]["parameters"] == [
        {
            "name": "value",
            "type": None,
            "default": None,
            "required": True,
            "position": 0,
        }
    ]
    assert result.data["symbol"]["return_type"] is None
    method = result.data["resolution"]["method"]
    engine = result.data["resolution"]["engine"]
    confidence = result.data["resolution"]["confidence"]
    degraded = result.data["resolution"]["degraded"]
    assert method
    assert engine == method
    assert 0.0 <= confidence <= 1.0
    assert degraded is any(token in method for token in ("regex", "fallback", "missing"))
    if degraded:
        assert confidence < 0.8
    else:
        assert confidence >= 0.8


@pytest.mark.asyncio
async def test_locate_enclosing_function_tool_parses_line_from_file_path(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text(
        "def outer():\n"
        "    safe = 1\n"
        "\n"
        "def target(value):\n"
        "    return value + 1\n",
        encoding="utf-8",
    )

    tool = LocateEnclosingFunctionTool(project_root=str(tmp_path))
    result = await tool.execute(file_path="demo.py:5")

    assert result.success is True
    assert result.data["file_path"] == "demo.py"
    assert result.data["line"] == 5
    assert result.data["symbol"]["name"] == "target"


@pytest.mark.asyncio
async def test_locate_enclosing_function_tool_prefers_explicit_line_start_and_path_alias(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text(
        "def outer():\n"
        "    safe = 1\n"
        "\n"
        "def target(value):\n"
        "    return value + 1\n",
        encoding="utf-8",
    )

    tool = LocateEnclosingFunctionTool(project_root=str(tmp_path))
    result = await tool.execute(path="demo.py:1", line=1, line_start=5)

    assert result.success is True
    assert result.data["file_path"] == "demo.py"
    assert result.data["line"] == 5
    assert result.data["symbol"]["name"] == "target"


@pytest.mark.asyncio
async def test_locate_enclosing_function_tool_marks_regex_fallback_as_degraded(tmp_path, monkeypatch):
    source = tmp_path / "demo.c"
    source.write_text(
        "static int helper(void) { return 0; }\n"
        "char *target(const struct tm *tm, char *buf) {\n"
        "  return buf;\n"
        "}\n",
        encoding="utf-8",
    )

    tool = LocateEnclosingFunctionTool(project_root=str(tmp_path))

    def _fake_locate(**kwargs):
        return {
            "file_path": "demo.c",
            "function": "target",
            "start_line": 2,
            "end_line": 4,
            "language": "c",
            "resolution_method": "tree_sitter_cli_regex",
            "resolution_engine": "tree_sitter_cli_regex",
            "diagnostics": ["regex_enclosing_match"],
        }

    monkeypatch.setattr(tool.locator, "locate", _fake_locate)

    result = await tool.execute(file_path="demo.c", line=3)

    assert result.success is True
    assert result.data["symbol"]["signature"].startswith("char *target(")
    assert result.data["symbol"]["parameters"] == [
        {
            "name": "tm",
            "type": "const struct tm *",
            "default": None,
            "required": True,
            "position": 0,
        },
        {
            "name": "buf",
            "type": "char *",
            "default": None,
            "required": True,
            "position": 1,
        },
    ]
    assert result.data["symbol"]["return_type"] == "char *"
    method = result.data["resolution"]["method"]
    engine = result.data["resolution"]["engine"]
    confidence = result.data["resolution"]["confidence"]
    assert method == "tree_sitter_cli_regex"
    assert engine == method
    assert result.data["resolution"]["degraded"] is True
    assert confidence < 0.8


@pytest.mark.asyncio
async def test_locate_enclosing_function_tool_rejects_out_of_range_line(tmp_path):
    source = tmp_path / "demo.py"
    source.write_text(
        "def target(value):\n"
        "    return value + 1\n",
        encoding="utf-8",
    )

    tool = LocateEnclosingFunctionTool(project_root=str(tmp_path))
    result = await tool.execute(file_path="demo.py", line=99)

    assert result.success is False
    assert result.error_code == "invalid_input"
    assert result.data is None


@pytest.mark.asyncio
async def test_locate_enclosing_function_tool_rejects_unsupported_language(tmp_path):
    source = tmp_path / "demo.rb"
    source.write_text(
        "def target(value)\n"
        "  value + 1\n"
        "end\n",
        encoding="utf-8",
    )

    tool = LocateEnclosingFunctionTool(project_root=str(tmp_path))
    result = await tool.execute(file_path="demo.rb", line=2)

    assert result.success is False
    assert result.error_code == "unsupported_language"
    assert result.data is None
