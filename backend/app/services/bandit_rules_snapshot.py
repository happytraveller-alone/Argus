"""Bandit 内置规则快照生成与读取服务。

用途：
- 从当前运行时安装的 Bandit 插件加载规则元数据
- 生成稳定排序的 JSON 快照（便于后续规则页/规则开关接入）
- 提供读取快照的轻量接口，作为后续 seed 同步到 DB 的预留入口
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

_BANDIT_BUILTIN_JSON_PATH = (
    Path(__file__).resolve().parent.parent / "db" / "bandit_builtin" / "bandit_builtin_rules.json"
)
_SCHEMA_VERSION = "1.0"
_MAX_DOC_LENGTH = 4000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_doc_texts(raw_doc: Any) -> Tuple[str, str]:
    """提取文档首行摘要和截断后的完整描述。"""
    doc = str(raw_doc or "").strip()
    if not doc:
        return "", ""
    lines = [line.strip() for line in doc.splitlines() if line.strip()]
    summary = lines[0] if lines else ""
    full = doc[:_MAX_DOC_LENGTH]
    return summary, full


def _normalize_checks(raw_checks: Any) -> List[str]:
    if not isinstance(raw_checks, list):
        return []
    checks: List[str] = []
    for item in raw_checks:
        text = str(item or "").strip()
        if text and text not in checks:
            checks.append(text)
    return checks


def _import_bandit_runtime() -> Tuple[str, Any]:
    """导入 bandit 运行时并返回版本和插件 manager。"""
    try:
        bandit_module = importlib.import_module("bandit")
        extension_loader = importlib.import_module("bandit.core.extension_loader")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Bandit runtime import failed: {exc}") from exc

    manager = getattr(extension_loader, "MANAGER", None)
    if manager is None:
        raise RuntimeError("Bandit extension manager is unavailable")
    version = str(getattr(bandit_module, "__version__", "unknown") or "unknown").strip()
    return version, manager


def build_bandit_builtin_snapshot(
    *,
    bandit_version: str | None = None,
    manager: Any = None,
    generated_at: str | None = None,
) -> Dict[str, Any]:
    """构建 Bandit 内置规则快照（内存对象）。"""
    resolved_version = str(bandit_version or "").strip()
    resolved_manager = manager

    if resolved_manager is None:
        resolved_version, resolved_manager = _import_bandit_runtime()
    if not resolved_version:
        resolved_version = "unknown"

    plugins = getattr(resolved_manager, "plugins", []) or []
    rules: List[Dict[str, Any]] = []

    for plugin_descriptor in plugins:
        plugin = getattr(plugin_descriptor, "plugin", None)
        if plugin is None:
            continue

        test_id = str(getattr(plugin, "_test_id", "") or "").strip().upper()
        if not test_id:
            # 跳过非规则插件或缺失 test_id 的插件，避免脏数据进入快照。
            continue

        name = str(getattr(plugin, "__name__", "") or "").strip()
        summary, full_description = _extract_doc_texts(getattr(plugin, "__doc__", ""))
        checks = _normalize_checks(getattr(plugin, "_checks", []))
        source = str(getattr(plugin_descriptor, "name", "") or "").strip()

        rules.append(
            {
                "test_id": test_id,
                "name": name,
                "description": full_description,
                "description_summary": summary,
                "checks": checks,
                "source": source,
                "bandit_version": resolved_version,
            }
        )

    rules.sort(key=lambda item: (str(item.get("test_id") or ""), str(item.get("name") or "")))
    generated_timestamp = str(generated_at or "").strip() or _utc_now_iso()

    return {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": generated_timestamp,
        "bandit_version": resolved_version,
        "count": len(rules),
        "rules": rules,
    }


def write_bandit_builtin_snapshot(output_path: Path | str | None = None) -> Dict[str, Any]:
    """生成并写入 Bandit 内置规则快照文件。"""
    snapshot = build_bandit_builtin_snapshot()
    target_path = Path(output_path) if output_path is not None else _BANDIT_BUILTIN_JSON_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    logger.info("bandit builtin snapshot generated: path=%s count=%s", target_path, snapshot["count"])
    return snapshot


def load_bandit_builtin_snapshot(snapshot_path: Path | str | None = None) -> Dict[str, Any]:
    """读取 Bandit 内置规则快照（后续可用于 seed 同步入口）。"""
    target_path = Path(snapshot_path) if snapshot_path is not None else _BANDIT_BUILTIN_JSON_PATH
    if not target_path.exists():
        raise FileNotFoundError(f"Bandit builtin snapshot not found: {target_path}")
    payload = json.loads(target_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid bandit builtin snapshot payload")
    return payload


def update_bandit_builtin_snapshot_rule(
    *,
    rule_id: str,
    updates: Dict[str, Any],
    snapshot_path: Path | str | None = None,
) -> Dict[str, Any]:
    """更新快照中的单条规则并原子写回文件。"""
    if not isinstance(updates, dict) or not updates:
        raise ValueError("updates must contain at least one field")

    target_path = Path(snapshot_path) if snapshot_path is not None else _BANDIT_BUILTIN_JSON_PATH
    payload = load_bandit_builtin_snapshot(target_path)
    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Invalid bandit builtin snapshot payload: rules is not a list")

    normalized_rule_id = str(rule_id or "").strip().upper()
    if not normalized_rule_id:
        raise ValueError("rule_id is required")

    matched_rule: Dict[str, Any] | None = None
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        current_rule_id = str(rule.get("test_id") or "").strip().upper()
        if current_rule_id == normalized_rule_id:
            matched_rule = rule
            break

    if matched_rule is None:
        raise KeyError(f"Bandit rule not found: {normalized_rule_id}")

    for field, value in updates.items():
        matched_rule[field] = value

    payload["count"] = len([item for item in rules if isinstance(item, dict)])
    payload["generated_at"] = _utc_now_iso()

    target_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="bandit_builtin_rules.",
        dir=target_path.parent,
        delete=False,
        encoding="utf-8",
    ) as tmp_file:
        tmp_file.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
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

    return matched_rule
