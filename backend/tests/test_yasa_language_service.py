import pytest

from app.services.yasa_language import (
    normalize_yasa_language,
    resolve_yasa_language_from_programming_languages,
    resolve_yasa_language_with_preference,
)


def test_resolve_yasa_language_from_programming_languages_supports_json_and_csv():
    assert resolve_yasa_language_from_programming_languages('["php","javascript"]') == "javascript"
    assert resolve_yasa_language_from_programming_languages("php,javascript") == "javascript"


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
            programming_languages='["php","javascript"]',
        )
        is None
    )
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="auto",
            programming_languages="php8,javascript",
        )
        is None
    )


def test_resolve_yasa_language_with_preference_allows_manual_override_for_php_like_projects():
    assert (
        resolve_yasa_language_with_preference(
            preferred_language="python",
            programming_languages='["php"]',
        )
        == "python"
    )


def test_normalize_yasa_language_rejects_invalid_value():
    with pytest.raises(ValueError, match="不支持语言: php"):
        normalize_yasa_language("php", allow_auto=True)
