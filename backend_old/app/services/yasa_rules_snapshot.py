"""YASA 内置规则快照生成与读取服务。"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

YASA_RULES_SNAPSHOT_PATH = (
    Path(__file__).resolve().parent.parent / "db" / "yasa_builtin" / "yasa_rules_snapshot.json"
)
YASA_RULES_SNAPSHOT_SCHEMA_VERSION = "1.0"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalize_string_list(raw_value: Any) -> list[str]:
    if not isinstance(raw_value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for item in raw_value:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def infer_yasa_languages_from_pack_id(pack_id: str) -> list[str]:
    normalized = str(pack_id or "").strip().lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", normalized) if token}
    tags: list[str] = []
    if "java" in tokens:
        tags.append("java")
    if "python" in tokens:
        tags.append("python")
    if "go" in tokens or "golang" in tokens:
        tags.append("golang")
    if tokens.intersection({"javascript", "js", "express", "node", "nodejs", "ts", "typescript"}):
        tags.extend(["javascript", "typescript"])

    ordered: list[str] = []
    seen: set[str] = set()
    for item in tags:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def build_yasa_rules_snapshot(
    *,
    resource_dir: Path | str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    resource_root = Path(resource_dir)
    checker_config_path = resource_root / "checker" / "checker-config.json"
    checker_pack_config_path = resource_root / "checker" / "checker-pack-config.json"

    checker_payload = _safe_json_load(checker_config_path)
    checker_pack_payload = _safe_json_load(checker_pack_config_path)
    if not isinstance(checker_payload, list) or not isinstance(checker_pack_payload, list):
        raise ValueError("YASA checker 资源格式错误")

    checker_pack_map: dict[str, list[str]] = {}
    checker_language_map: dict[str, list[str]] = {}
    pack_map: dict[str, list[str]] = {}
    checker_pack_ids: set[str] = set()

    for item in checker_pack_payload:
        if not isinstance(item, dict):
            continue
        checker_pack_id = str(item.get("checkerPackId") or "").strip()
        checker_ids = _normalize_string_list(item.get("checkerIds"))
        if not checker_pack_id or not checker_ids:
            continue
        checker_pack_ids.add(checker_pack_id)
        pack_map[checker_pack_id] = checker_ids
        languages = infer_yasa_languages_from_pack_id(checker_pack_id)
        for checker_id in checker_ids:
            checker_pack_map.setdefault(checker_id, []).append(checker_pack_id)
            checker_language_map.setdefault(checker_id, [])
            for language in languages:
                if language not in checker_language_map[checker_id]:
                    checker_language_map[checker_id].append(language)

    rules: list[dict[str, Any]] = []
    checker_ids: set[str] = set()
    for raw in checker_payload:
        if not isinstance(raw, dict):
            continue
        checker_id = str(raw.get("checkerId") or "").strip()
        if not checker_id:
            continue
        checker_ids.add(checker_id)
        rules.append(
            {
                "checker_id": checker_id,
                "checker_path": str(raw.get("checkerPath") or "").strip() or None,
                "description": str(raw.get("description") or "").strip() or None,
                "checker_packs": checker_pack_map.get(checker_id, []),
                "languages": checker_language_map.get(checker_id, []),
                "demo_rule_config_path": str(raw.get("demoRuleConfigPath") or "").strip()
                or None,
                "source": "builtin",
            }
        )

    rules.sort(key=lambda item: str(item.get("checker_id") or "").lower())

    return {
        "schema_version": YASA_RULES_SNAPSHOT_SCHEMA_VERSION,
        "generated_at": str(generated_at or "").strip() or _utc_now_iso(),
        "source_resource_dir": str(resource_root),
        "count": len(rules),
        "checker_ids": sorted(checker_ids),
        "checker_pack_ids": sorted(checker_pack_ids),
        "pack_map": {key: pack_map[key] for key in sorted(pack_map)},
        "rules": rules,
    }


def write_yasa_rules_snapshot(
    *,
    resource_dir: Path | str,
    output_path: Path | str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    snapshot = build_yasa_rules_snapshot(resource_dir=resource_dir, generated_at=generated_at)
    target_path = Path(output_path) if output_path is not None else YASA_RULES_SNAPSHOT_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="yasa_rules_snapshot.",
        dir=target_path.parent,
        delete=False,
        encoding="utf-8",
    ) as tmp_file:
        tmp_file.write(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n")
        tmp_path = Path(tmp_file.name)

    try:
        os.replace(tmp_path, target_path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise

    return snapshot


def load_yasa_rules_snapshot(snapshot_path: Path | str | None = None) -> dict[str, Any]:
    target_path = Path(snapshot_path) if snapshot_path is not None else YASA_RULES_SNAPSHOT_PATH
    if not target_path.exists():
        raise FileNotFoundError(f"YASA 规则快照不存在: {target_path}")
    payload = json.loads(target_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("YASA 规则快照格式错误")
    return payload


def extract_yasa_snapshot_rules(snapshot_path: Path | str | None = None) -> list[dict[str, Any]]:
    payload = load_yasa_rules_snapshot(snapshot_path)
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError("YASA 规则快照格式错误: rules 缺失")

    rules: list[dict[str, Any]] = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        checker_id = str(raw.get("checker_id") or "").strip()
        if not checker_id:
            continue
        rules.append(
            {
                "checker_id": checker_id,
                "checker_path": str(raw.get("checker_path") or "").strip() or None,
                "description": str(raw.get("description") or "").strip() or None,
                "checker_packs": _normalize_string_list(raw.get("checker_packs")),
                "languages": _normalize_string_list(raw.get("languages")),
                "demo_rule_config_path": str(raw.get("demo_rule_config_path") or "").strip()
                or None,
                "source": str(raw.get("source") or "builtin").strip() or "builtin",
            }
        )

    rules.sort(key=lambda item: item["checker_id"].lower())
    return rules


def load_yasa_checker_catalog(snapshot_path: Path | str | None = None) -> dict[str, Any]:
    payload = load_yasa_rules_snapshot(snapshot_path)
    checker_ids = payload.get("checker_ids")
    checker_pack_ids = payload.get("checker_pack_ids")
    raw_pack_map = payload.get("pack_map")
    if not isinstance(raw_pack_map, dict):
        raise ValueError("YASA 规则快照格式错误: pack_map 缺失")

    normalized_pack_map: dict[str, list[str]] = {}
    for raw_key, raw_value in raw_pack_map.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        normalized_pack_map[key] = _normalize_string_list(raw_value)

    return {
        "checker_ids": set(_normalize_string_list(checker_ids)),
        "checker_pack_ids": set(_normalize_string_list(checker_pack_ids)),
        "pack_map": normalized_pack_map,
    }
