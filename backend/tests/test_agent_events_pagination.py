from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints.agent_tasks_routes_tasks import get_agent_task
from app.api.v1.endpoints.agent_tasks import list_agent_events
from app.models.agent_task import AgentTask
from app.models.project import Project
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
async def test_agent_events_pagination_fetches_all_without_duplicates():
    task_id = "task-1"
    page_size = 500
    total_events = 1203

    large_tool_output = "X" * 12000
    all_rows = [
        SimpleNamespace(
            id=f"evt-{idx}",
            task_id=task_id,
            event_type="info",
            phase=None,
            message=f"event-{idx}",
            sequence=idx,
            created_at=datetime(2026, 2, 12, 8, 0, 0, tzinfo=timezone.utc),
            tool_name="demo_tool" if idx == 1 else None,
            tool_input=None,
            tool_output={
                "result": large_tool_output,
                "truncated": False,
                "metadata": {
                    "render_type": "analysis_summary",
                    "display_command": "demo_tool",
                    "command_chain": ["demo_tool"],
                    "entries": [],
                },
            } if idx == 1 else None,
            tool_duration_ms=None,
            progress_percent=None,
            finding_id=None,
            tokens_used=None,
            event_metadata=None,
        )
        for idx in range(1, total_events + 1)
    ]

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return SimpleNamespace(id=task_id, project_id="project-1")
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    async def execute_side_effect(stmt):
        compiled = stmt.compile()
        params = compiled.params
        after_sequence = 0
        limit_value = page_size
        for key, value in params.items():
            if "sequence" in key and isinstance(value, int):
                after_sequence = value
            if "param" in key and isinstance(value, int) and value > 0:
                limit_value = value

        rows = [row for row in all_rows if row.sequence > after_sequence][:limit_value]
        return _ScalarListResult(rows)

    db.get = AsyncMock(side_effect=get_side_effect)
    db.execute = AsyncMock(side_effect=execute_side_effect)

    fetched_sequences = []
    after_sequence = 0
    for _ in range(10):
        events = await list_agent_events(
            task_id=task_id,
            after_sequence=after_sequence,
            limit=page_size,
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )
        if not events:
            break

        page_sequences = [event.sequence for event in events]
        fetched_sequences.extend(page_sequences)
        after_sequence = page_sequences[-1]
        if len(events) < page_size:
            break

    assert len(fetched_sequences) == total_events
    assert fetched_sequences == sorted(fetched_sequences)
    assert len(fetched_sequences) == len(set(fetched_sequences))
    assert fetched_sequences[0] == 1
    assert fetched_sequences[-1] == total_events

    first_page = await list_agent_events(
        task_id=task_id,
        after_sequence=0,
        limit=1,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )
    assert len(first_page) == 1
    assert first_page[0].tool_output["result"] == large_tool_output
    assert first_page[0].tool_output["metadata"]["display_command"] == "demo_tool"


@pytest.mark.asyncio
async def test_get_agent_task_detail_includes_tool_evidence_protocol(monkeypatch):
    task_id = "task-native-protocol"
    task = SimpleNamespace(
        id=task_id,
        project_id="project-1",
        name="native evidence task",
        description=None,
        task_type="agent_audit",
        status="completed",
        current_phase="reporting",
        current_step=None,
        total_files=0,
        indexed_files=0,
        analyzed_files=0,
        total_chunks=0,
        total_iterations=1,
        tool_calls_count=1,
        tokens_used=10,
        findings_count=0,
        verified_count=0,
        false_positive_count=0,
        critical_count=0,
        high_count=0,
        medium_count=0,
        low_count=0,
        quality_score=0.0,
        security_score=0.0,
        progress_percentage=100.0,
        created_at=datetime(2026, 2, 12, 8, 0, 0, tzinfo=timezone.utc),
        started_at=None,
        completed_at=None,
        error_message=None,
        audit_scope=None,
        target_vulnerabilities=None,
        verification_level="analysis_with_poc_plan",
        exclude_patterns=None,
        target_files=None,
        report=None,
        agent_config={"tool_evidence_protocol": "native_v1"},
    )

    db = AsyncMock()

    async def get_side_effect(model, _id):
        if model is AgentTask:
            return task
        if model is Project:
            return SimpleNamespace(id="project-1")
        return None

    db.get = AsyncMock(side_effect=get_side_effect)
    monkeypatch.setattr(
        "app.api.v1.endpoints.agent_tasks_routes_tasks._load_verified_severity_counts",
        AsyncMock(return_value={task_id: {}}),
    )

    response = await get_agent_task(
        task_id=task_id,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.tool_evidence_protocol == "native_v1"
