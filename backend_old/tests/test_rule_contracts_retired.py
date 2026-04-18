from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_rule_contracts_module_stays_deleted():
    contracts_path = PROJECT_ROOT / "app/services/rule_contracts.py"
    assert not contracts_path.exists(), (
        "retired app.services.rule_contracts module should stay deleted"
    )


def test_rule_contracts_module_has_no_live_python_importers():
    offenders = _collect_direct_module_import_offenders(
        "app.services.rule_contracts",
        "app.services",
        "rule_contracts",
    )
    assert not offenders, (
        "retired app.services.rule_contracts module should have no live Python importers:\n"
        + "\n".join(offenders)
    )
