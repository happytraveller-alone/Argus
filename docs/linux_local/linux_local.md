# Linux 一键部署统一入口计划

## 摘要
为仓库新增一个统一的 Linux 部署入口，支持两种明确模式：

- `docker`：继续走现有 `docker compose` 链路，作为默认全功能部署方式
- `local`：`frontend`、`backend`、`nexus-web` 在宿主机本地运行，`PostgreSQL/Redis` 仍使用本机服务，扫描 runner、flow parser、PoC 沙箱继续依赖本机 Docker daemon

目标是让用户在 Ubuntu/Debian 上下载仓库后，通过一个脚本完成环境准备、模式选择、依赖检查、服务启动、健康检查和停止管理，而不需要自己拼启动命令。

## 关键变更
### 1. 新增统一部署接口
新增根级 Linux 入口脚本，固定对外接口为：

- `./scripts/deploy-linux.sh`
- `./scripts/deploy-linux.sh docker`
- `./scripts/deploy-linux.sh local`
- `./scripts/deploy-linux.sh status`
- `./scripts/deploy-linux.sh stop`

无参数时进入交互式菜单；有参数时走非交互模式。`status` 和 `stop` 同时覆盖 `docker` 与 `local` 两种启动结果。

公开接口新增内容：

- 新的 CLI 子命令接口如上
- 新的本地部署约定目录：`./.deploy/logs`、`./.deploy/pids`、`./.deploy/runtime`
- 新的本地模式环境文件约定：
  - `backend/.env.local`
  - `frontend/.env.local`
  - `nexus-web/.env.local`（仅当上游项目需要）
- 新的 `nexus-web` 外部源码工作目录约定：
  - `./nexus-web/src`

不修改现有后端 HTTP API、前端路由、Docker Compose 接口。

### 2. Docker 模式统一封装
在 `docker` 模式下，脚本只做外层治理，不重写现有 Compose 逻辑：

- 检查并安装 `docker`、`docker compose plugin`
- 检查 `backend/.env` 是否存在，不存在则从 `backend/env.example` 生成
- 预检端口占用，默认使用仓库当前端口约定：
  - frontend `3000`
  - backend `8000`
  - nexus `5174`（若该服务启用）
- 调用现有 `docker compose up --build`
- 启动后输出访问地址和后端 OpenAPI 地址
- `status` 显示 Compose 服务状态
- `stop` 调用 `docker compose down`

### 3. Local 模式宿主机运行链路
`local` 模式只本地化主服务，不试图消灭扫描链路里的 Docker 依赖。

本地模式固定行为：

- 自动安装或检查：
  - `git`
  - `curl`
  - `ca-certificates`
  - `build-essential`
  - `python3`, `python3-venv`, `python3-pip`
  - `uv`
  - `nodejs` `>=20.6`
  - `corepack` / `pnpm`
  - `postgresql`
  - `redis-server`
  - `docker.io` 或等价 Docker Engine
- 启动并检查本机 `postgresql`、`redis`
- 生成 `backend/.env.local`，覆盖以下关键项：
  - `POSTGRES_SERVER=localhost`
  - `REDIS_URL=redis://localhost:6379/0`
  - `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/vulhunter`
  - `ASYNCPG_DSN=postgresql://postgres:postgres@localhost/vulhunter`
  - `RUNNER_PREFLIGHT_BUILD_CONTEXT=<repo>/backend`
  - `XDG_CONFIG_HOME=<repo>/.deploy/runtime/xdg-config`
  - 保留 `SANDBOX_ENABLED=true`
  - 保留 `FLOW_PARSER_RUNNER_ENABLED=true`
  - 保留 `RUNNER_PREFLIGHT_ENABLED=true`
- 初始化数据库：
  - 若 `vulhunter` 数据库不存在则创建
  - 执行 `uv sync`
  - 执行 `alembic upgrade head`
- 启动 backend：
  - 统一使用非热重载服务模式
  - 命令固定为 `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log`
- 启动 frontend：
  - 使用构建后预览模式，而不是 Vite 热更新开发模式
  - 固定流程：`pnpm install --no-frozen-lockfile` -> `pnpm build` -> `pnpm exec vite preview --host 0.0.0.0 --port 3000`
- 启动 `nexus-web`：
  - 不按 submodule 处理，因为当前仓库截至 `2026-03-29` 没有 `.gitmodules`，`git submodule status` 为空
  - 按“脚本托管的外部 checkout”处理，源码拉取到 `nexus-web/src`
  - 拉取逻辑沿用 [`backend/docker/nexus-web.Dockerfile`](/Users/apple/Project/AuditTool/backend/docker/nexus-web.Dockerfile) 中的约定：
    - 默认 repo URL：`https://github.com/happytraveller-alone/nexus-web.git`
    - 默认 mirror 前缀：`https://v6.gh-proxy.org/`
    - 支持可选 Git ref
    - 若上游 `package.json` 缺 `packageManager`，脚本补 `pnpm@10.32.1`
  - 启动流程固定为：安装依赖 -> 构建 -> 本地静态服务监听 `5174`
  - 优先使用上游现成 preview/build 脚本；若上游无 preview 脚本，则使用一个简单本地静态文件服务兜底
- 所有本地进程统一写入：
  - PID：`./.deploy/pids/*.pid`
  - 日志：`./.deploy/logs/*.log`

### 4. 公共脚本结构
建议拆成 4 个脚本，避免一个大 Bash 垃圾堆：

- `scripts/deploy-linux.sh`
  - 参数解析、交互菜单、模式分发
- `scripts/lib/common.sh`
  - 日志、端口检查、命令存在检查、sudo 包装、PID/日志目录、公用健康检查
- `scripts/lib/docker-mode.sh`
  - Docker 安装检测、Compose 启停、Docker 状态输出
- `scripts/lib/local-mode.sh`
  - apt 安装、env 生成、数据库/Redis 初始化、backend/frontend/nexus 拉起与停止

如果实现时需要少量辅助脚本，可以再增加：

- `scripts/lib/nexus.sh`
- `scripts/lib/postgres.sh`

但不引入更多抽象层，不做跨发行版兼容框架。

### 5. 文档与提示
更新 [`README.md`](/Users/apple/Project/AuditTool/README.md) 与 [`README_EN.md`](/Users/apple/Project/AuditTool/README_EN.md)，新增 Linux 一键部署章节，明确写死：

- `docker` 模式和 `local` 模式的区别
- `local` 模式不是“完全无 Docker”
- 在 `local` 模式里，只有主服务本地化；真正执行扫描、flow parser、PoC 仍需 Docker daemon
- `nexus-web` 会在首次本地部署时自动拉取到 `nexus-web/src`

## 实现计划
### 任务 1：确定本地运行命令与环境文件模板
- 检查 frontend 当前可用于“构建后预览”的稳定命令，避免误用 dev 模式
- 确认 backend 在宿主机运行时所需的最小环境覆盖项，尤其是 `DATABASE_URL`、`REDIS_URL`、`RUNNER_PREFLIGHT_BUILD_CONTEXT`
- 确认 `nexus-web` 的本地静态服务命令兜底方案
- 产出 `.env.local` 生成模板和公共端口常量

### 任务 2：实现统一入口与公共库
- 新增 `scripts/deploy-linux.sh`
- 新增 `scripts/lib/common.sh`
- 实现：
  - 参数解析
  - 交互模式选择
  - OS 检测，仅支持 Ubuntu/Debian
  - `sudo` 可用性检查
  - 统一日志函数
  - 端口占用检查
  - PID 文件管理
  - 健康检查与等待逻辑

### 任务 3：实现 Docker 模式包装
- 新增或补充 `scripts/lib/docker-mode.sh`
- 复用现有 Compose，不修改现有 Compose 文件
- 实现：
  - Docker/Compose 安装与检查
  - `.env` 自动准备
  - 启动、状态、停止
  - 启动完成后的 URL 输出

### 任务 4：实现 Local 模式主链路
- 新增或补充 `scripts/lib/local-mode.sh`
- 实现：
  - apt 安装依赖
  - PostgreSQL 初始化与数据库创建
  - Redis 启动检查
  - backend `.env.local` 生成
  - frontend `.env.local` 生成
  - 本地启动 backend/frontend
  - 记录 PID 与日志
  - 端口健康检查

### 任务 5：实现 Nexus 外部拉取与本地启动
- 新增或补充 `scripts/lib/nexus.sh`
- 严格按当前仓库事实实现为“受控外部拉取”，不是 submodule
- 拉取逻辑对齐 `nexus-web` Dockerfile 的 mirror/fallback 行为
- 首次部署拉取到 `nexus-web/src`，后续部署执行 `git fetch` + 目标 ref 校验
- 安装依赖、构建、启动 `5174`
- 若上游缺少 preview/static-serve 命令，使用脚本兜底静态服务，不要求改上游仓库

### 任务 6：实现 `status` / `stop`
- `status`
  - Docker 模式：展示 `docker compose ps`
  - Local 模式：展示 backend/frontend/nexus PID 是否存活、端口是否监听、数据库/Redis 探活结果
- `stop`
  - Docker 模式：`docker compose down`
  - Local 模式：优先按 PID 优雅停止，超时后强杀，并清理 PID 文件

### 任务 7：补测试与文档
- 为 Bash 脚本增加最少可维护测试
- 优先复用仓库已有脚本测试风格，新增以 Python/pytest 驱动的脚本输出契约测试
- README 中新增：
  - 一键部署命令
  - 两种模式说明
  - 本地模式依赖 Docker 的边界说明
  - 常见失败排查

## 测试计划
### 核心脚本测试
- `deploy-linux.sh` 无参数时能进入模式选择
- `deploy-linux.sh docker` 正确分发到 Docker 链路
- `deploy-linux.sh local` 正确分发到 Local 链路
- `deploy-linux.sh status` / `stop` 在无运行实例时返回可读信息，不报错
- 非 Ubuntu/Debian 环境下返回明确错误
- 缺少 `sudo` 或权限不足时返回明确错误

### Local 模式测试
- 缺少 `backend/.env` 时可自动生成 `backend/.env.local`
- Local 模式生成的 env 文件包含正确的 localhost 配置
- Local 模式把 `RUNNER_PREFLIGHT_BUILD_CONTEXT` 指向宿主机 `backend` 绝对路径
- PostgreSQL 数据库不存在时能创建，已存在时不会重复报错
- Redis/PostgreSQL 未启动时脚本能启动或给出明确失败信息
- backend 启动后 `/health` 可达
- frontend 启动后根路径可达
- `nexus-web` 首次缺源码时可拉取，已有源码时可更新
- 本地模式日志和 PID 文件写入到 `./.deploy` 目录

### Docker 模式测试
- Docker 模式不改变现有 Compose 命令接口
- `.env` 缺失时能自动提示或生成
- `status` 能读取 Compose 状态
- `stop` 能正确关闭 Compose 服务

### 回归测试
- 不修改后端 API 路由
- 不修改 frontend 业务页面
- 不修改现有 `docker-compose.yml` 的默认行为
- 不破坏扫描 runner 的 Docker 预检与运行逻辑

## 假设与默认值
- 目标系统只支持 Ubuntu/Debian，首版不做 CentOS/Rocky/Arch 兼容
- `local` 模式面向“本地服务可用”，不是开发热更新模式
- `local` 模式默认端口固定为：
  - frontend `3000`
  - backend `8000`
  - nexus `5174`
- `nexus-web` 当前不是真正 submodule；实现按“脚本托管外部仓库”处理，这是基于 `2026-03-29` 的仓库事实做的默认方案
- 扫描 runner、flow parser、PoC 沙箱继续依赖 Docker daemon，这不是 bug，而是明确保留的边界
- 首版不生成 systemd 服务，不做后台常驻安装器，只做脚本级一键部署与停启管理
- 若 `nexus-web` 上游仓库的构建脚本与当前 Dockerfile 假设不一致，以“脚本检测并降级到静态服务兜底”为默认行为
