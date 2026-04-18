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
import os
import re
import hashlib
import threading
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.agent.json_safe import dump_json_safe
from app.models.analysis import (
    REAL_DATAFLOW_EVIDENCE_LIST_FIELDS,
    REAL_DATAFLOW_PLACEHOLDER_VALUES,
)

from .base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern, TaskHandoff
from .react_parser import parse_react_response
from .verification_table import VerificationFindingTable
from ..json_parser import AgentJsonParser
from ..flow.lightweight.function_locator import EnclosingFunctionLocator
from ..flow.lightweight.function_locator_payload import (
    parse_locator_payload,
    select_locator_function,
)
from ..prompts.system_prompts import CORE_SECURITY_PRINCIPLES, VULNERABILITY_PRIORITIES
from ..utils.vulnerability_naming import (
    build_cn_structured_description,
    build_cn_structured_description_markdown,
    build_cn_structured_title,
    normalize_vulnerability_type,
    resolve_cwe_id,
    resolve_vulnerability_profile,
)
from ..tools.verification_result_tools import ensure_finding_identity

logger = logging.getLogger(__name__)

_TRACE_HANDLER_LOCK = threading.Lock()

_PSEUDO_FUNCTION_NAMES = {"__attribute__", "__declspec"}
_CONTROL_KEYWORDS = {"if", "for", "while", "switch", "catch", "else", "return"}
_SINK_REACHABLE_TRUTHY_VALUES = {
    "true",
    "1",
    "yes",
    "y",
    "reachable",
    "triggerable",
    "can_trigger",
    "可达",
    "可触发",
}
_SOURCE_SINK_PLACEHOLDER_VALUES = set(REAL_DATAFLOW_PLACEHOLDER_VALUES)
_SOURCE_SINK_GATE_METADATA_KEYS: Tuple[str, ...] = (
    "sink_reachable",
    "upstream_call_chain",
    "sink_trigger_condition",
)
_SOURCE_SINK_GATE_VULNERABILITY_TYPES = {
    "business_logic",
    "idor",
    "auth_bypass",
}

# === 全局置信度阈值常量 ===
# 统一所有地方的置信度判定逻辑，避免阈值不一致导致的误判
CONFIDENCE_THRESHOLD_LIKELY = 0.7  # >= 0.7 判定为 likely
CONFIDENCE_THRESHOLD_FALSE_POSITIVE = 0.3  # <= 0.3 判定为 false_positive
CONFIDENCE_DEFAULT_ON_MISSING = None  # 缺失置信度时：None表示保留LLM原始verdict，不强制降级
CONFIDENCE_DEFAULT_FALLBACK = 0.5  # 最后兜底：信息不足时使用0.5作为中立值


VERIFICATION_SYSTEM_PROMPT = """你是 VulHunter 的漏洞验证 Agent，一个**自主的安全验证专家**。你的核心目标是**以最高标准确认漏洞真实性，坚决排除误报**。

## 你的角色
你是漏洞验证的**大脑**，不是机械验证器。你需要：
1. 优先尝试**反证漏洞不存在**
2. 理解每个漏洞的上下文
3. 设计合适的验证策略
4. **在反证失败后编写测试代码进行正向动态验证**
5. 判断漏洞是否真实存在
6. 评估实际影响并生成 PoC

## 首要流程：先反证，后正证
你必须先寻找“漏洞不存在”的证据，例如：
1. 输入实际不可控、被白名单/转义/参数化/类型约束拦截
2. 危险路径不可达，关键分支、权限、状态机、特性开关无法满足
3. sink 不可触发，source/sink 关联是误判，或依赖真实上下文后不成立
4. 已有防御在真实执行路径上生效

如果你已经获得足够反证，必须立即终止该漏洞的继续验证，直接判定为 `false_positive` 并保存结果。
只有在反证失败，无法排除漏洞不存在时，才继续做正向验证；正向验证阶段必须结合真实代码路径分析，并尽量使用 Mock/Fuzzing Harness 做动态验证。

## 核心理念：Fuzzing Harness
即使整个项目无法运行，你也应该能够验证漏洞！方法是：
1. **提取目标函数** - 从代码中提取存在漏洞的函数
2. **构建 Mock** - 模拟函数依赖（数据库、HTTP、文件系统等）
3. **编写测试脚本** - 构造各种恶意输入测试函数
4. **分析执行结果** - 判断是否触发漏洞

最终报告标题必须保持标题结构化，例如：`src/time64.c中asctime64_r栈溢出漏洞`。

═══════════════════════════════════════════════════════════════

## 🎯 核心职责

| 职责 | 说明 |
|------|------|
| **深度理解** | 分析漏洞上下文、触发条件和利用路径 |
| **反证优先** | **先证明漏洞不存在**，优先寻找过滤、不可达、防御生效、依赖缺失等否定证据 |
| **动态跟进** | 仅在**反证失败后**，再通过 Fuzzing Harness / Mock 进行正向触发；这是 confirmed 的必要条件 |
| **严谨验证** | 必须验证所有限制条件， 编写测试代码，只有**稳定触发**才能评为 confirmed |
| **误报排除** | 一旦反证成立（输入被过滤、路径不可达、防御有效），立即终止并判定 false_positive |
| **结果持久化** | 每验证完一个漏洞后**必须调用 `save_verification_result`** 保存结果 |

═══════════════════════════════════════════════════════════════

##  降低误报的黄金准则

1. **输入可控且无过滤**：证明用户输入能到达危险函数，且没有有效防御（参数化查询、转义、白名单）
2. **Source/Sink 必须真实**：`source`/`sink` 不能是占位符；必须有上游调用链与 sink 可触发证据
3. **代码路径可达**：确认函数被外部调用（路由、API、公开方法），否则 confidence ≤ 0.5
4. **构造稳定 PoC**：confirmed 判定必须提供能稳定触发的 payload 和执行结果
5. **考虑上下文防御**：检查上游过滤、类型转换、安全配置（HttpOnly、CSP）等
6. **多 payload 测试**：测试多种变形，绕过简单过滤
7. **误报分析**：若未触发，分析原因（过滤函数、参数限制、框架转义）并记录

═══════════════════════════════════════════════════════════════

## 事实 / 推论 / 结论 三分法（必须执行）

你必须把每个发现的验证分析拆成三层，禁止把推测写成事实：
1. **已知事实 (`known_facts`)**：只能写工具直接返回的代码、配置、日志、运行输出、文件路径、行号、调用关系，或能被代码语义直接推出的事实。
2. **待验证推论 (`inferences_to_verify`)**：列出关键中间判断，例如“输入可控”“sink 可达”“过滤可绕过”“分支必定可进入”；每条都要说明它依赖哪些事实、还缺什么证据。
3. **最终结论 (`final_conclusion`)**：只能基于已经获得直接支持的事实和推论得出；若关键一跳仍缺证据，必须降级为 `uncertain` 或降低 confidence。

在 Final Answer 的每个 finding 中，除 verdict 等字段外，还必须显式列出：
- `known_facts`: 已确认事实列表
- `inferences_to_verify`: 关键推论列表；每项至少说明 `claim`、`basis`、`support_status`
- `final_conclusion`: 最终结论摘要，且不得引入新的未验证内容

禁止把以下内容写成事实：猜测的调用链、未读取到的分支行为、默认假设的框架安全行为、未执行验证却宣称“可稳定触发”的结果。

═══════════════════════════════════════════════════════════════

## 推理链逐跳审计（必须执行）

每当你在思考、工具分析或最终结论中使用“因此”“从而”“所以”“说明”“意味着”“可见”等连接词时，必须逐跳自检：
1. 连接词前面的陈述是**已知事实**，还是**尚未证实的推论**？
2. 连接词后面的陈述，是否能被前面的内容**直接**以代码证据、控制流/数据流证据或明确逻辑规则推出？
3. 如果不能直接推出，必须把后一句降级为“待验证推论”，继续调用工具补证；禁止脑补把缺失链路补齐。
4. 任意一跳缺少直接代码或逻辑支持时，不得输出 `confirmed` / `likely` 这类强结论。

═══════════════════════════════════════════════════════════════

## 工具使用指南

### 核心验证工具（按优先级使用）

| 优先级 | 工具 | 用途 | 调用时机 |
|--------|------|------|---------|
| 1 | `get_symbol_body` | 提取目标函数代码 | 开始验证时，获取完整函数体 |
| 2 | `run_code` | 执行 Fuzzing Harness/PoC | **核心验证手段**，执行测试脚本 |
| 3 | `get_code_window` | 读取代码上下文 | 需要 surrounding code 时 |
| 4 | `search_code` | 查找调用链、依赖关系 | 验证可达性时 |
| 5 | `save_verification_result` | **持久化单个验证结果** | **每验证完一个漏洞就调用** |

**辅助工具**：
- `sandbox_exec`：沙箱命令执行（验证命令注入）
- `sandbox_http`：HTTP 请求（如有运行服务）

### 工具调用原则
1. **必须先调工具再输出结论** - 禁止仅凭已知信息判断
2. **首轮必须输出 Action** - 不允许首轮直接 Final Answer
3. **反证优先** - 先用工具验证“漏洞不存在”的可能性，再决定是否进入正向验证
4. **故障自主恢复** - **工具失败时分析错误、调整策略、继续验证，禁止直接放弃**
5. **文件路径** - 涉及到项目文件的路径，统一用相对于项目根目录的路径表示（如 `app/api/user.py`），禁止使用绝对路径或外部路径。

═══════════════════════════════════════════════════════════════

## 工具调用失败处理（关键）

### 失败响应原则
**遇到工具调用失败时，你必须：**
1. **分析错误信息** - 理解失败原因（文件不存在、语法错误、超时、权限等）
2. **自主调整策略** - 根据错误类型选择替代方案
3. **继续验证流程** - **禁止直接输出 Final Answer 或放弃验证**
4. 如果多次调用`save_verification_result`失败，必须在Final Answer中明确说明验证结果未保存，并提供失败原因。

═══════════════════════════════════════════════════════════════

## 🧪 Fuzzing Harness 编写规范

### 原则
1. **你是大脑** - 你决定测试策略、payload、检测方法
2. **不依赖完整项目** - 提取函数，mock 依赖，隔离测试
3. **多种 payload** - 设计多种恶意输入，不要只测一个
4. **检测漏洞特征** - 根据漏洞类型设计检测逻辑

### 命令注入 Fuzzing Harness 示例 (Python)
```python
import os
import subprocess

# === Mock 危险函数来检测调用 ===
executed_commands = []
original_system = os.system

def mock_system(cmd):
    print(f"[DETECTED] os.system called: {cmd}")
    executed_commands.append(cmd)
    return 0

os.system = mock_system

# === 目标函数（从项目代码复制） ===
def vulnerable_function(user_input):
    os.system(f"echo {user_input}")

# === Fuzzing 测试 ===
payloads = [
    "test",           # 正常输入
    "; id",           # 命令连接符
    "| whoami",       # 管道
    "$(cat /etc/passwd)",  # 命令替换
    "`id`",           # 反引号
    "&& ls -la",      # AND 连接
]

print("=== Fuzzing Start ===")
for payload in payloads:
    print(f"\\nPayload: {payload}")
    executed_commands.clear()
    try:
        vulnerable_function(payload)
        if executed_commands:
            print(f"[VULN] Detected! Commands: {executed_commands}")
    except Exception as e:
        print(f"[ERROR] {e}")
```

### SQL 注入 Fuzzing Harness 示例 (Python)
```python
# === Mock 数据库 ===
class MockCursor:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=None):
        print(f"[SQL] Query: {query}")
        print(f"[SQL] Params: {params}")
        self.queries.append((query, params))

        # 检测 SQL 注入特征
        if params is None and ("'" in query or "OR" in query.upper() or "--" in query):
            print("[VULN] Possible SQL injection - no parameterized query!")

class MockDB:
    def cursor(self):
        return MockCursor()

# === 目标函数 ===
def get_user(db, user_id):
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id = '{user_id}'")  # 漏洞！

# === Fuzzing ===
db = MockDB()
payloads = ["1", "1'", "1' OR '1'='1", "1'; DROP TABLE users--", "1 UNION SELECT * FROM admin"]

for p in payloads:
    print(f"\\n=== Testing: {p} ===")
    get_user(db, p)
```

### PHP 命令注入 Fuzzing Harness 示例
```php
// 注意：php -r 不需要 <?php 标签

// Mock $_GET
$_GET['cmd'] = '; id';
$_POST['cmd'] = '; id';
$_REQUEST['cmd'] = '; id';

// 目标代码（从项目复制）
$output = shell_exec($_GET['cmd']);
echo "Output: " . $output;

// 如果有输出，说明命令被执行
if ($output) {
    echo "\\n[VULN] Command executed!";
}
```

### XSS 检测 Harness 示例 (Python)
```python
def vulnerable_render(user_input):
    # 模拟模板渲染
    return f"<div>Hello, {user_input}!</div>"

payloads = [
    "test",
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "{{7*7}}",  # SSTI
]

for p in payloads:
    output = vulnerable_render(p)
    print(f"Input: {p}")
    print(f"Output: {output}")
    # 检测：payload 是否原样出现在输出中
    if p in output and ("<" in p or "{{" in p):
        print("[VULN] XSS - input not escaped!")
```

### 业务逻辑漏洞验证 Harness 示例 (Python)
```python
# 场景：转账接口未将 from_user 与 current_user 绑定，导致越权扣款
class BankService:
    def __init__(self):
        self.balances = {"alice": 1000, "bob": 1000, "attacker": 10}

    # 漏洞：from_user 由客户端传入，未校验是否属于当前登录用户
    def transfer(self, current_user, from_user, to_user, amount):
        if self.balances.get(from_user, 0) < amount:
            return False
        self.balances[from_user] -= amount
        self.balances[to_user] = self.balances.get(to_user, 0) + amount
        return True

svc = BankService()

# (current_user, from_user, to_user, amount)
payloads = [
    ("attacker", "attacker", "bob", 5),      # 正常场景
    ("attacker", "alice", "attacker", 300),  # 越权扣 Alice 余额
    ("attacker", "bob", "attacker", 200),    # 越权扣 Bob 余额
]

for current_user, from_user, to_user, amount in payloads:
    before = dict(svc.balances)
    ok = svc.transfer(current_user, from_user, to_user, amount)
    after = dict(svc.balances)
    print(f"Request: user={current_user}, from={from_user}, to={to_user}, amount={amount}, ok={ok}")
    print(f"Before: {before}")
    print(f"After : {after}")
    if ok and current_user != from_user:
        print("[VULN] Business Logic Bypass: unauthorized debit succeeded!")
```

═══════════════════════════════════════════════════════════════

## 📊 真实性与置信度判定

### verdict 等级（必填）
| 等级 | 标准 | Confidence |
|------|------|-----------|
| `confirmed` | 漏洞确认存在且可利用 | ≥ 0.8 |
| `likely` | 高度可能存在漏洞，代码分析明确但无法动态验证 | ≥ 0.7 |
| `uncertain` | 需要更多信息才能判断 | 0.3-0.7 |
| `false_positive` | 确认是误报，有明确理由 | ≤ 0.3 |

保存 `save_verification_result` 时，`status` 字段请使用：
- `verified`：对应 `confirmed`
- `likely`：对应 `likely`，以及 legacy 的 `uncertain`
- `false_positive`：对应 `false_positive`

═══════════════════════════════════════════════════════════════

## 🔄 标准验证流程

```
步骤1: 先做反证
    └─> get_code_window / get_symbol_body / search_code 检查过滤、白名单、参数化、权限、状态条件
    └─> 验证 source 是否真实可控、sink 是否真实可触发、路径是否真实可达
    └─> 若反证成功（漏洞不存在），立即判定 false_positive，保存结果并结束该发现
    └─> 若反证失败，进入后续正向验证

步骤2: 提取目标
    └─> get_symbol_body 获取函数代码
    └─> 若失败则用 get_code_window 读取行范围

步骤3: 分析上下文
    └─> search_code 查找调用链（验证可达性）
    └─> get_code_window 读取配置文件附近窗口（检查防御机制）

步骤4: 构建 Harness
    └─> 根据漏洞类型选择模板
    └─> Mock 依赖（DB/文件系统/HTTP）
    └─> 构造 3-5 个 payload

步骤5: 正向动态验证
    └─> run_code 执行 Harness
    └─> 分析输出，确认触发

步骤6: 判定与推送
    └─> 根据结果确定 verdict 和 confidence
    └─> 构造 finding 对象（含 verification_result）
    └─> finding 中必须显式区分 known_facts / inferences_to_verify / final_conclusion
    └─> verification_result.flow 必须概括验证链路
    └─> function_trigger_flow 必须保留函数级触发路径

步骤7: 持久化（必须）
    └─> save_verification_result 保存结果
    └─> 输出 Final Answer（仅摘要，无详情）
```

═══════════════════════════════════════════════════════════════

## 强制约束

1. **禁止幻觉**：所有判定必须基于工具返回的实际代码/输出
2. **反证优先**：先排查漏洞不存在的证据，只有在反证失败后才进入正向动态验证
3. **禁止矛盾**：不允许 (verdict=confirmed AND confidence≤0.3) 等组合
4. **必须数值化**：confidence 必须是 0.0-1.0 浮点数，禁止文本
5. **语言要求**：title/description/suggestion/verification_evidence 必须用**简体中文**
6. **格式严格**：使用纯文本 `Thought: / Action: / Action Input: / Final Answer:`，**禁止 Markdown 标记（**、###、* 等）**
7. **禁止交互**：不允许"请选择/请确认后继续"等语句
8. **结果保存**：**验证完漏洞需要调用 save_verification_result 工具保存结果**
9. **区分事实与推论**：`known_facts` 只能来自工具返回、代码内容或可被代码语义直接证明的逻辑事实
10. **逐跳审计推理链**：凡出现“因此/从而/所以/说明/意味着”等推理连接，必须核查前后两步是否有直接支持；缺支持就继续取证或降级
11. **禁止脑补强结论**：任何关键推论未被直接支持前，不得给出 `confirmed` / `likely`

`function_name` 为必填：
- 优先使用定位结果（TreeSitter/regex/get_symbol_body）
- 若定位失败，尝试从标题中提取函数名
- 若仍失败，使用语义化占位符（如 `<function_at_line_45>`），禁止留空

## 重要原则
1. **你是验证的大脑** - 你决定如何测试，工具只提供执行能力
2. **先反证后正证** - 先排查漏洞不存在的证据，反证失败后再做正向和 Mock 动态验证
3. **质量优先** - 宁可漏报也不要误报太多
4. **证据支撑** - 每个判定都需要有依据
5. **根因说明** - 无论结果如何，都要有详细的分析结果。

## 输出格式

**标准行动格式：**
```
Thought: [当前状态分析，下一步计划]
Action: [工具名称]
Action Input: { "参数": "值" }
```

现在开始验证漏洞发现。记住：**先反证后正证，证据支撑判定，结果必须保存**。
"""


@dataclass
class VerificationStep:
    """验证步骤"""
    thought: str
    action: Optional[str] = None
    action_input: Optional[Dict] = None
    observation: Optional[str] = None
    is_final: bool = False
    final_answer: Optional[Dict] = None


@dataclass
class VerificationTodoItem:
    """逐漏洞验证 TODO 项"""

    id: str
    fingerprint: str
    file_path: str
    line_start: int
    title: str
    status: str = "pending"  # pending|running|verified|false_positive|uncertain|blocked
    attempts: int = 0
    max_attempts: int = 2
    blocked_reason: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)
    final_verdict: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "title": self.title,
            "status": self.status,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "blocked_reason": self.blocked_reason,
            "evidence_refs": list(self.evidence_refs or []),
            "final_verdict": self.final_verdict,
        }


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
            max_iterations=500,
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)
        
        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[VerificationStep] = []
        self._trace_logger, self._trace_log_path = self._build_trace_logger(self.name, None)
        self._trace("verification_agent_initialized", tool_count=len(tools or {}))

    @staticmethod
    def _sanitize_logger_identity(agent_name: str) -> str:
        raw = str(agent_name or "verification").strip().lower()
        safe = re.sub(r"[^a-z0-9._-]+", "_", raw)
        return safe or "verification"

    @staticmethod
    def _resolve_trace_log_path(agent_name: str, task_id: Optional[str] = None) -> str:
        safe = VerificationAgent._sanitize_logger_identity(agent_name)
        safe_task = VerificationAgent._sanitize_logger_identity(task_id or "no_task")
        log_dir = Path(__file__).resolve().parents[4] / "log" / "verification" / safe_task
        log_dir.mkdir(parents=True, exist_ok=True)
        return str(log_dir / f"{safe}.log")

    @staticmethod
    def _resolve_fallback_trace_log_path(agent_name: str, task_id: Optional[str] = None) -> str:
        safe = VerificationAgent._sanitize_logger_identity(agent_name)
        safe_task = VerificationAgent._sanitize_logger_identity(task_id or "no_task")
        log_dir = Path(tempfile.gettempdir()) / "vulhunter" / "verification" / safe_task
        log_dir.mkdir(parents=True, exist_ok=True)
        return str(log_dir / f"{safe}.log")

    @classmethod
    def _build_trace_logger(cls, agent_name: str, task_id: Optional[str] = None) -> tuple[logging.Logger, str]:
        safe = cls._sanitize_logger_identity(agent_name)
        safe_task = cls._sanitize_logger_identity(task_id or "no_task")
        trace_logger_name = f"{__name__}.trace.{safe_task}.{safe}"
        trace_logger = logging.getLogger(trace_logger_name)
        trace_logger.setLevel(logging.INFO)
        trace_logger.propagate = False

        try:
            target_file = cls._resolve_trace_log_path(agent_name, task_id)
        except PermissionError:
            target_file = cls._resolve_fallback_trace_log_path(agent_name, task_id)
        with _TRACE_HANDLER_LOCK:
            has_handler = False
            for handler in trace_logger.handlers:
                if isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", "") == target_file:
                    has_handler = True
                    break
            if not has_handler:
                try:
                    file_handler = logging.FileHandler(target_file, encoding="utf-8")
                except PermissionError:
                    target_file = cls._resolve_fallback_trace_log_path(agent_name, task_id)
                    file_handler = logging.FileHandler(target_file, encoding="utf-8")
                file_handler.setLevel(logging.INFO)
                file_handler.setFormatter(
                    logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
                )
                trace_logger.addHandler(file_handler)
        return trace_logger, target_file

    def configure_trace_logger(self, identity: Optional[str] = None, task_id: Optional[str] = None) -> str:
        """根据运行时身份重建 trace logger，确保并发 worker 各自落盘。"""
        final_identity = str(identity or self.name or "verification").strip() or "verification"
        final_task_id = str(task_id or getattr(self, "_task_id", "") or "").strip() or None
        self._task_id = final_task_id
        self._trace_logger, self._trace_log_path = self._build_trace_logger(final_identity, final_task_id)
        self._trace(
            "trace_logger_configured",
            logger_identity=final_identity,
            task_id=final_task_id or "no_task",
        )
        return self._trace_log_path

    def _trace(self, message: str, **fields: Any) -> None:
        if not hasattr(self, "_trace_logger") or self._trace_logger is None:
            return
        details = []
        for key, value in fields.items():
            if value is None:
                continue
            text = str(value)
            if len(text) > 400:
                text = text[:400] + "..."
            details.append(f"{key}={text}")
        suffix = f" | {'; '.join(details)}" if details else ""
        self._trace_logger.info(f"[{self.name}] {message}{suffix}")



    
    def _parse_llm_response(self, response: str) -> VerificationStep:
        """解析 LLM 响应（共享 ReAct 解析器）"""
        parsed = parse_react_response(
            response,
            final_default={"findings": [], "raw_answer": (response or "").strip()},
            action_input_raw_key="raw_input",
        )
        step = VerificationStep(
            thought=parsed.thought or "",
            action=parsed.action,
            action_input=parsed.action_input or {},
            is_final=bool(parsed.is_final),
            final_answer=parsed.final_answer if isinstance(parsed.final_answer, dict) else None,
        )

        if step.action and not step.action_input:
            logger.warning(f"[Verification] Action '{step.action}' found but Action Input is empty")

        self._trace(
            "llm_response_parsed",
            is_final=step.is_final,
            action=step.action,
            thought_len=len(step.thought or ""),
        )

        if step.is_final and isinstance(step.final_answer, dict) and "findings" in step.final_answer:
            step.final_answer["findings"] = [
                f for f in step.final_answer["findings"]
                if isinstance(f, dict)
            ]
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

            normalized_status = self._normalize_verification_status(
                finding.get("status")
                or (finding.get("verification_result") or {}).get("status")
            )
            if not normalized_status:
                has_authenticity = finding.get("authenticity") or finding.get("verdict")
                if not has_authenticity:
                    return False, f"第 {index} 条 finding 缺少 status（或兼容字段 authenticity/verdict）"
                if str(has_authenticity).strip().lower() not in {"confirmed", "likely", "uncertain", "false_positive"}:
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

            cwe_id = finding.get("cwe_id") or finding.get("cwe")
            if not isinstance(cwe_id, str) or not cwe_id.strip():
                return False, f"第 {index} 条 finding 缺少 cwe_id"

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

    @staticmethod
    def _normalize_verification_status(value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"verified", "true_positive", "exists", "vulnerable", "confirmed"}:
            return "verified"
        if normalized in {"likely", "uncertain", "unknown", "needs_review", "needs-review"}:
            return "likely"
        if normalized in {"false_positive", "false-positive", "not_vulnerable", "not_exists", "non_vuln"}:
            return "false_positive"
        if normalized in {"blocked"}:
            return "blocked"
        return ""

    @staticmethod
    def _status_to_verdict(status: str) -> str:
        normalized_status = str(status or "").strip().lower()
        if normalized_status == "verified":
            return "confirmed"
        if normalized_status == "likely":
            return "likely"
        if normalized_status == "false_positive":
            return "false_positive"
        return "likely"

    def _normalize_verdict(self, finding: Dict[str, Any]) -> str:
        """兼容性方法：优先尊重显式 verdict，再回退按 status 推断。"""
        verdict = finding.get("verdict") or finding.get("authenticity")
        if isinstance(verdict, str):
            verdict = verdict.strip().lower()
        else:
            verdict = None
        if verdict in {"confirmed", "likely", "uncertain", "false_positive"}:
            return verdict

        normalized_status = self._normalize_verification_status(finding.get("status"))
        if normalized_status:
            return self._status_to_verdict(normalized_status)

        confidence_raw = finding.get("confidence")
        confidence = None
        if confidence_raw is not None:
            try:
                confidence = float(confidence_raw)
            except Exception:
                logger.warning(
                    f"[Verification] confidence 类型转换失败: {confidence_raw} (type: {type(confidence_raw).__name__})"
                )

        if confidence is not None:
            if confidence >= CONFIDENCE_THRESHOLD_LIKELY:
                return "likely"
            if confidence <= CONFIDENCE_THRESHOLD_FALSE_POSITIVE:
                return "false_positive"
            return "likely"

        logger.debug(
            f"[Verification] status/verdict 均缺失，保守设为likely: "
            f"{finding.get('file_path')}:{finding.get('line_start')}"
        )
        return "likely"

    def _normalize_reachability_value(self, value: Any, verdict: str) -> str:
        """规范化可达性判定
        
        改进：添加对'uncertain'状态的支持
        """
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"reachable", "likely_reachable", "unreachable", "unknown"}:
                return normalized
        if verdict == "confirmed":
            return "reachable"
        if verdict == "likely":
            return "likely_reachable"
        if verdict == "uncertain":
            return "unknown"
        return "unreachable"

    @staticmethod
    def _normalize_text_list(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = str(value).strip()
            return [text] if text else []
        return []

    @staticmethod
    def _normalize_sink_reachability_flag(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False
            return None
        text = str(value or "").strip().lower()
        if not text:
            return None
        if text in _SINK_REACHABLE_TRUTHY_VALUES:
            return True
        if text in {"false", "0", "no", "n", "unreachable", "blocked", "不可达", "不可触发"}:
            return False
        return None

    @staticmethod
    def _is_placeholder_source_or_sink(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        text = str(value or "").strip().lower()
        if not text:
            return True
        if text in _SOURCE_SINK_PLACEHOLDER_VALUES:
            return True
        return text.startswith("<") and text.endswith(">")

    @classmethod
    def _pick_best_text_value(
        cls,
        primary: Any,
        fallback: Any,
        reject_placeholders: bool = False,
    ) -> str:
        for candidate in (primary, fallback):
            text = str(candidate or "").strip()
            if not text:
                continue
            if reject_placeholders and cls._is_placeholder_source_or_sink(text):
                continue
            return text
        for candidate in (primary, fallback):
            text = str(candidate or "").strip()
            if text:
                return text
        return ""

    @classmethod
    def _pick_best_text_list(
        cls,
        primary: Any,
        fallback: Any,
        min_items: int = 0,
    ) -> List[str]:
        primary_list = cls._normalize_text_list(primary)
        fallback_list = cls._normalize_text_list(fallback)
        min_required = max(1, int(min_items or 0))
        if len(primary_list) >= min_required:
            return primary_list
        if len(fallback_list) >= min_required:
            return fallback_list
        return primary_list or fallback_list

    @staticmethod
    def _metadata_has_source_sink_signal(payload: Dict[str, Any]) -> bool:
        metadata_payload = payload.get("finding_metadata")
        if not isinstance(metadata_payload, dict):
            return False
        for key in _SOURCE_SINK_GATE_METADATA_KEYS:
            value = metadata_payload.get(key)
            if value not in (None, "", [], {}):
                return True
        return False

    @classmethod
    def _has_source_sink_signal(cls, payload: Dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        # 仅在存在 source/sink 门禁元数据或历史门禁结果时触发。
        # 普通漏洞（如 SQLi/XSS）即使包含 source/sink 字段，也不应被业务逻辑门禁误伤。
        if cls._metadata_has_source_sink_signal(payload):
            return True
        for key in _SOURCE_SINK_GATE_METADATA_KEYS:
            value = payload.get(key)
            if value not in (None, "", [], {}):
                return True
        verification_payload = payload.get("verification_result")
        if isinstance(verification_payload, dict):
            if verification_payload.get("source_sink_authenticity_passed") in {True, False}:
                return True
            if verification_payload.get("source_sink_authenticity_errors"):
                return True
            nested_metadata = verification_payload.get("finding_metadata")
            if isinstance(nested_metadata, dict):
                for key in _SOURCE_SINK_GATE_METADATA_KEYS:
                    value = nested_metadata.get(key)
                    if value not in (None, "", [], {}):
                        return True
        return False

    @classmethod
    def _should_enforce_source_sink_authenticity_gate(
        cls,
        finding: Dict[str, Any],
        fallback: Optional[Dict[str, Any]] = None,
    ) -> bool:
        for payload in (fallback, finding):
            if not isinstance(payload, dict):
                continue
            vulnerability_type = normalize_vulnerability_type(payload.get("vulnerability_type"))
            if vulnerability_type in _SOURCE_SINK_GATE_VULNERABILITY_TYPES:
                return True
            if cls._has_source_sink_signal(payload):
                return True
        return False

    @staticmethod
    def _extract_source_sink_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        extracted: Dict[str, Any] = {}
        metadata_payload = payload.get("finding_metadata")
        if isinstance(metadata_payload, dict):
            extracted.update(metadata_payload)
        verification_payload = payload.get("verification_result")
        if isinstance(verification_payload, dict):
            nested_metadata = verification_payload.get("finding_metadata")
            if isinstance(nested_metadata, dict):
                extracted.update(nested_metadata)
        for metadata_key in _SOURCE_SINK_GATE_METADATA_KEYS:
            raw_value = payload.get(metadata_key)
            if raw_value in (None, "", [], {}):
                continue
            extracted[metadata_key] = raw_value
        return extracted

    @classmethod
    def _validate_source_sink_authenticity(
        cls,
        finding: Dict[str, Any],
        fallback: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        finding_payload = finding if isinstance(finding, dict) else {}
        fallback_payload = fallback if isinstance(fallback, dict) else {}
        finding_metadata_raw = cls._extract_source_sink_metadata(finding_payload)
        fallback_metadata_raw = cls._extract_source_sink_metadata(fallback_payload)
        merged_metadata: Dict[str, Any] = {}

        source = cls._pick_best_text_value(
            finding_payload.get("source"),
            fallback_payload.get("source"),
            reject_placeholders=True,
        )
        sink = cls._pick_best_text_value(
            finding_payload.get("sink"),
            fallback_payload.get("sink"),
            reject_placeholders=True,
        )
        attacker_flow = cls._pick_best_text_value(
            finding_payload.get("attacker_flow"),
            fallback_payload.get("attacker_flow"),
        )
        taint_flow = cls._pick_best_text_list(
            finding_payload.get("taint_flow"),
            fallback_payload.get("taint_flow"),
        )
        evidence_chain = cls._pick_best_text_list(
            finding_payload.get("evidence_chain"),
            fallback_payload.get("evidence_chain"),
        )

        errors: List[str] = []
        if not source:
            raw_source = cls._pick_best_text_value(
                finding_payload.get("source"),
                fallback_payload.get("source"),
            )
            if raw_source and cls._is_placeholder_source_or_sink(raw_source):
                errors.append("source 为占位符，无法证明输入来源真实")
            else:
                errors.append("source 为空，无法证明输入来源真实")
        elif cls._is_placeholder_source_or_sink(source):
            errors.append("source 为占位符，无法证明输入来源真实")

        if not sink:
            raw_sink = cls._pick_best_text_value(
                finding_payload.get("sink"),
                fallback_payload.get("sink"),
            )
            if raw_sink and cls._is_placeholder_source_or_sink(raw_sink):
                errors.append("sink 为占位符，无法证明危险点真实")
            else:
                errors.append("sink 为空，无法证明危险点真实")
        elif cls._is_placeholder_source_or_sink(sink):
            errors.append("sink 为占位符，无法证明危险点真实")

        sink_reachable = cls._normalize_sink_reachability_flag(finding_metadata_raw.get("sink_reachable"))
        if sink_reachable is None:
            sink_reachable = cls._normalize_sink_reachability_flag(fallback_metadata_raw.get("sink_reachable"))
        if sink_reachable is not True:
            errors.append("sink_reachable 未明确为 true，无法证明 sink 可触发")
        else:
            merged_metadata["sink_reachable"] = True

        upstream_call_chain = cls._pick_best_text_list(
            finding_metadata_raw.get("upstream_call_chain"),
            fallback_metadata_raw.get("upstream_call_chain"),
            min_items=2,
        )
        if len(upstream_call_chain) < 2:
            errors.append("upstream_call_chain 不完整，缺少上游调用链证据")
        else:
            merged_metadata["upstream_call_chain"] = upstream_call_chain

        sink_trigger_condition = cls._pick_best_text_value(
            finding_metadata_raw.get("sink_trigger_condition"),
            fallback_metadata_raw.get("sink_trigger_condition"),
        )
        if not sink_trigger_condition:
            errors.append("sink_trigger_condition 为空，缺少触发前置条件")
        else:
            merged_metadata["sink_trigger_condition"] = sink_trigger_condition

        has_flow_evidence = bool(attacker_flow) or any(
            bool(cls._normalize_text_list(finding_payload.get(field_name)))
            or bool(cls._normalize_text_list(fallback_payload.get(field_name)))
            for field_name in REAL_DATAFLOW_EVIDENCE_LIST_FIELDS
        )
        if not has_flow_evidence:
            errors.append("缺少 flow 证据（attacker_flow / taint_flow / evidence_chain）")

        normalized_context: Dict[str, Any] = {
            "source": source,
            "sink": sink,
            "attacker_flow": attacker_flow,
            "taint_flow": taint_flow,
            "evidence_chain": evidence_chain,
            "finding_metadata": merged_metadata,
        }
        return len(errors) == 0, errors, normalized_context

    @classmethod
    def _apply_source_sink_authenticity_gate(
        cls,
        finding: Dict[str, Any],
        fallback: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized = dict(finding or {})
        verification_result = (
            dict(normalized.get("verification_result"))
            if isinstance(normalized.get("verification_result"), dict)
            else {}
        )

        if not cls._should_enforce_source_sink_authenticity_gate(normalized, fallback=fallback):
            verification_result.pop("source_sink_authenticity_passed", None)
            verification_result.pop("source_sink_authenticity_errors", None)
            if verification_result:
                normalized["verification_result"] = verification_result
            return normalized

        passed, errors, context = cls._validate_source_sink_authenticity(normalized, fallback=fallback)

        for key in ("source", "sink", "attacker_flow"):
            value = str(context.get(key) or "").strip()
            if not value:
                continue
            existing = str(normalized.get(key) or "").strip()
            if key in {"source", "sink"}:
                if not existing or cls._is_placeholder_source_or_sink(existing):
                    normalized[key] = value
            elif not existing:
                normalized[key] = value

        for list_key in ("taint_flow", "evidence_chain"):
            normalized_list = cls._normalize_text_list(context.get(list_key))
            if normalized_list and not cls._normalize_text_list(normalized.get(list_key)):
                normalized[list_key] = normalized_list

        merged_metadata = context.get("finding_metadata")
        if isinstance(merged_metadata, dict) and merged_metadata:
            existing_metadata = (
                dict(normalized.get("finding_metadata"))
                if isinstance(normalized.get("finding_metadata"), dict)
                else {}
            )
            existing_metadata.update(merged_metadata)
            normalized["finding_metadata"] = existing_metadata

        if passed:
            verification_result["source_sink_authenticity_passed"] = True
            verification_result.pop("source_sink_authenticity_errors", None)
            normalized["verification_result"] = verification_result
            return normalized

        reason = f"source/sink 真实性校验失败: {'; '.join(errors)}"

        normalized["status"] = "false_positive"
        normalized["verdict"] = "false_positive"
        normalized["authenticity"] = "false_positive"
        normalized["reachability"] = "unreachable"
        normalized["is_verified"] = False
        normalized["verified_at"] = None

        try:
            raw_confidence = float(normalized.get("confidence", CONFIDENCE_DEFAULT_FALLBACK))
        except Exception:
            raw_confidence = CONFIDENCE_DEFAULT_FALLBACK
        normalized["confidence"] = max(0.0, min(raw_confidence, CONFIDENCE_THRESHOLD_FALSE_POSITIVE))

        verification_evidence = str(
            verification_result.get("verification_evidence")
            or normalized.get("verification_evidence")
            or normalized.get("description")
            or ""
        ).strip()
        if verification_evidence:
            verification_evidence = f"{verification_evidence}\n[SourceSinkGate] {reason}"
        else:
            verification_evidence = f"[SourceSinkGate] {reason}"

        normalized["verification_evidence"] = verification_evidence

        verification_result.update(
            {
                "status": "false_positive",
                "verdict": "false_positive",
                "authenticity": "false_positive",
                "reachability": "unreachable",
                "confidence": normalized["confidence"],
                "verification_evidence": verification_evidence,
                "verification_details": verification_evidence,
                "source_sink_authenticity_passed": False,
                "source_sink_authenticity_errors": errors,
                "verification_reason": "source_sink_authenticity_failed",
            }
        )
        normalized["verification_result"] = verification_result
        return normalized

    def _normalize_vulnerability_key(self, finding: Dict[str, Any]) -> str:
        return normalize_vulnerability_type(finding.get("vulnerability_type"))

    def _build_finding_match_features(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(finding, dict):
            return {
                "identity": "",
                "vulnerability_key": "",
                "file_path": "",
                "line_start": 0,
                "title": "",
            }
        file_path, normalized_line_start, _line_end = self._normalize_file_location(finding)

        has_explicit_line = False
        for line_key in ("line_start", "line"):
            try:
                if int(finding.get(line_key)) > 0:
                    has_explicit_line = True
                    break
            except Exception:
                continue
        if not has_explicit_line and file_path:
            # 文件路径中显式包含 `path:line` 时，视为真实定位信息。
            raw_file_path = str(finding.get("file_path") or finding.get("file") or "").strip()
            if ":" in raw_file_path:
                _prefix, suffix = raw_file_path.split(":", 1)
                token = suffix.split()[0] if suffix.split() else ""
                has_explicit_line = token.isdigit() and int(token) > 0

        line_start = int(normalized_line_start or 0) if has_explicit_line else 0
        return {
            "identity": str(finding.get("finding_identity") or "").strip(),
            "vulnerability_key": self._normalize_vulnerability_key(finding),
            "file_path": file_path,
            "line_start": line_start,
            "title": str(finding.get("title") or "").strip().lower(),
        }

    def _select_fallback_finding(
        self,
        finding: Dict[str, Any],
        fallback_findings: List[Dict[str, Any]],
        used_indexes: set[int],
        preferred_index: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(finding, dict):
            return None
        if not isinstance(fallback_findings, list) or not fallback_findings:
            return None

        target = self._build_finding_match_features(finding)
        best_index: Optional[int] = None
        best_score = -1

        for index, candidate in enumerate(fallback_findings):
            if index in used_indexes or not isinstance(candidate, dict):
                continue
            candidate_features = self._build_finding_match_features(candidate)
            score = 0
            if target["identity"] and candidate_features["identity"] and target["identity"] == candidate_features["identity"]:
                score += 100
            if (
                target["vulnerability_key"]
                and candidate_features["vulnerability_key"]
                and target["vulnerability_key"] == candidate_features["vulnerability_key"]
            ):
                score += 20
            if target["file_path"] and candidate_features["file_path"] and target["file_path"] == candidate_features["file_path"]:
                score += 20
            if target["line_start"] > 0 and candidate_features["line_start"] > 0 and target["line_start"] == candidate_features["line_start"]:
                score += 20
            if target["title"] and candidate_features["title"] and target["title"] == candidate_features["title"]:
                score += 5
            if preferred_index is not None and index == preferred_index:
                score += 1
            if score > best_score:
                best_score = score
                best_index = index

        if best_index is None:
            if (
                preferred_index is not None
                and 0 <= preferred_index < len(fallback_findings)
                and preferred_index not in used_indexes
                and isinstance(fallback_findings[preferred_index], dict)
            ):
                best_index = preferred_index
            else:
                return None
        elif best_score <= 0 and (
            preferred_index is not None
            and 0 <= preferred_index < len(fallback_findings)
            and preferred_index not in used_indexes
            and isinstance(fallback_findings[preferred_index], dict)
        ):
            best_index = preferred_index

        used_indexes.add(best_index)
        selected = fallback_findings[best_index]
        return selected if isinstance(selected, dict) else None

    def _infer_cwe_id(self, finding: Dict[str, Any]) -> str:
        resolved = resolve_cwe_id(
            finding.get("cwe_id") or finding.get("cwe"),
            finding.get("vulnerability_type"),
            title=finding.get("title"),
            description=finding.get("description"),
            code_snippet=finding.get("code_snippet"),
        )
        return resolved or "CWE-20"

    def _build_structured_title(self, finding: Dict[str, Any]) -> str:
        return build_cn_structured_title(
            file_path=finding.get("file_path"),
            function_name=finding.get("function_name"),
            vulnerability_type=finding.get("vulnerability_type"),
            title=finding.get("title"),
            description=finding.get("description"),
            code_snippet=finding.get("code_snippet"),
            fallback_vulnerability_name=finding.get("title"),
            localization_status=finding.get("localization_status"),
        )

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
            "description": f"Mock PoC: {vuln_type} 的非武器化验证思路",
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

    def _build_minimal_probe_request(
        self,
        finding: Dict[str, Any],
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        file_path, line_start, _line_end = self._normalize_file_location(finding)
        normalized_file_path = str(file_path or finding.get("file_path") or "").strip()
        function_name = str(finding.get("function_name") or "").strip()

        if normalized_file_path and "get_code_window" in self.tools:
            return (
                "get_code_window",
                {
                    "file_path": normalized_file_path,
                    "anchor_line": line_start,
                    "before_lines": 8,
                    "after_lines": 20,
                },
            )

        if normalized_file_path and function_name and "get_symbol_body" in self.tools:
            return (
                "get_symbol_body",
                {
                    "file_path": normalized_file_path,
                    "symbol_name": function_name,
                },
            )

        if normalized_file_path and "read_file" in self.tools:
            return ("read_file", {"file_path": normalized_file_path})

        if normalized_file_path and function_name and "extract_function" in self.tools:
            return (
                "extract_function",
                {
                    "file_path": normalized_file_path,
                    "function_name": function_name,
                },
            )

        if "search_code" in self.tools:
            keyword = (
                function_name
                or str(finding.get("title") or "").strip()
                or str(finding.get("vulnerability_type") or "").strip()
                or normalized_file_path
            )
            if keyword:
                payload: Dict[str, Any] = {"keyword": keyword}
                if normalized_file_path:
                    parent_dir = str(Path(normalized_file_path).parent).strip()
                    if parent_dir and parent_dir != ".":
                        payload["directory"] = parent_dir
                return ("search_code", payload)

        return None

    def _normalize_mock_poc(self, poc_value: Any) -> Any:
        if poc_value is None:
            return None
        if isinstance(poc_value, dict):
            normalized = dict(poc_value)
            description = str(normalized.get("description") or "").strip()
            if description:
                if not description.lower().startswith("mock poc"):
                    normalized["description"] = f"Mock PoC: {description}"
            else:
                normalized["description"] = "Mock PoC: 非武器化验证方案"
            return normalized
        text = str(poc_value).strip()
        if not text:
            return None
        if text.lower().startswith("mock poc"):
            return text
        return f"Mock PoC: {text}"

    def _normalize_int_line(self, value: Any, default: int) -> int:
        try:
            line = int(value)
            if line > 0:
                return line
        except Exception:
            pass
        return default

    def _normalize_file_location(self, finding: Dict[str, Any]) -> tuple[str, int, int]:
        file_path = str(finding.get("file_path") or finding.get("file") or "").strip()
        line_start_raw = finding.get("line_start") or finding.get("line")
        line_end_raw = finding.get("line_end")
        if file_path and ":" in file_path:
            prefix, suffix = file_path.split(":", 1)
            token = suffix.split()[0] if suffix.split() else ""
            if token.isdigit():
                file_path = prefix.strip()
                if line_start_raw in (None, "", 0):
                    line_start_raw = int(token)
        line_start = self._normalize_int_line(line_start_raw, 1)
        line_end = self._normalize_int_line(line_end_raw, line_start)
        if line_end < line_start:
            line_end = line_start
        return file_path, line_start, line_end

    def _resolve_file_paths(
        self,
        file_path: str,
        project_root: Optional[str],
    ) -> tuple[Optional[str], Optional[str]]:
        clean = str(file_path or "").strip().replace("\\", "/")
        if not clean:
            return None, None
        display_fallback = self._to_display_file_path(clean, project_root)
        candidates = [clean]
        if clean.startswith("./"):
            candidates.append(clean[2:])
        if "/" in clean:
            candidates.append(clean.split("/", 1)[1])

        if os.path.isabs(clean) and os.path.isfile(clean):
            if project_root:
                try:
                    rel = os.path.relpath(clean, project_root).replace("\\", "/")
                    if not rel.startswith("../"):
                        return rel, clean
                except Exception:
                    pass
            return display_fallback, None

        if project_root:
            root = Path(project_root)
            for candidate in candidates:
                full = root / candidate
                if full.is_file():
                    rel = os.path.relpath(str(full), project_root).replace("\\", "/")
                    return rel, str(full)
        return display_fallback, None

    def _to_display_file_path(self, file_path: str, project_root: Optional[str]) -> str:
        clean = str(file_path or "").strip().replace("\\", "/")
        if not clean:
            return ""
        if project_root:
            try:
                rel = os.path.relpath(clean, project_root).replace("\\", "/")
                if not rel.startswith("../"):
                    return rel
            except Exception:
                pass
        if os.path.isabs(clean):
            return os.path.basename(clean)
        while clean.startswith("./"):
            clean = clean[2:]
        return clean

    def _extract_function_name_from_title(self, title: Any) -> Optional[str]:
        text = str(title or "").strip()
        if not text:
            return None
        patterns = [
            r"中([A-Za-z_][A-Za-z0-9_]*)函数",
            r"中([A-Za-z_][A-Za-z0-9_]*)"
            r"(?:SQL注入漏洞|跨站脚本漏洞|命令注入漏洞|路径遍历漏洞|服务器端请求伪造漏洞|XML外部实体漏洞|"
            r"不安全反序列化漏洞|硬编码密钥漏洞|认证绕过漏洞|越权访问漏洞|弱加密漏洞|NoSQL注入漏洞|代码注入漏洞|"
            r"缓冲区溢出漏洞|栈溢出漏洞|堆溢出漏洞|释放后使用漏洞|重复释放漏洞|越界访问漏洞|整数溢出漏洞|"
            r"格式化字符串漏洞|空指针解引用漏洞|未知类型漏洞)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                candidate = match.group(1).strip()
                if candidate.lower() in _PSEUDO_FUNCTION_NAMES:
                    continue
                return candidate
        return None

    def _infer_function_by_regex(
        self,
        file_lines: List[str],
        line_start: int,
    ) -> tuple[Optional[str], Optional[int], Optional[int]]:
        """
        增强的多语言函数定位正则推断
        支持: Python, JavaScript/TypeScript, PHP, Ruby, Go, Java, C/C++, Bash/Shell
        """
        if not file_lines:
            return None, None, None
        start_idx = max(0, min(len(file_lines) - 1, line_start - 1))
        
        # 增强的多语言模式
        patterns = [
            # Python: def, async def, @decorator 修饰
            ("python", re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
            
            # JavaScript/TypeScript: function, async function, arrow, methods
            ("javascript", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:function\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*[(:=]")),
            ("javascript_method", re.compile(r"^\s*(?:async\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\([^)]*\)\s*[{:]")),
            
            # PHP: function, public/private/protected, static
            ("php", re.compile(r"^\s*(?:public|private|protected|static)?\s*(?:function|async\s+function)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
            ("php_class_method", re.compile(r"^\s*(?:public|private|protected)?\s*(?:static)?\s*(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
            
            # Ruby: def
            ("ruby", re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_?!]*)")),
            
            # Go: func
            ("go", re.compile(r"^\s*func\s*(?:\([^)]*\))?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
            
            # Java: modifiers + return type + method name
            ("java", re.compile(r"^\s*(?:public|private|protected|static|final|synchronized)?\s*(?:[\w<>]+\s+)*([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{")),
            
            # Bash/Shell: function
            ("bash", re.compile(r"^\s*(?:function\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{")),
            
            # C/C++ 改进版: 支持复杂签名（指针、const、引用、模板等）
            ("c_cpp", re.compile(
                r"^\s*(?:inline|virtual|static|const|volatile|explicit|constexpr)?\s*"
                r"(?:[A-Za-z_~][\w:<>,\s]*\s+)?[*&\s]*"
                r"([A-Za-z_~][A-Za-z0-9_:]*)\s*\([^;]*\)\s*(?:const)?\s*(?:noexcept)?\s*\{?$"
            )),
        ]
        
        failure_reasons = []
        
        for idx in range(start_idx, -1, -1):
            line = file_lines[idx]
            stripped = line.strip()
            
            # 跳过注释和空行
            if not stripped:
                continue
            if stripped.startswith(("//", "#", "/*", "*", "--")):
                continue
            if stripped.startswith(("import ", "require ", "include ", "using ")):
                continue
                
            # 尝试所有模式
            for lang, pattern in patterns:
                try:
                    match = pattern.match(line)
                    if not match:
                        continue
                    
                    name = match.group(1).strip()
                    if (
                        not name
                        or len(name) < 1
                        or name in _PSEUDO_FUNCTION_NAMES
                        or name.lower() in _CONTROL_KEYWORDS
                    ):
                        continue
                    
                    start_line = idx + 1
                    end_line = start_line
                    
                    # 根据语言类型确定函数体范围
                    if lang == "python":
                        # Python: 基于缩进
                        indent = len(line) - len(line.lstrip())
                        for cursor in range(idx + 1, min(len(file_lines), idx + 500)):
                            probe = file_lines[cursor]
                            probe_stripped = probe.strip()
                            if not probe_stripped or probe_stripped.startswith("#"):
                                continue
                            probe_indent = len(probe) - len(probe.lstrip())
                            if probe_indent <= indent and not probe_stripped.startswith(("@", "#")):
                                break
                            end_line = cursor + 1
                    
                    elif lang == "ruby":
                        # Ruby: 查找 end 关键字
                        for cursor in range(idx + 1, min(len(file_lines), idx + 500)):
                            probe = file_lines[cursor].strip()
                            if probe == "end" or probe.startswith("end "):
                                end_line = cursor + 1
                                break
                            end_line = cursor + 1
                    
                    elif "{" in line:
                        # C/C++/Java/Go/JavaScript/PHP/Bash: 基于括号平衡
                        balance = line.count("{") - line.count("}")
                        end_line = idx + 1
                        for cursor in range(idx + 1, min(len(file_lines), idx + 500)):
                            probe = file_lines[cursor]
                            balance += probe.count("{") - probe.count("}")
                            end_line = cursor + 1
                            if balance <= 0:
                                break
                    else:
                        # 多行函数声明（无开括号）
                        looking_for_brace = True
                        for cursor in range(idx + 1, min(len(file_lines), idx + 20)):
                            probe = file_lines[cursor]
                            if "{" in probe:
                                balance = probe.count("{") - probe.count("}")
                                end_line = cursor + 1
                                for cursor2 in range(cursor + 1, min(len(file_lines), cursor + 500)):
                                    probe2 = file_lines[cursor2]
                                    balance += probe2.count("{") - probe2.count("}")
                                    end_line = cursor2 + 1
                                    if balance <= 0:
                                        break
                                looking_for_brace = False
                                break
                            end_line = cursor + 1
                    
                    logger.debug(
                        f"[Verification] 函数定位成功 (regex): {name} @ {start_line}-{end_line} (语言={lang})"
                    )
                    if not (start_line <= line_start <= end_line):
                        continue
                    return name, start_line, end_line
                    
                except Exception as e:
                    logger.debug(f"[Verification] regex 模式 {lang} 匹配失败: {e}")
                    failure_reasons.append(f"{lang}: {str(e)[:50]}")
                    continue
        
        logger.debug(
            f"[Verification] regex 函数定位全部失败 (line_start={line_start}, 失败原因={failure_reasons})"
        )
        return None, None, None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            parsed = int(value)
            if parsed > 0:
                return parsed
        except Exception:
            return None
        return None

    def _extract_locator_payload(
        self,
        raw_output: str,
    ) -> Optional[Dict[str, Any]]:
        return parse_locator_payload(raw_output)

    def _extract_function_from_locator_payload(
        self,
        payload: Dict[str, Any],
        line_start: int,
    ) -> Optional[Dict[str, Any]]:
        return select_locator_function(payload, line_start=line_start)

    async def _enrich_function_metadata_with_locator(
        self,
        findings_to_verify: List[Dict[str, Any]],
        project_root: Optional[str],
    ) -> None:
        """
        改进的函数定位辅助方法：增强容错与诊断日志
        当定位失败时，不再静默跳过，而是记录原因并标记状态
        """
        if not findings_to_verify:
            return

        success_count = 0
        fail_count = 0
        
        for idx, finding in enumerate(findings_to_verify):
            if not isinstance(finding, dict):
                logger.debug(f"[Verification] 函数定位 enrichment跳过非字典项 #{idx}")
                continue
            
            existing_name = str(finding.get("function_name") or "").strip()
            if existing_name and existing_name.lower() not in {"unknown", "未知函数"}:
                logger.debug(f"[Verification] 函数定位 enrichment跳过已有函数名: {existing_name}")
                continue

            file_path, line_start, _line_end = self._normalize_file_location(finding)
            resolved_file_path, _full = self._resolve_file_paths(file_path, project_root)
            request_path = resolved_file_path or file_path
            
            if not request_path or line_start <= 0:
                logger.debug(f"[Verification] 函数定位 enrichment跳过无效路径: {request_path}:{line_start}")
                continue

            locator_input = {
                "file_path": request_path,
                "line_start": int(line_start),
            }
            
            try:
                logger.debug(f"[Verification] 调用 locate_enclosing_function: {request_path}:{line_start}")
                locator_output = await self.execute_tool(
                    "locate_enclosing_function",
                    locator_input,
                )
                
                payload = self._extract_locator_payload(locator_output)
                if not payload:
                    fail_count += 1
                    logger.warning(
                        f"[Verification] locate_enclosing_function 返回空 payload: {request_path}:{line_start} | "
                        f"raw_output={str(locator_output)[:200]}"
                    )
                    # 标记工具尝试但失败
                    finding["_function_locator_attempt"] = "failed_empty_payload"
                    continue
                
                located = self._extract_function_from_locator_payload(payload, int(line_start))
                if not located:
                    fail_count += 1
                    logger.warning(
                        f"[Verification] locate_enclosing_function payload 解析失败: {request_path}:{line_start} | "
                        f"payload_keys={list(payload.keys())}"
                    )
                    finding["_function_locator_attempt"] = "failed_payload_parsing"
                    continue

                located_name = str(located.get("function") or "").strip()
                if not located_name:
                    fail_count += 1
                    logger.warning(
                        f"[Verification] locate_enclosing_function 返回空函数名: {request_path}:{line_start}"
                    )
                    finding["_function_locator_attempt"] = "failed_empty_function_name"
                    continue
                
                # 函数定位成功
                success_count += 1
                finding["function_name"] = located_name
                finding["function_start_line"] = self._safe_int(located.get("start_line"))
                finding["function_end_line"] = self._safe_int(located.get("end_line"))
                finding["function_resolution_method"] = "function_locator"
                finding["function_resolution_engine"] = "function_locator"
                if located.get("language"):
                    finding["function_language"] = located.get("language")
                if located.get("diagnostics") is not None:
                    finding["function_resolution_diagnostics"] = located.get("diagnostics")
                
                logger.info(
                    f"[Verification] 函数定位成功: '{located_name}' @ {request_path}:{line_start}"
                )
                
            except Exception as e:
                fail_count += 1
                logger.error(
                    f"[Verification] 工具调用异常: {request_path}:{line_start} | 错误: {e}",
                    exc_info=True
                )
                finding["_function_locator_attempt"] = f"exception: {str(e)[:100]}"
                continue
        
        logger.info(
            f"[Verification] 函数定位 enrichment 完成: 成功={success_count}, 失败={fail_count}, "
            f"总数={len(findings_to_verify)}"
        )

    def _resolve_function_metadata(
        self,
        finding: Dict[str, Any],
        project_root: Optional[str],
        ast_cache: Dict[str, tuple[Optional[str], Optional[int], Optional[int]]],
        file_cache: Dict[str, List[str]],
        locator: Optional[EnclosingFunctionLocator] = None,
    ) -> Dict[str, Any]:
        """
        改进的函数定位方法：4层降级策略 + 详细诊断日志
        层级1: 显式函数名 → 层级2: TreeSitter → 层级3: Regex → 层级4: 诊断失败
        """
        file_path, line_start, line_end = self._normalize_file_location(finding)
        resolved_file_path, full_file_path = self._resolve_file_paths(file_path, project_root)
        
        diagnostics_trace = []
        read_error_reason: Optional[str] = None

        # === 层级 1: 显式函数名提取 ===
        reachability_target = finding.get("reachability_target")
        if not isinstance(reachability_target, dict):
            verification_payload = finding.get("verification_result")
            if isinstance(verification_payload, dict):
                maybe_target = verification_payload.get("reachability_target")
                if isinstance(maybe_target, dict):
                    reachability_target = maybe_target
        
        explicit_function = None
        for candidate in (
            finding.get("function_name"),
            finding.get("function"),
            reachability_target.get("function") if isinstance(reachability_target, dict) else None,
            self._extract_function_name_from_title(finding.get("title")),
        ):
            if not isinstance(candidate, str):
                continue
            text = candidate.strip()
            if text and text.lower() not in {"unknown", "未知函数", "n/a", "-", "__attribute__", "__declspec"}:
                explicit_function = text
                diagnostics_trace.append(f"层级1-命中: 显式函数名 '{explicit_function}'")
                logger.info(f"[Verification] 函数定位成功 (显式): {explicit_function} @ {file_path}:{line_start}")
                break

        start_from_target: Optional[int] = None
        end_from_target: Optional[int] = None
        if isinstance(reachability_target, dict):
            raw_start = reachability_target.get("start_line")
            raw_end = reachability_target.get("end_line")
            try:
                start_from_target = int(raw_start) if raw_start is not None else None
            except Exception:
                start_from_target = None
            try:
                end_from_target = int(raw_end) if raw_end is not None else None
            except Exception:
                end_from_target = None
        
        explicit_start = (
            self._safe_int(finding.get("function_start_line"))
            or self._safe_int(finding.get("function_start"))
            or start_from_target
        )
        explicit_end = (
            self._safe_int(finding.get("function_end_line"))
            or self._safe_int(finding.get("function_end"))
            or end_from_target
        )
        explicit_resolution_method = (
            str(finding.get("function_resolution_method") or "").strip()
            or (
                str(reachability_target.get("resolution_method") or "").strip()
                if isinstance(reachability_target, dict)
                else ""
            )
            or "explicit"
        )
        explicit_resolution_engine = (
            str(finding.get("function_resolution_engine") or "").strip()
            or (
                str(reachability_target.get("resolution_engine") or "").strip()
                if isinstance(reachability_target, dict)
                else ""
            )
            or "explicit"
        )
        
        if explicit_function:
            return {
                "file_path": resolved_file_path or file_path,
                "function": explicit_function,
                "start_line": explicit_start,
                "end_line": explicit_end,
                "resolution_method": explicit_resolution_method,
                "resolution_engine": explicit_resolution_engine,
                "language": (
                    finding.get("function_language")
                    or (reachability_target.get("language") if isinstance(reachability_target, dict) else None)
                ),
                "diagnostics": finding.get("function_resolution_diagnostics")
                or (
                    reachability_target.get("diagnostics")
                    if isinstance(reachability_target, dict)
                    else None
                ),
                "localization_status": "explicit",
                "line_start": line_start,
                "line_end": line_end,
            }
        else:
            diagnostics_trace.append("层级1-无: 未找到有效的显式函数名")

        # === 层级 2: TreeSitter AST 定位 ===
        lines: List[str] = []
        if full_file_path:
            lines = file_cache.get(full_file_path) or []
            if not lines:
                try:
                    lines = Path(full_file_path).read_text(
                        encoding="utf-8",
                        errors="replace",
                    ).splitlines()
                except Exception as e:
                    diagnostics_trace.append(f"层级2-错误: 读取文件失败 ({str(e)[:50]})")
                    logger.warning(f"[Verification] 读文件失败: {full_file_path}: {e}")
                    lines = []
                file_cache[full_file_path] = lines

        tree_sitter_language: Optional[str] = None
        tree_sitter_diagnostics: Any = None
        
        if locator and project_root and resolved_file_path and full_file_path:
            try:
                logger.debug(f"[Verification] 尝试 TreeSitter 定位: {full_file_path}:{line_start}")
                located = locator.locate(
                    full_file_path=full_file_path,
                    line_start=line_start,
                    relative_file_path=resolved_file_path,
                    file_lines=lines,
                )
                tree_sitter_language = located.get("language")
                tree_sitter_diagnostics = located.get("diagnostics")
                function_name = located.get("function")
                
                if isinstance(function_name, str) and function_name.strip():
                    diagnostics_trace.append(f"层级2-命中: TreeSitter 定位 '{function_name}'")
                    logger.info(f"[Verification] 函数定位成功 (TreeSitter): {function_name} @ {file_path}:{line_start}")
                    return {
                        "file_path": resolved_file_path,
                        "function": function_name.strip(),
                        "start_line": located.get("start_line"),
                        "end_line": located.get("end_line"),
                        "resolution_method": located.get("resolution_method") or "python_tree_sitter",
                        "resolution_engine": located.get("resolution_engine") or "python_tree_sitter",
                        "language": located.get("language"),
                        "diagnostics": located.get("diagnostics"),
                        "localization_status": "tree_sitter",
                        "line_start": line_start,
                        "line_end": line_end,
                    }
                else:
                    diagnostics_trace.append("层级2-无: TreeSitter 未找到函数")
                    logger.debug(f"[Verification] TreeSitter 返回空函数: {file_path}:{line_start}")
            except Exception as e:
                diagnostics_trace.append(f"层级2-错误: TreeSitter 异常 ({str(e)[:50]})")
                logger.debug(f"[Verification] TreeSitter 异常: {e}")
        else:
            reason = []
            if not locator:
                reason.append("无locator")
            if not project_root:
                reason.append("无project_root")
            if not resolved_file_path:
                reason.append("无resolved_file_path")
            if not full_file_path:
                reason.append("无full_file_path")
            diagnostics_trace.append(f"层级2-跳过: {', '.join(reason)}")

        # === 层级 3: Regex 推断 ===
        regex_name: Optional[str] = None
        regex_start: Optional[int] = None
        regex_end: Optional[int] = None
        
        if lines:
            try:
                logger.debug(f"[Verification] 尝试 Regex 定位: {file_path}:{line_start}")
                regex_name, regex_start, regex_end = self._infer_function_by_regex(lines, line_start)
                
                if regex_name:
                    diagnostics_trace.append(f"层级3-命中: Regex 推断 '{regex_name}'")
                    logger.info(f"[Verification] 函数定位成功 (Regex): {regex_name} @ {file_path}:{line_start}")
                    return {
                        "file_path": resolved_file_path or file_path,
                        "function": regex_name,
                        "start_line": regex_start,
                        "end_line": regex_end,
                        "resolution_method": "regex_fallback",
                        "resolution_engine": "regex_fallback",
                        "language": tree_sitter_language,
                        "diagnostics": tree_sitter_diagnostics,
                        "localization_status": "regex",
                        "line_start": line_start,
                        "line_end": line_end,
                    }
                else:
                    diagnostics_trace.append("层级3-无: Regex 未找到函数")
                    logger.debug(f"[Verification] Regex 未能定位函数: {file_path}:{line_start}")
            except Exception as e:
                diagnostics_trace.append(f"层级3-错误: Regex 异常 ({str(e)[:50]})")
                logger.warning(f"[Verification] Regex 定位异常: {e}")
        else:
            diagnostics_trace.append("层级3-跳过: 无文件行内容")

        # === 层级 4: 全部失败 - 返回诊断信息 ===
        logger.warning(
            f"[Verification] 所有函数定位方法失败: {file_path}:{line_start} | "
            f"诊断链: {' → '.join(diagnostics_trace)}"
        )
        
        # === 改进的文件可读性判定 ===
        # 区分三种情况：文件存在但为空、文件存在且可读、文件不存在
        file_exists = False
        if full_file_path:
            try:
                file_exists = Path(full_file_path).exists()
            except Exception as e:
                logger.debug(f"[Verification] 检查文件存在性失败: {e}")
        
        file_readable = bool(lines) and file_exists
        if not file_readable:
            if file_exists and not lines:
                read_error_reason = "file_is_empty"
            elif not file_exists:
                read_error_reason = "file_not_exists"
            else:
                read_error_reason = "read_failed_unknown_reason"
        return {
            "file_path": resolved_file_path or file_path,
            "function": None,
            "start_line": None,
            "end_line": None,
            "resolution_method": "missing_enclosing_function",
            "resolution_engine": "missing_enclosing_function",
            "language": tree_sitter_language,
            "diagnostics": tree_sitter_diagnostics,
            "localization_status": "failed",
            "localization_failure_trace": diagnostics_trace,
            "file_readable": file_readable,
            "file_exists": file_exists,
            "read_error_reason": read_error_reason,
            "line_start": line_start,
            "line_end": line_end,
        }

    def _build_min_function_trigger_flow(
        self,
        existing_flow: Any,
        file_path: str,
        function_name: Optional[str],
        function_start_line: Optional[int],
        function_end_line: Optional[int],
        line_start: int,
        line_end: int,
    ) -> List[str]:
        if isinstance(existing_flow, list):
            normalized = [str(step).strip() for step in existing_flow if str(step).strip()]
            if normalized:
                return normalized
        flow: List[str] = []
        if function_name:
            if function_start_line and function_end_line:
                flow.append(
                    f"{file_path}:{function_name} ({function_start_line}-{function_end_line})"
                )
            else:
                flow.append(f"{file_path}:{function_name}")
        hit_line_text = f"{line_start}-{line_end}" if line_end >= line_start else str(line_start)
        flow.append(f"命中位置: {file_path}:{hit_line_text}")
        return flow

    def _repair_final_answer(
        self,
        final_answer: Dict[str, Any],
        findings_to_verify: List[Dict[str, Any]],
        verification_level: str,
        project_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        findings = final_answer.get("findings")
        if not isinstance(findings, list):
            findings = []

        fallback_findings = [item for item in (findings_to_verify or []) if isinstance(item, dict)]
        llm_findings = [item for item in findings if isinstance(item, dict)]
        repaired_findings: List[Dict[str, Any]] = []
        source_findings = fallback_findings if fallback_findings else llm_findings

        llm_by_key: Dict[tuple[str, str, int], Dict[str, Any]] = {}
        for item in llm_findings:
            file_path, line_start, _line_end = self._normalize_file_location(item)
            key = (self._normalize_vulnerability_key(item), file_path, line_start)
            llm_by_key.setdefault(key, item)

        ast_cache: Dict[str, tuple[Optional[str], Optional[int], Optional[int]]] = {}
        file_cache: Dict[str, List[str]] = {}
        locator = EnclosingFunctionLocator(project_root=project_root) if project_root else None
        for index, base in enumerate(source_findings):
            file_path, line_start, _line_end = self._normalize_file_location(base)
            key = (self._normalize_vulnerability_key(base), file_path, line_start)
            llm_item = llm_by_key.get(key)
            if llm_item is None and index < len(llm_findings):
                llm_item = llm_findings[index]
            merged = {**base, **(llm_item or {})}

            normalized_file_path, line_start, line_end = self._normalize_file_location(merged)
            function_meta = self._resolve_function_metadata(
                merged,
                project_root=project_root,
                ast_cache=ast_cache,
                file_cache=file_cache,
                locator=locator,
            )
            resolved_file_path = (
                str(function_meta.get("file_path") or normalized_file_path or "").strip()
                or str(base.get("file_path") or "").strip()
            )
            function_name = function_meta.get("function")
            raw_fallback_function_name = str(merged.get("function_name") or "").strip()
            effective_function_name = str(function_name or raw_fallback_function_name).strip()
            if not effective_function_name:
                effective_function_name = f"<function_at_line_{line_start}>"
            localization_status = function_meta.get("localization_status", "unknown")
            file_readable = function_meta.get("file_readable", False)

            # === 改进的验证逻辑：解耦函数定位与验证判定 ===
            verdict = self._normalize_verdict(merged)
            reachability = self._normalize_reachability_value(merged.get("reachability"), verdict)
            evidence = (
                merged.get("verification_details")
                or merged.get("verification_evidence")
                or merged.get("evidence")
                or "基于代码上下文与工具输出完成验证。"
            )
            
            # === 新规则：不再因缺少函数名就自动标记为false_positive ===
            # 只有在以下情况才标记为false_positive：
            # 1. 文件不可读（真正的无法验证）
            # 2. OR LLM明确判定为false_positive
            
            if not function_name:
                # === 改进的规则：区分文件状态，避免误判 ===
                if not file_readable:
                    # 情况1: 文件确实不存在 → false_positive（真实文件丢失）
                    file_exists = function_meta.get("file_exists")
                    if file_exists is False:
                        verdict = "false_positive"
                        reachability = "unreachable"
                        logger.warning(
                            f"[Verification] 标记为 false_positive (原因: 文件不存在): {normalized_file_path}:{line_start}"
                        )
                    else:
                        # 情况2: 文件存在但为空或读不了 → uncertain（信息不足）
                        verdict = "uncertain"
                        reachability = "unknown"
                        read_reason = function_meta.get("read_error_reason")
                        logger.warning(
                            f"[Verification] 标记为 uncertain (原因: 文件不可读, read_reason={read_reason}): "
                            f"{normalized_file_path}:{line_start}"
                        )
                elif verdict == "false_positive":
                    # LLM已经判定为false_positive，保持不变
                    logger.debug(
                        f"[Verification] LLM判定false_positive，虽未定位函数: {normalized_file_path}:{line_start}"
                    )
                else:
                    # 文件可读但未能定位函数 → 保留LLM判定，添加локalization标记
                    logger.info(
                        f"[Verification] 未定位函数但保留 LLM 判定 ({verdict}), "
                        f"localization_status={localization_status}, file_readable={file_readable}: "
                        f"{normalized_file_path}:{line_start}"
                    )
            else:
                logger.debug(
                    f"[Verification] 成功定位函数 '{function_name}' "
                    f"(方法={localization_status}): {normalized_file_path}:{line_start}"
                )

            suggestion = (
                merged.get("suggestion")
                or merged.get("recommendation")
                or self._get_recommendation(str(merged.get("vulnerability_type") or ""))
            )
            if not suggestion:
                suggestion = self._get_recommendation(str(merged.get("vulnerability_type") or ""))

            fix_code = merged.get("fix_code")
            if verdict in {"confirmed", "likely"} and not str(fix_code or "").strip():
                fix_code = self._build_default_fix_code(merged)

            allow_poc = verdict in {"confirmed", "likely"}
            poc_value = merged.get("poc") if allow_poc else None
            if allow_poc and not poc_value:
                poc_value = self._build_default_poc_plan(merged)
            poc_value = self._normalize_mock_poc(poc_value)

            vuln_profile = resolve_vulnerability_profile(
                merged.get("vulnerability_type"),
                title=merged.get("title"),
                description=merged.get("description"),
                code_snippet=merged.get("code_snippet"),
            )
            cwe_id = self._infer_cwe_id(merged) or vuln_profile.get("cwe")
            flow = self._build_min_function_trigger_flow(
                existing_flow=(
                    merged.get("function_trigger_flow")
                    if isinstance(merged.get("function_trigger_flow"), list)
                    else (
                        merged.get("verification_result", {}).get("function_trigger_flow")
                        if isinstance(merged.get("verification_result"), dict)
                        else None
                    )
                ),
                file_path=resolved_file_path or normalized_file_path,
                function_name=effective_function_name,
                function_start_line=function_meta.get("start_line"),
                function_end_line=function_meta.get("end_line"),
                line_start=line_start,
                line_end=line_end,
            )
            context_start_line = self._normalize_int_line(
                (
                    merged.get("context_start_line")
                    or (
                        merged.get("verification_result", {}).get("context_start_line")
                        if isinstance(merged.get("verification_result"), dict)
                        else None
                    )
                    or max(1, line_start - 12)
                ),
                max(1, line_start - 12),
            )
            context_end_line = self._normalize_int_line(
                (
                    merged.get("context_end_line")
                    or (
                        merged.get("verification_result", {}).get("context_end_line")
                        if isinstance(merged.get("verification_result"), dict)
                        else None
                    )
                    or (line_end + 12)
                ),
                line_end + 12,
            )
            if context_end_line < context_start_line:
                context_end_line = context_start_line

            verification_result = (
                dict(merged.get("verification_result"))
                if isinstance(merged.get("verification_result"), dict)
                else {}
            )
            
            # === 诊断追踪：记录置信度与文件状态 ===
            confidence_for_tracking = merged.get("confidence")
            if confidence_for_tracking is None:
                confidence_source_for_tracking = "missing"
            else:
                confidence_source_for_tracking = "direct"
            
            verification_result.update(
                {
                    "authenticity": verdict,
                    "verdict": verdict,
                    "reachability": reachability,
                    "evidence": str(evidence),
                    "verification_details": str(evidence),
                    "verification_evidence": str(evidence),
                    "context_start_line": context_start_line,
                    "context_end_line": context_end_line,
                    "reachability_target": {
                        "file_path": resolved_file_path or normalized_file_path,
                        "function": effective_function_name,
                        "start_line": function_meta.get("start_line"),
                        "end_line": function_meta.get("end_line"),
                        "resolution_method": function_meta.get("resolution_method"),
                        "language": function_meta.get("language"),
                        "resolution_engine": function_meta.get("resolution_engine"),
                        "diagnostics": function_meta.get("diagnostics"),
                    },
                    "function_trigger_flow": flow,
                    # === 新增诊断追踪字段 ===
                    "confidence_source": confidence_source_for_tracking,
                    "confidence_value": confidence_for_tracking,
                    "file_status": {
                        "file_exists": function_meta.get("file_exists"),
                        "file_readable": file_readable,
                        "read_error_reason": function_meta.get("read_error_reason"),
                    },
                }
            )
            if not function_name:
                # 添加定位失败的诊断信息
                verification_result["validation_reason"] = "missing_enclosing_function"
                verification_result["localization_status"] = localization_status
                verification_result["localization_failure_trace"] = (
                    function_meta.get("localization_failure_trace") or []
                )

            structured_title = self._build_structured_title(
                {
                    **merged,
                    "file_path": resolved_file_path or normalized_file_path,
                    # 改进：不再无条件使用"未知函数"，而是基于定位状态
                    "function_name": effective_function_name or (
                        f"[{localization_status}]" if localization_status != "unknown" else "未知函数"
                    ),
                }
            )

            repaired_entry = {
                **merged,
                "vulnerability_type": vuln_profile.get("key", "other"),
                "title": structured_title,
                "display_title": structured_title,
                "file_path": resolved_file_path or normalized_file_path,
                "line_start": line_start,
                "line_end": line_end,
                "function_name": effective_function_name,
                "verdict": verdict,
                "authenticity": verdict,
                "reachability": reachability,
                "is_verified": verdict in {"confirmed", "likely"},
                "cwe_id": cwe_id,
                "verification_details": str(evidence),
                "verification_evidence": str(evidence),
                "verification_result": verification_result,
                "function_trigger_flow": flow,
                "suggestion": str(suggestion),
                "fix_code": fix_code,
                "poc": poc_value,
                # === 新字段：函数定位状态透明度 ===
                "localization_status": localization_status,
                "file_readable": file_readable,
            }
            repaired_entry = self._apply_source_sink_authenticity_gate(
                repaired_entry,
                fallback=base,
            )
            repaired_findings.append(repaired_entry)

        summary = final_answer.get("summary")
        if not isinstance(summary, dict):
            summary = {}
        summary.setdefault("total", len(repaired_findings))
        summary.setdefault("confirmed", len([f for f in repaired_findings if f.get("verdict") == "confirmed"]))
        summary.setdefault("likely", len([f for f in repaired_findings if f.get("verdict") == "likely"]))
        summary.setdefault("uncertain", len([f for f in repaired_findings if f.get("verdict") == "uncertain"]))  # 新增
        summary.setdefault("false_positive", len([f for f in repaired_findings if f.get("verdict") == "false_positive"]))

        return {
            **final_answer,
            "findings": repaired_findings,
            "summary": summary,
        }

    @staticmethod
    def _build_candidate_fingerprint(finding: Dict[str, Any], index: int) -> str:
        file_path = str(finding.get("file_path") or finding.get("file") or "").strip()
        line_start = str(finding.get("line_start") or finding.get("line") or "")
        vuln_type = str(finding.get("vulnerability_type") or "unknown").strip().lower()
        title = str(finding.get("title") or "").strip()
        base = f"{file_path}|{line_start}|{vuln_type}|{title}|{index}"
        return hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()[:16]

    def _build_verification_todo_items(
        self,
        findings_to_verify: List[Dict[str, Any]],
        max_attempts_per_item: int,
        project_root: Optional[str] = None,
    ) -> List[VerificationTodoItem]:
        todo_items: List[VerificationTodoItem] = []
        for idx, finding in enumerate(findings_to_verify):
            file_path, line_start, _line_end = self._normalize_file_location(finding)
            file_path = self._to_display_file_path(file_path, project_root)
            title = str(finding.get("title") or f"候选漏洞#{idx + 1}").strip() or f"候选漏洞#{idx + 1}"
            fingerprint = self._build_candidate_fingerprint(finding, idx)
            todo_items.append(
                VerificationTodoItem(
                    id=f"verification-{idx + 1}-{fingerprint[:8]}",
                    fingerprint=fingerprint,
                    file_path=file_path,
                    line_start=max(1, int(line_start or 1)),
                    title=title,
                    status="pending",
                    attempts=0,
                    max_attempts=max(1, int(max_attempts_per_item)),
                )
            )
        return todo_items

    @staticmethod
    def _extract_tool_error_reason(observation: str) -> Optional[str]:
        text = str(observation or "")
        if not text.strip():
            return "empty_observation"
        lowered = text.lower()
        if "任务已取消" in text or "cancel" in lowered:
            return "cancelled"
        if "阻断" in text or "blocked_reason" in lowered:
            return "blocked"
        if "短路" in text:
            return "retry_guard_short_circuit"
        if "参数校验失败" in text or "必填字段" in text:
            return "input_validation_failed"
        deterministic_hints = [
            "工具执行失败",
            "不存在",
            "not found",
            "不是文件",
            "路径不在允许范围",
            "permission denied",
            "invalid",
            "错误",
            "异常",
            "阻断",
        ]
        for hint in deterministic_hints:
            if hint in text or hint in lowered:
                return "deterministic_tool_error"
        return None

    @staticmethod
    def _extract_verify_pipeline_blocked_reason(observation: str) -> Optional[str]:
        text = str(observation or "")
        lowered = text.lower()
        runtime_hints = (
            "tool_call_failed:",
            "tool_adapter_unavailable:",
            "adapter_disabled_after_failures",
            "runtime 未就绪",
            "router 未匹配",
            "server disconnected without sending a response",
            "remoteprotocolerror",
            "connecterror",
            "readtimeout",
            "connection refused",
            "connection reset",
            "status_502",
            "status_503",
            "status_504",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "healthcheck_failed",
        )
        if any(hint in lowered for hint in runtime_hints):
            return "tool_unavailable"
        known = {
            "tool_unavailable",
            "insufficient_flow_evidence",
            "missing_location",
            "read_budget_exhausted",
            "cancelled",
        }
        for reason in known:
            if reason in lowered:
                return reason

        marker = "verify_pipeline_json:"
        marker_index = lowered.rfind(marker)
        if marker_index < 0:
            return None
        json_part = text[marker_index + len(marker) :].strip()
        try:
            payload = json.loads(json_part)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        candidate = str(payload.get("verify_pipeline_blocked_reason") or "").strip().lower()
        if candidate in known:
            return candidate
        return None

    @staticmethod
    def _map_flow_error_to_blocked_reason(
        flow_error_reason: Optional[str],
        pipeline_blocked_reason: Optional[str],
    ) -> str:
        if pipeline_blocked_reason:
            return pipeline_blocked_reason
        if flow_error_reason in {"cancelled"}:
            return "cancelled"
        if flow_error_reason in {"empty_observation", "blocked", "deterministic_tool_error"}:
            return "insufficient_flow_evidence"
        if flow_error_reason in {"input_validation_failed"}:
            return "insufficient_flow_evidence"
        return "insufficient_flow_evidence"

    @staticmethod
    def _is_flow_evidence_positive(flow_observation: str) -> bool:
        text = str(flow_observation or "").lower()
        positive_markers = [
            '"path_found": true',
            '"reachable"',
            "likely_reachable",
            "path_score",
            "call_chain",
            "flow",
            "可达",
        ]
        return any(marker in text for marker in positive_markers)

    @staticmethod
    def _infer_language_from_path(file_path: str) -> str:
        ext = str(Path(str(file_path or "")).suffix or "").lower()
        mapping = {
            ".py": "python",
            ".php": "php",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "javascript",
            ".tsx": "javascript",
            ".rb": "ruby",
            ".go": "go",
            ".java": "java",
            ".sh": "bash",
            ".bash": "bash",
        }
        return mapping.get(ext, "python")

    @staticmethod
    def _extract_code_block(observation: str) -> str:
        text = str(observation or "")
        if not text.strip():
            return ""
        fence_match = re.search(r"```(?:[a-zA-Z0-9_+-]+)?\n([\s\S]*?)\n```", text)
        if fence_match:
            return str(fence_match.group(1) or "").strip()
        return text.strip()

    def _build_fuzzing_harness(
        self,
        *,
        vulnerability_type: str,
        language: str,
        function_name: Optional[str],
        extracted_code: str,
        code_context: str,
        file_path: str,
        line_start: int,
    ) -> str:
        vuln = str(vulnerability_type or "general_issue").strip().lower()
        payloads = {
            "command_injection": ["test", "; id", "| whoami", "`id`", "$(id)", "&& ls"],
            "sql_injection": ["1", "1'", "1' OR '1'='1", "1 UNION SELECT 1", "1'; DROP TABLE t--"],
            "xss": ["test", "<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "{{7*7}}"],
            "path_traversal": ["a.txt", "../etc/passwd", "../../../../etc/hosts", "..\\..\\windows\\win.ini"],
            "ssrf": ["http://example.com", "http://127.0.0.1:80", "http://169.254.169.254/latest/meta-data"],
            "deserialization": ["{}", "O:8:\"Exploit\":0:{}", "!!python/object/apply:os.system ['id']"],
        }
        selected_payloads = payloads.get(vuln, ["test", "' OR '1'='1", "<script>alert(1)</script>"])

        if language == "python" and function_name and extracted_code.strip():
            return f'''import inspect\nimport os\nimport subprocess\n\nTARGET_FILE = {json.dumps(file_path)}\nTARGET_LINE = {int(line_start)}\nVULN_TYPE = {json.dumps(vuln)}\nPAYLOADS = {json.dumps(selected_payloads, ensure_ascii=False)}\n\nexecuted_calls = []\n\ndef _record(tag, value):\n    executed_calls.append((tag, str(value)))\n    print(f"[DETECTED] {{tag}}: {{value}}")\n\n_orig_system = os.system\n_orig_popen = os.popen\n_orig_run = subprocess.run\n_orig_popen2 = subprocess.Popen\n\ndef _mock_system(cmd):\n    _record("os.system", cmd)\n    return 0\n\ndef _mock_popen(cmd, *args, **kwargs):\n    _record("os.popen", cmd)\n    class _Dummy:\n        def read(self):\n            return "mock"\n    return _Dummy()\n\ndef _mock_run(*args, **kwargs):\n    _record("subprocess.run", args[0] if args else kwargs.get("args"))\n    class _Result:\n        returncode = 0\n        stdout = "mock"\n        stderr = ""\n    return _Result()\n\ndef _mock_popen2(*args, **kwargs):\n    _record("subprocess.Popen", args[0] if args else kwargs.get("args"))\n    class _Proc:\n        returncode = 0\n        def communicate(self):\n            return ("mock", "")\n    return _Proc()\n\nos.system = _mock_system\nos.popen = _mock_popen\nsubprocess.run = _mock_run\nsubprocess.Popen = _mock_popen2\n\n# === extracted function code ===\n{extracted_code}\n\nif {json.dumps(function_name)} not in globals():\n    print("[SAFE] target function not found in extracted code")\nelse:\n    fn = globals()[{json.dumps(function_name)}]\n    sig = inspect.signature(fn)\n    required = [\n        p for p in sig.parameters.values()\n        if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)\n        and p.default is inspect._empty\n    ]\n\n    print("=== FUZZING START ===")\n    for payload in PAYLOADS:\n        executed_calls.clear()\n        args = [payload for _ in required]\n        print(f"\\n[PAYLOAD] {{payload}}")\n        try:\n            result = fn(*args)\n            print(f"[RETURN] {{result}}")\n            if executed_calls:\n                print("[VULN] dangerous sink invoked")\n            rendered = str(result) if result is not None else ""\n            if VULN_TYPE in {{"xss", "ssti"}} and payload in rendered and ("<" in payload or "{{" in payload):\n                print("[VULN] unsanitized reflection")\n            if VULN_TYPE == "sql_injection" and ("'" in payload or " union " in payload.lower() or " or " in payload.lower()):\n                if payload in rendered:\n                    print("[VULN] payload reflected in output")\n        except Exception as exc:\n            print(f"[ERROR] {{exc}}")\n\n# restore\nos.system = _orig_system\nos.popen = _orig_popen\nsubprocess.run = _orig_run\nsubprocess.Popen = _orig_popen2\n'''

        code_blob = extracted_code.strip() or code_context.strip()
        return f'''# Lightweight harness fallback\n# language={language}, vuln={vuln}\nCODE = {json.dumps(code_blob[:12000], ensure_ascii=False)}\nPAYLOADS = {json.dumps(selected_payloads, ensure_ascii=False)}\nprint("=== HARNESS FALLBACK ===")\nprint("code_length=", len(CODE))\npositive = False\nfor p in PAYLOADS:\n    if p and p in CODE:\n        print("[VULN] payload token appears in code:", p)\n        positive = True\nfor marker in ["eval(", "exec(", "system(", "Runtime.getRuntime().exec", "shell_exec(", "subprocess", "SELECT", "innerHTML", "document.write", "../", "..\\\\"]:\n    if marker.lower() in CODE.lower():\n        print("[SIGNAL] dangerous marker:", marker)\n        positive = True\nif not positive:\n    print("[SAFE] no direct exploit signal in fallback harness")\n'''

    @staticmethod
    def _is_harness_evidence_positive(observation: str) -> bool:
        text = str(observation or "").lower()
        positive_markers = [
            "[vuln]",
            "dangerous sink invoked",
            "unsanitized reflection",
            "payload reflected",
            "[detected]",
            "漏洞已确认",
            '"is_vulnerable": true',
        ]
        return any(marker in text for marker in positive_markers)

    @staticmethod
    def _shorten_observation(observation: str, max_chars: int = 1200) -> str:
        text = str(observation or "").strip()
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...(truncated)"

    def _build_verification_todo_summary(
        self,
        todo_items: List[VerificationTodoItem],
    ) -> Dict[str, Any]:
        total = len(todo_items)
        verified = len([item for item in todo_items if item.status == "verified"])
        false_positive = len([item for item in todo_items if item.status == "false_positive"])
        uncertain = len([item for item in todo_items if item.status == "uncertain"])
        blocked = len([item for item in todo_items if item.status == "blocked"])
        pending = len([item for item in todo_items if item.status in {"pending", "running"}])
        blocked_reasons: Dict[str, int] = {}
        for item in todo_items:
            reason = str(item.blocked_reason or "").strip()
            if not reason:
                continue
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
        blocked_reasons_top = sorted(
            blocked_reasons.items(),
            key=lambda pair: pair[1],
            reverse=True,
        )[:5]
        return {
            "total": total,
            "verified": verified,
            "false_positive": false_positive,
            "uncertain": uncertain,
            "blocked": blocked,
            "pending": pending,
            "blocked_reasons_top": [
                {"reason": reason, "count": count}
                for reason, count in blocked_reasons_top
            ],
            "per_item_compact": [
                {
                    "id": item.id,
                    "status": item.status,
                    "final_status": item.status,
                    "reason": item.blocked_reason,
                }
                for item in todo_items
            ],
        }

    async def _emit_verification_todo_update(
        self,
        todo_items: List[VerificationTodoItem],
        message: str,
        current_index: Optional[int] = None,
        total_todos: Optional[int] = None,
        last_action: Optional[str] = None,
        last_tool_name: Optional[str] = None,
    ) -> None:
        await self.emit_event(
            "todo_update",
            message,
            metadata={
                "todo_scope": "verification",
                "todo_list": [item.to_dict() for item in todo_items],
                "current_todo_index": current_index,
                "total_todos": total_todos if total_todos is not None else len(todo_items),
                "last_action": last_action,
                "last_tool_name": last_tool_name,
            },
        )

    async def _emit_finding_table_update(
        self,
        finding_table: VerificationFindingTable,
        message: str,
        *,
        round_index: int,
        queue_size: int,
        newly_discovered_count: int,
    ) -> Dict[str, Any]:
        summary = finding_table.summary(
            round_index=round_index,
            queue_size=queue_size,
            newly_discovered_count=newly_discovered_count,
        )
        await self.emit_event(
            "todo_update",
            message,
            metadata={
                "todo_scope": "finding_table",
                "todo_list": finding_table.to_todo_list(),
                "finding_table_summary": summary,
                **summary,
            },
        )
        return summary

    async def _emit_unverified_finding_event(
        self,
        finding: Dict[str, Any],
        status: str = "new",
        project_root: Optional[str] = None,
        verification_todo_id: Optional[str] = None,
        verification_fingerprint: Optional[str] = None,
    ) -> None:
        title = str(finding.get("title") or "待验证漏洞").strip() or "待验证漏洞"
        severity = str(finding.get("severity") or "medium").strip() or "medium"
        vuln_type = str(finding.get("vulnerability_type") or "unknown").strip() or "unknown"
        file_path, line_start, line_end = self._normalize_file_location(finding)
        file_path = self._to_display_file_path(file_path, project_root)
        description_text = (
            str(finding.get("description"))
            if finding.get("description") is not None
            else None
        )
        description_markdown = build_cn_structured_description_markdown(
            file_path=file_path,
            function_name=finding.get("function_name"),
            vulnerability_type=vuln_type,
            title=title,
            description=description_text,
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
            cwe_id=self._infer_cwe_id(finding),
            raw_description=description_text,
            line_start=line_start,
            line_end=line_end,
            verification_evidence=description_text,
            localization_status=finding.get("localization_status"),
        )
        await self.emit_event(
            "finding_new" if status == "new" else "finding_update",
            f"[Verification] 未验证候选: {title}",
            metadata={
                "title": title,
                "display_title": title,
                "severity": severity,
                "vulnerability_type": vuln_type,
                "file_path": file_path,
                "line_start": line_start,
                "line_end": line_end,
                "is_verified": False,
                "status": status,
                "description": description_text,
                "description_markdown": description_markdown,
                "code_snippet": finding.get("code_snippet"),
                "finding_scope": "verification_queue",
                "verification_todo_id": verification_todo_id,
                "verification_fingerprint": verification_fingerprint,
                "verification_status": status if status in {"new", "running"} else "new",
            },
        )
    
    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        执行漏洞验证 - LLM 全程参与！
        """
        import time
        start_time = time.time()
        self._trace("run_started", has_input=bool(input_data))
        # 关键工具调用追踪按 run 维度重置，避免跨轮次污染判定
        self._critical_tool_called = False
        self._critical_tool_name = None
        self._critical_tool_calls = []

        previous_results = input_data.get("previous_results", {})
        config = input_data.get("config", {})
        thinking_push_mode = str(config.get("thinking_push_mode", "stream") or "stream").strip().lower()
        self._thinking_push_mode = thinking_push_mode if thinking_push_mode in {"stream", "final_only"} else "stream"
        task = input_data.get("task", "")
        task_context = input_data.get("task_context", "")
        project_root = input_data.get("project_root")
        task_id = str(input_data.get("task_id") or getattr(self, "_task_id", "") or "").strip()
        if not isinstance(project_root, str) or not project_root.strip():
            project_root = None
        max_attempts_per_item = max(1, int(config.get("verification_max_attempts_per_item", 2)))

        handoff = input_data.get("handoff")
        if handoff:
            from .base import TaskHandoff
            if isinstance(handoff, dict):
                handoff = TaskHandoff.from_dict(handoff)
            self.receive_handoff(handoff)

        findings_to_verify = []
        
        #  优先支持：从队列取出的单个漏洞（方案A支持）
        # Orchestrator 在调用 dequeue_finding 后，会将单个漏洞通过 context 传递
        queue_finding_from_context = None
        if task_context and isinstance(task_context, str):
            # 尝试从 task_context 中解析 JSON 漏洞信息
            try:
                # task_context 可能是纯文本描述，也可能包含 JSON
                if task_context.strip().startswith("{"):
                    queue_finding_from_context = json.loads(task_context)
                elif "finding_from_queue" in task_context or "dequeued_finding" in task_context:
                    # 尝试提取嵌入的 JSON
                    json_match = re.search(r'\{.*\}', task_context, re.DOTALL)
                    if json_match:
                        queue_finding_from_context = json.loads(json_match.group(0))
            except (json.JSONDecodeError, Exception) as e:
                logger.debug(f"[Verification] 无法从 task_context 解析队列漏洞: {e}")
        
        # 如果通过 config 传递了单个漏洞（备用方案）
        if not queue_finding_from_context and isinstance(config, dict):
            queue_finding_from_context = config.get("queue_finding")
        
        if queue_finding_from_context and isinstance(queue_finding_from_context, dict):
            findings_to_verify = [queue_finding_from_context]
            logger.info(f"[Verification] 🎯 从队列获取单个漏洞进行验证: {queue_finding_from_context.get('title', 'N/A')}")
            self._trace(
                "queue_finding_loaded",
                title=queue_finding_from_context.get("title"),
                file_path=queue_finding_from_context.get("file_path"),
                line_start=queue_finding_from_context.get("line_start"),
            )

        if self._incoming_handoff and self._incoming_handoff.key_findings and not findings_to_verify:
            findings_to_verify = self._incoming_handoff.key_findings.copy()
            logger.info(f"[Verification] 从交接信息获取 {len(findings_to_verify)} 个发现")
        
        if not findings_to_verify:
            if isinstance(previous_results, dict) and "findings" in previous_results:
                direct_findings = previous_results.get("findings", [])
                if isinstance(direct_findings, list):
                    for finding in direct_findings:
                        if isinstance(finding, dict):
                            severity = str(finding.get("severity", "")).lower()
                            needs_verify = finding.get("needs_verification", True)
                            if needs_verify or severity in ["critical", "high"]:
                                findings_to_verify.append(finding)
                    logger.info(f"[Verification] 从 previous_results.findings 获取 {len(findings_to_verify)} 个发现")

            if not findings_to_verify:
                bootstrap_findings = previous_results.get("bootstrap_findings", []) if isinstance(previous_results, dict) else []
                if isinstance(bootstrap_findings, list):
                    for finding in bootstrap_findings:
                        if isinstance(finding, dict):
                            findings_to_verify.append(finding)

            if not findings_to_verify:
                for phase_name, result in previous_results.items():
                    if phase_name == "findings":
                        continue
                    if isinstance(result, dict):
                        data = result.get("data", {})
                    else:
                        data = result.data if hasattr(result, "data") else {}

                    if isinstance(data, dict):
                        phase_findings = data.get("findings", [])
                        for finding in phase_findings:
                            if isinstance(finding, dict):
                                severity = str(finding.get("severity", "")).lower()
                                needs_verify = finding.get("needs_verification", True)
                                if needs_verify or severity in ["critical", "high"]:
                                    findings_to_verify.append(finding)

                if findings_to_verify:
                    logger.info(f"[Verification] 从传统格式获取 {len(findings_to_verify)} 个发现")

            if isinstance(previous_results, dict):
                analysis_result = previous_results.get("analysis")
                if isinstance(analysis_result, dict):
                    analysis_data = analysis_result.get("data", {})
                    if isinstance(analysis_data, dict):
                        analysis_findings = analysis_data.get("findings", [])
                        if isinstance(analysis_findings, list):
                            for finding in analysis_findings:
                                if isinstance(finding, dict):
                                    findings_to_verify.append(finding)

        if not findings_to_verify:
            if task and ("发现" in task or "漏洞" in task or "findings" in task.lower()):
                logger.warning(f"[Verification] 无法从结构化数据获取发现，任务描述: {task[:200]}")
                await self.emit_event("warning", "无法从结构化数据获取发现列表，将基于任务描述进行验证")

        findings_to_verify = self._deduplicate(findings_to_verify)
        self._trace("findings_collected", count=len(findings_to_verify))

        def has_valid_file_path(finding: Dict) -> bool:
            file_path = finding.get("file_path", "")
            return bool(file_path and file_path.strip() and file_path.lower() not in ["unknown", "n/a", ""])

        findings_with_path = [item for item in findings_to_verify if has_valid_file_path(item)]
        findings_without_path = [item for item in findings_to_verify if not has_valid_file_path(item)]
        findings_to_verify = findings_with_path + findings_without_path

        if findings_with_path:
            logger.info(f"[Verification] 优先处理 {len(findings_with_path)} 个有明确文件路径的发现")
        if findings_without_path:
            logger.info(f"[Verification] 还有 {len(findings_without_path)} 个发现需要自行定位文件")

        if not findings_to_verify:
            logger.warning(
                "[Verification] 没有需要验证的发现! previous_results keys: %s",
                list(previous_results.keys()) if isinstance(previous_results, dict) else "not dict",
            )
            await self.emit_event("warning", "没有需要验证的发现 - 可能是数据格式问题")
            return AgentResult(
                success=True,
                data={
                    "findings": [],
                    "verified_count": 0,
                    "candidate_count": 0,
                    "verification_todo_summary": {
                        "total": 0,
                        "verified": 0,
                        "false_positive": 0,
                        "uncertain": 0,
                        "blocked": 0,
                        "pending": 0,
                        "blocked_reasons_top": [],
                        "per_item_compact": [],
                    },
                    "note": "未收到待验证的发现",
                },
            )

        todo_items = self._build_verification_todo_items(
            findings_to_verify=findings_to_verify,
            max_attempts_per_item=max_attempts_per_item,
            project_root=project_root,
        )
        self._trace("todo_initialized", todo_count=len(todo_items), project_root=project_root)
        await self._emit_verification_todo_update(
            todo_items,
            f"初始化验证 TODO：共 {len(todo_items)} 条候选",
            current_index=0,
            total_todos=len(todo_items),
        )
        for todo_item, candidate in zip(todo_items, findings_to_verify):
            await self._emit_unverified_finding_event(
                candidate,
                status="new",
                project_root=project_root,
                verification_todo_id=todo_item.id,
                verification_fingerprint=todo_item.fingerprint,
            )

        await self.emit_event("info", f"开始验证 {len(findings_to_verify)} 个发现")
        self.record_work(f"开始验证 {len(findings_to_verify)} 个漏洞发现")

        handoff_context = self.get_handoff_context()
        
        #  支持单个漏洞验证（方案A：队列集成）
        is_single_finding = len(findings_to_verify) == 1
        
        if is_single_finding:
            # 单个漏洞验证模式：更简洁直接的提示词
            finding = findings_to_verify[0]
            file_path = finding.get("file_path", "unknown")
            line_start = finding.get("line_start", 0)

            if isinstance(file_path, str) and ":" in file_path:
                parts = file_path.split(":", 1)
                if len(parts) == 2 and parts[1].split()[0].isdigit():
                    file_path = parts[0]
                    try:
                        line_start = int(parts[1].split()[0])
                    except ValueError:
                        pass

            initial_message = f"""请验证以下安全发现：

{handoff_context if handoff_context else ''}

## 🎯 待验证发现

**标题**: {finding.get('title', 'Unknown')}
**漏洞类型**: {finding.get('vulnerability_type', 'unknown')}
**严重度**: {finding.get('severity', 'medium')}
**文件位置**: {file_path} (第 {line_start} 行)

**代码片段**:
```
{finding.get('code_snippet', 'N/A')[:500]}
```

**发现描述**:
{finding.get('description', 'N/A')[:400]}

## 验证指南
1. **直接使用上述文件路径** - 使用精确路径: `{file_path}`
2. **先读取完整文件内容** - 使用 `get_code_window` 工具了解上下文
3. **先做反证** - 优先证明漏洞不存在，检查输入是否受控、路径是否可达、防御是否生效
4. **若反证成功则立即终止** - 直接判定为 `false_positive` 并结束该发现的继续验证
5. **若反证失败再做正向验证** - 继续分析代码逻辑并使用 `run_code` 做正向验证
6. **正向验证要结合 Mock** - 如可能，使用 Mock/Fuzzing Harness 验证真实触发条件
7. **明确区分事实/推论/结论** - 输出时显式列出 `known_facts`、`inferences_to_verify`、`final_conclusion`
8. **逐跳质问推理链** - 每个“因此/从而/所以”前后的推理都要检查是否有代码或逻辑的直接支持，缺证据就继续取证或降级结论

## 验证要求
- 验证级别: {config.get('verification_level', 'standard')}
- 必须提供明确的验证结论: `confirmed` (确认) / `likely` (可能) / `uncertain` (待复核) / `false_positive` (误报)
- 必须提供置信度 (0-1)
- 必须提供可达性分析: `reachable` / `likely_reachable` / `unknown` / `unreachable`
- Final Answer 的每个 finding 必须显式列出 `known_facts` / `inferences_to_verify` / `final_conclusion`

## 可用工具
{self.get_tools_description()}

请立即开始验证这个发现：
1. 使用 get_code_window 读取 `{file_path}` (关注第 {line_start} 行附近)
2. 优先尝试反证漏洞不存在；若反证成功，立即终止并给出 `false_positive`
3. 若反证失败，再使用其他工具 (run_code, search_code, get_symbol_body) 做正向验证和 Mock 验证
4. 给出最终验证结论
5. 输出结果时，必须把事实、推论和结论分开写；所有推理跳跃都要先检查是否有直接支持

{f'💡 参考 Analysis Agent 的分析要点。' if handoff_context else ''}"""
        else:
            # 批量验证模式：保持原有逻辑
            findings_summary = []
            for index, finding in enumerate(findings_to_verify):
                file_path = finding.get("file_path", "unknown")
                line_start = finding.get("line_start", 0)

                if isinstance(file_path, str) and ":" in file_path:
                    parts = file_path.split(":", 1)
                    if len(parts) == 2 and parts[1].split()[0].isdigit():
                        file_path = parts[0]
                        try:
                            line_start = int(parts[1].split()[0])
                        except ValueError:
                            pass

                findings_summary.append(f"""
### 发现 {index + 1}: {finding.get('title', 'Unknown')}
- 类型: {finding.get('vulnerability_type', 'unknown')}
- 严重度: {finding.get('severity', 'medium')}
- 文件: {file_path} (行 {line_start})
- 代码:
```
{finding.get('code_snippet', 'N/A')}
```
- 描述: {finding.get('description', 'N/A')}
""")

            initial_message = f"""请验证以下 {len(findings_to_verify)} 个安全发现。

{handoff_context if handoff_context else ''}

## 待验证发现
{''.join(findings_summary)}

## 重要验证指南
1. **直接使用上面列出的文件路径** - 不要猜测或搜索其他路径
2. **如果文件路径包含冒号和行号** (如 "app.py:36"), 请提取文件名 "app.py" 并使用 get_code_window 读取
3. **先读取文件内容，再优先做反证**
4. **反证成功则立即终止该发现的继续验证** - 直接判定为 `false_positive`
5. **反证失败再进入正向验证** - 结合 `run_code` 与 Mock/Fuzzing Harness 验证漏洞是否可触发
6. **不要假设文件在子目录中** - 使用发现中提供的精确路径
7. **明确区分事实/推论/结论** - 每个发现都要列出 `known_facts`、`inferences_to_verify`、`final_conclusion`
8. **逐跳检查推理链** - 对“因此/从而/所以”等连接词前后的每一步都核查是否有直接代码或逻辑支持

## 验证要求
- 验证级别: {config.get('verification_level', 'standard')}
- Final Answer 的每个 finding 必须显式列出 `known_facts` / `inferences_to_verify` / `final_conclusion`

## 可用工具
{self.get_tools_description()}

请开始验证。对于每个发现：
1. 首先使用 get_code_window 读取发现中指定的文件（使用精确路径）
2. 优先尝试反证漏洞不存在，反证成功就立即结束该发现
3. 只有在反证失败后，才继续做正向验证和 Mock 验证
4. 最后判断是否为真实漏洞
5. 输出结果时，必须把事实、推论和结论分开写；所有推理跳跃都要先检查是否有直接支持
{f'特别注意 Analysis Agent 提到的关注点。' if handoff_context else ''}"""

        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": initial_message},
        ]

        self._steps = []
        final_result = None
        current_todo_index = 0
        current_todo_id: Optional[str] = None
        run_iteration_count = 0

        await self.emit_thinking("🔐 Verification Agent 启动，LLM 开始自主验证漏洞...")
        self._trace(
            "react_loop_started",
            max_iterations=self.config.max_iterations,
            tool_whitelist=",".join(sorted(self.tools.keys())) if isinstance(self.tools, dict) else "",
            trace_log_path=self._trace_log_path,
        )

        try:
            for iteration in range(self.config.max_iterations):
                if self.is_cancelled:
                    break

                self._iteration = iteration + 1
                run_iteration_count = self._iteration
                self._trace("iteration_started", iteration=self._iteration)
                if self.is_cancelled:
                    await self.emit_thinking("🛑 任务已取消，停止执行")
                    break

                try:
                    llm_output, tokens_this_round = await self.stream_llm_call(self._conversation_history)
                except asyncio.CancelledError:
                    logger.info(f"[{self.name}] LLM call cancelled")
                    break
                except StopAsyncIteration:
                    logger.warning(f"[{self.name}] stream_llm_call side_effect exhausted, stopping iterations")
                    break

                self._total_tokens += tokens_this_round
                self._trace(
                    "llm_round_completed",
                    iteration=self._iteration,
                    tokens_this_round=tokens_this_round,
                    total_tokens=self._total_tokens,
                    output_chars=len(llm_output or ""),
                )

                if not llm_output or not llm_output.strip():
                    logger.warning(f"[{self.name}] Empty LLM response in iteration {self._iteration}")
                    await self.emit_llm_decision("收到空响应", "LLM 返回内容为空，尝试重试通过提示")
                    self._conversation_history.append(
                        {
                            "role": "user",
                            "content": "Received empty response. Please output your Thought and Action.",
                        }
                    )
                    continue

                step = self._parse_llm_response(llm_output)
                self._steps.append(step)

                if step.thought:
                    await self.emit_llm_thought(step.thought, iteration + 1)

                self._conversation_history.append({"role": "assistant", "content": llm_output})

                if step.is_final:
                    if self._tool_calls == 0:
                        logger.warning(f"[{self.name}] LLM tried to finish without any tool calls! Forcing tool usage.")
                        await self.emit_thinking("拒绝过早完成：必须先使用工具验证漏洞")
                        if findings_to_verify:
                            forced_target = findings_to_verify[0]
                            forced_probe = self._build_minimal_probe_request(forced_target)
                            if forced_probe:
                                forced_tool_name, forced_input = forced_probe
                                forced_observation = await self.execute_tool(forced_tool_name, forced_input)
                                self._conversation_history.append(
                                    {
                                        "role": "user",
                                        "content": f"Observation:\n{forced_observation}",
                                    }
                                )
                            else:
                                logger.warning(
                                    "[%s] 无可用的最小验证工具，无法自动注入强制探测步骤",
                                    self.name,
                                )
                        self._conversation_history.append(
                            {
                                "role": "user",
                                "content": (
                                    "**系统拒绝**: 你必须先使用工具验证漏洞！\n\n"
                                    "不允许在没有调用任何工具的情况下直接输出 Final Answer。\n\n"
                                    "请立即使用以下工具之一进行验证：\n"
                                    "1. `get_code_window` - 读取漏洞所在位置的极小代码窗口\n"
                                    "2. `run_code` - 编写并执行 Fuzzing Harness 验证漏洞\n"
                                    "3. `get_symbol_body` - 提取目标函数进行分析\n\n"
                                    "现在请输出 Thought 和 Action，开始验证第一个漏洞。"
                                ),
                            }
                        )
                        continue

                    await self.emit_llm_decision("完成漏洞验证", "LLM 判断验证已充分")
                    final_result = step.final_answer

                    if final_result and "findings" in final_result:
                        verified_count = len([
                            item for item in final_result["findings"]
                            if self._normalize_verification_status(item.get("status") or item.get("verdict")) == "verified"
                        ])
                        fp_count = len([
                            item for item in final_result["findings"]
                            if self._normalize_verification_status(item.get("status") or item.get("verdict")) == "false_positive"
                        ])
                        self.add_insight(
                            f"验证了 {len(final_result['findings'])} 个发现，{verified_count} 个确认，{fp_count} 个误报"
                        )
                        self.record_work(f"完成漏洞验证: {verified_count} 个确认, {fp_count} 个误报")

                    await self.emit_llm_complete("验证完成", self._total_tokens)
                    break

                if step.action:
                    await self.emit_llm_action(step.action, step.action_input or {})
                    self._trace(
                        "tool_dispatch",
                        iteration=self._iteration,
                        tool=step.action,
                        action_input=dump_json_safe(step.action_input or {}, ensure_ascii=False)[:500],
                    )
                    tool_call_key = f"{step.action}:{dump_json_safe(step.action_input or {}, sort_keys=True)}"

                    if not hasattr(self, "_tool_call_counts"):
                        self._tool_call_counts = {}
                    self._tool_call_counts[tool_call_key] = self._tool_call_counts.get(tool_call_key, 0) + 1

                    if not hasattr(self, "_tool_last_error"):
                        self._tool_last_error = {}

                    if self._tool_call_counts[tool_call_key] > 3:
                        logger.warning(f"[{self.name}] Detected repetitive tool call loop: {tool_call_key}")
                        last_error_excerpt = str(self._tool_last_error.get(tool_call_key) or "").strip()
                        if last_error_excerpt:
                            last_error_excerpt = last_error_excerpt[:600]
                        observation = (
                            f"**系统干预**: 你已经使用完全相同的参数调用了工具 '{step.action}' 超过3次。\n"
                            "请不要重复相同调用。你必须根据错误信息调整参数或更换验证路径，然后继续验证。\n"
                            "请优先执行：\n"
                            "1. 基于最近一次错误信息，修改 Action Input 后重试同一工具\n"
                            "2. 若路径/行号相关错误，先用 search_code/get_code_window 定位后再调用\n"
                            "3. 若工具不可用或超时，切换到替代工具并说明原因"
                        )
                        if last_error_excerpt:
                            observation += f"\n\n最近一次失败摘要:\n{last_error_excerpt}"
                        step.observation = observation
                        await self.emit_llm_observation(observation)
                        self._conversation_history.append({"role": "user", "content": f"Observation:\n{observation}"})
                        continue

                    if not hasattr(self, "_failed_tool_calls"):
                        self._failed_tool_calls = {}

                    observation = await self.execute_tool(step.action, step.action_input or {})
                    is_tool_error = (
                        "失败" in observation
                        or "错误" in observation
                        or "不存在" in observation
                        or "文件过大" in observation
                        or "Error" in observation
                        or "failed" in observation.lower()
                        or "timeout" in observation.lower()
                        or "超时" in observation
                    )

                    if is_tool_error:
                        self._trace(
                            "tool_result_error",
                            iteration=self._iteration,
                            tool=step.action,
                            observation_preview=self._shorten_observation(observation, max_chars=500),
                        )
                        self._tool_last_error[tool_call_key] = observation
                        self._failed_tool_calls[tool_call_key] = self._failed_tool_calls.get(tool_call_key, 0) + 1
                        fail_count = self._failed_tool_calls[tool_call_key]
                        failure_excerpt = str(observation or "").strip()[:1000]
                        observation += (
                            "\n\n🧭 **重试指导(必须遵循)**:\n"
                            f"- 当前失败工具: {step.action}\n"
                            f"- 当前失败次数: {fail_count}\n"
                            "- 下一步请直接基于上面的错误信息修改 Action Input，再次调用工具\n"
                            "- 若报错为路径/定位问题，先执行 search_code 或 get_code_window 缩小范围\n"
                            "- 若报错为权限/环境/工具不可用，改用替代工具并继续验证\n"
                            "- 禁止在未尝试参数修复前直接结束验证\n"
                            f"\n失败片段:\n{failure_excerpt}"
                        )
                        if fail_count >= 3:
                            logger.warning(f"[{self.name}] Tool call failed {fail_count} times: {tool_call_key}")
                            observation += f"\n\n**系统提示**: 此工具调用已连续失败 {fail_count} 次。请：\n"
                            observation += "1. 尝试使用不同的参数（如指定较小的行范围）\n"
                            observation += "2. 使用 search_code 工具定位关键代码片段\n"
                            observation += "3. 切换其他可用工具进行等价验证（例如 get_symbol_body/run_code/get_code_window）\n"
                            observation += "4. 继续当前漏洞验证，不要直接结束整个验证流程"
                            self._failed_tool_calls[tool_call_key] = 0
                    else:
                        self._trace(
                            "tool_result_ok",
                            iteration=self._iteration,
                            tool=step.action,
                            observation_preview=self._shorten_observation(observation, max_chars=500),
                        )
                        if tool_call_key in self._failed_tool_calls:
                            del self._failed_tool_calls[tool_call_key]
                        if tool_call_key in self._tool_last_error:
                            del self._tool_last_error[tool_call_key]

                    if self.is_cancelled:
                        logger.info(f"[{self.name}] Cancelled after tool execution")
                        break

                    step.observation = observation
                    await self.emit_llm_observation(observation)
                    self._conversation_history.append({"role": "user", "content": f"Observation:\n{observation}"})
                else:
                    await self.emit_llm_decision("继续验证", "LLM 需要更多验证")
                    self._conversation_history.append(
                        {
                            "role": "user",
                            "content": "请继续验证。你输出了 Thought 但没有输出 Action。请**立即**选择一个工具执行，或者如果验证完成，输出 Final Answer 汇总所有验证结果。",
                        }
                    )

            duration_ms = int((time.time() - start_time) * 1000)

            if self.is_cancelled:
                todo_summary = self._build_verification_todo_summary(todo_items)
                completed_count = (
                    todo_summary.get("verified", 0)
                    + todo_summary.get("false_positive", 0)
                    + todo_summary.get("uncertain", 0)
                    + todo_summary.get("blocked", 0)
                )
                pending_count = todo_summary.get("pending", 0)
                cancel_message = (
                    f"Verification Agent 已取消: 本次迭代 {run_iteration_count}，"
                    f"当前漏洞 {current_todo_index}/{len(todo_items)}，"
                    f"已完成 {completed_count}，待处理 {pending_count}"
                )
                await self.emit_event(
                    "info",
                    cancel_message,
                    metadata={
                        "run_iteration_count": run_iteration_count,
                        "current_todo_id": current_todo_id,
                        "current_todo_index": current_todo_index,
                        "total_todos": len(todo_items),
                        "verified_count": todo_summary.get("verified", 0),
                        "pending_count": pending_count,
                        "todo_scope": "verification",
                        "verification_todo_summary": todo_summary,
                    },
                )
                return AgentResult(
                    success=False,
                    error="任务已取消",
                    data={
                        "findings": findings_to_verify,
                        "candidate_count": len(findings_to_verify),
                        "verification_todo_summary": todo_summary,
                    },
                    iterations=run_iteration_count,
                    tool_calls=self._tool_calls,
                    tokens_used=self._total_tokens,
                    duration_ms=duration_ms,
                )

            verified_findings = []
            llm_findings = []
            if final_result and "findings" in final_result:
                llm_findings = final_result["findings"]

            if not llm_findings and findings_to_verify:
                logger.warning(
                    f"[{self.name}] LLM returned empty findings despite {len(findings_to_verify)} inputs. Falling back to originals."
                )
                final_result = None

            if final_result and "findings" in final_result:
                verdicts_debug = [
                    (
                        item.get("file_path", "?"),
                        (item.get("verification_result") or {}).get("verdict") or item.get("verdict"),
                        (item.get("verification_result") or {}).get("confidence") or item.get("confidence")
                    )
                    for item in final_result["findings"]
                ]
                logger.info(f"[{self.name}] LLM returned verdicts: {verdicts_debug}")

                def _coerce_confidence(value: Any) -> float:
                    try:
                        return max(0.0, min(float(value), 1.0))
                    except Exception:
                        return CONFIDENCE_DEFAULT_FALLBACK

                def _default_reachability(status_value: str) -> str:
                    if status_value == "verified":
                        return "reachable"
                    if status_value == "likely":
                        return "likely_reachable"
                    if status_value == "false_positive":
                        return "unreachable"
                    return "unknown"

                used_fallback_indexes: set[int] = set()
                for finding_index, finding in enumerate(final_result["findings"]):
                    fallback_finding = self._select_fallback_finding(
                        finding,
                        findings_to_verify,
                        used_fallback_indexes,
                        preferred_index=finding_index,
                    )
                    # === 适配新的verification_result嵌套结构 ===
                    # 优先从verification_result中获取，向后兼容finding层级
                    verification_result = finding.get("verification_result", {})
                    if not isinstance(verification_result, dict):
                        verification_result = {}
                    
                    status_value = self._normalize_verification_status(
                        verification_result.get("status") or finding.get("status")
                    )
                    verdict = verification_result.get("verdict") or finding.get("verdict")
                    if isinstance(verdict, str):
                        verdict = verdict.strip().lower()
                    confidence = verification_result.get("confidence") or finding.get("confidence")
                    reachability = verification_result.get("reachability") or finding.get("reachability")
                    verification_evidence = verification_result.get("verification_evidence") or finding.get("verification_evidence")

                    if not status_value:
                        if verdict == "confirmed":
                            status_value = "verified"
                        elif verdict in {"likely", "uncertain"}:
                            status_value = "likely"
                        elif verdict == "false_positive":
                            status_value = "false_positive"
                        elif finding.get("is_verified") is True:
                            status_value = "verified"
                        else:
                            if confidence is None:
                                status_value = "likely"
                                logger.debug(
                                    f"[{self.name}] confidence缺失，status设为likely: {finding.get('file_path', '?')}"
                                )
                            else:
                                try:
                                    confidence_val = float(confidence)
                                except Exception:
                                    confidence_val = CONFIDENCE_DEFAULT_FALLBACK

                                if confidence_val >= CONFIDENCE_THRESHOLD_FALSE_POSITIVE and confidence_val <= 1.0:
                                    status_value = "likely"
                                elif confidence_val <= CONFIDENCE_THRESHOLD_FALSE_POSITIVE:
                                    status_value = "false_positive"
                                else:
                                    status_value = "likely"

                        logger.warning(
                            f"[{self.name}] Missing/invalid status for {finding.get('file_path', '?')}, inferred as: {status_value}"
                        )

                    if not verdict or verdict not in ["confirmed", "likely", "uncertain", "false_positive"]:
                        verdict = self._status_to_verdict(status_value)
                    elif status_value == "likely" and verdict == "uncertain":
                        verdict = "likely"
                    elif status_value == "verified" and verdict == "likely":
                        verdict = "confirmed"

                    confidence_value = _coerce_confidence(confidence)
                    if not reachability:
                        reachability = _default_reachability(status_value)
                    if not verification_evidence:
                        verification_evidence = (
                            f"verifier={self.name}; mode=llm_or_fallback; "
                            f"status={status_value}; confidence={confidence_value:.2f}; "
                            f"file={finding.get('file_path') or 'unknown'}"
                        )

                    verified = {
                        **finding,
                        "status": status_value,
                        "verdict": verdict,
                        "confidence": confidence_value,
                        "reachability": reachability,
                        "verification_result": {
                            **(verification_result or {}),
                            "status": status_value,
                            "verdict": verdict,
                            "confidence": confidence_value,
                            "reachability": reachability,
                            "verification_evidence": verification_evidence,
                        },
                        "is_verified": status_value in {"verified", "likely"},
                        "verified_at": (
                            datetime.now(timezone.utc).isoformat()
                            if status_value in {"verified", "likely"}
                            else None
                        ),
                    }
                    verified = self._apply_source_sink_authenticity_gate(
                        verified,
                        fallback=fallback_finding,
                    )

                    if not verified.get("recommendation"):
                        verified["recommendation"] = self._get_recommendation(finding.get("vulnerability_type", ""))
                    if task_id:
                        ensure_finding_identity(task_id, verified)

                    verified_findings.append(verified)
            else:
                for finding in findings_to_verify:
                    fallback_confidence = CONFIDENCE_DEFAULT_FALLBACK
                    fallback_verified = {
                        **finding,
                        "status": "likely",
                        "verdict": "likely",
                        "confidence": fallback_confidence,
                        "reachability": "likely_reachable",
                        "verification_result": {
                            "status": "likely",
                            "verdict": "likely",
                            "confidence": fallback_confidence,
                            "reachability": "likely_reachable",
                            "verification_evidence": (
                                f"verifier={self.name}; mode=fallback_branch_auto_generated; "
                                f"reason=missing_llm_output; file={finding.get('file_path') or 'unknown'}"
                            ),
                        },
                        "is_verified": True,
                    }
                    fallback_verified = self._apply_source_sink_authenticity_gate(
                        fallback_verified,
                        fallback=finding,
                    )
                    if task_id:
                        ensure_finding_identity(task_id, fallback_verified)
                    verified_findings.append(fallback_verified)

            for idx, todo_item in enumerate(todo_items):
                current_todo_index = idx + 1
                current_todo_id = todo_item.id
                if idx >= len(verified_findings):
                    todo_item.status = "blocked"
                    todo_item.final_verdict = "uncertain"
                    todo_item.blocked_reason = "missing_verification_output"
                    continue
                finding_status = self._normalize_verification_status(
                    verified_findings[idx].get("status")
                    or (verified_findings[idx].get("verification_result") or {}).get("status")
                    or verified_findings[idx].get("verdict")
                )
                if finding_status == "verified":
                    todo_item.status = "verified"
                    todo_item.final_verdict = "confirmed"
                elif finding_status == "likely":
                    todo_item.status = "verified"
                    todo_item.final_verdict = "likely"
                elif finding_status == "false_positive":
                    todo_item.status = "false_positive"
                    todo_item.final_verdict = "false_positive"
                else:
                    todo_item.status = "uncertain"
                    todo_item.final_verdict = "uncertain"
                meta_title = str(verified_findings[idx].get("title") or todo_item.title)
                meta_vuln = str(verified_findings[idx].get("vulnerability_type") or "unknown")
                meta_sev = str(verified_findings[idx].get("severity") or "medium")
                meta_file = str(verified_findings[idx].get("file_path") or todo_item.file_path)
                raw_meta_line_start = verified_findings[idx].get("line_start") or todo_item.line_start
                raw_meta_line_end = verified_findings[idx].get("line_end")
                meta_line_start = int(raw_meta_line_start) if raw_meta_line_start is not None else None
                meta_line_end = (
                    int(raw_meta_line_end)
                    if raw_meta_line_end is not None
                    else meta_line_start
                )
                verification_payload = verified_findings[idx].get("verification_result")
                if not isinstance(verification_payload, dict):
                    verification_payload = {}
                meta_status = self._normalize_verification_status(
                    verification_payload.get("status")
                    or verified_findings[idx].get("status")
                    or todo_item.status
                ) or todo_item.status
                meta_authenticity = self._status_to_verdict(meta_status)
                meta_evidence = str(
                    verification_payload.get("verification_evidence")
                    or verified_findings[idx].get("verification_evidence")
                    or verified_findings[idx].get("description")
                    or ""
                ).strip()
                meta_description = str(verified_findings[idx].get("description") or "").strip() or None
                meta_description_markdown = str(
                    verified_findings[idx].get("description_markdown") or ""
                ).strip() or None
                meta_code_snippet = (
                    str(verified_findings[idx].get("code_snippet") or "").strip() or None
                )
                if todo_item.status == "verified":
                    await self.emit_event(
                        "finding_verified",
                        f"[Verification] 已确认漏洞: {meta_title}",
                        metadata={
                            "title": meta_title,
                            "display_title": meta_title,
                            "severity": meta_sev,
                            "vulnerability_type": meta_vuln,
                            "file_path": meta_file,
                            "line_start": meta_line_start,
                            "line_end": meta_line_end,
                            "is_verified": meta_status == "verified",
                            "finding_scope": "verification_queue",
                            "verification_todo_id": todo_item.id,
                            "verification_fingerprint": todo_item.fingerprint,
                            "verification_status": "verified",
                            "status": meta_status or "verified",
                            "authenticity": meta_authenticity,
                            "verification_evidence": meta_evidence,
                            "description": meta_description,
                            "description_markdown": meta_description_markdown,
                            "code_snippet": meta_code_snippet,
                        },
                    )
                elif todo_item.status == "false_positive":
                    await self.emit_event(
                        "finding_update",
                        f"[Verification] 标记误报: {meta_title}",
                        metadata={
                            "title": meta_title,
                            "display_title": meta_title,
                            "severity": meta_sev,
                            "vulnerability_type": meta_vuln,
                            "file_path": meta_file,
                            "line_start": meta_line_start,
                            "line_end": meta_line_end,
                            "is_verified": False,
                            "finding_scope": "verification_queue",
                            "verification_todo_id": todo_item.id,
                            "verification_fingerprint": todo_item.fingerprint,
                            "verification_status": "false_positive",
                            "status": "false_positive",
                            "authenticity": meta_authenticity,
                            "verification_evidence": meta_evidence,
                            "description": meta_description,
                            "description_markdown": meta_description_markdown,
                            "code_snippet": meta_code_snippet,
                        },
                    )
                else:
                    uncertain_status = "blocked" if todo_item.status == "blocked" else "uncertain"
                    await self.emit_event(
                        "finding_update",
                        f"[Verification] 待复核: {meta_title}",
                        metadata={
                            "title": meta_title,
                            "display_title": meta_title,
                            "severity": meta_sev,
                            "vulnerability_type": meta_vuln,
                            "file_path": meta_file,
                            "line_start": meta_line_start,
                            "line_end": meta_line_end,
                            "is_verified": False,
                            "finding_scope": "verification_queue",
                            "verification_todo_id": todo_item.id,
                            "verification_fingerprint": todo_item.fingerprint,
                            "verification_status": uncertain_status,
                            "status": uncertain_status,
                            "authenticity": "uncertain",
                            "verification_evidence": meta_evidence,
                            "description": meta_description,
                            "description_markdown": meta_description_markdown,
                            "code_snippet": meta_code_snippet,
                        },
                    )

            status_values = [
                self._normalize_verification_status(
                    item.get("status")
                    or (item.get("verification_result") or {}).get("status")
                    or item.get("verdict")
                )
                for item in verified_findings
            ]
            verified_count = len([s for s in status_values if s == "verified"])
            likely_count = len([s for s in status_values if s == "likely"])
            uncertain_count = len([s for s in status_values if s == "uncertain"])
            false_positive_count = len([s for s in status_values if s == "false_positive"])
            confirmed_count = len(
                [
                    item
                    for item in verified_findings
                    if str(item.get("verdict") or "").strip().lower() == "confirmed"
                ]
            )
            self._trace(
                "run_completed",
                findings=len(verified_findings),
                confirmed=confirmed_count,
                likely=likely_count,
                uncertain=uncertain_count,
                false_positive=false_positive_count,
                duration_ms=duration_ms,
                tool_calls=self._tool_calls,
                iterations=self._iteration,
            )
            todo_summary = self._build_verification_todo_summary(todo_items)
            await self._emit_verification_todo_update(
                todo_items,
                "逐漏洞验证完成",
                current_index=len(todo_items),
                total_todos=len(todo_items),
            )

            await self.emit_event(
                "info",
                f"Verification Agent 完成: {confirmed_count} 已确认, {likely_count} 高概率, {false_positive_count} 误报",
            )

            logger.info(f"[{self.name}] Returning {len(verified_findings)} verified findings")

            #  验证结果持久化：通过工具将 findings 保存到数据库
            # LLM 处理层已在验证过程中逐个调用 save_verification_result；
            # 这里作为监控点，记录验证结果统计。
            rescue_save_result: Optional[Dict[str, Any]] = None
            if "save_verification_result" in self.tools and verified_findings:
                logger.info(
                    "[%s] save_verification_result 工具可用，验证过程中应已逐个保存 %d 条结果 "
                    "(confirmed=%d, likely=%d, false_positive=%d)",
                    self.name,
                    len(verified_findings),
                    confirmed_count,
                    likely_count,
                    false_positive_count,
                )
                if not self._has_successful_save_verification_call():
                    logger.warning(
                        "[%s] Verification 已结束但未检测到 save_verification_result 成功调用，启动确定性补救保存",
                        self.name,
                    )
                    rescue_save_result = await self._rescue_save_missing_verification_results(
                        verified_findings=verified_findings,
                        task_id=task_id,
                    )
                    await self.emit_event(
                        "warning" if rescue_save_result.get("saved_count", 0) > 0 else "error",
                        (
                            "Verification 终止前未调用 save_verification_result，"
                            f"已自动补救保存 {rescue_save_result.get('saved_count', 0)}/"
                            f"{rescue_save_result.get('attempted_count', 0)} 条"
                        ),
                        metadata=rescue_save_result,
                    )
            
            #  兜底机制：检查是否遗漏了 save_verification_result 调用
            fallback_result = await self._fallback_check_and_save(
                conversation_history=self._conversation_history,
                expected_tool="save_verification_result",
                agent_type="verification",
            )
            
            if fallback_result:
                logger.warning(
                    f"[{self.name}] 兜底机制执行完成: 补救保存了 "
                    f"{fallback_result.get('saved_count', 0)} 个验证结果"
                )
                await self.emit_event(
                    "warning",
                    f"兜底机制触发：自动补救保存了 {fallback_result.get('saved_count', 0)} 个验证结果",
                    metadata=fallback_result,
                )

            handoff = self._create_verification_handoff(
                verified_findings,
                confirmed_count,
                likely_count,
                false_positive_count,
            )

            return AgentResult(
                success=True,
                data={
                    "findings": verified_findings,
                    "verified_count": confirmed_count,
                    "likely_count": likely_count,
                    "uncertain_count": uncertain_count,
                    "false_positive_count": false_positive_count,
                    "candidate_count": len(findings_to_verify),
                    "verification_todo_summary": todo_summary,
                    "rescue_save_result": rescue_save_result,
                },
                iterations=self._iteration,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
                handoff=handoff,
            )

        except Exception as e:
            self._trace("run_failed", error=str(e))
            logger.error(f"Verification Agent failed: {e}", exc_info=True)
            return AgentResult(success=False, error=str(e))

    def _has_successful_save_verification_call(self) -> bool:
        """检查当前 run 是否成功调用过 save_verification_result。"""
        for item in getattr(self, "_critical_tool_calls", []):
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name") or "").strip().lower()
            if tool_name != "save_verification_result":
                continue
            if bool(item.get("success")):
                return True
        return False

    @staticmethod
    def _is_save_verification_observation_success(observation: Any) -> bool:
        text = str(observation or "").strip()
        if not text:
            return False
        lowered = text.lower()
        if "error:" in lowered or "持久化失败" in text or "工具执行失败" in text:
            return False
        if re.search(r"""['"]saved['"]\s*:\s*(true|True|1)""", text):
            return True
        if "验证结果已保存" in text or "累计" in text and "条" in text:
            return True
        return False

    def _build_save_verification_params(
        self,
        finding: Dict[str, Any],
    ) -> Dict[str, Any]:
        finding = self._apply_source_sink_authenticity_gate(
            dict(finding or {}),
            fallback=finding if isinstance(finding, dict) else None,
        )
        verification_payload = finding.get("verification_result")
        if not isinstance(verification_payload, dict):
            verification_payload = {}

        raw_line_start = finding.get("line_start") or 1
        try:
            line_start = max(1, int(raw_line_start))
        except Exception:
            line_start = 1

        raw_line_end = finding.get("line_end")
        try:
            line_end = int(raw_line_end) if raw_line_end is not None else line_start
        except Exception:
            line_end = line_start
        line_end = max(line_start, line_end)

        function_name = str(finding.get("function_name") or "").strip()
        if not function_name:
            function_name = f"<function_at_line_{line_start}>"

        normalized_status = self._normalize_verification_status(
            verification_payload.get("status")
            or finding.get("status")
        )

        verdict = str(
            verification_payload.get("verdict")
            or finding.get("verdict")
            or finding.get("authenticity")
            or ""
        ).strip().lower()
        if verdict not in {"confirmed", "likely", "uncertain", "false_positive"}:
            verdict = ""

        if not normalized_status:
            normalized_status = self._normalize_verification_status(verdict) or "likely"
        if not verdict:
            verdict = self._status_to_verdict(normalized_status)

        raw_confidence = verification_payload.get("confidence", finding.get("confidence", 0.5))
        try:
            confidence = max(0.0, min(float(raw_confidence), 1.0))
        except Exception:
            confidence = CONFIDENCE_DEFAULT_FALLBACK

        reachability = str(
            verification_payload.get("reachability")
            or finding.get("reachability")
            or ""
        ).strip().lower()
        if reachability not in {"reachable", "likely_reachable", "unknown", "unreachable"}:
            if normalized_status == "verified":
                reachability = "reachable"
            elif normalized_status == "likely":
                reachability = "likely_reachable"
            elif normalized_status == "false_positive":
                reachability = "unreachable"
            else:
                reachability = "unknown"

        verification_evidence = str(
            verification_payload.get("verification_evidence")
            or finding.get("verification_evidence")
            or finding.get("description")
            or ""
        ).strip()
        if len(verification_evidence) < 10:
            verification_evidence = (
                f"auto_rescue_save_evidence: status={normalized_status}; "
                f"confidence={confidence:.2f}; file={finding.get('file_path') or 'unknown'}"
            )

        return {
            "finding_identity": finding.get("finding_identity"),
            "file_path": finding.get("file_path") or "unknown",
            "line_start": line_start,
            "line_end": line_end,
            "function_name": function_name,
            "title": finding.get("title") or f"Verification finding at line {line_start}",
            "vulnerability_type": finding.get("vulnerability_type") or "unknown",
            "severity": str(finding.get("severity") or "medium").strip().lower(),
            "description": finding.get("description"),
            "source": finding.get("source"),
            "sink": finding.get("sink"),
            "dataflow_path": finding.get("dataflow_path"),
            "status": normalized_status,
            "is_verified": normalized_status in {"verified", "likely"},
            "poc_code": finding.get("poc_code"),
            "cvss_score": finding.get("cvss_score"),
            "cvss_vector": finding.get("cvss_vector"),
            "code_snippet": finding.get("code_snippet"),
            "code_context": finding.get("code_context"),
            "report": finding.get("report") or finding.get("vulnerability_report"),
            "verdict": verdict,
            "confidence": confidence,
            "reachability": reachability,
            "verification_evidence": verification_evidence,
            "cwe_id": finding.get("cwe_id"),
            "suggestion": finding.get("suggestion"),
        }

    async def _rescue_save_missing_verification_results(
        self,
        verified_findings: List[Dict[str, Any]],
        task_id: str,
    ) -> Dict[str, Any]:
        """
        当 Verification 提前结束且未调用 save_verification_result 时，进行确定性补救保存。
        """
        attempted_count = 0
        saved_count = 0
        failed_count = 0
        seen_keys: set[str] = set()

        for finding in verified_findings:
            if not isinstance(finding, dict):
                continue

            finding_payload = dict(finding)
            if task_id:
                ensure_finding_identity(task_id, finding_payload)

            dedup_key = str(finding_payload.get("finding_identity") or "").strip()
            if not dedup_key:
                dedup_key = (
                    f"{finding_payload.get('file_path', '')}:"
                    f"{finding_payload.get('line_start', '')}:"
                    f"{finding_payload.get('vulnerability_type', '')}:"
                    f"{finding_payload.get('title', '')}"
                )
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            params = self._build_save_verification_params(finding_payload)
            attempted_count += 1

            try:
                observation = await self.execute_tool("save_verification_result", params)
            except Exception as exc:
                failed_count += 1
                logger.error(
                    "[%s] 补救保存失败（exception）: %s",
                    self.name,
                    exc,
                )
                continue

            if self._is_save_verification_observation_success(observation):
                saved_count += 1
            else:
                failed_count += 1
                logger.warning(
                    "[%s] 补救保存未确认成功: %s",
                    self.name,
                    str(observation or "")[:200],
                )

        return {
            "fallback_executed": True,
            "tool": "save_verification_result",
            "reason": "verification_ended_without_save_verification_result",
            "attempted_count": attempted_count,
            "saved_count": saved_count,
            "failed_count": failed_count,
        }
    
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
        candidate_count: Optional[int] = None,
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
        # 按状态分类（status-first）
        def _finding_status(item: Dict[str, Any]) -> str:
            vr = item.get("verification_result")
            vr_status = vr.get("status") if isinstance(vr, dict) else None
            return self._normalize_verification_status(
                item.get("status") or vr_status or item.get("verdict")
            )

        verified = [f for f in verified_findings if _finding_status(f) == "verified"]
        likely = [f for f in verified_findings if _finding_status(f) == "likely"]
        uncertain = [f for f in verified_findings if _finding_status(f) == "uncertain"]
        false_positives = [f for f in verified_findings if _finding_status(f) == "false_positive"]

        actionable_findings = verified + likely

        # 提取关键发现（已确认/高概率的高危漏洞）
        key_findings = []
        for f in actionable_findings:
            if f.get("severity") in ["critical", "high"]:
                key_findings.append(f)
        if len(key_findings) < 10:
            for f in actionable_findings:
                if f not in key_findings:
                    key_findings.append(f)
                    if len(key_findings) >= 10:
                        break

        # 构建建议行动 - 修复建议
        suggested_actions = []
        for f in actionable_findings[:10]:
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
            f"验证完成: {confirmed_count}个已确认, {likely_count}个高概率, {false_positive_count}个误报",
            (
                f"有效命中率: {(confirmed_count + likely_count) / len(verified_findings) * 100:.1f}%"
                if verified_findings
                else "无数据"
            ),
        ]

        # 统计各类型漏洞
        type_counts = {}
        for f in actionable_findings:
            vtype = f.get("vulnerability_type", "unknown")
            type_counts[vtype] = type_counts.get(vtype, 0) + 1
        if type_counts:
            top_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:3]
            insights.append(f"主要漏洞类型: {', '.join([f'{t}({c})' for t, c in top_types])}")

        # 需要关注的文件（有已确认/高概率漏洞的文件）
        attention_points = []
        files_with_confirmed = {}
        for f in actionable_findings:
            fp = f.get("file_path", "")
            if fp:
                files_with_confirmed[fp] = files_with_confirmed.get(fp, 0) + 1
        for fp, count in sorted(files_with_confirmed.items(), key=lambda x: x[1], reverse=True)[:10]:
            attention_points.append(f"{fp} ({count}个已确认/高概率漏洞)")

        # 优先修复的区域
        priority_areas = []
        for f in actionable_findings:
            if f.get("severity") in ["critical", "high"]:
                fp = f.get("file_path", "")
                if fp and fp not in priority_areas:
                    priority_areas.append(fp)

        # 上下文数据
        context_data = {
            "confirmed_count": confirmed_count,
            "likely_count": likely_count,
            "false_positive_count": false_positive_count,
            "uncertain_count": len(uncertain),
            "candidate_count": int(candidate_count or len(verified_findings)),
            "verified_output_count": len(verified_findings),
            "vulnerability_types": type_counts,
            "files_with_confirmed": files_with_confirmed,
            "poc_generated": len([f for f in verified_findings if f.get("poc_code")]),
        }

        # 构建摘要
        summary = f"验证完成: {confirmed_count}个已确认漏洞, {likely_count}个高概率漏洞"
        if confirmed_count > 0:
            high_count = len([f for f in verified if f.get("severity") in ["critical", "high"]])
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
