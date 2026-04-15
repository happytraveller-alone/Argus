from pathlib import Path
from types import SimpleNamespace

import pytest

import app.services.agent.bootstrap.opengrep as opengrep_bootstrap
from app.services.agent.bootstrap.opengrep import OpenGrepBootstrapScanner


def _prepare_opengrep_workspace(monkeypatch, tmp_path):
    workspace_dir = tmp_path / "scans" / "opengrep-bootstrap" / "task-1"
    project_dir = workspace_dir / "project"
    output_dir = workspace_dir / "output"
    logs_dir = workspace_dir / "logs"
    meta_dir = workspace_dir / "meta"
    monkeypatch.setattr(
        opengrep_bootstrap,
        "settings",
        SimpleNamespace(SCANNER_OPENGREP_IMAGE="vulhunter/opengrep-runner:test"),
        raising=False,
    )
    monkeypatch.setattr(
        opengrep_bootstrap,
        "ensure_scan_workspace",
        lambda *_args, **_kwargs: workspace_dir,
        raising=False,
    )
    monkeypatch.setattr(
        opengrep_bootstrap,
        "ensure_scan_project_dir",
        lambda *_args, **_kwargs: project_dir,
        raising=False,
    )
    monkeypatch.setattr(
        opengrep_bootstrap,
        "ensure_scan_output_dir",
        lambda *_args, **_kwargs: output_dir,
        raising=False,
    )
    monkeypatch.setattr(
        opengrep_bootstrap,
        "ensure_scan_logs_dir",
        lambda *_args, **_kwargs: logs_dir,
        raising=False,
    )
    monkeypatch.setattr(
        opengrep_bootstrap,
        "ensure_scan_meta_dir",
        lambda *_args, **_kwargs: meta_dir,
        raising=False,
    )
    monkeypatch.setattr(
        opengrep_bootstrap.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("bootstrap opengrep scanner should not use subprocess.run")
        ),
    )
    return workspace_dir, project_dir, output_dir, logs_dir, meta_dir


@pytest.mark.asyncio
async def test_opengrep_bootstrap_scanner_uses_runner_and_normalizes_findings(monkeypatch, tmp_path):
    workspace_dir, _project_dir, output_dir, _logs_dir, _meta_dir = _prepare_opengrep_workspace(
        monkeypatch,
        tmp_path,
    )
    active_rules = [
        SimpleNamespace(
            id="rule-1",
            name="demo.rule",
            confidence="HIGH",
            pattern_yaml="rules:\n  - id: demo.rule\n    languages: [python]\n    pattern: dangerous(...)",
        )
    ]
    seen = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        output_dir.mkdir(parents=True, exist_ok=True)
        Path(output_dir / "report.json").write_text(
            """{
              "results": [
                {
                  "check_id": "demo.rule",
                  "path": "/scan/project/src/a.py",
                  "start": {"line": 7},
                  "end": {"line": 7},
                  "extra": {
                    "message": "dangerous call",
                    "severity": "ERROR",
                    "lines": "dangerous()"
                  }
                }
              ]
            }""",
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=True,
            container_id="opengrep-bootstrap-1",
            exit_code=0,
            stdout_path=None,
            stderr_path=None,
            error=None,
        )

    monkeypatch.setattr(
        opengrep_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = OpenGrepBootstrapScanner(active_rules=active_rules, timeout_seconds=60)
    result = await scanner.scan(str(tmp_path))

    assert result.scanner_name == "opengrep"
    assert result.source == "opengrep_bootstrap"
    assert result.total_findings == 1
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.file_path == "src/a.py"
    assert finding.confidence == "HIGH"
    assert finding.severity == "ERROR"
    assert seen["spec"].image == "vulhunter/opengrep-runner:test"
    assert seen["spec"].workspace_dir == str(workspace_dir)
    assert seen["spec"].command[:2] == ["opengrep", "--config"]
    assert seen["spec"].command[-2:] == ["--json", "/scan/project"]
    assert seen["spec"].command[2].startswith("/scan/meta/")
    assert seen["spec"].capture_stdout_path == "output/report.json"


@pytest.mark.asyncio
async def test_opengrep_bootstrap_scanner_raises_when_failed_without_results(monkeypatch, tmp_path):
    _workspace_dir, _project_dir, _output_dir, logs_dir, _meta_dir = _prepare_opengrep_workspace(
        monkeypatch,
        tmp_path,
    )
    active_rules = [
        SimpleNamespace(
            id="rule-1",
            name="demo.rule",
            confidence="HIGH",
            pattern_yaml="rules:\n  - id: demo.rule\n    languages: [python]\n    pattern: dangerous(...)",
        )
    ]

    async def _fake_run_scanner_container(_spec, **_kwargs):
        logs_dir.mkdir(parents=True, exist_ok=True)
        Path(logs_dir / "stdout.log").write_text("", encoding="utf-8")
        Path(logs_dir / "stderr.log").write_text("opengrep command error", encoding="utf-8")
        return SimpleNamespace(
            success=False,
            container_id="opengrep-bootstrap-2",
            exit_code=2,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error="scanner container exited with code 2",
        )

    monkeypatch.setattr(
        opengrep_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = OpenGrepBootstrapScanner(active_rules=active_rules)
    with pytest.raises(RuntimeError, match="opengrep failed"):
        await scanner.scan(str(tmp_path))


@pytest.mark.asyncio
async def test_opengrep_bootstrap_scanner_raises_when_no_executable_rules():
    scanner = OpenGrepBootstrapScanner(active_rules=[])
    with pytest.raises(ValueError, match="No executable opengrep rules found"):
        await scanner.scan("/tmp/project")
