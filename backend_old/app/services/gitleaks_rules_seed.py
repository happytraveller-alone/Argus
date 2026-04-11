from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gitleaks import GitleaksRule

logger = logging.getLogger(__name__)


_BUILTIN_TOML_PATH = Path(__file__).resolve().parent.parent / "db" / "gitleaks_builtin" / "gitleaks-default.toml"


def _to_clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _normalize_builtin_rule(raw_rule: dict[str, Any]) -> dict[str, Any] | None:
    rule_id = str(raw_rule.get("id") or "").strip()
    regex = str(raw_rule.get("regex") or "").strip()
    if not rule_id or not regex:
        return None

    title = str(raw_rule.get("title") or "").strip()
    description = str(raw_rule.get("description") or "").strip() or None
    path = str(raw_rule.get("path") or "").strip() or None

    secret_group_raw = raw_rule.get("secretGroup", 0)
    try:
        secret_group = int(secret_group_raw)
    except Exception:
        secret_group = 0
    if secret_group < 0:
        secret_group = 0

    entropy_raw = raw_rule.get("entropy")
    entropy: float | None
    if entropy_raw is None:
        entropy = None
    else:
        try:
            entropy = float(entropy_raw)
        except Exception:
            entropy = None

    return {
        "name": title or rule_id,
        "description": description,
        "rule_id": rule_id,
        "secret_group": secret_group,
        "regex": regex,
        "keywords": _to_clean_list(raw_rule.get("keywords")),
        "path": path,
        "tags": _to_clean_list(raw_rule.get("tags")),
        "entropy": entropy,
        "is_active": True,
        "source": "builtin",
    }


async def ensure_builtin_gitleaks_rules(db: AsyncSession) -> dict[str, int]:
    if not _BUILTIN_TOML_PATH.exists():
        logger.warning("gitleaks builtin rules file not found: %s", _BUILTIN_TOML_PATH)
        return {"created": 0, "updated": 0, "skipped_custom": 0, "invalid": 0, "total": 0}

    try:
        parsed = tomllib.loads(_BUILTIN_TOML_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("failed to parse gitleaks builtin rules toml: %s", exc)
        return {"created": 0, "updated": 0, "skipped_custom": 0, "invalid": 0, "total": 0}

    raw_rules = parsed.get("rules")
    if not isinstance(raw_rules, list):
        return {"created": 0, "updated": 0, "skipped_custom": 0, "invalid": 0, "total": 0}

    normalized: list[dict[str, Any]] = []
    invalid = 0
    for raw in raw_rules:
        if not isinstance(raw, dict):
            invalid += 1
            continue
        mapped = _normalize_builtin_rule(raw)
        if mapped is None:
            invalid += 1
            continue
        normalized.append(mapped)

    if not normalized:
        return {"created": 0, "updated": 0, "skipped_custom": 0, "invalid": invalid, "total": 0}

    rule_ids = [item["rule_id"] for item in normalized]
    result = await db.execute(select(GitleaksRule).where(GitleaksRule.rule_id.in_(rule_ids)))
    existing_rows = result.scalars().all()
    existing_by_rule_id = {row.rule_id: row for row in existing_rows}

    created = 0
    updated = 0
    skipped_custom = 0

    for item in normalized:
        existing = existing_by_rule_id.get(item["rule_id"])
        if existing is None:
            db.add(GitleaksRule(**item))
            created += 1
            continue

        if existing.source != "builtin":
            skipped_custom += 1
            continue

        existing.name = item["name"]
        existing.description = item["description"]
        existing.secret_group = item["secret_group"]
        existing.regex = item["regex"]
        existing.keywords = item["keywords"]
        existing.path = item["path"]
        existing.tags = item["tags"]
        existing.entropy = item["entropy"]
        existing.is_active = item["is_active"]
        updated += 1

    await db.commit()

    total = created + updated
    logger.info(
        "gitleaks builtin rules sync finished: created=%s updated=%s skipped_custom=%s invalid=%s",
        created,
        updated,
        skipped_custom,
        invalid,
    )
    return {
        "created": created,
        "updated": updated,
        "skipped_custom": skipped_custom,
        "invalid": invalid,
        "total": total,
    }
