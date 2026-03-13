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


@pytest.mark.asyncio
async def test_dashboard_snapshot_includes_bandit_in_static_metrics(monkeypatch):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _AllResult([("project-1", "alpha")]),  # projects
            _AllResult([("op-1", "project-1", "completed", 1000)]),  # opengrep
            _AllResult([("project-1", "completed", 5, 500)]),  # gitleaks
            _AllResult([("project-1", "completed", 1, 2, 1, 300)]),  # bandit
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
    assert scan_item.static_runs == 3  # opengrep + gitleaks + bandit

    vuln_item = response.vulns[0]
    # static_vulns = opengrep_high_conf(2) + gitleaks(5) + bandit(1+2+1)
    assert vuln_item.static_vulns == 11
