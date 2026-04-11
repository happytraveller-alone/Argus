"""
Sandbox Runner - 底层容器执行抽象

参考 scanner_runner.py 的模式,但适配 sandbox 特定需求:
- 默认 network_mode="none" (安全隔离)
- 默认 cap_drop=["ALL"] (最小权限)
- 支持 tmpfs 挂载
- 支持 security_opt
"""

from __future__ import annotations

import time
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import docker

from app.core.config import settings


MAX_RETAINED_LOG_CHARS = 12000
DOCKER_EXCEPTION = getattr(getattr(docker, "errors", None), "DockerException", Exception)
DOCKER_NOT_FOUND = getattr(getattr(docker, "errors", None), "NotFound", Exception)


@dataclass
class SandboxRunSpec:
    """Sandbox 容器执行规范"""

    # 基础执行参数
    image: str
    command: List[str]
    workspace_dir: str
    working_dir: str = "/workspace"

    # 安全与资源限制
    timeout_seconds: int = 60
    memory_limit: str = "512m"
    cpu_limit: float = 1.0
    network_mode: str = "none"  # "none" | "bridge" | "host"
    read_only: bool = False
    user: str = "1000:1000"

    # Docker 安全选项 (默认最严格)
    cap_drop: List[str] = field(default_factory=lambda: ["ALL"])
    security_opt: List[str] = field(default_factory=lambda: ["no-new-privileges:true"])

    # 挂载与环境
    env: Dict[str, str] = field(default_factory=dict)
    volumes: Dict[str, Dict[str, str]] = field(default_factory=dict)
    tmpfs: Dict[str, str] = field(default_factory=dict)

    # 执行策略
    expected_exit_codes: Set[int] = field(default_factory=lambda: {0})
    auto_remove: bool = False  # 设为 False,便于调试和日志收集
    detach: bool = True  # 默认分离模式

    def __post_init__(self):
        """验证配置"""
        if not self.image:
            raise ValueError("image is required")
        if not self.workspace_dir:
            raise ValueError("workspace_dir is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        # 确保 expected_exit_codes 是 set
        if not isinstance(self.expected_exit_codes, set):
            self.expected_exit_codes = set(self.expected_exit_codes or [0])


@dataclass
class SandboxRunResult:
    """Sandbox 执行结果"""

    # 执行状态
    success: bool
    exit_code: int
    error: Optional[str] = None

    # 输出 (内存态,保持工具兼容)
    stdout: str = ""
    stderr: str = ""

    # 镜像信息 (保持现有工具输出兼容)
    image: str = ""
    image_candidates: List[str] = field(default_factory=list)

    # 持久化路径
    stdout_path: Optional[Path] = None
    stderr_path: Optional[Path] = None
    runner_meta_path: Optional[Path] = None

    # 元数据
    duration_seconds: float = 0.0
    container_id: Optional[str] = None
    workspace_dir: Optional[Path] = None

    @property
    def has_output(self) -> bool:
        return bool(self.stdout or self.stderr)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典,用于 JSON 序列化"""
        return {
            "success": self.success,
            "exit_code": self.exit_code,
            "error": self.error,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "image": self.image,
            "image_candidates": self.image_candidates,
            "stdout_path": str(self.stdout_path) if self.stdout_path else None,
            "stderr_path": str(self.stderr_path) if self.stderr_path else None,
            "runner_meta_path": str(self.runner_meta_path) if self.runner_meta_path else None,
            "duration_seconds": self.duration_seconds,
            "container_id": self.container_id,
            "workspace_dir": str(self.workspace_dir) if self.workspace_dir else None,
        }


def _truncate_log_text(text: str, *, max_chars: int = MAX_RETAINED_LOG_CHARS) -> str:
    """截断日志文本"""
    normalized = str(text or "")
    if len(normalized) <= max_chars:
        return normalized

    tail_chars = max(0, max_chars - 64)
    omitted_chars = len(normalized) - tail_chars
    return f"[truncated {omitted_chars} chars]\n{normalized[-tail_chars:]}"


def _write_retained_log(path: Path, text: str) -> str | None:
    """写入截断后的日志"""
    content = _truncate_log_text(text)
    if not content.strip():
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def _write_full_text(path: Path, text: str) -> str:
    """写入完整文本"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or ""), encoding="utf-8")
    return str(path)


def _ensure_workspace_artifacts(workspace_dir: str) -> tuple[Path, Path, Path, Path, Path]:
    """确保 workspace 目录结构存在"""
    workspace = Path(workspace_dir)
    logs_dir = workspace / "logs"
    meta_dir = workspace / "meta"
    input_dir = workspace / "input"
    output_dir = workspace / "output"

    for dir_path in [logs_dir, meta_dir, input_dir, output_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)

    return workspace, logs_dir, meta_dir, input_dir, output_dir


def run_sandbox_container(
    spec: SandboxRunSpec,
    *,
    on_container_started: Callable[[str], None] | None = None,
) -> SandboxRunResult:
    """
    执行 sandbox 容器 (同步版本)

    参考: backend/app/services/scanner_runner.py 的模式
    适配: sandbox 特定的安全配置和挂载点
    """
    start_time = time.time()
    workspace, logs_dir, meta_dir, input_dir, output_dir = _ensure_workspace_artifacts(spec.workspace_dir)

    stdout_path = logs_dir / "stdout.log"
    stderr_path = logs_dir / "stderr.log"
    meta_path = meta_dir / "runner.json"

    container = None
    container_id: Optional[str] = None
    expected_exit_codes = {int(code) for code in (spec.expected_exit_codes or {0})}

    try:
        # 1. 初始化 Docker client
        client = docker.from_env()

        # 2. 准备容器配置
        container_config = {
            "image": spec.image,
            "command": spec.command,
            "detach": spec.detach,
            "auto_remove": spec.auto_remove,
            "working_dir": spec.working_dir,
            "environment": spec.env,
            "network_mode": spec.network_mode,
            "read_only": spec.read_only,
            "user": spec.user,
            "mem_limit": spec.memory_limit,
            "cpu_period": 100000,
            "cpu_quota": int(100000 * spec.cpu_limit),
            "cap_drop": spec.cap_drop,
            "security_opt": spec.security_opt,
            "volumes": spec.volumes,
            "tmpfs": spec.tmpfs,
        }

        # 3. 运行容器
        container = client.containers.run(**container_config)
        container_id = getattr(container, "id", None)

        if container_id and on_container_started is not None:
            on_container_started(container_id)

        # 4. 等待完成
        wait_result = container.wait(timeout=max(1, int(spec.timeout_seconds)))
        exit_code = int((wait_result or {}).get("StatusCode", 1))

        # 5. 获取输出
        stdout_bytes = container.logs(stdout=True, stderr=False)
        stderr_bytes = container.logs(stdout=False, stderr=True)

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        # 6. 写入日志文件
        _write_retained_log(stdout_path, stdout_text)
        _write_retained_log(stderr_path, stderr_text)

        # 7. 写入元数据
        duration = time.time() - start_time
        meta = {
            "image": spec.image,
            "command": spec.command,
            "exit_code": exit_code,
            "duration_seconds": duration,
            "timestamp": time.time(),
            "workspace": str(workspace),
            "container_id": container_id,
        }
        _write_full_text(meta_path, json.dumps(meta, indent=2))

        # 8. 构造结果
        success = exit_code in expected_exit_codes

        return SandboxRunResult(
            success=success,
            exit_code=exit_code,
            stdout=stdout_text,
            stderr=stderr_text,
            image=spec.image,
            image_candidates=[spec.image],
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            runner_meta_path=meta_path,
            duration_seconds=duration,
            container_id=container_id,
            workspace_dir=workspace,
        )

    except docker.errors.ContainerError as e:
        # 容器执行失败
        duration = time.time() - start_time
        error_msg = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)

        # 尝试写入错误日志
        _write_retained_log(stderr_path, error_msg)

        return SandboxRunResult(
            success=False,
            exit_code=getattr(e, "exit_status", -1),
            error=f"Container error: {error_msg}",
            stderr=error_msg,
            image=spec.image,
            duration_seconds=duration,
            workspace_dir=workspace,
            stderr_path=stderr_path,
        )

    except docker.errors.ImageNotFound:
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            error=f"Image not found: {spec.image}",
            image=spec.image,
            workspace_dir=workspace,
        )

    except docker.errors.APIError as e:
        duration = time.time() - start_time
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            error=f"Docker API error: {str(e)}",
            image=spec.image,
            duration_seconds=duration,
            workspace_dir=workspace,
        )

    except Exception as e:
        duration = time.time() - start_time
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            error=f"Execution error: {str(e)}",
            image=spec.image,
            duration_seconds=duration,
            workspace_dir=workspace,
        )

    finally:
        # 清理容器 (如果没有 auto_remove)
        if container and not spec.auto_remove:
            try:
                container.remove(force=True)
            except Exception:
                pass  # 忽略清理错误
