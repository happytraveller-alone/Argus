from app.services.agent.core.flow.lightweight.callgraph_code2flow import Code2FlowCallGraph


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
        "app.services.agent.core.flow.lightweight.callgraph_code2flow.get_flow_parser_runner_client",
        lambda: _FakeRunnerClient(),
    )

    graph = Code2FlowCallGraph(project_root=str(tmp_path), max_files=10)
    result = graph.generate()

    assert len(seen["files"]) == 1
    assert seen["files"][0]["file_path"] == "demo.py"
    assert "def caller()" in seen["files"][0]["content"]
    assert result.used_engine == "code2flow"
    assert result.edges == {"caller": {"callee"}}


def test_code2flow_runtime_reports_exec_failed_when_runner_container_is_unavailable(tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text("def caller():\n    callee()\n\ndef callee():\n    return 1\n", encoding="utf-8")

    graph = Code2FlowCallGraph(project_root=str(tmp_path), max_files=10)
    result = graph.generate()

    assert result.used_engine == "fallback"
    assert "code2flow_exec_failed" in result.blocked_reasons


def test_code2flow_runtime_preserves_no_edges_reason(monkeypatch, tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text("def caller():\n    callee()\n\ndef callee():\n    return 1\n", encoding="utf-8")

    class _FakeRunnerClient:
        def generate_code2flow_callgraph(self, files, *, timeout_seconds=None):
            _ = files, timeout_seconds
            return {
                "ok": False,
                "edges": {},
                "blocked_reasons": ["code2flow_no_edges"],
                "used_engine": "fallback",
                "diagnostics": {
                    "binary_path": "/opt/flow-parser-venv/bin/code2flow",
                    "stderr_excerpt": "generated graph without edges",
                },
            }

    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.callgraph_code2flow.get_flow_parser_runner_client",
        lambda: _FakeRunnerClient(),
    )

    graph = Code2FlowCallGraph(project_root=str(tmp_path), max_files=10)
    result = graph.generate()

    assert result.used_engine == "fallback"
    assert result.blocked_reasons == ["code2flow_no_edges"]
    assert "code2flow_not_installed" not in result.blocked_reasons
    assert result.diagnostics["binary_path"] == "/opt/flow-parser-venv/bin/code2flow"
    assert "generated graph without edges" in result.diagnostics["stderr_excerpt"]


def test_code2flow_runtime_preserves_exec_failed_reason(monkeypatch, tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text("def caller():\n    callee()\n\ndef callee():\n    return 1\n", encoding="utf-8")

    class _FakeRunnerClient:
        def generate_code2flow_callgraph(self, files, *, timeout_seconds=None):
            _ = files, timeout_seconds
            return {
                "ok": False,
                "edges": {},
                "blocked_reasons": ["code2flow_exec_failed"],
                "used_engine": "fallback",
                "diagnostics": {
                    "binary_path": "/opt/flow-parser-venv/bin/code2flow",
                    "stderr_excerpt": "graphviz failed",
                    "error": "graphviz failed",
                },
            }

    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.callgraph_code2flow.get_flow_parser_runner_client",
        lambda: _FakeRunnerClient(),
    )

    graph = Code2FlowCallGraph(project_root=str(tmp_path), max_files=10)
    result = graph.generate()

    assert result.used_engine == "fallback"
    assert result.blocked_reasons == ["code2flow_exec_failed"]
    assert result.diagnostics["error"] == "graphviz failed"
    assert result.diagnostics["binary_path"] == "/opt/flow-parser-venv/bin/code2flow"


def test_code2flow_runtime_maps_binary_not_found_to_not_installed(monkeypatch, tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text("def caller():\n    callee()\n\ndef callee():\n    return 1\n", encoding="utf-8")

    class _FakeRunnerClient:
        def generate_code2flow_callgraph(self, files, *, timeout_seconds=None):
            _ = files, timeout_seconds
            return {
                "ok": False,
                "edges": {},
                "blocked_reasons": ["code2flow_binary_not_found"],
                "used_engine": "fallback",
                "diagnostics": {
                    "binary_path": "",
                    "error": "code2flow_binary_not_found",
                },
            }

    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.callgraph_code2flow.get_flow_parser_runner_client",
        lambda: _FakeRunnerClient(),
    )

    graph = Code2FlowCallGraph(project_root=str(tmp_path), max_files=10)
    result = graph.generate()

    assert result.used_engine == "fallback"
    assert result.blocked_reasons == ["code2flow_not_installed"]
    assert result.diagnostics["error"] == "code2flow_binary_not_found"
