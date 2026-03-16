"""PHPStan 规则页接口测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints import static_tasks


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _mock_user():
    return SimpleNamespace(id="u-1")


def test_merge_phpstan_rule_payload_defaults_active_true():
    merged = static_tasks._phpstan._merge_phpstan_rule_payload(
        snapshot_rules=[
            {
                "id": "pkg:RuleClass",
                "package": "phpstan/phpstan-strict-rules",
                "repo": "phpstan-strict-rules",
                "rule_class": "PHPStan\\Rules\\Foo",
                "name": "Foo",
                "description_summary": "desc",
                "source_file": "src/Rules/Foo.php",
                "source": "official_extension",
            }
        ],
        states_by_rule_id={},
    )

    assert merged[0]["is_active"] is True
    assert merged[0]["updated_at"] is None


@pytest.mark.asyncio
async def test_update_phpstan_rule_enabled_creates_state_when_missing(monkeypatch):
    monkeypatch.setattr(
        static_tasks._phpstan,
        "_extract_phpstan_snapshot_rules",
        lambda: [{"id": "pkg:RuleClass"}],
    )

    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(None))
    db.add = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock(side_effect=lambda obj: setattr(obj, "is_active", True))

    response = await static_tasks.update_phpstan_rule_enabled(
        rule_id="pkg:RuleClass",
        request=static_tasks._phpstan.PhpstanRuleEnabledUpdateRequest(is_active=True),
        db=db,
        current_user=_mock_user(),
    )

    assert response["rule_id"] == "pkg:RuleClass"
    assert response["is_active"] is True
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_update_phpstan_rules_enabled_no_match(monkeypatch):
    monkeypatch.setattr(
        static_tasks._phpstan,
        "_extract_phpstan_snapshot_rules",
        lambda: [
            {
                "id": "pkg:RuleClass",
                "package": "phpstan/phpstan-strict-rules",
                "repo": "phpstan-strict-rules",
                "rule_class": "PHPStan\\Rules\\Foo",
                "name": "Foo",
                "description_summary": "desc",
                "source_file": "src/Rules/Foo.php",
                "source": "official_extension",
            }
        ],
    )
    monkeypatch.setattr(static_tasks._phpstan, "_load_phpstan_rule_states", AsyncMock(return_value={}))

    db = AsyncMock()

    response = await static_tasks.batch_update_phpstan_rules_enabled(
        request=static_tasks._phpstan.PhpstanRuleBatchEnabledUpdateRequest(
            keyword="not-exists",
            is_active=False,
        ),
        db=db,
        current_user=_mock_user(),
    )

    assert response["updated_count"] == 0
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_list_phpstan_rules_filters_keyword_and_status(monkeypatch):
    monkeypatch.setattr(
        static_tasks._phpstan,
        "_extract_phpstan_snapshot_rules",
        lambda: [
            {
                "id": "pkg:A",
                "package": "phpstan/phpstan-doctrine",
                "repo": "phpstan-doctrine",
                "rule_class": "A",
                "name": "A",
                "description_summary": "doctrine rule",
                "source_file": "src/A.php",
                "source": "official_extension",
            },
            {
                "id": "pkg:B",
                "package": "phpstan/phpstan-src",
                "repo": "phpstan-src",
                "rule_class": "B",
                "name": "B",
                "description_summary": "core rule",
                "source_file": "src/B.php",
                "source": "official_extension",
            },
        ],
    )

    state_row = SimpleNamespace(rule_id="pkg:A", is_active=False, created_at=None, updated_at=None)
    monkeypatch.setattr(
        static_tasks._phpstan,
        "_load_phpstan_rule_states",
        AsyncMock(return_value={"pkg:A": state_row}),
    )

    db = AsyncMock()
    rows = await static_tasks.list_phpstan_rules(
        is_active=False,
        source="official_extension",
        keyword="doctrine",
        skip=0,
        limit=10,
        db=db,
        current_user=_mock_user(),
    )

    assert len(rows) == 1
    assert rows[0]["id"] == "pkg:A"
