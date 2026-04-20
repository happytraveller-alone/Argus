from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_CORE_CONFIG = (
    PROJECT_ROOT / "app/core/config.py",
    "app.core.config",
)


def test_retired_core_config_stays_deleted():
    config_path, _ = RETIRED_CORE_CONFIG
    assert not config_path.exists(), (
        "retired app.core.config should stay deleted:\n"
        + str(config_path)
    )


def test_retired_core_config_has_no_live_python_importers():
    _, dotted_module = RETIRED_CORE_CONFIG
    offenders = _collect_direct_module_import_offenders(
        dotted_module,
        "app.core",
        "config",
    )
    assert not offenders, (
        "retired app.core.config should have no live Python importers:\n"
        + "\n".join(offenders)
    )
