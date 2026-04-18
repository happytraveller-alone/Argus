from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_module_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RETIRED_BUSINESS_LOGIC_RUNTIME_MODULES = (
    (
        "business_logic_risk_queue",
        PROJECT_ROOT / "app/services/agent/business_logic_risk_queue.py",
        "app.services.agent.business_logic_risk_queue",
    ),
    (
        "business_logic_recon",
        PROJECT_ROOT / "app/services/agent/agents/business_logic_recon.py",
        "app.services.agent.agents.business_logic_recon",
    ),
    (
        "business_logic_analysis",
        PROJECT_ROOT / "app/services/agent/agents/business_logic_analysis.py",
        "app.services.agent.agents.business_logic_analysis",
    ),
    (
        "business_logic_recon_queue_tools",
        PROJECT_ROOT / "app/services/agent/tools/business_logic_recon_queue_tools.py",
        "app.services.agent.tools.business_logic_recon_queue_tools",
    ),
)


def test_business_logic_runtime_cluster_stays_deleted():
    existing = [
        str(path)
        for _, path, _ in RETIRED_BUSINESS_LOGIC_RUNTIME_MODULES
        if path.exists()
    ]
    assert not existing, (
        "business logic python runtime cluster should stay deleted:\n"
        + "\n".join(existing)
    )


def test_business_logic_runtime_cluster_has_no_live_python_importers():
    for module_name, _, dotted_module in RETIRED_BUSINESS_LOGIC_RUNTIME_MODULES:
        offenders = _collect_direct_module_import_offenders(
            dotted_module,
            ".".join(dotted_module.split(".")[:-1]),
            dotted_module.rsplit(".", 1)[-1],
        )
        assert not offenders, (
            f"retired business logic runtime module {module_name} should have no live Python importers:\n"
            + "\n".join(offenders)
        )
