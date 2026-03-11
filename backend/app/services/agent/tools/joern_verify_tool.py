from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.agent.flow.joern.joern_client import JoernClient
from .base import AgentTool, ToolResult


class JoernReachabilityVerifyInput(BaseModel):
    file_path: str = Field(description="目标文件路径")
    line_start: int = Field(description="目标起始行")
    call_chain: Optional[List[str]] = Field(default=None, description="已有调用链")
    control_conditions: Optional[List[str]] = Field(default=None, description="已有控制条件")


class JoernReachabilityVerifyTool(AgentTool):
    def __init__(self, project_root: str, enabled: bool = True, timeout_sec: int = 45):
        super().__init__()
        self.project_root = project_root
        self.client = JoernClient(
            enabled=enabled,
            timeout_sec=timeout_sec,
            mcp_enabled=bool(getattr(settings, "JOERN_MCP_ENABLED", False)),
            mcp_url=str(
                getattr(settings, "JOERN_MCP_URL", "")
                or getattr(settings, "MCP_CODEBADGER_BACKEND_URL", "")
                or ""
            ),
            mcp_prefer=bool(getattr(settings, "JOERN_MCP_PREFER", False)),
            mcp_cpg_timeout_sec=int(getattr(settings, "JOERN_MCP_CPG_TIMEOUT_SEC", 240)),
            mcp_query_timeout_sec=int(getattr(settings, "JOERN_MCP_QUERY_TIMEOUT_SEC", 90)),
        )

    @property
    def name(self) -> str:
        return "joern_reachability_verify"

    @property
    def description(self) -> str:
        return "使用 Joern 对高危候选执行深度可达性复核，输出控制流/数据流证据。"

    @property
    def args_schema(self):
        return JoernReachabilityVerifyInput

    async def _execute(
        self,
        file_path: str,
        line_start: int,
        call_chain: Optional[List[str]] = None,
        control_conditions: Optional[List[str]] = None,
        **kwargs,
    ) -> ToolResult:
        evidence = await self.client.verify_reachability(
            project_root=self.project_root,
            file_path=file_path,
            line_start=line_start,
            call_chain=call_chain,
            control_conditions=control_conditions,
        )
        return ToolResult(
            success=True,
            data=evidence.to_dict(),
            metadata={"engine": "joern", "file_path": file_path},
        )


__all__ = ["JoernReachabilityVerifyTool"]
