from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.orm.attributes import instance_state

from app.api.v1.endpoints import agent_tasks_routes_tasks
from app.api.v1.endpoints import static_tasks_opengrep
from app.api.v1.endpoints import static_tasks_shared
from app.api.v1.endpoints.agent_tasks_contracts import AgentTaskCreate
from app.models.project import Project


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _CreateSession:
    def __init__(self, *, project=None, rules=None):
        self.project = project
        self.rules = list(rules or [])
        self.added = []
        self.rollback_calls = 0
        self.close_calls = 0
        self.commit_calls = 0
        self._in_transaction = True

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) in {None, ""}:
            obj.id = f"generated-{len(self.added)}"
        now = datetime.now(timezone.utc)
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = now
        for field in (
            "total_findings",
            "high_count",
            "medium_count",
            "low_count",
            "scan_duration_ms",
            "files_scanned",
            "error_count",
            "warning_count",
            "lines_scanned",
        ):
            if hasattr(obj, field) and getattr(obj, field, None) is None:
                setattr(obj, field, 0)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1
        self._in_transaction = False

    async def close(self):
        self.close_calls += 1

    def in_transaction(self):
        return self._in_transaction

    async def get(self, model, value):
        if model is Project:
            return self.project
        return None

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is Project:
            return _ScalarOneOrNoneResult(self.project)
        return _ScalarsResult(self.rules)


class _DetachedOnCloseSession(_CreateSession):
    async def close(self):
        await super().close()
        for obj in self.added:
            state = instance_state(obj)
            state.session_id = None
            state._expire(state.dict, set())


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "factory_name", "request_payload"),
    [
        (
            static_tasks_opengrep,
            "create_static_task",
            static_tasks_opengrep.OpengrepScanTaskCreate(
                project_id="project-1",
                target_path=".",
                rule_ids=["rule-1"],
            ),
        ),
    ],
)
async def test_static_scan_create_routes_launch_async_job_and_release_request_session(
    monkeypatch,
    module,
    factory_name,
    request_payload,
):
    project = SimpleNamespace(
        id="project-1",
        name="demo-project",
        source_type="zip",
        programming_languages="typescript",
    )
    rules = [SimpleNamespace(id="rule-1")]
    db = _CreateSession(project=project, rules=rules)
    launched = []

    monkeypatch.setattr(module, "_get_project_root", AsyncMock(return_value="/tmp/project"))
    monkeypatch.setattr(module, "_launch_static_background_job", lambda scan_type, task_id, coro: launched.append((scan_type, task_id, coro)), raising=False)
    monkeypatch.setattr(module, "_record_scan_progress", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(module, "_get_user_config", AsyncMock(return_value={}), raising=False)

    create_fn = getattr(module, factory_name)
    response = await create_fn(
        request=request_payload,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.id.startswith("generated-")
    assert launched, f"{module.__name__} did not launch an asyncio task"
    assert db.rollback_calls == 1
    assert db.close_calls == 1

    for _scan_type, _task_id, coro in launched:
        coro.close()


@pytest.mark.asyncio
async def test_create_agent_task_launches_async_job_and_releases_request_session(monkeypatch):
    project = SimpleNamespace(
        id="project-1",
        name="demo-project",
        source_type="zip",
    )
    db = _CreateSession(project=project)
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

    response = await agent_tasks_routes_tasks.create_agent_task(
        request=AgentTaskCreate(project_id="project-1", target_files=["src/app.py"]),
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.id
    assert response.project_id == "project-1"
    assert created_tasks
    assert db.rollback_calls == 1
    assert db.close_calls == 1

    for _name, coro in created_tasks:
        coro.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "factory_name", "request_payload"),
    [
        (
            static_tasks_opengrep,
            "create_static_task",
            static_tasks_opengrep.OpengrepScanTaskCreate(
                project_id="project-1",
                target_path=".",
                rule_ids=["rule-1"],
            ),
        ),
    ],
)
async def test_static_scan_create_routes_do_not_touch_detached_orm_after_releasing_session(
    monkeypatch,
    module,
    factory_name,
    request_payload,
):
    project = SimpleNamespace(
        id="project-1",
        name="demo-project",
        source_type="zip",
        programming_languages="typescript",
    )
    rules = [SimpleNamespace(id="rule-1")]
    db = _DetachedOnCloseSession(project=project, rules=rules)
    launched = []

    monkeypatch.setattr(module, "_get_project_root", AsyncMock(return_value="/tmp/project"))
    monkeypatch.setattr(
        module,
        "_launch_static_background_job",
        lambda scan_type, task_id, coro: launched.append((scan_type, task_id, coro)),
        raising=False,
    )
    monkeypatch.setattr(module, "_record_scan_progress", lambda *_args, **_kwargs: None, raising=False)
    monkeypatch.setattr(module, "_get_user_config", AsyncMock(return_value={}), raising=False)

    create_fn = getattr(module, factory_name)
    response = await create_fn(
        request=request_payload,
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.id.startswith("generated-")
    assert launched

    for _scan_type, _task_id, coro in launched:
        coro.close()


@pytest.mark.asyncio
async def test_create_agent_task_does_not_touch_detached_orm_after_releasing_session(monkeypatch):
    project = SimpleNamespace(
        id="project-1",
        name="demo-project",
        source_type="zip",
    )
    db = _DetachedOnCloseSession(project=project)
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

    response = await agent_tasks_routes_tasks.create_agent_task(
        request=AgentTaskCreate(project_id="project-1", target_files=["src/app.py"]),
        db=db,
        current_user=SimpleNamespace(id="user-1"),
    )

    assert response.id
    assert created_tasks

    for _name, coro in created_tasks:
        coro.close()
