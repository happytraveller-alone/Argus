"""
Sandbox Runner Client - 高层客户端

职责:
1. Profile 到 spec 的映射 (isolated_exec, network_verify, tool_workdir)
2. Workspace 生命周期管理
3. 镜像选择与 fallback
4. 结果标准化
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Literal, Optional
from pathlib import Path

from app.core.config import settings
from app.services.sandbox_runner import (
    SandboxRunSpec,
    SandboxRunResult,
    run_sandbox_container,
)


ProfileType = Literal["isolated_exec", "network_verify", "tool_workdir"]


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
