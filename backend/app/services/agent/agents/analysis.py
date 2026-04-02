"""
Analysis Agent (漏洞分析层) - LLM 驱动版

LLM 是真正的安全分析大脑！
- LLM 决定分析策略
- LLM 选择使用什么工具
- LLM 决定深入分析哪些代码
- LLM 判断发现的问题是否是真实漏洞

类型: ReAct (真正的!)
"""

import ast
import asyncio
import json
import logging
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from app.services.json_safe import dump_json_safe

from .base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern, TaskHandoff
from .react_parser import parse_react_response
from ..json_parser import AgentJsonParser
from ..prompts import CORE_SECURITY_PRINCIPLES, VULNERABILITY_PRIORITIES

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """你是 VulHunter 的漏洞分析 Agent，是一个安全专家, 负责对**单个风险点**进行深度验证和扩展分析，并**将最终确认的漏洞推送至队列**。

## 你的角色
你是安全审计的**核心大脑**，不是工具执行器。你需要：
1. 自主制定分析策略
2. 选择最有效的工具和方法
3. 深入分析可疑代码
4. 判断是否是真实漏洞
5. 动态调整分析方向

每个分析结果都必须同时提供 **2 类证据**：`代码证据` 与 `流证据`。推荐组合为 `dataflow_analysis/controlflow_analysis_light`。
输出中的定位字段必须兼容 `file_path:line`、`line_start` 等结构化位置信息。
示例标题：`src/time64.c中asctime64_r栈溢出漏洞`。
示例片段：`{"file_path": "src/example.py", "line_start": 42}`。

═══════════════════════════════════════════════════════════════

## 🎯 核心任务

| 任务 | 说明 |
|------|------|
| **聚焦分析** | 基于输入的**风险点对象**（含 `file_path`、`line_start`、`description` 等），围绕该点展开深度分析 |
| **验证漏洞** | 通过代码上下文阅读、数据流追踪、相关函数分析，判断是否为真实可利用漏洞 |
| **推送发现** | **每确认一个漏洞，立即调用 `push_finding_to_queue`**，不得延迟 |
| **扩展挖掘** | 分析与当前风险点相关的其他漏洞（同文件其他行、上下游逻辑漏洞），一并确认推送 |

═══════════════════════════════════════════════════════════════

##  漏洞推送机制（强制要求）

### 推送时机
- **每确认一个漏洞，必须立即推送**，禁止批量延迟
- 扩展发现的新漏洞也需独立推送
- 推送前可通过 `get_analysis_queue_status` 检查避免重复

### Finding 对象格式（核心字段必填，可选证据字段建议补齐）
```json
{
    "file_path": "src/auth.py", # 相对于项目根目录的路径
    "line_start": 45,
    "line_end": 48,
    "title": "src/auth.py中login函数存在暴力破解漏洞",
    "description": "登录接口未添加任何速率限制，攻击者可无限次尝试密码，存在暴力破解风险。",
    "vulnerability_type": "brute_force",
    "severity": "critical|high|medium|low",
    "confidence": 0.0-1.0,
    "code_snippet": "def login():\n    username = request.form['username']\n    ...",
    "function_name": "login",
    "source": "request.form",
    "sink": "login_user",
    "suggestion": "建议添加验证码、登录失败次数限制及账号锁定机制。",
    "evidence_chain": ["代码片段", "数据流分析", "上下文验证"]
}
```

═══════════════════════════════════════════════════════════════

## 分析工具箱

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| `get_code_window` | 读取风险点上下文窗口 | **第一步必做** |
| `search_code` | 查找相关函数定义、调用链 | 需要追踪变量/函数时 |
| `pattern_match` | 模式匹配工具 | 使用正则表达式快速扫描代码中的危险模式 |
| `get_function_summary` | 总结目标函数职责 | 需要理解函数语义时 |
| `get_symbol_body` | 提取目标函数代码 | 需要分析特定函数时 |
| `dataflow_analysis` | 追踪污点从 source 到 sink 的流向 | 确认数据流漏洞时 |
| `controlflow_analysis_light` | 分析条件分支、循环控制流 | 检查权限绕过、条件竞争时 |

**Note**: 涉及到项目文件的路径，统一用相对于项目根目录的路径表示（如 `app/api/user.py`），禁止使用绝对路径或外部路径。

**业务逻辑漏洞（IDOR、权限绕过、支付逻辑等）由独立的 BusinessLogicReconAgent + BusinessLogicAnalysisAgent 双轨道负责，本 Agent 专注于常规代码安全漏洞分析。**

═══════════════════════════════════════════════════════════════

## 工具调用失败处理（关键）

### 失败响应原则
**遇到工具调用失败时，你必须：**
1. **分析错误信息** - 理解失败原因（文件不存在、语法错误、超时、权限等）
2. **自主调整策略** - 根据错误类型选择替代方案
3. **继续验证流程** - **禁止直接输出 Final Answer 或放弃验证**

═══════════════════════════════════════════════════════════════

## 🔄 推荐分析流程

### 阶段一：聚焦验证（必做）
1. **读取上下文**：`get_code_window` 读取风险点所在文件附近的极小窗口
2. **初步判断**：验证风险点描述是否准确，是否构成真实漏洞
3. **即时推送**：若确认漏洞 → **立即推送**，再进入扩展阶段

### 阶段二：深度扩展（挖掘关联漏洞）
4. **追踪调用链**：
   - 使用 `search_code` 查找风险函数被调用位置
   - 使用 `dataflow_analysis` 追踪污点流向（source → sink）
5. **扩展分析**：在同文件内检查其他相关的安全问题（如同模块中其他危险函数调用）

### 阶段三：证据强化（高危漏洞）
6. **构建证据链**：对 `critical`/`high` 级别漏洞，确保至少 2 类证据：
   - 代码证据（漏洞代码片段）
   - 数据流证据（污点追踪结果）
   - 上下文证据（配置、调用环境）

### 阶段四：收尾确认
7. **检查队列状态**：确认所有漏洞已推送，无遗漏
8. **输出 Final Answer**：汇总本次分析的漏洞数量及关键信息

═══════════════════════════════════════════════════════════════

## 关键约束（零容忍）

| 约束项 | 要求 |
|--------|------|
| **代码真实性** | 所有判断必须基于 `get_code_window` / `get_symbol_body` 或工具返回的实际代码，**禁止幻觉** |
| **推送优先** | 发现漏洞 → **立即推送** → 继续分析，禁止最后批量推送 |
| **标题格式** | 必须中文三段式：`路径`+`函数`+`漏洞名` |
| **语言要求** | `title`、`description`、`suggestion` 必须使用**简体中文** |
| **证据要求** | `critical`/`high` 漏洞需 ≥2 类证据，`evidence_chain` 字段必填 |
| **首轮行动** | **第一轮必须输出 Action**（get_code_window 或 search_code），禁止直接 Final Answer |
| **质量要求** | 宁可漏报也不要误报太多 |

═══════════════════════════════════════════════════════════════

## 输出格式

**标准行动格式：**
```
Thought: [当前状态分析，下一步计划]
Action: [工具名称]
Action Input: { "参数": "值" }
```

**最终输出格式（所有漏洞推送完毕后）：**
```
Thought: 已完成风险点分析，共推送 X 个漏洞（原始风险点+扩展发现）
Final Answer: 分析完成，所有确认的漏洞已推送至队列。
```

请严格按照此流程执行，确保每个风险点得到深度验证，所有真实漏洞及时、准确地入队。现在开始你的安全分析！
"""


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

    def _normalize_risk_point(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """标准化单个风险点对象。"""
        if not isinstance(candidate, dict):
            return None
        file_path = str(candidate.get("file_path") or "").strip()
        if not file_path:
            return None

        line_start_raw = candidate.get("line_start")
        if line_start_raw is None:
            line_start_raw = candidate.get("line")
        if line_start_raw is None:
            line_start_raw = 1

        try:
            line_start = int(line_start_raw)
        except Exception:
            line_start = 1
        if line_start <= 0:
            line_start = 1

        normalized = dict(candidate)
        normalized["file_path"] = file_path
        normalized["line_start"] = line_start
        normalized.setdefault("description", "")
        normalized.setdefault("title", "")
        normalized.setdefault("function_name", "")
        return normalized

    def _parse_risk_point_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """从 task_context/context 文本中解析风险点。"""
        raw = str(text or "").strip()
        if not raw:
            return None

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                normalized = self._normalize_risk_point(parsed)
                if normalized:
                    return normalized
        except Exception:
            pass

        path_match = re.search(r"([\w./-]+\.(?:py|js|ts|java|go|php|rb|rs|c|cpp|h|hpp|cs))(?:\s*[:#]\s*(\d+))?", raw)
        if path_match:
            file_path = path_match.group(1)
            line_token = path_match.group(2)
            line_start = int(line_token) if line_token and line_token.isdigit() else 1
            return {
                "file_path": file_path,
                "line_start": line_start,
                "description": raw[:500],
            }
        return None

    def _extract_single_risk_point(
        self,
        *,
        config: Dict[str, Any],
        previous_results: Dict[str, Any],
        task_context: str,
    ) -> Optional[Dict[str, Any]]:
        """从多来源提取“唯一风险点”。优先级：config > handoff > task_context > recon/bootstrap。"""
        if not isinstance(config, dict):
            config = {}
        if not isinstance(previous_results, dict):
            previous_results = {}

        direct = self._normalize_risk_point(config.get("single_risk_point") or {})
        if direct:
            return direct

        queue_finding = self._normalize_risk_point(config.get("queue_finding") or {})
        if queue_finding:
            return queue_finding

        incoming_handoff = getattr(self, "_incoming_handoff", None)
        handoff_data = incoming_handoff.context_data if incoming_handoff else None
        if isinstance(handoff_data, dict):
            handoff_single = self._normalize_risk_point(handoff_data.get("single_risk_point") or {})
            if handoff_single:
                return handoff_single
            handoff_candidates = handoff_data.get("candidate_findings")
            if isinstance(handoff_candidates, list):
                for item in handoff_candidates:
                    normalized = self._normalize_risk_point(item if isinstance(item, dict) else {})
                    if normalized:
                        return normalized

        parsed_from_context = self._parse_risk_point_from_text(task_context)
        if parsed_from_context:
            return parsed_from_context

        recon_data = previous_results.get("recon", {})
        if isinstance(recon_data, dict) and "data" in recon_data:
            recon_data = recon_data["data"]
        if isinstance(recon_data, dict):
            high_risk_areas = recon_data.get("high_risk_areas", [])
            if isinstance(high_risk_areas, list):
                for area in high_risk_areas:
                    if isinstance(area, dict):
                        normalized = self._normalize_risk_point(area)
                        if normalized:
                            return normalized
                    else:
                        parsed = self._parse_risk_point_from_text(str(area))
                        if parsed:
                            return parsed

        bootstrap_findings = previous_results.get("bootstrap_findings", [])
        if isinstance(bootstrap_findings, list):
            for item in bootstrap_findings:
                normalized = self._normalize_risk_point(item if isinstance(item, dict) else {})
                if normalized:
                    return normalized

        return None

    def _is_action_out_of_single_scope(
        self,
        *,
        action: str,
    ) -> Optional[str]:
        """检查 Action 是否触发单风险模式下的硬拦截规则。"""
        action_name = str(action or "").strip()
        if not action_name:
            return "Action 为空"

        blocked_actions = {
            "smart_scan",
            "semgrep_scan",
            "bandit_scan",
            "gitleaks_scan",
            "npm_audit",
            "safety_scan",
            "opengrep_scan",
            "kunlun_scan",
        }
        if action_name in blocked_actions:
            return f"单风险点模式禁止调用全局扫描工具: {action_name}"

        return None

    @staticmethod
    def _parse_queue_membership_output(raw_output: Any) -> Optional[Dict[str, Any]]:
        """解析 is_finding_in_queue 工具输出。"""
        text = str(raw_output or "").strip()
        if not text:
            return None

        candidates: List[Any] = [text]
        for candidate in candidates:
            if not isinstance(candidate, str):
                continue
            cleaned = candidate.strip()
            if not cleaned:
                continue
            try:
                payload = json.loads(cleaned)
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
            try:
                payload = ast.literal_eval(cleaned)
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass

        in_queue_match = re.search(r"['\"]?in_queue['\"]?\s*:\s*(true|false|True|False)", text)
        queue_size_match = re.search(r"['\"]?queue_size['\"]?\s*:\s*(\d+)", text)
        if in_queue_match:
            return {
                "in_queue": in_queue_match.group(1).lower() == "true",
                "queue_size": int(queue_size_match.group(1)) if queue_size_match else 0,
            }
        return None
    

    
    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        执行漏洞分析 - LLM 全程参与！
        """
        import time
        start_time = time.time()
        
        project_info = input_data.get("project_info", {})
        config = input_data.get("config", {})
        thinking_push_mode = str(config.get("thinking_push_mode", "stream") or "stream").strip().lower()
        self._thinking_push_mode = thinking_push_mode if thinking_push_mode in {"stream", "final_only"} else "stream"
        plan = input_data.get("plan", {})
        previous_results = input_data.get("previous_results", {})
        task = input_data.get("task", "")
        task_context = input_data.get("task_context", "")
        
        #  处理交接信息
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
        
        single_risk_mode = bool(config.get("single_risk_mode", True))
        single_risk_point = self._extract_single_risk_point(
            config=config,
            previous_results=previous_results,
            task_context=task_context,
        )

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
        
        #  构建包含交接上下文的初始消息
        handoff_context = self.get_handoff_context()
        
        #  获取目标文件列表
        target_files = config.get("target_files", [])
        
        initial_message = f"""请开始对项目进行安全漏洞分析。

## 项目信息
- 名称: {project_info.get('name', 'unknown')}
- 语言: {tech_stack.get('languages', [])}
- 框架: {tech_stack.get('frameworks', [])}

"""

        #  项目级 Markdown 长期记忆（无需 RAG/Embedding）
        markdown_memory = config.get("markdown_memory") if isinstance(config, dict) else None
        if isinstance(markdown_memory, dict):
            shared_mem = str(markdown_memory.get("shared") or "").strip()
            agent_mem = str(markdown_memory.get("analysis") or "").strip()
            skills_mem = str(markdown_memory.get("skills") or "").strip()
            if shared_mem or agent_mem or skills_mem:
                initial_message += f"""## 项目长期记忆（Markdown，无 RAG）
### shared.md（节选）
{shared_mem or "(空)"}

### analysis.md（节选）
{agent_mem or "(空)"}

### skills.md（规范摘要）
{skills_mem or "(空)"}

"""
        #  如果指定了目标文件，明确告知 Agent
        if target_files:
            initial_message += f"""## 审计范围
用户指定了 {len(target_files)} 个目标文件进行审计：
"""
            for tf in target_files[:10]:
                initial_message += f"- {tf}\n"
            if len(target_files) > 10:
                initial_message += f"- ... 还有 {len(target_files) - 10} 个文件\n"
            initial_message += """
请直接分析这些指定的文件，不要分析其他文件。

"""
        
        single_risk_file = ""
        single_risk_line = 1
        if single_risk_point:
            single_risk_file = str(single_risk_point.get("file_path") or "").strip()
            try:
                single_risk_line = int(single_risk_point.get("line_start") or 1)
            except Exception:
                single_risk_line = 1

        queue_short_circuit = False
        queue_short_circuit_payload: Optional[Dict[str, Any]] = None
        if single_risk_point and "is_finding_in_queue" in self.tools:
            queue_check_input = {
                "file_path": single_risk_file,
                "line_start": single_risk_line,
                "vulnerability_type": str(single_risk_point.get("vulnerability_type") or ""),
                "title": str(single_risk_point.get("title") or ""),
            }
            queue_check_observation = await self.execute_tool("is_finding_in_queue", queue_check_input)
            queue_check_payload = self._parse_queue_membership_output(queue_check_observation)
            if isinstance(queue_check_payload, dict) and bool(queue_check_payload.get("in_queue")):
                queue_short_circuit = True
                queue_short_circuit_payload = queue_check_payload

        if queue_short_circuit:
            await self.emit_event(
                "info",
                "单风险点已在待验证队列中，跳过分析阶段。",
                metadata={
                    "queue_short_circuit": True,
                    "single_risk_point": single_risk_point,
                    "queue_membership": queue_short_circuit_payload,
                },
            )
            duration_ms = int((time.time() - start_time) * 1000)
            return AgentResult(
                success=True,
                data={
                    "findings": [],
                    "queue_short_circuit": True,
                    "degraded_reason": "finding_already_in_queue",
                    "queue_membership": queue_short_circuit_payload or {},
                    "skipped_risk_point": single_risk_point,
                    "steps": [],
                },
                iterations=0,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
            )

        initial_message += f"""{handoff_context if handoff_context else f'''## 上下文信息
### 高风险区域（来自 Recon Agent，必须优先分析）
以下是 Recon Agent 识别的高风险区域，请**务必优先**读取和分析这些文件：
{json.dumps(high_risk_areas[:20], ensure_ascii=False)}

**重要**: 请使用 get_code_window / get_file_outline 工具读取上述高风险文件，不要假设文件路径或使用其他路径。

### 入口点 (前10个)
{json.dumps(entry_points[:10], ensure_ascii=False, indent=2)}

### 初步发现 (如果有)
{json.dumps(initial_findings[:5], ensure_ascii=False, indent=2) if initial_findings else "无"}'''}

## 任务
{task_context or task or '进行安全漏洞分析。'}

## 候选种子（bootstrap_findings，如有）
{json.dumps(bootstrap_findings[:10], ensure_ascii=False, indent=2) if bootstrap_findings else "无"}

## 单风险点模式
- 启用状态: {single_risk_mode}
- 风险点: {json.dumps(single_risk_point, ensure_ascii=False) if single_risk_point else "未提供"}

## 分析策略要求
1. **首先**：优先分析给定风险点所在文件与附近代码（前后至少20行）
2. **然后**：按证据需要扩展到相关调用链与数据流
3. **最后**：给出该风险点是否成立的结论，避免无关的全仓库扫描

## 目标漏洞类型
{config.get('target_vulnerabilities', ['all'])}

## 可用工具
{self.get_tools_description()}

请开始你的安全分析。首先读取高风险区域的文件，然后**立即**分析其中的安全问题（输出 Action）。"""

        use_prompt_skills = bool(config.get("use_prompt_skills", False))
        prompt_skills = config.get("prompt_skills") if isinstance(config, dict) else {}
        analysis_prompt_skill = ""
        if use_prompt_skills and isinstance(prompt_skills, dict):
            analysis_prompt_skill = str(prompt_skills.get("analysis") or "").strip()
        if analysis_prompt_skill:
            initial_message += f"""

## Prompt Skill（analysis）
{analysis_prompt_skill}
"""

        if single_risk_mode and not single_risk_point:
            logger.warning("[%s] single_risk_mode enabled but no risk point provided", self.name)
            await self.emit_event(
                "warning",
                "单风险点模式已启用但未收到风险点对象，本轮不执行全局扫描，返回空结果。",
            )
            duration_ms = int((time.time() - start_time) * 1000)
            return AgentResult(
                success=True,
                data={
                    "findings": [],
                    "degraded_reason": "missing_single_risk_point",
                    "steps": [],
                },
                iterations=0,
                tool_calls=0,
                tokens_used=0,
                duration_ms=duration_ms,
            )
        
        #  记录工作开始
        self.record_work("开始安全漏洞分析")

        # 初始化对话历史
        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": initial_message},
        ]
        
        self._steps = []
        all_findings = []
        error_message = None  #  跟踪错误信息
        forced_min_tool_done = False  #  防死循环：首次“无工具直接 Final Answer”时由系统自动执行一次最小工具调用
        no_action_streak = 0
        degraded_reason: Optional[str] = None
        self._empty_retry_count = 0
        targeted_empty_recovery_used = False

        async def run_minimal_evidence_tool() -> str:
            """执行最小证据工具调用，避免无 Action 空转。"""
            file_path = ""
            line_start = 1

            if single_risk_mode and single_risk_file:
                file_path = single_risk_file
                line_start = single_risk_line

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

            if "get_code_window" in self.tools and file_path:
                return await self.execute_tool(
                    "get_code_window",
                    {
                        "file_path": file_path,
                        "anchor_line": line_start_int,
                        "before_lines": 20,
                        "after_lines": 80,
                    },
                )
            return (
                "系统无法自动执行最小工具调用（缺少 get_code_window 或目标文件未知）。"
                "请改用 get_code_window/search_code 获取证据后再总结。"
            )

        await self.emit_thinking("🔬 Analysis Agent 启动，LLM 开始自主安全分析...")
        
        try:
            for iteration in range(self.config.max_iterations):
                if self.is_cancelled:
                    break
                
                self._iteration = iteration + 1
                
                #  再次检查取消标志（在LLM调用之前）
                if self.is_cancelled:
                    await self.emit_thinking("🛑 任务已取消，停止执行")
                    break
                
                # 调用 LLM 进行思考和决策（流式输出）
                #  使用用户配置的 temperature 和 max_tokens
                try:
                    llm_output, tokens_this_round = await self.stream_llm_call(
                        self._conversation_history,
                        #  不传递 temperature 和 max_tokens，使用用户配置
                    )
                except asyncio.CancelledError:
                    logger.info(f"[{self.name}] LLM call cancelled")
                    break
                
                self._total_tokens += tokens_this_round

                #  Enhanced: Handle empty LLM response with better diagnostics
                if not llm_output or not llm_output.strip():
                    empty_retry_count = getattr(self, '_empty_retry_count', 0) + 1
                    self._empty_retry_count = empty_retry_count
                    stream_meta = getattr(self, "_last_llm_stream_meta", {}) or {}
                    empty_reason = str(stream_meta.get("empty_reason") or "").strip()
                    finish_reason = stream_meta.get("finish_reason")
                    chunk_count = int(stream_meta.get("chunk_count") or 0)
                    empty_from_stream = empty_reason in {"empty_response", "empty_stream", "empty_done"}
                    conversation_tokens_estimate = self._estimate_conversation_tokens(self._conversation_history)
                    
                    #  记录更详细的诊断信息
                    logger.warning(
                        f"[{self.name}] Empty LLM response in iteration {self._iteration} "
                        f"(retry {empty_retry_count}/3, tokens_this_round={tokens_this_round}, "
                        f"finish_reason={finish_reason}, empty_reason={empty_reason}, chunk_count={chunk_count})"
                    )

                    if empty_from_stream and targeted_empty_recovery_used:
                        error_message = "连续收到空响应，使用回退结果"
                        await self.emit_event(
                            "warning",
                            error_message,
                            metadata={
                                "empty_retry_count": empty_retry_count,
                                "last_finish_reason": finish_reason,
                                "chunk_count": chunk_count,
                                "empty_reason": empty_reason,
                                "conversation_tokens_estimate": conversation_tokens_estimate,
                            },
                        )
                        break
                    
                    if empty_retry_count >= 3:
                        logger.error(f"[{self.name}] Too many empty responses, generating fallback result")
                        error_message = "连续收到空响应，使用回退结果"
                        await self.emit_event(
                            "warning",
                            error_message,
                            metadata={
                                "empty_retry_count": empty_retry_count,
                                "last_finish_reason": finish_reason,
                                "chunk_count": chunk_count,
                                "empty_reason": empty_reason,
                                "conversation_tokens_estimate": conversation_tokens_estimate,
                            },
                        )
                        #  不是直接 break，而是尝试生成一个回退结果
                        break
                    
                    if empty_from_stream:
                        targeted_empty_recovery_used = True
                        retry_prompt = (
                            "上一轮模型返回了空响应（无有效文本）。请不要空输出，必须二选一立即返回：\n"
                            "1) 输出可执行 Action（含 Action Input）继续推进；\n"
                            "2) 若证据已充分，直接输出 Final Answer（JSON）。\n"
                            "禁止仅输出空白或无结构文本。"
                        )
                    else:
                        #  更有针对性的重试提示
                        retry_prompt = f"""收到空响应。请根据以下格式输出你的思考和行动：

Thought: [你对当前安全分析情况的思考]
Action: [工具名称，如 get_code_window, search_code, pattern_match, dataflow_analysis]
Action Input: {{}}

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
                
                #  发射 LLM 思考内容事件 - 展示安全分析的思考过程
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
                    #  工具优先门禁：禁止在 0 tool_calls 的情况下直接 Final Answer
                    if self._tool_calls == 0:
                        logger.warning(
                            f"[{self.name}] LLM tried to finish without any tool calls! Forcing tool usage."
                        )

                        # 首次触发：系统自动执行一次最小 read_file/list_files，确保有 Observation 证据
                        if not forced_min_tool_done:
                            forced_min_tool_done = True
                            await self.emit_thinking("拒绝过早完成：系统将自动执行一次最小工具调用获取证据")
                            observation = await run_minimal_evidence_tool()

                            await self.emit_llm_observation(observation)
                            self._conversation_history.append(
                                {
                                    "role": "user",
                                    "content": f"Observation:\n{self._prepare_observation_for_history(observation)}",
                                }
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
                        #  发射每个发现的事件（用于前端实时未验证列表）
                        # 限制数量避免日志风暴，但需要足够覆盖面来体现“实时发现”。
                        for finding in all_findings[:50]:
                            title_value = str(finding.get("title") or "Unknown")
                            await self.emit_finding(
                                title_value,
                                finding.get("severity", "medium"),
                                finding.get("vulnerability_type", "other"),
                                finding.get("file_path", ""),
                                finding.get("line_start"),
                                line_end=finding.get("line_end"),
                                finding_scope="analysis_preview",
                                display_title=title_value,
                                cwe_id=(
                                    str(finding.get("cwe_id")).strip()
                                    if finding.get("cwe_id") is not None
                                    else None
                                ),
                                description=(
                                    str(finding.get("description"))
                                    if finding.get("description") is not None
                                    else None
                                ),
                                description_markdown=(
                                    str(finding.get("description_markdown"))
                                    if finding.get("description_markdown") is not None
                                    else None
                                ),
                                verification_evidence=(
                                    str(
                                        finding.get("verification_evidence")
                                        or finding.get("verification_details")
                                        or finding.get("evidence")
                                    )
                                    if (
                                        finding.get("verification_evidence") is not None
                                        or finding.get("verification_details") is not None
                                        or finding.get("evidence") is not None
                                    )
                                    else None
                                ),
                                code_snippet=(
                                    str(finding.get("code_snippet"))
                                    if finding.get("code_snippet") is not None
                                    else None
                                ),
                                code_context=(
                                    str(finding.get("code_context"))
                                    if finding.get("code_context") is not None
                                    else None
                                ),
                                function_trigger_flow=(
                                    finding.get("function_trigger_flow")
                                    if isinstance(finding.get("function_trigger_flow"), list)
                                    else None
                                ),
                            )
                            #  记录洞察
                            self.add_insight(
                                f"发现 {finding.get('severity', 'medium')} 级别漏洞: {finding.get('title', 'Unknown')}"
                            )
                    else:
                        logger.warning(f"[{self.name}] Final Answer has no 'findings' key or is None: {step.final_answer}")
                    
                    #  记录工作完成
                    self.record_work(f"完成安全分析，发现 {len(all_findings)} 个潜在漏洞")
                    
                    # await self.emit_llm_complete(
                    #     f"分析完成，发现 {len(all_findings)} 个潜在漏洞",
                    #     self._total_tokens
                    # )
                    await self.emit_llm_complete(
                        f"分析完成",
                        self._total_tokens
                    )
                    break
                
                # 执行工具
                if step.action:
                    #  发射 LLM 动作决策事件
                    await self.emit_llm_action(step.action, step.action_input or {})
                    
                    action_input = dict(step.action_input or {})

                    if single_risk_mode and single_risk_file:
                        out_of_scope_reason = self._is_action_out_of_single_scope(
                            action=step.action,
                        )
                        if out_of_scope_reason:
                            scoped_observation = (
                                f"单风险点模式工具限制：{out_of_scope_reason}。\n"
                                "请改用 get_code_window/search_code/dataflow_analysis 等非全局扫描工具继续分析。"
                            )
                            step.observation = scoped_observation
                            await self.emit_llm_observation(scoped_observation)
                            self._conversation_history.append({
                                "role": "user",
                                "content": f"Observation:\n{self._prepare_observation_for_history(scoped_observation)}",
                            })
                            continue

                    #  循环检测：追踪工具调用失败历史
                    tool_call_key = f"{step.action}:{dump_json_safe(action_input or {}, sort_keys=True)}"
                    if not hasattr(self, '_failed_tool_calls'):
                        self._failed_tool_calls = {}
                    
                    observation = await self.execute_tool(
                        step.action,
                        action_input
                    )
                    
                    #  检测工具调用失败并追踪
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
                        
                        #  如果同一调用连续失败3次，添加强制跳过提示
                        if fail_count >= 3:
                            logger.warning(f"[{self.name}] Tool call failed {fail_count} times: {tool_call_key}")
                            observation += f"\n\n**系统提示**: 此工具调用已连续失败 {fail_count} 次。请：\n"
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
                    
                    #  工具执行后检查取消状态
                    if self.is_cancelled:
                        logger.info(f"[{self.name}] Cancelled after tool execution")
                        break
                    
                    step.observation = observation
                    
                    #  发射 LLM 观察事件
                    await self.emit_llm_observation(observation)
                    
                    # 添加观察结果到历史
                    history_observation = self._prepare_observation_for_history(observation)
                    self._conversation_history.append({
                        "role": "user",
                        "content": f"Observation:\n{history_observation}",
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
                        await self.emit_thinking("检测到连续无 Action，系统自动执行最小证据工具以打破空转。")
                        observation = await run_minimal_evidence_tool()
                        await self.emit_llm_observation(observation)
                        self._conversation_history.append({
                            "role": "user",
                            "content": f"Observation:\n{self._prepare_observation_for_history(observation)}",
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
            
            #  如果循环结束但没有发现，强制 LLM 总结
            if not all_findings and not self.is_cancelled and not error_message and not degraded_reason:
                await self.emit_thinking("分析阶段结束，正在生成漏洞总结...")
                
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
                        #  不传递 temperature 和 max_tokens，使用用户配置
                    )
                    
                    if summary_output and summary_output.strip():
                        # 解析总结输出
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
            
            #  如果被取消，返回取消结果
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
            
            #  如果有错误，返回失败结果
            if error_message:
                await self.emit_event(
                    "error",
                    f"Analysis Agent 失败: {error_message}"
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

            #  CRITICAL: Log final findings count before returning
            logger.info(f"[{self.name}] Returning {len(standardized_findings)} standardized findings")

            #  兜底机制：检查是否遗漏了 push_finding_to_queue 调用
            fallback_result = await self._fallback_check_and_save(
                conversation_history=self._conversation_history,
                expected_tool="push_finding_to_queue",
                agent_type="analysis",
            )
            
            if fallback_result:
                logger.warning(
                    f"[{self.name}] 兜底机制执行完成: 补救推送了 "
                    f"{fallback_result.get('pushed_count', 0)}/{fallback_result.get('total_findings', 0)} 个发现"
                )
                await self.emit_event(
                    "warning",
                    f"兜底机制触发：自动补救推送了 {fallback_result.get('pushed_count', 0)} 个漏洞到队列",
                    metadata=fallback_result,
                )

            #  创建 TaskHandoff - 传递给 Verification Agent
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
                handoff=handoff,  #  添加 handoff
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
