"""Selection normalization helpers for chat-to-rule planning and prototyping."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class Chat2RuleSelection:
    """Canonical server-side representation for a selected code range."""

    file_path: str
    start_line: int
    end_line: int


def _normalize_file_path(file_path: Any) -> str:
    normalized = str(file_path or "").strip().replace("\\", "/")
    if not normalized:
        raise ValueError("file_path is required")

    path = PurePosixPath(normalized)
    if path.is_absolute():
        raise ValueError("file_path must be relative to the project root")
    if ".." in path.parts:
        raise ValueError("file_path must not escape the project root")

    clean_path = path.as_posix().lstrip("./")
    if not clean_path:
        raise ValueError("file_path is required")
    return clean_path


def _coerce_positive_line_number(value: Any, *, field_name: str) -> int:
    try:
        line_number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if line_number < 1:
        raise ValueError(f"{field_name} must be >= 1")
    return line_number


def format_chat2rule_selection_anchor(selection: Chat2RuleSelection) -> str:
    """Render a stable anchor for logs, prompts, and UI previews."""

    if selection.start_line == selection.end_line:
        return f"{selection.file_path}:{selection.start_line}"
    return f"{selection.file_path}:{selection.start_line}-{selection.end_line}"


def normalize_chat2rule_selections(
    raw_selections: Iterable[Mapping[str, Any]],
    *,
    merge_gap: int = 1,
) -> list[Chat2RuleSelection]:
    """
    Normalize user-provided ranges before prompting the LLM.

    Why this matters:
    - We should not trust the client to send already-canonical ranges.
    - Overlapping or adjacent selections in the same file should become one
      anchor to avoid duplicated context in the prompt budget.
    """

    parsed: list[Chat2RuleSelection] = []
    for raw in raw_selections:
        file_path = _normalize_file_path(raw.get("file_path"))
        start_line = _coerce_positive_line_number(
            raw.get("start_line"),
            field_name="start_line",
        )
        end_line = _coerce_positive_line_number(
            raw.get("end_line", start_line),
            field_name="end_line",
        )
        if end_line < start_line:
            start_line, end_line = end_line, start_line
        parsed.append(
            Chat2RuleSelection(
                file_path=file_path,
                start_line=start_line,
                end_line=end_line,
            )
        )

    parsed.sort(key=lambda item: (item.file_path, item.start_line, item.end_line))

    if not parsed:
        return []

    normalized: list[Chat2RuleSelection] = []
    for current in parsed:
        if not normalized:
            normalized.append(current)
            continue

        previous = normalized[-1]
        can_merge = (
            previous.file_path == current.file_path
            and current.start_line <= previous.end_line + max(0, int(merge_gap))
        )
        if can_merge:
            normalized[-1] = Chat2RuleSelection(
                file_path=previous.file_path,
                start_line=previous.start_line,
                end_line=max(previous.end_line, current.end_line),
            )
            continue

        normalized.append(current)

    return normalized
