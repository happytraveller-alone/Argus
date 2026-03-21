from datetime import datetime, timezone
import sys
import types

import pytest

fastmcp_stub = types.ModuleType("fastmcp")
fastmcp_stub.Client = object
fastmcp_stub.FastMCP = object
fastmcp_client_stub = types.ModuleType("fastmcp.client")
fastmcp_transports_stub = types.ModuleType("fastmcp.client.transports")
fastmcp_transports_stub.StdioTransport = object
fastmcp_transports_stub.StreamableHttpTransport = object
git_stub = types.ModuleType("git")
git_stub.Repo = object
sys.modules.setdefault("fastmcp", fastmcp_stub)
sys.modules.setdefault("fastmcp.client", fastmcp_client_stub)
sys.modules.setdefault("fastmcp.client.transports", fastmcp_transports_stub)
sys.modules.setdefault("git", git_stub)

import app.models.agent_task  # noqa: F401
import app.models.gitleaks  # noqa: F401
import app.models.opengrep  # noqa: F401
import app.models.bandit  # noqa: F401
import app.models.phpstan  # noqa: F401
import app.models.yasa  # noqa: F401
from app.main import (
    INTERRUPTED_ERROR_MESSAGE,
    RECOVERABLE_AGENT_TASK_STATUSES,
    RECOVERABLE_BANDIT_TASK_STATUSES,
    RECOVERABLE_GITLEAKS_TASK_STATUSES,
    RECOVERABLE_OPENGREP_TASK_STATUSES,
    RECOVERABLE_PHPSTAN_TASK_STATUSES,
    RECOVERABLE_YASA_TASK_STATUSES,
    recover_interrupted_tasks,
)
from app.models.agent_task import AgentTask, AgentTaskStatus
from app.models.gitleaks import GitleaksScanTask
from app.models.opengrep import OpengrepScanTask
from app.models.bandit import BanditScanTask
from app.models.phpstan import PhpstanScanTask
from app.models.yasa import YasaScanTask


class _FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeSession:
    def __init__(self, items_by_model):
        self._items_by_model = items_by_model
        self.commit_calls = 0
        self.rollback_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        items = self._items_by_model.get(entity, [])
        recoverable_statuses = {
            AgentTask: RECOVERABLE_AGENT_TASK_STATUSES,
            OpengrepScanTask: RECOVERABLE_OPENGREP_TASK_STATUSES,
            GitleaksScanTask: RECOVERABLE_GITLEAKS_TASK_STATUSES,
            BanditScanTask: RECOVERABLE_BANDIT_TASK_STATUSES,
            PhpstanScanTask: RECOVERABLE_PHPSTAN_TASK_STATUSES,
            YasaScanTask: RECOVERABLE_YASA_TASK_STATUSES,
        }[entity]
        filtered = [item for item in items if str(item.status).lower() in recoverable_statuses]
        return _FakeScalarResult(filtered)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1


@pytest.mark.asyncio
async def test_recover_interrupted_tasks_marks_running_and_pending_tasks(monkeypatch):
    interrupted_time = None
    agent_task = AgentTask(
        id="agent-running",
        project_id="project-1",
        created_by="user-1",
        status=AgentTaskStatus.RUNNING,
        error_message=None,
        completed_at=None,
    )
    opengrep_task = OpengrepScanTask(
        id="opengrep-running",
        project_id="project-1",
        name="static",
        target_path="/tmp/project",
        status="running",
    )
    gitleaks_task = GitleaksScanTask(
        id="gitleaks-pending",
        project_id="project-1",
        name="gitleaks",
        target_path="/tmp/project",
        status="pending",
        error_message=None,
    )
    bandit_task = BanditScanTask(
        id="bandit-running",
        project_id="project-1",
        name="bandit",
        target_path="/tmp/project",
        status="running",
        error_message=None,
    )
    phpstan_task = PhpstanScanTask(
        id="phpstan-pending",
        project_id="project-1",
        name="phpstan",
        target_path="/tmp/project",
        status="pending",
        error_message=None,
    )
    yasa_task = YasaScanTask(
        id="yasa-running",
        project_id="project-1",
        name="yasa",
        target_path="/tmp/project",
        status="running",
        error_message=None,
    )

    fake_session = _FakeSession(
        {
            AgentTask: [agent_task],
            OpengrepScanTask: [opengrep_task],
            GitleaksScanTask: [gitleaks_task],
            BanditScanTask: [bandit_task],
            PhpstanScanTask: [phpstan_task],
            YasaScanTask: [yasa_task],
        }
    )
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: fake_session)

    counts = await recover_interrupted_tasks()

    assert counts == {
        "agent": 1,
        "opengrep": 1,
        "gitleaks": 1,
        "bandit": 1,
        "phpstan": 1,
        "yasa": 1,
    }
    assert fake_session.commit_calls == 1
    assert fake_session.rollback_calls == 0

    assert agent_task.status == "interrupted"
    assert agent_task.error_message == INTERRUPTED_ERROR_MESSAGE
    assert isinstance(agent_task.completed_at, datetime)
    interrupted_time = agent_task.completed_at

    assert opengrep_task.status == "interrupted"
    assert opengrep_task.error_count == 1

    assert gitleaks_task.status == "interrupted"
    assert gitleaks_task.error_message == INTERRUPTED_ERROR_MESSAGE
    assert bandit_task.status == "interrupted"
    assert bandit_task.error_message == INTERRUPTED_ERROR_MESSAGE
    assert phpstan_task.status == "interrupted"
    assert phpstan_task.error_message == INTERRUPTED_ERROR_MESSAGE
    assert yasa_task.status == "interrupted"
    assert yasa_task.error_message == INTERRUPTED_ERROR_MESSAGE

    assert interrupted_time.tzinfo is not None


@pytest.mark.asyncio
async def test_recover_interrupted_tasks_preserves_terminal_statuses_and_existing_errors(monkeypatch):
    completed_at = datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc)
    agent_interrupted = AgentTask(
        id="agent-interrupted",
        project_id="project-1",
        created_by="user-1",
        status="interrupted",
        error_message="原始错误",
        completed_at=completed_at,
    )
    agent_paused = AgentTask(
        id="agent-paused",
        project_id="project-1",
        created_by="user-1",
        status=AgentTaskStatus.PAUSED,
        error_message=None,
        completed_at=None,
    )
    gitleaks_failed = GitleaksScanTask(
        id="gitleaks-failed",
        project_id="project-1",
        name="gitleaks",
        target_path="/tmp/project",
        status="failed",
        error_message="已存在的失败原因",
    )

    fake_session = _FakeSession(
        {
            AgentTask: [agent_interrupted, agent_paused],
            OpengrepScanTask: [],
            GitleaksScanTask: [gitleaks_failed],
            BanditScanTask: [],
            PhpstanScanTask: [],
            YasaScanTask: [],
        }
    )
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: fake_session)

    counts = await recover_interrupted_tasks()

    assert counts == {
        "agent": 0,
        "opengrep": 0,
        "gitleaks": 0,
        "bandit": 0,
        "phpstan": 0,
        "yasa": 0,
    }
    assert fake_session.commit_calls == 0
    assert fake_session.rollback_calls == 1

    assert agent_interrupted.status == "interrupted"
    assert agent_interrupted.error_message == "原始错误"
    assert agent_interrupted.completed_at == completed_at

    assert agent_paused.status == AgentTaskStatus.PAUSED
    assert agent_paused.completed_at is None

    assert gitleaks_failed.status == "failed"
    assert gitleaks_failed.error_message == "已存在的失败原因"
