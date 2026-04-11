import importlib


def test_agent_tasks_split_modules_exist():
    module_names = [
        "app.api.v1.endpoints.agent_tasks_contracts",
        "app.api.v1.endpoints.agent_tasks_tool_runtime",
        "app.api.v1.endpoints.agent_tasks_bootstrap",
        "app.api.v1.endpoints.agent_tasks_findings",
    ]

    for module_name in module_names:
        importlib.import_module(module_name)


def test_agent_tasks_facade_re_exports_key_symbols():
    from app.api.v1.endpoints import agent_tasks
    from app.api.v1.endpoints import agent_tasks_bootstrap
    from app.api.v1.endpoints import agent_tasks_contracts
    from app.api.v1.endpoints import agent_tasks_findings
    from app.api.v1.endpoints import agent_tasks_tool_runtime
    from app.services.agent import bootstrap_findings
    from app.services.agent import bootstrap_policy
    from app.services.agent import scope_filters

    assert agent_tasks.AgentTaskCreate is agent_tasks_contracts.AgentTaskCreate
    assert (
        agent_tasks.build_task_write_scope_guard
        is agent_tasks_tool_runtime.build_task_write_scope_guard
    )
    assert (
        agent_tasks._sync_tool_playbook_to_memory
        is agent_tasks_tool_runtime._sync_tool_playbook_to_memory
    )
    assert (
        agent_tasks._resolve_static_bootstrap_config
        is bootstrap_policy._resolve_static_bootstrap_config
    )
    assert (
        agent_tasks_bootstrap._resolve_static_bootstrap_config
        is bootstrap_policy._resolve_static_bootstrap_config
    )
    assert (
        agent_tasks._normalize_bootstrap_finding_from_gitleaks_payload
        is bootstrap_findings._normalize_bootstrap_finding_from_gitleaks_payload
    )
    assert (
        agent_tasks_bootstrap._dedupe_bootstrap_findings
        is bootstrap_findings._dedupe_bootstrap_findings
    )
    assert agent_tasks._filter_bootstrap_findings is scope_filters._filter_bootstrap_findings
    assert agent_tasks_findings._is_core_ignored_path is scope_filters._is_core_ignored_path
    assert agent_tasks._save_findings is agent_tasks_findings._save_findings


def test_agent_tasks_api_router_import_remains_healthy():
    from app.api.v1.api import api_router

    paths = {route.path for route in api_router.routes}
    assert paths == set()
