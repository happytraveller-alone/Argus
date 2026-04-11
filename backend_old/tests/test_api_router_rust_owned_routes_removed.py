from app.api.v1.api import api_router


def test_api_router_excludes_rust_owned_route_modules():
    endpoint_modules = {
        getattr(route.endpoint, "__module__", "")
        for route in api_router.routes
        if hasattr(route, "endpoint")
    }

    rust_owned_modules = {
        "app.api.v1.endpoints.search",
        "app.api.v1.endpoints.skills",
        "app.api.v1.endpoints.projects_crud",
        "app.api.v1.endpoints.projects_files",
        "app.api.v1.endpoints.projects_insights",
        "app.api.v1.endpoints.projects_transfer",
        "app.api.v1.endpoints.projects_uploads",
    }

    assert endpoint_modules.isdisjoint(rust_owned_modules)

    remaining_python_modules = {
        "app.api.v1.endpoints.config",
        "app.api.v1.endpoints.members",
        "app.api.v1.endpoints.prompts",
        "app.api.v1.endpoints.rules",
        "app.api.v1.endpoints.agent_tasks_access",
        "app.api.v1.endpoints.static_tasks_cache",
    }

    assert remaining_python_modules.intersection(endpoint_modules)
