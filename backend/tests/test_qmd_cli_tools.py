import pytest

from app.services.agent.tools.qmd_cli_tools import (
    QmdGetTool,
    QmdMultiGetTool,
    QmdQueryTool,
    QmdStatusTool,
)


class _FakeKB:
    collection_name = "task_abc"

    def __init__(self):
        self.query_calls = []
        self.get_calls = []
        self.multi_calls = []
        self.status_calls = 0

    @staticmethod
    def build_multiline_query(searches):
        return "\n".join(f"{item.get('type')}:{item.get('query')}" for item in searches)

    def query(self, *, query_text, limit=5, collection=None, full=False):
        self.query_calls.append((query_text, limit, collection, full))
        if "boom" in query_text:
            return {"success": False, "error": "query_failed"}
        return {"success": True, "data": [{"docid": "doc-1", "score": 0.9}]}

    def get(self, *, doc_id, lines=None, from_line=None):
        self.get_calls.append((doc_id, lines, from_line))
        return {"success": True, "data": f"content:{doc_id}"}

    def multi_get(self, *, pattern, lines=None, max_bytes=None):
        self.multi_calls.append((pattern, lines, max_bytes))
        return {"success": True, "data": [{"docid": "a.md"}, {"docid": "b.md"}]}

    def status(self):
        self.status_calls += 1
        return {"success": True, "data": "ok"}


@pytest.mark.asyncio
async def test_qmd_query_tool_supports_multiline_searches():
    kb = _FakeKB()
    tool = QmdQueryTool(kb)  # type: ignore[arg-type]

    result = await tool.execute(
        searches=[
            {"type": "lex", "query": "time64"},
            {"type": "vec", "query": "overflow"},
        ],
        limit=7,
        collections=["task_custom"],
    )

    assert result.success is True
    assert kb.query_calls
    query_text, limit, collection, full = kb.query_calls[0]
    assert query_text == "lex:time64\nvec:overflow"
    assert limit == 7
    assert collection == "task_custom"
    assert full is False


@pytest.mark.asyncio
async def test_qmd_query_tool_returns_prefixed_error():
    kb = _FakeKB()
    tool = QmdQueryTool(kb)  # type: ignore[arg-type]

    result = await tool.execute(query="boom")
    assert result.success is False
    assert "qmd_cli_failed:" in str(result.error)


@pytest.mark.asyncio
async def test_qmd_get_multi_get_and_status_tools():
    kb = _FakeKB()
    get_tool = QmdGetTool(kb)  # type: ignore[arg-type]
    multi_get_tool = QmdMultiGetTool(kb)  # type: ignore[arg-type]
    status_tool = QmdStatusTool(kb)  # type: ignore[arg-type]

    get_result = await get_tool.execute(path="agents/recon.md", lines=50)
    multi_result = await multi_get_tool.execute(ids=["a.md", "b.md"], lines=30)
    status_result = await status_tool.execute()

    assert get_result.success is True
    assert multi_result.success is True
    assert status_result.success is True
    assert kb.get_calls[0][0] == "agents/recon.md"
    assert kb.multi_calls[0][0] == "a.md,b.md"
    assert kb.status_calls == 1
