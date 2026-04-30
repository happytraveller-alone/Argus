"""Tests for ClaudeTraceParser content_block_delta handling (T4.3)."""
from __future__ import annotations

import json

import pytest

from agentflow.specs import AgentKind
from agentflow.traces import ClaudeTraceParser


def _parser() -> ClaudeTraceParser:
    return ClaudeTraceParser(node_id="test-node", agent=AgentKind.CLAUDE)


def _line(payload: dict) -> str:
    return json.dumps(payload)


def test_content_block_delta_text_emits_assistant_delta() -> None:
    parser = _parser()
    events = parser.feed(_line({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}}))
    assert len(events) >= 1
    kinds = [e.kind for e in events]
    assert "assistant_delta" in kinds
    delta_events = [e for e in events if e.kind == "assistant_delta"]
    assert delta_events[0].content == "Hello"


def test_content_block_delta_thinking_emits_thinking_delta() -> None:
    parser = _parser()
    events = parser.feed(_line({"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "reasoning"}}))
    assert len(events) >= 1
    kinds = [e.kind for e in events]
    assert "thinking_delta" in kinds
    delta_events = [e for e in events if e.kind == "thinking_delta"]
    assert delta_events[0].content == "reasoning"


def test_content_block_start_falls_through_safely() -> None:
    parser = _parser()
    # Should not raise; falls through to catch-all 'event'
    events = parser.feed(_line({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}))
    assert isinstance(events, list)


def test_assistant_message_branch_still_works() -> None:
    parser = _parser()
    events = parser.feed(_line({"type": "assistant", "message": "final answer"}))
    assert len(events) >= 1
    kinds = [e.kind for e in events]
    assert "assistant_message" in kinds


def test_content_block_delta_empty_text_emits_nothing() -> None:
    """Empty text_delta should not emit any event (guarded by 'if delta_text')."""
    parser = _parser()
    events = parser.feed(_line({"type": "content_block_delta", "delta": {"type": "text_delta", "text": ""}}))
    # No assistant_delta event for empty string
    assert not any(e.kind == "assistant_delta" for e in events)


def test_content_block_delta_unknown_delta_type_emits_nothing() -> None:
    """Unknown delta type inside content_block_delta should produce an empty list."""
    parser = _parser()
    events = parser.feed(_line({"type": "content_block_delta", "delta": {"type": "unknown_delta", "data": "x"}}))
    # Neither assistant_delta nor thinking_delta
    assert not any(e.kind in {"assistant_delta", "thinking_delta"} for e in events)
