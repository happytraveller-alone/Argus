import importlib

from sqlalchemy.orm import configure_mappers

from app.services.agent.task_models import AgentTask
from tests.support.legacy_orm_models import (
    OpengrepFinding,
    OpengrepRule,
    OpengrepScanTask,
    Project,
    User,
)


def test_test_support_legacy_models_configure_with_agent_task():
    assert all(
        model is not None
        for model in (User, Project, AgentTask, OpengrepRule, OpengrepScanTask, OpengrepFinding)
    )

    configure_mappers()

    project = Project(name="demo", owner_id="owner-1")
    assert project.name == "demo"
    assert project.owner_id == "owner-1"


def test_legacy_model_import_aliases_resolve_to_test_support_models():
    assert importlib.import_module("app.models.user").User is User
    assert importlib.import_module("app.models.project").Project is Project
    assert importlib.import_module("app.models.opengrep").OpengrepRule is OpengrepRule
