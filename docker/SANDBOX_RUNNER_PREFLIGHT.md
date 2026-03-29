# Sandbox Runner Preflight 集成

## 概述

Sandbox Runner 已集成到 VulHunter 的 Runner Preflight 机制中,在 `docker compose up --build` 时自动构建和自检。

## Preflight 机制

### 工作流程

```
1. docker compose up --build
   ↓
2. Backend 容器启动
   ↓
3. runner_preflight.py 执行
   ↓
4. 检查所有配置的 runner 镜像
   ├─> 镜像存在? → 运行自检
   └─> 镜像不存在? → 自动构建 → 运行自检
   ↓
5. 所有 runners 验证通过
   ↓
6. Backend 完成启动
```

### Preflight 检查项

Backend 启动时会自动检查以下 8 个 runners:

| Runner | 镜像 | 自检命令 |
|--------|------|---------|
| yasa | vulhunter/yasa-runner:latest | `/opt/yasa/bin/yasa --version` |
| opengrep | vulhunter/opengrep-runner:latest | `opengrep --version` |
| bandit | vulhunter/bandit-runner:latest | `bandit --version` |
| gitleaks | vulhunter/gitleaks-runner:latest | `gitleaks version` |
| phpstan | vulhunter/phpstan-runner:latest | `php /opt/phpstan/phpstan --version` |
| pmd | vulhunter/pmd-runner:latest | `pmd --version` |
| flow-parser | vulhunter/flow-parser-runner:latest | `python3 /opt/flow-parser/flow_parser_runner.py --help` |
| **sandbox-runner** | **vulhunter/sandbox-runner:latest** | **`python3 -c "import requests; import httpx; import jwt; print('OK')"`** |

## 配置

### 环境变量

在 `docker/env/backend/.env` 或 `docker-compose.full.yml` 中配置:

```bash
# Sandbox Runner 镜像
SANDBOX_RUNNER_IMAGE=vulhunter/sandbox-runner:latest
SANDBOX_RUNNER_ENABLED=true

# Preflight 控制
RUNNER_PREFLIGHT_ENABLED=true           # 启用 preflight
RUNNER_PREFLIGHT_STRICT=true            # 严格模式 (任一失败则中止)
RUNNER_PREFLIGHT_TIMEOUT_SECONDS=30     # 每个 runner 的超时
RUNNER_PREFLIGHT_MAX_CONCURRENCY=2      # 并发检查数

# 构建参数 (传递给 Dockerfile)
SANDBOX_RUNNER_APT_MIRROR_PRIMARY=mirrors.aliyun.com
SANDBOX_RUNNER_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
SANDBOX_RUNNER_NPM_REGISTRY=https://registry.npmmirror.com
```

### Preflight 模式

#### 宽松模式 (默认)

```bash
RUNNER_PREFLIGHT_STRICT=false
```

- 单个 runner 失败不影响 backend 启动
- 记录警告日志
- 适合开发环境

#### 严格模式

```bash
RUNNER_PREFLIGHT_STRICT=true
```

- 任一 runner 失败则 backend 中止启动
- 确保所有工具可用
- 适合生产环境

## 使用

### 标准流程

```bash
# 1. 使用完整构建配置
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build
```

**发生的事情**:

1. ✅ Backend 镜像构建
2. ✅ Backend 容器启动
3. ✅ Preflight 检查开始
4. 🔍 检查 sandbox-runner 镜像
   - 不存在 → 从 `docker/sandbox-runner.Dockerfile` 自动构建
   - 存在 → 直接运行自检
5. ✅ 运行自检命令: `python3 -c "import requests; ..."`
6. ✅ 自检通过 → Backend 完成启动

### 日志输出

```
🔄 Runner preflight starting...
📦 Checking runner: sandbox-runner
  Image: vulhunter/sandbox-runner:latest
  Dockerfile: docker/sandbox-runner.Dockerfile

🏗️ Building image: vulhunter/sandbox-runner:latest
  (构建输出...)

✅ Runner preflight passed: sandbox-runner
  Exit code: 0
  Output: Sandbox Runner OK

🎉 All runners verified (8/8)
```

### 跳过 Preflight

如果需要跳过 preflight (不推荐):

```bash
RUNNER_PREFLIGHT_ENABLED=false \
docker compose up --build
```

## 自动构建触发

### 何时会自动构建

1. **镜像不存在**:
   ```bash
   # 首次启动或镜像被删除
   docker compose up --build
   # → 自动构建 sandbox-runner
   ```

2. **Dockerfile 更新**:
   ```bash
   # 修改 docker/sandbox-runner.Dockerfile
   # 删除旧镜像
   docker rmi vulhunter/sandbox-runner:latest

   # 重新启动
   docker compose up --build
   # → 重新构建 sandbox-runner
   ```

3. **依赖更新**:
   ```bash
   # 修改 docker/sandbox-runner.requirements.txt
   docker rmi vulhunter/sandbox-runner:latest
   docker compose up --build
   # → 重新构建
   ```

### 手动触发构建

```bash
# 方式 1: 删除镜像后启动
docker rmi vulhunter/sandbox-runner:latest
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build

# 方式 2: 使用构建脚本
cd docker/sandbox
./build-runner.sh

# 方式 3: 使用 docker compose 直接构建
docker compose -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  build sandbox-runner
```

## 构建参数传递

### 从环境变量到 Dockerfile

```
docker-compose.full.yml 环境变量
  ↓
runner_preflight.py (读取环境变量)
  ↓
build_args (传递给 docker build)
  ↓
Dockerfile ARG (接收构建参数)
```

### 示例

**docker-compose.full.yml**:
```yaml
environment:
  SANDBOX_RUNNER_APT_MIRROR_PRIMARY: mirrors.aliyun.com
  SANDBOX_RUNNER_PYPI_INDEX_PRIMARY: https://mirrors.aliyun.com/pypi/simple/
```

**runner_preflight.py**:
```python
build_args={
    "SANDBOX_RUNNER_APT_MIRROR_PRIMARY": os.environ.get("SANDBOX_RUNNER_APT_MIRROR_PRIMARY"),
    "SANDBOX_RUNNER_PYPI_INDEX_PRIMARY": os.environ.get("SANDBOX_RUNNER_PYPI_INDEX_PRIMARY"),
}
```

**Dockerfile**:
```dockerfile
ARG SANDBOX_RUNNER_APT_MIRROR_PRIMARY=mirrors.aliyun.com
ARG SANDBOX_RUNNER_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/

RUN apt-get update ...
```

## 验证

### 检查 Preflight 配置

```python
from app.services.runner_preflight import get_configured_runner_preflight_specs

specs = get_configured_runner_preflight_specs()
sandbox_spec = next(s for s in specs if s.name == "sandbox-runner")

print(f"Image: {sandbox_spec.image}")
print(f"Dockerfile: {sandbox_spec.dockerfile}")
print(f"Build args: {sandbox_spec.build_args}")
```

### 检查启动日志

```bash
# 启动并查看日志
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build 2>&1 | grep -i "sandbox-runner"
```

应该看到:
```
📦 Checking runner: sandbox-runner
✅ Runner preflight passed: sandbox-runner
```

### 验证镜像存在

```bash
# 启动后检查
docker images | grep sandbox-runner

# 应该输出:
# vulhunter/sandbox-runner  latest  abc123  2 minutes ago  580MB
```

## 故障排查

### Preflight 失败

**问题**: Sandbox runner preflight 失败

**解决**:

1. **查看详细日志**:
   ```bash
   docker compose logs backend | grep -A 20 "sandbox-runner"
   ```

2. **手动测试自检命令**:
   ```bash
   docker run --rm vulhunter/sandbox-runner:latest \
     python3 -c "import requests; import httpx; import jwt; print('OK')"
   ```

3. **重新构建镜像**:
   ```bash
   docker rmi vulhunter/sandbox-runner:latest
   cd docker/sandbox && ./build-runner.sh
   ```

### 构建超时

**问题**: Preflight 构建超时 (30s 默认)

**解决**:

```bash
# 增加超时时间
RUNNER_PREFLIGHT_TIMEOUT_SECONDS=120 \
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build
```

### 依赖安装失败

**问题**: Python/npm 包安装失败

**解决**:

1. **检查网络**:
   ```bash
   curl -I https://mirrors.aliyun.com
   ```

2. **使用备用源**:
   ```bash
   SANDBOX_RUNNER_PYPI_INDEX_PRIMARY=https://pypi.org/simple \
   docker compose up --build
   ```

3. **查看构建日志**:
   ```bash
   docker build --no-cache --progress=plain \
     -f docker/sandbox-runner.Dockerfile \
     -t vulhunter/sandbox-runner:latest \
     .
   ```

## 高级配置

### 禁用特定 Runner

```python
# 在 runner_preflight.py 中临时注释
specs = [
    # RunnerPreflightSpec(name="sandbox-runner", ...),  # 禁用
]
```

### 自定义自检命令

编辑 `backend/app/services/runner_preflight.py`:

```python
RunnerPreflightSpec(
    name="sandbox-runner",
    image="vulhunter/sandbox-runner:latest",
    command=["python3", "-c", "你的自定义验证代码"],  # 修改这里
    # ...
)
```

### 添加新的构建参数

1. **在 Dockerfile 中添加 ARG**:
   ```dockerfile
   ARG MY_NEW_ARG=default_value
   ```

2. **在 runner_preflight.py 中传递**:
   ```python
   build_args={
       "MY_NEW_ARG": os.environ.get("MY_NEW_ARG"),
   }
   ```

3. **在 docker-compose.full.yml 中配置**:
   ```yaml
   environment:
     MY_NEW_ARG: ${MY_NEW_ARG:-default}
   ```

## 完整工作流程示例

### 开发环境

```bash
# 1. 首次启动 (自动构建所有 runners)
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build

# 2. 修改 sandbox-runner.Dockerfile
vim docker/sandbox-runner.Dockerfile

# 3. 删除旧镜像
docker rmi vulhunter/sandbox-runner:latest

# 4. 重新启动 (自动重新构建)
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build

# 5. 验证
docker compose logs backend | grep "sandbox-runner"
```

### 生产环境

```bash
# 1. 预先构建所有镜像
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  build

# 2. 推送到镜像仓库
docker tag vulhunter/sandbox-runner:latest \
  myregistry/sandbox-runner:v1.0.0
docker push myregistry/sandbox-runner:v1.0.0

# 3. 部署时使用预构建镜像
SANDBOX_RUNNER_IMAGE=myregistry/sandbox-runner:v1.0.0 \
docker compose up
```

## 性能优化

### 并行构建

Preflight 支持并发检查,加快启动速度:

```bash
# 增加并发数 (默认 2)
RUNNER_PREFLIGHT_MAX_CONCURRENCY=4 \
docker compose up --build
```

### 构建缓存

```bash
# 使用 BuildKit 缓存
export DOCKER_BUILDKIT=1

# 保留中间镜像
docker compose build --no-rm
```

## 监控

### 启动日志

查看 preflight 执行情况:

```bash
docker compose logs backend 2>&1 | grep -i "preflight"
```

### 成功输出

```
🔄 Runner preflight starting...
📦 Checking 8 runners...
✅ sandbox-runner: OK (exit_code=0)
✅ yasa: OK (exit_code=0)
✅ opengrep: OK (exit_code=0)
...
🎉 All runners verified (8/8)
```

### 失败输出

```
❌ sandbox-runner: FAILED (exit_code=1)
   Error: Import error: No module named 'requests'

⚠️ Preflight completed with 1 failure(s)
```

## 总结

✅ **已集成**: Sandbox Runner 已加入 preflight 机制

✅ **自动构建**: `docker compose up --build` 时自动构建

✅ **自动验证**: 启动时自动运行自检命令

✅ **智能 fallback**: 构建失败时自动使用 `vulhunter/sandbox:latest`

✅ **并发检查**: 支持多个 runners 并行验证

这确保了 sandbox-runner 镜像始终可用且功能正常! 🎉

## 参考

- [Runner Preflight 实现](../backend/app/services/runner_preflight.py)
- [Sandbox Runner Dockerfile](sandbox-runner.Dockerfile)
- [Docker Compose Full](../docker-compose.full.yml)
- [使用文档](SANDBOX_RUNNER.md)
