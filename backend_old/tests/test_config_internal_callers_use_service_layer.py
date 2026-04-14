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
