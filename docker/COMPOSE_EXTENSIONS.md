# Docker Compose 扩展配置说明

## 文件结构

```
项目根目录/
├── docker-compose.yml            # 主配置 (日常开发)
├── docker-compose.full.yml       # 完整构建 (本地构建所有镜像)
└── docker/
    ├── docker-compose.yasa-host.yml        # YASA 主机模式配置
    └── docker-compose.sandbox-runner.yml   # Sandbox Runner 配置
```

## 主配置文件

### `docker-compose.yml` (根目录)

**用途**: 日常开发默认配置

**特点**:
- 使用预构建的 scanner runner 镜像
- Backend 启动时执行 runner preflight 验证
- 最快的启动速度

**使用**:
```bash
# 标准启动 (推荐)
docker compose up --build

# 后台运行
docker compose up -d
```

### `docker-compose.full.yml` (根目录)

**用途**: 完整本地构建所有镜像

**特点**:
- 本地构建所有 scanner runner 镜像
- 适合开发和测试 scanner 镜像
- 构建时间较长,但可控性更强

**使用**:
```bash
# 完整构建
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build

# 只构建特定服务
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  build opengrep-runner
```

## 扩展配置 (docker/ 目录)

### `docker-compose.yasa-host.yml`

**用途**: YASA 主机模式配置

**特点**:
- 使用主机上的 YASA 而不是容器中的
- 适合 YASA 开发和调试
- 需要主机已安装 YASA

**使用**:
```bash
docker compose -f docker-compose.yml \
  -f docker/docker-compose.yasa-host.yml \
  up --build
```

**要求**:
- 主机上安装了 YASA
- 设置环境变量: `YASA_HOST_PATH=/path/to/yasa`

### `docker-compose.sandbox-runner.yml`

**用途**: Sandbox Runner 按需加载镜像构建 (可选,推荐使用 preflight 自动构建)

**特点**:
- 构建轻量级 sandbox runner 镜像
- 支持 build 和 warmup profiles
- 独立于主 compose 文件
- ⚠️ **注意**: 使用 `docker-compose.full.yml` 时会通过 **preflight 自动构建**,无需手动构建

**使用**:
```bash
# 方式 1: 推荐 - 使用 preflight 自动构建
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build
# → Backend 启动时会自动检查并构建 sandbox-runner

# 方式 2: 手动构建 (可选)
docker compose -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  build sandbox-runner

# 方式 3: 预热镜像 (可选)
docker compose -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  --profile warmup \
  up sandbox-runner-warmup
```

## 组合使用示例

### 场景 1: 日常开发 (默认)

```bash
# 最简单,使用预构建镜像
docker compose up --build
```

### 场景 2: 完整本地构建

```bash
# 本地构建所有 scanner runners
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build
```

### 场景 3: YASA 开发

```bash
# 使用主机 YASA + 本地构建其他 runners
YASA_HOST_PATH=/path/to/yasa \
docker compose -f docker-compose.yml \
  -f docker/docker-compose.yasa-host.yml \
  up --build
```

### 场景 4: Sandbox Runner 开发

```bash
# 构建 sandbox runner + 启动主服务
docker compose -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  build sandbox-runner

docker compose up --build
```

### 场景 5: 组合多个扩展

```bash
# 完整构建 + YASA 主机模式 + Sandbox Runner
docker compose \
  -f docker-compose.yml \
  -f docker-compose.full.yml \
  -f docker/docker-compose.yasa-host.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  up --build
```

## Profiles 说明

### 默认 profiles

- **无 profile**: 启动核心服务 (db, redis, backend, frontend)
- **build**: 构建镜像但不启动服务

### 扩展 profiles

- **sandbox-runner**: Sandbox Runner 相关服务
- **warmup**: 镜像预热服务

**使用示例**:

```bash
# 只构建,不启动
docker compose --profile build up

# 启动 + 预热 sandbox-runner
docker compose \
  -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  --profile warmup \
  up
```

## 环境变量

### 主配置

```bash
# .env 或 docker/env/backend/.env

# 镜像源
DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library

# Sandbox 配置
SANDBOX_IMAGE=vulhunter/sandbox:latest
SANDBOX_RUNNER_ENABLED=true
SANDBOX_RUNNER_IMAGE=vulhunter/sandbox-runner:latest

# Scanner Runners
SCANNER_YASA_IMAGE=vulhunter/yasa-runner-local:latest
SCANNER_OPENGREP_IMAGE=vulhunter/opengrep-runner-local:latest
SCANNER_BANDIT_IMAGE=vulhunter/bandit-runner-local:latest
# ...
```

### YASA 主机模式

```bash
# 启用主机 YASA
YASA_HOST_PATH=/path/to/yasa/binary
```

### Sandbox Runner

```bash
# Sandbox Runner 配置
SANDBOX_RUNNER_APT_MIRROR_PRIMARY=mirrors.aliyun.com
SANDBOX_RUNNER_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
SANDBOX_RUNNER_NPM_REGISTRY=https://registry.npmmirror.com
```

## 故障排查

### 文件找不到

```bash
# 错误: docker-compose.yasa-host.yml not found
# 解决: 使用正确的路径
docker compose -f docker-compose.yml \
  -f docker/docker-compose.yasa-host.yml \
  up
```

### 服务冲突

```bash
# 错误: service name conflicts
# 解决: 检查是否多次引用同一个配置文件
docker compose -f docker-compose.yml up  # ✅ 正确
docker compose -f docker-compose.yml -f docker-compose.yml up  # ❌ 错误
```

### 镜像版本不匹配

```bash
# 清理旧镜像
docker compose down --rmi local

# 重新构建
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  build --no-cache
```

## 最佳实践

### 1. 日常开发

```bash
# 使用默认配置,快速启动
docker compose up --build
```

### 2. 测试新功能

```bash
# 组合使用扩展配置
docker compose \
  -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  up --build
```

### 3. CI/CD

```bash
# 完整构建,确保所有镜像可构建
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  build
```

### 4. 生产部署

参考 `deploy/compose/` 中的生产配置:
- `docker-compose.prod.yml` - 国际生产环境
- `docker-compose.prod.cn.yml` - 中国生产环境

## 参考

- [Sandbox Runner 文档](SANDBOX_RUNNER.md)
- [构建指南](BUILD_SANDBOX_RUNNER.md)
- [主 README](../README.md)
