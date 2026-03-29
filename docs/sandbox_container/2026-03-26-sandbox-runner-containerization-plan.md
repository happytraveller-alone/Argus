# Sandbox Runner Containerization Implementation Plan

> **For agentic workers:** Prefer implementing this plan in phases. Phase 1 is the only in-scope implementation plan in this document. Do not start by introducing a brand new `sandbox-runner` image, compose service, or publish workflow.

**Goal:** 将 `run_code`、`sandbox_exec`、`verify_vulnerability` 以及现有 `SandboxManager` 兼容调用路径，从“各工具直接依赖内联 Docker 细节”的实现，迁移为统一的 sandbox runner 抽象；本轮优先复用现有 `SANDBOX_IMAGE` 运行时，不强制拆分独立 `sandbox-runner` 镜像。

**Architecture:** 新增 `SandboxRunSpec`、`SandboxRunResult`、`run_sandbox_container(...)` 和 `SandboxRunnerClient`，由 client 负责 workspace、profile、镜像选择和结果整形。`SandboxManager` 保留公开方法和生命周期语义，但内部改为委托给新 client，作为兼容门面继续服务现有调用者。

**Tech Stack:** Python, Docker SDK, FastAPI backend, existing runner patterns, pytest, uv

---

## Why This Plan Was Adjusted

原始版本把“新增独立 `sandbox-runner` 镜像 + compose 预热服务 + workflow 发布链路”作为默认路径，但仓库现状并不支持将这一步当作低风险重构：

- `SandboxManager` 的调用面比文档最初假设更广，不止 `run_code`、`sandbox_exec`、`verify_vulnerability` 在使用。
- 现有 scanner runner 的 compose / workflow 交付链路已经成熟，但 sandbox 与 scanner 的职责不同，不能机械照搬。
- `docker/sandbox/Dockerfile` 目前承载大量真实运行能力，直接拆出新镜像会放大迁移成本和兼容风险。
- 原文中的若干测试命令与仓库实际 `uv` / `pytest` 调用方式不一致，按原文执行会直接失败。

因此，本计划改为两阶段：

- **Phase 1（本轮实施）**：抽象 runner 契约，统一执行路径，保持兼容。
- **Phase 2（后续可选）**：在 Phase 1 稳定后，再评估是否拆分独立 `sandbox-runner` 镜像和交付链路。

---

## Scope For Phase 1

### In Scope

- 新增 sandbox runner 抽象层和高层 client
- 将核心公开工具迁移到新抽象：
  - `run_code`
  - `sandbox_exec`
  - `verify_vulnerability`
- 将 `SandboxManager` 改造成兼容 facade，继续覆盖其他现存调用者
- 新增/更新针对 runner 契约、client、兼容层和核心工具的测试
- 增加可选配置 `SANDBOX_RUNNER_IMAGE`，但默认仍可回退到 `SANDBOX_IMAGE`

### Out Of Scope

- 不新增 `backend/docker/sandbox-runner.Dockerfile`
- 不新增 compose `sandbox-runner` 预热服务
- 不修改 `.github/workflows/docker-publish.yml` 发布新的 sandbox runner 镜像
- 不要求将所有历史/遗留沙箱工具都迁移成直接依赖 `SandboxRunnerClient`
- 不改变公开工具名、args schema、metadata/evidence 协议

---

## 当前代码现状

### 已存在的 Sandbox 实现

**核心工具** (`backend/app/services/agent/tools/`):
- ✅ `sandbox_tool.py` (54KB) - 包含完整的 `SandboxManager` 实现
  - `execute_command()` - 基础命令执行
  - `execute_tool_command()` - 工具工作目录执行
  - `execute_http_request()` - 网络请求执行
  - `verify_vulnerability()` - 漏洞验证编排
- ✅ `run_code.py` (35KB) - `RunCodeTool` 实现，直接依赖 Docker SDK
- ✅ `sandbox_vuln.py` (55KB) - 漏洞验证工具
- ✅ `sandbox_language.py` (46KB) - 语言特定沙箱工具

**配置** (`backend/app/core/config.py`):
- ✅ `SANDBOX_IMAGE`: `"vulhunter/sandbox:latest"`
- ✅ `SANDBOX_MEMORY_LIMIT`: `"512m"`
- ✅ `SANDBOX_CPU_LIMIT`: `1.0`
- ✅ `SANDBOX_TIMEOUT`: `60`
- ✅ `SANDBOX_NETWORK_MODE`: `"none"`
- ✅ `SCAN_WORKSPACE_ROOT`: `"/tmp/vulhunter/scans"`
- ❌ `SANDBOX_RUNNER_IMAGE` - **需新增**

**Docker 镜像** (`docker/sandbox/`):
- ✅ `Dockerfile` (10KB) - 完整的 sandbox 运行时镜像
- ✅ `seccomp.json` - 安全策略配置
- ✅ `build.sh` / `build.ps1` / `build.bat` - 构建脚本

**参考实现**:
- ✅ `backend/app/services/scanner_runner.py` - Scanner runner 模式
- ✅ `backend/app/services/flow_parser_runner.py` - Flow parser runner 模式
- ✅ `backend/tests/test_scanner_runner.py` - Scanner 测试
- ✅ `backend/tests/test_flow_parser_runner_client.py` - Flow parser 测试

### SandboxManager 当前调用者

通过代码扫描发现的使用情况：
```bash
# backend/app/services/agent/tools/external_tools.py
from .sandbox_tool import SandboxManager

class ExecuteToolCommandTool:
    def __init__(self, project_root: str, sandbox_manager: Optional["SandboxManager"] = None):
        self.sandbox_manager = sandbox_manager or SandboxManager()

class ExecuteHttpRequestTool:
    def __init__(self, project_root: str, sandbox_manager: Optional["SandboxManager"] = None):
        self.sandbox_manager = sandbox_manager or SandboxManager()
```

**⚠️ 兼容性要求**：
- `SandboxManager` 的公开接口不能破坏
- `external_tools.py` 中的工具需继续工作
- 其他可能的隐式调用者需要识别和保护

### 测试现状

**已有测试**:
- ✅ `backend/tests/simple_sandbox_test.py` (12KB) - 基础 sandbox 烟雾测试
  - 需 `RUN_SANDBOX_TESTS=1` 环境变量启用
  - 依赖 Docker 可用性

**缺失测试**:
- ❌ `test_sandbox_runner.py` - 需新建
- ❌ `test_sandbox_runner_client.py` - 需新建

---

## File Structure

### New Files (需创建)

- `backend/app/services/sandbox_runner.py` ⭐
  - 定义底层 runner spec/result
  - 实现 `SandboxRunSpec`, `SandboxRunResult`
  - 实现 `run_sandbox_container(...)` 核心执行函数
  - 参考：`scanner_runner.py` 的模式

- `backend/app/services/sandbox_runner_client.py` ⭐
  - 提供高层 client
  - 实现 profile 映射（isolated_exec, network_verify, tool_workdir）
  - 实现镜像选择逻辑（SANDBOX_RUNNER_IMAGE fallback to SANDBOX_IMAGE）
  - workspace 生命周期管理

- `backend/tests/test_sandbox_runner.py`
  - `run_sandbox_container(...)` 的底层契约测试
  - spec/result 字段完整性测试
  - 日志/元数据持久化测试

- `backend/tests/test_sandbox_runner_client.py`
  - `SandboxRunnerClient` 的 workspace、profile、image fallback 测试
  - 结果解析和错误处理测试

### Modified Files (需修改)

- `backend/app/core/config.py`
  - **新增配置**：
    ```python
    # Sandbox Runner 配置
    SANDBOX_RUNNER_IMAGE: str = "vulhunter/sandbox-runner:latest"
    SANDBOX_RUNNER_ENABLED: bool = True
    SANDBOX_RUNNER_TIMEOUT: int = 60
    SANDBOX_RUNNER_WORKSPACE_ROOT: str = "{SCAN_WORKSPACE_ROOT}/sandbox-runner"
    ```
  - **保留兼容**：`SANDBOX_IMAGE` 作为 fallback

- `backend/app/services/agent/tools/sandbox_tool.py` ⭐⭐⭐
  - **重构 `SandboxManager`**：
    - 保留公开方法签名（`execute_command`, `execute_tool_command`, `execute_http_request`, `verify_vulnerability`）
    - 内部委托给 `SandboxRunnerClient`
    - 保持 `initialize()` / `is_available` / `get_diagnosis()` 语义
  - **注意**：此文件 54KB，重构需谨慎，确保不破坏现有调用者

- `backend/app/services/agent/tools/run_code.py`
  - 从直接使用 Docker SDK 改为使用 `SandboxRunnerClient`
  - 保持工具输出格式不变（frontend 依赖）
  - 保持元数据字段（`image`, `image_candidates`, `stdout`, `stderr`）

- `backend/app/services/agent/tools/external_tools.py`
  - **可能不需修改**：通过 `SandboxManager` 兼容门面自动适配
  - 需验证 `ExecuteToolCommandTool` 和 `ExecuteHttpRequestTool` 仍正常工作

- `backend/tests/test_run_code_tool.py`
  - 添加 runner 抽象后的兼容性断言
  - 验证输出格式不变

- `backend/tests/agent/test_tools.py`
  - 增加 `verify_vulnerability` 的元数据契约断言

- `backend/tests/simple_sandbox_test.py`
  - 更新为验证新 runner 抽象通过兼容层工作
  - 保持可选执行（需 `RUN_SANDBOX_TESTS=1`）

### Existing Files To Reference (参考模式)

- `backend/app/services/scanner_runner.py` ⭐
  - **关键参考**：runner spec/result 模式
  - **关键参考**：容器启动、日志留存、清理流程

- `backend/app/services/flow_parser_runner.py` ⭐
  - **关键参考**：client 层抽象
  - **关键参考**：workspace 管理

- `backend/tests/test_scanner_runner.py`
  - **测试模式参考**：runner 契约测试

- `backend/tests/test_flow_parser_runner_client.py`
  - **测试模式参考**：client 层测试

---

## Runtime Contract

### `SandboxRunSpec`

字段至少包含：

- `image`
- `command`
- `workspace_dir`
- `working_dir`
- `timeout_seconds`
- `env`
- `network_mode`
- `read_only`
- `user`
- `volumes`
- `tmpfs`
- `expected_exit_codes`

约束：

- 保持 sandbox 特有的运行时控制显式可见，不要把所有逻辑藏进 client。
- `cap_drop=["ALL"]` 和 `security_opt=["no-new-privileges:true"]` 为默认安全基线。
- 默认挂载的 scratch workspace 路径固定为 `/workspace`。
- 如需暴露项目源码，统一只读挂载到 `/project`。

### `SandboxRunResult`

返回值至少包含：

- `success`
- `exit_code`
- `stdout`
- `stderr`
- `error`
- `image`
- `image_candidates`
- `stdout_path`
- `stderr_path`
- `runner_meta_path`

约束：

- 不能只保留日志路径，必须继续向上提供工具层当前依赖的内存态 `stdout` / `stderr` / `error` 字段。
- 保留 `image` 和 `image_candidates`，避免破坏现有工具输出与测试。

### Workspace Layout

统一使用：

```text
<SCAN_WORKSPACE_ROOT>/sandbox-runner/<run_id>/
  input/
  output/
  logs/
    stdout.log
    stderr.log
  meta/
    runner.json
```

其中：

- `input/` 用于必要的 staged 输入
- `output/` 预留给后续扩展，不要求本轮每种调用都产生产物
- `logs/` 和 `meta/` 为底层 runner 统一维护

---

## Client And Profile Mapping

`SandboxRunnerClient` 负责集中维护 profile 到运行时参数的映射，避免每个工具自己拼 Docker 细节。

### Required Profiles

- `isolated_exec`
  - 供 `run_code` 和 `sandbox_exec` 使用
  - `network_mode=none`
- `network_verify`
  - 供 `execute_http_request` 和 `verify_vulnerability` 使用
  - `network_mode=bridge`
- `tool_workdir`
  - 供 `execute_tool_command` 使用
  - 将指定工作目录只读挂载到 `/workspace`

### Image Resolution

镜像选择顺序固定为：

1. `SANDBOX_RUNNER_IMAGE`
2. `SANDBOX_IMAGE`
3. 现有 legacy fallback candidates

要求：

- 继续保留当前 `SandboxManager` 的本地镜像优先和候选列表行为
- 不要把“必须存在新镜像”作为 `initialize()` 成功前提

---

## Compatibility Rules

`SandboxManager` 在 Phase 1 仍然是对外兼容入口，必须保留以下行为：

- `initialize()`：仍负责建立 Docker 可用性判断
- `is_available`：继续代表“Docker sandbox execution 可用”
- `get_diagnosis()`：继续返回面向调用者的可读诊断信息
- `execute_command(...)`
- `execute_tool_command(...)`
- `execute_http_request(...)`
- `verify_vulnerability(...)`

兼容要求：

- 公开方法名不变
- 返回字段不删减
- 现有任务入口继续可共享一个长生命周期 `SandboxManager` 实例
- 其他直接依赖 `SandboxManager` 的调用者不要求本轮改造，但不能被破坏

---

## Implementation Tasks (详细步骤与代码示例)

### Task 1: Define sandbox runner execution contracts

**目标**：创建底层 runner 抽象，参考 `scanner_runner.py` 但适配 sandbox 特定需求

**Files:**
- Create: `backend/app/services/sandbox_runner.py`
- Create: `backend/tests/test_sandbox_runner.py`

---

#### Step 1: 创建基础结构

**1.1 定义 SandboxRunSpec** (`sandbox_runner.py`):

参考 `scanner_runner.py` 的模式，但增加 sandbox 特有字段：

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

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
    network_mode: str = "none"  # "none" | "bridge"
    read_only: bool = False
    user: str = "sandbox"

    # Docker 安全选项（默认最严格）
    cap_drop: List[str] = field(default_factory=lambda: ["ALL"])
    security_opt: List[str] = field(default_factory=lambda: ["no-new-privileges:true"])

    # 挂载与环境
    env: Dict[str, str] = field(default_factory=dict)
    volumes: Dict[str, Dict[str, str]] = field(default_factory=dict)
    tmpfs: Dict[str, str] = field(default_factory=dict)

    # 执行策略
    expected_exit_codes: Set[int] = field(default_factory=lambda: {0})
    auto_remove: bool = True
    detach: bool = False

    def __post_init__(self):
        """验证配置"""
        if not self.image:
            raise ValueError("image is required")
        if not self.workspace_dir:
            raise ValueError("workspace_dir is required")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
```

**1.2 定义 SandboxRunResult** (`sandbox_runner.py`):

```python
from pathlib import Path

@dataclass
class SandboxRunResult:
    """Sandbox 执行结果"""

    # 执行状态
    success: bool
    exit_code: int
    error: Optional[str] = None

    # 输出（内存态，保持工具兼容）
    stdout: str = ""
    stderr: str = ""

    # 镜像信息（保持现有工具输出兼容）
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
        """转换为字典，用于 JSON 序列化"""
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
```

**1.3 实现 run_sandbox_container** (`sandbox_runner.py`):

```python
import time
import json
import docker
from pathlib import Path
from typing import Dict, Any

def run_sandbox_container(spec: SandboxRunSpec) -> SandboxRunResult:
    """
    执行 sandbox 容器

    参考：backend/app/services/scanner_runner.py 的模式
    """
    start_time = time.time()
    workspace_path = Path(spec.workspace_dir)

    # 1. 创建 workspace 结构
    logs_dir = workspace_path / "logs"
    meta_dir = workspace_path / "meta"
    input_dir = workspace_path / "input"
    output_dir = workspace_path / "output"

    for dir_path in [logs_dir, meta_dir, input_dir, output_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)

    stdout_path = logs_dir / "stdout.log"
    stderr_path = logs_dir / "stderr.log"
    meta_path = meta_dir / "runner.json"

    try:
        # 2. 初始化 Docker client
        client = docker.from_env()

        # 3. 准备容器配置
        container_config = {
            "image": spec.image,
            "command": spec.command,
            "working_dir": spec.working_dir,
            "environment": spec.env,
            "network_mode": spec.network_mode,
            "read_only": spec.read_only,
            "user": spec.user,
            "detach": spec.detach,
            "auto_remove": spec.auto_remove,
            "cap_drop": spec.cap_drop,
            "security_opt": spec.security_opt,
            "mem_limit": spec.memory_limit,
            "nano_cpus": int(spec.cpu_limit * 1e9),
            "volumes": spec.volumes,
            "tmpfs": spec.tmpfs,
        }

        # 4. 运行容器
        container = client.containers.run(**container_config)

        # 5. 等待完成（如果 detach=False）
        if not spec.detach:
            result = container.wait(timeout=spec.timeout_seconds)
            exit_code = result.get("StatusCode", -1)

            # 6. 获取输出
            stdout_bytes = container.logs(stdout=True, stderr=False)
            stderr_bytes = container.logs(stdout=False, stderr=True)

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # 7. 写入日志文件
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text(stderr, encoding="utf-8")

            # 8. 写入元数据
            duration = time.time() - start_time
            meta = {
                "image": spec.image,
                "command": spec.command,
                "exit_code": exit_code,
                "duration_seconds": duration,
                "timestamp": time.time(),
                "workspace": str(workspace_path),
            }
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

            # 9. 构造结果
            success = exit_code in spec.expected_exit_codes

            return SandboxRunResult(
                success=success,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                image=spec.image,
                image_candidates=[spec.image],
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                runner_meta_path=meta_path,
                duration_seconds=duration,
                container_id=container.id,
                workspace_dir=workspace_path,
            )

        else:
            # detach 模式，返回容器信息
            return SandboxRunResult(
                success=True,
                exit_code=0,
                image=spec.image,
                container_id=container.id,
                workspace_dir=workspace_path,
            )

    except docker.errors.ContainerError as e:
        # 容器执行失败
        duration = time.time() - start_time
        return SandboxRunResult(
            success=False,
            exit_code=e.exit_status,
            error=f"Container error: {e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)}",
            stderr=e.stderr.decode("utf-8", errors="replace") if e.stderr else "",
            image=spec.image,
            duration_seconds=duration,
            workspace_dir=workspace_path,
        )

    except docker.errors.ImageNotFound:
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            error=f"Image not found: {spec.image}",
            image=spec.image,
            workspace_dir=workspace_path,
        )

    except Exception as e:
        duration = time.time() - start_time
        return SandboxRunResult(
            success=False,
            exit_code=-1,
            error=f"Execution error: {str(e)}",
            image=spec.image,
            duration_seconds=duration,
            workspace_dir=workspace_path,
        )
```

---

#### Step 2: 编写测试

**2.1 创建测试** (`tests/test_sandbox_runner.py`):

```python
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

    # 缺少必需字段
    with pytest.raises(ValueError, match="image is required"):
        SandboxRunSpec(image="", command=[], workspace_dir="/tmp")


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


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境"
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
    assert result.stdout_path.exists()
    assert result.runner_meta_path.exists()


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker 环境"
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
```

**2.2 运行测试**:

```bash
cd backend

# 首次运行，应该失败（因为 sandbox_runner.py 未实现）
UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest \
  tests/test_sandbox_runner.py -v

# 实现后运行（需 Docker）
RUN_SANDBOX_TESTS=1 UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest \
  tests/test_sandbox_runner.py -v
```

---

#### Step 3: 实施建议

**参考现有实现**:

1. **Scanner Runner 模式** (`backend/app/services/scanner_runner.py`):
   ```bash
   # 查看参考实现
   cat backend/app/services/scanner_runner.py | head -200
   ```

2. **关键要点**:
   - 使用 `docker.from_env()` 初始化客户端
   - 使用 `container.wait(timeout=...)` 控制超时
   - 使用 `container.logs()` 分别获取 stdout/stderr
   - workspace 结构：`logs/`, `meta/`, `input/`, `output/`
   - 错误处理：`ContainerError`, `ImageNotFound`, `APIError`

3. **Sandbox 特定调整**:
   - 默认 `network_mode="none"` （scanner 可能是 bridge）
   - 默认 `cap_drop=["ALL"]` （最严格）
   - 支持 `tmpfs` 挂载
   - 支持 `security_opt`

---

#### Step 4: 验证通过

```bash
# 完整测试
RUN_SANDBOX_TESTS=1 UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest \
  backend/tests/test_sandbox_runner.py -v --tb=short
```

### Task 2: Add `SandboxRunnerClient`

**目标**：创建高层 client，封装 profile 映射、workspace 管理和镜像选择

**Files:**
- Create: `backend/app/services/sandbox_runner_client.py`
- Create: `backend/tests/test_sandbox_runner_client.py`

---

#### Step 1: 实现 SandboxRunnerClient

**参考现有配置** (`backend/app/core/config.py`):

```python
# 当前已有的配置
SANDBOX_IMAGE: str = "vulhunter/sandbox:latest"
SANDBOX_MEMORY_LIMIT: str = "512m"
SANDBOX_CPU_LIMIT: float = 1.0
SANDBOX_TIMEOUT: int = 60
SANDBOX_NETWORK_MODE: str = "none"
SCAN_WORKSPACE_ROOT: str = "/tmp/vulhunter/scans"
```

**实现 Client** (`sandbox_runner_client.py`):

```python
from typing import Dict, List, Optional, Literal
from pathlib import Path
import uuid
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

    职责：
    1. Profile 到 spec 的映射
    2. Workspace 生命周期管理
    3. 镜像选择与 fallback
    4. 结果标准化
    """

    def __init__(self):
        self.workspace_root = Path(settings.SCAN_WORKSPACE_ROOT) / "sandbox-runner"
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    def _get_image_candidates(self) -> List[str]:
        """获取镜像候选列表（优先级顺序）"""
        candidates = []

        # 1. 优先使用 SANDBOX_RUNNER_IMAGE（如果配置了）
        if hasattr(settings, 'SANDBOX_RUNNER_IMAGE') and settings.SANDBOX_RUNNER_IMAGE:
            candidates.append(settings.SANDBOX_RUNNER_IMAGE)

        # 2. Fallback 到 SANDBOX_IMAGE
        if settings.SANDBOX_IMAGE:
            candidates.append(settings.SANDBOX_IMAGE)

        # 3. 最终 fallback（本地镜像）
        candidates.extend([
            "vulhunter/sandbox:latest",
            "vulhunter/sandbox:dev",
        ])

        # 去重并保持顺序
        seen = set()
        unique_candidates = []
        for img in candidates:
            if img not in seen:
                seen.add(img)
                unique_candidates.append(img)

        return unique_candidates

    def _select_image(self) -> str:
        """选择可用镜像"""
        candidates = self._get_image_candidates()

        # 简化版：直接返回第一个
        # 生产版可以检查镜像是否存在
        if candidates:
            return candidates[0]

        raise RuntimeError("No sandbox image configured")

    def _create_workspace(self, run_id: Optional[str] = None) -> Path:
        """创建运行 workspace"""
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
        **kwargs
    ) -> SandboxRunSpec:
        """根据 profile 构建 spec"""

        # 基础配置
        base_spec = {
            "image": self._select_image(),
            "command": command,
            "workspace_dir": str(workspace),
            "timeout_seconds": kwargs.get("timeout", settings.SANDBOX_TIMEOUT),
            "memory_limit": kwargs.get("memory_limit", settings.SANDBOX_MEMORY_LIMIT),
            "cpu_limit": kwargs.get("cpu_limit", settings.SANDBOX_CPU_LIMIT),
            "env": kwargs.get("env", {}),
        }

        # Profile 特定配置
        if profile == "isolated_exec":
            # 完全隔离：无网络、最小权限
            base_spec.update({
                "network_mode": "none",
                "read_only": False,
                "working_dir": "/workspace",
                "volumes": {
                    str(workspace / "input"): {"bind": "/workspace", "mode": "rw"},
                    str(workspace / "output"): {"bind": "/output", "mode": "rw"},
                },
            })

        elif profile == "network_verify":
            # 网络验证：允许网络访问
            base_spec.update({
                "network_mode": "bridge",
                "read_only": False,
                "working_dir": "/workspace",
                "volumes": {
                    str(workspace / "input"): {"bind": "/workspace", "mode": "rw"},
                },
            })

        elif profile == "tool_workdir":
            # 工具工作目录：只读挂载项目目录
            project_dir = kwargs.get("project_dir")
            if not project_dir:
                raise ValueError("tool_workdir profile requires project_dir")

            base_spec.update({
                "network_mode": "none",
                "read_only": True,
                "working_dir": "/workspace",
                "volumes": {
                    str(project_dir): {"bind": "/workspace", "mode": "ro"},
                },
            })

        else:
            raise ValueError(f"Unknown profile: {profile}")

        return SandboxRunSpec(**base_spec)

    def execute(
        self,
        profile: ProfileType,
        command: List[str],
        run_id: Optional[str] = None,
        **kwargs
    ) -> SandboxRunResult:
        """
        执行 sandbox 命令

        Args:
            profile: 执行 profile（isolated_exec, network_verify, tool_workdir）
            command: 要执行的命令
            run_id: 可选的运行 ID
            **kwargs: 额外参数（timeout, env, project_dir 等）

        Returns:
            SandboxRunResult
        """
        # 1. 创建 workspace
        workspace = self._create_workspace(run_id)

        # 2. 构建 spec
        spec = self._build_spec_for_profile(profile, command, workspace, **kwargs)

        # 3. 执行
        result = run_sandbox_container(spec)

        # 4. 补充 image_candidates（保持兼容）
        result.image_candidates = self._get_image_candidates()

        return result

    # 便捷方法
    def execute_isolated(
        self,
        command: List[str],
        **kwargs
    ) -> SandboxRunResult:
        """隔离执行（无网络）"""
        return self.execute("isolated_exec", command, **kwargs)

    def execute_with_network(
        self,
        command: List[str],
        **kwargs
    ) -> SandboxRunResult:
        """网络执行（用于验证）"""
        return self.execute("network_verify", command, **kwargs)

    def execute_in_project(
        self,
        command: List[str],
        project_dir: str,
        **kwargs
    ) -> SandboxRunResult:
        """在项目目录执行（只读挂载）"""
        return self.execute("tool_workdir", command, project_dir=project_dir, **kwargs)
```

---

#### Step 2: 编写测试

**创建测试** (`tests/test_sandbox_runner_client.py`):

```python
import pytest
from pathlib import Path
from app.services.sandbox_runner_client import SandboxRunnerClient

def test_client_initialization():
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


def test_profile_spec_building():
    """测试 profile 到 spec 的映射"""
    client = SandboxRunnerClient()
    workspace = client._create_workspace()

    # isolated_exec profile
    spec1 = client._build_spec_for_profile(
        "isolated_exec",
        ["echo", "test"],
        workspace
    )
    assert spec1.network_mode == "none"
    assert spec1.working_dir == "/workspace"

    # network_verify profile
    spec2 = client._build_spec_for_profile(
        "network_verify",
        ["curl", "example.com"],
        workspace
    )
    assert spec2.network_mode == "bridge"

    # tool_workdir profile
    spec3 = client._build_spec_for_profile(
        "tool_workdir",
        ["ls", "-la"],
        workspace,
        project_dir="/tmp/project"
    )
    assert spec3.read_only is True
    assert "/tmp/project" in str(spec3.volumes)


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker"
)
def test_execute_isolated():
    """测试隔离执行"""
    client = SandboxRunnerClient()
    result = client.execute_isolated(["echo", "hello"])

    assert result.success is True
    assert "hello" in result.stdout


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker"
)
def test_execute_network_isolation():
    """测试网络隔离"""
    client = SandboxRunnerClient()

    # isolated_exec 应该无法访问网络
    result = client.execute_isolated(["ping", "-c", "1", "8.8.8.8"])
    assert result.success is False

    # network_verify 应该可以访问网络
    result_net = client.execute_with_network(["ping", "-c", "1", "8.8.8.8"])
    # 注意：这个可能因环境而异，谨慎断言


def test_result_compatibility():
    """测试结果兼容性（保持与 SandboxManager 输出一致）"""
    client = SandboxRunnerClient()

    # 模拟执行（不实际运行 Docker）
    workspace = client._create_workspace()
    spec = client._build_spec_for_profile("isolated_exec", ["echo", "test"], workspace)

    # 验证 spec 包含必需字段
    assert hasattr(spec, 'image')
    assert hasattr(spec, 'command')
    assert hasattr(spec, 'network_mode')
    assert hasattr(spec, 'security_opt')
    assert hasattr(spec, 'cap_drop')
```

**运行测试**:

```bash
cd backend

# 基础测试（不需要 Docker）
UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest \
  tests/test_sandbox_runner_client.py::test_client_initialization \
  tests/test_sandbox_runner_client.py::test_image_candidates_selection \
  tests/test_sandbox_runner_client.py::test_workspace_creation \
  tests/test_sandbox_runner_client.py::test_profile_spec_building \
  -v

# 完整测试（需要 Docker）
RUN_SANDBOX_TESTS=1 UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest \
  tests/test_sandbox_runner_client.py -v
```

---

#### Step 3: 配置更新

**更新 config.py**:

```python
# 在 Settings 类中添加
class Settings(BaseSettings):
    # ... 现有配置 ...

    # Sandbox Runner 配置（Phase 1）
    SANDBOX_RUNNER_IMAGE: str = "vulhunter/sandbox-runner:latest"
    SANDBOX_RUNNER_ENABLED: bool = True
    SANDBOX_RUNNER_TIMEOUT: int = 60

    # 保持现有配置作为 fallback
    SANDBOX_IMAGE: str = "vulhunter/sandbox:latest"
    SANDBOX_MEMORY_LIMIT: str = "512m"
    SANDBOX_CPU_LIMIT: float = 1.0
    SANDBOX_TIMEOUT: int = 60
    SANDBOX_NETWORK_MODE: str = "none"
```

**更新 .env 文件** (`docker/env/backend/.env`):

```bash
# Sandbox Runner 配置
SANDBOX_RUNNER_IMAGE=vulhunter/sandbox-runner:latest
SANDBOX_RUNNER_ENABLED=true
SANDBOX_RUNNER_TIMEOUT=60

# 现有配置保持不变（作为 fallback）
SANDBOX_IMAGE=vulhunter/sandbox:latest
SANDBOX_MEMORY_LIMIT=512m
SANDBOX_CPU_LIMIT=1.0
```

### Task 3: Rewire `SandboxManager` into a compatibility facade

**⚠️ 关键任务**：这是最复杂的重构，需谨慎处理，避免破坏现有调用者

**Files:**
- Modify: `backend/app/services/agent/tools/sandbox_tool.py` (54KB，需谨慎)
- Update tests in: `backend/tests/test_run_code_tool.py`

---

#### Step 1: 分析现有 SandboxManager

**当前接口** (`sandbox_tool.py`):

```python
class SandboxManager:
    """当前实现直接使用 Docker SDK"""

    def __init__(self):
        self.docker_client = None
        self.is_available = False
        self.diagnosis = ""

    def initialize(self) -> bool:
        """初始化 Docker 客户端"""
        # 当前逻辑...

    def get_diagnosis(self) -> str:
        """获取诊断信息"""
        # 当前逻辑...

    def execute_command(
        self,
        command: List[str],
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
        network_mode: str = "none",
    ) -> Dict[str, Any]:
        """执行命令（返回 dict）"""
        # 当前逻辑：直接使用 docker_client.containers.run(...)

    def execute_tool_command(
        self,
        command: List[str],
        working_dir: str,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """在工作目录执行命令"""
        # 当前逻辑...

    def execute_http_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[str] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """执行 HTTP 请求"""
        # 当前逻辑...

    def verify_vulnerability(
        self,
        url: str,
        method: str = "GET",
        expected_indicators: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """验证漏洞"""
        # 当前逻辑...
```

**现有调用者识别**:

```bash
# 查找所有使用 SandboxManager 的地方
grep -r "SandboxManager" backend/app --include="*.py" | grep -v __pycache__

# 已知调用者：
# 1. external_tools.py - ExecuteToolCommandTool, ExecuteHttpRequestTool
# 2. run_code.py - RunCodeTool（可能）
# 3. sandbox_vuln.py - VulnerabilityVerifyTool
# 4. 其他可能的内部调用
```

---

#### Step 2: 重构策略

**重构方法**：渐进式门面化

1. **保持外部接口不变**：所有公开方法签名不变
2. **内部委托到 Client**：将 Docker 逻辑替换为 `SandboxRunnerClient` 调用
3. **保持返回格式**：确保返回的 dict 格式与旧版本一致
4. **保留初始化语义**：`initialize()` 仍负责验证 Docker 可用性

**重构实现** (`sandbox_tool.py`):

```python
from typing import Dict, List, Optional, Any
from app.services.sandbox_runner_client import SandboxRunnerClient

class SandboxManager:
    """
    Sandbox 管理器 - 兼容门面

    Phase 1: 保持公开接口，内部委托给 SandboxRunnerClient
    """

    def __init__(self):
        # 保留原有字段（向后兼容）
        self.is_available = False
        self.diagnosis = ""

        # 新增：runner client
        self._client: Optional[SandboxRunnerClient] = None

    def initialize(self) -> bool:
        """
        初始化 sandbox 环境

        保持原有语义：验证 Docker 可用性
        """
        try:
            # 尝试初始化 Docker（通过 client）
            import docker
            docker_client = docker.from_env()
            docker_client.ping()

            # 初始化 runner client
            self._client = SandboxRunnerClient()

            self.is_available = True
            self.diagnosis = "Sandbox is available"
            return True

        except docker.errors.DockerException as e:
            self.is_available = False
            self.diagnosis = f"Docker not available: {str(e)}"
            return False

        except Exception as e:
            self.is_available = False
            self.diagnosis = f"Initialization error: {str(e)}"
            return False

    def get_diagnosis(self) -> str:
        """获取诊断信息（保持接口）"""
        return self.diagnosis

    def execute_command(
        self,
        command: List[str],
        timeout: int = 60,
        env: Optional[Dict[str, str]] = None,
        network_mode: str = "none",
    ) -> Dict[str, Any]:
        """
        执行命令（兼容旧接口）

        返回格式：
        {
            "success": bool,
            "exit_code": int,
            "stdout": str,
            "stderr": str,
            "error": Optional[str],
            "image": str,
            "image_candidates": List[str],
        }
        """
        if not self.is_available or self._client is None:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": "Sandbox not initialized",
                "image": "",
                "image_candidates": [],
            }

        try:
            # 选择 profile
            profile = "network_verify" if network_mode == "bridge" else "isolated_exec"

            # 执行
            result = self._client.execute(
                profile=profile,
                command=command,
                timeout=timeout,
                env=env or {},
            )

            # 转换为旧格式
            return {
                "success": result.success,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error": result.error,
                "image": result.image,
                "image_candidates": result.image_candidates,
            }

        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": str(e),
                "image": "",
                "image_candidates": [],
            }

    def execute_tool_command(
        self,
        command: List[str],
        working_dir: str,
        timeout: int = 60,
    ) -> Dict[str, Any]:
        """在工具工作目录执行命令（只读挂载）"""

        if not self.is_available or self._client is None:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": "Sandbox not initialized",
                "image": "",
                "image_candidates": [],
            }

        try:
            result = self._client.execute_in_project(
                command=command,
                project_dir=working_dir,
                timeout=timeout,
            )

            return {
                "success": result.success,
                "exit_code": result.exit_code,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error": result.error,
                "image": result.image,
                "image_candidates": result.image_candidates,
            }

        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "",
                "error": str(e),
                "image": "",
                "image_candidates": [],
            }

    def execute_http_request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[str] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """
        执行 HTTP 请求（网络访问）

        返回格式：
        {
            "success": bool,
            "response_status": int,
            "response_body": str,
            "error": Optional[str],
        }
        """

        if not self.is_available or self._client is None:
            return {
                "success": False,
                "response_status": 0,
                "response_body": "",
                "error": "Sandbox not initialized",
            }

        try:
            # 构建 curl 命令
            curl_cmd = ["curl", "-i", "-s", "-X", method]

            if headers:
                for key, value in headers.items():
                    curl_cmd.extend(["-H", f"{key}: {value}"])

            if data:
                curl_cmd.extend(["-d", data])

            curl_cmd.extend(["--max-time", str(timeout), url])

            # 使用 network_verify profile
            result = self._client.execute_with_network(
                command=curl_cmd,
                timeout=timeout + 5,  # 留出余量
            )

            if not result.success:
                return {
                    "success": False,
                    "response_status": 0,
                    "response_body": "",
                    "error": result.error or "HTTP request failed",
                }

            # 解析 curl 输出
            response_body = result.stdout
            status_code = self._parse_http_status(response_body)

            return {
                "success": True,
                "response_status": status_code,
                "response_body": response_body,
                "error": None,
            }

        except Exception as e:
            return {
                "success": False,
                "response_status": 0,
                "response_body": "",
                "error": str(e),
            }

    def verify_vulnerability(
        self,
        url: str,
        method: str = "GET",
        expected_indicators: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        验证漏洞（复合操作）

        返回格式：
        {
            "is_vulnerable": bool,
            "evidence": str,
            "response_status": int,
            "error": Optional[str],
        }
        """

        # 执行 HTTP 请求
        http_result = self.execute_http_request(
            url=url,
            method=method,
            headers=kwargs.get("headers"),
            data=kwargs.get("data"),
            timeout=kwargs.get("timeout", 30),
        )

        if not http_result["success"]:
            return {
                "is_vulnerable": False,
                "evidence": "",
                "response_status": 0,
                "error": http_result["error"],
            }

        # 检查指标
        response_body = http_result["response_body"]
        is_vulnerable = False
        evidence = ""

        if expected_indicators:
            for indicator in expected_indicators:
                if indicator in response_body:
                    is_vulnerable = True
                    evidence = f"Found indicator: {indicator}"
                    break

        return {
            "is_vulnerable": is_vulnerable,
            "evidence": evidence,
            "response_status": http_result["response_status"],
            "error": None,
        }

    @staticmethod
    def _parse_http_status(curl_output: str) -> int:
        """从 curl -i 输出解析 HTTP 状态码"""
        try:
            # 查找 "HTTP/1.1 200 OK" 等
            import re
            match = re.search(r'HTTP/[\d.]+\s+(\d+)', curl_output)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return 0
```

---

#### Step 3: 编写兼容性测试

**创建测试** (`tests/test_sandbox_manager_facade.py`):

```python
import pytest
from app.services.agent.tools.sandbox_tool import SandboxManager

def test_sandbox_manager_initialization():
    """测试初始化"""
    manager = SandboxManager()

    # 尝试初始化
    success = manager.initialize()

    # 无论成功与否，diagnosis 应该有值
    assert manager.diagnosis != ""
    assert isinstance(manager.is_available, bool)


def test_sandbox_manager_interface_compatibility():
    """测试接口兼容性（方法存在）"""
    manager = SandboxManager()

    # 验证所有公开方法存在
    assert hasattr(manager, 'initialize')
    assert hasattr(manager, 'get_diagnosis')
    assert hasattr(manager, 'execute_command')
    assert hasattr(manager, 'execute_tool_command')
    assert hasattr(manager, 'execute_http_request')
    assert hasattr(manager, 'verify_vulnerability')


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker"
)
def test_execute_command_return_format():
    """测试 execute_command 返回格式（旧接口兼容）"""
    manager = SandboxManager()
    manager.initialize()

    result = manager.execute_command(["echo", "hello"])

    # 验证返回字段
    assert "success" in result
    assert "exit_code" in result
    assert "stdout" in result
    assert "stderr" in result
    assert "error" in result
    assert "image" in result
    assert "image_candidates" in result

    # 验证类型
    assert isinstance(result["success"], bool)
    assert isinstance(result["exit_code"], int)
    assert isinstance(result["stdout"], str)
    assert isinstance(result["image_candidates"], list)


@pytest.mark.skipif(
    not os.environ.get("RUN_SANDBOX_TESTS"),
    reason="需要 RUN_SANDBOX_TESTS=1 和 Docker"
)
def test_execute_tool_command_readonly():
    """测试 execute_tool_command（只读挂载）"""
    manager = SandboxManager()
    manager.initialize()

    # 使用 /tmp 作为测试目录
    result = manager.execute_tool_command(
        command=["ls", "-la"],
        working_dir="/tmp",
    )

    assert "success" in result
    assert "stdout" in result
```

---

#### Step 4: 验证与回归测试

```bash
cd backend

# 1. 运行新的兼容性测试
UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest \
  tests/test_sandbox_manager_facade.py -v

# 2. 运行现有的 run_code_tool 测试（确保不破坏）
UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest \
  tests/test_run_code_tool.py -v

# 3. 运行所有 sandbox 相关测试
RUN_SANDBOX_TESTS=1 UV_CACHE_DIR=/tmp/uv-cache uv run python -m pytest \
  tests/test_sandbox_manager_facade.py \
  tests/test_run_code_tool.py \
  tests/simple_sandbox_test.py \
  -v
```

---

#### Step 5: 验证现有调用者

**检查 external_tools.py**:

```bash
# 确认 ExecuteToolCommandTool 仍正常工作
grep -A 10 "class ExecuteToolCommandTool" backend/app/services/agent/tools/external_tools.py
```

如果使用了 `SandboxManager`，应该自动适配（因为接口保持不变）。

**如有必要，添加集成测试**:

```python
def test_external_tools_integration():
    """测试 external_tools.py 的工具仍正常工作"""
    from app.services.agent.tools.external_tools import ExecuteToolCommandTool

    tool = ExecuteToolCommandTool(project_root="/tmp")
    # 验证工具可以正常初始化
    assert tool.sandbox_manager is not None
```

### Task 4: Migrate core verification tools to the new runner path

**Files:**

- Modify: `backend/app/services/agent/tools/run_code.py`
- Modify: `backend/app/services/agent/tools/sandbox_tool.py`
- Update tests in:
  - `backend/tests/test_run_code_tool.py`
  - `backend/tests/agent/test_tools.py`

- [ ] **Step 1: Add failing tests for profile-specific execution**

Add tests that verify:

- `run_code` uses the isolated execution profile
- `sandbox_exec` uses the isolated execution profile
- `verify_vulnerability` uses the network verification profile
- tool metadata remains unchanged for current frontend / agent consumers

- [ ] **Step 2: Run focused tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  backend/tests/test_run_code_tool.py \
  backend/tests/agent/test_tools.py -q
```

- [ ] **Step 3: Rewire tool construction and execution**

Implementation requirements:

- `RunCodeTool` stops depending on inline Docker orchestration details
- `SandboxTool` and `VulnerabilityVerifyTool` delegate through the new client/facade
- tool names, args schema, prompt contracts, and metadata layout remain unchanged

- [ ] **Step 4: Re-run focused tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  backend/tests/test_run_code_tool.py \
  backend/tests/agent/test_tools.py -q
```

### Task 5: Validate compatibility and public surface stability

**Files:**

- Review / update only as needed:
  - `backend/tests/test_agent_tool_registry.py`
  - `backend/tests/test_agent_prompt_contracts.py`
  - `backend/tests/test_legacy_cleanup.py`
  - `backend/tests/simple_sandbox_test.py`

- [ ] **Step 1: Confirm public tool surface stays stable**

Verify:

- public core tools remain `run_code`, `sandbox_exec`, `verify_vulnerability`
- removed tools stay absent
- prompt contracts still reference the same verification tools

- [ ] **Step 2: Run targeted validation**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  backend/tests/test_agent_tool_registry.py \
  backend/tests/test_agent_prompt_contracts.py \
  backend/tests/test_legacy_cleanup.py -q
```

- [ ] **Step 3: Run opt-in Docker smoke test if environment allows**

Run:

```bash
RUN_SANDBOX_TESTS=1 UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  backend/tests/simple_sandbox_test.py -q
```

Record whether Docker was available and whether the smoke test was skipped.

### Task 6: End-to-end regression pass

- [ ] **Step 1: Run the main impacted suites**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  backend/tests/test_sandbox_runner.py \
  backend/tests/test_sandbox_runner_client.py \
  backend/tests/test_scanner_runner.py \
  backend/tests/test_flow_parser_runner_client.py \
  backend/tests/test_run_code_tool.py \
  backend/tests/agent/test_tools.py \
  backend/tests/test_agent_tool_registry.py \
  backend/tests/test_agent_prompt_contracts.py \
  backend/tests/test_legacy_cleanup.py -q
```

- [ ] **Step 2: Summarize environment assumptions**

Document in the implementation summary:

- whether Docker was available
- whether `UV_CACHE_DIR` had to be overridden
- whether smoke tests were skipped

---

## Phase 2 (Optional, Only After Phase 1 Stabilizes)

下列事项明确延后，不属于本轮默认实施内容：

- 抽离专用 `backend/docker/sandbox-runner.Dockerfile`
- 为 compose 增加 `sandbox-runner` 一次性预热服务
- 为 workflow 增加 sandbox runner 镜像构建和发布
- 从 `docker/sandbox/Dockerfile` 中进一步裁剪运行时能力

只有当满足以下前提时，才进入 Phase 2：

- Phase 1 的 runner 抽象已经稳定
- `SandboxManager` 兼容调用没有新增回归
- 已能明确证明独立镜像能带来可观收益，例如镜像体积、构建时间、职责隔离或安全边界收敛

---

## 实施检查清单

### Phase 1: 底层 Runner（预计 2 天）

- [ ] **创建 sandbox_runner.py**
  - [ ] 定义 `SandboxRunSpec` dataclass
  - [ ] 定义 `SandboxRunResult` dataclass
  - [ ] 实现 `run_sandbox_container()` 函数
  - [ ] 参考 `scanner_runner.py` 的模式

- [ ] **编写基础测试**
  - [ ] 创建 `tests/test_sandbox_runner.py`
  - [ ] 测试 spec/result 数据结构
  - [ ] 测试 workspace 创建（logs/, meta/, input/, output/）
  - [ ] 测试日志和元数据持久化

- [ ] **验证**（需 Docker）
  - [ ] 运行基础容器执行测试
  - [ ] 验证网络隔离（network_mode=none）
  - [ ] 验证安全选项（cap_drop, security_opt）

### Phase 2: Client 层（预计 2 天）

- [ ] **创建 sandbox_runner_client.py**
  - [ ] 实现 `SandboxRunnerClient` 类
  - [ ] 实现 profile 映射（isolated_exec, network_verify, tool_workdir）
  - [ ] 实现镜像选择与 fallback
  - [ ] 实现 workspace 生命周期管理

- [ ] **编写 Client 测试**
  - [ ] 创建 `tests/test_sandbox_runner_client.py`
  - [ ] 测试 workspace 创建路径
  - [ ] 测试 profile 到 spec 的映射
  - [ ] 测试镜像候选列表

- [ ] **配置更新**
  - [ ] 在 `config.py` 添加 `SANDBOX_RUNNER_IMAGE`
  - [ ] 更新 `.env` 模板
  - [ ] 保持 `SANDBOX_IMAGE` 作为 fallback

### Phase 3: SandboxManager 重构（预计 3-4 天）⚠️

- [ ] **分析现有实现**
  - [ ] 识别所有公开方法
  - [ ] 识别所有调用者（external_tools.py 等）
  - [ ] 确定返回格式兼容性要求

- [ ] **重构为门面**
  - [ ] 保持 `initialize()` / `is_available` / `get_diagnosis()`
  - [ ] 重写 `execute_command()` 委托到 client
  - [ ] 重写 `execute_tool_command()` 委托到 client
  - [ ] 重写 `execute_http_request()` 委托到 client
  - [ ] 重写 `verify_vulnerability()` 委托到 client

- [ ] **兼容性测试**
  - [ ] 创建 `tests/test_sandbox_manager_facade.py`
  - [ ] 测试所有公开方法的返回格式
  - [ ] 测试字段完整性（success, exit_code, stdout, stderr, error, image, image_candidates）

### Phase 4: 核心工具迁移（预计 2 天）

- [ ] **run_code.py**
  - [ ] 分析当前 Docker SDK 使用
  - [ ] 改为使用 `SandboxRunnerClient` 或 `SandboxManager` 门面
  - [ ] 保持工具输出格式不变
  - [ ] 更新 `tests/test_run_code_tool.py`

- [ ] **sandbox_vuln.py**
  - [ ] 验证 `VulnerabilityVerifyTool` 仍正常工作
  - [ ] 测试元数据契约

- [ ] **external_tools.py**
  - [ ] 验证 `ExecuteToolCommandTool` 自动适配
  - [ ] 验证 `ExecuteHttpRequestTool` 自动适配

### Phase 5: 集成测试（预计 1-2 天）

- [ ] **端到端测试**
  - [ ] 测试 isolated_exec profile（无网络）
  - [ ] 测试 network_verify profile（有网络）
  - [ ] 测试 tool_workdir profile（只读挂载）

- [ ] **回归测试**
  - [ ] 运行 `simple_sandbox_test.py`
  - [ ] 运行所有 sandbox 相关测试
  - [ ] 验证现有工具不被破坏

- [ ] **性能基准**
  - [ ] 对比重构前后执行时间
  - [ ] 验证 workspace 清理正确

### Phase 6: 文档与清理（预计 1 天）

- [ ] **代码清理**
  - [ ] 移除 `SandboxManager` 中的旧 Docker 逻辑
  - [ ] 添加类型注解和文档字符串
  - [ ] 统一错误处理

- [ ] **文档更新**
  - [ ] 更新架构图
  - [ ] 记录 profile 映射规则
  - [ ] 记录 workspace 结构

### 验收标准

✅ **必须满足**：

1. **底层抽象完整**：
   - [ ] `SandboxRunSpec` 包含所有必需字段
   - [ ] `SandboxRunResult` 保留内存态和文件路径
   - [ ] `run_sandbox_container()` 正确处理超时、错误、日志

2. **Client 功能完整**：
   - [ ] 三种 profile 正确映射
   - [ ] 镜像 fallback 机制工作
   - [ ] Workspace 结构标准化

3. **兼容性保证**：
   - [ ] `SandboxManager` 所有公开方法签名不变
   - [ ] 返回字段与旧版完全一致
   - [ ] 现有调用者（external_tools.py 等）无需修改

4. **测试覆盖**：
   - [ ] 单元测试覆盖所有新组件
   - [ ] 集成测试覆盖三种 profile
   - [ ] 回归测试全部通过

### 关键风险点

⚠️ **必须注意**：

1. **SandboxManager 文件大（54KB）**：
   - 重构需谨慎，建议分步进行
   - 先备份原文件
   - 每次修改后立即测试

2. **未知调用者**：
   - 可能存在未识别的 `SandboxManager` 使用
   - 建议全局搜索确认
   - 保持宽松的兼容策略

3. **Docker 依赖**：
   - 测试需要 Docker 环境
   - CI 环境需配置 Docker
   - 开发者需安装 Docker

4. **网络隔离验证**：
   - `network_mode=none` 可能因环境而异
   - 需在不同环境测试
   - 文档中明确网络策略

### 估算总工时

- **最小实施（Phase 1-3）**：7-8 天
- **包含核心工具迁移（Phase 1-4）**：9-10 天
- **完整实施（含测试和文档）**：11-13 天

**总计**：11-13 工作日

### 测试命令速查

```bash
# 基础测试（无需 Docker）
UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  backend/tests/test_sandbox_runner.py::test_sandbox_run_spec_validation \
  backend/tests/test_sandbox_runner_client.py::test_client_initialization \
  -v

# 完整测试（需要 Docker）
RUN_SANDBOX_TESTS=1 UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  backend/tests/test_sandbox_runner.py \
  backend/tests/test_sandbox_runner_client.py \
  backend/tests/test_sandbox_manager_facade.py \
  backend/tests/test_run_code_tool.py \
  backend/tests/simple_sandbox_test.py \
  -v --tb=short

# 单个功能测试
UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  backend/tests/test_sandbox_runner.py::test_run_sandbox_container_basic \
  -v -s
```

---

## Notes And Constraints

- 使用 `uv run --project backend python -m pytest ...` 作为基准测试命令
- 如默认 `uv` 缓存目录不可写，可显式设置 `UV_CACHE_DIR=/tmp/uv-cache`
- 保持当前语义分离：
  - `run_code` / `sandbox_exec` 默认无网络
  - `verify_vulnerability` 允许网络访问
- 保持验证工具协议稳定，不修改前端和 agent 消费侧的字段约定
- 本轮兼容策略是”核心工具 + 兼容层”，不是”只保三把工具，不管其他调用者”

### 参考文件对照表

| 需实现文件 | 参考文件 | 关键要点 |
|----------|---------|---------|
| `sandbox_runner.py` | `scanner_runner.py` | Spec/Result 模式、日志留存 |
| `sandbox_runner_client.py` | `flow_parser_runner.py` | Client 层抽象、workspace 管理 |
| `test_sandbox_runner.py` | `test_scanner_runner.py` | Runner 契约测试 |
| `test_sandbox_runner_client.py` | `test_flow_parser_runner_client.py` | Client 层测试 |

### 现有代码快速定位

```bash
# 查看 SandboxManager 当前实现
cat backend/app/services/agent/tools/sandbox_tool.py | grep -A 5 “class SandboxManager”

# 查找所有调用者
grep -r “SandboxManager” backend/app --include=”*.py” | grep -v __pycache__ | grep -v “.pyc”

# 查看 scanner runner 参考实现
cat backend/app/services/scanner_runner.py | head -100

# 查看现有 sandbox 配置
grep “SANDBOX” backend/app/core/config.py
```

---

## 最佳实践与实施建议

### 开发流程建议

**1. TDD 方式实施**：
```bash
# 推荐顺序
1. 先写测试（test_sandbox_runner.py）
2. 运行测试，确认失败
3. 实现代码（sandbox_runner.py）
4. 运行测试，确认通过
5. 重构优化
```

**2. 渐进式重构**：
- **不要一次性重写** `sandbox_tool.py`
- 先实现 `SandboxRunnerClient`
- 然后逐个方法重构 `SandboxManager`
- 每重构一个方法，运行一次测试

**3. 备份与回滚**：
```bash
# 重构前备份
cp backend/app/services/agent/tools/sandbox_tool.py \
   backend/app/services/agent/tools/sandbox_tool.py.backup

# 如遇问题，快速回滚
git checkout backend/app/services/agent/tools/sandbox_tool.py
```

### 测试策略

**1. 分层测试**：
```python
# 单元测试（不需要 Docker）
def test_spec_validation():
    spec = SandboxRunSpec(...)
    assert spec.image == "..."

# 集成测试（需要 Docker）
@pytest.mark.skipif(not os.environ.get("RUN_SANDBOX_TESTS"))
def test_container_execution():
    result = run_sandbox_container(spec)
    assert result.success

# 端到端测试
def test_sandbox_manager_full_flow():
    manager = SandboxManager()
    manager.initialize()
    result = manager.execute_command([...])
    assert result["success"]
```

**2. 环境隔离**：
```bash
# CI 环境可能没有 Docker
RUN_SANDBOX_TESTS=1  # 只在有 Docker 的环境启用

# 使用临时目录
pytest --basetemp=/tmp/pytest-sandbox
```

### 常见问题与解决方案

**Q1: Docker 镜像不存在怎么办？**

A: 实现优雅的 fallback 机制：
```python
def _select_image(self) -> str:
    candidates = self._get_image_candidates()

    # 尝试检查镜像是否存在
    for img in candidates:
        try:
            client = docker.from_env()
            client.images.get(img)
            return img
        except docker.errors.ImageNotFound:
            continue

    # 使用第一个候选
    return candidates[0] if candidates else "alpine:latest"
```

**Q2: 容器超时如何处理？**

A: 使用 `timeout_seconds` 参数：
```python
try:
    result = container.wait(timeout=spec.timeout_seconds)
except docker.errors.ContainerError as e:
    # 超时会抛出异常
    return SandboxRunResult(
        success=False,
        error=f"Timeout after {spec.timeout_seconds}s"
    )
```

**Q3: 如何调试容器执行问题？**

A: 保留日志和元数据：
```bash
# 查看 workspace
ls -la /tmp/vulhunter/scans/sandbox-runner/<run_id>/

# 查看日志
cat /tmp/vulhunter/scans/sandbox-runner/<run_id>/logs/stdout.log
cat /tmp/vulhunter/scans/sandbox-runner/<run_id>/logs/stderr.log

# 查看元数据
cat /tmp/vulhunter/scans/sandbox-runner/<run_id>/meta/runner.json
```

**Q4: `SandboxManager` 重构后旧代码不工作？**

A: 检查返回格式：
```python
# 旧代码期望的格式
{
    "success": bool,
    "exit_code": int,
    "stdout": str,
    "stderr": str,
    "error": Optional[str],
    "image": str,
    "image_candidates": List[str],
}

# 确保新实现返回相同格式
def execute_command(...) -> Dict[str, Any]:
    result = self._client.execute(...)
    return {
        "success": result.success,  # 字段名必须一致
        "exit_code": result.exit_code,
        # ...
    }
```

### 性能优化建议

**1. Workspace 清理策略**：
```python
# 定期清理旧 workspace
import shutil
from datetime import datetime, timedelta

def cleanup_old_workspaces(max_age_hours=24):
    workspace_root = Path(settings.SCAN_WORKSPACE_ROOT) / "sandbox-runner"

    for run_dir in workspace_root.iterdir():
        if not run_dir.is_dir():
            continue

        # 检查创建时间
        created_at = datetime.fromtimestamp(run_dir.stat().st_mtime)
        if datetime.now() - created_at > timedelta(hours=max_age_hours):
            shutil.rmtree(run_dir)
```

**2. 镜像预热**：
```bash
# 在部署时预先拉取镜像
docker pull vulhunter/sandbox:latest

# 或在 docker-compose.yml 中配置
services:
  backend:
    depends_on:
      - sandbox-warmup
  
  sandbox-warmup:
    image: vulhunter/sandbox:latest
    command: ["echo", "prewarmed"]
```

**3. 复用 Docker Client**：
```python
# 避免每次执行都创建新 client
class SandboxRunnerClient:
    def __init__(self):
        self._docker_client = None

    def _get_docker_client(self):
        if self._docker_client is None:
            self._docker_client = docker.from_env()
        return self._docker_client
```

### 安全注意事项

**1. 最小权限原则**：
```python
# 始终使用严格的安全选项
SandboxRunSpec(
    cap_drop=["ALL"],  # 禁用所有 capabilities
    security_opt=["no-new-privileges:true"],  # 禁止提权
    read_only=True,  # 只读文件系统（如适用）
    user="sandbox",  # 非 root 用户
)
```

**2. 网络隔离**：
```python
# 默认无网络
network_mode="none"

# 只在必要时开启（如 verify_vulnerability）
network_mode="bridge"
```

**3. 资源限制**：
```python
# 防止资源耗尽
memory_limit="512m",
cpu_limit=1.0,
timeout_seconds=60,
```

### 验收清单

在提交 PR 前，确保：

- [ ] 所有单元测试通过（不需要 Docker）
- [ ] 所有集成测试通过（需要 `RUN_SANDBOX_TESTS=1`）
- [ ] `SandboxManager` 的所有公开方法保持兼容
- [ ] `external_tools.py` 中的工具仍正常工作
- [ ] `run_code` 工具输出格式不变
- [ ] 文档更新（如有 API 变更）
- [ ] 配置文件示例更新（`env.example`）
- [ ] Workspace 目录结构符合规范
- [ ] 错误处理完整（镜像不存在、超时、权限等）
- [ ] 日志和元数据正确写入
- [ ] 安全选项正确应用

### 参考资料

- [Docker SDK for Python](https://docker-py.readthedocs.io/)
- [Scanner Runner 实现](../backend/app/services/scanner_runner.py)
- [Flow Parser Runner 实现](../backend/app/services/flow_parser_runner.py)
- [Sandbox Dockerfile](../docker/sandbox/Dockerfile)
- [项目 CLAUDE.md](../CLAUDE.md)

---

## 附录：快速参考命令

### 开发命令

```bash
# 创建新文件
touch backend/app/services/sandbox_runner.py
touch backend/app/services/sandbox_runner_client.py
touch backend/tests/test_sandbox_runner.py
touch backend/tests/test_sandbox_runner_client.py

# 运行测试（无 Docker）
UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  tests/test_sandbox_runner.py::test_sandbox_run_spec_validation \
  tests/test_sandbox_runner_client.py::test_client_initialization \
  -v

# 运行测试（需 Docker）
RUN_SANDBOX_TESTS=1 UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  tests/test_sandbox_runner.py \
  tests/test_sandbox_runner_client.py \
  -v

# 运行兼容性测试
RUN_SANDBOX_TESTS=1 UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  tests/test_sandbox_manager_facade.py \
  tests/test_run_code_tool.py \
  -v

# 运行所有 sandbox 相关测试
RUN_SANDBOX_TESTS=1 UV_CACHE_DIR=/tmp/uv-cache uv run --project backend python -m pytest \
  tests/test_sandbox* \
  tests/test_run_code_tool.py \
  tests/simple_sandbox_test.py \
  -v
```

### 调试命令

```bash
# 查看 Docker 镜像
docker images | grep sandbox

# 查看运行中的容器
docker ps -a | grep sandbox

# 查看 workspace
ls -la /tmp/vulhunter/scans/sandbox-runner/

# 清理 workspace
rm -rf /tmp/vulhunter/scans/sandbox-runner/*

# 查看最近的执行日志
find /tmp/vulhunter/scans/sandbox-runner -name "*.log" -mtime -1
```

### 代码检查

```bash
# 类型检查
cd backend
mypy app/services/sandbox_runner.py
mypy app/services/sandbox_runner_client.py

# 代码格式
black app/services/sandbox_runner*.py
ruff check app/services/sandbox_runner*.py

# 查找调用者
grep -r "SandboxManager" backend/app --include="*.py" | grep -v __pycache__
grep -r "from.*sandbox_tool import" backend/app --include="*.py"
```
