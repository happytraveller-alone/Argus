from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest


fastmcp_stub = types.ModuleType("fastmcp")
fastmcp_stub.Client = object
fastmcp_stub.FastMCP = object
fastmcp_client_stub = types.ModuleType("fastmcp.client")
fastmcp_transports_stub = types.ModuleType("fastmcp.client.transports")
fastmcp_transports_stub.StdioTransport = object
fastmcp_transports_stub.StreamableHttpTransport = object
docker_stub = types.ModuleType("docker")
docker_stub.from_env = lambda: None
docker_stub.errors = SimpleNamespace(
    DockerException=RuntimeError,
    ImageNotFound=type("ImageNotFound", (Exception,), {}),
)
git_stub = types.ModuleType("git")
git_stub.Repo = object
alembic_config_stub = types.ModuleType("alembic.config")
alembic_config_stub.Config = object
alembic_script_stub = types.ModuleType("alembic.script")
alembic_script_stub.ScriptDirectory = type(
    "ScriptDirectory",
    (),
    {"from_config": staticmethod(lambda *_args, **_kwargs: SimpleNamespace(get_current_head=lambda: "head"))},
)
sys.modules.setdefault("fastmcp", fastmcp_stub)
sys.modules.setdefault("fastmcp.client", fastmcp_client_stub)
sys.modules.setdefault("fastmcp.client.transports", fastmcp_transports_stub)
sys.modules.setdefault("docker", docker_stub)
sys.modules.setdefault("git", git_stub)
sys.modules.setdefault("alembic.config", alembic_config_stub)
sys.modules.setdefault("alembic.script", alembic_script_stub)


from app.services import runner_preflight


def test_get_configured_runner_preflight_specs_do_not_include_local_build_metadata() -> None:
    specs = runner_preflight.get_configured_runner_preflight_specs()

    assert specs
    for spec in specs:
        assert spec.image
        assert spec.command
        assert spec.dockerfile is None
        assert spec.build_context is None
        assert spec.build_args == {}


def test_ensure_runner_image_pulls_missing_cloud_image_without_local_build(monkeypatch):
    seen: dict[str, object] = {}

    class _FakeImages:
        def get(self, image):
            seen["get"] = image
            raise runner_preflight.DOCKER_NOT_FOUND("missing")

        def pull(self, image):
            seen["pull"] = image
            return object()

    runner_preflight._ensure_runner_image(SimpleNamespace(images=_FakeImages()), runner_preflight.RunnerPreflightSpec(
        name="bandit",
        image="ghcr.io/acme/vulhunter-bandit-runner:latest",
        command=["bandit", "--version"],
        timeout_seconds=10,
    ))

    assert seen == {
        "get": "ghcr.io/acme/vulhunter-bandit-runner:latest",
        "pull": "ghcr.io/acme/vulhunter-bandit-runner:latest",
    }


def test_ensure_runner_image_raises_when_cloud_pull_fails(monkeypatch):
    class _FakeImages:
        def get(self, _image):
            raise runner_preflight.DOCKER_NOT_FOUND("missing")

        def pull(self, _image):
            raise RuntimeError("registry denied")

    spec = runner_preflight.RunnerPreflightSpec(
        name="bandit",
        image="ghcr.io/acme/vulhunter-bandit-runner:latest",
        command=["bandit", "--version"],
        timeout_seconds=10,
    )

    with pytest.raises(RuntimeError, match="pull failed for bandit"):
        runner_preflight._ensure_runner_image(SimpleNamespace(images=_FakeImages()), spec)


def test_run_runner_preflight_sync_uses_explicit_command_and_removes_container(monkeypatch):
    seen: dict[str, object] = {}

    class _FakeContainer:
        id = "preflight-123"

        def wait(self, timeout=None):
            seen["wait_timeout"] = timeout
            return {"StatusCode": 0}

        def logs(self, stdout=True, stderr=False):
            if stdout and not stderr:
                return b"runner ok"
            if stderr and not stdout:
                return b""
            return b""

        def remove(self, force=False):
            seen["removed"] = force

    class _FakeContainers:
        def run(self, image, command=None, detach=None, auto_remove=None, environment=None, working_dir=None):
            seen["image"] = image
            seen["command"] = command
            seen["detach"] = detach
            seen["auto_remove"] = auto_remove
            seen["environment"] = environment
            seen["working_dir"] = working_dir
            return _FakeContainer()

    monkeypatch.setattr(
        runner_preflight.docker,
        "from_env",
        lambda: SimpleNamespace(containers=_FakeContainers()),
        raising=False,
    )
    monkeypatch.setattr(runner_preflight, "_ensure_runner_image", lambda *_args, **_kwargs: None)

    spec = runner_preflight.RunnerPreflightSpec(
        name="bandit",
        image="vulhunter/bandit-runner-local:latest",
        command=["bandit", "--version"],
        timeout_seconds=17,
    )

    result = runner_preflight.run_runner_preflight_sync(spec)

    assert result.success is True
    assert result.container_id == "preflight-123"
    assert result.exit_code == 0
    assert result.stdout == "runner ok"
    assert result.stderr == ""
    assert seen["image"] == "vulhunter/bandit-runner-local:latest"
    assert seen["command"] == ["bandit", "--version"]
    assert seen["detach"] is True
    assert seen["auto_remove"] is False
    assert seen["wait_timeout"] == 17
    assert seen["removed"] is True


def test_run_runner_preflight_sync_reports_failure_and_removes_container(monkeypatch):
    seen: dict[str, object] = {}

    class _FakeContainer:
        id = "preflight-failed"

        def wait(self, timeout=None):
            return {"StatusCode": 9}

        def logs(self, stdout=True, stderr=False):
            if stdout and not stderr:
                return b""
            if stderr and not stdout:
                return b"tool missing"
            return b""

        def remove(self, force=False):
            seen["removed"] = force

    class _FakeContainers:
        def run(self, image, command=None, detach=None, auto_remove=None, environment=None, working_dir=None):
            return _FakeContainer()

    monkeypatch.setattr(
        runner_preflight.docker,
        "from_env",
        lambda: SimpleNamespace(containers=_FakeContainers()),
        raising=False,
    )
    monkeypatch.setattr(runner_preflight, "_ensure_runner_image", lambda *_args, **_kwargs: None)

    spec = runner_preflight.RunnerPreflightSpec(
        name="phpstan",
        image="vulhunter/phpstan-runner-local:latest",
        command=["php", "/opt/phpstan/phpstan", "--version"],
        timeout_seconds=10,
    )

    result = runner_preflight.run_runner_preflight_sync(spec)

    assert result.success is False
    assert result.exit_code == 9
    assert result.stderr == "tool missing"
    assert result.error is not None
    assert seen["removed"] is True


def test_run_runner_preflight_sync_reports_timeout_and_removes_container(monkeypatch):
    seen: dict[str, object] = {}

    class _FakeContainer:
        id = "preflight-timeout"

        def wait(self, timeout=None):
            raise TimeoutError("timed out")

        def logs(self, stdout=True, stderr=False):
            return b""

        def remove(self, force=False):
            seen["removed"] = force

    class _FakeContainers:
        def run(self, image, command=None, detach=None, auto_remove=None, environment=None, working_dir=None):
            return _FakeContainer()

    monkeypatch.setattr(
        runner_preflight.docker,
        "from_env",
        lambda: SimpleNamespace(containers=_FakeContainers()),
        raising=False,
    )
    monkeypatch.setattr(runner_preflight, "_ensure_runner_image", lambda *_args, **_kwargs: None)

    spec = runner_preflight.RunnerPreflightSpec(
        name="flow-parser",
        image="vulhunter/flow-parser-runner-local:latest",
        command=["python3", "/opt/flow-parser/flow_parser_runner.py", "--help"],
        timeout_seconds=4,
    )

    result = runner_preflight.run_runner_preflight_sync(spec)

    assert result.success is False
    assert result.exit_code == 124
    assert "timed out" in (result.error or "")
    assert seen["removed"] is True


@pytest.mark.asyncio
async def test_run_configured_runner_preflights_obeys_strict_mode(monkeypatch):
    specs = [
        runner_preflight.RunnerPreflightSpec(
            name="bandit",
            image="vulhunter/bandit-runner-local:latest",
            command=["bandit", "--version"],
            timeout_seconds=10,
        )
    ]

    async def _fake_run(spec):
        return runner_preflight.RunnerPreflightResult(
            name=spec.name,
            image=spec.image,
            command=list(spec.command),
            timeout_seconds=spec.timeout_seconds,
            success=False,
            exit_code=7,
            stdout="",
            stderr="broken",
            error="broken",
            container_id="cid-1",
        )

    monkeypatch.setattr(runner_preflight, "get_configured_runner_preflight_specs", lambda: specs)
    monkeypatch.setattr(runner_preflight, "run_runner_preflight", _fake_run)
    monkeypatch.setattr(runner_preflight.settings, "RUNNER_PREFLIGHT_MAX_CONCURRENCY", 2)

    monkeypatch.setattr(runner_preflight.settings, "RUNNER_PREFLIGHT_STRICT", False)
    non_strict = await runner_preflight.run_configured_runner_preflights()
    assert len(non_strict) == 1
    assert non_strict[0].success is False

    monkeypatch.setattr(runner_preflight.settings, "RUNNER_PREFLIGHT_STRICT", True)
    with pytest.raises(RuntimeError):
        await runner_preflight.run_configured_runner_preflights()


@pytest.mark.asyncio
async def test_lifespan_runs_runner_preflight_before_agent_service_check(monkeypatch):
    from app import main

    order: list[str] = []

    async def _noop_async(*_args, **_kwargs):
        return None

    async def _fake_preflight():
        order.append("preflight")
        return []

    async def _fake_check_agent_services():
        order.append("agent_services")
        return []

    monkeypatch.setattr(main, "assert_database_schema_is_latest", _noop_async)
    monkeypatch.setattr(main, "recover_interrupted_tasks", _noop_async)
    monkeypatch.setattr(main, "cleanup_stale_yasa_processes", _noop_async)
    monkeypatch.setattr(main, "run_configured_runner_preflights", _fake_preflight)
    monkeypatch.setattr(main, "check_agent_services", _fake_check_agent_services)
    monkeypatch.setattr(main, "init_db", _noop_async)
    monkeypatch.setattr(main, "_run_daily_cache_cleanup", _noop_async)
    monkeypatch.setattr(main.GlobalRepoCacheManager, "set_cache_dir", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main,
        "AsyncSessionLocal",
        lambda: SimpleNamespace(
            __aenter__=lambda self: self,
            __aexit__=lambda self, exc_type, exc, tb: False,
        ),
        raising=False,
    )

    class _FakeSessionContext:
        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _FakeSessionContext())

    app = SimpleNamespace(state=SimpleNamespace())

    async with main.lifespan(app):
        pass

    assert order[:2] == ["preflight", "agent_services"]
