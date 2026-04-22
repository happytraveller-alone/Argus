import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
SCRIPT_PATH = PROJECT_ROOT / "backend" / "scripts" / "flow_parser_runner.py"


def _load_flow_parser_runner_module():
    temp_root = tempfile.mkdtemp(prefix="flow-parser-runner-test-")
    runtime_root = Path(temp_root)
    (runtime_root / "app" / "services" / "rag").mkdir(parents=True, exist_ok=True)
    (runtime_root / "flow_parser_runner.py").write_text(
        SCRIPT_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (runtime_root / "app" / "services" / "parser.py").write_text(
        "class TreeSitterParser:\n"
        "    def parse(self, content, language):\n"
        "        return None\n"
        "    def extract_definitions(self, tree, content, language):\n"
        "        return []\n",
        encoding="utf-8",
    )
    (runtime_root / "app" / "services" / "rag" / "splitter.py").write_text(
        "class TreeSitterParser:\n"
        "    def parse(self, content, language):\n"
        "        return None\n"
        "    def extract_definitions(self, tree, content, language):\n"
        "        return []\n",
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
