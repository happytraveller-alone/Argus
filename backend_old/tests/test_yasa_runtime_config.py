import json
from datetime import datetime, timezone

import pytest

from app.api.v1.endpoints import static_tasks_yasa
from app.models.user_config import UserConfig
from app.services import yasa_runtime_config


class _FakeResult:
    def __init__(self, *, single=None, items=None):
        self._single = single
        self._items = items or []

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return self

    def all(self):
        return list(self._items)


class _FakeDb:
    def __init__(self, *, single=None, items=None):
        self.single = single
        self.items = items or []
        self.added = []
        self.commit_calls = 0

    async def execute(self, _stmt):
        if self.single is not None:
            return _FakeResult(single=self.single)
        return _FakeResult(items=self.items)

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_load_global_yasa_runtime_config_prefers_saved_config():
    row = UserConfig(
        user_id="u1",
        llm_config="{}",
        other_config=json.dumps(
            {
                yasa_runtime_config.GLOBAL_YASA_RUNTIME_CONFIG_KEY: {
                    "yasa_timeout_seconds": 700,
                    "yasa_orphan_stale_seconds": 180,
                    "yasa_exec_heartbeat_seconds": 20,
                    "yasa_process_kill_grace_seconds": 3,
                }
            },
            ensure_ascii=False,
        ),
    )
    row.updated_at = datetime.now(timezone.utc)
    db = _FakeDb(items=[row])

    loaded = await yasa_runtime_config.load_global_yasa_runtime_config(db)  # type: ignore[arg-type]
    assert loaded["yasa_timeout_seconds"] == 700
    assert loaded["yasa_process_kill_grace_seconds"] == 3


@pytest.mark.asyncio
async def test_save_global_yasa_runtime_config_updates_existing_other_config():
    row = UserConfig(
        user_id="u1",
        llm_config="{}",
        other_config=json.dumps({"maxAnalyzeFiles": 100}, ensure_ascii=False),
    )
    db = _FakeDb(single=row)

    saved = await yasa_runtime_config.save_global_yasa_runtime_config(
        db,  # type: ignore[arg-type]
        user_id="u1",
        runtime_config={
            "yasa_timeout_seconds": 800,
            "yasa_orphan_stale_seconds": 200,
            "yasa_exec_heartbeat_seconds": 10,
            "yasa_process_kill_grace_seconds": 4,
        },
    )
    assert saved["yasa_timeout_seconds"] == 800
    payload = json.loads(row.other_config)
    assert payload["maxAnalyzeFiles"] == 100
    assert payload[yasa_runtime_config.GLOBAL_YASA_RUNTIME_CONFIG_KEY]["yasa_timeout_seconds"] == 800


@pytest.mark.asyncio
async def test_runtime_config_endpoints_delegate_to_service(monkeypatch):
    expected = {
        "yasa_timeout_seconds": 600,
        "yasa_orphan_stale_seconds": 120,
        "yasa_exec_heartbeat_seconds": 15,
        "yasa_process_kill_grace_seconds": 2,
    }

    async def _fake_load(_db):
        return expected

    async def _fake_save(_db, *, user_id, runtime_config):
        assert user_id == "u1"
        assert runtime_config["yasa_timeout_seconds"] == 666
        merged = dict(expected)
        merged.update(runtime_config)
        return merged

    monkeypatch.setattr(static_tasks_yasa, "load_global_yasa_runtime_config", _fake_load)
    monkeypatch.setattr(static_tasks_yasa, "save_global_yasa_runtime_config", _fake_save)

    user = type("User", (), {"id": "u1"})()
    runtime = await static_tasks_yasa.get_yasa_runtime_config(db=object(), current_user=user)
    assert runtime.yasa_timeout_seconds == 600

    payload = static_tasks_yasa.YasaRuntimeConfigUpdateRequest(
        yasa_timeout_seconds=666,
        yasa_orphan_stale_seconds=120,
        yasa_exec_heartbeat_seconds=15,
        yasa_process_kill_grace_seconds=2,
    )
    updated = await static_tasks_yasa.update_yasa_runtime_config(
        payload=payload,
        db=object(),
        current_user=user,
    )
    assert updated.yasa_timeout_seconds == 666
