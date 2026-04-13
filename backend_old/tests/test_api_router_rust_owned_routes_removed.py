from pathlib import Path

from app.api.v1.api import api_router


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_api_router_excludes_rust_owned_route_modules():
    endpoint_modules = {
        getattr(route.endpoint, "__module__", "")
        for route in api_router.routes
        if hasattr(route, "endpoint")
    }

    rust_owned_modules = {
        "app.api.v1.endpoints.config",
        "app.api.v1.endpoints.members",
        "app.api.v1.endpoints.projects",
        "app.api.v1.endpoints.search",
        "app.api.v1.endpoints.skills",
        "app.api.v1.endpoints.prompts",
        "app.api.v1.endpoints.rules",
        "app.api.v1.endpoints.projects_crud",
        "app.api.v1.endpoints.projects_files",
        "app.api.v1.endpoints.projects_insights",
        "app.api.v1.endpoints.projects_transfer",
        "app.api.v1.endpoints.projects_uploads",
        "app.api.v1.endpoints.users",
    }

    assert endpoint_modules.isdisjoint(rust_owned_modules)

    assert endpoint_modules == set()


def test_legacy_config_endpoint_module_has_been_retired():
    config_path = PROJECT_ROOT / "app/api/v1/endpoints/config.py"
    assert not config_path.exists()


def test_legacy_api_deps_module_has_been_retired():
    deps_path = PROJECT_ROOT / "app/api/deps.py"
    assert not deps_path.exists()


def test_legacy_static_tasks_facade_module_has_been_retired():
    static_tasks_path = PROJECT_ROOT / "app/api/v1/endpoints/static_tasks.py"
    assert not static_tasks_path.exists()


def test_legacy_static_scan_runtime_endpoint_module_has_been_retired():
    runtime_helpers_path = PROJECT_ROOT / "app/api/v1/endpoints" / "_".join(
        ["static", "tasks", "shared.py"]
    )
    assert not runtime_helpers_path.exists()


def test_legacy_init_db_module_has_been_retired():
    init_db_path = PROJECT_ROOT / "app/db/init_db.py"
    assert not init_db_path.exists()


def test_legacy_scan_path_db_helper_module_has_been_retired():
    retired_helper_path = PROJECT_ROOT / "app/db" / "_".join(["static", "finding_paths.py"])
    assert not retired_helper_path.exists()


def test_legacy_agent_tasks_execution_module_has_been_retired():
    execution_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_execution.py"
    assert not execution_path.exists()


def test_legacy_agent_tasks_runtime_module_has_been_retired():
    runtime_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_runtime.py"
    assert not runtime_path.exists()


def test_legacy_agent_tasks_access_module_has_been_retired():
    access_path = PROJECT_ROOT / "app/api/v1/endpoints/agent_tasks_access.py"
    assert not access_path.exists()


def test_legacy_project_metrics_service_module_has_been_retired():
    metrics_path = PROJECT_ROOT / "app/services/project_metrics.py"
    assert not metrics_path.exists()


def test_legacy_zip_cache_manager_has_been_retired():
    cache_path = PROJECT_ROOT / "app/services/zip_cache_manager.py"
    assert not cache_path.exists()


def test_legacy_search_service_has_been_retired():
    search_service_path = PROJECT_ROOT / "app/services/search_service.py"
    assert not search_service_path.exists()


def test_legacy_report_generator_service_has_been_retired():
    report_generator_path = PROJECT_ROOT / "app/services/report_generator.py"
    assert not report_generator_path.exists()


def test_legacy_runner_preflight_service_has_been_retired():
    runner_preflight_path = PROJECT_ROOT / "app/services/runner_preflight.py"
    assert not runner_preflight_path.exists()
