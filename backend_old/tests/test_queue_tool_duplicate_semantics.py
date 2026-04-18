import pytest

from app.services.agent.tools.recon_queue_tools import (
    PushRiskPointToQueueTool,
    PushRiskPointsBatchToQueueTool,
)


TASK_ID = "duplicate-semantics"


class _LocalReconQueue:
    def __init__(self):
        self._items: list[dict] = []
        self._seen: set[tuple[str, int, str, str, str, str, str, str]] = set()

    @staticmethod
    def _fingerprint(risk_point: dict) -> tuple[str, int, str, str, str, str, str, str]:
        description = " ".join(str(risk_point.get("description") or "").lower().split())
        return (
            str(risk_point.get("file_path") or "").strip().lower(),
            int(risk_point.get("line_start") or 0),
            str(risk_point.get("vulnerability_type") or "").strip().lower(),
            str(risk_point.get("entry_function") or "").strip().lower(),
            str(risk_point.get("source") or "").strip().lower(),
            str(risk_point.get("sink") or "").strip().lower(),
            str(risk_point.get("input_surface") or "").strip().lower(),
            str(risk_point.get("trust_boundary") or "").strip().lower() + "|" + description,
        )

    def contains(self, _task_id: str, risk_point: dict) -> bool:
        return self._fingerprint(risk_point) in self._seen

    def enqueue(self, _task_id: str, risk_point: dict) -> bool:
        fingerprint = self._fingerprint(risk_point)
        if fingerprint in self._seen:
            return False
        self._seen.add(fingerprint)
        self._items.append(dict(risk_point))
        return True

    def enqueue_batch(self, task_id: str, risk_points: list[dict]) -> int:
        count = 0
        for risk_point in risk_points:
            if self.enqueue(task_id, risk_point):
                count += 1
        return count

    def size(self, _task_id: str) -> int:
        return len(self._items)


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
    queue = _LocalReconQueue()
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
    queue = _LocalReconQueue()
    tool = PushRiskPointsBatchToQueueTool(queue_service=queue, task_id=TASK_ID)
    point = _make_recon_point()

    result = await tool.execute(risk_points=[point, dict(point)])

    assert result.success is True
    assert result.data["enqueued"] == 1
    assert result.data["duplicate_skipped"] == 1
    assert result.data["queue_size"] == 1


@pytest.mark.asyncio
async def test_recon_queue_keeps_structurally_distinct_points_on_same_line():
    queue = _LocalReconQueue()
    tool = PushRiskPointsBatchToQueueTool(queue_service=queue, task_id=TASK_ID)
    base = _make_recon_point()

    first = dict(base, entry_function="login", trust_boundary="HTTP -> auth -> SQL")
    second = dict(base, entry_function="admin_search", trust_boundary="HTTP -> admin -> SQL")

    result = await tool.execute(risk_points=[first, second])

    assert result.success is True
    assert result.data["enqueued"] == 2
    assert result.data["duplicate_skipped"] == 0
    assert result.data["queue_size"] == 2
