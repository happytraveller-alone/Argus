from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

PUSH_FINDING_ALIAS_MAP: Dict[str, str] = {
    "line": "line_start",
    "start_line": "line_start",
    "end_line": "line_end",
    "type": "vulnerability_type",
    "code": "code_snippet",
    "snippet": "code_snippet",
    "vulnerable_code": "code_snippet",
    "recommendation": "suggestion",
    "fix_suggestion": "suggestion",
}
PUSH_FINDING_LIST_FIELDS = {"evidence_chain", "missing_checks", "taint_flow"}
PUSH_FINDING_ALLOWED_FIELDS = {
    "file_path",
    "line_start",
    "line_end",
    "title",
    "description",
    "vulnerability_type",
    "severity",
    "confidence",
    "function_name",
    "code_snippet",
    "source",
    "sink",
    "suggestion",
    "evidence_chain",
    "attacker_flow",
    "missing_checks",
    "taint_flow",
    "finding_metadata",
}
_PUSH_FINDING_ENVELOPE_FIELDS = {"finding", "arguments"}
_PUSH_FINDING_MAX_EXTRA_KEYS = 20
_PUSH_FINDING_MAX_EXTRA_BYTES = 8 * 1024


def _parse_object_payload(raw_value: Any) -> Dict[str, Any]:
    if isinstance(raw_value, dict):
        return dict(raw_value)
    if not isinstance(raw_value, str):
        return {}
    text = str(raw_value or "").strip()
    if not text:
        return {}

    candidates = [text]
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        if end > start:
            candidates.append(text[start : end + 1])

    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return dict(parsed)
    return {}


def _normalize_extra_value(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _is_placeholder_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    text = str(value or "").strip().lower()
    if not text:
        return True
    if text in {
        "<value>",
        "<str>",
        "<int>",
        "<float>",
        "value",
        "string",
        "placeholder",
        "todo",
        "none",
        "null",
        "参数值",
        "参数名",
    }:
        return True
    return text.startswith("<") and text.endswith(">")


def _is_placeholder_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    public_items = {str(key): value for key, value in payload.items() if not str(key).startswith("__")}
    if not public_items:
        return False
    return all(_is_placeholder_text(key) or _is_placeholder_text(value) for key, value in public_items.items())


def _normalize_text_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    return []


def _coerce_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def _merge_payload_fields(
    target: Dict[str, Any],
    source_name: str,
    source_payload: Dict[str, Any],
    repair_map: Dict[str, str],
) -> None:
    for source_key, source_value in source_payload.items():
        if source_key in {"finding", "arguments"}:
            continue
        existing = target.get(source_key)
        if existing not in (None, "", [], {}):
            continue
        target[source_key] = source_value
        repair_map[f"{source_name}.{source_key}"] = source_key


def _limit_extra_tool_input(extra_payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    limited: Dict[str, Any] = {}
    truncated = False

    for index, (key, value) in enumerate(extra_payload.items()):
        if index >= _PUSH_FINDING_MAX_EXTRA_KEYS:
            truncated = True
            break
        candidate = {**limited, str(key): _normalize_extra_value(value)}
        encoded = json.dumps(candidate, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        if len(encoded) > _PUSH_FINDING_MAX_EXTRA_BYTES:
            truncated = True
            break
        limited = candidate

    return limited, truncated


def normalize_push_finding_payload(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    normalized = dict(payload or {})
    repair_map: Dict[str, str] = {}

    for source_name in ("arguments", "finding"):
        nested_payload = normalized.get(source_name)
        if isinstance(nested_payload, dict):
            _merge_payload_fields(normalized, f"__envelope.{source_name}", nested_payload, repair_map)

    raw_input_payload = _parse_object_payload(normalized.get("raw_input"))
    if raw_input_payload:
        _merge_payload_fields(normalized, "__raw_input", raw_input_payload, repair_map)
        for nested_name in ("arguments", "finding"):
            nested_payload = raw_input_payload.get(nested_name)
            if isinstance(nested_payload, dict):
                _merge_payload_fields(normalized, f"__raw_input.{nested_name}", nested_payload, repair_map)

    if _is_placeholder_payload(normalized):
        for key in list(normalized.keys()):
            if not str(key).startswith("__"):
                normalized.pop(key, None)
        repair_map["__placeholder_payload"] = "removed"

    for alias_key, target_key in PUSH_FINDING_ALIAS_MAP.items():
        alias_value = normalized.get(alias_key)
        target_value = normalized.get(target_key)
        if alias_value not in (None, "", [], {}) and target_value in (None, "", [], {}):
            normalized[target_key] = alias_value
            repair_map[alias_key] = target_key
        if alias_key != target_key:
            normalized.pop(alias_key, None)

    metadata_payload = _parse_object_payload(normalized.get("finding_metadata"))
    metadata_payload = dict(metadata_payload or {})
    existing_extra = metadata_payload.get("extra_tool_input")
    extra_tool_input = dict(existing_extra) if isinstance(existing_extra, dict) else {}

    for key in list(normalized.keys()):
        key_text = str(key)
        if key_text in PUSH_FINDING_ALLOWED_FIELDS or key_text.startswith("__"):
            continue
        if key_text in _PUSH_FINDING_ENVELOPE_FIELDS or key_text == "raw_input":
            normalized.pop(key_text, None)
            continue
        value = normalized.pop(key_text, None)
        if value in (None, "", [], {}) or _is_placeholder_text(value):
            continue
        extra_tool_input[key_text] = _normalize_extra_value(value)
        repair_map[f"__extra.{key_text}"] = f"finding_metadata.extra_tool_input.{key_text}"

    if extra_tool_input:
        limited_extra, truncated = _limit_extra_tool_input(extra_tool_input)
        if limited_extra:
            metadata_payload["extra_tool_input"] = limited_extra
        if truncated:
            metadata_payload["extra_tool_input_truncated"] = True

    if metadata_payload:
        normalized["finding_metadata"] = metadata_payload
    else:
        normalized.pop("finding_metadata", None)

    for line_key in ("line_start", "line_end"):
        parsed = _coerce_positive_int(normalized.get(line_key))
        if parsed is not None:
            normalized[line_key] = parsed

    for list_key in PUSH_FINDING_LIST_FIELDS:
        normalized_list = _normalize_text_list(normalized.get(list_key))
        if normalized_list:
            normalized[list_key] = normalized_list
        else:
            normalized.pop(list_key, None)

    for cleanup_key in ("finding", "arguments", "raw_input"):
        normalized.pop(cleanup_key, None)

    return normalized, repair_map


__all__ = [
    "PUSH_FINDING_ALLOWED_FIELDS",
    "PUSH_FINDING_LIST_FIELDS",
    "normalize_push_finding_payload",
]
