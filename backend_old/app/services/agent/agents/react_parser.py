"""Shared ReAct parser helpers for agent responses."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, Optional

from ..json_parser import AgentJsonParser


_SECTION_MARKERS = ("Thought:", "Action:", "Action Input:", "Observation:", "Final Answer:")


@dataclass
class ParsedReactResponse:
    thought: str = ""
    action: Optional[str] = None
    action_input: Dict[str, Any] = field(default_factory=dict)
    is_final: bool = False
    final_answer: Optional[Dict[str, Any]] = None


def _normalize_markdown_sections(text: str) -> str:
    """Normalize markdown-ish section headers into `Label:` lines."""
    normalized = text or ""

    replacements = {
        r"\*\*Thought:\*\*": "Thought:",
        r"\*\*Action:\*\*": "Action:",
        r"\*\*Action Input:\*\*": "Action Input:",
        r"\*\*Observation:\*\*": "Observation:",
        r"\*\*Final Answer:\*\*": "Final Answer:",
    }
    for pattern, repl in replacements.items():
        normalized = re.sub(pattern, repl, normalized)

    # Convert heading variants like `## Action` / `### Action Input` into label lines.
    normalized = re.sub(
        r"(?mi)^\s*#{1,6}\s*Thought\s*[:：]?\s*$",
        "Thought:",
        normalized,
    )
    normalized = re.sub(
        r"(?mi)^\s*#{1,6}\s*Action Input\s*[:：]?\s*$",
        "Action Input:",
        normalized,
    )
    normalized = re.sub(
        r"(?mi)^\s*#{1,6}\s*Observation\s*[:：]?\s*$",
        "Observation:",
        normalized,
    )
    normalized = re.sub(
        r"(?mi)^\s*#{1,6}\s*Final Answer\s*[:：]?\s*$",
        "Final Answer:",
        normalized,
    )
    normalized = re.sub(
        r"(?mi)^\s*#{1,6}\s*Action\s*[:：]?\s*$",
        "Action:",
        normalized,
    )

    # Handle inline heading forms such as `## Action read_file`.
    normalized = re.sub(
        r"(?mi)^\s*#{1,6}\s*Thought\s*[:：]?\s*(.+?)\s*$",
        r"Thought: \1",
        normalized,
    )
    normalized = re.sub(
        r"(?mi)^\s*#{1,6}\s*Action Input\s*[:：]?\s*(.+?)\s*$",
        r"Action Input: \1",
        normalized,
    )
    normalized = re.sub(
        r"(?mi)^\s*#{1,6}\s*Observation\s*[:：]?\s*(.+?)\s*$",
        r"Observation: \1",
        normalized,
    )
    normalized = re.sub(
        r"(?mi)^\s*#{1,6}\s*Final Answer\s*[:：]?\s*(.+?)\s*$",
        r"Final Answer: \1",
        normalized,
    )
    normalized = re.sub(
        r"(?mi)^\s*#{1,6}\s*Action\s*[:：]?\s*(.+?)\s*$",
        r"Action: \1",
        normalized,
    )
    return normalized


def _extract_section(cleaned_text: str, label: str) -> Optional[str]:
    pattern = (
        rf"{re.escape(label)}\s*(.*?)(?=\n(?:"
        rf"{'|'.join(re.escape(marker) for marker in _SECTION_MARKERS if marker != label)}"
        rf")|\Z)"
    )
    match = re.search(pattern, cleaned_text, flags=re.DOTALL)
    if not match:
        return None
    return match.group(1).strip()


def _extract_action_name(cleaned_text: str) -> Optional[str]:
    action_match = re.search(r"Action:\s*([^\n\r]*)", cleaned_text)
    if not action_match:
        return None

    action_text = action_match.group(1).strip()
    if not action_text:
        # `Action:` may be on its own line; use the next non-empty line.
        remainder = cleaned_text[action_match.end() :]
        next_line_match = re.search(r"\n\s*([^\n\r]+)", remainder)
        if next_line_match:
            action_text = next_line_match.group(1).strip()

    action_text = action_text.strip("`").strip()
    if action_text.startswith("```"):
        return None

    # Truncate obvious trailing fragments from malformed model outputs.
    for marker_pattern in (
        r"(?i)\bAction\s*Input\b",
        r"(?i)\bObservation\b",
        r"(?i)\bFinal\s*Answer\b",
    ):
        action_text = re.split(marker_pattern, action_text, maxsplit=1)[0].strip()

    # Remove trailing Chinese punctuation / connectors that can leak into action text.
    action_text = re.split(r"[，。；：！？、（）【】《》“”‘’]", action_text, maxsplit=1)[0].strip()
    action_text = re.split(r"\s+", action_text, maxsplit=1)[0].strip()

    # ASCII-only tool token; do not allow Unicode word chars here.
    action_name_match = re.match(r"([A-Za-z_][A-Za-z0-9_-]*)", action_text)
    if not action_name_match:
        return None
    return action_name_match.group(1)


def _strip_fenced_json(text: str) -> str:
    value = text.strip()
    value = re.sub(r"^\s*```(?:json)?\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s*```\s*$", "", value)
    return value.strip()


def parse_react_response(
    response: str,
    *,
    final_default: Optional[Dict[str, Any]] = None,
    action_input_raw_key: str = "raw_input",
) -> ParsedReactResponse:
    """Parse a ReAct-formatted LLM response with markdown compatibility."""
    parsed = ParsedReactResponse()
    cleaned_response = _normalize_markdown_sections(response)

    thought_section = _extract_section(cleaned_response, "Thought:")
    if thought_section:
        parsed.thought = thought_section

    action_name = _extract_action_name(cleaned_response)
    if action_name:
        parsed.action = action_name

        if not parsed.thought:
            action_pos = cleaned_response.find("Action:")
            if action_pos > 0:
                before_action = cleaned_response[:action_pos].strip()
                before_action = re.sub(r"^Thought:\s*", "", before_action)
                if before_action:
                    parsed.thought = before_action[:500] if len(before_action) > 500 else before_action

        action_input_text = _extract_section(cleaned_response, "Action Input:")
        if action_input_text:
            input_text = _strip_fenced_json(action_input_text)
            parsed.action_input = AgentJsonParser.parse(
                input_text,
                default={action_input_raw_key: input_text},
            )
        else:
            parsed.action_input = {}
        return parsed

    final_section = _extract_section(cleaned_response, "Final Answer:")
    if final_section is not None:
        parsed.is_final = True
        answer_text = _strip_fenced_json(final_section)
        parsed.final_answer = AgentJsonParser.parse(
            answer_text,
            default=final_default or {"findings": [], "raw_answer": answer_text},
        )

        if not parsed.thought:
            final_pos = cleaned_response.find("Final Answer:")
            if final_pos > 0:
                before_final = cleaned_response[:final_pos].strip()
                before_final = re.sub(r"^Thought:\s*", "", before_final)
                if before_final:
                    parsed.thought = before_final[:500] if len(before_final) > 500 else before_final
        return parsed

    if not parsed.thought and response and response.strip():
        parsed.thought = response.strip()[:500]
    return parsed
