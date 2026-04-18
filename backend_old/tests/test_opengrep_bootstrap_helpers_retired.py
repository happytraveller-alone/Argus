from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_OPENGREP_BOOTSTRAP_HELPERS = (
    (
        "bootstrap_base",
        PROJECT_ROOT / "app/services/agent/bootstrap/base.py",
        "app.services.agent.bootstrap.base",
    ),
    (
        "bootstrap_opengrep",
        PROJECT_ROOT / "app/services/agent/bootstrap/opengrep.py",
        "app.services.agent.bootstrap.opengrep",
    ),
)


def test_opengrep_bootstrap_helpers_stay_deleted():
    existing = [str(path) for _, path, _ in RETIRED_OPENGREP_BOOTSTRAP_HELPERS if path.exists()]
    assert not existing, (
        "opengrep bootstrap helpers should stay deleted:\n" + "\n".join(existing)
    )


def test_opengrep_bootstrap_helpers_have_no_live_python_importers():
    for module_name, _, dotted_module in RETIRED_OPENGREP_BOOTSTRAP_HELPERS:
        offenders = _collect_direct_module_import_offenders(
            dotted_module,
            ".".join(dotted_module.split(".")[:-1]),
            dotted_module.rsplit(".", 1)[-1],
        )
        assert not offenders, (
            f"retired opengrep bootstrap helper {module_name} should have no live Python importers:\n"
            + "\n".join(offenders)
        )
