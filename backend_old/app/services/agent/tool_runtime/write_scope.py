from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

HARD_MAX_WRITABLE_FILES_PER_TASK = 50

_WRITE_TOOL_NAMES: Set[str] = {"edit_file", "write_file"}
_BLOCKED_WRITE_TOOLS: Set[str] = {"move_file", "create_directory"}
_FORBIDDEN_SEGMENTS: Set[str] = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    ".pytest_cache",
}


@dataclass(frozen=True)
class WriteScopeDecision:
    allowed: bool
    reason: str
    file_path: Optional[str]
    total_files: int
    added_to_scope: bool = False


class TaskWriteScopeGuard:
    """Per-task write scope guard.

    Rules:
    - every write target must be an in-project relative file path;
    - disallow directory-level / wildcard / project-wide writes;
    - disallow writes under forbidden segments;
    - writable allowlist is evidence-bound and capped by HARD_MAX_WRITABLE_FILES_PER_TASK.
    """

    def __init__(
        self,
        *,
        project_root: str,
        max_writable_files_per_task: int = HARD_MAX_WRITABLE_FILES_PER_TASK,
        require_evidence_binding: bool = True,
        forbid_project_wide_writes: bool = True,
    ) -> None:
        self.project_root = os.path.normpath(str(project_root or "").strip())
        configured_cap = int(max_writable_files_per_task or HARD_MAX_WRITABLE_FILES_PER_TASK)
        configured_cap = max(1, configured_cap)
        self.max_writable_files_per_task = min(configured_cap, HARD_MAX_WRITABLE_FILES_PER_TASK)
        self.require_evidence_binding = bool(require_evidence_binding)
        self.forbid_project_wide_writes = bool(forbid_project_wide_writes)
        self._writable_files: Set[str] = set()

    @property
    def writable_files(self) -> Set[str]:
        return set(self._writable_files)

    @staticmethod
    def _normalize_rel_path(path_value: str) -> str:
        normalized = str(path_value or "").replace("\\", "/").strip()
        while normalized.startswith("./"):
            normalized = normalized[2:]
        while normalized.startswith("/"):
            normalized = normalized[1:]
        while "//" in normalized:
            normalized = normalized.replace("//", "/")
        return normalized

    @staticmethod
    def _contains_wildcard(path_value: str) -> bool:
        text = str(path_value or "")
        return any(token in text for token in ("*", "?", "[", "]", "{", "}"))

    @staticmethod
    def _looks_like_directory(path_value: str) -> bool:
        text = str(path_value or "").strip().replace("\\", "/")
        if not text:
            return True
        if text.endswith("/"):
            return True
        basename = os.path.basename(text)
        if not basename:
            return True
        return "." not in basename

    def _normalize_in_project_path(self, file_path: Any) -> Tuple[Optional[str], Optional[str]]:
        raw = str(file_path or "").strip().replace("\\", "/")
        if not raw:
            return None, "write_scope_not_allowed"

        if self._contains_wildcard(raw):
            return None, "write_scope_path_forbidden"

        root_norm = self.project_root
        if not root_norm:
            return None, "write_scope_not_allowed"

        if os.path.isabs(raw):
            candidate = os.path.normpath(raw)
            try:
                if os.path.commonpath([candidate, root_norm]) != root_norm:
                    return None, "write_scope_path_forbidden"
            except Exception:
                return None, "write_scope_path_forbidden"
            rel = os.path.relpath(candidate, root_norm).replace("\\", "/")
        else:
            joined = os.path.normpath(os.path.join(root_norm, raw))
            try:
                if os.path.commonpath([joined, root_norm]) != root_norm:
                    return None, "write_scope_path_forbidden"
            except Exception:
                return None, "write_scope_path_forbidden"
            rel = os.path.relpath(joined, root_norm).replace("\\", "/")

        rel = self._normalize_rel_path(rel)
        if not rel or rel in {".", ".."}:
            return None, "write_scope_path_forbidden"

        parts = [part for part in rel.split("/") if part]
        if any(part in _FORBIDDEN_SEGMENTS for part in parts):
            return None, "write_scope_path_forbidden"

        if self._looks_like_directory(rel):
            return None, "write_scope_path_forbidden"

        return rel, None

    def _extract_write_target(self, tool_input: Dict[str, Any]) -> Optional[str]:
        for key in ("file_path", "path", "target_path", "target_file", "filepath"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    def _has_evidence_binding(self, tool_input: Dict[str, Any]) -> bool:
        for key in ("finding_id", "todo_id", "reason", "evidence_ref"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                return True
        return False

    def _is_project_wide_write(self, tool_input: Dict[str, Any]) -> bool:
        if not self.forbid_project_wide_writes:
            return False

        for key in ("directory", "root", "glob", "pattern"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                return True

        for key in (
            "recursive",
            "replace_all",
            "apply_to_all",
            "project_wide",
            "all_files",
            "batch",
        ):
            if tool_input.get(key) is True:
                return True

        return False

    def is_write_tool(self, tool_name: str) -> bool:
        normalized = str(tool_name or "").strip().lower()
        return normalized in _WRITE_TOOL_NAMES or normalized in _BLOCKED_WRITE_TOOLS

    def evaluate_write_request(self, tool_name: str, tool_input: Dict[str, Any]) -> WriteScopeDecision:
        normalized_tool = str(tool_name or "").strip().lower()
        if normalized_tool in _BLOCKED_WRITE_TOOLS:
            return WriteScopeDecision(
                allowed=False,
                reason="write_scope_path_forbidden",
                file_path=None,
                total_files=len(self._writable_files),
            )

        if normalized_tool not in _WRITE_TOOL_NAMES:
            return WriteScopeDecision(
                allowed=True,
                reason="not_write_tool",
                file_path=None,
                total_files=len(self._writable_files),
            )

        if self._is_project_wide_write(tool_input):
            return WriteScopeDecision(
                allowed=False,
                reason="write_scope_path_forbidden",
                file_path=None,
                total_files=len(self._writable_files),
            )

        target = self._extract_write_target(tool_input)
        normalized_path, path_error = self._normalize_in_project_path(target)
        if path_error or not normalized_path:
            return WriteScopeDecision(
                allowed=False,
                reason=path_error or "write_scope_not_allowed",
                file_path=None,
                total_files=len(self._writable_files),
            )

        if normalized_path in self._writable_files:
            return WriteScopeDecision(
                allowed=True,
                reason="write_scope_allowed",
                file_path=normalized_path,
                total_files=len(self._writable_files),
                added_to_scope=False,
            )

        if self.require_evidence_binding and not self._has_evidence_binding(tool_input):
            return WriteScopeDecision(
                allowed=False,
                reason="write_scope_not_allowed",
                file_path=normalized_path,
                total_files=len(self._writable_files),
            )

        if len(self._writable_files) >= self.max_writable_files_per_task:
            return WriteScopeDecision(
                allowed=False,
                reason="write_scope_limit_reached",
                file_path=normalized_path,
                total_files=len(self._writable_files),
            )

        self._writable_files.add(normalized_path)
        return WriteScopeDecision(
            allowed=True,
            reason="write_scope_allowed",
            file_path=normalized_path,
            total_files=len(self._writable_files),
            added_to_scope=True,
        )

    def register_evidence_path(self, file_path: Any) -> bool:
        normalized_path, path_error = self._normalize_in_project_path(file_path)
        if path_error or not normalized_path:
            return False

        if normalized_path in self._writable_files:
            return True

        if len(self._writable_files) >= self.max_writable_files_per_task:
            return False

        self._writable_files.add(normalized_path)
        return True

    def register_evidence_paths(self, file_paths: Iterable[Any]) -> int:
        added = 0
        for file_path in file_paths:
            if self.register_evidence_path(file_path):
                added += 1
        return added

    def seed_from_task_inputs(
        self,
        *,
        target_files: Optional[List[str]] = None,
        findings: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        seed_paths: List[Any] = []
        if isinstance(target_files, list):
            seed_paths.extend(target_files)

        if isinstance(findings, list):
            for finding in findings:
                if not isinstance(finding, dict):
                    continue
                seed_paths.append(finding.get("file_path"))

        return self.register_evidence_paths(seed_paths)

    @staticmethod
    def decision_metadata(decision: WriteScopeDecision) -> Dict[str, Any]:
        return {
            "write_scope_allowed": bool(decision.allowed),
            "write_scope_reason": decision.reason,
            "write_scope_file": decision.file_path,
            "write_scope_total_files": int(decision.total_files),
        }
