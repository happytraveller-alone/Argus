import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.services.agent.bandit_bootstrap_rules import (
    _extract_bandit_snapshot_test_ids_for_bootstrap,
    _normalize_bandit_rule_id,
    _resolve_bandit_bootstrap_rule_ids,
    _resolve_bandit_effective_rule_ids_for_bootstrap,
)


def test_normalize_bandit_rule_id_uppercases_and_trims():
    assert _normalize_bandit_rule_id(" b101 ") == "B101"
    assert _normalize_bandit_rule_id(None) == ""


def test_extract_bandit_snapshot_test_ids_for_bootstrap_dedupes_and_skips_invalid():
    with patch(
        "app.services.agent.bandit_bootstrap_rules.load_bandit_builtin_snapshot",
        return_value={
            "rules": [
                {"test_id": "b101"},
                {"test_id": " B101 "},
                {"test_id": "b102"},
                {"other": "ignored"},
                "bad-row",
            ]
        },
    ):
        assert _extract_bandit_snapshot_test_ids_for_bootstrap() == ["B101", "B102"]


def test_resolve_bandit_effective_rule_ids_for_bootstrap_respects_active_and_deleted_flags():
    states_by_test_id = {
        "B101": SimpleNamespace(is_active=True, is_deleted=False),
        "B102": SimpleNamespace(is_active=False, is_deleted=False),
        "B103": SimpleNamespace(is_active=True, is_deleted=True),
    }

    assert _resolve_bandit_effective_rule_ids_for_bootstrap(
        snapshot_test_ids=["B101", "B102", "B103", "B104"],
        states_by_test_id=states_by_test_id,
    ) == ["B101", "B104"]


def test_resolve_bandit_bootstrap_rule_ids_filters_snapshot_and_db_rows():
    rows = [
        SimpleNamespace(test_id="b101", is_active=True, is_deleted=False),
        SimpleNamespace(test_id="B102", is_active=False, is_deleted=False),
    ]

    class _FakeResult:
        def scalars(self):
            return self

        def all(self):
            return rows

    class _FakeDb:
        async def execute(self, _query):
            return _FakeResult()

    with patch(
        "app.services.agent.bandit_bootstrap_rules._extract_bandit_snapshot_test_ids_for_bootstrap",
        return_value=["B101", "B102", "B103"],
    ):
        resolved = asyncio.run(_resolve_bandit_bootstrap_rule_ids(_FakeDb()))

    assert resolved == ["B101", "B103"]


def test_resolve_bandit_bootstrap_rule_ids_errors_when_no_rules_left():
    rows = [SimpleNamespace(test_id="B101", is_active=False, is_deleted=False)]

    class _FakeResult:
        def scalars(self):
            return self

        def all(self):
            return rows

    class _FakeDb:
        async def execute(self, _query):
            return _FakeResult()

    with patch(
        "app.services.agent.bandit_bootstrap_rules._extract_bandit_snapshot_test_ids_for_bootstrap",
        return_value=["B101"],
    ):
        try:
            asyncio.run(_resolve_bandit_bootstrap_rule_ids(_FakeDb()))
        except RuntimeError as exc:
            assert "无可执行 Bandit 规则" in str(exc)
        else:
            raise AssertionError("expected RuntimeError when no rules remain")
