from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_MODULE_PATH = PROJECT_ROOT / "app/services/agent/core/flow/flow_parser_runner.py"
RETIRED_IMPORT = "app.services.agent.core.flow.flow_parser_runner"


def test_flow_parser_runner_module_has_been_retired():
    assert not RETIRED_MODULE_PATH.exists(), "retired flow_parser_runner helper should stay deleted"


def test_no_live_python_module_imports_retired_flow_parser_runner():
    offenders = _collect_direct_module_import_offenders(
        RETIRED_IMPORT,
        "app.services.agent.core.flow",
        "flow_parser_runner",
    )
    assert not offenders, (
        "retired flow_parser_runner helper should have no live Python importers:\n"
        + "\n".join(offenders)
    )
