# Docker Compose 构建脚本使用指南

本项目提供了跨平台的 Docker Compose 构建脚本，支持自动镜像源选择和故障转移。

## 平台支持

### Linux / macOS / WSL
使用 Bash 脚本（推荐）：
```bash
./scripts/compose-up-with-fallback.sh
```

### Windows

#### 方式 1：PowerShell（推荐，支持自动镜像选择）
```powershell
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1
```

#### 方式 2：批处理文件（简单快速）
```cmd
scripts\compose-up-with-fallback.bat
```

## 功能对比

| 功能 | Bash (Linux/Mac/WSL) | PowerShell (Windows) | Batch (Windows) |
|------|---------------------|---------------------|-----------------|
| 自动检测 docker compose | ✅ | ✅ | ✅ |
| 镜像源延迟测试 | ✅ | ✅ | ❌ |
| 自动选择最快镜像 | ✅ | ✅ | ❌ |
| 多阶段故障转移 | ✅ | ⚠️ 简化版 | ❌ |
| 并行探测 | ✅ | ❌ | ❌ |
| 自定义重试次数 | ✅ | ❌ | ❌ |
| 启动完成 ready 提示 | ✅ | ❌ | ❌ |
| 可选自动打开浏览器 | ✅ | ❌ | ❌ |

## 环境变量配置

所有脚本都支持通过环境变量自定义镜像源：

### Docker 镜像源
```bash
# Linux/Mac/WSL
export DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
export GHCR_REGISTRY=ghcr.nju.edu.cn

# Windows PowerShell
$env:DOCKERHUB_LIBRARY_MIRROR="docker.m.daocloud.io/library"
$env:GHCR_REGISTRY="ghcr.nju.edu.cn"

# Windows CMD
set DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
set GHCR_REGISTRY=ghcr.nju.edu.cn
```

### NPM 镜像源
```bash
# Linux/Mac/WSL
export BACKEND_NPM_REGISTRY_PRIMARY=https://registry.npmmirror.com
export FRONTEND_NPM_REGISTRY=https://registry.npmmirror.com

# Windows PowerShell
$env:BACKEND_NPM_REGISTRY_PRIMARY="https://registry.npmmirror.com"
$env:FRONTEND_NPM_REGISTRY="https://registry.npmmirror.com"
```

### PyPI 镜像源
```bash
# Linux/Mac/WSL
export BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
export SANDBOX_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/

# Windows PowerShell
$env:BACKEND_PYPI_INDEX_PRIMARY="https://mirrors.aliyun.com/pypi/simple/"
$env:SANDBOX_PYPI_INDEX_PRIMARY="https://mirrors.aliyun.com/pypi/simple/"
```

## 高级用法

### 传递自定义 compose 参数

所有脚本都支持传递自定义参数给 docker compose：

```bash
# Linux/Mac/WSL
./scripts/compose-up-with-fallback.sh up -d
./scripts/compose-up-with-fallback.sh down
./scripts/compose-up-with-fallback.sh logs -f backend

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1 up -d
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1 down

# Windows Batch
scripts\compose-up-with-fallback.bat up -d
scripts\compose-up-with-fallback.bat down
```

### Bash 脚本高级配置

```bash
# 设置重试次数
export PHASE_RETRY_COUNT=5

# 设置探测次数
export PROBE_ATTEMPTS=5

# 设置超时时间（秒）
export PROBE_TIMEOUT_SECONDS=15
export PROBE_CONNECT_TIMEOUT_SECONDS=5

# 设置重试间隔（秒）
export RETRY_INTERVAL_SECONDS=10

# 设置服务 ready 等待上限（秒）
export VULHUNTER_READY_TIMEOUT_SECONDS=900

# 服务 ready 后自动打开默认浏览器（显式开启）
export VULHUNTER_OPEN_BROWSER=1

# 执行
./scripts/compose-up-with-fallback.sh
```

## 故障排查

### Windows PowerShell 执行策略错误

如果遇到 "无法加载文件，因为在此系统上禁止运行脚本" 错误：

```powershell
# 临时允许执行（推荐）
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1

# 或永久修改策略（需要管理员权限）
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Docker 连接失败

确保 Docker Desktop 正在运行：
- Windows: 检查系统托盘中的 Docker 图标
- Linux/Mac: 运行 `docker ps` 验证

### 镜���拉取失败

1. 检查网络连接
2. 尝试手动指定镜像源（见环境变量配置）
3. 如果在中国大陆，使用国内镜像源：
   ```bash
   export DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
   export GHCR_REGISTRY=ghcr.nju.edu.cn
   ```

## 推荐配置

### 中国大陆用户
```bash
# Linux/Mac/WSL
export DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
export GHCR_REGISTRY=ghcr.nju.edu.cn
export BACKEND_NPM_REGISTRY_PRIMARY=https://registry.npmmirror.com
export BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/

# Windows PowerShell
$env:DOCKERHUB_LIBRARY_MIRROR="docker.m.daocloud.io/library"
$env:GHCR_REGISTRY="ghcr.nju.edu.cn"
$env:BACKEND_NPM_REGISTRY_PRIMARY="https://registry.npmmirror.com"
$env:BACKEND_PYPI_INDEX_PRIMARY="https://mirrors.aliyun.com/pypi/simple/"
```

### 国际用户
```bash
# Linux/Mac/WSL
export DOCKERHUB_LIBRARY_MIRROR=docker.io/library
export GHCR_REGISTRY=ghcr.io
export BACKEND_NPM_REGISTRY_PRIMARY=https://registry.npmjs.org
export BACKEND_PYPI_INDEX_PRIMARY=https://pypi.org/simple

# Windows PowerShell
$env:DOCKERHUB_LIBRARY_MIRROR="docker.io/library"
$env:GHCR_REGISTRY="ghcr.io"
$env:BACKEND_NPM_REGISTRY_PRIMARY="https://registry.npmjs.org"
$env:BACKEND_PYPI_INDEX_PRIMARY="https://pypi.org/simple"
```

## 快速开始

### Linux / macOS / WSL
```bash
# 克隆仓库后直接运行
./scripts/compose-up-with-fallback.sh

# 服务 ready 后自动打开浏览器（可选）
VULHUNTER_OPEN_BROWSER=1 ./scripts/compose-up-with-fallback.sh

# 或直接使用默认日常增量开发链路（前后端容器内热重载）
docker compose up -d --build

# 显式执行全量本地构建
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d --build

# 通过脚本执行全量本地构建
./scripts/compose-up-with-fallback.sh -f docker-compose.yml -f docker-compose.full.yml up -d --build
```

### Windows
```powershell
# PowerShell（推荐）
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1

# 或批处理文件
scripts\compose-up-with-fallback.bat

# 或直接使用 docker compose
docker compose up -d --build
```

## 当前构建边界

- 默认 `docker compose up --build` 已切到日常增量开发链路。
- 该默认链路会把 `backend`/`frontend` 切到源码挂载 + 热重载，并默认关闭 `MCP_REQUIRE_ALL_READY_ON_STARTUP`、`SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP` 等重型启动项。
- `./scripts/compose-up-with-fallback.sh` 在 `up` / `up -d` 时会等待前端首页和 backend `/health` 都可访问，再打印统一的 `services ready` 提示。
- `VULHUNTER_OPEN_BROWSER=1` 仅在 Bash/WSL/Linux 包装脚本中生效；裸 `docker compose up --build` 只打印 ready 提示，不会自动打开浏览器。
- 显式全量本地构建请叠加 `docker-compose.full.yml`。
- Adminer 已并入 `tools` profile：`docker compose --profile tools up -d adminer`。
- 预构建镜像部署模板已迁移到 `deploy/compose/docker-compose.prod.yml` 与 `deploy/compose/docker-compose.prod.cn.yml`。
