from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import agent_tasks_routes_tasks as routes_module


@pytest.mark.asyncio
async def test_stream_agent_events_releases_request_db_session_before_stream(monkeypatch):
    db = AsyncMock()
    db.get = AsyncMock(
        side_effect=[
            SimpleNamespace(id="task-1", project_id="project-1"),
            SimpleNamespace(id="project-1"),
        ]
    )
    release_mock = AsyncMock()
    monkeypatch.setattr(routes_module, "_release_request_db_session", release_mock)

    response = await routes_module.stream_agent_events(
        task_id="task-1",
        after_sequence=0,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.media_type == "text/event-stream"
    release_mock.assert_awaited_once_with(db)


@pytest.mark.asyncio
async def test_stream_agent_with_thinking_releases_request_db_session_before_stream(monkeypatch):
    db = AsyncMock()
    db.get = AsyncMock(
        side_effect=[
            SimpleNamespace(id="task-1", project_id="project-1"),
            SimpleNamespace(id="project-1"),
        ]
    )
    release_mock = AsyncMock()
    monkeypatch.setattr(routes_module, "_release_request_db_session", release_mock)

    response = await routes_module.stream_agent_with_thinking(
        task_id="task-1",
        include_thinking=True,
        include_tool_calls=True,
        after_sequence=0,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.media_type == "text/event-stream"
    release_mock.assert_awaited_once_with(db)
