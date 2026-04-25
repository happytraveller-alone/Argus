"""
沙箱执行工具
在 Docker 沙箱中执行代码和命令进行漏洞验证
"""

import asyncio
import json
import logging
import re
import tempfile
import os
import shutil
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from dataclasses import dataclass

from .base import AgentTool, ToolResult
from .evidence_protocol import (
    build_display_command,
    build_execution_status,
    build_inline_code_lines,
    unique_command_chain,
    validate_evidence_metadata,
)
from app.services.agent.runtime_settings import settings

logger = logging.getLogger(__name__)


@dataclass
class SandboxConfig:
    """沙箱配置"""
    image: str = None  # 默认从 settings.SANDBOX_IMAGE 读取
    memory_limit: str | None = None
    cpu_limit: float | None = None
    timeout: int | None = None
    network_mode: str = "none"  # none, bridge, host
    read_only: bool = True
    user: str = "1000:1000"

    def __post_init__(self):
        if self.image is None:
            self.image = settings.SANDBOX_IMAGE
        if self.memory_limit is None:
            self.memory_limit = settings.SANDBOX_MEMORY_LIMIT
        if self.cpu_limit is None:
            self.cpu_limit = settings.SANDBOX_CPU_LIMIT
        if self.timeout is None:
            self.timeout = settings.SANDBOX_TIMEOUT


class SandboxManager:
    """
    沙箱管理器 - 兼容门面 (Phase 1)

    保持公开接口不变,内部委托给 SandboxRunnerClient
    """

    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        self._docker_client = None
        self._initialized = False
        self._init_error = None
        self._resolved_image = str(self.config.image or "").strip()
        self._last_image_candidates: List[str] = []

        # Phase 1: 新增 runner client (如果启用)
        self._runner_client = None
        self._use_new_runner = getattr(settings, "SANDBOX_RUNNER_ENABLED", True)
    
    async def initialize(self):
        """初始化 Docker 客户端和 Runner Client"""
        if self._initialized:
            logger.info("SandboxManager already initialized")
            return

        try:
            import docker
            logger.info(f"🔄 Attempting to connect to Docker... (lib: {docker.__file__})")
            self._docker_client = docker.from_env()
            # 测试连接
            self._docker_client.ping()

            # 初始化 runner client (如果启用)
            if self._use_new_runner:
                try:
                    from app.services.agent.tools.sandbox_runner_client import SandboxRunnerClient
                    self._runner_client = SandboxRunnerClient()
                    logger.info("✅ SandboxRunnerClient initialized successfully")
                except Exception as e:
                    logger.warning(f"Failed to initialize SandboxRunnerClient: {e}")
                    self._runner_client = None

            self._initialized = True
            self._init_error = None
            logger.info("Docker sandbox manager initialized successfully")
        except ImportError as e:
            logger.error(f"Docker library not installed: {e}")
            self._docker_client = None
            self._init_error = f"ImportError: {e}"
        except Exception as e:
            logger.warning(f"Docker not available: {e}")
            import traceback
            logger.warning(f"Docker connection traceback: {traceback.format_exc()}")
            self._docker_client = None
            self._init_error = f"{type(e).__name__}: {str(e)}"
    
    @property
    def is_available(self) -> bool:
        """检查 Docker 是否可用"""
        return self._docker_client is not None
        
    def get_diagnosis(self) -> str:
        """获取诊断信息"""
        if self.is_available:
            return "Docker Service Available"
        return f"Docker Service Unavailable. Error: {self._init_error or 'Not initialized'}"

    def _image_candidates(self) -> List[str]:
        explicit_image = str(self.config.image or settings.SANDBOX_IMAGE or "").strip()
        ghcr_registry = str(os.environ.get("GHCR_REGISTRY") or "docker.m.daocloud.io").strip() or "docker.m.daocloud.io"
        image_tag = str(os.environ.get("Argus_IMAGE_TAG") or "latest").strip() or "latest"
        remote_image = f"{ghcr_registry}/audittool/Argus-sandbox-runner:{image_tag}"
        ordered_candidates = [
            explicit_image,
            "Argus/sandbox-runner:latest",
            "Argus/sandbox-runner:latest",
            "Argus-sandbox-runner:latest",
            remote_image,
        ]
        deduped: List[str] = []
        for candidate in ordered_candidates:
            normalized = str(candidate or "").strip()
            if not normalized or normalized in deduped:
                continue
            deduped.append(normalized)
        self._last_image_candidates = deduped
        return deduped

    def _image_exists_locally(self, image: str) -> bool:
        if not self._docker_client:
            return False
        try:
            self._docker_client.images.get(image)
            return True
        except Exception:
            return False

    def _select_runtime_image(self, candidates: Optional[List[str]] = None) -> str:
        resolved_candidates = list(candidates or self._image_candidates())
        for image in resolved_candidates:
            if self._image_exists_locally(image):
                self._resolved_image = image
                return image
        self._resolved_image = resolved_candidates[0] if resolved_candidates else str(self.config.image or "")
        return self._resolved_image

    @staticmethod
    def _looks_like_image_not_found_error(error: Exception) -> bool:
        error_text = f"{type(error).__name__}: {error}".lower()
        return any(
            token in error_text
            for token in (
                "not found",
                "no such image",
                "pull access denied",
                "failed to resolve reference",
            )
        )

    def _format_image_resolution_error(self, candidates: List[str], attempt_errors: List[str]) -> str:
        attempted = ", ".join(candidates) or str(self.config.image or "<unset>")
        detail_text = " | ".join(attempt_errors[-3:]) if attempt_errors else "镜像不存在或拉取失败"
        build_hint = "docker build -f docker/sandbox-runner.Dockerfile -t Argus/sandbox-runner:latest ."
        return (
            f"未找到可用沙箱镜像。已尝试: {attempted}。"
            f"详情: {detail_text}。"
            f"建议先构建本地镜像：{build_hint}"
        )

    async def _run_container_with_image_fallback(self, container_config: Dict[str, Any]) -> tuple[Any, str, List[str]]:
        candidates = self._image_candidates()
        preferred = self._select_runtime_image(candidates)
        ordered_candidates = [preferred, *[image for image in candidates if image != preferred]]
        attempt_errors: List[str] = []
        for image in ordered_candidates:
            candidate_config = dict(container_config)
            candidate_config["image"] = image
            try:
                container = await asyncio.to_thread(
                    self._docker_client.containers.run,
                    **candidate_config,
                )
                self._resolved_image = image
                self._last_image_candidates = ordered_candidates
                return container, image, ordered_candidates
            except Exception as exc:
                if self._looks_like_image_not_found_error(exc):
                    attempt_errors.append(f"{image}: {exc}")
                    continue
                raise
        raise RuntimeError(self._format_image_resolution_error(ordered_candidates, attempt_errors))
    
    async def execute_command(
        self,
        command: str,
        working_dir: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        host_project_dir: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        在沙箱中执行命令

        Args:
            command: 要执行的命令
            working_dir: 工作目录
            env: 环境变量
            timeout: 超时时间（秒）
            project_root: 项目根目录（绝对路径），提供时将只读挂载到 /workspace
            host_project_dir: 宿主机上的项目根目录，将以只读方式挂载到容器 /project，
                              并自动设置 PYTHONPATH=/project，便于导入项目模块。

        Returns:
            执行结果
        """
        if not self.is_available:
            return {
                "success": False,
                "error": "Docker 不可用",
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }

        # Phase 1: 如果启用了新 runner,使用新路径
        if self._use_new_runner and self._runner_client:
            return await self._execute_command_via_runner(
                command=command,
                working_dir=working_dir,
                env=env,
                timeout=timeout,
                host_project_dir=host_project_dir,
                project_root=project_root,
            )

        # 否则使用原始实现 (保持兼容)

        timeout = timeout or self.config.timeout

        # 禁用代理环境变量，防止 Docker 自动注入的代理干扰容器网络
        no_proxy_env = {
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "http_proxy": "",
            "https_proxy": "",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
        # 挂载项目目录时，将 PYTHONPATH 指向 /project，便于代码在沙箱内导入项目模块
        project_env: Dict[str, str] = {}
        if host_project_dir and os.path.isdir(host_project_dir):
            project_env["PYTHONPATH"] = "/project"
        # 合并用户传入的环境变量（用户变量优先）
        container_env = {**no_proxy_env, **project_env, **(env or {})}

        try:
            # 确定 /workspace 挂载源：优先使用项目根目录（只读），否则使用临时目录（读写）
            resolved_project_root = None
            if project_root:
                abs_root = os.path.abspath(project_root)
                if os.path.isdir(abs_root):
                    resolved_project_root = abs_root

            # 创建临时目录（作为无项目源码时的 fallback 或作为沙箱写入区域）
            with tempfile.TemporaryDirectory() as temp_dir:
                # 修复临时目录权限：确保沙箱用户（UID 1000）可访问
                os.chmod(temp_dir, 0o777)

                if resolved_project_root:
                    # 有项目源码：只读挂载到 /workspace，临时目录挂载到 /sandbox_data
                    volumes = {
                        resolved_project_root: {"bind": "/workspace", "mode": "ro"},
                        temp_dir: {"bind": "/sandbox_data", "mode": "rw"},
                    }
                else:
                    # 无项目源码（降级模式）：临时目录挂载到 /workspace
                    volumes = {
                        temp_dir: {"bind": "/workspace", "mode": "rw"},
                    }

                # 挂载卷：workspace（可读写）+ 可选的项目目录（只读）
                volumes: Dict[str, Any] = {
                    temp_dir: {"bind": "/workspace", "mode": "rw"},
                }
                if host_project_dir and os.path.isdir(host_project_dir):
                    volumes[os.path.realpath(host_project_dir)] = {"bind": "/project", "mode": "ro"}

                # 准备容器配置
                container_config = {
                    "command": ["sh", "-c", command],
                    "detach": True,
                    "mem_limit": self.config.memory_limit,
                    "cpu_period": 100000,
                    "cpu_quota": int(100000 * self.config.cpu_limit),
                    "network_mode": self.config.network_mode,
                    "user": self.config.user,
                    "read_only": self.config.read_only,
                    "volumes": volumes,
                    "tmpfs": {
                            "/home/sandbox": "rw,exec,size=512m,mode=1777",
                            "/tmp": "rw,exec,size=512m,mode=1777"
                        },
                    "working_dir": working_dir or "/workspace",
                    "environment": container_env,
                    # 安全配置
                    "cap_drop": ["ALL"],
                    "security_opt": ["no-new-privileges:true"],
                }
                
                # 创建并启动容器
                container, selected_image, image_candidates = await self._run_container_with_image_fallback(
                    container_config
                )
                
                try:
                    # 等待执行完成
                    result = await asyncio.wait_for(
                        asyncio.to_thread(container.wait),
                        timeout=timeout
                    )
                    
                    # 获取日志
                    stdout = await asyncio.to_thread(
                        container.logs, stdout=True, stderr=False
                    )
                    stderr = await asyncio.to_thread(
                        container.logs, stdout=False, stderr=True
                    )
                    
                    return {
                        "success": result["StatusCode"] == 0,
                        "stdout": stdout.decode('utf-8', errors='ignore')[:10000],
                        "stderr": stderr.decode('utf-8', errors='ignore')[:2000],
                        "exit_code": result["StatusCode"],
                        "error": None,
                        "image": selected_image,
                        "image_candidates": image_candidates,
                    }
                    
                except asyncio.TimeoutError:
                    await asyncio.to_thread(container.kill)
                    return {
                        "success": False,
                        "error": f"执行超时 ({timeout}秒)",
                        "stdout": "",
                        "stderr": "",
                        "exit_code": -1,
                        "image": selected_image,
                        "image_candidates": image_candidates,
                    }
                    
                finally:
                    # 清理容器
                    await asyncio.to_thread(container.remove, force=True)
                    
        except Exception as e:
            logger.error(f"Sandbox execution error: {e}")
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "image": self._resolved_image,
                "image_candidates": list(self._last_image_candidates),
            }
    
    async def execute_tool_command(
        self,
        command: str,
        host_workdir: str,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        network_mode: str = "none",
    ) -> Dict[str, Any]:
        """
        在沙箱中对指定目录执行工具命令

        Args:
            command: 要执行的命令
            host_workdir: 宿主机上的工作目录（将被挂载到 /workspace）
            timeout: 超时时间
            env: 环境变量
            network_mode: 网络模式 (none, bridge, host)

        Returns:
            执行结果
        """
        if not self.is_available:
            return {
                "success": False,
                "error": "Docker 不可用",
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }

        # Phase 1: 如果启用了新 runner,使用新路径
        if self._use_new_runner and self._runner_client:
            return await self._execute_tool_command_via_runner(
                command=command,
                host_workdir=host_workdir,
                timeout=timeout,
                env=env,
                network_mode=network_mode,
            )

        # 否则使用原始实现 (保持兼容)
        timeout = timeout or self.config.timeout

        # 禁用代理环境变量，防止 Docker 自动注入的代理干扰容器网络
        no_proxy_env = {
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "http_proxy": "",
            "https_proxy": "",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
        # 合并用户传入的环境变量（用户变量优先）
        container_env = {**no_proxy_env, **(env or {})}

        try:
            # 清除代理环境变量：在命令前添加 unset（双重保险）
            unset_proxy_prefix = "unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy 2>/dev/null; "
            wrapped_command = unset_proxy_prefix + command

            # 准备容器配置
            container_config = {
                "command": ["sh", "-c", wrapped_command],
                "detach": True,
                "mem_limit": self.config.memory_limit,
                "cpu_period": 100000,
                "cpu_quota": int(100000 * self.config.cpu_limit),
                "network_mode": network_mode,
                "user": self.config.user,
                "read_only": self.config.read_only,
                "volumes": {
                    host_workdir: {"bind": "/workspace", "mode": "ro"}, # 只读挂载项目代码
                },
                "tmpfs": {
                    "/home/sandbox": "rw,exec,size=512m,mode=1777",  # 添加 exec 允许执行，用于 opengrep 规则缓存
                    "/tmp": "rw,exec,size=512m,mode=1777"  # 添加 exec 允许执行临时文件
                },
                "working_dir": "/workspace",
                "environment": container_env,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
            }
            
            # 创建并启动容器
            container, selected_image, image_candidates = await self._run_container_with_image_fallback(
                container_config
            )
            
            try:
                # 等待执行完成
                result = await asyncio.wait_for(
                    asyncio.to_thread(container.wait),
                    timeout=timeout
                )
                
                # 获取日志
                stdout = await asyncio.to_thread(
                    container.logs, stdout=True, stderr=False
                )
                stderr = await asyncio.to_thread(
                    container.logs, stdout=False, stderr=True
                )
                
                return {
                    "success": result["StatusCode"] == 0,
                    "stdout": stdout.decode('utf-8', errors='ignore')[:50000], # 增大日志限制
                    "stderr": stderr.decode('utf-8', errors='ignore')[:5000],
                    "exit_code": result["StatusCode"],
                    "error": None,
                    "image": selected_image,
                    "image_candidates": image_candidates,
                }
                
            except asyncio.TimeoutError:
                await asyncio.to_thread(container.kill)
                return {
                    "success": False,
                    "error": f"执行超时 ({timeout}秒)",
                    "stdout": "",
                    "stderr": "",
                    "exit_code": -1,
                    "image": selected_image,
                    "image_candidates": image_candidates,
                }
                
            finally:
                # 清理容器
                await asyncio.to_thread(container.remove, force=True)
                
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "image": self._resolved_image,
                "image_candidates": list(self._last_image_candidates),
            }
    async def execute_python(
        self,
        code: str,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        在沙箱中执行 Python 代码
        
        Args:
            code: Python 代码
            timeout: 超时时间
            
        Returns:
            执行结果
        """
        # 转义代码中的单引号
        escaped_code = code.replace("'", "'\\''")
        command = f"python3 -c '{escaped_code}'"
        return await self.execute_command(command, timeout=timeout)
    
    async def execute_http_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[str] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        在沙箱中执行 HTTP 请求
        
        Args:
            method: HTTP 方法
            url: URL
            headers: 请求头
            data: 请求体
            timeout: 超时
            
        Returns:
            HTTP 响应
        """
        # 构建 curl 命令
        curl_parts = ["curl", "-s", "-S", "-w", "'\\n%{http_code}'", "-X", method]
        
        if headers:
            for key, value in headers.items():
                curl_parts.extend(["-H", f"'{key}: {value}'"])
        
        if data:
            curl_parts.extend(["-d", f"'{data}'"])
        
        curl_parts.append(f"'{url}'")
        
        command = " ".join(curl_parts)
        
        # 使用带网络的镜像
        original_network = self.config.network_mode
        self.config.network_mode = "bridge"  # 允许网络访问
        
        try:
            result = await self.execute_command(command, timeout=timeout)
            
            if result["success"] and result["stdout"]:
                lines = result["stdout"].strip().split('\n')
                if lines:
                    status_code = lines[-1].strip()
                    body = '\n'.join(lines[:-1])
                    return {
                        "success": True,
                        "status_code": int(status_code) if status_code.isdigit() else 0,
                        "body": body[:5000],
                        "error": None,
                    }
            
            return {
                "success": False,
                "status_code": 0,
                "body": "",
                "error": result.get("error") or result.get("stderr"),
            }
            
        finally:
            self.config.network_mode = original_network
    
    async def verify_vulnerability(
        self,
        vulnerability_type: str,
        target_url: str,
        payload: str,
        expected_pattern: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        验证漏洞
        
        Args:
            vulnerability_type: 漏洞类型
            target_url: 目标 URL
            payload: 攻击载荷
            expected_pattern: 期望在响应中匹配的模式
            
        Returns:
            验证结果
        """
        verification_result = {
            "vulnerability_type": vulnerability_type,
            "target_url": target_url,
            "payload": payload,
            "is_vulnerable": False,
            "evidence": None,
            "error": None,
        }
        
        try:
            # 发送请求
            response = await self.execute_http_request(
                method="GET" if "?" in target_url else "POST",
                url=target_url,
                data=payload if "?" not in target_url else None,
            )
            
            if not response["success"]:
                verification_result["error"] = response.get("error")
                return verification_result
            
            body = response.get("body", "")
            status_code = response.get("status_code", 0)
            
            # 检查响应
            if expected_pattern:
                if re.search(expected_pattern, body, re.IGNORECASE):
                    verification_result["is_vulnerable"] = True
                    verification_result["evidence"] = f"响应中包含预期模式: {expected_pattern}"
            else:
                # 根据漏洞类型进行通用检查
                if vulnerability_type == "sql_injection":
                    error_patterns = [
                        r"SQL syntax",
                        r"mysql_fetch",
                        r"ORA-\d+",
                        r"PostgreSQL.*ERROR",
                        r"SQLite.*error",
                        r"ODBC.*Driver",
                    ]
                    for pattern in error_patterns:
                        if re.search(pattern, body, re.IGNORECASE):
                            verification_result["is_vulnerable"] = True
                            verification_result["evidence"] = f"SQL错误信息: {pattern}"
                            break
                
                elif vulnerability_type == "xss":
                    if payload in body:
                        verification_result["is_vulnerable"] = True
                        verification_result["evidence"] = "XSS payload 被反射到响应中"
                
                elif vulnerability_type == "command_injection":
                    # 检查命令执行结果
                    if "uid=" in body or "root:" in body:
                        verification_result["is_vulnerable"] = True
                        verification_result["evidence"] = "命令执行成功"
            
            verification_result["response_status"] = status_code
            verification_result["response_length"] = len(body)
            
        except Exception as e:
            verification_result["error"] = str(e)
        
        return verification_result

    # === Phase 1: 新 Runner 实现方法 ===

    async def _execute_command_via_runner(
        self,
        command: str,
        working_dir: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        host_project_dir: Optional[str] = None,
        project_root: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        使用 SandboxRunnerClient 执行命令 (新实现)

        保持返回格式与旧版本完全一致
        """
        timeout = timeout or self.config.timeout

        # 禁用代理环境变量
        no_proxy_env = {
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "http_proxy": "",
            "https_proxy": "",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }

        # 挂载项目目录时设置 PYTHONPATH
        project_env: Dict[str, str] = {}
        if host_project_dir and os.path.isdir(host_project_dir):
            project_env["PYTHONPATH"] = "/project"

        # 合并环境变量
        container_env = {**no_proxy_env, **project_env, **(env or {})}

        try:
            # 判断使用哪种 profile
            if project_root and os.path.isdir(project_root):
                # 使用 tool_workdir profile (只读挂载项目)
                result = await asyncio.to_thread(
                    self._runner_client.execute_in_project,
                    command=["sh", "-c", command],
                    project_dir=project_root,
                    timeout=timeout,
                    env=container_env,
                    network_mode=self.config.network_mode,
                    read_only=self.config.read_only,
                )
            else:
                # 使用 isolated_exec profile
                result = await asyncio.to_thread(
                    self._runner_client.execute_isolated,
                    command=["sh", "-c", command],
                    timeout=timeout,
                    env=container_env,
                )

            # 转换为旧格式
            return {
                "success": result.success,
                "stdout": result.stdout[:10000] if result.stdout else "",
                "stderr": result.stderr[:2000] if result.stderr else "",
                "exit_code": result.exit_code,
                "error": result.error,
                "image": result.image,
                "image_candidates": result.image_candidates,
            }

        except Exception as e:
            logger.error(f"Sandbox execution error (runner): {e}")
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "image": self._resolved_image,
                "image_candidates": list(self._last_image_candidates),
            }

    async def _execute_tool_command_via_runner(
        self,
        command: str,
        host_workdir: str,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None,
        network_mode: str = "none",
    ) -> Dict[str, Any]:
        """
        使用 SandboxRunnerClient 执行工具命令 (新实现)
        """
        timeout = timeout or self.config.timeout

        # 禁用代理环境变量
        no_proxy_env = {
            "HTTP_PROXY": "",
            "HTTPS_PROXY": "",
            "http_proxy": "",
            "https_proxy": "",
            "NO_PROXY": "*",
            "no_proxy": "*",
        }
        container_env = {**no_proxy_env, **(env or {})}

        try:
            # 清除代理变量前缀
            unset_proxy_prefix = "unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy 2>/dev/null; "
            wrapped_command = unset_proxy_prefix + command

            # 使用 tool_workdir profile
            result = await asyncio.to_thread(
                self._runner_client.execute_in_project,
                command=["sh", "-c", wrapped_command],
                project_dir=host_workdir,
                timeout=timeout,
                env=container_env,
                network_mode=network_mode,
                read_only=True,  # 工具命令默认只读
            )

            # 转换为旧格式
            return {
                "success": result.success,
                "stdout": result.stdout[:50000] if result.stdout else "",
                "stderr": result.stderr[:5000] if result.stderr else "",
                "exit_code": result.exit_code,
                "error": result.error,
                "image": result.image,
                "image_candidates": result.image_candidates,
            }

        except Exception as e:
            logger.error(f"Tool execution error (runner): {e}")
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
                "image": self._resolved_image,
                "image_candidates": list(self._last_image_candidates),
            }


class SandboxCommandInput(BaseModel):
    """沙箱命令输入"""
    command: str = Field(description="要执行的命令")
    timeout: int = Field(default=30, description="超时时间（秒）")


class SandboxTool(AgentTool):
    """
    沙箱执行工具
    在安全隔离的环境中执行代码和命令
    """

    # 允许的命令前缀 - 放宽限制以支持更灵活的测试
    ALLOWED_COMMANDS = [
        # 编程语言解释器
        "python", "python3", "node", "php", "ruby", "perl",
        "go", "java", "javac", "bash", "sh",
        # 网络工具
        "curl", "wget", "nc", "netcat",
        # 文件操作
        "cat", "head", "tail", "grep", "find", "ls", "wc",
        "sed", "awk", "cut", "sort", "uniq", "tr", "xargs",
        # 系统信息（用于验证命令执行）
        "echo", "printf", "test", "id", "whoami", "uname",
        "env", "printenv", "pwd", "hostname",
        # 编码/解码工具
        "base64", "xxd", "od", "hexdump",
        # 其他实用工具
        "timeout", "time", "sleep", "true", "false",
        "md5sum", "sha256sum", "strings",
    ]
    
    def __init__(self, sandbox_manager: Optional[SandboxManager] = None):
        super().__init__()
        self.sandbox_manager = sandbox_manager or SandboxManager()
    
    @property
    def name(self) -> str:
        return "sandbox_exec"
    
    @property
    def description(self) -> str:
        return """在安全沙箱中执行命令或代码。
用于验证漏洞、测试 PoC 或执行安全检查。

安全限制:
- 命令在 Docker 容器中执行
- 网络默认隔离
- 资源有限制
- 只允许特定命令

允许的命令: python, python3, node, curl, cat, grep, find, ls, echo, id

使用场景:
- 验证命令注入漏洞
- 执行 PoC 代码
- 测试 payload 效果"""
    
    @property
    def args_schema(self):
        return SandboxCommandInput
    
    async def _execute(
        self,
        command: str,
        timeout: int = 30,
        **kwargs
    ) -> ToolResult:
        """执行沙箱命令"""
        # 初始化沙箱
        await self.sandbox_manager.initialize()
        
        if not self.sandbox_manager.is_available:
            return self._build_execution_tool_result(
                success=False,
                command=command,
                result_payload={
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "",
                    "error": "沙箱环境不可用（Docker 未安装或未运行）",
                },
                error_message="沙箱环境不可用（Docker 未安装或未运行）",
                fallback_data="沙箱环境不可用（Docker 未安装或未运行）",
            )
        
        # 安全检查：验证命令是否允许
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return self._build_execution_tool_result(
                success=False,
                command=command,
                result_payload={
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "",
                    "error": "命令不能为空",
                },
                error_message="命令不能为空",
                fallback_data="命令不能为空",
            )
        
        base_cmd = cmd_parts[0]
        if not any(base_cmd.startswith(allowed) for allowed in self.ALLOWED_COMMANDS):
            error_text = f"命令 '{base_cmd}' 不在允许列表中。允许的命令: {', '.join(self.ALLOWED_COMMANDS)}"
            return self._build_execution_tool_result(
                success=False,
                command=command,
                result_payload={
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": "",
                    "error": error_text,
                },
                error_message=error_text,
                fallback_data=error_text,
            )
        
        # 执行命令
        result = await self.sandbox_manager.execute_command(
            command=command,
            timeout=timeout,
        )
        
        # 格式化输出
        output_parts = ["🐳 沙箱执行结果\n"]
        output_parts.append(f"命令: {command}")
        if result.get("image"):
            output_parts.append(f"镜像: {result['image']}")
        if result.get("image_candidates"):
            output_parts.append(f"镜像候选: {', '.join(result['image_candidates'])}")
        output_parts.append(f"退出码: {result['exit_code']}")
        
        if result["stdout"]:
            output_parts.append(f"\n标准输出:\n```\n{result['stdout']}\n```")
        
        if result["stderr"]:
            output_parts.append(f"\n标准错误:\n```\n{result['stderr']}\n```")
        
        if result.get("error"):
            output_parts.append(f"\n错误: {result['error']}")
        
        #  修复：当命令执行失败时，确保 error 字段包含有意义的错误信息
        # 如果 result['error'] 为空但执行失败，从 stderr 中提取错误
        error_message = result.get("error")
        if not error_message and not result.get("success", False):
            # 执行失败但没有 error 字段，尝试从 stderr 提取
            stderr = result.get("stderr", "")
            if stderr:
                # 取 stderr 的前 500 字符作为 error 摘要
                error_message = stderr[:500] if len(stderr) > 500 else stderr
            elif result.get("exit_code", 0) != 0:
                error_message = f"命令执行失败，退出码: {result.get('exit_code')}"
        
        return self._build_execution_tool_result(
            success=result["success"],
            command=command,
            result_payload=result,
            error_message=error_message,
            fallback_data="\n".join(output_parts),
        )

    def _build_execution_tool_result(
        self,
        *,
        success: bool,
        command: str,
        result_payload: Dict[str, Any],
        fallback_data: str,
        error_message: Optional[str] = None,
    ) -> ToolResult:
        base_cmd = str(command or "").strip().split()[0] if str(command or "").strip() else "sandbox_exec"
        command_chain = unique_command_chain(["sandbox_exec", base_cmd])
        display_command = build_display_command(command_chain)
        exit_code = int(result_payload.get("exit_code", -1))
        inline_code = self._extract_inline_code(command)
        entry: Dict[str, Any] = {
            "exit_code": exit_code,
            "status": build_execution_status(
                success=success,
                error=error_message or result_payload.get("error"),
                exit_code=exit_code,
            ),
            "title": "沙箱命令执行",
            "execution_command": command,
            "runtime_image": result_payload.get("image"),
            "stdout_preview": self._preview_text(result_payload.get("stdout", ""), 300),
            "stderr_preview": self._preview_text(result_payload.get("stderr", ""), 300),
            "artifacts": self._build_execution_artifacts(exit_code, result_payload),
            "code": inline_code,
        }
        validate_evidence_metadata(
            render_type="execution_result",
            command_chain=command_chain,
            display_command=display_command,
            entries=[entry],
        )
        return ToolResult(
            success=success,
            data=fallback_data,
            error=error_message,
            metadata={
                "render_type": "execution_result",
                "command_chain": command_chain,
                "display_command": display_command,
                "entries": [entry],
                "command": command,
                "exit_code": exit_code,
                "image": result_payload.get("image"),
                "image_candidates": result_payload.get("image_candidates") or [],
            },
        )

    @staticmethod
    def _preview_text(value: Any, max_length: int) -> str:
        text = str(value or "")
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."

    @staticmethod
    def _build_execution_artifacts(exit_code: int, result_payload: Dict[str, Any]) -> list[Dict[str, str]]:
        artifacts = [{"label": "退出码", "value": str(exit_code)}]
        if result_payload.get("image"):
            artifacts.append({"label": "镜像", "value": str(result_payload["image"])})
        image_candidates = result_payload.get("image_candidates") or []
        if image_candidates:
            artifacts.append(
                {"label": "镜像候选", "value": ", ".join(str(item) for item in image_candidates)}
            )
        return artifacts

    @staticmethod
    def _extract_inline_code(command: str) -> Optional[Dict[str, Any]]:
        text = str(command or "").strip()
        if "python3 -c " in text or "python -c " in text:
            snippet = text.split(" -c ", 1)[1].strip().strip("'").strip('"')
            return build_inline_code_lines(snippet, language="python")
        if "node -e " in text:
            snippet = text.split(" -e ", 1)[1].strip().strip("'").strip('"')
            return build_inline_code_lines(snippet, language="javascript")
        if text.startswith("bash -c ") or text.startswith("sh -c "):
            snippet = text.split(" -c ", 1)[1].strip().strip("'").strip('"')
            return build_inline_code_lines(snippet, language="bash")
        return None


