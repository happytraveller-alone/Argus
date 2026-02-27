import asyncio

import pytest

from app.services.agent.event_manager import EventManager


@pytest.mark.asyncio
async def test_wait_for_tool_drain_unblocks_after_tool_result():
    event_manager = EventManager()
    task_id = "task-drain-1"

    await event_manager.add_event(
        task_id=task_id,
        event_type="tool_call",
        sequence=1,
        tool_name="read_file",
        tool_input={"file_path": "src/main.py"},
        metadata={"tool_call_id": "call-1"},
    )

    waiter = asyncio.create_task(
        event_manager.wait_for_tool_drain(task_id, timeout_seconds=2)
    )
    await asyncio.sleep(0.02)

    await event_manager.add_event(
        task_id=task_id,
        event_type="tool_result",
        sequence=2,
        tool_name="read_file",
        metadata={"tool_call_id": "call-1"},
    )

    result = await waiter
    assert result["ready"] is True
    assert result["timed_out"] is False
    assert result["pending_tool_calls"] == []
