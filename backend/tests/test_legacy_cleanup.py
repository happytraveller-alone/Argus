import importlib



def test_legacy_mcp_and_skill_exports_removed():
    mcp_module = importlib.import_module("app.services.agent.mcp")
    tools_module = importlib.import_module("app.services.agent.tools")
    skills_module = importlib.import_module("app.services.agent.skills")
    config_module = importlib.import_module("app.api.v1.endpoints.config")
    runtime_module = importlib.import_module("app.services.agent.mcp.runtime")

    for name in [
        "FastMCPHttpAdapter",
        "LocalMCPProxyAdapter",
        "QmdLazyIndexAdapter",
        "MCPDaemonManager",
        "resolve_qmd_backend_url",
        "resolve_sequential_backend_url",
    ]:
        assert name not in getattr(mcp_module, "__all__", [])

    for name in [
        "SkillLookupTool",
        "SandboxHttpTool",
        "PhpTestTool",
        "PythonTestTool",
        "JavaScriptTestTool",
        "JavaTestTool",
        "GoTestTool",
        "RubyTestTool",
        "ShellTestTool",
        "UniversalCodeTestTool",
        "CommandInjectionTestTool",
        "SqlInjectionTestTool",
        "XssTestTool",
        "PathTraversalTestTool",
        "SstiTestTool",
        "DeserializationTestTool",
        "UniversalVulnTestTool",
    ]:
        assert name not in getattr(tools_module, "__all__", [])

    assert getattr(skills_module, "__all__", []) == []
    assert not hasattr(config_module, "verify_qmd_cli_runtime")
    assert not hasattr(config_module, "verify_mcp_runtime")
    assert not hasattr(config_module, "list_mcp_tools_runtime")
    assert not hasattr(config_module, "call_mcp_tool_runtime")
    assert not hasattr(runtime_module.MCPRuntime, "register_local_tool")
    assert not hasattr(runtime_module.MCPRuntime, "register_local_tools")
