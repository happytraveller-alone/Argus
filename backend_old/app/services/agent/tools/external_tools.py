"""
外部安全工具集成
集成 Opengrep、Gitleaks、TruffleHog、npm audit 等专业安全工具
"""

import asyncio
import json
import logging
import os
import re
import tempfile
import shutil
import shlex
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from dataclasses import dataclass
from uuid import uuid4

from app.core.config import settings
from app.services.pmd_rulesets import PMD_RULESET_ALIASES
from app.services.agent.scanner_runner import ScannerRunSpec, run_scanner_container
from .base import AgentTool, ToolResult
from .sandbox_tool import SandboxManager

logger = logging.getLogger(__name__)


# ============ 公共辅助函数 ============

def _smart_resolve_target_path(
    target_path: str, 
    project_root: str, 
    tool_name: str = "Tool"
) -> tuple[str, str, Optional[str]]:
    """
    智能解析目标路径
    
    Args:
        target_path: 用户/Agent 传入的目标路径
        project_root: 项目根目录（绝对路径）
        tool_name: 工具名称（用于日志）
    
    Returns:
        (safe_target_path, host_check_path, error_msg)
        - safe_target_path: 容器内使用的安全路径
        - host_check_path: 宿主机上的检查路径
        - error_msg: 如果有错误返回错误信息，否则为 None
    """
    # 获取项目根目录名
    project_dir_name = os.path.basename(project_root.rstrip('/'))
    
    if target_path in (".", "", "./"):
        # 扫描整个项目根目录，在容器内对应 /workspace
        safe_target_path = "."
        host_check_path = project_root
    elif target_path == project_dir_name or target_path == f"./{project_dir_name}":
        #  智能修复：Agent 可能把项目名当作子目录传入
        logger.info(f"[{tool_name}] 智能路径修复: '{target_path}' -> '.' (项目根目录名: {project_dir_name})")
        safe_target_path = "."
        host_check_path = project_root
    else:
        # 相对路径，需要验证是否存在
        safe_target_path = target_path.lstrip("/") if target_path.startswith("/") else target_path
        host_check_path = os.path.join(project_root, safe_target_path)
        
        #  智能回退：如果路径不存在，尝试扫描整个项目
        if not os.path.exists(host_check_path):
            logger.warning(
                f"[{tool_name}] 路径 '{target_path}' 不存在于项目中，自动回退到扫描整个项目 "
                f"(project_root={project_root}, project_dir_name={project_dir_name})"
            )
            # 回退到扫描整个项目
            safe_target_path = "."
            host_check_path = project_root
    
    # 最终检查
    if not os.path.exists(host_check_path):
        error_msg = f"目标路径不存在: {target_path} (完整路径: {host_check_path})"
        logger.error(f"[{tool_name}] {error_msg}")
        return safe_target_path, host_check_path, error_msg
    
    return safe_target_path, host_check_path, None


# ============ Opengrep 工具 ============

class OpengrepInput(BaseModel):
    """Opengrep 扫描输入"""
    target_path: str = Field(
        default=".",
        description="要扫描的路径。重要：使用 '.' 扫描整个项目（推荐），或使用 'src/' 等子目录。不要使用项目目录名如 'PHP-Project'！"
    )
    rules: Optional[str] = Field(
        default="p/security-audit",
        description="规则集: p/security-audit, p/owasp-top-ten, p/r2c-security-audit"
    )
    severity: Optional[str] = Field(
        default=None,
        description="过滤严重程度: ERROR, WARNING, INFO"
    )
    max_results: int = Field(default=50, description="最大返回结果数")


class OpengrepTool(AgentTool):
    """
    Opengrep 静态分析工具
    
    Opengrep 是一款快速、轻量级的静态分析工具，支持多种编程语言。
    提供丰富的安全规则库，可以检测各种安全漏洞。
    
    官方规则集:
    - p/security-audit: 综合安全审计
    - p/owasp-top-ten: OWASP Top 10 漏洞
    - p/r2c-security-audit: R2C 安全审计规则
    - p/python: Python 特定规则
    - p/javascript: JavaScript 特定规则
    """
    
    AVAILABLE_RULESETS = [
        "p/security-audit",
        "p/owasp-top-ten",
        "p/r2c-security-audit",
        "p/python",
        "p/javascript",
        "p/typescript",
        "p/java",
        "p/go",
        "p/php",
        "p/ruby",
        "p/secrets",
        "p/sql-injection",
        "p/xss",
        "p/command-injection",
    ]
    
    def __init__(self, project_root: str, sandbox_manager: Optional["SandboxManager"] = None):
        super().__init__()
        #  将相对路径转换为绝对路径，Docker 需要绝对路径
        self.project_root = os.path.abspath(project_root)
        #  使用共享的 SandboxManager 实例，避免重复初始化
        self.sandbox_manager = sandbox_manager or SandboxManager()

    @property
    def name(self) -> str:
        return "opengrep_scan"
    
    @property
    def description(self) -> str:
        return """使用 Opengrep 进行静态安全分析。
Opengrep 是业界领先的静态分析工具，支持 30+ 种编程语言。

重要提示:
- target_path 使用 '.' 扫描整个项目（推荐）
- 或使用子目录如 'src/'、'app/' 等
- 不要使用项目目录名（如 'PHP-Project'、'MyApp'）！

可用规则集:
- p/security-audit: 综合安全审计（推荐）
- p/owasp-top-ten: OWASP Top 10 漏洞检测
- p/secrets: 密钥泄露检测
- p/sql-injection: SQL 注入检测

使用场景:
- 快速全面的代码安全扫描
- 检测常见安全漏洞模式"""
    
    @property
    def args_schema(self):
        return OpengrepInput
    
    async def _execute(
        self,
        target_path: str = ".",
        rules: str = "p/security-audit",
        severity: Optional[str] = None,
        max_results: int = 50,
        **kwargs
    ) -> ToolResult:
        """执行 Opengrep 扫描"""
        # 确保 Docker 可用
        await self.sandbox_manager.initialize()
        if not self.sandbox_manager.is_available:
            error_msg = f"Opengrep unavailable: {self.sandbox_manager.get_diagnosis()}"
            return ToolResult(
                success=False,
                data=error_msg,  #  修复：设置 data 字段避免 None
                error=error_msg
            )

        #  使用公共函数进行智能路径解析
        safe_target_path, host_check_path, error_msg = _smart_resolve_target_path(
            target_path, self.project_root, "Opengrep"
        )
        if error_msg:
            return ToolResult(success=False, data=error_msg, error=error_msg)
        
        cmd = ["opengrep", "--json", "--quiet"]
        
        if rules == "auto":
            #  Fallback if user explicitly requests 'auto', but prefer security-audit
            cmd.extend(["--config", "p/security-audit"])
        elif rules.startswith("p/"):
            cmd.extend(["--config", rules])
        else:
            cmd.extend(["--config", rules])
        
        if severity:
            cmd.extend(["--severity", severity])
        
        # 在容器内，路径相对于 /workspace
        cmd.append(safe_target_path)
        
        cmd_str = " ".join(cmd)
        
        try:
            result = await self.sandbox_manager.execute_tool_command(
                command=cmd_str,
                host_workdir=self.project_root,
                timeout=300,
                network_mode="bridge"  #  Opengrep 需要网络来下载规则
            )

            #  添加调试日志
            logger.info(f"[Opengrep] 执行结果: success={result['success']}, exit_code={result['exit_code']}, "
                       f"stdout_len={len(result.get('stdout', ''))}, stderr_len={len(result.get('stderr', ''))}")
            if result.get('error'):
                logger.warning(f"[Opengrep] 错误信息: {result['error']}")
            if result.get('stderr'):
                logger.warning(f"[Opengrep] stderr: {result['stderr'][:500]}")
            if not result["success"] and result["exit_code"] != 1:  # 1 means findings were found
                #  增强：优先使用 stderr，其次 stdout，最后用 error 字段
                stdout_preview = result.get('stdout', '')[:500]
                stderr_preview = result.get('stderr', '')[:500]
                error_msg = stderr_preview or stdout_preview or result.get('error') or "未知错误"
                logger.error(f"[Opengrep] 执行失败 (exit_code={result['exit_code']}): {error_msg}")
                if stdout_preview:
                    logger.error(f"[Opengrep] stdout: {stdout_preview}")
                return ToolResult(
                    success=False,
                    data=f"Opengrep 执行失败 (exit_code={result['exit_code']}): {error_msg}",
                    error=f"Opengrep 执行失败: {error_msg}",
                )

            # 解析结果
            stdout = result.get('stdout', '')
            try:
                # 尝试从 stdout 查找 JSON
                json_start = stdout.find('{')
                logger.debug(f"[Opengrep] JSON 起始位置: {json_start}, stdout 前200字符: {stdout[:200]}")

                if json_start >= 0:
                    json_str = stdout[json_start:]
                    results = json.loads(json_str)
                    logger.info(f"[Opengrep] JSON 解析成功, results 数量: {len(results.get('results', []))}")
                else:
                    logger.warning(f"[Opengrep] 未找到 JSON 起始符 '{{', stdout: {stdout[:500]}")
                    results = {}
            except json.JSONDecodeError as e:
                error_msg = f"无法解析 Opengrep 输出 (位置 {e.pos}): {e.msg}"
                logger.error(f"[Opengrep] JSON 解析失败: {error_msg}")
                logger.error(f"[Opengrep] 原始输出前500字符: {stdout[:500]}")
                return ToolResult(
                    success=False,
                    data=error_msg,  #  修复：设置 data 字段避免 None
                    error=error_msg,
                )
            
            findings = results.get("results", [])[:max_results]
            
            if not findings:
                return ToolResult(
                    success=True,
                    data=f"Opengrep 扫描完成，未发现安全问题 (规则集: {rules})",
                    metadata={"findings_count": 0, "rules": rules}
                )
            
            # 格式化输出
            output_parts = [f" Opengrep 扫描结果 (规则集: {rules})\n"]
            output_parts.append(f"发现 {len(findings)} 个问题:\n")
            
            severity_icons = {"ERROR": "🔴", "WARNING": "🟠", "INFO": "🟡"}
            
            for i, finding in enumerate(findings[:max_results]):
                sev = finding.get("extra", {}).get("severity", "INFO")
                icon = severity_icons.get(sev, "⚪")
                
                output_parts.append(f"\n{icon} [{sev}] {finding.get('check_id', 'unknown')}")
                output_parts.append(f"   文件: {finding.get('path', '')}:{finding.get('start', {}).get('line', 0)}")
                output_parts.append(f"   消息: {finding.get('extra', {}).get('message', '')[:200]}")
                
                # 代码片段
                lines = finding.get("extra", {}).get("lines", "")
                if lines:
                    output_parts.append(f"   代码: {lines[:150]}")
            
            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={
                    "findings_count": len(findings),
                    "rules": rules,
                    "findings": findings[:10],
                }
            )
            
        except Exception as e:
            error_msg = f"Opengrep 执行错误: {str(e)}"
            return ToolResult(
                success=False,
                data=error_msg,  #  修复：设置 data 字段避免 None
                error=error_msg
            )


# ============ npm audit 工具 ============

class NpmAuditInput(BaseModel):
    """npm audit 扫描输入"""
    target_path: str = Field(default=".", description="包含 package.json 的目录")
    production_only: bool = Field(default=False, description="仅扫描生产依赖")


class NpmAuditTool(AgentTool):
    """
    npm audit 依赖漏洞扫描工具
    
    扫描 Node.js 项目的依赖漏洞，基于 npm 官方漏洞数据库。
    """
    
    def __init__(self, project_root: str, sandbox_manager: Optional["SandboxManager"] = None):
        super().__init__()
        #  将相对路径转换为绝对路径，Docker 需要绝对路径
        self.project_root = os.path.abspath(project_root)
        #  使用共享的 SandboxManager 实例，避免重复初始化
        self.sandbox_manager = sandbox_manager or SandboxManager()

    @property
    def name(self) -> str:
        return "npm_audit"
    
    @property
    def description(self) -> str:
        return """使用 npm audit 扫描 Node.js 项目的依赖漏洞。
基于 npm 官方漏洞数据库，检测已知的依赖安全问题。

适用于:
- 包含 package.json 的 Node.js 项目
- 前端项目 (React, Vue, Angular 等)

需要先运行 npm install 安装依赖。"""
    
    @property
    def args_schema(self):
        return NpmAuditInput
    
    async def _execute(
        self,
        target_path: str = ".",
        production_only: bool = False,
        **kwargs
    ) -> ToolResult:
        """执行 npm audit"""
        # 确保 Docker 可用
        await self.sandbox_manager.initialize()
        if not self.sandbox_manager.is_available:
            error_msg = f"npm audit unavailable: {self.sandbox_manager.get_diagnosis()}"
            return ToolResult(success=False, data=error_msg, error=error_msg)

        # 这里的 target_path 是相对于 project_root 的
        # 防止空路径
        safe_target_path = target_path if not target_path.startswith("/") else target_path.lstrip("/")
        if not safe_target_path:
            safe_target_path = "."
            
        full_path = os.path.normpath(os.path.join(self.project_root, target_path))
        
        # 宿主机预检查
        package_json = os.path.join(full_path, "package.json")
        if not os.path.exists(package_json):
            error_msg = f"未找到 package.json: {target_path}"
            return ToolResult(
                success=False,
                data=error_msg,
                error=error_msg,
            )
        
        cmd = ["npm", "audit", "--json"]
        if production_only:
            cmd.append("--production")
        
        # 组合命令: cd 到目标目录然后执行
        cmd_str = f"cd {safe_target_path} && {' '.join(cmd)}"
        
        try:
            # 清除代理设置，避免容器内网络问题
            proxy_env = {
                "HTTPS_PROXY": "",
                "HTTP_PROXY": "",
                "https_proxy": "",
                "http_proxy": ""
            }
            
            result = await self.sandbox_manager.execute_tool_command(
                command=cmd_str,
                host_workdir=self.project_root,
                timeout=120,
                network_mode="bridge",
                env=proxy_env
            )
            
            try:
                # npm audit json starts with {
                json_start = result['stdout'].find('{')
                if json_start >= 0:
                    results = json.loads(result['stdout'][json_start:])
                else:
                    return ToolResult(success=True, data=f"npm audit 输出为空或格式错误: {result['stdout'][:100]}")
            except json.JSONDecodeError:
                return ToolResult(success=True, data=f"npm audit 输出格式错误")
            
            vulnerabilities = results.get("vulnerabilities", {})
            
            if not vulnerabilities:
                return ToolResult(
                    success=True,
                    data="npm audit 完成，未发现依赖漏洞",
                    metadata={"findings_count": 0}
                )
            
            output_parts = ["npm audit 依赖漏洞扫描结果\n"]
            
            severity_counts = {"critical": 0, "high": 0, "moderate": 0, "low": 0}
            for name, vuln in vulnerabilities.items():
                severity = vuln.get("severity", "low")
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
            
            output_parts.append(f"漏洞统计: 🔴 Critical: {severity_counts['critical']}, 🟠 High: {severity_counts['high']}, 🟡 Moderate: {severity_counts['moderate']}, 🟢 Low: {severity_counts['low']}\n")
            
            severity_icons = {"critical": "🔴", "high": "🟠", "moderate": "🟡", "low": "🟢"}
            
            for name, vuln in list(vulnerabilities.items())[:20]:
                sev = vuln.get("severity", "low")
                icon = severity_icons.get(sev, "⚪")
                output_parts.append(f"\n{icon} [{sev.upper()}] {name}")
                output_parts.append(f"   版本范围: {vuln.get('range', 'unknown')}")
                
                via = vuln.get("via", [])
                if via and isinstance(via[0], dict):
                    output_parts.append(f"   来源: {via[0].get('title', '')[:100]}")
            
            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={
                    "findings_count": len(vulnerabilities),
                    "severity_counts": severity_counts,
                }
            )
            
        except Exception as e:
            error_msg = f"npm audit 错误: {str(e)}"
            return ToolResult(success=False, data=error_msg, error=error_msg)


# ============ Safety 工具 (Python 依赖) ============

class SafetyInput(BaseModel):
    """Safety 扫描输入"""
    requirements_file: str = Field(default="requirements.txt", description="requirements 文件路径")


class SafetyTool(AgentTool):
    """
    Safety Python 依赖漏洞扫描工具
    
    检查 Python 依赖中的已知安全漏洞。
    """
    
    def __init__(self, project_root: str, sandbox_manager: Optional["SandboxManager"] = None):
        super().__init__()
        #  将相对路径转换为绝对路径，Docker 需要绝对路径
        self.project_root = os.path.abspath(project_root)
        #  使用共享的 SandboxManager 实例，避免重复初始化
        self.sandbox_manager = sandbox_manager or SandboxManager()

    @property
    def name(self) -> str:
        return "safety_scan"
    
    @property
    def description(self) -> str:
        return """使用 Safety 扫描 Python 依赖的安全漏洞。
基于 PyUp.io 漏洞数据库检测已知的依赖安全问题。

适用于:
- 包含 requirements.txt 的 Python 项目
- Pipenv 项目 (Pipfile.lock)
- Poetry 项目 (poetry.lock)"""
    
    @property
    def args_schema(self):
        return SafetyInput
    
    async def _execute(
        self,
        requirements_file: str = "requirements.txt",
        **kwargs
    ) -> ToolResult:
        """执行 Safety 扫描"""
        # 确保 Docker 可用
        await self.sandbox_manager.initialize()
        if not self.sandbox_manager.is_available:
            error_msg = f"Safety unavailable: {self.sandbox_manager.get_diagnosis()}"
            return ToolResult(success=False, data=error_msg, error=error_msg)

        full_path = os.path.join(self.project_root, requirements_file)
        if not os.path.exists(full_path):
            error_msg = f"未找到依赖文件: {requirements_file}"
            return ToolResult(success=False, data=error_msg, error=error_msg)
            
        # commands
        # requirements_file relative path inside container is just requirements_file (assuming it's relative to root)
        # If requirements_file is absolute, we need to make it relative.
        # But for security, `requirements_file` should be relative to project_root.
        safe_req_file = requirements_file if not requirements_file.startswith("/") else requirements_file.lstrip("/")

        cmd = ["safety", "check", "-r", safe_req_file, "--json"]
        cmd_str = " ".join(cmd)
        
        try:
            result = await self.sandbox_manager.execute_tool_command(
                command=cmd_str,
                host_workdir=self.project_root,
                timeout=120
            )
            
            stdout = result['stdout']
            try:
                # Safety 输出的 JSON 格式可能不同版本有差异
                # find first { or [
                start_idx = -1
                for i, char in enumerate(stdout):
                    if char in ['{', '[']:
                        start_idx = i
                        break
                
                if start_idx >= 0:
                     output_json = stdout[start_idx:]
                     if "No known security" in output_json:
                          return ToolResult(
                            success=True,
                            data="🐍 Safety 扫描完成，未发现 Python 依赖漏洞",
                            metadata={"findings_count": 0}
                        )
                     results = json.loads(output_json)
                else:
                     return ToolResult(success=True, data=f"Safety 输出:\n{stdout[:1000]}")

            except:
                return ToolResult(success=True, data=f"Safety 输出解析失败:\n{stdout[:1000]}")
            
            vulnerabilities = results if isinstance(results, list) else results.get("vulnerabilities", [])
            
            if not vulnerabilities:
                return ToolResult(
                    success=True,
                    data="🐍 Safety 扫描完成，未发现 Python 依赖漏洞",
                    metadata={"findings_count": 0}
                )
            
            output_parts = ["🐍 Safety Python 依赖漏洞扫描结果\n"]
            output_parts.append(f"发现 {len(vulnerabilities)} 个漏洞:\n")
            
            for vuln in vulnerabilities[:20]:
                if isinstance(vuln, list) and len(vuln) >= 4:
                    output_parts.append(f"\n🔴 {vuln[0]} ({vuln[1]})")
                    output_parts.append(f"   漏洞 ID: {vuln[4] if len(vuln) > 4 else 'N/A'}")
                    output_parts.append(f"   描述: {vuln[3][:200] if len(vuln) > 3 else ''}")
            
            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={"findings_count": len(vulnerabilities)}
            )
            
        except Exception as e:
            error_msg = f"Safety 执行错误: {str(e)}"
            return ToolResult(success=False, data=error_msg, error=error_msg)


# ============ TruffleHog 工具 ============

class TruffleHogInput(BaseModel):
    """TruffleHog 扫描输入"""
    target_path: str = Field(
        default=".",
        description="要扫描的路径。使用 '.' 扫描整个项目（推荐），不要使用项目目录名！"
    )
    only_verified: bool = Field(default=False, description="仅显示已验证的密钥")


class TruffleHogTool(AgentTool):
    """
    TruffleHog 深度密钥扫描工具
    
    TruffleHog 可以检测代码和 Git 历史中的密钥泄露，
    并可以验证密钥是否仍然有效。
    """
    
    def __init__(self, project_root: str, sandbox_manager: Optional["SandboxManager"] = None):
        super().__init__()
        #  将相对路径转换为绝对路径，Docker 需要绝对路径
        self.project_root = os.path.abspath(project_root)
        #  使用共享的 SandboxManager 实例，避免重复初始化
        self.sandbox_manager = sandbox_manager or SandboxManager()

    @property
    def name(self) -> str:
        return "trufflehog_scan"
    
    @property
    def description(self) -> str:
        return """使用 TruffleHog 进行深度密钥扫描。

重要提示: target_path 使用 '.' 扫描整个项目，不要使用项目目录名！

特点:
- 支持 700+ 种密钥类型
- 可以验证密钥是否仍然有效
- 高精度，低误报

建议与 Opengrep 组合使用。"""
    
    @property
    def args_schema(self):
        return TruffleHogInput
    
    async def _execute(
        self,
        target_path: str = ".",
        only_verified: bool = False,
        **kwargs
    ) -> ToolResult:
        """执行 TruffleHog 扫描"""
        # 确保 Docker 可用
        await self.sandbox_manager.initialize()
        if not self.sandbox_manager.is_available:
            error_msg = f"TruffleHog unavailable: {self.sandbox_manager.get_diagnosis()}"
            return ToolResult(success=False, data=error_msg, error=error_msg)

        #  使用公共函数进行智能路径解析
        safe_target_path, host_check_path, error_msg = _smart_resolve_target_path(
            target_path, self.project_root, "TruffleHog"
        )
        if error_msg:
            return ToolResult(success=False, data=error_msg, error=error_msg)

        cmd = ["trufflehog", "filesystem", safe_target_path, "--json"]
        if only_verified:
            cmd.append("--only-verified")
        
        cmd_str = " ".join(cmd)
        
        try:
            result = await self.sandbox_manager.execute_tool_command(
                command=cmd_str,
                host_workdir=self.project_root,
                timeout=180
            )
            
            stdout = result['stdout']
            
            if not stdout.strip():
                return ToolResult(
                    success=True,
                    data=" TruffleHog 扫描完成，未发现密钥泄露",
                    metadata={"findings_count": 0}
                )
            
            # TruffleHog 输出每行一个 JSON 对象
            findings = []
            for line in stdout.strip().split('\n'):
                if line.strip():
                    try:
                        findings.append(json.loads(line))
                    except:
                        pass
            
            if not findings:
                return ToolResult(
                    success=True,
                    data=" TruffleHog 扫描完成，未发现密钥泄露",
                    metadata={"findings_count": 0}
                )
            
            output_parts = [" TruffleHog 密钥扫描结果\n"]
            output_parts.append(f"发现 {len(findings)} 处密钥泄露!\n")
            
            for i, finding in enumerate(findings[:20]):
                verified = "已验证有效" if finding.get("Verified") else "未验证"
                output_parts.append(f"\n🔴 [{i+1}] {finding.get('DetectorName', 'unknown')} - {verified}")
                output_parts.append(f"   文件: {finding.get('SourceMetadata', {}).get('Data', {}).get('Filesystem', {}).get('file', '')}")
            
            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={"findings_count": len(findings)}
            )
            
        except Exception as e:
            error_msg = f"TruffleHog 执行错误: {str(e)}"
            return ToolResult(success=False, data=error_msg, error=error_msg)


# ============ OSV-Scanner 工具 ============

class OSVScannerInput(BaseModel):
    """OSV-Scanner 扫描输入"""
    target_path: str = Field(
        default=".",
        description="要扫描的路径。使用 '.' 扫描整个项目（推荐），不要使用项目目录名！"
    )


class OSVScannerTool(AgentTool):
    """
    OSV-Scanner 开源漏洞扫描工具
    
    Google 开源的漏洞扫描工具，使用 OSV 数据库。
    支持多种包管理器和锁文件。
    """
    
    def __init__(self, project_root: str, sandbox_manager: Optional["SandboxManager"] = None):
        super().__init__()
        #  将相对路径转换为绝对路径，Docker 需要绝对路径
        self.project_root = os.path.abspath(project_root)
        #  使用共享的 SandboxManager 实例，避免重复初始化
        self.sandbox_manager = sandbox_manager or SandboxManager()

    @property
    def name(self) -> str:
        return "osv_scan"
    
    @property
    def description(self) -> str:
        return """使用 OSV-Scanner 扫描开源依赖漏洞。
Google 开源的漏洞扫描工具。

重要提示: target_path 使用 '.' 扫描整个项目，不要使用项目目录名！

支持:
- package.json (npm)
- requirements.txt (Python)
- go.mod (Go)
- Cargo.lock (Rust)
- pom.xml (Maven)
- composer.lock (PHP)"""
    
    @property
    def args_schema(self):
        return OSVScannerInput
    
    async def _execute(
        self,
        target_path: str = ".",
        **kwargs
    ) -> ToolResult:
        """执行 OSV-Scanner"""
        # 确保 Docker 可用
        await self.sandbox_manager.initialize()
        if not self.sandbox_manager.is_available:
            error_msg = f"OSV-Scanner unavailable: {self.sandbox_manager.get_diagnosis()}"
            return ToolResult(success=False, data=error_msg, error=error_msg)

        #  使用公共函数进行智能路径解析
        safe_target_path, host_check_path, error_msg = _smart_resolve_target_path(
            target_path, self.project_root, "OSV-Scanner"
        )
        if error_msg:
            return ToolResult(success=False, data=error_msg, error=error_msg)

        # OSV-Scanner
        cmd = ["osv-scanner", "--json", "-r", safe_target_path]
        cmd_str = " ".join(cmd)
        
        try:
            result = await self.sandbox_manager.execute_tool_command(
                command=cmd_str,
                host_workdir=self.project_root,
                timeout=120
            )
            
            stdout = result['stdout']
            
            try:
                results = json.loads(stdout)
            except:
                if "no package sources found" in stdout.lower():
                    return ToolResult(success=True, data="OSV-Scanner: 未找到可扫描的包文件")
                return ToolResult(success=True, data=f"OSV-Scanner 输出:\n{stdout[:1000]}")
            
            vulns = results.get("results", [])
            
            if not vulns:
                return ToolResult(
                    success=True,
                    data="OSV-Scanner 扫描完成，未发现依赖漏洞",
                    metadata={"findings_count": 0}
                )
            
            total_vulns = sum(len(r.get("vulnerabilities", [])) for r in vulns)
            
            output_parts = ["OSV-Scanner 开源漏洞扫描结果\n"]
            output_parts.append(f"发现 {total_vulns} 个漏洞:\n")
            
            for result in vulns[:10]:
                source = result.get("source", {}).get("path", "unknown")
                for vuln in result.get("vulnerabilities", [])[:5]:
                    vuln_id = vuln.get("id", "")
                    summary = vuln.get("summary", "")[:100]
                    output_parts.append(f"\n🔴 {vuln_id}")
                    output_parts.append(f"   来源: {source}")
                    output_parts.append(f"   描述: {summary}")
            
            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={"findings_count": total_vulns}
            )
            
        except Exception as e:
            error_msg = f"OSV-Scanner 执行错误: {str(e)}"
            return ToolResult(success=False, data=error_msg, error=error_msg)

# ============ PMD 工具 (Java 源码分析) ============


def _normalize_pmd_target_path(target_path: str, project_root: str) -> str:
    normalized = str(target_path or "").replace("\\", "/").strip()
    if normalized in {"", ".", "./"}:
        return "."

    if os.path.isabs(normalized) or re.match(r"^[A-Za-z]:/", normalized):
        raise ValueError(f"PMD target_path 不支持绝对路径: {normalized}")

    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if any(part == ".." for part in parts):
        raise ValueError(f"PMD target_path 不支持包含 .. 的路径: {normalized}")

    relative_path = "/".join(parts)
    if not relative_path:
        return "."

    host_path = Path(project_root) / relative_path
    if not host_path.exists():
        raise FileNotFoundError(f"PMD 目标路径不存在: {relative_path}")
    if not host_path.is_dir():
        raise ValueError(f"PMD target_path 必须是目录: {relative_path}")

    return relative_path


def _prepare_pmd_workspace(project_root: str) -> tuple[Path, Path, Path, Path, Path]:
    workspace_dir = Path(settings.SCAN_WORKSPACE_ROOT) / "pmd-tool" / uuid4().hex
    project_dir = workspace_dir / "project"
    output_dir = workspace_dir / "output"
    logs_dir = workspace_dir / "logs"
    meta_dir = workspace_dir / "meta"

    project_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    project_root_path = Path(project_root)
    workspace_parts: tuple[str, ...] = ()
    try:
        rel_workspace = os.path.relpath(workspace_dir.resolve(), project_root_path.resolve())
        if rel_workspace != "." and not rel_workspace.startswith(".."):
            workspace_parts = tuple(
                part for part in Path(rel_workspace).parts if part not in {"", "."}
            )
    except ValueError:
        workspace_parts = ()

    ignore = None
    if workspace_parts:
        def _ignore_workspace_prefix(src: str, names: list[str]) -> set[str]:
            try:
                rel_src = os.path.relpath(Path(src).resolve(), project_root_path.resolve())
            except ValueError:
                return set()

            src_parts = tuple(part for part in Path(rel_src).parts if part not in {"", "."})
            if not src_parts:
                return set()
            if len(src_parts) >= len(workspace_parts):
                return set()
            if src_parts != workspace_parts[:len(src_parts)]:
                return set()

            next_part = workspace_parts[len(src_parts)]
            return {next_part} if next_part in names else set()

        ignore = _ignore_workspace_prefix

    shutil.copytree(
        project_root_path,
        project_dir,
        dirs_exist_ok=True,
        symlinks=True,
        ignore=ignore,
    )

    return workspace_dir, project_dir, output_dir, logs_dir, meta_dir


def _stage_pmd_ruleset(host_ruleset_path: Path, meta_dir: Path) -> str:
    rules_dir = meta_dir / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    staged_path = rules_dir / host_ruleset_path.name
    shutil.copy2(host_ruleset_path, staged_path)
    return f"/scan/meta/rules/{staged_path.name}"


def _resolve_pmd_ruleset(ruleset: str, project_root: str, meta_dir: Path) -> str:
    if ruleset in PMD_RULESET_ALIASES:
        return PMD_RULESET_ALIASES[ruleset]

    normalized_ruleset = str(ruleset or "").replace("\\", "/").strip()
    if not normalized_ruleset.endswith(".xml"):
        raise ValueError(f"PMD ruleset 不支持: {ruleset}")

    project_root_path = Path(project_root)
    candidate_path = Path(normalized_ruleset)
    if candidate_path.is_absolute():
        host_ruleset_path = candidate_path
        ruleset_is_relative = False
    else:
        host_ruleset_path = project_root_path / normalized_ruleset
        ruleset_is_relative = True

    if not host_ruleset_path.exists():
        raise FileNotFoundError(f"PMD ruleset 文件不存在: {normalized_ruleset}")

    resolved_ruleset_path = host_ruleset_path.resolve()
    resolved_project_root = project_root_path.resolve()
    try:
        if os.path.commonpath([str(resolved_ruleset_path), str(resolved_project_root)]) == str(resolved_project_root):
            relative_ruleset = os.path.relpath(resolved_ruleset_path, resolved_project_root).replace(os.sep, "/")
            return f"/scan/project/{relative_ruleset}"
    except ValueError:
        pass

    if ruleset_is_relative:
        raise ValueError(f"PMD ruleset 相对路径必须位于项目目录内: {normalized_ruleset}")

    return _stage_pmd_ruleset(resolved_ruleset_path, meta_dir)


def _build_pmd_runner_command(runner_target_path: str, selected_ruleset: str) -> list[str]:
    return [
        "pmd",
        "check",
        "--dir",
        runner_target_path,
        "--rulesets",
        selected_ruleset,
        "--format",
        "json",
        "--report-file",
        "/scan/output/report.json",
        "--no-cache",
    ]


def _read_pmd_report(workspace_dir: Path) -> dict[str, Any]:
    report_path = workspace_dir / "output" / "report.json"
    if not report_path.exists():
        logger.warning("[PMD] report.json 缺失: %s", report_path)
        raise RuntimeError("PMD 报告缺失: report.json")

    raw_output = report_path.read_text(encoding="utf-8")
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as exc:
        logger.warning("[PMD] report.json JSON 无法解析: %s (%s)", report_path, exc)
        raise ValueError(f"PMD 报告 JSON 解析失败: {exc.msg}") from exc


_PMD_FAILURE_DETAIL_LIMIT = 240
_PMD_LOG_READ_BYTES = 4096
_PMD_ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?:(?:[A-Za-z]:)?[\\/](?:[^\s:;,'\"()<>]+[\\/])*[^\s:;,'\"()<>]+)"
)


def _sanitize_pmd_failure_detail(detail: Optional[str], limit: int = _PMD_FAILURE_DETAIL_LIMIT) -> Optional[str]:
    if not detail:
        return None

    cleaned = " ".join(str(detail).split())
    if not cleaned:
        return None

    cleaned = _PMD_ABSOLUTE_PATH_PATTERN.sub("[path]", cleaned)
    if len(cleaned) > limit:
        cleaned = cleaned[:limit].rstrip() + "..."
    return cleaned


def _read_pmd_log_excerpt(
    log_path: Optional[str],
    limit: int = _PMD_FAILURE_DETAIL_LIMIT,
    read_bytes: int = _PMD_LOG_READ_BYTES,
) -> Optional[str]:
    if not log_path:
        return None

    try:
        with Path(log_path).open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            file_size = handle.tell()
            start = max(0, file_size - max(read_bytes, limit))
            handle.seek(start)
            raw_bytes = handle.read(max(read_bytes, limit))
    except OSError as exc:
        logger.warning("[PMD] 无法读取 runner 日志 %s: %s", log_path, exc)
        return None

    raw_text = raw_bytes.decode("utf-8", errors="replace")
    if start > 0 and "\n" in raw_text:
        raw_text = raw_text.split("\n", 1)[1]

    return _sanitize_pmd_failure_detail(raw_text, limit=limit)


def _build_pmd_failure_summary(process_result: Any) -> str:
    exit_code = getattr(process_result, "exit_code", None)
    summary = f"PMD 扫描失败 (exit_code={exit_code})"

    details: list[str] = []
    for candidate in (
        getattr(process_result, "error", None),
        _read_pmd_log_excerpt(getattr(process_result, "stderr_path", None)),
        _read_pmd_log_excerpt(getattr(process_result, "stdout_path", None)),
    ):
        detail = _sanitize_pmd_failure_detail(candidate)
        if detail and detail not in details:
            details.append(detail)

    if not details:
        details.append("PMD runner 执行未成功")

    return f"{summary}: {'；'.join(details)}"


def _build_pmd_report_failure_summary(process_result: Any, exc: Exception) -> str:
    base_summary = _build_pmd_failure_summary(process_result)
    detail = _sanitize_pmd_failure_detail(str(exc))
    if not detail:
        return base_summary
    return f"{base_summary}；{detail}"


def _cleanup_pmd_workspace(workspace_dir: Optional[Path]) -> None:
    if workspace_dir is None:
        return
    try:
        shutil.rmtree(workspace_dir, ignore_errors=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        logger.warning("[PMD] 清理 workspace 失败 %s: %s", workspace_dir, exc)


def _normalize_pmd_violation_path(file_path: str) -> str:
    normalized = str(file_path or "").replace("\\", "/")
    if normalized == "/scan/project":
        return "."
    if normalized.startswith("/scan/project/"):
        return normalized[len("/scan/project/"):]
    if normalized.startswith("/workspace/"):
        return normalized[len("/workspace/"):]
    return normalized


class PMDInput(BaseModel):
    """PMD 扫描输入"""
    target_path: str = Field(
        default=".",
        description="要扫描的路径。使用 '.' 扫描整个项目（推荐）"
    )
    ruleset: str = Field(
        default="security",
        description="规则集: security, quickstart, all。security 专注安全问题"
    )
    max_results: int = Field(
        default=50,
        description="最大返回结果数"
    )


class PMDTool(AgentTool):
    """
    PMD Java 源代码安全扫描工具
    
    PMD 直接分析 Java 源代码（无需编译），可以检测：
    - SQL 注入风险
    - 硬编码密码/密钥
    - 空 catch 块（可能隐藏错误）
    - 不安全的随机数生成
    - 资源未关闭
    - 潜在的 XSS 问题
    - 代码质量问题
    """
    
    def __init__(self, project_root: str, sandbox_manager: Optional["SandboxManager"] = None):
        super().__init__()
        self.project_root = os.path.abspath(project_root)
        self.sandbox_manager = sandbox_manager or SandboxManager()

    @property
    def name(self) -> str:
        return "pmd_scan"
    
    @property
    def description(self) -> str:
        return """使用 PMD 扫描 Java 源代码的安全和质量问题。
PMD 直接分析源代码，无需编译！

重要提示: target_path 使用 '.' 扫描整个项目

检测能力:
- 硬编码密码/凭证
- 空 catch 块（隐藏异常）
- 不安全的随机数
- 资源泄漏（未关闭连接）
- SQL 拼接风险
- 潜在的注入点
- 代码复杂度问题

适用于 Java/JSP 项目，无需预先编译。"""
    
    @property
    def args_schema(self):
        return PMDInput
    
    async def _execute(
        self,
        target_path: str = ".",
        ruleset: str = "security",
        max_results: int = 50,
        **kwargs
    ) -> ToolResult:
        """执行 PMD 扫描"""
        workspace_dir: Optional[Path] = None
        try:
            normalized_target_path = _normalize_pmd_target_path(target_path, self.project_root)
            workspace_dir, _project_dir, _output_dir, _logs_dir, meta_dir = _prepare_pmd_workspace(self.project_root)
            selected_ruleset = _resolve_pmd_ruleset(ruleset, self.project_root, meta_dir)
            runner_target_path = "/scan/project"
            if normalized_target_path != ".":
                runner_target_path = f"/scan/project/{normalized_target_path}"

            process_result = await run_scanner_container(
                ScannerRunSpec(
                    scanner_type="pmd-tool",
                    image=settings.SCANNER_PMD_IMAGE,
                    workspace_dir=str(workspace_dir),
                    command=_build_pmd_runner_command(runner_target_path, selected_ruleset),
                    timeout_seconds=180,
                    env={},
                    expected_exit_codes=[0, 4],
                    artifact_paths=["output/report.json"],
                )
            )

            if process_result.exit_code not in {0, 4}:
                error_msg = _build_pmd_failure_summary(process_result)
                return ToolResult(success=False, data=error_msg, error=error_msg)

            try:
                pmd_result = _read_pmd_report(workspace_dir)
            except (RuntimeError, ValueError) as exc:
                error_msg = _build_pmd_report_failure_summary(process_result, exc)
                logger.warning("[PMD] %s", error_msg)
                return ToolResult(success=False, data=error_msg, error=error_msg)
            
            # 提取 violations
            violations = []
            files = pmd_result.get('files', [])
            for file_info in files:
                filename = _normalize_pmd_violation_path(file_info.get('filename', ''))
                for v in file_info.get('violations', []):
                    violations.append({
                        'file': filename,
                        'beginLine': v.get('beginline', 0),
                        'endLine': v.get('endline', 0),
                        'rule': v.get('rule', ''),
                        'ruleset': v.get('ruleset', ''),
                        'priority': v.get('priority', 3),
                        'message': v.get('message', ''),
                    })
            
            if not violations:
                return ToolResult(
                    success=True,
                    data=" PMD 扫描完成，未发现安全问题",
                    metadata={
                        "findings_count": 0,
                        "high_count": 0,
                        "medium_count": 0,
                        "low_count": 0,
                        "findings": [],
                        "raw_result": pmd_result,
                    }
                )
            
            # 按优先级排序
            violations.sort(key=lambda x: x.get('priority', 5))
            
            # 格式化输出
            output_parts = [" PMD Java 源码安全扫描结果\n"]
            output_parts.append(f"发现 {len(violations)} 个问题!\n")
            
            # 统计
            high_count = sum(1 for v in violations if v.get('priority', 5) <= 2)
            medium_count = sum(1 for v in violations if v.get('priority', 5) == 3)
            low_count = sum(1 for v in violations if v.get('priority', 5) >= 4)
            
            output_parts.append(f"📊 优先级分布: 🔴 高 {high_count} | 🟡 中 {medium_count} | 🟢 低 {low_count}\n")
            
            for i, v in enumerate(violations[:max_results]):
                priority = v.get('priority', 5)
                icon = "🔴" if priority <= 2 else ("🟡" if priority == 3 else "🟢")
                
                # 简化文件路径
                filepath = _normalize_pmd_violation_path(v.get('file', ''))
                
                output_parts.append(f"\n{icon} [{i+1}] {v.get('rule', 'Unknown')}")
                output_parts.append(f"   文件: {filepath}")
                output_parts.append(f"   行号: {v.get('beginLine', '?')}-{v.get('endLine', '?')}")
                output_parts.append(f"   规则集: {v.get('ruleset', 'Unknown')}")
                if v.get('message'):
                    msg = v.get('message', '')[:200]
                    output_parts.append(f"   描述: {msg}")
            
            if len(violations) > max_results:
                output_parts.append(f"\n... 还有 {len(violations) - max_results} 个问题未显示")
            
            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={
                    "findings_count": len(violations),
                    "high_count": high_count,
                    "medium_count": medium_count,
                    "low_count": low_count,
                    # 结构化 Python 对象，便于 Agent 后续处理（对齐 Opengrep）
                    "findings": violations[:10],
                    "raw_result": pmd_result,
                }
            )
            
        except (ValueError, FileNotFoundError) as e:
            error_msg = f"PMD 执行错误: {str(e)}"
            logger.warning("[PMD] %s", error_msg)
            return ToolResult(success=False, data=error_msg, error=error_msg)
        except Exception as e:
            error_msg = f"PMD 执行错误: {str(e)}"
            logger.error(f"[PMD] {error_msg}", exc_info=True)
            return ToolResult(success=False, data=error_msg, error=error_msg)
        finally:
            _cleanup_pmd_workspace(workspace_dir)

# ============ PHPStan 工具 (PHP 静态分析) ============

class PHPStanInput(BaseModel):
    """PHPStan 扫描输入"""
    target_path: str = Field(
        default=".",
        description="要扫描的路径。使用 '.' 扫描整个项目（推荐）"
    )
    level: int = Field(
        default=5,
        description="分析级别 0-9，级别越高检测越严格。推荐 5 或以上"
    )
    max_results: int = Field(
        default=50,
        description="最大返回结果数"
    )


class PHPStanTool(AgentTool):
    """
    PHPStan PHP 静态分析工具
    
    PHPStan 是 PHP 静态分析工具，可以检测：
    - 类型错误和不匹配
    - 未定义的变量/方法/类
    - 死代码检测
    - 可能的空指针异常
    - 不安全的类型转换
    - 代码逻辑错误
    
    配合安全规则可检测部分安全问题：
    - 危险函数调用 (eval, exec, system 等)
    - 不安全的文件操作
    - 潜在的注入点
    """
    
    def __init__(self, project_root: str, sandbox_manager: Optional["SandboxManager"] = None):
        super().__init__()
        self.project_root = os.path.abspath(project_root)
        self.sandbox_manager = sandbox_manager or SandboxManager()

    @property
    def name(self) -> str:
        return "phpstan_scan"
    
    @property
    def description(self) -> str:
        return """使用 PHPStan 扫描 PHP 代码的质量和潜在安全问题。
PHPStan 是 PHP 静态分析工具，无需运行代码即可发现错误。

重要提示: target_path 使用 '.' 扫描整个项目

检测能力:
- 类型错误和不匹配
- 未定义的变量/方法/类
- 死代码和不可达代码
- 可能的空指针异常
- 危险函数调用 (eval, exec, system)
- 不安全的文件操作
- 代码逻辑错误

分析级别 (0-9):
- 0-2: 基础检查
- 3-5: 推荐级别，平衡严格性和实用性
- 6-9: 严格模式，可能有较多误报

适用于 PHP 项目，无需运行代码。"""
    
    @property
    def args_schema(self):
        return PHPStanInput
    
    async def _execute(
        self,
        target_path: str = ".",
        level: int = 5,
        max_results: int = 50,
        **kwargs
    ) -> ToolResult:
        """执行 PHPStan 扫描"""
        # 确保 Docker 可用
        await self.sandbox_manager.initialize()
        if not self.sandbox_manager.is_available:
            error_msg = f"PHPStan unavailable: {self.sandbox_manager.get_diagnosis()}"
            return ToolResult(success=False, data=error_msg, error=error_msg)

        # 智能路径解析
        safe_target_path, host_check_path, error_msg = _smart_resolve_target_path(
            target_path, self.project_root, "PHPStan"
        )
        if error_msg:
            return ToolResult(success=False, data=error_msg, error=error_msg)

        # 检查是否有 PHP 源文件
        has_php_files = False
        for root, dirs, files in os.walk(host_check_path):
            dirs[:] = [d for d in dirs if d not in {'.git', 'node_modules', 'vendor', '.idea'}]
            for f in files:
                if f.endswith('.php'):
                    has_php_files = True
                    break
            if has_php_files:
                break
        
        if not has_php_files:
            return ToolResult(
                success=False,
                data="未找到 PHP 源文件 (.php)。请确认这是一个 PHP 项目。",
                error="no_php_source"
            )

        # 限制级别范围
        level = max(0, min(9, level))

        # 构建 PHPStan 命令
        cmd = [
            "phpstan", "analyse",
            "--error-format=json",
            f"--level={level}",
            "--no-progress",
            "--no-interaction",
            safe_target_path
        ]
        
        cmd_str = " ".join(cmd)
        
        try:
            result = await self.sandbox_manager.execute_tool_command(
                command=cmd_str,
                host_workdir=self.project_root,
                timeout=300  # PHP 项目扫描可能较慢
            )
            
            stdout = result.get('stdout', '')
            stderr = result.get('stderr', '')
            exit_code = result.get('exit_code', 0)
            
            # PHPStan 返回非零退出码表示发现问题
            if not stdout.strip():
                if exit_code == 0:
                    return ToolResult(
                        success=True,
                        data=" PHPStan 扫描完成，未发现问题",
                        metadata={"findings_count": 0}
                    )
                else:
                    error_info = stderr[:500] if stderr else "未知错误"
                    return ToolResult(
                        success=False,
                        data=f"PHPStan 执行失败: {error_info}",
                        error="phpstan_error"
                    )
            
            # 解析 JSON 结果（对齐 Opengrep/PMD：容忍 stdout 前缀噪音）
            try:
                json_start = stdout.find('{')
                if json_start >= 0:
                    phpstan_result = json.loads(stdout[json_start:])
                else:
                    error_msg = "PHPStan 输出中未找到 JSON 起始符 '{'"
                    logger.error(f"[PHPStan] {error_msg}, stdout前500字符: {stdout[:500]}")
                    return ToolResult(success=False, data=error_msg, error=error_msg)
            except json.JSONDecodeError as e:
                error_msg = f"无法解析 PHPStan JSON 输出 (位置 {e.pos}): {e.msg}"
                logger.error(f"[PHPStan] {error_msg}")
                logger.error(f"[PHPStan] 原始输出前500字符: {stdout[:500]}")
                return ToolResult(success=False, data=error_msg, error=error_msg)
            
            # 提取错误信息
            files = phpstan_result.get('files', {})
            totals = phpstan_result.get('totals', {})
            total_errors = totals.get('errors', 0) + totals.get('file_errors', 0)
            
            if total_errors == 0:
                return ToolResult(
                    success=True,
                    data=" PHPStan 扫描完成，未发现问题",
                    metadata={"findings_count": 0}
                )
            
            # 收集所有问题
            all_issues = []
            for filepath, file_data in files.items():
                messages = file_data.get('messages', [])
                for msg in messages:
                    all_issues.append({
                        'file': filepath,
                        'line': msg.get('line', 0),
                        'message': msg.get('message', ''),
                        'identifier': msg.get('identifier', ''),
                        'tip': msg.get('tip', ''),
                        'is_security': self._is_security_issue(msg)
                    })
            
            # 优先显示安全相关问题
            all_issues.sort(key=lambda x: (0 if x['is_security'] else 1, x['file'], x['line']))
            
            # 统计
            security_count = sum(1 for i in all_issues if i['is_security'])
            
            # 格式化输出
            output_parts = [" PHPStan PHP 静态分析结果\n"]
            output_parts.append(f"📊 分析级别: {level}/9\n")
            output_parts.append(f"发现 {total_errors} 个问题")
            if security_count > 0:
                output_parts.append(f" (其中 {security_count} 个安全相关)")
            output_parts.append("\n")
            
            for i, issue in enumerate(all_issues[:max_results]):
                icon = "🔴" if issue['is_security'] else "🟡"
                
                # 简化文件路径
                filepath = issue['file']
                if '/workspace/' in filepath:
                    filepath = filepath.split('/workspace/')[-1]
                
                output_parts.append(f"\n{icon} [{i+1}] {filepath}:{issue['line']}")
                output_parts.append(f"   {issue['message'][:200]}")
                if issue['identifier']:
                    output_parts.append(f"   标识: {issue['identifier']}")
                if issue['tip']:
                    output_parts.append(f"   💡 提示: {issue['tip'][:100]}")
            
            if len(all_issues) > max_results:
                output_parts.append(f"\n... 还有 {len(all_issues) - max_results} 个问题未显示")
            
            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata={
                    "findings_count": total_errors,
                    "security_count": security_count,
                    "level": level,
                    # 结构化 Python 对象，便于 Agent 后续处理（对齐 Opengrep/PMD）
                    "findings": all_issues[:10],
                    "raw_result": phpstan_result,
                }
            )
            
        except Exception as e:
            error_msg = f"PHPStan 执行错误: {str(e)}"
            logger.error(f"[PHPStan] {error_msg}", exc_info=True)
            return ToolResult(success=False, data=error_msg, error=error_msg)
    
    def _is_security_issue(self, msg: Dict[str, Any]) -> bool:
        """判断是否为安全相关问题"""
        message = str(msg.get('message', '')).lower()
        identifier = str(msg.get('identifier', '')).lower()
        
        security_keywords = [
            'eval', 'exec', 'system', 'passthru', 'shell_exec', 'popen', 'proc_open',
            'assert', 'create_function', 'call_user_func', 'preg_replace',
            'include', 'require', 'include_once', 'require_once',
            'file_get_contents', 'file_put_contents', 'fopen', 'fwrite', 'unlink',
            'move_uploaded_file', 'copy', 'rename',
            'unserialize', 'maybe_unserialize',
            'mysqli_query', 'mysql_query', 'pg_query', 'sqlite_query',
            'header', 'setcookie',
            'dangerous', 'unsafe', 'security', 'injection', 'xss', 'sql',
            'ldap', 'xpath', 'xml',
            '$_get', '$_post', '$_request', '$_cookie', '$_server', '$_files'
        ]
        
        return any(keyword in message or keyword in identifier for keyword in security_keywords)

# ============ 导出所有工具 ============

__all__ = [
    "OpengrepTool",
    "NpmAuditTool",
    "SafetyTool",
    "TruffleHogTool",
    "OSVScannerTool",
    "PMDTool",
    "PHPStanTool",
]
