from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import (
    _filter_bootstrap_findings,
    _prepare_bootstrap_opengrep_findings,
)
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _ScalarOneResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _ScalarListResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_prepare_bootstrap_reuse_latest_completed(monkeypatch):
    latest_task = SimpleNamespace(id="og-task-1")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneResult(latest_task))

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
    )

    collected_candidates = [
        {"id": "f-1", "severity": "ERROR", "confidence": "HIGH"}
    ]
    collect_mock = AsyncMock(return_value=collected_candidates)
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks._collect_bootstrap_findings_for_task",
        collect_mock,
    )

    candidates, bootstrap_task_id, source = await _prepare_bootstrap_opengrep_findings(
        db=db,
        project_id="project-1",
        project_root="/tmp/project",
        event_emitter=event_emitter,
    )

    assert source == "reuse"
    assert bootstrap_task_id == "og-task-1"
    assert candidates == collected_candidates
    collect_mock.assert_awaited_once()
    event_emitter.emit_info.assert_awaited()


@pytest.mark.asyncio
async def test_prepare_bootstrap_fallback_scan_when_no_history(monkeypatch):
    active_rules = [
        SimpleNamespace(id="rule-1", pattern_yaml="rules: []"),
        SimpleNamespace(id="rule-2", pattern_yaml="rules: []"),
    ]
    parsed_findings = [
        {
            "path": "src/a.py",
            "start": {"line": 11},
            "end": {"line": 11},
            "extra": {"severity": "ERROR", "message": "danger", "lines": "danger()"},
        },
        {
            "path": "src/b.py",
            "start": {"line": 9},
            "end": {"line": 10},
            "extra": {"severity": "WARNING", "message": "warn", "lines": "warn()"},
        },
    ]
    filtered_candidates = [
        {"id": "candidate-1", "severity": "ERROR", "confidence": "HIGH"}
    ]

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def refresh_side_effect(task):
        task.id = "scan-task-1"

    db.refresh = AsyncMock(side_effect=refresh_side_effect)
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(None),
            _ScalarListResult(active_rules),
        ]
    )

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks._run_bootstrap_opengrep_scan",
        AsyncMock(return_value=parsed_findings),
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks._collect_bootstrap_findings_for_task",
        AsyncMock(return_value=filtered_candidates),
    )

    candidates, bootstrap_task_id, source = await _prepare_bootstrap_opengrep_findings(
        db=db,
        project_id="project-1",
        project_root="/tmp/project",
        event_emitter=event_emitter,
    )

    assert source == "scan"
    assert bootstrap_task_id == "scan-task-1"
    assert candidates == filtered_candidates
    assert db.add.call_count >= 3  # 1 task + findings
    assert db.commit.await_count >= 2
    event_emitter.emit_info.assert_awaited()


@pytest.mark.asyncio
async def test_prepare_bootstrap_no_active_rules_degrade():
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(None),
            _ScalarListResult([]),
        ]
    )

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
    )

    candidates, bootstrap_task_id, source = await _prepare_bootstrap_opengrep_findings(
        db=db,
        project_id="project-1",
        project_root="/tmp/project",
        event_emitter=event_emitter,
    )

    assert source == "degraded_no_rules"
    assert bootstrap_task_id is None
    assert candidates == []
    event_emitter.emit_warning.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_bootstrap_scan_failed_degrade(monkeypatch):
    active_rules = [SimpleNamespace(id="rule-1", pattern_yaml="rules: []")]

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def refresh_side_effect(task):
        task.id = "scan-task-2"

    db.refresh = AsyncMock(side_effect=refresh_side_effect)
    db.execute = AsyncMock(
        side_effect=[
            _ScalarOneResult(None),
            _ScalarListResult(active_rules),
        ]
    )

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks._run_bootstrap_opengrep_scan",
        AsyncMock(side_effect=RuntimeError("opengrep bootstrap failure")),
    )

    candidates, bootstrap_task_id, source = await _prepare_bootstrap_opengrep_findings(
        db=db,
        project_id="project-1",
        project_root="/tmp/project",
        event_emitter=event_emitter,
    )

    assert source == "degraded_scan_failed"
    assert bootstrap_task_id == "scan-task-2"
    assert candidates == []
    event_emitter.emit_warning.assert_awaited()


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
