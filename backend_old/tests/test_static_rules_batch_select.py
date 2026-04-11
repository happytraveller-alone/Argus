from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.endpoints.static_tasks import (
    OpengrepRuleBatchUpdateRequest,
    select_opengrep_rules,
)


class _ScalarsResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _make_db_with_rows(rows):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarsResult(rows))
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_no_filter_global_enable_updates_all_rules():
    rule_a = SimpleNamespace(id="rule-a", is_active=False)
    rule_b = SimpleNamespace(id="rule-b", is_active=True)
    db = _make_db_with_rows([rule_a, rule_b])

    response = await select_opengrep_rules(
        request=OpengrepRuleBatchUpdateRequest(is_active=True),
        db=db,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert response["updated_count"] == 2
    assert response["is_active"] is True
    assert rule_a.is_active is True
    assert rule_b.is_active is True
    db.commit.assert_awaited_once()

    stmt = db.execute.call_args.args[0]
    assert "where" not in str(stmt).lower()


@pytest.mark.asyncio
async def test_keyword_filter_disable_updates_matching_rules_only():
    matched_rule = SimpleNamespace(id="rule-auth", is_active=True)
    db = _make_db_with_rows([matched_rule])

    response = await select_opengrep_rules(
        request=OpengrepRuleBatchUpdateRequest(keyword="Auth", is_active=False),
        db=db,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert response["updated_count"] == 1
    assert matched_rule.is_active is False

    stmt = db.execute.call_args.args[0]
    sql = str(stmt).lower()
    assert "lower(opengrep_rules.name)" in sql
    assert "lower(opengrep_rules.id)" in sql
    compiled = stmt.compile()
    str_params = [v for v in compiled.params.values() if isinstance(v, str)]
    assert "%auth%" in str_params


@pytest.mark.asyncio
async def test_active_filter_toggle_only_updates_currently_enabled_rules():
    enabled_rule = SimpleNamespace(id="rule-enabled", is_active=True)
    db = _make_db_with_rows([enabled_rule])

    response = await select_opengrep_rules(
        request=OpengrepRuleBatchUpdateRequest(
            current_is_active=True,
            is_active=False,
        ),
        db=db,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert response["updated_count"] == 1
    assert enabled_rule.is_active is False

    stmt = db.execute.call_args.args[0]
    assert "opengrep_rules.is_active" in str(stmt).lower()


@pytest.mark.asyncio
async def test_combined_filters_apply_together():
    matched_rule = SimpleNamespace(id="py-auth-1", is_active=False)
    db = _make_db_with_rows([matched_rule])

    response = await select_opengrep_rules(
        request=OpengrepRuleBatchUpdateRequest(
            language="python",
            source="internal",
            severity="ERROR",
            confidence="HIGH",
            keyword="auth",
            current_is_active=False,
            is_active=True,
        ),
        db=db,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert response["updated_count"] == 1
    assert matched_rule.is_active is True

    stmt = db.execute.call_args.args[0]
    sql = str(stmt).lower()
    assert "opengrep_rules.language" in sql
    assert "opengrep_rules.source" in sql
    assert "opengrep_rules.severity" in sql
    assert "opengrep_rules.confidence" in sql
    assert "opengrep_rules.is_active" in sql
    assert "lower(opengrep_rules.name)" in sql


@pytest.mark.asyncio
async def test_rule_ids_filter_updates_only_targeted_rules():
    target_a = SimpleNamespace(id="rule-1", is_active=False)
    target_b = SimpleNamespace(id="rule-2", is_active=False)
    db = _make_db_with_rows([target_a, target_b])

    response = await select_opengrep_rules(
        request=OpengrepRuleBatchUpdateRequest(
            rule_ids=["rule-1", "rule-2"],
            is_active=True,
        ),
        db=db,
        current_user=SimpleNamespace(id="u-1"),
    )

    assert response["updated_count"] == 2
    assert target_a.is_active is True
    assert target_b.is_active is True

    stmt = db.execute.call_args.args[0]
    sql = str(stmt).lower()
    assert "opengrep_rules.id" in sql
    assert " in " in sql
