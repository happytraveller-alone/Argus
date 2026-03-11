from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.agent.flow.models import FlowEvidence

from .codebadger_poc_query import (
    build_poc_trigger_chain_batch_cpgql_query,
    infer_codebadger_language,
    parse_codebadger_query_data,
)
from .codebadger_mcp_client import CodeBadgerMCPClient
from .codebadger_reachability_query import build_reachability_cpgql_query

logger = logging.getLogger(__name__)


class JoernClient:
    """Best-effort Joern client for deep reachability verification.

    If Joern is unavailable, callers receive a structured blocked reason and can
    safely fall back to lightweight evidence.
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout_sec: int = 45,
        mcp_enabled: bool | None = None,
        mcp_url: str | None = None,
        mcp_prefer: bool | None = None,
        mcp_cpg_timeout_sec: int | None = None,
        mcp_query_timeout_sec: int | None = None,
    ):
        self.enabled = bool(enabled)
        self.timeout_sec = max(10, int(timeout_sec))
        self._joern_bin = shutil.which("joern")
        self._version_checked = False
        self._version_ok = False
        normalized_url = str(mcp_url or "").strip()
        self._mcp_enabled = bool(mcp_enabled) and bool(normalized_url)
        self._mcp_prefer = bool(mcp_prefer) and bool(normalized_url)
        self._mcp_url = str(mcp_url or "")
        self._mcp_cpg_timeout_sec = max(self.timeout_sec, int(mcp_cpg_timeout_sec or self.timeout_sec))
        self._mcp_query_timeout_sec = max(10, int(mcp_query_timeout_sec or self.timeout_sec))
        self._mcp_checked = False
        self._mcp_ok = False
        self._mcp = (
            CodeBadgerMCPClient(url=normalized_url)
            if normalized_url and (self._mcp_enabled or self._mcp_prefer)
            else None
        )
        # In-process cache to avoid regenerating CPG for repeated verifications
        # within the same task execution (project_root, language) -> codebase_hash.
        self._mcp_codebase_hash_cache: dict[tuple[str, str], str] = {}

    async def _check_mcp_available(self) -> bool:
        if not (self._mcp_enabled or self._mcp_prefer):
            return False
        if self._mcp_checked:
            return self._mcp_ok
        self._mcp_checked = True
        self._mcp_ok = await self._mcp.ping()
        return self._mcp_ok

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

    def _blocked_with_context(
        self,
        reason: str,
        *,
        call_chain: Optional[List[str]] = None,
        control_conditions: Optional[List[str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> FlowEvidence:
        return FlowEvidence(
            path_found=False,
            path_score=0.0,
            call_chain=[str(item) for item in (call_chain or []) if str(item).strip()],
            control_conditions=[str(item) for item in (control_conditions or []) if str(item).strip()],
            taint_paths=[],
            entry_inferred=False,
            blocked_reasons=[reason],
            engine="joern",
            extra=extra or {},
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
        sink_hint: str = "",
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
            "--param",
            f"hint={sink_hint or ''}",
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

            combined = "\n".join([t for t in [stdout_text, stderr_text] if t])
            if not combined:
                return None

            # Fast path: stdout is pure JSON.
            if stdout_text:
                try:
                    return json.loads(stdout_text)
                except Exception:
                    pass

            # Marker-based extraction (robust against Joern REPL noise).
            marker_start = "<<<JOERN_REACHABILITY_JSON_START>>>"
            marker_end = "<<<JOERN_REACHABILITY_JSON_END>>>"
            start_idx = combined.rfind(marker_start)
            end_idx = combined.rfind(marker_end)
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_text = combined[start_idx + len(marker_start) : end_idx].strip()
                try:
                    parsed = json.loads(json_text)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    logger.debug("Joern reachability marker JSON parse failed")

            logger.debug("Joern query output is not JSON")
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
            "engine": "joern_dataflow" | "codebadger_mcp",
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

        # Smart audit policy: only allow Joern for Java / C / C++.
        lang_errors: Dict[str, str] = {}
        supported_items: List[Dict[str, Any]] = []
        for item in (items or []):
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if not key:
                continue
            sink_file = str(item.get("sink_file") or "")
            if not infer_codebadger_language(sink_file):
                lang_errors[str(key)] = "unsupported_language"
                continue
            supported_items.append(item)

        if lang_errors and not supported_items:
            return {
                "version": 1,
                "engine": "joern_dataflow",
                "results": {},
                "errors": dict(lang_errors),
            }

        # Only run supported items; merge unsupported errors into final response.
        items = supported_items

        # Engine selection:
        # - If user forces MCP and it's reachable: use MCP.
        # - Else prefer local `joern` if available.
        # - Else fall back to MCP when enabled.
        if self._mcp_prefer and await self._check_mcp_available():
            out = await self._build_poc_trigger_chains_batch_mcp(
                project_root=project_root,
                items=items,
                max_flows=max_flows,
                max_nodes=max_nodes,
            )
            if isinstance(out, dict) and lang_errors:
                err = out.get("errors")
                if isinstance(err, dict):
                    err.update(lang_errors)
                else:
                    out["errors"] = dict(lang_errors)
            return out

        local_ok = await self._check_version()
        if not local_ok:
            if self._mcp_enabled:
                if await self._check_mcp_available():
                    out = await self._build_poc_trigger_chains_batch_mcp(
                        project_root=project_root,
                        items=items,
                        max_flows=max_flows,
                        max_nodes=max_nodes,
                    )
                    if isinstance(out, dict) and lang_errors:
                        err = out.get("errors")
                        if isinstance(err, dict):
                            err.update(lang_errors)
                        else:
                            out["errors"] = dict(lang_errors)
                    return out
                out = {
                    "version": 1,
                    "engine": "codebadger_mcp",
                    "results": {},
                    "errors": {
                        str(item.get("key")): "joern_mcp_unavailable"
                        for item in (items or [])
                        if item.get("key")
                    },
                }
                if lang_errors and isinstance(out.get("errors"), dict):
                    out["errors"].update(lang_errors)
                return out
            out = {
                "version": 1,
                "engine": "joern_dataflow",
                "results": {},
                "errors": {
                    str(item.get("key")): "joern_not_available" for item in (items or []) if item.get("key")
                },
            }
            if lang_errors and isinstance(out.get("errors"), dict):
                out["errors"].update(lang_errors)
            return out

        script_path = self._poc_chain_batch_script_path()
        if not script_path.exists():
            out = {
                "version": 1,
                "engine": "joern_dataflow",
                "results": {},
                "errors": {str(item.get("key")): "script_missing" for item in (items or []) if item.get("key")},
            }
            if lang_errors and isinstance(out.get("errors"), dict):
                out["errors"].update(lang_errors)
            return out

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
                out = {
                    "version": 1,
                    "engine": "joern_dataflow",
                    "results": {},
                    "errors": {str(item.get("key")): "joern_exec_failed" for item in (items or []) if item.get("key")},
                }
                if lang_errors and isinstance(out.get("errors"), dict):
                    out["errors"].update(lang_errors)
                return out

            combined = f"{out_text}\n{err_text}"
            start_idx = combined.rfind(marker_start)
            end_idx = combined.rfind(marker_end)
            if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
                logger.debug("Joern batch chain missing markers")
                out = {
                    "version": 1,
                    "engine": "joern_dataflow",
                    "results": {},
                    "errors": {str(item.get("key")): "missing_json_markers" for item in (items or []) if item.get("key")},
                }
                if lang_errors and isinstance(out.get("errors"), dict):
                    out["errors"].update(lang_errors)
                return out

            json_text = combined[start_idx + len(marker_start) : end_idx].strip()
            try:
                parsed = json.loads(json_text)
                if isinstance(parsed, dict):
                    if lang_errors:
                        err = parsed.get("errors")
                        if isinstance(err, dict):
                            err.update(lang_errors)
                        else:
                            parsed["errors"] = dict(lang_errors)
                    return parsed
            except Exception:
                logger.debug("Joern batch chain JSON parse failed")

            out = {
                "version": 1,
                "engine": "joern_dataflow",
                "results": {},
                "errors": {str(item.get("key")): "invalid_json" for item in (items or []) if item.get("key")},
            }
            if lang_errors and isinstance(out.get("errors"), dict):
                out["errors"].update(lang_errors)
            return out
        finally:
            try:
                Path(input_path).unlink(missing_ok=True)
            except Exception:
                pass

    async def _build_poc_trigger_chains_batch_mcp(
        self,
        *,
        project_root: str,
        items: List[Dict[str, Any]],
        max_flows: int = 3,
        max_nodes: int = 80,
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        errors: Dict[str, str] = {}

        # Group items by CodeBadger language (based on sink_file suffix).
        by_lang: dict[str, list[dict[str, Any]]] = {}
        for item in items or []:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if not key:
                continue
            sink_file = str(item.get("sink_file") or "")
            lang = infer_codebadger_language(sink_file)
            if not lang:
                errors[str(key)] = "unsupported_language"
                continue
            by_lang.setdefault(lang, []).append(item)

        for lang, group_items in by_lang.items():
            # 1) Ensure CPG is ready.
            gen = await self._mcp.generate_cpg_local(
                source_path=project_root,
                language=lang,
                timeout=self._mcp_cpg_timeout_sec,
            )
            if not gen.get("success"):
                reason = str(gen.get("error") or "generate_cpg_failed")
                for it in group_items:
                    k = it.get("key")
                    if k and str(k) not in results and str(k) not in errors:
                        errors[str(k)] = f"joern_mcp_generate_cpg_failed:{reason}"
                continue

            codebase_hash = gen.get("codebase_hash")
            if not isinstance(codebase_hash, str) or not codebase_hash.strip():
                for it in group_items:
                    k = it.get("key")
                    if k and str(k) not in results and str(k) not in errors:
                        errors[str(k)] = "joern_mcp_missing_codebase_hash"
                continue

            # 2) Build and run query.
            query = build_poc_trigger_chain_batch_cpgql_query(
                items=group_items,
                max_flows=max_flows,
                max_nodes=max_nodes,
            )
            qres = await self._mcp.run_cpgql_query(
                codebase_hash=codebase_hash,
                query=query,
                timeout=self._mcp_query_timeout_sec,
            )
            if not qres.get("success"):
                reason = str(qres.get("error") or "query_failed")
                for it in group_items:
                    k = it.get("key")
                    if k and str(k) not in results and str(k) not in errors:
                        errors[str(k)] = f"joern_mcp_query_failed:{reason}"
                continue

            parsed = parse_codebadger_query_data(qres.get("data"))
            if not isinstance(parsed, dict):
                for it in group_items:
                    k = it.get("key")
                    if k and str(k) not in results and str(k) not in errors:
                        errors[str(k)] = "joern_mcp_invalid_query_result"
                continue

            group_results = parsed.get("results")
            group_errors = parsed.get("errors")
            if isinstance(group_results, dict):
                for k, v in group_results.items():
                    if k and k not in results:
                        results[str(k)] = v
            if isinstance(group_errors, dict):
                for k, v in group_errors.items():
                    if not k:
                        continue
                    if k in results:
                        continue
                    if isinstance(v, str) and v.strip():
                        errors[str(k)] = v.strip()

            # Ensure every item has either result or error.
            for it in group_items:
                k = it.get("key")
                if not k:
                    continue
                ks = str(k)
                if ks not in results and ks not in errors:
                    errors[ks] = "no_result"

        # Ensure items that were filtered into errors above are represented.
        for item in items or []:
            if not isinstance(item, dict):
                continue
            k = item.get("key")
            if not k:
                continue
            ks = str(k)
            if ks not in results and ks not in errors:
                errors[ks] = "no_result"

        return {"version": 1, "engine": "codebadger_mcp", "results": results, "errors": errors}

    def _read_sink_hint(self, *, project_root: str, file_path: str, line_start: int) -> str:
        rel = str(file_path or "").replace("\\", "/").strip()
        if rel.startswith("./"):
            rel = rel[2:]
        if not rel:
            return ""
        try:
            p = (Path(project_root) / rel).resolve()
            if not p.is_file():
                return ""
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            idx = max(0, int(line_start) - 1)
            if idx >= len(lines):
                return ""
            return str(lines[idx]).strip()[:120]
        except Exception:
            return ""

    async def _verify_reachability_mcp(
        self,
        *,
        project_root: str,
        file_path: str,
        line_start: int,
        sink_hint: str,
        call_chain: Optional[List[str]] = None,
        control_conditions: Optional[List[str]] = None,
    ) -> FlowEvidence:
        lang = infer_codebadger_language(file_path)
        if not lang:
            return self._blocked_with_context(
                "unsupported_language",
                call_chain=call_chain,
                control_conditions=control_conditions,
                extra={"source": "codebadger_mcp"},
            )

        cache_key = (str(project_root), str(lang))
        codebase_hash = self._mcp_codebase_hash_cache.get(cache_key)

        if not codebase_hash:
            gen = await self._mcp.generate_cpg_local(
                source_path=project_root,
                language=lang,
                timeout=self._mcp_cpg_timeout_sec,
            )
            if not gen.get("success"):
                reason = str(gen.get("error") or "generate_cpg_failed")
                return self._blocked_with_context(
                    f"joern_mcp_generate_cpg_failed:{reason}",
                    call_chain=call_chain,
                    control_conditions=control_conditions,
                    extra={"source": "codebadger_mcp"},
                )
            cbh = gen.get("codebase_hash")
            if not isinstance(cbh, str) or not cbh.strip():
                return self._blocked_with_context(
                    "joern_mcp_missing_codebase_hash",
                    call_chain=call_chain,
                    control_conditions=control_conditions,
                    extra={"source": "codebadger_mcp"},
                )
            codebase_hash = cbh.strip()
            self._mcp_codebase_hash_cache[cache_key] = codebase_hash

        query = build_reachability_cpgql_query(
            file_path=file_path,
            line_start=max(1, int(line_start)),
            sink_hint=sink_hint or "",
            max_nodes=80,
        )
        qres = await self._mcp.run_cpgql_query(
            codebase_hash=codebase_hash,
            query=query,
            timeout=self._mcp_query_timeout_sec,
        )
        if not qres.get("success"):
            reason = str(qres.get("error") or "query_failed")
            return self._blocked_with_context(
                f"joern_mcp_query_failed:{reason}",
                call_chain=call_chain,
                control_conditions=control_conditions,
                extra={"source": "codebadger_mcp", "codebase_hash": codebase_hash},
            )

        parsed = parse_codebadger_query_data(qres.get("data"))
        if not isinstance(parsed, dict):
            return self._blocked_with_context(
                "joern_mcp_invalid_query_result",
                call_chain=call_chain,
                control_conditions=control_conditions,
                extra={"source": "codebadger_mcp", "codebase_hash": codebase_hash},
            )

        call_chain_payload = [str(item) for item in (parsed.get("call_chain") or []) if str(item).strip()]
        control_payload = [
            str(item) for item in (parsed.get("control_conditions") or []) if str(item).strip()
        ]
        blocked = [str(item) for item in (parsed.get("blocked_reasons") or []) if str(item).strip()]
        taint_paths = [str(item) for item in (parsed.get("taint_paths") or []) if str(item).strip()]

        try:
            score = float(parsed.get("path_score") or 0.0)
        except Exception:
            score = 0.0

        return FlowEvidence(
            path_found=bool(parsed.get("path_found")),
            path_score=score,
            call_chain=call_chain_payload,
            control_conditions=control_payload,
            taint_paths=taint_paths,
            entry_inferred=bool(parsed.get("entry_inferred")),
            blocked_reasons=blocked,
            engine="joern",
            extra={"source": "codebadger_mcp", "codebase_hash": codebase_hash},
        )

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

        # Smart audit policy: only allow Joern for Java / C / C++.
        if not infer_codebadger_language(file_path):
            return self._blocked_with_context(
                "unsupported_language",
                call_chain=call_chain,
                control_conditions=control_conditions,
            )

        sink_hint = self._read_sink_hint(
            project_root=project_root,
            file_path=file_path,
            line_start=max(1, int(line_start)),
        )

        # Engine selection:
        # - If user forces MCP and it's reachable: use MCP.
        # - Else prefer local `joern` if available.
        # - Else fall back to MCP when enabled.
        if self._mcp_prefer and await self._check_mcp_available():
            return await self._verify_reachability_mcp(
                project_root=project_root,
                file_path=file_path,
                line_start=line_start,
                sink_hint=sink_hint,
                call_chain=call_chain,
                control_conditions=control_conditions,
            )

        local_ok = await self._check_version()
        if not local_ok:
            if self._mcp_enabled:
                if await self._check_mcp_available():
                    return await self._verify_reachability_mcp(
                        project_root=project_root,
                        file_path=file_path,
                        line_start=line_start,
                        sink_hint=sink_hint,
                        call_chain=call_chain,
                        control_conditions=control_conditions,
                    )
                return self._blocked_with_context(
                    "joern_mcp_unavailable",
                    call_chain=call_chain,
                    control_conditions=control_conditions,
                    extra={"source": "codebadger_mcp"},
                )
            return self._blocked_with_context(
                "joern_not_available",
                call_chain=call_chain,
                control_conditions=control_conditions,
            )

        payload = await self._run_query(
            project_root=project_root,
            file_path=file_path,
            line_start=max(1, int(line_start)),
            sink_hint=sink_hint,
        )

        if isinstance(payload, dict):
            call_chain_payload = [str(item) for item in (payload.get("call_chain") or []) if str(item).strip()]
            control_payload = [str(item) for item in (payload.get("control_conditions") or []) if str(item).strip()]
            blocked = [str(item) for item in (payload.get("blocked_reasons") or []) if str(item).strip()]
            taint_paths = [str(item) for item in (payload.get("taint_paths") or []) if str(item).strip()]

            try:
                score = float(payload.get("path_score") or 0.0)
            except Exception:
                score = 0.0

            return FlowEvidence(
                path_found=bool(payload.get("path_found")),
                path_score=score,
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
