from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.services.agent.flow.pipeline import FlowEvidencePipeline
from app.services.agent.flow.lightweight.ast_index import ASTCallIndex
from .base import AgentTool, ToolResult


class ControlFlowAnalysisLightInput(BaseModel):
    file_path: str = Field(description="目标文件路径")
    line_start: Optional[int] = Field(default=None, description="目标起始行")
    line_end: Optional[int] = Field(default=None, description="目标结束行")
    severity: Optional[str] = Field(default=None, description="漏洞严重度")
    confidence: Optional[float] = Field(default=None, description="漏洞置信度 0-1")
    entry_points: Optional[List[str]] = Field(default=None, description="候选入口函数")
    function_name: Optional[str] = Field(default=None, description="目标函数名（缺少 line_start 时可选）")
    vulnerability_type: Optional[str] = Field(default=None, description="漏洞类型")
    call_chain_hint: Optional[List[str]] = Field(default=None, description="已知调用链提示")
    control_conditions_hint: Optional[List[str]] = Field(default=None, description="已知控制条件提示")
    entry_points_hint: Optional[List[str]] = Field(default=None, description="入口函数提示")


class ControlFlowAnalysisLightTool(AgentTool):
    """Lightweight control/data-flow analysis based on tree-sitter + code2flow."""

    def __init__(self, project_root: str, target_files: Optional[List[str]] = None):
        super().__init__()
        self.project_root = project_root
        self.target_files = target_files or []
        self._ast_index: Optional[ASTCallIndex] = None
        self.pipeline = FlowEvidencePipeline(
            project_root=project_root,
            target_files=target_files,
        )

    @property
    def name(self) -> str:
        return "controlflow_analysis_light"

    @property
    def description(self) -> str:
        return (
            "轻量控制流/数据流分析：基于 tree-sitter 和 code2flow 推断从入口到漏洞位置的调用链、"
            "控制条件和可达性分值。适用于不完整代码和不可编译项目。"
            "优先输入 file_path:line 或显式 line_start 以确保可定位。"
        )

    @property
    def args_schema(self):
        return ControlFlowAnalysisLightInput

    async def _execute(
        self,
        file_path: str,
        line_start: Optional[int] = None,
        line_end: Optional[int] = None,
        severity: Optional[str] = None,
        confidence: Optional[float] = None,
        entry_points: Optional[List[str]] = None,
        function_name: Optional[str] = None,
        vulnerability_type: Optional[str] = None,
        call_chain_hint: Optional[List[str]] = None,
        control_conditions_hint: Optional[List[str]] = None,
        entry_points_hint: Optional[List[str]] = None,
        **kwargs,
    ) -> ToolResult:
        normalized_file_path, embedded_line = self._parse_file_path_line(file_path)
        resolved_line_start = self._coerce_positive_int(line_start) or embedded_line
        resolved_line_end = self._coerce_positive_int(line_end)

        if resolved_line_start is None and function_name:
            resolved_line_start = self._resolve_line_start_by_function(
                file_path=normalized_file_path,
                function_name=function_name,
            )
        if resolved_line_start is None:
            return ToolResult(
                success=False,
                error=(
                    "缺少 line_start。请使用 file_path:line、传入 line_start，或提供可定位的 function_name。"
                ),
            )
        if resolved_line_end is None:
            resolved_line_end = resolved_line_start
        if resolved_line_end < resolved_line_start:
            resolved_line_end = resolved_line_start

        effective_entry_points = (
            [str(item).strip() for item in (entry_points or []) if str(item).strip()]
            or [str(item).strip() for item in (entry_points_hint or []) if str(item).strip()]
        )
        finding: Dict[str, Any] = {
            "file_path": normalized_file_path,
            "line_start": resolved_line_start,
            "line_end": resolved_line_end,
            "severity": severity,
            "confidence": confidence,
            "entry_points": effective_entry_points,
            "function_name": function_name,
            "vulnerability_type": vulnerability_type,
            "call_chain_hint": call_chain_hint or [],
            "control_conditions_hint": control_conditions_hint or [],
        }

        evidence = await self.pipeline.analyze_finding(finding)
        flow_payload = evidence.get("flow") if isinstance(evidence, dict) else {}
        summary = self._build_summary(flow_payload)
        return ToolResult(
            success=True,
            data=evidence,
            metadata={
                "engine": "ts_code2flow",
                "file_path": normalized_file_path,
                "line_start": resolved_line_start,
                "line_end": resolved_line_end,
                "function_name": function_name,
                "summary": summary,
            },
        )

    @staticmethod
    def _coerce_positive_int(value: Any) -> Optional[int]:
        try:
            parsed = int(value)
        except Exception:
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _parse_file_path_line(file_path: str) -> tuple[str, Optional[int]]:
        text = str(file_path or "").strip()
        if not text:
            return "", None
        parts = text.rsplit(":", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0].strip(), int(parts[1])
        return text, None

    def _resolve_line_start_by_function(self, file_path: str, function_name: str) -> Optional[int]:
        name = str(function_name or "").strip()
        path = str(file_path or "").strip()
        if not name or not path:
            return None
        if self._ast_index is None:
            self._ast_index = ASTCallIndex(project_root=self.project_root, target_files=self.target_files)
            self._ast_index.build()
        symbols = self._ast_index.symbols_by_name.get(name) or []
        normalized_path = str(path).replace("\\", "/").lstrip("./")
        for symbol in symbols:
            symbol_path = str(symbol.file_path or "").replace("\\", "/").lstrip("./")
            if symbol_path == normalized_path:
                return int(symbol.start_line)
        if symbols:
            return int(symbols[0].start_line)
        return None

    @staticmethod
    def _build_summary(flow_payload: Any) -> str:
        if not isinstance(flow_payload, dict):
            return "flow 结果不可用。"
        path_found = bool(flow_payload.get("path_found"))
        path_score = flow_payload.get("path_score")
        blocked = flow_payload.get("blocked_reasons") if isinstance(flow_payload.get("blocked_reasons"), list) else []
        entry_inferred = bool(flow_payload.get("entry_inferred"))
        try:
            score_text = f"{float(path_score):.2f}" if path_score is not None else "N/A"
        except Exception:
            score_text = "N/A"
        blocked_text = ", ".join(str(item) for item in blocked if str(item).strip()) or "无"
        summary = (
            f"path_found={path_found}; path_score={score_text}; "
            f"entry_inferred={entry_inferred}; blocked_reasons={blocked_text}"
        )
        if "code2flow_not_installed" in blocked:
            summary += "; code2flow=missing"
        if "auto_install_failed" in blocked:
            summary += "; install_hint=auto_install_failed"
        return summary


__all__ = ["ControlFlowAnalysisLightTool"]
