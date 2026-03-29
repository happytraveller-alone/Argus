# Sandbox Runner 镜像说明

## 概述

`vulhunter/sandbox-runner` 是一个轻量级的按需加载代码执行镜像,参考 `flow-parser-runner` 的设计模式,专注于安全隔离的代码执行能力。

## 设计特点

### 1. 多阶段构建

```
Stage 1 (nodebase)  → 提取 Node.js 运行时
Stage 2 (builder)   → 安装 Python 依赖到 venv
Stage 3 (runtime)   → 精简的运行时镜像
```

### 2. 与完整 Sandbox 的区别

| 特性 | sandbox:latest | sandbox-runner:latest |
|------|----------------|----------------------|
| 用途 | 完整沙箱环境 + 扫描工具 | 按需代码执行 |
| 扫描工具 | ✅ Opengrep, Bandit, Gitleaks, PMD 等 | ❌ 不包含 |
| 镜像大小 | ~2GB | ~600MB (预估) |
| 构建工具 | ✅ gcc, cmake, clang | ❌ 运行时不包含 |
| Go/Rust | ✅ 完整工具链 | ❌ 不包含 |
| 运行时语言 | ✅ Python, Node, PHP, Java, Ruby | ✅ 相同 |
| 使用场景 | 常驻容器,综合扫描 | 按需启动,快速执行 |

### 3. 包含的运行时

- **Python 3.11** + venv (隔离依赖)
- **Node.js 22** + npm
- **PHP 8.2** (CLI)
- **Java 21** (JRE,无 JDK)
- **Ruby 3.1**

### 4. Python 库 (最小集)

只包含代码执行常用的库:
- `requests` - HTTP 客户端
- `httpx` - 异步 HTTP 客户端
- `beautifulsoup4` - HTML 解析
- `pycryptodome` - 加密库
- `pyjwt` - JWT 处理

**不包含**: bandit, safety, code2flow 等扫描工具

### 5. 安全特性

- ✅ 非 root 用户 (uid=1000, user=sandbox)
- ✅ 只读基础系统 (通过 Docker run `--read-only`)
- ✅ 网络隔离 (通过 Docker run `--network none`)
- ✅ 资源限制 (通过 Docker run `--memory`, `--cpus`)
- ✅ 最小权限 (无构建工具,无编译器)

## 构建

### 本地构建

```bash
cd docker/sandbox
./build-runner.sh
```

### 自定义构建参数

```bash
IMAGE_NAME=myregistry/sandbox-runner \
IMAGE_TAG=v1.0 \
PLATFORM=linux/amd64 \
./build-runner.sh
```

### Docker Compose 构建

```bash
docker compose -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  build sandbox-runner
```

## 使用

### 1. 直接运行

```bash
# 基础测试
docker run --rm vulhunter/sandbox-runner:latest python3 -c "print('Hello')"

# 网络隔离 + 只读文件系统
docker run --rm \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,exec,size=512m \
  --memory 512m \
  --cpus 1.0 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  vulhunter/sandbox-runner:latest \
  python3 -c "import requests; print('OK')"
```

### 2. 通过 SandboxRunnerClient

```python
from app.services.sandbox_runner_client import SandboxRunnerClient

client = SandboxRunnerClient()

# 执行 Python 代码
result = client.execute_isolated(
    command=["python3", "-c", "print('hello')"],
    timeout=30,
)

print(result.stdout)  # hello
```

### 3. 按需加载模式

参考 `flow_parser_runner.py` 的实现:

```python
# 临时容器,执行后自动清理
with tempfile.TemporaryDirectory() as workspace:
    spec = SandboxRunSpec(
        image="vulhunter/sandbox-runner:latest",
        command=["python3", "-c", "print('test')"],
        workspace_dir=workspace,
        auto_remove=True,  # 自动清理
    )
    result = run_sandbox_container(spec)
```

## 性能优化

### 镜像优化

1. **多阶段构建**: 构建依赖不包含在最终镜像
2. **venv 隔离**: Python 依赖独立,易于更新
3. **层缓存**: 按变化频率组织指令
4. **精简运行时**: 只安装 JRE,不包含 JDK

### 启动优化

1. **预热镜像**:
   ```bash
   docker pull vulhunter/sandbox-runner:latest
   ```

2. **Compose 预启动** (可选):
   ```yaml
   services:
     sandbox-runner-warmup:
       image: vulhunter/sandbox-runner:latest
       command: ["true"]
   ```

## 与后端集成

### 配置 (backend/.env)

```bash
# 启用新 sandbox runner
SANDBOX_RUNNER_ENABLED=true
SANDBOX_RUNNER_IMAGE=vulhunter/sandbox-runner:latest
SANDBOX_RUNNER_TIMEOUT=60

# Fallback 到完整 sandbox (如果 runner 不可用)
SANDBOX_IMAGE=vulhunter/sandbox:latest
```

### 自动 Fallback

如果 `sandbox-runner` 镜像不存在,会自动回退到 `vulhunter/sandbox:latest`:

```python
# SandboxRunnerClient 会自动选择
candidates = [
    "vulhunter/sandbox-runner:latest",  # 优先
    "vulhunter/sandbox:latest",         # Fallback
]
```

## 更新 & 维护

### 更新依赖

编辑 `docker/sandbox-runner.requirements.txt`:

```bash
# 添加新依赖
echo "aiohttp==3.9.0" >> docker/sandbox-runner.requirements.txt

# 重新构建
./build-runner.sh
```

### 版本固定

始终在 `requirements.txt` 中指定版本号,避免不可预测的更新:

```
# ✅ 好
requests==2.31.0

# ❌ 不好
requests
```

## 故障排查

### 镜像拉取失败

```bash
# 检查镜像是否存在
docker images | grep sandbox-runner

# 手动构建
cd docker/sandbox && ./build-runner.sh
```

### 运行时错误

```bash
# 检查日志
docker logs <container_id>

# 交互式调试
docker run -it --rm \
  vulhunter/sandbox-runner:latest \
  /bin/bash
```

### 依赖缺失

```bash
# 验证 Python 依赖
docker run --rm vulhunter/sandbox-runner:latest \
  python3 -c "import requests; import httpx; print('OK')"

# 验证运行时
docker run --rm vulhunter/sandbox-runner:latest \
  sh -c "python3 --version && node --version && php --version"
```

## 安全建议

### 生产环境

1. **使用特定版本标签**:
   ```
   vulhunter/sandbox-runner:v1.2.3  # ✅ 好
   vulhunter/sandbox-runner:latest  # ❌ 避免
   ```

2. **定期扫描漏洞**:
   ```bash
   docker scan vulhunter/sandbox-runner:latest
   ```

3. **最小权限运行**:
   ```bash
   docker run --rm \
     --user 1000:1000 \
     --read-only \
     --cap-drop ALL \
     --security-opt no-new-privileges:true \
     vulhunter/sandbox-runner:latest \
     python3 -c "..."
   ```

## 参考

- 完整 Sandbox: `docker/sandbox/Dockerfile`
- Flow Parser Runner: `docker/flow-parser-runner.Dockerfile`
- Scanner Runner: `backend/app/services/scanner_runner.py`
- Runner Client: `backend/app/services/sandbox_runner_client.py`
