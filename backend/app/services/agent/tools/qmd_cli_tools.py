from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.services.agent.qmd.task_kb import QmdTaskKnowledgeBase

from .base import AgentTool, ToolResult


def _normalize_qmd_error(result: Dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return "qmd_execution_failed"
    for key in ("error", "stderr", "stdout"):
        value = str(result.get(key) or "").strip()
        if value:
            return value
    return "qmd_execution_failed"


class QmdQueryInput(BaseModel):
    query: Optional[str] = Field(default=None, description="查询字符串，支持自然语言或 QMD 语法。")
    searches: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="可选多检索表达式，格式: [{type:'lex|vec|hyde',query:'...'}]",
    )
    collections: Optional[List[str]] = Field(default=None, description="集合名列表（仅使用首个值）")
    limit: Optional[int] = Field(default=5, description="返回条数")
    full: Optional[bool] = Field(default=False, description="是否返回全文")


class QmdGetInput(BaseModel):
    doc_id: Optional[str] = Field(default=None, description="文档 ID 或路径")
    id: Optional[str] = Field(default=None, description="doc_id 别名")
    path: Optional[str] = Field(default=None, description="doc_id 别名")
    lines: Optional[int] = Field(default=120, description="最大读取行数")
    from_line: Optional[int] = Field(default=None, description="起始行号")


class QmdMultiGetInput(BaseModel):
    pattern: Optional[str] = Field(default=None, description="glob 模式或逗号分隔文档列表")
    ids: Optional[List[str]] = Field(default=None, description="文档 ID 列表")
    lines: Optional[int] = Field(default=120, description="每文件最大行数")
    max_bytes: Optional[int] = Field(default=200000, description="单文件最大字节数")


class QmdStatusInput(BaseModel):
    detail: Optional[bool] = Field(default=False, description="保留参数，兼容调用端。")


class _QmdToolBase(AgentTool):
    def __init__(self, kb: QmdTaskKnowledgeBase, *, name: str, description: str) -> None:
        super().__init__()
        self.kb = kb
        self._name = name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description


class QmdQueryTool(_QmdToolBase):
    def __init__(self, kb: QmdTaskKnowledgeBase) -> None:
        super().__init__(
            kb,
            name="qmd_query",
            description="基于任务知识库执行语义/关键词检索（QMD CLI）。",
        )

    @property
    def args_schema(self):
        return QmdQueryInput

    async def _execute(self, **kwargs) -> ToolResult:
        searches = kwargs.get("searches")
        query = str(kwargs.get("query") or "").strip()
        if isinstance(searches, list) and searches:
            multiline_query = self.kb.build_multiline_query(searches)
            if multiline_query.strip():
                query = multiline_query
        if not query:
            return ToolResult(success=False, error="query_required", data="query_required")

        collections = kwargs.get("collections")
        collection_name = None
        if isinstance(collections, list) and collections:
            collection_name = str(collections[0] or "").strip() or None

        try:
            result = await asyncio.to_thread(
                self.kb.query,
                query_text=query,
                limit=max(1, int(kwargs.get("limit") or 5)),
                collection=collection_name,
                full=bool(kwargs.get("full", False)),
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"qmd_query_error:{exc}", data=f"qmd_query_error:{exc}")

        if not result.get("success"):
            error_text = _normalize_qmd_error(result)
            return ToolResult(success=False, error=f"qmd_cli_failed:{error_text}", data=f"qmd_cli_failed:{error_text}")

        return ToolResult(
            success=True,
            data=result.get("data", result.get("stdout", "")),
            metadata=result.get("metadata") if isinstance(result.get("metadata"), dict) else {},
        )


class QmdGetTool(_QmdToolBase):
    def __init__(self, kb: QmdTaskKnowledgeBase) -> None:
        super().__init__(
            kb,
            name="qmd_get",
            description="读取任务知识库中的单个文档（QMD CLI）。",
        )

    @property
    def args_schema(self):
        return QmdGetInput

    async def _execute(self, **kwargs) -> ToolResult:
        doc_id = (
            str(kwargs.get("doc_id") or "").strip()
            or str(kwargs.get("id") or "").strip()
            or str(kwargs.get("path") or "").strip()
        )
        if not doc_id:
            return ToolResult(success=False, error="doc_id_required", data="doc_id_required")
        try:
            result = await asyncio.to_thread(
                self.kb.get,
                doc_id=doc_id,
                lines=kwargs.get("lines"),
                from_line=kwargs.get("from_line"),
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"qmd_get_error:{exc}", data=f"qmd_get_error:{exc}")

        if not result.get("success"):
            error_text = _normalize_qmd_error(result)
            return ToolResult(success=False, error=f"qmd_cli_failed:{error_text}", data=f"qmd_cli_failed:{error_text}")
        return ToolResult(success=True, data=result.get("data", result.get("stdout", "")))


class QmdMultiGetTool(_QmdToolBase):
    def __init__(self, kb: QmdTaskKnowledgeBase) -> None:
        super().__init__(
            kb,
            name="qmd_multi_get",
            description="批量读取任务知识库文档（QMD CLI）。",
        )

    @property
    def args_schema(self):
        return QmdMultiGetInput

    async def _execute(self, **kwargs) -> ToolResult:
        pattern = str(kwargs.get("pattern") or "").strip()
        ids = kwargs.get("ids")
        if isinstance(ids, list):
            normalized_ids = [str(item).strip() for item in ids if str(item).strip()]
            if normalized_ids:
                pattern = ",".join(normalized_ids)
        if not pattern:
            return ToolResult(success=False, error="pattern_required", data="pattern_required")
        try:
            result = await asyncio.to_thread(
                self.kb.multi_get,
                pattern=pattern,
                lines=kwargs.get("lines"),
                max_bytes=kwargs.get("max_bytes"),
            )
        except Exception as exc:
            return ToolResult(success=False, error=f"qmd_multi_get_error:{exc}", data=f"qmd_multi_get_error:{exc}")
        if not result.get("success"):
            error_text = _normalize_qmd_error(result)
            return ToolResult(success=False, error=f"qmd_cli_failed:{error_text}", data=f"qmd_cli_failed:{error_text}")
        return ToolResult(success=True, data=result.get("data", result.get("stdout", "")))


class QmdStatusTool(_QmdToolBase):
    def __init__(self, kb: QmdTaskKnowledgeBase) -> None:
        super().__init__(
            kb,
            name="qmd_status",
            description="查看任务知识库索引状态（QMD CLI）。",
        )

    @property
    def args_schema(self):
        return QmdStatusInput

    async def _execute(self, **kwargs) -> ToolResult:
        del kwargs
        try:
            result = await asyncio.to_thread(self.kb.status)
        except Exception as exc:
            return ToolResult(success=False, error=f"qmd_status_error:{exc}", data=f"qmd_status_error:{exc}")
        if not result.get("success"):
            error_text = _normalize_qmd_error(result)
            return ToolResult(success=False, error=f"qmd_cli_failed:{error_text}", data=f"qmd_cli_failed:{error_text}")
        return ToolResult(success=True, data=result.get("data", result.get("stdout", "")))
