from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_QUEUE_MODULES = (
    (
        "recon_risk_queue",
        PROJECT_ROOT / "app/services/agent/recon_risk_queue.py",
        "app.services.agent.recon_risk_queue",
    ),
    (
        "vulnerability_queue",
        PROJECT_ROOT / "app/services/agent/vulnerability_queue.py",
        "app.services.agent.vulnerability_queue",
    ),
)


def test_queue_service_modules_stay_deleted():
    for _, path, _ in RETIRED_QUEUE_MODULES:
        assert not path.exists(), f"retired queue service module should stay deleted: {path.name}"


def test_queue_service_modules_have_no_live_python_importers():
    for module_name, _, dotted_module in RETIRED_QUEUE_MODULES:
        offenders = _collect_direct_module_import_offenders(
            dotted_module,
            ".".join(dotted_module.split(".")[:-1]),
            dotted_module.rsplit(".", 1)[-1],
        )
        assert not offenders, (
            f"retired queue service module {module_name} should have no live Python importers:\n"
            + "\n".join(offenders)
        )
