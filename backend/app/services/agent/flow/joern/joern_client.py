from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.agent.flow.models import FlowEvidence

logger = logging.getLogger(__name__)


class JoernClient:
    """Best-effort Joern client for deep reachability verification.

    If Joern is unavailable, callers receive a structured blocked reason and can
    safely fall back to lightweight evidence.
    """

    def __init__(self, *, enabled: bool = True, timeout_sec: int = 45):
        self.enabled = bool(enabled)
        self.timeout_sec = max(10, int(timeout_sec))
        self._joern_bin = shutil.which("joern")
        self._version_checked = False
        self._version_ok = False

    def _base_blocked(self, reason: str) -> FlowEvidence:
        return FlowEvidence(
            path_found=False,
            path_score=0.0,
            call_chain=[],
            control_conditions=[],
            taint_paths=[],
            entry_inferred=False,
            blocked_reasons=[reason],
            engine="joern",
        )

    async def _check_version(self) -> bool:
        if self._version_checked:
            return self._version_ok

        self._version_checked = True
        if not self._joern_bin:
            self._version_ok = False
            return False

        try:
            proc = await asyncio.create_subprocess_exec(
                self._joern_bin,
                "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8)
            _ = (stdout or b"").decode("utf-8", errors="ignore")
            err_text = (stderr or b"").decode("utf-8", errors="ignore")
            self._version_ok = proc.returncode == 0
            if not self._version_ok:
                logger.warning("Joern version check failed: %s", err_text[:200])
            return self._version_ok
        except Exception as exc:
            logger.warning("Joern version check exception: %s", exc)
            self._version_ok = False
            return False

    def _query_script_path(self) -> Path:
        return Path(__file__).resolve().parent / "queries" / "reachability.sc"

    def _poc_chain_batch_script_path(self) -> Path:
        return Path(__file__).resolve().parent / "queries" / "poc_trigger_chain_batch.sc"

    async def _run_query(
        self,
        *,
        project_root: str,
        file_path: str,
        line_start: int,
    ) -> Optional[Dict[str, Any]]:
        if not self._joern_bin:
            return None

        script_path = self._query_script_path()
        if not script_path.exists():
            return None

        cmd = [
            self._joern_bin,
            "--nocolors",
            "--script",
            str(script_path),
            "--param",
            f"project={project_root}",
            "--param",
            f"file={file_path}",
            "--param",
            f"line={line_start}",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_root if project_root else None,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_sec)
            stdout_text = (stdout or b"").decode("utf-8", errors="replace").strip()
            stderr_text = (stderr or b"").decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                logger.debug("Joern query failed: %s", stderr_text[:280])
                return None

            if not stdout_text:
                return None

            try:
                return json.loads(stdout_text)
            except Exception:
                logger.debug("Joern query output is not JSON, fallback heuristic used")
                return None
        except Exception as exc:
            logger.debug("Joern query exception: %s", exc)
            return None

    async def build_poc_trigger_chains_batch(
        self,
        *,
        project_root: str,
        items: List[Dict[str, Any]],
        max_flows: int = 3,
        max_nodes: int = 80,
    ) -> Dict[str, Any]:
        """Batch compute source->sink dataflow chains for eligible findings.

        Returns:
          {
            "version": 1,
            "engine": "joern_dataflow",
            "results": { key: chain_dict },
            "errors": { key: reason }
          }
        """
        if not self.enabled:
            return {
                "version": 1,
                "engine": "joern_dataflow",
                "results": {},
                "errors": {str(item.get("key")): "joern_disabled" for item in (items or []) if item.get("key")},
            }

        if not await self._check_version():
            return {
                "version": 1,
                "engine": "joern_dataflow",
                "results": {},
                "errors": {str(item.get("key")): "joern_not_available" for item in (items or []) if item.get("key")},
            }

        script_path = self._poc_chain_batch_script_path()
        if not script_path.exists():
            return {
                "version": 1,
                "engine": "joern_dataflow",
                "results": {},
                "errors": {str(item.get("key")): "script_missing" for item in (items or []) if item.get("key")},
            }

        import tempfile

        payload = {"items": items or []}
        marker_start = "<<<POC_TRIGGER_CHAIN_JSON_START>>>"
        marker_end = "<<<POC_TRIGGER_CHAIN_JSON_END>>>"

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False)
            input_path = fp.name

        cmd = [
            self._joern_bin,
            "--nocolors",
            "--script",
            str(script_path),
            "--param",
            f"project={project_root}",
            "--param",
            f"input={input_path}",
            "--param",
            f"maxFlows={max(1, int(max_flows))}",
            "--param",
            f"maxNodes={max(10, int(max_nodes))}",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_root if project_root else None,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_sec)
            out_text = (stdout or b"").decode("utf-8", errors="replace")
            err_text = (stderr or b"").decode("utf-8", errors="replace")

            if proc.returncode != 0:
                logger.debug("Joern batch chain failed: %s", (err_text or out_text)[:600])
                return {
                    "version": 1,
                    "engine": "joern_dataflow",
                    "results": {},
                    "errors": {str(item.get("key")): "joern_exec_failed" for item in (items or []) if item.get("key")},
                }

            combined = f"{out_text}\n{err_text}"
            start_idx = combined.rfind(marker_start)
            end_idx = combined.rfind(marker_end)
            if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
                logger.debug("Joern batch chain missing markers")
                return {
                    "version": 1,
                    "engine": "joern_dataflow",
                    "results": {},
                    "errors": {str(item.get("key")): "missing_json_markers" for item in (items or []) if item.get("key")},
                }

            json_text = combined[start_idx + len(marker_start) : end_idx].strip()
            try:
                parsed = json.loads(json_text)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                logger.debug("Joern batch chain JSON parse failed")

            return {
                "version": 1,
                "engine": "joern_dataflow",
                "results": {},
                "errors": {str(item.get("key")): "invalid_json" for item in (items or []) if item.get("key")},
            }
        finally:
            try:
                Path(input_path).unlink(missing_ok=True)
            except Exception:
                pass

    async def verify_reachability(
        self,
        *,
        project_root: str,
        file_path: str,
        line_start: int,
        call_chain: Optional[List[str]] = None,
        control_conditions: Optional[List[str]] = None,
    ) -> FlowEvidence:
        if not self.enabled:
            return self._base_blocked("joern_disabled")

        if not await self._check_version():
            return self._base_blocked("joern_not_available")

        payload = await self._run_query(
            project_root=project_root,
            file_path=file_path,
            line_start=max(1, int(line_start)),
        )

        if isinstance(payload, dict):
            call_chain_payload = [
                str(item) for item in (payload.get("call_chain") or []) if str(item).strip()
            ]
            control_payload = [
                str(item)
                for item in (payload.get("control_conditions") or [])
                if str(item).strip()
            ]
            blocked = [str(item) for item in (payload.get("blocked_reasons") or []) if str(item)]
            taint_paths = [str(item) for item in (payload.get("taint_paths") or []) if str(item)]

            return FlowEvidence(
                path_found=bool(payload.get("path_found")),
                path_score=float(payload.get("path_score") or 0.0),
                call_chain=call_chain_payload,
                control_conditions=control_payload,
                taint_paths=taint_paths,
                entry_inferred=bool(payload.get("entry_inferred")),
                blocked_reasons=blocked,
                engine="joern",
                extra={"source": "joern_script"},
            )

        # If Joern is available but the script didn't yield a parseable payload, do not
        # "upgrade" reachability. Preserve existing chain/conditions for debugging only.
        return FlowEvidence(
            path_found=False,
            path_score=0.0,
            call_chain=[str(item) for item in (call_chain or []) if str(item).strip()],
            control_conditions=[str(item) for item in (control_conditions or []) if str(item).strip()],
            taint_paths=[],
            entry_inferred=False,
            blocked_reasons=["joern_query_unavailable"],
            engine="joern",
            extra={"source": "joern_query_unavailable"},
        )


__all__ = ["JoernClient"]
