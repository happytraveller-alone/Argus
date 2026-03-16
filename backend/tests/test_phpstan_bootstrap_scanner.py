"""PHPStan bootstrap scanner 单元测试。"""

from types import SimpleNamespace

import pytest

from app.services.agent.bootstrap.phpstan import PhpstanBootstrapScanner


@pytest.mark.asyncio
async def test_phpstan_bootstrap_scanner_parses_and_filters_security_findings(monkeypatch):
    stdout_payload = """{
      "files": {
        "src/a.php": {
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
    }"""

    def _fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout=stdout_payload, stderr="")

    monkeypatch.setattr(
        "app.services.agent.bootstrap.phpstan.subprocess.run",
        _fake_run,
    )

    scanner = PhpstanBootstrapScanner(level=8, timeout_seconds=30)
    result = await scanner.scan("/tmp/project")

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


@pytest.mark.asyncio
async def test_phpstan_bootstrap_scanner_supports_stdout_noise(monkeypatch):
    stdout_payload = """NOTICE...
    {"files":{"src/a.php":{"messages":[{"message":"Potential XSS injection sink.","line":3}]}}}"""

    def _fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout=stdout_payload, stderr="")

    monkeypatch.setattr(
        "app.services.agent.bootstrap.phpstan.subprocess.run",
        _fake_run,
    )

    scanner = PhpstanBootstrapScanner()
    result = await scanner.scan("/tmp/project")
    assert result.total_findings == 1
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_phpstan_bootstrap_scanner_supports_stderr_payload_fallback(monkeypatch):
    stderr_payload = """{
      "files": {
        "src/a.php": {
          "messages": [
            {"message": "Possible command injection", "line": 9}
          ]
        }
      }
    }"""

    def _fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr=stderr_payload)

    monkeypatch.setattr(
        "app.services.agent.bootstrap.phpstan.subprocess.run",
        _fake_run,
    )

    scanner = PhpstanBootstrapScanner()
    result = await scanner.scan("/tmp/project")
    assert result.total_findings == 1
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_phpstan_bootstrap_scanner_raises_on_invalid_json(monkeypatch):
    def _fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=1, stdout="{invalid", stderr="")

    monkeypatch.setattr(
        "app.services.agent.bootstrap.phpstan.subprocess.run",
        _fake_run,
    )

    scanner = PhpstanBootstrapScanner()
    with pytest.raises(RuntimeError, match="phpstan output parse failed"):
        await scanner.scan("/tmp/project")


@pytest.mark.asyncio
async def test_phpstan_bootstrap_scanner_raises_when_failed_without_results(monkeypatch):
    def _fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=2, stdout="", stderr="phpstan command error")

    monkeypatch.setattr(
        "app.services.agent.bootstrap.phpstan.subprocess.run",
        _fake_run,
    )

    scanner = PhpstanBootstrapScanner()
    with pytest.raises(RuntimeError, match="phpstan failed"):
        await scanner.scan("/tmp/project")
