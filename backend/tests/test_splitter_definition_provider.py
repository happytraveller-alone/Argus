import pytest

from app.services.rag.splitter import ChunkType, CodeSplitter


def test_splitter_uses_precomputed_definitions_without_local_tree_sitter(monkeypatch):
    splitter = CodeSplitter()

    def _fail_parse(*args, **kwargs):
        raise AssertionError("local tree-sitter should not run when definitions are precomputed")

    monkeypatch.setattr(splitter._ts_parser, "parse", _fail_parse)

    content = "def target(value):\n    return value + 1\n"
    chunks = splitter.split_file(
        content,
        "demo.py",
        definitions=[
            {
                "type": "function",
                "name": "target",
                "parent_name": None,
                "start_point": [0, 0],
                "end_point": [1, 0],
                "start_byte": 0,
                "end_byte": len(content),
                "node_type": "function_definition",
            }
        ],
    )

    assert len(chunks) == 1
    assert chunks[0].name == "target"
    assert chunks[0].chunk_type == ChunkType.FUNCTION


@pytest.mark.asyncio
async def test_splitter_async_accepts_precomputed_definitions(monkeypatch):
    splitter = CodeSplitter()

    def _fail_parse(*args, **kwargs):
        raise AssertionError("local tree-sitter should not run when definitions are precomputed")

    monkeypatch.setattr(splitter._ts_parser, "parse", _fail_parse)

    content = "def target(value):\n    return value + 1\n"
    chunks = await splitter.split_file_async(
        content,
        "demo.py",
        definitions=[
            {
                "type": "function",
                "name": "target",
                "parent_name": None,
                "start_point": [0, 0],
                "end_point": [1, 0],
                "start_byte": 0,
                "end_byte": len(content),
                "node_type": "function_definition",
            }
        ],
    )

    assert len(chunks) == 1
    assert chunks[0].name == "target"
