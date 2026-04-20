from pathlib import Path

from sqlalchemy.orm import configure_mappers

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_MODEL_SHELLS = (
    (
        "prompt_skill",
        PROJECT_ROOT / "app/models/prompt_skill.py",
        "app.models.prompt_skill",
    ),
    (
        "user_config",
        PROJECT_ROOT / "app/models/user_config.py",
        "app.models.user_config",
    ),
    (
        "prompt_template",
        PROJECT_ROOT / "app/models/prompt_template.py",
        "app.models.prompt_template",
    ),
    (
        "audit_rule",
        PROJECT_ROOT / "app/models/audit_rule.py",
        "app.models.audit_rule",
    ),
    (
        "project_info",
        PROJECT_ROOT / "app/models/project_info.py",
        "app.models.project_info",
    ),
    (
        "project_management_metrics",
        PROJECT_ROOT / "app/models/project_management_metrics.py",
        "app.models.project_management_metrics",
    ),
    (
        "analysis",
        PROJECT_ROOT / "app/models/analysis.py",
        "app.models.analysis",
    ),
)


def test_retired_model_shells_stay_deleted():
    existing = [str(path) for _, path, _ in RETIRED_MODEL_SHELLS if path.exists()]
    assert not existing, (
        "rust-owned or dead model shells should stay deleted:\n" + "\n".join(existing)
    )


def test_retired_model_shells_have_no_live_python_importers():
    for module_name, _, dotted_module in RETIRED_MODEL_SHELLS:
        offenders = _collect_direct_module_import_offenders(
            dotted_module,
            ".".join(dotted_module.split(".")[:-1]),
            dotted_module.rsplit(".", 1)[-1],
        )
        assert not offenders, (
            f"retired model shell {module_name} should have no live Python importers:\n"
            + "\n".join(offenders)
        )


def test_project_model_stays_usable_without_retired_optional_model_shells():
    import app.models.user  # noqa: F401
    import app.models.agent_task  # noqa: F401
    import app.models.opengrep  # noqa: F401
    from app.models.project import Project

    project = Project(name="demo", owner_id="user-1")

    assert project.name == "demo"


def test_project_core_models_still_configure_without_optional_shells():
    from app.models.user import User
    from app.models.project import Project
    from app.models.agent_task import AgentTask
    from app.models.opengrep import OpengrepFinding, OpengrepRule, OpengrepScanTask

    assert all(
        model is not None
        for model in (User, Project, AgentTask, OpengrepRule, OpengrepScanTask, OpengrepFinding)
    )

    configure_mappers()

    project = Project(name="demo", owner_id="owner-1")
    assert project.name == "demo"
    assert project.owner_id == "owner-1"
