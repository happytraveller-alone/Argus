from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_SCAN_WORKSPACE_MODULE = (
    "scan_workspace",
    PROJECT_ROOT / "app/services/agent/scan_workspace.py",
    "app.services.agent.scan_workspace",
)


def test_scan_workspace_module_stays_deleted():
    _, path, _ = RETIRED_SCAN_WORKSPACE_MODULE
    assert not path.exists(), "scan_workspace helper should stay deleted"


def test_scan_workspace_module_has_no_live_python_importers():
    module_name, _, dotted_module = RETIRED_SCAN_WORKSPACE_MODULE
    offenders = _collect_direct_module_import_offenders(
        dotted_module,
        ".".join(dotted_module.split(".")[:-1]),
        dotted_module.rsplit(".", 1)[-1],
    )
    assert not offenders, (
        f"retired scanner workspace helper {module_name} should have no live Python importers:\n"
        + "\n".join(offenders)
    )
