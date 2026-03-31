import pytest

from app.services.yasa_language import (
    is_yasa_blocked_project_language,
    normalize_yasa_language,
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
        )
        == "typescript"
    )


def test_resolve_yasa_language_with_preference_skips_php_like_projects_in_auto_mode():
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="auto",
            programming_languages='["php","typescript"]',
        )
        == "typescript"
    )
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="auto",
            programming_languages="php8,typescript",
        )
        == "typescript"
    )


def test_resolve_yasa_language_with_preference_blocks_projects_without_whitelist_language():
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="python",
            programming_languages='["php"]',
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
        )
        == "java"
    )


def test_normalize_yasa_language_rejects_invalid_value():
    with pytest.raises(ValueError, match="不支持语言: php"):
        normalize_yasa_language("php", allow_auto=True)
