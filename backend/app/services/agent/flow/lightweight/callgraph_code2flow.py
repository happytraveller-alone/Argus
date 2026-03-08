from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

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

    def _run_code2flow(self, file_paths: List[Path], output_dot: str) -> Dict[str, str]:
        commands: List[List[str]] = []
        path_args = [str(item) for item in file_paths]

        binary = shutil.which("code2flow")
        if binary:
            commands.extend(
                [
                    [binary, *path_args, "-o", output_dot],
                    [binary, "-o", output_dot, *path_args],
                    [binary, *path_args, "--output", output_dot],
                ]
            )

        python_bin = shutil.which("python3") or shutil.which("python")
        if python_bin:
            commands.append([python_bin, "-m", "code2flow", *path_args, "-o", output_dot])

        if not commands:
            return {
                "error": "code2flow_binary_not_found",
            }

        last_error = ""
        for cmd in commands:
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_sec,
                )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue

            if proc.returncode == 0 and Path(output_dot).exists():
                return {
                    "command": " ".join(cmd),
                    "stderr": (proc.stderr or "").strip()[:400],
                }

            stderr = (proc.stderr or proc.stdout or "").strip()
            last_error = f"returncode={proc.returncode}; {stderr[:300]}"

        return {
            "error": last_error or "code2flow_failed",
        }

    def _has_code2flow_runtime(self) -> bool:
        if shutil.which("code2flow"):
            return True
        python_bin = shutil.which("python3") or shutil.which("python")
        if not python_bin:
            return False
        try:
            probe = subprocess.run(
                [python_bin, "-c", "import code2flow"],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            return False
        return probe.returncode == 0

    def generate(self) -> Code2FlowGraphResult:
        result = Code2FlowGraphResult()

        file_paths = self._iter_candidate_files()
        if not file_paths:
            result.blocked_reasons.append("code2flow_no_candidate_files")
            return result

        if not self._has_code2flow_runtime():
            result.blocked_reasons.append("code2flow_not_installed")
            if str(os.environ.get("CODE2FLOW_AUTO_INSTALL_FAILED") or "0").strip() == "1":
                result.blocked_reasons.append("auto_install_failed")
            return result

        with tempfile.NamedTemporaryFile(suffix=".dot", delete=False) as temp_file:
            dot_path = temp_file.name

        try:
            exec_info = self._run_code2flow(file_paths, dot_path)
            result.diagnostics.update(exec_info)

            if "error" in exec_info:
                result.blocked_reasons.append("code2flow_exec_failed")
                return result

            try:
                dot_text = Path(dot_path).read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                result.blocked_reasons.append("code2flow_dot_read_failed")
                result.diagnostics["error"] = f"{type(exc).__name__}: {exc}"
                return result

            edges = self._parse_dot_edges(dot_text)
            if not edges:
                result.blocked_reasons.append("code2flow_no_edges")
                return result

            result.edges = edges
            result.used_engine = "code2flow"
            result.diagnostics["edge_count"] = str(sum(len(v) for v in edges.values()))
            result.diagnostics["node_count"] = str(len(edges))
            return result
        finally:
            try:
                os.unlink(dot_path)
            except Exception:
                pass


__all__ = ["Code2FlowCallGraph", "Code2FlowGraphResult"]
