"""Bandit 规则页接口测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import static_tasks_bandit


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _mock_user():
    return SimpleNamespace(id="u-1")


def test_extract_bandit_snapshot_rules_normalizes_and_sorts(monkeypatch):
    monkeypatch.setattr(
        static_tasks_bandit,
        "load_bandit_builtin_snapshot",
        lambda: {
            "rules": [
                {
                    "test_id": "b602",
                    "name": "subprocess",
                    "description": "desc",
                    "description_summary": "summary",
                    "checks": ["Call", "Call", ""],
                    "source": "builtin",
                    "bandit_version": "1.9.4",
                },
                {
                    "test_id": "B101",
                    "name": "assert_used",
                    "description": "",
                    "description_summary": "",
                    "checks": ["Assert"],
                    "source": "builtin",
                    "bandit_version": "1.9.4",
                },
            ]
        },
    )

    rules = static_tasks_bandit._extract_bandit_snapshot_rules()
    assert [item["test_id"] for item in rules] == ["B101", "B602"]
    assert rules[1]["checks"] == ["Call", "Call"]


def test_merge_bandit_rule_payload_defaults_to_active_true():
    merged = static_tasks_bandit._merge_bandit_rule_payload(
        snapshot_rules=[
            {
                "id": "B101",
                "test_id": "B101",
                "name": "assert_used",
                "description": "",
                "description_summary": "",
                "checks": ["Assert"],
                "source": "builtin",
                "bandit_version": "1.9.4",
            }
        ],
        states_by_test_id={},
    )

    assert merged[0]["is_active"] is True
    assert merged[0]["is_deleted"] is False
    assert merged[0]["updated_at"] is None


def test_resolve_bandit_effective_rule_ids_respects_state_filters():
    snapshot_rules = [
        {
            "id": "B101",
            "test_id": "B101",
            "name": "assert_used",
            "description": "",
            "description_summary": "",
            "checks": ["Assert"],
            "source": "builtin",
            "bandit_version": "1.9.4",
        },
        {
            "id": "B102",
            "test_id": "B102",
            "name": "exec_used",
            "description": "",
            "description_summary": "",
            "checks": ["Exec"],
            "source": "builtin",
            "bandit_version": "1.9.4",
        },
        {
            "id": "B103",
            "test_id": "B103",
            "name": "set_bad_file_permissions",
            "description": "",
            "description_summary": "",
            "checks": ["Call"],
            "source": "builtin",
            "bandit_version": "1.9.4",
        },
    ]
    states_by_test_id = {
        "B102": SimpleNamespace(is_active=False, is_deleted=False),
        "B103": SimpleNamespace(is_active=True, is_deleted=True),
    }

    rule_ids = static_tasks_bandit._resolve_bandit_effective_rule_ids(
        snapshot_rules=snapshot_rules,
        states_by_test_id=states_by_test_id,
    )

    assert rule_ids == ["B101"]


@pytest.mark.asyncio
async def test_resolve_bandit_scan_rule_ids_raises_when_empty(monkeypatch):
    monkeypatch.setattr(static_tasks_bandit, "_extract_bandit_snapshot_rules", lambda: [{"test_id": "B101"}])
    monkeypatch.setattr(
        static_tasks_bandit,
        "_load_bandit_rule_states",
        AsyncMock(return_value={"B101": SimpleNamespace(is_active=False, is_deleted=False)}),
    )

    with pytest.raises(RuntimeError, match="无可执行 Bandit 规则"):
        await static_tasks_bandit._resolve_bandit_scan_rule_ids(AsyncMock())


@pytest.mark.asyncio
async def test_update_bandit_rule_enabled_creates_state_when_missing(monkeypatch):
    monkeypatch.setattr(
        static_tasks_bandit,
        "_extract_bandit_snapshot_rules",
        lambda: [{"test_id": "B101"}],
    )

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    db.add = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(
        side_effect=lambda obj: (setattr(obj, "is_active", True), setattr(obj, "is_deleted", False)),
    )

    response = await static_tasks_bandit.update_bandit_rule_enabled(
        rule_id="b101",
        request=static_tasks_bandit.BanditRuleEnabledUpdateRequest(is_active=True),
        db=db,
        current_user=_mock_user(),
    )

    assert response["rule_id"] == "B101"
    assert response["is_active"] is True
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_bandit_rules_default_hides_deleted(monkeypatch):
    monkeypatch.setattr(
        static_tasks_bandit,
        "_extract_bandit_snapshot_rules",
        lambda: [
            {
                "id": "B101",
                "test_id": "B101",
                "name": "assert_used",
                "description": "",
                "description_summary": "",
                "checks": ["Assert"],
                "source": "builtin",
                "bandit_version": "1.9.4",
            }
        ],
    )
    state_row = SimpleNamespace(
        test_id="B101",
        is_active=False,
        is_deleted=True,
        created_at=None,
        updated_at=None,
    )
    monkeypatch.setattr(
        static_tasks_bandit,
        "_load_bandit_rule_states",
        AsyncMock(return_value={"B101": state_row}),
    )
    rows = await static_tasks_bandit.list_bandit_rules(
        deleted="false",
        db=AsyncMock(),
        current_user=_mock_user(),
    )
    assert rows == []


@pytest.mark.asyncio
async def test_delete_and_restore_bandit_rule(monkeypatch):
    monkeypatch.setattr(
        static_tasks_bandit,
        "_extract_bandit_snapshot_rules",
        lambda: [{"test_id": "B101"}],
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    db.add = AsyncMock()
    db.commit = AsyncMock()

    deleted = await static_tasks_bandit.delete_bandit_rule(
        rule_id="B101",
        db=db,
        current_user=_mock_user(),
    )
    assert deleted["is_deleted"] is True

    restored = await static_tasks_bandit.restore_bandit_rule(
        rule_id="B101",
        db=db,
        current_user=_mock_user(),
    )
    assert restored["is_deleted"] is False


@pytest.mark.asyncio
async def test_batch_update_bandit_rules_enabled_no_match(monkeypatch):
    monkeypatch.setattr(
        static_tasks_bandit,
        "_extract_bandit_snapshot_rules",
        lambda: [
            {
                "id": "B101",
                "test_id": "B101",
                "name": "assert_used",
                "description": "",
                "description_summary": "",
                "checks": ["Assert"],
                "source": "builtin",
                "bandit_version": "1.9.4",
            }
        ],
    )
    monkeypatch.setattr(static_tasks_bandit, "_load_bandit_rule_states", AsyncMock(return_value={}))

    db = AsyncMock()

    response = await static_tasks_bandit.batch_update_bandit_rules_enabled(
        request=static_tasks_bandit.BanditRuleBatchEnabledUpdateRequest(
            keyword="not-exists",
            is_active=False,
        ),
        db=db,
        current_user=_mock_user(),
    )

    assert response["updated_count"] == 0
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_update_bandit_rule_updates_snapshot_and_returns_merged_rule(monkeypatch):
    monkeypatch.setattr(
        static_tasks_bandit,
        "_extract_bandit_snapshot_rules",
        lambda: [
            {
                "id": "B101",
                "test_id": "B101",
                "name": "assert_used",
                "description": "old",
                "description_summary": "old summary",
                "checks": ["Assert"],
                "source": "builtin",
                "bandit_version": "1.9.4",
            }
        ],
    )
    monkeypatch.setattr(static_tasks_bandit, "_load_bandit_rule_states", AsyncMock(return_value={}))

    captured = {}

    def _fake_update_snapshot_rule(*, rule_id, updates, snapshot_path=None):
        captured["rule_id"] = rule_id
        captured["updates"] = updates
        return {}

    monkeypatch.setattr(
        static_tasks_bandit,
        "update_bandit_builtin_snapshot_rule",
        _fake_update_snapshot_rule,
    )

    db = AsyncMock()
    response = await static_tasks_bandit.update_bandit_rule(
        rule_id="b101",
        request=static_tasks_bandit.BanditRuleUpdateRequest(
            name="assert_used_custom",
            description_summary="custom summary",
            description="custom description",
            checks=["Assert", "Call", "Call"],
        ),
        db=db,
        current_user=_mock_user(),
    )

    assert response["message"] == "规则更新成功"
    assert response["rule"]["test_id"] == "B101"
    assert captured["rule_id"] == "B101"
    assert captured["updates"]["name"] == "assert_used_custom"
    assert captured["updates"]["description_summary"] == "custom summary"
    assert captured["updates"]["description"] == "custom description"
    assert captured["updates"]["checks"] == ["Assert", "Call"]


@pytest.mark.asyncio
async def test_update_bandit_rule_rejects_empty_updates(monkeypatch):
    monkeypatch.setattr(
        static_tasks_bandit,
        "_extract_bandit_snapshot_rules",
        lambda: [{"test_id": "B101"}],
    )

    with pytest.raises(static_tasks_bandit.HTTPException) as exc_info:
        await static_tasks_bandit.update_bandit_rule(
            rule_id="B101",
            request=static_tasks_bandit.BanditRuleUpdateRequest(),
            db=AsyncMock(),
            current_user=_mock_user(),
        )

    assert exc_info.value.status_code == 400
