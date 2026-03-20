import pytest

from app.main import assert_database_schema_is_latest


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
    def __init__(self, heads):
        self._heads = list(heads)

    def get_heads(self):
        return list(self._heads)


@pytest.mark.asyncio
async def test_assert_database_schema_is_latest_runs_alembic_upgrade_on_revision_mismatch(
    monkeypatch,
):
    fake_session = _FakeSession([["90a71996ac03"], ["a8f1c2d3e4b5"]])
    upgrade_calls = []

    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(
        "app.main.ScriptDirectory.from_config",
        lambda _cfg: _FakeScriptDirectory(["a8f1c2d3e4b5"]),
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
    fake_session = _FakeSession([["90a71996ac03"], ["90a71996ac03"]])

    monkeypatch.setattr("app.main.AsyncSessionLocal", lambda: fake_session)
    monkeypatch.setattr(
        "app.main.ScriptDirectory.from_config",
        lambda _cfg: _FakeScriptDirectory(["a8f1c2d3e4b5"]),
    )

    async def _fake_run_upgrade():
        return None

    monkeypatch.setattr("app.main.run_pending_database_migrations", _fake_run_upgrade)

    with pytest.raises(RuntimeError, match="current=\\['90a71996ac03'\\] heads=\\['a8f1c2d3e4b5'\\]"):
        await assert_database_schema_is_latest()
