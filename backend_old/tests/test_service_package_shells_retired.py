from pathlib import Path

from tests.test_config_internal_callers_use_service_layer import (
    _collect_direct_package_import_offenders,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_llm_package_shell_stays_deleted():
    llm_package_init = PROJECT_ROOT / "app/services/llm/__init__.py"
    assert not llm_package_init.exists(), (
        "retired app.services.llm package shell should stay deleted after direct-module imports took over"
    )


def test_llm_package_shell_has_no_live_python_importers():
    offenders = _collect_direct_package_import_offenders(
        "app.services.llm",
        "app.services",
        "llm",
    )
    assert not offenders, (
        "retired app.services.llm package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )


def test_agent_agents_package_shell_stays_deleted():
    agents_package_init = PROJECT_ROOT / "app/services/agent/agents/__init__.py"
    assert not agents_package_init.exists(), (
        "retired app.services.agent.agents package shell should stay deleted"
    )


def test_agent_agents_package_shell_has_no_live_python_importers():
    offenders = _collect_direct_package_import_offenders(
        "app.services.agent.agents",
        "app.services.agent",
        "agents",
    )
    assert not offenders, (
        "retired app.services.agent.agents package shell should have no live Python importers:\n"
        + "\n".join(offenders)
    )
