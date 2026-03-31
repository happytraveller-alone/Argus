from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

YASA_SUPPORTED_LANGUAGES: tuple[str, ...] = (
    "java",
    "golang",
    "typescript",
    "python",
)

YASA_SUPPORTED_LANGUAGES_TEXT = "/".join(YASA_SUPPORTED_LANGUAGES)

YASA_LANGUAGE_ERROR_TEMPLATE = (
    "不支持语言: {language}，YASA 仅支持 java/golang/typescript/python"
)

YASA_PROFILE_MAPPING: Dict[str, Dict[str, str]] = {
    "python": {
        "language": "python",
        "checker_pack": "taint-flow-python-default",
        "rule_config": "rule_config_python.json",
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
    "ts": "typescript",
    "typescript": "typescript",
    "go": "golang",
    "golang": "golang",
    "java": "java",
}

_YASA_LANGUAGE_PRIORITY: tuple[str, ...] = (
    "java",
    "golang",
    "typescript",
    "python",
)

_YASA_LANGUAGE_SUFFIX_MAP: Dict[str, Tuple[str, ...]] = {
    "python": (".py",),
    "typescript": (".ts", ".tsx"),
    "golang": (".go",),
    "java": (".java",),
}

_YASA_SUFFIX_LANGUAGE_MAP: Dict[str, str] = {}
for _language, _suffixes in _YASA_LANGUAGE_SUFFIX_MAP.items():
    for _suffix in _suffixes:
        _YASA_SUFFIX_LANGUAGE_MAP[_suffix] = _language

_YASA_LANGUAGE_SCAN_SKIP_DIRS: set[str] = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    ".idea",
    ".vscode",
    "__pycache__",
    ".next",
}

MAX_YASA_LANGUAGE_DETECTION_FILES = 120000


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


def is_yasa_blocked_project_language(raw_languages: Any) -> bool:
    project_languages = parse_programming_languages(raw_languages)
    if not project_languages:
        return True

    for item in project_languages:
        normalized = str(item or "").strip().lower()
        resolved = _YASA_LANGUAGE_ALIAS.get(normalized)
        if resolved and resolved in YASA_SUPPORTED_LANGUAGES:
            return False
    return True


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
    if is_yasa_blocked_project_language(raw_languages):
        return None

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


def collect_yasa_language_counts_from_source_tree(source_root: Optional[str]) -> Dict[str, int]:
    normalized_root = str(source_root or "").strip()
    if not normalized_root:
        return {}

    root_path = Path(normalized_root)
    if not root_path.exists() or not root_path.is_dir():
        return {}

    counts: Dict[str, int] = {}
    scanned_files = 0

    for current_root, dirs, files in os.walk(root_path):
        dirs[:] = [
            item
            for item in dirs
            if item not in _YASA_LANGUAGE_SCAN_SKIP_DIRS and not item.startswith(".")
        ]
        for filename in files:
            scanned_files += 1
            if scanned_files > MAX_YASA_LANGUAGE_DETECTION_FILES:
                return counts
            suffix = Path(filename).suffix.lower()
            language = _YASA_SUFFIX_LANGUAGE_MAP.get(suffix)
            if not language:
                continue
            counts[language] = int(counts.get(language, 0) or 0) + 1

    return counts


def resolve_yasa_language_from_source_tree(source_root: Optional[str]) -> Optional[str]:
    counts = collect_yasa_language_counts_from_source_tree(source_root)
    if not counts:
        return None

    best_language = None
    best_count = -1
    priority_index = {lang: index for index, lang in enumerate(_YASA_LANGUAGE_PRIORITY)}

    for language, count in counts.items():
        normalized_count = int(count or 0)
        if normalized_count > best_count:
            best_language = language
            best_count = normalized_count
            continue
        if normalized_count != best_count:
            continue
        if best_language is None:
            best_language = language
            continue
        if priority_index.get(language, 10_000) < priority_index.get(best_language, 10_000):
            best_language = language

    return best_language


def resolve_yasa_language_with_preference(
    *,
    preferred_language: Optional[str],
    programming_languages: Any,
    source_root: Optional[str] = None,
) -> Optional[str]:
    normalized_preference = normalize_yasa_language(preferred_language, allow_auto=True)
    if is_yasa_blocked_project_language(programming_languages):
        return None
    if normalized_preference and normalized_preference != "auto":
        return normalized_preference
    resolved_from_source = resolve_yasa_language_from_source_tree(source_root)
    if resolved_from_source:
        return resolved_from_source
    return resolve_yasa_language_from_programming_languages(programming_languages)


def resolve_yasa_language_profile(language: Optional[str]) -> Dict[str, str]:
    normalized = normalize_yasa_language(language, allow_auto=False)
    if not normalized:
        raise ValueError("未检测到可用于 YASA 的项目语言，请在创建时手动指定支持语言")
    profile = YASA_PROFILE_MAPPING.get(normalized)
    if profile:
        return profile
    raise ValueError(YASA_LANGUAGE_ERROR_TEMPLATE.format(language=normalized))
