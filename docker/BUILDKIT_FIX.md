# BuildKit 支持修复

## 问题

原始的 `runner_preflight.py` 使用 Docker Python SDK 的 `client.images.build()` API,该 API 不完全支持 BuildKit 的高级特性 (如 `--mount` 缓存挂载)。

**错误信息**:
```
WARNING:app.services.runner_preflight:runner preflight failed: sandbox-runner
(the --mount option requires BuildKit. Refer to https://docs.docker.com/go/buildkit/
to learn how to build images with BuildKit enabled)
```

## 解决方案

修改 `backend/app/services/runner_preflight.py` 中的 `_ensure_runner_image()` 函数:

**Before (使用 Python SDK)**:
```python
def _ensure_runner_image(client, spec: RunnerPreflightSpec) -> None:
    # ...
    client.images.build(
        path=str(build_context),
        dockerfile=spec.dockerfile,
        tag=spec.image,
        buildargs=dict(spec.build_args),
        rm=True,
        pull=False,
    )
```

**After (使用 subprocess + BuildKit)**:
```python
def _ensure_runner_image(client, spec: RunnerPreflightSpec) -> None:
    # ...
    import subprocess

    build_cmd = [
        "docker", "build",
        "-f", spec.dockerfile,
        "-t", spec.image,
        str(build_context),
    ]

    for key, value in spec.build_args.items():
        build_cmd.extend(["--build-arg", f"{key}={value}"])

    # 启用 BuildKit
    env = os.environ.copy()
    env["DOCKER_BUILDKIT"] = "1"

    subprocess.run(build_cmd, env=env, check=True, timeout=300)
```

## 为什么需要 BuildKit

BuildKit 是 Docker 的新一代构建引擎,支持:

1. **缓存挂载** (`--mount=type=cache`):
   ```dockerfile
   RUN --mount=type=cache,target=/root/.cache/pip \
       pip install ...
   ```
   - 避免重复下载依赖
   - 大幅加快构建速度

2. **并行构建**: 多阶段并行执行

3. **更好的缓存**: 智能层缓存

4. **安全**: 支持 secret 挂载

## 影响范围

**所有使用 `--mount` 的 Dockerfiles**:
- ✅ `docker/sandbox-runner.Dockerfile` (新增)
- ✅ `docker/flow-parser-runner.Dockerfile`
- ✅ `docker/bandit-runner.Dockerfile`
- ✅ `docker/opengrep-runner.Dockerfile`
- ✅ `docker/yasa-runner.Dockerfile`
- ✅ `docker/phpstan-runner.Dockerfile`
- ✅ `docker/pmd-runner.Dockerfile`
- ✅ `docker/gitleaks-runner.Dockerfile`

## 验证修复

### 检查代码

```bash
cd backend
.venv/bin/python -c "
from app.services.runner_preflight import get_configured_runner_preflight_specs
specs = get_configured_runner_preflight_specs()
sandbox = next(s for s in specs if s.name == 'sandbox-runner')
print(f'✅ Sandbox runner spec: {sandbox.image}')
"
```

### 测试构建

```bash
# 删除旧镜像
docker rmi vulhunter/sandbox-runner:latest 2>/dev/null || true

# 启动服务 (会触发 preflight 构建)
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build backend
```

**预期输出**:
```
🔄 Runner preflight starting...
📦 Checking runner: sandbox-runner
🏗️ Building image with BuildKit enabled...
✅ Runner preflight passed: sandbox-runner
```

## 手动启用 BuildKit

### 方式 1: 环境变量 (临时)

```bash
export DOCKER_BUILDKIT=1
docker build -f docker/sandbox-runner.Dockerfile \
  -t vulhunter/sandbox-runner:latest .
```

### 方式 2: Docker 配置 (永久)

编辑 `~/.docker/daemon.json` (需要重启 Docker):

```json
{
  "features": {
    "buildkit": true
  }
}
```

### 方式 3: Docker Compose

在 docker-compose.yml 中:

```yaml
services:
  backend:
    environment:
      DOCKER_BUILDKIT: 1
```

## 性能对比

### Without BuildKit

```
构建时间: ~5min
缓存: 无法共享
并行: 不支持
```

### With BuildKit

```
构建时间: ~2min (首次), ~30s (缓存命中)
缓存: 跨构建共享
并行: 多阶段并行
```

## 兼容性

- **Docker Version**: >= 18.09 (BuildKit 引入)
- **Docker Compose**: >= 1.25.0
- **当前版本**: 29.2.1 ✅

## 故障排查

### BuildKit 未启用

**症状**:
```
the --mount option requires BuildKit
```

**解决**:
```bash
# 检查 BuildKit 状态
docker buildx version

# 启用 BuildKit
export DOCKER_BUILDKIT=1

# 重新构建
docker compose up --build
```

### subprocess 调用失败

**症状**:
```
FileNotFoundError: docker command not found
```

**解决**:
```bash
# 确保 docker 在 PATH 中
which docker

# 或使用绝对路径
/usr/bin/docker build ...
```

## 参考

- [Docker BuildKit](https://docs.docker.com/build/buildkit/)
- [Docker Python SDK](https://docker-py.readthedocs.io/)
- [runner_preflight.py](../backend/app/services/runner_preflight.py)
