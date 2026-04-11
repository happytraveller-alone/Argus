from app.services.agent.flow.lightweight.ast_index import ASTCallIndex


def test_ast_index_build_uses_definition_provider_batch(tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text(
        "def caller():\n    callee()\n\ndef callee():\n    return 1\n",
        encoding="utf-8",
    )

    class _FakeDefinitionProvider:
        def extract_definitions_batch(self, items):
            assert len(items) == 1
            assert items[0]["file_path"] == "demo.py"
            return {
                "demo.py": {
                    "ok": True,
                    "definitions": [
                        {
                            "type": "function",
                            "name": "caller",
                            "parent_name": None,
                            "start_point": [0, 0],
                            "end_point": [1, 0],
                            "start_byte": 0,
                            "end_byte": 26,
                            "node_type": "function_definition",
                        },
                        {
                            "type": "function",
                            "name": "callee",
                            "parent_name": None,
                            "start_point": [3, 0],
                            "end_point": [4, 0],
                            "start_byte": 28,
                            "end_byte": 54,
                            "node_type": "function_definition",
                        },
                    ],
                    "diagnostics": ["runner_ok"],
                    "error": None,
                }
            }

    index = ASTCallIndex(
        project_root=str(tmp_path),
        definition_provider=_FakeDefinitionProvider(),
    )
    index.build()

    assert "caller" in index.symbols_by_name
    assert "callee" in index.symbols_by_name
    assert index.symbols_by_name["caller"][0].file_path == "demo.py"
