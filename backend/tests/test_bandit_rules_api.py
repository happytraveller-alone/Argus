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
    assert merged[0]["updated_at"] is None


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
        side_effect=lambda obj: setattr(obj, "is_active", True),
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
