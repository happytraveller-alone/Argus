"""
Verification Agent (漏洞验证层) - LLM 驱动版

LLM 是验证的大脑！
- LLM 决定如何验证每个漏洞
- LLM 构造验证策略
- LLM 分析验证结果
- LLM 判断是否为真实漏洞

类型: ReAct (真正的!)
"""

import asyncio
import json
import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from .base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern, TaskHandoff
from ..json_parser import AgentJsonParser
from ..prompts import CORE_SECURITY_PRINCIPLES, VULNERABILITY_PRIORITIES

logger = logging.getLogger(__name__)

VERIFICATION_SYSTEM_PROMPT = """你是漏洞验证 Agent，负责自主完成漏洞真实性校验与修复建议输出。

## 执行原则（强约束）
1. 禁止向用户追问“下一步选项/是否生成补丁/是否继续”等问题，必须自主推进。
2. 信息不足时使用默认策略补齐并继续，不得停在“等待用户确认”。
3. 只能调用运行时提供的工具白名单；未提供的工具不能调用。
4. 输出必须包含 `suggestion` 与 `fix_code`（允许简化补丁，但不能为空）。
5. 若发现无法定位到真实文件或无法形成证据，结论应为 `false_positive` 或 `likely`，不得强行 `confirmed`。
6. 若存在 `bootstrap_findings`，优先验证其高风险项并回填真实性/可达性。
7. 不允许输出“请选择/请确认后继续”等交互语句，必须直接执行默认策略并收敛结束。
8. 若字段缺失需先自我补全（基于证据与默认模板），再输出 Final Answer。
9. **语言要求**：Final Answer 中 title/description/suggestion/fix_description/verification_evidence/poc_plan 必须使用简体中文，禁止输出英文段落。
10. **验证范围强约束**：本次仅验证 `bootstrap_findings`（候选种子）列表中的项，最多验证 8 条；列表为空则应直接跳过验证并返回空 findings。不得验证或新增清单以外的发现。
11. **工具优先门禁（强约束）**：在输出任何结论或 Final Answer 前，必须至少执行一次工具调用获取代码证据（最低要求：至少一次 `read_file` 或 `search_code`），并在结论中引用 Observation 证据，禁止无证据宣称“已验证/已读取”。
12. **首轮强约束**：第一轮必须输出 Action（优先 `read_file`），不允许第一轮直接输出 Final Answer。

## 工作流
1. 先读取/提取目标代码，验证文件与行号是否真实存在。
2. 结合上下文分析可达性与真实性。
3. 输出非武器化 PoC 思路（步骤、前置条件、观测信号），禁止提供可直接利用的 payload/命令。
4. 汇总输出 Final Answer。

## 输出格式
使用纯文本 ReAct：
Thought: ...
Action: ...
Action Input: {...}

完成后输出：
Thought: ...
Final Answer: {...}

## Final Answer 字段要求
每条 finding 至少包含：
- file_path, line_start, line_end
- reachability: reachable|likely_reachable|unreachable
- authenticity/verdict: confirmed|likely|false_positive
- verification_details/evidence
- suggestion
- fix_code

PoC 约束：
- 仅输出“思路级”PoC，不输出可直接执行的利用代码或命令。
- 建议至少对 confirmed/likely 的发现提供 poc 字段。"""

@dataclass
class VerificationStep:
    """验证步骤"""
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[Dict] = None


class VerificationAgent(BaseAgent):
    """
    漏洞验证 Agent - LLM 驱动版
    
    LLM 全程参与，自主决定：
    1. 如何验证每个漏洞
    2. 使用什么工具
    3. 判断真假
    """
    
    def __init__(
        self,
        llm_service,
        tools: Dict[str, Any],
        event_emitter=None,
    ):
        # 组合增强的系统提示词
        tool_whitelist = ", ".join(sorted(tools.keys())) if tools else "无"
        full_system_prompt = (
            f"{VERIFICATION_SYSTEM_PROMPT}\n\n"
            f"## 当前工具白名单\n{tool_whitelist}\n"
            f"只能调用以上工具，不得编造工具名称。\n\n"
            f"{CORE_SECURITY_PRINCIPLES}\n\n{VULNERABILITY_PRIORITIES}"
        )
        
        config = AgentConfig(
            name="Verification",
            agent_type=AgentType.VERIFICATION,
            pattern=AgentPattern.REACT,
            max_iterations=25,
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)
        
        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[VerificationStep] = []



    
    def _parse_llm_response(self, response: str) -> VerificationStep:
        """解析 LLM 响应 - 增强版，更健壮地提取思考内容"""
        step = VerificationStep(thought="")

        # 🔥 v2.1: 预处理 - 移除 Markdown 格式标记（LLM 有时会输出 **Action:** 而非 Action:）
        cleaned_response = response
        cleaned_response = re.sub(r'\*\*Action:\*\*', 'Action:', cleaned_response)
        cleaned_response = re.sub(r'\*\*Action Input:\*\*', 'Action Input:', cleaned_response)
        cleaned_response = re.sub(r'\*\*Thought:\*\*', 'Thought:', cleaned_response)
        cleaned_response = re.sub(r'\*\*Final Answer:\*\*', 'Final Answer:', cleaned_response)
        cleaned_response = re.sub(r'\*\*Observation:\*\*', 'Observation:', cleaned_response)

        # 🔥 首先尝试提取明确的 Thought 标记（Thought 可以不存在）
        thought_match = re.search(r'Thought:\s*(.*?)(?=Action:|Final Answer:|$)', cleaned_response, re.DOTALL)
        if thought_match:
            step.thought = thought_match.group(1).strip()

        # 🔥 提取 Action（Action 优先于 Final Answer；避免同轮同时输出导致跳过工具）
        action_match = re.search(r'Action:\s*(\w+)', cleaned_response)
        if action_match:
            step.action = action_match.group(1).strip()

            # 🔥 如果没有提取到 thought，提取 Action 之前的内容作为思考
            if not step.thought:
                action_pos = cleaned_response.find('Action:')
                if action_pos > 0:
                    before_action = cleaned_response[:action_pos].strip()
                    before_action = re.sub(r'^Thought:\s*', '', before_action)
                    if before_action:
                        step.thought = before_action[:500] if len(before_action) > 500 else before_action

            # 🔥 提取 Action Input - 增强版，处理多种格式
            # 注意：必须在遇到 Final Answer 前截断，否则会把 Final Answer JSON 拼进 Action Input
            input_match = re.search(
                r'Action Input:\s*(.*?)(?=Thought:|Action:|Observation:|Final Answer:|$)',
                cleaned_response,
                re.DOTALL,
            )
            if input_match:
                input_text = input_match.group(1).strip()
                input_text = re.sub(r'```json\s*', '', input_text)
                input_text = re.sub(r'```\s*', '', input_text)

                # 🔥 v2.1: 如果 Action Input 为空或只有 **，记录警告
                if not input_text or input_text == '**' or input_text.strip() == '':
                    logger.warning(f"[Verification] Action Input is empty or malformed: '{input_text}'")
                    step.action_input = {}
                else:
                    # 使用增强的 JSON 解析器
                    step.action_input = AgentJsonParser.parse(
                        input_text,
                        default={"raw_input": input_text}
                    )
            else:
                # 🔥 v2.1: 有 Action 但没有 Action Input，记录警告
                logger.warning(f"[Verification] Action '{step.action}' found but no Action Input")
                step.action_input = {}

            return step

        # 🔥 检查是否是最终答案（仅当不存在 Action 时）
        final_match = re.search(r'Final Answer:\s*(.*?)$', cleaned_response, re.DOTALL)
        if final_match:
            step.is_final = True
            answer_text = final_match.group(1).strip()
            answer_text = re.sub(r'```json\s*', '', answer_text)
            answer_text = re.sub(r'```\s*', '', answer_text)
            # 使用增强的 JSON 解析器
            step.final_answer = AgentJsonParser.parse(
                answer_text,
                default={"findings": [], "raw_answer": answer_text}
            )
            # 确保 findings 格式正确
            if "findings" in step.final_answer:
                step.final_answer["findings"] = [
                    f for f in step.final_answer["findings"]
                    if isinstance(f, dict)
                ]

            # 🔥 如果没有提取到 thought，使用 Final Answer 前的内容作为思考
            if not step.thought:
                before_final = cleaned_response[:cleaned_response.find('Final Answer:')].strip()
                if before_final:
                    before_final = re.sub(r'^Thought:\s*', '', before_final)
                    step.thought = before_final[:500] if len(before_final) > 500 else before_final

            return step

        # 🔥 最后的 fallback：如果整个响应没有任何标记，整体作为思考
        if not step.thought and not step.action and not step.is_final:
            if response.strip():
                step.thought = response.strip()[:500]

        return step

    def _validate_final_answer_schema(self, final_answer: Dict[str, Any]) -> tuple[bool, str]:
        findings = final_answer.get("findings")
        if not isinstance(findings, list) or not findings:
            return False, "Final Answer 必须包含非空 findings 数组。"

        required_fields = ["file_path", "line_start", "line_end"]
        for index, finding in enumerate(findings, start=1):
            if not isinstance(finding, dict):
                return False, f"第 {index} 条 finding 不是对象。"

            for field_name in required_fields:
                if finding.get(field_name) in (None, "", []):
                    return False, f"第 {index} 条 finding 缺少字段: {field_name}"

            has_authenticity = finding.get("authenticity") or finding.get("verdict")
            if not has_authenticity:
                return False, f"第 {index} 条 finding 缺少 authenticity/verdict"
            if str(has_authenticity).strip().lower() not in {"confirmed", "likely", "false_positive"}:
                return False, f"第 {index} 条 finding authenticity/verdict 非法: {has_authenticity}"

            if finding.get("reachability") in (None, "", []):
                return False, f"第 {index} 条 finding 缺少 reachability"

            has_evidence = (
                finding.get("verification_details")
                or finding.get("verification_evidence")
                or finding.get("evidence")
            )
            if not has_evidence:
                return False, f"第 {index} 条 finding 缺少 verification_details/evidence"

        return True, ""

    def _contains_interactive_drift(self, text: str) -> bool:
        normalized = (text or "").lower()
        patterns = [
            "请选择",
            "请确认",
            "是否需要",
            "你需要选择",
            "需要你决定",
            "select one",
            "choose one",
            "please confirm",
            "need your choice",
        ]
        return any(pattern in normalized for pattern in patterns)

    def _normalize_verdict(self, finding: Dict[str, Any]) -> str:
        verdict = finding.get("verdict") or finding.get("authenticity")
        if isinstance(verdict, str):
            verdict = verdict.strip().lower()
        else:
            verdict = None
        if verdict in {"confirmed", "likely", "false_positive"}:
            return verdict
        confidence = finding.get("confidence", 0.0)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.0
        if finding.get("is_verified") is True:
            return "confirmed"
        if confidence >= 0.8:
            return "likely"
        if confidence <= 0.2:
            return "false_positive"
        return "likely"

    def _normalize_reachability_value(self, value: Any, verdict: str) -> str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"reachable", "likely_reachable", "unreachable"}:
                return normalized
        if verdict == "confirmed":
            return "reachable"
        if verdict == "likely":
            return "likely_reachable"
        return "unreachable"

    def _build_default_fix_code(self, finding: Dict[str, Any]) -> str:
        vuln_type = str(finding.get("vulnerability_type") or "general_issue")
        code_snippet = str(finding.get("code_snippet") or "").strip()
        if code_snippet:
            return (
                f"// secure-fix template for {vuln_type}\n"
                "// 1) validate/normalize untrusted input\n"
                "// 2) replace dangerous API with safe API\n"
                f"{code_snippet}"
            )
        return (
            f"// secure-fix template for {vuln_type}\n"
            "// apply input validation, output encoding and least-privilege checks here"
        )

    def _build_default_poc_plan(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        vuln_type = str(finding.get("vulnerability_type") or "general_issue")
        file_path = str(finding.get("file_path") or "unknown")
        line_start = finding.get("line_start") or 1
        return {
            "description": f"{vuln_type} 的非武器化验证思路",
            "steps": [
                f"在测试环境准备并定位目标代码：{file_path}:{line_start}",
                "构造最小化的可控输入，触发可疑分支并记录行为差异",
                "观察日志、返回值、异常与数据流，验证是否符合漏洞预期",
            ],
            "preconditions": [
                "仅在授权测试环境执行",
                "保留审计日志与请求样本，避免影响生产数据",
            ],
            "signals": [
                "安全边界被绕过或输入未被正确约束",
                "出现与漏洞描述一致的异常响应/执行路径",
            ],
        }

    def _repair_final_answer(
        self,
        final_answer: Dict[str, Any],
        findings_to_verify: List[Dict[str, Any]],
        verification_level: str,
    ) -> Dict[str, Any]:
        findings = final_answer.get("findings")
        if not isinstance(findings, list):
            findings = []

        fallback_findings = findings_to_verify or []
        repaired_findings: List[Dict[str, Any]] = []
        source_findings = findings if findings else fallback_findings

        for index, finding in enumerate(source_findings):
            if not isinstance(finding, dict):
                continue
            base = fallback_findings[index] if index < len(fallback_findings) and isinstance(fallback_findings[index], dict) else {}
            merged = {**base, **finding}

            file_path = str(merged.get("file_path") or merged.get("file") or "").strip()
            line_start = merged.get("line_start") or merged.get("line")
            line_end = merged.get("line_end")
            try:
                line_start = int(line_start) if line_start is not None else None
            except Exception:
                line_start = None
            try:
                line_end = int(line_end) if line_end is not None else None
            except Exception:
                line_end = None
            if line_start is None:
                line_start = 1
            if line_end is None:
                line_end = line_start

            verdict = self._normalize_verdict(merged)
            reachability = self._normalize_reachability_value(merged.get("reachability"), verdict)
            evidence = (
                merged.get("verification_details")
                or merged.get("verification_evidence")
                or merged.get("evidence")
                or "基于代码上下文与工具输出完成验证。"
            )

            suggestion = (
                merged.get("suggestion")
                or merged.get("recommendation")
                or self._get_recommendation(str(merged.get("vulnerability_type") or ""))
            )
            fix_code = merged.get("fix_code") or self._build_default_fix_code(merged)

            allow_poc = verdict in {"confirmed", "likely"}
            poc_value = merged.get("poc") if allow_poc else None
            if allow_poc and not poc_value:
                poc_value = self._build_default_poc_plan(merged)

            repaired_findings.append(
                {
                    **merged,
                    "file_path": file_path or str(base.get("file_path") or "").strip(),
                    "line_start": line_start,
                    "line_end": line_end,
                    "verdict": verdict,
                    "authenticity": verdict,
                    "reachability": reachability,
                    "verification_details": str(evidence),
                    "verification_evidence": str(evidence),
                    "suggestion": str(suggestion),
                    "fix_code": str(fix_code),
                    "poc": poc_value,
                }
            )

        summary = final_answer.get("summary")
        if not isinstance(summary, dict):
            summary = {}
        summary.setdefault("total", len(repaired_findings))
        summary.setdefault("confirmed", len([f for f in repaired_findings if f.get("verdict") == "confirmed"]))
        summary.setdefault("likely", len([f for f in repaired_findings if f.get("verdict") == "likely"]))
        summary.setdefault("false_positive", len([f for f in repaired_findings if f.get("verdict") == "false_positive"]))

        return {
            **final_answer,
            "findings": repaired_findings,
            "summary": summary,
        }
    
    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        执行漏洞验证 - LLM 全程参与！
        """
        import time
        start_time = time.time()
        
        previous_results = input_data.get("previous_results", {})
        config = input_data.get("config", {})
        verification_level = str(
            config.get("verification_level", "analysis_with_poc_plan")
        ).strip().lower()
        task = input_data.get("task", "")
        task_context = input_data.get("task_context", "")
        
        # 🔥 处理交接信息
        handoff = input_data.get("handoff")
        if handoff:
            from .base import TaskHandoff
            if isinstance(handoff, dict):
                handoff = TaskHandoff.from_dict(handoff)
            self.receive_handoff(handoff)

        # 收集待验证发现（强约束）：
        # - 仅验证 bootstrap_findings（候选种子）列表中的项
        # - 最多验证 8 条
        def _coerce_bootstrap_confidence_numeric(value: Any) -> float:
            # 入库与 flow pipeline 更偏好数值置信度；兼容 "HIGH/MEDIUM/LOW" 等字符串输入。
            if isinstance(value, (int, float)):
                return max(0.0, min(float(value), 1.0))
            if isinstance(value, str):
                text = value.strip().upper()
                if text == "HIGH":
                    return 0.9
                if text == "MEDIUM":
                    return 0.7
                if text == "LOW":
                    return 0.4
                try:
                    return max(0.0, min(float(text), 1.0))
                except Exception:
                    return 0.5
            return 0.5

        def _normalize_seed_severity(value: Any) -> str:
            text = str(value or "").strip().lower()
            if text in {"critical", "high", "medium", "low", "info"}:
                return text
            if text == "error":
                return "high"
            if text == "warning":
                return "medium"
            return "medium"

        def _iter_bootstrap_findings_sources() -> List[Dict[str, Any]]:
            candidates: List[Dict[str, Any]] = []
            # 1) handoff.context_data.bootstrap_findings（优先，避免误用 analysis findings）
            if self._incoming_handoff and isinstance(self._incoming_handoff.context_data, dict):
                items = self._incoming_handoff.context_data.get("bootstrap_findings")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            candidates.append(item)
            # 2) previous_results.bootstrap_findings
            if isinstance(previous_results, dict):
                items = previous_results.get("bootstrap_findings")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            candidates.append(item)
            # 3) input_data.config.bootstrap_findings（兼容直接调用 VerificationAgent 的情况）
            if isinstance(config, dict):
                items = config.get("bootstrap_findings")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            candidates.append(item)
            return candidates

        raw_bootstrap_candidates = _iter_bootstrap_findings_sources()
        findings_to_verify: List[Dict[str, Any]] = []
        for item in raw_bootstrap_candidates:
            if not isinstance(item, dict):
                continue
            mapped = dict(item)
            mapped["severity"] = _normalize_seed_severity(item.get("severity"))
            mapped["confidence"] = _coerce_bootstrap_confidence_numeric(item.get("confidence"))
            findings_to_verify.append(mapped)

        # 去重
        findings_to_verify = self._deduplicate(findings_to_verify)

        # 优先验证高风险项（不改变“只能验证 bootstrap_findings 列表”的强约束）
        severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        findings_to_verify.sort(
            key=lambda f: (
                -severity_weight.get(str(f.get("severity") or "medium").strip().lower(), 2),
                -float(_coerce_bootstrap_confidence_numeric(f.get("confidence"))),
            )
        )

        # 🔥 FIX: 优先处理有明确文件路径的发现，将没有文件路径的发现放到后面
        # 这确保 Analysis 的具体发现优先于 Recon 的泛化描述
        def has_valid_file_path(finding: Dict) -> bool:
            file_path = finding.get("file_path", "")
            return bool(file_path and file_path.strip() and file_path.lower() not in ["unknown", "n/a", ""])

        findings_with_path = [f for f in findings_to_verify if has_valid_file_path(f)]
        findings_without_path = [f for f in findings_to_verify if not has_valid_file_path(f)]

        # 合并：有路径的在前，没路径的在后
        findings_to_verify = findings_with_path + findings_without_path

        if findings_with_path:
            logger.info(f"[Verification] 优先处理 {len(findings_with_path)} 个有明确文件路径的发现")
        if findings_without_path:
            logger.info(f"[Verification] 还有 {len(findings_without_path)} 个发现需要自行定位文件")

        # 强制上限：只验证候选种子的前 8 条
        findings_to_verify = findings_to_verify[:8]

        if not findings_to_verify:
            note = "跳过验证：本次 bootstrap_findings（候选种子）为空。"
            logger.info(f"[Verification] {note}")
            await self.emit_event("info", note)
            self.record_work(note)
            duration_ms = int((time.time() - start_time) * 1000)
            handoff = self.create_handoff(
                to_agent="orchestrator",
                summary=note,
                key_findings=[],
                context_data={
                    "skipped": True,
                    "reason": "no_bootstrap_candidates",
                    "verified_count": 0,
                },
            )
            return AgentResult(
                success=True,
                data={"findings": [], "verified_count": 0, "note": note},
                iterations=0,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
                handoff=handoff,
            )
        
        # 数量已在上面强制限制为 <= 8
        
        await self.emit_event(
            "info",
            f"开始验证 {len(findings_to_verify)} 个发现"
        )
        
        # 🔥 记录工作开始
        self.record_work(f"开始验证 {len(findings_to_verify)} 个漏洞发现")
        
        # 🔥 构建包含交接上下文的初始消息
        handoff_context = self.get_handoff_context()
        
        findings_summary = []
        for i, f in enumerate(findings_to_verify):
            # 🔥 FIX: 正确处理 file_path 格式，可能包含行号 (如 "app.py:36")
            file_path = f.get('file_path', 'unknown')
            line_start = f.get('line_start', 0)

            # 如果 file_path 已包含行号，提取出来
            if isinstance(file_path, str) and ':' in file_path:
                parts = file_path.split(':', 1)
                if len(parts) == 2 and parts[1].split()[0].isdigit():
                    file_path = parts[0]
                    try:
                        line_start = int(parts[1].split()[0])
                    except ValueError:
                        pass

        findings_summary.append(f"""
### 发现 {i+1}: {f.get('title', 'Unknown')}
- 类型: {f.get('vulnerability_type', 'unknown')}
- 严重度: {f.get('severity', 'medium')}
- 文件: {file_path} (行 {line_start})
- 代码:
```
{f.get('code_snippet', 'N/A')[:500]}
```
- 描述: {f.get('description', 'N/A')[:300]}
""")

        # 🔥 项目级 Markdown 长期记忆（无需 RAG/Embedding）
        memory_block = ""
        markdown_memory = config.get("markdown_memory") if isinstance(config, dict) else None
        if isinstance(markdown_memory, dict):
            shared_mem = str(markdown_memory.get("shared") or "").strip()
            agent_mem = str(markdown_memory.get("verification") or "").strip()
            skills_mem = str(markdown_memory.get("skills") or "").strip()
            if shared_mem or agent_mem or skills_mem:
                memory_block = f"""## 🧠 项目长期记忆（Markdown，无 RAG）
### shared.md（节选）
{shared_mem or "(空)"}

### verification.md（节选）
{agent_mem or "(空)"}

### skills.md（规范摘要）
{skills_mem or "(空)"}
"""
        
        initial_message = f"""请验证以下 {len(findings_to_verify)} 个安全发现。

{handoff_context if handoff_context else ''}

{memory_block if memory_block else ''}

## 待验证发现
{''.join(findings_summary)}

## ⚠️ 重要验证指南
1. **直接使用上面列出的文件路径** - 不要猜测或搜索其他路径
2. **如果文件路径包含冒号和行号** (如 "app.py:36"), 请提取文件名 "app.py" 并使用 read_file 读取
3. **先读取文件内容，再判断漏洞是否存在**
4. **不要假设文件在子目录中** - 使用发现中提供的精确路径

## 验证要求
- 验证级别: analysis_with_poc_plan（分析 + 非武器化 PoC 思路）

## 可用工具
{self.get_tools_description()}

请开始验证。对于每个发现：
1. 首先使用 read_file 读取发现中指定的文件（使用精确路径）
2. 分析代码上下文
3. 判断是否为真实漏洞
{f"特别注意 Analysis Agent 提到的关注点。" if handoff_context else ""}"""

        # 🔥 Tool-first 门禁提示：第一轮必须 Action（避免模型直接 Final Answer 触发拒绝/兜底）
        initial_message += """

## ✅ 门禁（必须遵守）
- **第一轮必须输出 Action**（优先 `read_file`，必要时可用 `search_code`），不允许第一轮直接输出 Final Answer。
- **仅验证上述待验证发现列表**（来源：bootstrap_findings 候选种子，最多 8 条），不得新增清单外发现。
"""

        # 初始化对话历史
        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": initial_message},
        ]
        
        self._steps = []
        final_result = None
        schema_retry_count = 0
        drift_retry_count = 0
        max_schema_retry = 2
        max_drift_retry = 2
        forced_min_tool_done = False  # 🔥 防死循环：首次“无工具直接 Final Answer”时由系统自动执行一次最小验证

        await self.emit_thinking("🔐 Verification Agent 启动，LLM 开始自主验证漏洞...")
        
        try:
            for iteration in range(self.config.max_iterations):
                if self.is_cancelled:
                    break
                
                self._iteration = iteration + 1
                
                # 🔥 再次检查取消标志（在LLM调用之前）
                if self.is_cancelled:
                    await self.emit_thinking("🛑 任务已取消，停止执行")
                    break
                
                # 调用 LLM 进行思考和决策（流式输出）
                try:
                    llm_output, tokens_this_round = await self.stream_llm_call(
                        self._conversation_history,
                        # 🔥 不传递 temperature 和 max_tokens，使用用户配置
                    )
                except asyncio.CancelledError:
                    logger.info(f"[{self.name}] LLM call cancelled")
                    break
                
                self._total_tokens += tokens_this_round

                # 🔥 Handle empty LLM response to prevent loops
                if not llm_output or not llm_output.strip():
                    logger.warning(f"[{self.name}] Empty LLM response in iteration {self._iteration}")
                    await self.emit_llm_decision("收到空响应", "LLM 返回内容为空，尝试重试通过提示")
                    self._conversation_history.append({
                        "role": "user",
                        "content": "Received empty response. Please output your Thought and Action.",
                    })
                    continue

                # 解析 LLM 响应
                step = self._parse_llm_response(llm_output)
                self._steps.append(step)

                if self._contains_interactive_drift(llm_output):
                    drift_retry_count += 1
                    await self.emit_thinking("⚠️ 检测到交互漂移，已自动纠偏继续执行。")
                    if drift_retry_count > max_drift_retry:
                        final_result = self._repair_final_answer(
                            {"findings": findings_to_verify},
                            findings_to_verify,
                            verification_level,
                        )
                        await self.emit_llm_decision("强制收敛", "交互漂移超过阈值，使用自动修复结果收敛")
                        break
                    self._conversation_history.append({
                        "role": "user",
                        "content": (
                            "不要向用户提问或要求选择下一步。请直接继续验证流程并输出结构化结果。"
                            "若信息不足，请采用默认策略补齐字段并推进。"
                        ),
                    })
                    continue
                
                # 🔥 发射 LLM 思考内容事件 - 展示验证的思考过程
                if step.thought:
                    await self.emit_llm_thought(step.thought, iteration + 1)
                
                # 添加 LLM 响应到历史
                self._conversation_history.append({
                    "role": "assistant",
                    "content": llm_output,
                })
                
                # 检查是否完成
                if step.is_final:
                    # 🔥 强制检查：必须至少调用过一次工具才能完成
                    if self._tool_calls == 0:
                        logger.warning(
                            f"[{self.name}] LLM tried to finish without any tool calls! Forcing tool usage."
                        )

                        # 🔥 兜底策略：首次触发时自动执行一次最小 read_file 验证，避免模型持续 Final Answer 导致死循环
                        if not forced_min_tool_done:
                            forced_min_tool_done = True
                            await self.emit_thinking("⚠️ 拒绝过早完成：系统将自动执行一次 read_file 获取证据")

                            target = findings_to_verify[0] if findings_to_verify else {}
                            file_path = str(target.get("file_path") or "").strip()
                            line_start = target.get("line_start") or 1

                            # 兼容 file_path 形如 "a.py:36"
                            if file_path and ":" in file_path:
                                parts = file_path.split(":", 1)
                                if len(parts) == 2 and parts[1].split()[0].isdigit():
                                    file_path = parts[0].strip()
                                    try:
                                        line_start = int(parts[1].split()[0])
                                    except Exception:
                                        line_start = target.get("line_start") or 1

                            try:
                                line_start_int = int(line_start) if line_start is not None else 1
                            except Exception:
                                line_start_int = 1

                            start_line = max(1, line_start_int - 20)
                            end_line = line_start_int + 80

                            if "read_file" in self.tools and file_path:
                                observation = await self.execute_tool(
                                    "read_file",
                                    {
                                        "file_path": file_path,
                                        "start_line": start_line,
                                        "end_line": end_line,
                                        "max_lines": 200,
                                    },
                                )
                            else:
                                observation = (
                                    "⚠️ 系统无法自动执行 read_file（缺少工具或 file_path 为空）。"
                                    "请改用 search_code/extract_function 手动验证。"
                                )

                            await self.emit_llm_observation(observation)
                            self._conversation_history.append(
                                {"role": "user", "content": f"Observation:\n{observation}"}
                            )
                            self._conversation_history.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "你之前尝试在没有任何工具证据的情况下直接输出 Final Answer。"
                                        "系统已自动执行了一次 read_file 并给出 Observation。"
                                        "现在请基于 Observation 继续：输出 Thought + Action（继续补充证据），"
                                        "或在证据充分时再输出 Final Answer。"
                                    ),
                                }
                            )
                            continue

                        # 兜底已执行但仍无工具调用（极端情况），继续强制提示模型调用工具
                        await self.emit_thinking("⚠️ 拒绝过早完成：必须先使用工具验证漏洞")
                        self._conversation_history.append(
                            {
                                "role": "user",
                                "content": (
                                    "⚠️ **系统拒绝**: 你必须先使用工具验证漏洞！\n\n"
                                    "不允许在没有调用任何工具的情况下直接输出 Final Answer。\n\n"
                                    "请立即使用以下工具之一进行验证：\n"
                                    "1. `read_file` - 读取漏洞所在文件的代码\n"
                                    "2. `extract_function` - 提取目标函数进行分析\n"
                                    "3. `search_code` - 搜索关键字定位证据\n\n"
                                    "现在请输出 Thought 和 Action，开始验证第一个漏洞。"
                                ),
                            }
                        )
                        continue

                    if not isinstance(step.final_answer, dict):
                        self._conversation_history.append({
                            "role": "user",
                            "content": "Final Answer 不是合法 JSON 对象。请严格按约定 JSON 结构重新输出。",
                        })
                        continue

                    repaired_answer = self._repair_final_answer(
                        step.final_answer,
                        findings_to_verify,
                        verification_level,
                    )
                    schema_ok, schema_error = self._validate_final_answer_schema(repaired_answer)
                    if not schema_ok:
                        schema_retry_count += 1
                        await self.emit_thinking(
                            f"⚠️ Final Answer 自动修复后仍不完整（第 {schema_retry_count} 次）: {schema_error}"
                        )
                        if schema_retry_count > max_schema_retry:
                            final_result = self._repair_final_answer(
                                {"findings": findings_to_verify},
                                findings_to_verify,
                                verification_level,
                            )
                            await self.emit_llm_decision("强制收敛", "结构化重试超过阈值，使用自动修复结果")
                            break
                        self._conversation_history.append({
                            "role": "user",
                            "content": (
                                "请重新输出 Final Answer。保持 JSON 完整并包含必要字段。"
                                f"当前错误: {schema_error}"
                            ),
                        })
                        continue

                    await self.emit_llm_decision("完成漏洞验证", "LLM 判断验证已充分")
                    final_result = repaired_answer

                    # 🔥 实时推送已验证漏洞事件（用于前端“实时漏洞报告”）
                    # 说明：此处的 finding_id 是事件 id，不等于最终入库的 AgentFinding.id。
                    try:
                        if isinstance(final_result, dict) and isinstance(final_result.get("findings"), list):
                            for item in final_result["findings"]:
                                if not isinstance(item, dict):
                                    continue
                                verdict = item.get("verdict") or item.get("authenticity")
                                verdict = str(verdict or "").strip().lower()
                                if verdict not in {"confirmed", "likely", "false_positive"}:
                                    verdict = "likely"

                                if verdict == "false_positive":
                                    continue

                                await self.emit_finding(
                                    title=str(item.get("title") or "已验证漏洞"),
                                    severity=str(item.get("severity") or "medium"),
                                    vuln_type=str(item.get("vulnerability_type") or "unknown"),
                                    file_path=str(item.get("file_path") or ""),
                                    line_start=item.get("line_start"),
                                    is_verified=True,
                                )
                    except Exception as emit_error:
                        logger.warning(
                            "[%s] Failed to emit finding_verified events: %s",
                            self.name,
                            emit_error,
                        )
                    
                    # 🔥 记录洞察和工作
                    if final_result and "findings" in final_result:
                        verified_count = len([f for f in final_result["findings"] if f.get("is_verified")])
                        fp_count = len([f for f in final_result["findings"] if f.get("verdict") == "false_positive"])
                        self.add_insight(f"验证了 {len(final_result['findings'])} 个发现，{verified_count} 个确认，{fp_count} 个误报")
                        self.record_work(f"完成漏洞验证: {verified_count} 个确认, {fp_count} 个误报")
                    
                    await self.emit_llm_complete(
                        f"验证完成",
                        self._total_tokens
                    )
                    break
                
                # 执行工具
                if step.action:
                    # 🔥 发射 LLM 动作决策事件
                    await self.emit_llm_action(step.action, step.action_input or {})
                    
                    start_tool_time = time.time()
                    
                    # 🔥 智能循环检测: 追踪重复调用 (无论成功与否)
                    tool_call_key = f"{step.action}:{json.dumps(step.action_input or {}, sort_keys=True)}"
                    
                    if not hasattr(self, '_tool_call_counts'):
                        self._tool_call_counts = {}
                    
                    self._tool_call_counts[tool_call_key] = self._tool_call_counts.get(tool_call_key, 0) + 1
                    
                    # 如果同一操作重复尝试超过3次，强制干预
                    if self._tool_call_counts[tool_call_key] > 3:
                        logger.warning(f"[{self.name}] Detected repetitive tool call loop: {tool_call_key}")
                        observation = (
                            f"⚠️ **系统干预**: 你已经使用完全相同的参数调用了工具 '{step.action}' 超过3次。\n"
                            "请**不要**重复尝试相同的操作。这是无效的。\n"
                            "请尝试：\n"
                            "1. 修改参数 (例如改变 input payload)\n"
                            # "2. 使用不同的工具 (例如从 sandbox_exec 换到 php_test)\n"
                            "2. 如果之前的尝试都失败了，请尝试 analyze_file 重新分析代码\n"
                            "3. 如果无法验证，请输出 Final Answer 并标记为 uncertain"
                        )
                        
                        # 模拟观察结果，跳过实际执行
                        step.observation = observation
                        await self.emit_llm_observation(observation)
                        self._conversation_history.append({
                            "role": "user",
                            "content": f"Observation:\n{observation}",
                        })
                        continue

                    # 🔥 循环检测：追踪工具调用失败历史 (保留原有逻辑用于错误追踪)
                    if not hasattr(self, '_failed_tool_calls'):
                        self._failed_tool_calls = {}
                    
                    observation = await self.execute_tool(
                        step.action,
                        step.action_input or {}
                    )
                    
                    # 🔥 检测工具调用失败并追踪
                    is_tool_error = (
                        "失败" in observation or 
                        "错误" in observation or 
                        "不存在" in observation or
                        "文件过大" in observation or
                        "Error" in observation
                    )
                    
                    if is_tool_error:
                        self._failed_tool_calls[tool_call_key] = self._failed_tool_calls.get(tool_call_key, 0) + 1
                        fail_count = self._failed_tool_calls[tool_call_key]
                        
                        # 🔥 如果同一调用连续失败3次，添加强制跳过提示
                        if fail_count >= 3:
                            logger.warning(f"[{self.name}] Tool call failed {fail_count} times: {tool_call_key}")
                            observation += f"\n\n⚠️ **系统提示**: 此工具调用已连续失败 {fail_count} 次。请：\n"
                            observation += "1. 尝试使用不同的参数（如指定较小的行范围）\n"
                            observation += "2. 使用 search_code 工具定位关键代码片段\n"
                            observation += "3. 跳过此发现的验证，继续验证其他发现\n"
                            observation += "4. 如果已有足够验证结果，直接输出 Final Answer"
                            
                            # 重置计数器
                            self._failed_tool_calls[tool_call_key] = 0
                    else:
                        # 成功调用，重置失败计数
                        if tool_call_key in self._failed_tool_calls:
                            del self._failed_tool_calls[tool_call_key]

                    # 🔥 工具执行后检查取消状态
                    if self.is_cancelled:
                        logger.info(f"[{self.name}] Cancelled after tool execution")
                        break

                    step.observation = observation
                    
                    # 🔥 发射 LLM 观察事件
                    await self.emit_llm_observation(observation)
                    
                    # 添加观察结果到历史
                    self._conversation_history.append({
                        "role": "user",
                        "content": f"Observation:\n{observation}",
                    })
                else:
                    # LLM 没有选择工具，提示它继续
                    await self.emit_llm_decision("继续验证", "LLM 需要更多验证")
                    self._conversation_history.append({
                        "role": "user",
                        "content": "请继续验证。你输出了 Thought 但没有输出 Action。请**立即**选择一个工具执行，或者如果验证完成，输出 Final Answer 汇总所有验证结果。",
                    })
            
            # 处理结果
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 🔥 如果被取消，返回取消结果
            if self.is_cancelled:
                await self.emit_event(
                    "info",
                    f"🛑 Verification Agent 已取消: {self._iteration} 轮迭代"
                )
                return AgentResult(
                    success=False,
                    error="任务已取消",
                    data={"findings": findings_to_verify},
                    iterations=self._iteration,
                    tool_calls=self._tool_calls,
                    tokens_used=self._total_tokens,
                    duration_ms=duration_ms,
                )
            
            # 处理最终结果
            verified_findings = []

            # 🔥 Robustness: If LLM returns empty findings but we had input, fallback to original
            llm_findings = []
            if final_result and "findings" in final_result:
                llm_findings = final_result["findings"]

            if not llm_findings and findings_to_verify:
                logger.warning(f"[{self.name}] LLM returned empty findings despite {len(findings_to_verify)} inputs. Falling back to originals.")
                # Fallback to logic below (else branch)
                final_result = None

            if final_result and "findings" in final_result:
                # 🔥 DEBUG: Log what LLM returned for verdict diagnosis
                verdicts_debug = [(f.get("file_path", "?"), f.get("verdict"), f.get("confidence")) for f in final_result["findings"]]
                logger.info(f"[{self.name}] LLM returned verdicts: {verdicts_debug}")

                for f in final_result["findings"]:
                    # 🔥 FIX: Normalize verdict - handle missing/empty verdict
                    verdict = f.get("verdict")
                    if not verdict or verdict not in ["confirmed", "likely", "false_positive"]:
                        # Try to infer verdict from other fields
                        if f.get("is_verified") is True:
                            verdict = "confirmed"
                        elif f.get("confidence", 0) >= 0.8:
                            verdict = "likely"
                        elif f.get("confidence", 0) <= 0.3:
                            verdict = "false_positive"
                        else:
                            verdict = "uncertain"
                        logger.warning(f"[{self.name}] Missing/invalid verdict for {f.get('file_path', '?')}, inferred as: {verdict}")

                    reachability = f.get("reachability")
                    if reachability not in ["reachable", "likely_reachable", "unreachable"]:
                        if verdict == "confirmed":
                            reachability = "reachable"
                        elif verdict == "likely":
                            reachability = "likely_reachable"
                        else:
                            reachability = "unreachable"

                    evidence = (
                        f.get("verification_details")
                        or f.get("verification_evidence")
                        or f.get("evidence")
                    )

                    verified = {
                        **f,
                        "verdict": verdict,  # 🔥 Ensure verdict is set
                        "authenticity": verdict,
                        "reachability": reachability,
                        "is_verified": verdict == "confirmed" or (
                            verdict == "likely" and f.get("confidence", 0) >= 0.8
                        ),
                        "verification_evidence": evidence,
                        "verification_details": evidence,
                        "line_end": f.get("line_end") or f.get("line_start"),
                        "verified_at": datetime.now(timezone.utc).isoformat() if verdict in ["confirmed", "likely"] else None,
                    }

                    suggestion = (
                        verified.get("suggestion")
                        or verified.get("recommendation")
                        or self._get_recommendation(f.get("vulnerability_type", ""))
                    )
                    verified["suggestion"] = suggestion
                    verified["recommendation"] = suggestion
                    verified["fix_code"] = verified.get("fix_code") or self._build_default_fix_code(verified)

                    allow_poc = verdict in {"confirmed", "likely"}
                    if allow_poc and not verified.get("poc"):
                        verified["poc"] = self._build_default_poc_plan(verified)
                    if not allow_poc:
                        verified.pop("poc", None)
                        verified["poc_code"] = None
                        verified["poc_description"] = None
                        verified["poc_steps"] = None

                    verified_findings.append(verified)
            else:
                # 如果没有最终结果，使用原始发现
                for f in findings_to_verify:
                    suggestion = self._get_recommendation(f.get("vulnerability_type", ""))
                    verified_findings.append({
                        **f,
                        "verdict": "likely",
                        "confidence": 0.6,
                        "is_verified": True,
                        "authenticity": "likely",
                        "reachability": "likely_reachable",
                        "verification_details": "模型未返回完整结果，系统已自动生成保守验证结论。",
                        "verification_evidence": "模型未返回完整结果，系统已自动生成保守验证结论。",
                        "suggestion": suggestion,
                        "recommendation": suggestion,
                        "fix_code": self._build_default_fix_code(f),
                        "poc": None,
                        "poc_code": None,
                        "poc_description": None,
                        "poc_steps": None,
                    })
            
            # 统计
            confirmed_count = len([f for f in verified_findings if f.get("verdict") == "confirmed"])
            likely_count = len([f for f in verified_findings if f.get("verdict") == "likely"])
            false_positive_count = len([f for f in verified_findings if f.get("verdict") == "false_positive"])

            await self.emit_event(
                "info",
                f"Verification Agent 完成: {confirmed_count} 确认, {likely_count} 可能, {false_positive_count} 误报"
            )

            # 🔥 CRITICAL: Log final findings count before returning
            logger.info(f"[{self.name}] Returning {len(verified_findings)} verified findings")

            # 🔥 创建 TaskHandoff - 记录验证结果，供 Orchestrator 汇总
            handoff = self._create_verification_handoff(
                verified_findings, confirmed_count, likely_count, false_positive_count
            )

            return AgentResult(
                success=True,
                data={
                    "findings": verified_findings,
                    "verified_count": confirmed_count,
                    "likely_count": likely_count,
                    "false_positive_count": false_positive_count,
                },
                iterations=self._iteration,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
                handoff=handoff,  # 🔥 添加 handoff
            )
            
        except Exception as e:
            logger.error(f"Verification Agent failed: {e}", exc_info=True)
            return AgentResult(success=False, error=str(e))
    
    def _get_recommendation(self, vuln_type: str) -> str:
        """获取修复建议"""
        recommendations = {
            "sql_injection": "使用参数化查询或 ORM，避免字符串拼接构造 SQL",
            "xss": "对用户输入进行 HTML 转义，使用 CSP，避免 innerHTML",
            "command_injection": "避免使用 shell=True，使用参数列表传递命令",
            "path_traversal": "验证和规范化路径，使用白名单，避免直接使用用户输入",
            "ssrf": "验证和限制目标 URL，使用白名单，禁止内网访问",
            "deserialization": "避免反序列化不可信数据，使用 JSON 替代 pickle/yaml",
            "hardcoded_secret": "使用环境变量或密钥管理服务存储敏感信息",
            "weak_crypto": "使用强加密算法（AES-256, SHA-256+），避免 MD5/SHA1",
        }
        return recommendations.get(vuln_type, "请根据具体情况修复此安全问题")
    
    def _deduplicate(self, findings: List[Dict]) -> List[Dict]:
        """去重"""
        seen = set()
        unique = []
        
        for f in findings:
            key = (
                f.get("file_path", ""),
                f.get("line_start", 0),
                f.get("vulnerability_type", ""),
            )
            
            if key not in seen:
                seen.add(key)
                unique.append(f)
        
        return unique
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self._conversation_history

    def get_steps(self) -> List[VerificationStep]:
        """获取执行步骤"""
        return self._steps

    def _create_verification_handoff(
        self,
        verified_findings: List[Dict[str, Any]],
        confirmed_count: int,
        likely_count: int,
        false_positive_count: int,
    ) -> TaskHandoff:
        """
        创建 Verification Agent 的任务交接信息

        Args:
            verified_findings: 验证后的发现列表
            confirmed_count: 确认的漏洞数量
            likely_count: 可能的漏洞数量
            false_positive_count: 误报数量

        Returns:
            TaskHandoff 对象，供 Orchestrator 汇总
        """
        # 按验证结果分类
        confirmed = [f for f in verified_findings if f.get("verdict") == "confirmed"]
        likely = [f for f in verified_findings if f.get("verdict") == "likely"]
        false_positives = [f for f in verified_findings if f.get("verdict") == "false_positive"]

        # 提取关键发现（已确认的高危漏洞）
        key_findings = []
        for f in confirmed:
            if f.get("severity") in ["critical", "high"]:
                key_findings.append(f)
        # 如果高危不够，添加其他确认的漏洞
        if len(key_findings) < 10:
            for f in confirmed:
                if f not in key_findings:
                    key_findings.append(f)
                    if len(key_findings) >= 10:
                        break

        # 构建建议行动 - 修复建议
        suggested_actions = []
        for f in confirmed[:10]:
            suggestion = f.get("suggestion", "") or f.get("recommendation", "")
            suggested_actions.append({
                "action": "fix_vulnerability",
                "target": f.get("file_path", ""),
                "line": f.get("line_start", 0),
                "vulnerability_type": f.get("vulnerability_type", "unknown"),
                "severity": f.get("severity", "medium"),
                "recommendation": suggestion[:200] if suggestion else "请根据漏洞类型进行修复"
            })

        # 构建洞察
        insights = [
            f"验证完成: {confirmed_count}个确认, {likely_count}个可能, {false_positive_count}个误报",
            f"验证准确率: {(confirmed_count + likely_count) / len(verified_findings) * 100:.1f}%" if verified_findings else "无数据",
        ]

        # 统计各类型漏洞
        type_counts = {}
        for f in confirmed + likely:
            vtype = f.get("vulnerability_type", "unknown")
            type_counts[vtype] = type_counts.get(vtype, 0) + 1
        if type_counts:
            top_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            insights.append(f"主要漏洞类型: {', '.join([f'{t}({c})' for t, c in top_types])}")

        # 需要关注的文件（有确认漏洞的文件）
        attention_points = []
        files_with_confirmed = {}
        for f in confirmed:
            fp = f.get("file_path", "")
            if fp:
                files_with_confirmed[fp] = files_with_confirmed.get(fp, 0) + 1
        for fp, count in sorted(files_with_confirmed.items(), key=lambda x: x[1], reverse=True)[:10]:
            attention_points.append(f"{fp} ({count}个确认漏洞)")

        # 优先修复的区域
        priority_areas = []
        for f in confirmed:
            if f.get("severity") in ["critical", "high"]:
                fp = f.get("file_path", "")
                if fp and fp not in priority_areas:
                    priority_areas.append(fp)

        # 上下文数据
        context_data = {
            "confirmed_count": confirmed_count,
            "likely_count": likely_count,
            "false_positive_count": false_positive_count,
            "vulnerability_types": type_counts,
            "files_with_confirmed": files_with_confirmed,
            "poc_generated": len([f for f in verified_findings if f.get("poc_code")]),
        }

        # 构建摘要
        summary = f"验证完成: {confirmed_count}个确认漏洞, {likely_count}个可能漏洞"
        if confirmed_count > 0:
            high_count = len([f for f in confirmed if f.get("severity") in ["critical", "high"]])
            if high_count > 0:
                summary += f", 其中{high_count}个高危"

        return self.create_handoff(
            to_agent="orchestrator",
            summary=summary,
            key_findings=key_findings,
            suggested_actions=suggested_actions,
            attention_points=attention_points,
            priority_areas=priority_areas,
            context_data=context_data,
        )
