# Docker Compose 本地启动指南

本项目默认推荐直接使用 Docker Compose，而不是包装脚本。
默认启动只拉起常驻 compose 服务。
runner preflight 改由 backend 启动时托管执行 runner preflight，统一校验 `SCANNER_*_IMAGE` / `FLOW_PARSER_RUNNER_IMAGE` 指向的镜像和命令；真正执行扫描时仍由 backend 按镜像名动态拉起临时 runner 容器。

## 默认启动方式

### 日常本地开发默认入口

```bash
docker compose up --build
```

该默认链路会把 `backend` / `frontend` 切到源码挂载 + 热重载，并默认关闭 `MCP_REQUIRE_ALL_READY_ON_STARTUP`、`SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP` 等重型启动项。

### 全量本地构建入口

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

该覆盖层会把 `backend` / `frontend` 切回完整本地镜像构建，并恢复更严格的启动期 ready 门禁，适合需要验证全量本地镜像构建的场景。

## 平台支持

### Linux / macOS / WSL

默认直接使用上面的 `docker compose` 命令即可。

### Windows

仅支持 Docker Desktop + Linux containers 场景，默认同样直接使用上面的 `docker compose` 命令即可。

## 可选 legacy 包装脚本

以下脚本不再是默认或必需启动方式，只是保留给需要镜像源探测、故障转移、统一 ready 提示等能力的用户使用。

### Bash helper（Linux / macOS / WSL）

```bash
./scripts/compose-up-with-fallback.sh
```

### PowerShell helper（Windows）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1
```

### Batch helper（Windows）

```cmd
scripts\compose-up-with-fallback.bat
```

## 功能对比

| 项目 | 直接 `docker compose` | Legacy Bash | Legacy PowerShell | Legacy Batch |
|------|---------------------|-------------|-------------------|--------------|
| 默认定位 | 默认推荐 | 可选 legacy helper | 可选 legacy helper | 可选 legacy helper |
| 适用平台 | Linux / macOS / WSL / Windows（Docker Desktop + Linux containers） | Linux / macOS / WSL | Windows | Windows |
| 镜像源探测与排序 | 否 | 是 | 是 | 否 |
| 多阶段故障转移 | 否 | 是 | 简化版 | 否 |
| 并行探测 | 否 | 是 | 否 | 否 |
| 自定义重试次数 | 否 | 是 | 否 | 否 |
| 统一 `services ready` 提示 | 否 | 是 | 否 | 否 |
| 可选自动打开浏览器 | 否 | 是 | 否 | 否 |

## 环境变量配置

直接 `docker compose` 与可选 legacy 包装脚本都可以配合以下环境变量使用：

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

### 前端 / Sandbox NPM 镜像源
```bash
# Linux/Mac/WSL
export FRONTEND_NPM_REGISTRY=https://registry.npmmirror.com

# Windows PowerShell
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

### 直接传递 compose 参数

直接使用 `docker compose` 时，按 Compose 原生方式传参：

```bash
docker compose up --build
docker compose down
docker compose logs -f backend
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

### 通过 legacy 包装脚本传递 compose 参数

legacy 包装脚本会把自定义参数透传给 `docker compose`：

```bash
# Linux/Mac/WSL
./scripts/compose-up-with-fallback.sh up
./scripts/compose-up-with-fallback.sh down
./scripts/compose-up-with-fallback.sh logs -f backend

# Windows PowerShell
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1 up
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1 down

# Windows Batch
scripts\compose-up-with-fallback.bat up
scripts\compose-up-with-fallback.bat down
```

### Legacy Bash helper 高级配置

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

如果使用可选 legacy PowerShell helper 时遇到 "无法加载文件，因为在此系统上禁止运行脚本" 错误：

```powershell
# 临时允许执行（推荐）
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1

# 或永久修改策略（需要管理员权限）
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Docker 连接失败

确保 Docker Desktop 正在运行：
- Windows（Docker Desktop + Linux containers）: 检查系统托盘中的 Docker 图标，并确认已切换到 Linux containers
- Linux/Mac: 运行 `docker ps` 验证

### 镜像拉取失败

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
export BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/

# Windows PowerShell
$env:DOCKERHUB_LIBRARY_MIRROR="docker.m.daocloud.io/library"
$env:GHCR_REGISTRY="ghcr.nju.edu.cn"
$env:BACKEND_PYPI_INDEX_PRIMARY="https://mirrors.aliyun.com/pypi/simple/"
```

### 国际用户
```bash
# Linux/Mac/WSL
export DOCKERHUB_LIBRARY_MIRROR=docker.io/library
export GHCR_REGISTRY=ghcr.io
export BACKEND_PYPI_INDEX_PRIMARY=https://pypi.org/simple

# Windows PowerShell
$env:DOCKERHUB_LIBRARY_MIRROR="docker.io/library"
$env:GHCR_REGISTRY="ghcr.io"
$env:BACKEND_PYPI_INDEX_PRIMARY="https://pypi.org/simple"
```

## 快速开始

### Linux / macOS / WSL
```bash
# 默认日常增量开发链路（前后端容器内热重载）
docker compose up --build

# 显式执行全量本地构建
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build

# 可选：使用 legacy Bash helper
./scripts/compose-up-with-fallback.sh

# 可选：服务 ready 后自动打开浏览器（仅 legacy Bash helper）
VULHUNTER_OPEN_BROWSER=1 ./scripts/compose-up-with-fallback.sh
```

### Windows
```powershell
# Docker Desktop + Linux containers 默认入口
docker compose up --build

# 显式执行全量本地构建
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build

# 可选：legacy PowerShell helper
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1

# 可选：legacy Batch helper
scripts\compose-up-with-fallback.bat
```

## 当前构建边界

- 默认 `docker compose up --build` 已切到日常增量开发链路。
- 该默认链路会把 `backend`/`frontend` 切到源码挂载 + 热重载，并默认关闭 `MCP_REQUIRE_ALL_READY_ON_STARTUP`、`SKILL_REGISTRY_AUTO_SYNC_ON_STARTUP` 等重型启动项。
- 默认 `docker compose up --build` 的 compose 层只拉起常驻服务，backend 启动时托管执行 runner preflight。
- 真正执行扫描时，backend 会通过 Docker SDK 按 `SCANNER_*_IMAGE` / `FLOW_PARSER_RUNNER_IMAGE` 动态拉起临时 runner 容器，而不是依赖 compose 里的 runner services。
- 可选 legacy Bash helper `./scripts/compose-up-with-fallback.sh` 在 `up` 时会等待前端首页和 backend `/health` 都可访问，再打印统一的 `services ready` 提示。
- `VULHUNTER_OPEN_BROWSER=1` 仅在 legacy Bash helper 中生效；直接使用 `docker compose up --build` 不会自动打开浏览器。
- 显式全量本地构建请叠加 `docker-compose.full.yml`。
- Adminer 已并入 `tools` profile：`docker compose --profile tools up -d adminer`。
- 预构建镜像部署模板已迁移到 `deploy/compose/docker-compose.prod.yml` 与 `deploy/compose/docker-compose.prod.cn.yml`。
