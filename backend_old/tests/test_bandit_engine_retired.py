from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_BANDIT_MODULES = (
    (
        "model",
        PROJECT_ROOT / "app/models/bandit.py",
        "app.models.bandit",
    ),
    (
        "rules_snapshot",
        PROJECT_ROOT / "app/services/bandit_rules_snapshot.py",
        "app.services.bandit_rules_snapshot",
    ),
    (
        "bootstrap_rules",
        PROJECT_ROOT / "app/services/agent/bandit_bootstrap_rules.py",
        "app.services.agent.bandit_bootstrap_rules",
    ),
    (
        "bootstrap_scanner",
        PROJECT_ROOT / "app/services/agent/bootstrap/bandit.py",
        "app.services.agent.bootstrap.bandit",
    ),
)


def test_bandit_modules_stay_deleted():
    existing = [str(path) for _, path, _ in RETIRED_BANDIT_MODULES if path.exists()]
    assert not existing, (
        "bandit should be fully retired in opengrep-only mode:\n" + "\n".join(existing)
    )


def test_bandit_modules_have_no_live_python_importers():
    for module_name, _, dotted_module in RETIRED_BANDIT_MODULES:
        offenders = _collect_direct_module_import_offenders(
            dotted_module,
            ".".join(dotted_module.split(".")[:-1]),
            dotted_module.rsplit(".", 1)[-1],
        )
        assert not offenders, (
            f"retired bandit module {module_name} should have no live Python importers:\n"
            + "\n".join(offenders)
        )
