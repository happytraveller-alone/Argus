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

    remaining_python_modules = {
        "app.api.v1.endpoints.agent_tasks_routes_tasks",
        "app.api.v1.endpoints.agent_tasks_routes_results",
        "app.api.v1.endpoints.agent_tasks_reporting",
    }

    assert remaining_python_modules.issubset(endpoint_modules)


def test_legacy_config_endpoint_module_has_been_retired():
    config_path = PROJECT_ROOT / "app/api/v1/endpoints/config.py"
    assert not config_path.exists()
