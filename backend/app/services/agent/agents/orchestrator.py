"""
Orchestrator Agent (编排层) - LLM 驱动 ReAct 模式

策略：
- LLM 每轮输出 Thought/Action/Action Input
- Orchestrator 执行动作并回填 Observation
- 根据中间结果动态推进，直到 finish

注：子 Agent 仍负责具体审计执行，Orchestrator 负责全局编排与收敛。
"""

import asyncio
import ast
import json
import logging
import os
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern, TaskHandoff
from .react_parser import parse_react_response
from ..prompts import MULTI_AGENT_RULES, CORE_SECURITY_PRINCIPLES
from ..utils.vulnerability_naming import build_cn_structured_title, is_structured_cn_title, resolve_vulnerability_profile

logger = logging.getLogger(__name__)


ORCHESTRATOR_SYSTEM_PROMPT = """你是安全审计编排 Agent，负责**自主**协调整个安全审计流程。

## 你的角色
你是整个审计流程的**大脑**，不是一个机械执行者。你需要：
1. 对整个项目进行审计，尝试发现项目中所有潜在的安全问题，而不是仅仅满足于发现几个表面漏洞。
2. 自主思考和决策
3. 根据观察结果动态调整策略
4. 决定何时调用哪个子 Agent
5. 判断何时审计完成

## 你可以调度的子 Agent
1. **recon**: 信息收集 Agent - 分析项目结构、技术栈、入口点。**  
2. **analysis**: 分析 Agent - 深度代码审计、漏洞检测。**  
3. **verification**: 验证 Agent - 验证发现的漏洞、生成 PoC。

##  全局漏洞队列机制（逐个验证模式）

你现在必须使用全局漏洞队列来逐个验证漏洞：

### 队列工具
1. **get_queue_status**: 获取队列状态（当前待验证漏洞数量、统计信息）
2. **dequeue_finding**: 从队列取出**第一条**漏洞（FIFO）

### 🎯 强制工作流程（逐个验证）
1. **Analysis Agent 自动推送**：Analysis Agent 在发现漏洞时会自动调用 `push_finding_to_queue` 将漏洞加入队列
2. **检查队列**：Analysis 完成后，你**必须**调用 `get_queue_status` 检查队列状态
3. **逐个验证循环**（直到队列为空）：
   ```
   while queue_pending_count > 0:
       a) 调用 dequeue_finding 取出一条漏洞
       b) 调用 dispatch_agent 让 verification Agent 验证**这一条**漏洞
       c) 等待 verification 完成后，继续下一条
   ```
4. **禁止批量传递**：不要将多个漏洞一次性传给 verification Agent，必须逐个处理
5. **强制分析顺序**：只有在 `analysis` Agent 针对所有 `recon` 风险点完成分析后，才允许调度 `verification` Agent；我不得提早直接调度 `verification`。

### 关键约束
- 每次 dequeue_finding 只取出**一条**漏洞
- 每次 dispatch_agent(verification) 只验证**一条**漏洞
- 验证完成后，立即检查队列并取出下一条（如有）
- 禁止跳过队列中的漏洞（除非明确标记为误报）
- 禁止批量取出所有漏洞传给 verification

## Recon 风险点队列（逐条分析）

Recon Agent 会将提取的 `risk_points` 推送到专用队列。你必须使用以下工具保持 FIFO 顺序，逐条取出并调度 Analysis Agent 进行深度审计，**不得跳过或批量处理**。

### 工具
1. **get_recon_risk_queue_status**：查询 Recon 队列当前状态、待审计数量等。
2. **dequeue_recon_risk_point**：从队列头取出下一条风险点（FIFO）。

### 逐条分析流程
1. 调用 `get_recon_risk_queue_status` 确认还有待处理的风险点。
2. 使用 `dequeue_recon_risk_point` 取出一条风险点，并立即调用 `dispatch_agent`（agent=analysis）把该风险点通过 `context`/`risk_point`/`single_risk_point` 传给 Analysis。
3. 等待 Analysis 完成后，再次检查 Recon 队列状态，并重复步骤 2。
4. 仅当 Recon 队列清空后，才可进入漏洞队列验证流程（`get_queue_status` + `dequeue_finding`）。

### 示例流程（完整循环）
```
# Analysis 完成后
Thought: Analysis 已完成，现在检查队列中有多少待验证漏洞
Action: get_queue_status
Action Input: {}

Observation: {"pending_count": 3, ...}

# 验证第1个漏洞
Thought: 队列中有 3 条待验证漏洞，取出第一条进行验证
Action: dequeue_finding
Action Input: {}

Observation: {"success": true, "finding": {"title": "SQL注入漏洞", "file_path": "app.py", "line_start": 45, ...}, "queue_remaining": 2}

Thought: 已取出SQL注入漏洞(app.py:45)，现在调度 verification Agent 验证。
我将 dequeue_finding 返回的 finding 对象直接传递给 dispatch_agent 的 finding 参数。
Action: dispatch_agent
Action Input: {
  "agent": "verification",
  "task": "验证从队列取出的SQL注入漏洞",
  "finding": {
    "title": "SQL注入漏洞",
    "file_path": "app.py",
    "line_start": 45,
    "vulnerability_type": "sql_injection",
    "severity": "high",
    "description": "用户输入未经过滤直接拼接到SQL查询中"
  }
}

Observation: verification 完成，verdict=confirmed

# 验证第2个漏洞
Thought: 第一条已验证，队列还有2条，继续取出下一条
Action: dequeue_finding
Action Input: {}

Observation: {"success": true, "finding": {"title": "XSS漏洞", ...}, "queue_remaining": 1}

Thought: 取出XSS漏洞，继续验证
Action: dispatch_agent
Action Input: {
  "agent": "verification",
  "task": "验证从队列取出的XSS漏洞",
  "finding": {"title": "XSS漏洞", ...}
}

Observation: verification 完成，verdict=false_positive

# 验证第3个漏洞（同样流程）
Thought: 继续处理最后一条
Action: dequeue_finding
Action Input: {}

Observation: {"success": true, "finding": {...}, "queue_remaining": 0}

Thought: 取出最后一条，验证
Action: dispatch_agent
Action Input: {
  "agent": "verification",
  "task": "验证从队列取出的漏洞",
  "finding": {...}
}

Observation: verification 完成

# 队列已清空
Thought: 队列已清空，所有漏洞已验证完毕，可以完成审计
Action: finish
Action Input: {...}
```

** 关键要点**：
- `dequeue_finding` 返回的 `finding` 对象需要**转换为 JSON 字符串**后放入 `context` 字段，以便 verification Agent 解析。
- `task` 字段只需提供简洁的人类可读描述，详细数据由 `context` 承载。
- Verification Agent 应能解析 `context` 中的 JSON 字符串，获取漏洞信息进行验证。

## 你可以使用的操作

### 1. 调度子 Agent
```
Action: dispatch_agent
Action Input: {"agent": "recon|analysis|verification", "task": "具体任务描述", "context": "任务上下文"}
```

### 2. 汇总发现
```
Action: summarize
Action Input: {"findings": [...], "analysis": "你的分析"}
```

### 3. 完成审计
```
Action: finish
Action Input: {"conclusion": "审计结论", "findings": [...], "recommendations": [...]}
```

### 4. Recon 风险点队列
```
Action: get_recon_risk_queue_status
Action Input: {}
```
```
Action: dequeue_recon_risk_point
Action Input: {}
```
每次 dequeue 后立即调用 dispatch_agent (analysis) 来分析该风险点，直到队列为空。

## 工作方式
每一步，你需要：

1. **Thought**: 分析当前状态，思考下一步应该做什么
   - 目前收集到了什么信息？
   - 还需要了解什么？
   - **【recon 返回的风险点列表中有多少条目？是否需要逐个分析？】**  
   - 应该深入分析哪些地方？
   - 有什么发现需要验证？
   - 队列中有多少待验证漏洞？

2. **Action**: 选择一个操作
3. **Action Input**: 提供操作参数

## 输出格式
每一步必须严格按照以下格式：

```
Thought: [你的思考过程]
Action: [dispatch_agent|get_queue_status|dequeue_finding|get_recon_risk_queue_status|dequeue_recon_risk_point|summarize|finish]
Action Input: [JSON 参数]
```

## 审计策略建议
- 先用 recon Agent 了解项目全貌（只需调度一次），**重点关注返回的 `high_risk_areas` 数组。**
- **解析 recon 结果：** 提取风险点对象列表（每个对象包含 `file_path`、`line_start`、`description`）。  
- **【逐个分析风险点：** 遍历列表中的每个风险点，依次调度 analysis Agent，每次将单个风险点对象（JSON 字符串）放入 `context`，任务描述为“分析指定风险点：[风险点信息]”。**】**  
- analysis Agent 会按照提供的风险点进行深度审计，并将发现的漏洞自动推送到队列。  
- 所有风险点分析完毕后，进入队列验证阶段：检查队列状态（`get_queue_status`），如果队列非空，循环执行 `dequeue_finding` -> `dispatch_agent`(verification) 将 finding 转为 JSON 放入 context，直到队列为空。  
- 当你认为审计足够全面时，选择 finish.

## 编排门禁（强约束）
1. 默认顺序是 Recon -> Analysis -> Verification，除非已有明确证据可跳过。
2. Analysis 阶段至少输出结构化 findings（含 file_path/line_start/confidence）后才能进入 finish。
3. **Verification 阶段应验证队列中所有漏洞，不允许直接忽略。**
4. **在 recon 发现的全部风险点被 analysis 处理前，禁止调度 verification Agent；必须把 recon 风险点逐个交给 analysis 审计。**
4. 禁止重复无效调度：同一 Agent 在无新增证据时不得连续重复调度。
5. 完成前必须给出可解释统计：编排发现数、验证处理数、剩余待验证数。
6. 严禁输出“请用户选择下一步”；若信息不完美，按默认策略继续推进并结束。
7. **语言要求**：所有输出字段（Thought 除外）必须使用简体中文，禁止输出英文段落。
8. 高危候选在最终确认前必须具备 flow 证据（`dataflow_analysis` 或 `controlflow_analysis_light`）。

## 重要原则
1. **你是大脑，不是执行器** - 每一步都要思考
2. **动态调整** - 根据发现调整策略
3. **主动决策** - 不要等待，主动推进
4. **质量优先** - 宁可深入分析几个真实漏洞，不要浅尝辄止
5. **避免重复** - 每个 Agent 通常只需要调度一次，如果结果不理想，尝试其他 Agent 或直接完成审计
6. **禁止交互漂移** - 不能向用户追问“是否继续/二选一”，必须按默认策略自主完成
7. **默认输出完整修复信息** - 汇总阶段默认同时包含修复说明与补丁片段建议
8. **队列优先** - 优先验证队列中的漏洞，确保所有发现都被验证

## 处理子 Agent 结果
- 子 Agent 返回的 Observation 包含它们的分析结果
- 即使结果看起来不完整，也要基于已有信息继续推进
- 不要反复调度同一个 Agent 期望得到不同结果
- 如果 recon 完成后，应该调度 analysis 进行深度分析
- **如果 analysis 完成后，检查队列状态并验证所有待验证漏洞**
- 如果没有更多工作要做，使用 finish 结束审计

现在，基于项目信息开始你的审计工作！"""


@dataclass
class AgentStep:
    """执行步骤"""
    thought: str
    action: str
    action_input: Dict[str, Any]
    observation: Optional[str] = None
    sub_agent_result: Optional[AgentResult] = None


class OrchestratorAgent(BaseAgent):
    """
    编排 Agent - LLM 驱动 ReAct 模式

    - LLM 在每轮中输出 Thought/Action/Action Input
    - Orchestrator 执行动作并反馈 Observation
    - 持续迭代直到 LLM 输出 finish
    """
    
    def __init__(
        self,
        llm_service,
        tools: Dict[str, Any],
        event_emitter=None,
        sub_agents: Optional[Dict[str, BaseAgent]] = None,
        tracer=None,
    ):
        # 组合增强的系统提示词，注入多Agent协作规则和核心安全原则
        full_system_prompt = f"{ORCHESTRATOR_SYSTEM_PROMPT}\n\n{CORE_SECURITY_PRINCIPLES}\n\n{MULTI_AGENT_RULES}"
        
        config = AgentConfig(
            name="Orchestrator",
            agent_type=AgentType.ORCHESTRATOR,
            pattern=AgentPattern.REACT,  # 改为 ReAct 模式！
            max_iterations=20,
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)
        
        self.sub_agents = sub_agents or {}
        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[AgentStep] = []
        self._all_findings: List[Dict] = []
        
        #  Tracer 遥测支持
        self.tracer = tracer

        #  存储运行时上下文，用于传递给子 Agent
        self._runtime_context: Dict[str, Any] = {}

        #  跟踪已调度的 Agent 任务，避免重复调度
        self._dispatched_tasks: Dict[str, int] = {}  # agent_name -> dispatch_count

        #  保存各个 Agent 的完整结果，用于传递给后续 Agent
        self._agent_results: Dict[str, Dict[str, Any]] = {}  # agent_name -> full result data

        #  保存各个 Agent 返回的 TaskHandoff，用于 Agent 间通信
        self._agent_handoffs: Dict[str, TaskHandoff] = {}  # agent_name -> TaskHandoff
        self._phase_planning_applied: Dict[str, bool] = {}
        self._verified_queue_fingerprints: set[str] = set()
        self._recon_queue_snapshot: Dict[str, Any] = {}
        self._last_recon_risk_point: Optional[Dict[str, Any]] = None
    
    def register_sub_agent(self, name: str, agent: BaseAgent):
        """注册子 Agent"""
        self.sub_agents[name] = agent

    def _dedup_findings(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Best-effort dedup to keep deterministic persistence stable.

        Key: (file_path, line_start, vulnerability_type)
        """
        if not isinstance(findings, list) or not findings:
            return []
        out: List[Dict[str, Any]] = []
        seen: set[tuple[str, int, str]] = set()
        for item in findings:
            if not isinstance(item, dict):
                continue
            fp = str(item.get("file_path") or "").strip()
            vt = str(item.get("vulnerability_type") or "").strip()
            try:
                ln = int(item.get("line_start") or 0)
            except Exception:
                ln = 0
            key = (fp, ln, vt)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    @staticmethod
    def _build_queue_fingerprint(finding: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(finding, dict):
            return None
        file_path = str(finding.get("file_path") or "").strip().lower()
        vulnerability_type = str(finding.get("vulnerability_type") or "").strip().lower()
        title = str(finding.get("title") or "").strip().lower()
        try:
            line_start = int(finding.get("line_start") or finding.get("line") or 0)
        except Exception:
            line_start = 0
        if not file_path and line_start <= 0 and not title:
            return None
        return f"{file_path}|{line_start}|{vulnerability_type}|{title}"

    def _infer_verification_dispatch_reason(
        self,
        dispatch_observation: str,
        verification_payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """从调度返回文本与运行诊断中提取 Verification 失败原因。"""
        payload = verification_payload if isinstance(verification_payload, dict) else {}
        run_error = str(payload.get("_run_error") or "").strip()
        if run_error:
            lowered = run_error.lower()
            if "取消" in run_error or "cancel" in lowered:
                return "verification_cancelled"
            if "超时" in run_error or "timeout" in lowered:
                return "verification_timeout"
            return "verification_agent_error"

        todo_summary = payload.get("verification_todo_summary")
        if isinstance(todo_summary, dict):
            blocked_reasons = todo_summary.get("blocked_reasons_top")
            if isinstance(blocked_reasons, list) and blocked_reasons:
                first = blocked_reasons[0]
                if isinstance(first, dict):
                    reason = str(first.get("reason") or "").strip()
                else:
                    reason = str(first).strip()
                if reason:
                    return f"verification_blocked:{reason}"

        text = str(dispatch_observation or "")
        lowered = text.lower()
        if "执行超时" in text or "timeout" in lowered:
            return "verification_timeout"
        if "执行取消" in text or "任务已取消" in text or "cancel" in lowered:
            return "verification_cancelled"
        if "执行失败" in text or "错误" in text:
            return "verification_agent_error"
        return None

    def _build_degraded_verified_findings(
        self,
        analysis_candidates: List[Dict[str, Any]],
        degraded_reason: str,
    ) -> List[Dict[str, Any]]:
        """
        在 Verification 重试耗尽时，用 Analysis 候选生成可入库的降级验证结果。
        """
        if not isinstance(analysis_candidates, list) or not analysis_candidates:
            return []

        degraded_findings: List[Dict[str, Any]] = []
        for candidate in analysis_candidates:
            if not isinstance(candidate, dict):
                continue

            file_path = str(candidate.get("file_path") or "").strip()
            if not file_path:
                continue
            try:
                line_start = int(candidate.get("line_start") or candidate.get("line") or 0)
            except Exception:
                line_start = 0
            if line_start <= 0:
                continue
            try:
                line_end = int(candidate.get("line_end") or line_start)
            except Exception:
                line_end = line_start
            if line_end < line_start:
                line_end = line_start

            description_text = str(candidate.get("description") or "").strip()
            snippet_text = str(candidate.get("code_snippet") or "").strip()
            evidence_lines = [
                f"Verification 阶段降级: {degraded_reason}",
                "基于 Analysis 候选证据生成 likely 结论。",
                f"证据位置: {file_path}:{line_start}-{line_end}",
            ]
            if description_text:
                evidence_lines.append(f"Analysis 描述: {description_text[:800]}")
            if snippet_text:
                evidence_lines.append(f"Analysis 代码片段:\n{snippet_text[:1200]}")
            evidence_text = "\n".join(evidence_lines).strip()

            verification_payload = (
                dict(candidate.get("verification_result"))
                if isinstance(candidate.get("verification_result"), dict)
                else {}
            )
            verification_payload.update(
                {
                    "authenticity": "likely",
                    "verdict": "likely",
                    "reachability": "likely_reachable",
                    "evidence": evidence_text,
                    "verification_details": evidence_text,
                    "verification_evidence": evidence_text,
                    "degraded": True,
                    "degraded_reason": degraded_reason,
                }
            )

            degraded_candidate = {
                **candidate,
                "line_start": line_start,
                "line_end": line_end,
                "verdict": "likely",
                "authenticity": "likely",
                "reachability": "likely_reachable",
                "is_verified": True,
                "degraded": True,
                "degraded_reason": degraded_reason,
                "verification_method": "degraded_from_analysis",
                "verification_details": evidence_text,
                "verification_evidence": evidence_text,
                "verification_result": verification_payload,
                "source": candidate.get("source") or "analysis_degraded_verification",
            }
            normalized = self._normalize_finding(degraded_candidate)
            if isinstance(normalized, dict):
                degraded_findings.append(normalized)

        return self._dedup_findings(degraded_findings)
    
    def cancel(self):
        """
        取消执行 - 同时取消所有子 Agent
        
        重写父类方法，确保取消信号传播到所有子 Agent
        """
        self._cancelled = True
        logger.info(f"[{self.name}] Cancel requested, propagating to {len(self.sub_agents)} sub-agents")
        
        #  传播取消信号到所有子 Agent
        for name, agent in self.sub_agents.items():
            if hasattr(agent, 'cancel'):
                agent.cancel()
                logger.info(f"[{self.name}] Cancelled sub-agent: {name}")
    
    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        执行编排任务 - LLM ReAct 编排
        
        Args:
            input_data: {
                "project_info": 项目信息,
                "config": 审计配置,
                "project_root": 项目根目录,
                "task_id": 任务ID,
            }
        """
        import time
        start_time = time.time()
        project_info = input_data.get("project_info", {}) if isinstance(input_data, dict) else {}
        config = input_data.get("config", {}) if isinstance(input_data, dict) else {}

        # 保存运行时上下文，用于传递给子 Agent
        self._runtime_context = {
            "project_info": project_info,
            "config": config,
            "project_root": input_data.get("project_root", project_info.get("root", ".")),
            "task_id": input_data.get("task_id"),
        }
        if hasattr(self, "configure_trace_logger"):
            try:
                self.configure_trace_logger(self.name, self._runtime_context.get("task_id"))
            except Exception as exc:
                logger.warning("[%s] configure_trace_logger failed: %s", self.name, exc)

        # 初始化状态
        self._steps = []
        self._all_findings = []
        self._agent_results = {}
        self._agent_handoffs = {}
        self._phase_planning_applied = {}
        self._verified_queue_fingerprints = set()
        self._iteration = 0
        self._total_tokens = 0
        self._tool_calls = 0

        # 构建初始消息与对话历史
        initial_message = self._build_initial_message(project_info, config)
        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": initial_message},
        ]

        final_result = None
        error_message = None
        last_dequeued_finding: Optional[Dict[str, Any]] = None
        last_dequeued_fingerprint: Optional[str] = None

        await self.emit_thinking("Orchestrator Agent 启动，LLM 开始自主编排决策...")

        try:
            for iteration in range(self.config.max_iterations):
                if self.is_cancelled:
                    break

                self._iteration = iteration + 1

                if self.is_cancelled:
                    await self.emit_thinking("🛑 任务已取消，停止执行")
                    break

                try:
                    llm_output, tokens_this_round = await self.stream_llm_call(
                        self._conversation_history,
                    )
                except asyncio.CancelledError:
                    logger.info("[%s] LLM call cancelled", self.name)
                    break

                self._total_tokens += tokens_this_round

                if not llm_output or not llm_output.strip():
                    logger.warning("[%s] Empty LLM response", self.name)
                    empty_retry_count = getattr(self, "_empty_retry_count", 0) + 1
                    self._empty_retry_count = empty_retry_count
                    if empty_retry_count >= 5:
                        logger.error("[%s] Too many empty responses, stopping", self.name)
                        error_message = "连续收到空响应，停止编排"
                        await self.emit_event("error", error_message)
                        break

                    await asyncio.sleep(1.0)
                    retry_prompt = f"""收到空响应（第 {empty_retry_count} 次）。请严格按照以下格式输出你的决策：

Thought: [你对当前审计状态的思考]
Action: [dispatch_agent|get_queue_status|dequeue_finding|summarize|finish]
Action Input: {{}}

当前可调度的子 Agent: {list(self.sub_agents.keys())}
当前已收集发现: {len(self._all_findings)} 个

请立即输出你的下一步决策。"""

                    self._conversation_history.append({
                        "role": "user",
                        "content": retry_prompt,
                    })
                    continue

                self._empty_retry_count = 0

                if llm_output.startswith("[API_ERROR:"):
                    match = re.match(r"\[API_ERROR:(\w+)\]\s*(.*)", llm_output)
                    if match:
                        error_type = match.group(1)
                        api_error_message = match.group(2)

                        if error_type == "rate_limit":
                            api_retry_count = getattr(self, "_api_retry_count", 0) + 1
                            self._api_retry_count = api_retry_count
                            if api_retry_count >= 3:
                                logger.error("[%s] Too many rate limit errors, stopping", self.name)
                                await self.emit_event("error", f"API 速率限制重试次数过多: {api_error_message}")
                                break
                            logger.warning("[%s] Rate limit hit, waiting before retry (%s/3)", self.name, api_retry_count)
                            await self.emit_event("warning", f"API 速率限制，等待后重试 ({api_retry_count}/3)")
                            await asyncio.sleep(30)
                            continue

                        if error_type == "quota_exceeded":
                            logger.error("[%s] API quota exceeded: %s", self.name, api_error_message)
                            await self.emit_event("error", f"API 配额已用尽: {api_error_message}")
                            break

                        if error_type == "authentication":
                            logger.error("[%s] API authentication error: %s", self.name, api_error_message)
                            await self.emit_event("error", f"API 认证失败: {api_error_message}")
                            break

                        if error_type == "connection":
                            api_retry_count = getattr(self, "_api_retry_count", 0) + 1
                            self._api_retry_count = api_retry_count
                            if api_retry_count >= 3:
                                logger.error("[%s] Too many connection errors, stopping", self.name)
                                await self.emit_event("error", f"API 连接错误重试次数过多: {api_error_message}")
                                break
                            logger.warning("[%s] Connection error, retrying (%s/3)", self.name, api_retry_count)
                            await self.emit_event("warning", f"API 连接错误，重试中 ({api_retry_count}/3)")
                            await asyncio.sleep(5)
                            continue

                self._api_retry_count = 0

                step = self._parse_llm_response(llm_output)
                if not step:
                    format_retry_count = getattr(self, "_format_retry_count", 0) + 1
                    self._format_retry_count = format_retry_count
                    if format_retry_count >= 3:
                        logger.error("[%s] Too many format errors, stopping", self.name)
                        error_message = "连续格式错误，停止编排"
                        await self.emit_event("error", error_message)
                        break
                    await self.emit_llm_decision("格式错误", "需要重新输出")
                    self._conversation_history.append({"role": "assistant", "content": llm_output})
                    self._conversation_history.append({
                        "role": "user",
                        "content": "请按照规定格式输出：Thought + Action + Action Input",
                    })
                    continue

                self._format_retry_count = 0
                self._steps.append(step)

                if step.thought:
                    await self.emit_llm_thought(step.thought, iteration + 1)

                self._conversation_history.append({"role": "assistant", "content": llm_output})

                action_input = step.action_input if isinstance(step.action_input, dict) else {}

                if step.action == "finish":
                    await self.emit_llm_decision("完成审计", "LLM 判断审计已充分完成")
                    await self.emit_llm_complete(
                        f"编排完成，发现 {len(self._all_findings)} 个漏洞",
                        self._total_tokens,
                    )
                    final_result = action_input
                    break

                if step.action == "dispatch_agent":
                    agent_name = action_input.get("agent", "unknown")
                    task_desc = action_input.get("task", "")

                    recon_point_injected = False
                    if str(agent_name).lower() == "analysis":
                        if not action_input.get("risk_point") and not action_input.get("single_risk_point"):
                            if isinstance(self._last_recon_risk_point, dict):
                                action_input["risk_point"] = self._last_recon_risk_point
                                if not action_input.get("context"):
                                    action_input["context"] = json.dumps(
                                        self._last_recon_risk_point,
                                        ensure_ascii=False,
                                    )
                                recon_point_injected = True
                                logger.info(
                                    "[Orchestrator] Injected Recon 风险点给 Analysis: %s:%s",
                                    self._last_recon_risk_point.get("file_path", ""),
                                    self._last_recon_risk_point.get("line_start", 1),
                                )

                    if (
                        str(agent_name).lower() == "verification"
                        and isinstance(last_dequeued_finding, dict)
                        and not isinstance(action_input.get("finding"), dict)
                    ):
                        action_input["finding"] = last_dequeued_finding
                        if not action_input.get("context"):
                            action_input["context"] = json.dumps(last_dequeued_finding, ensure_ascii=False)

                    verification_finding = (
                        action_input.get("finding")
                        if isinstance(action_input.get("finding"), dict)
                        else None
                    )
                    verification_fingerprint = self._build_queue_fingerprint(verification_finding)
                    if (
                        str(agent_name).lower() == "verification"
                        and verification_fingerprint
                        and verification_fingerprint in self._verified_queue_fingerprints
                    ):

                        observation = (
                            "## Verification 跳过\n\n"
                            "该 finding 已在当前任务中完成验证，已按幂等策略跳过重复调度，"
                            "继续处理队列下一项。"
                        )
                        step.observation = observation
                        await self.emit_llm_decision("跳过重复验证", "队列项命中已验证指纹")
                        await self.emit_llm_observation(observation)
                        self._conversation_history.append({
                            "role": "user",
                            "content": f"Observation:\n{step.observation}",
                        })
                        continue

                    await self.emit_llm_decision(
                        f"调度 {agent_name} Agent",
                        f"任务: {str(task_desc)[:100]}",
                    )
                    await self.emit_llm_action("dispatch_agent", action_input)
                    observation = await self._dispatch_agent(action_input)
                    step.observation = observation

                    if str(agent_name).lower() == "analysis" and recon_point_injected:
                        self._last_recon_risk_point = None

                    if self.is_cancelled:
                        logger.info("[%s] Cancelled after sub-agent dispatch", self.name)
                        break

                    if str(agent_name).lower() == "verification":
                        run_ok = bool(self._agent_results.get("verification", {}).get("_run_success"))
                        if run_ok:
                            candidate_fp = verification_fingerprint or last_dequeued_fingerprint
                            if candidate_fp:
                                self._verified_queue_fingerprints.add(candidate_fp)

                    await self.emit_llm_observation(observation)

                    #  v2.2: 验证 Agent 完成后自动检查队列 - 队列为空则立即终止
                    if str(agent_name).lower() == "verification":
                        try:
                            queue_status_result = await self.execute_tool("get_queue_status", {})
                            queue_data = self._parse_tool_output(queue_status_result)
                            
                            pending_count = 0
                            if isinstance(queue_data, dict):
                                pending_count = queue_data.get("pending_count") or queue_data.get("queue_status", {}).get("current_size") or 0
                            
                            if pending_count == 0:
                                await self.emit_event(
                                    "info",
                                    "🎯 验证 Agent 完成，队列为空，自动终止审计"
                                )
                                logger.info("[Orchestrator] Verification completed and queue is empty, auto-terminating audit")
                                break
                        except Exception as e:
                            logger.warning(f"[Orchestrator] Failed to check queue after verification: {e}")

                elif step.action == "get_queue_status":
                    await self.emit_llm_decision("查询队列状态", "执行 get_queue_status")
                    await self.emit_llm_action("get_queue_status", action_input)
                    queue_observation = await self.execute_tool("get_queue_status", action_input)
                    observation = f"## 队列状态\n\n{queue_observation}"
                    step.observation = observation
                    await self.emit_llm_observation(observation)

                elif step.action == "dequeue_finding":
                    await self.emit_llm_decision("取出队列漏洞", "执行 dequeue_finding")
                    await self.emit_llm_action("dequeue_finding", action_input)
                    dequeue_observation = await self.execute_tool("dequeue_finding", action_input)
                    observation = f"## 队列取出结果\n\n{dequeue_observation}"
                    step.observation = observation

                    parsed_finding = None
                    payload = self._parse_tool_output(dequeue_observation)
                    if isinstance(payload, dict) and isinstance(payload.get("finding"), dict):
                        parsed_finding = payload.get("finding")

                    if isinstance(parsed_finding, dict):
                        last_dequeued_finding = parsed_finding
                        last_dequeued_fingerprint = self._build_queue_fingerprint(parsed_finding)

                    await self.emit_llm_observation(observation)

                elif step.action == "get_recon_risk_queue_status":
                    await self.emit_llm_decision("查询 Recon 队列状态", "执行 get_recon_risk_queue_status")
                    await self.emit_llm_action("get_recon_risk_queue_status", action_input)
                    recon_status_observation = await self.execute_tool("get_recon_risk_queue_status", action_input)
                    step.observation = f"## Recon 风险点队列状态\n\n{recon_status_observation}"
                    parsed_status = self._parse_tool_output(recon_status_observation)
                    if isinstance(parsed_status, dict):
                        self._recon_queue_snapshot = parsed_status
                    await self.emit_llm_observation(step.observation)

                elif step.action == "dequeue_recon_risk_point":
                    await self.emit_llm_decision("取出 Recon 风险点", "执行 dequeue_recon_risk_point")
                    await self.emit_llm_action("dequeue_recon_risk_point", action_input)
                    recon_dequeue_observation = await self.execute_tool("dequeue_recon_risk_point", action_input)
                    payload = self._parse_tool_output(recon_dequeue_observation)
                    risk_point = None
                    queue_remaining = None
                    if isinstance(payload, dict):
                        risk_point = payload.get("risk_point")
                        queue_remaining = payload.get("queue_remaining")
                    if isinstance(risk_point, dict):
                        self._last_recon_risk_point = risk_point
                        risk_repr = json.dumps(risk_point, ensure_ascii=False, indent=2)
                    else:
                        self._last_recon_risk_point = None
                        risk_repr = "队列为空或未返回有效风险点。"
                    queue_info = f"\n队列剩余: {queue_remaining}" if queue_remaining is not None else ""
                    observation = f"## Recon 风险点取出结果\n\n{risk_repr}{queue_info}"
                    step.observation = observation
                    await self.emit_llm_observation(observation)

                elif step.action == "summarize":
                    await self.emit_llm_decision("汇总发现", "LLM 请求查看当前发现汇总")
                    observation = self._summarize_findings()
                    step.observation = observation
                    await self.emit_llm_observation(observation)

                else:
                    observation = (
                        f"未知操作: {step.action}，可用操作: "
                        "dispatch_agent, get_queue_status, dequeue_finding, get_recon_risk_queue_status, dequeue_recon_risk_point, summarize, finish"
                    )
                    step.observation = observation
                    await self.emit_llm_decision("未知操作", observation)

                self._conversation_history.append({
                    "role": "user",
                    "content": f"Observation:\n{step.observation}",
                })

            duration_ms = int((time.time() - start_time) * 1000)

            if self.is_cancelled:
                await self.emit_event(
                    "info",
                    f"🛑 Orchestrator 已取消: {len(self._all_findings)} 个发现, {self._iteration} 轮决策",
                )
                return AgentResult(
                    success=False,
                    error="任务已取消",
                    data={
                        "findings": self._all_findings,
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
                )

            if error_message:
                await self.emit_event("error", f"Orchestrator 失败: {error_message}")
                return AgentResult(
                    success=False,
                    error=error_message,
                    data={
                        "findings": self._all_findings,
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
                )

            verification_payload = self._agent_results.get("verification")
            has_verification_payload = isinstance(verification_payload, dict)
            if has_verification_payload:
                verification_findings = verification_payload.get("findings")
                if not isinstance(verification_findings, list) or not verification_findings:
                    analysis_payload = self._agent_results.get("analysis")
                    analysis_candidates = (
                        analysis_payload.get("findings")
                        if isinstance(analysis_payload, dict)
                        else []
                    )
                    degraded_verified = self._build_degraded_verified_findings(
                        analysis_candidates if isinstance(analysis_candidates, list) else [],
                        "verification_missing_or_empty_findings",
                    )
                    if degraded_verified:
                        for finding in degraded_verified:
                            if isinstance(finding, dict):
                                self._all_findings.append(finding)
                        self._all_findings = self._dedup_findings(
                            [f for f in self._all_findings if isinstance(f, dict)]
                        )
                        logger.warning(
                            "[Orchestrator] verification degraded fallback applied: %s findings",
                            len(degraded_verified),
                        )

            await self.emit_event(
                "info",
                f"🎯 Orchestrator 完成: {len(self._all_findings)} 个发现, {self._iteration} 轮决策",
            )

            logger.info("[Orchestrator] Final result: %s findings collected", len(self._all_findings))
            if len(self._all_findings) == 0:
                logger.warning(
                    "[Orchestrator] No findings collected! Dispatched agents: %s, Iterations: %s",
                    list(self._dispatched_tasks.keys()),
                    self._iteration,
                )

            return AgentResult(
                success=True,
                data={
                    "findings": self._all_findings,
                    "summary": final_result or self._generate_default_summary(),
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
            )

        except Exception as e:
            logger.error("Orchestrator failed: %s", e, exc_info=True)
            return AgentResult(
                success=False,
                error=str(e),
            )
    
    def _build_initial_message(
        self,
        project_info: Dict[str, Any],
        config: Dict[str, Any],
    ) -> str:
        """构建初始消息"""
        structure = project_info.get('structure', {})
        
        #  检查是否是限定范围的审计
        scope_limited = structure.get('scope_limited', False)
        scope_message = structure.get('scope_message', '')
        
        msg = f"""请开始对以下项目进行安全审计。

## 项目信息
- 名称: {project_info.get('name', 'unknown')}
- 语言: {project_info.get('languages', [])}
- 文件数量: {project_info.get('file_count', 0)}
"""

        #  项目级 Markdown 长期记忆（无需 RAG/Embedding）
        markdown_memory = config.get("markdown_memory") if isinstance(config, dict) else None
        if isinstance(markdown_memory, dict):
            shared_mem = str(markdown_memory.get("shared") or "").strip()
            agent_mem = str(markdown_memory.get("orchestrator") or "").strip()
            skills_mem = str(markdown_memory.get("skills") or "").strip()
            if shared_mem or agent_mem or skills_mem:
                msg += f"""
## 项目长期记忆（Markdown，无 RAG）
### shared.md（节选）
{shared_mem or "(空)"}

### orchestrator.md（节选）
{agent_mem or "(空)"}

### skills.md（规范摘要）
{skills_mem or "(空)"}
"""
        
        #  根据是否限定范围显示不同的结构信息
        if scope_limited:
            msg += f"""
## 审计范围限定
**{scope_message}**

### 目标文件列表
"""
            for f in structure.get('files', []):
                msg += f"- {f}\n"
            
            if structure.get('directories'):
                msg += f"""
### 相关目录
{structure.get('directories', [])}
"""
        else:
            msg += f"""
## 目录结构
{json.dumps(structure, ensure_ascii=False, indent=2)}
"""
        
        #  如果配置了 target_files，也明确显示
        target_files = config.get('target_files', [])
        if target_files:
            msg += f"""
## 重要提示
用户指定了 **{len(target_files)}** 个目标文件进行审计。
请确保你的分析集中在这些指定的文件上，不要浪费时间分析其他文件。
"""

        bootstrap_findings = config.get("bootstrap_findings", []) or []
        bootstrap_source = config.get("bootstrap_source") or "none"
        bootstrap_task_id = config.get("bootstrap_task_id")
        if bootstrap_findings:
            msg += f"""
##  候选种子（bootstrap_findings，高优先级）
- 来源: {bootstrap_source}
- 任务ID: {bootstrap_task_id or "N/A"}
- 候选数量: {len(bootstrap_findings)}

请优先围绕这些候选种子进行验证和深挖，然后再扩展全量审计。
候选示例（最多5条）:
{json.dumps(bootstrap_findings[:5], ensure_ascii=False, indent=2)}
"""
            entry_points_cfg = config.get("entry_points") if isinstance(config, dict) else None
            if isinstance(entry_points_cfg, list) and entry_points_cfg:
                msg += f"""
### 入口点（deterministic fallback，最多10条）
{json.dumps(entry_points_cfg[:10], ensure_ascii=False, indent=2)}
"""
            entry_funcs_cfg = config.get("entry_function_names") if isinstance(config, dict) else None
            if isinstance(entry_funcs_cfg, list) and entry_funcs_cfg:
                msg += f"""
### 入口函数名提示（用于调用链约束，最多20个）
{json.dumps(entry_funcs_cfg[:20], ensure_ascii=False, indent=2)}
"""
        elif bootstrap_source and str(bootstrap_source).startswith("degraded"):
            msg += f"""
## OpenGrep 预处理降级提示
预处理状态: {bootstrap_source}
没有可用候选，请按常规流程执行审计。
"""
        
        msg += f"""
## 用户配置
- 目标漏洞: {config.get('target_vulnerabilities', ['all'])}
- 验证级别: {config.get('verification_level', 'sandbox')}
- 排除模式: {config.get('exclude_patterns', [])}

## 可用子 Agent
{', '.join(self.sub_agents.keys()) if self.sub_agents else '(暂无子 Agent)'}

请开始你的审计工作。首先思考应该如何开展，然后决定第一步做什么。"""
        
        return msg
    
    def _parse_llm_response(self, response: str) -> Optional[AgentStep]:
        """解析 LLM 响应"""
        parsed = parse_react_response(
            response,
            final_default={"raw_answer": (response or "").strip()},
            action_input_raw_key="raw",
        )
        if not parsed.action:
            return None

        return AgentStep(
            thought=parsed.thought or "",
            action=parsed.action,
            action_input=parsed.action_input or {},
        )

    def _build_file_planning_template(
        self,
        *,
        agent_name: str,
        task: str,
        context: str,
    ) -> Dict[str, Any]:
        config = self._runtime_context.get("config", {})
        target_files = config.get("target_files") if isinstance(config, dict) else []
        if not isinstance(target_files, list):
            target_files = []
        normalized_targets = [
            str(path).strip()
            for path in target_files
            if str(path).strip()
        ][:20]
        return {
            "template": "planning_with_files",
            "phase": str(agent_name or "").strip().lower(),
            "goal": str(task or "").strip(),
            "task_context": str(context or "").strip(),
            "file_targets": normalized_targets,
            "checklist": [
                "先确认输入面与信任边界，再进入漏洞验证。",
                "优先复用已有证据，禁止重复检索同一输入。",
                "每条结论必须绑定 file_path 与 line_start。",
            ],
            "constraints": [
                "仅分析当前项目范围内文件。",
                "禁止产出未绑定证据的结论。",
                "优先调用 MCP 工具链执行。",
            ],
        }

    def _normalize_single_risk_point(self, candidate: Any) -> Optional[Dict[str, Any]]:
        """标准化单风险点对象。"""
        if not isinstance(candidate, dict):
            return None
        file_path = str(candidate.get("file_path") or "").strip()
        if not file_path:
            return None
        line_raw = candidate.get("line_start")
        if line_raw is None:
            line_raw = candidate.get("line")
        if line_raw is None:
            line_raw = 1
        try:
            line_start = int(line_raw)
        except Exception:
            line_start = 1
        if line_start <= 0:
            line_start = 1
        normalized = dict(candidate)
        normalized["file_path"] = file_path
        normalized["line_start"] = line_start
        normalized.setdefault("description", "")
        normalized.setdefault("title", "")
        return normalized

    def _extract_single_risk_point_for_analysis(
        self,
        *,
        params: Dict[str, Any],
        context: str,
        runtime_config: Dict[str, Any],
        handoff: Optional[TaskHandoff],
    ) -> Optional[Dict[str, Any]]:
        """为 analysis 调度提取唯一风险点。优先级：显式参数 > context JSON > handoff/context_data > bootstrap。"""
        explicit = self._normalize_single_risk_point(
            params.get("single_risk_point") or params.get("risk_point")
        )
        if explicit:
            return explicit

        context_text = str(context or "").strip()
        if context_text:
            try:
                parsed_context = json.loads(context_text)
                if isinstance(parsed_context, dict):
                    parsed_point = self._normalize_single_risk_point(parsed_context)
                    if parsed_point:
                        return parsed_point
            except Exception:
                pass

            path_match = re.search(r"([\\w./-]+\\.(?:py|js|ts|java|go|php|rb|rs|c|cpp|h|hpp|cs))(?:\\s*[:#]\\s*(\\d+))?", context_text)
            if path_match:
                line_token = path_match.group(2)
                line_start = int(line_token) if line_token and line_token.isdigit() else 1
                return {
                    "file_path": path_match.group(1),
                    "line_start": line_start,
                    "description": context_text[:500],
                }

        if handoff and isinstance(handoff.context_data, dict):
            handoff_point = self._normalize_single_risk_point(handoff.context_data.get("single_risk_point"))
            if handoff_point:
                return handoff_point

            candidate_findings = handoff.context_data.get("candidate_findings")
            if isinstance(candidate_findings, list):
                for item in candidate_findings:
                    normalized = self._normalize_single_risk_point(item)
                    if normalized:
                        return normalized

        bootstrap_findings = runtime_config.get("bootstrap_findings")
        if isinstance(bootstrap_findings, list):
            for item in bootstrap_findings:
                normalized = self._normalize_single_risk_point(item)
                if normalized:
                    return normalized

        return None
    
    async def _dispatch_agent(self, params: Dict[str, Any]) -> str:
        """调度子 Agent"""
        agent_name = params.get("agent", "")
        task = params.get("task", "")
        context = params.get("context", "")
        
        logger.debug(f"[Orchestrator] _dispatch_agent 被调用: agent_name='{agent_name}', task='{task[:50]}...'")
        
        #  尝试大小写不敏感匹配
        agent = self.sub_agents.get(agent_name)
        if not agent:
            # 尝试小写匹配
            agent_name_lower = agent_name.lower()
            agent = self.sub_agents.get(agent_name_lower)
            if agent:
                agent_name = agent_name_lower
                logger.debug(f"[Orchestrator] 使用小写匹配: {agent_name}")
        
        if not agent:
            available = list(self.sub_agents.keys())
            logger.warning(f"[Orchestrator] Agent '{agent_name}' 不存在，可用: {available}")
            return f"错误: Agent '{agent_name}' 不存在。可用的 Agent: {available}"
        
        # NOTE: TODO 模式用「每个 todo item 的 attempts」控制重试与降级完成。
        # 不再使用“同一 agent 调度次数上限”作为门禁（否则会阻断 todo 重试逻辑）。
        dispatch_count = self._dispatched_tasks.get(agent_name, 0)
        self._dispatched_tasks[agent_name] = dispatch_count + 1
        is_phase_first_dispatch = dispatch_count == 0
        
        #  设置父 Agent ID 并注册到注册表（动态 Agent 树）
        logger.debug(f"[Orchestrator] 准备调度 {agent_name} Agent, agent._registered={agent._registered}")
        agent.set_parent_id(self._agent_id)
        if hasattr(agent, "configure_trace_logger"):
            try:
                agent.configure_trace_logger(agent.name, self._runtime_context.get("task_id"))
            except Exception as exc:
                logger.warning(
                    "[Orchestrator] configure_trace_logger failed for %s: %s",
                    agent_name,
                    exc,
                )
        logger.debug(f"[Orchestrator] 设置 parent_id 完成，准备注册 {agent_name}")
        agent._register_to_registry(task=task)
        logger.debug(f"[Orchestrator] {agent_name} 注册完成，agent._registered={agent._registered}")
        
        await self.emit_event(
            "dispatch",
            f"📤 调度 {agent_name} Agent: {task[:100]}...",
            agent=agent_name,
            task=task,
        )
        
        self._tool_calls += 1
        
        try:
            #  构建子 Agent 输入 - 传递完整的运行时上下文
            project_info = self._runtime_context.get("project_info", {}).copy()
            # 确保 project_info 包含 root 路径
            if "root" not in project_info:
                project_info["root"] = self._runtime_context.get("project_root", ".")

            #  FIX: 构建完整的 previous_results，包含所有已执行 Agent 的结果
            previous_results = {
                "findings": self._all_findings,  # 传递已收集的发现
            }
            bootstrap_findings = (
                self._runtime_context.get("config", {}).get("bootstrap_findings", [])
                or []
            )
            if bootstrap_findings:
                previous_results["bootstrap_findings"] = bootstrap_findings
                previous_results["bootstrap_source"] = (
                    self._runtime_context.get("config", {}).get("bootstrap_source")
                )
                previous_results["bootstrap_task_id"] = (
                    self._runtime_context.get("config", {}).get("bootstrap_task_id")
                )

            #  将之前 Agent 的完整结果传递给后续 Agent
            for prev_agent, prev_data in self._agent_results.items():
                previous_results[prev_agent] = {"data": prev_data}

            #  构建 TaskHandoff - Agent 间的结构化通信协议
            handoff = self._build_handoff_for_agent(agent_name, task, context)

            runtime_config = (
                dict(self._runtime_context.get("config", {}))
                if isinstance(self._runtime_context.get("config"), dict)
                else {}
            )

            if agent_name == "analysis":
                single_risk_point = self._extract_single_risk_point_for_analysis(
                    params=params,
                    context=context,
                    runtime_config=runtime_config,
                    handoff=handoff,
                )
                runtime_config["single_risk_mode"] = True
                if single_risk_point:
                    runtime_config["single_risk_point"] = single_risk_point
                    runtime_config["target_files"] = [single_risk_point.get("file_path", "")]
                    if isinstance(previous_results, dict):
                        previous_results["bootstrap_findings"] = [single_risk_point]
                    if handoff:
                        if not isinstance(handoff.context_data, dict):
                            handoff.context_data = {}
                        handoff.context_data["single_risk_point"] = single_risk_point
                    logger.info(
                        "[Orchestrator] Analysis 单风险点注入: %s:%s",
                        single_risk_point.get("file_path", ""),
                        single_risk_point.get("line_start", 1),
                    )
                else:
                    logger.warning("[Orchestrator] Analysis 单风险点注入失败：未解析到有效风险点")
            
            #  支持从队列传递单个漏洞（方案A）
            # 如果 params 包含 finding 或 queue_finding，将其添加到 runtime_config
            queue_finding = params.get("finding") or params.get("queue_finding")
            if queue_finding and isinstance(queue_finding, dict):
                runtime_config["queue_finding"] = queue_finding
                logger.info(
                    f"[Orchestrator] 传递队列漏洞给 {agent_name}: "
                    f"{queue_finding.get('title', 'N/A')}"
                )
            
            planning_template_applied = False
            file_planning_payload = params.get("file_planning")
            if not isinstance(file_planning_payload, dict):
                candidate = runtime_config.get("file_planning")
                file_planning_payload = candidate if isinstance(candidate, dict) else None
            if (
                agent_name in {"recon", "analysis", "verification"}
                and is_phase_first_dispatch
                and not isinstance(file_planning_payload, dict)
            ):
                file_planning_payload = self._build_file_planning_template(
                    agent_name=agent_name,
                    task=task,
                    context=context,
                )
                planning_template_applied = True
                self._phase_planning_applied[agent_name] = True
            if isinstance(file_planning_payload, dict):
                runtime_config["file_planning"] = file_planning_payload

            sub_input = {
                "task": task,
                "task_context": context,
                "project_info": project_info,
                "config": runtime_config,
                "project_root": self._runtime_context.get("project_root", "."),
                "task_id": self._runtime_context.get("task_id"),
                "previous_results": previous_results,
                "handoff": handoff.to_dict() if handoff else None,  #  传递 TaskHandoff
                "file_planning": file_planning_payload,
            }

            if planning_template_applied:
                await self.emit_event(
                    "info",
                    f"📐 已自动应用 Planning With Files 模板：{agent_name}",
                    metadata={
                        "planning_template_applied": True,
                        "planning_phase": agent_name,
                    },
                )

            #  执行子 Agent 前检查取消状态
            if self.is_cancelled:
                self._agent_results[agent_name] = {
                    "_run_success": False,
                    "_run_error": "任务已取消",
                }
                return f"## {agent_name} Agent 执行取消\n\n任务已被用户取消"

            #  重试隔离：同一实例在新 attempt 前重置取消状态，避免取消标志粘连。
            if hasattr(agent, "reset_cancellation_state"):
                try:
                    agent.reset_cancellation_state()
                except Exception as exc:
                    logger.warning(
                        "[%s] Failed to reset cancellation state for %s: %s",
                        self.name,
                        agent_name,
                        exc,
                    )

            #  执行子 Agent - 支持取消和超时
            # 使用用户配置的子Agent超时时间
            default_sub_agent_timeout = self._timeout_config.get('sub_agent_timeout', 3000)
            # 设置子 Agent 超时（根据 Agent 类型，recon稍短）
            agent_timeouts = {
                "recon": min(3000, default_sub_agent_timeout), 
                "analysis": default_sub_agent_timeout,
                "verification": default_sub_agent_timeout,
            }
            timeout = agent_timeouts.get(agent_name, default_sub_agent_timeout)

            async def run_with_cancel_check():
                """包装子 Agent 执行，定期检查取消状态"""
                run_task = asyncio.create_task(agent.run(sub_input))
                try:
                    while not run_task.done():
                        if self.is_cancelled:
                            #  传播取消到子 Agent
                            logger.info(f"[{self.name}] Cancelling sub-agent {agent_name} due to parent cancel")
                            if hasattr(agent, 'cancel'):
                                agent.cancel()
                            run_task.cancel()
                            try:
                                await run_task
                            except asyncio.CancelledError:
                                pass
                            raise asyncio.CancelledError("任务已取消")

                        # Use asyncio.wait to poll without cancelling the task
                        done, pending = await asyncio.wait(
                            [run_task],
                            timeout=0.5,
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        if run_task in done:
                            return run_task.result()
                        # If not done, continue loop
                        continue

                    return await run_task
                except asyncio.CancelledError:
                    #  确保子任务被取消
                    if not run_task.done():
                        if hasattr(agent, 'cancel'):
                            agent.cancel()
                        run_task.cancel()
                        try:
                            await run_task
                        except asyncio.CancelledError:
                            pass
                    raise

            try:
                result = await asyncio.wait_for(
                    run_with_cancel_check(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                logger.warning(f"[{self.name}] Sub-agent {agent_name} timed out after {timeout}s")
                self._agent_results[agent_name] = {
                    "_run_success": False,
                    "_run_error": f"sub_agent_timeout:{timeout}s",
                }
                return f"## {agent_name} Agent 执行超时\n\n子 Agent 执行超过 {timeout} 秒，已强制终止。请尝试更具体的任务或使用其他 Agent。"
            except asyncio.CancelledError:
                logger.info(f"[{self.name}] Sub-agent {agent_name} was cancelled")
                self._agent_results[agent_name] = {
                    "_run_success": False,
                    "_run_error": "任务已取消",
                }
                return f"## {agent_name} Agent 执行取消\n\n任务已被用户取消"

            #  执行后再次检查取消状态
            if self.is_cancelled:
                self._agent_results[agent_name] = {
                    "_run_success": False,
                    "_run_error": "任务已取消",
                }
                return f"## {agent_name} Agent 执行中断\n\n任务已被用户取消"

            #  处理子 Agent 结果 - 不同 Agent 返回不同的数据结构
            #  DEBUG: 添加诊断日志
            logger.info(
                f"[Orchestrator] Processing {agent_name} result: success={result.success}, "
                f"data_type={type(result.data).__name__}, "
                f"data_keys={list(result.data.keys()) if isinstance(result.data, dict) else 'N/A'}"
            )

            result_payload: Dict[str, Any] = {}
            if isinstance(result.data, dict):
                result_payload.update(result.data)
            result_payload["_run_success"] = bool(result.success)
            if result.error:
                result_payload["_run_error"] = str(result.error)
            self._agent_results[agent_name] = result_payload
            logger.info(
                "[Orchestrator] Saved %s runtime diagnostics: success=%s, error=%s",
                agent_name,
                bool(result.success),
                result_payload.get("_run_error"),
            )

            if result.success and isinstance(result.data, dict):
                data = result_payload

                #  保存 Agent 返回的 handoff，用于传递给后续 Agent
                if result.handoff:
                    if not hasattr(self, '_agent_handoffs'):
                        self._agent_handoffs = {}
                    self._agent_handoffs[agent_name] = result.handoff
                    logger.info(
                        f"[Orchestrator] Saved {agent_name} handoff: "
                        f"summary={result.handoff.summary[:50]}..."
                    )

                #  CRITICAL FIX: 收集发现 - 支持多种字段名
                # findings 字段通常来自 Analysis/Verification Agent
                # initial_findings 来自 Recon Agent
                raw_findings = data.get("findings", [])
                logger.info(f"[Orchestrator] {agent_name} returned data with {len(raw_findings)} findings in 'findings' field")

                #  ENHANCED: Also check for initial_findings (from Recon) - 改进逻辑
                # 即使 findings 为空列表，也检查 initial_findings
                if "initial_findings" in data:
                    initial = data.get("initial_findings", [])
                    logger.info(f"[Orchestrator] {agent_name} has {len(initial)} initial_findings, types: {[type(f).__name__ for f in initial[:3]]}")
                    for f in initial:
                        if isinstance(f, dict):
                            #  Normalize finding format - 处理 Recon 返回的格式
                            normalized = self._normalize_finding(f)
                            if normalized not in raw_findings:
                                raw_findings.append(normalized)
                                logger.info(f"[Orchestrator] Added dict finding from initial_findings")
                        elif isinstance(f, str) and f.strip():
                            #  FIX: Convert string finding to dict format instead of skipping
                            # Recon Agent 有时候会返回字符串格式的发现
                            # 尝试从字符串中提取文件路径（格式如 "app.py:36 - 描述"）
                            file_path = ""
                            line_start = 0
                            if ":" in f:
                                parts = f.split(":", 1)
                                potential_file = parts[0].strip()
                                # 检查是否像文件路径
                                if "." in potential_file and "/" not in potential_file[:3]:
                                    file_path = potential_file
                                    # 尝试提取行号
                                    if len(parts) > 1:
                                        remaining = parts[1].strip()
                                        line_match = remaining.split()[0] if remaining else ""
                                        if line_match.isdigit():
                                            line_start = int(line_match)

                            string_finding = {
                                "title": f[:100] if len(f) > 100 else f,
                                "description": f,
                                "file_path": file_path,
                                "line_start": line_start,
                                "severity": "medium",  # 默认中等严重度，Analysis 会重新评估
                                "vulnerability_type": "potential_issue",
                                "source": "recon",
                                "needs_verification": True,
                                "confidence": 0.5,  # 较低置信度，需要进一步分析
                            }
                            logger.info(f"[Orchestrator] Converted string finding to dict: {f[:80]}... (file={file_path}, line={line_start})")
                            raw_findings.append(string_finding)
                else:
                    logger.info(f"[Orchestrator] {agent_name} has no 'initial_findings' key in data")

                #  Also check high_risk_areas from Recon for potential findings
                if agent_name == "recon" and "high_risk_areas" in data:
                    high_risk = data.get("high_risk_areas", [])
                    logger.info(f"[Orchestrator] {agent_name} identified {len(high_risk)} high risk areas")
                    #  FIX: 将 high_risk_areas 也转换为发现
                    for area in high_risk:
                        if isinstance(area, str) and area.strip():
                            # 尝试从描述中提取文件路径和漏洞类型
                            file_path = ""
                            line_start = 0
                            vuln_type = "potential_issue"

                            #  FIX: 改进文件路径提取逻辑
                            # 格式1: "file.py:36 - 描述" -> 提取 file.py 和 36
                            # 格式2: "描述性文本" -> 不提取文件路径
                            if ":" in area:
                                parts = area.split(":", 1)
                                potential_file = parts[0].strip()
                                # 只有当 parts[0] 看起来像文件路径时才提取
                                # 文件路径通常包含 . 且没有空格（或只在结尾有扩展名）
                                if ("." in potential_file and
                                    " " not in potential_file and
                                    len(potential_file) < 100 and
                                    any(potential_file.endswith(ext) for ext in ['.py', '.js', '.ts', '.java', '.go', '.php', '.rb', '.c', '.cpp', '.h'])):
                                    file_path = potential_file
                                    # 尝试提取行号
                                    if len(parts) > 1:
                                        remaining = parts[1].strip()
                                        line_match = remaining.split()[0] if remaining else ""
                                        if line_match.isdigit():
                                            line_start = int(line_match)

                            # 推断漏洞类型
                            area_lower = area.lower()
                            if "command" in area_lower or "命令" in area_lower or "subprocess" in area_lower:
                                vuln_type = "command_injection"
                            elif "sql" in area_lower:
                                vuln_type = "sql_injection"
                            elif "xss" in area_lower:
                                vuln_type = "xss"
                            elif "path" in area_lower or "traversal" in area_lower or "路径" in area_lower:
                                vuln_type = "path_traversal"
                            elif "ssrf" in area_lower:
                                vuln_type = "ssrf"
                            elif "secret" in area_lower or "密钥" in area_lower or "key" in area_lower:
                                vuln_type = "hardcoded_secret"

                            high_risk_finding = {
                                "title": area[:100] if len(area) > 100 else area,
                                "description": area,
                                "file_path": file_path,
                                "line_start": line_start,
                                "severity": "high",  # 高风险区域默认高严重度
                                "vulnerability_type": vuln_type,
                                "source": "recon_high_risk",
                                "needs_verification": True,
                                "confidence": 0.6,
                            }
                            raw_findings.append(high_risk_finding)
                            logger.info(f"[Orchestrator] Converted high_risk_area to finding: {area[:60]}... (file={file_path}, type={vuln_type})")

                #  初始化 valid_findings，确保后续代码可以访问
                valid_findings = []

                if raw_findings:
                    # 只添加字典格式的发现
                    valid_findings = [f for f in raw_findings if isinstance(f, dict)]

                    logger.info(f"[Orchestrator] {agent_name} returned {len(valid_findings)} valid findings")

                    #  ENHANCED: Merge findings with better deduplication
                    for new_f in valid_findings:
                        # Normalize the finding first
                        normalized_new = self._normalize_finding(new_f)
                        if not normalized_new:
                            logger.warning("[Orchestrator] Skip invalid normalized finding (None)")
                            continue

                        has_file_location = bool(normalized_new.get("file_path"))
                        has_context_hint = bool(
                            normalized_new.get("line_start")
                            or normalized_new.get("line_end")
                            or normalized_new.get("code_snippet")
                        )
                        if not has_file_location or not has_context_hint:
                            logger.info(
                                "[Orchestrator] Skip candidate finding without required location/context: "
                                f"title={normalized_new.get('title', 'N/A')[:80]}"
                            )
                            continue

                        # Create fingerprint for deduplication (file + description similarity)
                        new_file = normalized_new.get("file_path", "").lower().strip()
                        new_desc = (normalized_new.get("description", "") or "").lower()[:100]
                        new_type = (normalized_new.get("vulnerability_type", "") or "").lower()
                        new_line = normalized_new.get("line_start") or normalized_new.get("line", 0)

                        # Check if exists (more flexible matching)
                        found = False
                        for i, existing_f in enumerate(self._all_findings):
                            existing_file = (existing_f.get("file_path", "") or existing_f.get("file", "")).lower().strip()
                            existing_desc = (existing_f.get("description", "") or "").lower()[:100]
                            existing_type = (existing_f.get("vulnerability_type", "") or existing_f.get("type", "")).lower()
                            existing_line = existing_f.get("line_start") or existing_f.get("line", 0)

                            # Match if same file AND (same line OR similar description OR same vulnerability type)
                            same_file = new_file and existing_file and (
                                new_file == existing_file or
                                new_file.endswith(existing_file) or
                                existing_file.endswith(new_file)
                            )
                            same_line = new_line and existing_line and new_line == existing_line
                            similar_desc = new_desc and existing_desc and (
                                new_desc in existing_desc or existing_desc in new_desc
                            )
                            same_type = new_type and existing_type and (
                                new_type == existing_type or
                                (new_type in existing_type) or (existing_type in new_type)
                            )

                            if same_file and (same_line or similar_desc or same_type):
                                # Update existing with new info (e.g. verification results)
                                #  FIX: Smart merge - don't overwrite good data with empty values
                                merged = dict(existing_f)  # Start with existing data
                                for key, value in normalized_new.items():
                                    # Only overwrite if new value is meaningful
                                    if value is not None and value != "" and value != 0:
                                        merged[key] = value
                                    elif key not in merged or merged[key] is None:
                                        # Fill in missing fields even with empty values
                                        merged[key] = value

                                # Keep the better title
                                if normalized_new.get("title") and len(normalized_new.get("title", "")) > len(existing_f.get("title", "")):
                                    merged["title"] = normalized_new["title"]
                                # Keep verified status if either is verified
                                if existing_f.get("is_verified") or normalized_new.get("is_verified"):
                                    merged["is_verified"] = True
                                #  FIX: Preserve non-zero line numbers
                                if existing_f.get("line_start") and not normalized_new.get("line_start"):
                                    merged["line_start"] = existing_f["line_start"]
                                #  FIX: Preserve vulnerability_type
                                if existing_f.get("vulnerability_type") and not normalized_new.get("vulnerability_type"):
                                    merged["vulnerability_type"] = existing_f["vulnerability_type"]

                                self._all_findings[i] = merged
                                found = True
                                logger.info(f"[Orchestrator] Merged finding: {new_file}:{merged.get('line_start', 0)} ({merged.get('vulnerability_type', '')})")
                                break

                        if not found:
                            self._all_findings.append(normalized_new)
                            logger.info(f"[Orchestrator] Added new finding: {new_file}:{new_line} ({new_type})")

                    logger.info(f"[Orchestrator] Total findings now: {len(self._all_findings)}")
                else:
                    logger.info(f"[Orchestrator] {agent_name} returned no findings")
                
                await self.emit_event(
                    "dispatch_complete",
                    f"{agent_name} Agent 完成",
                    agent=agent_name,
                    findings_count=len(self._all_findings),  #  Use total findings count
                )
                
                #  根据 Agent 类型构建不同的观察结果
                if agent_name == "recon":
                    # Recon Agent 返回项目信息
                    observation = f"""## Recon Agent 执行结果

**状态**: 成功
**迭代次数**: {result.iterations}
**耗时**: {result.duration_ms}ms

### 项目结构
{json.dumps(data.get('project_structure', {}), ensure_ascii=False, indent=2)}

### 技术栈
- 语言: {data.get('tech_stack', {}).get('languages', [])}
- 框架: {data.get('tech_stack', {}).get('frameworks', [])}
- 数据库: {data.get('tech_stack', {}).get('databases', [])}

### 入口点 ({len(data.get('entry_points', []))} 个)
"""
                    for i, ep in enumerate(data.get('entry_points', [])[:10]):
                        if isinstance(ep, dict):
                            observation += f"{i+1}. [{ep.get('type', 'unknown')}] {ep.get('file', '')}:{ep.get('line', '')}\n"
                    
                    observation += f"""
### 高风险区域
{data.get('high_risk_areas', [])}

### 初步发现 ({len(data.get('initial_findings', []))} 个)
"""
                    for finding in data.get('initial_findings', [])[:5]:
                        if isinstance(finding, str):
                            observation += f"- {finding}\n"
                        elif isinstance(finding, dict):
                            observation += f"- {finding.get('title', finding)}\n"
                    
                else:
                    # Analysis/Verification Agent 返回漏洞发现
                    observation = f"""## {agent_name} Agent 执行结果

**状态**: 成功
**发现数量**: {len(valid_findings)}
**迭代次数**: {result.iterations}
**耗时**: {result.duration_ms}ms

### 发现摘要
"""
                    for i, f in enumerate(valid_findings[:10]):
                        if not isinstance(f, dict):
                            continue
                        observation += f"""
{i+1}. [{f.get('severity', 'unknown')}] {f.get('title', 'Unknown')}
   - 类型: {f.get('vulnerability_type', 'unknown')}
   - 文件: {f.get('file_path', 'unknown')}
   - 描述: {f.get('description', '')[:200]}...
"""

                    if len(valid_findings) > 10:
                        observation += f"\n... 还有 {len(valid_findings) - 10} 个发现"
                
                if data.get("summary"):
                    observation += f"\n\n### Agent 总结\n{data['summary']}"
                
                return observation
            else:
                return f"## {agent_name} Agent 执行失败\n\n错误: {result.error}"
                
        except Exception as e:
            logger.error(f"Sub-agent dispatch failed: {e}", exc_info=True)
            self._agent_results[agent_name] = {
                "_run_success": False,
                "_run_error": str(e),
            }
            return f"## 调度失败\n\n错误: {str(e)}"

    def _parse_tool_output(self, raw_output: Any) -> Any:
        if isinstance(raw_output, dict) or isinstance(raw_output, list):
            return raw_output
        if not isinstance(raw_output, str):
            return raw_output or {}
        trimmed = raw_output.strip()
        if not trimmed:
            return {}
        try:
            return json.loads(trimmed)
        except Exception:
            try:
                return ast.literal_eval(trimmed)
            except Exception:
                return {}

    def _validate_file_path(self, file_path: str) -> bool:
        """
         v2.1: 验证文件路径是否真实存在

        Args:
            file_path: 相对或绝对文件路径（可能包含行号，如 "app.py:36"）

        Returns:
            bool: 文件是否存在
        """
        if not file_path or not file_path.strip():
            return False

        # 获取项目根目录
        project_root = self._runtime_context.get("project_root", "")
        if not project_root:
            # 没有项目根目录时，无法验证，返回 True 以避免误判
            return True

        # 清理路径（移除可能的行号）
        clean_path = file_path.split(":")[0].strip() if ":" in file_path else file_path.strip()

        # 尝试相对路径
        full_path = os.path.join(project_root, clean_path)
        if os.path.isfile(full_path):
            return True

        # 尝试绝对路径
        if os.path.isabs(clean_path) and os.path.isfile(clean_path):
            return True

        return False

    def _build_structured_title(self, finding: Dict[str, Any], fallback: Optional[str] = None) -> str:
        return build_cn_structured_title(
            file_path=finding.get("file_path"),
            function_name=finding.get("function_name"),
            vulnerability_type=finding.get("vulnerability_type"),
            title=finding.get("title"),
            description=finding.get("description"),
            code_snippet=finding.get("code_snippet"),
            fallback_vulnerability_name=fallback,
        )

    def _is_structured_cn_title(self, title: str) -> bool:
        return is_structured_cn_title(title)

    def _normalize_finding(self, finding: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        标准化发现格式

        不同 Agent 可能返回不同格式的发现，这个方法将它们标准化为统一格式

         v2.1: 添加文件路径验证，返回 None 表示发现无效（幻觉）
        """
        normalized = dict(finding)  # 复制原始数据

        #  处理 location 字段 -> file_path + line_start
        if "location" in normalized and "file_path" not in normalized:
            location = normalized["location"]
            if isinstance(location, str) and ":" in location:
                parts = location.split(":")
                normalized["file_path"] = parts[0]
                try:
                    normalized["line_start"] = int(parts[1])
                except (ValueError, IndexError):
                    pass
            elif isinstance(location, str):
                normalized["file_path"] = location

        #  处理 file 字段 -> file_path
        if "file" in normalized and "file_path" not in normalized:
            normalized["file_path"] = normalized["file"]

        #  处理 line 字段 -> line_start
        if "line" in normalized and "line_start" not in normalized:
            normalized["line_start"] = normalized["line"]

        #  处理 type 字段 -> vulnerability_type
        if "type" in normalized and "vulnerability_type" not in normalized:
            # 不是所有 type 都是漏洞类型，比如 "Vulnerability" 只是标记
            type_val = normalized["type"]
            if type_val and type_val.lower() not in ["vulnerability", "finding", "issue"]:
                normalized["vulnerability_type"] = type_val
            elif "description" in normalized:
                # 尝试从描述中推断漏洞类型
                desc = normalized["description"].lower()
                if "command injection" in desc or "rce" in desc or "system(" in desc:
                    normalized["vulnerability_type"] = "command_injection"
                elif "sql injection" in desc or "sqli" in desc:
                    normalized["vulnerability_type"] = "sql_injection"
                elif "xss" in desc or "cross-site scripting" in desc:
                    normalized["vulnerability_type"] = "xss"
                elif "path traversal" in desc or "directory traversal" in desc:
                    normalized["vulnerability_type"] = "path_traversal"
                elif "ssrf" in desc:
                    normalized["vulnerability_type"] = "ssrf"
                elif "xxe" in desc:
                    normalized["vulnerability_type"] = "xxe"
                else:
                    normalized["vulnerability_type"] = "other"

        #  确保 severity 字段存在且为小写
        if "severity" in normalized:
            normalized["severity"] = str(normalized["severity"]).lower()
        else:
            normalized["severity"] = "medium"

        #  处理 risk 字段 -> severity
        if "risk" in normalized and "severity" not in normalized:
            normalized["severity"] = str(normalized["risk"]).lower()

        # 生成/规范 title（三段式中文标题）
        title_value = str(normalized.get("title") or "").strip()
        if not self._is_structured_cn_title(title_value):
            normalized["title"] = self._build_structured_title(normalized, fallback=title_value)
        normalized["display_title"] = normalized.get("title")

        # 统一细化类型，避免保留“安全漏洞/other”。
        profile = resolve_vulnerability_profile(
            normalized.get("vulnerability_type"),
            title=normalized.get("title"),
            description=normalized.get("description"),
            code_snippet=normalized.get("code_snippet"),
        )
        normalized["vulnerability_type"] = profile.get("key", "other")

        #  处理 code 字段 -> code_snippet
        if "code" in normalized and "code_snippet" not in normalized:
            normalized["code_snippet"] = normalized["code"]

        #  处理 recommendation -> suggestion
        if "recommendation" in normalized and "suggestion" not in normalized:
            normalized["suggestion"] = normalized["recommendation"]

        #  处理 impact -> 添加到 description
        if "impact" in normalized and normalized.get("description"):
            if "impact" not in normalized["description"].lower():
                normalized["description"] += f"\n\nImpact: {normalized['impact']}"

        #  v2.1: 验证文件路径存在性
        file_path = normalized.get("file_path", "")
        if file_path and not self._validate_file_path(file_path):
            logger.warning(
                f"[Orchestrator] 🚫 过滤幻觉发现: 文件不存在 '{file_path}' "
                f"(title: {normalized.get('title', 'N/A')[:50]})"
            )
            return None  # 返回 None 表示发现无效

        return normalized

    def _summarize_findings(self) -> str:
        """汇总当前发现"""
        if not self._all_findings:
            return "目前还没有发现任何漏洞。"
        
        # 统计
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        type_counts = {}
        
        for f in self._all_findings:
            if not isinstance(f, dict):
                continue
                
            sev = f.get("severity", "low")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
            
            vtype = f.get("vulnerability_type", "other")
            type_counts[vtype] = type_counts.get(vtype, 0) + 1
        
        summary = f"""## 当前发现汇总

**总计**: {len(self._all_findings)} 个漏洞

### 严重程度分布
- Critical: {severity_counts['critical']}
- High: {severity_counts['high']}
- Medium: {severity_counts['medium']}
- Low: {severity_counts['low']}

### 漏洞类型分布
"""
        for vtype, count in type_counts.items():
            summary += f"- {vtype}: {count}\n"
        
        summary += "\n### 详细列表\n"
        for i, f in enumerate(self._all_findings):
            if isinstance(f, dict):
                summary += f"{i+1}. [{f.get('severity')}] {f.get('title')} ({f.get('file_path')})\n"
        
        return summary
    
    def _generate_default_summary(self) -> Dict[str, Any]:
        """生成默认摘要"""
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        
        for f in self._all_findings:
            if isinstance(f, dict):
                sev = f.get("severity", "low")
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
        
        return {
            "total_findings": len(self._all_findings),
            "severity_distribution": severity_counts,
            "conclusion": "审计完成（未通过 LLM 生成结论）",
        }
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """获取对话历史"""
        return self._conversation_history

    def get_steps(self) -> List[AgentStep]:
        """获取执行步骤"""
        return self._steps

    def _build_handoff_for_agent(
        self,
        target_agent: str,
        task: str,
        context: str,
    ) -> Optional[TaskHandoff]:
        """
        为目标 Agent 构建 TaskHandoff

        根据目标 Agent 类型，从之前的 Agent 结果中提取相关信息，
        构建结构化的任务交接协议。

        优先使用前序 Agent 返回的 handoff（如果存在），否则从 _agent_results 构建。

        Args:
            target_agent: 目标 Agent 名称 (recon/analysis/verification)
            task: 任务描述
            context: 任务上下文

        Returns:
            TaskHandoff 对象，如果没有前序信息则返回 None
        """
        #  如果是第一个 Agent (recon)，没有前序信息
        if target_agent == "recon" and not self._agent_results:
            return None

        #  优先使用前序 Agent 返回的 handoff
        # Analysis Agent 需要 Recon 的 handoff
        if target_agent == "analysis" and "recon" in self._agent_handoffs:
            recon_handoff = self._agent_handoffs["recon"]
            logger.info(f"[Orchestrator] Using Recon's handoff for Analysis Agent")
            context_data = dict(recon_handoff.context_data)
            key_findings = list(recon_handoff.key_findings)
            bootstrap_findings = (
                self._runtime_context.get("config", {}).get("bootstrap_findings", [])
                or []
            )
            if bootstrap_findings:
                context_data["bootstrap_findings"] = bootstrap_findings[:20]
                context_data["bootstrap_source"] = (
                    self._runtime_context.get("config", {}).get("bootstrap_source")
                )
                context_data["bootstrap_task_id"] = (
                    self._runtime_context.get("config", {}).get("bootstrap_task_id")
                )
                for item in bootstrap_findings[:10]:
                    if isinstance(item, dict):
                        key_findings.append(item)
            # 更新目标 Agent
            return TaskHandoff(
                from_agent=recon_handoff.from_agent,
                to_agent=target_agent,
                summary=recon_handoff.summary,
                work_completed=recon_handoff.work_completed,
                key_findings=key_findings,
                insights=recon_handoff.insights,
                suggested_actions=recon_handoff.suggested_actions,
                attention_points=recon_handoff.attention_points,
                priority_areas=recon_handoff.priority_areas,
                context_data=context_data,
                confidence=recon_handoff.confidence,
            )

        # Verification Agent 需要 Analysis 的 handoff（也可能需要 Recon 的信息）
        if target_agent == "verification" and "analysis" in self._agent_handoffs:
            analysis_handoff = self._agent_handoffs["analysis"]
            logger.info(f"[Orchestrator] Using Analysis's handoff for Verification Agent")

            # 合并 Recon 的上下文信息（如果有）
            context_data = dict(analysis_handoff.context_data)
            key_findings: List[Dict[str, Any]] = []
            if "recon" in self._agent_handoffs:
                recon_handoff = self._agent_handoffs["recon"]
                context_data["recon_tech_stack"] = recon_handoff.context_data.get("tech_stack", {})
                context_data["recon_entry_points"] = recon_handoff.context_data.get("entry_points", [])
            bootstrap_findings = self._runtime_context.get("config", {}).get("bootstrap_findings", []) or []
            analysis_findings = self._agent_results.get("analysis", {}).get("findings", []) if isinstance(self._agent_results.get("analysis"), dict) else []

            candidates: List[Dict[str, Any]] = []
            for source in (analysis_findings, bootstrap_findings):
                if not isinstance(source, list):
                    continue
                for item in source:
                    if isinstance(item, dict):
                        candidates.append(item)

            dedup_candidates: List[Dict[str, Any]] = []
            seen_keys: set[tuple[str, int, str, str]] = set()
            for candidate in candidates:
                file_path = str(candidate.get("file_path") or "").strip().lower()
                try:
                    line_start = int(candidate.get("line_start") or candidate.get("line") or 0)
                except Exception:
                    line_start = 0
                vuln_type = str(candidate.get("vulnerability_type") or "").strip().lower()
                title = str(candidate.get("title") or "").strip().lower()
                key = (file_path, line_start, vuln_type, title)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                dedup_candidates.append(candidate)

            context_data["bootstrap_findings"] = bootstrap_findings[:50] if isinstance(bootstrap_findings, list) else []
            context_data["candidate_findings"] = dedup_candidates[:100]
            context_data["bootstrap_source"] = self._runtime_context.get("config", {}).get("bootstrap_source")
            context_data["bootstrap_task_id"] = self._runtime_context.get("config", {}).get("bootstrap_task_id")
            key_findings.extend(dedup_candidates[:20])

            summary_suffix = (
                f"；验证范围：全量候选 {len(dedup_candidates)} 条（analysis + bootstrap）"
                if dedup_candidates
                else "；本次无可验证候选，建议直接返回空验证结果"
            )
            return TaskHandoff(
                from_agent=analysis_handoff.from_agent,
                to_agent=target_agent,
                summary=f"{analysis_handoff.summary}{summary_suffix}",
                work_completed=analysis_handoff.work_completed,
                key_findings=key_findings,
                insights=analysis_handoff.insights,
                suggested_actions=analysis_handoff.suggested_actions,
                attention_points=analysis_handoff.attention_points,
                priority_areas=analysis_handoff.priority_areas,
                context_data=context_data,
                confidence=analysis_handoff.confidence,
            )

        #  如果没有前序 Agent 的 handoff，从 _agent_results 构建（回退逻辑）
        logger.info(f"[Orchestrator] Building handoff from _agent_results for {target_agent}")

        #  收集工作摘要和关键发现
        work_completed = []
        key_findings = []
        insights = []
        suggested_actions = []
        attention_points = []
        priority_areas = []
        context_data = {}
        bootstrap_findings = (
            self._runtime_context.get("config", {}).get("bootstrap_findings", [])
            or []
        )
        if bootstrap_findings:
            context_data["bootstrap_findings"] = bootstrap_findings[:20]
            context_data["bootstrap_source"] = (
                self._runtime_context.get("config", {}).get("bootstrap_source")
            )
            context_data["bootstrap_task_id"] = (
                self._runtime_context.get("config", {}).get("bootstrap_task_id")
            )
            for finding in bootstrap_findings[:10]:
                if isinstance(finding, dict):
                    key_findings.append(finding)

        # 从 Recon 结果构建 handoff（给 Analysis）
        if target_agent == "analysis" and "recon" in self._agent_results:
            recon_data = self._agent_results["recon"]

            work_completed.append("完成项目信息收集和技术栈识别")

            # 提取技术栈信息
            tech_stack = recon_data.get("tech_stack", {})
            if tech_stack:
                work_completed.append(
                    f"识别技术栈: {', '.join(tech_stack.get('languages', []))} / "
                    f"{', '.join(tech_stack.get('frameworks', []))}"
                )
                context_data["tech_stack"] = tech_stack

            # 提取入口点
            entry_points = recon_data.get("entry_points", [])
            if entry_points:
                work_completed.append(f"发现 {len(entry_points)} 个入口点")
                context_data["entry_points"] = entry_points[:20]  # 限制数量
                for ep in entry_points[:10]:
                    if isinstance(ep, dict):
                        attention_points.append(
                            f"[{ep.get('type', 'unknown')}] {ep.get('file', '')}:{ep.get('line', '')}"
                        )

            # 提取高风险区域
            high_risk_areas = recon_data.get("high_risk_areas", [])
            if high_risk_areas:
                insights.append(f"发现 {len(high_risk_areas)} 个高风险区域需要重点分析")
                priority_areas.extend(high_risk_areas[:15])

            # 提取初步发现
            initial_findings = recon_data.get("initial_findings", [])
            if initial_findings:
                for f in initial_findings[:10]:
                    if isinstance(f, dict):
                        key_findings.append(f)
                        suggested_actions.append({
                            "action": "deep_analysis",
                            "target": f.get("file_path", ""),
                            "reason": f.get("title", "需要深入分析")
                        })

            # 推荐的工具
            recommended_tools = recon_data.get("recommended_tools", {})
            if recommended_tools:
                context_data["recommended_tools"] = recommended_tools

        # 从 Analysis 结果构建 handoff（给 Verification）
        elif target_agent == "verification":
            # 先添加 Recon 的信息（如果有）
            if "recon" in self._agent_results:
                recon_data = self._agent_results["recon"]
                context_data["tech_stack"] = recon_data.get("tech_stack", {})
                context_data["entry_points"] = recon_data.get("entry_points", [])[:10]

            if "analysis" in self._agent_results:
                work_completed.append("完成代码深度分析（Verification 将执行全量候选验证）")

            # 也包含已有的发现（可能来自多个 Agent）
            if self._all_findings:
                context_data["all_findings"] = self._all_findings[:20]

            bootstrap_items = context_data.get("bootstrap_findings", [])
            analysis_items = (
                self._agent_results.get("analysis", {}).get("findings", [])
                if isinstance(self._agent_results.get("analysis"), dict)
                else []
            )
            candidates: List[Dict[str, Any]] = []
            for source in (analysis_items, bootstrap_items):
                if not isinstance(source, list):
                    continue
                for item in source:
                    if isinstance(item, dict):
                        candidates.append(item)
            context_data["candidate_findings"] = candidates[:100]
            key_findings = candidates[:20]

        # 如果没有任何工作记录，说明没有前序信息
        if not work_completed and not key_findings:
            return None

        # 构建 TaskHandoff
        summary = f"任务: {task[:100]}"
        if work_completed:
            summary = f"前序工作已完成: {', '.join(work_completed[:3])}"

        return TaskHandoff(
            from_agent="Orchestrator",
            to_agent=target_agent,
            summary=summary,
            work_completed=work_completed,
            key_findings=key_findings,
            insights=insights,
            suggested_actions=suggested_actions,
            attention_points=attention_points,
            priority_areas=priority_areas,
            context_data=context_data,
            confidence=0.85,
        )
