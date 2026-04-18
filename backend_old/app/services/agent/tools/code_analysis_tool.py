"""
代码分析工具
使用 LLM 深度分析代码安全问题
"""

import json
import logging
import os
import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from .base import AgentTool, ToolResult
from .evidence_protocol import (
    build_display_command,
    unique_command_chain,
    validate_evidence_metadata,
)

logger = logging.getLogger(__name__)


def _build_flow_analysis_metadata(
    *,
    command_name: str,
    analysis: Dict[str, Any],
    file_path: str,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    source_nodes = list(analysis.get("source_nodes") or [])
    sink_nodes = list(analysis.get("sink_nodes") or [])
    taint_steps = list(analysis.get("taint_steps") or [])
    call_chain = list(analysis.get("call_chain") or taint_steps)
    confidence = float(analysis.get("confidence") or 0.0)
    path_found = bool(taint_steps and sink_nodes)
    reachability = "reachable" if path_found else "unknown"
    command_chain = unique_command_chain([command_name])
    display_command = build_display_command(command_chain)
    entries = [
        {
            "source_nodes": source_nodes,
            "sink_nodes": sink_nodes,
            "taint_steps": taint_steps,
            "call_chain": call_chain,
            "blocked_reasons": list(analysis.get("blocked_reasons") or []),
            "reachability": reachability,
            "path_found": path_found,
            "path_score": confidence,
            "confidence": confidence,
            "engine": str(analysis.get("analysis_engine") or "rules"),
            "next_actions": list(analysis.get("next_actions") or []),
            "file_path": file_path,
        }
    ]
    validate_evidence_metadata(
        render_type="flow_analysis",
        command_chain=command_chain,
        display_command=display_command,
        entries=entries,
    )
    metadata = {
        "render_type": "flow_analysis",
        "command_chain": command_chain,
        "display_command": display_command,
        "entries": entries,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return metadata


class CodeAnalysisInput(BaseModel):
    """代码分析输入"""
    code: str = Field(description="要分析的代码内容")
    file_path: str = Field(default="unknown", description="文件路径")
    language: str = Field(default="python", description="编程语言")
    focus: Optional[str] = Field(
        default=None,
        description="重点关注的漏洞类型，如 sql_injection, xss, command_injection"
    )
    context: Optional[str] = Field(
        default=None,
        description="额外的上下文信息，如相关的其他代码片段"
    )


class CodeAnalysisTool(AgentTool):
    """
    代码分析工具
    使用 LLM 对代码进行深度安全分析
    """
    
    def __init__(self, llm_service):
        """
        初始化代码分析工具
        
        Args:
            llm_service: LLM 服务实例
        """
        super().__init__()
        self.llm_service = llm_service
    
    @property
    def name(self) -> str:
        return "code_analysis"
    
    @property
    def description(self) -> str:
        return """深度分析代码安全问题。
使用 LLM 对代码进行全面的安全审计，识别潜在漏洞。

使用场景:
- 对疑似有问题的代码进行深入分析
- 分析复杂的业务逻辑漏洞
- 追踪数据流和污点传播
- 生成详细的漏洞报告和修复建议

输入:
- code: 必填，待分析代码片段（建议最小化到与风险相关的函数或片段）
- file_path: 选填，文件路径，用于结果标识
- language: 选填，语言标记（如 c/python/javascript）
- focus: 选填，重点关注的漏洞类型（如 sql_injection、xss、command_injection）
- context: 选填，补充上下文（调用链、上游输入、下游危险操作等）

这个工具会消耗较多的 Token，建议在确认有疑似问题后使用。"""
    
    @property
    def args_schema(self):
        return CodeAnalysisInput
    
    async def _execute(
        self,
        code: str,
        file_path: str = "unknown",
        language: str = "python",
        focus: Optional[str] = None,
        context: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        """执行代码分析"""
        import asyncio
        
        try:
            # 限制代码长度，避免超时
            max_code_length = 50000  # 约 50KB
            if len(code) > max_code_length:
                code = code[:max_code_length] + "\n\n... (代码已截断，仅分析前 50000 字符)"
            
            # 添加超时保护（5分钟）
            try:
                analysis = await asyncio.wait_for(
                    self.llm_service.analyze_code(code, language),
                    timeout=300.0  # 5分钟超时
                )
            except asyncio.TimeoutError:
                return ToolResult(
                    success=False,
                    error="代码分析超时（超过5分钟）。代码可能过长或过于复杂，请尝试分析较小的代码片段。",
                )
            
            issues = analysis.get("issues", [])
            
            if not issues:
                return ToolResult(
                    success=True,
                    data="代码分析完成，未发现明显的安全问题。\n\n"
                         f"质量评分: {analysis.get('quality_score', 'N/A')}\n"
                         f"文件: {file_path}",
                    metadata={
                        "file_path": file_path,
                        "issues_count": 0,
                        "quality_score": analysis.get("quality_score"),
                    }
                )
            
            # 格式化输出
            output_parts = [f" 代码分析结果 - {file_path}\n"]
            output_parts.append(f"发现 {len(issues)} 个问题:\n")
            
            for i, issue in enumerate(issues):
                severity_icon = {
                    "critical": "🔴",
                    "high": "🟠", 
                    "medium": "🟡",
                    "low": "🟢"
                }.get(issue.get("severity", ""), "⚪")
                
                output_parts.append(f"\n{severity_icon} 问题 {i+1}: {issue.get('title', 'Unknown')}")
                output_parts.append(f"   类型: {issue.get('type', 'unknown')}")
                output_parts.append(f"   严重程度: {issue.get('severity', 'unknown')}")
                output_parts.append(f"   行号: {issue.get('line', 'N/A')}")
                output_parts.append(f"   描述: {issue.get('description', '')}")
                
                if issue.get("code_snippet"):
                    output_parts.append(f"   代码片段:\n   ```\n   {issue.get('code_snippet')}\n   ```")
                
                if issue.get("suggestion"):
                    output_parts.append(f"   修复建议: {issue.get('suggestion')}")
                
                if issue.get("ai_explanation"):
                    output_parts.append(f"   AI解释: {issue.get('ai_explanation')}")
            
            output_parts.append(f"\n质量评分: {analysis.get('quality_score', 'N/A')}/100")
            
            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={
                    "file_path": file_path,
                    "issues_count": len(issues),
                    "quality_score": analysis.get("quality_score"),
                    "issues": issues,
                }
            )
            
        except Exception as e:
            import traceback
            logger.error(f"代码分析失败: {e}")
            logger.error(f"LLM Provider: {self.llm_service.config.provider.value if self.llm_service.config else 'N/A'}")
            logger.error(f"LLM Model: {self.llm_service.config.model if self.llm_service.config else 'N/A'}")
            logger.error(f"API Key 前缀: {self.llm_service.config.api_key[:10] + '...' if self.llm_service.config and self.llm_service.config.api_key else 'N/A'}")
            logger.error(traceback.format_exc())
            return ToolResult(
                success=False,
                error=f"代码分析失败: {str(e)}",
            )


class DataFlowAnalysisInput(BaseModel):
    """数据流分析输入"""
    source_code: Optional[str] = Field(default=None, description="包含数据源的代码")
    sink_code: Optional[str] = Field(default=None, description="包含数据汇的代码（如危险函数）")
    variable_name: str = Field(default="user_input", description="要追踪的变量名")
    file_path: str = Field(default="unknown", description="文件路径")
    start_line: Optional[int] = Field(default=None, description="源码起始行")
    end_line: Optional[int] = Field(default=None, description="源码结束行")
    source_hints: Optional[List[str]] = Field(default=None, description="Source 提示词列表")
    sink_hints: Optional[List[str]] = Field(default=None, description="Sink 提示词列表")
    language: Optional[str] = Field(default=None, description="编程语言")
    max_hops: int = Field(default=5, ge=1, le=20, description="最大传播步数")


class DataFlowAnalysisTool(AgentTool):
    """
    数据流分析工具
    追踪变量从源到汇的数据流
    """
    
    def __init__(self, llm_service, project_root: Optional[str] = None):
        super().__init__()
        self.llm_service = llm_service
        self.project_root = project_root
    
    @property
    def name(self) -> str:
        return "dataflow_analysis"
    
    @property
    def description(self) -> str:
        return """分析代码中的数据流，追踪变量从源（如用户输入）到汇（如危险函数）的路径。

使用场景:
- 追踪用户输入如何流向危险函数
- 分析变量是否经过净化处理
- 识别污点传播路径

输入:
- source_code: 包含数据源的代码
- sink_code: 包含数据汇的代码（可选）
- variable_name: 要追踪的变量名
- file_path: 文件路径
- start_line/end_line: 可选，限定分析片段
- source_hints/sink_hints: 可选，补充语义提示"""
    
    @property
    def args_schema(self):
        return DataFlowAnalysisInput
    
    async def _execute(
        self,
        source_code: Optional[str] = None,
        variable_name: str = "user_input",
        sink_code: Optional[str] = None,
        file_path: str = "unknown",
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        source_hints: Optional[List[str]] = None,
        sink_hints: Optional[List[str]] = None,
        language: Optional[str] = None,
        max_hops: int = 5,
        **kwargs
    ) -> ToolResult:
        """执行数据流分析（规则优先，LLM 细化，失败回退）。"""
        import asyncio
        source_text = str(source_code or "").strip()
        resolved_start_line = start_line
        resolved_end_line = end_line

        if (not source_text) and str(file_path or "").strip() and str(file_path).strip() != "unknown":
            loaded = self._load_source_code_from_file(file_path, start_line=start_line, end_line=end_line)
            if not loaded.get("ok"):
                return ToolResult(success=False, error=str(loaded.get("error") or "读取源码失败"))
            source_text = str(loaded.get("code") or "")
            file_path = str(loaded.get("file_path") or file_path)
            resolved_start_line = loaded.get("start_line")
            resolved_end_line = loaded.get("end_line")

        if not source_text:
            return ToolResult(
                success=False,
                error="必须提供 source_code，或提供可读取的 file_path（可选 start_line/end_line）",
            )

        normalized_variable = str(variable_name or "user_input").strip() or "user_input"
        quick_analysis = self._quick_pattern_analysis(
            source_code=source_text,
            variable_name=normalized_variable,
            sink_code=sink_code,
            source_hints=source_hints,
            sink_hints=sink_hints,
            max_hops=max_hops,
        )

        llm_analysis: Optional[Dict[str, Any]] = None
        try:
            prompt = self._build_analysis_prompt(
                source_code=source_text,
                sink_code=sink_code,
                variable_name=normalized_variable,
                source_hints=source_hints,
                sink_hints=sink_hints,
            )
            raw_result = await asyncio.wait_for(
                self.llm_service.analyze_code_with_custom_prompt(
                    code=source_text,
                    language=language or "text",
                    custom_prompt=prompt,
                ),
                timeout=120.0,
            )
            llm_analysis = self._normalize_llm_analysis(raw_result)
        except asyncio.TimeoutError:
            logger.warning("dataflow_analysis LLM 调用超时，回退规则分析")
        except Exception as exc:
            logger.warning("dataflow_analysis LLM 调用失败，回退规则分析: %s", exc)

        merged_analysis = self._merge_analysis(quick_analysis, llm_analysis)
        output_text = self._format_analysis_result(
            analysis=merged_analysis,
            variable_name=normalized_variable,
            file_path=file_path,
        )
        fallback_used = llm_analysis is None
        analysis_mode = "rules_only_fallback" if fallback_used else "rules_plus_llm"

        return ToolResult(
            success=True,
            data=output_text,
            metadata=_build_flow_analysis_metadata(
                command_name="dataflow_analysis",
                analysis=merged_analysis,
                file_path=file_path,
                extra_metadata={
                    "variable": normalized_variable,
                    "file_path": file_path,
                    "start_line": resolved_start_line,
                    "end_line": resolved_end_line,
                    "analysis": merged_analysis,
                    "fallback_used": fallback_used,
                    "analysis_mode": analysis_mode,
                },
            ),
        )
    
    def _quick_pattern_analysis(
        self,
        source_code: str,
        variable_name: str,
        sink_code: Optional[str] = None,
        source_hints: Optional[List[str]] = None,
        sink_hints: Optional[List[str]] = None,
        max_hops: int = 5,
    ) -> Dict[str, Any]:
        """基于规则的快速数据流分析（不依赖 LLM）。"""

        code_to_analyze = f"{source_code}\n{sink_code or ''}"
        lower_code = code_to_analyze.lower()
        hints_source = self._normalize_hints(source_hints)
        hints_sink = self._normalize_hints(sink_hints)

        source_patterns: List[tuple[str, str]] = [
            (r"\$_GET\[|\$_POST\[|\$_REQUEST\[|\$_COOKIE\[", "http_request_input"),
            (r"request\.(args|form|get_json|values|data)|ctx\.query|ctx\.params", "http_request_input"),
            (r"\binput\s*\(|argv\\b|getenv\s*\(", "runtime_input"),
            (r"\brecv\s*\(|\bread\s*\(|\bfgets\s*\(", "io_input"),
        ]
        sink_patterns: List[tuple[str, str]] = [
            (r"execute\s*\(|query\s*\(|rawquery", "sql_sink"),
            (r"system\s*\(|exec\s*\(|popen\s*\(|shell_exec", "command_sink"),
            (r"eval\s*\(|new\\s+Function", "code_exec_sink"),
            (r"innerHTML|dangerouslySetInnerHTML|document\.write", "xss_sink"),
            (r"strcpy\s*\(|strcat\s*\(|sprintf\s*\(", "stack_overflow_risk"),
            (r"memcpy\s*\(|memmove\s*\(", "buffer_overflow_risk"),
            (r"gets\s*\(|scanf\s*\(", "unsafe_io_sink"),
        ]
        sanitizer_patterns: List[tuple[str, str]] = [
            (r"htmlspecialchars\s*\(|escape\(|encodeURIComponent", "output_encoding"),
            (r"filter_var\s*\(|validate|sanitize", "input_validation"),
            (r"preparedstatement|bindparam|parameterized|execute\s*\([^)]*[,)]", "parameter_binding"),
            (r"snprintf\s*\(|strncpy\s*\(|memcpy_s\s*\(|strlcpy\s*\(", "bounds_checked_copy"),
        ]

        source_nodes = [
            name for pattern, name in source_patterns if re.search(pattern, code_to_analyze, re.IGNORECASE)
        ] + hints_source
        sink_nodes = [name for pattern, name in sink_patterns if re.search(pattern, code_to_analyze, re.IGNORECASE)] + hints_sink
        sanitizers = [name for pattern, name in sanitizer_patterns if re.search(pattern, code_to_analyze, re.IGNORECASE)]

        source_nodes = self._unique_list(source_nodes)
        sink_nodes = self._unique_list(sink_nodes)
        sanitizers = self._unique_list(sanitizers)

        if source_nodes and sink_nodes and not sanitizers:
            risk_level = "high"
        elif source_nodes and sink_nodes and sanitizers:
            risk_level = "medium"
        elif sink_nodes:
            risk_level = "low"
        else:
            risk_level = "none"

        evidence_patterns = [
            variable_name,
            "strcpy(",
            "sprintf(",
            "memcpy(",
            "execute(",
            "query(",
            "system(",
            "eval(",
        ]
        evidence_lines = self._collect_evidence_lines(source_code, evidence_patterns)
        taint_steps = self._build_taint_steps(source_nodes, sanitizers, sink_nodes, variable_name, max_hops=max_hops)
        confidence = self._estimate_confidence(risk_level, source_nodes, sink_nodes, sanitizers)

        next_actions: List[str] = []
        if risk_level in {"high", "medium"}:
            next_actions.append("结合 controlflow_analysis_light 验证可达性和控制条件。")
        if any(node in {"stack_overflow_risk", "buffer_overflow_risk"} for node in sink_nodes):
            next_actions.append("提取目标函数并检查缓冲区长度边界与目标缓冲区大小。")
        if not sanitizers and risk_level in {"high", "medium"}:
            next_actions.append("补充输入验证或边界检查，并在汇点前进行约束。")
        if not next_actions:
            next_actions.append("未发现明确高风险链路，建议结合上下文继续交叉验证。")

        return {
            "source_nodes": source_nodes,
            "sink_nodes": sink_nodes,
            "sanitizers": sanitizers,
            "taint_steps": taint_steps,
            "risk_level": risk_level,
            "confidence": confidence,
            "evidence_lines": evidence_lines,
            "next_actions": next_actions,
            "analysis_engine": "rules",
        }

    def _load_source_code_from_file(
        self,
        file_path: str,
        *,
        start_line: Optional[int],
        end_line: Optional[int],
    ) -> Dict[str, Any]:
        normalized = str(file_path or "").strip()
        if not normalized:
            return {"ok": False, "error": "file_path 为空"}

        candidates: List[str] = []
        if self.project_root:
            candidates.append(os.path.normpath(os.path.join(self.project_root, normalized)))
        candidates.append(os.path.normpath(normalized))

        full_path = None
        for candidate in candidates:
            if self.project_root:
                root_norm = os.path.normpath(self.project_root)
                if candidate.startswith(root_norm) and os.path.isfile(candidate):
                    full_path = candidate
                    break
            elif os.path.isfile(candidate):
                full_path = candidate
                break

        if not full_path:
            return {"ok": False, "error": f"无法读取文件: {normalized}"}

        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                lines = file_obj.readlines()
        except Exception as exc:
            return {"ok": False, "error": f"读取文件失败: {exc}"}

        total_lines = len(lines)
        if total_lines == 0:
            return {"ok": True, "code": "", "file_path": normalized, "start_line": 1, "end_line": 1}

        start = max(1, int(start_line)) if start_line is not None else 1
        end = max(start, int(end_line)) if end_line is not None else min(total_lines, start + 299)
        end = min(end, total_lines)
        selected = lines[start - 1 : end]
        return {
            "ok": True,
            "code": "".join(selected),
            "file_path": normalized,
            "start_line": start,
            "end_line": end,
        }

    @staticmethod
    def _normalize_hints(value: Optional[List[str]]) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _unique_list(values: List[str]) -> List[str]:
        output: List[str] = []
        seen = set()
        for item in values:
            key = str(item).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            output.append(key)
        return output

    @staticmethod
    def _collect_evidence_lines(source_code: str, patterns: List[str], max_lines: int = 12) -> List[int]:
        lines = source_code.splitlines()
        results: List[int] = []
        for idx, line in enumerate(lines, start=1):
            if any(pattern and pattern.lower() in line.lower() for pattern in patterns):
                results.append(idx)
            if len(results) >= max_lines:
                break
        return results

    def _build_taint_steps(
        self,
        source_nodes: List[str],
        sanitizers: List[str],
        sink_nodes: List[str],
        variable_name: str,
        *,
        max_hops: int,
    ) -> List[str]:
        hops = max(2, min(max_hops, 12))
        steps: List[str] = [f"source -> {variable_name}"]
        if sanitizers:
            for sanitizer in sanitizers[: max(1, hops - 2)]:
                steps.append(f"{variable_name} -> {sanitizer}")
        else:
            steps.append(f"{variable_name} -> unsanitized_flow")
        if sink_nodes:
            steps.append(f"{variable_name} -> {sink_nodes[0]}")
        return self._unique_list(steps)[:hops]

    @staticmethod
    def _estimate_confidence(
        risk_level: str,
        source_nodes: List[str],
        sink_nodes: List[str],
        sanitizers: List[str],
    ) -> float:
        base = {"high": 0.85, "medium": 0.72, "low": 0.55, "none": 0.35}.get(risk_level, 0.5)
        if source_nodes and sink_nodes:
            base += 0.05
        if sanitizers:
            base -= 0.08
        return max(0.0, min(base, 1.0))

    def _build_analysis_prompt(
        self,
        *,
        source_code: str,
        sink_code: Optional[str],
        variable_name: str,
        source_hints: Optional[List[str]],
        sink_hints: Optional[List[str]],
    ) -> str:
        source_hint_text = ", ".join(self._normalize_hints(source_hints)) or "无"
        sink_hint_text = ", ".join(self._normalize_hints(sink_hints)) or "无"
        prompt = f"""你是代码数据流分析器，请分析变量 `{variable_name}` 的 Source->Sink 传播链路。\n\n源码:\n```\n{source_code}\n```\n"""
        if sink_code:
            prompt += f"""候选汇点代码:\n```\n{sink_code}\n```\n"""
        prompt += f"""提示:\n- source_hints: {source_hint_text}\n- sink_hints: {sink_hint_text}\n\n请输出 JSON，字段必须包含：\n- source_nodes: string[]\n- sink_nodes: string[]\n- sanitizers: string[]\n- taint_steps: string[]\n- risk_level: high|medium|low|none\n- confidence: 0-1\n- evidence_lines: integer[]\n- next_actions: string[]\n"""
        return prompt

    def _normalize_llm_analysis(self, result: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(result, dict):
            return None
        source_nodes = result.get("source_nodes")
        if not isinstance(source_nodes, list):
            source_type = result.get("source_type")
            source_nodes = [source_type] if isinstance(source_type, str) and source_type.strip() else []
        sink_nodes = result.get("sink_nodes")
        if not isinstance(sink_nodes, list):
            sink_nodes = result.get("dangerous_sinks") if isinstance(result.get("dangerous_sinks"), list) else []
        sanitizers = result.get("sanitizers")
        if not isinstance(sanitizers, list):
            sanitizers = result.get("sanitization_methods") if isinstance(result.get("sanitization_methods"), list) else []
        taint_steps = result.get("taint_steps") if isinstance(result.get("taint_steps"), list) else []
        risk_level = str(result.get("risk_level") or "low").strip().lower()
        if risk_level not in {"high", "medium", "low", "none"}:
            risk_level = "low"
        confidence = result.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else 0.65
        except Exception:
            confidence_value = 0.65
        evidence_lines_raw = result.get("evidence_lines")
        evidence_lines: List[int] = []
        if isinstance(evidence_lines_raw, list):
            for item in evidence_lines_raw:
                try:
                    line_value = int(item)
                except Exception:
                    continue
                if line_value > 0:
                    evidence_lines.append(line_value)
        next_actions = result.get("next_actions")
        if not isinstance(next_actions, list):
            recommendation = result.get("recommendation")
            next_actions = [str(recommendation)] if isinstance(recommendation, str) and recommendation.strip() else []

        return {
            "source_nodes": self._unique_list([str(item).strip() for item in source_nodes if str(item).strip()]),
            "sink_nodes": self._unique_list([str(item).strip() for item in sink_nodes if str(item).strip()]),
            "sanitizers": self._unique_list([str(item).strip() for item in sanitizers if str(item).strip()]),
            "taint_steps": self._unique_list([str(item).strip() for item in taint_steps if str(item).strip()]),
            "risk_level": risk_level,
            "confidence": max(0.0, min(confidence_value, 1.0)),
            "evidence_lines": sorted(set(evidence_lines)),
            "next_actions": self._unique_list([str(item).strip() for item in next_actions if str(item).strip()]),
            "analysis_engine": "llm",
        }

    @staticmethod
    def _merge_risk_level(primary: str, secondary: Optional[str]) -> str:
        ranking = {"none": 0, "low": 1, "medium": 2, "high": 3}
        if not secondary:
            return primary
        left = ranking.get(primary, 1)
        right = ranking.get(str(secondary).strip().lower(), 1)
        return primary if left >= right else str(secondary).strip().lower()

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except Exception:
            return default

    def _merge_analysis(
        self,
        quick_analysis: Dict[str, Any],
        llm_analysis: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not isinstance(llm_analysis, dict):
            return quick_analysis

        merged = dict(quick_analysis)
        merged["source_nodes"] = self._unique_list(list(quick_analysis.get("source_nodes", [])) + list(llm_analysis.get("source_nodes", [])))
        merged["sink_nodes"] = self._unique_list(list(quick_analysis.get("sink_nodes", [])) + list(llm_analysis.get("sink_nodes", [])))
        merged["sanitizers"] = self._unique_list(list(quick_analysis.get("sanitizers", [])) + list(llm_analysis.get("sanitizers", [])))
        merged["taint_steps"] = self._unique_list(list(quick_analysis.get("taint_steps", [])) + list(llm_analysis.get("taint_steps", [])))
        merged["risk_level"] = self._merge_risk_level(
            str(quick_analysis.get("risk_level") or "low"),
            str(llm_analysis.get("risk_level") or "").strip().lower() or None,
        )
        merged["confidence"] = max(
            self._coerce_float(quick_analysis.get("confidence"), 0.0),
            self._coerce_float(llm_analysis.get("confidence"), 0.0),
        )
        merged["evidence_lines"] = sorted(
            set(list(quick_analysis.get("evidence_lines", [])) + list(llm_analysis.get("evidence_lines", [])))
        )
        merged["next_actions"] = self._unique_list(
            list(quick_analysis.get("next_actions", [])) + list(llm_analysis.get("next_actions", []))
        )
        merged["analysis_engine"] = "rules+llm"
        return merged

    @staticmethod
    def _format_analysis_result(analysis: Dict[str, Any], variable_name: str, file_path: str) -> str:
        lines = [
            "数据流分析结果",
            f"变量: {variable_name}",
            f"文件: {file_path}",
            f"风险等级: {analysis.get('risk_level', 'low')}",
            f"置信度: {analysis.get('confidence', 0.0):.2f}",
            f"Source 节点: {', '.join(analysis.get('source_nodes', [])) or '无'}",
            f"Sink 节点: {', '.join(analysis.get('sink_nodes', [])) or '无'}",
            f"净化节点: {', '.join(analysis.get('sanitizers', [])) or '无'}",
        ]
        taint_steps = analysis.get("taint_steps") or []
        if taint_steps:
            lines.append("传播路径:")
            lines.extend([f"- {step}" for step in taint_steps[:10]])
        evidence_lines = analysis.get("evidence_lines") or []
        if evidence_lines:
            lines.append(f"证据行: {', '.join(str(item) for item in evidence_lines[:20])}")
        next_actions = analysis.get("next_actions") or []
        if next_actions:
            lines.append("建议动作:")
            lines.extend([f"- {item}" for item in next_actions[:6]])
        return "\n".join(lines)


class VulnerabilityValidationInput(BaseModel):
    """漏洞验证输入"""
    code: str = Field(description="可能存在漏洞的代码")
    vulnerability_type: str = Field(description="漏洞类型")
    file_path: str = Field(default="unknown", description="文件路径")
    line_number: Optional[int] = Field(default=None, description="行号")
    context: Optional[str] = Field(default=None, description="额外上下文")


class VulnerabilityValidationTool(AgentTool):
    """
    漏洞验证工具
    验证疑似漏洞是否真实存在
    """
    
    def __init__(self, llm_service):
        super().__init__()
        self.llm_service = llm_service
    
    @property
    def name(self) -> str:
        return "vulnerability_validation"
    
    @property
    def description(self) -> str:
        return """验证疑似漏洞是否真实存在。
对发现的潜在漏洞进行深入分析，判断是否为真正的安全问题。

输入:
- code: 包含疑似漏洞的代码
- vulnerability_type: 漏洞类型（如 sql_injection, xss 等）
- file_path: 文件路径
- line_number: 可选，行号
- context: 可选，额外的上下文代码

输出:
- 验证结果（确认/可能/误报）
- 详细分析
- 利用条件
- PoC 思路（如果确认存在漏洞）"""
    
    @property
    def args_schema(self):
        return VulnerabilityValidationInput
    
    async def _execute(
        self,
        code: str,
        vulnerability_type: str,
        file_path: str = "unknown",
        line_number: Optional[int] = None,
        context: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        """执行漏洞验证"""
        try:
            validation_prompt = f"""你是一个专业的安全研究员，请验证以下代码中是否真的存在 {vulnerability_type} 漏洞。

代码:
```
{code}
```

{f'额外上下文:' + chr(10) + '```' + chr(10) + context + chr(10) + '```' if context else ''}

请分析:
1. 这段代码是否真的存在 {vulnerability_type} 漏洞？
2. 漏洞的利用条件是什么？
3. 攻击者如何利用这个漏洞？
4. 这是否可能是误报？为什么？

请返回 JSON 格式:
{{
    "is_vulnerable": true/false/null (null表示无法确定),
    "confidence": 0.0-1.0,
    "verdict": "confirmed/likely/unlikely/false_positive",
    "exploitation_conditions": ["条件1", "条件2"],
    "attack_vector": "攻击向量描述",
    "poc_idea": "PoC思路（如果存在漏洞）",
    "false_positive_reason": "如果是误报，说明原因",
    "detailed_analysis": "详细分析"
}}
"""
            
            result = await self.llm_service.analyze_code_with_custom_prompt(
                code=code,
                language="text",
                custom_prompt=validation_prompt,
            )
            
            # 格式化输出
            output_parts = [f"🔎 漏洞验证结果 - {vulnerability_type}\n"]
            output_parts.append(f"文件: {file_path}")
            if line_number:
                output_parts.append(f"行号: {line_number}")
            output_parts.append("")
            
            if isinstance(result, dict):
                # 验证结果
                verdict_icons = {
                    "confirmed": "🔴 确认存在漏洞",
                    "likely": "🟠 可能存在漏洞",
                    "unlikely": "🟡 可能是误报",
                    "false_positive": "🟢 误报",
                }
                verdict = result.get("verdict", "unknown")
                output_parts.append(f"判定: {verdict_icons.get(verdict, verdict)}")
                
                if result.get("confidence"):
                    output_parts.append(f"置信度: {result.get('confidence') * 100:.0f}%")
                
                if result.get("exploitation_conditions"):
                    output_parts.append(f"\n利用条件:")
                    for cond in result.get("exploitation_conditions", []):
                        output_parts.append(f"  - {cond}")
                
                if result.get("attack_vector"):
                    output_parts.append(f"\n攻击向量: {result.get('attack_vector')}")
                
                if result.get("poc_idea") and verdict in ["confirmed", "likely"]:
                    output_parts.append(f"\nPoC思路: {result.get('poc_idea')}")
                
                if result.get("false_positive_reason") and verdict in ["unlikely", "false_positive"]:
                    output_parts.append(f"\n误报原因: {result.get('false_positive_reason')}")
                
                if result.get("detailed_analysis"):
                    output_parts.append(f"\n详细分析:\n{result.get('detailed_analysis')}")
            else:
                output_parts.append(str(result))
            
            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={
                    "vulnerability_type": vulnerability_type,
                    "file_path": file_path,
                    "line_number": line_number,
                    "validation": result,
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"漏洞验证失败: {str(e)}",
            )
