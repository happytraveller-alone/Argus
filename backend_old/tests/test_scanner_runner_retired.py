from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_SCANNER_RUNNER_PATH = PROJECT_ROOT / "app/services/agent/scanner_runner.py"


def test_scanner_runner_module_stays_deleted():
    assert not RETIRED_SCANNER_RUNNER_PATH.exists(), (
        "scanner_runner.py should stay deleted after the Rust runner bridge takeover"
    )


def test_scanner_runner_has_no_live_python_importers():
    offenders = _collect_direct_module_import_offenders(
        "app.services.agent.scanner_runner",
        "app.services.agent",
        "scanner_runner",
    )
    assert not offenders, (
        "retired scanner_runner module should have no live Python importers:\n"
        + "\n".join(offenders)
    )
