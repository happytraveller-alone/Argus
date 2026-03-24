"""PHPStan bootstrap scanner 单元测试。"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.agent.bootstrap import phpstan as phpstan_bootstrap
from app.services.agent.bootstrap.phpstan import PhpstanBootstrapScanner


def _prepare_phpstan_workspace(monkeypatch, tmp_path):
    workspace_dir = tmp_path / "scans" / "phpstan-bootstrap" / "task-1"
    project_dir = workspace_dir / "project"
    output_dir = workspace_dir / "output"
    logs_dir = workspace_dir / "logs"
    meta_dir = workspace_dir / "meta"
    monkeypatch.setattr(
        phpstan_bootstrap,
        "settings",
        SimpleNamespace(SCANNER_PHPSTAN_IMAGE="vulhunter/phpstan-runner:test"),
        raising=False,
    )
    monkeypatch.setattr(
        phpstan_bootstrap,
        "ensure_scan_workspace",
        lambda *_args, **_kwargs: workspace_dir,
        raising=False,
    )
    monkeypatch.setattr(
        phpstan_bootstrap,
        "ensure_scan_project_dir",
        lambda *_args, **_kwargs: project_dir,
        raising=False,
    )
    monkeypatch.setattr(
        phpstan_bootstrap,
        "ensure_scan_output_dir",
        lambda *_args, **_kwargs: output_dir,
        raising=False,
    )
    monkeypatch.setattr(
        phpstan_bootstrap,
        "ensure_scan_logs_dir",
        lambda *_args, **_kwargs: logs_dir,
        raising=False,
    )
    monkeypatch.setattr(
        phpstan_bootstrap,
        "ensure_scan_meta_dir",
        lambda *_args, **_kwargs: meta_dir,
        raising=False,
    )
    monkeypatch.setattr(
        phpstan_bootstrap.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("bootstrap phpstan scanner should not use subprocess.run")
        ),
    )
    return workspace_dir, project_dir, output_dir, logs_dir


@pytest.mark.asyncio
async def test_phpstan_bootstrap_scanner_parses_and_filters_security_findings(monkeypatch, tmp_path):
    workspace_dir, _project_dir, output_dir, _logs_dir = _prepare_phpstan_workspace(
        monkeypatch,
        tmp_path,
    )
    seen = {}

    async def _fake_run_scanner_container(spec, **_kwargs):
        seen["spec"] = spec
        output_dir.mkdir(parents=True, exist_ok=True)
        Path(output_dir / "report.json").write_text(
            """{
              "files": {
                "/scan/project/src/a.php": {
                  "messages": [
                    {
                      "message": "User input reaches eval() and may cause code execution.",
                      "line": 12,
                      "identifier": "security.eval",
                      "tip": "Avoid eval"
                    },
                    {
                      "message": "Call to undefined variable $foo.",
                      "line": 20,
                      "identifier": "variable.undefined"
                    }
                  ]
                }
              }
            }""",
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=False,
            container_id="phpstan-bootstrap-1",
            exit_code=1,
            stdout_path=None,
            stderr_path=None,
            error="scanner container exited with code 1",
        )

    monkeypatch.setattr(
        phpstan_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = PhpstanBootstrapScanner(level=8, timeout_seconds=30)
    result = await scanner.scan(str(tmp_path))

    assert result.scanner_name == "phpstan"
    assert result.source == "phpstan_bootstrap"
    assert result.total_findings == 2
    assert len(result.findings) == 1
    finding = result.findings[0]
    assert finding.severity == "ERROR"
    assert finding.confidence == "MEDIUM"
    assert finding.vulnerability_type == "security.eval"
    assert finding.file_path == "src/a.php"
    assert finding.line_start == 12
    assert finding.extra.get("phpstan_identifier") == "security.eval"
    assert seen["spec"].image == "vulhunter/phpstan-runner:test"
    assert seen["spec"].workspace_dir == str(workspace_dir)
    assert seen["spec"].command[:2] == ["/bin/sh", "-lc"]
    assert "/scan/output/report.json" in seen["spec"].command[2]


@pytest.mark.asyncio
async def test_phpstan_bootstrap_scanner_supports_stdout_noise(monkeypatch, tmp_path):
    _workspace_dir, _project_dir, output_dir, _logs_dir = _prepare_phpstan_workspace(
        monkeypatch,
        tmp_path,
    )

    async def _fake_run_scanner_container(_spec, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        Path(output_dir / "report.json").write_text(
            """NOTICE...
            {"files":{"src/a.php":{"messages":[{"message":"Potential XSS injection sink.","line":3}]}}}""",
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=False,
            container_id="phpstan-bootstrap-2",
            exit_code=1,
            stdout_path=None,
            stderr_path=None,
            error="scanner container exited with code 1",
        )

    monkeypatch.setattr(
        phpstan_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = PhpstanBootstrapScanner()
    result = await scanner.scan(str(tmp_path))
    assert result.total_findings == 1
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_phpstan_bootstrap_scanner_supports_stderr_payload_fallback(monkeypatch, tmp_path):
    _workspace_dir, _project_dir, _output_dir, logs_dir = _prepare_phpstan_workspace(
        monkeypatch,
        tmp_path,
    )

    async def _fake_run_scanner_container(_spec, **_kwargs):
        logs_dir.mkdir(parents=True, exist_ok=True)
        Path(logs_dir / "stdout.log").write_text("", encoding="utf-8")
        Path(logs_dir / "stderr.log").write_text(
            """{
              "files": {
                "/scan/project/src/a.php": {
                  "messages": [
                    {"message": "Possible command injection", "line": 9}
                  ]
                }
              }
            }""",
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=False,
            container_id="phpstan-bootstrap-3",
            exit_code=1,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error="scanner container exited with code 1",
        )

    monkeypatch.setattr(
        phpstan_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = PhpstanBootstrapScanner()
    result = await scanner.scan(str(tmp_path))
    assert result.total_findings == 1
    assert len(result.findings) == 1
    assert result.findings[0].file_path == "src/a.php"


@pytest.mark.asyncio
async def test_phpstan_bootstrap_scanner_raises_on_invalid_json(monkeypatch, tmp_path):
    _workspace_dir, _project_dir, output_dir, _logs_dir = _prepare_phpstan_workspace(
        monkeypatch,
        tmp_path,
    )

    async def _fake_run_scanner_container(_spec, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        Path(output_dir / "report.json").write_text("{invalid", encoding="utf-8")
        return SimpleNamespace(
            success=False,
            container_id="phpstan-bootstrap-4",
            exit_code=1,
            stdout_path=None,
            stderr_path=None,
            error="scanner container exited with code 1",
        )

    monkeypatch.setattr(
        phpstan_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = PhpstanBootstrapScanner()
    with pytest.raises(RuntimeError, match="phpstan output parse failed"):
        await scanner.scan(str(tmp_path))


def test_phpstan_bootstrap_parse_output_supports_bracket_noise_before_json():
    parsed = phpstan_bootstrap._parse_output(
        "[warning] bootstrap log\n{\"files\":{},\"totals\":{}}"
    )

    assert isinstance(parsed, dict)
    assert parsed.get("files") == {}


@pytest.mark.asyncio
async def test_phpstan_bootstrap_scanner_raises_when_failed_without_results(monkeypatch, tmp_path):
    _workspace_dir, _project_dir, _output_dir, logs_dir = _prepare_phpstan_workspace(
        monkeypatch,
        tmp_path,
    )

    async def _fake_run_scanner_container(_spec, **_kwargs):
        logs_dir.mkdir(parents=True, exist_ok=True)
        Path(logs_dir / "stdout.log").write_text("", encoding="utf-8")
        Path(logs_dir / "stderr.log").write_text("phpstan command error", encoding="utf-8")
        return SimpleNamespace(
            success=False,
            container_id="phpstan-bootstrap-5",
            exit_code=2,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error="scanner container exited with code 2",
        )

    monkeypatch.setattr(
        phpstan_bootstrap,
        "run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    scanner = PhpstanBootstrapScanner()
    with pytest.raises(RuntimeError, match="phpstan failed"):
        await scanner.scan(str(tmp_path))
