from types import SimpleNamespace

import pytest

from app.api.v1.endpoints.agent_tasks import _bootstrap_task_mcp_runtime, _build_task_mcp_runtime


class _Emitter:
    def __init__(self):
        self.infos = []
        self.errors = []

    async def emit_info(self, message: str, metadata=None):
        self.infos.append((message, metadata or {}))

    async def emit_error(self, message: str, metadata=None):
        self.errors.append((message, metadata or {}))


class _Runtime:
    def __init__(
        self,
        *,
        extra_domain_registered: bool = False,
    ):
        self.calls = []
        self.domain_adapters = {"legacy_backend": {"backend": object()}} if extra_domain_registered else {}


@pytest.mark.asyncio
async def test_bootstrap_task_mcp_runtime_skips_filesystem_binding(tmp_path):
    emitter = _Emitter()
    runtime = _Runtime()

    result = await _bootstrap_task_mcp_runtime(
        runtime,
        project_root=str(tmp_path),
        event_emitter=emitter,
    )

    assert result == {}
    assert runtime.calls == []
    assert emitter.infos == []
    assert emitter.errors == []


@pytest.mark.asyncio
async def test_bootstrap_task_mcp_runtime_does_not_touch_code_index_on_bootstrap(tmp_path):
    emitter = _Emitter()
    runtime = _Runtime()

    result = await _bootstrap_task_mcp_runtime(
        runtime,
        project_root=str(tmp_path),
        event_emitter=emitter,
    )
    assert result == {}
    assert runtime.calls == []


@pytest.mark.asyncio
async def test_bootstrap_task_mcp_runtime_ignores_unrelated_runtime_domains(tmp_path):
    emitter = _Emitter()
    runtime = _Runtime(
        extra_domain_registered=True,
    )

    result = await _bootstrap_task_mcp_runtime(
        runtime,
        project_root=str(tmp_path),
        event_emitter=emitter,
    )

    assert runtime.calls == []
    assert "legacy_backend" not in result
    assert emitter.infos == []


def test_build_task_mcp_runtime_only_registers_required_domains(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.MCP_ENABLED", True)

    runtime = _build_task_mcp_runtime(
        project_root=str(tmp_path),
        user_config=None,
        target_files=None,
    )

    assert runtime.domain_adapters == {}
    assert runtime.runtime_modes == {}
    assert runtime.required_mcps == []
