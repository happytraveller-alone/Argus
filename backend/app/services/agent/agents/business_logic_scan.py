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


BUSINESS_LOGIC_SYSTEM_PROMPT = """你是业务逻辑漏洞扫描子 Agent。

你必须通过 ReAct 模式自主推进，并且只调用工具白名单中的工具。

## 执行要求
1. 你需要按阶段目标分析，但可以灵活选择工具顺序。
2. 每个阶段至少调用 1 次工具后再输出阶段结果。
3. 输出格式必须使用：Thought / Action / Action Input / Final Answer。
4. Final Answer 必须是 JSON。
5. findings 的 title/description/poc_plan/fix_suggestion 使用简体中文。

## 阶段目标
1. HTTP 入口发现：识别路由、控制器与处理函数。
2. 入口功能分析：识别鉴权、权限检查、参数验证。
3. 敏感操作锚点：识别数据更新、权限变更、资金相关操作。
4. 轻量级污点分析：追踪入口参数到敏感操作的数据路径，识别缺失校验。
5. 漏洞确认：输出结构化业务逻辑漏洞 findings。

## 结果 JSON 最低要求
可按阶段输出以下键之一：
- entries
- entry_analysis
- sensitive_operations
- taint_paths
- findings
"""


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
    
    # 类级别的调用缓存：确保整个应用生命周期内只执行一次
    _scan_executed = False
    _cached_result: Optional[Dict[str, Any]] = None
    _scan_lock = asyncio.Lock()

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

    @classmethod
    def reset_cache(cls) -> None:
        """
        重置扫描缓存状态。
        用于测试、调试或需要重新执行扫描的场景。
        """
        cls._scan_executed = False
        cls._cached_result = None
        logger.info("[BusinessLogicScanAgent] 缓存状态已重置，下次调用将重新执行扫描")

    @classmethod
    def is_scan_cached(cls) -> bool:
        """检查是否已有缓存的扫描结果"""
        return cls._scan_executed and cls._cached_result is not None

    @classmethod
    def get_cache_info(cls) -> Dict[str, Any]:
        """获取缓存信息（用于诊断）"""
        if not cls._cached_result:
            return {"cached": False, "reason": "no_cache"}
        
        cached = cls._cached_result
        return {
            "cached": True,
            "success": cached.get("success"),
            "cached_at": cached.get("cached_at"),
            "findings_count": len(cached.get("data", {}).get("findings", [])),
            "total_findings": cached.get("data", {}).get("total_findings", 0),
        }

    async def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """执行业务逻辑扫描 - 仅第一次实际执行，后续调用返回缓存结果"""
        start_time = time.time()
        
        # === 缓存检查机制 ===
        async with self._scan_lock:
            if BusinessLogicScanAgent._scan_executed:
                # 已经执行过，返回缓存结果
                logger.info(
                    "[BusinessLogicScanAgent] 业务逻辑扫描已执行过，返回缓存结果"
                )
                await self.emit_event(
                    "info",
                    "业务逻辑扫描已在本应用会话中执行过，返回之前的缓存结果"
                )
                
                if BusinessLogicScanAgent._cached_result:
                    cached = BusinessLogicScanAgent._cached_result
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
                else:
                    # 标记为执行过但无结果
                    duration_ms = int((time.time() - start_time) * 1000)
                    return AgentResult(
                        success=False,
                        error="业务逻辑扫描已执行，但缓存结果为空",
                        data={"findings": [], "from_cache": True},
                        iterations=0,
                        tool_calls=0,
                        tokens_used=0,
                        duration_ms=duration_ms,
                    )
            
            # 第一次调用，标记为已执行
            BusinessLogicScanAgent._scan_executed = True
            logger.info("[BusinessLogicScanAgent] 首次执行业务逻辑扫描")

        target = str(input_data.get("target") or ".")
        framework_hint = input_data.get("framework_hint")
        entry_points_hint = input_data.get("entry_points_hint") or []
        quick_mode = bool(input_data.get("quick_mode", False))
        max_iterations = int(input_data.get("max_iterations") or self.config.max_iterations)

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

        self.record_work(f"开始业务逻辑扫描: target={target}")

        try:
            for phase in self.phases:
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
                },
                iterations=self._iteration,
                tool_calls=self._tool_calls,
                tokens_used=self._total_tokens,
                duration_ms=duration_ms,
                handoff=handoff,
            )
            
            # === 缓存本次结果供后续调用使用 ===
            BusinessLogicScanAgent._cached_result = {
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
                "[BusinessLogicScanAgent] 业务逻辑扫描完成，结果已缓存。"
                "后续调用将返回此缓存结果。"
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
            BusinessLogicScanAgent._cached_result = {
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
                "[BusinessLogicScanAgent] 业务逻辑扫描执行失败，失败结果已缓存。"
                "后续调用将返回此失败状态。"
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

        if phase.phase_num == 2:
            seed_entries = json.dumps(context.get("discovered_entries", [])[:8], ensure_ascii=False, indent=2)
            return (
                base_prompt
                + f"""
## 目标
分析关键入口的业务逻辑、鉴权和权限检查。

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
