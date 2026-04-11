"""
测试 FileReadTool 的行号输出格式。
"""

import re
import pytest

from app.services.agent.tools.file_tool import FileReadTool


@pytest.fixture()
def sample_py(tmp_path):
    """创建一个 5 行的示例 Python 文件。"""
    content = (
        "def hello():\n"
        '    print("hello")\n'
        "\n"
        "def world():\n"
        "    return 42\n"
    )
    p = tmp_path / "sample.py"
    p.write_text(content, encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_full_file_has_line_numbers(sample_py):
    """读取完整文件时，每行都应包含行号前缀（格式：'N| code'）。"""
    tool = FileReadTool(project_root=str(sample_py))
    result = await tool._execute(file_path="sample.py")

    assert result.success is True
    assert result.data is not None

    # 至少第 1、2、4、5 行需要有行号前缀
    data = result.data
    assert re.search(r"\b1\|", data), "第 1 行行号缺失"
    assert re.search(r"\b2\|", data), "第 2 行行号缺失"
    assert re.search(r"\b4\|", data), "第 4 行行号缺失"
    assert re.search(r"\b5\|", data), "第 5 行行号缺失"


@pytest.mark.asyncio
async def test_line_range_preserves_original_line_numbers(sample_py):
    """读取部分行时，行号应保持在文件中的原始编号，而不是从 1 重新计数。"""
    tool = FileReadTool(project_root=str(sample_py))
    result = await tool._execute(file_path="sample.py", start_line=4, end_line=5)

    assert result.success is True
    data = result.data

    # 应包含原始行号 4 和 5，而不是 1 和 2
    assert re.search(r"\b4\|", data), "start_line=4 时行号应为 4，而非 1"
    assert re.search(r"\b5\|", data), "end_line=5 时行号应为 5，而非 2"
    # 不应包含行号 1 或 2（这些行没有被读取）
    assert not re.search(r"^\s*1\|", data, re.MULTILINE), "不应包含第 1 行行号"
    assert not re.search(r"^\s*2\|", data, re.MULTILINE), "不应包含第 2 行行号"


@pytest.mark.asyncio
async def test_metadata_contains_line_range(sample_py):
    """metadata 中应包含正确的 start_line / end_line / total_lines 信息。"""
    tool = FileReadTool(project_root=str(sample_py))
    result = await tool._execute(file_path="sample.py", start_line=2, end_line=4)

    assert result.success is True
    meta = result.metadata
    assert meta["start_line"] == 2
    assert meta["end_line"] == 4
    assert meta["total_lines"] == 5


@pytest.mark.asyncio
async def test_nonexistent_file_returns_error(tmp_path):
    """读取不存在的文件时应返回 success=False 且包含错误信息。"""
    tool = FileReadTool(project_root=str(tmp_path))
    result = await tool._execute(file_path="nonexistent.py")

    assert result.success is False
    assert result.error is not None
