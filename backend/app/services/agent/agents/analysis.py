"""
Analysis Agent (漏洞分析层) - LLM 驱动版

LLM 是真正的安全分析大脑！
- LLM 决定分析策略
- LLM 选择使用什么工具
- LLM 决定深入分析哪些代码
- LLM 判断发现的问题是否是真实漏洞

类型: ReAct (真正的!)
"""

import asyncio
import json
import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern, TaskHandoff
from .react_parser import parse_react_response
from ..json_parser import AgentJsonParser
from ..prompts import CORE_SECURITY_PRINCIPLES, VULNERABILITY_PRIORITIES

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """你是漏洞分析 Agent，负责自主发现高价值安全问题并输出可验证发现。

## 执行原则
1. 禁止向用户追问“下一步怎么选/是否继续”，必须自主推进。
2. 只能调用运行时提供的工具白名单，不得编造工具。
3. 先覆盖高风险候选（bootstrap/high-risk），再扩展全局分析。
4. 没有证据的推测不得作为最终漏洞输出。
5. 优先分析 `target_files` 范围内文件；若提供 `bootstrap_findings`，必须优先处理。
6. 不允许无效循环：同一工具同一参数连续失败后必须更换策略或结束。
7. Final Answer 必须是结构化 JSON，且 findings 不得缺失关键定位字段。
8. **语言要求**：Final Answer 中 title/description/suggestion/fix_description/verification_evidence/poc_plan 必须使用简体中文，禁止输出英文段落。
9. **工具优先门禁（强约束）**：在输出任何结论或 Final Answer 前，必须至少执行一次“代码证据”工具调用（最低要求：至少一次 `read_file`；并建议再执行一次 `search_code/pattern_match/opengrep_scan` 之一）。结论必须引用 Observation 证据，禁止无证据宣称“已阅读/已验证”。
10. **首轮强约束**：第一轮必须输出 Action（优先 `read_file` 或 `search_code`），不允许第一轮直接输出 Final Answer。
11. **标题强约束**：每条 finding 的 `title` 必须是中文四段式：`路径+函数+缺陷名称+可能造成的危害`。示例：`src/time64.c中sprintf函数缓冲区溢出漏洞，可能造成的危害：可导致内存破坏与进程崩溃`。
12. **禁止标题漂移**：不得输出英文标题、不得只写漏洞类型；函数名必须可解析，无法定位函数的候选不得进入最终可验证结果。
13. **输出格式约束**：禁止使用 `## Action`/`## Action Input` 标题样式，必须使用 `Action:`/`Action Input:` 行格式。

## 工作流
1. 先读取关键文件/候选位置，确认上下文。
2. 使用可用扫描工具与数据流分析形成证据链。
3. 输出结构化 findings，并标记 `needs_verification=true` 供验证阶段处理。

## 输出格式
Thought: ...
Action: ...
Action Input: {...}

最终：
Thought: ...
Final Answer: {"findings":[...], "summary":"..."}

## finding 最低字段
- vulnerability_type
- severity
- title
- description
- file_path
- function_name
- line_start
- code_snippet
- confidence
- needs_verification"""

@dataclass
class AnalysisStep:
    """分析步骤"""
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[Dict] = None


class AnalysisAgent(BaseAgent):
    """
    漏洞分析 Agent - LLM 驱动版
    
    LLM 全程参与，自主决定：
    1. 分析什么
    2. 使用什么工具
    3. 深入哪些代码
    4. 报告什么发现
    """
    
    def __init__(
        self,
        llm_service,
        tools: Dict[str, Any],
        event_emitter=None,
    ):
        # 组合增强的系统提示词，注入核心安全原则和漏洞优先级
        tool_whitelist = ", ".join(sorted(tools.keys())) if tools else "无"
        full_system_prompt = (
            f"{ANALYSIS_SYSTEM_PROMPT}\n\n"
            f"## 当前工具白名单\n{tool_whitelist}\n"
            f"只能调用以上工具。\n\n"
            f"{CORE_SECURITY_PRINCIPLES}\n\n{VULNERABILITY_PRIORITIES}"
        )
        
        config = AgentConfig(
            name="Analysis",
            agent_type=AgentType.ANALYSIS,
            pattern=AgentPattern.REACT,
            max_iterations=30,
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)
        
        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[AnalysisStep] = []
    

    
    def _parse_llm_response(self, response: str) -> AnalysisStep:
        """解析 LLM 响应（共享 ReAct 解析器）"""
        parsed = parse_react_response(
            response,
            final_default={"findings": [], "raw_answer": (response or "").strip()},
            action_input_raw_key="raw_input",
        )
        step = AnalysisStep(
            thought=parsed.thought or "",
            action=parsed.action,
            action_input=parsed.action_input or {},
            is_final=bool(parsed.is_final),
            final_answer=parsed.final_answer if isinstance(parsed.final_answer, dict) else None,
        )

        if step.is_final and isinstance(step.final_answer, dict) and "findings" in step.final_answer:
            step.final_answer["findings"] = [
                f for f in step.final_answer["findings"]
                if isinstance(f, dict)
            ]
        return step
    

    
    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        执行漏洞分析 - LLM 全程参与！
        """
        import time
        start_time = time.time()
        
        project_info = input_data.get("project_info", {})
        config = input_data.get("config", {})
        plan = input_data.get("plan", {})
        previous_results = input_data.get("previous_results", {})
        task = input_data.get("task", "")
        task_context = input_data.get("task_context", "")
        
        # 🔥 处理交接信息
        handoff = input_data.get("handoff")
        if handoff:
            from .base import TaskHandoff
            if isinstance(handoff, dict):
                handoff = TaskHandoff.from_dict(handoff)
            self.receive_handoff(handoff)
        
        # 从 Recon 结果获取上下文
        recon_data = previous_results.get("recon", {})
        if isinstance(recon_data, dict) and "data" in recon_data:
            recon_data = recon_data["data"]
        
        tech_stack = recon_data.get("tech_stack", {})
        entry_points = recon_data.get("entry_points", [])
        high_risk_areas = recon_data.get("high_risk_areas", plan.get("high_risk_areas", []))
        initial_findings = recon_data.get("initial_findings", [])
        bootstrap_findings = previous_results.get("bootstrap_findings", [])
        if isinstance(bootstrap_findings, list):
            for bootstrap_item in bootstrap_findings[:20]:
                if isinstance(bootstrap_item, dict):
                    initial_findings.append(bootstrap_item)
        else:
            bootstrap_findings = []
        
        # 🔥 构建包含交接上下文的初始消息
        handoff_context = self.get_handoff_context()
        
        # 🔥 获取目标文件列表
        target_files = config.get("target_files", [])
        
        initial_message = f"""请开始对项目进行安全漏洞分析。

## 项目信息
- 名称: {project_info.get('name', 'unknown')}
- 语言: {tech_stack.get('languages', [])}
- 框架: {tech_stack.get('frameworks', [])}

"""

        # 🔥 项目级 Markdown 长期记忆（无需 RAG/Embedding）
        markdown_memory = config.get("markdown_memory") if isinstance(config, dict) else None
        if isinstance(markdown_memory, dict):
            shared_mem = str(markdown_memory.get("shared") or "").strip()
            agent_mem = str(markdown_memory.get("analysis") or "").strip()
            skills_mem = str(markdown_memory.get("skills") or "").strip()
            if shared_mem or agent_mem or skills_mem:
                initial_message += f"""## 🧠 项目长期记忆（Markdown，无 RAG）
### shared.md（节选）
{shared_mem or "(空)"}

### analysis.md（节选）
{agent_mem or "(空)"}

### skills.md（规范摘要）
{skills_mem or "(空)"}

"""
        # 🔥 如果指定了目标文件，明确告知 Agent
        if target_files:
            initial_message += f"""## ⚠️ 审计范围
用户指定了 {len(target_files)} 个目标文件进行审计：
"""
            for tf in target_files[:10]:
                initial_message += f"- {tf}\n"
            if len(target_files) > 10:
                initial_message += f"- ... 还有 {len(target_files) - 10} 个文件\n"
            initial_message += """
请直接分析这些指定的文件，不要分析其他文件。

"""
        
        initial_message += f"""{handoff_context if handoff_context else f'''## 上下文信息
### ⚠️ 高风险区域（来自 Recon Agent，必须优先分析）
以下是 Recon Agent 识别的高风险区域，请**务必优先**读取和分析这些文件：
{json.dumps(high_risk_areas[:20], ensure_ascii=False)}

**重要**: 请使用 read_file 工具读取上述高风险文件，不要假设文件路径或使用其他路径。

### 入口点 (前10个)
{json.dumps(entry_points[:10], ensure_ascii=False, indent=2)}

### 初步发现 (如果有)
{json.dumps(initial_findings[:5], ensure_ascii=False, indent=2) if initial_findings else "无"}'''}

## 任务
{task_context or task or '进行全面的安全漏洞分析，发现代码中的安全问题。'}

## 候选种子（bootstrap_findings，如有）
{json.dumps(bootstrap_findings[:10], ensure_ascii=False, indent=2) if bootstrap_findings else "无"}

## ⚠️ 分析策略要求
1. **首先**：优先处理候选种子（bootstrap_findings）与高风险文件
2. **然后**：分析这些文件中的安全问题
3. **最后**：如果需要，使用 smart_scan 或其他工具扩展分析

**禁止**：不要跳过高风险区域直接做全局扫描

## 目标漏洞类型
{config.get('target_vulnerabilities', ['all'])}

## 可用工具
{self.get_tools_description()}

请开始你的安全分析。**第一步必须输出 Action**（优先 `read_file` 或 `search_code`），不允许第一轮直接输出 Final Answer。首先读取高风险区域的文件，然后**立即**分析其中的安全问题（输出 Action）。"""
        
        # 🔥 记录工作开始
        self.record_work("开始安全漏洞分析")

        # 初始化对话历史
        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": initial_message},
        ]
        
        self._steps = []
        all_findings = []
        error_message = None  # 🔥 跟踪错误信息
        forced_min_tool_done = False  # 🔥 防死循环：首次“无工具直接 Final Answer”时由系统自动执行一次最小工具调用
        no_action_streak = 0
        degraded_reason: Optional[str] = None

        async def run_minimal_evidence_tool() -> str:
            """执行最小证据工具调用，避免无 Action 空转。"""
            file_path = ""
            line_start = 1

            if target_files and isinstance(target_files[0], str):
                file_path = target_files[0].strip()
                line_start = 1

            if (not file_path) and bootstrap_findings and isinstance(bootstrap_findings[0], dict):
                file_path = str(bootstrap_findings[0].get("file_path") or "").strip()
                line_start = bootstrap_findings[0].get("line_start") or 1

            if (not file_path) and high_risk_areas:
                first_area = str(high_risk_areas[0])
                if ":" in first_area:
                    area_path, rest = first_area.split(":", 1)
                    file_path = area_path.strip()
                    line_token = rest.strip().split()[0] if rest.strip() else ""
                    if line_token.isdigit():
                        line_start = int(line_token)

            if file_path and ":" in file_path:
                parts = file_path.split(":", 1)
                if len(parts) == 2 and parts[1].split()[0].isdigit():
                    file_path = parts[0].strip()
                    try:
                        line_start = int(parts[1].split()[0])
                    except Exception:
                        line_start = 1

            try:
                line_start_int = int(line_start) if line_start is not None else 1
            except Exception:
                line_start_int = 1

            start_line = max(1, line_start_int - 20)
            end_line = line_start_int + 80

            if "read_file" in self.tools and file_path:
                return await self.execute_tool(
                    "read_file",
                    {
                        "file_path": file_path,
                        "start_line": start_line,
                        "end_line": end_line,
                        "max_lines": 200,
                    },
                )
            if "list_files" in self.tools:
                return await self.execute_tool(
                    "list_files",
                    {
                        "directory": ".",
                        "recursive": False,
                        "max_files": 80,
                    },
                )
            return (
                "⚠️ 系统无法自动执行最小工具调用（缺少 read_file/list_files 或目标文件未知）。"
                "请改用 read_file/search_code 获取证据后再总结。"
            )

        await self.emit_thinking("🔬 Analysis Agent 启动，LLM 开始自主安全分析...")
        
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
                # 🔥 使用用户配置的 temperature 和 max_tokens
                try:
                    llm_output, tokens_this_round = await self.stream_llm_call(
                        self._conversation_history,
                        # 🔥 不传递 temperature 和 max_tokens，使用用户配置
                    )
                except asyncio.CancelledError:
                    logger.info(f"[{self.name}] LLM call cancelled")
                    break
                
                self._total_tokens += tokens_this_round

                # 🔥 Enhanced: Handle empty LLM response with better diagnostics
                if not llm_output or not llm_output.strip():
                    empty_retry_count = getattr(self, '_empty_retry_count', 0) + 1
                    self._empty_retry_count = empty_retry_count
                    
                    # 🔥 记录更详细的诊断信息
                    logger.warning(
                        f"[{self.name}] Empty LLM response in iteration {self._iteration} "
                        f"(retry {empty_retry_count}/3, tokens_this_round={tokens_this_round})"
                    )
                    
                    if empty_retry_count >= 3:
                        logger.error(f"[{self.name}] Too many empty responses, generating fallback result")
                        error_message = "连续收到空响应，使用回退结果"
                        await self.emit_event("warning", error_message)
                        # 🔥 不是直接 break，而是尝试生成一个回退结果
                        break
                    
                    # 🔥 更有针对性的重试提示
                    retry_prompt = f"""收到空响应。请根据以下格式输出你的思考和行动：

Thought: [你对当前安全分析情况的思考]
Action: [工具名称，如 read_file, search_code, pattern_match, opengrep_scan]
Action Input: {{"参数名": "参数值"}}

可用工具: {', '.join(self.tools.keys())}

如果你已完成分析，请输出：
Thought: [总结所有发现]
Final Answer: {{"findings": [...], "summary": "..."}}"""
                    
                    self._conversation_history.append({
                        "role": "user",
                        "content": retry_prompt,
                    })
                    continue
                
                # 重置空响应计数器
                self._empty_retry_count = 0

                # 解析 LLM 响应
                step = self._parse_llm_response(llm_output)
                self._steps.append(step)
                
                # 🔥 发射 LLM 思考内容事件 - 展示安全分析的思考过程
                if step.thought:
                    await self.emit_llm_thought(step.thought, iteration + 1)
                
                # 添加 LLM 响应到历史
                self._conversation_history.append({
                    "role": "assistant",
                    "content": llm_output,
                })
                if step.action or step.is_final:
                    no_action_streak = 0
                
                # 检查是否完成
                if step.is_final:
                    # 🔥 工具优先门禁：禁止在 0 tool_calls 的情况下直接 Final Answer
                    if self._tool_calls == 0:
                        logger.warning(
                            f"[{self.name}] LLM tried to finish without any tool calls! Forcing tool usage."
                        )

                        # 首次触发：系统自动执行一次最小 read_file/list_files，确保有 Observation 证据
                        if not forced_min_tool_done:
                            forced_min_tool_done = True
                            await self.emit_thinking("⚠️ 拒绝过早完成：系统将自动执行一次最小工具调用获取证据")
                            observation = await run_minimal_evidence_tool()

                            await self.emit_llm_observation(observation)
                            self._conversation_history.append(
                                {"role": "user", "content": f"Observation:\n{observation}"}
                            )
                            self._conversation_history.append(
                                {
                                    "role": "user",
                                    "content": (
                                        "你之前尝试在没有任何工具证据的情况下直接输出 Final Answer。"
                                        "系统已自动执行了一次最小工具调用并给出 Observation。"
                                        "现在请基于 Observation 继续：输出 Thought + Action（继续补充证据），"
                                        "或在证据充分时再输出 Final Answer。"
                                    ),
                                }
                            )
                            continue

                        # 已兜底过但仍无 tool_calls（极端情况）：允许收敛，避免空转
                        logger.warning(f"[{self.name}] Forced tool bootstrap already attempted; allowing finalization to avoid loops.")

                    await self.emit_llm_decision("完成安全分析", "LLM 判断分析已充分")
                    logger.info(f"[{self.name}] Received Final Answer: {step.final_answer}")
                    if step.final_answer and "findings" in step.final_answer:
                        all_findings = step.final_answer["findings"]
                        logger.info(f"[{self.name}] Final Answer contains {len(all_findings)} findings")
                        # 🔥 发射每个发现的事件（用于前端实时未验证列表）
                        # 限制数量避免日志风暴，但需要足够覆盖面来体现“实时发现”。
                        for finding in all_findings[:50]:
                            title_value = str(finding.get("title") or "Unknown")
                            await self.emit_finding(
                                title_value,
                                finding.get("severity", "medium"),
                                finding.get("vulnerability_type", "other"),
                                finding.get("file_path", ""),
                                finding.get("line_start"),
                                display_title=title_value,
                                cwe_id=(
                                    str(finding.get("cwe_id")).strip()
                                    if finding.get("cwe_id") is not None
                                    else None
                                ),
                                code_snippet=(
                                    str(finding.get("code_snippet"))
                                    if finding.get("code_snippet") is not None
                                    else None
                                ),
                                function_trigger_flow=(
                                    finding.get("function_trigger_flow")
                                    if isinstance(finding.get("function_trigger_flow"), list)
                                    else None
                                ),
                            )
                            # 🔥 记录洞察
                            self.add_insight(
                                f"发现 {finding.get('severity', 'medium')} 级别漏洞: {finding.get('title', 'Unknown')}"
                            )
                    else:
                        logger.warning(f"[{self.name}] Final Answer has no 'findings' key or is None: {step.final_answer}")
                    
                    # 🔥 记录工作完成
                    self.record_work(f"完成安全分析，发现 {len(all_findings)} 个潜在漏洞")
                    
                    await self.emit_llm_complete(
                        f"分析完成，发现 {len(all_findings)} 个潜在漏洞",
                        self._total_tokens
                    )
                    break
                
                # 执行工具
                if step.action:
                    # 🔥 发射 LLM 动作决策事件
                    await self.emit_llm_action(step.action, step.action_input or {})
                    
                    # 🔥 循环检测：追踪工具调用失败历史
                    tool_call_key = f"{step.action}:{json.dumps(step.action_input or {}, sort_keys=True)}"
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
                            observation += "3. 跳过此文件，继续分析其他文件\n"
                            observation += "4. 如果已有足够发现，直接输出 Final Answer"
                            
                            # 重置计数器但保留记录
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
                    no_action_streak += 1
                    await self.emit_llm_decision("继续分析", f"LLM 未输出 Action (streak={no_action_streak})")

                    if no_action_streak == 3:
                        self._conversation_history.append({
                            "role": "user",
                            "content": (
                                "你连续多轮没有输出可执行 Action。请严格按以下格式立即输出：\n"
                                "Thought: ...\nAction: <tool_name>\nAction Input: {...}\n"
                                "禁止使用 `## Action` 标题样式。"
                            ),
                        })
                    elif no_action_streak == 5:
                        await self.emit_thinking("⚠️ 检测到连续无 Action，系统自动执行最小证据工具以打破空转。")
                        observation = await run_minimal_evidence_tool()
                        await self.emit_llm_observation(observation)
                        self._conversation_history.append({
                            "role": "user",
                            "content": f"Observation:\n{observation}",
                        })
                        self._conversation_history.append({
                            "role": "user",
                            "content": (
                                "系统已自动补充证据。下一轮必须输出可执行 Action，"
                                "或在证据充分时输出 Final Answer。"
                            ),
                        })
                    elif no_action_streak >= 7:
                        degraded_reason = "analysis_stagnation"
                        await self.emit_event(
                            "warning",
                            "Analysis 连续无 Action，已触发有界收敛并降级结束。",
                            metadata={"degraded_reason": degraded_reason, "streak": no_action_streak},
                        )
                        break
                    else:
                        self._conversation_history.append({
                            "role": "user",
                            "content": "请继续分析。你输出了 Thought 但没有输出 Action。请**立即**选择一个工具执行，或者如果分析完成，输出 Final Answer 汇总所有发现。",
                        })
            
            # 🔥 如果循环结束但没有发现，强制 LLM 总结
            if not all_findings and not self.is_cancelled and not error_message and not degraded_reason:
                await self.emit_thinking("📝 分析阶段结束，正在生成漏洞总结...")
                
                # 添加强制总结的提示
                self._conversation_history.append({
                    "role": "user",
                    "content": """分析阶段已结束。请立即输出 Final Answer，总结你发现的所有安全问题。

即使没有发现严重漏洞，也请总结你的分析过程和观察到的潜在风险点。

请按以下 JSON 格式输出：
```json
{
    "findings": [
        {
            "vulnerability_type": "sql_injection|xss|command_injection|path_traversal|ssrf|hardcoded_secret|other",
            "severity": "critical|high|medium|low",
            "title": "漏洞标题",
            "description": "详细描述",
            "file_path": "文件路径",
            "line_start": 行号,
            "code_snippet": "相关代码片段",
            "suggestion": "修复建议"
        }
    ],
    "summary": "分析总结"
}
```

Final Answer:""",
                })
                
                try:
                    summary_output, _ = await self.stream_llm_call(
                        self._conversation_history,
                        # 🔥 不传递 temperature 和 max_tokens，使用用户配置
                    )
                    
                    if summary_output and summary_output.strip():
                        # 解析总结输出
                        import re
                        summary_text = summary_output.strip()
                        summary_text = re.sub(r'```json\s*', '', summary_text)
                        summary_text = re.sub(r'```\s*', '', summary_text)
                        parsed_result = AgentJsonParser.parse(
                            summary_text,
                            default={"findings": [], "summary": ""}
                        )
                        if "findings" in parsed_result:
                            all_findings = parsed_result["findings"]
                except Exception as e:
                    logger.warning(f"[{self.name}] Failed to generate summary: {e}")
            
            # 处理结果
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 🔥 如果被取消，返回取消结果
            if self.is_cancelled:
                await self.emit_event(
                    "info",
                    f"🛑 Analysis Agent 已取消: {len(all_findings)} 个发现, {self._iteration} 轮迭代"
                )
                return AgentResult(
                    success=False,
                    error="任务已取消",
                    data={
                        "findings": all_findings,
                        **({"degraded_reason": degraded_reason} if degraded_reason else {}),
                    },
                    iterations=self._iteration,
                    tool_calls=self._tool_calls,
                    tokens_used=self._total_tokens,
                    duration_ms=duration_ms,
                )
            
            # 🔥 如果有错误，返回失败结果
            if error_message:
                await self.emit_event(
                    "error",
                    f"❌ Analysis Agent 失败: {error_message}"
                )
                return AgentResult(
                    success=False,
                    error=error_message,
                    data={
                        "findings": all_findings,
                        **({"degraded_reason": degraded_reason} if degraded_reason else {}),
                    },
                    iterations=self._iteration,
                    tool_calls=self._tool_calls,
                    tokens_used=self._total_tokens,
                    duration_ms=duration_ms,
                )
            
            # 标准化发现
            logger.info(f"[{self.name}] Standardizing {len(all_findings)} findings")
            standardized_findings = []
            for finding in all_findings:
                # 确保 finding 是字典
                if not isinstance(finding, dict):
                    logger.warning(f"Skipping invalid finding (not a dict): {finding}")
                    continue
                    
                standardized = {
                    "vulnerability_type": finding.get("vulnerability_type", "other"),
                    "severity": finding.get("severity", "medium"),
                    "title": finding.get("title", "Unknown Finding"),
                    "description": finding.get("description", ""),
                    "file_path": finding.get("file_path", ""),
                    "line_start": finding.get("line_start") or finding.get("line", 0),
                    "code_snippet": finding.get("code_snippet", ""),
                    "source": finding.get("source", ""),
                    "sink": finding.get("sink", ""),
                    "suggestion": finding.get("suggestion", ""),
                    "confidence": finding.get("confidence", 0.7),
                    "needs_verification": finding.get("needs_verification", True),
                }
                standardized_findings.append(standardized)
            
            await self.emit_event(
                "info",
                f"Analysis Agent 完成: {len(standardized_findings)} 个发现, {self._iteration} 轮迭代, {self._tool_calls} 次工具调用"
            )

            # 🔥 CRITICAL: Log final findings count before returning
            logger.info(f"[{self.name}] Returning {len(standardized_findings)} standardized findings")

            # 🔥 创建 TaskHandoff - 传递给 Verification Agent
            handoff = self._create_analysis_handoff(standardized_findings)

            return AgentResult(
                success=True,
                data={
                    "findings": standardized_findings,
                    **({"degraded_reason": degraded_reason} if degraded_reason else {}),
                    "steps": [
                        {
                            "thought": s.thought,
                            "action": s.action,
                            "action_input": s.action_input,
                            "observation": s.observation[:500] if s.observation else None,
                        }
                        for s in self._steps
                    ],
                },
                iterations=self._iteration,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
                handoff=handoff,  # 🔥 添加 handoff
            )
            
        except Exception as e:
            logger.error(f"Analysis Agent failed: {e}", exc_info=True)
            return AgentResult(success=False, error=str(e))
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self._conversation_history

    def get_steps(self) -> List[AnalysisStep]:
        """获取执行步骤"""
        return self._steps

    def _create_analysis_handoff(self, findings: List[Dict[str, Any]]) -> TaskHandoff:
        """
        创建 Analysis Agent 的任务交接信息

        Args:
            findings: 分析发现的漏洞列表

        Returns:
            TaskHandoff 对象，供 Verification Agent 使用
        """
        # 按严重程度排序
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_findings = sorted(
            findings,
            key=lambda x: severity_order.get(x.get("severity", "low"), 3)
        )

        # 提取关键发现（优先高危漏洞）
        key_findings = sorted_findings[:15]

        # 构建建议行动 - 哪些漏洞需要优先验证
        suggested_actions = []
        for f in sorted_findings[:10]:
            suggested_actions.append({
                "action": "verify_vulnerability",
                "target": f.get("file_path", ""),
                "line": f.get("line_start", 0),
                "vulnerability_type": f.get("vulnerability_type", "unknown"),
                "severity": f.get("severity", "medium"),
                "priority": "high" if f.get("severity") in ["critical", "high"] else "normal",
                "reason": f.get("title", "需要验证")
            })

        # 统计漏洞类型和严重程度
        severity_counts = {}
        type_counts = {}
        for f in findings:
            sev = f.get("severity", "unknown")
            vtype = f.get("vulnerability_type", "unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            type_counts[vtype] = type_counts.get(vtype, 0) + 1

        # 构建洞察
        insights = [
            f"发现 {len(findings)} 个潜在漏洞需要验证",
            f"严重程度分布: Critical={severity_counts.get('critical', 0)}, "
            f"High={severity_counts.get('high', 0)}, "
            f"Medium={severity_counts.get('medium', 0)}, "
            f"Low={severity_counts.get('low', 0)}",
        ]

        # 最常见的漏洞类型
        if type_counts:
            top_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            insights.append(f"主要漏洞类型: {', '.join([f'{t}({c})' for t, c in top_types])}")

        # 需要关注的文件
        attention_points = []
        files_with_findings = {}
        for f in findings:
            fp = f.get("file_path", "")
            if fp:
                files_with_findings[fp] = files_with_findings.get(fp, 0) + 1

        for fp, count in sorted(files_with_findings.items(), key=lambda x: x[1], reverse=True)[:10]:
            attention_points.append(f"{fp} ({count}个漏洞)")

        # 优先验证的区域 - 高危漏洞所在文件
        priority_areas = []
        for f in sorted_findings[:10]:
            if f.get("severity") in ["critical", "high"]:
                fp = f.get("file_path", "")
                if fp and fp not in priority_areas:
                    priority_areas.append(fp)

        # 上下文数据
        context_data = {
            "severity_distribution": severity_counts,
            "vulnerability_types": type_counts,
            "files_with_findings": files_with_findings,
        }

        # 构建摘要
        high_count = severity_counts.get("critical", 0) + severity_counts.get("high", 0)
        summary = f"完成代码分析: 发现{len(findings)}个漏洞, 其中{high_count}个高危"

        return self.create_handoff(
            to_agent="verification",
            summary=summary,
            key_findings=key_findings,
            suggested_actions=suggested_actions,
            attention_points=attention_points,
            priority_areas=priority_areas,
            context_data=context_data,
        )
