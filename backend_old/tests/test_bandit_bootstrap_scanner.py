from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.agent.bootstrap import bandit as bandit_bootstrap
from app.services.agent.bootstrap.bandit import BanditBootstrapScanner


def _prepare_bandit_workspace(monkeypatch, tmp_path):
    workspace_dir = tmp_path / "scans" / "bandit-bootstrap" / "task-1"
    project_dir = workspace_dir / "project"
    output_dir = workspace_dir / "output"
    logs_dir = workspace_dir / "logs"
    meta_dir = workspace_dir / "meta"
    monkeypatch.setattr(
        bandit_bootstrap,
        "settings",
        SimpleNamespace(SCANNER_BANDIT_IMAGE="vulhunter/bandit-runner:test"),
        raising=False,
    )
    monkeypatch.setattr(
        bandit_bootstrap,
        "ensure_scan_workspace",
        lambda *_args, **_kwargs: workspace_dir,
        raising=False,
    )
    monkeypatch.setattr(
        bandit_bootstrap,
        "ensure_scan_project_dir",
        lambda *_args, **_kwargs: project_dir,
        raising=False,
    )
    monkeypatch.setattr(
        bandit_bootstrap,
        "ensure_scan_output_dir",
        lambda *_args, **_kwargs: output_dir,
        raising=False,
    )
    monkeypatch.setattr(
        bandit_bootstrap,
        "ensure_scan_logs_dir",
        lambda *_args, **_kwargs: logs_dir,
        raising=False,
    )
    monkeypatch.setattr(
        bandit_bootstrap,
        "ensure_scan_meta_dir",
        lambda *_args, **_kwargs: meta_dir,
        raising=False,
    )
    monkeypatch.setattr(
        bandit_bootstrap.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("bootstrap bandit scanner should not use subprocess.run")
        ),
    )
    return workspace_dir, project_dir, output_dir, logs_dir


@pytest.mark.asyncio
async def test_bandit_bootstrap_scanner_uses_runner_and_normalizes_findings(monkeypatch, tmp_path):
    workspace_dir, _project_dir, output_dir, logs_dir = _prepare_bandit_workspace(
        monkeypatch,
        tmp_path,
    )
    seen = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text(
            """{
              "results": [
                {
                  "test_id": "B105",
                  "test_name": "hardcoded_password_string",
                  "issue_text": "Possible hardcoded password",
                  "issue_severity": "HIGH",
                  "issue_confidence": "HIGH",
                  "filename": "/scan/project/src/a.py",
                  "line_number": 9,
                  "code": "password = 'secret'"
                },
                {
                  "test_id": "B101",
                  "issue_text": "assert used",
                  "issue_severity": "LOW",
                  "issue_confidence": "LOW",
                  "filename": "/scan/project/src/a.py",
                  "line_number": 12
                }
              ]
            }""",
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=True,
            container_id="bandit-bootstrap-1",
            exit_code=1,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error="scanner container exited with code 1",
        )

    monkeypatch.setattr(
        bandit_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = BanditBootstrapScanner(timeout_seconds=30, rule_ids=["B105", "B101"])
    result = await scanner.scan(str(tmp_path))

    assert result.scanner_name == "bandit"
    assert result.source == "bandit_bootstrap"
    assert result.total_findings == 2
    assert len(result.findings) == 2
    assert result.findings[0].severity == "ERROR"
    assert result.findings[0].confidence == "HIGH"
    assert result.findings[0].file_path == "src/a.py"
    assert result.findings[1].severity == "WARNING"
    assert result.findings[1].confidence == "LOW"
    assert seen["spec"].image == "vulhunter/bandit-runner:test"
    assert seen["spec"].workspace_dir == str(workspace_dir)
    assert seen["spec"].command[0] == "bandit"
    assert seen["spec"].command[seen["spec"].command.index("-o") + 1] == "/scan/output/report.json"
    assert "-t" in seen["spec"].command
    assert seen["spec"].command[seen["spec"].command.index("-t") + 1] == "B105,B101"


@pytest.mark.asyncio
async def test_bandit_bootstrap_scanner_raises_on_invalid_json(monkeypatch, tmp_path):
    _workspace_dir, _project_dir, output_dir, logs_dir = _prepare_bandit_workspace(
        monkeypatch,
        tmp_path,
    )

    async def _fake_run_scanner_container(_spec, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text("{invalid", encoding="utf-8")
        return SimpleNamespace(
            success=True,
            container_id="bandit-bootstrap-2",
            exit_code=0,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error=None,
        )

    monkeypatch.setattr(
        bandit_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = BanditBootstrapScanner()
    with pytest.raises(RuntimeError, match="bandit output parse failed"):
        await scanner.scan(str(tmp_path))


@pytest.mark.asyncio
async def test_bandit_bootstrap_scanner_raises_when_failed_without_results(monkeypatch, tmp_path):
    _workspace_dir, _project_dir, _output_dir, logs_dir = _prepare_bandit_workspace(
        monkeypatch,
        tmp_path,
    )

    async def _fake_run_scanner_container(_spec, **_kwargs):
        logs_dir.mkdir(parents=True, exist_ok=True)
        Path(logs_dir / "stderr.log").write_text("bandit command error", encoding="utf-8")
        return SimpleNamespace(
            success=False,
            container_id="bandit-bootstrap-3",
            exit_code=2,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error="scanner container exited with code 2",
        )

    monkeypatch.setattr(
        bandit_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = BanditBootstrapScanner()
    with pytest.raises(RuntimeError, match="bandit failed"):
        await scanner.scan(str(tmp_path))


@pytest.mark.asyncio
async def test_bandit_bootstrap_scanner_supports_stderr_payload_fallback(monkeypatch, tmp_path):
    _workspace_dir, _project_dir, _output_dir, logs_dir = _prepare_bandit_workspace(
        monkeypatch,
        tmp_path,
    )

    async def _fake_run_scanner_container(_spec, **_kwargs):
        logs_dir.mkdir(parents=True, exist_ok=True)
        Path(logs_dir / "stdout.log").write_text("", encoding="utf-8")
        Path(logs_dir / "stderr.log").write_text(
            """{
              "results": [
                {
                  "test_id": "B105",
                  "issue_text": "Possible hardcoded password",
                  "issue_severity": "HIGH",
                  "issue_confidence": "MEDIUM",
                  "filename": "/scan/project/src/a.py",
                  "line_number": 9
                }
              ]
            }""",
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=False,
            container_id="bandit-bootstrap-4",
            exit_code=1,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error="scanner container exited with code 1",
        )

    monkeypatch.setattr(
        bandit_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = BanditBootstrapScanner()
    result = await scanner.scan(str(tmp_path))
    assert result.total_findings == 1
    assert len(result.findings) == 1
    assert result.findings[0].severity == "ERROR"
    assert result.findings[0].confidence == "MEDIUM"


@pytest.mark.asyncio
async def test_bandit_bootstrap_scanner_without_rule_ids_keeps_original_command(monkeypatch, tmp_path):
    workspace_dir, _project_dir, output_dir, logs_dir = _prepare_bandit_workspace(
        monkeypatch,
        tmp_path,
    )
    seen = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "report.json").write_text('{"results":[]}', encoding="utf-8")
        return SimpleNamespace(
            success=True,
            container_id="bandit-bootstrap-5",
            exit_code=0,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error=None,
        )

    monkeypatch.setattr(
        bandit_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = BanditBootstrapScanner()
    result = await scanner.scan(str(tmp_path))

    assert result.total_findings == 0
    assert seen["spec"].workspace_dir == str(workspace_dir)
    assert "-t" not in seen["spec"].command
