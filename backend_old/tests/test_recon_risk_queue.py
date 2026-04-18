import pytest

from app.services.agent.tools.recon_queue_tools import GetReconRiskQueueStatusTool


class _LocalReconQueue:
    def __init__(self):
        self._items: list[dict] = []

    def enqueue(self, _task_id: str, risk_point: dict) -> bool:
        self._items.append(dict(risk_point))
        return True

    def stats(self, _task_id: str) -> dict:
        return {
            "current_size": len(self._items),
            "total_enqueued": len(self._items),
            "total_dequeued": 0,
            "total_deduplicated": 0,
            "last_enqueue_time": None,
            "last_dequeue_time": None,
        }

    def peek(self, _task_id: str, limit: int = 3) -> list[dict]:
        return self._items[:limit]


def _sample_risk_point() -> dict:
    return {
        "file_path": "src/auth/login.py",
        "line_start": 88,
        "description": "possible sql injection",
        "severity": "high",
    }


def test_recon_queue_status_tool_keyword_only_constructor():
    queue = _LocalReconQueue()
    with pytest.raises(TypeError):
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
    queue = _LocalReconQueue()
    task_id = "task-valid-binding"
    assert queue.enqueue(task_id, _sample_risk_point()) is True

    tool = GetReconRiskQueueStatusTool(queue_service=queue, task_id=task_id)
    result = await tool.execute()

    assert result.success is True
    assert result.data["pending_count"] == 1
    assert result.data["queue_status"]["current_size"] == 1


@pytest.mark.asyncio
async def test_recon_queue_status_tool_ignores_redundant_kwargs():
    queue = _LocalReconQueue()
    task_id = "task-valid-binding-extra-kwargs"
    assert queue.enqueue(task_id, _sample_risk_point()) is True

    tool = GetReconRiskQueueStatusTool(queue_service=queue, task_id=task_id)
    result = await tool.execute(raw_input="{}", file_path="src/demo.py")

    assert result.success is True
    assert result.data["pending_count"] == 1
    assert result.data["queue_status"]["current_size"] == 1
