from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_TOOL_RUNTIME_MODULES = (
    (
        "runtime",
        PROJECT_ROOT / "app/services/agent/tool_runtime/runtime.py",
        "app.services.agent.tool_runtime.runtime",
    ),
    (
        "router",
        PROJECT_ROOT / "app/services/agent/tool_runtime/router.py",
        "app.services.agent.tool_runtime.router",
    ),
    (
        "health_probe",
        PROJECT_ROOT / "app/services/agent/tool_runtime/health_probe.py",
        "app.services.agent.tool_runtime.health_probe",
    ),
    (
        "write_scope",
        PROJECT_ROOT / "app/services/agent/tool_runtime/write_scope.py",
        "app.services.agent.tool_runtime.write_scope",
    ),
    (
        "catalog",
        PROJECT_ROOT / "app/services/agent/tool_runtime/catalog.py",
        "app.services.agent.tool_runtime.catalog",
    ),
)


def test_tool_runtime_retained_core_files_stay_deleted():
    missing_files = [
        str(path)
        for _, path, _ in RETIRED_TOOL_RUNTIME_MODULES
        if path.exists()
    ]
    assert not missing_files, (
        "retired tool_runtime retained core files should stay deleted:\n"
        + "\n".join(missing_files)
    )


def test_tool_runtime_retained_core_has_no_live_python_importers():
    for module_name, _, dotted_module in RETIRED_TOOL_RUNTIME_MODULES:
        offenders = _collect_direct_module_import_offenders(
            dotted_module,
            "app.services.agent.tool_runtime",
            module_name,
        )
        assert not offenders, (
            f"retired tool_runtime.{module_name} should have no live Python importers:\n"
            + "\n".join(offenders)
        )
