from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_MODULES = (
    (
        "config_utils",
        PROJECT_ROOT / "app/services/llm/config_utils.py",
        "app.services.llm.config_utils",
        "app.services.llm",
        "config_utils",
    ),
    (
        "provider_registry",
        PROJECT_ROOT / "app/services/llm/provider_registry.py",
        "app.services.llm.provider_registry",
        "app.services.llm",
        "provider_registry",
    ),
)


def test_retired_llm_provider_config_modules_stay_deleted():
    existing = [label for label, path, *_ in RETIRED_MODULES if path.exists()]
    assert not existing, (
        "retired llm provider/config modules should stay deleted:\n"
        + "\n".join(existing)
    )


def test_retired_llm_provider_config_modules_have_no_live_python_importers():
    offenders = []
    for _, _, module_name, parent_package, symbol in RETIRED_MODULES:
        offenders.extend(
            _collect_direct_module_import_offenders(module_name, parent_package, symbol)
        )

    assert not offenders, (
        "retired llm provider/config modules should have no live Python importers:\n"
        + "\n".join(offenders)
    )
