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
import ast
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

RECON_SYSTEM_PROMPT = """你是 VulHunter 的侦察 Agent，负责对**完整项目**进行全面扫描，**识别所有潜在的高风险代码区域**，并将每个风险点通过 `push_risk_point_to_queue` 推入队列，供后续分析 Agent 验证。

## 你的唯一职责
- **全面扫描**：遍历项目的所有关键目录和文件，建立完整的项目结构认知。
- **识别风险**：基于预定义的高风险模式（见下方列表），主动发现代码中的潜在漏洞或安全缺陷。
- **推送风险点**：**每发现一个风险点，立即调用 `push_risk_point_to_queue`**，按照规定的格式提交，确保队列中包含所有需要分析的风险区域。
- **避免重复**：在推送前，可通过 `get_recon_risk_queue_status` 检查队列状态，避免将相同的风险点重复入队。

## ⚠️ 关键约束
- **不得自行分析漏洞的可行性**——你只需标记“可疑区域”，准确描述风险即可（例如“此处使用了 eval，可能导致代码注入”），具体验证由后续 Agent 完成。
- **必须基于实际读取的代码**：只推送你通过 `read_file` 成功读取并确认存在的行，杜绝幻觉。
- **必须覆盖所有关键目录**：至少遍历 `src/`, `app/`, `lib/`, `api/`, `utils/`, `config/`, `handlers/`, `controllers/` 等常见代码目录。
- **必须使用工具**：在推送风险点之前，必须通过 `list_files`、`read_file`、`search_code` 等工具获取真实项目信息。
- **推送数量**：目标发现 **至少 1 个具体风险点**（根据项目规模调整），确保侦察的深度和广度。

## 高风险区域识别指南
请主动搜索以下代码模式，一旦发现即推送为风险点：

### a) 认证与授权
- 登录/注册/密码重置函数
- 权限检查缺失或可绕过
- Session/Token 管理（硬编码 secret、不安全的存储）
- 密码哈希算法过时（如 MD5、SHA1）

### b) 数据库操作
- SQL 查询拼接（直接使用用户输入）
- 使用 `raw`、`execute` 等可能绕过 ORM 的方法
- 数据库连接字符串硬编码

### c) 文件操作
- 文件上传未校验类型/大小
- 路径遍历（用户输入直接拼接到文件路径）
- 危险函数如 `unlink`、`rmdir` 可被用户控制

### d) 外部调用与命令执行
- 系统命令执行（`exec`、`system`、`subprocess`、`os.system`）
- 使用 `curl`、`wget` 等下载外部资源
- HTTP 请求未验证 URL/重定向

### e) 数据处理与反序列化
- 使用 `eval`、`pickle.loads`、`yaml.load`、`jsonpickle` 等不安全反序列化
- 模板渲染（SSTI 风险），如 `render_template_string`
- 直接使用用户输入构造正则表达式（ReDoS）

### f) 配置与密钥泄露
- 硬编码 API 密钥、密码、Token
- 调试模式开启（DEBUG = True）
- 敏感信息暴露（`.env` 文件、密钥文件）
- CORS 配置过于宽松（`Access-Control-Allow-Origin: *`）

### g) 其他常见漏洞
- XSS（用户输入未过滤直接输出到 HTML/JS）
- 不安全的随机数生成
- 重放攻击风险（无时间戳/nonce）
- 不安全的跳转（`redirect` 接受用户输入）

## 工作流程（必须按顺序执行）

### 阶段一：项目概览（1-2 轮）
1. 使用 `list_files` 查看根目录，识别主要目录和关键文件（如 `package.json`, `requirements.txt`, `go.mod`）。
2. 读取包管理文件，确定技术栈（语言、框架、依赖）。

### 阶段二：深度遍历与风险挖掘（8-15 轮）
3. 依次遍历所有关键代码目录，使用 `list_files` 获取文件列表。
4. 对每个疑似风险文件（如路由、控制器、工具类），使用 `read_file` 读取内容（可限制行数）。
5. 对特定模式（如 `eval`, `exec`, `subprocess`）使用 `search_code` 进行项目级搜索。
6. **每当发现符合高风险模式的具体代码行**，立即构造风险点并调用 `push_risk_point_to_queue`。
   - 必须包含：`file_path`（相对路径）、`line_start`（行号）、`description`（简述风险）、`severity`（高危/中危等）、`vulnerability_type`（如 `sql_injection`）、`confidence`（置信度，0~1）。
   - 可参考队列状态避免重复推送。
   
### 阶段三：收尾（1 轮）
7. 确认已覆盖所有主要目录，并尽可能推送了所有识别到的风险点。
8. 输出 Final Answer，简要总结扫描结果（如“共推送 X 个风险点”），无需重复列出风险点（已在队列中）。

## ⚠️ 输出格式

**禁止使用 Markdown 格式标记！** 你的输出必须是纯文本格式：
```
Thought: [分析当前情况，计划下一步行动]
Action: [工具名称]
Action Input: { "参数名": "参数值" }
```

✅ 正确格式：
```
Thought: 我需要查看项目结构来了解项目组成
Action: list_files
Action Input: {"directory": "."}
```

当所有风险点推送完毕，输出最终结论：
Thought: 已完成所有侦察工作，共推送 N 个风险点。
Final Answer: 侦察任务完成，已将所有识别的风险点推入队列。

## 防止幻觉（重要！）
- 仅当通过 `read_file` 实际读取了某文件的某行代码后，才能将该行作为风险点推送。
- 推送的行号必须真实对应代码内容，禁止凭空捏造。
- 如果通过 `search_code` 匹配到某行，建议再用 `read_file` 确认上下文，避免误报。
- 不要因为项目是“常见类型”就假设存在典型漏洞文件（如 `routes.py` 不一定存在），一切以实际文件为准。

## 示例交互
```bash
Thought: 我需要先查看项目根目录，了解基本结构。
Action: list_files
Action Input: { "directory": "." }

Observation: ["src/", "tests/", "requirements.txt", "README.md"]

Thought: 发现 requirements.txt，读取它确定依赖。
Action: read_file
Action Input: { "file_path": "requirements.txt" }

Observation: Flask==2.0.1, SQLAlchemy==1.4.27, ...

Thought: 这是 Flask 项目，需要深入 src/ 目录查找路由和数据库操作。
Action: list_files
Action Input: { "directory": "src" }

Observation: ["app.py", "auth.py", "models.py", "utils.py"]

Thought: 读取 app.py 查看路由定义，可能存在未经验证的入口。
Action: read_file
Action Input: { "file_path": "src/app.py", "max_lines": 100 }

Observation: (文件内容) ... @app.route('/login', methods=['POST']) def login(): ...

Thought: 发现登录接口，检查是否存在速率限制或 SQL 注入风险。继续读取 auth.py。
Action: read_file
Action Input: { "file_path": "src/auth.py" }

Observation: ... cursor.execute(f"SELECT * FROM users WHERE username = '{username}'") ...

Thought: 检测到 SQL 查询直接拼接用户输入，存在注入风险。推送风险点。
Action: push_risk_point_to_queue
Action Input: {
    "file_path": "src/auth.py",
    "line_start": 42,
    "description": "SQL 查询直接拼接用户输入的用户名，可能导致 SQL 注入",
    "severity": "high",
    "vulnerability_type": "sql_injection",
    "confidence": 0.95
}

... (持续扫描并推送其他风险点) ...

Thought: 已遍历所有主要目录，共推送 27 个风险点。
Final Answer: 侦察任务完成，已将所有识别的风险点推入队列。
```

请严格按照此流程执行，确保项目侦察全面、风险点推送准确。
"""

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
            max_iterations=25,  # 🔥 增加迭代次数以支持全面侦查
            system_prompt=full_system_prompt,
        )
        super().__init__(config, llm_service, tools, event_emitter)
        
        self._conversation_history: List[Dict[str, str]] = []
        self._steps: List[ReconStep] = []
        self._recon_queue_snapshot: Dict[str, Any] = {}
        # 上下文压缩追踪
        self._files_read: List[str] = []
        self._risk_points_pushed: List[Dict[str, Any]] = []
        self._history_compressed_at: List[int] = []
    
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
            description = f"潜在风险点，来自 {file_path}:{line_start}"
        severity = str(candidate.get("severity") or "high").lower()
        if severity not in {"critical", "high", "medium", "low", "info"}:
            severity = "high"
        vuln_type = str(candidate.get("vulnerability_type") or candidate.get("type") or "potential_issue").lower()
        confidence = None
        try:
            confidence = float(candidate.get("confidence") or 0.6)
        except Exception:
            confidence = 0.6
        return {
            "file_path": file_path,
            "line_start": line_start,
            "description": description,
            "severity": severity,
            "vulnerability_type": vuln_type,
            "confidence": max(0.0, min(1.0, confidence)),
        }

    def _parse_risk_area(self, area: str) -> Optional[Dict[str, Any]]:
        text = str(area or "").strip()
        if not text:
            return None
        description = text
        file_path = ""
        line_start = 1
        if ":" in text:
            candidate, rest = text.split(":", 1)
            candidate = candidate.strip()
            if "." in candidate or "/" in candidate:
                file_path = candidate
                rest = rest.strip()
                parts = rest.split("-", 1)
                line_part = parts[0].strip().split()[0] if parts else ""
                if line_part.isdigit():
                    line_start = int(line_part)
                description = rest if rest else text
        if not file_path:
            return None
        vuln_type = self._infer_vulnerability_type(description)
        return {
            "file_path": file_path,
            "line_start": line_start,
            "description": description,
            "severity": "high",
            "vulnerability_type": vuln_type,
            "confidence": 0.6,
        }

    def _infer_vulnerability_type(self, text: str) -> str:
        lowered = text.lower()
        if any(keyword in lowered for keyword in ["sql", "query", "injection"]):
            return "sql_injection"
        if any(keyword in lowered for keyword in ["xss", "html", "innerhtml"]):
            return "xss"
        if any(keyword in lowered for keyword in ["command", "exec", "subprocess", "system"]):
            return "command_injection"
        if any(keyword in lowered for keyword in ["path", "traversal"]):
            return "path_traversal"
        if "ssrf" in lowered:
            return "ssrf"
        if any(keyword in lowered for keyword in ["secret", "key", "token", "env"]):
            return "hardcoded_secret"
        return "potential_issue"

    def _extract_risk_points(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        points: List[Dict[str, Any]] = []
        seen: set[tuple[str, int, str]] = set()
        if isinstance(result.get("initial_findings"), list):
            for item in result.get("initial_findings", []):
                normalized = self._normalize_risk_point(item)
                if not normalized:
                    continue
                key = (normalized["file_path"], normalized["line_start"], normalized["description"])
                if key in seen:
                    continue
                seen.add(key)
                points.append(normalized)
        high_risk = result.get("high_risk_areas", [])
        if isinstance(high_risk, list):
            for area in high_risk:
                parsed = self._parse_risk_area(area)
                if not parsed:
                    continue
                key = (parsed["file_path"], parsed["line_start"], parsed["description"])
                if key in seen:
                    continue
                seen.add(key)
                points.append(parsed)
        return points

    def _ensure_risk_points(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        points = result.get("risk_points")
        if isinstance(points, list) and points:
            return points
        extracted = self._extract_risk_points(result)
        result["risk_points"] = extracted
        return extracted

    async def _push_risk_points_to_queue(self, risk_points: List[Dict[str, Any]]):
        if not risk_points:
            return
        if "push_risk_point_to_queue" not in self.tools:
            return
        for point in risk_points:
            tool_input = {
                "file_path": point["file_path"],
                "line_start": point["line_start"],
                "description": point["description"],
                "severity": point.get("severity", "high"),
                "confidence": point.get("confidence", 0.6),
                "vulnerability_type": point.get("vulnerability_type", "potential_issue"),
            }
            try:
                await self.execute_tool("push_risk_point_to_queue", tool_input)
            except Exception as exc:
                logger.warning("[Recon] Risk queue push failed: %s", exc)

    async def _refresh_recon_queue_status(self):
        if "get_recon_risk_queue_status" not in self.tools:
            self._recon_queue_snapshot = {}
            return
        observation = await self.execute_tool("get_recon_risk_queue_status", {})
        parsed = self._parse_tool_output(observation)
        if isinstance(parsed, dict):
            self._recon_queue_snapshot = parsed
        else:
            self._recon_queue_snapshot = {"raw": observation}

    async def _sync_recon_queue(self, result: Dict[str, Any]):
        if not isinstance(result, dict):
            return
        risk_points = self._ensure_risk_points(result)
        await self._push_risk_points_to_queue(risk_points)
        await self._refresh_recon_queue_status()
        result["recon_queue_status"] = self._recon_queue_snapshot
    
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
        self._empty_retry_count = 0
        targeted_empty_recovery_used = False
        
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
            initial_message += f"""⚠️ **部分文件审计模式**: 用户指定了 {len(target_files)} 个目标文件进行审计：
"""
            for tf in target_files[:10]:
                initial_message += f"- {tf}\n"
            if len(target_files) > 10:
                initial_message += f"- ... 还有 {len(target_files) - 10} 个文件\n"
            initial_message += """
虽然用户指定了目标文件，但你仍需要：
1. 查看项目整体结构（使用 list_files 查看根目录和主要目录）
2. 读取配置文件和包管理文件，识别技术栈
3. 重点分析指定的目标文件
4. 发现并标记所有高风险区域（不限于目标文件）
"""
        else:
            initial_message += """🎯 **完整项目审计模式**（推荐）

你需要对整个项目进行全面深入的侦查：

### 必须完成的侦查任务：
1. **遍历主要目录**：使用 list_files 查看 src/, app/, api/, lib/, utils/, config/ 等目录
2. **读取关键文件**：包管理文件（requirements.txt, package.json 等）、配置文件、入口文件
3. **识别技术栈**：准确识别语言、框架、数据库、第三方库
4. **发现入口点**：HTTP路由、API端点、CLI命令、后台任务等
5. **挖掘风险区域**：主动搜索认证、数据库操作、文件处理、命令执行等高风险代码

### 侦查深度要求：
- 至少调用 **8-12 个工具**进行充分覆盖
- 必须使用 search_code 搜索高风险模式（exec, eval, subprocess, sql, password 等）
- 输出至少 **10-30 个具体的高风险区域**（格式：文件路径:行号 - 描述）
"""
        
        if exclude_patterns:
            initial_message += f"\n⚠️ 排除模式: {', '.join(exclude_patterns[:5])}\n"
        
        initial_message += f"""
## 任务上下文
{task_context or task or '进行全面深入的项目信息收集和风险侦查，为安全审计提供完整的项目画像。'}

## 可用工具
{self.get_tools_description()}

## 🎯 开始侦查！

请按照以下策略开始你的侦查工作：

**第1步**：使用 list_files 查看根目录，了解项目整体结构
**第2步**：读取包管理文件（requirements.txt, package.json 等），识别技术栈
**第3步**：遍历主要代码目录（src/, app/, api/ 等）
**第4步**：读取入口文件和路由文件
**第5步**：使用 search_code 搜索高风险代码模式
**第6-10步**：继续深入分析和风险挖掘

记住：不要只输出 Thought，必须立即执行 Action！"""

        # 初始化对话历史
        self._conversation_history = [
            {"role": "system", "content": self.config.system_prompt},
            {"role": "user", "content": initial_message},
        ]
        
        self._steps = []
        # 重置上下文压缩追踪
        self._files_read = []
        self._risk_points_pushed = []
        self._history_compressed_at = []
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

                # 🗜️ 上下文压缩：对话历史超过 20 条时自动压缩
                if self._should_compress_history():
                    self._compress_history()
                    await self.emit_event(
                        "info",
                        f"🗜️ 对话历史已压缩（迭代={self._iteration}，"
                        f"已读文件={len(self._files_read)}，"
                        f"已推送风险点={len(self._risk_points_pushed)}）",
                    )
                
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
                                "content": f"Observation:\n{self._prepare_observation_for_history(observation)}",
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
                        # 📌 追踪已读文件和已推送风险点
                        ai = step.action_input or {}
                        if step.action == "read_file" and ai.get("file_path"):
                            fp = str(ai["file_path"]).strip()
                            if fp and fp not in self._files_read:
                                self._files_read.append(fp)
                        elif step.action == "push_risk_point_to_queue" and ai.get("file_path"):
                            self._risk_points_pushed.append({
                                "file_path": str(ai.get("file_path", "")),
                                "line_start": ai.get("line_start", 1),
                                "description": str(ai.get("description", ""))[:200],
                                "severity": str(ai.get("severity", "high")),
                                "vulnerability_type": str(ai.get("vulnerability_type", "unknown")),
                            })
                    
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
                await self._sync_recon_queue(final_result)
            
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

    # ──────────────────────────────────────────────────────────────
    # 上下文压缩 (Context Compression)
    # ──────────────────────────────────────────────────────────────

    _COMPRESS_THRESHOLD = 20   # 对话消息条数超过此值时触发压缩
    _COMPRESS_KEEP_RECENT = 4  # 压缩后在末尾保留的最近消息数

    def _should_compress_history(self) -> bool:
        """当对话历史条数超过阈值时返回 True。
        每次压缩后历史会缩短，因此自然地不会立刻再次触发。
        """
        return len(self._conversation_history) > self._COMPRESS_THRESHOLD

    def _build_context_summary_message(self) -> str:
        """根据已追踪的信息构建紧凑摘要，用于替换历史中的中间片段。"""
        lines = [
            "[系统: 以下是本次侦察到目前为止收集的关键信息摘要，对话历史已压缩。]",
            "",
        ]

        # 已读取的文件
        if self._files_read:
            lines.append(f"## 已读取文件（共 {len(self._files_read)} 个）")
            for f in self._files_read[:30]:
                lines.append(f"  - {f}")
            if len(self._files_read) > 30:
                lines.append(f"  ... 还有 {len(self._files_read) - 30} 个文件")
            lines.append("")

        # 已推送的风险点
        if self._risk_points_pushed:
            lines.append(f"## 已推送风险点（共 {len(self._risk_points_pushed)} 个）")
            for rp in self._risk_points_pushed[:25]:
                sev   = rp.get("severity", "?")
                vtype = rp.get("vulnerability_type", "?")
                fp    = rp.get("file_path", "?")
                ln    = rp.get("line_start", "?")
                desc  = rp.get("description", "")[:100]
                lines.append(f"  - [{sev}] {fp}:{ln} ({vtype}) — {desc}")
            if len(self._risk_points_pushed) > 25:
                lines.append(f"  ... 还有 {len(self._risk_points_pushed) - 25} 个")
            lines.append("")

        # 技术栈（从步骤中提取）
        partial = self._summarize_from_steps()
        tech = partial.get("tech_stack", {})
        langs = tech.get("languages", [])
        fwks  = tech.get("frameworks", [])
        dbs   = tech.get("databases", [])
        if langs or fwks or dbs:
            lines.append("## 识别到的技术栈")
            if langs:
                lines.append(f"  - 语言: {', '.join(langs)}")
            if fwks:
                lines.append(f"  - 框架: {', '.join(fwks)}")
            if dbs:
                lines.append(f"  - 数据库: {', '.join(dbs)}")
            lines.append("")

        # 最近的分析思路（最后 5 步中有 thought 的）
        recent_thoughts = [s.thought for s in self._steps[-5:] if s.thought]
        if recent_thoughts:
            lines.append("## 最近的分析思路")
            for t in recent_thoughts:
                lines.append(f"  > {t[:200]}")
            lines.append("")

        lines.append(
            "请继续执行侦察任务，基于以上已收集的信息继续深入分析尚未覆盖的区域，"
            "并将新发现的风险点推送到队列。"
        )
        return "\n".join(lines)

    def _compress_history(self) -> None:
        """压缩对话历史。

        策略：
          保留 [0] 系统提示 + [1] 初始用户消息 + 摘要消息 + 最近 N 条消息。
          中间所有历史消息被替换为一条结构化摘要，避免 token 溢出。
        """
        if len(self._conversation_history) <= self._COMPRESS_THRESHOLD:
            return

        system_msg  = self._conversation_history[0]
        initial_msg = self._conversation_history[1] if len(self._conversation_history) > 1 else None
        recent_msgs = self._conversation_history[-self._COMPRESS_KEEP_RECENT:]

        summary_msg = {
            "role": "user",
            "content": self._build_context_summary_message(),
        }

        new_history: List[Dict[str, str]] = [system_msg]
        if initial_msg:
            new_history.append(initial_msg)
        new_history.append(summary_msg)
        new_history.extend(recent_msgs)

        old_len = len(self._conversation_history)
        self._conversation_history = new_history
        self._history_compressed_at.append(self._iteration)
        logger.info(
            "[%s] 历史已压缩: %d → %d 条（iteration=%d，文件=%d，风险点=%d）",
            self.name, old_len, len(self._conversation_history),
            self._iteration, len(self._files_read), len(self._risk_points_pushed),
        )

    # ──────────────────────────────────────────────────────────────

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
        result["risk_points"] = self._extract_risk_points(result)
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
            # "recommended_tools": final_result.get("recommended_tools", {}),
            "recommended_tools": {},  # 🔥 目前不传递工具推荐
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
