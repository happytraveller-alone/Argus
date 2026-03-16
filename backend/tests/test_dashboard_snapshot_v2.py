from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import projects


class _RowsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


def _build_execute_side_effect(now: datetime):
    project_rows = [
        ("p1", "Alpha"),
        ("p2", "Beta"),
    ]

    project_info_rows = [
        (
            "p1",
            {
                "total": 1000,
                "total_files": 10,
                "languages": {
                    "TypeScript": {"loc_number": 700, "files_count": 7, "proportion": 0.7},
                    "PHP": {"loc_number": 300, "files_count": 3, "proportion": 0.3},
                },
            },
            "completed",
        ),
        (
            "p2",
            {
                "total": 600,
                "total_files": 6,
                "languages": {
                    "Python": {"loc_number": 500, "files_count": 5, "proportion": 0.8333},
                    "Shell": {"loc_number": 100, "files_count": 1, "proportion": 0.1667},
                },
            },
            "completed",
        ),
    ]

    opengrep_rows = [
        ("og1", "p1", "completed", 1200, now - timedelta(days=1)),
        ("og2", "p2", "failed", 500, now - timedelta(days=9)),
    ]
    gitleaks_rows = [
        ("gl1", "p1", "completed", 2, 800, now - timedelta(days=2)),
        ("gl2", "p2", "completed", 1, 900, now - timedelta(days=15)),
    ]
    bandit_rows = [
        ("ba1", "p2", "completed", 1, 0, 0, 600, now - timedelta(days=3)),
        ("ba2", "p2", "completed", 0, 1, 0, 650, now - timedelta(days=4)),
    ]
    phpstan_rows = [
        ("ps1", "p1", "completed", 3, 700, now - timedelta(days=1)),
        ("ps2", "p2", "completed", 2, 700, now - timedelta(days=40)),
    ]
    agent_rows = [
        (
            "at1",
            "p1",
            "completed",
            "[HYBRID] audit",
            "",
            2,
            now - timedelta(days=1, seconds=1),
            now - timedelta(days=1),
            now - timedelta(days=1),
        ),
        (
            "at2",
            "p2",
            "running",
            "[INTELLIGENT] audit",
            "",
            0,
            now - timedelta(hours=2),
            None,
            now - timedelta(hours=2),
        ),
    ]
    rule_rows = [
        ("ts.rule", "TypeScript", "ERROR", "HIGH", True, ["CWE-79"]),
        ("py.rule", "Python", "ERROR", "MEDIUM", True, ["CWE-89"]),
        ("php.rule", "PHP", "ERROR", "HIGH", True, ["CWE-89"]),
    ]
    opengrep_finding_rows = [
        (
            "og1",
            {
                "check_id": "ts.rule",
                "metadata": {"cwe": ["CWE-79"]},
                "confidence": "HIGH",
            },
            "ERROR",
            "open",
            "src/app.ts",
            now - timedelta(days=1),
        ),
        (
            "og1",
            {
                "check_id": "ts.rule",
                "metadata": {"cwe": ["CWE-79"]},
                "confidence": "HIGH",
            },
            "WARNING",
            "verified",
            "src/app.ts",
            now - timedelta(days=1),
        ),
        (
            "og2",
            {
                "check_id": "py.rule",
                "metadata": {"cwe": ["CWE-89"]},
                "confidence": "MEDIUM",
            },
            "ERROR",
            "false_positive",
            "service.py",
            now - timedelta(days=5),
        ),
    ]
    gitleaks_finding_rows = [
        ("gl1", "open", "config/.env", now - timedelta(days=2)),
        ("gl1", "verified", "secrets.txt", now - timedelta(days=2)),
        ("gl2", "open", "beta.env", now - timedelta(days=15)),
    ]
    bandit_finding_rows = [
        (
            "ba1",
            "B602",
            "HIGH",
            "subprocess shell true",
            "subprocess_shell_true",
            "HIGH",
            "verified",
            "app/main.py",
            now - timedelta(days=3),
        ),
        (
            "ba2",
            "B303",
            "LOW",
            "md5 is insecure",
            "weak_hash",
            "MEDIUM",
            "false_positive",
            "legacy.py",
            now - timedelta(days=4),
        ),
    ]
    phpstan_finding_rows = [
        ("ps1", "open", "src/index.php", now - timedelta(days=1)),
        ("ps1", "verified", "src/risk.php", now - timedelta(days=1)),
        ("ps2", "fixed", "legacy.php", now - timedelta(days=40)),
    ]
    agent_finding_rows = [
        (
            "at1",
            True,
            ["CWE-79"],
            "xss",
            "Reflected XSS",
            "",
            "",
            0.91,
            0.91,
            "verified",
            "confirmed",
            "high",
            "src/app.ts",
            now - timedelta(days=1),
        ),
        (
            "at2",
            False,
            ["CWE-89"],
            "sql-injection",
            "Potential SQL injection",
            "",
            "",
            0.22,
            0.22,
            "false_positive",
            "false_positive",
            "critical",
            "legacy.py",
            now - timedelta(hours=2),
        ),
    ]

    return [
        _RowsResult(project_rows),
        _RowsResult(project_info_rows),
        _RowsResult(opengrep_rows),
        _RowsResult(gitleaks_rows),
        _RowsResult(bandit_rows),
        _RowsResult(phpstan_rows),
        _RowsResult(agent_rows),
        _RowsResult(rule_rows),
        _RowsResult(opengrep_finding_rows),
        _RowsResult(gitleaks_finding_rows),
        _RowsResult(bandit_finding_rows),
        _RowsResult(phpstan_finding_rows),
        _RowsResult(agent_finding_rows),
    ]


@pytest.mark.asyncio
async def test_dashboard_snapshot_v2_exposes_summary_and_windowed_panels(monkeypatch):
    now = datetime.now(timezone.utc)
    db = SimpleNamespace(execute=AsyncMock(side_effect=_build_execute_side_effect(now)))
    monkeypatch.setattr(
        projects,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"og1": 1, "og2": 1}),
    )

    snapshot = await projects.get_dashboard_snapshot(
        top_n=10,
        range_days=7,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert snapshot.summary.total_projects == 2
    assert snapshot.summary.current_effective_findings == 9
    assert snapshot.summary.current_verified_findings == 5
    assert snapshot.summary.window_scanned_projects == 2
    assert snapshot.summary.window_new_effective_findings == 8
    assert snapshot.summary.window_verified_findings == 5
    assert snapshot.verification_funnel.raw_findings == 11
    assert snapshot.verification_funnel.effective_findings == 8
    assert snapshot.verification_funnel.verified_findings == 5
    assert snapshot.verification_funnel.false_positive_count == 3
    assert snapshot.task_status_breakdown.completed == 8
    assert snapshot.task_status_breakdown.failed == 1
    assert snapshot.task_status_breakdown.running == 1
    assert [item.engine for item in snapshot.engine_breakdown] == [
        "agent",
        "opengrep",
        "gitleaks",
        "bandit",
        "phpstan",
    ]
    assert [item.date for item in snapshot.daily_activity]


@pytest.mark.asyncio
async def test_dashboard_snapshot_v2_builds_weighted_hotspots_and_language_risk(monkeypatch):
    now = datetime.now(timezone.utc)
    db = SimpleNamespace(execute=AsyncMock(side_effect=_build_execute_side_effect(now)))
    monkeypatch.setattr(
        projects,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"og1": 1, "og2": 1}),
    )

    snapshot = await projects.get_dashboard_snapshot(
        top_n=10,
        range_days=7,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert [item.project_name for item in snapshot.project_hotspots] == ["Alpha", "Beta"]
    assert snapshot.project_hotspots[0].risk_score == pytest.approx(32.0)
    assert snapshot.project_hotspots[1].risk_score == pytest.approx(12.5)
    assert snapshot.project_hotspots[0].verified_findings == 4
    assert snapshot.project_hotspots[1].effective_findings == 2
    assert [item.language for item in snapshot.language_risk] == [
        "TypeScript",
        "PHP",
        "Python",
    ]
    assert snapshot.language_risk[0].rules_high == 1
    assert snapshot.language_risk[2].rules_medium == 1
    assert snapshot.language_risk[0].findings_per_kloc == pytest.approx(7.14, abs=0.01)
    assert {item.cwe_id for item in snapshot.cwe_distribution} == {"CWE-79", "CWE-78"}
