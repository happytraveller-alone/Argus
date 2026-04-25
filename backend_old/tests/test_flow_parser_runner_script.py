import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
SCRIPT_PATH = PROJECT_ROOT / "backend" / "scripts" / "flow_parser_runner.py"
HOST_PATH = PROJECT_ROOT / "backend" / "scripts" / "flow_parser_host.py"


def _load_flow_parser_runner_module():
    temp_root = tempfile.mkdtemp(prefix="flow-parser-runner-test-")
    runtime_root = Path(temp_root)
    (runtime_root / "flow_parser_runner.py").write_text(
        SCRIPT_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (runtime_root / "flow_parser_host.py").write_text(
        HOST_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    spec = importlib.util.spec_from_file_location(
        "test_flow_parser_runner_script_module",
        runtime_root / "flow_parser_runner.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_flow_parser_runner_module_loads_non_legacy_host_artifact():
    module = _load_flow_parser_runner_module()
    assert module.TreeSitterParser is not None


def test_extract_definitions_batch_uses_non_legacy_host_parser(monkeypatch):
    module = _load_flow_parser_runner_module()

    class FakeParser:
        def parse(self, content, language):
            assert language == "python"
            assert "demo" in content
            return object()

        def extract_definitions(self, tree, content, language):
            assert tree is not None
            return [
                {
                    "name": "demo",
                    "type": "function",
                    "start_point": [0, 0],
                    "end_point": [2, 0],
                    "language": language,
                }
            ]

    monkeypatch.setattr(module, "TreeSitterParser", FakeParser)

    result = module._extract_definitions_batch(
        {
            "items": [
                {
                    "file_path": "demo.py",
                    "language": "python",
                    "content": "def demo():\n    return 1\n",
                }
            ]
        }
    )

    assert result["items"][0]["ok"] is True
    assert result["items"][0]["definitions"][0]["name"] == "demo"
    assert "runner_tree_sitter" in result["items"][0]["diagnostics"]


def test_locate_enclosing_function_uses_non_legacy_host_parser(monkeypatch):
    module = _load_flow_parser_runner_module()

    class FakeParser:
        def parse(self, content, language):
            assert language == "python"
            return object()

        def extract_definitions(self, tree, content, language):
            return [
                {
                    "name": "demo",
                    "type": "function",
                    "start_point": [0, 0],
                    "end_point": [2, 0],
                    "language": language,
                }
            ]

    monkeypatch.setattr(module, "TreeSitterParser", FakeParser)

    result = module._locate_enclosing_function(
        {
            "file_path": "demo.py",
            "language": "python",
            "content": "def demo():\n    print('x')\n    return 1\n",
            "line_start": 2,
        }
    )

    assert result["ok"] is True
    assert result["function"] == "demo"
    assert result["resolution_engine"] == "python_tree_sitter"
    assert result["start_line"] == 1
    assert result["end_line"] == 3


def test_code2flow_callgraph_reports_binary_probe_details_when_missing(monkeypatch):
    module = _load_flow_parser_runner_module()
    monkeypatch.setattr(module.shutil, "which", lambda name: None)

    result = module._code2flow_callgraph(
        {"files": [{"file_path": "demo.py", "content": "def caller():\n    callee()\n"}]}
    )

    assert result["ok"] is False
    assert result["blocked_reasons"] == ["code2flow_not_installed"]
    assert "binary_path" in result["diagnostics"]
    assert "probe_command" in result["diagnostics"]


def test_code2flow_callgraph_reports_exec_failed_diagnostics(monkeypatch):
    module = _load_flow_parser_runner_module()
    monkeypatch.setattr(module.shutil, "which", lambda name: "/opt/flow-parser-venv/bin/code2flow")

    def _fake_run(cmd, cwd, capture_output, text, timeout):
        _ = cwd, capture_output, text, timeout
        return SimpleNamespace(returncode=1, stdout="", stderr=f"failed: {' '.join(cmd)}")

    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    result = module._code2flow_callgraph(
        {"files": [{"file_path": "demo.py", "content": "def caller():\n    callee()\n"}]}
    )

    assert result["ok"] is False
    assert result["blocked_reasons"] == ["code2flow_exec_failed"]
    assert result["diagnostics"]["binary_path"] == "/opt/flow-parser-venv/bin/code2flow"
    assert result["diagnostics"]["probe_command"].startswith("/opt/flow-parser-venv/bin/code2flow")
    assert "failed:" in result["diagnostics"]["stderr_excerpt"]


def test_code2flow_callgraph_reports_no_edges_without_relabeling(monkeypatch):
    module = _load_flow_parser_runner_module()
    monkeypatch.setattr(module.shutil, "which", lambda name: "/opt/flow-parser-venv/bin/code2flow")

    def _fake_run(cmd, cwd, capture_output, text, timeout):
        _ = capture_output, text, timeout
        Path(cwd, "graph.dot").write_text("digraph G {}\n", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr=f"ran: {' '.join(cmd)}")

    monkeypatch.setattr(module.subprocess, "run", _fake_run)

    result = module._code2flow_callgraph(
        {"files": [{"file_path": "demo.py", "content": "def caller():\n    callee()\n"}]}
    )

    assert result["ok"] is False
    assert result["blocked_reasons"] == ["code2flow_no_edges"]
    assert result["diagnostics"]["binary_path"] == "/opt/flow-parser-venv/bin/code2flow"
    assert "ran:" in result["diagnostics"]["stderr_excerpt"]
