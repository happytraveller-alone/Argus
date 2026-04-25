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


REPORT_SYSTEM_PROMPT = """你是 Argus 的漏洞报告智能体，负责针对**已通过初步验证的漏洞**（输入 verdict 通常为 confirmed 或 likely）进行二次代码复审，并在漏洞真实存在时生成结构清晰、内容详实、技术人员可直接阅读的漏洞详情报告。

## 🎯 核心职责

你的任务是：
1. **阅读源代码并再次审查**：深入阅读漏洞所在文件及相关代码，确认输入 finding 与实际代码是否一致
2. **追踪攻击路径**：从用户可控输入（source）追踪到危险操作（sink）的完整调用链
3. **修正 finding**：如果输入中的 file_path、line_start、function_name、title、vulnerability_type、description 等字段与实际代码不一致，必须调用 `update_vulnerability_finding` 修正
4. **写明复审结论**：如果复审后认为漏洞并不成立，必须通过 `update_vulnerability_finding` 更新描述、标题、定位信息或 verification_result 允许字段，把“不成立/证据不足”的结论写清楚
5. **撰写详情报告**：输出格式规范的 Markdown 漏洞报告，并基于修正后的 finding 内容

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
| `get_code_window` | 读取漏洞所在文件窗口 | **第一步必做**：读取 file_path 及相关文件 |
| `get_symbol_body` | 提取目标函数的完整代码体 | 需要精确分析函数逻辑时 |
| `search_code` | 搜索调用方、依赖、相关模式 | 追踪调用链或寻找相关利用点 |
| `dataflow_analysis` | 数据流分析 | 追踪从 source 到 sink 的完整污染传播路径 |
| `update_vulnerability_finding` | 修正 finding 结构化字段 | 核对源码发现输入存在幻觉/错位时必须调用 |

**工具使用原则：**
- 文件路径统一使用相对于项目根目录的路径（如 `app/api/user.py`）
- 先读代码再写报告，禁止凭空捏造代码内容
- 输入 finding 可能存在幻觉，尤其是 line_start、function_name、title、漏洞类型、描述
- 一旦发现结构化字段与实际代码不一致，必须先调用 `update_vulnerability_finding`，再继续写报告
- 如果复审后认为漏洞不成立，必须先调用 `update_vulnerability_finding` 记录修正后的结论与证据，再输出最终结果
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
- **结束前自检**：Final Answer 前必须确认修正后的 finding_identity 仍然正确，且报告内容与最新 finding 一致
- **Final Answer 必须是完整 Markdown 报告**：不是摘要，不是 JSON，是完整的 Markdown 文档
- **格式**：Thought/Action/Action Input/Observation/Final Answer 纯文本格式，Final Answer 后跟 Markdown 报告正文

## 示例流程

```
Thought: 首先读取漏洞所在文件，了解代码上下文。
Action: get_code_window
Action Input: {"file_path": "app/api/search.py", "anchor_line": 45, "before_lines": 15, "after_lines": 20}

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


PROJECT_REPORT_SYSTEM_PROMPT = """你是 Argus 的项目风险评估智能体。你的输入是已经验证过的漏洞列表（可包含 confirmed / likely / uncertain / false_positive）。

你的任务是生成一份**项目总体风险评估报告**（Markdown），用于管理层和研发团队决策。请严格遵守：

1. 基于输入数据进行归纳，禁止虚构不存在的漏洞或组件
2. 报告必须包含：总体风险等级、漏洞分布、主要攻击面、关键证据摘要、优先修复路线
3. 若输入为空或仅有误报，明确说明”当前未发现可确认风险”
4. 输出必须是完整 Markdown，禁止 JSON

## Top 风险条目格式规范（严格遵守）
- 每条格式：`N. [SEVERITY] title (file_path:line_start)`
- **title 字段直接使用输入数据中的 title，禁止在 title 前追加 file_path 或 function_name**
- 若同一 (file_path, line_start, vulnerability_type) 组合出现多次，仅保留其中置信度最高的一条（去重）
- file_path 和 line_start 直接取自输入数据，不做拼接修改
- 示例：`1. [CRITICAL] node_from_xml 函数栈溢出漏洞 (src/xplist.c:1334)`

## 严重程度分布格式（统一风格）
- 使用表格或结构化列表，不要使用 JSON 字典字面量
- 漏洞类型分布同理，使用 Markdown 列表而非 Python dict 格式

## 输出结构
- 项目概览（漏洞总数、各 verdict 数量）
- 风险总览（严重程度分布 + 漏洞类型分布，使用表格或列表）
- Top 风险条目（取前10条，按严重程度+置信度排序，格式见上）
- 业务影响评估
- 优先级修复计划（P0/P1/P2）
- 后续治理建议（测试、监控、流程）
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
            max_iterations=500,
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)

        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[ReportStep] = []
        self._latest_updated_finding: Optional[Dict[str, Any]] = None
        # WorkflowEngine 会据此决定是否调用项目级报告模式。
        self.supports_project_risk_report: bool = True

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

        project_info: Dict[str, Any] = input_data.get("project_info") or {}
        config: Dict[str, Any] = input_data.get("config") or {}
        report_mode = str(input_data.get("report_mode") or "").strip().lower()
        findings_payload = input_data.get("findings")
        finding: Dict[str, Any] = input_data.get("finding") or {}

        project_mode = report_mode == "project" or (
            isinstance(findings_payload, list) and not finding
        )
        if project_mode:
            return await self._run_project_report_mode(
                findings=findings_payload if isinstance(findings_payload, list) else [],
                project_info=project_info,
                config=config,
                start_ts=start_ts,
            )

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
            f"请先对以下已验证漏洞做一次代码级复审，再生成完整的漏洞详情报告。\n\n"
            f"**项目名称**: {project_name}\n\n"
            f"**已验证漏洞数据**：\n```json\n{finding_json}\n```\n\n"
            "请先调用工具读取源代码；如果发现 finding 与代码不一致或漏洞并不成立，先调用 update_vulnerability_finding 修正，再输出最终 Markdown。"
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

        effective_finding = self._latest_updated_finding or finding
        validation_error = self._validate_effective_finding(finding, effective_finding)
        if validation_error:
            duration_ms = int((time.time() - start_ts) * 1000)
            return AgentResult(
                success=False,
                error=validation_error,
                data={
                    "vulnerability_report": "",
                    "finding_title": effective_finding.get("title", ""),
                    "finding_id": finding.get("id", ""),
                    "updated_finding": self._latest_updated_finding,
                    "finding_validated": False,
                },
                iterations=iteration,
                tool_calls=tool_calls_count,
                tokens_used=total_tokens,
                duration_ms=duration_ms,
            )

        # ── 兜底：若 LLM 未给出 Final Answer，尝试从对话提取 ────────────
        if not final_report:
            final_report = self._extract_report_fallback(effective_finding)
            last_error = last_error or "ReportAgent 未在最大迭代内给出 Final Answer，已使用兜底报告"
            logger.warning("[ReportAgent] %s", last_error)

        duration_ms = int((time.time() - start_ts) * 1000)

        return AgentResult(
            success=bool(final_report),
            error=last_error if not final_report else None,
            data={
                "vulnerability_report": final_report,
                "finding_title": effective_finding.get("title", ""),
                "finding_id": finding.get("id", ""),
                "updated_finding": self._latest_updated_finding,
                "finding_validated": True,
            },
            iterations=iteration,
            tool_calls=tool_calls_count,
            tokens_used=total_tokens,
            duration_ms=duration_ms,
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    async def _run_project_report_mode(
        self,
        findings: List[Dict[str, Any]],
        project_info: Dict[str, Any],
        config: Dict[str, Any],
        start_ts: float,
    ) -> AgentResult:
        """项目级风险评估报告模式：一次性汇总所有 findings。"""
        safe_findings = [item for item in findings if isinstance(item, dict)]
        project_name = (
            project_info.get("name")
            or project_info.get("project_name")
            or config.get("project_name")
            or "unknown"
        )
        root_path = project_info.get("root") or config.get("project_root") or ""

        severity_stats = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        verdict_stats = {"confirmed": 0, "likely": 0, "uncertain": 0, "false_positive": 0}
        vuln_type_stats: Dict[str, int] = {}
        for item in safe_findings:
            severity = str(item.get("severity") or "").strip().lower()
            if severity in severity_stats:
                severity_stats[severity] += 1
            verdict = str(
                item.get("verdict")
                or ((item.get("verification_result") or {}).get("verdict") if isinstance(item.get("verification_result"), dict) else "")
                or ""
            ).strip().lower()
            if verdict in verdict_stats:
                verdict_stats[verdict] += 1
            vuln_type = str(item.get("vulnerability_type") or "unknown").strip().lower()
            vuln_type_stats[vuln_type] = vuln_type_stats.get(vuln_type, 0) + 1

        condensed_findings = []
        for idx, item in enumerate(safe_findings[:50], start=1):
            condensed_findings.append(
                {
                    "rank": idx,
                    "title": item.get("title"),
                    "vulnerability_type": item.get("vulnerability_type"),
                    "severity": item.get("severity"),
                    "verdict": item.get("verdict")
                    or (
                        (item.get("verification_result") or {}).get("verdict")
                        if isinstance(item.get("verification_result"), dict)
                        else None
                    ),
                    "confidence": item.get("confidence")
                    or (
                        (item.get("verification_result") or {}).get("confidence")
                        if isinstance(item.get("verification_result"), dict)
                        else None
                    ),
                    "file_path": item.get("file_path"),
                    "line_start": item.get("line_start"),
                    "line_end": item.get("line_end"),
                    "source": item.get("source"),
                    "sink": item.get("sink"),
                }
            )

        user_payload = {
            "project": {"name": project_name, "root": root_path},
            "stats": {
                "total_findings": len(safe_findings),
                "severity_distribution": severity_stats,
                "verdict_distribution": verdict_stats,
                "vulnerability_type_distribution": vuln_type_stats,
            },
            "findings": condensed_findings,
        }

        prompt = (
            "请基于以下输入生成项目总体风险评估报告。"
            "输出必须是 Markdown，且包含风险等级、重点漏洞、业务影响与修复优先级。\n\n"
            f"```json\n{json.dumps(user_payload, ensure_ascii=False, indent=2)}\n```"
        )
        messages = [
            {"role": "system", "content": PROJECT_REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        tokens_used = 0
        report_text = ""
        error_text: Optional[str] = None
        try:
            report_text, usage = await self._call_llm(messages)
            if isinstance(usage, dict):
                tokens_used = int(usage.get("total_tokens") or 0)
        except Exception as exc:
            error_text = str(exc)
            logger.warning("[ReportAgent] Project report LLM call failed: %s", exc)

        if not report_text or not str(report_text).strip():
            report_text = self._build_project_report_fallback(
                project_name=project_name,
                findings=safe_findings,
                severity_stats=severity_stats,
                verdict_stats=verdict_stats,
                vuln_type_stats=vuln_type_stats,
            )
            if not error_text:
                error_text = "ReportAgent: 项目级报告使用兜底模板生成"

        duration_ms = int((time.time() - start_ts) * 1000)
        return AgentResult(
            success=bool(report_text),
            error=None if report_text else (error_text or "ReportAgent: 项目级报告生成失败"),
            data={
                "project_risk_report": report_text,
                "project_name": project_name,
                "total_findings": len(safe_findings),
                "severity_distribution": severity_stats,
                "verdict_distribution": verdict_stats,
                "vulnerability_type_distribution": vuln_type_stats,
            },
            iterations=1,
            tool_calls=0,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
        )

    async def _call_llm(self, messages: List[Dict[str, str]]):
        """调用 LLM 服务，返回 (response_text, usage_dict)。"""
        result = await self.llm_service.complete(
            messages=messages,
            temperature=0.2,
        )
        if isinstance(result, dict):
            return result.get("content", ""), result.get("usage", {})
        return str(result), {}

    def _build_project_report_fallback(
        self,
        *,
        project_name: str,
        findings: List[Dict[str, Any]],
        severity_stats: Dict[str, int],
        verdict_stats: Dict[str, int],
        vuln_type_stats: Dict[str, int],
    ) -> str:
        """LLM 失败时的项目级风险报告兜底模板。"""
        total = len(findings)

        def _coerce_confidence(value: Any) -> float:
            if value is None:
                return 0.0
            if isinstance(value, (int, float)):
                return float(value)
            text = str(value).strip().lower()
            if not text:
                return 0.0
            try:
                return float(text.rstrip("%"))
            except Exception:
                pass
            severity_alias = {
                "critical": 0.95,
                "严重": 0.95,
                "high": 0.85,
                "高危": 0.85,
                "medium": 0.6,
                "中危": 0.6,
                "low": 0.35,
                "低危": 0.35,
                "info": 0.2,
                "信息": 0.2,
            }
            return severity_alias.get(text, 0.0)

        top_findings = sorted(
            [item for item in findings if isinstance(item, dict)],
            key=lambda item: (
                {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(
                    str(item.get("severity") or "").strip().lower(),
                    9,
                ),
                -_coerce_confidence(item.get("confidence")),
            ),
        )[:10]

        lines = [
            f"# 项目风险评估报告：{project_name}",
            "",
            "## 项目概览",
            "",
            f"- 漏洞总数：{total}",
            f"- confirmed：{verdict_stats.get('confirmed', 0)}",
            f"- likely：{verdict_stats.get('likely', 0)}",
            f"- uncertain：{verdict_stats.get('uncertain', 0)}",
            f"- false_positive：{verdict_stats.get('false_positive', 0)}",
            "",
            "## 风险总览",
            "",
            "- 严重程度分布",
            f"  - critical：{severity_stats.get('critical', 0)}",
            f"  - high：{severity_stats.get('high', 0)}",
            f"  - medium：{severity_stats.get('medium', 0)}",
            f"  - low：{severity_stats.get('low', 0)}",
            f"  - info：{severity_stats.get('info', 0)}",
            "- 漏洞类型分布",
        ]

        sorted_vuln_types = sorted(
            vuln_type_stats.items(),
            key=lambda item: (-int(item[1]), str(item[0])),
        )
        if sorted_vuln_types:
            for vuln_type, count in sorted_vuln_types:
                lines.append(f"  - {vuln_type}：{count}")
        else:
            lines.append("  - 暂无")
        lines.extend(
            [
                "",
                "## Top 风险条目",
                "",
            ]
        )

        if not top_findings:
            lines.extend(
                [
                    "- 当前未发现可确认风险，建议继续保持基线安全扫描与代码审查。",
                    "",
                ]
            )
        else:
            for idx, item in enumerate(top_findings, start=1):
                lines.append(
                    f"{idx}. {item.get('title') or '未命名漏洞'} | "
                    f"{item.get('severity') or 'unknown'} | "
                    f"{item.get('file_path') or '-'}:{item.get('line_start') or '-'}"
                )
            lines.append("")

        lines.extend(
            [
                "## 业务影响评估",
                "",
                "- 高危漏洞可能导致核心数据泄露、权限绕过或远程代码执行，建议优先治理 confirmed/high-risk 项。",
                "- uncertain 项建议安排人工复核，避免遗漏真实风险。",
                "",
                "## 优先级修复计划",
                "",
                "- P0：confirmed 且严重程度为 critical/high 的漏洞，立即修复并回归验证。",
                "- P1：likely 或 medium 风险漏洞，纳入最近迭代修复计划。",
                "- P2：uncertain/low 风险项，结合业务暴露面做人工复审与监控。",
                "",
                "## 后续治理建议",
                "",
                "- 将漏洞类型热点沉淀为编码规范与静态规则。",
                "- 对关键入口补充单元/集成安全测试和运行时告警。",
                "- 在发布前执行最小化回归与复测，确保修复不引入新缺陷。",
            ]
        )
        return "\n".join(lines)

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

    def _validate_effective_finding(
        self,
        original_finding: Dict[str, Any],
        effective_finding: Dict[str, Any],
    ) -> Optional[str]:
        """在返回前校验最终使用的 finding 是否仍可安全同步。"""
        if not isinstance(effective_finding, dict):
            return "ReportAgent: 最终 finding 不是有效对象"

        original_identity = str(original_finding.get("finding_identity") or "").strip()
        effective_identity = str(effective_finding.get("finding_identity") or "").strip()
        if not effective_identity:
            return "ReportAgent: 最终 finding 缺少 finding_identity，无法同步数据库"
        if original_identity and effective_identity != original_identity:
            return (
                "ReportAgent: 最终 finding_identity 与输入不一致，"
                f"input={original_identity}, effective={effective_identity}"
            )

        required_fields = ("title", "file_path", "line_start", "vulnerability_type")
        missing_fields = [
            field_name
            for field_name in required_fields
            if not str(effective_finding.get(field_name) or "").strip()
        ]
        if missing_fields:
            return (
                "ReportAgent: 最终 finding 缺少关键字段: "
                + ", ".join(missing_fields)
            )
        return None
