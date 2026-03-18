from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

YASA_SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "python",
    "javascript",
    "typescript",
    "golang",
    "java",
)

YASA_SUPPORTED_LANGUAGES_TEXT = "/".join(YASA_SUPPORTED_LANGUAGES)

YASA_LANGUAGE_ERROR_TEMPLATE = (
    "不支持语言: {language}，YASA 仅支持 python/javascript/typescript/golang/java"
)

YASA_PROFILE_MAPPING: Dict[str, Dict[str, str]] = {
    "python": {
        "language": "python",
        "checker_pack": "taint-flow-python-default",
        "rule_config": "rule_config_python.json",
    },
    "javascript": {
        "language": "javascript",
        "checker_pack": "taint-flow-javascript-default",
        "rule_config": "rule_config_js.json",
    },
    "typescript": {
        "language": "typescript",
        "checker_pack": "taint-flow-javascript-default",
        "rule_config": "rule_config_js.json",
    },
    "golang": {
        "language": "golang",
        "checker_pack": "taint-flow-golang-default",
        "rule_config": "rule_config_go.json",
    },
    "java": {
        "language": "java",
        "checker_pack": "taint-flow-java-default",
        "rule_config": "rule_config_java.json",
    },
}

_YASA_LANGUAGE_ALIAS: Dict[str, str] = {
    "py": "python",
    "python": "python",
    "js": "javascript",
    "javascript": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
    "ts": "typescript",
    "typescript": "typescript",
    "go": "golang",
    "golang": "golang",
    "java": "java",
    "kotlin": "java",
    "scala": "java",
}

_YASA_LANGUAGE_PRIORITY: tuple[str, ...] = (
    "java",
    "golang",
    "python",
    "typescript",
    "javascript",
)


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def parse_programming_languages(raw_languages: Any) -> List[str]:
    if isinstance(raw_languages, list):
        return [str(item).strip() for item in raw_languages if str(item).strip()]

    if isinstance(raw_languages, str):
        text = raw_languages.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
            return _split_csv(str(parsed))
        except Exception:
            return _split_csv(text)

    return []


def normalize_yasa_language(
    language: Optional[str],
    *,
    allow_auto: bool,
) -> Optional[str]:
    normalized = str(language or "").strip().lower()
    if not normalized:
        return None
    if normalized == "auto":
        if allow_auto:
            return "auto"
        raise ValueError(YASA_LANGUAGE_ERROR_TEMPLATE.format(language=normalized))

    resolved = _YASA_LANGUAGE_ALIAS.get(normalized)
    if resolved and resolved in YASA_SUPPORTED_LANGUAGES:
        return resolved
    raise ValueError(YASA_LANGUAGE_ERROR_TEMPLATE.format(language=normalized))


def resolve_yasa_language_from_programming_languages(raw_languages: Any) -> Optional[str]:
    candidates = parse_programming_languages(raw_languages)
    mapped: List[str] = []
    for item in candidates:
        normalized = str(item).strip().lower()
        resolved = _YASA_LANGUAGE_ALIAS.get(normalized)
        if resolved and resolved in YASA_SUPPORTED_LANGUAGES:
            mapped.append(resolved)

    if not mapped:
        return None

    for preferred in _YASA_LANGUAGE_PRIORITY:
        if preferred in mapped:
            return preferred
    return mapped[0]


def resolve_yasa_language_with_preference(
    *,
    preferred_language: Optional[str],
    programming_languages: Any,
) -> Optional[str]:
    normalized_preference = normalize_yasa_language(preferred_language, allow_auto=True)
    if normalized_preference and normalized_preference != "auto":
        return normalized_preference
    # YASA auto policy: PHP-like projects should be skipped even if other
    # supported languages are also detected.
    project_languages = parse_programming_languages(programming_languages)
    if any(str(item).strip().lower().startswith("php") for item in project_languages):
        return None
    return resolve_yasa_language_from_programming_languages(programming_languages)


def resolve_yasa_language_profile(language: Optional[str]) -> Dict[str, str]:
    normalized = normalize_yasa_language(language, allow_auto=False)
    if not normalized:
        raise ValueError("未检测到可用于 YASA 的项目语言，请在创建时手动指定支持语言")
    profile = YASA_PROFILE_MAPPING.get(normalized)
    if profile:
        return profile
    raise ValueError(YASA_LANGUAGE_ERROR_TEMPLATE.format(language=normalized))
