import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.agent_tasks import (
    _filter_bootstrap_findings,
    _prepare_embedded_bootstrap_findings,
    _resolve_bandit_bootstrap_rule_ids,
    _resolve_bandit_effective_rule_ids_for_bootstrap,
    _run_bootstrap_gitleaks_scan,
    _resolve_static_bootstrap_config,
)
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401
from app.models.yasa import YasaRuleConfig


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _ScalarOneResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


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
        "app.api.v1.endpoints.agent_tasks_bootstrap._run_bootstrap_gitleaks_scan",
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
        "app.api.v1.endpoints.agent_tasks_bootstrap._run_bootstrap_gitleaks_scan",
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
    workspace_dir = tmp_path / "scans" / "gitleaks-bootstrap" / "task-1"
    project_dir = workspace_dir / "project"
    output_dir = workspace_dir / "output"
    logs_dir = workspace_dir / "logs"
    meta_dir = workspace_dir / "meta"
    captured = {}

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap.settings",
        SimpleNamespace(SCANNER_GITLEAKS_IMAGE="vulhunter/gitleaks-runner:test"),
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap.ensure_scan_workspace",
        lambda *_args, **_kwargs: workspace_dir,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap.ensure_scan_project_dir",
        lambda *_args, **_kwargs: project_dir,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap.ensure_scan_output_dir",
        lambda *_args, **_kwargs: output_dir,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap.ensure_scan_logs_dir",
        lambda *_args, **_kwargs: logs_dir,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap.ensure_scan_meta_dir",
        lambda *_args, **_kwargs: meta_dir,
        raising=False,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap.subprocess.run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("bootstrap gitleaks helper should use runner container")
        ),
    )

    async def _fake_run_scanner_container(spec, **_kwargs):
        captured["spec"] = spec
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        Path(output_dir / "report.json").write_text(
            json.dumps(parsed_gitleaks),
            encoding="utf-8",
        )
        return SimpleNamespace(
            success=True,
            container_id="gitleaks-bootstrap-1",
            exit_code=0,
            stdout_path=str(logs_dir / "stdout.log"),
            stderr_path=str(logs_dir / "stderr.log"),
            error=None,
        )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap.run_scanner_container",
        _fake_run_scanner_container,
        raising=False,
    )

    findings = await _run_bootstrap_gitleaks_scan(str(tmp_path))

    assert findings == parsed_gitleaks
    assert captured["spec"].image == "vulhunter/gitleaks-runner:test"
    assert captured["spec"].workspace_dir == str(workspace_dir)
    assert captured["spec"].command == [
        "gitleaks",
        "detect",
        "--source",
        "/scan/project",
        "--report-format",
        "json",
        "--report-path",
        "/scan/output/report.json",
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

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap._run_bootstrap_gitleaks_scan",
        AsyncMock(side_effect=FileNotFoundError("gitleaks not found")),
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
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap._resolve_bandit_bootstrap_rule_ids",
        AsyncMock(return_value=["B105", "B101"]),
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
async def test_prepare_embedded_bootstrap_bandit_uses_resolved_rule_ids(monkeypatch):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarListResult([]))
    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )
    captured = {}

    class _FakeBanditScanner:
        def __init__(self, *, timeout_seconds=900, rule_ids=None):
            captured["rule_ids"] = list(rule_ids or [])

        async def scan(self, _project_root):
            return SimpleNamespace(total_findings=0, findings=[])

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap.BanditBootstrapScanner",
        _FakeBanditScanner,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap._resolve_bandit_bootstrap_rule_ids",
        AsyncMock(return_value=["B105", "B602"]),
    )

    candidates, bootstrap_task_id, source = await _prepare_embedded_bootstrap_findings(
        db=db,
        project_root="/tmp/project",
        event_emitter=event_emitter,
        opengrep_enabled=False,
        bandit_enabled=True,
        gitleaks_enabled=False,
    )

    assert candidates == []
    assert bootstrap_task_id is None
    assert source == "embedded_bandit"
    assert captured["rule_ids"] == ["B105", "B602"]


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_bandit_zero_rules_raises_and_emits_error(monkeypatch):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarListResult([]))
    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap._resolve_bandit_bootstrap_rule_ids",
        AsyncMock(side_effect=RuntimeError("无可执行 Bandit 规则，请先在规则页启用至少 1 条规则")),
    )

    with pytest.raises(RuntimeError, match="无可执行 Bandit 规则"):
        await _prepare_embedded_bootstrap_findings(
            db=db,
            project_root="/tmp/project",
            event_emitter=event_emitter,
            opengrep_enabled=False,
            bandit_enabled=True,
            gitleaks_enabled=False,
        )

    event_emitter.emit_error.assert_awaited_once_with(
        "无可执行 Bandit 规则，请先在规则页启用至少 1 条规则"
    )


def test_resolve_bandit_effective_rule_ids_for_bootstrap_filters_inactive_and_deleted():
    snapshot_test_ids = ["B101", "B102", "B103", "B104"]
    states_by_test_id = {
        "B102": SimpleNamespace(test_id="B102", is_active=False, is_deleted=False),
        "B103": SimpleNamespace(test_id="B103", is_active=True, is_deleted=True),
        "B104": SimpleNamespace(test_id="B104", is_active=True, is_deleted=False),
    }
    assert _resolve_bandit_effective_rule_ids_for_bootstrap(
        snapshot_test_ids=snapshot_test_ids,
        states_by_test_id=states_by_test_id,
    ) == ["B101", "B104"]


@pytest.mark.asyncio
async def test_resolve_bandit_bootstrap_rule_ids_raises_when_all_disabled(monkeypatch):
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_ScalarListResult(
            [SimpleNamespace(test_id="B101", is_active=False, is_deleted=False)]
        )
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap._extract_bandit_snapshot_test_ids_for_bootstrap",
        lambda: ["B101"],
    )

    with pytest.raises(RuntimeError, match="无可执行 Bandit 规则"):
        await _resolve_bandit_bootstrap_rule_ids(db)


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
        "yasa_enabled": False,
        "yasa_language": "auto",
        "yasa_rule_config_id": None,
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
        "yasa_enabled": False,
        "yasa_language": "auto",
        "yasa_rule_config_id": None,
    }


def test_resolve_static_bootstrap_config_accepts_manual_yasa_language():
    task = SimpleNamespace(
        audit_scope={
            "static_bootstrap": {
                "mode": "embedded",
                "yasa_enabled": True,
                "yasa_language": "javascript",
            }
        }
    )
    config = _resolve_static_bootstrap_config(task, source_mode="hybrid")
    assert config["yasa_enabled"] is True
    assert config["yasa_language"] == "javascript"


def test_resolve_static_bootstrap_config_preserves_yasa_rule_config_id():
    task = SimpleNamespace(
        audit_scope={
            "static_bootstrap": {
                "mode": "embedded",
                "yasa_enabled": True,
                "yasa_language": "auto",
                "yasa_rule_config_id": "cfg-1",
            }
        }
    )
    config = _resolve_static_bootstrap_config(task, source_mode="hybrid")
    assert config["yasa_rule_config_id"] == "cfg-1"


def test_resolve_static_bootstrap_config_accepts_yasa_rule_config_id():
    task = SimpleNamespace(
        audit_scope={
            "static_bootstrap": {
                "mode": "embedded",
                "yasa_enabled": True,
                "yasa_language": "auto",
                "yasa_rule_config_id": "custom-yasa-1",
            }
        }
    )
    config = _resolve_static_bootstrap_config(task, source_mode="hybrid")
    assert config["yasa_rule_config_id"] == "custom-yasa-1"


def test_resolve_static_bootstrap_config_rejects_invalid_yasa_language():
    task = SimpleNamespace(
        audit_scope={
            "static_bootstrap": {
                "mode": "embedded",
                "yasa_enabled": True,
                "yasa_language": "php",
            }
        }
    )
    with pytest.raises(HTTPException, match="不支持语言: php"):
        _resolve_static_bootstrap_config(task, source_mode="hybrid")


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_yasa_uses_custom_rule_config(monkeypatch):
    custom_rule_config = YasaRuleConfig(
        id="cfg-1",
        name="custom-yasa",
        language="javascript",
        checker_pack_ids="pack-js",
        checker_ids="checker-js",
        rule_config_json='{"rules":[]}',
        is_active=True,
        source="custom",
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneResult(custom_rule_config))
    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )
    captured: dict[str, object] = {}

    class _FakeYasaBootstrapScanner:
        def __init__(self, *, language, custom_rule_config=None, timeout_seconds=None):
            captured["language"] = language
            captured["custom_rule_config"] = custom_rule_config

        async def scan(self, project_root):
            return SimpleNamespace(total_findings=0, findings=[])

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_bootstrap.YasaBootstrapScanner",
        _FakeYasaBootstrapScanner,
    )

    candidates, bootstrap_task_id, source = await _prepare_embedded_bootstrap_findings(
        db=db,
        project_root="/tmp/project",
        event_emitter=event_emitter,
        programming_languages='["javascript"]',
        opengrep_enabled=False,
        yasa_enabled=True,
        yasa_language="auto",
        yasa_rule_config_id="cfg-1",
    )

    assert source == "embedded_yasa"
    assert bootstrap_task_id is None
    assert candidates == []
    assert captured["language"] == "javascript"
    assert captured["custom_rule_config"] is custom_rule_config


@pytest.mark.asyncio
async def test_prepare_embedded_bootstrap_yasa_rejects_disabled_rule_config():
    disabled_rule_config = YasaRuleConfig(
        id="cfg-2",
        name="disabled-yasa",
        language="javascript",
        checker_pack_ids="pack-js",
        checker_ids="checker-js",
        rule_config_json='{"rules":[]}',
        is_active=False,
        source="custom",
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneResult(disabled_rule_config))
    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="自定义规则配置已禁用"):
        await _prepare_embedded_bootstrap_findings(
            db=db,
            project_root="/tmp/project",
            event_emitter=event_emitter,
            programming_languages='["javascript"]',
            opengrep_enabled=False,
            yasa_enabled=True,
            yasa_rule_config_id="cfg-2",
        )
