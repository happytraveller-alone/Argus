import json
import subprocess
from pathlib import Path

from app.services.agent.runtime_settings import settings
from app.services.agent.core.flow.lightweight.callgraph_code2flow import Code2FlowCallGraph


def test_code2flow_runtime_delegates_generation_contract_to_rust(monkeypatch, tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text("def caller():\n    callee()\n\ndef callee():\n    return 1\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("skip", encoding="utf-8")

    seen = {}

    def _fake_run(args, *, capture_output, text, check, timeout):
        assert capture_output is True
        assert text is True
        assert check is False
        seen["args"] = list(args)
        seen["timeout"] = timeout
        request_path = Path(args[3])
        seen["request"] = json.loads(request_path.read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "edges": {"caller": ["callee"]},
                    "blocked_reasons": [],
                    "used_engine": "code2flow",
                    "diagnostics": {
                        "runner": "ok",
                        "binary_path": "/opt/flow-parser-venv/bin/code2flow",
                        "edge_count": "1",
                        "node_count": "1",
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.callgraph_code2flow.subprocess.run",
        _fake_run,
    )
    monkeypatch.setattr(
        settings,
        "FLOW_PARSER_RUNNER_IMAGE",
        "vulhunter/flow-parser-runner-local:latest",
    )

    graph = Code2FlowCallGraph(
        project_root=str(tmp_path),
        target_files=["./demo.py"],
        timeout_sec=37,
        max_files=23,
    )
    result = graph.generate()

    assert seen["args"][1:3] == ["code2flow", "--request"]
    assert seen["timeout"] == 37
    assert seen["request"] == {
        "project_root": str(tmp_path.resolve()),
        "target_files": ["demo.py"],
        "timeout_seconds": 37,
        "max_files": 23,
        "image": "vulhunter/flow-parser-runner-local:latest",
    }
    assert "files" not in seen["request"]
    assert result.used_engine == "code2flow"
    assert result.edges == {"caller": {"callee"}}
    assert result.diagnostics["binary_path"] == "/opt/flow-parser-venv/bin/code2flow"
    assert result.diagnostics["edge_count"] == "1"
    assert result.diagnostics["node_count"] == "1"


def test_code2flow_runtime_reports_not_installed_when_rust_bridge_is_unavailable(monkeypatch, tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text("def caller():\n    callee()\n\ndef callee():\n    return 1\n", encoding="utf-8")

    def _fake_run(*args, **kwargs):
        _ = args, kwargs
        raise OSError("backend runtime startup missing")

    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.callgraph_code2flow.subprocess.run",
        _fake_run,
    )

    graph = Code2FlowCallGraph(project_root=str(tmp_path), max_files=10)
    result = graph.generate()

    assert result.used_engine == "fallback"
    assert result.blocked_reasons == ["code2flow_not_installed"]
    assert "backend runtime startup missing" in result.diagnostics["error"]


def test_code2flow_runtime_preserves_no_edges_reason(monkeypatch, tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text("def caller():\n    callee()\n\ndef callee():\n    return 1\n", encoding="utf-8")

    def _fake_run(args, *, capture_output, text, check, timeout):
        _ = args, capture_output, text, check, timeout
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": False,
                    "edges": {},
                    "blocked_reasons": ["code2flow_no_edges"],
                    "used_engine": "fallback",
                    "diagnostics": {
                        "binary_path": "/opt/flow-parser-venv/bin/code2flow",
                        "stderr_excerpt": "generated graph without edges",
                        "edge_count": "0",
                        "node_count": "0",
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.callgraph_code2flow.subprocess.run",
        _fake_run,
    )

    graph = Code2FlowCallGraph(project_root=str(tmp_path), max_files=10)
    result = graph.generate()

    assert result.used_engine == "fallback"
    assert result.blocked_reasons == ["code2flow_no_edges"]
    assert "code2flow_not_installed" not in result.blocked_reasons
    assert result.diagnostics["binary_path"] == "/opt/flow-parser-venv/bin/code2flow"
    assert "generated graph without edges" in result.diagnostics["stderr_excerpt"]
    assert result.diagnostics["edge_count"] == "0"
    assert result.diagnostics["node_count"] == "0"


def test_code2flow_runtime_preserves_exec_failed_reason(monkeypatch, tmp_path):
    source_file = tmp_path / "demo.py"
    source_file.write_text("def caller():\n    callee()\n\ndef callee():\n    return 1\n", encoding="utf-8")

    def _fake_run(args, *, capture_output, text, check, timeout):
        _ = args, capture_output, text, check, timeout
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
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
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.callgraph_code2flow.subprocess.run",
        _fake_run,
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

    def _fake_run(args, *, capture_output, text, check, timeout):
        _ = args, capture_output, text, check, timeout
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "ok": False,
                    "edges": {},
                    "blocked_reasons": ["code2flow_not_installed"],
                    "used_engine": "fallback",
                    "diagnostics": {
                        "binary_path": "",
                        "error": "code2flow_binary_not_found",
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.callgraph_code2flow.subprocess.run",
        _fake_run,
    )

    graph = Code2FlowCallGraph(project_root=str(tmp_path), max_files=10)
    result = graph.generate()

    assert result.used_engine == "fallback"
    assert result.blocked_reasons == ["code2flow_not_installed"]
    assert result.diagnostics["error"] == "code2flow_binary_not_found"
