from __future__ import annotations

from typing import Optional, Type

from pydantic import BaseModel, Field

from ..tools.base import AgentTool, ToolResult


class VirtualWriteInput(BaseModel):
    file_path: Optional[str] = Field(default=None, description="目标文件路径（项目内相对路径）")
    path: Optional[str] = Field(default=None, description="目标文件路径别名")
    content: Optional[str] = Field(default=None, description="新文件内容")
    old_text: Optional[str] = Field(default=None, description="待替换原文")
    new_text: Optional[str] = Field(default=None, description="替换新文本")
    reason: Optional[str] = Field(default=None, description="写入原因（建议必填）")
    finding_id: Optional[str] = Field(default=None, description="关联 finding id")
    todo_id: Optional[str] = Field(default=None, description="关联 todo id")
    evidence_ref: Optional[str] = Field(default=None, description="证据引用")


class VirtualWriteTool(AgentTool):
    """Placeholder tool to expose write capability in tool whitelist."""

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
        return VirtualWriteInput

    async def _execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=False,
            error="写工具仅支持通过 BaseAgent 运行时执行。",
            data="",
            metadata={"virtual_tool": True, "tool_name": self._name},
        )


class VirtualReadInput(BaseModel):
    query: Optional[str] = Field(default=None, description="查询内容（可选）")
    path: Optional[str] = Field(default=None, description="路径（可选）")
    file_path: Optional[str] = Field(default=None, description="文件路径（可选）")
    line_start: Optional[int] = Field(default=None, description="起始行号（可选）")
    line_end: Optional[int] = Field(default=None, description="结束行号（可选）")
    function_name: Optional[str] = Field(default=None, description="函数名（可选）")
    keyword: Optional[str] = Field(default=None, description="关键词（可选）")
    searches: Optional[list] = Field(default=None, description="QMD 搜索表达式（可选）")
    collections: Optional[list] = Field(default=None, description="QMD 集合（可选）")


class VirtualReadTool(AgentTool):
    """Placeholder tool to expose read capability in tool whitelist."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        args_model: Type[BaseModel] = VirtualReadInput,
        fallback_tools: Optional[list[str]] = None,
    ):
        super().__init__()
        self._name = name
        self._description = description
        self._args_model = args_model
        self.runtime_proxy_only = True
        self.runtime_fallback_tools = [str(item).strip() for item in (fallback_tools or []) if str(item).strip()]

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def args_schema(self):
        return self._args_model

    async def _execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=False,
            error="只读工具仅支持通过 BaseAgent 运行时执行。",
            data="",
            metadata={"virtual_tool": True, "tool_name": self._name},
        )


class DeprecatedToolInput(BaseModel):
    reason: Optional[str] = Field(default=None, description="兼容占位参数")


class DeprecatedTool(AgentTool):
    """Compatibility shim for downlined legacy skill names."""

    def __init__(self, *, name: str, message: str):
        super().__init__()
        self._name = name
        self._message = message

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "该工具已下线，仅用于兼容历史调用。"

    @property
    def args_schema(self):
        return DeprecatedToolInput

    async def _execute(self, **kwargs) -> ToolResult:
        return ToolResult(
            success=False,
            error=self._message,
            data=self._message,
            metadata={
                "virtual_tool": True,
                "tool_name": self._name,
                "tool_deprecated": True,
            },
        )
