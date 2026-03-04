import pytest

from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue
from app.services.agent.tools.recon_queue_tools import GetReconRiskQueueStatusTool


def _sample_risk_point() -> dict:
    return {
        "file_path": "src/auth/login.py",
        "line_start": 88,
        "description": "possible sql injection",
        "severity": "high",
    }


def test_inmemory_recon_risk_queue_stats_method_callable():
    queue = InMemoryReconRiskQueue()
    task_id = "task-stats-callable"

    assert callable(queue.stats)
    assert queue.enqueue(task_id, _sample_risk_point()) is True

    stats = queue.stats(task_id)
    assert stats["current_size"] == 1
    assert stats["total_enqueued"] == 1
    assert stats["total_dequeued"] == 0


def test_inmemory_recon_risk_queue_enqueue_dequeue_clear_and_contains():
    queue = InMemoryReconRiskQueue()
    task_id = "task-queue-flow"
    point = _sample_risk_point()

    assert queue.enqueue(task_id, point) is True
    assert queue.contains(task_id, point) is True
    assert queue.size(task_id) == 1
    assert queue.peek(task_id, limit=1)[0]["file_path"] == point["file_path"]

    item = queue.dequeue(task_id)
    assert item is not None
    assert item["line_start"] == point["line_start"]
    assert queue.size(task_id) == 0

    assert queue.clear(task_id) is True
    stats = queue.stats(task_id)
    assert stats["current_size"] == 0
    assert stats["total_enqueued"] == 0


def test_recon_queue_status_tool_keyword_only_constructor():
    queue = InMemoryReconRiskQueue()
    with pytest.raises(TypeError):
        # keyword-only contract should reject positional binding
        GetReconRiskQueueStatusTool(queue, "task-keyword-only")


def test_recon_queue_status_tool_invalid_binding_fails_fast():
    invalid_queue_service = {"stats": {"current_size": 1}}
    with pytest.raises(TypeError) as exc_info:
        GetReconRiskQueueStatusTool(
            queue_service=invalid_queue_service,
            task_id="task-invalid-binding",
        )

    message = str(exc_info.value)
    assert "invalid_recon_queue_service_binding" in message
    assert "missing_callable=stats" in message


@pytest.mark.asyncio
async def test_recon_queue_status_tool_executes_with_valid_binding():
    queue = InMemoryReconRiskQueue()
    task_id = "task-valid-binding"
    assert queue.enqueue(task_id, _sample_risk_point()) is True

    tool = GetReconRiskQueueStatusTool(queue_service=queue, task_id=task_id)
    result = await tool.execute()

    assert result.success is True
    assert result.data["pending_count"] == 1
    assert result.data["queue_status"]["current_size"] == 1


@pytest.mark.asyncio
async def test_recon_queue_status_tool_ignores_redundant_kwargs():
    queue = InMemoryReconRiskQueue()
    task_id = "task-valid-binding-extra-kwargs"
    assert queue.enqueue(task_id, _sample_risk_point()) is True

    tool = GetReconRiskQueueStatusTool(queue_service=queue, task_id=task_id)
    result = await tool.execute(raw_input="{}", file_path="src/demo.py")

    assert result.success is True
    assert result.data["pending_count"] == 1
    assert result.data["queue_status"]["current_size"] == 1
