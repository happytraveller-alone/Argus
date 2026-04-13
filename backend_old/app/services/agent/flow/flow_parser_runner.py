from __future__ import annotations

import asyncio
import json
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.scanner_runner import SCANNER_MOUNT_PATH, ScannerRunSpec, run_scanner_container


def _run_coroutine_blocking(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: Dict[str, Any] = {}
    error: Dict[str, BaseException] = {}

    def _target() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive
            error["value"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join()
    if "value" in error:
        raise error["value"]
    return result.get("value")


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

            spec = ScannerRunSpec(
                scanner_type="flow_parser",
                image=self.image,
                workspace_dir=str(workspace),
                command=[
                    "python3",
                    "/opt/flow-parser/flow_parser_runner.py",
                    subcommand,
                    "--request",
                    f"{SCANNER_MOUNT_PATH}/request.json",
                    "--response",
                    f"{SCANNER_MOUNT_PATH}/response.json",
                ],
                timeout_seconds=int(timeout_seconds or self.timeout_seconds),
                env={},
                expected_exit_codes=[0],
            )
            result = _run_coroutine_blocking(run_scanner_container(spec))
            if not getattr(result, "success", False):
                return {"ok": False, "error": getattr(result, "error", None) or "flow_parser_runner_failed"}
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
