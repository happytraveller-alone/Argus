import importlib


def test_agent_tasks_split_modules_exist():
    module_names = [
        "app.api.v1.endpoints.agent_tasks_contracts",
        "app.api.v1.endpoints.agent_tasks_runtime",
        "app.api.v1.endpoints.agent_tasks_tool_runtime",
        "app.api.v1.endpoints.agent_tasks_bootstrap",
        "app.api.v1.endpoints.agent_tasks_execution",
        "app.api.v1.endpoints.agent_tasks_findings",
        "app.api.v1.endpoints.agent_tasks_access",
        "app.api.v1.endpoints.agent_tasks_routes_tasks",
        "app.api.v1.endpoints.agent_tasks_routes_results",
    ]

    for module_name in module_names:
        importlib.import_module(module_name)


def test_agent_tasks_facade_re_exports_key_symbols():
    from app.api.v1.endpoints import agent_tasks
    from app.api.v1.endpoints import agent_tasks_bootstrap
    from app.api.v1.endpoints import agent_tasks_contracts
    from app.api.v1.endpoints import agent_tasks_execution
    from app.api.v1.endpoints import agent_tasks_findings
    from app.api.v1.endpoints import agent_tasks_routes_results
    from app.api.v1.endpoints import agent_tasks_routes_tasks
    from app.api.v1.endpoints import agent_tasks_tool_runtime
    from app.api.v1.endpoints import agent_tasks_runtime

    assert agent_tasks.AgentTaskCreate is agent_tasks_contracts.AgentTaskCreate
    assert agent_tasks.StepRetryExceededError is agent_tasks_runtime.StepRetryExceededError
    assert (
        agent_tasks.build_task_write_scope_guard
        is agent_tasks_tool_runtime.build_task_write_scope_guard
    )
    assert (
        agent_tasks._sync_tool_playbook_to_memory
        is agent_tasks_tool_runtime._sync_tool_playbook_to_memory
    )
    assert agent_tasks._resolve_static_bootstrap_config is agent_tasks_bootstrap._resolve_static_bootstrap_config
    assert agent_tasks._execute_agent_task is agent_tasks_execution._execute_agent_task
    assert agent_tasks._save_findings is agent_tasks_findings._save_findings
    assert agent_tasks.create_agent_task is agent_tasks_routes_tasks.create_agent_task
    assert agent_tasks.get_task_progress is agent_tasks_routes_results.get_task_progress


def test_agent_tasks_api_router_import_remains_healthy():
    from app.api.v1.api import api_router

    paths = {route.path for route in api_router.routes}
    assert "/agent-tasks/" in paths
