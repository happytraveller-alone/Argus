from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from typing import Any


def normalize_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        try:
            return normalize_json_safe(value.model_dump())  # type: ignore[attr-defined]
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return normalize_json_safe(value.dict())  # type: ignore[attr-defined]
        except Exception:
            pass
    if is_dataclass(value) and not isinstance(value, type):
        try:
            return normalize_json_safe(asdict(value))
        except Exception:
            pass
    if isinstance(value, dict):
        return {
            str(key): normalize_json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [normalize_json_safe(item) for item in value]
    return value


def dump_json_safe(value: Any, **kwargs: Any) -> str:
    return json.dumps(
        normalize_json_safe(value),
        default=str,
        **kwargs,
    )
