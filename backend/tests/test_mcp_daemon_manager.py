from __future__ import annotations

from types import SimpleNamespace

from app.services.agent.mcp.daemon_manager import (
    MCPDaemonManager,
    MCPDaemonSpec,
    get_default_filesystem_daemon_url,
    get_default_sequential_daemon_url,
    resolve_filesystem_backend_url,
    resolve_sequential_backend_url,
)


class _FakeProcess:
    def __init__(self, cmd):
        self.cmd = list(cmd)
        self.pid = 12345
        self._terminated = False
        self._killed = False

    def poll(self):
        return 0 if self._terminated else None

    def terminate(self):
        self._terminated = True

    def wait(self, timeout=None):
        self._terminated = True
        return 0

    def kill(self):
        self._killed = True
        self._terminated = True


def _build_settings():
    return SimpleNamespace(
        MCP_DAEMON_AUTOSTART=True,
        MCP_DAEMON_LOG_DIR="/tmp/deepaudit/mcp-daemons",
        MCP_FILESYSTEM_DAEMON_HOST="127.0.0.1",
        MCP_FILESYSTEM_DAEMON_PORT=8770,
        MCP_FILESYSTEM_DAEMON_COMMAND="fastmcp",
        MCP_FILESYSTEM_DAEMON_ARGS="",
        MCP_FILESYSTEM_DAEMON_ALLOWED_DIRS="/tmp,/app",
        MCP_FILESYSTEM_DAEMON_SOURCE_DIR="/app/mcp-src/filesystem",
        MCP_FILESYSTEM_DAEMON_STARTUP_TIMEOUT_SECONDS=10,
        MCP_CODE_INDEX_DAEMON_HOST="127.0.0.1",
        MCP_CODE_INDEX_DAEMON_PORT=8765,
        MCP_CODE_INDEX_DAEMON_COMMAND="code-index-mcp",
        MCP_CODE_INDEX_DAEMON_ARGS="--transport streamable-http --host 127.0.0.1",
        MCP_CODE_INDEX_DAEMON_INDEXER_PATH="/app/data/mcp/code-index",
        MCP_CODE_INDEX_DAEMON_SOURCE_DIR="/app/mcp-src/code-index-mcp",
        MCP_CODE_INDEX_DAEMON_STARTUP_TIMEOUT_SECONDS=10,
        MCP_SEQUENTIAL_THINKING_DAEMON_HOST="127.0.0.1",
        MCP_SEQUENTIAL_THINKING_DAEMON_PORT=8771,
        MCP_SEQUENTIAL_THINKING_DAEMON_COMMAND="node",
        MCP_SEQUENTIAL_THINKING_DAEMON_ARGS="dist/index.js --transport streamable-http --port 8771",
        MCP_SEQUENTIAL_THINKING_DAEMON_SOURCE_DIR="/app/mcp-src/sequential-thinking",
        MCP_SEQUENTIAL_THINKING_DAEMON_STARTUP_TIMEOUT_SECONDS=10,
        MCP_SEQUENTIAL_THINKING_FORCE_STDIO=False,
        MCP_QMD_DAEMON_HOST="127.0.0.1",
        MCP_QMD_DAEMON_PORT=8181,
        MCP_QMD_DAEMON_COMMAND="node",
        MCP_QMD_DAEMON_ARGS="dist/index.js mcp --transport streamable-http --port 8181",
        MCP_QMD_DAEMON_SOURCE_DIR="/app/mcp-src/qmd",
        MCP_QMD_DAEMON_STARTUP_TIMEOUT_SECONDS=10,
        MCP_FILESYSTEM_BACKEND_URL="http://127.0.0.1:8770/mcp",
        MCP_CODE_INDEX_BACKEND_URL="http://127.0.0.1:8765/mcp",
        MCP_SEQUENTIAL_THINKING_BACKEND_URL="http://127.0.0.1:8771/mcp",
        MCP_QMD_BACKEND_URL="http://127.0.0.1:8181/mcp",
        QMD_DATA_DIR="/tmp/deepaudit/qmd",
    )


def test_build_specs_contains_filesystem_code_index_sequential_and_qmd(tmp_path):
    settings = _build_settings()
    manager = MCPDaemonManager()

    specs = manager.build_specs(settings, project_root=str(tmp_path))
    by_name = {spec.name: spec for spec in specs}

    assert {"filesystem", "code_index", "sequentialthinking", "qmd"} == set(by_name.keys())
    assert by_name["filesystem"].command == "fastmcp"
    assert by_name["filesystem"].cwd == "/app/mcp-src/filesystem"
    assert by_name["filesystem"].url == "http://127.0.0.1:8770/mcp"
    assert by_name["filesystem"].args == []
    assert by_name["filesystem"].env.get("MCP_FILESYSTEM_ALLOWED_DIRS") == "/tmp,/app"
    assert "--indexer-path" in by_name["code_index"].args
    assert by_name["sequentialthinking"].cwd == "/app/mcp-src/sequential-thinking"
    assert by_name["sequentialthinking"].url == "http://127.0.0.1:8771/mcp"
    assert "--transport" in by_name["sequentialthinking"].args
    assert "--port" in by_name["sequentialthinking"].args
    assert "8771" in by_name["sequentialthinking"].args
    assert by_name["qmd"].command == "node"
    assert by_name["qmd"].cwd == "/app/mcp-src/qmd"
    assert by_name["qmd"].args[:2] == ["dist/index.js", "mcp"]
    assert "--transport" in by_name["qmd"].args
    assert "streamable-http" in by_name["qmd"].args
    assert by_name["qmd"].url == "http://localhost:8181/mcp"


def test_build_specs_skips_sequential_when_force_stdio_enabled(tmp_path):
    settings = _build_settings()
    settings.MCP_SEQUENTIAL_THINKING_FORCE_STDIO = True
    manager = MCPDaemonManager()

    specs = manager.build_specs(settings, project_root=str(tmp_path))
    by_name = {spec.name: spec for spec in specs}

    assert {"filesystem", "code_index", "qmd"} == set(by_name.keys())
    assert "sequentialthinking" not in by_name


def test_filesystem_fallback_command_drops_dist_entry():
    manager = MCPDaemonManager()
    spec = MCPDaemonSpec(
        name="filesystem",
        url="http://127.0.0.1:8770/mcp",
        command="fastmcp",
        args=["run", "/tmp/filesystem.proxy.json", "--transport", "streamable-http"],
        fallback_commands=[["mcp-server-filesystem"]],
    )

    candidates = list(manager._command_candidates(spec))
    assert candidates[0][0].endswith("fastmcp")
    assert candidates[0][1] == "run"
    assert candidates[1][:2] == ["mcp-server-filesystem", "run"]


def test_resolve_filesystem_backend_url_prefers_explicit():
    settings = _build_settings()
    settings.MCP_DAEMON_AUTOSTART = True
    settings.MCP_FILESYSTEM_BACKEND_URL = "http://127.0.0.1:9770/mcp"

    assert resolve_filesystem_backend_url(settings) == "http://127.0.0.1:9770/mcp"


def test_resolve_filesystem_backend_url_defaults_when_autostart_enabled():
    settings = _build_settings()
    settings.MCP_DAEMON_AUTOSTART = True
    settings.MCP_FILESYSTEM_BACKEND_URL = ""

    assert resolve_filesystem_backend_url(settings) == get_default_filesystem_daemon_url(settings)


def test_resolve_filesystem_backend_url_empty_when_autostart_disabled():
    settings = _build_settings()
    settings.MCP_DAEMON_AUTOSTART = False
    settings.MCP_FILESYSTEM_BACKEND_URL = ""

    assert resolve_filesystem_backend_url(settings) == ""


def test_resolve_sequential_backend_url_prefers_explicit():
    settings = _build_settings()
    settings.MCP_DAEMON_AUTOSTART = True
    settings.MCP_SEQUENTIAL_THINKING_BACKEND_URL = "http://127.0.0.1:9771/mcp"

    assert resolve_sequential_backend_url(settings) == "http://127.0.0.1:9771/mcp"


def test_resolve_sequential_backend_url_defaults_when_autostart_enabled():
    settings = _build_settings()
    settings.MCP_DAEMON_AUTOSTART = True
    settings.MCP_SEQUENTIAL_THINKING_BACKEND_URL = ""

    assert resolve_sequential_backend_url(settings) == get_default_sequential_daemon_url(settings)


def test_resolve_sequential_backend_url_empty_when_force_stdio_enabled():
    settings = _build_settings()
    settings.MCP_DAEMON_AUTOSTART = True
    settings.MCP_SEQUENTIAL_THINKING_BACKEND_URL = "http://127.0.0.1:9771/mcp"
    settings.MCP_SEQUENTIAL_THINKING_FORCE_STDIO = True

    assert resolve_sequential_backend_url(settings) == ""


def test_prepare_filesystem_source_requires_fastmcp(tmp_path, monkeypatch):
    manager = MCPDaemonManager()
    spec = MCPDaemonSpec(
        name="filesystem",
        url="http://127.0.0.1:8770/mcp",
        command="fastmcp",
        args=[],
        cwd=str(tmp_path / "filesystem-src"),
    )

    monkeypatch.setattr(
        "app.services.agent.mcp.daemon_manager._resolve_executable",
        lambda command: None if command == "fastmcp" else "/usr/bin/node",
    )

    prepared, reason = manager._prepare_spec(spec)
    assert prepared is False
    assert reason == "filesystem_fastmcp_missing"


def test_prepare_filesystem_spec_generates_fastmcp_proxy(tmp_path, monkeypatch):
    manager = MCPDaemonManager()
    source_dir = tmp_path / "filesystem-src"
    source_dir.mkdir(parents=True, exist_ok=True)
    spec = MCPDaemonSpec(
        name="filesystem",
        url="http://127.0.0.1:8770/mcp",
        command="fastmcp",
        args=[],
        cwd=str(source_dir),
        env={"MCP_FILESYSTEM_ALLOWED_DIRS": "/tmp,/app"},
        log_file=str(tmp_path / "filesystem.log"),
    )

    def _fake_resolve(command: str):
        mapping = {
            "fastmcp": "/usr/local/bin/fastmcp",
            "mcp-server-filesystem": "/usr/local/bin/mcp-server-filesystem",
        }
        return mapping.get(command)

    monkeypatch.setattr(
        "app.services.agent.mcp.daemon_manager._resolve_executable",
        _fake_resolve,
    )

    prepared, reason = manager._prepare_spec(spec)
    assert prepared is True
    assert reason == "ready:binary"
    assert spec.command == "/usr/local/bin/fastmcp"
    assert spec.args[:3] == ["run", str(tmp_path / "filesystem.proxy.json"), "--transport"]
    proxy_payload = (tmp_path / "filesystem.proxy.json").read_text(encoding="utf-8")
    assert "mcp-server-filesystem" in proxy_payload
    assert "/tmp" in proxy_payload
    assert "/app" in proxy_payload


def test_prepare_sequential_source_requires_package_json(tmp_path):
    manager = MCPDaemonManager()
    source_dir = tmp_path / "sequential-src"
    source_dir.mkdir(parents=True, exist_ok=True)
    spec = MCPDaemonSpec(
        name="sequentialthinking",
        url="http://127.0.0.1:8771/mcp",
        command="node",
        args=["dist/index.js", "--transport", "streamable-http", "--port", "8771"],
        cwd=str(source_dir),
    )

    prepared, reason = manager._prepare_spec(spec)
    assert prepared is False
    assert reason.startswith("sequentialthinking_package_json_missing:")


def test_prepare_qmd_spec_falls_back_to_local_cli(tmp_path, monkeypatch):
    manager = MCPDaemonManager()
    source_dir = tmp_path / "qmd-src"
    spec = MCPDaemonSpec(
        name="qmd",
        url="http://localhost:8181/mcp",
        command="node",
        args=["dist/index.js", "mcp", "--transport", "streamable-http", "--port", "8181"],
        cwd=str(source_dir),
    )

    monkeypatch.setattr(
        "app.services.agent.mcp.daemon_manager._resolve_executable",
        lambda command: "/usr/local/bin/qmd" if command == "qmd" else None,
    )

    prepared, reason = manager._prepare_spec(spec)
    assert prepared is True
    assert reason.startswith("ready_fallback_qmd_cli:")
    assert spec.command == "/usr/local/bin/qmd"
    assert spec.args[:2] == ["mcp", "--transport"]


def test_ensure_daemon_is_idempotent_when_endpoint_ready(monkeypatch):
    manager = MCPDaemonManager()
    spec = MCPDaemonSpec(
        name="code_index",
        url="http://127.0.0.1:8765/mcp",
        command="code-index-mcp",
        args=["--transport", "streamable-http"],
    )

    monkeypatch.setattr("app.services.agent.mcp.daemon_manager.MCPDaemonManager._endpoint_ready", lambda *_: True)

    result = manager.ensure_daemon(spec)
    assert result.ready is True
    assert result.started is False
    assert result.reason == "already_running"


def test_ensure_daemon_falls_back_when_primary_command_missing(monkeypatch, tmp_path):
    manager = MCPDaemonManager()
    source_dir = tmp_path / "code-index-src"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "pyproject.toml").write_text("[project]\nname='code-index-mcp'\nversion='0.0.0'\n", encoding="utf-8")
    spec = MCPDaemonSpec(
        name="code_index",
        url="http://127.0.0.1:8765/mcp",
        command="missing-code-index",
        args=["--transport", "streamable-http"],
        fallback_commands=[["/usr/local/bin/code-index-mcp"]],
        cwd=str(source_dir),
    )

    calls = []

    def _fake_popen(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[0] == "missing-code-index":
            raise FileNotFoundError("missing")
        return _FakeProcess(cmd)

    monkeypatch.setattr("app.services.agent.mcp.daemon_manager.subprocess.Popen", _fake_popen)
    monkeypatch.setattr("app.services.agent.mcp.daemon_manager.MCPDaemonManager._wait_ready", lambda *_: True)
    monkeypatch.setattr(
        "app.services.agent.mcp.daemon_manager.MCPDaemonManager._open_log_handle",
        lambda *_: (None, None),
    )

    result = manager.ensure_daemon(spec)
    assert result.ready is True
    assert result.started is True
    assert calls[0][0] == "missing-code-index"
    assert calls[1][0] == "/usr/local/bin/code-index-mcp"


def test_stop_all_terminates_managed_processes():
    manager = MCPDaemonManager()
    process = _FakeProcess(["qmd", "mcp", "--http"])
    manager._processes["qmd"] = process

    manager.stop_all()

    assert process._terminated is True
    assert manager._processes == {}
