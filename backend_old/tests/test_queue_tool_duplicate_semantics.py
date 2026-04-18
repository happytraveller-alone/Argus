import pytest

from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue
from app.services.agent.tools.recon_queue_tools import (
    PushRiskPointToQueueTool,
    PushRiskPointsBatchToQueueTool,
)


TASK_ID = "duplicate-semantics"


def _make_recon_point() -> dict:
    return {
        "file_path": "src/auth.py",
        "line_start": 42,
        "description": "SQL query uses user input directly",
        "severity": "high",
        "confidence": 0.8,
        "vulnerability_type": "sql_injection",
    }


@pytest.mark.asyncio
async def test_push_risk_point_duplicate_is_idempotent_success():
    queue = InMemoryReconRiskQueue()
    tool = PushRiskPointToQueueTool(queue_service=queue, task_id=TASK_ID)
    point = _make_recon_point()

    first = await tool.execute(**point)
    second = await tool.execute(**point)

    assert first.success is True
    assert first.data["enqueue_status"] == "enqueued"
    assert first.data["duplicate_skipped"] is False

    assert second.success is True
    assert second.data["enqueue_status"] == "duplicate_skipped"
    assert second.data["duplicate_skipped"] is True
    assert second.data["queue_size"] == 1
    assert queue.size(TASK_ID) == 1


@pytest.mark.asyncio
async def test_push_risk_points_batch_reports_duplicate_count():
    queue = InMemoryReconRiskQueue()
    tool = PushRiskPointsBatchToQueueTool(queue_service=queue, task_id=TASK_ID)
    point = _make_recon_point()

    result = await tool.execute(risk_points=[point, dict(point)])

    assert result.success is True
    assert result.data["enqueued"] == 1
    assert result.data["duplicate_skipped"] == 1
    assert result.data["queue_size"] == 1


@pytest.mark.asyncio
async def test_recon_queue_keeps_structurally_distinct_points_on_same_line():
    queue = InMemoryReconRiskQueue()
    tool = PushRiskPointsBatchToQueueTool(queue_service=queue, task_id=TASK_ID)
    base = _make_recon_point()

    first = dict(base, entry_function="login", trust_boundary="HTTP -> auth -> SQL")
    second = dict(base, entry_function="admin_search", trust_boundary="HTTP -> admin -> SQL")

    result = await tool.execute(risk_points=[first, second])

    assert result.success is True
    assert result.data["enqueued"] == 2
    assert result.data["duplicate_skipped"] == 0
    assert result.data["queue_size"] == 2
