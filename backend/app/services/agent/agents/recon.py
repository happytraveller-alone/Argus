"""
Recon Agent (信息收集层) - LLM 驱动版

LLM 是真正的大脑！
- LLM 决定收集什么信息
- LLM 决定使用哪个工具
- LLM 决定何时信息足够
- LLM 动态调整收集策略

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

logger = logging.getLogger(__name__)

WEB_FRAMEWORK_HINTS = {
    "react", "vue", "angular", "express", "django", "flask",
    "fastapi", "spring", "laravel", "rails", "next.js", "nuxt",
}
WEB_SIGNAL_HINTS = {
    "http", "https", "route", "router", "controller", "request",
    "response", "middleware", "template", "csrf", "session", "cookie",
    "rest", "graphql", "api",
}
WEB_VULNERABILITY_FOCUS_DEFAULT = [
    "sql_injection",
    "xss",
    "command_injection",
    "path_traversal",
    "ssrf",
    "idor",
    "auth_bypass",
    "csrf",
    "open_redirect",
    "ssti",
    "xxe",
    "deserialization",
]

RECON_SYSTEM_PROMPT = """你是侦察 Agent，负责收集后续分析所需的结构化安全上下文。

## 执行原则（强约束）
1. 必须输出 `Thought + Action + Action Input` 或 `Final Answer`。
2. 禁止向用户追问下一步，必须自主推进。
3. 只能调用运行时工具白名单，不得编造工具。
4. 只允许报告实际读取/检索到的文件和行号，禁止猜测。
5. 不允许连续两轮只输出空泛 Thought；每轮必须有明确推进动作或完成结论。
6. 若存在 `target_files`，优先且聚焦这些文件，避免无关目录遍历。
7. 若存在 `bootstrap_findings`，优先为其补齐上下文定位信息。
8. **语言要求**：Final Answer 中所有字段必须使用简体中文，禁止输出英文段落。
9. 必须判断项目是否属于 Web 项目，并给出判定依据（框架/路由/HTTP入口/模板引擎/中间件等）。

## 任务目标
1. 识别项目技术栈与入口点。
2. 输出高风险区域（必须带 file_path:line）。
3. 输出可执行的 `input_surfaces` 与 `trust_boundaries`，供后续 flow 分析直接使用。
4. 形成 `initial_findings` 候选（供 Analysis/Verification 使用）。
5. 给出 `recommended_tools`（must_use/reason）。
6. 输出 `project_profile`，明确是否为 Web 项目；若为 Web 项目，给出优先覆盖的 Web 漏洞类型清单。

## Final Answer 结构
```json
{
  "project_structure": {},
  "tech_stack": {"languages": [], "frameworks": [], "databases": []},
  "project_profile": {
    "is_web_project": false,
    "web_project_confidence": 0.0,
    "signals": [],
    "web_vulnerability_focus": []
  },
  "recommended_tools": {"must_use": [], "reason": ""},
  "entry_points": [{"type": "", "file": "", "line": 0, "method": ""}],
  "input_surfaces": [{"source": "", "file_path": "", "line": 0, "details": ""}],
  "trust_boundaries": [{"from": "", "to": "", "file_path": "", "line": 0}],
  "high_risk_areas": ["path/to/file.py:12 - 风险描述"],
  "initial_findings": [{"title": "", "file_path": "", "line_start": 0, "description": "", "confidence": 0.5}],
  "summary": ""
}
```"""

@dataclass
class ReconStep:
    """信息收集步骤"""
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[Dict] = None


class ReconAgent(BaseAgent):
    """
    信息收集 Agent - LLM 驱动版
    
    LLM 全程参与，自主决定：
    1. 收集什么信息
    2. 使用什么工具
    3. 何时足够
    """
    
    def __init__(
        self,
        llm_service,
        tools: Dict[str, Any],
        event_emitter=None,
    ):
        # 仅注入运行时白名单，避免提示词指导调用不存在工具
        tool_whitelist = ", ".join(sorted(tools.keys())) if tools else "无"
        full_system_prompt = (
            f"{RECON_SYSTEM_PROMPT}\n\n"
            f"## 当前工具白名单\n{tool_whitelist}\n"
            "只能调用以上工具，禁止调用未在白名单中的工具。\n\n"
            "## 最小调用规范\n"
            "每轮必须输出：Thought + Action + Action Input。\n"
            "Action 必须是白名单中的工具名，Action Input 必须是 JSON 对象。\n"
            "禁止使用 `## Action`/`## Action Input` 标题样式。"
        )
        
        config = AgentConfig(
            name="Recon",
            agent_type=AgentType.RECON,
            pattern=AgentPattern.REACT,
            max_iterations=15,
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)
        
        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[ReconStep] = []
    
    def _parse_llm_response(self, response: str) -> ReconStep:
        """解析 LLM 响应（共享 ReAct 解析器）"""
        parsed = parse_react_response(
            response,
            final_default={"raw_answer": (response or "").strip()},
            action_input_raw_key="raw_input",
        )
        step = ReconStep(
            thought=parsed.thought or "",
            action=parsed.action,
            action_input=parsed.action_input or {},
            is_final=bool(parsed.is_final),
            final_answer=parsed.final_answer if isinstance(parsed.final_answer, dict) else None,
        )

        if step.is_final and isinstance(step.final_answer, dict) and "initial_findings" in step.final_answer:
            step.final_answer["initial_findings"] = [
                f for f in step.final_answer["initial_findings"]
                if isinstance(f, dict)
            ]
        return step
    

    
    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        执行信息收集 - LLM 全程参与！
        """
        import time
        start_time = time.time()
        
        project_info = input_data.get("project_info", {})
        config = input_data.get("config", {})
        task = input_data.get("task", "")
        task_context = input_data.get("task_context", "")
        
        # 🔥 获取目标文件列表
        target_files = config.get("target_files", [])
        exclude_patterns = config.get("exclude_patterns", [])
        
        # 构建初始消息
        initial_message = f"""请开始收集项目信息。

## 项目基本信息
- 名称: {project_info.get('name', 'unknown')}
- 根目录: {project_info.get('root', '.')}
- 文件数量: {project_info.get('file_count', 'unknown')}

"""

        # 🔥 项目级 Markdown 长期记忆（无需 RAG/Embedding）
        markdown_memory = config.get("markdown_memory") if isinstance(config, dict) else None
        if isinstance(markdown_memory, dict):
            shared_mem = str(markdown_memory.get("shared") or "").strip()
            agent_mem = str(markdown_memory.get("recon") or "").strip()
            skills_mem = str(markdown_memory.get("skills") or "").strip()
            if shared_mem or agent_mem or skills_mem:
                initial_message += f"""## 🧠 项目长期记忆（Markdown，无 RAG）
### shared.md（节选）
{shared_mem or "(空)"}

### recon.md（节选）
{agent_mem or "(空)"}

### skills.md（规范摘要）
{skills_mem or "(空)"}

"""

        initial_message += "## 审计范围\n"
        # 🔥 如果指定了目标文件，明确告知 Agent
        if target_files:
            initial_message += f"""⚠️ **重要**: 用户指定了 {len(target_files)} 个目标文件进行审计：
"""
            for tf in target_files[:10]:
                initial_message += f"- {tf}\n"
            if len(target_files) > 10:
                initial_message += f"- ... 还有 {len(target_files) - 10} 个文件\n"
            initial_message += """
请直接读取和分析这些指定的文件，不要浪费时间遍历其他目录。
"""
        else:
            initial_message += "全项目审计（无特定文件限制）\n"
        
        if exclude_patterns:
            initial_message += f"\n排除模式: {', '.join(exclude_patterns[:5])}\n"
        
        initial_message += f"""
## 任务上下文
{task_context or task or '进行全面的信息收集，为安全审计做准备。'}

## 可用工具
{self.get_tools_description()}

请开始你的信息收集工作。首先思考应该收集什么信息，然后**立即**选择合适的工具执行（输出 Action）。不要只输出 Thought，必须紧接着输出 Action。"""

        # 初始化对话历史
        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": initial_message},
        ]
        
        self._steps = []
        final_result = None
        error_message = None  # 🔥 跟踪错误信息
        last_action_signature: Optional[str] = None
        repeated_action_streak = 0
        llm_timeout_streak = 0
        no_action_streak = 0
        
        await self.emit_thinking("Recon Agent 启动，LLM 开始自主收集信息...")
        
        try:
            for iteration in range(self.config.max_iterations):
                if self.is_cancelled:
                    break
                
                self._iteration = iteration + 1
                
                # 🔥 再次检查取消标志（在LLM调用之前）
                if self.is_cancelled:
                    await self.emit_thinking("🛑 任务已取消，停止执行")
                    break
                
                # 调用 LLM 进行思考和决策（使用基类统一方法）
                try:
                    llm_output, tokens_this_round = await self.stream_llm_call(
                        self._conversation_history,
                        # 🔥 不传递 temperature 和 max_tokens，使用用户配置
                    )
                except asyncio.CancelledError:
                    logger.info(f"[{self.name}] LLM call cancelled")
                    break
                
                self._total_tokens += tokens_this_round

                timeout_like_output = str(llm_output or "").strip().startswith("[超时错误:")
                if timeout_like_output:
                    llm_timeout_streak += 1
                else:
                    llm_timeout_streak = 0

                if llm_timeout_streak >= 3:
                    await self.emit_event(
                        "warning",
                        "LLM 连续超时，进入降级收敛并输出当前已收集结果",
                        metadata={"timeout_streak": llm_timeout_streak},
                    )
                    final_result = self._summarize_from_steps()
                    break
                
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

Thought: [你对当前情况的分析]
Action: [工具名称，如 list_files, read_file, search_code]
Action Input: {{"参数名": "参数值"}}

可用工具: {', '.join(self.tools.keys())}

如果你认为信息收集已经完成，请输出：
Thought: [总结收集到的信息]
Final Answer: [JSON格式的结果]"""
                    
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
                
                # 🔥 发射 LLM 思考内容事件 - 展示 LLM 在想什么
                if step.thought:
                    await self.emit_llm_thought(step.thought, iteration + 1)
                
                # 添加 LLM 响应到历史
                self._conversation_history.append({
                    "role": "assistant",
                    "content": llm_output,
                })
                
                # 检查是否完成
                if step.is_final:
                    no_action_streak = 0
                    await self.emit_llm_decision("完成信息收集", "LLM 判断已收集足够信息")
                    await self.emit_llm_complete(
                        f"信息收集完成，共 {self._iteration} 轮思考",
                        self._total_tokens
                    )
                    final_result = step.final_answer
                    break
                
                # 执行工具
                if step.action:
                    no_action_streak = 0
                    # 🔥 发射 LLM 动作决策事件
                    await self.emit_llm_action(step.action, step.action_input or {})

                    action_signature = (
                        f"{step.action}:{json.dumps(step.action_input or {}, ensure_ascii=False, sort_keys=True)}"
                    )
                    if action_signature == last_action_signature:
                        repeated_action_streak += 1
                    else:
                        repeated_action_streak = 1
                        last_action_signature = action_signature

                    if repeated_action_streak >= 3:
                        observation = (
                            "⚠️ 检测到连续重复工具调用，已自动跳过本次执行以避免无效消耗。"
                            "请更换参数、切换工具或直接输出 Final Answer。"
                        )
                        step.observation = observation
                        await self.emit_llm_observation(observation)
                        self._conversation_history.append(
                            {
                                "role": "user",
                                "content": f"Observation:\n{observation}",
                            }
                        )
                        continue
                    
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
                            observation += "4. 如果已有足够信息，直接输出 Final Answer"
                            
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
                    no_action_streak += 1
                    repeated_action_streak = 0
                    last_action_signature = None
                    # LLM 没有选择工具，提示它继续
                    await self.emit_llm_decision("继续思考", "LLM 需要更多信息")
                    if no_action_streak >= 5:
                        await self.emit_event(
                            "warning",
                            "连续多轮未给出有效 Action，进入降级收敛并输出当前结果",
                            metadata={"no_action_streak": no_action_streak},
                        )
                        final_result = self._summarize_from_steps()
                        break
                    self._conversation_history.append({
                        "role": "user",
                        "content": "请继续。你输出了 Thought 但没有输出 Action。请**立即**选择一个工具执行（Action: ...），或者如果信息收集完成，输出 Final Answer。",
                    })
            
            # 🔥 如果循环结束但没有 final_result，强制 LLM 总结
            if not final_result and not self.is_cancelled and not error_message:
                await self.emit_thinking("📝 信息收集阶段结束，正在生成总结...")
                
                # 添加强制总结的提示
                self._conversation_history.append({
                    "role": "user",
                    "content": """信息收集阶段已结束。请立即输出 Final Answer，总结你收集到的所有信息。

请按以下 JSON 格式输出：
```json
{
    "project_structure": {"directories": [...], "key_files": [...]},
    "tech_stack": {"languages": [...], "frameworks": [...], "databases": [...]},
    "project_profile": {
        "is_web_project": false,
        "web_project_confidence": 0.0,
        "signals": [],
        "web_vulnerability_focus": []
    },
    "entry_points": [{"type": "...", "file": "...", "description": "..."}],
    "high_risk_areas": ["file1.py", "file2.js"],
    "initial_findings": [{"title": "...", "description": "...", "file_path": "..."}],
    "summary": "项目总结描述"
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
                        summary_text = summary_output.strip()
                        summary_text = re.sub(r'```json\s*', '', summary_text)
                        summary_text = re.sub(r'```\s*', '', summary_text)
                        final_result = AgentJsonParser.parse(
                            summary_text,
                            default=self._summarize_from_steps()
                        )
                except Exception as e:
                    logger.warning(f"[{self.name}] Failed to generate summary: {e}")
            
            # 处理结果
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 🔥 如果被取消，返回取消结果
            if self.is_cancelled:
                await self.emit_event(
                    "info",
                    f"🛑 Recon Agent 已取消: {self._iteration} 轮迭代"
                )
                return AgentResult(
                    success=False,
                    error="任务已取消",
                    data=self._summarize_from_steps(),
                    iterations=self._iteration,
                    tool_calls=self._tool_calls,
                    tokens_used=self._total_tokens,
                    duration_ms=duration_ms,
                )
            
            # 🔥 如果有错误，返回失败结果
            if error_message:
                await self.emit_event(
                    "error",
                    f"❌ Recon Agent 失败: {error_message}"
                )
                return AgentResult(
                    success=False,
                    error=error_message,
                    data=self._summarize_from_steps(),
                    iterations=self._iteration,
                    tool_calls=self._tool_calls,
                    tokens_used=self._total_tokens,
                    duration_ms=duration_ms,
                )
            
            # 如果没有最终结果，从历史中汇总
            if not final_result:
                final_result = self._summarize_from_steps()
            if isinstance(final_result, dict):
                final_result = self._ensure_project_profile(final_result)
            
            # 🔥 记录工作和洞察
            self.record_work(f"完成项目信息收集，发现 {len(final_result.get('entry_points', []))} 个入口点")
            self.record_work(f"识别技术栈: {final_result.get('tech_stack', {})}")

            if final_result.get("high_risk_areas"):
                self.add_insight(f"发现 {len(final_result['high_risk_areas'])} 个高风险区域需要重点分析")
            if final_result.get("initial_findings"):
                self.add_insight(f"初步发现 {len(final_result['initial_findings'])} 个潜在问题")

            await self.emit_event(
                "info",
                f"Recon Agent 完成: {self._iteration} 轮迭代, {self._tool_calls} 次工具调用"
            )

            # 🔥 创建 TaskHandoff - 传递给下游 Agent
            handoff = self._create_recon_handoff(final_result)

            return AgentResult(
                success=True,
                data=final_result,
                iterations=self._iteration,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
                handoff=handoff,  # 🔥 添加 handoff
            )
            
        except Exception as e:
            logger.error(f"Recon Agent failed: {e}", exc_info=True)
            return AgentResult(success=False, error=str(e))
    
    def _ensure_project_profile(self, final_result: Dict[str, Any]) -> Dict[str, Any]:
        tech_stack = final_result.get("tech_stack", {})
        frameworks = tech_stack.get("frameworks", []) if isinstance(tech_stack, dict) else []
        framework_lowers = {str(item).strip().lower() for item in frameworks if str(item).strip()}

        profile = final_result.get("project_profile")
        if not isinstance(profile, dict):
            profile = {}

        signals = {
            str(item).strip()
            for item in profile.get("signals", [])
            if isinstance(item, str) and str(item).strip()
        }
        for framework in framework_lowers:
            if framework in WEB_FRAMEWORK_HINTS:
                signals.add(f"framework:{framework}")
        for step in self._steps:
            observation = str(step.observation or "").lower()
            if not observation:
                continue
            for keyword in WEB_SIGNAL_HINTS:
                if keyword in observation:
                    signals.add(f"signal:{keyword}")

        is_web_raw = profile.get("is_web_project")
        if isinstance(is_web_raw, bool):
            is_web_project = is_web_raw
        else:
            is_web_project = bool(signals)

        confidence_raw = profile.get("web_project_confidence")
        try:
            confidence = float(confidence_raw)
        except Exception:
            confidence = min(1.0, len(signals) * 0.1)
            if is_web_project and confidence < 0.4:
                confidence = 0.4
        confidence = max(0.0, min(1.0, confidence))
        if not is_web_project:
            confidence = 0.0

        raw_focus = profile.get("web_vulnerability_focus", [])
        focus = [
            str(item).strip()
            for item in raw_focus
            if isinstance(item, str) and str(item).strip()
        ]
        if is_web_project and not focus:
            focus = list(WEB_VULNERABILITY_FOCUS_DEFAULT)
        if not is_web_project:
            focus = []

        final_result["project_profile"] = {
            "is_web_project": is_web_project,
            "web_project_confidence": round(confidence, 2),
            "signals": sorted(signals)[:16],
            "web_vulnerability_focus": focus,
        }
        return final_result

    def _summarize_from_steps(self) -> Dict[str, Any]:
        """从步骤中汇总结果 - 增强版，从 LLM 思考过程中提取更多信息"""
        # 默认结果结构
        result = {
            "project_structure": {},
            "tech_stack": {
                "languages": [],
                "frameworks": [],
                "databases": [],
            },
            "project_profile": {
                "is_web_project": False,
                "web_project_confidence": 0.0,
                "signals": [],
                "web_vulnerability_focus": [],
            },
            "entry_points": [],
            "high_risk_areas": [],
            "dependencies": {},
            "initial_findings": [],
            "summary": "",  # 🔥 新增：汇总 LLM 的思考
        }
        
        # 🔥 收集所有 LLM 的思考内容
        thoughts = []
        
        # 从步骤的观察结果和思考中提取信息
        for step in self._steps:
            # 收集思考内容
            if step.thought:
                thoughts.append(step.thought)
            
            if step.observation:
                # 尝试从观察中识别技术栈等信息
                obs_lower = step.observation.lower()
                
                # 识别语言
                if "package.json" in obs_lower or ".js" in obs_lower or ".ts" in obs_lower:
                    result["tech_stack"]["languages"].append("JavaScript/TypeScript")
                if "requirements.txt" in obs_lower or "setup.py" in obs_lower or ".py" in obs_lower:
                    result["tech_stack"]["languages"].append("Python")
                if "go.mod" in obs_lower or ".go" in obs_lower:
                    result["tech_stack"]["languages"].append("Go")
                if "pom.xml" in obs_lower or ".java" in obs_lower:
                    result["tech_stack"]["languages"].append("Java")
                if ".php" in obs_lower:
                    result["tech_stack"]["languages"].append("PHP")
                if ".rb" in obs_lower or "gemfile" in obs_lower:
                    result["tech_stack"]["languages"].append("Ruby")
                
                # 识别框架
                if "react" in obs_lower:
                    result["tech_stack"]["frameworks"].append("React")
                if "vue" in obs_lower:
                    result["tech_stack"]["frameworks"].append("Vue")
                if "angular" in obs_lower:
                    result["tech_stack"]["frameworks"].append("Angular")
                if "django" in obs_lower:
                    result["tech_stack"]["frameworks"].append("Django")
                if "flask" in obs_lower:
                    result["tech_stack"]["frameworks"].append("Flask")
                if "fastapi" in obs_lower:
                    result["tech_stack"]["frameworks"].append("FastAPI")
                if "express" in obs_lower:
                    result["tech_stack"]["frameworks"].append("Express")
                if "spring" in obs_lower:
                    result["tech_stack"]["frameworks"].append("Spring")
                if "streamlit" in obs_lower:
                    result["tech_stack"]["frameworks"].append("Streamlit")
                
                # 识别数据库
                if "mysql" in obs_lower or "pymysql" in obs_lower:
                    result["tech_stack"]["databases"].append("MySQL")
                if "postgres" in obs_lower or "asyncpg" in obs_lower:
                    result["tech_stack"]["databases"].append("PostgreSQL")
                if "mongodb" in obs_lower or "pymongo" in obs_lower:
                    result["tech_stack"]["databases"].append("MongoDB")
                if "redis" in obs_lower:
                    result["tech_stack"]["databases"].append("Redis")
                if "sqlite" in obs_lower:
                    result["tech_stack"]["databases"].append("SQLite")
                
                # 🔥 识别高风险区域（从观察中提取）
                risk_keywords = ["api", "auth", "login", "password", "secret", "key", "token", 
                               "admin", "upload", "download", "exec", "eval", "sql", "query"]
                for keyword in risk_keywords:
                    if keyword in obs_lower:
                        # 尝试从观察中提取文件路径
                        import re
                        file_matches = re.findall(r'[\w/]+\.(?:py|js|ts|java|php|go|rb)', step.observation)
                        for file_path in file_matches[:3]:  # 限制数量
                            if file_path not in result["high_risk_areas"]:
                                result["high_risk_areas"].append(file_path)
        
        # 去重
        result["tech_stack"]["languages"] = list(set(result["tech_stack"]["languages"]))
        result["tech_stack"]["frameworks"] = list(set(result["tech_stack"]["frameworks"]))
        result["tech_stack"]["databases"] = list(set(result["tech_stack"]["databases"]))
        result["high_risk_areas"] = list(set(result["high_risk_areas"]))[:20]  # 限制数量
        result = self._ensure_project_profile(result)
        
        # 🔥 汇总 LLM 的思考作为 summary
        if thoughts:
            # 取最后几个思考作为总结
            result["summary"] = "\n".join(thoughts[-3:])
        
        return result
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self._conversation_history

    def get_steps(self) -> List[ReconStep]:
        """获取执行步骤"""
        return self._steps

    def _create_recon_handoff(self, final_result: Dict[str, Any]) -> TaskHandoff:
        """
        创建 Recon Agent 的任务交接信息

        Args:
            final_result: Recon 收集的最终结果

        Returns:
            TaskHandoff 对象，供 Analysis Agent 使用
        """
        # 提取关键发现
        key_findings = []
        for f in final_result.get("initial_findings", [])[:10]:
            if isinstance(f, dict):
                key_findings.append(f)

        # 构建建议行动
        suggested_actions = []
        for area in final_result.get("high_risk_areas", [])[:10]:
            if isinstance(area, str):
                suggested_actions.append({
                    "action": "deep_analysis",
                    "target": area,
                    "reason": "高风险区域需要深入分析"
                })

        # 提取入口点作为关注点
        attention_points = []
        for ep in final_result.get("entry_points", [])[:15]:
            if isinstance(ep, dict):
                attention_points.append(
                    f"[{ep.get('type', 'unknown')}] {ep.get('file', '')}:{ep.get('line', '')}"
                )

        # 构建上下文数据
        context_data = {
            "tech_stack": final_result.get("tech_stack", {}),
            "project_profile": final_result.get("project_profile", {}),
            "project_structure": final_result.get("project_structure", {}),
            "recommended_tools": final_result.get("recommended_tools", {}),
            "dependencies": final_result.get("dependencies", {}),
        }

        # 构建摘要
        tech_stack = final_result.get("tech_stack", {})
        languages = tech_stack.get("languages", [])
        frameworks = tech_stack.get("frameworks", [])

        summary = f"完成项目侦察: "
        if languages:
            summary += f"语言={', '.join(languages[:3])}; "
        if frameworks:
            summary += f"框架={', '.join(frameworks[:3])}; "
        profile = final_result.get("project_profile", {})
        if isinstance(profile, dict):
            if profile.get("is_web_project") is True:
                summary += "判定为Web项目; "
            elif profile.get("is_web_project") is False:
                summary += "判定为非Web项目; "
        summary += f"入口点={len(final_result.get('entry_points', []))}个; "
        summary += f"高风险区域={len(final_result.get('high_risk_areas', []))}个"

        return self.create_handoff(
            to_agent="analysis",
            summary=summary,
            key_findings=key_findings,
            suggested_actions=suggested_actions,
            attention_points=attention_points,
            priority_areas=final_result.get("high_risk_areas", [])[:15],
            context_data=context_data,
        )
