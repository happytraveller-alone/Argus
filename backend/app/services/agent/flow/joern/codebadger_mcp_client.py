from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastmcp import Client as MCPClient
from app.services.agent.mcp.health_probe import probe_mcp_endpoint_readiness

logger = logging.getLogger(__name__)


def _coerce_dict(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()  # type: ignore[attr-defined]
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            return None
    return None


def _extract_tool_payload(result: Any) -> Dict[str, Any]:
    """Best-effort unwrap for FastMCP client call_tool results.

    CodeBadger tools return Python dicts; depending on fastmcp version/transport
    the result may be a dict or a model carrying `structuredContent`/`content`.
    """
    if isinstance(result, dict):
        return result

    for attr in ("structuredContent", "data"):
        try:
            v = getattr(result, attr)
        except Exception:
            v = None
        if isinstance(v, dict):
            return v

    dumped = _coerce_dict(result)
    if dumped:
        sc = dumped.get("structuredContent")
        if isinstance(sc, dict):
            return sc
        data = dumped.get("data")
        if isinstance(data, dict):
            return data
        # MCP spec shape: {"content":[{"type":"text","text":"..."}], ...}
        content = dumped.get("content")
        if isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                sc2 = part.get("structuredContent") or part.get("data")
                if isinstance(sc2, dict):
                    return sc2
                # Some clients put JSON into a text content part.
                text = part.get("text")
                if isinstance(text, str):
                    return {"text": text}
        return dumped

    return {"raw": str(result)}


def _tool_response_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize CodeBadger tool wrapper response.

    CodeBadger wraps tool outputs as:
      {"code": 200, "response": <data>}
    """
    resp = payload.get("response")
    if isinstance(resp, dict):
        return resp
    return payload


@dataclass(slots=True)
class CodeBadgerMCPClient:
    url: str
    poll_interval_sec: float = 1.0
    health_timeout_sec: float = 3.0

    async def ping(self) -> bool:
        try:
            ready, reason = await asyncio.to_thread(
                probe_mcp_endpoint_readiness,
                self.url,
                timeout=self.health_timeout_sec,
            )
            if not ready:
                logger.debug("CodeBadger MCP ping failed: %s", reason)
            return bool(ready)
        except Exception as exc:
            logger.debug("CodeBadger MCP ping failed: %s", exc)
            return False

    async def generate_cpg_local(
        self,
        *,
        source_path: str,
        language: str,
        timeout: int,
    ) -> Dict[str, Any]:
        """Generate CPG for a local source directory and wait until ready (best-effort)."""
        timeout_sec = max(10, int(timeout))
        deadline = asyncio.get_running_loop().time() + timeout_sec

        try:
            async with MCPClient(self.url) as client:
                tool_res = await client.call_tool(
                    "generate_cpg",
                    {"source_type": "local", "source_path": source_path, "language": language},
                )
                payload = _extract_tool_payload(tool_res)
                response = _tool_response_dict(payload)

                codebase_hash = response.get("codebase_hash") or response.get("codebaseHash")
                status = response.get("status")

                if not isinstance(codebase_hash, str) or not codebase_hash.strip():
                    return {
                        "success": False,
                        "error": "missing_codebase_hash",
                        "detail": payload,
                    }

                # Poll until ready/failed.
                while status not in {"ready", "failed", "not_found"}:
                    if asyncio.get_running_loop().time() >= deadline:
                        return {
                            "success": False,
                            "error": "cpg_timeout",
                            "codebase_hash": codebase_hash,
                            "last_status": status,
                        }
                    await asyncio.sleep(self.poll_interval_sec)
                    st_res = await client.call_tool("get_cpg_status", {"codebase_hash": codebase_hash})
                    st_payload = _extract_tool_payload(st_res)
                    response = _tool_response_dict(st_payload)
                    status = response.get("status")

                if status == "ready":
                    return {"success": True, **response}

                return {
                    "success": False,
                    "error": f"cpg_{status}",
                    **response,
                }
        except Exception as exc:
            logger.warning("CodeBadger MCP generate_cpg_local failed: %s", exc)
            return {"success": False, "error": "exception", "message": str(exc)}

    async def run_cpgql_query(
        self,
        *,
        codebase_hash: str,
        query: str,
        timeout: int,
    ) -> Dict[str, Any]:
        """Run a CPGQL query via CodeBadger MCP (best-effort, no exceptions)."""
        try:
            async with MCPClient(self.url) as client:
                tool_res = await client.call_tool(
                    "run_cpgql_query",
                    {
                        "codebase_hash": codebase_hash,
                        "query": query,
                        "timeout": max(5, int(timeout)),
                        # We generate the query ourselves; disable strict validation to avoid false rejects.
                        "validate": False,
                    },
                )
                payload = _extract_tool_payload(tool_res)
                response = _tool_response_dict(payload)
                if isinstance(response, dict):
                    return response
                return {"success": False, "error": "invalid_response", "detail": payload}
        except Exception as exc:
            logger.warning("CodeBadger MCP run_cpgql_query failed: %s", exc)
            return {"success": False, "error": "exception", "message": str(exc)}
