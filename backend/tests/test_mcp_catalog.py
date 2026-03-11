from app.api.v1.endpoints.config import _sanitize_mcp_config
from app.services.agent.mcp.catalog import build_mcp_catalog


def test_mcp_catalog_only_exposes_stdio_core_mcps(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_COMMAND", "python3")
    monkeypatch.setattr("app.core.config.settings.MCP_CODEBADGER_ENABLED", False)

    catalog = build_mcp_catalog(mcp_enabled=True)
    catalog_by_id = {item["id"]: item for item in catalog}

    assert set(catalog_by_id.keys()) == {"filesystem"}
    assert all(item.get("type") == "mcp-server" for item in catalog)
    assert all(item.get("runtime_mode") == "stdio_only" for item in catalog)
    assert catalog_by_id["filesystem"].get("includedSkills") == ["read_file"]
    assert catalog_by_id["filesystem"].get("verificationTools") == ["read_file"]
    assert "code_index" not in catalog_by_id
    assert "sequentialthinking" not in catalog_by_id
    assert all(item.get("backend") is None for item in catalog)
    assert all(item.get("sandbox") is None for item in catalog)


def test_mcp_catalog_exposes_codebadger_as_not_ready_when_endpoint_unreachable(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_COMMAND", "python3")
    monkeypatch.setattr("app.core.config.settings.MCP_CODEBADGER_ENABLED", True)
    monkeypatch.setattr(
        "app.core.config.settings.MCP_CODEBADGER_BACKEND_URL",
        "http://codebadger-mcp:4242/mcp",
    )
    monkeypatch.setattr(
        "app.services.agent.mcp.catalog.probe_mcp_endpoint_readiness",
        lambda *args, **kwargs: (False, "healthcheck_failed"),
    )

    catalog = build_mcp_catalog(mcp_enabled=True)
    catalog_by_id = {item["id"]: item for item in catalog}

    assert set(catalog_by_id.keys()) == {"filesystem", "codebadger"}
    assert catalog_by_id["codebadger"]["runtime_mode"] == "backend_only"
    assert catalog_by_id["codebadger"]["backend"] == {
        "enabled": True,
        "startup_ready": False,
        "startup_error": "healthcheck_failed",
    }
    assert catalog_by_id["codebadger"]["source"] == "https://github.com/Lekssays/codebadger"


def test_sanitize_mcp_config_ignores_client_runtime_overrides(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MCP_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_COMMAND", "python3")

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
    assert {item["id"] for item in sanitized["catalog"]} == {"filesystem"}
    assert sanitized["runtimePolicy"] == {
        "default_mode": "stdio_only",
        "filesystem": {"runtime_mode": "stdio_only", "enabled": True},
    }


def test_sanitize_mcp_config_skill_availability_only_contains_scan_core(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_COMMAND", "python3")

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
    assert skill_availability["locate_enclosing_function"]["source"] == "local"
