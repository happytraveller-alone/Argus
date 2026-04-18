from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_SCANNER_RUNNER_MODULE = (
    "scanner_runner",
    PROJECT_ROOT / "app/services/agent/scanner_runner.py",
    "app.services.agent.scanner_runner",
)


def test_scanner_runner_module_stays_deleted():
    _, path, _ = RETIRED_SCANNER_RUNNER_MODULE
    assert not path.exists(), "scanner_runner runtime helper should stay deleted"


def test_scanner_runner_module_has_no_live_python_importers():
    module_name, _, dotted_module = RETIRED_SCANNER_RUNNER_MODULE
    offenders = _collect_direct_module_import_offenders(
        dotted_module,
        ".".join(dotted_module.split(".")[:-1]),
        dotted_module.rsplit(".", 1)[-1],
    )
    assert not offenders, (
        f"retired scanner runner module {module_name} should have no live Python importers:\n"
        + "\n".join(offenders)
    )
