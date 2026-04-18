from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.services.agent.core.flow.flow_parser_runner import get_flow_parser_runner_client

logger = logging.getLogger(__name__)

DOT_EDGE_RE = re.compile(r'"([^"]+)"\s*->\s*"([^"]+)"')
SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
}


@dataclass
class Code2FlowGraphResult:
    edges: Dict[str, Set[str]] = field(default_factory=dict)
    blocked_reasons: List[str] = field(default_factory=list)
    used_engine: str = "fallback"
    diagnostics: Dict[str, str] = field(default_factory=dict)

    def add_edge(self, src: str, dst: str) -> None:
        if not src or not dst:
            return
        self.edges.setdefault(src, set()).add(dst)


class Code2FlowCallGraph:
    """Optional code2flow bridge.

    This component is intentionally best-effort. If code2flow is missing or fails,
    callers can still continue with AST-only path inference.
    """

    def __init__(
        self,
        project_root: str,
        target_files: Optional[List[str]] = None,
        timeout_sec: int = 40,
        max_files: int = 400,
    ):
        self.project_root = Path(project_root).resolve()
        self.target_files = [self._normalize_rel_path(item) for item in (target_files or []) if item]
        self.timeout_sec = max(10, int(timeout_sec))
        self.max_files = max(20, int(max_files))

    def _normalize_rel_path(self, raw_path: str) -> str:
        return str(raw_path).replace("\\", "/").lstrip("./")

    def _iter_candidate_files(self) -> List[Path]:
        files: List[Path] = []
        if self.target_files:
            for rel in sorted(set(self.target_files)):
                path = (self.project_root / rel).resolve()
                if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    files.append(path)
            return files[: self.max_files]

        for path in self.project_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            rel = path.as_posix()
            if "/.git/" in rel or "/node_modules/" in rel:
                continue
            files.append(path)
            if len(files) >= self.max_files:
                break
        return files

    def _normalize_symbol_name(self, raw_node: str) -> str:
        node = raw_node.strip().strip('"')
        if not node:
            return ""

        # Some outputs include file paths and line numbers.
        node = node.replace("\\", "/")
        if ":" in node:
            node = node.split(":")[-1]
        if "(" in node:
            node = node.split("(", 1)[0]

        # Keep the right-most function token for matching AST symbols by name.
        tokens = re.split(r"[./:#\\s]+", node)
        token = tokens[-1] if tokens else node
        return token.strip()

    def _parse_dot_edges(self, dot_text: str) -> Dict[str, Set[str]]:
        edges: Dict[str, Set[str]] = {}
        for src_raw, dst_raw in DOT_EDGE_RE.findall(dot_text):
            src = self._normalize_symbol_name(src_raw)
            dst = self._normalize_symbol_name(dst_raw)
            if not src or not dst or src == dst:
                continue
            edges.setdefault(src, set()).add(dst)
        return edges

    @staticmethod
    def _normalize_runner_blocked_reasons(
        blocked_reasons: object,
        diagnostics: Dict[str, str],
    ) -> List[str]:
        raw_reasons = [
            str(item).strip()
            for item in (blocked_reasons or [])
            if str(item).strip()
        ]
        if any(reason in {"code2flow_not_installed", "code2flow_binary_not_found"} for reason in raw_reasons):
            return ["code2flow_not_installed"]

        error_text = str(diagnostics.get("error") or "").strip()
        if error_text == "code2flow_binary_not_found":
            return ["code2flow_not_installed"]

        if raw_reasons:
            return raw_reasons
        if error_text:
            return ["code2flow_exec_failed"]
        return []

    def generate(self) -> Code2FlowGraphResult:
        result = Code2FlowGraphResult()

        file_paths = self._iter_candidate_files()
        if not file_paths:
            result.blocked_reasons.append("code2flow_no_candidate_files")
            return result

        files_payload: List[Dict[str, str]] = []
        for file_path in file_paths:
            try:
                files_payload.append(
                    {
                        "file_path": str(file_path.relative_to(self.project_root)).replace("\\", "/"),
                        "content": file_path.read_text(encoding="utf-8", errors="replace"),
                    }
                )
            except Exception:
                continue

        if not files_payload:
            result.blocked_reasons.append("code2flow_no_candidate_files")
            return result

        try:
            runner = get_flow_parser_runner_client()
            payload = runner.generate_code2flow_callgraph(
                files_payload,
                timeout_seconds=self.timeout_sec,
            )
        except Exception as exc:
            result.blocked_reasons.append("code2flow_not_installed")
            result.diagnostics["error"] = f"{type(exc).__name__}: {exc}"
            return result

        if not isinstance(payload, dict):
            result.blocked_reasons.append("code2flow_exec_failed")
            result.diagnostics["error"] = "invalid_runner_response"
            return result

        result.used_engine = str(payload.get("used_engine") or "fallback")
        result.diagnostics.update(
            payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
        )

        if payload.get("error"):
            result.diagnostics["error"] = str(payload["error"])

        if payload.get("ok") is False:
            result.blocked_reasons.extend(
                self._normalize_runner_blocked_reasons(
                    payload.get("blocked_reasons"),
                    result.diagnostics,
                )
            )
            if not result.blocked_reasons:
                result.blocked_reasons.append("code2flow_exec_failed")
            return result

        raw_edges = payload.get("edges")
        if not isinstance(raw_edges, dict):
            result.blocked_reasons.append("code2flow_no_edges")
            return result

        parsed_edges: Dict[str, Set[str]] = {}
        for src, targets in raw_edges.items():
            src_name = str(src or "").strip()
            if not src_name:
                continue
            if isinstance(targets, list):
                parsed_edges[src_name] = {str(item).strip() for item in targets if str(item).strip()}
            elif isinstance(targets, set):
                parsed_edges[src_name] = {str(item).strip() for item in targets if str(item).strip()}
        if not parsed_edges:
            result.blocked_reasons.append("code2flow_no_edges")
            return result

        result.edges = parsed_edges
        result.used_engine = str(payload.get("used_engine") or "code2flow")
        result.diagnostics["edge_count"] = str(sum(len(v) for v in parsed_edges.values()))
        result.diagnostics["node_count"] = str(len(parsed_edges))
        return result


__all__ = ["Code2FlowCallGraph", "Code2FlowGraphResult"]
