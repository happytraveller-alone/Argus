from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_findings_module_stays_deleted():
    findings_path = PROJECT_ROOT / "app/services/agent/bootstrap_findings.py"
    assert not findings_path.exists(), (
        "retired app.services.agent.bootstrap_findings module should stay deleted"
    )


def test_bootstrap_findings_module_has_no_live_python_importers():
    offenders = _collect_direct_module_import_offenders(
        "app.services.agent.bootstrap_findings",
        "app.services.agent",
        "bootstrap_findings",
    )
    assert not offenders, (
        "retired app.services.agent.bootstrap_findings module should have no live Python importers:\n"
        + "\n".join(offenders)
    )
