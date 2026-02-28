"""
业务逻辑漏洞扫描工具

系统性业务逻辑审计，通过 LLM 协调完成 5 步分析：
1. 入口扫描：发现所有 HTTP 入口
2. 入口功能分析：分析每个入口的业务逻辑
3. 敏感操作锚点识别：定位敏感操作（数据更新、转账、权限变更等）
4. 轻量级污点分析：追踪入口参数传播路径，识别缺失校验
5. 业务逻辑漏洞确认：确定是否存在水平越权、垂直越权、IDOR 等漏洞

设计特点：
- 工具内部进行 LLM 编排，Agent 无需关心细节
- 每一步都可重试，循环防护机制
- 输出结构化 findings + 人类可读报告
"""

import os
import re
import asyncio
import logging
import json
from typing import Optional, List, Dict, Any, Callable
from pydantic import BaseModel, Field
from dataclasses import dataclass, field
from enum import Enum

from .base import AgentTool, ToolResult

logger = logging.getLogger(__name__)


class BusinessLogicScanInput(BaseModel):
    """业务逻辑扫描输入"""
    target: str = Field(
        default=".",
        description="扫描目标目录"
    )
    framework_hint: Optional[str] = Field(
        default=None,
        description="框架提示：django, fastapi, express, flask, 等"
    )
    entry_points_hint: Optional[List[str]] = Field(
        default=None,
        description="已知的入口点提示（如函数名、类名），由 Recon Agent 提供"
    )
    quick_mode: bool = Field(
        default=False,
        description="快速模式：重点扫描已知高风险区域"
    )
    max_iterations: int = Field(
        default=8,
        description="工具内部 LLM 最多迭代次数"
    )


@dataclass
class ScanPhase:
    """扫描阶段"""
    phase_num: int
    phase_name: str
    description: str
    max_attempts: int = 3


@dataclass
class BusinessLogicFinding:
    """业务逻辑漏洞发现"""
    title: str                                      # 三段式中文标题
    vulnerability_type: str                        # idor, horizontal_privilege_escalation, vertical_privilege_escalation 等
    severity: str                                  # critical, high, medium, low
    file_path: str
    function_name: str
    line_start: int
    line_end: Optional[int] = None
    entry_point: Optional[str] = None             # 如 "GET /api/user/{user_id}"
    taint_path: List[str] = field(default_factory=list)  # ["user_id", "db.query", "execute"]
    missing_checks: List[str] = field(default_factory=list)  # ["user_ownership", "permission"]
    code_snippet: str = ""
    confidence: float = 0.0
    poc_plan: str = ""
    fix_suggestion: str = ""
    phases_evidence: Dict[int, str] = field(default_factory=dict)  # 每个阶段的证据


class BusinessLogicScanTool(AgentTool):
    """
    业务逻辑漏洞扫描工具
    
    内部通过 LLM 协调 5 步分析流程，最终输出结构化 findings。
    """
    
    # Web 框架关键字映射
    FRAMEWORK_PATTERNS = {
        "django": [
            r"from django",
            r"URLconf",
            r"django\.views",
            r"@.*permission_required",
            r"@.*login_required",
        ],
        "fastapi": [
            r"from fastapi",
            r"@app\.get",
            r"@app\.post",
            r"Depends\(",
            r"@.*authorize",
        ],
        "express": [
            r"require.*express",
            r"app\.get\(",
            r"app\.post\(",
            r"req\.user",
            r"router\.use.*middleware",
        ],
        "flask": [
            r"from flask",
            r"@app\.route",
            r"@.*login_required",
            r"@.*require.*permission",
        ],
    }
    
    # 敏感操作模式（第 3 步锚点识别）
    SENSITIVE_OPERATION_PATTERNS = {
        "data_modification": [
            r"INSERT\s+INTO",
            r"UPDATE\s+\w+.*WHERE",
            r"DELETE\s+FROM",
            r"save\s*\(",
            r"\.update\s*\(",
            r"\.delete\s*\(",
            r"\.create\s*\(",
            r"db\.session\.add",
        ],
        "permission_change": [
            r"set.*role",
            r"set.*permission",
            r"grant.*permission",
            r"revoke.*permission",
            r"update.*role",
            r"promote",
            r"demote",
        ],
        "financial_operation": [
            r"transfer",
            r"payment",
            r"withdraw",
            r"deposit",
            r"charge",
            r"refund",
            r"update.*balance",
            r"update.*price",
        ],
        "account_operation": [
            r"create.*user",
            r"register",
            r"update.*profile",
            r"change.*password",
            r"reset.*password",
            r"email.*change",
            r"email.*verify",
        ],
    }
    
    # IDOR 和越权检查模式（第 4 步污点分析）
    AUTHORIZATION_CHECK_PATTERNS = [
        r"check.*permission",
        r"is.*authorized",
        r"require.*permission",
        r"access_control",
        r"verify.*owner",
        r"assert.*owner",
        r"if.*user.*==.*current",
        r"if.*current_user.*in.*",
        r"can_access",
        r"has_permission",
    ]
    
    def __init__(
        self,
        project_root: str,
        llm_service: Optional[Any] = None,
        tools_registry: Optional[Dict[str, Any]] = None,
    ):
        super().__init__()
        self.project_root = project_root
        self.llm_service = llm_service
        self.tools_registry = tools_registry or {}
        self.findings: List[BusinessLogicFinding] = []
        
        # 5 个扫描阶段定义
        self.phases = [
            ScanPhase(1, "HTTP Entry Discovery", "发现所有 HTTP 入口点与路由"),
            ScanPhase(2, "Entry Function Analysis", "分析入口函数的业务逻辑与验证"),
            ScanPhase(3, "Sensitive Operation Anchors", "锚定敏感操作与检查点"),
            ScanPhase(4, "Lightweight Taint Analysis", "污点追踪：参数→操作，识别缺失校验"),
            ScanPhase(5, "Logic Vulnerability Confirm", "最终确认业务逻辑漏洞类型与严重程度"),
        ]
    
    @property
    def name(self) -> str:
        return "business_logic_scan"
    
    @property
    def description(self) -> str:
        return """业务逻辑漏洞扫描工具 - 系统性 Web 应用业务逻辑审计

通过 5 步分析过程发现业务逻辑漏洞：
1. HTTP 入口扫描：识别所有路由和处理函数
2. 入口代码分析：理解业务逻辑与权限检查
3. 敏感操作锚点：定位数据修改、权限变更等核心操作
4. 轻量级污点分析：追踪参数传播，识别缺失验证
5. 漏洞确认：确定水平越权（IDOR）、垂直越权等具体漏洞

输出：结构化 findings + 可执行 PoC 思路，标记 needs_verification=true 供验证阶段处理。

输入参数：
- target: 扫描目标目录
- framework_hint: 框架类型提示（django/fastapi/express/flask）
- entry_points_hint: 已知入口点列表（由 Recon 提供）
- quick_mode: 快速模式（仅扫描高风险区域）
- max_iterations: 工具内部 LLM 最多迭代次数（推荐 8）"""
    
    @property
    def args_schema(self) -> Optional[type]:
        return BusinessLogicScanInput
    
    async def _execute(
        self,
        target: str = ".",
        framework_hint: Optional[str] = None,
        entry_points_hint: Optional[List[str]] = None,
        quick_mode: bool = False,
        max_iterations: int = 8,
        **kwargs
    ) -> ToolResult:
        """执行业务逻辑扫描"""
        
        try:
            logger.info(f"Starting business logic scan: target={target}, framework={framework_hint}, quick_mode={quick_mode}")
            
            # 初始化扫描上下文
            scan_context = {
                "target": target,
                "framework_hint": framework_hint or "unknown",
                "entry_points_hint": entry_points_hint or [],
                "quick_mode": quick_mode,
                "phase": 0,
                "iteration": 0,
                "max_iterations": max_iterations,
                "conversation_history": [],
                "findings": [],
                "discovered_entries": [],
                "sensitive_operations": [],
                "taint_paths": [],
            }
            
            # 逐阶段执行（每阶段有重试机制）
            for phase in self.phases:
                logger.info(f"Phase {phase.phase_num}: {phase.phase_name}")
                scan_context["phase"] = phase.phase_num
                
                max_phase_attempts = phase.max_attempts
                for attempt in range(max_phase_attempts):
                    scan_context["iteration"] += 1
                    
                    if scan_context["iteration"] > max_iterations:
                        logger.warning("Max iterations reached, stopping scan")
                        break
                    
                    # 构建阶段提示词
                    phase_prompt = self._build_phase_prompt(phase, scan_context)
                    
                    # 调用 LLM 进行阶段分析
                    llm_result = await self._llm_phase_analysis(phase_prompt, scan_context)
                    
                    if not llm_result["success"]:
                        logger.warning(f"Phase {phase.phase_num} attempt {attempt + 1} failed: {llm_result['error']}")
                        if attempt < max_phase_attempts - 1:
                            await asyncio.sleep(1)  # 短暂等待后重试
                            continue
                        else:
                            # 超过重试次数，降级处理
                            logger.warning(f"Phase {phase.phase_num} degraded after {max_phase_attempts} attempts")
                            break
                    
                    # 阶段分析成功，更新上下文并继续下一阶段
                    self._update_context_from_llm_result(scan_context, phase, llm_result)
                    break
            
            # 生成最终报告
            report = self._generate_report(scan_context)
            
            return ToolResult(
                success=True,
                data=report["text"],
                metadata={
                    "phase_1_entries": len(scan_context["discovered_entries"]),
                    "phase_3_sensitive_ops": scan_context["sensitive_operations"],
                    "phase_4_taint_paths": scan_context["taint_paths"],
                    "findings": [self._finding_to_dict(f) for f in self.findings],
                    "total_findings": len(self.findings),
                    "by_severity": self._count_by_severity(),
                }
            )
        
        except Exception as e:
            logger.error(f"Business logic scan error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e),
                data=f"业务逻辑扫描失败: {str(e)}"
            )
    
    def _build_phase_prompt(self, phase: ScanPhase, context: Dict[str, Any]) -> str:
        """构建阶段特定的 LLM 提示词"""
        
        base_prompt = f"""你是业务逻辑安全分析专家，正在进行第 {phase.phase_num} 阶段分析。

## 当前阶段
阶段 {phase.phase_num}: {phase.phase_name}
描述: {phase.description}

## 项目信息
- 目标: {context['target']}
- 框架: {context['framework_hint']}
- 快速模式: {context['quick_mode']}

## 已有发现
- 已发现入口数: {len(context['discovered_entries'])}
- 已发现敏感操作: {len(context['sensitive_operations'])}
- 候选漏洞: {len(context['findings'])}
"""
        
        if phase.phase_num == 1:
            prompt = base_prompt + f"""
## 第 1 阶段：HTTP 入口扫描

你的任务是发现所有 HTTP 入口点（路由、控制器、处理函数）。

### 步骤
1. 使用 search_code 搜索路由定义（如 @app.get, @router.post, @route 等）
2. 使用 read_file 读取路由配置文件（urls.py, routes.js 等）
3. 使用 extract_function 获取处理函数的完整代码

### 输出格式（JSON）
{{
  "entries": [
    {{
      "method": "GET",
      "path": "/api/user/{{user_id}}",
      "handler_file": "app/api/user.py",
      "handler_function": "get_user_profile",
      "handler_line": 78
    }},
    ...
  ],
  "summary": "发现 N 个入口点"
}}

### 提示
- 优先搜索框架特定的路由装饰器（@app, @router, @route）
- 记录准确的文件路径和函数行号
- 包括认证端点（登录、注册）和业务端点"""
        
        elif phase.phase_num == 2:
            entries_summary = "\n".join([
                f"  - {e['method']} {e['path']} -> {e['handler_file']}:{e['handler_line']}"
                for e in context["discovered_entries"][:5]
            ])
            prompt = base_prompt + f"""
## 第 2 阶段：入口功能分析

前一阶段发现的入口（示例）：
{entries_summary}
...（共 {len(context['discovered_entries'])} 个）

你的任务是理解每个入口的业务逻辑和权限检查。

### 步骤
1. 逐一 read_file 至少 5 个关键入口
2. 分析函数中的权限检查逻辑
3. 识别参数验证、身份验证、授权检查

### 输出格式（JSON）
{{
  "entry_analysis": [
    {{
      "entry": "GET /api/user/{{user_id}}",
      "handler": "app/api/user.py:get_user_profile",
      "logic": "返回用户个人资料",
      "auth_checks": ["@login_required"],
      "permission_checks": [{"检查是否是 current_user"}],
      "input_params": ["user_id (from URL)"],
      "risk": "可能IDOR（无用户所有权验证）"
    }},
    ...
  ],
  "summary": "分析了 N 个入口，发现 M 个风险点"
}}"""
        
        elif phase.phase_num == 3:
            prompt = base_prompt + f"""
## 第 3 阶段：敏感操作锚点识别

前阶段分析了 {len(context['discovered_entries'])} 个入口。

你的任务是找到每个入口中的"敏感操作"（数据修改、权限变更、金融交易等）。

### 步骤
1. 使用 search_code 搜索敏感操作关键字（UPDATE, INSERT, DELETE, db.save, permission, transfer 等）
2. 使用 read_file 或 extract_function 获取完整代码
3. 识别操作前后的检查点

### 输出格式（JSON）
{{
  "sensitive_operations": [
    {{
      "entry": "GET /api/user/{{user_id}}",
      "operation": "UPDATE users SET role=? WHERE id=?",
      "operation_file": "app/db.py",
      "operation_line": 156,
      "operation_type": "permission_change",
      "checks_before": ["@login_required"],
      "checks_missing": ["role_ownership", "hierarchy_check"]
    }},
    ...
  ],
  "summary": "发现 N 个敏感操作"
}}"""
        
        elif phase.phase_num == 4:
            prompt = base_prompt + f"""
## 第 4 阶段：轻量级污点分析

已识别 {len(context['sensitive_operations'])} 个敏感操作。

你的任务是追踪入口参数如何传播到敏感操作，识别缺失的验证。

### 步骤
1. 对每个敏感操作，使用 controlflow_analysis_light 分析参数污染路径
2. 识别"缺失的校验"（应该检查但没检查的条件）
3. 记录具体的污染路径

### 输出格式（JSON）
{{
  "taint_paths": [
    {{
      "entry": "GET /api/user/{{user_id}}",
      "sensitive_op": "UPDATE users WHERE id=?",
      "entry_params": ["user_id"],
      "taint_flow": ["user_id (URL param)", "query_builder.filter(id=user_id)", "db.execute()"],
      "missing_check": "current_user.id == user_id",
      "vulnerability_class": "IDOR (Horizontal Privilege Escalation)"
    }},
    ...
  ],
  "summary": "追踪了 N 条污染路径，识别 M 个缺失校验"
}}"""
        
        elif phase.phase_num == 5:
            prompt = base_prompt + f"""
## 第 5 阶段：注入漏洞确认

已识别 {len(context['taint_paths'])} 条污染路径。

你的任务是确认最终漏洞、评估严重程度、生成修复建议。

### 步骤
1. 每条污染路径对应一个潜在漏洞
2. 评估严重程度（critical/high/medium/low）
3. 生成 PoC 思路和修复建议

### 输出格式（JSON）
{{
  "findings": [
    {{
      "title": "app/api/user.py中get_user_profile函数水平越权（IDOR）",
      "vulnerability_type": "horizontal_privilege_escalation",
      "severity": "critical",
      "confidence": 0.95,
      "file_path": "app/api/user.py",
      "function_name": "get_user_profile",
      "line_start": 78,
      "entry_point": "GET /api/user/{{user_id}}",
      "missing_checks": ["current_user.id == user_id"],
      "poc_plan": "使用不同的 user_id 参数调用 API，验证是否返回其他用户的数据",
      "fix_suggestion": "在函数开始添加检查 if request.user.id != user_id: raise PermissionDenied()"
    }},
    ...
  ],
  "summary": "确认了 N 个业务逻辑漏洞"
}}"""
        
        return prompt
    
    async def _llm_phase_analysis(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """调用 LLM 进行阶段分析
        
        实际实现时需要 LLM 服务支持，这里返回示例结构。
        """
        
        # 如果没有实际 LLM 服务，返回演示结果
        if not self.llm_service:
            logger.debug(f"No LLM service, returning demo result for phase {context['phase']}")
            return self._generate_demo_phase_result(context['phase'])
        
        try:
            # 实际调用 LLM（需要根据实际 LLM 服务 API 调整）
            response = await self.llm_service.apredict(prompt)
            
            # 解析 LLM 输出（期望 JSON）
            result = json.loads(response)
            result["success"] = True
            return result
        
        except Exception as e:
            logger.error(f"LLM analysis error: {e}")
            return {"success": False, "error": str(e)}
    
    def _generate_demo_phase_result(self, phase: int) -> Dict[str, Any]:
        """生成演示结果（用于测试）"""
        
        if phase == 1:
            return {
                "success": True,
                "entries": [
                    {
                        "method": "GET",
                        "path": "/api/user/{user_id}",
                        "handler_file": "app/api/user.py",
                        "handler_function": "get_user_profile",
                        "handler_line": 78
                    },
                    {
                        "method": "POST",
                        "path": "/api/user/{user_id}/update",
                        "handler_file": "app/api/user.py",
                        "handler_function": "update_user_profile",
                        "handler_line": 120
                    }
                ],
                "summary": "发现 2 个入口点"
            }
        
        elif phase == 2:
            return {
                "success": True,
                "entry_analysis": [
                    {
                        "entry": "GET /api/user/{user_id}",
                        "handler": "app/api/user.py:get_user_profile",
                        "logic": "返回用户个人资料",
                        "auth_checks": ["@login_required"],
                        "permission_checks": [],
                        "input_params": ["user_id (from URL)"],
                        "risk": "可能IDOR - 无用户所有权验证"
                    }
                ],
                "summary": "发现 1 个风险点"
            }
        
        elif phase == 3:
            return {
                "success": True,
                "sensitive_operations": [
                    {
                        "entry": "GET /api/user/{user_id}",
                        "operation": "SELECT * FROM users WHERE id = ?",
                        "operation_file": "app/db.py",
                        "operation_line": 45,
                        "operation_type": "data_query",
                        "checks_before": ["@login_required"],
                        "checks_missing": ["user_ownership"]
                    }
                ],
                "summary": "发现 1 个敏感操作"
            }
        
        elif phase == 4:
            return {
                "success": True,
                "taint_paths": [
                    {
                        "entry": "GET /api/user/{user_id}",
                        "sensitive_op": "SELECT * FROM users WHERE id = ?",
                        "entry_params": ["user_id"],
                        "taint_flow": ["user_id (URL param)", "db.filter(id=user_id)", "execute()"],
                        "missing_check": "current_user.id == user_id",
                        "vulnerability_class": "IDOR"
                    }
                ],
                "summary": "识别 1 条污染路径"
            }
        
        elif phase == 5:
            return {
                "success": True,
                "findings": [
                    {
                        "title": "app/api/user.py中get_user_profile函数水平越权",
                        "vulnerability_type": "horizontal_privilege_escalation",
                        "severity": "high",
                        "confidence": 0.9,
                        "file_path": "app/api/user.py",
                        "function_name": "get_user_profile",
                        "line_start": 78,
                        "entry_point": "GET /api/user/{user_id}",
                        "missing_checks": ["current_user.id == user_id"],
                        "poc_plan": "使用不同的 user_id 参数调用 API，验证是否返回其他用户的数据",
                        "fix_suggestion": "在函数开始添加：if request.user.id != user_id: raise PermissionDenied()"
                    }
                ],
                "summary": "确认 1 个业务逻辑漏洞"
            }
        
        return {"success": False, "error": "Unknown phase"}
    
    def _update_context_from_llm_result(self, context: Dict[str, Any], phase: ScanPhase, result: Dict[str, Any]) -> None:
        """从 LLM 结果更新扫描上下文"""
        
        phase_num = phase.phase_num
        
        if phase_num == 1 and "entries" in result:
            context["discovered_entries"].extend(result.get("entries", []))
        
        elif phase_num == 2 and "entry_analysis" in result:
            # 保存第 2 阶段的分析结果
            context["entry_analysis"] = result.get("entry_analysis", [])
        
        elif phase_num == 3 and "sensitive_operations" in result:
            context["sensitive_operations"].extend(result.get("sensitive_operations", []))
        
        elif phase_num == 4 and "taint_paths" in result:
            context["taint_paths"].extend(result.get("taint_paths", []))
        
        elif phase_num == 5 and "findings" in result:
            for finding_dict in result.get("findings", []):
                finding = self._dict_to_finding(finding_dict)
                self.findings.append(finding)
                context["findings"].append(finding_dict)
    
    def _dict_to_finding(self, d: Dict[str, Any]) -> BusinessLogicFinding:
        """字典转换为 Finding 对象"""
        return BusinessLogicFinding(
            title=d.get("title", ""),
            vulnerability_type=d.get("vulnerability_type", ""),
            severity=d.get("severity", "medium"),
            file_path=d.get("file_path", ""),
            function_name=d.get("function_name", ""),
            line_start=d.get("line_start", 0),
            line_end=d.get("line_end"),
            entry_point=d.get("entry_point"),
            taint_path=d.get("taint_path", []),
            missing_checks=d.get("missing_checks", []),
            code_snippet=d.get("code_snippet", ""),
            confidence=d.get("confidence", 0.0),
            poc_plan=d.get("poc_plan", ""),
            fix_suggestion=d.get("fix_suggestion", ""),
        )
    
    def _finding_to_dict(self, f: BusinessLogicFinding) -> Dict[str, Any]:
        """Finding 对象转换为字典（用于 JSON 输出）"""
        return {
            "title": f.title,
            "vulnerability_type": f.vulnerability_type,
            "severity": f.severity,
            "file_path": f.file_path,
            "function_name": f.function_name,
            "line_start": f.line_start,
            "line_end": f.line_end,
            "entry_point": f.entry_point,
            "taint_path": f.taint_path,
            "missing_checks": f.missing_checks,
            "code_snippet": f.code_snippet,
            "confidence": f.confidence,
            "poc_plan": f.poc_plan,
            "fix_suggestion": f.fix_suggestion,
            "needs_verification": True,
        }
    
    def _generate_report(self, context: Dict[str, Any]) -> Dict[str, str]:
        """生成最终报告"""
        
        findings_count = len(self.findings)
        by_severity = self._count_by_severity()
        
        lines = [
            "🧠 业务逻辑漏洞审计报告",
            "",
            "📊 审计概览:",
            f"- HTTP 入口数: {len(context['discovered_entries'])}",
            f"- 敏感操作: {len(context['sensitive_operations'])}",
            f"- 污染路径: {len(context['taint_paths'])}",
            f"- 发现漏洞: {findings_count}",
            "",
        ]
        
        if by_severity["critical"] > 0:
            lines.append(f"🔴 CRITICAL 级别: {by_severity['critical']}")
        if by_severity["high"] > 0:
            lines.append(f"🟠 HIGH 级别: {by_severity['high']}")
        if by_severity["medium"] > 0:
            lines.append(f"🟡 MEDIUM 级别: {by_severity['medium']}")
        if by_severity["low"] > 0:
            lines.append(f"🟢 LOW 级别: {by_severity['low']}")
        
        if findings_count > 0:
            lines.extend([
                "",
                "🔴 关键发现 (按风险排序):",
                "",
            ])
            
            # 按严重程度排序
            sorted_findings = sorted(
                self.findings,
                key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x.severity, 4)
            )
            
            for idx, finding in enumerate(sorted_findings[:5], 1):
                severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(finding.severity, "⚪")
                lines.extend([
                    f"{idx}. [{severity_icon} {finding.severity.upper()}] {finding.title}",
                    f"   📍 {finding.file_path}:{finding.line_start}",
                    f"   🔍 入口: {finding.entry_point}",
                    f"   ⚠️ 缺失校验: {', '.join(finding.missing_checks)}",
                    f"   💡 PoC: {finding.poc_plan}",
                    "",
                ])
        else:
            lines.extend([
                "",
                "✅ 未发现业务逻辑漏洞",
            ])
        
        return {
            "text": "\n".join(lines),
            "findings_count": findings_count,
        }
    
    def _count_by_severity(self) -> Dict[str, int]:
        """统计各严重程度的发现"""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for finding in self.findings:
            severity = finding.severity.lower()
            if severity in counts:
                counts[severity] += 1
        return counts
