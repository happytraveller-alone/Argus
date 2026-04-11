from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.v1.endpoints.agent_tasks import AgentTaskCreate, create_agent_task
from app.api.v1.endpoints import agent_tasks_routes_tasks
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


def _mock_db_with_project(project_id: str = "project-1"):
    db = AsyncMock()
    db.get = AsyncMock(
        return_value=SimpleNamespace(id=project_id, name="demo-project", source_type="zip")
    )
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    db.in_transaction = MagicMock(return_value=False)
    return db


def _stub_background_launch(monkeypatch):
    created_tasks = []

    class _CreatedTask:
        def __init__(self, coro):
            self._coro = coro

        def cancel(self):
            self._coro.close()

    monkeypatch.setattr(
        agent_tasks_routes_tasks.asyncio,
        "create_task",
        lambda coro, name=None: created_tasks.append((name, coro)) or _CreatedTask(coro),
    )
    monkeypatch.setattr(
        agent_tasks_routes_tasks.project_metrics_refresher,
        "enqueue",
        lambda *_args, **_kwargs: None,
    )
    return created_tasks


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verification_level",
    [
        "analysis_only",
        "sandbox",
        "generate_poc",
        "poc_plan",
        "analysis_with_poc_plan",
        "unexpected_value",
        None,
    ],
)
async def test_create_agent_task_normalizes_verification_level(monkeypatch, verification_level):
    db = _mock_db_with_project()
    created_tasks = _stub_background_launch(monkeypatch)
    request = AgentTaskCreate(
        project_id="project-1",
        verification_level=verification_level,  # type: ignore[arg-type]
        target_files=["src/app.py"],
    )

    task = await create_agent_task(
        request=request,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert task.verification_level == "analysis_with_poc_plan"
    assert task.target_files == ["src/app.py"]
    db.commit.assert_awaited()
    assert created_tasks
    for _name, coro in created_tasks:
        coro.close()


@pytest.mark.asyncio
async def test_create_agent_task_merges_system_core_exclude_patterns(monkeypatch):
    db = _mock_db_with_project()
    created_tasks = _stub_background_launch(monkeypatch)
    request = AgentTaskCreate(
        project_id="project-1",
        verification_level="analysis_with_poc_plan",
        exclude_patterns=["custom/**", "test/**"],
    )

    task = await create_agent_task(
        request=request,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert "custom/**" in (task.exclude_patterns or [])
    assert "test/**" in (task.exclude_patterns or [])
    assert "**/.*/**" in (task.exclude_patterns or [])
    assert "**/*.yaml" in (task.exclude_patterns or [])
    assert created_tasks
    for _name, coro in created_tasks:
        coro.close()


@pytest.mark.asyncio
async def test_create_agent_task_persists_use_prompt_skills_in_agent_config(monkeypatch):
    db = _mock_db_with_project()
    created_tasks = _stub_background_launch(monkeypatch)
    request = AgentTaskCreate(
        project_id="project-1",
        use_prompt_skills=True,
    )

    await create_agent_task(
        request=request,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    added_task = db.add.call_args.args[0]
    assert isinstance(added_task.agent_config, dict)
    assert added_task.agent_config.get("use_prompt_skills") is True

    assert created_tasks
    for _name, coro in created_tasks:
        coro.close()
