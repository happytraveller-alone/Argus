from app.services.agent.flow.lightweight.callgraph_code2flow import Code2FlowCallGraph


def test_code2flow_runtime_prefers_flow_parser_runner(monkeypatch, tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text("def caller():\n    callee()\n\ndef callee():\n    return 1\n", encoding="utf-8")

    seen = {}

    class _FakeRunnerClient:
        def generate_code2flow_callgraph(self, files, *, timeout_seconds=None):
            seen["files"] = files
            seen["timeout_seconds"] = timeout_seconds
            return {
                "edges": {"caller": ["callee"]},
                "blocked_reasons": [],
                "used_engine": "code2flow",
                "diagnostics": {"runner": "ok"},
            }

    monkeypatch.setattr(
        "app.services.agent.flow.lightweight.callgraph_code2flow.get_flow_parser_runner_client",
        lambda: _FakeRunnerClient(),
    )

    graph = Code2FlowCallGraph(project_root=str(tmp_path), max_files=10)
    result = graph.generate()

    assert len(seen["files"]) == 1
    assert seen["files"][0]["file_path"] == "demo.py"
    assert "def caller()" in seen["files"][0]["content"]
    assert result.used_engine == "code2flow"
    assert result.edges == {"caller": {"callee"}}


def test_code2flow_runtime_reports_compatible_missing_reason_when_runner_unavailable(tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text("def caller():\n    callee()\n\ndef callee():\n    return 1\n", encoding="utf-8")

    graph = Code2FlowCallGraph(project_root=str(tmp_path), max_files=10)
    result = graph.generate()

    assert result.used_engine == "fallback"
    assert "code2flow_not_installed" in result.blocked_reasons
