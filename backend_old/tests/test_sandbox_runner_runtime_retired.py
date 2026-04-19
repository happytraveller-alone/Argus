from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_MODULE = (
    "sandbox_runner",
    PROJECT_ROOT / "app/services/sandbox_runner.py",
    "app.services.sandbox_runner",
    "app.services",
    "sandbox_runner",
)


def test_retired_sandbox_runner_module_stays_deleted():
    _, path, *_ = RETIRED_MODULE
    assert not path.exists(), "retired sandbox_runner module should stay deleted"


def test_retired_sandbox_runner_module_has_no_live_python_importers():
    _, _, module_name, parent_package, symbol = RETIRED_MODULE
    offenders = _collect_direct_module_import_offenders(
        module_name,
        parent_package,
        symbol,
    )
    assert not offenders, (
        "retired sandbox_runner module should have no live Python importers:\n"
        + "\n".join(offenders)
    )
