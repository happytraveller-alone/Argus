import pytest

from app.services import static_scan_runtime


@pytest.mark.asyncio
async def test_launch_static_background_job_registers_and_cleans_up():
    task = static_scan_runtime._launch_static_background_job(
        "bandit",
        "task-1",
        static_scan_runtime.asyncio.sleep(0),
    )

    key = static_scan_runtime._scan_task_key("bandit", "task-1")
    assert static_scan_runtime._static_background_jobs[key] is task

    await task

    assert key not in static_scan_runtime._static_background_jobs
