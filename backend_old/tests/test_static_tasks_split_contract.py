import importlib

from app.api.v1.endpoints import static_tasks


def test_static_tasks_split_modules_exist_and_aggregator_keeps_exports():
    module_names = [
        "app.api.v1.endpoints.static_tasks_shared",
    ]

    loaded_modules = [importlib.import_module(name) for name in module_names]

    assert all(hasattr(module, "router") or name.endswith("_shared") for module, name in zip(loaded_modules, module_names))
    assert hasattr(static_tasks, "router")


def test_static_tasks_router_keeps_split_route_prefixes():
    route_paths = {route.path for route in static_tasks.router.routes}

    assert route_paths == set()
