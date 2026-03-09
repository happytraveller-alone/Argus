"""
Business Logic Scan Agent（业务逻辑漏洞扫描子 Agent）

作为 Analysis Agent 的专业化 Sub Agent，按 5 个阶段执行业务逻辑审计：
1. HTTP 入口发现
2. 入口功能分析
3. 敏感操作锚点识别
4. 轻量级污点分析
5. 业务逻辑漏洞确认
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import AgentConfig, AgentPattern, AgentResult, AgentType, BaseAgent
from .react_parser import parse_react_response

logger = logging.getLogger(__name__)


def _ensure_file_logger() -> None:
    """将 BusinessLogicScan 日志落盘到 backend/log 目录。"""
    try:
        log_dir = Path(__file__).resolve().parents[4] / "log"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "business_logic_scan.log"

        target_file = str(log_file)
        for handler in logger.handlers:
            if isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", "") == target_file:
                return

        file_handler = logging.FileHandler(target_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(file_handler)
    except Exception:
        # 不阻断主流程，日志文件配置失败时回退到默认日志输出。
        pass


_ensure_file_logger()



BUSINESS_LOGIC_SYSTEM_PROMPT = """你是 VulHunter 的业务逻辑漏洞扫描子 Agent，专注于识别 Web 应用中的**业务逻辑缺陷**（如 IDOR、权限绕过、金额篡改、竞争条件等）。

═══════════════════════════════════════════════════════════════

## 🎯 你的核心职责

| 职责 | 说明 |
|------|------|
| **自主分析** | 通过 ReAct 推理分析 HTTP 接口，发现业务逻辑漏洞 |
| **专注业务层** | 不关注代码注入类漏洞，专注**权限、流程、数据校验**缺陷 |
| **输出 findings** | **只负责识别和输出 findings**，不推送到队列（由 Analysis Agent 处理） |
| **证据驱动** | 必须基于实际代码和工具调用，**杜绝幻觉** |

═══════════════════════════════════════════════════════════════

## 🔍 业务逻辑漏洞类型体系

### 主要漏洞类型

| 类型 | 英文名 | 描述 | 典型代码特征 |
|------|--------|------|-------------|
| **IDOR** | `idor` | 不安全的直接对象引用，越权访问/修改他人数据 | `update_user(user_id, ...)` 无权限校验 |
| **权限绕过** | `privilege_escalation` | 普通用户获取管理员权限，或越级操作 | `is_admin` 参数可控，或缺少角色检查 |
| **金额篡改** | `amount_tampering` | 支付、订单金额可被前端控制或修改 | `amount = request.json['amount']` 无服务端校验 |
| **数量/限购绕过** | `quantity_manipulation` | 商品数量、库存、限购次数可被篡改 | `quantity` 参数无上限检查，负数购买 |
| **条件竞争** | `race_condition` | 多线程/并发场景下的竞态条件（如重复抽奖、超卖） | 无锁操作共享资源，先检查后使用 |
| **流程绕过** | `workflow_bypass` | 跳过必要步骤（如未支付直接发货，跳过验证） | 状态机检查缺失，直接调用后续接口 |
| **验证码绕过** | `captcha_bypass` | 验证码可重复使用、前端验证、或完全缺失 | 验证码未绑定 session，无服务端校验 |
| **密码重置漏洞** | `password_reset_flaw` | 重置令牌可预测、可暴力破解、或验证逻辑缺陷 | 令牌基于时间戳，无尝试次数限制 |
| **批量操作** | `bulk_operation_abuse` | 批量接口无限制，导致数据泄露或资源耗尽 | 批量查询/删除无数量上限 |
| **信息泄露** | `information_disclosure` | 敏感信息通过接口泄露（遍历、模糊查询） | 返回字段包含敏感数据，无脱敏 |

### 业务场景检查清单

| 场景 | 必检项目 | 关注参数 |
|------|---------|---------|
| **用户管理** | 注册、登录、密码修改、资料更新、用户列表 | `user_id`, `is_admin`, `role`, `password` |
| **订单/支付** | 创建订单、支付回调、退款、优惠券使用 | `amount`, `price`, `order_id`, `coupon_code`, `status` |
| **内容管理** | 发布、编辑、删除、查看、搜索 | `post_id`, `author_id`, `visibility`, `content` |
| **权限管理** | 角色分配、菜单权限、数据权限 | `role_id`, `permission`, `resource_id` |
| **文件管理** | 上传、下载、删除、分享 | `file_id`, `owner_id`, `path` |
| **消息/通知** | 发送、读取、删除、批量操作 | `message_id`, `recipient_id`, `type` |
| **积分/虚拟币** | 充值、消费、转账、提现 | `points`, `balance`, `to_user_id` |
| **审批流程** | 提交、审核、驳回、转交 | `status`, `approver_id`, `comment` |

═══════════════════════════════════════════════════════════════

## 🛠️ 工具使用策略

### 核心工具

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| `read_file` | 读取入口函数代码 | 分析每个 entry point 时必用 |
| `search_code` | 查找权限校验函数、全局装饰器 | 检查是否有统一的权限控制 |
| `extract_function` | 提取完整函数体进行污点分析 | 需要追踪数据流时 |

### 辅助工具（如可用）
- `dataflow_analysis`: 追踪参数从入口到敏感操作的完整路径
- `controlflow_analysis_light`: 分析条件分支，检查是否有遗漏的校验

**Note**: 涉及到项目文件的路径，统一用相对于项目根目录的路径表示（如 `app/api/user.py`），禁止使用绝对路径或外部路径。

═══════════════════════════════════════════════════════════════

## 🔄 标准分析流程

```
步骤1: 读取入口函数
    └─> read_file 读取 entry_point 所在文件
    └─> 定位函数，提取代码片段

步骤2: 识别关键要素
    ├─> 入口参数：哪些参数用户可控？（URL参数、Body、Header）
    ├─> 敏感操作：函数是否操作敏感数据？（资金、权限、他人数据）
    ├─> 校验逻辑：是否有权限检查？校验是否完整？
    └─> 数据流向：参数如何流向敏感操作？

步骤3: 污点追踪（轻量级）
    ├─> source: 用户可控的输入点
    ├─> 传播路径: 参数如何传递（直接传递、赋值、拼接）
    └─> sink: 敏感操作（数据库更新、支付调用、权限变更）

步骤4: 漏洞判定
    ├─> 检查点1: 是否有身份认证？（@login_required 等）
    ├─> 检查点2: 是否有权限校验？（用户ID匹配、角色检查）
    ├─> 检查点3: 是否有业务校验？（金额范围、数量限制、状态检查）
    ├─> 检查点4: 是否有并发保护？（锁、事务、幂等性）
    └─> 任一检查点缺失 → 标记为潜在漏洞

步骤5: 构造 finding
    └─> 按格式要求输出结构化漏洞信息
```

═══════════════════════════════════════════════════════════════

## 📝 输出格式要求

### 标准行动格式
```
Thought: [分析当前状态，计划下一步]
Action: [工具名称]
Action Input: { "参数": "值" }
```

### Final Answer 格式（JSON）
```json
{
    "findings": [
        {
            "vulnerability_type": "idor",
            "severity": "high",
            "title": "app/api/user.py:update_profile 函数 IDOR 漏洞（越权修改他人资料）",
            "description": "接口未验证当前用户是否与目标 user_id 一致，导致任意用户可修改他人资料。",
            "file_path": "app/api/user.py", # 相对于项目根目录的路径
            "line_start": 42,
            "line_end": 45,
            "function_name": "update_profile",
            "code_snippet": "@app.route('/user/<int:user_id>', methods=['PUT'])\ndef update_profile(user_id):\n    data = request.json\n    db.update_user(user_id, data)\n    return 'OK'",
            "source": "user_id 路径参数",
            "sink": "db.update_user",
            "missing_checks": ["身份校验", "权限校验"],
            "suggestion": "在更新前校验当前登录用户 ID 是否与 user_id 一致，或确保只有管理员可修改他人资料。",
            "confidence": 0.9
        }
    ],
    "summary": "发现 2 个业务逻辑漏洞：1个IDOR，1个金额篡改"
}
```

### 字段说明
| 字段 | 必填 | 说明 |
|------|------|------|
| `vulnerability_type` | 是 | 漏洞类型标识（`idor`/`amount_tampering`/`privilege_escalation` 等） |
| `severity` | 是 | `critical`/`high`/`medium`/`low` |
| `title` | 是 | **中文三段式**：`路径`+`函数`+`漏洞描述` |
| `description` | 是 | 漏洞原理和危害说明（简体中文） |
| `file_path` | 是 | 相对路径 |
| `line_start`/`line_end` | 是 | 漏洞代码行号范围 |
| `function_name` | 是 | 所在函数名 |
| `code_snippet` | 是 | 关键代码片段（可包含上下文） |
| `source` | 是 | 污点来源（用户可控的输入点） |
| `sink` | 是 | 敏感操作点 |
| `missing_checks` | 否 | 缺失的检查项列表（如 `["权限校验", "金额校验"]`） |
| `suggestion` | 是 | 修复建议（简体中文） |
| `confidence` | 是 | 置信度 0.0-1.0 |

### 语言要求
- **所有文本字段必须使用简体中文**（title/description/suggestion/missing_checks）
- 禁止英文输出（除代码和字段名外）

═══════════════════════════════════════════════════════════════

## ⚠️ 关键约束

1. **禁止直接 Final Answer**：必须先调用工具收集证据，至少 2-3 轮工具调用
2. **基于实际代码**：所有 evidence 必须来自 `read_file`/`search_code` 等工具返回
3. **不推送队列**：不得在 findings 中包含 `push_to_queue` 或相关字段
4. **聚焦模式**：必须针对 `entry_points_hint` 列表深度分析，不得遗漏
5. **跳过无效入口**：若入口点文件不存在，注明并跳过，继续分析其他
6. **污点追踪**：必须明确标识 `source`（入口参数）和 `sink`（敏感操作）
7. **检查完整性**：必须检查认证、权限、业务校验、并发保护四个维度

═══════════════════════════════════════════════════════════════

## 📋 完整示例交互

**输入：**
```json
{
    "entry_points_hint": [
        "app/api/order.py:create_order",
        "app/api/user.py:update_profile",
        "app/api/admin.py:reset_password"
    ]
}
```

**执行过程：**

```
Thought: 收到 3 个入口点，进入聚焦模式。按顺序分析：order.py:create_order、user.py:update_profile、admin.py:reset_password。首先读取 order.py。
Action: read_file
Action Input: { "file_path": "app/api/order.py", "max_lines": 100 }

Observation: 
```python
@app.route('/order', methods=['POST'])
def create_order():
    data = request.json
    product_id = data['product_id']
    quantity = data['quantity']
    amount = data['amount']  # 第28行：金额来自前端
    user_id = current_user.id
    
    # 检查库存
    product = Product.query.get(product_id)
    if product.stock < quantity:
        return 'Out of stock', 400
    
    # 创建订单（第36行：直接使用前端金额）
    order = Order(
        user_id=user_id,
        product_id=product_id,
        quantity=quantity,
        amount=amount  # 未校验金额是否正确
    )
    db.session.add(order)
    db.session.commit()
    return jsonify(order.id)
```

Thought: 发现关键问题：amount 直接来自前端 request.json，未与 product.price * quantity 校验。存在金额篡改漏洞。检查是否有其他校验（搜索全局金额校验函数）。
Action: search_code
Action Input: { "keyword": "check_amount|validate_amount|calculate_total", "file_pattern": "*.py", "is_regex": true }

Observation: 未找到全局金额校验函数。

Thought: 确认 create_order 存在金额篡改漏洞。继续分析 user.py:update_profile。
Action: read_file
Action Input: { "file_path": "app/api/user.py", "max_lines": 100 }

Observation:
```python
@app.route('/user/<int:user_id>', methods=['PUT'])
def update_profile(user_id):  # 第42行：用户ID来自URL参数
    if not current_user.is_authenticated:  # 仅有登录检查
        return 'Login required', 401
    
    data = request.json
    # 第47行：直接更新指定user_id的数据，无权限校验
    User.query.filter_by(id=user_id).update(data)
    db.session.commit()
    return 'Updated'
```

Thought: 发现 IDOR 漏洞：仅检查登录状态，未验证 current_user.id == user_id。任意登录用户可修改他人资料。继续分析 admin.py:reset_password。
Action: read_file
Action Input: { "file_path": "app/api/admin.py", "max_lines": 100 }

Observation:
```python
@app.route('/admin/reset-password', methods=['POST'])
def reset_password():
    email = request.json.get('email')
    # 生成重置令牌（第25行：基于时间戳，可预测）
    token = hashlib.md5(f"{email}{int(time.time())}".encode()).hexdigest()
    
    # 保存令牌（无过期时间）
    PasswordResetToken.create(email=email, token=token)
    
    # 发送邮件（省略）
    return 'Reset link sent'

@app.route('/admin/confirm-reset', methods=['POST'])
def confirm_reset():
    token = request.json.get('token')
    new_password = request.json.get('new_password')
    
    # 验证令牌（第40行：无尝试次数限制，可暴力破解）
    reset_token = PasswordResetToken.query.filter_by(token=token).first()
    if reset_token:
        User.query.filter_by(email=reset_token.email).update({'password': new_password})
        return 'Password updated'
    return 'Invalid token', 400
```

Thought: 发现两个漏洞：1) 令牌基于时间戳生成，可预测；2) 无尝试次数限制，可暴力破解。但令牌预测属于加密问题，暴力破解属于速率限制问题，均属于业务逻辑缺陷。检查是否有速率限制装饰器。
Action: search_code
Action Input: { "keyword": "@rate_limit|@limiter|throttle|@require_admin", "file_pattern": "*.py", "is_regex": true }

Observation: 未找到速率限制装饰器，也无管理员权限检查。

Thought: 确认 reset_password 存在业务逻辑缺陷：普通用户可调用管理员密码重置接口（无角色检查），且令牌可暴力破解。构造 findings。
Action: （分析完成，准备输出）

Thought: 已完成 3 个入口点分析，确认 3 个业务逻辑漏洞：金额篡改、IDOR、密码重置缺陷。现在输出结构化 findings。
Final Answer: {
    "findings": [
        {
            "vulnerability_type": "amount_tampering",
            "severity": "high",
            "title": "app/api/order.py:create_order 函数金额篡改漏洞",
            "description": "订单创建接口直接使用前端传入的 amount 参数，未与商品价格×数量进行服务端校验，攻击者可提交任意金额（如负数、极小值）创建异常订单。",
            "file_path": "app/api/order.py",
            "line_start": 28,
            "line_end": 36,
            "function_name": "create_order",
            "code_snippet": "amount = data['amount']\n...\norder = Order(\n    user_id=user_id,\n    product_id=product_id,\n    quantity=quantity,\n    amount=amount  # 未校验金额\n)",
            "source": "request.json['amount']",
            "sink": "Order(amount=amount)",
            "missing_checks": ["金额计算校验", "金额范围校验"],
            "suggestion": "应在服务端重新计算金额：amount = product.price * quantity，并校验传入金额与计算值一致，同时限制金额范围（>0且不超过上限）。",
            "confidence": 0.95
        },
        {
            "vulnerability_type": "idor",
            "severity": "high",
            "title": "app/api/user.py:update_profile 函数 IDOR 越权修改漏洞",
            "description": "用户资料更新接口仅检查登录状态，未验证当前用户是否有权修改指定 user_id 的资料，导致任意登录用户可修改其他用户资料（水平越权）。",
            "file_path": "app/api/user.py",
            "line_start": 42,
            "line_end": 48,
            "function_name": "update_profile",
            "code_snippet": "@app.route('/user/<int:user_id>', methods=['PUT'])\ndef update_profile(user_id):\n    if not current_user.is_authenticated:\n        return 'Login required', 401\n    data = request.json\n    User.query.filter_by(id=user_id).update(data)",
            "source": "user_id 路径参数",
            "sink": "User.query.filter_by(id=user_id).update",
            "missing_checks": ["身份所有权校验", "权限校验"],
            "suggestion": "添加权限校验：仅允许 current_user.id == user_id 或 current_user.is_admin 时执行更新，否则返回 403。",
            "confidence": 0.9
        },
        {
            "vulnerability_type": "password_reset_flaw",
            "severity": "medium",
            "title": "app/api/admin.py:reset_password 函数密码重置逻辑缺陷",
            "description": "密码重置接口存在两处缺陷：1) 重置令牌基于时间戳和邮箱生成，可被预测；2) 无速率限制，可暴力破解令牌；3) 无管理员权限检查，普通用户可调用。",
            "file_path": "app/api/admin.py",
            "line_start": 25,
            "line_end": 40,
            "function_name": "reset_password / confirm_reset",
            "code_snippet": "token = hashlib.md5(f\"{email}{int(time.time())}\".encode()).hexdigest()\n...\nreset_token = PasswordResetToken.query.filter_by(token=token).first()",
            "source": "request.json['token']",
            "sink": "PasswordResetToken.query.filter_by",
            "missing_checks": ["令牌强度校验", "速率限制", "管理员权限校验"],
            "suggestion": "1. 使用加密安全随机数生成令牌（如 secrets.token_urlsafe）；2. 添加速率限制（每邮箱每IP限制尝试次数）；3. 添加 @require_admin 装饰器限制接口访问权限；4. 设置令牌过期时间（如15分钟）。",
            "confidence": 0.85
        }
    ],
    "summary": "发现 3 个业务逻辑漏洞：1个金额篡改（high）、1个IDOR越权（high）、1个密码重置缺陷（medium），均涉及关键业务操作缺少必要校验。"
}
```

═══════════════════════════════════════════════════════════════

现在开始执行你的业务逻辑扫描任务。记住：**聚焦业务逻辑、追踪污点、检查四维校验（认证/权限/业务/并发）**。"""



@dataclass
class ScanPhase:
    phase_num: int
    phase_name: str
    description: str
    max_attempts: int = 3


@dataclass
class BusinessLogicFinding:
    title: str
    vulnerability_type: str
    severity: str
    file_path: str
    function_name: str
    line_start: int
    line_end: Optional[int] = None
    entry_point: Optional[str] = None
    taint_path: List[str] = field(default_factory=list)
    missing_checks: List[str] = field(default_factory=list)
    code_snippet: str = ""
    confidence: float = 0.0
    poc_plan: str = ""
    fix_suggestion: str = ""


class BusinessLogicScanAgent(BaseAgent):
    """业务逻辑漏洞扫描子 Agent。"""
    
    # 类级别的参数化缓存：根据 entry_points_hint 独立缓存
    # key: 缓存 key（通过 entry_points_hint 生成）
    # value: 缓存的 AgentResult 数据
    _cache_dict: Dict[str, Dict[str, Any]] = {}
    _cache_lock = asyncio.Lock()

    def __init__(self, llm_service, tools: Dict[str, Any], event_emitter=None):
        tool_whitelist = ", ".join(sorted(tools.keys())) if tools else "无"
        config = AgentConfig(
            name="BusinessLogicScan",
            agent_type=AgentType.ANALYSIS,
            pattern=AgentPattern.REACT,
            max_iterations=8,
            system_prompt=(
                f"{BUSINESS_LOGIC_SYSTEM_PROMPT}\n\n"
                f"## 当前工具白名单\n{tool_whitelist}\n"
                "只能调用以上工具。"
            ),
        )
        super().__init__(config, llm_service, tools, event_emitter)
        self.findings: List[BusinessLogicFinding] = []
        self.phases: List[ScanPhase] = [
            ScanPhase(1, "HTTP Entry Discovery", "发现所有 HTTP 入口点与路由"),
            ScanPhase(2, "Entry Function Analysis", "分析入口函数的业务逻辑与校验"),
            ScanPhase(3, "Sensitive Operation Anchors", "识别敏感操作与关键检查点"),
            ScanPhase(4, "Lightweight Taint Analysis", "追踪参数传播并识别缺失校验"),
            ScanPhase(5, "Logic Vulnerability Confirm", "确认漏洞类型、严重程度与修复建议"),
        ]
        # 聚焦模式下的简化阶段（跳过第 1 阶段全局入口发现）
        self.focused_phases: List[ScanPhase] = [
            ScanPhase(2, "Entry Function Analysis", "分析指定接口的业务逻辑、鉴权和权限检查"),
            ScanPhase(3, "Sensitive Operation Anchors", "识别敏感操作与关键检查点"),
            ScanPhase(4, "Lightweight Taint Analysis", "追踪参数传播并识别缺失校验"),
            ScanPhase(5, "Logic Vulnerability Confirm", "确认漏洞类型、严重程度与修复建议"),
        ]
        self._focused_mode = False  # 标记是否为聚焦模式

    @staticmethod
    def _get_cache_key(entry_points_hint: Optional[List[str]]) -> str:
        """
        根据 entry_points_hint 生成缓存 key。
        
        - 如果 entry_points_hint 为空或 None，返回 "global_scan"
        - 如果 entry_points_hint 非空，生成基于内容的 key
        
        这允许不同的接口列表被独立缓存。
        """
        if not entry_points_hint:
            return "global_scan"
        
        # 创建标准化类型
        normalized = sorted([str(ep).strip() for ep in entry_points_hint if ep])
        if not normalized:
            return "global_scan"
        
        # 使用简单的字符串连接作为 key（而非复杂的哈希）
        key_str = "::".join(normalized)
        # 如果 key 太长，使用 hash
        if len(key_str) > 256:
            import hashlib
            return f"focused_scan_{hashlib.md5(key_str.encode()).hexdigest()}"
        return f"focused_scan_{key_str}"

    @classmethod
    def reset_cache(cls, entry_points_hint: Optional[List[str]] = None) -> None:
        """
        重置扫描缓存状态。
        
        Args:
            entry_points_hint: 如果指定，仅重置该 entry_points_hint 对应的缓存；
                              如果为 None，重置所有缓存。
        
        用于测试、调试或需要重新执行扫描的场景。
        """
        if entry_points_hint is None:
            # 重置所有缓存
            cls._cache_dict.clear()
            logger.info("[BusinessLogicScanAgent] 所有缓存已重置")
        else:
            # 重置特定的缓存
            cache_key = cls._get_cache_key(entry_points_hint)
            if cache_key in cls._cache_dict:
                del cls._cache_dict[cache_key]
                logger.info(
                    "[BusinessLogicScanAgent] 缓存已重置: %s",
                    cache_key,
                )

    @classmethod
    def is_scan_cached(cls, entry_points_hint: Optional[List[str]] = None) -> bool:
        """检查指定的 entry_points_hint 是否已有缓存的扫描结果"""
        cache_key = cls._get_cache_key(entry_points_hint)
        return cache_key in cls._cache_dict

    @classmethod
    def get_cache_info(cls) -> Dict[str, Any]:
        """获取缓存信息（用于诊断）"""
        if not cls._cache_dict:
            return {"cached_entries": 0, "total_keys": 0}
        
        info = {
            "cached_entries": len(cls._cache_dict),
            "total_keys": len(cls._cache_dict),
            "caches": {}
        }
        
        for key, cached in cls._cache_dict.items():
            info["caches"][key] = {
                "success": cached.get("success"),
                "cached_at": cached.get("cached_at"),
                "findings_count": len(cached.get("data", {}).get("findings", [])),
            }
        
        return info

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """执行业务逻辑扫描 - 支持参数化缓存和聚焦模式"""
        start_time = time.time()
        
        target = str(input_data.get("target") or ".")
        framework_hint = input_data.get("framework_hint")
        entry_points_hint = input_data.get("entry_points_hint") or []
        quick_mode = bool(input_data.get("quick_mode", False))
        max_iterations = int(input_data.get("max_iterations") or self.config.max_iterations)
        
        # 生成缓存 key
        cache_key = self._get_cache_key(entry_points_hint)
        
        # === 参数化缓存检查机制 ===
        async with self._cache_lock:
            if cache_key in self._cache_dict:
                # 缓存命中，返回缓存结果
                logger.info(
                    "[BusinessLogicScanAgent] 缓存命中: %s，返回缓存结果",
                    cache_key,
                )
                await self.emit_event(
                    "info",
                    f"业务逻辑扫描缓存命中 ({cache_key})，返回之前的扫描结果"
                )
                
                cached = self._cache_dict[cache_key]
                duration_ms = int((time.time() - start_time) * 1000)
                # 标记为缓存调用
                cached_data = dict(cached.get("data", {}))
                cached_data["from_cache"] = True
                cached_data["cached_at"] = cached.get("cached_at")
                return AgentResult(
                    success=cached["success"],
                    data=cached_data,
                    iterations=cached.get("iterations", 0),
                    tool_calls=cached.get("tool_calls", 0),
                    tokens_used=cached.get("tokens_used", 0),
                    duration_ms=duration_ms,
                    handoff=cached.get("handoff"),
                )
            
            logger.info(
                "[BusinessLogicScanAgent] 缓存不存在: %s，执行新的扫描",
                cache_key,
            )
        
        # === 判断执行模式 ===
        self._focused_mode = bool(entry_points_hint)
        if self._focused_mode:
            await self.emit_thinking(f"🎯 业务逻辑扫描聚焦模式：分析 {len(entry_points_hint)} 个接口")
            logger.info(
                "[BusinessLogicScanAgent] 进入聚焦模式，分析 %d 个接口",
                len(entry_points_hint),
            )
        else:
            await self.emit_thinking("🌍 业务逻辑扫描全局模式：完整 5 阶段分析")
            logger.info("[BusinessLogicScanAgent] 进入全局模式，执行完整扫描")

        scan_context: Dict[str, Any] = {
            "target": target,
            "framework_hint": framework_hint or "unknown",
            "entry_points_hint": entry_points_hint,
            "quick_mode": quick_mode,
            "phase": 0,
            "iteration": 0,
            "max_iterations": max_iterations,
            "findings": [],
            "discovered_entries": [],
            "entry_analysis": [],
            "sensitive_operations": [],
            "taint_paths": [],
        }

        self.record_work(f"开始业务逻辑扫描: target={target}, mode={'focused' if self._focused_mode else 'global'}")

        try:
            # 根据模式选择要执行的阶段
            phases_to_run = self.focused_phases if self._focused_mode else self.phases
            
            for phase in phases_to_run:
                if self.is_cancelled:
                    break

                scan_context["phase"] = phase.phase_num
                await self.emit_thinking(f"🧠 BusinessLogicScan 第 {phase.phase_num} 阶段: {phase.phase_name}")

                phase_result = await self._run_phase_with_react(phase, scan_context)
                if phase_result.get("success"):
                    self._update_context_from_phase_result(scan_context, phase, phase_result)
                    self.record_work(f"完成阶段 {phase.phase_num}: {phase.phase_name}")
                else:
                    logger.warning(
                        "[BusinessLogicScan] phase=%s failed: %s",
                        phase.phase_num,
                        phase_result.get("error"),
                    )

            report = self._generate_report(scan_context)
            findings_dict = [self._finding_to_dict(finding) for finding in self.findings]
            for finding in findings_dict[:20]:
                self.add_insight(
                    f"业务逻辑漏洞[{finding.get('severity', 'medium')}] {finding.get('title', 'Unknown')}"
                )

            handoff = self.create_handoff(
                to_agent="Analysis",
                summary=f"业务逻辑子扫描完成，共发现 {len(findings_dict)} 个候选漏洞。",
                key_findings=findings_dict,
                suggested_actions=[
                    {
                        "type": "verification",
                        "priority": "high",
                        "description": "优先验证 IDOR/权限提升/支付路径相关业务逻辑漏洞",
                    }
                ],
                attention_points=[
                    "重点复核缺失所有权校验和角色层级校验场景",
                    "对高危 findings 进行动态可达性验证",
                ],
                priority_areas=[
                    item.get("file_path", "")
                    for item in findings_dict[:10]
                    if isinstance(item, dict) and item.get("file_path")
                ],
                context_data={
                    "phase_1_entries": len(scan_context["discovered_entries"]),
                    "phase_3_sensitive_ops": len(scan_context["sensitive_operations"]),
                    "phase_4_taint_paths": len(scan_context["taint_paths"]),
                    "scan_mode": "focused" if self._focused_mode else "global",
                },
            )

            duration_ms = int((time.time() - start_time) * 1000)
            result = AgentResult(
                success=not self.is_cancelled,
                data={
                    "report": report["text"],
                    "findings": findings_dict,
                    "phase_1_entries": len(scan_context["discovered_entries"]),
                    "phase_3_sensitive_ops": scan_context["sensitive_operations"],
                    "phase_4_taint_paths": scan_context["taint_paths"],
                    "total_findings": len(findings_dict),
                    "by_severity": self._count_by_severity(),
                    "scan_mode": "focused" if self._focused_mode else "global",
                },
                iterations=self._iteration,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
                handoff=handoff,
            )
            
            # === 缓存本次结果供后续调用使用 ===
            self._cache_dict[cache_key] = {
                "success": result.success,
                "data": result.data,
                "iterations": result.iterations,
                "tool_calls": result.tool_calls,
                "tokens_used": result.tokens_used,
                "duration_ms": result.duration_ms,
                "handoff": result.handoff,
                "cached_at": time.time(),
            }
            logger.info(
                "[BusinessLogicScanAgent] 扫描完成，结果已缓存于 %s。"
                "后续同样的 entry_points_hint 调用将返回此缓存结果。",
                cache_key,
            )
            
            return result
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error("BusinessLogicScanAgent failed: %s", exc, exc_info=True)
            result = AgentResult(
                success=False,
                error=str(exc),
                data={"findings": []},
                iterations=self._iteration,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
            )
            
            # === 即使失败也缓存结果，但标记为失败状态 ===
            self._cache_dict[cache_key] = {
                "success": False,
                "data": {"findings": [], "error": str(exc)},
                "iterations": self._iteration,
                "tool_calls": self._tool_calls,
                "tokens_used": self._total_tokens,
                "duration_ms": duration_ms,
                "handoff": None,
                "cached_at": time.time(),
            }
            logger.warning(
                "[BusinessLogicScanAgent] 扫描执行失败，失败结果已缓存于 %s。"
                "后续同样的 entry_points_hint 调用将返回此失败状态。",
                cache_key,
            )
            
            return result

    async def _run_phase_with_react(self, phase: ScanPhase, context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.llm_service:
            return self._generate_demo_phase_result(phase.phase_num)

        phase_prompt = self._build_phase_prompt(phase, context)
        conversation_history: List[Dict[str, str]] = [
            {"role": "system", "content": self.config.system_prompt or BUSINESS_LOGIC_SYSTEM_PROMPT},
            {"role": "user", "content": phase_prompt},
        ]

        max_turns = max(3, min(8, phase.max_attempts * 2))
        tool_used = False

        for _ in range(max_turns):
            self._iteration += 1
            if self._iteration > int(context.get("max_iterations") or self.config.max_iterations):
                return {"success": False, "error": "达到最大迭代次数"}

            llm_output, tokens_this_round = await self.stream_llm_call(conversation_history)
            self._total_tokens += tokens_this_round

            parsed = parse_react_response(
                llm_output,
                final_default={"success": False, "error": "invalid_phase_result", "raw": llm_output},
            )

            conversation_history.append({"role": "assistant", "content": llm_output})

            if parsed.action:
                tool_used = True
                observation = await self.execute_tool(parsed.action, parsed.action_input or {})
                conversation_history.append({"role": "user", "content": f"Observation:\n{observation}"})
                continue

            if parsed.is_final:
                final_answer = parsed.final_answer if isinstance(parsed.final_answer, dict) else {}
                if not tool_used:
                    conversation_history.append(
                        {
                            "role": "user",
                            "content": "你在未调用任何工具前就尝试结束。请先调用至少一个工具获取代码证据，再输出 Final Answer。",
                        }
                    )
                    continue
                final_answer["success"] = True
                return final_answer

            conversation_history.append(
                {
                    "role": "user",
                    "content": "请按格式继续：先输出 Action 并调用工具，或在证据充分后输出 Final Answer JSON。",
                }
            )

        return {"success": False, "error": f"阶段 {phase.phase_num} 未能在限定轮次内完成"}

    def _build_phase_prompt(self, phase: ScanPhase, context: Dict[str, Any]) -> str:
        base_prompt = f"""你正在执行业务逻辑扫描第 {phase.phase_num} 阶段。

## 当前阶段
- 阶段: {phase.phase_name}
- 描述: {phase.description}
- 模式: {'聚焦模式' if self._focused_mode else '全局模式'}

## 项目信息
- target: {context['target']}
- framework_hint: {context['framework_hint']}
- quick_mode: {context['quick_mode']}

## 已有上下文
- discovered_entries: {len(context['discovered_entries'])}
- sensitive_operations: {len(context['sensitive_operations'])}
- taint_paths: {len(context['taint_paths'])}
- findings: {len(context['findings'])}

先进行 Thought，然后调用工具（Action）获取证据。证据充分后再输出 Final Answer JSON。
"""

        # === 聚焦模式：阶段 2 - 直接分析指定的接口 ===
        if self._focused_mode and phase.phase_num == 2:
            entry_points_str = json.dumps(context.get("entry_points_hint", [])[:10], ensure_ascii=False, indent=2)
            return (
                base_prompt
                + f"""
## 目标
分析以下指定接口的业务逻辑、鉴权和权限检查（聚焦模式）。

## 待分析的接口列表
{entry_points_str}

## 分析重点
1. 定位每个接口的处理函数
2. 分析其中的鉴权逻辑（是否有 @login_required 等装饰器）
3. 分析权限检查（是否验证用户身份和权限）
4. 识别输入参数中包含的用户/资源标识符
5. 评估接口风险等级

## Final Answer JSON
{{
  "entry_analysis": [
    {{
      "entry": "接口路径",
      "handler": "文件:函数",
      "logic": "业务逻辑描述",
      "auth_checks": ["鉴权检查列表"],
      "permission_checks": ["权限检查列表"],
      "input_params": ["输入参数列表"],
      "risk": "风险评估"
    }}
  ],
  "summary": "分析总结"
}}
"""
            )

        if phase.phase_num == 1:
            return (
                base_prompt
                + """
## 目标
发现 HTTP 入口点（method/path/handler_file/handler_function/handler_line）。

## 建议工具
- search_code: 搜索路由装饰器/路由注册
- read_file: 阅读路由文件与控制器
- extract_function: 提取入口处理函数

## Final Answer JSON
{
  "entries": [{"method": "GET", "path": "/api/user/{id}", "handler_file": "...", "handler_function": "...", "handler_line": 1}],
  "summary": "..."
}
"""
            )

        if phase.phase_num == 2 and not self._focused_mode:
            seed_entries = json.dumps(context.get("discovered_entries", [])[:8], ensure_ascii=False, indent=2)
            return (
                base_prompt
                + f"""
## 目标
分析关键入口的业务逻辑、鉴权和权限检查（全局模式）。

## 入口样例
{seed_entries}

## Final Answer JSON
{{
  "entry_analysis": [
    {{
      "entry": "GET /api/user/{{user_id}}",
      "handler": "app/api/user.py:get_user_profile",
      "logic": "...",
      "auth_checks": ["..."],
      "permission_checks": ["..."],
      "input_params": ["..."],
      "risk": "..."
    }}
  ],
  "summary": "..."
}}
"""
            )

        if phase.phase_num == 3:
            return (
                base_prompt
                + """
## 目标
识别敏感操作锚点（数据修改、权限变更、资金操作、账号操作）及其前置检查。

## Final Answer JSON
{
  "sensitive_operations": [
    {
      "entry": "...",
      "operation": "...",
      "operation_file": "...",
      "operation_line": 1,
      "operation_type": "data_modification|permission_change|financial_operation|account_operation",
      "checks_before": ["..."],
      "checks_missing": ["..."]
    }
  ],
  "summary": "..."
}
"""
            )

        if phase.phase_num == 4:
            return (
                base_prompt
                + """
## 目标
追踪入口参数到敏感操作的数据传播路径，识别缺失授权/所有权校验。

## 建议工具
- controlflow_analysis_light
- dataflow_analysis
- read_file

## Final Answer JSON
{
  "taint_paths": [
    {
      "entry": "...",
      "sensitive_op": "...",
      "entry_params": ["..."],
      "taint_flow": ["..."],
      "missing_check": "...",
      "vulnerability_class": "IDOR|horizontal_privilege_escalation|vertical_privilege_escalation|business_logic_flaw"
    }
  ],
  "summary": "..."
}
"""
            )

        return (
            base_prompt
            + """
## 目标
确认最终业务逻辑漏洞，输出结构化 findings（用于后续验证阶段）。

## Final Answer JSON
{
  "findings": [
    {
      "title": "路径中函数具体漏洞名",
      "vulnerability_type": "horizontal_privilege_escalation|vertical_privilege_escalation|idor|business_logic_flaw",
      "severity": "critical|high|medium|low",
      "confidence": 0.9,
      "file_path": "...",
      "function_name": "...",
      "line_start": 1,
      "line_end": 1,
      "entry_point": "...",
      "missing_checks": ["..."],
      "taint_path": ["..."],
      "code_snippet": "...",
      "poc_plan": "...",
      "fix_suggestion": "..."
    }
  ],
  "summary": "..."
}
"""
        )

    def _generate_demo_phase_result(self, phase: int) -> Dict[str, Any]:
        if phase == 1:
            return {
                "success": True,
                "entries": [
                    {
                        "method": "GET",
                        "path": "/api/user/{user_id}",
                        "handler_file": "app/api/user.py",
                        "handler_function": "get_user_profile",
                        "handler_line": 78,
                    }
                ],
                "summary": "发现 1 个入口点",
            }
        if phase == 2:
            return {
                "success": True,
                "entry_analysis": [
                    {
                        "entry": "GET /api/user/{user_id}",
                        "handler": "app/api/user.py:get_user_profile",
                        "logic": "返回用户资料",
                        "auth_checks": ["@login_required"],
                        "permission_checks": [],
                        "input_params": ["user_id"],
                        "risk": "可能 IDOR",
                    }
                ],
                "summary": "发现 1 个风险点",
            }
        if phase == 3:
            return {
                "success": True,
                "sensitive_operations": [
                    {
                        "entry": "GET /api/user/{user_id}",
                        "operation": "SELECT * FROM users WHERE id=?",
                        "operation_file": "app/db.py",
                        "operation_line": 45,
                        "operation_type": "data_modification",
                        "checks_before": ["@login_required"],
                        "checks_missing": ["user_ownership"],
                    }
                ],
                "summary": "发现 1 个敏感操作",
            }
        if phase == 4:
            return {
                "success": True,
                "taint_paths": [
                    {
                        "entry": "GET /api/user/{user_id}",
                        "sensitive_op": "SELECT * FROM users WHERE id=?",
                        "entry_params": ["user_id"],
                        "taint_flow": ["user_id", "query", "execute"],
                        "missing_check": "current_user.id == user_id",
                        "vulnerability_class": "IDOR",
                    }
                ],
                "summary": "识别 1 条污染路径",
            }
        return {
            "success": True,
            "findings": [
                {
                    "title": "app/api/user.py中get_user_profile函数水平越权漏洞",
                    "vulnerability_type": "horizontal_privilege_escalation",
                    "severity": "high",
                    "confidence": 0.9,
                    "file_path": "app/api/user.py",
                    "function_name": "get_user_profile",
                    "line_start": 78,
                    "entry_point": "GET /api/user/{user_id}",
                    "missing_checks": ["current_user.id == user_id"],
                    "taint_path": ["user_id", "db.query", "execute"],
                    "poc_plan": "使用其他用户 user_id 请求接口验证越权读取。",
                    "fix_suggestion": "补充所有权校验并拒绝越权访问。",
                }
            ],
            "summary": "确认 1 个业务逻辑漏洞",
        }

    def _update_context_from_phase_result(self, context: Dict[str, Any], phase: ScanPhase, result: Dict[str, Any]) -> None:
        if phase.phase_num == 1 and isinstance(result.get("entries"), list):
            context["discovered_entries"].extend(result.get("entries", []))
            return

        if phase.phase_num == 2 and isinstance(result.get("entry_analysis"), list):
            context["entry_analysis"] = result.get("entry_analysis", [])
            return

        if phase.phase_num == 3 and isinstance(result.get("sensitive_operations"), list):
            context["sensitive_operations"].extend(result.get("sensitive_operations", []))
            return

        if phase.phase_num == 4 and isinstance(result.get("taint_paths"), list):
            context["taint_paths"].extend(result.get("taint_paths", []))
            return

        if phase.phase_num == 5 and isinstance(result.get("findings"), list):
            for finding_dict in result.get("findings", []):
                finding = self._dict_to_finding(finding_dict)
                self.findings.append(finding)
                context["findings"].append(finding_dict)

    def _dict_to_finding(self, payload: Dict[str, Any]) -> BusinessLogicFinding:
        return BusinessLogicFinding(
            title=str(payload.get("title") or ""),
            vulnerability_type=str(payload.get("vulnerability_type") or "business_logic_flaw"),
            severity=str(payload.get("severity") or "medium"),
            file_path=str(payload.get("file_path") or ""),
            function_name=str(payload.get("function_name") or ""),
            line_start=int(payload.get("line_start") or 0),
            line_end=(int(payload.get("line_end")) if payload.get("line_end") is not None else None),
            entry_point=(str(payload.get("entry_point")) if payload.get("entry_point") else None),
            taint_path=(payload.get("taint_path") if isinstance(payload.get("taint_path"), list) else []),
            missing_checks=(payload.get("missing_checks") if isinstance(payload.get("missing_checks"), list) else []),
            code_snippet=str(payload.get("code_snippet") or ""),
            confidence=float(payload.get("confidence") or 0.0),
            poc_plan=str(payload.get("poc_plan") or ""),
            fix_suggestion=str(payload.get("fix_suggestion") or ""),
        )

    def _finding_to_dict(self, finding: BusinessLogicFinding) -> Dict[str, Any]:
        return {
            "title": finding.title,
            "vulnerability_type": finding.vulnerability_type,
            "severity": finding.severity,
            "file_path": finding.file_path,
            "function_name": finding.function_name,
            "line_start": finding.line_start,
            "line_end": finding.line_end,
            "entry_point": finding.entry_point,
            "taint_path": finding.taint_path,
            "missing_checks": finding.missing_checks,
            "code_snippet": finding.code_snippet,
            "confidence": finding.confidence,
            "poc_plan": finding.poc_plan,
            "fix_suggestion": finding.fix_suggestion,
            "needs_verification": True,
            "source": "business_logic_scan_sub_agent",
        }

    def _generate_report(self, context: Dict[str, Any]) -> Dict[str, str]:
        findings_count = len(self.findings)
        by_severity = self._count_by_severity()

        lines = [
            "🧠 业务逻辑漏洞审计报告（Sub Agent）",
            "",
            "📊 审计概览:",
            f"- HTTP 入口数: {len(context['discovered_entries'])}",
            f"- 敏感操作: {len(context['sensitive_operations'])}",
            f"- 污染路径: {len(context['taint_paths'])}",
            f"- 发现漏洞: {findings_count}",
            "",
        ]

        for level in ("critical", "high", "medium", "low"):
            if by_severity[level] > 0:
                lines.append(f"- {level.upper()}: {by_severity[level]}")

        if findings_count <= 0:
            lines.extend(["", "✅ 未发现明确业务逻辑漏洞候选"]) 
        else:
            lines.extend(["", "🔍 Top Findings:"])
            sorted_findings = sorted(
                self.findings,
                key=lambda item: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(item.severity, 4),
            )
            for idx, finding in enumerate(sorted_findings[:5], 1):
                lines.append(
                    f"{idx}. [{finding.severity.upper()}] {finding.title} ({finding.file_path}:{finding.line_start})"
                )

        return {"text": "\n".join(lines)}

    def _count_by_severity(self) -> Dict[str, int]:
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for finding in self.findings:
            key = finding.severity.lower().strip()
            if key in counts:
                counts[key] += 1
        return counts
