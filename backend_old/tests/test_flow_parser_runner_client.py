from pathlib import Path
from types import SimpleNamespace

from app.core.config import settings
from app.services.agent.flow.flow_parser_runner import FlowParserRunnerClient


def test_flow_parser_runner_client_writes_request_and_reads_response(monkeypatch, tmp_path):
    seen = {}
    shared_root = tmp_path / "shared-scans"
    shared_root.mkdir()

    async def _fake_run(spec, **kwargs):
        seen["spec"] = spec
        workspace = Path(spec.workspace_dir)
        request_path = workspace / "request.json"
        response_path = workspace / "response.json"
        assert request_path.exists()
        assert "definitions-batch" in spec.command
        response_path.write_text(
            '{"items":[{"file_path":"demo.py","ok":true,"definitions":[{"type":"function","name":"target","parent_name":null,"start_point":[0,0],"end_point":[1,0],"start_byte":0,"end_byte":28,"node_type":"function_definition"}],"diagnostics":["runner_ok"],"error":null}]}',
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=True,
            container_id="runner-123",
            exit_code=0,
            stdout_path=None,
            stderr_path=None,
            error=None,
        )

    monkeypatch.setattr(
        "app.services.agent.flow.flow_parser_runner.run_scanner_container",
        _fake_run,
    )
    monkeypatch.setattr(settings, "SCAN_WORKSPACE_ROOT", str(shared_root))

    client = FlowParserRunnerClient(
        image="vulhunter/flow-parser-runner-local:latest",
        enabled=True,
        timeout_seconds=45,
    )
    results = client.extract_definitions_batch(
        [
            {
                "file_path": "demo.py",
                "language": "python",
                "content": "def target(value):\n    return value + 1\n",
            }
        ]
    )

    assert seen["spec"].image == "vulhunter/flow-parser-runner-local:latest"
    assert results["demo.py"]["ok"] is True
    assert results["demo.py"]["definitions"][0]["name"] == "target"
    assert results["demo.py"]["diagnostics"] == ["runner_ok"]


def test_flow_parser_runner_client_uses_scan_workspace_root_for_bind_mount(monkeypatch, tmp_path):
    seen = {}
    shared_root = tmp_path / "shared-scans"
    shared_root.mkdir()

    async def _fake_run(spec, **kwargs):
        seen["spec"] = spec
        workspace = Path(spec.workspace_dir)
        request_path = workspace / "request.json"
        response_path = workspace / "response.json"
        assert request_path.exists()
        assert workspace.is_relative_to(shared_root)
        response_path.write_text('{"items":[]}', encoding="utf-8")
        return SimpleNamespace(
            success=True,
            container_id="runner-456",
            exit_code=0,
            stdout_path=None,
            stderr_path=None,
            error=None,
        )

    monkeypatch.setattr(settings, "SCAN_WORKSPACE_ROOT", str(shared_root))
    monkeypatch.setattr(
        "app.services.agent.flow.flow_parser_runner.run_scanner_container",
        _fake_run,
    )

    client = FlowParserRunnerClient(enabled=True)
    client.extract_definitions_batch(
        [
            {
                "file_path": "demo.py",
                "language": "python",
                "content": "def target(value):\n    return value + 1\n",
            }
        ]
    )

    assert Path(seen["spec"].workspace_dir).is_relative_to(shared_root)


def test_flow_parser_runner_client_falls_back_to_system_tempdir_when_workspace_root_unwritable(
    monkeypatch,
    tmp_path,
):
    seen = {}
    original_tempdir = __import__("tempfile").TemporaryDirectory
    shared_root = tmp_path / "shared-scans"
    shared_root.mkdir()

    class _TemporaryDirectoryWithPermissionFallback:
        def __init__(self, *args, **kwargs):
            if kwargs.get("dir"):
                raise PermissionError("workspace root not writable")
            self._wrapped = original_tempdir(*args, **kwargs)

        def __enter__(self):
            return self._wrapped.__enter__()

        def __exit__(self, exc_type, exc, tb):
            return self._wrapped.__exit__(exc_type, exc, tb)

    async def _fake_run(spec, **kwargs):
        seen["spec"] = spec
        workspace = Path(spec.workspace_dir)
        response_path = workspace / "response.json"
        response_path.write_text('{"items":[]}', encoding="utf-8")
        return SimpleNamespace(
            success=True,
            container_id="runner-789",
            exit_code=0,
            stdout_path=None,
            stderr_path=None,
            error=None,
        )

    monkeypatch.setattr(settings, "SCAN_WORKSPACE_ROOT", str(shared_root))
    monkeypatch.setattr(
        "app.services.agent.flow.flow_parser_runner.tempfile.TemporaryDirectory",
        _TemporaryDirectoryWithPermissionFallback,
    )
    monkeypatch.setattr(
        "app.services.agent.flow.flow_parser_runner.run_scanner_container",
        _fake_run,
    )

    client = FlowParserRunnerClient(enabled=True)
    results = client.extract_definitions_batch(
        [
            {
                "file_path": "demo.py",
                "language": "python",
                "content": "def target(value):\n    return value + 1\n",
            }
        ]
    )

    assert results == {}
    assert Path(seen["spec"].workspace_dir).is_relative_to(shared_root) is False
