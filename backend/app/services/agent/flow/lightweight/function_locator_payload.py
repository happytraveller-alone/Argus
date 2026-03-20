from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, List, Optional


def _safe_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


def parse_locator_payload(raw_output: Any) -> Optional[Dict[str, Any]]:
    text = str(raw_output or "").strip()
    if not text:
        return None
    if text.startswith("") or text.startswith(""):
        return None

    candidates: List[str] = [text]
    if "```" in text:
        fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text)
        if fence_match:
            candidates.append(str(fence_match.group(1) or "").strip())

    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}")
        if end > start:
            candidates.append(text[start : end + 1])

    seen = set()
    for candidate in candidates:
        candidate_text = str(candidate or "").strip()
        if not candidate_text or candidate_text in seen:
            continue
        seen.add(candidate_text)
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(candidate_text)  # type: ignore[arg-type]
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def select_locator_function(
    payload: Dict[str, Any],
    *,
    line_start: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None

    safe_line = _safe_positive_int(line_start)
    payload_language = payload.get("language")
    diagnostics = payload.get("diagnostics")
    candidates: List[Dict[str, Any]] = []

    def _append_candidate(
        raw_name: Any,
        *,
        start_value: Any,
        end_value: Any,
        language: Any,
        kind: Any,
        source_priority: int,
    ) -> None:
        name = str(raw_name or "").strip()
        if not name:
            return

        normalized_kind = str(kind or "").strip().lower()
        if normalized_kind and all(
            tag not in normalized_kind for tag in ("function", "method", "constructor")
        ):
            return

        start_line = _safe_positive_int(start_value)
        end_line = _safe_positive_int(end_value)
        if start_line is not None and end_line is None:
            end_line = start_line
        if start_line is not None and end_line is not None and end_line < start_line:
            end_line = start_line

        span = 10**9
        if start_line is not None and end_line is not None:
            span = max(0, end_line - start_line)

        distance = 10**9
        if safe_line is not None and start_line is not None:
            if end_line is not None and start_line <= safe_line <= end_line:
                distance = 0
            else:
                distance = abs(start_line - safe_line)

        candidates.append(
            {
                "function": name,
                "start_line": start_line,
                "end_line": end_line,
                "language": language or payload_language,
                "source_priority": int(source_priority),
                "span": int(span),
                "distance": int(distance),
            }
        )

    direct_target = payload.get("enclosing_function") or payload.get("enclosingFunction")
    if isinstance(direct_target, dict):
        _append_candidate(
            direct_target.get("name")
            or direct_target.get("function")
            or direct_target.get("symbol"),
            start_value=direct_target.get("start_line")
            or direct_target.get("startLine")
            or direct_target.get("line"),
            end_value=direct_target.get("end_line") or direct_target.get("endLine"),
            language=direct_target.get("language"),
            kind=direct_target.get("kind") or "function",
            source_priority=1,
        )

    symbol_target = payload.get("symbol")
    if isinstance(symbol_target, dict):
        _append_candidate(
            symbol_target.get("name")
            or symbol_target.get("function")
            or symbol_target.get("symbol"),
            start_value=symbol_target.get("start_line")
            or symbol_target.get("startLine")
            or symbol_target.get("line"),
            end_value=symbol_target.get("end_line") or symbol_target.get("endLine"),
            language=symbol_target.get("language") or payload_language,
            kind=symbol_target.get("kind") or "function",
            source_priority=1,
        )

    for key in ("symbols", "functions", "definitions", "items", "members"):
        values = payload.get(key)
        if not isinstance(values, list):
            continue
        for raw in values:
            if not isinstance(raw, dict):
                continue
            _append_candidate(
                raw.get("name") or raw.get("function") or raw.get("symbol") or raw.get("identifier"),
                start_value=raw.get("start_line") or raw.get("startLine") or raw.get("line"),
                end_value=raw.get("end_line") or raw.get("endLine"),
                language=raw.get("language"),
                kind=raw.get("kind") or raw.get("type"),
                source_priority=2,
            )

    _append_candidate(
        payload.get("function") or payload.get("name") or payload.get("symbol"),
        start_value=payload.get("start_line"),
        end_value=payload.get("end_line"),
        language=payload_language,
        kind=payload.get("kind") or "function",
        source_priority=3,
    )

    if not candidates:
        return None

    if safe_line is not None:
        covering = [
            item
            for item in candidates
            if item["start_line"] is not None
            and item["end_line"] is not None
            and int(item["start_line"]) <= safe_line <= int(item["end_line"])
        ]
        if covering:
            best = min(
                covering,
                key=lambda item: (
                    int(item["span"]),
                    int(item["source_priority"]),
                    int(item["start_line"] or 10**9),
                    str(item["function"]),
                ),
            )
        else:
            prefix = [
                item
                for item in candidates
                if item["start_line"] is not None and int(item["start_line"]) <= safe_line
            ]
            pool = prefix or candidates
            best = min(
                pool,
                key=lambda item: (
                    int(item["distance"]),
                    int(item["span"]),
                    int(item["source_priority"]),
                    int(item["start_line"] or 10**9),
                    str(item["function"]),
                ),
            )
    else:
        best = min(
            candidates,
            key=lambda item: (
                int(item["source_priority"]),
                int(item["span"]),
                int(item["start_line"] or 10**9),
                str(item["function"]),
            ),
        )

    return {
        "function": best["function"],
        "start_line": best.get("start_line"),
        "end_line": best.get("end_line"),
        "language": best.get("language") or payload_language,
        "diagnostics": diagnostics,
    }
