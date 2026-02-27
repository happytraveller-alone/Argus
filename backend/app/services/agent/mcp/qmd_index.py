from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol


logger = logging.getLogger(__name__)


def _normalize_tool_descriptor(tool: Any) -> Optional[Dict[str, Any]]:
    if isinstance(tool, dict):
        source = dict(tool)
    elif hasattr(tool, "model_dump"):
        try:
            dumped = tool.model_dump()  # type: ignore[attr-defined]
        except Exception:
            dumped = None
        if not isinstance(dumped, dict):
            return None
        source = dict(dumped)
    else:
        source = {
            "name": getattr(tool, "name", None),
            "description": getattr(tool, "description", None),
            "inputSchema": getattr(tool, "inputSchema", getattr(tool, "input_schema", None)),
        }

    name = str(source.get("name") or source.get("tool") or source.get("id") or "").strip()
    if not name:
        return None
    schema = (
        source.get("inputSchema")
        or source.get("input_schema")
        or source.get("schema")
        or source.get("parameters")
    )
    if not isinstance(schema, dict):
        schema = {}
    return {
        "name": name,
        "description": str(source.get("description") or "").strip(),
        "inputSchema": dict(schema),
    }


class _QmdAdapter(Protocol):
    runtime_domain: str

    def is_available(self) -> bool:
        ...

    @property
    def availability_reason(self) -> Optional[str]:
        ...

    async def list_tools(self) -> List[Dict[str, Any]]:
        ...

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


def build_project_collection_name(project_id: str, prefix: str = "project") -> str:
    raw_id = "".join(ch for ch in str(project_id or "").strip() if ch.isalnum() or ch in ("-", "_"))
    safe_id = raw_id or "default"
    safe_prefix = "".join(ch for ch in str(prefix or "").strip() if ch.isalnum() or ch in ("-", "_")) or "project"
    return f"{safe_prefix}_{safe_id}"


@dataclass
class QmdEnsureResult:
    ok: bool
    reason: str = ""


class QmdLazyIndexAdapter:
    """Wrap qmd MCP adapter with lazy collection bootstrap.

    The wrapper is intentionally tolerant: collection bootstrap failures are logged
    and do not block MCP query execution.
    """

    def __init__(
        self,
        *,
        adapter: _QmdAdapter,
        project_root: str,
        project_id: str,
        command: str = "qmd",
        collection_prefix: str = "project",
        index_glob: str = "**/*",
        lazy_enabled: bool = True,
        auto_embed_on_first_use: bool = False,
    ) -> None:
        self._adapter = adapter
        self.runtime_domain = getattr(adapter, "runtime_domain", "backend")
        self.project_root = str(project_root or "").strip()
        self.project_id = str(project_id or "").strip() or "default"
        self.command = str(command or "qmd").strip() or "qmd"
        self.collection_prefix = str(collection_prefix or "project").strip() or "project"
        self.index_glob = str(index_glob or "**/*").strip() or "**/*"
        self.lazy_enabled = bool(lazy_enabled)
        self.auto_embed_on_first_use = bool(auto_embed_on_first_use)

        self._collection = build_project_collection_name(self.project_id, self.collection_prefix)
        self._ensure_lock = asyncio.Lock()
        self._ensured = False

    def is_available(self) -> bool:
        checker = getattr(self._adapter, "is_available", None)
        if callable(checker):
            return bool(checker())
        return True

    @property
    def availability_reason(self) -> Optional[str]:
        reason = getattr(self._adapter, "availability_reason", None)
        reason_text = str(reason or "").strip()
        return reason_text or None

    async def list_tools(self) -> List[Dict[str, Any]]:
        list_tools = getattr(self._adapter, "list_tools", None)
        if not callable(list_tools):
            return []
        raw_tools = await list_tools()
        if not isinstance(raw_tools, list):
            return []
        normalized: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_tools:
            tool = _normalize_tool_descriptor(item)
            if not tool:
                continue
            tool_name = str(tool.get("name") or "").strip()
            if not tool_name or tool_name in seen:
                continue
            seen.add(tool_name)
            normalized.append(tool)
        return normalized

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(arguments or {})
        normalized_tool = str(tool_name or "").strip().lower()
        collection_scoped_tools = {
            "query",
            "search",
            "vector_search",
            "deep_search",
        }
        if normalized_tool in collection_scoped_tools:
            payload.setdefault("collection", self._collection)

        if self.lazy_enabled and normalized_tool in collection_scoped_tools:
            ensure_result = await self.ensure_project_collection()
            if not ensure_result.ok:
                logger.warning(
                    "[QMD] lazy ensure failed for collection %s: %s",
                    self._collection,
                    ensure_result.reason,
                )

        return await self._adapter.call_tool(tool_name, payload)

    async def ensure_project_collection(self) -> QmdEnsureResult:
        if self._ensured:
            return QmdEnsureResult(ok=True)
        async with self._ensure_lock:
            if self._ensured:
                return QmdEnsureResult(ok=True)
            result = await asyncio.to_thread(self._ensure_collection_sync)
            if result.ok:
                self._ensured = True
            return result

    def _ensure_collection_sync(self) -> QmdEnsureResult:
        root = Path(self.project_root).resolve()
        if not root.exists() or not root.is_dir():
            return QmdEnsureResult(ok=False, reason="project_root_not_found")

        add_cmd = [
            self.command,
            "collection",
            "add",
            str(root),
            "--name",
            self._collection,
            "--mask",
            self.index_glob,
        ]
        completed = self._run_qmd_cmd(add_cmd)
        if completed.returncode != 0:
            # Keep tolerant behavior: if collection already exists, continue.
            stderr = (completed.stderr or "").lower()
            stdout = (completed.stdout or "").lower()
            if "already exists" not in stderr and "already exists" not in stdout:
                return QmdEnsureResult(
                    ok=False,
                    reason=f"collection_add_failed:{(completed.stderr or completed.stdout or '').strip()}",
                )

        if self.auto_embed_on_first_use:
            update_cmd = [
                self.command,
                "update",
                "--collection",
                self._collection,
                "--embed",
            ]
            update_result = self._run_qmd_cmd(update_cmd)
            if update_result.returncode != 0:
                return QmdEnsureResult(
                    ok=False,
                    reason=f"collection_embed_failed:{(update_result.stderr or update_result.stdout or '').strip()}",
                )

        return QmdEnsureResult(ok=True)

    def _run_qmd_cmd(self, argv: List[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            argv,
            cwd=self.project_root or None,
            text=True,
            capture_output=True,
            timeout=60,
            env=None,
            shell=False,
        )
