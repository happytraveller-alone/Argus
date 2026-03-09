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
    result = await tool.execute(file_path="demo.py", line_start=5)

    assert result.success is True
    assert result.data["enclosing_function"]["name"] == "target"
    assert result.data["enclosing_function"]["start_line"] == 4
    assert result.data["enclosing_function"]["end_line"] == 5
