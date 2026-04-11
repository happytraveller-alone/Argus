"""Bandit bootstrap rule resolution helpers."""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.bandit_rules_snapshot import load_bandit_builtin_snapshot


def _normalize_bandit_rule_id(raw_rule_id: Any) -> str:
    return str(raw_rule_id or "").strip().upper()


def _extract_bandit_snapshot_test_ids_for_bootstrap() -> List[str]:
    try:
        payload = load_bandit_builtin_snapshot()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Bandit 预处理失败：Bandit 内置规则快照不存在: {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Bandit 预处理失败：Bandit 内置规则快照格式错误: {exc}") from exc
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        return []

    test_ids: List[str] = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        test_id = _normalize_bandit_rule_id(raw.get("test_id"))
        if not test_id or test_id in test_ids:
            continue
        test_ids.append(test_id)
    return test_ids


def _resolve_bandit_effective_rule_ids_for_bootstrap(
    *,
    snapshot_test_ids: List[str],
    states_by_test_id: Dict[str, Any],
) -> List[str]:
    return [
        test_id
        for test_id in snapshot_test_ids
        if (
            (states_by_test_id.get(test_id) is None)
            or (
                bool(getattr(states_by_test_id.get(test_id), "is_active", True))
                and not bool(getattr(states_by_test_id.get(test_id), "is_deleted", False))
            )
        )
    ]


async def _resolve_bandit_bootstrap_rule_ids(db: Any) -> List[str]:
    try:
        from sqlalchemy.exc import ProgrammingError
        from sqlalchemy.future import select

        from app.models.bandit import BanditRuleState
    except ModuleNotFoundError:
        class ProgrammingError(Exception):
            pass

        def select(model: Any) -> Any:
            return model

        class BanditRuleState:  # type: ignore[no-redef]
            pass

    snapshot_test_ids = _extract_bandit_snapshot_test_ids_for_bootstrap()
    try:
        result = await db.execute(select(BanditRuleState))
    except ProgrammingError as exc:
        if "bandit_rule_states" in str(exc):
            raise RuntimeError("Bandit 预处理失败：数据库缺少 bandit_rule_states 表，请先运行 alembic upgrade head") from exc
        raise RuntimeError(f"Bandit 预处理失败：读取规则状态失败: {exc}") from exc

    rows = result.scalars().all()
    states_by_test_id = {
        _normalize_bandit_rule_id(getattr(row, "test_id", None)): row
        for row in rows
    }
    rule_ids = _resolve_bandit_effective_rule_ids_for_bootstrap(
        snapshot_test_ids=snapshot_test_ids,
        states_by_test_id=states_by_test_id,
    )
    if not rule_ids:
        raise RuntimeError("无可执行 Bandit 规则，请先在规则页启用至少 1 条规则")
    return rule_ids
