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

VERIFICATION_SYSTEM_PROMPT = """你是 DeepAudit 的漏洞验证 Agent，一个自主的安全验证专家。

## 你的角色
你是漏洞验证的大脑，而不是机械验证器。你必须：
1. 理解每个漏洞候选的代码上下文与可利用条件。
2. 自主制定验证策略，不向用户追问“是否继续/如何选择”。
3. 优先编写并执行 Fuzzing Harness 进行动态验证。
4. 给出有证据支撑的真实性判断与影响分析。
5. 输出可复核的 PoC 思路与修复建议。

## 核心理念：Fuzzing Harness（强制优先）
即使项目无法整体运行，也要尽量完成验证：
1. 提取目标函数（`extract_function`）。
2. Mock 依赖（数据库/HTTP/文件系统/危险函数）。
3. 编写测试脚本并构造多组 payload。
4. 用 `run_code` 执行 Harness，基于输出判定。

## 工具优先级
1. 核心：`run_code`、`extract_function`
2. 文件证据：`read_file`（必要时 `search_code`）
3. 沙箱辅助：`sandbox_exec`、`sandbox_http`、`verify_vulnerability`
4. 语言专项：`php_test`/`python_test`/`javascript_test`/`java_test`/`go_test`/`ruby_test`/`shell_test`/`universal_code_test`

## 执行原则（强约束）
1. 只能调用运行时工具白名单中的工具，禁止编造工具名。
2. 必须验证全部候选（来源：`previous_results.findings` 与 `bootstrap_findings` 去重合并），不得新增清单外漏洞。
3. 在输出任何结论或 Final Answer 前，必须先完成至少一次工具调用，并包含代码证据。
4. 首轮必须输出 Action，不允许首轮直接 Final Answer。
5. 如果 `read_file` 证明目标文件不存在，该候选必须判定为 `false_positive`。
6. 如果关键字段缺失且无法补齐证据，按保守策略输出 `false_positive` 或 `likely`，不得强行 `confirmed`。
7. 输出语言必须为简体中文（title/description/suggestion/fix_description/verification_evidence/poc_plan）。
8. 禁止 Markdown 样式的 `**Thought:**`，必须使用纯文本 `Thought:` / `Action:` / `Action Input:` / `Final Answer:`。
9. 不允许“请选择/请确认后继续”等交互漂移语句。

## 真实性与置信度
- verdict: `confirmed` | `likely` | `false_positive`
- confidence_level: `must` | `probably` | `unlikely`
    - `confirmed` 通常对应 `must`
    - `likely` 通常对应 `probably`
    - `false_positive` 通常对应 `unlikely`

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

## Final Answer 要求
每条 finding 至少包含：
- file_path, line_start, line_end
- authenticity/verdict
- reachability
- verification_details 或 verification_evidence
- cwe_id
- suggestion, fix_code
- verification_method

PoC 约束：
- 仅授权场景下输出非武器化步骤；不要输出针对真实系统的攻击性操作指令。"""

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
        verdict = finding.get("verdict") or finding.get("authenticity")
        if isinstance(verdict, str):
            verdict = verdict.strip().lower()
        else:
            verdict = None
        if verdict in {"confirmed", "likely", "false_positive"}:
            return verdict
        confidence = finding.get("confidence", 0.0)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.0
        if finding.get("is_verified") is True:
            return "confirmed"
        if confidence >= 0.8:
            return "likely"
        if confidence <= 0.2:
            return "false_positive"
        return "likely"

    def _normalize_reachability_value(self, value: Any, verdict: str) -> str:
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"reachable", "likely_reachable", "unreachable"}:
                return normalized
        if verdict == "confirmed":
            return "reachable"
        if verdict == "likely":
            return "likely_reachable"
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
        if not file_lines:
            return None, None, None
        start_idx = max(0, min(len(file_lines) - 1, line_start - 1))
        patterns = [
            ("python", re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
            ("javascript", re.compile(r"^\s*(?:export\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
            (
                "c_like",
                re.compile(
                    r"^\s*[A-Za-z_][\w\s\*:&<>]*\s+[*&\s]*([A-Za-z_][A-Za-z0-9_]*)\s*\([^;]*\)\s*\{"
                ),
            ),
        ]
        for idx in range(start_idx, -1, -1):
            line = file_lines[idx]
            stripped = line.strip()
            if not stripped or stripped.startswith(("//", "#")):
                continue
            for lang, pattern in patterns:
                match = pattern.match(line)
                if not match:
                    continue
                name = match.group(1).strip()
                if not name:
                    continue
                start_line = idx + 1
                end_line = start_line
                if lang == "python":
                    indent = len(line) - len(line.lstrip())
                    for cursor in range(idx + 1, len(file_lines)):
                        probe = file_lines[cursor]
                        probe_stripped = probe.strip()
                        if not probe_stripped:
                            continue
                        probe_indent = len(probe) - len(probe.lstrip())
                        if probe_indent <= indent and not probe_stripped.startswith(("@", "#")):
                            break
                        end_line = cursor + 1
                elif "{" in line:
                    balance = line.count("{") - line.count("}")
                    end_line = idx + 1
                    for cursor in range(idx + 1, len(file_lines)):
                        probe = file_lines[cursor]
                        balance += probe.count("{") - probe.count("}")
                        end_line = cursor + 1
                        if balance <= 0:
                            break
                return name, start_line, end_line
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
        if not findings_to_verify:
            return

        for finding in findings_to_verify:
            if not isinstance(finding, dict):
                continue
            existing_name = str(finding.get("function_name") or "").strip()
            if existing_name and existing_name.lower() not in {"unknown", "未知函数"}:
                continue

            file_path, line_start, _line_end = self._normalize_file_location(finding)
            resolved_file_path, _full = self._resolve_file_paths(file_path, project_root)
            request_path = resolved_file_path or file_path
            if not request_path or line_start <= 0:
                continue

            locator_input = {
                "file_path": request_path,
                "line_start": int(line_start),
            }
            locator_output = await self.execute_tool(
                "locate_enclosing_function",
                locator_input,
            )
            payload = self._extract_locator_payload(locator_output)
            if not payload:
                continue
            located = self._extract_function_from_locator_payload(payload, int(line_start))
            if not located:
                continue

            located_name = str(located.get("function") or "").strip()
            if not located_name:
                continue
            finding["function_name"] = located_name
            finding["function_start_line"] = self._safe_int(located.get("start_line"))
            finding["function_end_line"] = self._safe_int(located.get("end_line"))
            finding["function_resolution_method"] = "mcp_symbol_index"
            finding["function_resolution_engine"] = "mcp_symbol_index"
            if located.get("language"):
                finding["function_language"] = located.get("language")
            if located.get("diagnostics") is not None:
                finding["function_resolution_diagnostics"] = located.get("diagnostics")

    def _resolve_function_metadata(
        self,
        finding: Dict[str, Any],
        project_root: Optional[str],
        ast_cache: Dict[str, tuple[Optional[str], Optional[int], Optional[int]]],
        file_cache: Dict[str, List[str]],
        locator: Optional[EnclosingFunctionLocator] = None,
    ) -> Dict[str, Any]:
        file_path, line_start, line_end = self._normalize_file_location(finding)
        resolved_file_path, full_file_path = self._resolve_file_paths(file_path, project_root)

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
                "line_start": line_start,
                "line_end": line_end,
            }

        lines: List[str] = []
        if full_file_path:
            lines = file_cache.get(full_file_path) or []
            if not lines:
                try:
                    lines = Path(full_file_path).read_text(
                        encoding="utf-8",
                        errors="replace",
                    ).splitlines()
                except Exception:
                    lines = []
                file_cache[full_file_path] = lines

        tree_sitter_language: Optional[str] = None
        tree_sitter_diagnostics: Any = None
        if project_root and resolved_file_path and full_file_path and locator:
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
                return {
                    "file_path": resolved_file_path,
                    "function": function_name.strip(),
                    "start_line": located.get("start_line"),
                    "end_line": located.get("end_line"),
                    "resolution_method": located.get("resolution_method") or "python_tree_sitter",
                    "resolution_engine": located.get("resolution_engine") or "python_tree_sitter",
                    "language": located.get("language"),
                    "diagnostics": located.get("diagnostics"),
                    "line_start": line_start,
                    "line_end": line_end,
                }

        if lines:
            regex_name, regex_start, regex_end = self._infer_function_by_regex(
                lines,
                line_start,
            )
            if regex_name:
                return {
                    "file_path": resolved_file_path or file_path,
                    "function": regex_name,
                    "start_line": regex_start,
                    "end_line": regex_end,
                    "resolution_method": "regex_fallback",
                    "resolution_engine": "regex_fallback",
                    "language": tree_sitter_language,
                    "diagnostics": tree_sitter_diagnostics,
                    "line_start": line_start,
                    "line_end": line_end,
                }

        return {
            "file_path": resolved_file_path or file_path,
            "function": None,
            "start_line": None,
            "end_line": None,
            "resolution_method": "missing_enclosing_function",
            "resolution_engine": "missing_enclosing_function",
            "language": tree_sitter_language,
            "diagnostics": tree_sitter_diagnostics,
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

            verdict = self._normalize_verdict(merged)
            reachability = self._normalize_reachability_value(merged.get("reachability"), verdict)
            evidence = (
                merged.get("verification_details")
                or merged.get("verification_evidence")
                or merged.get("evidence")
                or "基于代码上下文与工具输出完成验证。"
            )
            if not function_name:
                verdict = "false_positive"
                reachability = "unreachable"

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
                }
            )
            if not function_name:
                verification_result["validation_reason"] = "missing_enclosing_function"

            structured_title = self._build_structured_title(
                {
                    **merged,
                    "file_path": resolved_file_path or normalized_file_path,
                    "function_name": function_name or "未知函数",
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
                }
            )

        summary = final_answer.get("summary")
        if not isinstance(summary, dict):
            summary = {}
        summary.setdefault("total", len(repaired_findings))
        summary.setdefault("confirmed", len([f for f in repaired_findings if f.get("verdict") == "confirmed"]))
        summary.setdefault("likely", len([f for f in repaired_findings if f.get("verdict") == "likely"]))
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
            "is_vulnerable": true,
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
        执行漏洞验证（逐漏洞 TODO 状态机）。
        """
        import time
        start_time = time.time()

        # 每次 run 都重置会话语义状态，避免重试间状态粘连。
        self._conversation_history = []
        self._steps = []

        previous_results = input_data.get("previous_results", {})
        config = input_data.get("config", {})
        verification_level = str(
            config.get("verification_level", "analysis_with_poc_plan")
        ).strip().lower()
        max_iterations_per_item = max(1, int(config.get("verification_max_iterations_per_item", 6)))
        max_attempts_per_item = max(1, int(config.get("verification_max_attempts_per_item", 2)))
        project_root = input_data.get("project_root")
        if not isinstance(project_root, str) or not project_root.strip():
            project_root = None

        # 🔥 处理交接信息
        handoff = input_data.get("handoff")
        if handoff:
            from .base import TaskHandoff
            if isinstance(handoff, dict):
                handoff = TaskHandoff.from_dict(handoff)
            self.receive_handoff(handoff)

        def _coerce_bootstrap_confidence_numeric(value: Any) -> float:
            if isinstance(value, (int, float)):
                return max(0.0, min(float(value), 1.0))
            if isinstance(value, str):
                text = value.strip().upper()
                if text == "HIGH":
                    return 0.9
                if text == "MEDIUM":
                    return 0.7
                if text == "LOW":
                    return 0.4
                try:
                    return max(0.0, min(float(text), 1.0))
                except Exception:
                    return 0.5
            return 0.5

        def _normalize_seed_severity(value: Any) -> str:
            text = str(value or "").strip().lower()
            if text in {"critical", "high", "medium", "low", "info"}:
                return text
            if text == "error":
                return "high"
            if text == "warning":
                return "medium"
            return "medium"

        def _extract_findings_from_agent_result(data: Any) -> List[Dict[str, Any]]:
            if not isinstance(data, dict):
                return []
            direct = data.get("findings")
            if isinstance(direct, list):
                return [item for item in direct if isinstance(item, dict)]
            nested = data.get("data")
            if isinstance(nested, dict):
                nested_findings = nested.get("findings")
                if isinstance(nested_findings, list):
                    return [item for item in nested_findings if isinstance(item, dict)]
            return []

        def _iter_candidate_findings_sources() -> List[Dict[str, Any]]:
            candidates: List[Dict[str, Any]] = []
            # 1) handoff.context_data.findings / all_findings / bootstrap_findings
            if self._incoming_handoff and isinstance(self._incoming_handoff.context_data, dict):
                for key in ("findings", "all_findings", "bootstrap_findings"):
                    items = self._incoming_handoff.context_data.get(key)
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                candidates.append(item)
            # 2) previous_results.findings / analysis.findings / verification.findings
            if isinstance(previous_results, dict):
                direct = previous_results.get("findings")
                if isinstance(direct, list):
                    for item in direct:
                        if isinstance(item, dict):
                            candidates.append(item)
                for key in ("analysis", "verification"):
                    for item in _extract_findings_from_agent_result(previous_results.get(key)):
                        candidates.append(item)
                items = previous_results.get("bootstrap_findings")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            candidates.append(item)
            # 3) input_data.config.bootstrap_findings（兼容直接调用 VerificationAgent 的情况）
            if isinstance(config, dict):
                items = config.get("bootstrap_findings")
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            candidates.append(item)
            return candidates

        raw_bootstrap_candidates = _iter_candidate_findings_sources()
        findings_to_verify: List[Dict[str, Any]] = []
        for item in raw_bootstrap_candidates:
            if not isinstance(item, dict):
                continue
            mapped = dict(item)
            mapped["severity"] = _normalize_seed_severity(item.get("severity"))
            mapped["confidence"] = _coerce_bootstrap_confidence_numeric(item.get("confidence"))
            findings_to_verify.append(mapped)

        # 去重
        findings_to_verify = self._deduplicate(findings_to_verify)

        # 优先验证高风险项（不改变“仅验证候选列表本身，不新增清单外发现”的强约束）
        severity_weight = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
        findings_to_verify.sort(
            key=lambda f: (
                -severity_weight.get(str(f.get("severity") or "medium").strip().lower(), 2),
                -float(_coerce_bootstrap_confidence_numeric(f.get("confidence"))),
            )
        )

        # 🔥 FIX: 优先处理有明确文件路径的发现，将没有文件路径的发现放到后面
        # 这确保 Analysis 的具体发现优先于 Recon 的泛化描述
        def has_valid_file_path(finding: Dict) -> bool:
            file_path = finding.get("file_path", "")
            return bool(file_path and file_path.strip() and file_path.lower() not in ["unknown", "n/a", ""])

        findings_with_path = [f for f in findings_to_verify if has_valid_file_path(f)]
        findings_without_path = [f for f in findings_to_verify if not has_valid_file_path(f)]

        findings_to_verify = findings_with_path + findings_without_path

        if findings_with_path:
            logger.info(f"[Verification] 优先处理 {len(findings_with_path)} 个有明确文件路径的发现")
        if findings_without_path:
            logger.info(f"[Verification] 还有 {len(findings_without_path)} 个发现需要自行定位文件")

        finding_table = VerificationFindingTable(
            max_rounds=max(1, int(config.get("finding_table_max_rounds", 10))),
            max_items=max(1, int(config.get("finding_table_max_items", 200))),
        )
        candidate_by_fingerprint: Dict[str, Dict[str, Any]] = {}
        for idx, candidate in enumerate(findings_to_verify):
            item = finding_table.add_candidate(
                candidate,
                source="seed",
                index=idx,
                discovered_by="seed_candidates",
            )
            if item is not None:
                candidate_by_fingerprint[item.fingerprint] = dict(candidate)

        finding_table_summary = await self._emit_finding_table_update(
            finding_table,
            "初始化缺陷表：开始上下文收敛",
            round_index=0,
            queue_size=len(finding_table.pending_context_items()),
            newly_discovered_count=0,
        )

        context_round = 0
        while (
            not self.is_cancelled
            and finding_table.pending_context_items()
            and context_round < finding_table.max_rounds
        ):
            context_round += 1
            pending_items = finding_table.pending_context_items()
            newly_discovered_count = 0

            for pending in pending_items:
                source_candidate = dict(candidate_by_fingerprint.get(pending.fingerprint) or {})
                finding_table.mark_context(
                    pending.fingerprint,
                    status="collecting",
                    context_round=context_round,
                    context_bundle=source_candidate,
                )

                file_path, line_start, line_end = self._normalize_file_location(source_candidate)
                resolved_file_path, _full_path = self._resolve_file_paths(file_path, project_root)
                effective_file_path = resolved_file_path or file_path
                if not effective_file_path or line_start <= 0:
                    finding_table.mark_context(
                        pending.fingerprint,
                        status="failed",
                        context_round=context_round,
                        blocked_reason="missing_file_or_line",
                        context_bundle={
                            **source_candidate,
                            "file_path": effective_file_path or file_path,
                            "line_start": max(1, int(line_start or 1)),
                            "line_end": max(1, int(line_end or line_start or 1)),
                        },
                    )
                    continue

                function_name = (
                    str(source_candidate.get("function_name") or "").strip()
                    or self._extract_function_name_from_title(source_candidate.get("title"))
                )
                context_bundle = {
                    **source_candidate,
                    "file_path": effective_file_path,
                    "line_start": max(1, int(line_start)),
                    "line_end": max(int(line_end or line_start), int(line_start)),
                    "function_name": function_name or None,
                }
                finding_table.mark_context(
                    pending.fingerprint,
                    status="ready",
                    context_round=context_round,
                    context_bundle=context_bundle,
                )
                candidate_by_fingerprint[pending.fingerprint] = context_bundle

                discovered = source_candidate.get("discovered_findings")
                if isinstance(discovered, list):
                    for idx, discovered_item in enumerate(discovered):
                        if not isinstance(discovered_item, dict):
                            continue
                        mapped_discovered = dict(discovered_item)
                        mapped_discovered.setdefault("severity", "medium")
                        mapped_discovered.setdefault("confidence", 0.5)
                        added = finding_table.add_candidate(
                            mapped_discovered,
                            source="context_discovery",
                            index=idx,
                            parent_fingerprint=pending.fingerprint,
                            discovered_by="context_collection",
                        )
                        if added is None:
                            continue
                        if added.fingerprint not in candidate_by_fingerprint:
                            candidate_by_fingerprint[added.fingerprint] = mapped_discovered
                            newly_discovered_count += 1

            finding_table_summary = await self._emit_finding_table_update(
                finding_table,
                f"缺陷表上下文收敛轮次 {context_round} 完成",
                round_index=context_round,
                queue_size=len(finding_table.pending_context_items()),
                newly_discovered_count=newly_discovered_count,
            )

        findings_to_verify = []
        for item in finding_table.iter_items():
            candidate = dict(candidate_by_fingerprint.get(item.fingerprint) or {})
            if not isinstance(candidate, dict):
                candidate = {}
            candidate.setdefault("title", item.title)
            candidate.setdefault("file_path", item.file_path)
            candidate.setdefault("line_start", item.line_start)
            candidate.setdefault("line_end", item.line_end)
            candidate.setdefault("function_name", item.function_name)
            candidate.setdefault("vulnerability_type", item.vulnerability_type)
            candidate.setdefault("severity", item.severity)
            if isinstance(item.context_bundle, dict) and item.context_bundle:
                candidate.update(item.context_bundle)
            candidate["_finding_table_fingerprint"] = item.fingerprint
            candidate["_finding_table_context_status"] = item.context_status
            if item.blocked_reason:
                candidate["_finding_table_blocked_reason"] = item.blocked_reason
            findings_to_verify.append(candidate)

        if not findings_to_verify:
            note = "跳过验证：本次候选列表为空。"
            logger.info(f"[Verification] {note}")
            await self.emit_event("info", note)
            self.record_work(note)
            duration_ms = int((time.time() - start_time) * 1000)
            handoff = self.create_handoff(
                to_agent="orchestrator",
                summary=note,
                key_findings=[],
                context_data={
                    "skipped": True,
                    "reason": "no_candidates",
                    "verified_count": 0,
                    "candidate_count": 0,
                    "finding_table_summary": finding_table_summary,
                },
            )
            return AgentResult(
                success=True,
                data={
                    "findings": [],
                    "verified_count": 0,
                    "candidate_count": 0,
                    "note": note,
                    "finding_table_summary": finding_table_summary,
                },
                iterations=0,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
                handoff=handoff,
            )

        try:
            await self._enrich_function_metadata_with_locator(
                findings_to_verify=findings_to_verify,
                project_root=project_root,
            )
        except Exception as exc:
            logger.warning("[Verification] MCP 函数定位预处理失败: %s", exc)

        await self.emit_event("info", f"开始逐漏洞验证 {len(findings_to_verify)} 个候选")
        self.record_work(f"开始逐漏洞验证 {len(findings_to_verify)} 个漏洞候选")

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

        # 初始化时所有候选均标记为未验证，推送给前端未验证面板。
        for todo_item, candidate in zip(todo_items, findings_to_verify):
            await self._emit_unverified_finding_event(
                candidate,
                status="new",
                project_root=project_root,
                verification_todo_id=todo_item.id,
                verification_fingerprint=todo_item.fingerprint,
            )

        run_iteration_count = 0
        provisional_findings: List[Dict[str, Any]] = []
        current_todo_index = 0
        current_todo_id: Optional[str] = None
        last_action: Optional[str] = None
        last_tool_name: Optional[str] = None

        try:
            total_todos = len(todo_items)
            for idx, (todo_item, candidate) in enumerate(zip(todo_items, findings_to_verify), start=1):
                if self.is_cancelled:
                    break

                current_todo_index = idx
                current_todo_id = todo_item.id
                todo_item.status = "running"
                table_fingerprint = str(
                    candidate.get("_finding_table_fingerprint") or todo_item.fingerprint
                ).strip()
                if table_fingerprint:
                    finding_table.mark_verify(
                        table_fingerprint,
                        status="verifying",
                        attempts=todo_item.attempts,
                    )
                await self._emit_verification_todo_update(
                    todo_items,
                    f"开始逐漏洞验证：{idx}/{total_todos} {todo_item.title}",
                    current_index=idx,
                    total_todos=total_todos,
                )
                await self._emit_unverified_finding_event(
                    candidate,
                    status="running",
                    project_root=project_root,
                    verification_todo_id=todo_item.id,
                    verification_fingerprint=todo_item.fingerprint,
                )

                file_path, line_start, line_end = self._normalize_file_location(candidate)
                resolved_file_path, _full_file_path = self._resolve_file_paths(file_path, project_root)
                if resolved_file_path:
                    file_path = resolved_file_path
                severity = str(candidate.get("severity") or "medium").strip().lower()
                confidence = _coerce_bootstrap_confidence_numeric(candidate.get("confidence"))
                function_name = (
                    str(candidate.get("function_name") or "").strip()
                    or self._extract_function_name_from_title(candidate.get("title"))
                )

                final_verdict: Optional[str] = None
                reachability: str = "unreachable"
                blocked_reason: Optional[str] = None
                evidence_blocks: List[str] = []
                harness_observation: str = ""
                remaining_item_iterations = max_iterations_per_item

                for attempt in range(1, todo_item.max_attempts + 1):
                    if self.is_cancelled:
                        break
                    if remaining_item_iterations <= 0:
                        blocked_reason = "iteration_budget_exhausted"
                        break

                    todo_item.attempts = attempt
                    remaining_item_iterations -= 1
                    run_iteration_count += 1
                    self._iteration = run_iteration_count

                    await self.emit_llm_thought(
                        (
                            f"逐漏洞验证 {idx}/{total_todos}（attempt {attempt}/{todo_item.max_attempts}）："
                            "先读取命中代码，再验证所属函数可达性与触发可能性。"
                        ),
                        run_iteration_count,
                    )

                    if not file_path or line_start <= 0:
                        blocked_reason = "missing_file_or_line"
                        evidence_blocks.append("缺少可定位的 file_path/line_start，无法执行代码与流证据验证。")
                        continue

                    read_input = {
                        "file_path": file_path,
                        "start_line": max(1, int(line_start) - 12),
                        "end_line": max(int(line_end or line_start), int(line_start)) + 28,
                        "max_lines": 160,
                    }
                    last_action = "collect_code_evidence"
                    last_tool_name = "read_file"
                    read_observation = await self.execute_tool("read_file", read_input)
                    self._steps.append(
                        VerificationStep(
                            thought=f"读取命中代码用于验证: {file_path}:{line_start}",
                            action="read_file",
                            action_input=read_input,
                            observation=read_observation,
                        )
                    )
                    read_error_reason = self._extract_tool_error_reason(read_observation)
                    todo_item.evidence_refs.append("read_file")
                    if read_observation:
                        evidence_blocks.append(
                            "[代码证据/read_file]\n" + self._shorten_observation(read_observation, 900)
                        )

                    if read_error_reason == "cancelled":
                        break
                    if read_error_reason is not None:
                        blocked_reason = read_error_reason
                        continue

                    extracted_code = ""
                    if function_name:
                        extract_input = {
                            "file_path": file_path,
                            "function_name": function_name,
                            "include_imports": True,
                        }
                        last_action = "extract_target_function"
                        last_tool_name = "extract_function"
                        extract_observation = await self.execute_tool("extract_function", extract_input)
                        self._steps.append(
                            VerificationStep(
                                thought=f"提取目标函数构建 Harness: {function_name}",
                                action="extract_function",
                                action_input=extract_input,
                                observation=extract_observation,
                            )
                        )
                        todo_item.evidence_refs.append("extract_function")
                        if extract_observation:
                            evidence_blocks.append(
                                "[函数提取/extract_function]\n" + self._shorten_observation(extract_observation, 1000)
                            )
                        extract_error = self._extract_tool_error_reason(extract_observation)
                        if extract_error == "cancelled":
                            break
                        if extract_error is None:
                            extracted_code = self._extract_code_block(extract_observation)

                    language = self._infer_language_from_path(file_path)
                    harness_code = self._build_fuzzing_harness(
                        vulnerability_type=str(candidate.get("vulnerability_type") or ""),
                        language=language,
                        function_name=function_name,
                        extracted_code=extracted_code,
                        code_context=read_observation,
                        file_path=file_path,
                        line_start=int(line_start),
                    )

                    run_code_input = {
                        "code": harness_code,
                        "language": language,
                        "timeout": 90,
                        "description": (
                            f"verification harness for {candidate.get('vulnerability_type') or 'unknown'} "
                            f"at {file_path}:{line_start}"
                        ),
                    }
                    last_action = "execute_fuzzing_harness"
                    last_tool_name = "run_code"
                    harness_observation = await self.execute_tool("run_code", run_code_input)
                    self._steps.append(
                        VerificationStep(
                            thought=f"执行 Fuzzing Harness 进行动态验证: {file_path}:{line_start}",
                            action="run_code",
                            action_input=run_code_input,
                            observation=harness_observation,
                        )
                    )
                    todo_item.evidence_refs.append("run_code")
                    if harness_observation:
                        evidence_blocks.append(
                            "[动态验证/run_code]\n" + self._shorten_observation(harness_observation, 1400)
                        )

                    run_error = self._extract_tool_error_reason(harness_observation)
                    if run_error == "cancelled":
                        break
                    if run_error is not None:
                        blocked_reason = "harness_execution_failed"
                        continue

                    harness_positive = self._is_harness_evidence_positive(harness_observation)
                    harness_negative = "[safe]" in str(harness_observation or "").lower()

                    if harness_positive and confidence >= 0.7:
                        final_verdict = "confirmed"
                        reachability = "reachable"
                        break

                    if harness_positive:
                        final_verdict = "likely"
                        reachability = "likely_reachable"
                        break

                    if harness_negative:
                        final_verdict = "false_positive"
                        reachability = "unreachable"
                        blocked_reason = blocked_reason or "no_exploit_signal"
                        break

                    # 无明确阳性信号但有代码证据时，保守给 likely。
                    final_verdict = "likely"
                    reachability = "likely_reachable"
                    blocked_reason = blocked_reason or "insufficient_dynamic_signal"
                    break

                if self.is_cancelled:
                    break

                if not final_verdict:
                    todo_item.status = "false_positive"
                    todo_item.blocked_reason = blocked_reason or "insufficient_evidence"
                    todo_item.final_verdict = "false_positive"
                    final_verdict = "false_positive"
                    reachability = "unreachable"
                    evidence_blocks.append(
                        f"验证受阻：{todo_item.blocked_reason}。已达到单项重试上限 {todo_item.max_attempts}。"
                    )
                elif final_verdict in {"confirmed", "likely"}:
                    todo_item.status = "verified"
                    todo_item.final_verdict = final_verdict
                else:
                    todo_item.status = "false_positive"
                    todo_item.final_verdict = "false_positive"
                    if not todo_item.blocked_reason and blocked_reason:
                        todo_item.blocked_reason = blocked_reason

                if table_fingerprint:
                    finding_table.mark_verify(
                        table_fingerprint,
                        status=(
                            "verified"
                            if todo_item.status == "verified"
                            else "false_positive"
                        ),
                        attempts=todo_item.attempts,
                        blocked_reason=todo_item.blocked_reason,
                        verification_result={
                            "verdict": final_verdict,
                            "reachability": reachability,
                        },
                    )

                evidence_text = "\n\n".join([block for block in evidence_blocks if block]).strip()
                if not evidence_text:
                    evidence_text = "未采集到充分证据，按保守策略降级为 false_positive。"

                line_start_int = self._normalize_int_line(line_start, 1)
                line_end_int = self._normalize_int_line(line_end, line_start_int)
                if line_end_int < line_start_int:
                    line_end_int = line_start_int
                function_trigger_flow = (
                    [self._shorten_observation(harness_observation, 800)]
                    if harness_observation
                    else [f"harness_evidence_unavailable:{todo_item.blocked_reason or 'not_collected'}"]
                )
                root_cause_description = build_cn_structured_description(
                    file_path=file_path,
                    function_name=function_name,
                    vulnerability_type=candidate.get("vulnerability_type"),
                    title=candidate.get("title"),
                    description=candidate.get("description"),
                    code_snippet=candidate.get("code_snippet"),
                    code_context=candidate.get("code_context"),
                    cwe_id=self._infer_cwe_id(candidate),
                    raw_description=evidence_text,
                    line_start=line_start_int,
                    line_end=line_end_int,
                    verification_evidence=evidence_text,
                    function_trigger_flow=function_trigger_flow,
                )
                root_cause_description_markdown = build_cn_structured_description_markdown(
                    file_path=file_path,
                    function_name=function_name,
                    vulnerability_type=candidate.get("vulnerability_type"),
                    title=candidate.get("title"),
                    description=candidate.get("description"),
                    code_snippet=candidate.get("code_snippet"),
                    code_context=candidate.get("code_context"),
                    cwe_id=self._infer_cwe_id(candidate),
                    raw_description=evidence_text,
                    line_start=line_start_int,
                    line_end=line_end_int,
                    verification_evidence=evidence_text,
                    function_trigger_flow=function_trigger_flow,
                )

                provisional = {
                    **candidate,
                    "file_path": file_path,
                    "line_start": line_start_int,
                    "line_end": line_end_int,
                    "function_name": function_name,
                    "description": root_cause_description,
                    "verdict": final_verdict,
                    "authenticity": final_verdict,
                    "reachability": reachability,
                    "is_verified": final_verdict in {"confirmed", "likely"},
                    "verification_details": evidence_text,
                    "verification_evidence": evidence_text,
                    "verification_result": {
                        "authenticity": final_verdict,
                        "verdict": final_verdict,
                        "reachability": reachability,
                        "evidence": evidence_text,
                        "verification_details": evidence_text,
                        "verification_evidence": evidence_text,
                        "todo_id": todo_item.id,
                        "todo_status": todo_item.status,
                        "blocked_reason": todo_item.blocked_reason,
                        "function_trigger_flow": function_trigger_flow,
                    },
                }
                provisional_findings.append(provisional)

                structured_title = self._build_structured_title(provisional)
                severity_text = str(provisional.get("severity") or "medium")
                vuln_type = str(provisional.get("vulnerability_type") or "unknown")

                if final_verdict in {"confirmed", "likely"}:
                    await self.emit_finding(
                        title=structured_title,
                        severity=severity_text,
                        vuln_type=vuln_type,
                        file_path=file_path,
                        line_start=line_start_int,
                        line_end=line_end_int,
                        is_verified=True,
                        display_title=structured_title,
                        cwe_id=self._infer_cwe_id(provisional),
                        description=(
                            str(provisional.get("description"))
                            if provisional.get("description") is not None
                            else None
                        ),
                        description_markdown=root_cause_description_markdown,
                        verification_evidence=evidence_text,
                        code_snippet=(
                            str(provisional.get("code_snippet"))
                            if provisional.get("code_snippet") is not None
                            else None
                        ),
                        code_context=(
                            str(provisional.get("code_context"))
                            if provisional.get("code_context") is not None
                            else None
                        ),
                        finding_scope="verification_queue",
                        verification_todo_id=todo_item.id,
                        verification_fingerprint=todo_item.fingerprint,
                        verification_status="verified",
                        extra_metadata={
                            "status": "verified",
                            "verdict": final_verdict,
                            "authenticity": final_verdict,
                        },
                    )
                else:
                    await self.emit_event(
                        "finding_update",
                        f"[Verification] {structured_title} -> {todo_item.status}",
                        metadata={
                            "title": structured_title,
                            "display_title": structured_title,
                            "severity": severity_text,
                            "vulnerability_type": vuln_type,
                            "file_path": file_path,
                            "line_start": line_start_int,
                            "line_end": line_end_int,
                            "is_verified": False,
                            "status": todo_item.status,
                            "authenticity": "false_positive",
                            "verdict": "false_positive",
                            "verification_evidence": evidence_text,
                            "description": root_cause_description,
                            "description_markdown": root_cause_description_markdown,
                            "blocked_reason": todo_item.blocked_reason,
                            "finding_scope": "verification_queue",
                            "verification_todo_id": todo_item.id,
                            "verification_fingerprint": todo_item.fingerprint,
                            "verification_status": "false_positive",
                        },
                    )

                await self._emit_verification_todo_update(
                    todo_items,
                    (
                        f"完成逐漏洞验证：{idx}/{total_todos} {todo_item.title} "
                        f"-> {todo_item.status}"
                    ),
                    current_index=idx,
                    total_todos=total_todos,
                    last_action=last_action,
                    last_tool_name=last_tool_name,
                )

            duration_ms = int((time.time() - start_time) * 1000)

            if self.is_cancelled:
                todo_summary = self._build_verification_todo_summary(todo_items)
                finding_table_summary = finding_table.summary(
                    round_index=context_round,
                    queue_size=len(finding_table.pending_context_items()),
                    newly_discovered_count=0,
                )
                completed_count = todo_summary.get("verified", 0) + todo_summary.get("false_positive", 0) + todo_summary.get("blocked", 0)
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
                        "last_action": last_action,
                        "last_tool_name": last_tool_name,
                        "todo_scope": "verification",
                        "verification_todo_summary": todo_summary,
                        "finding_table_summary": finding_table_summary,
                    },
                )
                return AgentResult(
                    success=False,
                    error="任务已取消",
                    data={
                        "findings": provisional_findings if provisional_findings else findings_to_verify,
                        "candidate_count": len(findings_to_verify),
                        "verification_todo_summary": todo_summary,
                        "finding_table_summary": finding_table_summary,
                    },
                    iterations=run_iteration_count,
                    tool_calls=self._tool_calls,
                    tokens_used=self._total_tokens,
                    duration_ms=duration_ms,
                )

            repaired_result = self._repair_final_answer(
                {"findings": provisional_findings},
                findings_to_verify,
                verification_level,
                project_root=project_root,
            )
            verified_findings = [
                item for item in repaired_result.get("findings", [])
                if isinstance(item, dict)
            ]

            # 用 TODO 状态机结果回填最终 finding，确保状态语义一致。
            for idx, finding in enumerate(verified_findings):
                if idx >= len(todo_items):
                    continue
                todo_item = todo_items[idx]
                verdict = str(finding.get("verdict") or finding.get("authenticity") or "").strip().lower()
                if todo_item.status == "verified":
                    if verdict not in {"confirmed", "likely"}:
                        verdict = "likely"
                    finding["verdict"] = verdict
                    finding["authenticity"] = verdict
                    finding["is_verified"] = True
                    if verdict == "confirmed":
                        finding["reachability"] = "reachable"
                    elif str(finding.get("reachability") or "").strip().lower() not in {"reachable", "likely_reachable"}:
                        finding["reachability"] = "likely_reachable"
                else:
                    finding["verdict"] = "false_positive"
                    finding["authenticity"] = "false_positive"
                    finding["reachability"] = "unreachable"
                    finding["is_verified"] = False

                verification_payload = (
                    dict(finding.get("verification_result"))
                    if isinstance(finding.get("verification_result"), dict)
                    else {}
                )
                verification_payload["todo_id"] = todo_item.id
                verification_payload["todo_status"] = todo_item.status
                verification_payload["blocked_reason"] = todo_item.blocked_reason
                if todo_item.status == "false_positive" and todo_item.blocked_reason:
                    verification_payload["degraded"] = True
                    verification_payload["degraded_reason"] = todo_item.blocked_reason or "verification_blocked"
                finding["verification_result"] = verification_payload

            confirmed_count = len([f for f in verified_findings if f.get("verdict") == "confirmed"])
            likely_count = len([f for f in verified_findings if f.get("verdict") == "likely"])
            false_positive_count = len([f for f in verified_findings if f.get("verdict") == "false_positive"])
            todo_summary = self._build_verification_todo_summary(todo_items)
            finding_table_summary = finding_table.summary(
                round_index=context_round,
                queue_size=len(finding_table.pending_context_items()),
                newly_discovered_count=0,
            )

            await self.emit_event(
                "info",
                (
                    f"Verification Agent 完成: confirmed={confirmed_count}, "
                    f"likely={likely_count}, false_positive={false_positive_count}, "
                    f"blocked={todo_summary.get('blocked', 0)}"
                ),
                metadata={
                    "todo_scope": "verification",
                    "verification_todo_summary": todo_summary,
                    "finding_table_summary": finding_table_summary,
                },
            )
            await self._emit_verification_todo_update(
                todo_items,
                "逐漏洞验证完成",
                current_index=len(todo_items),
                total_todos=len(todo_items),
                last_action=last_action,
                last_tool_name=last_tool_name,
            )

            handoff = self._create_verification_handoff(
                verified_findings,
                confirmed_count,
                likely_count,
                false_positive_count,
                candidate_count=len(findings_to_verify),
            )
            if isinstance(handoff.context_data, dict):
                handoff.context_data["verification_todo_summary"] = todo_summary
                handoff.context_data["finding_table_summary"] = finding_table_summary

            return AgentResult(
                success=True,
                data={
                    "findings": verified_findings,
                    "verified_count": confirmed_count,
                    "likely_count": likely_count,
                    "false_positive_count": false_positive_count,
                    "candidate_count": len(findings_to_verify),
                    "verified_output_count": len(verified_findings),
                    "summary": {
                        "verification_todo_summary": todo_summary,
                        "finding_table_summary": finding_table_summary,
                    },
                    "verification_todo_summary": todo_summary,
                    "finding_table_summary": finding_table_summary,
                },
                iterations=run_iteration_count,
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
