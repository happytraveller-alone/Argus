from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import projects, projects_insights


class _RowsResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


def test_parse_dashboard_language_info_accepts_legacy_language_maps():
    parsed = projects_insights._parse_dashboard_language_info(
        {
            "Python": 10,
            "TypeScript": {"loc_number": 25, "file_count": 2},
            "Shell": {"code": 7, "files": 1},
        }
    )

    assert parsed == {
        "Python": {"loc_number": 10, "files_count": 0},
        "TypeScript": {"loc_number": 25, "files_count": 2},
        "Shell": {"loc_number": 7, "files_count": 1},
    }


def _assert_task_status_by_scan_type_totals(snapshot) -> None:
    for status_name in (
        "pending",
        "running",
        "completed",
        "failed",
        "interrupted",
        "cancelled",
    ):
        total = getattr(snapshot.task_status_breakdown, status_name)
        breakdown = getattr(snapshot.task_status_by_scan_type, status_name)
        assert total == (
            breakdown.static + breakdown.intelligent + breakdown.hybrid
        )


def _build_empty_project_info_side_effect():
    project_rows = [("p1", "Alpha", "zip")]
    management_metrics_rows = [("p1", "ready", 0, 0, 0, 0)]
    project_info_rows = []
    empty_rows = _RowsResult([])

    return [
        _RowsResult(project_rows),
        _RowsResult(management_metrics_rows),
        _RowsResult(project_info_rows),
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
    ]


def _build_execute_side_effect(now: datetime):
    project_rows = [
        ("p1", "Alpha", "zip"),
        ("p2", "Beta", "zip"),
    ]
    management_metrics_rows = [
        ("p1", "ready", 1, 1, 2, 0),
        ("p2", "ready", 0, 1, 0, 2),
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
        ("og1", "p1", "completed", "OpenGrep scan", 1200, now - timedelta(days=1)),
        ("og2", "p2", "failed", "OpenGrep scan", 500, now - timedelta(days=9)),
    ]
    gitleaks_rows = [
        ("gl1", "p1", "completed", "Gitleaks scan", 2, 800, now - timedelta(days=2)),
        ("gl2", "p2", "completed", "Gitleaks scan", 1, 900, now - timedelta(days=15)),
    ]
    bandit_rows = [
        ("ba1", "p2", "completed", "Bandit scan", 1, 0, 0, 600, now - timedelta(days=3)),
        ("ba2", "p2", "completed", "Bandit scan", 0, 1, 0, 650, now - timedelta(days=4)),
    ]
    phpstan_rows = [
        ("ps1", "p1", "completed", "PHPStan scan", 3, 700, now - timedelta(days=1)),
        ("ps2", "p2", "completed", "PHPStan scan", 2, 700, now - timedelta(days=40)),
    ]
    yasa_rows = [
        ("ya1", "p1", "completed", "YASA scan", 4, 550, now - timedelta(days=1, hours=6)),
        ("ya2", "p2", "failed", "YASA scan", 1, 300, now - timedelta(days=6)),
    ]
    agent_rows = [
        (
            "at1",
            "p1",
            "completed",
            "[HYBRID] audit",
            "",
            2,
            2048,
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
            512,
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
    gitleaks_rule_rows = [("gl.rule.1",), ("gl.rule.2",)]
    bandit_rule_rows = [("bandit.rule.1",), ("bandit.rule.2",), ("bandit.rule.3",)]
    phpstan_rule_rows = [("phpstan.rule.1",), ("phpstan.rule.2",)]
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
        ("ps2", "verified", "legacy.php", now - timedelta(days=40)),
    ]
    yasa_finding_rows = [
        ("ya1", "open", "high", "src/policy.ts", now - timedelta(days=1, hours=6)),
        ("ya1", "verified", "warning", "src/access.ts", now - timedelta(days=1, hours=6)),
        ("ya2", "false_positive", "warning", "scripts/run.sh", now - timedelta(days=6)),
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
        _RowsResult(management_metrics_rows),
        _RowsResult(project_info_rows),
        _RowsResult(opengrep_rows),
        _RowsResult(gitleaks_rows),
        _RowsResult(bandit_rows),
        _RowsResult(phpstan_rows),
        _RowsResult(yasa_rows),
        _RowsResult(agent_rows),
        _RowsResult(rule_rows),
        _RowsResult(gitleaks_rule_rows),
        _RowsResult(bandit_rule_rows),
        _RowsResult(phpstan_rule_rows),
        _RowsResult(opengrep_finding_rows),
        _RowsResult(gitleaks_finding_rows),
        _RowsResult(bandit_finding_rows),
        _RowsResult(phpstan_finding_rows),
        _RowsResult(yasa_finding_rows),
        _RowsResult(agent_finding_rows),
    ]


def _build_static_engine_rule_total_mismatch_side_effect(now: datetime):
    rows = _build_execute_side_effect(now)
    rows[11] = _RowsResult([("bandit.state.1",), ("bandit.state.2",)])
    rows[12] = _RowsResult([("phpstan.state.1",)])
    rows.append(_ScalarResult(2))
    return rows


def _build_grouped_static_recent_tasks_side_effect(now: datetime):
    project_rows = [
        ("p1", "Alpha", "zip"),
    ]
    management_metrics_rows = [("p1", "ready", 0, 0, 1, 1)]

    project_info_rows = [
        (
            "p1",
            {
                "total": 1000,
                "total_files": 10,
                "languages": {
                    "Python": {"loc_number": 1000, "files_count": 10, "proportion": 1.0},
                },
            },
            "completed",
        ),
    ]

    batch_marker = "[[STATIC_BATCH:batch-123]]"
    opengrep_rows = []
    gitleaks_rows = [
        (
            "gl-batch",
            "p1",
            "completed",
            f"Gitleaks scan {batch_marker}",
            2,
            800,
            now - timedelta(minutes=12),
        ),
    ]
    bandit_rows = [
        (
            "ba-batch",
            "p1",
            "completed",
            f"Bandit scan {batch_marker}",
            1,
            1,
            0,
            600,
            now - timedelta(minutes=6),
        ),
    ]
    phpstan_rows = []
    yasa_rows = []
    agent_rows = []
    rule_rows = []
    gitleaks_rule_rows = []
    bandit_rule_rows = []
    phpstan_rule_rows = []
    opengrep_finding_rows = []
    gitleaks_finding_rows = [
        ("gl-batch", "open", "config/.env", now - timedelta(minutes=12)),
    ]
    bandit_finding_rows = [
        (
            "ba-batch",
            "B602",
            "HIGH",
            "subprocess shell true",
            "subprocess_shell_true",
            "HIGH",
            "verified",
            "app/main.py",
            now - timedelta(minutes=6),
        ),
    ]
    phpstan_finding_rows = []
    yasa_finding_rows = []
    agent_finding_rows = []

    return [
        _RowsResult(project_rows),
        _RowsResult(management_metrics_rows),
        _RowsResult(project_info_rows),
        _RowsResult(opengrep_rows),
        _RowsResult(gitleaks_rows),
        _RowsResult(bandit_rows),
        _RowsResult(phpstan_rows),
        _RowsResult(yasa_rows),
        _RowsResult(agent_rows),
        _RowsResult(rule_rows),
        _RowsResult(gitleaks_rule_rows),
        _RowsResult(bandit_rule_rows),
        _RowsResult(phpstan_rule_rows),
        _RowsResult(opengrep_finding_rows),
        _RowsResult(gitleaks_finding_rows),
        _RowsResult(bandit_finding_rows),
        _RowsResult(phpstan_finding_rows),
        _RowsResult(yasa_finding_rows),
        _RowsResult(agent_finding_rows),
    ]


def _build_project_risk_distribution_from_metrics_side_effect():
    project_rows = [
        ("p1", "Alpha", "repository"),
        ("p2", "Beta", "repository"),
        ("p3", "Gamma", "repository"),
        ("p4", "Delta", "repository"),
    ]
    management_metrics_rows = [
        ("p1", "ready", 0, 2, 1, 0),
        ("p2", "ready", 0, 0, 0, 0),
        ("p3", "failed", 3, 0, 0, 0),
        ("p4", "ready", 1, 0, 1, 2),
    ]
    project_info_rows = []
    empty_rows = _RowsResult([])

    return [
        _RowsResult(project_rows),
        _RowsResult(management_metrics_rows),
        _RowsResult(project_info_rows),
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
    ]


def _build_agent_trend_split_side_effect(now: datetime):
    project_rows = [("p1", "Alpha", "zip")]
    management_metrics_rows = [("p1", "ready", 0, 0, 0, 0)]
    project_info_rows = [("p1", {"languages": {}}, "completed")]
    empty_rows = _RowsResult([])

    agent_rows = [
        (
            "int-1",
            "p1",
            "completed",
            "[INTELLIGENT] audit",
            "",
            1,
            100,
            now - timedelta(days=1, minutes=3),
            now - timedelta(days=1),
            now - timedelta(days=1),
        ),
        (
            "hy-1",
            "p1",
            "completed",
            "[HYBRID] audit",
            "",
            1,
            100,
            now - timedelta(days=1, minutes=2),
            now - timedelta(days=1),
            now - timedelta(days=1),
        ),
        (
            "int-fp",
            "p1",
            "completed",
            "[INTELLIGENT] audit",
            "",
            0,
            100,
            now - timedelta(days=1, minutes=1),
            now - timedelta(days=1),
            now - timedelta(days=1),
        ),
        (
            "hy-pending",
            "p1",
            "completed",
            "[HYBRID] audit",
            "",
            0,
            100,
            now - timedelta(days=2, minutes=1),
            now - timedelta(days=2),
            now - timedelta(days=2),
        ),
    ]
    agent_finding_rows = [
        (
            "int-1",
            True,
            ["CWE-79"],
            "xss",
            "Verified intelligent finding",
            "",
            "",
            0.91,
            0.91,
            "verified",
            "confirmed",
            "high",
            "src/intelligent.ts",
            now - timedelta(days=1),
        ),
        (
            "hy-1",
            True,
            ["CWE-89"],
            "sql-injection",
            "Verified hybrid finding",
            "",
            "",
            0.84,
            0.84,
            "verified",
            "likely",
            "critical",
            "src/hybrid.ts",
            now - timedelta(days=1),
        ),
        (
            "int-fp",
            False,
            ["CWE-22"],
            "path-traversal",
            "False positive intelligent finding",
            "",
            "",
            0.8,
            0.8,
            "false_positive",
            "false_positive",
            "high",
            "src/ignored.ts",
            now - timedelta(days=1),
        ),
        (
            "hy-pending",
            False,
            ["CWE-352"],
            "csrf",
            "Unverified hybrid finding",
            "",
            "",
            0.76,
            0.76,
            "open",
            "pending",
            "medium",
            "src/unverified.ts",
            now - timedelta(days=2),
        ),
    ]

    return [
        _RowsResult(project_rows),
        _RowsResult(management_metrics_rows),
        _RowsResult(project_info_rows),
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        _RowsResult(agent_rows),
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        empty_rows,
        _RowsResult(agent_finding_rows),
    ]


@pytest.mark.asyncio
async def test_dashboard_snapshot_v2_exposes_summary_and_windowed_panels(monkeypatch):
    now = datetime.now(timezone.utc)
    db = SimpleNamespace(execute=AsyncMock(side_effect=_build_execute_side_effect(now)))
    monkeypatch.setattr(
        projects_insights,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"og1": 1, "og2": 1}),
    )
    monkeypatch.setattr(
        projects_insights,
        "_get_yasa_rule_total",
        AsyncMock(return_value=7),
    )
    monkeypatch.setattr(
        projects_insights,
        "_extract_bandit_snapshot_rules",
        lambda: [{"test_id": "B101"}, {"test_id": "B102"}, {"test_id": "B103"}],
        raising=False,
    )
    monkeypatch.setattr(
        projects_insights,
        "_extract_phpstan_snapshot_rules",
        lambda: [{"id": "phpstan.rule.1"}, {"id": "phpstan.rule.2"}],
        raising=False,
    )

    snapshot = await projects.get_dashboard_snapshot(
        top_n=10,
        range_days=7,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert snapshot.summary.total_projects == 2
    assert snapshot.summary.current_effective_findings == 12
    assert snapshot.summary.current_verified_findings == 7
    assert snapshot.summary.total_model_tokens == 2560
    assert snapshot.summary.window_scanned_projects == 2
    assert snapshot.summary.window_new_effective_findings == 10
    assert snapshot.summary.window_verified_findings == 6
    assert snapshot.verification_funnel.raw_findings == 14
    assert snapshot.verification_funnel.effective_findings == 10
    assert snapshot.verification_funnel.verified_findings == 6
    assert snapshot.verification_funnel.false_positive_count == 4
    assert snapshot.task_status_breakdown.completed == 8
    assert snapshot.task_status_breakdown.failed == 2
    assert snapshot.task_status_breakdown.running == 1
    assert snapshot.task_status_by_scan_type.completed.static == 7
    assert snapshot.task_status_by_scan_type.completed.intelligent == 0
    assert snapshot.task_status_by_scan_type.completed.hybrid == 1
    assert snapshot.task_status_by_scan_type.running.intelligent == 1
    assert snapshot.task_status_by_scan_type.failed.static == 2
    _assert_task_status_by_scan_type_totals(snapshot)
    assert [item.engine for item in snapshot.engine_breakdown] == [
        "llm",
        "opengrep",
        "gitleaks",
        "bandit",
        "phpstan",
        "yasa",
    ]
    assert snapshot.engine_breakdown[-1].effective_findings == 2
    assert snapshot.recent_tasks[0].task_id == "at2"
    assert snapshot.recent_tasks[0].task_type == "智能扫描"
    assert snapshot.recent_tasks[1].task_type == "混合扫描"
    assert snapshot.recent_tasks[2].task_type == "静态扫描"
    assert len(snapshot.recent_tasks) == 11
    assert snapshot.recent_tasks[-1].task_id == "ps2"
    assert [
        (
            item.date,
            item.total_new_findings,
            item.static_findings,
            item.intelligent_verified_findings,
            item.hybrid_verified_findings,
        )
        for item in snapshot.daily_activity
    ] == [
        ((now - timedelta(days=4)).date().isoformat(), 0, 0, 0, 0),
        ((now - timedelta(days=3)).date().isoformat(), 1, 1, 0, 0),
        ((now - timedelta(days=2)).date().isoformat(), 2, 2, 0, 0),
        ((now - timedelta(days=1)).date().isoformat(), 7, 6, 0, 1),
    ]


@pytest.mark.asyncio
async def test_dashboard_snapshot_v2_builds_weighted_hotspots_and_language_risk(monkeypatch):
    now = datetime.now(timezone.utc)
    db = SimpleNamespace(execute=AsyncMock(side_effect=_build_execute_side_effect(now)))
    monkeypatch.setattr(
        projects_insights,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"og1": 1, "og2": 1}),
    )
    monkeypatch.setattr(
        projects_insights,
        "_get_yasa_rule_total",
        AsyncMock(return_value=7),
    )
    monkeypatch.setattr(
        projects_insights,
        "_extract_bandit_snapshot_rules",
        lambda: [{"test_id": "B101"}, {"test_id": "B102"}, {"test_id": "B103"}],
        raising=False,
    )
    monkeypatch.setattr(
        projects_insights,
        "_extract_phpstan_snapshot_rules",
        lambda: [{"id": "phpstan.rule.1"}, {"id": "phpstan.rule.2"}],
        raising=False,
    )

    snapshot = await projects.get_dashboard_snapshot(
        top_n=10,
        range_days=7,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert [item.project_name for item in snapshot.project_hotspots] == ["Alpha", "Beta"]
    assert snapshot.project_hotspots[0].risk_score == pytest.approx(38.5)
    assert snapshot.project_hotspots[1].risk_score == pytest.approx(14.0)
    assert snapshot.project_hotspots[0].verified_findings == 5
    assert snapshot.project_hotspots[1].effective_findings == 3
    assert [item.language for item in snapshot.language_risk] == [
        "TypeScript",
        "PHP",
        "Python",
        "Shell",
    ]
    assert snapshot.language_risk[0].rules_high == 1
    assert snapshot.language_risk[2].rules_medium == 1
    assert snapshot.language_risk[0].findings_per_kloc == pytest.approx(10.0, abs=0.01)
    assert {item.cwe_id for item in snapshot.cwe_distribution} == {"CWE-79", "CWE-78"}
    assert [item.project_name for item in snapshot.project_risk_distribution] == [
        "Alpha",
        "Beta",
    ]
    assert snapshot.project_risk_distribution[0].critical_count == 1
    assert snapshot.project_risk_distribution[0].high_count == 1
    assert snapshot.project_risk_distribution[0].medium_count == 2
    assert snapshot.project_risk_distribution[0].total_findings == 4
    assert snapshot.project_risk_distribution[1].high_count == 1
    assert snapshot.project_risk_distribution[1].low_count == 2
    assert snapshot.project_risk_distribution[1].total_findings == 3
    assert snapshot.verified_vulnerability_types[0].type_code == "CWE-79"
    assert snapshot.verified_vulnerability_types[0].verified_count == 1
    assert [item.engine for item in snapshot.static_engine_rule_totals] == [
        "opengrep",
        "gitleaks",
        "bandit",
        "phpstan",
        "yasa",
    ]
    assert snapshot.static_engine_rule_totals[1].total_rules == 2
    assert snapshot.static_engine_rule_totals[2].total_rules == 3
    assert snapshot.static_engine_rule_totals[3].total_rules == 2
    assert snapshot.static_engine_rule_totals[-1].total_rules == 7
    assert [item.language for item in snapshot.language_loc_distribution] == [
        "TypeScript",
        "Python",
        "PHP",
        "Shell",
    ]
    assert snapshot.language_loc_distribution[0].loc_number == 700


@pytest.mark.asyncio
async def test_dashboard_snapshot_v2_static_engine_rule_totals_follow_engine_page_counts(
    monkeypatch,
):
    now = datetime.now(timezone.utc)
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=_build_static_engine_rule_total_mismatch_side_effect(now))
    )
    monkeypatch.setattr(
        projects_insights,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"og1": 1, "og2": 1}),
    )
    monkeypatch.setattr(
        projects_insights,
        "_extract_bandit_snapshot_rules",
        lambda: [
            {"test_id": "B101"},
            {"test_id": "B102"},
            {"test_id": "B103"},
            {"test_id": "B104"},
            {"test_id": "B105"},
        ],
        raising=False,
    )
    monkeypatch.setattr(
        projects_insights,
        "_extract_phpstan_snapshot_rules",
        lambda: [
            {"id": "phpstan.rule.1"},
            {"id": "phpstan.rule.2"},
            {"id": "phpstan.rule.3"},
            {"id": "phpstan.rule.4"},
        ],
        raising=False,
    )
    monkeypatch.setattr(
        projects_insights,
        "extract_yasa_snapshot_rules",
        lambda: [
            {"checker_id": "yasa-1"},
            {"checker_id": "yasa-2"},
            {"checker_id": "yasa-3"},
        ],
    )

    snapshot = await projects.get_dashboard_snapshot(
        top_n=10,
        range_days=7,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    totals = {item.engine: item.total_rules for item in snapshot.static_engine_rule_totals}

    assert totals["bandit"] == 5
    assert totals["phpstan"] == 4
    assert totals["yasa"] == 5


@pytest.mark.asyncio
async def test_dashboard_snapshot_v2_splits_intelligent_and_hybrid_verified_daily_activity(
    monkeypatch,
):
    now = datetime.now(timezone.utc)
    db = SimpleNamespace(execute=AsyncMock(side_effect=_build_agent_trend_split_side_effect(now)))
    monkeypatch.setattr(
        projects_insights,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        projects_insights,
        "_get_yasa_rule_total",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr(
        projects_insights,
        "_extract_bandit_snapshot_rules",
        lambda: [],
        raising=False,
    )
    monkeypatch.setattr(
        projects_insights,
        "_extract_phpstan_snapshot_rules",
        lambda: [],
        raising=False,
    )

    snapshot = await projects.get_dashboard_snapshot(
        top_n=10,
        range_days=7,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    previous_day = (now - timedelta(days=2)).date().isoformat()
    latest_day = (now - timedelta(days=1)).date().isoformat()
    assert [
        (
            item.date,
            item.total_new_findings,
            item.static_findings,
            item.intelligent_verified_findings,
            item.hybrid_verified_findings,
        )
        for item in snapshot.daily_activity
    ] == [
        (previous_day, 0, 0, 0, 0),
        (latest_day, 2, 0, 1, 1),
    ]


@pytest.mark.asyncio
async def test_dashboard_snapshot_v2_groups_multi_engine_static_recent_tasks(monkeypatch):
    now = datetime.now(timezone.utc)
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=_build_grouped_static_recent_tasks_side_effect(now))
    )
    monkeypatch.setattr(
        projects_insights,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        projects_insights,
        "_get_yasa_rule_total",
        AsyncMock(return_value=0),
    )

    snapshot = await projects.get_dashboard_snapshot(
        top_n=10,
        range_days=7,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert snapshot.task_status_breakdown.completed == 1
    assert snapshot.task_status_by_scan_type.completed.static == 1
    assert snapshot.task_status_by_scan_type.completed.intelligent == 0
    assert snapshot.task_status_by_scan_type.completed.hybrid == 0
    _assert_task_status_by_scan_type_totals(snapshot)
    assert len(snapshot.recent_tasks) == 1
    recent_task = snapshot.recent_tasks[0]
    assert recent_task.task_id == "gl-batch"
    assert recent_task.task_type == "静态扫描"
    assert recent_task.detail_path.startswith("/static-analysis/gl-batch?")
    assert "gitleaksTaskId=gl-batch" in recent_task.detail_path
    assert "banditTaskId=ba-batch" in recent_task.detail_path
    assert recent_task.detail_path != "/tasks/static"


@pytest.mark.asyncio
async def test_dashboard_snapshot_v2_project_risk_distribution_uses_ready_management_metrics_only(
    monkeypatch,
):
    db = SimpleNamespace(
        execute=AsyncMock(
            side_effect=_build_project_risk_distribution_from_metrics_side_effect()
        )
    )
    monkeypatch.setattr(
        projects_insights,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        projects_insights,
        "_get_yasa_rule_total",
        AsyncMock(return_value=0),
    )

    snapshot = await projects.get_dashboard_snapshot(
        top_n=1,
        range_days=14,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert [item.project_name for item in snapshot.project_risk_distribution] == ["Delta"]
    assert snapshot.project_risk_distribution[0].critical_count == 1
    assert snapshot.project_risk_distribution[0].medium_count == 1
    assert snapshot.project_risk_distribution[0].low_count == 2
    assert snapshot.project_risk_distribution[0].total_findings == 4


@pytest.mark.asyncio
async def test_dashboard_snapshot_v2_backfills_missing_project_info_for_language_loc(
    monkeypatch,
):
    db = SimpleNamespace(
        execute=AsyncMock(side_effect=_build_empty_project_info_side_effect())
    )
    monkeypatch.setattr(
        projects_insights,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        projects_insights,
        "_get_yasa_rule_total",
        AsyncMock(return_value=0),
    )
    backfill_mock = AsyncMock(
        return_value=SimpleNamespace(
            project_id="p1",
            status="completed",
            language_info={
                "total": 42,
                "total_files": 2,
                "languages": {
                    "Python": {"loc_number": 42, "files_count": 2, "proportion": 1.0},
                },
            },
        )
    )
    monkeypatch.setattr(
        projects_insights,
        "ensure_project_info_language_stats",
        backfill_mock,
        raising=False,
    )

    snapshot = await projects.get_dashboard_snapshot(
        top_n=10,
        range_days=14,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    backfill_mock.assert_awaited_once()
    assert snapshot.language_loc_distribution == [
        projects_insights.DashboardLanguageLocItem(
            language="Python",
            loc_number=42,
            project_count=1,
        )
    ]
