"""
测试 sandbox_runner.py - 底层容器执行抽象

参考: tests/test_scanner_runner.py
"""

import os
import pytest
from pathlib import Path

from app.services.sandbox_runner import (
    SandboxRunSpec,
    SandboxRunResult,
    run_sandbox_container,
)


def test_sandbox_run_spec_validation():
    """测试 spec 验证"""

    # 正常情况
    spec = SandboxRunSpec(
        image="alpine:latest",
        command=["echo", "hello"],
        workspace_dir="/tmp/test",
    )
    assert spec.image == "alpine:latest"
    assert spec.network_mode == "none"
    assert "ALL" in spec.cap_drop
    assert spec.timeout_seconds == 60

    # 缺少必需字段
    with pytest.raises(ValueError, match="image is required"):
        SandboxRunSpec(image="", command=[], workspace_dir="/tmp")

    with pytest.raises(ValueError, match="workspace_dir is required"):
        SandboxRunSpec(image="test", command=[], workspace_dir="")


def test_sandbox_run_result_to_dict():
    """测试结果序列化"""

    result = SandboxRunResult(
        success=True,
        exit_code=0,
        stdout="output",
        stderr="",
        image="alpine:latest",
    )

    data = result.to_dict()
    assert data["success"] is True
    assert data["exit_code"] == 0
    assert data["stdout"] == "output"
    assert isinstance(data["image_candidates"], list)


def test_sandbox_run_result_has_output():
    """测试 has_output 属性"""

    result1 = SandboxRunResult(success=True, exit_code=0, stdout="test", stderr="")
    assert result1.has_output is True

    result2 = SandboxRunResult(success=True, exit_code=0, stdout="", stderr="error")
    assert result2.has_output is True

    result3 = SandboxRunResult(success=True, exit_code=0, stdout="", stderr="")
    assert result3.has_output is False


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境",
)
def test_run_sandbox_container_basic(tmp_path):
    """测试基础容器执行"""

    workspace = tmp_path / "sandbox_test"
    spec = SandboxRunSpec(
        image="alpine:latest",
        command=["echo", "hello world"],
        workspace_dir=str(workspace),
    )

    result = run_sandbox_container(spec)

    assert result.success is True
    assert result.exit_code == 0
    assert "hello world" in result.stdout
    assert result.stdout_path is not None
    assert result.stdout_path.exists()
    assert result.runner_meta_path is not None
    assert result.runner_meta_path.exists()


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境",
)
def test_run_sandbox_container_network_isolation(tmp_path):
    """测试网络隔离"""

    workspace = tmp_path / "network_test"
    spec = SandboxRunSpec(
        image="alpine:latest",
        command=["ping", "-c", "1", "8.8.8.8"],
        workspace_dir=str(workspace),
        network_mode="none",
    )

    result = run_sandbox_container(spec)

    # network=none 应该失败
    assert result.success is False
    assert result.exit_code != 0


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境",
)
def test_run_sandbox_container_with_env(tmp_path):
    """测试环境变量"""

    workspace = tmp_path / "env_test"
    spec = SandboxRunSpec(
        image="alpine:latest",
        command=["sh", "-c", "echo $TEST_VAR"],
        workspace_dir=str(workspace),
        env={"TEST_VAR": "test_value"},
    )

    result = run_sandbox_container(spec)

    assert result.success is True
    assert "test_value" in result.stdout


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境",
)
def test_run_sandbox_container_timeout(tmp_path):
    """测试超时处理"""

    workspace = tmp_path / "timeout_test"
    spec = SandboxRunSpec(
        image="alpine:latest",
        command=["sleep", "10"],
        workspace_dir=str(workspace),
        timeout_seconds=1,  # 1秒超时
    )

    result = run_sandbox_container(spec)

    # 应该超时
    # 注意: 超时行为可能因实现而异,这里只检查是否有错误
    assert result.exit_code != 0 or result.error is not None


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境",
)
def test_run_sandbox_container_nonzero_exit(tmp_path):
    """测试非零退出码"""

    workspace = tmp_path / "exit_code_test"
    spec = SandboxRunSpec(
        image="alpine:latest",
        command=["sh", "-c", "exit 42"],
        workspace_dir=str(workspace),
        expected_exit_codes={42},  # 期望退出码 42
    )

    result = run_sandbox_container(spec)

    assert result.exit_code == 42
    assert result.success is True  # 因为 42 在 expected_exit_codes 中


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境",
)
def test_run_sandbox_container_workspace_structure(tmp_path):
    """测试 workspace 目录结构"""

    workspace = tmp_path / "workspace_test"
    spec = SandboxRunSpec(
        image="alpine:latest",
        command=["echo", "test"],
        workspace_dir=str(workspace),
    )

    result = run_sandbox_container(spec)

    assert result.success is True

    # 检查目录结构
    assert (workspace / "logs").exists()
    assert (workspace / "meta").exists()
    assert (workspace / "input").exists()
    assert (workspace / "output").exists()

    # 检查日志文件
    assert (workspace / "logs" / "stdout.log").exists()
    assert (workspace / "meta" / "runner.json").exists()
