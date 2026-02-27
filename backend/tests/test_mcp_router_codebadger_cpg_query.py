from app.services.agent.mcp.router import MCPToolRouter


def test_router_maps_extract_function_new_contract_to_symbol_name_and_symbol():
    router = MCPToolRouter()
    route = router.route(
        "extract_function",
        {
            "code": "int validate_access(User* user) { return user != NULL; }",
            "file_name": "authz.c",
            "file_path": "src/authz.c",
            "line": 12,
        },
    )

    assert route is not None
    assert route.adapter_name == "code_index"
    assert route.mcp_tool_name == "get_symbol_body"
    assert route.arguments.get("path") == "src/authz.c"
    assert route.arguments.get("symbol_name") == "validate_access"
    assert route.arguments.get("symbol") == "validate_access"
    assert route.arguments.get("line") == 12
    assert route.arguments.get("line_start") == 12
    assert "code" not in route.arguments
    assert "file_name" not in route.arguments


def test_router_maps_extract_function_legacy_function_name_for_compatibility():
    router = MCPToolRouter()
    route = router.route(
        "extract_function",
        {
            "file_path": "src/authz.c",
            "function_name": "validate_access",
        },
    )

    assert route is not None
    assert route.adapter_name == "code_index"
    assert route.mcp_tool_name == "get_symbol_body"
    assert route.arguments.get("path") == "src/authz.c"
    assert route.arguments.get("symbol_name") == "validate_access"
    assert route.arguments.get("symbol") == "validate_access"
    assert "function_name" not in route.arguments


def test_router_maps_reasoning_alias_and_canonical_to_sequentialthinking():
    router = MCPToolRouter()

    alias_route = router.route(
        "reasoning_trace",
        {"goal": "startup_probe", "step_index": 1},
    )
    canonical_route = router.route(
        "sequentialthinking",
        {"thought": "startup_probe", "thoughtNumber": 1, "totalThoughts": 1},
    )

    assert alias_route is not None
    assert alias_route.adapter_name == "sequentialthinking"
    assert alias_route.mcp_tool_name == "sequentialthinking"
    assert alias_route.arguments.get("thought") == "startup_probe"
    assert alias_route.arguments.get("thoughtNumber") == 1
    assert alias_route.arguments.get("totalThoughts") >= 1

    assert canonical_route is not None
    assert canonical_route.adapter_name == "sequentialthinking"
    assert canonical_route.mcp_tool_name == "sequentialthinking"
    assert canonical_route.arguments.get("thought") == "startup_probe"
