"""
测试 sandbox_runner_client.py - 高层客户端

参考: tests/test_flow_parser_runner_client.py
"""

import os
import pytest
from pathlib import Path

from app.services.sandbox_runner_client import SandboxRunnerClient


def test_client_initialization(tmp_path):
    """测试 client 初始化"""
    client = SandboxRunnerClient()
    assert client.workspace_root.exists()
    assert "sandbox-runner" in str(client.workspace_root)


def test_image_candidates_selection():
    """测试镜像选择逻辑"""
    client = SandboxRunnerClient()
    candidates = client._get_image_candidates()

    assert len(candidates) > 0
    assert all(isinstance(img, str) for img in candidates)
    # 应该包含配置的镜像
    assert any("sandbox" in img.lower() for img in candidates)
    # 不应该有重复
    assert len(candidates) == len(set(candidates))


def test_workspace_creation():
    """测试 workspace 创建"""
    client = SandboxRunnerClient()
    workspace = client._create_workspace(run_id="test123")

    assert workspace.exists()
    assert "test123" in str(workspace)
    assert (workspace / "input").exists()
    assert (workspace / "output").exists()
    assert (workspace / "logs").exists()
    assert (workspace / "meta").exists()


def test_profile_spec_building_isolated():
    """测试 isolated_exec profile"""
    client = SandboxRunnerClient()
    workspace = client._create_workspace(run_id="test_isolated")

    spec = client._build_spec_for_profile(
        "isolated_exec",
        ["echo", "test"],
        workspace,
    )

    assert spec.network_mode == "none"
    assert spec.working_dir == "/workspace"
    assert spec.image is not None
    # 应该挂载 input 和 output
    assert len(spec.volumes) == 2


def test_profile_spec_building_network():
    """测试 network_verify profile"""
    client = SandboxRunnerClient()
    workspace = client._create_workspace(run_id="test_network")

    spec = client._build_spec_for_profile(
        "network_verify",
        ["curl", "example.com"],
        workspace,
    )

    assert spec.network_mode == "bridge"
    assert spec.working_dir == "/workspace"


def test_profile_spec_building_tool_workdir(tmp_path):
    """测试 tool_workdir profile"""
    client = SandboxRunnerClient()
    workspace = client._create_workspace(run_id="test_tool")
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    spec = client._build_spec_for_profile(
        "tool_workdir",
        ["ls", "-la"],
        workspace,
        project_dir=str(project_dir),
    )

    assert spec.read_only is True
    assert str(project_dir) in str(spec.volumes)


def test_profile_tool_workdir_requires_project_dir():
    """测试 tool_workdir 需要 project_dir"""
    client = SandboxRunnerClient()
    workspace = client._create_workspace(run_id="test_error")

    with pytest.raises(ValueError, match="requires project_dir"):
        client._build_spec_for_profile(
            "tool_workdir",
            ["ls"],
            workspace,
        )


def test_unknown_profile():
    """测试未知 profile"""
    client = SandboxRunnerClient()
    workspace = client._create_workspace(run_id="test_unknown")

    with pytest.raises(ValueError, match="Unknown profile"):
        client._build_spec_for_profile(
            "invalid_profile",
            ["echo", "test"],
            workspace,
        )


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境",
)
def test_execute_isolated():
    """测试隔离执行"""
    client = SandboxRunnerClient()
    result = client.execute_isolated(["echo", "hello from runner"])

    assert result.success is True
    assert "hello from runner" in result.stdout
    assert result.image_candidates is not None
    assert len(result.image_candidates) > 0


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境",
)
def test_execute_network_isolation():
    """测试网络隔离"""
    client = SandboxRunnerClient()

    # isolated_exec 应该无法访问网络
    result = client.execute_isolated(["ping", "-c", "1", "8.8.8.8"])
    # network=none 应该失败
    assert result.success is False


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境",
)
def test_execute_in_project(tmp_path):
    """测试项目目录执行"""
    client = SandboxRunnerClient()

    # 创建测试项目目录
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    (project_dir / "test.txt").write_text("test content")

    # 执行 ls 命令
    result = client.execute_in_project(
        command=["ls", "-la"],
        project_dir=str(project_dir),
    )

    assert result.success is True
    assert "test.txt" in result.stdout


def test_result_compatibility():
    """测试结果兼容性 (保持与 SandboxManager 输出一致)"""
    client = SandboxRunnerClient()

    # 创建 workspace 和 spec
    workspace = client._create_workspace(run_id="test_compat")
    spec = client._build_spec_for_profile("isolated_exec", ["echo", "test"], workspace)

    # 验证 spec 包含必需字段
    assert hasattr(spec, "image")
    assert hasattr(spec, "command")
    assert hasattr(spec, "network_mode")
    assert hasattr(spec, "security_opt")
    assert hasattr(spec, "cap_drop")

    # 验证安全配置
    assert "ALL" in spec.cap_drop
    assert "no-new-privileges:true" in spec.security_opt
