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



BUSINESS_LOGIC_SYSTEM_PROMPT = """你是 VulHunter 的业务逻辑漏洞扫描子 Agent，专注于识别 Web 应用中的**业务逻辑缺陷**（如 IDOR、权限绕过、金额篡改、竞争条件、批量赋值等）。

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
| **水平越权** | `horizontal_privilege_escalation` | 同级用户访问他人资源（读/写） | 无 current_user.id == resource.owner_id 校验 |
| **垂直越权** | `vertical_privilege_escalation` | 普通用户执行管理员操作 | 缺少 is_admin / role 校验 |
| **金额篡改** | `amount_tampering` | 支付、订单金额可被前端控制或修改 | `amount = request.json['amount']` 无服务端校验 |
| **数量/限购绕过** | `quantity_manipulation` | 商品数量、库存、限购次数可被篡改 | `quantity` 参数无上限检查，负数购买 |
| **条件竞争** | `race_condition` | 并发场景下的 TOCTOU（先检查后使用）漏洞 | 无锁操作共享资源（余额、库存、优惠券） |
| **流程绕过** | `workflow_bypass` | 跳过必要步骤（如未支付直接发货，跳过验证） | 状态机检查缺失，直接调用后续接口 |
| **验证码绕过** | `captcha_bypass` | 验证码可重复使用、前端验证、或完全缺失 | 验证码未绑定 session，无服务端校验 |
| **密码重置漏洞** | `password_reset_flaw` | 重置令牌可预测、可暴力破解、或验证逻辑缺陷 | 令牌基于时间戳，无尝试次数限制 |
| **批量操作滥用** | `bulk_operation_abuse` | 批量接口无限制，导致数据泄露或资源耗尽 | 批量查询/删除无数量上限 |
| **信息泄露** | `information_disclosure` | 敏感信息通过接口泄露（遍历、模糊查询） | 返回字段包含敏感数据，无脱敏 |
| **批量赋值** | `mass_assignment` | 用户可覆盖不应修改的模型字段（如 role、is_admin） | `User(**request.json)` 或 `.update(data)` 无字段白名单 |
| **接口链式利用** | `api_chaining` | 组合多个低危接口实现高危目标 | 单接口无明显问题，组合使用可绕过限制 |
| **二阶逻辑漏洞** | `second_order_logic` | 数据先被存储，后被另一接口不安全处理 | 注册时存入特权角色，登录时未重新校验 |

### 框架特定权限检查模式（必须对照检查）

#### Python / Flask
```python
# 应存在的鉴权
@login_required
@jwt_required()
if current_user.id != user_id: abort(403)
if not current_user.is_admin: abort(403)

# 危险模式（缺少所有权校验）
User.query.filter_by(id=user_id).update(data)  # 无 current_user.id == user_id
```

#### Python / FastAPI
```python
# 应存在的依赖注入鉴权
async def endpoint(user: User = Depends(get_current_user)): ...
async def endpoint(user: User = Depends(require_admin)): ...

# 危险模式（缺少 Depends 参数）
@router.put("/users/{user_id}")
async def update_user(user_id: int, data: dict):  # 无 current_user
    await db.execute(update(User).where(User.id == user_id).values(**data))
```

#### Python / Django
```python
# 应存在
@login_required
@permission_required('app.change_user')
if request.user.id != user_id: return HttpResponseForbidden()

# 危险模式
User.objects.filter(pk=user_id).update(**request.POST.dict())  # 批量赋值
```

#### Java / Spring
```java
// 应存在
@PreAuthorize("hasRole('ADMIN')")
@PreAuthorize("#user.id == authentication.principal.id")

// 危险模式（mass assignment）
userRepository.save(userFromRequest);  // 直接保存请求体对象
```

#### Node.js / Express
```javascript
// 应存在
router.put('/users/:id', authenticate, authorize('admin'), handler)

// 危险模式
await User.findByIdAndUpdate(req.params.id, req.body)  // 无所有权校验 + mass assignment
```

### 批量赋值（Mass Assignment）检测信号
```python
# 危险：直接用用户输入更新模型
User(**request.json)                           # Flask/SQLAlchemy
User.objects.filter(pk=pk).update(**data)      # Django（无字段白名单）
userRepository.save(userFromRequest)           # Spring（直接 save 请求体）
User.findByIdAndUpdate(id, req.body)           # Mongoose（无 $set 字段限制）

# 安全：使用字段白名单
ALLOWED = {'name', 'email', 'bio'}
data = {k: v for k, v in request.json.items() if k in ALLOWED}
```

### TOCTOU（竞态条件）检测信号
```python
# 危险：check-then-act 无原子性
balance = user.balance
if balance >= amount:        # 检查
    user.balance -= amount   # 使用（并发时可超支）
    db.save(user)

# 安全：数据库级原子操作
User.query.with_for_update().filter_by(id=uid).first()
UPDATE users SET balance = balance - ? WHERE id=? AND balance >= ?
```

### 业务场景检查清单

| 场景 | 必检项目 | 关键风险参数 | 高危模式 |
|------|---------|------------|---------|
| **用户管理** | 注册、登录、密码修改、资料更新、用户列表 | `user_id`, `is_admin`, `role`, `password` | 批量赋值覆盖 role/is_admin |
| **订单/支付** | 创建订单、支付回调、退款、优惠券使用 | `amount`, `price`, `order_id`, `coupon_code`, `status` | 前端传入金额、竞态重复支付 |
| **内容管理** | 发布、编辑、删除、查看、搜索 | `post_id`, `author_id`, `visibility`, `content` | 越权修改/删除他人内容 |
| **权限管理** | 角色分配、菜单权限、数据权限 | `role_id`, `permission`, `resource_id` | 普通用户提升至 admin |
| **文件管理** | 上传、下载、删除、分享 | `file_id`, `owner_id`, `path` | 遍历他人文件 ID |
| **消息/通知** | 发送、读取、删除、批量操作 | `message_id`, `recipient_id`, `type` | 越权读取私信 |
| **积分/虚拟币** | 充值、消费、转账、提现 | `points`, `balance`, `to_user_id` | 竞态超支、负数转账 |
| **审批流程** | 提交、审核、驳回、转交 | `status`, `approver_id`, `comment` | 跳过审核状态机 |
| **管理员接口** | 用户封禁、数据导出、配置修改 | `target_id`, `action`, `config` | 缺少 admin 角色校验 |

═══════════════════════════════════════════════════════════════

## 🛠️ 工具使用策略

### 核心工具

| 工具 | 用途 | 调用时机 |
|------|------|---------|
| `read_file` | 读取入口函数完整代码 | 分析每个 entry point 时必用 |
| `search_code` | 搜索权限校验、装饰器、危险模式 | 每个阶段的横向验证 |
| `extract_function` | 提取完整函数体进行污点分析 | 需要追踪跨函数数据流时 |

### 辅助工具（如可用）
- `dataflow_analysis`: 追踪参数从入口到敏感操作的完整路径
- `controlflow_analysis_light`: 分析条件分支，检查遗漏的校验

### 高效搜索策略（优先使用）
```
# 搜索框架鉴权模式
"@login_required|@jwt_required|Depends(get_current_user)|@permission_required"

# 搜索危险的直接对象操作（IDOR 信号）
"filter_by\\(id=|find_by_id|get_or_404|findById|WHERE.*id\\s*="

# 搜索批量赋值风险
"\\*\\*request\\.json|\\*\\*data|update_attributes|\\.update\\(data\\)|save\\(.*[Rr]equest"

# 搜索金额/余额操作（竞态条件信号）
"balance.*-=|amount.*=.*request|price.*=.*request\\.json"

# 搜索状态机操作（流程绕过信号）
"status\\s*=\\s*['\"](approved|shipped|paid|completed)|state\\s*=\\s*request"
```

**Note**: 所有文件路径使用相对于项目根目录的路径（如 `app/api/user.py`），禁止绝对路径。

═══════════════════════════════════════════════════════════════

## 🔄 标准分析流程

```
步骤1: 读取入口函数
    └─> read_file 读取 entry_point 所在文件（取足够行数）
    └─> 定位函数，识别所有用户可控参数

步骤2: 识别关键要素
    ├─> 入口参数：URL参数 / 请求体 / Header / Cookie
    ├─> 框架鉴权：是否有装饰器/依赖注入？（对照框架模式）
    ├─> 批量赋值：是否使用 **data / **request.json？
    ├─> 敏感操作：是否操作资金、权限、他人数据？
    └─> 校验逻辑：所有权校验、角色校验是否存在且充分？

步骤3: 横向搜索验证
    ├─> search_code 搜索是否有全局/中间件层面的权限控制
    ├─> search_code 验证是否存在统一的金额校验、数量校验工具函数
    └─> 确认局部缺失不是被全局补偿的

步骤4: 污点追踪（轻量级）
    ├─> source: 用户可控输入点（URL/Body/Header/Cookie）
    ├─> taint_flow: 参数传播步骤列表
    └─> sink: 敏感操作（DB 写入、支付调用、权限变更）

步骤5: 漏洞判定（四维校验）
    ├─> [认证] 是否有身份认证？
    ├─> [权限] 是否有资源所有权/角色校验？
    ├─> [业务] 金额/数量/状态/字段是否有服务端校验？
    ├─> [并发] 是否有锁/原子操作/幂等保护？
    └─> 任一缺失 + 有可利用路径 → 输出 finding

步骤6: 构造 finding（必须基于工具证据）
    └─> code_snippet 必须是工具实际返回的代码
    └─> line_start/line_end 必须准确
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
            "title": "app/api/user.py:update_profile 函数 IDOR 越权修改漏洞",
            "description": "接口仅校验登录状态，未验证当前用户是否与目标 user_id 一致，任意已登录用户可修改他人资料（水平越权）。",
            "file_path": "app/api/user.py",
            "line_start": 42,
            "line_end": 48,
            "function_name": "update_profile",
            "code_snippet": "@app.route('/user/<int:user_id>', methods=['PUT'])\ndef update_profile(user_id):\n    data = request.json\n    db.update_user(user_id, data)\n    return 'OK'",
            "source": "user_id 路径参数（URL: /user/<int:user_id>）",
            "sink": "db.update_user(user_id, data) 直接操作目标用户数据",
            "taint_flow": [
                "URL 路径参数 user_id 由调用者完全控制",
                "直接传入 update_user(user_id, data) 无所有权校验",
                "执行 UPDATE users SET ... WHERE id=user_id"
            ],
            "missing_checks": [
                "current_user.id == user_id 所有权校验",
                "current_user.is_admin 管理员豁免校验"
            ],
            "suggestion": "添加所有权校验：if current_user.id != user_id and not current_user.is_admin: abort(403)",
            "poc_plan": "以用户A身份登录，发送 PUT /user/<用户B的ID> 携带修改数据，观察是否成功修改他人资料。",
            "confidence": 0.92
        }
    ],
    "summary": "发现 2 个业务逻辑漏洞：1个IDOR越权（high），1个金额篡改（high）"
}
```

### 字段说明
| 字段 | 必填 | 说明 |
|------|------|------|
| `vulnerability_type` | 是 | 漏洞类型标识（见上方类型体系） |
| `severity` | 是 | `critical` / `high` / `medium` / `low` |
| `title` | 是 | **中文三段式**：`文件路径:函数名` + `漏洞类型简述` |
| `description` | 是 | 漏洞原理、触发条件、危害（简体中文，2-3句） |
| `file_path` | 是 | 相对于项目根目录的路径 |
| `line_start` / `line_end` | 是 | 漏洞代码行号（来自工具实际返回，必须准确） |
| `function_name` | 是 | 所在函数名 |
| `code_snippet` | 是 | 关键代码片段（工具实际返回的代码，含足够上下文） |
| `source` | 是 | 污点来源（用户可控的具体输入点，含参数名和位置） |
| `sink` | 是 | 敏感操作点（具体危险调用，含函数名） |
| `taint_flow` | 是 | 数据流路径列表（source → sink 的完整步骤） |
| `missing_checks` | 是 | 缺失的具体代码级校验列表 |
| `suggestion` | 是 | 修复建议（含具体代码示例，简体中文） |
| `poc_plan` | 是 | 漏洞复现步骤（攻击者如何利用，简体中文） |
| `confidence` | 是 | 置信度 0.0-1.0（证据越充分越高） |

### 严重性评定标准
- **critical**: 直接导致资金损失、账户接管、全量数据泄露
- **high**: 水平越权读写他人数据、提升管理员权限、绕过核心业务规则
- **medium**: 流程绕过（无直接财务影响）、竞态条件（需特定触发）、批量赋值（低敏感字段）
- **low**: 速率限制缺失（仅枚举风险）、非敏感信息泄露、低危信息暴露

### 语言要求
- **所有描述性文本字段必须使用简体中文**（title/description/suggestion/missing_checks/poc_plan）
- 禁止英文叙述（除代码、字段名、技术术语外）

═══════════════════════════════════════════════════════════════

## ⚠️ 关键约束

1. **禁止直接 Final Answer**：必须先调用工具收集代码证据，至少 3 轮工具调用
2. **基于实际代码**：code_snippet 必须是工具实际返回的代码，行号必须准确
3. **不推送队列**：不得在 findings 中包含 `push_to_queue` 或相关字段
4. **聚焦模式**：必须针对 `entry_points_hint` 列表逐一深度分析，不得遗漏
5. **横向验证**：发现局部缺失校验时，必须 search_code 确认无全局补偿
6. **完整污点链**：必须完整标识 source → taint_flow → sink 路径
7. **四维检查**：必须逐一检查认证、权限、业务校验、并发保护四个维度
8. **批量赋值必查**：每个接收请求体并写入模型的接口，必须检查字段白名单
9. **置信度诚实**：证据不足时置信度应 < 0.7，并说明不确定原因

═══════════════════════════════════════════════════════════════

现在开始执行你的业务逻辑扫描任务。记住：**聚焦业务逻辑、追踪完整污点链（source→flow→sink）、检查四维校验（认证/权限/业务/并发）、不放过批量赋值和竞态条件**。"""




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
    description: str = ""
    source: str = ""
    sink: str = ""
    taint_flow: List[str] = field(default_factory=list)
    taint_path: List[str] = field(default_factory=list)  # backward compat alias
    missing_checks: List[str] = field(default_factory=list)
    code_snippet: str = ""
    confidence: float = 0.0
    poc_plan: str = ""
    fix_suggestion: str = ""
    suggestion: str = ""


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
            ScanPhase(1, "HTTP Entry Discovery", "分析相关 HTTP 入口点与路由"),
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
        framework = context.get("framework_hint") or "unknown"
        base_prompt = f"""你正在执行业务逻辑扫描第 {phase.phase_num} 阶段。

## 当前阶段
- 阶段: {phase.phase_name}
- 描述: {phase.description}
- 模式: {'聚焦模式' if self._focused_mode else '全局模式'}
- 框架: {framework}

## 项目信息
- target: {context['target']}
- quick_mode: {context['quick_mode']}

## 已有上下文摘要
- 已发现入口: {len(context['discovered_entries'])} 个
- 已识别敏感操作: {len(context['sensitive_operations'])} 个
- 已追踪污点路径: {len(context['taint_paths'])} 条
- 当前 findings: {len(context['findings'])} 个

先进行 Thought，然后调用工具（Action）获取证据。证据充分后再输出 Final Answer JSON。
"""

        # === 阶段 1：HTTP 入口发现 ===
        if phase.phase_num == 1:
            framework_hints = {
                "flask":   '"@app.route|@blueprint.route|add_url_rule"',
                "fastapi": '"@router\\.(get|post|put|delete|patch)|@app\\.(get|post|put|delete)"',
                "django":  '"path\\(|url\\(|re_path\\(|urlpatterns"',
                "express": '"app\\.(get|post|put|delete|patch)|router\\.(get|post|put|delete)"',
                "spring":  '"@GetMapping|@PostMapping|@PutMapping|@DeleteMapping|@RequestMapping"',
            }
            route_hint = framework_hints.get(str(framework).lower(), '"@route|@app\\.|router\\.|@mapping"')
            return (
                base_prompt
                + f"""
## 目标
发现项目中所有 HTTP 入口点，重点关注涉及用户数据、资金、权限的接口。

## 推荐搜索模式（根据框架 {framework}）
```
search_code: {route_hint}
```

## 优先关注的路径模式
- `/user`, `/account`, `/profile` → IDOR / 越权风险
- `/admin`, `/manage`, `/dashboard` → 权限绕过风险  
- `/order`, `/pay`, `/checkout`, `/refund` → 金额篡改风险
- `/role`, `/permission`, `/grant` → 权限提升风险
- `/password`, `/reset`, `/verify` → 认证逻辑缺陷风险

## Final Answer JSON
{{
  "entries": [
    {{
      "method": "GET",
      "path": "/api/user/{{id}}",
      "handler_file": "app/api/user.py",
      "handler_function": "get_user_profile",
      "handler_line": 42,
      "risk_category": "idor"
    }}
  ],
  "summary": "发现 N 个 HTTP 入口点，其中 M 个涉及高风险操作"
}}
"""
            )

        # === 阶段 2 聚焦模式：深度分析指定接口 ===
        if self._focused_mode and phase.phase_num == 2:
            entry_points_str = json.dumps(context.get("entry_points_hint", [])[:10], ensure_ascii=False, indent=2)
            return (
                base_prompt
                + f"""
## 目标
对以下每个接口执行深度分析：读取代码 → 识别鉴权模式 → 检查批量赋值风险 → 评估风险。

## 待分析的接口列表
{entry_points_str}

## 逐项分析清单（每个接口必须完成）
1. **read_file** 读取接口所在文件（取足够行数定位函数）
2. **鉴权检查**：是否有 @login_required / Depends(get_current_user) / @jwt_required 等？
3. **所有权校验**：是否验证 current_user.id == resource.owner_id？
4. **角色校验**：是否检查 is_admin / role / permission？
5. **批量赋值**：请求体是否通过 **data / **request.json 直接映射到模型？
6. **输入参数**：URL 参数 / 请求体 / Header 中有哪些用户可控字段？
7. **search_code** 验证是否有全局鉴权中间件补偿局部缺失

## Final Answer JSON
{{
  "entry_analysis": [
    {{
      "entry": "PUT /api/user/{{user_id}}",
      "handler": "app/api/user.py:update_profile",
      "logic": "更新用户资料",
      "auth_checks": ["@login_required"],
      "permission_checks": [],
      "mass_assignment_risk": true,
      "input_params": ["user_id（路径）", "data（请求体，含 role 字段）"],
      "risk": "IDOR + 批量赋值：无所有权校验，且 data 直接传入 .update()"
    }}
  ],
  "summary": "分析总结"
}}
"""
            )

        # === 阶段 2 全局模式：分析已发现入口 ===
        if phase.phase_num == 2 and not self._focused_mode:
            seed_entries = json.dumps(context.get("discovered_entries", [])[:8], ensure_ascii=False, indent=2)
            return (
                base_prompt
                + f"""
## 目标
对已发现的 HTTP 入口逐一深度分析业务逻辑、鉴权、批量赋值风险。

## 入口列表
{seed_entries}

## 分析要求（每个入口）
1. read_file 读取处理函数代码
2. 检查四维校验：[认证] [权限] [业务校验] [并发保护]
3. 检查批量赋值：请求体是否直接映射模型？
4. 搜索全局鉴权中间件（middleware/decorator）

## Final Answer JSON
{{
  "entry_analysis": [
    {{
      "entry": "GET /api/user/{{user_id}}",
      "handler": "app/api/user.py:get_user_profile",
      "logic": "返回用户详情",
      "auth_checks": ["@login_required"],
      "permission_checks": [],
      "mass_assignment_risk": false,
      "input_params": ["user_id（路径参数）"],
      "risk": "IDOR：缺少 current_user.id == user_id 校验"
    }}
  ],
  "summary": "..."
}}
"""
            )

        # === 阶段 3：敏感操作锚点识别 ===
        if phase.phase_num == 3:
            entry_analysis_summary = ""
            if context.get("entry_analysis"):
                risky = [e for e in context["entry_analysis"] if e.get("risk")]
                if risky:
                    entry_analysis_summary = "\n## 阶段2识别的高风险接口\n" + json.dumps(risky[:5], ensure_ascii=False, indent=2)
            return (
                base_prompt
                + f"""
## 目标
在阶段2发现的高风险接口中，精确定位敏感操作代码行，识别前置校验是否充分。
{entry_analysis_summary}

## 敏感操作类型
- **data_modification**: DB UPDATE/INSERT/DELETE 涉及他人数据
- **permission_change**: 角色/权限/is_admin 字段修改
- **financial_operation**: 余额/积分/订单金额操作
- **account_operation**: 密码/邮箱/手机号修改，账户状态变更

## 检查重点
1. read_file 精确定位敏感操作代码行
2. 检查操作前是否有完整的前置校验
3. 对于 UPDATE/INSERT，检查 WHERE 子句是否包含用户 ID 过滤
4. 对于金融操作，检查是否有 with_for_update() 或原子操作

## Final Answer JSON
{{
  "sensitive_operations": [
    {{
      "entry": "PUT /api/user/{{user_id}}",
      "operation": "User.query.filter_by(id=user_id).update(data)",
      "operation_file": "app/api/user.py",
      "operation_line": 55,
      "operation_type": "data_modification",
      "checks_before": ["@login_required（仅认证）"],
      "checks_missing": ["current_user.id == user_id 所有权校验", "字段白名单校验（mass_assignment）"]
    }}
  ],
  "summary": "..."
}}
"""
            )

        # === 阶段 4：污点分析 ===
        if phase.phase_num == 4:
            sensitive_ops_summary = ""
            if context.get("sensitive_operations"):
                sensitive_ops_summary = "\n## 阶段3识别的敏感操作\n" + json.dumps(
                    context["sensitive_operations"][:5], ensure_ascii=False, indent=2
                )
            return (
                base_prompt
                + f"""
## 目标
对每个敏感操作，追踪用户输入到危险调用的完整数据流，确认漏洞可利用性。
{sensitive_ops_summary}

## 分析维度
1. **source**: 用户可控的输入点（URL参数/请求体字段/Header）
2. **传播路径**: 参数如何传递到敏感操作（直接传递/字典解包/变量赋值）
3. **sink**: 具体的危险调用（DB写入/支付/权限变更）
4. **缺失检查**: 从 source 到 sink 路径上缺少什么校验

## 建议工具
- `dataflow_analysis` / `controlflow_analysis_light`（如可用）
- `read_file` 跟踪函数调用链
- `search_code` 验证是否有全局补偿

## Final Answer JSON
{{
  "taint_paths": [
    {{
      "entry": "PUT /api/user/{{user_id}}",
      "sensitive_op": "User.query.filter_by(id=user_id).update(data)",
      "source": "URL 路径参数 user_id",
      "taint_flow": [
        "URL 参数 user_id 由调用方完全控制",
        "直接传入 filter_by(id=user_id)，无所有权校验",
        "执行 UPDATE users SET ... WHERE id=user_id"
      ],
      "sink": "User.query.filter_by(id=user_id).update(data)",
      "missing_check": "current_user.id == user_id 校验缺失",
      "vulnerability_class": "idor",
      "exploitable": true
    }}
  ],
  "summary": "..."
}}
"""
            )

        # === 阶段 5：漏洞确认与输出 ===
        taint_summary = ""
        if context.get("taint_paths"):
            taint_summary = "\n## 阶段4污点分析结果\n" + json.dumps(
                context["taint_paths"][:5], ensure_ascii=False, indent=2
            )
        return (
            base_prompt
            + f"""
## 目标
综合前 4 阶段证据，输出最终确认的业务逻辑漏洞 findings。
{taint_summary}

## 输出要求
- 每个 finding 必须有实际代码证据（code_snippet 来自工具返回的真实代码）
- title 使用中文三段式：文件路径:函数名 + 漏洞类型描述
- taint_flow 列表必须完整覆盖 source → sink 路径
- poc_plan 描述具体攻击步骤（攻击者视角）
- suggestion 提供具体修复代码示例

## 漏洞类型参考
`idor` / `horizontal_privilege_escalation` / `vertical_privilege_escalation` /
`amount_tampering` / `quantity_manipulation` / `race_condition` / `workflow_bypass` /
`mass_assignment` / `password_reset_flaw` / `bulk_operation_abuse` /
`information_disclosure` / `captcha_bypass` / `api_chaining` / `second_order_logic`

## Final Answer JSON
{{
  "findings": [
    {{
      "title": "app/api/user.py:update_profile 函数 IDOR 越权修改漏洞",
      "vulnerability_type": "idor",
      "severity": "high",
      "confidence": 0.92,
      "description": "接口仅校验登录状态，未验证 current_user.id == user_id，任意已登录用户可修改他人资料（水平越权）。",
      "file_path": "app/api/user.py",
      "function_name": "update_profile",
      "line_start": 42,
      "line_end": 55,
      "entry_point": "PUT /api/user/{{user_id}}",
      "source": "URL 路径参数 user_id（完全由调用方控制）",
      "sink": "User.query.filter_by(id=user_id).update(data)",
      "taint_flow": [
        "URL 路径参数 user_id 由调用方控制",
        "无所有权校验直接传入 filter_by(id=user_id)",
        "执行 UPDATE users SET ... WHERE id=user_id"
      ],
      "missing_checks": ["current_user.id == user_id 所有权校验", "字段白名单（data 直接传入 .update()）"],
      "code_snippet": "# 工具返回的实际代码片段",
      "poc_plan": "以用户A身份登录，发送 PUT /api/user/<用户B的ID>，携带 {{\"role\": \"admin\"}} 等修改数据，验证越权成功。",
      "suggestion": "添加所有权校验：\nif current_user.id != user_id and not current_user.is_admin:\n    abort(403)\n# 同时添加字段白名单\nALLOWED = {{\'name\', \'email\', \'bio\'}}\ndata = {{k: v for k, v in data.items() if k in ALLOWED}}"
    }}
  ],
  "summary": "发现 N 个业务逻辑漏洞：..."
}}
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
                    "title": "app/api/user.py:get_user_profile 函数水平越权（IDOR）漏洞",
                    "vulnerability_type": "idor",
                    "severity": "high",
                    "confidence": 0.9,
                    "description": "接口仅检查登录状态，未验证 current_user.id == user_id，任意登录用户可读取他人资料。",
                    "file_path": "app/api/user.py",
                    "function_name": "get_user_profile",
                    "line_start": 78,
                    "line_end": 90,
                    "entry_point": "GET /api/user/{user_id}",
                    "source": "URL 路径参数 user_id",
                    "sink": "User.query.filter_by(id=user_id).first()",
                    "taint_flow": ["URL 参数 user_id 由调用方控制", "传入 filter_by(id=user_id)", "返回目标用户数据"],
                    "taint_path": ["user_id", "db.query", "execute"],
                    "missing_checks": ["current_user.id == user_id 所有权校验"],
                    "code_snippet": "def get_user_profile(user_id):\n    user = User.query.filter_by(id=user_id).first()\n    return jsonify(user.to_dict())",
                    "poc_plan": "以用户A身份登录，发送 GET /api/user/<用户B的ID>，验证是否返回用户B的资料。",
                    "suggestion": "添加所有权校验：if current_user.id != user_id and not current_user.is_admin: abort(403)",
                    "fix_suggestion": "添加所有权校验并拒绝越权访问。",
                }
            ],
            "summary": "确认 1 个业务逻辑漏洞（IDOR）",
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
        # taint_flow is the canonical field; taint_path is a legacy alias
        taint_flow = (
            payload.get("taint_flow")
            if isinstance(payload.get("taint_flow"), list)
            else (payload.get("taint_path") if isinstance(payload.get("taint_path"), list) else [])
        )
        suggestion = str(payload.get("suggestion") or payload.get("fix_suggestion") or "")
        return BusinessLogicFinding(
            title=str(payload.get("title") or ""),
            vulnerability_type=str(payload.get("vulnerability_type") or "business_logic_flaw"),
            severity=str(payload.get("severity") or "medium"),
            file_path=str(payload.get("file_path") or ""),
            function_name=str(payload.get("function_name") or ""),
            line_start=int(payload.get("line_start") or 0),
            line_end=(int(payload.get("line_end")) if payload.get("line_end") is not None else None),
            entry_point=(str(payload.get("entry_point")) if payload.get("entry_point") else None),
            description=str(payload.get("description") or ""),
            source=str(payload.get("source") or ""),
            sink=str(payload.get("sink") or ""),
            taint_flow=taint_flow,
            taint_path=taint_flow,
            missing_checks=(payload.get("missing_checks") if isinstance(payload.get("missing_checks"), list) else []),
            code_snippet=str(payload.get("code_snippet") or ""),
            confidence=float(payload.get("confidence") or 0.0),
            poc_plan=str(payload.get("poc_plan") or ""),
            fix_suggestion=suggestion,
            suggestion=suggestion,
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
            "description": finding.description,
            "source": finding.source,
            "sink": finding.sink,
            "taint_flow": finding.taint_flow,
            "taint_path": finding.taint_flow,  # backward compat
            "missing_checks": finding.missing_checks,
            "code_snippet": finding.code_snippet,
            "confidence": finding.confidence,
            "poc_plan": finding.poc_plan,
            "fix_suggestion": finding.suggestion or finding.fix_suggestion,
            "suggestion": finding.suggestion or finding.fix_suggestion,
            "needs_verification": True,
            "agent_source": "business_logic_scan_sub_agent",
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
