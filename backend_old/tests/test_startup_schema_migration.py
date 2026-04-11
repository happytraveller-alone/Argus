import sys
import types

import pytest

fastmcp_module = types.ModuleType("fastmcp")
fastmcp_module.Client = object
fastmcp_client_module = types.ModuleType("fastmcp.client")
fastmcp_transports_module = types.ModuleType("fastmcp.client.transports")
fastmcp_transports_module.StdioTransport = object
fastmcp_transports_module.StreamableHttpTransport = object
git_module = types.ModuleType("git")

sys.modules.setdefault("fastmcp", fastmcp_module)
sys.modules.setdefault("fastmcp.client", fastmcp_client_module)
sys.modules.setdefault("fastmcp.client.transports", fastmcp_transports_module)
sys.modules.setdefault("git", git_module)

from app.main import assert_database_schema_is_latest

CURRENT_REVISION = "prev_linear_revision"
LATEST_REVISION = "linear_head_revision"


class _FakeScalarResult:
    def __init__(self, items):
        self._items = list(items)

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeSession:
    def __init__(self, version_sequences):
        self._version_sequences = [list(items) for items in version_sequences]
        self._execute_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _statement):
        index = min(self._execute_calls, len(self._version_sequences) - 1)
        self._execute_calls += 1
        return _FakeScalarResult(self._version_sequences[index])


class _FakeScriptDirectory:
    def __init__(self, head):
        self._head = head

    def get_current_head(self):
        return self._head


@pytest.mark.asyncio
async def test_assert_database_schema_is_latest_runs_alembic_upgrade_on_revision_mismatch(
    monkeypatch,
):
    fake_session = _FakeSession([[CURRENT_REVISION], [LATEST_REVISION]])
    upgrade_calls = []

    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(
        "app.main.ScriptDirectory.from_config",
        lambda _cfg: _FakeScriptDirectory(LATEST_REVISION),
    )

    async def _fake_run_upgrade():
        upgrade_calls.append("called")

    monkeypatch.setattr("app.main.run_pending_database_migrations", _fake_run_upgrade)

    await assert_database_schema_is_latest()

    assert upgrade_calls == ["called"]
    assert fake_session._execute_calls == 2


@pytest.mark.asyncio
async def test_assert_database_schema_is_latest_raises_when_schema_still_mismatched_after_upgrade(
    monkeypatch,
):
    fake_session = _FakeSession([[CURRENT_REVISION], [CURRENT_REVISION]])

    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(
        "app.main.ScriptDirectory.from_config",
        lambda _cfg: _FakeScriptDirectory(LATEST_REVISION),
    )

    async def _fake_run_upgrade():
        return None

    monkeypatch.setattr("app.main.run_pending_database_migrations", _fake_run_upgrade)

    with pytest.raises(
        RuntimeError,
        match="current=\\['prev_linear_revision'\\] expected=\\['linear_head_revision'\\]",
    ):
        await assert_database_schema_is_latest()


@pytest.mark.asyncio
async def test_assert_database_schema_is_latest_rejects_database_with_multiple_recorded_versions(
    monkeypatch,
):
    fake_session = _FakeSession([["old_head_a", "old_head_b"], ["old_head_a", "old_head_b"]])
    upgrade_calls = []

    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(
        "app.main.ScriptDirectory.from_config",
        lambda _cfg: _FakeScriptDirectory(LATEST_REVISION),
    )

    async def _fake_run_upgrade():
        upgrade_calls.append("called")

    monkeypatch.setattr("app.main.run_pending_database_migrations", _fake_run_upgrade)

    with pytest.raises(
        RuntimeError,
        match="current=\\['old_head_a', 'old_head_b'\\] expected=\\['linear_head_revision'\\]",
    ):
        await assert_database_schema_is_latest()
    assert upgrade_calls == ["called"]
