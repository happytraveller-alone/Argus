from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.services.agent.logic.authz_rules import AuthzRuleEngine
from .base import AgentTool, ToolResult
from .evidence_protocol import (
    build_display_command,
    unique_command_chain,
    validate_evidence_metadata,
)


class LogicAuthzAnalysisInput(BaseModel):
    file_path: Optional[str] = Field(default=None, description="目标文件路径")
    line_start: Optional[int] = Field(default=None, description="目标行号")
    vulnerability_type: Optional[str] = Field(default=None, description="漏洞类型")


class LogicAuthzAnalysisTool(AgentTool):
    """Graph-rule authz/idor analysis without compile dependency."""

    def __init__(self, project_root: str, target_files: Optional[List[str]] = None):
        super().__init__()
        self.engine = AuthzRuleEngine(project_root=project_root, target_files=target_files)

    @property
    def name(self) -> str:
        return "logic_authz_analysis"

    @property
    def description(self) -> str:
        return """逻辑漏洞图规则分析：检查 route/handler 到资源访问路径上的认证、授权、对象级权限(IDOR)与作用域一致性。

输入:
- file_path: 可选，目标文件路径
- line_start: 可选，目标行号
- vulnerability_type: 可选，漏洞类型（用于提示规则引擎聚焦）

执行模式:
- 单点分析: 同时提供 file_path 与 line_start 时，调用 analyze_finding 对单个可疑点做授权逻辑分析
- 全项目分析: 未同时提供 file_path + line_start 时，调用 analyze_project 做项目级扫描

输出:
- data: 规则引擎分析结果（命中规则、风险结论、证据摘要等）
- metadata.engine: 固定为 logic_graph"""

    @property
    def args_schema(self):
        return LogicAuthzAnalysisInput

    async def _execute(
        self,
        file_path: Optional[str] = None,
        line_start: Optional[int] = None,
        vulnerability_type: Optional[str] = None,
        **kwargs,
    ) -> ToolResult:
        if file_path and line_start:
            result = self.engine.analyze_finding(
                {
                    "file_path": file_path,
                    "line_start": line_start,
                    "vulnerability_type": vulnerability_type,
                }
            )
        else:
            result = self.engine.analyze_project()

        blocked_reasons = list(result.get("blocked_reasons") or [])
        issue_count = sum(
            1
            for flag in ("missing_authz_checks", "resource_scope_mismatch", "idor_path")
            if result.get(flag)
        )
        entry = {
            "source_nodes": list(result.get("proof_nodes") or []),
            "sink_nodes": list(result.get("evidence") or []),
            "taint_steps": list(result.get("evidence") or []),
            "call_chain": list(result.get("proof_nodes") or []),
            "blocked_reasons": blocked_reasons,
            "reachability": "reachable" if issue_count > 0 else ("blocked" if blocked_reasons else "unknown"),
            "path_found": issue_count > 0,
            "path_score": 1.0 if issue_count > 0 else 0.0,
            "confidence": 0.85 if issue_count > 0 else 0.4,
            "engine": "logic_graph",
            "next_actions": (
                ["核对访问控制与对象级作用域检查实现。"]
                if issue_count > 0
                else ["补充目标定位信息或扩大项目级分析范围。"]
            ),
            "file_path": str(file_path or ""),
        }
        command_chain = unique_command_chain(["logic_authz_analysis"])
        display_command = build_display_command(command_chain)
        validate_evidence_metadata(
            render_type="flow_analysis",
            command_chain=command_chain,
            display_command=display_command,
            entries=[entry],
        )

        return ToolResult(
            success=True,
            data=result,
            metadata={
                "engine": "logic_graph",
                "render_type": "flow_analysis",
                "command_chain": command_chain,
                "display_command": display_command,
                "entries": [entry],
            },
        )


__all__ = ["LogicAuthzAnalysisTool"]
