from app.api.v1.endpoints.config import _sanitize_mcp_config
from app.services.agent.mcp.catalog import build_mcp_catalog


def test_mcp_catalog_contains_servers_and_skill_packs():
    catalog = build_mcp_catalog(mcp_enabled=True)
    ids = {item.get("id") for item in catalog}

    expected = {
        "filesystem",
        "code_index",
        "memory",
        "sequentialthinking",
        "qmd",
        "codebadger",
        "mcp-builder",
        "skill-creator",
        "planning-with-files",
        "superpowers",
    }
    assert expected.issubset(ids)


def test_sanitize_mcp_config_catalog_is_backend_read_only():
    sanitized = _sanitize_mcp_config(
        {
            "enabled": True,
            "preferMcp": True,
            "catalog": [{"id": "fake-item", "name": "fake"}],
        }
    )

    catalog = sanitized.get("catalog")
    assert isinstance(catalog, list)
    assert all(item.get("id") != "fake-item" for item in catalog)
    assert any(item.get("id") == "filesystem" for item in catalog)
