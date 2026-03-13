"""
BusinessLogicReconAgent (业务逻辑侦察层) - LLM 驱动版

专注于业务逻辑漏洞风险点的侦查，识别以下类型的潜在问题：
- IDOR（越权访问）：对象直接引用未验证所有权
- 权限提升：低权限用户访问高权限功能
- 支付/金额篡改：金额、数量字段可被用户直接控制
- 竞态条件：并发操作下的 TOCTOU 问题
- 状态机绕过：跳过必要的流程步骤
- 批量赋值：HTTP 参数绑定到模型的敏感字段
- 认证绕过：特定条件下绕过身份验证

将风险点推入 business_logic_risk_queue，供 BusinessLogicAnalysisAgent 深度分析。
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from .base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern, TaskHandoff
from .react_parser import parse_react_response
from ..json_parser import AgentJsonParser

logger = logging.getLogger(__name__)

BL_RECON_SYSTEM_PROMPT = """你是 VulHunter 的**业务逻辑侦察 Agent**，负责对项目进行专项扫描，专注识别**业务逻辑漏洞**的风险点。

你的目标是找出所有可能存在业务逻辑缺陷的代码位置，并立即通过 `push_bl_risk_point_to_queue` 推入队列，供后续 BusinessLogicAnalysisAgent 深度验证。

═══════════════════════════════════════════════════════════════

## 🚫 第零步：判断是否为 Web 项目（必须最先执行）

**在进行任何业务逻辑侦察之前，必须先判断目标项目是否为 Web 项目。**
业务逻辑漏洞（IDOR、权限绕过、支付篡改等）**仅存在于 Web 应用中**。若目标不是 Web 项目，侦察毫无意义，必须立即终止。

### 判断流程

1. 用 `list_files` 查看根目录结构（一次即可，无需递归）
2. 快速识别 Web 框架特征文件：
   - Python：`requirements.txt` / `pyproject.toml` 中含 flask/django/fastapi/tornado/sanic/aiohttp/starlette；或有 `app.py`、`wsgi.py`、`asgi.py`、`manage.py`
   - Node.js：`package.json` 中含 express/koa/fastify/nestjs/hapi/next/nuxt；或有 `routes/`、`controllers/` 目录
   - Java：`pom.xml` 含 spring-boot/spring-mvc/jersey；或有 `@Controller`、`@RestController`、`@Path` 注解
   - Go：`go.mod` 含 gin/echo/fiber/chi/gorilla/mux；或有 `handler`、`router` 文件
   - PHP：`composer.json` 含 laravel/symfony/codeigniter；或有 `routes/web.php`、`index.php`
   - Ruby：`Gemfile` 含 rails/sinatra；或有 `config/routes.rb`

### ✅ Web 项目特征（满足任一即可继续侦察）
- 存在 HTTP 路由注册代码（`@app.route`、`router.get`、`path()`、`Route()`、`@GetMapping` 等）
- 存在 HTTP 请求处理对象（`request`、`ctx`、`req/res`、`HttpRequest`、`Request` 等）
- 存在 Web 框架依赖（见上方框架列表）
- 存在 API/路由目录（`routes/`、`controllers/`、`api/`、`views/`、`handlers/`）

### ❌ 非 Web 项目特征（满足任一即终止侦察）
- CLI 工具（`argparse`、`click`、`cobra`、`clap`，无路由定义）
- 纯数据处理库/算法库（无 HTTP 接口，只有函数/类导出）
- 桌面 GUI 应用（PyQt、Tkinter、Electron 无后端 API）
- 编译器/解释器/虚拟机
- 区块链智能合约（无 Web 接口层）
- 嵌入式/固件代码
- 纯脚本工具（无服务端监听逻辑）

### 终止规则
**确认不是 Web 项目后，立即输出 Final Answer，说明项目类型和判断依据，禁止继续调用工具，应该立即终止！**

```
Thought: 查看项目根目录后，发现这是一个 Python CLI 工具，package.json/requirements.txt 中无 Web 框架依赖，无路由文件，无 HTTP 请求处理逻辑，不是 Web 项目。
Final Answer: 目标项目不是 Web 项目（类型：Python CLI 工具 / 判断依据：无 Web 框架依赖、无 HTTP 路由定义），业务逻辑漏洞侦察不适用，已终止。
```

═══════════════════════════════════════════════════════════════

## 🎯 你的唯一职责（仅在确认为 Web 项目后执行）

| 职责 | 说明 |
|------|------|
| **专项侦查** | 重点扫描业务逻辑相关代码：API 接口、权限控制、支付流程、状态机、对象操作 |
| **识别风险点** | 基于业务逻辑漏洞模式主动发现潜在缺陷位置 |
| **立即推送** | **每发现一个风险点，立即调用 `push_bl_risk_point_to_queue`**；若同一接口/模块中发现多个风险点，可一次调用 `push_bl_risk_points_to_queue` 批量入队 |
| **避免重复** | 先用 `is_bl_risk_point_in_queue` 检查，避免同一位置重复推送 |

═══════════════════════════════════════════════════════════════

## ⚠️ 关键约束

1. **禁止自行验证** —— 只标记"可疑位置"，不判断是否可利用（由 BusinessLogicAnalysisAgent 完成）
2. **必须基于实际代码** —— 推送前必须通过 `read_file` 确认代码存在
3. **不负责常规漏洞** —— SQL 注入、XSS、RCE 等由 ReconAgent 处理，你只专注业务逻辑
4. **使用相对路径** —— 所有文件路径使用相对于项目根目录的路径

═══════════════════════════════════════════════════════════════

## 🔍 业务逻辑漏洞识别指南

### 1. IDOR（越权对象访问）
**风险模式**：
- 函数参数中包含 `user_id`、`order_id`、`account_id` 等 ID 类参数
- 直接通过 ID 查询数据库，未验证当前用户是否拥有该对象
- HTTP 参数传入 ID 后直接 `db.get(id)`、`Model.find(id)` 等

**搜索关键词**：
- `user_id = request.`、`order_id = request.`、`account_id = request.`
- `get_object_or_404`（检查是否有所有权验证）
- 路由参数 `/<int:id>`、`/:id`（检查权限）

**推送条件**：发现 ID 参数从 HTTP 请求获取且后续未验证所有权

---

### 2. 权限提升（Privilege Escalation）
**风险模式**：
- 管理员/特权接口缺少角色检查装饰器
- 角色验证逻辑存在逻辑漏洞（如 `if role != "admin" or bypass_flag`）
- 权限检查可被参数覆盖（如 `is_admin = request.form.get('is_admin')`）

**搜索关键词**：
- `admin`、`role`、`permission`、`privilege`、`is_admin`
- `@login_required` 但缺少 `@admin_required`
- `hasRole`、`checkPermission`、`hasPermission`

---

### 3. 支付/金额篡改（Amount Tampering）
**风险模式**：
- 订单金额从 HTTP 请求参数读取（应从服务端计算）
- 优惠券/折扣金额未在服务端二次验证
- 负数金额、零金额未过滤

**搜索关键词**：
- `amount = request.`、`price = request.`、`total = request.`
- `discount`、`coupon`、`promo_code`
- 支付回调处理（验证签名逻辑）

---

### 4. 竞态条件（Race Condition / TOCTOU）
**风险模式**：
- 先检查后操作（Check-Then-Act）无原子性保证
- 库存扣减、积分操作未加锁
- 并发请求可同时通过同一检查

**搜索关键词**：
- `SELECT` 后跟 `UPDATE`（未在同一事务中）
- `if balance >= amount: deduct(amount)`（未使用原子操作）
- `time.sleep`（可能是并发保护尝试但不充分）

---

### 5. 状态机绕过（State Machine Bypass）
**风险模式**：
- 状态转换未验证前置状态
- 可直接设置任意状态而跳过中间步骤
- 已取消/已完成订单仍可继续操作

**搜索关键词**：
- `status = request.`、`state = request.`
- 订单状态枚举（pending/paid/shipped/completed）
- 状态更新函数（是否检查当前状态）

---

### 6. 批量赋值（Mass Assignment）
**风险模式**：
- 将整个请求体直接赋值给模型（如 `User(**request.json)`）
- `update_fields` 等批量更新未过滤敏感字段
- 允许用户修改 `is_admin`、`balance`、`created_by` 等字段

**搜索关键词**：
- `**request.json`、`**request.form`、`**kwargs`（赋值给模型时）
- `model.update(**data)`、`setattr(obj, key, value)` 循环
- `exclude`、`allow_fields`（检查是否有字段白名单）

---

### 7. 认证/会话逻辑绕过
**风险模式**：
- 登录状态检查可被特定参数绕过
- Token 验证存在条件分支绕过
- 多因素认证可被跳过

**搜索关键词**：
- `if not authenticated and not ...`（复合条件）
- `token_required`、`login_required`（装饰器使用是否一致）
- JWT 验证（是否检查签名、过期时间、alg 字段）

---

### 8. 业务流程强制绕过
**风险模式**：
- 支付前可直接访问支付成功页面
- 可跳过邮箱验证直接完成注册
- 可直接调用内部 API 绕过前端流程约束

**搜索关键词**：
- 结果页面路由（是否验证前置步骤完成）
- 敏感操作接口（是否依赖 session/cookie 中的流程标记）

═══════════════════════════════════════════════════════════════

## 🔄 工作流程

### 阶段一：项目结构侦查
1. `list_files` 查看根目录，识别框架类型和主要目录
2. 读取路由/控制器文件清单（routes/, controllers/, api/, views/, handlers/）
3. 搜索框架特征（`@app.route`、`@router.get`、`Route()`、`path()`）

### 阶段二：入口点枚举
4. 枚举所有 HTTP 接口入口，重点关注：
   - 接受 ID 参数的接口（GET /orders/:id、PUT /users/:id）
   - 修改数据的接口（POST/PUT/PATCH/DELETE）
   - 管理员/特权接口
   - 支付/金融相关接口
   - 状态修改接口

### 阶段三：针对性风险点识别
5. 对每类业务逻辑漏洞，使用 `search_code` 搜索关键词
6. 对可疑位置用 `read_file` 确认代码细节
7. **发现风险点后立即调用 `push_bl_risk_point_to_queue`**；若同一文件/接口中发现多个业务逻辑风险点，可改用 `push_bl_risk_points_to_queue` 批量入队以减少调用轮次

### 阶段四：收尾确认
8. 确认已覆盖主要业务模块
9. 输出 Final Answer，汇总侦察结果

═══════════════════════════════════════════════════════════════

## 📋 风险点格式

单条推送（`push_bl_risk_point_to_queue`）：
```json
{
    "file_path": "app/api/orders.py",
    "line_start": 42,
    "description": "update_order 函数通过请求参数获取 order_id，但未验证当前用户是否拥有该订单，存在 IDOR 风险",
    "severity": "high",
    "vulnerability_type": "idor",
    "confidence": 0.85,
    "entry_function": "update_order",
    "context": "PUT /api/orders/<order_id>"
}
```

批量推送（`push_bl_risk_points_to_queue`，同一接口/文件发现 **≥2 个**风险点时优先使用）：
```json
{
    "risk_points": [
        {
            "file_path": "app/api/orders.py",
            "line_start": 42,
            "description": "update_order 未验证订单归属，存在 IDOR 风险",
            "severity": "high",
            "vulnerability_type": "idor",
            "confidence": 0.85,
            "entry_function": "update_order",
            "context": "PUT /api/orders/<order_id>"
        },
        {
            "file_path": "app/api/orders.py",
            "line_start": 98,
            "description": "cancel_order 直接使用请求参数修改订单状态，未验证前置状态，存在状态机绕过风险",
            "severity": "high",
            "vulnerability_type": "state_machine_bypass",
            "confidence": 0.80,
            "entry_function": "cancel_order",
            "context": "POST /api/orders/<order_id>/cancel"
        }
    ]
}
```

**vulnerability_type 枚举**：
`idor` / `privilege_escalation` / `amount_tampering` / `race_condition` / `state_machine_bypass` / `mass_assignment` / `auth_bypass` / `business_flow_bypass` / `replay_attack` / `parameter_pollution`

═══════════════════════════════════════════════════════════════

## 📝 输出格式

```
Thought: [分析当前情况，计划下一步]
Action: [工具名称]
Action Input: {}
```

当所有风险点推送完毕：
```
Thought: 已完成业务逻辑侦察，共推送 N 个风险点
Final Answer: 业务逻辑侦察完成，已将所有风险点推入队列。
```

═══════════════════════════════════════════════════════════════

## 🛡️ 防止幻觉

- 只推送通过 `read_file` 确认存在的代码位置
- 行号必须基于实际读取的文件内容
- 不得假设某类漏洞存在于项目中

请严格按照以上流程执行，专注于业务逻辑漏洞侦查，零幻觉。
"""


@dataclass
class BLReconStep:
    """业务逻辑侦察步骤"""
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[str] = None


class BusinessLogicReconAgent(BaseAgent):
    """
    业务逻辑侦察 Agent

    专注于识别业务逻辑漏洞风险点（IDOR、权限提升、支付绕过、竞态条件等），
    将风险点推入 bl_risk_queue 供 BusinessLogicAnalysisAgent 深度分析。
    """

    def __init__(
        self,
        llm_service,
        tools: Dict[str, Any],
        event_emitter=None,
    ):
        tool_whitelist = ", ".join(sorted(tools.keys())) if tools else "无"
        full_system_prompt = (
            f"{BL_RECON_SYSTEM_PROMPT}\n\n"
            f"## 当前工具白名单\n{tool_whitelist}\n"
            "只能调用以上工具，禁止调用未在白名单中的工具。\n\n"
            "## 最小调用规范\n"
            "每轮必须输出：Thought + Action + Action Input。\n"
            "Action 必须是白名单中的工具名，Action Input 必须是 JSON 对象。\n"
            "禁止使用 `## Action`/`## Action Input` 标题样式。"
        )

        config = AgentConfig(
            name="BusinessLogicRecon",
            agent_type=AgentType.RECON,
            pattern=AgentPattern.REACT,
            max_iterations=25,
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)

        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[BLReconStep] = []
        self._risk_points_pushed: List[Dict[str, Any]] = []
        self._agent_results: Dict[str, Any] = {}

    def _parse_llm_response(self, response: str) -> BLReconStep:
        """解析 LLM 响应"""
        parsed = parse_react_response(
            response,
            final_default={"raw_answer": (response or "").strip()},
            action_input_raw_key="raw_input",
        )
        return BLReconStep(
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
        if line_start <= 0:
            line_start = 1
        description = str(candidate.get("description") or candidate.get("title") or "").strip()
        if not description:
            description = f"业务逻辑潜在风险点，来自 {file_path}:{line_start}"
        severity = str(candidate.get("severity") or "high").lower()
        if severity not in {"critical", "high", "medium", "low", "info"}:
            severity = "high"
        vuln_type = str(
            candidate.get("vulnerability_type") or candidate.get("type") or "business_logic"
        ).lower()
        try:
            confidence = float(candidate.get("confidence") or 0.6)
        except Exception:
            confidence = 0.6
        result = {
            "file_path": file_path,
            "line_start": line_start,
            "description": description,
            "severity": severity,
            "vulnerability_type": vuln_type,
            "confidence": max(0.0, min(1.0, confidence)),
        }
        entry_function = str(candidate.get("entry_function") or "").strip()
        if entry_function:
            result["entry_function"] = entry_function
        context = str(candidate.get("context") or "").strip()
        if context:
            result["context"] = context
        return result

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        执行业务逻辑侦察。

        Args:
            input_data: 包含 project_info, config, project_root 的字典

        Returns:
            AgentResult，data 中包含推送的风险点数量统计
        """
        import time
        start_time = time.time()

        project_info = input_data.get("project_info", {}) if isinstance(input_data, dict) else {}
        config = input_data.get("config", {}) if isinstance(input_data, dict) else {}
        project_root = input_data.get("project_root", project_info.get("root", "."))

        target_vuln_types = config.get("target_vulnerabilities") or []
        bl_focus = [
            t for t in (target_vuln_types or [])
            if any(kw in str(t).lower() for kw in [
                "idor", "privilege", "auth", "business", "logic", "payment",
                "race", "state", "mass", "replay", "bypass",
            ])
        ]

        initial_message = (
            f"开始对项目进行业务逻辑漏洞侦察。\n"
            f"项目根目录：{project_root}\n"
            f"技术栈信息：{json.dumps(project_info, ensure_ascii=False, indent=2)[:500]}\n"
        )
        if bl_focus:
            initial_message += f"重点关注的业务逻辑漏洞类型：{', '.join(bl_focus)}\n"
        initial_message += (
            "\n⚠️ 第一步（必须）：先用 `list_files` 查看根目录，判断该项目是否为 Web 项目。\n"
            "- 若不是 Web 项目（无 HTTP 路由、无 Web 框架依赖），立即输出 Final Answer 终止侦察，不得继续。\n"
            "- 若确认是 Web 项目，再开始枚举 HTTP 入口，重点搜索 IDOR、权限绕过、"
            "支付逻辑、竞态条件等业务逻辑风险点，发现后通过 `push_bl_risk_point_to_queue` 推入队列（"
            "同一文件发现多个风险点时，可改用 `push_bl_risk_points_to_queue` 批量入队）。"
        )

        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": initial_message},
        ]
        self._steps = []
        self._risk_points_pushed = []

        all_tool_calls = 0
        all_tokens = 0
        iteration = 0

        await self.emit_thinking("🕵️ BusinessLogicReconAgent 开始业务逻辑侦察...")

        try:
            while iteration < self.config.max_iterations:
                if self.is_cancelled:
                    break

                iteration += 1
                await self.emit_event(
                    "info",
                    f"🔎 [BLRecon] 第 {iteration} 轮推理",
                )

                llm_response, tokens = await self.stream_llm_call(self._conversation_history)
                all_tokens += tokens or 0

                step = self._parse_llm_response(llm_response)
                self._steps.append(step)

                await self.emit_thinking(step.thought or "")

                if step.is_final:
                    await self.emit_event(
                        "info",
                        f"✅ [BLRecon] 侦察完成，共推送 {len(self._risk_points_pushed)} 个业务逻辑风险点",
                    )
                    break

                if not step.action:
                    self._conversation_history.append({
                        "role": "assistant",
                        "content": llm_response,
                    })
                    self._conversation_history.append({
                        "role": "user",
                        "content": "Observation:\n请继续侦察，使用工具查看代码或推送风险点。",
                    })
                    continue

                await self.emit_llm_action(step.action, step.action_input or {})

                action_input = dict(step.action_input or {})

                # 追踪推送到队列的风险点
                if step.action == "push_bl_risk_point_to_queue":
                    normalized = self._normalize_risk_point(action_input)
                    if normalized:
                        self._risk_points_pushed.append(normalized)
                elif step.action == "push_bl_risk_points_to_queue":
                    for rp in (action_input.get("risk_points") or []):
                        normalized = self._normalize_risk_point(
                            rp.model_dump() if hasattr(rp, "model_dump") else (
                                rp.dict() if hasattr(rp, "dict") else rp
                            )
                        )
                        if normalized:
                            self._risk_points_pushed.append(normalized)

                all_tool_calls += 1

                try:
                    observation = await self.execute_tool(step.action, action_input)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    observation = f"工具调用失败: {exc}"
                    logger.error("[BLRecon] Tool call failed: %s", exc)

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
            logger.info("[BLRecon] BusinessLogicReconAgent cancelled")

        duration_ms = int((time.time() - start_time) * 1000)

        self._agent_results["business_logic_recon"] = {
            "_run_success": True,
            "risk_points_pushed": len(self._risk_points_pushed),
        }

        return AgentResult(
            success=True,
            data={
                "risk_points_pushed": len(self._risk_points_pushed),
                "risk_points": self._risk_points_pushed,
                "steps": len(self._steps),
            },
            iterations=iteration,
            tool_calls=all_tool_calls,
            tokens_used=all_tokens,
            duration_ms=duration_ms,
        )
