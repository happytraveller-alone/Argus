from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_GITLEAKS_MODULES = (
    (
        "model",
        PROJECT_ROOT / "app/models/gitleaks.py",
        "app.models.gitleaks",
    ),
    (
        "bootstrap_runtime",
        PROJECT_ROOT / "app/services/agent/bootstrap_gitleaks_runner.py",
        "app.services.agent.bootstrap_gitleaks_runner",
    ),
)


def test_gitleaks_modules_stay_deleted():
    existing = [str(path) for _, path, _ in RETIRED_GITLEAKS_MODULES if path.exists()]
    assert not existing, (
        "gitleaks should be fully retired in opengrep-only mode:\n" + "\n".join(existing)
    )


def test_gitleaks_modules_have_no_live_python_importers():
    for module_name, _, dotted_module in RETIRED_GITLEAKS_MODULES:
        offenders = _collect_direct_module_import_offenders(
            dotted_module,
            ".".join(dotted_module.split(".")[:-1]),
            dotted_module.rsplit(".", 1)[-1],
        )
        assert not offenders, (
            f"retired gitleaks module {module_name} should have no live Python importers:\n"
            + "\n".join(offenders)
        )
