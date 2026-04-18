from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings


def _runtime_startup_binary() -> str:
    env_configured = str(os.environ.get("BACKEND_RUNTIME_STARTUP_BIN", "") or "").strip()
    if env_configured:
        return env_configured
    configured = str(
        getattr(
            settings,
            "BACKEND_RUNTIME_STARTUP_BIN",
            "/usr/local/bin/backend-runtime-startup",
        )
        or ""
    ).strip()
    return configured or "/usr/local/bin/backend-runtime-startup"


class FlowParserRuntimeBridge:
    def __init__(
        self,
        *,
        image: Optional[str] = None,
        enabled: Optional[bool] = None,
        timeout_seconds: Optional[int] = None,
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

    @staticmethod
    def _workspace_root() -> Path:
        configured = str(getattr(settings, "SCAN_WORKSPACE_ROOT", "/tmp/vulhunter/scans") or "").strip()
        base_root = Path(configured or "/tmp/vulhunter/scans")
        return base_root / "flow-parser-runtime"

    def _invoke(
        self,
        operation: str,
        payload: Dict[str, Any],
        *,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "error": "flow_parser_runtime_disabled"}

        request_payload = dict(payload)
        request_payload.setdefault("image", self.image)
        request_payload.setdefault(
            "timeout_seconds",
            int(timeout_seconds if timeout_seconds is not None else self.timeout_seconds),
        )

        workspace_root = self._workspace_root()
        tempdir_kwargs: Dict[str, Any] = {"prefix": "flow-parser-runtime-"}
        try:
            workspace_root.mkdir(parents=True, exist_ok=True)
            tempdir_kwargs["dir"] = str(workspace_root)
        except Exception:
            pass

        try:
            workspace_context = tempfile.TemporaryDirectory(**tempdir_kwargs)
        except OSError:
            workspace_context = tempfile.TemporaryDirectory(
                prefix=str(tempdir_kwargs.get("prefix") or "flow-parser-runtime-")
            )

        with workspace_context as workspace_dir:
            workspace = Path(workspace_dir)
            request_path = workspace / "request.json"
            request_path.write_text(
                json.dumps(request_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            try:
                completed = subprocess.run(
                    [
                        _runtime_startup_binary(),
                        "flow-parser",
                        operation,
                        "--request",
                        str(request_path),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=max(
                        1,
                        int(timeout_seconds if timeout_seconds is not None else self.timeout_seconds),
                    ),
                )
            except OSError as exc:
                return {"ok": False, "error": str(exc)}
            except subprocess.TimeoutExpired:
                return {"ok": False, "error": "flow_parser_runtime_bridge_timeout"}

        stdout_text = (completed.stdout or "").strip()
        if stdout_text:
            try:
                parsed = json.loads(stdout_text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        stderr_text = (completed.stderr or "").strip()
        return {
            "ok": False,
            "error": stderr_text
            or stdout_text
            or f"flow_parser_runtime_bridge_failed:{completed.returncode}",
        }

    def extract_definitions_batch(
        self,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
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
