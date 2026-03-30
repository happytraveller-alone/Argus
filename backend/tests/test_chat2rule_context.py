import pytest

from app.services.chat2rule import (
    Chat2RuleSelection,
    format_chat2rule_selection_anchor,
    normalize_chat2rule_selections,
)


def test_normalize_chat2rule_selections_merges_same_file_ranges():
    selections = normalize_chat2rule_selections(
        [
            {"file_path": "src/auth.py", "start_line": 18, "end_line": 24},
            {"file_path": "src/auth.py", "start_line": 24, "end_line": 31},
            {"file_path": "src/utils.py", "start_line": 7, "end_line": 9},
        ]
    )

    assert selections == [
        Chat2RuleSelection(file_path="src/auth.py", start_line=18, end_line=31),
        Chat2RuleSelection(file_path="src/utils.py", start_line=7, end_line=9),
    ]


def test_normalize_chat2rule_selections_sorts_and_recovers_reversed_ranges():
    selections = normalize_chat2rule_selections(
        [
            {"file_path": "b.py", "start_line": 20, "end_line": 12},
            {"file_path": "a.py", "start_line": 5, "end_line": 5},
        ]
    )

    assert selections == [
        Chat2RuleSelection(file_path="a.py", start_line=5, end_line=5),
        Chat2RuleSelection(file_path="b.py", start_line=12, end_line=20),
    ]


def test_normalize_chat2rule_selections_rejects_project_escape_paths():
    with pytest.raises(ValueError, match="must not escape the project root"):
        normalize_chat2rule_selections(
            [{"file_path": "../etc/passwd", "start_line": 1, "end_line": 2}]
        )


def test_format_chat2rule_selection_anchor_renders_single_and_multi_line_ranges():
    assert (
        format_chat2rule_selection_anchor(
            Chat2RuleSelection(file_path="src/auth.py", start_line=42, end_line=42)
        )
        == "src/auth.py:42"
    )
    assert (
        format_chat2rule_selection_anchor(
            Chat2RuleSelection(file_path="src/auth.py", start_line=42, end_line=55)
        )
        == "src/auth.py:42-55"
    )
