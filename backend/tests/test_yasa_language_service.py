import pytest
from pathlib import Path

from app.services.yasa_language import (
    collect_yasa_language_counts_from_source_tree,
    is_yasa_blocked_project_language,
    normalize_yasa_language,
    resolve_yasa_language_from_source_tree,
    resolve_yasa_language_from_programming_languages,
    resolve_yasa_language_with_preference,
)


def test_resolve_yasa_language_from_programming_languages_supports_json_and_csv():
    assert resolve_yasa_language_from_programming_languages('["golang","python"]') == "golang"
    assert resolve_yasa_language_from_programming_languages("python,typescript") == "typescript"


def test_resolve_yasa_language_with_preference_prioritizes_manual_value():
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="typescript",
            programming_languages='["java"]',
            source_root=None,
        )
        == "typescript"
    )


def test_resolve_yasa_language_with_preference_skips_php_like_projects_in_auto_mode():
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="auto",
            programming_languages='["php","typescript"]',
            source_root=None,
        )
        == "typescript"
    )
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="auto",
            programming_languages="php8,typescript",
            source_root=None,
        )
        == "typescript"
    )


def test_resolve_yasa_language_with_preference_blocks_projects_without_whitelist_language():
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="python",
            programming_languages='["php"]',
            source_root=None,
        )
        is None
    )
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="typescript",
            programming_languages='["typescript","swift"]',
        )
        == "typescript"
    )


def test_is_yasa_blocked_project_language_detects_c_cpp_aliases():
    assert is_yasa_blocked_project_language('["cpp"]') is True
    assert is_yasa_blocked_project_language("c++,java") is False
    assert is_yasa_blocked_project_language(["cc", "python"]) is False
    assert is_yasa_blocked_project_language('["java","python"]') is False


def test_is_yasa_blocked_project_language_rejects_non_whitelist_languages():
    assert is_yasa_blocked_project_language('["javascript"]') is True
    assert is_yasa_blocked_project_language('["kotlin"]') is True
    assert is_yasa_blocked_project_language('["scala"]') is True
    assert is_yasa_blocked_project_language('["java","swift"]') is False
    assert is_yasa_blocked_project_language('["typescript"]') is False


def test_resolve_yasa_language_with_preference_accepts_manual_override_when_whitelist_language_exists():
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="java",
            programming_languages='["cpp","java"]',
            source_root=None,
        )
        == "java"
    )


def test_normalize_yasa_language_rejects_invalid_value():
    with pytest.raises(ValueError, match="不支持语言: php"):
        normalize_yasa_language("php", allow_auto=True)


def test_normalize_yasa_language_rejects_kotlin_alias():
    with pytest.raises(ValueError, match="不支持语言: kotlin"):
        normalize_yasa_language("kotlin", allow_auto=True)


def test_collect_yasa_language_counts_from_source_tree(tmp_path: Path):
    (tmp_path / "a.py").write_text("print('x')", encoding="utf-8")
    (tmp_path / "b.py").write_text("print('y')", encoding="utf-8")
    (tmp_path / "main.ts").write_text("const x = 1;", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")

    counts = collect_yasa_language_counts_from_source_tree(str(tmp_path))
    assert counts["python"] == 2
    assert counts["typescript"] == 1
    assert "java" not in counts


def test_resolve_yasa_language_from_source_tree_picks_majority(tmp_path: Path):
    (tmp_path / "a.py").write_text("print('x')", encoding="utf-8")
    (tmp_path / "b.py").write_text("print('y')", encoding="utf-8")
    (tmp_path / "c.ts").write_text("const x = 1;", encoding="utf-8")
    assert resolve_yasa_language_from_source_tree(str(tmp_path)) == "python"


def test_resolve_yasa_language_from_source_tree_tie_breaks_by_priority(tmp_path: Path):
    (tmp_path / "a.py").write_text("print('x')", encoding="utf-8")
    (tmp_path / "b.go").write_text("package main", encoding="utf-8")
    # Tie (1 vs 1), priority should choose golang over python.
    assert resolve_yasa_language_from_source_tree(str(tmp_path)) == "golang"


def test_resolve_yasa_language_from_source_tree_returns_none_for_kotlin_only(tmp_path: Path):
    (tmp_path / "main.kt").write_text("fun main() {}", encoding="utf-8")
    (tmp_path / "helper.kts").write_text("println(\"x\")", encoding="utf-8")
    assert resolve_yasa_language_from_source_tree(str(tmp_path)) is None
