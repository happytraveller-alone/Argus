from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import projects, projects_insights


class _AllResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


def _build_bandit_snapshot_side_effect(now: datetime):
    empty_rows = _AllResult([])
    return [
        _AllResult([("project-1", "alpha", "zip")]),
        _AllResult([("project-1", "ready", 0, 0, 0, 0)]),
        _AllResult(
            [
                (
                    "project-1",
                    {"languages": {"Python": {"loc_number": 120, "files_count": 3}}},
                    "completed",
                )
            ]
        ),
        _AllResult(
            [
                ("op-1", "project-1", "completed", "OpenGrep scan", 1000, now - timedelta(days=1)),
            ]
        ),
        _AllResult(
            [
                ("gl-1", "project-1", "completed", "Gitleaks scan", 5, 500, now - timedelta(days=2)),
            ]
        ),
        _AllResult(
            [
                ("ba-1", "project-1", "completed", "Bandit scan", 1, 2, 1, 300, now - timedelta(days=3)),
            ]
        ),
        _AllResult(
            [
                ("ps-1", "project-1", "completed", "PHPStan scan", 4, 200, now - timedelta(days=1)),
            ]
        ),
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        _AllResult(
            [
                (
                    "op-1",
                    {"check_id": "rule-sql", "confidence": "HIGH", "cwe": ["CWE-89"]},
                    "ERROR",
                    "open",
                    "src/app.py",
                    now - timedelta(days=1),
                ),
            ]
        ),
        _AllResult([("gl-1", "open", "config/.env", now - timedelta(days=2))]),
        _AllResult(
            [
                (
                    "ba-1",
                    "B602",
                    "HIGH",
                    "subprocess shell true",
                    "subprocess_shell_true",
                    "HIGH",
                    "verified",
                    "app/main.py",
                    now - timedelta(days=3),
                ),
            ]
        ),
        _AllResult([("ps-1", "open", "src/index.php", now - timedelta(days=1))]),
        empty_rows,
        empty_rows,
    ]


def _build_cwe_distribution_side_effect(now: datetime):
    empty_rows = _AllResult([])
    return [
        _AllResult([("project-1", "alpha", "zip")]),
        _AllResult([("project-1", "ready", 0, 0, 0, 0)]),
        _AllResult(
            [
                (
                    "project-1",
                    {"languages": {"python": {"loc_number": 120, "files_count": 3}}},
                    "completed",
                )
            ]
        ),
        _AllResult(
            [
                ("op-1", "project-1", "completed", "OpenGrep scan", 1000, now - timedelta(days=1)),
            ]
        ),
        empty_rows,
        _AllResult(
            [
                ("ba-1", "project-1", "completed", "Bandit scan", 1, 0, 0, 300, now - timedelta(days=3)),
            ]
        ),
        empty_rows,
        empty_rows,
        _AllResult(
            [
                (
                    "at-1",
                    "project-1",
                    "completed",
                    "[INTELLIGENT] task",
                    "desc",
                    1,
                    100,
                    now - timedelta(days=1, minutes=1),
                    now - timedelta(days=1),
                    now - timedelta(days=1),
                )
            ]
        ),
        _AllResult(
            [
                ("rule-sql", "python", "ERROR", "HIGH", True, ["CWE-89"]),
                ("rule-xss", "javascript", "ERROR", "MIDIUM", False, ["CWE-79"]),
            ]
        ),
        empty_rows,
        empty_rows,
        empty_rows,
        _AllResult(
            [
                (
                    "op-1",
                    {"check_id": "rule-sql", "confidence": "HIGH", "cwe": ["CWE-89", "89"]},
                    "ERROR",
                    "open",
                    "src/app.py",
                    now - timedelta(days=1),
                ),
                (
                    "op-1",
                    {"check_id": "rule-xss", "confidence": "MEDIUM", "cwe": ["CWE-79"]},
                    "ERROR",
                    "open",
                    "src/ui.js",
                    now - timedelta(days=1),
                ),
            ]
        ),
        empty_rows,
        _AllResult(
            [
                (
                    "ba-1",
                    "B105",
                    "HIGH",
                    "Possible hardcoded password",
                    "hardcoded_password_string",
                    "HIGH",
                    "verified",
                    "src/secrets.py",
                    now - timedelta(days=3),
                ),
            ]
        ),
        empty_rows,
        empty_rows,
        _AllResult(
            [
                (
                    "at-1",
                    True,
                    ["CWE-79"],
                    "xss",
                    "Reflected XSS",
                    "desc",
                    "print(user_input)",
                    0.91,
                    None,
                    "verified",
                    "confirmed",
                    "high",
                    "src/view.py",
                    now - timedelta(days=1),
                ),
                (
                    "at-1",
                    True,
                    ["CWE-89"],
                    "sql_injection",
                    "Medium confidence agent finding",
                    "desc",
                    None,
                    0.62,
                    None,
                    "verified",
                    "confirmed",
                    "high",
                    "src/db.py",
                    now - timedelta(days=1),
                ),
            ]
        ),
    ]


@pytest.mark.asyncio
async def test_dashboard_snapshot_includes_bandit_in_static_metrics(monkeypatch):
    now = datetime.now(timezone.utc)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_build_bandit_snapshot_side_effect(now))

    monkeypatch.setattr(
        projects_insights,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"op-1": 2}),
    )
    monkeypatch.setattr(
        projects_insights,
        "_get_yasa_rule_total",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(projects_insights, "_extract_bandit_snapshot_rules", lambda: [], raising=False)
    monkeypatch.setattr(projects_insights, "_extract_phpstan_snapshot_rules", lambda: [], raising=False)

    response = await projects.get_dashboard_snapshot(
        top_n=10,
        range_days=14,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert len(response.scan_runs) == 1
    assert len(response.vulns) == 1

    scan_item = response.scan_runs[0]
    assert scan_item.project_id == "project-1"
    assert scan_item.static_runs == 4

    vuln_item = response.vulns[0]
    assert vuln_item.static_vulns == 15

    assert [
        (
            item.date,
            item.total_new_findings,
            item.static_findings,
            item.intelligent_verified_findings,
            item.hybrid_verified_findings,
        )
        for item in response.daily_activity
    ] == [
        ((now - timedelta(days=3)).date().isoformat(), 1, 1, 0, 0),
        ((now - timedelta(days=2)).date().isoformat(), 1, 1, 0, 0),
        ((now - timedelta(days=1)).date().isoformat(), 2, 2, 0, 0),
    ]


@pytest.mark.asyncio
async def test_dashboard_snapshot_includes_rule_confidence_and_cwe_distribution(
    monkeypatch,
):
    now = datetime.now(timezone.utc)
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_build_cwe_distribution_side_effect(now))

    monkeypatch.setattr(
        projects_insights,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"op-1": 2}),
    )
    monkeypatch.setattr(
        projects_insights,
        "_get_yasa_rule_total",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(projects_insights, "_extract_bandit_snapshot_rules", lambda: [], raising=False)
    monkeypatch.setattr(projects_insights, "_extract_phpstan_snapshot_rules", lambda: [], raising=False)

    response = await projects.get_dashboard_snapshot(
        top_n=10,
        range_days=14,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert [item.confidence for item in response.rule_confidence] == [
        "HIGH",
        "MEDIUM",
        "LOW",
        "UNSPECIFIED",
    ]
    assert [(item.total_rules, item.enabled_rules) for item in response.rule_confidence] == [
        (1, 1),
        (1, 0),
        (0, 0),
        (0, 0),
    ]
    assert [
        (item.language, item.high_count, item.medium_count)
        for item in response.rule_confidence_by_language
    ] == [
        ("javascript", 0, 1),
        ("python", 1, 0),
    ]

    assert [item.cwe_id for item in response.cwe_distribution] == ["CWE-79", "CWE-89", "CWE-259"]
    assert [
        (
            item.total_findings,
            item.opengrep_findings,
            item.agent_findings,
            item.bandit_findings,
        )
        for item in response.cwe_distribution
    ] == [
        (2, 1, 1, 0),
        (2, 1, 1, 0),
        (1, 0, 0, 1),
    ]
