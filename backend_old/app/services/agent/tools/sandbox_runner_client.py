"""
Sandbox Runner Client - 高层客户端

职责:
1. Profile 到 spec 的映射 (isolated_exec, network_verify, tool_workdir)
2. Workspace 生命周期管理
3. 镜像选择与 fallback
4. 结果标准化
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional, Set

try:
    import docker
except ImportError:  # pragma: no cover - optional dependency in unit-test environments
    docker = None
from app.services.agent.runtime_settings import settings


ProfileType = Literal["isolated_exec", "network_verify", "tool_workdir"]

MAX_RETAINED_LOG_CHARS = 12000
_DOCKER_ERRORS = getattr(docker, "errors", None)
DOCKER_EXCEPTION = getattr(_DOCKER_ERRORS, "DockerException", Exception)
DOCKER_NOT_FOUND = getattr(_DOCKER_ERRORS, "NotFound", Exception)
DOCKER_CONTAINER_ERROR = getattr(_DOCKER_ERRORS, "ContainerError", Exception)
DOCKER_API_ERROR = getattr(_DOCKER_ERRORS, "APIError", Exception)


@dataclass
class SandboxRunSpec:
    image: str
    command: List[str]
    workspace_dir: str
    working_dir: str = "/workspace"
    timeout_seconds: int = 60
    memory_limit: str = "512m"
    cpu_limit: float = 1.0
    network_mode: str = "none"
    read_only: bool = False
    user: str = "1000:1000"
    cap_drop: List[str] = field(default_factory=lambda: ["ALL"])
    security_opt: List[str] = field(default_factory=lambda: ["no-new-privileges:true"])
    env: Dict[str, str] = field(default_factory=dict)
    volumes: Dict[str, Dict[str, str]] = field(default_factory=dict)
    tmpfs: Dict[str, str] = field(default_factory=dict)
    expected_exit_codes: Set[int] = field(default_factory=lambda: {0})
    auto_remove: bool = False
    detach: bool = True

    def __post_init__(self):
        if not self.image:
            raise ValueError("image is required")
        if not self.workspace_dir:
            raise ValueError("workspace_dir is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not isinstance(self.expected_exit_codes, set):
            self.expected_exit_codes = set(self.expected_exit_codes or [0])


@dataclass
class SandboxRunResult:
    success: bool
    exit_code: int
    error: Optional[str] = None
    stdout: str = ""
    stderr: str = ""
    image: str = ""
    image_candidates: List[str] = field(default_factory=list)
    stdout_path: Optional[Path] = None
    stderr_path: Optional[Path] = None
    runner_meta_path: Optional[Path] = None
    duration_seconds: float = 0.0
    container_id: Optional[str] = None
    workspace_dir: Optional[Path] = None

    @property
    def has_output(self) -> bool:
        return bool(self.stdout or self.stderr)

    def to_dict(self) -> Dict[str, Any]:
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
    normalized = str(text or "")
    if len(normalized) <= max_chars:
        return normalized

    tail_chars = max(0, max_chars - 64)
    omitted_chars = len(normalized) - tail_chars
    return f"[truncated {omitted_chars} chars]\n{normalized[-tail_chars:]}"


def _write_retained_log(path: Path, text: str) -> str | None:
    content = _truncate_log_text(text)
    if not content.strip():
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def _write_full_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(text or ""), encoding="utf-8")
    return str(path)


def _ensure_workspace_artifacts(workspace_dir: str) -> tuple[Path, Path, Path, Path, Path]:
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
    start_time = time.time()
    workspace, logs_dir, meta_dir, _, _ = _ensure_workspace_artifacts(spec.workspace_dir)

    stdout_path = logs_dir / "stdout.log"
    stderr_path = logs_dir / "stderr.log"
    meta_path = meta_dir / "runner.json"

    container = None
    container_id: Optional[str] = None
    expected_exit_codes = {int(code) for code in (spec.expected_exit_codes or {0})}

    try:
        if docker is None:
            return SandboxRunResult(
                success=False,
                exit_code=-1,
                error="Execution error: docker python package is not installed",
                image=spec.image,
                workspace_dir=workspace,
            )
        client = docker.from_env()
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

        container = client.containers.run(**container_config)
        container_id = getattr(container, "id", None)
        if container_id and on_container_started is not None:
            on_container_started(container_id)

        wait_result = container.wait(timeout=max(1, int(spec.timeout_seconds)))
        exit_code = int((wait_result or {}).get("StatusCode", 1))

        stdout_bytes = container.logs(stdout=True, stderr=False)
        stderr_bytes = container.logs(stdout=False, stderr=True)
        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        _write_retained_log(stdout_path, stdout_text)
        _write_retained_log(stderr_path, stderr_text)

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

        return SandboxRunResult(
            success=exit_code in expected_exit_codes,
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

    except DOCKER_CONTAINER_ERROR as error:
        duration = time.time() - start_time
        error_msg = error.stderr.decode("utf-8", errors="replace") if error.stderr else str(error)
        _write_retained_log(stderr_path, error_msg)
        return SandboxRunResult(
            success=False,
            exit_code=getattr(error, "exit_status", -1),
            error=f"Container error: {error_msg}",
            stderr=error_msg,
            image=spec.image,
            duration_seconds=duration,
            workspace_dir=workspace,
            stderr_path=stderr_path,
        )
    except DOCKER_NOT_FOUND:
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            error=f"Image not found: {spec.image}",
            image=spec.image,
            workspace_dir=workspace,
        )
    except DOCKER_API_ERROR as error:
        duration = time.time() - start_time
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            error=f"Docker API error: {str(error)}",
            image=spec.image,
            duration_seconds=duration,
            workspace_dir=workspace,
        )
    except Exception as error:
        duration = time.time() - start_time
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            error=f"Execution error: {str(error)}",
            image=spec.image,
            duration_seconds=duration,
            workspace_dir=workspace,
        )
    finally:
        if container and not spec.auto_remove:
            try:
                container.remove(force=True)
            except Exception:
                pass


class SandboxRunnerClient:
    """
    Sandbox Runner 高层客户端

    提供三种 profile:
    - isolated_exec: 完全隔离执行 (无网络)
    - network_verify: 网络验证 (允许网络访问)
    - tool_workdir: 工具工作目录 (只读挂载项目)
    """

    def __init__(self):
        self.workspace_root = Path(settings.SCAN_WORKSPACE_ROOT) / "sandbox-runner"
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def _get_image_candidates(self) -> List[str]:
        """
        获取镜像候选列表 (优先级顺序)

        优先级:
        1. SANDBOX_RUNNER_IMAGE (如果配置了)
        2. SANDBOX_IMAGE (fallback)
        3. 默认本地镜像
        """
        candidates = []

        # 1. 优先使用 SANDBOX_RUNNER_IMAGE (如果配置了)
        if hasattr(settings, "SANDBOX_RUNNER_IMAGE") and settings.SANDBOX_RUNNER_IMAGE:
            candidate = str(settings.SANDBOX_RUNNER_IMAGE).strip()
            if candidate:
                candidates.append(candidate)

        # 2. Fallback 到 SANDBOX_IMAGE
        if settings.SANDBOX_IMAGE:
            candidate = str(settings.SANDBOX_IMAGE).strip()
            if candidate:
                candidates.append(candidate)

        # 3. 最终 fallback (本地镜像)
        candidates.extend([
            "ghcr.io/audittool/vulhunter-sandbox-runner:latest",
            "vulhunter/sandbox-runner:latest",
        ])

        # 去重并保持顺序
        seen = set()
        unique_candidates = []
        for img in candidates:
            if img and img not in seen:
                seen.add(img)
                unique_candidates.append(img)

        return unique_candidates

    def _select_image(self) -> str:
        """
        选择可用镜像

        简化版: 直接返回第一个候选
        生产版可以检查镜像是否存在
        """
        candidates = self._get_image_candidates()

        if candidates:
            return candidates[0]

        # 最终 fallback
        return "ghcr.io/audittool/vulhunter-sandbox-runner:latest"

    def _create_workspace(self, run_id: Optional[str] = None) -> Path:
        """
        创建运行 workspace

        结构:
        <workspace_root>/<run_id>/
          input/
          output/
          logs/
          meta/
        """
        if run_id is None:
            run_id = str(uuid.uuid4())[:8]

        workspace = self.workspace_root / run_id
        workspace.mkdir(parents=True, exist_ok=True)

        # 创建标准结构
        (workspace / "input").mkdir(exist_ok=True)
        (workspace / "output").mkdir(exist_ok=True)
        (workspace / "logs").mkdir(exist_ok=True)
        (workspace / "meta").mkdir(exist_ok=True)

        return workspace

    def _build_spec_for_profile(
        self,
        profile: ProfileType,
        command: List[str],
        workspace: Path,
        **kwargs,
    ) -> SandboxRunSpec:
        """
        根据 profile 构建 spec

        Profile 映射:
        - isolated_exec: 无网络, 挂载 input/output
        - network_verify: 允许网络, 挂载 input
        - tool_workdir: 只读挂载项目目录
        """

        # 基础配置
        base_spec = {
            "image": self._select_image(),
            "command": command,
            "workspace_dir": str(workspace),
            "timeout_seconds": kwargs.get("timeout", settings.SANDBOX_TIMEOUT),
            "memory_limit": kwargs.get("memory_limit", settings.SANDBOX_MEMORY_LIMIT),
            "cpu_limit": kwargs.get("cpu_limit", settings.SANDBOX_CPU_LIMIT),
            "env": kwargs.get("env", {}),
            "user": kwargs.get("user", "1000:1000"),
        }

        # Profile 特定配置
        if profile == "isolated_exec":
            # 完全隔离: 无网络, 最小权限
            base_spec.update(
                {
                    "network_mode": "none",
                    "read_only": False,
                    "working_dir": "/workspace",
                    "volumes": {
                        str(workspace / "input"): {"bind": "/workspace", "mode": "rw"},
                        str(workspace / "output"): {"bind": "/output", "mode": "rw"},
                    },
                    "tmpfs": {
                        "/tmp": "rw,exec,size=512m,mode=1777",
                        "/home/sandbox": "rw,exec,size=512m,mode=1777",
                    },
                }
            )

        elif profile == "network_verify":
            # 网络验证: 允许网络访问
            base_spec.update(
                {
                    "network_mode": "bridge",
                    "read_only": False,
                    "working_dir": "/workspace",
                    "volumes": {
                        str(workspace / "input"): {"bind": "/workspace", "mode": "rw"},
                    },
                    "tmpfs": {
                        "/tmp": "rw,exec,size=512m,mode=1777",
                        "/home/sandbox": "rw,exec,size=512m,mode=1777",
                    },
                }
            )

        elif profile == "tool_workdir":
            # 工具工作目录: 只读挂载项目目录
            project_dir = kwargs.get("project_dir")
            if not project_dir:
                raise ValueError("tool_workdir profile requires project_dir")

            base_spec.update(
                {
                    "network_mode": kwargs.get("network_mode", "none"),
                    "read_only": kwargs.get("read_only", True),
                    "working_dir": "/workspace",
                    "volumes": {
                        str(project_dir): {"bind": "/workspace", "mode": "ro"},
                    },
                    "tmpfs": {
                        "/tmp": "rw,exec,size=512m,mode=1777",
                        "/home/sandbox": "rw,exec,size=512m,mode=1777",
                    },
                }
            )

        else:
            raise ValueError(f"Unknown profile: {profile}")

        return SandboxRunSpec(**base_spec)

    def execute(
        self,
        profile: ProfileType,
        command: List[str],
        run_id: Optional[str] = None,
        **kwargs,
    ) -> SandboxRunResult:
        """
        执行 sandbox 命令

        Args:
            profile: 执行 profile (isolated_exec, network_verify, tool_workdir)
            command: 要执行的命令
            run_id: 可选的运行 ID
            **kwargs: 额外参数 (timeout, env, project_dir 等)

        Returns:
            SandboxRunResult
        """
        # 1. 创建 workspace
        workspace = self._create_workspace(run_id)

        # 2. 构建 spec
        spec = self._build_spec_for_profile(profile, command, workspace, **kwargs)

        # 3. 执行
        result = run_sandbox_container(spec)

        # 4. 补充 image_candidates (保持兼容)
        result.image_candidates = self._get_image_candidates()

        return result

    # === 便捷方法 ===

    def execute_isolated(
        self,
        command: List[str],
        **kwargs,
    ) -> SandboxRunResult:
        """隔离执行 (无网络)"""
        return self.execute("isolated_exec", command, **kwargs)

    def execute_with_network(
        self,
        command: List[str],
        **kwargs,
    ) -> SandboxRunResult:
        """网络执行 (用于验证)"""
        return self.execute("network_verify", command, **kwargs)

    def execute_in_project(
        self,
        command: List[str],
        project_dir: str,
        **kwargs,
    ) -> SandboxRunResult:
        """在项目目录执行 (只读挂载)"""
        return self.execute("tool_workdir", command, project_dir=project_dir, **kwargs)
