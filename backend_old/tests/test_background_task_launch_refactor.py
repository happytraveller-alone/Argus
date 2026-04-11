import pytest

from app.api.v1.endpoints import static_tasks_shared


@pytest.mark.asyncio
async def test_launch_static_background_job_registers_and_cleans_up():
    task = static_tasks_shared._launch_static_background_job(
        "bandit",
        "task-1",
        static_tasks_shared.asyncio.sleep(0),
    )

    key = static_tasks_shared._scan_task_key("bandit", "task-1")
    assert static_tasks_shared._static_background_jobs[key] is task

    await task

    assert key not in static_tasks_shared._static_background_jobs
