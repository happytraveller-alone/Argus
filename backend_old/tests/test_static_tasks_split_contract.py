import importlib

from app.api.v1.endpoints import static_tasks


def test_static_tasks_split_modules_exist_and_aggregator_keeps_exports():
    module_names = [
        "app.api.v1.endpoints.static_tasks_shared",
        "app.api.v1.endpoints.static_tasks_opengrep",
        "app.api.v1.endpoints.static_tasks_opengrep_rules",
        "app.api.v1.endpoints.static_tasks_bandit",
        "app.api.v1.endpoints.static_tasks_phpstan",
        "app.api.v1.endpoints.static_tasks_cache",
    ]

    loaded_modules = [importlib.import_module(name) for name in module_names]

    assert all(hasattr(module, "router") or name.endswith("_shared") for module, name in zip(loaded_modules, module_names))
    assert hasattr(static_tasks, "router")
    assert hasattr(static_tasks, "_parse_opengrep_output")
    assert hasattr(static_tasks, "_parse_bandit_output_payload")
    assert hasattr(static_tasks, "_parse_phpstan_output_payload")


def test_static_tasks_router_keeps_split_route_prefixes():
    route_paths = {route.path for route in static_tasks.router.routes}

    assert "/tasks" in route_paths
    assert "/rules" in route_paths
    assert "/bandit/scan" in route_paths
    assert "/phpstan/scan" in route_paths
    assert "/cache/repo-stats" in route_paths
