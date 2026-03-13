from datetime import datetime, timezone

import pytest

import app.models.agent_task  # noqa: F401
import app.models.audit  # noqa: F401
import app.models.gitleaks  # noqa: F401
import app.models.opengrep  # noqa: F401
import app.models.bandit  # noqa: F401
from app.main import (
    INTERRUPTED_ERROR_MESSAGE,
    RECOVERABLE_AGENT_TASK_STATUSES,
    RECOVERABLE_AUDIT_TASK_STATUSES,
    RECOVERABLE_BANDIT_TASK_STATUSES,
    RECOVERABLE_GITLEAKS_TASK_STATUSES,
    RECOVERABLE_OPENGREP_TASK_STATUSES,
    recover_interrupted_tasks,
)
from app.models.agent_task import AgentTask, AgentTaskStatus
from app.models.audit import AuditTask
from app.models.gitleaks import GitleaksScanTask
from app.models.opengrep import OpengrepScanTask
from app.models.bandit import BanditScanTask


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
            AuditTask: RECOVERABLE_AUDIT_TASK_STATUSES,
            OpengrepScanTask: RECOVERABLE_OPENGREP_TASK_STATUSES,
            GitleaksScanTask: RECOVERABLE_GITLEAKS_TASK_STATUSES,
            BanditScanTask: RECOVERABLE_BANDIT_TASK_STATUSES,
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
    audit_task = AuditTask(
        id="audit-pending",
        project_id="project-1",
        created_by="user-1",
        task_type="repository",
        status="pending",
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

    fake_session = _FakeSession(
        {
            AgentTask: [agent_task],
            AuditTask: [audit_task],
            OpengrepScanTask: [opengrep_task],
            GitleaksScanTask: [gitleaks_task],
            BanditScanTask: [bandit_task],
        }
    )
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: fake_session)

    counts = await recover_interrupted_tasks()

    assert counts == {"agent": 1, "audit": 1, "opengrep": 1, "gitleaks": 1, "bandit": 1}
    assert fake_session.commit_calls == 1
    assert fake_session.rollback_calls == 0

    assert agent_task.status == "interrupted"
    assert agent_task.error_message == INTERRUPTED_ERROR_MESSAGE
    assert isinstance(agent_task.completed_at, datetime)
    interrupted_time = agent_task.completed_at

    assert audit_task.status == "interrupted"
    assert isinstance(audit_task.completed_at, datetime)

    assert opengrep_task.status == "interrupted"
    assert opengrep_task.error_count == 1

    assert gitleaks_task.status == "interrupted"
    assert gitleaks_task.error_message == INTERRUPTED_ERROR_MESSAGE
    assert bandit_task.status == "interrupted"
    assert bandit_task.error_message == INTERRUPTED_ERROR_MESSAGE

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
    audit_cancelled = AuditTask(
        id="audit-cancelled",
        project_id="project-1",
        created_by="user-1",
        task_type="repository",
        status="cancelled",
        completed_at=completed_at,
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
            AuditTask: [audit_cancelled],
            OpengrepScanTask: [],
            GitleaksScanTask: [gitleaks_failed],
            BanditScanTask: [],
        }
    )
    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: fake_session)

    counts = await recover_interrupted_tasks()

    assert counts == {"agent": 0, "audit": 0, "opengrep": 0, "gitleaks": 0, "bandit": 0}
    assert fake_session.commit_calls == 0
    assert fake_session.rollback_calls == 1

    assert agent_interrupted.status == "interrupted"
    assert agent_interrupted.error_message == "原始错误"
    assert agent_interrupted.completed_at == completed_at

    assert agent_paused.status == AgentTaskStatus.PAUSED
    assert agent_paused.completed_at is None

    assert audit_cancelled.status == "cancelled"
    assert audit_cancelled.completed_at == completed_at

    assert gitleaks_failed.status == "failed"
    assert gitleaks_failed.error_message == "已存在的失败原因"
