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


@pytest.mark.asyncio
async def test_concurrent_add_event_preserves_sequence_order_for_queue_and_stream():
    event_manager = EventManager(db_session_factory=True)
    task_id = "task-ordered-stream-1"
    event_manager.create_queue(task_id)

    async def fake_save(event_data):
        if event_data["sequence"] == 1:
            await asyncio.sleep(0.05)

    event_manager._save_event_to_db = fake_save  # type: ignore[attr-defined]

    await asyncio.gather(
        event_manager.add_event(
            task_id=task_id,
            event_type="info",
            sequence=1,
            message="first",
        ),
        event_manager.add_event(
            task_id=task_id,
            event_type="info",
            sequence=2,
            message="second",
        ),
    )

    queue = event_manager._event_queues[task_id]
    assert [event["sequence"] for event in list(queue._queue)] == [1, 2]

    stream = event_manager.stream_events(task_id, after_sequence=0)
    streamed_sequences = []
    async for event in stream:
        streamed_sequences.append(event["sequence"])
        if len(streamed_sequences) == 2:
            await stream.aclose()
            break

    assert streamed_sequences == [1, 2]
