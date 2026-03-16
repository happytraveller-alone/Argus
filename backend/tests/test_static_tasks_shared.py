from app.api.v1.endpoints import static_tasks_shared
from app.api.v1.endpoints.static_tasks_opengrep import get_static_task_progress


def test_record_scan_progress_initializes_shared_store():
    task_id = "task-progress-1"
    static_tasks_shared._scan_progress_store.clear()

    static_tasks_shared._record_scan_progress(
        task_id,
        status="pending",
        progress=5,
        stage="pending",
        message="queued",
    )

    state = static_tasks_shared._scan_progress_store[task_id]
    assert state["status"] == "pending"
    assert state["progress"] == 5
    assert state["current_stage"] == "pending"
    assert state["message"] == "queued"
    assert len(state["logs"]) == 1


async def test_get_static_task_progress_reads_shared_progress_store():
    task_id = "task-progress-2"
    static_tasks_shared._scan_progress_store.clear()
    static_tasks_shared._record_scan_progress(
        task_id,
        status="running",
        progress=42,
        stage="scan",
        message="scanning",
    )

    class _Result:
        def scalar_one_or_none(self):
            return type(
                "Task",
                (),
                {
                    "id": task_id,
                    "status": "running",
                    "created_at": None,
                    "updated_at": None,
                },
            )()

    class _Db:
        async def execute(self, _statement):
            return _Result()

    payload = await get_static_task_progress(
        task_id=task_id,
        include_logs=True,
        db=_Db(),
        current_user=type("User", (), {"id": "u-1"})(),
    )

    assert payload["task_id"] == task_id
    assert payload["status"] == "running"
    assert payload["progress"] == 42
    assert payload["logs"][0]["message"] == "scanning"
