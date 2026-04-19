from pathlib import Path

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
