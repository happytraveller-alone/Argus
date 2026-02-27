from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class LocalMCPProxyAdapter:
    """Expose local AgentTool instances via MCP adapter contract."""

    def __init__(self, *, runtime_domain: str = "backend") -> None:
        self.runtime_domain = str(runtime_domain or "backend").strip().lower() or "backend"
        self._tools: Dict[str, Any] = {}

    def is_available(self) -> bool:
        return True

    @property
    def availability_reason(self) -> None:
        return None

    def register_tool(self, tool_name: str, tool_obj: Any) -> None:
        normalized = str(tool_name or "").strip()
        if not normalized or tool_obj is None:
            return
        if not hasattr(tool_obj, "execute"):
            return
        self._tools[normalized] = tool_obj

    def register_tools(self, tools: Dict[str, Any]) -> int:
        count = 0
        for tool_name, tool_obj in (tools or {}).items():
            before = len(self._tools)
            self.register_tool(str(tool_name), tool_obj)
            if len(self._tools) > before:
                count += 1
        return count

    def has_tool(self, tool_name: str) -> bool:
        return str(tool_name or "").strip() in self._tools

    async def list_tools(self) -> list[Dict[str, Any]]:
        tools: list[Dict[str, Any]] = []
        for tool_name in sorted(self._tools.keys()):
            tools.append(
                {
                    "name": tool_name,
                    "description": "local_proxy_tool",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            )
        return tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        normalized = str(tool_name or "").strip()
        tool = self._tools.get(normalized)
        if tool is None:
            return {
                "success": False,
                "error": f"local_proxy_tool_not_found:{normalized or 'unknown'}",
                "metadata": {
                    "local_proxy": True,
                    "local_proxy_tool_name": normalized or None,
                },
            }

        payload = dict(arguments or {})
        try:
            result = await tool.execute(**payload)
        except Exception as exc:
            logger.warning("Local MCP proxy tool call failed (%s): %s", normalized, exc)
            return {
                "success": False,
                "error": f"local_proxy_call_failed:{exc}",
                "metadata": {
                    "local_proxy": True,
                    "local_proxy_tool_name": normalized or None,
                },
            }

        result_meta = {}
        if isinstance(getattr(result, "metadata", None), dict):
            result_meta = dict(result.metadata)

        success = bool(getattr(result, "success", False))
        data = getattr(result, "data", None)
        if data is None:
            data = "" if success else str(getattr(result, "error", "") or "")
        error = str(getattr(result, "error", "") or "").strip() or None
        duration_ms = getattr(result, "duration_ms", None)

        return {
            "success": success,
            "data": data,
            "error": error,
            "metadata": {
                **result_meta,
                "local_proxy": True,
                "local_proxy_tool_name": normalized or None,
                "local_proxy_duration_ms": duration_ms,
            },
        }
