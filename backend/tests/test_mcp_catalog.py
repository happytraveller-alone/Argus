from app.api.v1.endpoints.config import _sanitize_mcp_config
from app.services.agent.mcp.catalog import build_mcp_catalog


def test_mcp_catalog_contains_mcp_servers_only(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MCP_DAEMON_AUTOSTART", False)
    catalog = build_mcp_catalog(mcp_enabled=True)
    ids = {item.get("id") for item in catalog}

    expected = {
        "filesystem",
        "code_index",
        "sequentialthinking",
    }
    assert expected.issubset(ids)
    assert all(item.get("type") == "mcp-server" for item in catalog)
    assert "mcp-builder" not in ids
    assert "skill-creator" not in ids
    assert "planning-with-files" not in ids
    assert "superpowers" not in ids

    catalog_by_id = {item["id"]: item for item in catalog if isinstance(item, dict) and item.get("id")}
    code_index_skills = set(catalog_by_id["code_index"].get("includedSkills") or [])
    assert "code_search" not in code_index_skills
    assert {"extract_function", "list_files", "locate_enclosing_function"}.issubset(
        code_index_skills
    )
    assert catalog_by_id["code_index"].get("verificationTools") == [
        "extract_function",
        "list_files",
        "locate_enclosing_function",
    ]

    assert catalog_by_id["sequentialthinking"].get("verificationTools") == [
        "sequential_thinking",
        "reasoning_trace",
    ]

    assert catalog_by_id["filesystem"].get("verificationTools") == [
        "read_file",
        "search_code",
    ]
    assert catalog_by_id["sequentialthinking"].get("required") is False


def test_sanitize_mcp_config_catalog_is_backend_read_only(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MCP_DAEMON_AUTOSTART", False)
    sanitized = _sanitize_mcp_config(
        {
            "enabled": True,
            "preferMcp": True,
            "catalog": [{"id": "fake-item", "name": "fake"}],
            "runtimePolicy": {
                "filesystem": {
                    "runtime_mode": "backend_then_sandbox",
                    "backend_enabled": True,
                    "sandbox_enabled": True,
                },
                "qmd": {
                    "runtime_mode": "backend_only",
                    "backend_enabled": True,
                    "sandbox_enabled": False,
                },
            },
        }
    )

    catalog = sanitized.get("catalog")
    assert isinstance(catalog, list)
    assert all(item.get("id") != "fake-item" for item in catalog)
    assert any(item.get("id") == "filesystem" for item in catalog)
    runtime_policy = sanitized.get("runtimePolicy") or {}
    filesystem_policy = runtime_policy.get("filesystem") or {}
    assert filesystem_policy == {
        "runtime_mode": "sandbox_only",
        "backend_enabled": False,
        "sandbox_enabled": True,
    }
    assert "qmd" not in runtime_policy


def test_catalog_sequential_falls_back_to_stdio_when_http_unreachable(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.mcp.catalog._http_endpoint_ready",
        lambda *_args, **_kwargs: (False, "healthcheck_failed:ConnectError@http://127.0.0.1:8771/health"),
    )
    monkeypatch.setattr("app.core.config.settings.MCP_DAEMON_AUTOSTART", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_SANDBOX_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_FORCE_STDIO", False)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_COMMAND", "python3")
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_SANDBOX_COMMAND", "python3")

    catalog = build_mcp_catalog(mcp_enabled=True)
    by_id = {item["id"]: item for item in catalog}
    sequential = by_id["sequentialthinking"]

    assert sequential["startup_ready"] is True
    assert sequential["backend"]["startup_ready"] is True
    assert sequential["sandbox"]["startup_ready"] is True
    assert str(sequential["backend"]["startup_error"]).startswith("http_unreachable_stdio_fallback")


def test_catalog_sequential_force_stdio_skips_http_probe(monkeypatch):
    def _no_http_probe(url, **_kwargs):
        if "8771" in str(url or ""):
            raise AssertionError("http probe should not be called")
        return True, None

    monkeypatch.setattr("app.core.config.settings.MCP_DAEMON_AUTOSTART", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_SANDBOX_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_FORCE_STDIO", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_COMMAND", "python3")
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_SANDBOX_COMMAND", "python3")
    monkeypatch.setattr(
        "app.services.agent.mcp.catalog.probe_mcp_endpoint_readiness",
        _no_http_probe,
    )

    catalog = build_mcp_catalog(mcp_enabled=True)
    by_id = {item["id"]: item for item in catalog}
    sequential = by_id["sequentialthinking"]

    assert sequential["startup_ready"] is True
    assert sequential["backend"]["startup_error"] is None
    assert sequential["sandbox"]["startup_error"] is None


def test_catalog_prefers_http_probe_for_filesystem_code_index_and_sequential(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.mcp.catalog.probe_mcp_endpoint_readiness",
        lambda *_args, **_kwargs: (True, None),
    )
    monkeypatch.setattr("app.core.config.settings.MCP_DAEMON_AUTOSTART", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_FORCE_STDIO", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_FORCE_STDIO", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_BACKEND_URL", "http://127.0.0.1:8111/mcp")
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_URL", "http://127.0.0.1:8112/mcp")
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_BACKEND_URL", "http://127.0.0.1:8121/mcp")
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_SANDBOX_URL", "http://127.0.0.1:8122/mcp")
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_BACKEND_URL", "http://127.0.0.1:8765/mcp")
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_SANDBOX_URL", "http://127.0.0.1:8765/mcp")
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_COMMAND", "missing-filesystem-command")
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_COMMAND", "missing-seq-command")
    monkeypatch.setattr("app.core.config.settings.MCP_CODE_INDEX_COMMAND", "missing-code-index-command")

    catalog = build_mcp_catalog(mcp_enabled=True)
    by_id = {item["id"]: item for item in catalog}

    assert by_id["filesystem"]["backend"]["startup_ready"] is True
    assert by_id["filesystem"]["sandbox"]["startup_ready"] is True
    assert by_id["sequentialthinking"]["backend"]["startup_ready"] is True
    assert by_id["sequentialthinking"]["sandbox"]["startup_ready"] is True
    assert by_id["code_index"]["backend"]["startup_ready"] is True
    assert by_id["code_index"]["sandbox"]["startup_ready"] is True


def test_catalog_filesystem_uses_daemon_default_url_when_explicit_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.mcp.catalog.probe_mcp_endpoint_readiness",
        lambda *_args, **_kwargs: (True, None),
    )
    monkeypatch.setattr("app.core.config.settings.MCP_DAEMON_AUTOSTART", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_FORCE_STDIO", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_BACKEND_URL", "")
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_URL", "")
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_DAEMON_HOST", "127.0.0.1")
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_DAEMON_PORT", 9770)

    catalog = build_mcp_catalog(mcp_enabled=True)
    by_id = {item["id"]: item for item in catalog}
    filesystem = by_id["filesystem"]

    assert filesystem["runtime_mode"] == "sandbox_only"
    assert filesystem["backend"]["startup_ready"] is True
    assert filesystem["sandbox"]["startup_ready"] is True


def test_catalog_sequential_uses_daemon_default_url_when_explicit_missing(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.mcp.catalog.probe_mcp_endpoint_readiness",
        lambda *_args, **_kwargs: (True, None),
    )
    monkeypatch.setattr("app.core.config.settings.MCP_DAEMON_AUTOSTART", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_SANDBOX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_FORCE_STDIO", False)
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_BACKEND_URL", "")
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_SANDBOX_URL", "")
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_DAEMON_HOST", "127.0.0.1")
    monkeypatch.setattr("app.core.config.settings.MCP_SEQUENTIAL_THINKING_DAEMON_PORT", 9771)

    catalog = build_mcp_catalog(mcp_enabled=True)
    by_id = {item["id"]: item for item in catalog}
    sequential = by_id["sequentialthinking"]

    assert sequential["backend"]["startup_ready"] is True
    assert sequential["sandbox"]["startup_ready"] is True


def test_catalog_disabled_domain_does_not_mark_startup_failed(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.mcp.catalog.probe_mcp_endpoint_readiness",
        lambda *_args, **_kwargs: (True, None),
    )
    monkeypatch.setattr("app.core.config.settings.MCP_DAEMON_AUTOSTART", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_FORCE_STDIO", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_BACKEND_URL", "http://127.0.0.1:8765/mcp")
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_URL", "")

    catalog = build_mcp_catalog(mcp_enabled=True)
    by_id = {item["id"]: item for item in catalog}
    filesystem = by_id["filesystem"]

    assert filesystem["backend"]["enabled"] is True
    assert filesystem["backend"]["startup_ready"] is True
    assert filesystem["sandbox"]["enabled"] is False
    assert filesystem["sandbox"]["startup_error"] == "disabled"
    assert filesystem["startup_ready"] is True


def test_catalog_filesystem_force_stdio_ignores_http_connect_error(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent.mcp.catalog._http_endpoint_ready",
        lambda *_args, **_kwargs: (False, "healthcheck_failed:ConnectError@http://127.0.0.1:8770/health"),
    )
    monkeypatch.setattr("app.core.config.settings.MCP_DAEMON_AUTOSTART", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_FORCE_STDIO", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_ENABLED", False)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_COMMAND", "python3")
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_BACKEND_URL", "http://127.0.0.1:8770/mcp")
    monkeypatch.setattr("app.core.config.settings.MCP_FILESYSTEM_SANDBOX_URL", "http://127.0.0.1:8770/mcp")

    catalog = build_mcp_catalog(mcp_enabled=True)
    by_id = {item["id"]: item for item in catalog}
    filesystem = by_id["filesystem"]

    assert filesystem["startup_ready"] is True
    assert filesystem["sandbox"]["startup_ready"] is True
    assert filesystem["sandbox"]["startup_error"] is None
