# Sandbox Runner 构建指南

## 快速开始

### 1. 使用构建脚本 (推荐)

```bash
cd docker/sandbox
./build-runner.sh
```

### 2. 使用 Docker Compose

```bash
# 只构建 sandbox-runner
docker compose -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  build sandbox-runner

# 构建并测试
docker compose -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  up sandbox-runner

# 预热镜像 (可选)
docker compose -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  --profile warmup \
  up sandbox-runner-warmup
```

### 3. 手动构建

```bash
docker build \
  -f docker/sandbox-runner.Dockerfile \
  -t vulhunter/sandbox-runner:latest \
  .
```

## 构建参数

### 镜像源配置

```bash
# 使用自定义镜像仓库
docker build \
  -f docker/sandbox-runner.Dockerfile \
  --build-arg DOCKERHUB_LIBRARY_MIRROR=docker.io/library \
  --build-arg SANDBOX_RUNNER_APT_MIRROR_PRIMARY=deb.debian.org \
  --build-arg SANDBOX_RUNNER_PYPI_INDEX_PRIMARY=https://pypi.org/simple \
  -t vulhunter/sandbox-runner:latest \
  .
```

### 多平台构建

```bash
# 支持 AMD64 和 ARM64
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -f docker/sandbox-runner.Dockerfile \
  -t vulhunter/sandbox-runner:latest \
  --push \
  .
```

## 验证构建

### 基础验证

```bash
# 检查镜像
docker images vulhunter/sandbox-runner

# 检查大小 (应该 < 1GB)
docker images vulhunter/sandbox-runner --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# 运行基础测试
docker run --rm vulhunter/sandbox-runner:latest \
  python3 -c "import requests; import httpx; print('✅ Python OK')"

docker run --rm vulhunter/sandbox-runner:latest \
  node -e "console.log('✅ Node OK')"

docker run --rm vulhunter/sandbox-runner:latest \
  php -r "echo '✅ PHP OK\n';"
```

### 运行时验证

```bash
# 检查所有运行时
docker run --rm vulhunter/sandbox-runner:latest sh -c "
  python3 --version && echo '✅ Python' || echo '❌ Python'
  node --version && echo '✅ Node' || echo '❌ Node'
  npm --version && echo '✅ npm' || echo '❌ npm'
  php --version && echo '✅ PHP' || echo '❌ PHP'
  java --version && echo '✅ Java' || echo '❌ Java'
  ruby --version && echo '✅ Ruby' || echo '❌ Ruby'
"
```

### 安全验证

```bash
# 验证非 root 用户
docker run --rm vulhunter/sandbox-runner:latest id
# 应该输出: uid=1000(sandbox) gid=1000(sandbox)

# 验证网络隔离
docker run --rm --network none vulhunter/sandbox-runner:latest \
  ping -c 1 8.8.8.8 || echo "✅ Network isolation OK"

# 验证只读文件系统
docker run --rm --read-only \
  --tmpfs /tmp:rw,exec,size=512m \
  vulhunter/sandbox-runner:latest \
  python3 -c "import tempfile; tempfile.mktemp()" \
  && echo "✅ Read-only + tmpfs OK"
```

## 集成到后端

### 1. 更新配置

编辑 `docker/env/backend/.env`:

```bash
# 启用 Sandbox Runner
SANDBOX_RUNNER_ENABLED=true
SANDBOX_RUNNER_IMAGE=vulhunter/sandbox-runner:latest
SANDBOX_RUNNER_TIMEOUT=60

# Fallback (如果 runner 不可用)
SANDBOX_IMAGE=vulhunter/sandbox:latest
```

### 2. 重启服务

```bash
docker compose restart backend
```

### 3. 验证集成

检查后端日志:

```bash
docker compose logs backend | grep -i "sandbox"
```

应该看到:
```
✅ SandboxRunnerClient initialized successfully
```

## 持续集成

### GitHub Actions 示例

```yaml
name: Build Sandbox Runner

on:
  push:
    paths:
      - 'docker/sandbox-runner.Dockerfile'
      - 'docker/sandbox-runner.requirements.txt'

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/sandbox-runner.Dockerfile
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            vulhunter/sandbox-runner:latest
            vulhunter/sandbox-runner:${{ github.sha }}
```

## 故障排查

### 构建失败

1. **网络问题**:
   ```bash
   # 检查网络连接
   curl -I https://mirrors.aliyun.com

   # 使用代理
   docker build \
     --build-arg http_proxy=http://proxy:8080 \
     --build-arg https_proxy=http://proxy:8080 \
     -f docker/sandbox-runner.Dockerfile \
     -t vulhunter/sandbox-runner:latest \
     .
   ```

2. **依赖安装失败**:
   ```bash
   # 查看详细日志
   docker build --no-cache --progress=plain \
     -f docker/sandbox-runner.Dockerfile \
     -t vulhunter/sandbox-runner:latest \
     .
   ```

3. **镜像过大**:
   ```bash
   # 分析层大小
   docker history vulhunter/sandbox-runner:latest

   # 使用 dive 工具分析
   docker run --rm -it \
     -v /var/run/docker.sock:/var/run/docker.sock \
     wagoodman/dive:latest vulhunter/sandbox-runner:latest
   ```

### 运行时错误

1. **依赖缺失**:
   ```bash
   # 进入容器调试
   docker run -it --rm vulhunter/sandbox-runner:latest /bin/bash

   # 检查 Python 包
   pip list

   # 测试导入
   python3 -c "import requests; import httpx; import jwt"
   ```

2. **权限问题**:
   ```bash
   # 检查用户
   docker run --rm vulhunter/sandbox-runner:latest whoami

   # 检查目录权限
   docker run --rm vulhunter/sandbox-runner:latest ls -la /workspace
   ```

## 性能优化

### 构建缓存

```bash
# 使用 BuildKit 缓存
export DOCKER_BUILDKIT=1

# 挂载缓存目录
docker build \
  --cache-from vulhunter/sandbox-runner:latest \
  -f docker/sandbox-runner.Dockerfile \
  -t vulhunter/sandbox-runner:latest \
  .
```

### 镜像压缩

```bash
# 使用 docker-slim
docker-slim build --target vulhunter/sandbox-runner:latest \
  --http-probe=false \
  --include-path /opt/sandbox-runner-venv \
  --include-path /usr/local/bin
```

## 版本管理

### 语义化版本

```bash
# 标记版本
docker tag vulhunter/sandbox-runner:latest \
  vulhunter/sandbox-runner:v1.0.0

# 推送多个标签
docker push vulhunter/sandbox-runner:latest
docker push vulhunter/sandbox-runner:v1.0.0
```

### 依赖版本锁定

在 `docker/sandbox-runner.requirements.txt` 中使用精确版本:

```
requests==2.31.0   # ✅ 精确版本
httpx>=0.27.0      # ⚠️ 最低版本
beautifulsoup4     # ❌ 避免未指定版本
```

## 参考

- [Dockerfile](../docker/sandbox-runner.Dockerfile)
- [文档](../docker/SANDBOX_RUNNER.md)
- [构建脚本](build-runner.sh)
- [Compose 配置](../../docker-compose.sandbox-runner.yml)
