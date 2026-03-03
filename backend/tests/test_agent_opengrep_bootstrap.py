from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import (
    _filter_bootstrap_findings,
    _prepare_embedded_bootstrap_findings,
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
            "check_id": "rule-1",
            "path": "src/a.py",
            "start": {"line": 6},
            "end": {"line": 6},
            "extra": {
                "severity": "ERROR",
                "message": "danger",
                "lines": "danger()",
                "metadata": {"confidence": "HIGH"},
            },
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
        "app.api.v1.endpoints.agent_tasks._run_bootstrap_opengrep_scan",
        AsyncMock(return_value=parsed_findings),
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
            "check_id": "rule-1",
            "path": "src/a.py",
            "start": {"line": 10},
            "end": {"line": 10},
            "extra": {
                "severity": "ERROR",
                "message": "danger",
                "metadata": {"confidence": "MEDIUM"},
            },
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
        "app.api.v1.endpoints.agent_tasks._run_bootstrap_opengrep_scan",
        AsyncMock(return_value=parsed_opengrep),
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
