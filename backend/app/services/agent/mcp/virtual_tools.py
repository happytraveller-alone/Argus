from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..tools.base import AgentTool, ToolResult


class MCPWriteInput(BaseModel):
    file_path: Optional[str] = Field(default=None, description="目标文件路径（项目内相对路径）")
    path: Optional[str] = Field(default=None, description="目标文件路径别名")
    content: Optional[str] = Field(default=None, description="新文件内容")
    old_text: Optional[str] = Field(default=None, description="待替换原文")
    new_text: Optional[str] = Field(default=None, description="替换新文本")
    reason: Optional[str] = Field(default=None, description="写入原因（建议必填）")
    finding_id: Optional[str] = Field(default=None, description="关联 finding id")
    todo_id: Optional[str] = Field(default=None, description="关联 todo id")
    evidence_ref: Optional[str] = Field(default=None, description="证据引用")


class MCPVirtualWriteTool(AgentTool):
    """Placeholder tool to expose MCP write capability in tool whitelist."""

    def __init__(self, name: str, description: str):
        super().__init__()
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def args_schema(self):
        return MCPWriteInput

    async def _execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=False,
            error="MCP 写工具仅支持通过 BaseAgent MCP 运行时执行。",
            data="",
            metadata={"virtual_tool": True, "tool_name": self._name},
        )
