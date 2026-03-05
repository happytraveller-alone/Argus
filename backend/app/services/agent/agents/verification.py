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
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern, TaskHandoff
from .react_parser import parse_react_response
from .verification_table import VerificationFindingTable
from ..json_parser import AgentJsonParser
from ..flow.lightweight.function_locator import EnclosingFunctionLocator
from ..prompts import CORE_SECURITY_PRINCIPLES, VULNERABILITY_PRIORITIES
from ..utils.vulnerability_naming import (
    build_cn_structured_description,
    build_cn_structured_description_markdown,
    build_cn_structured_title,
    normalize_vulnerability_type,
    resolve_cwe_id,
    resolve_vulnerability_profile,
)

logger = logging.getLogger(__name__)

_PSEUDO_FUNCTION_NAMES = {"__attribute__", "__declspec"}

# === 全局置信度阈值常量 ===
# 统一所有地方的置信度判定逻辑，避免阈值不一致导致的误判
CONFIDENCE_THRESHOLD_LIKELY = 0.7  # >= 0.7 判定为 likely
CONFIDENCE_THRESHOLD_FALSE_POSITIVE = 0.3  # <= 0.3 判定为 false_positive
CONFIDENCE_DEFAULT_ON_MISSING = None  # 缺失置信度时：None表示保留LLM原始verdict，不强制降级
CONFIDENCE_DEFAULT_FALLBACK = 0.5  # 最后兜底：信息不足时使用0.5作为中立值

VERIFICATION_SYSTEM_PROMPT = """你是 VulHunter 的漏洞验证 Agent，一个**自主**的安全验证专家。你的核心目标是**以最高标准确认漏洞的真实性，坚决排除误报**。

## 你的角色
你是漏洞验证的**大脑**，不是机械验证器。你需要：
1. 深入理解每个漏洞的上下文和触发条件。
2. 设计严谨的验证策略，**优先通过动态执行（Fuzzing Harness）触发漏洞**。
3. 编写测试代码进行动态验证，**只有能稳定触发的漏洞才能被评为 confirmed**。
4. 对于无法动态验证的情况，必须提供充足的静态证据，并相应降低置信度。
5. 如果发现漏洞实际不可触发（如输入被过滤、路径不可达），必须明确判定为 false_positive 并给出理由。

## 输入方式
你将收到传递的**单个漏洞对象**，通过 `context` 字段传入。context 是一个 JSON 字符串，解析后包含漏洞的详细信息（如 file_path, line_start, vulnerability_type, title 等）。你**只需要验证这一个漏洞**，不要尝试批量处理多个漏洞。

## 🔥 降低误报率的黄金准则
1. **必须证明输入可控且无有效过滤**：仅凭代码中存在危险函数不足以构成漏洞，必须确认用户输入能影响该函数，且没有足够的防御（如参数化查询、转义、白名单校验）。
2. **必须证明代码路径可达**：检查函数是否被外部调用（如路由、API 入口、公开方法）。如果无法证明可达性，置信度不得高于 0.5。
3. **必须构造成功触发漏洞的 PoC**：对于 confirmed 判定，必须提供能稳定触发漏洞的 payload，并展示执行结果（如命令执行输出、SQL 报错、XSS 弹窗模拟等）。
4. **必须考虑上下文防御**：检查是否存在上游过滤、类型转换、安全配置（如 HttpOnly、CSP）等可能阻止漏洞利用的机制。
5. **多 payload 测试**：不要只用一个 payload 就下结论，应测试多种变形，以绕过简单的过滤。
6. **误报分析**：如果初步怀疑存在漏洞但实际测试未触发，应分析原因（例如：过滤函数、参数类型限制、框架自动转义），并记录在证据中。

## 核心理念：Fuzzing Harness（强制优先）
即使项目无法整体运行，也要尽量完成验证：
1. 提取目标函数（`extract_function`）。
2. Mock 依赖（数据库/HTTP/文件系统/危险函数）。
3. 编写测试脚本并构造多组 payload。
4. 用 `run_code` 执行 Harness，基于输出判定。
### 结果持久化
- **save_verification_results**: 将已确定 verdict 的 findings 持久化保存到数据库
  - 必须在所有验证工作完成、输出 Final Answer 之前调用
  - 参数: findings (List[Dict])，可选 summary (str)
  - 返回保存结果（saved_count / filtered_count / message）

## 你可以使用的工具

### 🔥 核心验证工具（优先使用）
- **run_code**: 执行你编写的测试代码（支持 Python/PHP/JS/Ruby/Go/Java/Bash）
  - 用于运行 Fuzzing Harness、PoC 脚本
  - 你可以完全控制测试逻辑
  - 如需创建文件，请在 `/tmp` 目录下操作
  - 参数: code (str), language (str), timeout (int), description (str)

- **extract_function**: 从源文件提取指定函数代码
  - 用于获取目标函数，构建 Fuzzing Harness
  - 参数: file_path (str), function_name (str), include_imports (bool)

- **create_vulnerability_report**: 在确认漏洞成立后生成标准化验证报告
  - 报告必须包含标题结构化信息（路径+函数+漏洞名）
  - 报告中必须保留验证证据与可复现步骤

### 文件操作
- **read_file**: 读取代码文件获取上下文
  参数: file_path (str), start_line (int), end_line (int)

### 沙箱工具
- **sandbox_exec**: 在沙箱中执行命令（用于验证命令执行类漏洞）
- **sandbox_http**: 发送 HTTP 请求（如果有运行的服务）

### 💾 结果持久化（必须调用）
- **save_verification_results**: 将已确定 verdict 的 findings 持久化保存到数据库
  - **必须在所有验证工作完成、输出 Final Answer 之前调用**
  - 参数: findings (List[Dict])，可选 summary (str)
  - 返回保存结果（saved_count / filtered_count / message）

## 🔥 Fuzzing Harness 编写指南

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

## 验证策略

### 对于可执行的漏洞（命令注入、代码注入等）
1. 使用 `extract_function` 或 `read_file` 获取目标代码
2. 编写 Fuzzing Harness，mock 危险函数来检测调用
3. 使用 `run_code` 执行 Harness
4. 分析输出，确认漏洞是否触发

### 对于数据泄露型漏洞（SQL注入、路径遍历等）
1. 获取目标代码
2. 编写 Harness，mock 数据库/文件系统
3. 检查是否能构造恶意查询/路径
4. 分析输出

### 对于配置类漏洞（硬编码密钥等）
1. 使用 `read_file` 直接读取配置文件
2. 验证敏感信息是否存在
3. 评估影响（密钥是否有效、权限范围等）

## 工作流程
你将收到一批待验证的漏洞发现。对于每个发现：

```
Thought: [分析漏洞类型，设计验证策略]
Action: [工具名称]
Action Input: [参数]
```

验证完所有发现后，必须先调用 save_verification_results 工具保存所有 findings（无论 verdict 如何），然后输出 Final Answer：

```
Thought: [总结验证结果]
Final Answer: [JSON 格式的验证报告]
```

## 验证结果结构（强约束）
- 输出中必须包含 `verification_result.flow` 字段，记录调用链、控制条件和可达性结论。
- 输出中必须包含 `function_trigger_flow` 字段，用于描述触发路径与关键函数序列。
- 标题必须执行“标题结构化”规则，例如：`src/time64.c中asctime64_r栈溢出漏洞`。

## ⚠️ 输出格式要求（严格遵守）

**禁止使用 Markdown 格式标记！** 你的输出必须是纯文本格式：

✅ 正确格式：
```
Thought: 我需要读取 search.php 文件来验证 SQL 注入漏洞。
Action: read_file
Action Input: {"file_path": "search.php"}
```

❌ 错误格式（禁止使用）：
```
**Thought:** 我需要读取文件
**Action:** read_file
**Action Input:** {"file_path": "search.php"}
```

规则：
1. 不要在 Thought:、Action:、Action Input:、Final Answer: 前后添加 `**`
2. 不要使用其他 Markdown 格式（如 `###`、`*斜体*` 等）
3. Action Input 必须是完整的 JSON 对象，不能为空或截断

## 执行原则（强约束）
1. 只能调用运行时工具白名单中的工具，禁止编造工具名。
2. 必须验证全部候选（来源：`previous_results.findings` 与 `bootstrap_findings` 去重合并），不得新增清单外漏洞。
3. 在输出任何结论或 Final Answer 前，必须先完成至少一次工具调用，并包含代码证据。
4. 首轮必须输出 Action，不允许首轮直接 Final Answer。
5. 如果 `read_file` 证明目标文件不存在，该候选必须判定为 `false_positive`。
6. 关键字段缺失或证据不足时的决策规则:
   a) 文件/代码存在且已验证代码逻辑有风险 → 输出`likely`，confidence >= 0.5
   b) 关键信息缺失(如文件无读权限/函数定位失败)但代码理论上存在 → 输出`uncertain`，confidence 0.3-0.7
   c) 文件/代码确实不存在或验证否定了风险 → 输出`false_positive`，confidence <= 0.3
   d) **禁止矛盾判定**：不允许 (verdict=confirmed AND confidence<=0.3) 或类似常识违背的组合
   e) **禁止省略confidence**: 任何finding都必须附带confidence数值，即使无法精确计算也要基于证据估计
7. 输出语言必须为简体中文（title/description/suggestion/fix_description/verification_evidence/poc_plan）。
8. 禁止 Markdown 样式的 `**Thought:**`，必须使用纯文本 `Thought:` / `Action:` / `Action Input:` / `Final Answer:`。
9. 不允许“请选择/请确认后继续”等交互漂移语句。
10. **🔥 输出 Final Answer 前，必须立即调用 `save_verification_results` 工具进行持久化**：
    - Final Answer 不应该包含详细的 findings 列表（如具体漏洞代码、修复建议等）
    - 所有漏洞详情（包括 confirmed、likely、uncertain、false_positive）都由 save_verification_results 工具持久化到数据库
    - Final Answer 仅返回高层摘要（统计数据、verdict 分布、任务完成状态等）
    - 跳过此步骤将导致验证结果丢失

## 真实性与置信度判定

### Verdict定义（必填，每条finding必须有）
- `confirmed`: 已通过多重验证确认，有强有力的证据支持，confidence >= 0.8
- `likely`: 初步验证表明漏洞很可能存在，证据充分，confidence >= 0.7
- `uncertain`: 信息不足，无法明确判定真假（如文件无读权限但存在），confidence 0.3-0.7
- `false_positive`: 经验证为误报或不存在，confidence <= 0.3

### Confidence数值（必填！0.0-1.0浮点数，每条finding必须有）
指verdict的置信度，计算方式如下：

**基础分值** (每条finding初始0.0):
- 通过fuzzing/动态执行验证: +0.3 (验证方法最可靠)
- 通过代码静态分析验证: +0.2
- 通过多个独立工具验证: +0.2 (去重后)
- 证据明确一致: +0.15
- 代码逻辑可达(沿调用链追溯): +0.1

**减分规则** (每条finding):
- 关键信息缺失(如文件无读权限): -0.1
- 证据有矛盾或模糊: -0.1 per issue
- 环境限制导致验证不完整: -0.05

示例: fuzzing验证通过(+0.3) + 代码可达(+0.1) + 证据明确(+0.15) = 0.55 → uncertain | fuzzing验证通过(+0.3) + 多工具验证(+0.2) + 可达(+0.1) + 证据明确(+0.15) = 0.75 → likely

## 逆向/函数级分析补充约束
1. 优先基于目标函数本体分析；若证据不足，再扩展到子函数与调用链。
2. 若子函数存在风险，必须判断当前函数是否满足其触发条件；不满足则视为不可触发。
3. 重点关注可利用高危漏洞：SQL 注入、XSS、命令执行、路径遍历、文件上传、业务逻辑绕过等。
4. 对具备调用关系的候选，至少向上追溯 3 层调用关系（能力允许范围内）。
5. 若输出触发条件结构，条件键优先使用“参数1/参数2/外部输入1”这类规范命名。
6. 对函数外部输入（HTTP 请求、环境变量、配置、文件）先判断可控性，再判断是否可触发漏洞。

## 工作流
1. 读取目标文件并校验定位（文件/行号/代码片段）。
2. 提取目标函数，构建 Harness，优先动态验证（`run_code`）。
3. 按单候选状态机推进：pending -> running -> verified/false_positive。
4. 汇总证据，输出 Final Answer JSON。
5. **输出 Final Answer 前，调用 `save_verification_results` 工具保存结果（必须执行）。**

## Final Answer 要求（JSON格式）

**重要：分层结构说明**：
- Finding层级字段：`file_path`, `line_start`, `line_end`, `title`, `cwe_id`, `suggestion`等
- **verification_result嵌套dict中（缺一不可）**：`verdict`, `confidence`, `reachability`, `verification_evidence`

**Finding层级必需字段**:
1. `file_path`: 完整文件路径
2. `line_start`, `line_end`: 代码行号范围
3. `title`: 漏洞标题
4. `cwe_id`: CWE编号(如"CWE-89"、"CWE-1333"等)

**verification_result嵌套dict中的必需字段（每条finding必须有，缺一不可）**:
1. `verdict`: 真实性判定(confirmed|likely|uncertain|false_positive)，不可省略
2. `confidence`: 置信度 [0.0-1.0浮点数] ← **必填！必须是数值而非文本**，计算见"真实性与置信度判定"
3. `reachability`: 可达性判定(reachable|likely_reachable|unknown|unreachable)
4. `verification_evidence`: 验证证据，必须包含：
   - 使用的验证方法（fuzzing/static_analysis/symbols/dynamic等）
   - 关键代码片段或执行输出
   - 漏洞存在或不存在的理由

**可选字段** (但强烈建议填写):
- `suggestion`: 修复建议
- `fix_code`: 修复代码片段
- `poc_plan`: 非武器化PoC思路
- `verification_method`: 验证方法详述
- `code_snippet`: 相关代码片段

**JSON示例** (正确格式):
```json
{
  "findings": [
    {
      "file_path": "server/app.py",
      "line_start": 36,
      "line_end": 36,
      "title": "search_posts函数正则表达式拒绝服务(ReDoS)漏洞",
      "cwe_id": "CWE-1333",
      "verification_result": {
        "verdict": "confirmed",
        "confidence": 0.92,
        "reachability": "reachable",
        "verification_evidence": "通过fuzzing动态执行验证：构造payload='(a+)+b'*31,执行时间从0.7s升至22.4s"
      },
      "suggestion": "使用regex库替代re.search，或对用户输入进行正则表达式复杂度检查"
    }
  ]
}
```

## ⚠️ 关键约束
1. **必须先调用工具验证** - 不允许仅凭已知信息直接判断
2. **优先使用 run_code** - 编写 Harness 进行动态验证
3. **PoC 必须完整可执行** - poc.payload 应该是可直接运行的代码
4. **不要假设环境** - 沙箱中没有运行的服务，需要 mock

## 重要原则
1. **你是验证的大脑** - 你决定如何测试，工具只提供执行能力
2. **动态验证优先** - 能运行代码验证的就不要仅靠静态分析
3. **质量优先** - 宁可漏报也不要误报太多
4. **证据支撑** - 每个判定都需要有依据

现在开始验证漏洞发现！"""

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
    status: str = "pending"  # pending|running|verified|false_positive
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
            max_iterations=25,
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)
        
        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[VerificationStep] = []



    
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

    def _normalize_verdict(self, finding: Dict[str, Any]) -> str:
        """改进的真实性判定方法
        
        规则：
        1. 如果有明确的verdict字段，直接返回（confirmed/likely/false_positive）
        2. 如果is_verified=True，返回confirmed
        3. 如果有有效的confidence值，按阈值判定
        4. 如果confidence缺失，保留原始LLM的verdict而非强制降级
        """
        verdict = finding.get("verdict") or finding.get("authenticity")
        if isinstance(verdict, str):
            verdict = verdict.strip().lower()
        else:
            verdict = None
        if verdict in {"confirmed", "likely", "false_positive"}:
            return verdict
        
        # === 改进：缺失confidence时保留LLM原始verdict ===
        confidence_raw = finding.get("confidence")
        confidence = None
        confidence_source = "missing"
        
        if confidence_raw is not None:
            try:
                confidence = float(confidence_raw)
                confidence_source = "direct"
            except Exception:
                logger.warning(
                    f"[Verification] confidence 类型转换失败: {confidence_raw} (type: {type(confidence_raw).__name__})"
                )
        
        # 规则1: is_verified=True 优先级最高
        if finding.get("is_verified") is True:
            return "confirmed"
        
        # 规则2: 有有效的confidence值时按阈值判定
        if confidence is not None:
            if confidence >= CONFIDENCE_THRESHOLD_LIKELY:
                return "likely"
            if confidence <= CONFIDENCE_THRESHOLD_FALSE_POSITIVE:
                return "false_positive"
            # 0.3 < confidence < 0.7 的灰色地带
            return "likely"
        
        # 规则3: 缺失confidence且无明确verdict时的兜底策略
        # 不再强制降级为false_positive，而是保守估计为likely
        logger.debug(
            f"[Verification] confidence缺失且无明确verdict，保留为likely: "
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

    def _normalize_vulnerability_key(self, finding: Dict[str, Any]) -> str:
        return normalize_vulnerability_type(finding.get("vulnerability_type"))

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
            r"格式化字符串漏洞|空指针解引用缺陷|未知类型漏洞)",
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
                r"(?:[\w:&*<>, ]+\s+)*?"  # complex return types with templates  
                r"(\w+)\s*\([^;]*\)\s*(?:const)?\s*(?:noexcept)?\s*\{?"
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
                    if not name or len(name) < 1 or name in _PSEUDO_FUNCTION_NAMES:
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
        text = str(raw_output or "").strip()
        if not text:
            return None
        if text.startswith("⚠️") or text.startswith("❌"):
            return None

        candidates = [text]
        if "```" in text:
            fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text)
            if fence_match:
                candidates.append(fence_match.group(1))
        json_match = re.search(r"(\{[\s\S]*\})", text)
        if json_match:
            candidates.append(json_match.group(1))

        for candidate in candidates:
            candidate_text = str(candidate or "").strip()
            if not candidate_text:
                continue
            try:
                data = json.loads(candidate_text)
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
        return None

    def _extract_function_from_locator_payload(
        self,
        payload: Dict[str, Any],
        line_start: int,
    ) -> Optional[Dict[str, Any]]:
        direct_target = payload.get("enclosing_function") or payload.get("enclosingFunction")
        if isinstance(direct_target, dict):
            name = str(
                direct_target.get("name")
                or direct_target.get("function")
                or direct_target.get("symbol")
                or ""
            ).strip()
            if name:
                return {
                    "function": name,
                    "start_line": self._safe_int(
                        direct_target.get("start_line")
                        or direct_target.get("startLine")
                        or direct_target.get("line")
                    ),
                    "end_line": self._safe_int(
                        direct_target.get("end_line")
                        or direct_target.get("endLine")
                    ),
                    "language": payload.get("language") or direct_target.get("language"),
                    "diagnostics": payload.get("diagnostics"),
                }

        symbol_candidates: List[Dict[str, Any]] = []
        for key in ("symbols", "functions", "definitions", "items", "members"):
            values = payload.get(key)
            if isinstance(values, list):
                for raw in values:
                    if isinstance(raw, dict):
                        symbol_candidates.append(raw)

        if not symbol_candidates:
            return None

        normalized_symbols: List[Dict[str, Any]] = []
        for symbol in symbol_candidates:
            name = str(
                symbol.get("name")
                or symbol.get("symbol")
                or symbol.get("identifier")
                or ""
            ).strip()
            if not name:
                continue
            kind = str(symbol.get("kind") or symbol.get("type") or "").strip().lower()
            if kind and all(tag not in kind for tag in ("function", "method", "constructor")):
                continue
            start = self._safe_int(
                symbol.get("start_line")
                or symbol.get("startLine")
                or symbol.get("line")
            )
            end = self._safe_int(symbol.get("end_line") or symbol.get("endLine"))
            if start and not end:
                end = start
            normalized_symbols.append(
                {
                    "function": name,
                    "start_line": start,
                    "end_line": end,
                    "distance": abs((start or line_start) - line_start),
                }
            )

        if not normalized_symbols:
            return None

        covering = [
            item
            for item in normalized_symbols
            if item["start_line"] is not None
            and item["end_line"] is not None
            and int(item["start_line"]) <= line_start <= int(item["end_line"])
        ]
        if covering:
            best = min(
                covering,
                key=lambda item: (
                    int(item["end_line"]) - int(item["start_line"]),
                    int(item["start_line"]),
                ),
            )
        else:
            prefix = [
                item
                for item in normalized_symbols
                if item["start_line"] is not None
                and int(item["start_line"]) <= line_start
            ]
            best = min(prefix or normalized_symbols, key=lambda item: item["distance"])

        return {
            "function": best["function"],
            "start_line": best.get("start_line"),
            "end_line": best.get("end_line"),
            "language": payload.get("language"),
            "diagnostics": payload.get("diagnostics"),
        }

    async def _enrich_function_metadata_with_locator(
        self,
        findings_to_verify: List[Dict[str, Any]],
        project_root: Optional[str],
    ) -> None:
        """
        改进的 MCP 函数定位辅助方法：增强容错与诊断日志
        当 MCP 失败时，不再静默跳过，而是记录原因并标记状态
        """
        if not findings_to_verify:
            return

        mcp_success_count = 0
        mcp_fail_count = 0
        
        for idx, finding in enumerate(findings_to_verify):
            if not isinstance(finding, dict):
                logger.debug(f"[Verification] MCP enrichment跳过非字典项 #{idx}")
                continue
            
            existing_name = str(finding.get("function_name") or "").strip()
            if existing_name and existing_name.lower() not in {"unknown", "未知函数"}:
                logger.debug(f"[Verification] MCP enrichment跳过已有函数名: {existing_name}")
                continue

            file_path, line_start, _line_end = self._normalize_file_location(finding)
            resolved_file_path, _full = self._resolve_file_paths(file_path, project_root)
            request_path = resolved_file_path or file_path
            
            if not request_path or line_start <= 0:
                logger.debug(f"[Verification] MCP enrichment跳过无效路径: {request_path}:{line_start}")
                continue

            locator_input = {
                "file_path": request_path,
                "line_start": int(line_start),
            }
            
            try:
                logger.debug(f"[Verification] 调用 MCP locate_enclosing_function: {request_path}:{line_start}")
                locator_output = await self.execute_tool(
                    "locate_enclosing_function",
                    locator_input,
                )
                
                payload = self._extract_locator_payload(locator_output)
                if not payload:
                    mcp_fail_count += 1
                    logger.warning(
                        f"[Verification] MCP返回空payload: {request_path}:{line_start} | "
                        f"raw_output={str(locator_output)[:200]}"
                    )
                    # 标记MCP尝试但失败
                    finding["_mcp_attempt"] = "failed_empty_payload"
                    continue
                
                located = self._extract_function_from_locator_payload(payload, int(line_start))
                if not located:
                    mcp_fail_count += 1
                    logger.warning(
                        f"[Verification] MCP payload解析失败: {request_path}:{line_start} | "
                        f"payload_keys={list(payload.keys())}"
                    )
                    finding["_mcp_attempt"] = "failed_payload_parsing"
                    continue

                located_name = str(located.get("function") or "").strip()
                if not located_name:
                    mcp_fail_count += 1
                    logger.warning(
                        f"[Verification] MCP返回空函数名: {request_path}:{line_start}"
                    )
                    finding["_mcp_attempt"] = "failed_empty_function_name"
                    continue
                
                # MCP 成功
                mcp_success_count += 1
                finding["function_name"] = located_name
                finding["function_start_line"] = self._safe_int(located.get("start_line"))
                finding["function_end_line"] = self._safe_int(located.get("end_line"))
                finding["function_resolution_method"] = "mcp_symbol_index"
                finding["function_resolution_engine"] = "mcp_symbol_index"
                if located.get("language"):
                    finding["function_language"] = located.get("language")
                if located.get("diagnostics") is not None:
                    finding["function_resolution_diagnostics"] = located.get("diagnostics")
                
                logger.info(
                    f"[Verification] MCP定位成功: '{located_name}' @ {request_path}:{line_start}"
                )
                
            except Exception as e:
                mcp_fail_count += 1
                logger.error(
                    f"[Verification] MCP调用异常: {request_path}:{line_start} | 错误: {e}",
                    exc_info=True
                )
                finding["_mcp_attempt"] = f"exception: {str(e)[:100]}"
                continue
        
        logger.info(
            f"[Verification] MCP enrichment 完成: 成功={mcp_success_count}, 失败={mcp_fail_count}, "
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
            fix_code = merged.get("fix_code") or self._build_default_fix_code(merged)
            if not suggestion:
                suggestion = self._get_recommendation(str(merged.get("vulnerability_type") or ""))

            allow_poc = verdict in {"confirmed", "likely"}
            poc_value = merged.get("poc") if allow_poc else None
            if allow_poc and not poc_value:
                poc_value = self._build_default_poc_plan(merged)

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
                function_name=function_name,
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
                        "function": function_name,
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
                    "function_name": function_name or (
                        f"[{localization_status}]" if localization_status != "unknown" else "未知函数"
                    ),
                }
            )

            repaired_findings.append(
                {
                    **merged,
                    "vulnerability_type": vuln_profile.get("key", "other"),
                    "title": structured_title,
                    "display_title": structured_title,
                    "file_path": resolved_file_path or normalized_file_path,
                    "line_start": line_start,
                    "line_end": line_end,
                    "function_name": function_name,
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
                    "fix_code": str(fix_code),
                    "poc": poc_value,
                    # === 新字段：函数定位状态透明度 ===
                    "localization_status": localization_status,
                    "file_readable": file_readable,
                }
            )

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
        mcp_hints = (
            "mcp_call_failed:",
            "mcp_adapter_unavailable:",
            "adapter_disabled_after_failures",
            "mcp_runtime_unavailable_strict_mode",
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
        if any(hint in lowered for hint in mcp_hints):
            return "mcp_unavailable"
        known = {
            "mcp_unavailable",
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
                    "verdict": item.final_verdict,
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
        title = str(finding.get("title") or "待验证缺陷").strip() or "待验证缺陷"
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

        previous_results = input_data.get("previous_results", {})
        config = input_data.get("config", {})
        task = input_data.get("task", "")
        task_context = input_data.get("task_context", "")
        project_root = input_data.get("project_root")
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
        
        # 🔥 优先支持：从队列取出的单个漏洞（方案A支持）
        # Orchestrator 在调用 dequeue_finding 后，会将单个漏洞通过 context 传递
        queue_finding_from_context = None
        if task_context and isinstance(task_context, str):
            # 尝试从 task_context 中解析 JSON 漏洞信息
            import json
            try:
                # task_context 可能是纯文本描述，也可能包含 JSON
                if task_context.strip().startswith("{"):
                    queue_finding_from_context = json.loads(task_context)
                elif "finding_from_queue" in task_context or "dequeued_finding" in task_context:
                    # 尝试提取嵌入的 JSON
                    import re
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
        
        # 🔥 支持单个漏洞验证（方案A：队列集成）
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

## ⚠️ 验证指南
1. **直接使用上述文件路径** - 使用精确路径: `{file_path}`
2. **先读取完整文件内容** - 使用 `read_file` 工具了解上下文
3. **深入分析代码逻辑** - 确认漏洞是否真实存在
4. **编写验证代码** - 如可能，使用 `run_code` 编写 Fuzzing Harness 验证

## 验证要求
- 验证级别: {config.get('verification_level', 'standard')}
- 必须提供明确的验证结论: `confirmed` (确认) / `likely` (可能) / `false_positive` (误报)
- 必须提供置信度 (0-1)
- 必须提供可达性分析: `reachable` / `likely_reachable` / `unreachable`

## 可用工具
{self.get_tools_description()}

请立即开始验证这个发现：
1. 使用 read_file 读取 `{file_path}` (关注第 {line_start} 行附近)
2. 分析代码上下文，确认漏洞是否存在
3. 如需要，使用其他工具 (run_code, search_code, extract_function) 深入验证
4. 给出最终验证结论

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
{finding.get('code_snippet', 'N/A')[:500]}
```
- 描述: {finding.get('description', 'N/A')[:300]}
""")

            initial_message = f"""请验证以下 {len(findings_to_verify)} 个安全发现。

{handoff_context if handoff_context else ''}

## 待验证发现
{''.join(findings_summary)}

## ⚠️ 重要验证指南
1. **直接使用上面列出的文件路径** - 不要猜测或搜索其他路径
2. **如果文件路径包含冒号和行号** (如 "app.py:36"), 请提取文件名 "app.py" 并使用 read_file 读取
3. **先读取文件内容，再判断漏洞是否存在**
4. **不要假设文件在子目录中** - 使用发现中提供的精确路径

## 验证要求
- 验证级别: {config.get('verification_level', 'standard')}

## 可用工具
{self.get_tools_description()}

请开始验证。对于每个发现：
1. 首先使用 read_file 读取发现中指定的文件（使用精确路径）
2. 分析代码上下文
3. 判断是否为真实漏洞
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

        try:
            for iteration in range(self.config.max_iterations):
                if self.is_cancelled:
                    break

                self._iteration = iteration + 1
                run_iteration_count = self._iteration
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
                        await self.emit_thinking("⚠️ 拒绝过早完成：必须先使用工具验证漏洞")
                        if findings_to_verify:
                            forced_target = findings_to_verify[0]
                            forced_file = str(forced_target.get("file_path") or "").strip()
                            forced_line = int(forced_target.get("line_start") or 1)
                            if forced_file:
                                forced_input = {
                                    "file_path": forced_file,
                                    "start_line": max(1, forced_line - 8),
                                    "end_line": max(forced_line + 20, forced_line),
                                }
                                forced_observation = await self.execute_tool("read_file", forced_input)
                                self._conversation_history.append(
                                    {
                                        "role": "user",
                                        "content": f"Observation:\n{forced_observation}",
                                    }
                                )
                        self._conversation_history.append(
                            {
                                "role": "user",
                                "content": (
                                    "⚠️ **系统拒绝**: 你必须先使用工具验证漏洞！\n\n"
                                    "不允许在没有调用任何工具的情况下直接输出 Final Answer。\n\n"
                                    "请立即使用以下工具之一进行验证：\n"
                                    "1. `read_file` - 读取漏洞所在文件的代码\n"
                                    "2. `run_code` - 编写并执行 Fuzzing Harness 验证漏洞\n"
                                    "3. `extract_function` - 提取目标函数进行分析\n\n"
                                    "现在请输出 Thought 和 Action，开始验证第一个漏洞。"
                                ),
                            }
                        )
                        continue

                    await self.emit_llm_decision("完成漏洞验证", "LLM 判断验证已充分")
                    final_result = step.final_answer

                    if final_result and "findings" in final_result:
                        verified_count = len([item for item in final_result["findings"] if item.get("is_verified")])
                        fp_count = len([item for item in final_result["findings"] if item.get("verdict") == "false_positive"])
                        self.add_insight(
                            f"验证了 {len(final_result['findings'])} 个发现，{verified_count} 个确认，{fp_count} 个误报"
                        )
                        self.record_work(f"完成漏洞验证: {verified_count} 个确认, {fp_count} 个误报")

                    await self.emit_llm_complete("验证完成", self._total_tokens)
                    break

                if step.action:
                    await self.emit_llm_action(step.action, step.action_input or {})
                    tool_call_key = f"{step.action}:{json.dumps(step.action_input or {}, sort_keys=True)}"

                    if not hasattr(self, "_tool_call_counts"):
                        self._tool_call_counts = {}
                    self._tool_call_counts[tool_call_key] = self._tool_call_counts.get(tool_call_key, 0) + 1

                    if self._tool_call_counts[tool_call_key] > 3:
                        logger.warning(f"[{self.name}] Detected repetitive tool call loop: {tool_call_key}")
                        observation = (
                            f"⚠️ **系统干预**: 你已经使用完全相同的参数调用了工具 '{step.action}' 超过3次。\n"
                            "请**不要**重复尝试相同的操作。这是无效的。\n"
                            "请尝试：\n"
                            "1. 修改参数 (例如改变 input payload)\n"
                            "2. 使用不同的工具 (例如从 sandbox_exec 换到 php_test)\n"
                            "3. 如果之前的尝试都失败了，请尝试 analyze_file 重新分析代码\n"
                            "4. 如果无法验证，请输出 Final Answer 并标记为 uncertain"
                        )
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
                    )

                    if is_tool_error:
                        self._failed_tool_calls[tool_call_key] = self._failed_tool_calls.get(tool_call_key, 0) + 1
                        fail_count = self._failed_tool_calls[tool_call_key]
                        if fail_count >= 3:
                            logger.warning(f"[{self.name}] Tool call failed {fail_count} times: {tool_call_key}")
                            observation += f"\n\n⚠️ **系统提示**: 此工具调用已连续失败 {fail_count} 次。请：\n"
                            observation += "1. 尝试使用不同的参数（如指定较小的行范围）\n"
                            observation += "2. 使用 search_code 工具定位关键代码片段\n"
                            observation += "3. 跳过此发现的验证，继续验证其他发现\n"
                            observation += "4. 如果已有足够验证结果，直接输出 Final Answer"
                            self._failed_tool_calls[tool_call_key] = 0
                    else:
                        if tool_call_key in self._failed_tool_calls:
                            del self._failed_tool_calls[tool_call_key]

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

                for finding in final_result["findings"]:
                    # === 适配新的verification_result嵌套结构 ===
                    # 优先从verification_result中获取，向后兼容finding层级
                    verification_result = finding.get("verification_result", {})
                    if not isinstance(verification_result, dict):
                        verification_result = {}
                    
                    verdict = verification_result.get("verdict") or finding.get("verdict")
                    confidence = verification_result.get("confidence") or finding.get("confidence")
                    reachability = verification_result.get("reachability") or finding.get("reachability")
                    verification_evidence = verification_result.get("verification_evidence") or finding.get("verification_evidence")
                    
                    if not verdict or verdict not in ["confirmed", "likely", "uncertain", "false_positive"]:
                        # === 使用全局阈值常量统一判定 ===
                        if finding.get("is_verified") is True:
                            verdict = "confirmed"
                        else:
                            if confidence is None:
                                # confidence缺失时保存原始值用于诊断
                                verdict = "likely"  # 保守估计为likely而非false_positive
                                logger.debug(
                                    f"[{self.name}] confidence缺失，保留为likely: {finding.get('file_path', '?')}"
                                )
                            else:
                                try:
                                    confidence_val = float(confidence)
                                except Exception:
                                    confidence_val = CONFIDENCE_DEFAULT_FALLBACK
                                
                                if confidence_val >= CONFIDENCE_THRESHOLD_LIKELY:
                                    verdict = "likely"
                                elif confidence_val <= CONFIDENCE_THRESHOLD_FALSE_POSITIVE:
                                    verdict = "false_positive"
                                else:
                                    verdict = "likely"
                        
                        logger.warning(
                            f"[{self.name}] Missing/invalid verdict for {finding.get('file_path', '?')}, inferred as: {verdict}"
                        )

                    verified = {
                        **finding,
                        "verdict": verdict,
                        "confidence": confidence,
                        "reachability": reachability,
                        "verification_result": {
                            **(verification_result or {}),
                            "verdict": verdict,
                            "confidence": confidence,
                            "reachability": reachability,
                            "verification_evidence": verification_evidence,
                        },
                        "is_verified": verdict == "confirmed" or (verdict == "likely" and (confidence or 0) >= CONFIDENCE_THRESHOLD_LIKELY),
                        "verified_at": datetime.now(timezone.utc).isoformat() if verdict in ["confirmed", "likely"] else None,
                    }

                    if not verified.get("recommendation"):
                        verified["recommendation"] = self._get_recommendation(finding.get("vulnerability_type", ""))

                    verified_findings.append(verified)
            else:
                for finding in findings_to_verify:
                    verified_findings.append({
                        **finding,
                        "verdict": "uncertain",
                        "confidence": 0.5,
                        "is_verified": False,
                    })

            for idx, todo_item in enumerate(todo_items):
                current_todo_index = idx + 1
                current_todo_id = todo_item.id
                if idx >= len(verified_findings):
                    todo_item.status = "false_positive"
                    todo_item.final_verdict = "false_positive"
                    todo_item.blocked_reason = "missing_verification_output"
                    continue
                verdict = str(verified_findings[idx].get("verdict") or "uncertain").strip().lower()
                if verdict in {"confirmed", "likely"}:
                    todo_item.status = "verified"
                    todo_item.final_verdict = verdict
                else:
                    todo_item.status = "false_positive"
                    todo_item.final_verdict = "false_positive"
                meta_title = str(verified_findings[idx].get("title") or todo_item.title)
                meta_vuln = str(verified_findings[idx].get("vulnerability_type") or "unknown")
                meta_sev = str(verified_findings[idx].get("severity") or "medium")
                meta_file = str(verified_findings[idx].get("file_path") or todo_item.file_path)
                meta_line_start = int(verified_findings[idx].get("line_start") or todo_item.line_start)
                meta_line_end = int(verified_findings[idx].get("line_end") or meta_line_start)
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
                            "is_verified": True,
                            "finding_scope": "verification_queue",
                            "verification_todo_id": todo_item.id,
                            "verification_fingerprint": todo_item.fingerprint,
                            "verification_status": "verified",
                            "status": "verified",
                        },
                    )
                else:
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
                        },
                    )

            confirmed_count = len([item for item in verified_findings if item.get("verdict") == "confirmed"])
            likely_count = len([item for item in verified_findings if item.get("verdict") == "likely"])
            false_positive_count = len([item for item in verified_findings if item.get("verdict") == "false_positive"])
            todo_summary = self._build_verification_todo_summary(todo_items)
            await self._emit_verification_todo_update(
                todo_items,
                "逐漏洞验证完成",
                current_index=len(todo_items),
                total_todos=len(todo_items),
            )

            await self.emit_event(
                "info",
                f"Verification Agent 完成: {confirmed_count} 确认, {likely_count} 可能, {false_positive_count} 误报",
            )

            logger.info(f"[{self.name}] Returning {len(verified_findings)} verified findings")

            # 🔥 验证结果持久化：通过工具将 findings 保存到数据库
            # LLM 处理层已在 Final Answer 后将 findings 传递给此工具；
            # 这里做兼容兴德：如果 LLM 未主动调用，仍由濒递逻辑处理。
            if "save_verification_results" in self.tools and verified_findings:
                confirmed_or_likely = [
                    f for f in verified_findings
                    if str(f.get("verdict") or "").lower() in {"confirmed", "likely"}
                ]
                if confirmed_or_likely:
                    try:
                        save_result = await self.execute_tool(
                            "save_verification_results",
                            {
                                "findings": confirmed_or_likely,
                                "summary": (
                                    f"共验证 {len(findings_to_verify)} 个候选，"
                                    f"{confirmed_count} 确认 / {likely_count} 可能 / "
                                    f"{false_positive_count} 误报"
                                ),
                            },
                        )
                        logger.info(
                            "[%s] save_verification_results: %s",
                            self.name,
                            (save_result.data or {}).get("message", ""),
                        )
                    except Exception as _save_err:
                        logger.warning(
                            "[%s] save_verification_results 工具调用失败 (已降级继续): %s",
                            self.name,
                            _save_err,
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
                    "false_positive_count": false_positive_count,
                    "candidate_count": len(findings_to_verify),
                    "verification_todo_summary": todo_summary,
                },
                iterations=self._iteration,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
                handoff=handoff,
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
            "candidate_count": int(candidate_count or len(verified_findings)),
            "verified_output_count": len(verified_findings),
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
