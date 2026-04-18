import json
import subprocess
import tempfile
from pathlib import Path

from app.core.config import settings
from app.services.agent.core.flow.lightweight.flow_parser_runtime import FlowParserRuntimeBridge


def test_flow_parser_runtime_bridge_writes_request_and_reads_response(monkeypatch, tmp_path):
    seen = {}

    def _fake_run(args, *, capture_output, text, check, timeout):
        assert capture_output is True
        assert text is True
        assert check is False
        seen["args"] = list(args)
        seen["timeout"] = timeout
        request_path = Path(args[4])
        seen["request"] = json.loads(request_path.read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "items": [
                        {
                            "file_path": "demo.py",
                            "ok": True,
                            "definitions": [{"name": "target"}],
                            "diagnostics": ["runner_ok"],
                            "error": None,
                        }
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.flow_parser_runtime.subprocess.run",
        _fake_run,
    )
    monkeypatch.setattr(settings, "SCAN_WORKSPACE_ROOT", str(tmp_path / "shared-scans"))

    bridge = FlowParserRuntimeBridge(
        image="vulhunter/flow-parser-runner-local:latest",
        enabled=True,
        timeout_seconds=45,
    )
    results = bridge.extract_definitions_batch(
        [
            {
                "file_path": "demo.py",
                "language": "python",
                "content": "def target(value):\n    return value + 1\n",
            }
        ]
    )

    assert seen["args"][1:4] == ["flow-parser", "definitions-batch", "--request"]
    assert seen["timeout"] == 45
    assert seen["request"] == {
        "items": [
            {
                "file_path": "demo.py",
                "language": "python",
                "content": "def target(value):\n    return value + 1\n",
            }
        ],
        "image": "vulhunter/flow-parser-runner-local:latest",
        "timeout_seconds": 45,
    }
    assert results["demo.py"]["ok"] is True
    assert results["demo.py"]["diagnostics"] == ["runner_ok"]


def test_flow_parser_runtime_bridge_prefers_scan_workspace_root_and_falls_back(monkeypatch, tmp_path):
    shared_root = tmp_path / "shared-scans"
    shared_root.mkdir()
    original_tempdir = tempfile.TemporaryDirectory
    seen = {"request_paths": []}

    class _TemporaryDirectoryWithPermissionFallback:
        attempts = []

        def __init__(self, *args, **kwargs):
            self.attempts.append(dict(kwargs))
            if kwargs.get("dir"):
                raise PermissionError("workspace root not writable")
            self._wrapped = original_tempdir(*args, **kwargs)

        def __enter__(self):
            return self._wrapped.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self._wrapped.__exit__(exc_type, exc, tb)

    def _fake_run(args, *, capture_output, text, check, timeout):
        _ = capture_output, text, check, timeout
        seen["request_paths"].append(Path(args[4]))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout='{"items":[]}', stderr="")

    monkeypatch.setattr(settings, "SCAN_WORKSPACE_ROOT", str(shared_root))
    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.flow_parser_runtime.tempfile.TemporaryDirectory",
        _TemporaryDirectoryWithPermissionFallback,
    )
    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.flow_parser_runtime.subprocess.run",
        _fake_run,
    )

    bridge = FlowParserRuntimeBridge(enabled=True)
    results = bridge.extract_definitions_batch(
        [{"file_path": "demo.py", "language": "python", "content": "def target():\n    pass\n"}]
    )

    assert results == {}
    assert _TemporaryDirectoryWithPermissionFallback.attempts[0]["dir"] == str(shared_root / "flow-parser-runtime")
    assert "dir" not in _TemporaryDirectoryWithPermissionFallback.attempts[1]
    assert seen["request_paths"][0].is_relative_to(shared_root) is False


def test_flow_parser_runtime_bridge_maps_missing_binary_to_none(monkeypatch):
    def _fake_run(*args, **kwargs):
        _ = args, kwargs
        raise OSError("backend runtime startup missing")

    monkeypatch.setattr(
        "app.services.agent.core.flow.lightweight.flow_parser_runtime.subprocess.run",
        _fake_run,
    )

    bridge = FlowParserRuntimeBridge(enabled=True)

    assert bridge.locate_enclosing_function(
        file_path="demo.py",
        line_start=2,
        language="python",
        content="def target(value):\n    return value + 1\n",
    ) is None
