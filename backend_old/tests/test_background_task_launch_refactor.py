import pytest

from app.services.agent import scan_tracking


@pytest.mark.asyncio
async def test_launch_static_background_job_registers_and_cleans_up():
    task = scan_tracking._launch_static_background_job(
        "bandit",
        "task-1",
        scan_tracking.asyncio.sleep(0),
    )

    key = scan_tracking._scan_task_key("bandit", "task-1")
    assert scan_tracking._static_background_jobs[key] is task

    await task

    assert key not in scan_tracking._static_background_jobs
