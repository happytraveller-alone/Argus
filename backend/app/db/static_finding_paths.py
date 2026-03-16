import os
import posixpath
import re
import zipfile
from pathlib import Path
from typing import Iterable, Optional, Set


_PATH_SEPARATORS_RE = re.compile(r"/+")
_LIKELY_PROJECT_ROOT_SEGMENTS = {
    "src",
    "include",
    "lib",
    "app",
    "apps",
    "test",
    "tests",
    "config",
    "configs",
}


def _normalize_path_text(path_value: str) -> str:
    raw = str(path_value or "").strip().replace("\\", "/")
    if not raw:
        return ""

    has_leading_slash = raw.startswith("/")
    collapsed = _PATH_SEPARATORS_RE.sub("/", raw)
    normalized = posixpath.normpath(collapsed)

    if normalized == ".":
        return ""
    if has_leading_slash and not normalized.startswith("/"):
        return f"/{normalized}"
    return normalized


def _normalize_relative_path(path_value: str) -> str:
    normalized = _normalize_path_text(path_value).lstrip("/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def normalize_static_scan_file_path(
    path_value: str,
    project_root: Optional[str],
) -> str:
    normalized = _normalize_path_text(path_value)
    if not normalized:
        return ""

    normalized_root = _normalize_path_text(project_root or "")
    if normalized_root:
        try:
            relative = os.path.relpath(normalized, normalized_root)
            relative = _normalize_relative_path(relative)
            if relative and relative != "." and not relative.startswith("../"):
                return relative
        except Exception:
            pass

    if os.path.isabs(normalized):
        return _normalize_relative_path(os.path.basename(normalized))

    return _normalize_relative_path(normalized)


def build_legacy_static_finding_path_candidates(file_path: str) -> list[str]:
    normalized = _normalize_path_text(file_path)
    if not normalized:
        return []

    candidates: list[str] = []

    leading_trimmed = _normalize_relative_path(normalized)
    if leading_trimmed:
        candidates.append(leading_trimmed)

    parts = [part for part in leading_trimmed.split("/") if part]
    if len(parts) >= 3 and parts[0] == "tmp":
        candidates.append("/".join(parts[2:]))
    if len(parts) >= 4 and parts[0] == "tmp":
        candidates.append("/".join(parts[3:]))

    basename = os.path.basename(leading_trimmed)
    if basename:
        candidates.append(basename)

    deduplicated: list[str] = []
    seen = set()
    for item in candidates:
        normalized_item = _normalize_relative_path(item)
        if not normalized_item or normalized_item in seen:
            continue
        deduplicated.append(normalized_item)
        seen.add(normalized_item)
    return deduplicated


def build_zip_member_path_candidates(file_path: str) -> list[str]:
    normalized = _normalize_relative_path(file_path)
    if not normalized:
        return []

    candidates: list[str] = []
    seen = set()

    def _append(value: str) -> None:
        normalized_value = _normalize_relative_path(value)
        if not normalized_value or normalized_value in seen:
            return
        candidates.append(normalized_value)
        seen.add(normalized_value)

    _append(normalized)

    parts = [part for part in normalized.split("/") if part]
    if len(parts) >= 2:
        first_segment = parts[0].lower()
        second_segment = parts[1].lower()
        should_strip_archive_root = (
            first_segment != "tmp"
            and first_segment not in _LIKELY_PROJECT_ROOT_SEGMENTS
            and (
                second_segment in _LIKELY_PROJECT_ROOT_SEGMENTS
                or "." in parts[1]
            )
        )
        if should_strip_archive_root:
            _append("/".join(parts[1:]))

    for candidate in build_legacy_static_finding_path_candidates(file_path):
        _append(candidate)

    return candidates


def resolve_zip_member_path(
    file_path: str,
    known_relative_paths: Iterable[str],
) -> Optional[str]:
    normalized_known = {
        _normalize_relative_path(item)
        for item in known_relative_paths
        if _normalize_relative_path(item)
    }
    for candidate in build_zip_member_path_candidates(file_path):
        if candidate in normalized_known:
            return candidate
    return None


def resolve_legacy_static_finding_path(
    file_path: str,
    known_relative_paths: Iterable[str],
) -> Optional[str]:
    return resolve_zip_member_path(file_path, known_relative_paths)


def collect_zip_relative_paths(zip_path: str | Path) -> Set[str]:
    normalized_paths: Set[str] = set()
    with zipfile.ZipFile(Path(zip_path), "r") as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            normalized = _normalize_relative_path(member.filename)
            if normalized:
                normalized_paths.add(normalized)
    return normalized_paths
