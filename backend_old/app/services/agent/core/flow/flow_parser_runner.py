from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings

SCANNER_MOUNT_PATH = "/scan"

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[6]


def _backend_runtime_startup_bin() -> str:
    explicit = str(getattr(settings, "BACKEND_RUNTIME_STARTUP_BIN", "") or "").strip()
    if explicit:
        return explicit

    candidates = [
        Path("/usr/local/bin/backend-runtime-startup"),
        _repo_root() / "backend" / "target" / "debug" / "backend-runtime-startup",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[0])


def _run_runner_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    workspace = Path(str(spec.get("workspace_dir") or ""))
    spec_path = workspace / "runner_spec.json"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            _backend_runtime_startup_bin(),
            "runner",
            "execute",
            "--spec",
            str(spec_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        return {
            "success": False,
            "error": stderr or stdout or "runner_bridge_failed",
            "exit_code": proc.returncode,
            "container_id": None,
            "stdout_path": None,
            "stderr_path": None,
        }

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {
            "success": False,
            "error": "invalid_runner_response",
            "exit_code": 1,
            "container_id": None,
            "stdout_path": None,
            "stderr_path": None,
        }

    if not isinstance(payload, dict):
        return {
            "success": False,
            "error": "invalid_runner_response",
            "exit_code": 1,
            "container_id": None,
            "stdout_path": None,
            "stderr_path": None,
        }
    return payload


class FlowParserRunnerClient:
    def __init__(
        self,
        *,
        image: Optional[str] = None,
        enabled: Optional[bool] = None,
        timeout_seconds: Optional[int] = None,
        batch_max_files: Optional[int] = None,
        batch_max_bytes: Optional[int] = None,
    ) -> None:
        self.image = image or str(
            getattr(settings, "FLOW_PARSER_RUNNER_IMAGE", "vulhunter/flow-parser-runner:latest")
        )
        self.enabled = (
            bool(getattr(settings, "FLOW_PARSER_RUNNER_ENABLED", True))
            if enabled is None
            else bool(enabled)
        )
        self.timeout_seconds = int(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "FLOW_PARSER_RUNNER_TIMEOUT_SECONDS", 120)
        )
        self.batch_max_files = int(
            batch_max_files
            if batch_max_files is not None
            else getattr(settings, "FLOW_PARSER_RUNNER_BATCH_MAX_FILES", 100)
        )
        self.batch_max_bytes = int(
            batch_max_bytes
            if batch_max_bytes is not None
            else getattr(settings, "FLOW_PARSER_RUNNER_BATCH_MAX_BYTES", 8 * 1024 * 1024)
        )

    @staticmethod
    def _workspace_root() -> Path:
        configured = str(getattr(settings, "SCAN_WORKSPACE_ROOT", "/tmp/vulhunter/scans") or "").strip()
        base_root = Path(configured or "/tmp/vulhunter/scans")
        return base_root / "flow-parser-runner"

    def _invoke(self, subcommand: str, payload: Dict[str, Any], *, timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "flow_parser_runner_disabled"}

        workspace_root = self._workspace_root()
        tempdir_kwargs: Dict[str, Any] = {"prefix": "flow-parser-runner-"}
        try:
            workspace_root.mkdir(parents=True, exist_ok=True)
            tempdir_kwargs["dir"] = str(workspace_root)
        except Exception:
            pass

        try:
            workspace_context = tempfile.TemporaryDirectory(**tempdir_kwargs)
        except OSError:
            workspace_context = tempfile.TemporaryDirectory(prefix=str(tempdir_kwargs.get("prefix") or "flow-parser-runner-"))

        with workspace_context as workspace_dir:
            workspace = Path(workspace_dir)
            request_path = workspace / "request.json"
            response_path = workspace / "response.json"
            request_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            workspace_root_override: Optional[str] = None
            try:
                if not workspace.is_relative_to(workspace_root):
                    workspace_root_override = str(workspace.parent)
            except Exception:
                workspace_root_override = str(workspace.parent)

            result = _run_runner_spec(
                {
                    "scanner_type": "flow_parser",
                    "image": self.image,
                    "workspace_dir": str(workspace),
                    "command": [
                        "python3",
                        "/opt/flow-parser/flow_parser_runner.py",
                        subcommand,
                        "--request",
                        f"{SCANNER_MOUNT_PATH}/request.json",
                        "--response",
                        f"{SCANNER_MOUNT_PATH}/response.json",
                    ],
                    "timeout_seconds": int(timeout_seconds or self.timeout_seconds),
                    "env": {},
                    "expected_exit_codes": [0],
                    "workspace_root_override": workspace_root_override,
                }
            )
            if not result.get("success", False):
                return {"ok": False, "error": result.get("error") or "flow_parser_runner_failed"}
            if not response_path.exists():
                return {"ok": False, "error": "flow_parser_runner_missing_response"}
            return json.loads(response_path.read_text(encoding="utf-8"))

    def extract_definitions_batch(self, items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        response = self._invoke("definitions-batch", {"items": items})
        response_items = response.get("items") if isinstance(response, dict) else None
        if not isinstance(response_items, list):
            return {}
        results: Dict[str, Dict[str, Any]] = {}
        for item in response_items:
            if not isinstance(item, dict):
                continue
            file_path = str(item.get("file_path") or "").strip()
            if not file_path:
                continue
            results[file_path] = item
        return results

    def locate_enclosing_function(
        self,
        *,
        file_path: str,
        line_start: int,
        language: str,
        content: str,
    ) -> Optional[Dict[str, Any]]:
        response = self._invoke(
            "locate-enclosing-function",
            {
                "file_path": file_path,
                "line_start": int(line_start),
                "language": language,
                "content": content,
            },
        )
        if not isinstance(response, dict) or not response.get("ok", True):
            return None
        return response

    def generate_code2flow_callgraph(
        self,
        files: List[Dict[str, str]],
        *,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        response = self._invoke(
            "code2flow-callgraph",
            {"files": files},
            timeout_seconds=timeout_seconds,
        )
        return response if isinstance(response, dict) else {"ok": False, "error": "invalid_runner_response"}


def get_flow_parser_runner_client() -> FlowParserRunnerClient:
    return FlowParserRunnerClient()
