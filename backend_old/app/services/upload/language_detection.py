from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Set


# 显示名称与前端保持一致
_EXT_LANGUAGE_MAP = {
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".py": "Python",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".cc": "C++",
    ".cxx": "C++",
    ".c": "C++",
    ".hpp": "C++",
    ".h": "C++",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
}

_MARKER_LANGUAGE_MAP = {
    "package.json": "JavaScript",
    "tsconfig.json": "TypeScript",
    "requirements.txt": "Python",
    "pyproject.toml": "Python",
    "pom.xml": "Java",
    "build.gradle": "Java",
    "build.gradle.kts": "Java",
    "go.mod": "Go",
    "cargo.toml": "Rust",
    "gemfile": "Ruby",
    "composer.json": "PHP",
    "package.swift": "Swift",
}

_ORDERED_LANGUAGES = [
    "JavaScript",
    "TypeScript",
    "Python",
    "Java",
    "Go",
    "Rust",
    "C++",
    "C#",
    "PHP",
    "Ruby",
    "Swift",
    "Kotlin",
]


def detect_languages_from_paths(file_paths: Iterable[str]) -> List[str]:
    """
    基于文件路径推断项目编程语言。

    说明：
    - 使用扩展名 + 常见项目标记文件进行推断；
    - 输出顺序固定，便于前端稳定展示。
    """
    found: Set[str] = set()

    for raw_path in file_paths:
        path = str(raw_path).strip().replace("\\", "/").lower()
        if not path:
            continue

        filename = path.rsplit("/", 1)[-1]
        if filename in _MARKER_LANGUAGE_MAP:
            found.add(_MARKER_LANGUAGE_MAP[filename])

        ext = Path(filename).suffix.lower()
        if ext in _EXT_LANGUAGE_MAP:
            found.add(_EXT_LANGUAGE_MAP[ext])

    return [lang for lang in _ORDERED_LANGUAGES if lang in found]
