from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import (
    _filter_bootstrap_findings,
    _prepare_bootstrap_opengrep_findings,
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
async def test_prepare_bootstrap_always_scan_even_when_history_exists(monkeypatch):
    active_rules = [SimpleNamespace(id="rule-1", pattern_yaml="rules: []")]
    parsed_findings = [
        {
            "path": "src/a.py",
            "start": {"line": 6},
            "end": {"line": 6},
            "extra": {"severity": "ERROR", "message": "danger", "lines": "danger()"},
        },
    ]
    filtered_candidates = [{"id": "f-1", "severity": "ERROR", "confidence": "HIGH"}]

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def refresh_side_effect(task):
        task.id = "forced-scan-task-1"

    db.refresh = AsyncMock(side_effect=refresh_side_effect)
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
    collect_mock = AsyncMock(return_value=filtered_candidates)
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

    assert source == "scan_forced"
    assert bootstrap_task_id == "forced-scan-task-1"
    assert candidates == filtered_candidates
    collect_mock.assert_awaited_once()
    event_emitter.emit_info.assert_awaited()
    last_info_call = event_emitter.emit_info.await_args_list[-1]
    last_metadata = last_info_call.kwargs.get("metadata")
    assert isinstance(last_metadata, dict)
    assert last_metadata.get("bootstrap") is True
    assert last_metadata.get("bootstrap_task_id") == "forced-scan-task-1"
    assert last_metadata.get("bootstrap_source") == "scan_forced"
    assert last_metadata.get("bootstrap_total_findings") == len(parsed_findings)
    assert (
        last_metadata.get("bootstrap_candidate_count")
        == len(filtered_candidates)
    )


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
        return_value=_ScalarListResult(active_rules)
    )

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
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

    assert source == "scan_forced"
    assert bootstrap_task_id == "scan-task-1"
    assert candidates == filtered_candidates
    assert db.add.call_count >= 3  # 1 task + findings
    assert db.commit.await_count >= 2
    event_emitter.emit_info.assert_awaited()
    last_info_call = event_emitter.emit_info.await_args_list[-1]
    last_metadata = last_info_call.kwargs.get("metadata")
    assert isinstance(last_metadata, dict)
    assert last_metadata.get("bootstrap") is True
    assert last_metadata.get("bootstrap_task_id") == "scan-task-1"
    assert last_metadata.get("bootstrap_source") == "scan_forced"
    assert last_metadata.get("bootstrap_total_findings") == len(parsed_findings)
    assert (
        last_metadata.get("bootstrap_candidate_count")
        == len(filtered_candidates)
    )


@pytest.mark.asyncio
async def test_prepare_bootstrap_no_active_rules_abort():
    db = AsyncMock()
    db.execute = AsyncMock(
        return_value=_ScalarListResult([])
    )

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await _prepare_bootstrap_opengrep_findings(
            db=db,
            project_id="project-1",
            project_root="/tmp/project",
            event_emitter=event_emitter,
        )

    assert "当前没有启用规则" in str(exc_info.value)
    event_emitter.emit_error.assert_awaited_once()


@pytest.mark.asyncio
async def test_prepare_bootstrap_scan_failed_abort(monkeypatch):
    active_rules = [SimpleNamespace(id="rule-1", pattern_yaml="rules: []")]

    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    async def refresh_side_effect(task):
        task.id = "scan-task-2"

    db.refresh = AsyncMock(side_effect=refresh_side_effect)
    db.execute = AsyncMock(
        return_value=_ScalarListResult(active_rules)
    )

    event_emitter = SimpleNamespace(
        emit_info=AsyncMock(),
        emit_warning=AsyncMock(),
        emit_error=AsyncMock(),
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks._run_bootstrap_opengrep_scan",
        AsyncMock(side_effect=RuntimeError("opengrep bootstrap failure")),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await _prepare_bootstrap_opengrep_findings(
            db=db,
            project_id="project-1",
            project_root="/tmp/project",
            event_emitter=event_emitter,
        )

    assert "预处理失败" in str(exc_info.value)
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
