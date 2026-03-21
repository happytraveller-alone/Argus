"""ZIP 项目文件筛选共享工具。"""

from pathlib import PurePosixPath
from typing import List

TEXT_EXTENSIONS = [
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".py",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".cc",
    ".hh",
    ".cs",
    ".php",
    ".rb",
    ".kt",
    ".swift",
    ".sql",
    ".sh",
    ".json",
    ".yml",
    ".yaml",
]

EXCLUDE_PATTERNS = [
    "node_modules/",
    "vendor/",
    "dist/",
    "build/",
    ".git/",
    "__pycache__/",
    ".pytest_cache/",
    "coverage/",
    ".nyc_output/",
    ".vscode/",
    ".idea/",
    ".vs/",
    "target/",
    "out/",
    "__MACOSX/",
    ".DS_Store",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    ".min.js",
    ".min.css",
    ".map",
]


def is_text_file(path: str) -> bool:
    return any(path.lower().endswith(ext) for ext in TEXT_EXTENSIONS)


def should_exclude(path: str, exclude_patterns: List[str] | None = None) -> bool:
    normalized_path = (path or "").replace("\\", "/")
    path_segments = [seg.lower() for seg in PurePosixPath(normalized_path).parts]
    if any("test" in segment for segment in path_segments[:-1]):
        return True

    all_patterns = EXCLUDE_PATTERNS + (exclude_patterns or [])
    return any(pattern in normalized_path for pattern in all_patterns)
