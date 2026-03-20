"""
BusinessLogicAnalysisAgent (业务逻辑分析层) - LLM 驱动版

深度分析来自 bl_risk_queue 的业务逻辑风险点，确认是否为真实可利用漏洞。
专注于：
- 授权链追踪（是否缺少 ownership check / role check）
- 参数绑定分析（HTTP 参数是否可操控关键字段）
- 状态机验证（状态跃迁是否有 guard 条件）
- 金额/数量追踪（是否存在整数溢出/精度问题/负数绕过）
- 竞态窗口分析（TOCTOU 时间窗口是否可被利用）

将确认的漏洞推入共享 vuln_queue，供 VerificationAgent 统一验证。
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from .base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern, TaskHandoff
from .react_parser import parse_react_response
from ..json_parser import AgentJsonParser

logger = logging.getLogger(__name__)

BL_ANALYSIS_SYSTEM_PROMPT = """你是 VulHunter 的**业务逻辑分析 Agent**，负责对单个**业务逻辑风险点**进行深度分析，确认是否为真实可利用漏洞，并将确认的漏洞推送至共享漏洞队列。

═══════════════════════════════════════════════════════════════

## 🎯 核心任务

| 任务 | 说明 |
|------|------|
| **聚焦分析** | 基于输入的业务逻辑风险点，深度追踪授权链、参数流向、状态机逻辑 |
| **验证漏洞** | 确认是否存在真实可利用的业务逻辑漏洞 |
| **立即推送** | **每确认一个漏洞，立即调用 `push_finding_to_queue`** |
| **攻击路径** | 必须提供从攻击者输入到敏感操作的完整链路 |
| **补偿校验** | 必须检查中间件、依赖注入、service guard、repository filter 等全局补偿逻辑 |

═══════════════════════════════════════════════════════════════

## 输入风险点格式

```json
{
    "file_path": "app/api/orders.py",
    "line_start": 42,
    "description": "update_order 通过请求参数获取 order_id，未验证所有权",
    "severity": "high",
    "vulnerability_type": "idor",
    "confidence": 0.85,
    "entry_function": "update_order",
    "context": "PUT /api/orders/<order_id>"
}
```

═══════════════════════════════════════════════════════════════

## 🔬 业务逻辑漏洞分析方法

### IDOR 分析方法
1. 读取目标函数代码，确认对象 ID 来源
2. 检查是否存在所有权验证（如 `order.user_id == current_user.id`）
3. 追踪 ID 从 HTTP 请求到数据库查询的完整路径
4. 检查同一模块中其他接口是否有类似问题

**确认条件**：ID 来自用户可控参数 AND 未验证当前用户与对象的绑定关系

---

### 权限提升分析方法
1. 读取目标函数，识别权限检查装饰器/函数
2. 分析权限检查逻辑是否有绕过条件
3. 检查是否存在多条执行路径可绕过权限检查
4. 追踪角色/权限变量的来源（是否可被用户影响）

**确认条件**：存在可达的代码路径可以绕过权限检查，执行特权操作

---

### 支付/金额篡改分析方法
1. 追踪支付金额的完整数据流（从 HTTP 请求到实际扣款）
2. 检查服务端是否独立计算金额（不依赖客户端传入）
3. 分析折扣/优惠逻辑是否在服务端二次验证
4. 检查是否有负数、零值、超出范围的过滤

**确认条件**：金额字段来自用户可控参数 AND 服务端未独立计算/验证

---

### 竞态条件分析方法
1. 找到 TOCTOU 窗口（读取状态 → 执行操作 的时间间隔）
2. 检查是否有数据库级别的原子操作（行锁、事务、乐观锁）
3. 分析并发请求能否同时通过检查并各自执行操作

**确认条件**：存在 Check-Act 时间窗口 AND 无原子性保证 AND 重复执行有实际危害

---

### 状态机绕过分析方法
1. 枚举所有状态值，找到状态转换函数
2. 检查每个状态转换是否验证前置状态
3. 分析是否可以直接设置目标状态

**确认条件**：可以跳过必要的前置状态直接达到目标状态

═══════════════════════════════════════════════════════════════

## 🔥 漏洞推送机制（强制要求）

每确认一个漏洞，立即调用 `push_finding_to_queue`：

```json
{
    "file_path": "app/api/orders.py",
    "line_start": 42,
    "line_end": 55,
    "title": "app/api/orders.py中update_order函数IDOR越权漏洞",
    "description": "update_order 接口通过请求参数获取 order_id，直接查询并修改该订单，未验证该订单是否属于当前登录用户，攻击者可通过遍历 order_id 越权修改任意用户的订单信息。",
    "vulnerability_type": "idor",
    "severity": "high",
    "confidence": 0.92,
    "code_snippet": "order_id = request.args.get('order_id')\norder = Order.query.get(order_id)\norder.status = 'cancelled'",
    "function_name": "update_order",
    "source": "request.args.get('order_id')",
    "sink": "Order.query.get(order_id)",
    "suggestion": "在查询后验证订单所有权：assert order.user_id == current_user.id",
    "evidence_chain": ["代码片段", "授权链分析"],
    "attacker_flow": "HTTP PUT /api/orders/999 → update_order() → Order.query.get(999) → order.status='cancelled'（无所有权验证）"
}
```

**必填字段**：
- `title`: 中文三段式：路径 + 函数名 + 漏洞名
- `attacker_flow`: 攻击者输入 → 敏感操作的完整链路
- `evidence_chain`: 支撑证据列表

═══════════════════════════════════════════════════════════════

## 分析工具箱

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| `get_code_window` | 读取风险点极小代码窗口 | **第一步必做** |
| `search_code` | 查找相关函数、权限检查逻辑 | 追踪调用链时 |
| `get_function_summary` | 总结目标函数职责与风险点 | 分析特定函数时 |
| `get_symbol_body` | 提取完整函数代码 | 需要完整函数体时 |
| `dataflow_analysis` | 追踪参数从入口到操作的完整流向 | 验证 IDOR/参数污染时 |
| `controlflow_analysis_light` | 分析条件分支（权限绕过路径） | 验证权限提升时 |
| `push_finding_to_queue` | 推送确认的漏洞 | **确认漏洞后立即调用** |

═══════════════════════════════════════════════════════════════

## 工具使用方法（必须遵循）

### 推荐调用顺序
1. `get_code_window`：首轮必须读取风险点附近代码窗口，确认真实上下文
2. `search_code` / `get_function_summary` / `get_symbol_body`：补齐调用链、权限检查与关键函数定义
3. `dataflow_analysis`：追踪关键参数从入口到敏感操作的完整流向
4. `controlflow_analysis_light`：验证是否存在可达的绕过路径
5. `push_finding_to_queue`：确认漏洞后立即推送，禁止延迟

### 使用规则
- 所有文件路径必须使用相对路径（如 `app/api/orders.py`），禁止绝对路径
- 没有 `get_code_window` 证据时禁止直接给出 Final Answer
- 对 `high/critical` 漏洞，优先补齐数据流或控制流证据后再推送
- 推送前检查字段完整性：`file_path`、`line_start`、`title`、`description`、`vulnerability_type`、`attacker_flow`、`evidence_chain`

### Action Input 示例（精简）
```json
Action Input: {"file_path": "app/api/orders.py", "start_line": 12, "end_line": 130}
```

```json
Action Input: {"keyword": "order.user_id|current_user|@admin_required", "file_pattern": "*.py", "is_regex": true}
```

```json
Action Input: {
  "file_path": "app/api/orders.py",
  "line_start": 42,
  "line_end": 55,
  "title": "app/api/orders.py中update_order函数IDOR越权漏洞",
  "description": "update_order 未验证订单归属，攻击者可遍历 order_id 越权修改订单。",
  "vulnerability_type": "idor",
  "severity": "high",
  "confidence": 0.92,
  "attacker_flow": "PUT /api/orders/999 -> update_order -> Order.query.get(999) -> update",
  "evidence_chain": ["代码片段", "授权链分析"]
}
```

═══════════════════════════════════════════════════════════════

## 工具调用失败处理（关键）

### 失败响应原则
**遇到工具调用失败时，你必须：**
1. **分析错误信息** - 理解失败原因（文件不存在、参数错误、超时、权限等）
2. **自主调整策略** - 根据错误类型更换参数、缩小范围或切换工具
3. **继续验证流程** - **禁止直接输出 Final Answer 或放弃分析**

═══════════════════════════════════════════════════════════════

## 🔄 推荐分析流程

1. **读取上下文**：`get_code_window` 读取风险点文件附近的极小窗口
2. **识别授权链**：找到所有权验证、角色检查的位置
3. **追踪数据流**：确认关键参数的来源和去向
4. **分析绕过路径**：是否存在可达的绕过条件
5. **验证全局补偿**：搜索是否由中间件/依赖注入/service guard/repository filter 统一兜底
6. **确认即推送**：确认漏洞后立即调用 `push_finding_to_queue`
7. **扩展分析**：检查同对象/同模块中类似的风险点
7. **输出 Final Answer**：汇总分析结果

═══════════════════════════════════════════════════════════════

## 关键约束

| 约束项 | 要求 |
|--------|------|
| **代码真实性** | 所有判断基于 `get_code_window` / `get_symbol_body` 返回的实际代码 |
| **推送优先** | 确认漏洞 → 立即推送 → 继续分析 |
| **标题格式** | 必须中文三段式：路径 + 函数名 + 漏洞名 |
| **语言要求** | title、description、suggestion 使用简体中文 |
| **攻击路径** | 必须提供 attacker_flow 字段 |
| **首轮行动** | 第一轮必须输出 Action（get_code_window），禁止直接 Final Answer |

### 置信度标准
- `0.9-1.0`: 代码直接证明，无歧义（如 IDOR 明确无所有权验证）
- `0.7-0.9`: 高概率存在，需特定条件（如竞态条件）
- `0.5-0.7`: 疑似存在，依赖环境配置
- `<0.5`: 不推送，继续收集证据

═══════════════════════════════════════════════════════════════

## 输出格式

```
Thought: [分析当前状态]
Action: [工具名称]
Action Input: { "参数": "值" }
```

完成后：
```
Thought: 分析完成，共推送 X 个业务逻辑漏洞
Final Answer: 分析完成，所有确认的业务逻辑漏洞已推送至队列。
```
"""


@dataclass
class BLAnalysisStep:
    """业务逻辑分析步骤"""
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[str] = None


class BusinessLogicAnalysisAgent(BaseAgent):
    """
    业务逻辑分析 Agent

    从 bl_risk_queue 消耗单条业务逻辑风险点，深度分析是否为真实漏洞，
    将确认的漏洞推入共享 vuln_queue 供 VerificationAgent 验证。
    """

    def __init__(
        self,
        llm_service,
        tools: Dict[str, Any],
        event_emitter=None,
    ):
        tool_whitelist = ", ".join(sorted(tools.keys())) if tools else "无"
        full_system_prompt = (
            f"{BL_ANALYSIS_SYSTEM_PROMPT}\n\n"
            f"## 当前工具白名单\n{tool_whitelist}\n"
            "只能调用以上工具，禁止调用未在白名单中的工具。\n\n"
            "## 最小调用规范\n"
            "每轮必须输出：Thought + Action + Action Input。\n"
            "Action 必须是白名单中的工具名，Action Input 必须是 JSON 对象。\n"
            "禁止使用 `## Action`/`## Action Input` 标题样式。"
        )

        config = AgentConfig(
            name="BusinessLogicAnalysis",
            agent_type=AgentType.ANALYSIS,
            pattern=AgentPattern.REACT,
            max_iterations=30,
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)

        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[BLAnalysisStep] = []
        self._agent_results: Dict[str, Any] = {}

    @staticmethod
    def _normalize_finding_payload(candidate: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(candidate, dict):
            return None
        nested = candidate.get("finding")
        if isinstance(nested, dict):
            merged_candidate = dict(candidate)
            merged_candidate.pop("finding", None)
            for key, value in nested.items():
                merged_candidate.setdefault(str(key), value)
            candidate = merged_candidate
        file_path = str(candidate.get("file_path") or "").strip()
        title = str(candidate.get("title") or "").strip()
        description = str(candidate.get("description") or "").strip()
        vulnerability_type = str(candidate.get("vulnerability_type") or "").strip().lower()
        if not (file_path and title and description and vulnerability_type):
            return None
        try:
            line_start = int(candidate.get("line_start") or 0)
        except Exception:
            line_start = 0
        try:
            line_end = int(candidate.get("line_end")) if candidate.get("line_end") is not None else None
        except Exception:
            line_end = None
        try:
            confidence = float(candidate.get("confidence") or 0.8)
        except Exception:
            confidence = 0.8
        finding = {
            "file_path": file_path,
            "line_start": max(1, line_start),
            "title": title,
            "description": description,
            "vulnerability_type": vulnerability_type,
            "severity": str(candidate.get("severity") or "medium").strip().lower(),
            "confidence": max(0.0, min(1.0, confidence)),
        }
        if line_end is not None and line_end >= finding["line_start"]:
            finding["line_end"] = line_end
        for optional_key in (
            "function_name",
            "source",
            "sink",
            "suggestion",
            "attacker_flow",
            "code_snippet",
        ):
            value = str(candidate.get(optional_key) or "").strip()
            if value:
                finding[optional_key] = value
        for list_key in ("evidence_chain", "missing_checks", "taint_flow"):
            raw_list = candidate.get(list_key)
            if isinstance(raw_list, list):
                normalized = [str(item).strip() for item in raw_list if str(item).strip()]
                if normalized:
                    finding[list_key] = normalized
        return finding

    @staticmethod
    def _parse_method_route_from_text(text: str) -> tuple[str, str]:
        raw = str(text or "").strip()
        if not raw:
            return "", ""
        match = re.search(
            r"\b(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD|WEBHOOK|RPC|GRPC|CALLBACK|CONSUMER|JOB)\b\s+([^\s,]+)",
            raw,
            flags=re.IGNORECASE,
        )
        if not match:
            return "", raw[:160]
        return match.group(1).upper(), match.group(2).strip()

    def _build_context_pack(
        self,
        risk_point: Dict[str, Any],
        input_context_pack: Any,
    ) -> Dict[str, Any]:
        context_pack = dict(input_context_pack) if isinstance(input_context_pack, dict) else {}
        route = str(context_pack.get("route") or risk_point.get("route") or "").strip()
        http_method = str(context_pack.get("http_method") or risk_point.get("http_method") or "").strip().upper()
        context_hint = str(risk_point.get("context") or "").strip()
        if (not route or not http_method) and context_hint:
            parsed_method, parsed_route = self._parse_method_route_from_text(context_hint)
            if not http_method and parsed_method:
                http_method = parsed_method
            if not route and parsed_route:
                route = parsed_route

        auth_context = str(context_pack.get("auth_context") or risk_point.get("auth_context") or "").strip()
        entry_function = str(risk_point.get("entry_function") or "").strip()
        object_type = str(context_pack.get("object_type") or risk_point.get("object_type") or "").strip()
        sensitive_action = str(
            context_pack.get("sensitive_action") or risk_point.get("sensitive_action") or ""
        ).strip()

        related_symbols: List[str] = []
        for source in (
            context_pack.get("related_symbols"),
            risk_point.get("related_symbols"),
        ):
            if not isinstance(source, list):
                continue
            for item in source:
                value = str(item).strip()
                if value and value not in related_symbols:
                    related_symbols.append(value)
        if entry_function and entry_function not in related_symbols:
            related_symbols.append(entry_function)

        evidence_refs: List[str] = []
        for source in (
            context_pack.get("evidence_refs"),
            risk_point.get("evidence_refs"),
        ):
            if not isinstance(source, list):
                continue
            for item in source:
                value = str(item).strip()
                if value and value not in evidence_refs:
                    evidence_refs.append(value)
        if risk_point.get("file_path"):
            evidence_anchor = f"{risk_point.get('file_path')}:{risk_point.get('line_start') or 1}"
            if evidence_anchor not in evidence_refs:
                evidence_refs.append(evidence_anchor)

        summary_parts = []
        if http_method or route:
            summary_parts.append(f"入口: {(http_method + ' ') if http_method else ''}{route}".strip())
        if auth_context:
            summary_parts.append(f"鉴权上下文: {auth_context}")
        if object_type:
            summary_parts.append(f"业务对象: {object_type}")
        if sensitive_action:
            summary_parts.append(f"敏感动作: {sensitive_action}")
        if related_symbols:
            summary_parts.append(f"关联符号: {', '.join(related_symbols[:6])}")

        context_pack.update(
            {
                "route": route,
                "http_method": http_method,
                "auth_context": auth_context,
                "related_symbols": related_symbols,
                "object_type": object_type,
                "sensitive_action": sensitive_action,
                "evidence_refs": evidence_refs,
                "summary": " | ".join(part for part in summary_parts if part),
            }
        )
        return context_pack

    def _parse_llm_response(self, response: str) -> BLAnalysisStep:
        """解析 LLM 响应"""
        parsed = parse_react_response(
            response,
            final_default={"raw_answer": (response or "").strip()},
            action_input_raw_key="raw_input",
        )
        return BLAnalysisStep(
            thought=parsed.thought or "",
            action=parsed.action,
            action_input=parsed.action_input or {},
            is_final=bool(parsed.is_final),
            final_answer=str(parsed.final_answer) if parsed.is_final else None,
        )

    def _normalize_risk_point(self, candidate: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(candidate, dict):
            return None
        file_path = str(candidate.get("file_path") or "").strip()
        if not file_path:
            return None
        try:
            line_start = int(candidate.get("line_start") or candidate.get("line") or 1)
        except Exception:
            line_start = 1
        return {
            "file_path": file_path,
            "line_start": max(1, line_start),
            "description": str(candidate.get("description") or "").strip(),
            "severity": str(candidate.get("severity") or "high").lower(),
            "vulnerability_type": str(candidate.get("vulnerability_type") or "business_logic").lower(),
            "confidence": max(0.0, min(1.0, float(candidate.get("confidence") or 0.6))),
            "entry_function": str(candidate.get("entry_function") or "").strip(),
            "context": str(candidate.get("context") or "").strip(),
            "route": str(candidate.get("route") or "").strip(),
            "http_method": str(candidate.get("http_method") or "").strip(),
            "auth_context": str(candidate.get("auth_context") or "").strip(),
            "object_type": str(candidate.get("object_type") or "").strip(),
            "sensitive_action": str(candidate.get("sensitive_action") or "").strip(),
            "related_symbols": list(candidate.get("related_symbols") or []),
            "evidence_refs": list(candidate.get("evidence_refs") or []),
        }

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        分析单个业务逻辑风险点。

        Args:
            input_data: 包含 risk_point 的字典（来自 bl_risk_queue）

        Returns:
            AgentResult，data 中包含 findings 列表
        """
        start_time = time.time()

        risk_point: Optional[Dict[str, Any]] = None
        if isinstance(input_data, dict):
            risk_point = input_data.get("risk_point") or input_data.get("context_dict")
            if not isinstance(risk_point, dict):
                context_raw = input_data.get("context") or ""
                if isinstance(context_raw, str) and context_raw.strip():
                    try:
                        risk_point = json.loads(context_raw)
                    except Exception:
                        pass
            if not isinstance(risk_point, dict):
                risk_point = None

        if risk_point is None:
            normalized = self._normalize_risk_point(input_data)
            if normalized:
                risk_point = normalized

        if not risk_point:
            duration_ms = int((time.time() - start_time) * 1000)
            await self.emit_event("warning", "[BLAnalysis] 未收到风险点，跳过分析")
            return AgentResult(
                success=True,
                data={"findings": [], "degraded_reason": "missing_bl_risk_point"},
                iterations=0,
                tool_calls=0,
                tokens_used=0,
                duration_ms=duration_ms,
            )

        file_path = str(risk_point.get("file_path") or "").strip()
        line_start = int(risk_point.get("line_start") or 1)
        description = str(risk_point.get("description") or "").strip()
        vuln_type = str(risk_point.get("vulnerability_type") or "business_logic").lower()
        entry_function = str(risk_point.get("entry_function") or "").strip()
        context_hint = str(risk_point.get("context") or "").strip()
        context_pack = self._build_context_pack(
            risk_point,
            input_data.get("context_pack") if isinstance(input_data, dict) else None,
        )

        initial_message = (
            f"## 业务逻辑风险点分析任务\n\n"
            f"**风险点信息：**\n"
            f"```json\n{json.dumps(risk_point, ensure_ascii=False, indent=2)}\n```\n\n"
            f"**分析要求：**\n"
            f"1. 首先使用 `get_code_window` 读取 `{file_path}` 第 {line_start} 行附近的极小窗口\n"
            f"2. 深度分析 `{vuln_type}` 类型的业务逻辑风险\n"
        )
        if entry_function:
            initial_message += f"3. 重点分析函数 `{entry_function}` 的授权/验证逻辑\n"
        if context_hint:
            initial_message += f"4. 上下文提示：{context_hint}\n"
        if context_pack:
            initial_message += (
                f"5. 最小证据包：\n```json\n{json.dumps(context_pack, ensure_ascii=False, indent=2)}\n```\n"
                "   请优先结合该证据包检查同对象接口、全局鉴权补偿、中间件/依赖注入/service guard/repository filter。\n"
            )
        initial_message += (
            f"\n确认为真实漏洞后，立即调用 `push_finding_to_queue` 推送，"
            f"必须包含 `attacker_flow` 字段描述攻击路径。\n"
            f"禁止直接输出 Final Answer，第一轮必须执行 `get_code_window`。\n"
            f"若发现局部缺少校验，必须尝试搜索全局补偿逻辑，避免将已被中间件/依赖统一保护的接口误报。"
        )
        initial_message += f"""

## 可用工具
{self.get_tools_description()}

请继续分析并先执行工具调用，再输出结论。
不要只输出 Thought，必须紧接着输出 Action + Action Input。"""

        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": initial_message},
        ]
        self._steps = []
        all_findings = []
        all_tool_calls = 0
        all_tokens = 0
        iteration = 0

        await self.emit_thinking(
            f"🔬 BusinessLogicAnalysisAgent 开始分析 {vuln_type} 风险点：{file_path}:{line_start}"
        )

        try:
            while iteration < self.config.max_iterations:
                if self.is_cancelled:
                    break

                iteration += 1
                await self.emit_event(
                    "info",
                    f" [BLAnalysis] 第 {iteration} 轮推理：{file_path}:{line_start}",
                )

                llm_response, tokens = await self.stream_llm_call(self._conversation_history)
                all_tokens += tokens or 0

                step = self._parse_llm_response(llm_response)
                self._steps.append(step)

                await self.emit_thinking(step.thought or "")

                if step.is_final:
                    await self.emit_event(
                        "info",
                        f"[BLAnalysis] 分析完成：{file_path}:{line_start}",
                    )
                    break

                if not step.action:
                    self._conversation_history.append({
                        "role": "assistant",
                        "content": llm_response,
                    })
                    self._conversation_history.append({
                        "role": "user",
                        "content": "Observation:\n请继续分析，使用工具读取代码或推送确认的漏洞。",
                    })
                    continue

                await self.emit_llm_action(step.action, step.action_input or {})

                action_input = dict(step.action_input or {})
                all_tool_calls += 1
                if step.action == "push_finding_to_queue":
                    normalized_finding = self._normalize_finding_payload(action_input)
                    if normalized_finding:
                        all_findings.append(normalized_finding)

                try:
                    observation = await self.execute_tool(step.action, action_input)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    observation = f"工具调用失败: {exc}"
                    logger.error("[BLAnalysis] Tool call failed: %s", exc)

                step.observation = observation
                await self.emit_llm_observation(observation)

                self._conversation_history.append({
                    "role": "assistant",
                    "content": llm_response,
                })
                self._conversation_history.append({
                    "role": "user",
                    "content": f"Observation:\n{self._prepare_observation_for_history(observation)}",
                })

        except asyncio.CancelledError:
            logger.info("[BLAnalysis] BusinessLogicAnalysisAgent cancelled")

        duration_ms = int((time.time() - start_time) * 1000)
        findings_pushed = len(all_findings)
        findings_with_complete_evidence = sum(
            1
            for finding in all_findings
            if finding.get("attacker_flow") and finding.get("evidence_chain")
        )
        false_positive_suspects = 1 if findings_pushed == 0 and iteration > 0 else 0
        analysis_with_evidence = int(bool(context_pack.get("summary") or context_pack.get("evidence_refs")))

        self._agent_results["business_logic_analysis"] = {
            "_run_success": True,
            "findings": all_findings,
            "risk_points_confirmed": findings_pushed,
            "findings_pushed": findings_pushed,
            "analysis_with_evidence": analysis_with_evidence,
            "findings_with_complete_evidence": findings_with_complete_evidence,
            "false_positive_suspects": false_positive_suspects,
            "context_pack": context_pack,
        }

        return AgentResult(
            success=True,
            data={
                "findings": all_findings,
                "steps": len(self._steps),
                "risk_points_confirmed": findings_pushed,
                "findings_pushed": findings_pushed,
                "analysis_with_evidence": analysis_with_evidence,
                "findings_with_complete_evidence": findings_with_complete_evidence,
                "false_positive_suspects": false_positive_suspects,
                "context_pack": context_pack,
            },
            iterations=iteration,
            tool_calls=all_tool_calls,
            tokens_used=all_tokens,
            duration_ms=duration_ms,
        )
