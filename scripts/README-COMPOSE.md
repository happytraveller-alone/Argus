# Docker Compose 本地启动指南

本项目默认推荐直接使用 Docker Compose，而不是包装脚本。
默认启动只拉起常驻 compose 服务。
本指南聚焦开发 / 联调 compose 链路；生产 release artifact 部署只复用其中的 backend / infra compose，frontend 改为直接消费打包好的静态包。
runner preflight 改由 backend 启动时托管执行 runner preflight，统一校验 `SCANNER_*_IMAGE` / `FLOW_PARSER_RUNNER_IMAGE` 指向的镜像和命令；真正执行扫描时仍由 backend 按镜像名动态拉起临时 runner 容器。

## 默认启动方式

### 日常本地开发默认入口（dev-with-source-mount）

```bash
docker compose up
```

该默认链路是远程镜像模式，只拉起常驻 compose 服务；对基础 compose 追加 `--build` 不会把 `backend` / `frontend` / `nexus-web` 切成本地构建。
如果首次启动时缺少 `docker/env/backend/.env`，backend 会基于 `docker/env/backend/env.example` 自动生成该文件，避免 compose 因缺少 env 文件直接中断。
默认远程镜像按 `GHCR_REGISTRY` + namespace + tag 规则解析，支持以下环境变量：

```bash
GHCR_REGISTRY
VULHUNTER_IMAGE_NAMESPACE
NEXUS_WEB_IMAGE_NAMESPACE
VULHUNTER_IMAGE_TAG
NEXUS_WEB_IMAGE_TAG
```

如果需要完全覆盖单个服务，继续使用 `BACKEND_IMAGE` / `FRONTEND_IMAGE` / `NEXUS_WEB_IMAGE` / `SCANNER_*_IMAGE` / `FLOW_PARSER_RUNNER_IMAGE` / `SANDBOX_IMAGE`。
默认远程模式按匿名可拉取设计；切换 registry host 不能绕过私有包权限。

### 无源码部署入口（self-contained-image）

```bash
docker compose -f docker-compose.yml -f docker-compose.self-contained.yml up -d
```

该覆盖层会移除 backend 对 `./backend` 和仓库根目录 `.` 的源码挂载，运行时仅保留：

- `./docker/env/backend:/docker/env/backend`
- `backend_uploads:/app/uploads`
- `backend_runtime_data:/app/data/runtime`
- `scan_workspace:/tmp/vulhunter/scans`
- `/var/run/docker.sock:/var/run/docker.sock`

同时固定 `RUNNER_PREFLIGHT_BUILD_CONTEXT=/opt/backend-build-context`，确保 runner fallback build 只使用镜像内上下文。

### 全量本地构建入口

```bash
./scripts/compose-up-local-build.sh

# 或保留原始 compose 命令
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

推荐优先使用 `./scripts/compose-up-local-build.sh`。该脚本会按 `backend -> frontend -> nexus-web` 顺序串行构建，再执行 `up -d`，可避开部分 Docker Desktop / Buildx 环境下的并发元数据解析错误。
如果首次拉取源码后只有 `docker/env/backend/env.example`，该脚本会自动生成 `docker/env/backend/.env`，避免本地构建入口因为缺少 backend env 文件而提前失败。
原始 compose 命令仍保留，适合已经确认本机并发构建稳定的场景。

### Release Artifact 生产部署（前端静态包直部署）

```bash
# 打包机
./deploy/package-release-artifacts.sh

# 目标机
./deploy/deploy-release-artifacts.sh \
  --artifacts /path/to/dist/release \
  --target /opt/vulhunter \
  --version 3.0.4
```

该链路会继续使用 `docker-compose.yml + docker-compose.full.yml` 提供 backend / infra 的现有部署行为，但 frontend 不再沿用 `docker-compose.full.yml` 的本地构建 dev server，而是额外叠加 `deploy/compose/docker-compose.release-static-frontend.yml`：

- frontend artifact 内含 `site/` 静态站点和 `nginx/default.conf`
- 目标机解压到 `deploy/runtime/frontend/` 后直接作为 nginx 挂载内容
- 保持同源 `/api` 反向代理，不依赖目标机安装 Node.js / pnpm 等前端构建工具
- 默认开发 compose 入口 `docker compose up`、`docker-compose.full.yml`、`docker-compose.self-contained.yml` 不受影响

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

legacy Bash helper 同样会在缺少 `docker/env/backend/.env` 时，自动从 `docker/env/backend/env.example` 补出默认 backend Docker 环境文件。

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
| 本地构建回退 | 否 | 是 | 否 | 否 |
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
export GHCR_REGISTRY=ghcr.io
export VULHUNTER_IMAGE_NAMESPACE=unbengable12
export NEXUS_WEB_IMAGE_NAMESPACE=unbengable12

# Windows PowerShell
$env:DOCKERHUB_LIBRARY_MIRROR="docker.m.daocloud.io/library"
$env:GHCR_REGISTRY="ghcr.io"
$env:VULHUNTER_IMAGE_NAMESPACE="unbengable12"
$env:NEXUS_WEB_IMAGE_NAMESPACE="unbengable12"

# Windows CMD
set DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
set GHCR_REGISTRY=ghcr.io
set VULHUNTER_IMAGE_NAMESPACE=unbengable12
set NEXUS_WEB_IMAGE_NAMESPACE=unbengable12
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
docker compose up
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

# 禁用远程拉取失败后的自动本地构建回退（默认启用）
export FALLBACK_LOCAL_BUILD=0

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

### 本地构建回退（Legacy Bash helper）

当所有远程镜像拉取阶段全部失败时（例如 GHCR packages 是 private 的），Legacy Bash helper 会自动回退到使用 `docker-compose.full.yml` 进行本地构建。此行为默认启用。

- 仅对 `up` 命令生效（`down`、`logs` 等不触发回退）
- 如果你已经在参数中指定了 `-f docker-compose.full.yml`，回退会被跳过
- 回退会复用探测阶段选出的最佳镜像源
- 自动注入 `--build` 标志

```bash
# 禁用自动本地构建回退
export FALLBACK_LOCAL_BUILD=0

# 启用（默认）
export FALLBACK_LOCAL_BUILD=1
```

### 镜像拉取失败

1. 检查网络连接
2. 检查 `GHCR_REGISTRY`、`VULHUNTER_IMAGE_NAMESPACE`、`NEXUS_WEB_IMAGE_NAMESPACE`、tag 是否指向了实际公开的包
3. 如果你使用 fork 或自有命名空间，显式覆盖 namespace：
   ```bash
   export GHCR_REGISTRY=ghcr.io
   export VULHUNTER_IMAGE_NAMESPACE=your-org
   export NEXUS_WEB_IMAGE_NAMESPACE=your-org
   ```
4. 如果包不是匿名可拉取的，直接通过 `BACKEND_IMAGE` / `FRONTEND_IMAGE` / `NEXUS_WEB_IMAGE` 指向你可访问的完整镜像地址

## 推荐配置

### 中国大陆用户
```bash
# Linux/Mac/WSL
export DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
export GHCR_REGISTRY=ghcr.io
export VULHUNTER_IMAGE_NAMESPACE=unbengable12
export NEXUS_WEB_IMAGE_NAMESPACE=unbengable12
export BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/

# Windows PowerShell
$env:DOCKERHUB_LIBRARY_MIRROR="docker.m.daocloud.io/library"
$env:GHCR_REGISTRY="ghcr.io"
$env:VULHUNTER_IMAGE_NAMESPACE="unbengable12"
$env:NEXUS_WEB_IMAGE_NAMESPACE="unbengable12"
$env:BACKEND_PYPI_INDEX_PRIMARY="https://mirrors.aliyun.com/pypi/simple/"
```

### 国际用户
```bash
# Linux/Mac/WSL
export DOCKERHUB_LIBRARY_MIRROR=docker.io/library
export GHCR_REGISTRY=ghcr.io
export VULHUNTER_IMAGE_NAMESPACE=unbengable12
export NEXUS_WEB_IMAGE_NAMESPACE=unbengable12
export BACKEND_PYPI_INDEX_PRIMARY=https://pypi.org/simple

# Windows PowerShell
$env:DOCKERHUB_LIBRARY_MIRROR="docker.io/library"
$env:GHCR_REGISTRY="ghcr.io"
$env:VULHUNTER_IMAGE_NAMESPACE="unbengable12"
$env:NEXUS_WEB_IMAGE_NAMESPACE="unbengable12"
$env:BACKEND_PYPI_INDEX_PRIMARY="https://pypi.org/simple"
```

## 快速开始

### Linux / macOS / WSL
```bash
# 默认远程镜像链路
docker compose up

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
docker compose up

# 显式执行全量本地构建
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build

# 可选：legacy PowerShell helper
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1

# 可选：legacy Batch helper
scripts\compose-up-with-fallback.bat
```

## 当前构建边界

- 默认 `docker compose up` 是远程镜像链路，基础 compose 上追加 `--build` 不会把主服务切成本地构建。
- 显式本地构建入口是 `docker compose -f docker-compose.yml -f docker-compose.full.yml up --build`。
- 默认 `docker compose up` 的 compose 层只拉起常驻服务，backend 启动时托管执行 runner preflight。
- 真正执行扫描时，backend 会通过 Docker SDK 按 `SCANNER_*_IMAGE` / `FLOW_PARSER_RUNNER_IMAGE` 动态拉起临时 runner 容器，而不是依赖 compose 里的 runner services。
- 可选 legacy Bash helper `./scripts/compose-up-with-fallback.sh` 在 `up` 时会等待前端首页和 backend `/health` 都可访问，再打印统一的 `services ready` 提示。
- `VULHUNTER_OPEN_BROWSER=1` 仅在 legacy Bash helper 中生效；直接使用 `docker compose up` 不会自动打开浏览器。
- 显式全量本地构建请叠加 `docker-compose.full.yml`。
- Adminer 已并入 `tools` profile：`docker compose --profile tools up -d adminer`。
- release artifact 的 frontend 静态包覆盖层位于 `deploy/compose/docker-compose.release-static-frontend.yml`，供 `deploy/deploy-release-artifacts.sh` 使用；默认开发 compose 不会自动叠加它。
