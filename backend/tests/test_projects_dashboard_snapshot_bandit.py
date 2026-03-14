from types import SimpleNamespace
from unittest.mock import AsyncMock
from datetime import datetime, timezone

import pytest

from app.api.v1.endpoints.projects import get_dashboard_snapshot


class _AllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self


@pytest.mark.asyncio
async def test_dashboard_snapshot_includes_bandit_in_static_metrics(monkeypatch):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _AllResult([("project-1", "alpha")]),  # projects
            _AllResult([("op-1", "project-1", "completed", 1000)]),  # opengrep
            _AllResult([("project-1", "completed", 5, 500)]),  # gitleaks
            _AllResult([("project-1", "completed", 1, 2, 1, 300)]),  # bandit
            _AllResult([("project-1", "completed", 4, 200)]),  # phpstan
            _AllResult(  # agent
                [
                    (
                        "project-1",
                        "completed",
                        "[INTELLIGENT] task",
                        "desc",
                        3,
                        datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
                        datetime(2026, 3, 1, 0, 1, tzinfo=timezone.utc),
                    )
                ]
            ),
            _AllResult([]),  # rules
            _AllResult([]),  # opengrep findings
            _AllResult([]),  # agent findings
        ]
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.projects.count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"op-1": 2}),
    )

    response = await get_dashboard_snapshot(
        top_n=10,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert len(response.scan_runs) == 1
    assert len(response.vulns) == 1

    scan_item = response.scan_runs[0]
    assert scan_item.project_id == "project-1"
    assert scan_item.static_runs == 4  # opengrep + gitleaks + bandit + phpstan

    vuln_item = response.vulns[0]
    # static_vulns = opengrep_high_conf(2) + gitleaks(5) + bandit(1+2+1) + phpstan(4)
    assert vuln_item.static_vulns == 15


@pytest.mark.asyncio
async def test_dashboard_snapshot_includes_rule_confidence_and_cwe_distribution(
    monkeypatch,
):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _AllResult([("project-1", "alpha")]),  # projects
            _AllResult([("op-1", "project-1", "completed", 1000)]),  # opengrep tasks
            _AllResult([]),  # gitleaks tasks
            _AllResult([]),  # bandit tasks
            _AllResult([]),  # phpstan tasks
            _AllResult(  # agent tasks
                [
                    (
                        "project-1",
                        "completed",
                        "[INTELLIGENT] task",
                        "desc",
                        1,
                        datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
                        datetime(2026, 3, 1, 0, 1, tzinfo=timezone.utc),
                    )
                ]
            ),
            _AllResult(  # severe opengrep rules only
                [
                    ("rule-sql", "ERROR", "HIGH", True, ["CWE-89"]),
                    ("rule-xss", "ERROR", "MIDIUM", False, ["CWE-79"]),
                    ("rule-low", "ERROR", "LOW", True, ["CWE-22"]),
                    ("rule-unknown", "ERROR", None, True, None),
                    ("rule-ignore", "WARNING", "HIGH", True, ["CWE-78"]),
                ]
            ),
            _AllResult(  # opengrep findings for cwe_distribution
                [
                    (
                        "op-1",
                        {
                            "check_id": "rule-sql",
                            "confidence": "HIGH",
                            "cwe": ["CWE-89", "89"],
                        },
                    ),
                    (
                        "op-1",
                        {
                            "check_id": "rule-sql",
                        },
                    ),
                    (
                        "op-1",
                        {
                            "check_id": "rule-xss",
                            "confidence": "MEDIUM",
                            "cwe": ["CWE-79"],
                        },
                    ),
                ]
            ),
            _AllResult(  # verified agent findings with resolved cwe
                [
                    (
                        True,
                        "CWE-79",
                        "xss",
                        "Reflected XSS",
                        "desc",
                        "print(user_input)",
                    ),
                    (
                        False,
                        "CWE-22",
                        "path_traversal",
                        "Ignored because not verified",
                        "desc",
                        None,
                    ),
                ]
            ),
        ]
    )

    monkeypatch.setattr(
        "app.api.v1.endpoints.projects.count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"op-1": 2}),
    )

    response = await get_dashboard_snapshot(
        top_n=10,
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
        (1, 1),
        (1, 1),
    ]

    assert [item.cwe_id for item in response.cwe_distribution] == ["CWE-89", "CWE-79"]
    assert [
        (item.total_findings, item.opengrep_findings, item.agent_findings)
        for item in response.cwe_distribution
    ] == [
        (2, 2, 0),
        (1, 0, 1),
    ]
