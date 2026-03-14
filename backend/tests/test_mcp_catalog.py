from app.api.v1.endpoints.config import _sanitize_mcp_config
from app.services.agent.mcp.catalog import build_mcp_catalog


def test_mcp_catalog_only_exposes_stdio_core_mcps(monkeypatch):
    catalog = build_mcp_catalog(mcp_enabled=True)

    assert catalog == []


def test_mcp_catalog_ignores_unrecognized_runtime_policy_entries(monkeypatch):
    catalog = build_mcp_catalog(mcp_enabled=True)
    assert catalog == []


def test_sanitize_mcp_config_ignores_client_runtime_overrides(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MCP_ENABLED", True)

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
                "legacy_backend": {
                    "runtime_mode": "backend_only",
                    "backend_enabled": True,
                    "sandbox_enabled": False,
                },
            },
        }
    )

    assert sanitized["enabled"] is True
    assert sanitized["preferMcp"] is True
    assert sanitized["runtimePolicy"] == {
        "default_mode": "stdio_only",
    }
    assert sanitized["catalog"] == []
    assert sanitized["deprecatedConfigs"]["filesystem"]["ignored"] is True
    assert sanitized["deprecatedConfigs"]["filesystem"]["deprecated"] is True


def test_sanitize_mcp_config_skill_availability_only_contains_scan_core(monkeypatch):
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
    assert skill_availability["read_file"]["source"] == "local"
    assert skill_availability["read_file"]["reason"] == "ready"
    assert skill_availability["search_code"]["source"] == "local"
    assert skill_availability["search_code"]["reason"] == "ready"
    assert skill_availability["list_files"]["source"] == "local"
    assert skill_availability["extract_function"]["source"] == "local"
    assert skill_availability["locate_enclosing_function"]["source"] == "local"
