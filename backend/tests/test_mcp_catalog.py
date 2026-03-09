from app.api.v1.endpoints.config import _sanitize_mcp_config
from app.services.agent.mcp.catalog import build_mcp_catalog


def test_mcp_catalog_only_exposes_stdio_core_mcps(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_COMMAND", "python3")
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_COMMAND", "python3")

    catalog = build_mcp_catalog(mcp_enabled=True)
    catalog_by_id = {item["id"]: item for item in catalog}

    assert set(catalog_by_id.keys()) == {"filesystem", "code_index"}
    assert all(item.get("type") == "mcp-server" for item in catalog)
    assert all(item.get("runtime_mode") == "stdio_only" for item in catalog)
    assert catalog_by_id["filesystem"].get("includedSkills") == ["read_file"]
    assert catalog_by_id["filesystem"].get("verificationTools") == ["read_file"]
    assert catalog_by_id["code_index"].get("includedSkills") == []
    assert catalog_by_id["code_index"].get("verificationTools") == []
    assert "sequentialthinking" not in catalog_by_id
    assert all(item.get("backend") is None for item in catalog)
    assert all(item.get("sandbox") is None for item in catalog)


def test_sanitize_mcp_config_ignores_client_runtime_overrides(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MCP_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_COMMAND", "python3")
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_COMMAND", "python3")

    sanitized = _sanitize_mcp_config(
        {
            "enabled": False,
            "preferMcp": False,
            "catalog": [{"id": "fake-item", "name": "fake"}],
            "runtimePolicy": {
                "filesystem": {
                    "runtime_mode": "backend_then_sandbox",
                    "backend_enabled": True,
                    "sandbox_enabled": True,
                },
                "sequentialthinking": {
                    "runtime_mode": "backend_only",
                    "backend_enabled": True,
                    "sandbox_enabled": False,
                },
            },
        }
    )

    assert sanitized["enabled"] is True
    assert sanitized["preferMcp"] is True
    assert {item["id"] for item in sanitized["catalog"]} == {"filesystem", "code_index"}
    assert sanitized["runtimePolicy"] == {
        "default_mode": "stdio_only",
        "filesystem": {"runtime_mode": "stdio_only", "enabled": True},
        "code_index": {"runtime_mode": "stdio_only", "enabled": True},
    }


def test_sanitize_mcp_config_skill_availability_only_contains_scan_core(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_COMMAND", "python3")
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_COMMAND", "python3")

    sanitized = _sanitize_mcp_config({})
    skill_availability = sanitized["skillAvailability"]

    expected_public_ids = {
        "read_file",
        "search_code",
        "list_files",
        "extract_function",
        "locate_enclosing_function",
        "smart_scan",
        "quick_audit",
        "pattern_match",
        "dataflow_analysis",
        "controlflow_analysis_light",
        "logic_authz_analysis",
        "run_code",
        "sandbox_exec",
        "verify_vulnerability",
        "create_vulnerability_report",
        "think",
        "reflect",
    }
    assert expected_public_ids.issubset(skill_availability.keys())
    assert "qmd_query" not in skill_availability
    assert "sequential_thinking" not in skill_availability
    assert "skill_lookup" not in skill_availability
    assert skill_availability["search_code"]["source"] == "local"
    assert skill_availability["search_code"]["reason"] == "ready"
    assert skill_availability["list_files"]["source"] == "local"
    assert skill_availability["extract_function"]["source"] == "local"
