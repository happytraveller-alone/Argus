"""
业务逻辑漏洞扫描工具（Sub Agent 包装器）

说明：
- 该工具不再直接在工具内部执行 5 阶段逻辑。
- 该工具会创建并运行 `BusinessLogicScanAgent`，作为 Analysis Agent 的专业化子 Agent。
- 子 Agent 复用 Analysis 工具集（read_file/search_code/extract_function/dataflow_analysis 等）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .base import AgentTool, ToolResult
from app.services.agent.agents.business_logic_scan import BusinessLogicScanAgent

logger = logging.getLogger(__name__)


class BusinessLogicScanInput(BaseModel):
    """业务逻辑扫描输入"""

    target: str = Field(default=".", description="扫描目标目录")
    framework_hint: Optional[str] = Field(
        default=None,
        description="框架提示：django, fastapi, express, flask, 等",
    )
    entry_points_hint: Optional[List[str]] = Field(
        default=None,
        description="已知入口点提示（如函数名、类名）",
    )
    quick_mode: bool = Field(default=False, description="快速模式：重点扫描高风险区域")
    max_iterations: int = Field(default=8, ge=1, le=30, description="子 Agent 最大迭代次数")
    focus_areas: Optional[List[str]] = Field(
        default=None,
        description="兼容字段：关注区域列表（authentication/authorization/payment 等）",
    )


class BusinessLogicScanTool(AgentTool):
    """业务逻辑漏洞扫描工具（通过 Sub Agent 执行）。"""

    def __init__(
        self,
        project_root: str,
        llm_service: Optional[Any] = None,
        tools_registry: Optional[Dict[str, Any]] = None,
        event_emitter: Optional[Any] = None,
    ):
        super().__init__()
        self.project_root = project_root
        self.llm_service = llm_service
        self.tools_registry = tools_registry or {}
        self.event_emitter = event_emitter

    @property
    def name(self) -> str:
        return "business_logic_scan"

    @property
    def description(self) -> str:
        return """业务逻辑漏洞扫描工具（Sub Agent 模式）

该工具会创建并执行 `BusinessLogicScanAgent` 子 Agent，按 5 阶段完成业务逻辑审计：
1. HTTP 入口扫描
2. 入口功能分析
3. 敏感操作锚点识别
4. 轻量级污点分析
5. 业务逻辑漏洞确认

输出：
- 文本报告（data）
- 结构化 findings（metadata.findings）
"""

    @property
    def args_schema(self) -> Optional[type]:
        return BusinessLogicScanInput

    async def _execute(
        self,
        target: str = ".",
        framework_hint: Optional[str] = None,
        entry_points_hint: Optional[List[str]] = None,
        quick_mode: bool = False,
        max_iterations: int = 8,
        focus_areas: Optional[List[str]] = None,
        **kwargs,
    ) -> ToolResult:
        try:
            if not isinstance(self.tools_registry, dict) or not self.tools_registry:
                return ToolResult(
                    success=False,
                    error="business_logic_scan 未绑定 analysis 工具集（tools_registry 为空）",
                    data="业务逻辑扫描失败：未绑定工具集。",
                )

            # 避免工具递归调用自身
            sub_agent_tools = {
                key: value
                for key, value in self.tools_registry.items()
                if key != self.name
            }
            if not sub_agent_tools:
                return ToolResult(
                    success=False,
                    error="business_logic_scan 可用子工具为空",
                    data="业务逻辑扫描失败：无可用分析工具。",
                )

            logger.info(
                "[BusinessLogicScanTool] Launch sub-agent with %s tools (target=%s, framework=%s)",
                len(sub_agent_tools),
                target,
                framework_hint,
            )

            sub_agent = BusinessLogicScanAgent(
                llm_service=self.llm_service,
                tools=sub_agent_tools,
                event_emitter=self.event_emitter,
            )

            # 透传 Tool Runtime / WriteScope（如果由外部注入）
            tool_runtime = kwargs.get("tool_runtime")
            if tool_runtime is not None and hasattr(sub_agent, "set_tool_runtime"):
                sub_agent.set_tool_runtime(tool_runtime)
            write_scope_guard = kwargs.get("write_scope_guard")
            if write_scope_guard is not None and hasattr(sub_agent, "set_write_scope_guard"):
                sub_agent.set_write_scope_guard(write_scope_guard)

            result = await sub_agent.run(
                {
                    "target": target,
                    "framework_hint": framework_hint,
                    "entry_points_hint": entry_points_hint or [],
                    "quick_mode": quick_mode,
                    "max_iterations": max_iterations,
                    "focus_areas": focus_areas or [],
                }
            )

            if not result.success:
                return ToolResult(
                    success=False,
                    error=result.error or "BusinessLogicScanAgent 执行失败",
                    data=f"业务逻辑扫描失败: {result.error or 'unknown error'}",
                    metadata={"sub_agent_result": result.to_dict()},
                )

            payload = result.data if isinstance(result.data, dict) else {}
            report_text = str(payload.get("report") or "业务逻辑扫描完成")
            findings = payload.get("findings") if isinstance(payload.get("findings"), list) else []

            return ToolResult(
                success=True,
                data=report_text,
                metadata={
                    "phase_1_entries": int(payload.get("phase_1_entries") or 0),
                    "phase_3_sensitive_ops": payload.get("phase_3_sensitive_ops") or [],
                    "phase_4_taint_paths": payload.get("phase_4_taint_paths") or [],
                    "findings": findings,
                    "total_findings": int(payload.get("total_findings") or len(findings)),
                    "by_severity": payload.get("by_severity") or {},
                    "sub_agent": "BusinessLogicScanAgent",
                    "sub_agent_iterations": result.iterations,
                    "sub_agent_tool_calls": result.tool_calls,
                    "sub_agent_tokens": result.tokens_used,
                    "focus_areas": focus_areas or [],
                },
            )

        except Exception as exc:
            logger.error("BusinessLogicScanTool wrapper error: %s", exc, exc_info=True)
            return ToolResult(
                success=False,
                error=str(exc),
                data=f"业务逻辑扫描失败: {exc}",
            )
