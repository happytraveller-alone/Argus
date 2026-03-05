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

from .base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern, TaskHandoff
from .react_parser import parse_react_response
from ..json_parser import AgentJsonParser
from ..prompts import CORE_SECURITY_PRINCIPLES, VULNERABILITY_PRIORITIES

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """你是 VulHunter 的漏洞分析 Agent，负责对**单个风险点**进行深度验证和扩展分析，并**将最终确认的漏洞推送至队列**。

## 你的核心任务
- **聚焦分析**：你收到的输入是一个**风险点对象**（包含 `file_path`、`line_start`、`description`、`severity`、`vulnerability_type` 等字段）。你的首要任务是**围绕该风险点展开分析**。
- **验证漏洞**：通过代码上下文阅读、数据流追踪、相关函数分析等手段，判断该风险点是否构成真实可利用的漏洞。
- **推送发现**：一旦确认漏洞存在，**必须立即调用 `push_finding_to_queue` 工具**，将详细的漏洞发现推送到队列，供后续 Verification Agent 验证。
- **扩展挖掘**：在分析过程中，如果发现与当前风险点相关的其他漏洞（如同一文件的其他行、被调用的函数、或上下游逻辑缺陷），也应一并分析确认，并分别推送。

## 输入风险点格式（示例）
你会在初始上下文或从队列中接收到类似以下格式的风险点：
```json
{
    "file_path": "src/auth.py",
    "line_start": 45,
    "description": "登录函数缺少速率限制，存在暴力破解风险",
    "severity": "medium",
    "vulnerability_type": "brute_force",
    "confidence": 0.7
}

## 🔥 漏洞队列推送机制（强制要求）

* 每确认一个漏洞，必须立即调用 push_finding_to_queue，不得延迟或批量推送。

* 推送的 finding 对象必须包含完整的定位信息和漏洞描述，格式如下：

```
{
    "file_path": "src/auth.py",
    "line_start": 45,
    "line_end": 48,                     // 可选，漏洞代码结束行
    "title": "src/auth.py中login函数存在暴力破解漏洞",  // 中文三段式：路径+函数+漏洞名
    "description": "登录接口未添加任何速率限制，攻击者可无限次尝试密码，存在暴力破解风险。",
    "vulnerability_type": "brute_force",
    "severity": "medium",
    "confidence": 0.9,
    "code_snippet": "def login():\n    username = request.form['username']\n    password = request.form['password']\n    user = User.query.filter_by(username=username).first()\n    if user and check_password(password, user.password):\n        login_user(user)",
    "function_name": "login",
    "source": "request.form",            // 污点来源（如适用）
    "sink": "login_user",                 // 危险函数/操作（如适用）
    "suggestion": "建议在登录接口添加验证码、登录失败次数限制及账号锁定机制。"
}
```

## 与业务逻辑扫描工具的协作
* 你可以调用 business_logic_scan 工具来分析疑似存在业务逻辑漏洞的接口。
* business_logic_scan 不负责推送漏洞，而是返回 findings 列表。你需要手动解析该工具返回的 findings，并逐个调用 push_finding_to_queue 进行推送。
* 调用 business_logic_scan 的方式
```
Action: business_logic_scan
Action Input: {
    "target": ".",
    "entry_points_hint": ["app/api/user.py:update_profile", "app/api/order.py:create_order"],
    "max_iterations": 5
}
```
工具返回的 Observation 将包含 findings 数组。你需要遍历它们，构造合适的 finding 对象（可能已符合格式）并推送。

## 推荐分析流程
### 第一步：聚焦风险点
1. 使用 read_file 读取风险点所在的文件，重点关注该行及上下文（前后至少 20 行）。
2. 分析代码逻辑，判断风险点描述是否准确，是否真的存在安全缺陷。
3. 如果确认存在漏洞 → 立即调用 push_finding_to_queue 推送。

### 第二步：深入扩展
* 跟踪风险点涉及的变量、函数调用，使用 search_code 查找相关定义。
* 如果漏洞涉及跨文件调用，可以进一步读取相关文件。
* 若识别到业务逻辑漏洞嫌疑（如权限绕过、IDOR），可调用 business_logic_scan 并传入相关入口点提示（通过 entry_points_hint 参数）进行专业扫描，该工具发现的漏洞会自动推送。
* 也可使用 dataflow_analysis 或 controlflow_analysis_light 等工具辅助追踪污点流向。

### 第三步：推送所有确认的漏洞
* 每确认一个漏洞（包括扩展发现的新漏洞），立即推送。
* 在推送时，确保 title 符合“路径+函数+漏洞名”的中文三段式格式，description、suggestion 等字段使用简体中文。

### 第四步: 收尾
* 确认所有漏洞均已推送，输出简短的 Final Answer，汇总本次分析的漏洞数量及关键信息（无需重复列出详情，因为已在队列中）。

## 关键约束
* **必须基于实际代码**：所有漏洞判断必须源自通过 read_file 读取的代码或工具返回的证据，禁止凭空捏造。
* **推送优先于汇总**：每发现一个漏洞必须立即推送，最后才能输出 Final Answer。
* **标题强约束**：每条 finding 的 title 必须是中文三段式：文件路径 + 函数名 + 具体漏洞名，例如 "src/auth.py中login函数SQL注入漏洞"。
* **语言要求**：title、description、suggestion 必须使用简体中文。
* **证据要求**：高危漏洞应至少包含 2 类证据（如代码证据 + 数据流分析结果）。
* **首轮必须输出 Action**：禁止第一轮直接输出 Final Answer。
* **避免重复**：推送前可检查队列状态，防止相同漏洞重复入队。

## 输出格式
每一步行动采用标准格式：
```
Thought: [分析当前状态，计划下一步]
Action: [工具名称]
Action Input: { "参数": "值" }
```
最终输出（所有漏洞推送完毕后）：
```
Thought: 已完成风险点分析，共推送 X 个漏洞。
Final Answer: 分析完成，所有确认的漏洞已推送至队列。
```

## 示例交互
**示例交互**

假设初始收到风险点：
```json
{
    "file_path": "app/api/upload.py",
    "line_start": 35,
    "description": "文件上传未校验文件类型，可能导致任意文件上传",
    "severity": "high",
    "vulnerability_type": "file_upload",
    "confidence": 0.8
}
```

分析过程：

```
Thought: 收到风险点，位于 app/api/upload.py:35，描述为文件上传未校验类型。我需要读取该文件，验证漏洞。
Action: read_file
Action Input: { "file_path": "app/api/upload.py", "max_lines": 50 }

Observation: (文件内容显示第35行附近代码)
```
```python
@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    filename = file.filename
    file.save(os.path.join('uploads', filename))
    return 'Uploaded'
```
```
Thought: 确实未校验文件类型，且直接保存文件名，存在任意文件上传风险。立即推送该漏洞。
Action: push_finding_to_queue
Action Input: {
    "file_path": "app/api/upload.py",
    "line_start": 35,
    "line_end": 39,
    "title": "app/api/upload.py中upload_file函数任意文件上传漏洞",
    "vulnerability_type": "file_upload",
    "severity": "high",
    "description": "文件上传接口未校验文件类型，攻击者可上传恶意脚本，导致服务器被控制。",
    "code_snippet": "@app.route('/upload', methods=['POST'])\ndef upload_file():\n    file = request.files['file']\n    filename = file.filename\n    file.save(os.path.join('uploads', filename))\n    return 'Uploaded'",
    "function_name": "upload_file",
    "source": "request.files['file']",
    "sink": "file.save",
    "suggestion": "限制上传文件类型（如白名单）、重命名文件、存储至非Web目录。",
    "confidence": 0.95
}

Observation: 漏洞推送成功，队列状态更新。

Thought: 文件上传漏洞已推送。但上传功能常与用户资料更新、订单附件等功能相关，可能存在业务逻辑缺陷。我应检查其他相关接口。
Action: list_files
Action Input: { "directory": "app/api" }

Observation: ["upload.py", "user.py", "order.py", "__init__.py"]

Thought: 读取 user.py 和 order.py，寻找可能的业务逻辑入口点。
Action: read_file
Action Input: { "file_path": "app/api/user.py", "max_lines": 100 }

Observation: (内容包含 update_profile 函数，使用用户ID参数，但未检查当前用户权限)
```
@app.route('/user/<int:user_id>', methods=['PUT'])
def update_profile(user_id):
    data = request.json
    # 直接更新 user_id 对应的用户，未验证当前用户是否为本人
    db.update_user(user_id, data)
    return 'OK'
```

Thought: 发现 update_profile 接口可能存在 IDOR（水平越权）漏洞，因为它未验证当前用户是否有权修改指定 user_id 的资料。将其列为可疑业务逻辑入口点。
Action: read_file
Action Input: { "file_path": "app/api/order.py", "max_lines": 100 }

Observation: (内容包含 create_order 函数，接受 amount 参数，但未在服务端验证金额)
```
@app.route('/order', methods=['POST'])
def create_order():
    data = request.json
    amount = data['amount']
    # 直接使用前端传入的 amount，未校验最小值或与商品匹配
    order = Order(amount=amount, user_id=current_user.id)
    db.session.add(order)
    db.session.commit()
    return jsonify(order.id)
```

Thought: create_order 接口可能存在金额篡改漏洞。现在我有两个可疑业务逻辑入口点：user.py:update_profile 和 order.py:create_order。我应调用 business_logic_scan 工具深入分析这些入口点。
Action: business_logic_scan
Action Input: {
    "target": ".",
    "entry_points_hint": [
        "app/api/user.py:update_profile",
        "app/api/order.py:create_order"
    ],
    "max_iterations": 5
}

Observation: business_logic_scan 执行完成，发现以下漏洞并已自动推送至队列：
- IDOR 漏洞：app/api/user.py:update_profile 未验证用户权限，可越权修改他人资料
- 金额篡改漏洞：app/api/order.py:create_order 未校验金额，可提交负数或极小值

推送状态：已入队。

Thought: 业务逻辑扫描已自动推送漏洞，无需我手动推送。现在检查队列状态，确保所有漏洞已入队。
Action: get_analysis_queue_status
Action Input: {}

Observation: { "pending_count": 3, "queue_status": "active" }

Thought: 三个漏洞已全部入队（文件上传 + IDOR + 金额篡改）。分析完成，可以输出 Final Answer。
Final Answer: 分析完成，已推送 3 个漏洞至队列，包括文件上传漏洞、IDOR漏洞和金额篡改漏洞。
```
请严格按照此流程执行，确保每个风险点得到深入分析，所有真实漏洞及时入队。
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
        action_input: Dict[str, Any],
        risk_file_path: str,
    ) -> Optional[str]:
        """判断 Action 是否越界到单风险点范围之外。返回原因字符串表示越界。"""
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
            "list_files",
            "business_logic_scan",
        }
        if action_name in blocked_actions:
            return f"单风险点模式禁止调用全局扫描工具: {action_name}"

        target_keys = [
            "file_path",
            "scan_file",
            "target_file",
            "path",
            "target_path",
            "target",
            "directory",
        ]
        allowed = str(risk_file_path or "").strip()
        for key in target_keys:
            value = action_input.get(key)
            if isinstance(value, str) and value.strip():
                candidate = value.strip()
                if candidate in {".", "./", "*", "./*"}:
                    return f"参数 {key}={candidate} 超出单风险点文件范围"
                if candidate != allowed:
                    return f"参数 {key}={candidate} 与目标文件 {allowed} 不一致"

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
### ⚠️ 高风险区域（来自 Recon Agent，必须优先分析）
以下是 Recon Agent 识别的高风险区域，请**务必优先**读取和分析这些文件：
{json.dumps(high_risk_areas[:20], ensure_ascii=False)}

**重要**: 请使用 read_file 工具读取上述高风险文件，不要假设文件路径或使用其他路径。

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

## ⚠️ 分析策略要求
1. **首先**：只分析给定风险点所在文件与附近代码（前后至少20行）
2. **然后**：仅在同一文件内做数据流/调用上下文扩展
3. **最后**：给出该风险点是否成立的结论，禁止扩展到全局扫描

**禁止**：不要跨文件、不要全局扫描、不要改为分析其他风险点

## 目标漏洞类型
{config.get('target_vulnerabilities', ['all'])}

## 可用工具
{self.get_tools_description()}

请开始你的安全分析。**第一步必须输出 Action**（优先 `read_file` 或 `search_code`），不允许第一轮直接输出 Final Answer。请先读取风险点所在文件的上下文，然后仅围绕该风险点继续分析。"""

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
        
        # 🔥 记录工作开始
        self.record_work("开始安全漏洞分析")
        
        # 🔥 初始化可疑接口列表（用于 business_logic_scan entry_points_hint）
        suspicious_interfaces: List[str] = []

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
            return (
                "⚠️ 系统无法自动执行最小工具调用（缺少 read_file 或目标文件未知）。"
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
                    stream_meta = getattr(self, "_last_llm_stream_meta", {}) or {}
                    empty_reason = str(stream_meta.get("empty_reason") or "").strip()
                    finish_reason = stream_meta.get("finish_reason")
                    chunk_count = int(stream_meta.get("chunk_count") or 0)
                    empty_from_stream = empty_reason in {"empty_response", "empty_stream", "empty_done"}
                    conversation_tokens_estimate = self._estimate_conversation_tokens(self._conversation_history)
                    
                    # 🔥 记录更详细的诊断信息
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
                        # 🔥 不是直接 break，而是尝试生成一个回退结果
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
                        # 🔥 更有针对性的重试提示
                        retry_prompt = f"""收到空响应。请根据以下格式输出你的思考和行动：

Thought: [你对当前安全分析情况的思考]
Action: [工具名称，如 read_file, search_code, pattern_match, opengrep_scan]
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
                            # 🔥 记录洞察
                            self.add_insight(
                                f"发现 {finding.get('severity', 'medium')} 级别漏洞: {finding.get('title', 'Unknown')}"
                            )
                    else:
                        logger.warning(f"[{self.name}] Final Answer has no 'findings' key or is None: {step.final_answer}")
                    
                    # 🔥 记录工作完成
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
                    # 🔥 发射 LLM 动作决策事件
                    await self.emit_llm_action(step.action, step.action_input or {})
                    
                    # 🔥 特殊处理：business_logic_scan 工具调用的条件响应机制
                    action_input = dict(step.action_input or {})

                    if single_risk_mode and single_risk_file:
                        out_of_scope_reason = self._is_action_out_of_single_scope(
                            action=step.action,
                            action_input=action_input,
                            risk_file_path=single_risk_file,
                        )
                        if out_of_scope_reason:
                            scoped_observation = (
                                f"⚠️ 单风险点范围约束：{out_of_scope_reason}。\n"
                                f"请仅分析文件 {single_risk_file}，并优先使用 read_file/search_code/dataflow_analysis。"
                            )
                            step.observation = scoped_observation
                            await self.emit_llm_observation(scoped_observation)
                            self._conversation_history.append({
                                "role": "user",
                                "content": f"Observation:\n{self._prepare_observation_for_history(scoped_observation)}",
                            })
                            continue

                    if step.action == "business_logic_scan":
                        # 如果 LLM 没有提供 entry_points_hint，添加提示
                        if not action_input.get("entry_points_hint") and not suspicious_interfaces:
                            # 提示 LLM 应该指定具体的接口
                            await self.emit_event(
                                "info",
                                "ℹ️ business_logic_scan 工具需要通过 entry_points_hint 参数指定要分析的接口。"
                                "您可以在 entry_points_hint 中列出具体的函数或入口点，例如 ['app/api/user.py:update_profile', ...]"
                            )
                            # 添加提示到对话历史
                            self._conversation_history.append({
                                "role": "user",
                                "content": "请使用 entry_points_hint 参数指定要分析的具体接口或函数。"
                                           "例如：entry_points_hint=['app/api/user.py:get_user', 'app/api/order.py:create_order']"
                            })
                            continue  # 跳过本次工具执行，等待 LLM 提供 entry_points_hint
                        
                        # 如果有收集到可疑接口但 LLM 没有完全指定，考虑自动填充
                        if suspicious_interfaces and not action_input.get("entry_points_hint"):
                            action_input["entry_points_hint"] = suspicious_interfaces[:20]
                    
                    # 🔥 循环检测：追踪工具调用失败历史
                    tool_call_key = f"{step.action}:{json.dumps(action_input or {}, sort_keys=True)}"
                    if not hasattr(self, '_failed_tool_calls'):
                        self._failed_tool_calls = {}
                    
                    observation = await self.execute_tool(
                        step.action,
                        action_input
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
                        await self.emit_thinking("⚠️ 检测到连续无 Action，系统自动执行最小证据工具以打破空转。")
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
