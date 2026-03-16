"""
Report Agent (漏洞报告层) - LLM 驱动版

当 VerificationAgent 判定一个漏洞为 confirmed 或 likely 后，由本 Agent 负责
通过阅读源码、追踪数据流，生成结构化的、供人阅读的漏洞详情报告（Markdown 格式）。

类型: ReAct（内部通过工具读取代码，最终输出 Markdown 报告）
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern
from .react_parser import parse_react_response

logger = logging.getLogger(__name__)


REPORT_SYSTEM_PROMPT = """你是 VulHunter 的漏洞报告智能体，负责针对**已验证的漏洞**（verdict 为 confirmed 或 likely）生成结构清晰、内容详实、技术人员可直接阅读的漏洞详情报告。

## 🎯 核心职责

你的任务是：
1. **阅读源代码**：深入阅读漏洞所在文件及相关代码，理解漏洞上下文
2. **追踪攻击路径**：从用户可控输入（source）追踪到危险操作（sink）的完整调用链
3. **修正 finding**：如果输入中的 file_path、line_start、function_name、title、vulnerability_type、description 等字段与实际代码不一致，必须调用 `update_vulnerability_finding` 修正
4. **撰写详情报告**：输出格式规范的 Markdown 漏洞报告

## 输入格式

你将收到一个已验证漏洞的 JSON 数据，包含以下关键字段：
```json
{
    "finding_identity": "fid:...",
    "title": "漏洞标题（三段式）",
    "file_path": "漏洞所在文件（相对路径）",
    "line_start": 45,
    "vulnerability_type": "sql_injection",
    "severity": "high",
    "confidence": 0.85,
    "verdict": "confirmed",
    "description": "漏洞描述",
    "code_snippet": "相关代码片段",
    "poc_code": "PoC 代码（如有）",
    "suggestion": "修复建议",
    "function_name": "触发漏洞的函数名",
    "source": "污染源",
    "sink": "危险函数"
}
```

## 工具使用指南

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| `read_file` | 读取漏洞所在文件 | **第一步必做**：读取 file_path 及相关文件 |
| `extract_function` | 提取目标函数的完整代码体 | 需要精确分析函数逻辑时 |
| `search_code` | 搜索调用方、依赖、相关模式 | 追踪调用链或寻找相关利用点 |
| `dataflow_analysis` | 数据流分析 | 追踪从 source 到 sink 的完整污染传播路径 |
| `update_vulnerability_finding` | 修正 finding 结构化字段 | 核对源码发现输入存在幻觉/错位时必须调用 |

**工具使用原则：**
- 文件路径统一使用相对于项目根目录的路径（如 `app/api/user.py`）
- 先读代码再写报告，禁止凭空捏造代码内容
- 输入 finding 可能存在幻觉，尤其是 line_start、function_name、title、漏洞类型、描述
- 一旦发现结构化字段与实际代码不一致，必须先调用 `update_vulnerability_finding`，再继续写报告
- 最多使用 8 轮工具调用，保持高效

## 报告格式要求

报告必须是合法 Markdown，包含以下所有章节，无一遗漏：

```
# 漏洞报告：{title}

## 漏洞概述

| 字段 | 详情 |
|------|------|
| **漏洞类型** | {vulnerability_type_cn} |
| **危险等级** | {severity_cn}（{severity}） |
| **置信度** | {confidence}（{verdict}） |
| **漏洞位置** | `{file_path}` 第 {line_start} 行 |
| **触发函数** | `{function_name}` |

## 漏洞详情

（结合代码阅读结果，详细描述漏洞的成因、触发条件、以及为什么会造成安全问题）

## 代码证据

```{language}
// 关键漏洞代码（标注行号和问题所在）
```

（对代码的详细解释，指出具体危险操作）

## 攻击路径分析

（描述从外部输入到漏洞触发的完整数据流 / 调用链，格式示例：）

1. **输入点**：`{source}` — 用户可控输入来源
2. **传播**：→ `function_a()` → `function_b()` → ...
3. **触发点**：`{sink}` — 危险操作执行位置

## 复现方式

（提供可操作的复现步骤或 PoC，若已有 poc_code 则展示并解释）

```
# 复现命令 / Payload 示例
```

## 影响分析

（描述该漏洞如果被成功利用可能造成的危害，如数据泄露、权限提升、远程代码执行等）

## 修复建议

（提供具体、可落地的修复方案，必要时给出代码示例）

```{language}
// 修复后的代码示例
```
```

## 重要约束

- **禁止首轮直接输出 Final Answer**：必须先调用工具读取代码再生成报告
- **禁止捏造代码**：报告中的代码证据必须来自实际读取的文件
- **禁止只修 Markdown 不修 finding**：如果发现输入 finding 不准，必须先调用 `update_vulnerability_finding`
- **Final Answer 必须是完整 Markdown 报告**：不是摘要，不是 JSON，是完整的 Markdown 文档
- **格式**：Thought/Action/Action Input/Observation/Final Answer 纯文本格式，Final Answer 后跟 Markdown 报告正文

## 示例流程

```
Thought: 首先读取漏洞所在文件，了解代码上下文。
Action: read_file
Action Input: {"file_path": "app/api/search.py", "start_line": 30, "end_line": 80}

Observation: ...（代码内容）...

Thought: 已读取代码，现在追踪 user_input 的数据流。
Action: dataflow_analysis
Action Input: {"source": "request.args.get('q')", "sink": "cursor.execute", "file_path": "app/api/search.py"}

Observation: ...（数据流分析结果）...

Thought: 信息已充分，生成报告。
Final Answer:
# 漏洞报告：app/api/search.py 中 search 函数 SQL 注入漏洞

...（完整 Markdown 报告）...
```
"""


@dataclass
class ReportStep:
    """ReportAgent 的单步 ReAct 执行记录"""
    thought: str = ""
    action: Optional[str] = None
    action_input: Optional[Dict[str, Any]] = None
    observation: str = ""
    is_final: bool = False
    final_answer: str = ""  # 最终报告（Markdown 字符串）


class ReportAgent(BaseAgent):
    """
    漏洞报告 Agent

    接收一条已验证的 finding，通过阅读源码生成结构化 Markdown 漏洞详情报告。
    报告写入 AgentResult.data["vulnerability_report"]。
    """

    def __init__(
        self,
        llm_service,
        tools: Dict[str, Any],
        event_emitter=None,
    ):
        tool_whitelist = ", ".join(sorted(tools.keys())) if tools else "无"
        full_system_prompt = (
            f"{REPORT_SYSTEM_PROMPT}\n\n"
            f"## 当前工具白名单\n{tool_whitelist}\n"
            "只能调用以上工具。\n"
        )

        config = AgentConfig(
            name="Report",
            agent_type=AgentType.REPORT,
            pattern=AgentPattern.REACT,
            max_iterations=12,
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)

        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[ReportStep] = []
        self._latest_updated_finding: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # ReAct 解析
    # ------------------------------------------------------------------

    def _parse_llm_response(self, response: str) -> ReportStep:
        parsed = parse_react_response(
            response,
            final_default={"report": (response or "").strip()},
            action_input_raw_key="raw_input",
        )
        step = ReportStep(
            thought=parsed.thought or "",
            action=parsed.action,
            action_input=parsed.action_input or {},
            is_final=bool(parsed.is_final),
        )
        if step.is_final:
            # Final Answer 可能是纯字符串或 dict；我们期望是 Markdown 字符串
            fa = parsed.final_answer
            if isinstance(fa, dict):
                step.final_answer = fa.get("report") or fa.get("content") or json.dumps(fa, ensure_ascii=False)
            elif isinstance(fa, str):
                step.final_answer = fa
            else:
                step.final_answer = str(response or "")
        return step

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        生成漏洞详情报告。

        input_data 结构::

            {
                "finding": <dict>,          # 已验证的 finding 对象（必须）
                "project_info": <dict>,     # 项目基本信息（可选）
                "config": <dict>,           # 运行时配置（可选）
            }

        返回 AgentResult，其中 data["vulnerability_report"] 为 Markdown 字符串。
        """
        start_ts = time.time()
        self._conversation_history = []
        self._steps = []
        self._latest_updated_finding = None

        finding: Dict[str, Any] = input_data.get("finding") or {}
        project_info: Dict[str, Any] = input_data.get("project_info") or {}
        config: Dict[str, Any] = input_data.get("config") or {}

        if not finding:
            return AgentResult(
                success=False,
                error="ReportAgent: 缺少 finding 输入",
                data={},
                iterations=0,
                tool_calls=0,
                tokens_used=0,
                duration_ms=0,
            )
        if not str(finding.get("finding_identity") or "").strip():
            return AgentResult(
                success=False,
                error="ReportAgent: finding 缺少 finding_identity",
                data={},
                iterations=0,
                tool_calls=0,
                tokens_used=0,
                duration_ms=0,
            )

        # 构建初始用户消息
        finding_json = json.dumps(finding, ensure_ascii=False, indent=2)
        project_name = project_info.get("name") or project_info.get("project_name") or "unknown"
        initial_message = (
            f"请为以下已验证漏洞生成完整的漏洞详情报告。\n\n"
            f"**项目名称**: {project_name}\n\n"
            f"**已验证漏洞数据**：\n```json\n{finding_json}\n```\n\n"
            "请先调用工具读取源代码，然后生成规范的 Markdown 格式漏洞详情报告。"
        )

        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": initial_message},
        ]

        await self.emit_thinking(
            f"ReportAgent 开始为漏洞 [{finding.get('title', '未知漏洞')}] 生成报告..."
        )

        iteration = 0
        tool_calls_count = 0
        total_tokens = 0
        final_report = ""
        last_error: Optional[str] = None

        while iteration < self.config.max_iterations:
            if self.is_cancelled:
                break

            iteration += 1

            # ── LLM 推理 ────────────────────────────────────────────────
            try:
                llm_response, usage = await self._call_llm(self._conversation_history)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("[ReportAgent] LLM call failed: %s", exc)
                last_error = str(exc)
                break

            total_tokens += usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
            self._conversation_history.append({"role": "assistant", "content": llm_response})

            # ── 解析步骤 ────────────────────────────────────────────────
            step = self._parse_llm_response(llm_response)
            self._steps.append(step)

            if step.is_final:
                final_report = step.final_answer
                await self.emit_event(
                    "info",
                    f"ReportAgent 完成报告生成（漏洞：{(self._latest_updated_finding or finding).get('title', '')}）",
                )
                break

            # ── 工具调用 ────────────────────────────────────────────────
            if step.action:
                tool_calls_count += 1
                observation = await self._execute_tool(step.action, step.action_input or {})
                step.observation = observation
                self._conversation_history.append(
                    {"role": "user", "content": f"Observation: {observation}"}
                )
            else:
                # 无工具调用也无 Final Answer：督促继续
                self._conversation_history.append(
                    {
                        "role": "user",
                        "content": (
                            "请继续执行报告生成任务。"
                            "如果信息已足够，请输出 Final Answer 并附完整 Markdown 报告。"
                        ),
                    }
                )

        # ── 兜底：若 LLM 未给出 Final Answer，尝试从对话提取 ────────────
        if not final_report:
            final_report = self._extract_report_fallback(self._latest_updated_finding or finding)
            last_error = last_error or "ReportAgent 未在最大迭代内给出 Final Answer，已使用兜底报告"
            logger.warning("[ReportAgent] %s", last_error)

        duration_ms = int((time.time() - start_ts) * 1000)

        return AgentResult(
            success=bool(final_report),
            error=last_error if not final_report else None,
            data={
                "vulnerability_report": final_report,
                "finding_title": (self._latest_updated_finding or finding).get("title", ""),
                "finding_id": finding.get("id", ""),
                "updated_finding": self._latest_updated_finding,
            },
            iterations=iteration,
            tool_calls=tool_calls_count,
            tokens_used=total_tokens,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    async def _call_llm(self, messages: List[Dict[str, str]]):
        """调用 LLM 服务，返回 (response_text, usage_dict)。"""
        result = await self.llm_service.complete(
            messages=messages,
            temperature=0.2,
        )
        if isinstance(result, dict):
            return result.get("content", ""), result.get("usage", {})
        return str(result), {}

    async def _execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """执行单个工具，返回 observation 字符串。"""
        tool = self.tools.get(tool_name)
        if tool is None:
            return f"错误：工具 '{tool_name}' 不存在，可用工具：{list(self.tools.keys())}"
        try:
            await self.emit_llm_action(tool_name, tool_input)
            if hasattr(tool, "execute") and asyncio.iscoroutinefunction(getattr(tool, "execute", None)):
                tool_result = await tool.execute(**(tool_input or {}))
                result = tool_result.data if hasattr(tool_result, "data") else tool_result
            elif asyncio.iscoroutinefunction(getattr(tool, "__call__", None)) or asyncio.iscoroutinefunction(tool):
                result = await tool(tool_input)
            else:
                result = tool(tool_input)
            if (
                tool_name == "update_vulnerability_finding"
                and isinstance(result, dict)
                and isinstance(result.get("updated_finding"), dict)
            ):
                self._latest_updated_finding = dict(result["updated_finding"])
            if isinstance(result, dict):
                return json.dumps(result, ensure_ascii=False)
            return str(result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[ReportAgent] Tool '%s' failed: %s", tool_name, exc)
            return f"工具 '{tool_name}' 执行失败：{exc}"

    def _extract_report_fallback(self, finding: Dict[str, Any]) -> str:
        """当 LLM 未完成时，根据 finding 字段生成基础兜底报告。"""
        title = finding.get("title") or "未命名漏洞"
        vuln_type = finding.get("vulnerability_type") or "unknown"
        severity = finding.get("severity") or "unknown"
        confidence = finding.get("confidence", "N/A")
        verdict = finding.get("verdict") or "unknown"
        file_path = finding.get("file_path") or ""
        line_start = finding.get("line_start") or ""
        function_name = finding.get("function_name") or ""
        description = finding.get("description") or ""
        code_snippet = finding.get("code_snippet") or ""
        poc_code = finding.get("poc_code") or ""
        suggestion = finding.get("suggestion") or ""
        source = finding.get("source") or ""
        sink = finding.get("sink") or ""

        location = f"`{file_path}`" + (f" 第 {line_start} 行" if line_start else "")

        report_lines = [
            f"# 漏洞报告：{title}",
            "",
            "## 漏洞概述",
            "",
            "| 字段 | 详情 |",
            "|------|------|",
            f"| **漏洞类型** | {vuln_type} |",
            f"| **危险等级** | {severity} |",
            f"| **置信度** | {confidence}（{verdict}） |",
            f"| **漏洞位置** | {location} |",
        ]
        if function_name:
            report_lines.append(f"| **触发函数** | `{function_name}` |")

        report_lines += ["", "## 漏洞详情", "", description or "（暂无描述）", ""]

        if code_snippet:
            report_lines += ["## 代码证据", "", "```", code_snippet, "```", ""]

        if source or sink:
            report_lines += ["## 攻击路径分析", ""]
            if source:
                report_lines.append(f"- **输入点（source）**：`{source}`")
            if sink:
                report_lines.append(f"- **触发点（sink）**：`{sink}`")
            report_lines.append("")

        if poc_code:
            report_lines += ["## 复现方式", "", "```", poc_code, "```", ""]

        if suggestion:
            report_lines += ["## 修复建议", "", suggestion, ""]

        return "\n".join(report_lines)
