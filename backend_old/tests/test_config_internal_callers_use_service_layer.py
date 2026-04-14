import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_HELPER_IMPORTS = (
    "ensure_scan_workspace",
    "ensure_scan_project_dir",
    "ensure_scan_output_dir",
    "ensure_scan_logs_dir",
    "ensure_scan_meta_dir",
    "cleanup_scan_workspace",
    "copy_project_tree_to_scan_dir",
)
SCAN_TRACKING_EXPORTS = {
    "_static_scan_process_lock",
    "_static_running_scan_processes",
    "_static_running_scan_containers",
    "_static_cancelled_scan_tasks",
    "_static_background_jobs",
    "_scan_task_key",
    "_register_static_background_job",
    "_pop_static_background_job",
    "_get_static_background_job",
    "_launch_static_background_job",
    "_shutdown_static_background_jobs",
    "_is_scan_task_cancelled",
    "_clear_scan_task_cancel",
    "_register_scan_container",
    "_pop_scan_container",
    "_stop_scan_container",
    "_request_scan_task_cancel",
    "_is_scan_process_active",
    "_terminate_scan_process",
    "_run_subprocess_with_tracking",
}


def test_internal_callers_no_longer_import_config_endpoint():
    caller_paths = [
        PROJECT_ROOT / "app/services/static_scan_runtime.py",
        PROJECT_ROOT / "app/services/agent/skill_test_runner.py",
    ]

    forbidden = "from app.api.v1.endpoints.config import _load_effective_user_config"
    required = "async def _load_effective_user_config("

    for path in caller_paths:
        content = path.read_text(encoding="utf-8")
        if path.name == "skill_test_runner.py":
            assert (
                "from app.api.v1.endpoints.config import (\n    _normalize_extracted_project_root,\n)"
                not in content
            ), "skill_test_runner.py still depends on config endpoint"
            assert (
                "def normalize_extracted_project_root(base_path: str) -> str:" in content
            ), "skill_test_runner.py should host normalize_extracted_project_root locally"
            continue

        assert forbidden not in content, f"{path.name} still depends on config endpoint"
        assert required in content, f"{path.name} should host _load_effective_user_config locally"


def test_static_scan_runtime_no_longer_imports_db_session_module():
    path = PROJECT_ROOT / "app/services/static_scan_runtime.py"
    content = path.read_text(encoding="utf-8")

    assert "from app.db.session import" not in content
    assert "async_session_factory" not in content
    assert "get_db" not in content


def test_bootstrap_callers_use_agent_scan_workspace_module():
    caller_paths = [
        PROJECT_ROOT / "app/services/agent/bootstrap/bandit.py",
        PROJECT_ROOT / "app/services/agent/bootstrap/opengrep.py",
        PROJECT_ROOT / "app/services/agent/bootstrap/phpstan.py",
        PROJECT_ROOT / "app/services/agent/bootstrap_gitleaks_runner.py",
    ]

    for path in caller_paths:
        content = path.read_text(encoding="utf-8")
        module = ast.parse(content, filename=str(path))
        import_from_nodes = [node for node in ast.walk(module) if isinstance(node, ast.ImportFrom)]

        required_nodes = [
            node
            for node in import_from_nodes
            if node.module == "app.services.agent.scan_workspace"
        ]
        assert required_nodes, f"{path.name} should import workspace helpers from agent.scan_workspace"

        forbidden_names = {
            alias.name
            for node in import_from_nodes
            if node.module == "app.services.static_scan_runtime"
            for alias in node.names
        }
        leaked_helpers = sorted(forbidden_names.intersection(WORKSPACE_HELPER_IMPORTS))
        assert not leaked_helpers, (
            f"{path.name} still imports workspace helpers from static_scan_runtime: "
            f"{', '.join(leaked_helpers)}"
        )


def test_static_scan_runtime_imports_scan_tracking_cluster_from_agent_module():
    path = PROJECT_ROOT / "app/services/static_scan_runtime.py"
    content = path.read_text(encoding="utf-8")
    module = ast.parse(content, filename=str(path))

    import_nodes = [node for node in ast.walk(module) if isinstance(node, ast.ImportFrom)]
    scan_tracking_imports = [
        node for node in import_nodes if node.module == "app.services.agent.scan_tracking"
    ]
    assert scan_tracking_imports, "static_scan_runtime.py should import scan tracking helpers"

    imported_names = {
        alias.name for node in scan_tracking_imports for alias in node.names if alias.name != "*"
    }
    missing_imports = sorted(SCAN_TRACKING_EXPORTS - imported_names)
    assert not missing_imports, (
        "static_scan_runtime.py should source the whole scan tracking cluster from "
        f"agent.scan_tracking: {', '.join(missing_imports)}"
    )

    for node in module.body:
        defined_name = getattr(node, "name", None)
        if defined_name in SCAN_TRACKING_EXPORTS:
            raise AssertionError(
                f"static_scan_runtime.py should not locally define {defined_name}; "
                "ownership belongs to agent.scan_tracking"
            )
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in SCAN_TRACKING_EXPORTS:
                    raise AssertionError(
                        f"static_scan_runtime.py should not locally assign {target.id}; "
                        "ownership belongs to agent.scan_tracking"
                    )
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id in SCAN_TRACKING_EXPORTS:
                raise AssertionError(
                    f"static_scan_runtime.py should not locally assign {target.id}; "
                    "ownership belongs to agent.scan_tracking"
                )
