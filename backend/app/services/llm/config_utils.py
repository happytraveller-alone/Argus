"""
LLM config parsing helpers.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit


_ROOT_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/completions",
    "/responses",
    "/embeddings",
    "/models",
)


def normalize_llm_base_url(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""

    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        return raw.rstrip("/")

    normalized_path = parts.path.rstrip("/")
    normalized_path_lower = normalized_path.lower()
    for suffix in _ROOT_ENDPOINT_SUFFIXES:
        if normalized_path_lower.endswith(suffix):
            normalized_path = normalized_path[: -len(suffix)]
            break
    normalized_path = normalized_path.rstrip("/")

    return urlunsplit((parts.scheme, parts.netloc, normalized_path, "", ""))


def parse_llm_custom_headers(value: Any) -> dict[str, str]:
    if value is None:
        return {}

    if isinstance(value, dict):
        raw_headers = value
    else:
        raw_text = str(value).strip()
        if not raw_text:
            return {}
        try:
            raw_headers = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError("llmCustomHeaders 必须是 JSON 对象") from exc

    if not isinstance(raw_headers, dict):
        raise ValueError("llmCustomHeaders 必须是 JSON 对象")

    normalized: dict[str, str] = {}
    for key, header_value in raw_headers.items():
        header_name = str(key or "").strip()
        if not header_name:
            continue
        if isinstance(header_value, (dict, list)):
            raise ValueError("llmCustomHeaders 必须是扁平的 JSON 对象")
        normalized[header_name] = "" if header_value is None else str(header_value)
    return normalized
