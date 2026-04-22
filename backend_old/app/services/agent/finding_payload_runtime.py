from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

from app.services.agent.runtime_settings import settings


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
    repo_root = Path(__file__).resolve().parents[4]
    repo_fallback = repo_root / "backend" / "target" / "debug" / "backend-runtime-startup"
    if repo_fallback.is_file():
        return str(repo_fallback)
    return configured or "/usr/local/bin/backend-runtime-startup"


class FindingPayloadRuntimeBridge:
    def __init__(self, *, timeout_seconds: int = 30) -> None:
        self.timeout_seconds = max(1, int(timeout_seconds or 30))

    def _invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_payload = {
            "payload": dict(payload or {}),
            "ordering": _build_object_ordering(dict(payload or {})),
        }
        with tempfile.TemporaryDirectory(prefix="finding-payload-runtime-") as workspace_dir:
            request_path = Path(workspace_dir) / "request.json"
            request_path.write_text(
                json.dumps(request_payload, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

            try:
                completed = subprocess.run(
                    [
                        _runtime_startup_binary(),
                        "finding-payload",
                        "normalize",
                        "--request",
                        str(request_path),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=self.timeout_seconds,
                )
            except OSError:
                return {"ok": False, "error": "finding_payload_runtime_unavailable"}
            except subprocess.TimeoutExpired:
                return {"ok": False, "error": "finding_payload_runtime_timeout"}

        stdout_text = (completed.stdout or "").strip()
        if stdout_text:
            try:
                parsed = json.loads(stdout_text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return parsed

        stderr_text = (completed.stderr or "").strip()
        return {
            "ok": False,
            "error": stderr_text
            or stdout_text
            or f"finding_payload_runtime_failed:{completed.returncode}",
        }

    def normalize_payload(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
        response = self._invoke(dict(payload or {}))
        if not isinstance(response, dict) or not response.get("ok", False):
            raise RuntimeError(str(response.get("error") if isinstance(response, dict) else "finding_payload_runtime_failed"))

        normalized_payload = response.get("normalized_payload")
        repair_map = response.get("repair_map")
        if not isinstance(normalized_payload, dict) or not isinstance(repair_map, dict):
            raise RuntimeError("finding_payload_runtime_invalid_response")
        return dict(normalized_payload), {
            str(key): str(value) for key, value in repair_map.items()
        }


def normalize_push_finding_payload(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    return FindingPayloadRuntimeBridge().normalize_payload(payload)


def _build_object_ordering(payload: Dict[str, Any]) -> Dict[str, list[str]]:
    ordering: Dict[str, list[str]] = {}

    def _walk(path: str, value: Any) -> None:
        if isinstance(value, dict):
            ordering[path] = [str(key) for key in value.keys()]
            for key, nested_value in value.items():
                _walk(f"{path}.{key}", nested_value)
            return

        if isinstance(value, str) and path.endswith((".raw_input", ".finding_metadata")):
            try:
                parsed = json.loads(value)
            except Exception:
                return
            if isinstance(parsed, dict):
                _walk(path, parsed)

    _walk("payload", dict(payload or {}))
    return ordering


__all__ = [
    "FindingPayloadRuntimeBridge",
    "normalize_push_finding_payload",
]
