from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.core.config import settings
from app.services.agent.core.flow.flow_parser_runner import _runtime_startup_binary

logger = logging.getLogger(__name__)


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
    """Thin compatibility bridge to the Rust-owned code2flow runtime."""

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

    @staticmethod
    def _normalize_rel_path(raw_path: str) -> str:
        return str(raw_path).replace("\\", "/").lstrip("./")

    def _build_request(self) -> Dict[str, object]:
        return {
            "project_root": str(self.project_root),
            "target_files": list(self.target_files),
            "timeout_seconds": self.timeout_sec,
            "max_files": self.max_files,
            "image": str(
                getattr(settings, "FLOW_PARSER_RUNNER_IMAGE", "vulhunter/flow-parser-runner:latest")
                or ""
            ).strip()
            or "vulhunter/flow-parser-runner:latest",
        }

    @staticmethod
    def _result_from_payload(payload: object) -> Code2FlowGraphResult:
        result = Code2FlowGraphResult()
        if not isinstance(payload, dict):
            result.blocked_reasons.append("code2flow_exec_failed")
            result.diagnostics["error"] = "invalid_runner_response"
            return result

        result.used_engine = str(payload.get("used_engine") or "fallback")
        diagnostics = payload.get("diagnostics")
        if isinstance(diagnostics, dict):
            result.diagnostics.update(
                {
                    str(key): str(value)
                    for key, value in diagnostics.items()
                    if str(key).strip() and value is not None
                }
            )
        if payload.get("error"):
            result.diagnostics["error"] = str(payload.get("error"))

        blocked_reasons = payload.get("blocked_reasons")
        if isinstance(blocked_reasons, list):
            result.blocked_reasons.extend(
                [str(item).strip() for item in blocked_reasons if str(item).strip()]
            )

        raw_edges = payload.get("edges")
        if isinstance(raw_edges, dict):
            for src, targets in raw_edges.items():
                src_name = str(src or "").strip()
                if not src_name:
                    continue
                if isinstance(targets, list):
                    target_values = targets
                elif isinstance(targets, set):
                    target_values = list(targets)
                else:
                    continue
                cleaned_targets = {
                    str(item).strip() for item in target_values if str(item).strip()
                }
                if cleaned_targets:
                    result.edges[src_name] = cleaned_targets

        if result.blocked_reasons or result.edges:
            return result

        result.blocked_reasons.append("code2flow_exec_failed")
        result.diagnostics.setdefault("error", "invalid_code2flow_response")
        return result

    def generate(self) -> Code2FlowGraphResult:
        with tempfile.TemporaryDirectory(prefix="code2flow-runtime-") as workspace_dir:
            workspace = Path(workspace_dir)
            request_path = workspace / "request.json"
            request_path.write_text(
                json.dumps(self._build_request(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            try:
                completed = subprocess.run(
                    [
                        _runtime_startup_binary(),
                        "code2flow",
                        "--request",
                        str(request_path),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self.timeout_sec,
                )
            except OSError as exc:
                result = Code2FlowGraphResult(blocked_reasons=["code2flow_not_installed"])
                result.diagnostics["error"] = f"{type(exc).__name__}: {exc}"
                return result
            except subprocess.TimeoutExpired:
                result = Code2FlowGraphResult(blocked_reasons=["code2flow_exec_failed"])
                result.diagnostics["error"] = "code2flow_runtime_bridge_timeout"
                return result

        stdout_text = (completed.stdout or "").strip()
        if stdout_text:
            try:
                return self._result_from_payload(json.loads(stdout_text))
            except json.JSONDecodeError:
                pass

        result = Code2FlowGraphResult(blocked_reasons=["code2flow_exec_failed"])
        result.diagnostics["error"] = (
            (completed.stderr or "").strip()
            or stdout_text
            or f"code2flow_runtime_bridge_failed:{completed.returncode}"
        )
        return result


__all__ = ["Code2FlowCallGraph", "Code2FlowGraphResult"]
