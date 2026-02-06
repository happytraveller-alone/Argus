from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints.projects import (
    _build_static_scan_overview_item_from_row,
    get_static_scan_overview,
)


class _ScalarResult:
    def __init__(self, value: int):
        self._value = value

    def scalar(self):
        return self._value


class _MappingResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


def _make_db_mock(total: int, rows):
    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarResult(total),
            _MappingResult(rows),
        ]
    )
    return db


def test_overview_item_opengrep_counts():
    row = {
        "project_id": "project-1",
        "project_name": "demo",
        "opengrep_task_id": "op-1",
        "opengrep_created_at": datetime(2026, 2, 1, 8, 0, 0, tzinfo=timezone.utc),
        "opengrep_total_findings": 10,
        "opengrep_error_count": 3,
        "opengrep_warning_count": 4,
        "paired_gitleaks_task_id": None,
        "paired_gitleaks_created_at": None,
        "paired_gitleaks_total_findings": None,
        "latest_gitleaks_task_id": None,
        "latest_gitleaks_created_at": None,
        "latest_gitleaks_total_findings": None,
    }

    item = _build_static_scan_overview_item_from_row(row)
    assert item is not None
    assert item.last_scan_tool == "opengrep"
    assert item.paired_gitleaks_task_id is None
    assert item.severe_count == 3
    assert item.hint_count == 4
    assert item.info_count == 3
    assert item.total_findings == 10


def test_overview_item_gitleaks_mapped_to_hint():
    row = {
        "project_id": "project-1",
        "project_name": "demo",
        "opengrep_task_id": None,
        "opengrep_created_at": None,
        "opengrep_total_findings": None,
        "opengrep_error_count": None,
        "opengrep_warning_count": None,
        "paired_gitleaks_task_id": None,
        "paired_gitleaks_created_at": None,
        "paired_gitleaks_total_findings": None,
        "latest_gitleaks_task_id": "git-1",
        "latest_gitleaks_created_at": datetime(2026, 2, 1, 8, 0, 0, tzinfo=timezone.utc),
        "latest_gitleaks_total_findings": 8,
    }

    item = _build_static_scan_overview_item_from_row(row)
    assert item is not None
    assert item.last_scan_tool == "gitleaks"
    assert item.paired_gitleaks_task_id is None
    assert item.severe_count == 0
    assert item.hint_count == 8
    assert item.info_count == 0
    assert item.total_findings == 8


def test_overview_item_paired_gitleaks_is_merged_into_hint():
    row = {
        "project_id": "project-1",
        "project_name": "demo",
        "opengrep_task_id": "op-1",
        "opengrep_created_at": datetime(2026, 2, 1, 8, 0, 0, tzinfo=timezone.utc),
        "opengrep_total_findings": 5,
        "opengrep_error_count": 1,
        "opengrep_warning_count": 2,
        "paired_gitleaks_task_id": "git-1",
        "paired_gitleaks_created_at": datetime(2026, 2, 1, 8, 0, 30, tzinfo=timezone.utc),
        "paired_gitleaks_total_findings": 9,
        "latest_gitleaks_task_id": "git-2",
        "latest_gitleaks_created_at": datetime(2026, 2, 1, 8, 3, 0, tzinfo=timezone.utc),
        "latest_gitleaks_total_findings": 1,
    }

    item = _build_static_scan_overview_item_from_row(row)
    assert item is not None
    assert item.last_scan_tool == "opengrep"
    assert item.last_scan_task_id == "op-1"
    assert item.paired_gitleaks_task_id == "git-1"
    assert item.severe_count == 1
    assert item.hint_count == 11
    assert item.info_count == 2
    assert item.total_findings == 14


def test_overview_item_unpaired_newer_gitleaks_does_not_override_opengrep():
    row = {
        "project_id": "project-1",
        "project_name": "demo",
        "opengrep_task_id": "op-1",
        "opengrep_created_at": datetime(2026, 2, 1, 8, 0, 0, tzinfo=timezone.utc),
        "opengrep_total_findings": 6,
        "opengrep_error_count": 2,
        "opengrep_warning_count": 1,
        "paired_gitleaks_task_id": None,
        "paired_gitleaks_created_at": None,
        "paired_gitleaks_total_findings": None,
        "latest_gitleaks_task_id": "git-99",
        "latest_gitleaks_created_at": datetime(2026, 2, 1, 8, 10, 0, tzinfo=timezone.utc),
        "latest_gitleaks_total_findings": 20,
    }

    item = _build_static_scan_overview_item_from_row(row)
    assert item is not None
    assert item.last_scan_tool == "opengrep"
    assert item.last_scan_task_id == "op-1"
    assert item.paired_gitleaks_task_id is None
    assert item.severe_count == 2
    assert item.hint_count == 1
    assert item.info_count == 3
    assert item.total_findings == 6


@pytest.mark.asyncio
async def test_static_scan_overview_endpoint_keyword_pagination_and_completed_filter():
    rows = [
        {
            "project_id": "project-2",
            "project_name": "beta",
            "opengrep_task_id": "op-2",
            "opengrep_created_at": datetime(2026, 2, 2, 10, 0, 0, tzinfo=timezone.utc),
            "opengrep_total_findings": 3,
            "opengrep_error_count": 1,
            "opengrep_warning_count": 1,
            "paired_gitleaks_task_id": "git-2",
            "paired_gitleaks_created_at": datetime(2026, 2, 2, 10, 0, 20, tzinfo=timezone.utc),
            "paired_gitleaks_total_findings": 2,
            "latest_gitleaks_task_id": "git-2",
            "latest_gitleaks_created_at": datetime(2026, 2, 2, 10, 0, 20, tzinfo=timezone.utc),
            "latest_gitleaks_total_findings": 2,
            "last_scan_at": datetime(2026, 2, 2, 10, 0, 0, tzinfo=timezone.utc),
        }
    ]
    db = _make_db_mock(total=13, rows=rows)

    response = await get_static_scan_overview(
        page=2,
        page_size=6,
        keyword="beta",
        db=db,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert response.total == 13
    assert response.page == 2
    assert response.page_size == 6
    assert response.total_pages == 3
    assert len(response.items) == 1
    assert response.items[0].project_name == "beta"
    assert response.items[0].paired_gitleaks_task_id == "git-2"
    assert response.items[0].severe_count == 1
    assert response.items[0].hint_count == 3
    assert response.items[0].info_count == 1

    # 核验 SQL：仅按 completed 状态参与“最近成功扫描”计算
    count_stmt = db.execute.call_args_list[0].args[0]
    count_sql = str(count_stmt).lower()
    assert "row_number()" in count_sql
    assert "opengrep_scan_tasks" in count_sql
    assert "gitleaks_scan_tasks" in count_sql
    assert "lower(opengrep_scan_tasks.status)" in count_sql
    assert "lower(gitleaks_scan_tasks.status)" in count_sql
    assert "lower(projects.name) like" in count_sql

    compiled_count = count_stmt.compile()
    completed_params = [v for v in compiled_count.params.values() if isinstance(v, str)]
    assert completed_params.count("completed") >= 2
    assert "%beta%" in completed_params

    paged_stmt = db.execute.call_args_list[1].args[0]
    paged_sql = str(paged_stmt).lower()
    assert " limit " in paged_sql
    assert " offset " in paged_sql
