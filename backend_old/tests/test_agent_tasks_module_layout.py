import importlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_agent_tasks_split_modules_exist():
    module_names = [
        "app.services.agent.task_findings",
    ]

    for module_name in module_names:
        importlib.import_module(module_name)


def test_agent_tasks_split_modules_expose_behavior_contracts_directly():
    import app.services.agent.task_findings as task_findings

    assert task_findings.AgentFindingResponse is not None
    assert callable(task_findings._build_core_audit_exclude_patterns)
    assert callable(task_findings._is_core_ignored_path)
    assert task_findings._is_core_ignored_path("tests/test_api.py") is True
    assert task_findings._is_core_ignored_path("src/api.py") is False
    assert task_findings._save_findings is not None


def test_agent_tasks_scope_filters_shell_has_been_retired():
    assert not (PROJECT_ROOT / "app/services/agent/scope_filters.py").exists()


def test_agent_tasks_api_router_shell_has_been_retired():
    assert not (PROJECT_ROOT / "app/api/v1/api.py").exists()


def test_agent_tasks_facade_shell_has_been_retired():
    assert not (PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks.py").exists()


def test_agent_tasks_tool_runtime_shell_has_been_retired():
    assert not (PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_tool_runtime.py").exists()


def test_agent_tasks_bootstrap_shell_has_been_retired():
    assert not (PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_bootstrap.py").exists()


def test_agent_tasks_contracts_shell_has_been_retired():
    assert not (PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_contracts.py").exists()


def test_agent_tasks_findings_shell_has_been_retired():
    assert not (PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_findings.py").exists()
