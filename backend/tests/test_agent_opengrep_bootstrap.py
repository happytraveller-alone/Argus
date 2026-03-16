import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import (
    _filter_bootstrap_findings,
    _prepare_embedded_bootstrap_findings,
    _run_bootstrap_gitleaks_scan,
    _resolve_static_bootstrap_config,
)
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_opengrep_only_no_static_task_record(
    monkeypatch,
):
    active_rules = [SimpleNamespace(id="rule-1", pattern_yaml="rules: []", confidence="HIGH")]
    parsed_findings = [
        {
            "id": "rule-1",
            "title": "danger",
            "description": "danger",
            "file_path": "src/a.py",
            "line_start": 6,
            "line_end": 6,
            "code_snippet": "danger()",
            "severity": "ERROR",
            "confidence": "HIGH",
            "vulnerability_type": "rule-1",
            "source": "opengrep_bootstrap",
        },
    ]

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarListResult(active_rules))

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.OpenGrepBootstrapScanner.scan",
        AsyncMock(
            return_value=SimpleNamespace(
                total_findings=len(parsed_findings),
                findings=parsed_findings,
            )
        ),
    )

    candidates, bootstrap_task_id, source = await _prepare_embedded_bootstrap_findings(
        db=db,
        project_root="/tmp/project",
        event_emitter=event_emitter,
        opengrep_enabled=True,
        gitleaks_enabled=False,
    )

    assert source == "embedded_opengrep"
    assert bootstrap_task_id is None
    assert len(candidates) == 1
    db.add.assert_not_called()
    db.commit.assert_not_awaited()

    event_emitter.emit_info.assert_awaited()
    last_info_call = event_emitter.emit_info.await_args_list[-1]
    metadata = last_info_call.kwargs.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("bootstrap") is True
    assert metadata.get("bootstrap_task_id") is None
    assert metadata.get("bootstrap_source") == "embedded_opengrep"
    assert metadata.get("bootstrap_total_findings") == 1
    assert metadata.get("bootstrap_candidate_count") == 1


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_with_gitleaks(monkeypatch):
    active_rules = [SimpleNamespace(id="rule-1", pattern_yaml="rules: []", confidence="MEDIUM")]
    parsed_opengrep = [
        {
            "id": "rule-1",
            "title": "danger",
            "description": "danger",
            "file_path": "src/a.py",
            "line_start": 10,
            "line_end": 10,
            "severity": "ERROR",
            "confidence": "MEDIUM",
            "vulnerability_type": "rule-1",
            "source": "opengrep_bootstrap",
        },
    ]
    parsed_gitleaks = [
        {
            "RuleID": "generic-api-key",
            "Description": "Potential API key",
            "File": "src/secret.ts",
            "StartLine": 3,
            "EndLine": 3,
            "Match": "apiKey = abc",
        },
    ]

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarListResult(active_rules))

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.OpenGrepBootstrapScanner.scan",
        AsyncMock(
            return_value=SimpleNamespace(
                total_findings=len(parsed_opengrep),
                findings=parsed_opengrep,
            )
        ),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks._run_bootstrap_gitleaks_scan",
        AsyncMock(return_value=parsed_gitleaks),
    )

    candidates, bootstrap_task_id, source = await _prepare_embedded_bootstrap_findings(
        db=db,
        project_root="/tmp/project",
        event_emitter=event_emitter,
        opengrep_enabled=True,
        gitleaks_enabled=True,
    )

    assert source == "embedded_opengrep_gitleaks"
    assert bootstrap_task_id is None
    assert len(candidates) == 2
    assert any(item.get("source") == "opengrep_bootstrap" for item in candidates)
    assert any(item.get("source") == "gitleaks_bootstrap" for item in candidates)

    last_info_call = event_emitter.emit_info.await_args_list[-1]
    metadata = last_info_call.kwargs.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("bootstrap_opengrep_total_findings") == 1
    assert metadata.get("bootstrap_gitleaks_total_findings") == 1
    assert metadata.get("bootstrap_candidate_count") == 2


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_no_active_rules_abort():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarListResult([]))

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await _prepare_embedded_bootstrap_findings(
            db=db,
            project_root="/tmp/project",
            event_emitter=event_emitter,
            opengrep_enabled=True,
            gitleaks_enabled=False,
        )

    assert "当前没有启用规则" in str(exc_info.value)
    event_emitter.emit_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_gitleaks_failed_abort(monkeypatch):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarListResult([]))

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks._run_bootstrap_gitleaks_scan",
        AsyncMock(side_effect=RuntimeError("gitleaks bootstrap failure")),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await _prepare_embedded_bootstrap_findings(
            db=db,
            project_root="/tmp/project",
            event_emitter=event_emitter,
            opengrep_enabled=False,
            gitleaks_enabled=True,
        )

    assert "Gitleaks 预处理失败" in str(exc_info.value)
    event_emitter.emit_error.assert_awaited()


@pytest.mark.asyncio
async def test_run_bootstrap_gitleaks_scan_parses_report(monkeypatch, tmp_path):
    parsed_gitleaks = [
        {
            "RuleID": "generic-api-key",
            "Description": "Potential API key",
            "File": "src/secret.ts",
            "StartLine": 3,
            "EndLine": 3,
            "Match": "apiKey = abc",
        },
    ]
    captured_cmd = {}

    def fake_run(cmd, capture_output, text, timeout):
        assert capture_output is True
        assert text is True
        assert timeout == 900
        captured_cmd["value"] = list(cmd)
        report_path = cmd[cmd.index("--report-path") + 1]
        with open(report_path, "w", encoding="utf-8") as report_file:
            json.dump(parsed_gitleaks, report_file)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.subprocess.run",
        fake_run,
    )

    findings = await _run_bootstrap_gitleaks_scan(str(tmp_path))

    assert findings == parsed_gitleaks
    assert captured_cmd["value"] == [
        "gitleaks",
        "detect",
        "--source",
        str(tmp_path),
        "--report-format",
        "json",
        "--report-path",
        captured_cmd["value"][7],
        "--exit-code",
        "0",
        "--no-git",
    ]


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_gitleaks_missing_binary_abort(monkeypatch):
    db = AsyncMock()

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("gitleaks not found")

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.subprocess.run",
        fake_run,
    )

    with pytest.raises(RuntimeError) as exc_info:
        await _prepare_embedded_bootstrap_findings(
            db=db,
            project_root="/tmp/project",
            event_emitter=event_emitter,
            opengrep_enabled=False,
            gitleaks_enabled=True,
        )

    assert "Gitleaks 预处理失败：未安装 gitleaks" in str(exc_info.value)
    event_emitter.emit_error.assert_awaited_once_with("Gitleaks 预处理失败：未安装 gitleaks")


def test_filter_bootstrap_findings_only_error_and_high_medium_confidence():
    raw = [
        {"id": "a", "severity": "ERROR", "confidence": "HIGH"},
        {"id": "b", "severity": "ERROR", "confidence": "MEDIUM"},
        {"id": "c", "severity": "ERROR", "confidence": "LOW"},
        {"id": "d", "severity": "WARNING", "confidence": "HIGH"},
        {"id": "e", "severity": "INFO", "confidence": "HIGH"},
        {"id": "f", "severity": "error", "confidence": "medium"},
    ]
    filtered = _filter_bootstrap_findings(raw)
    kept_ids = {item["id"] for item in filtered}
    assert kept_ids == {"a", "b", "f"}
    for item in filtered:
        assert item["severity"].upper() == "ERROR"
        assert item["confidence"] in {"HIGH", "MEDIUM"}


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_with_bandit_only(monkeypatch):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarListResult([]))

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.BanditBootstrapScanner.scan",
        AsyncMock(
            return_value=SimpleNamespace(
                total_findings=2,
                findings=[
                    {
                        "id": "bandit-0",
                        "title": "hardcoded password",
                        "description": "hardcoded password",
                        "file_path": "src/a.py",
                        "line_start": 8,
                        "line_end": 8,
                        "code_snippet": "password = 'secret'",
                        "severity": "ERROR",
                        "confidence": "HIGH",
                        "vulnerability_type": "B105",
                        "source": "bandit_bootstrap",
                    },
                    {
                        "id": "bandit-1",
                        "title": "low confidence sample",
                        "description": "low confidence sample",
                        "file_path": "src/a.py",
                        "line_start": 18,
                        "line_end": 18,
                        "code_snippet": "print('debug')",
                        "severity": "WARNING",
                        "confidence": "LOW",
                        "vulnerability_type": "B000",
                        "source": "bandit_bootstrap",
                    },
                ],
            )
        ),
    )

    candidates, bootstrap_task_id, source = await _prepare_embedded_bootstrap_findings(
        db=db,
        project_root="/tmp/project",
        event_emitter=event_emitter,
        opengrep_enabled=False,
        bandit_enabled=True,
        gitleaks_enabled=False,
    )

    assert bootstrap_task_id is None
    assert source == "embedded_bandit"
    assert len(candidates) == 1
    assert candidates[0]["source"] == "bandit_bootstrap"

    metadata = event_emitter.emit_info.await_args_list[-1].kwargs.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("bootstrap_bandit_total_findings") == 2
    assert metadata.get("bootstrap_bandit_candidate_count") == 1
    assert metadata.get("bootstrap_candidate_count") == 1


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_with_opengrep_and_bandit(monkeypatch):
    active_rules = [SimpleNamespace(id="rule-1", pattern_yaml="rules: []", confidence="HIGH")]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarListResult(active_rules))

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.OpenGrepBootstrapScanner.scan",
        AsyncMock(
            return_value=SimpleNamespace(
                total_findings=1,
                findings=[
                    {
                        "id": "og-1",
                        "title": "danger",
                        "description": "danger",
                        "file_path": "src/a.py",
                        "line_start": 6,
                        "line_end": 6,
                        "code_snippet": "danger()",
                        "severity": "ERROR",
                        "confidence": "HIGH",
                        "vulnerability_type": "rule-1",
                        "source": "opengrep_bootstrap",
                    }
                ],
            )
        ),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.BanditBootstrapScanner.scan",
        AsyncMock(
            return_value=SimpleNamespace(
                total_findings=1,
                findings=[
                    {
                        "id": "bandit-0",
                        "title": "hardcoded password",
                        "description": "hardcoded password",
                        "file_path": "src/b.py",
                        "line_start": 10,
                        "line_end": 10,
                        "code_snippet": "password = 'secret'",
                        "severity": "ERROR",
                        "confidence": "MEDIUM",
                        "vulnerability_type": "B105",
                        "source": "bandit_bootstrap",
                    }
                ],
            )
        ),
    )

    candidates, _, source = await _prepare_embedded_bootstrap_findings(
        db=db,
        project_root="/tmp/project",
        event_emitter=event_emitter,
        opengrep_enabled=True,
        bandit_enabled=True,
        gitleaks_enabled=False,
    )

    assert source == "embedded_opengrep_bandit"
    assert len(candidates) == 2
    assert {item["source"] for item in candidates} == {
        "opengrep_bootstrap",
        "bandit_bootstrap",
    }


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_with_phpstan_only(monkeypatch):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarListResult([]))

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.PhpstanBootstrapScanner.scan",
        AsyncMock(
            return_value=SimpleNamespace(
                total_findings=3,
                findings=[
                    {
                        "id": "phpstan-0",
                        "title": "security.eval",
                        "description": "eval sink",
                        "file_path": "src/a.php",
                        "line_start": 12,
                        "line_end": 12,
                        "code_snippet": "Avoid eval",
                        "severity": "ERROR",
                        "confidence": "MEDIUM",
                        "vulnerability_type": "security.eval",
                        "source": "phpstan_bootstrap",
                    }
                ],
            )
        ),
    )

    candidates, bootstrap_task_id, source = await _prepare_embedded_bootstrap_findings(
        db=db,
        project_root="/tmp/project",
        event_emitter=event_emitter,
        opengrep_enabled=False,
        bandit_enabled=False,
        gitleaks_enabled=False,
        phpstan_enabled=True,
    )

    assert bootstrap_task_id is None
    assert source == "embedded_phpstan"
    assert len(candidates) == 1
    assert candidates[0]["source"] == "phpstan_bootstrap"

    metadata = event_emitter.emit_info.await_args_list[-1].kwargs.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("bootstrap_phpstan_total_findings") == 3
    assert metadata.get("bootstrap_phpstan_candidate_count") == 1
    assert metadata.get("bootstrap_candidate_count") == 1


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_with_opengrep_and_phpstan(monkeypatch):
    active_rules = [SimpleNamespace(id="rule-1", pattern_yaml="rules: []", confidence="HIGH")]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarListResult(active_rules))

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.OpenGrepBootstrapScanner.scan",
        AsyncMock(
            return_value=SimpleNamespace(
                total_findings=1,
                findings=[
                    {
                        "id": "og-1",
                        "title": "danger",
                        "description": "danger",
                        "file_path": "src/a.py",
                        "line_start": 6,
                        "line_end": 6,
                        "code_snippet": "danger()",
                        "severity": "ERROR",
                        "confidence": "HIGH",
                        "vulnerability_type": "rule-1",
                        "source": "opengrep_bootstrap",
                    }
                ],
            )
        ),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks.PhpstanBootstrapScanner.scan",
        AsyncMock(
            return_value=SimpleNamespace(
                total_findings=2,
                findings=[
                    {
                        "id": "phpstan-0",
                        "title": "security.eval",
                        "description": "eval sink",
                        "file_path": "src/b.php",
                        "line_start": 10,
                        "line_end": 10,
                        "code_snippet": "Avoid eval",
                        "severity": "ERROR",
                        "confidence": "MEDIUM",
                        "vulnerability_type": "security.eval",
                        "source": "phpstan_bootstrap",
                    }
                ],
            )
        ),
    )

    candidates, _, source = await _prepare_embedded_bootstrap_findings(
        db=db,
        project_root="/tmp/project",
        event_emitter=event_emitter,
        opengrep_enabled=True,
        bandit_enabled=False,
        gitleaks_enabled=False,
        phpstan_enabled=True,
    )

    assert source == "embedded_opengrep_phpstan"
    assert len(candidates) == 2
    assert {item["source"] for item in candidates} == {
        "opengrep_bootstrap",
        "phpstan_bootstrap",
    }


def test_resolve_static_bootstrap_config_supports_phpstan():
    task = SimpleNamespace(
        audit_scope={
            "static_bootstrap": {
                "mode": "embedded",
                "opengrep_enabled": False,
                "bandit_enabled": True,
                "gitleaks_enabled": True,
                "phpstan_enabled": True,
            }
        }
    )
    config = _resolve_static_bootstrap_config(task, source_mode="hybrid")
    assert config == {
        "mode": "embedded",
        "opengrep_enabled": False,
        "bandit_enabled": True,
        "gitleaks_enabled": True,
        "phpstan_enabled": True,
    }

    disabled_task = SimpleNamespace(
        audit_scope={
            "static_bootstrap": {
                "mode": "disabled",
                "opengrep_enabled": True,
                "bandit_enabled": True,
                "gitleaks_enabled": True,
                "phpstan_enabled": True,
            }
        }
    )
    disabled_config = _resolve_static_bootstrap_config(disabled_task, source_mode="hybrid")
    assert disabled_config == {
        "mode": "disabled",
        "opengrep_enabled": False,
        "bandit_enabled": False,
        "gitleaks_enabled": False,
        "phpstan_enabled": False,
    }
