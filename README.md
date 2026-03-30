# VulHunter - 面向仓库级代码漏洞挖掘与安全审计的平台

<p align="center">
  <strong>简体中文</strong> | <a href="README_EN.md">English</a>
</p>

VulHunter 聚焦代码仓库级别的安全审计与漏洞挖掘，使用 Multi-Agent 协作、规则扫描、RAG 语义召回和 LLM 推理，把“发现可疑点”到“验证潜在漏洞”的流程串成一条完整链路。

## 使用场景

- 在项目上线、交付或开源发布前，对整个仓库做一次集中安全审计。
- 对存量代码库进行周期性巡检，补齐密钥泄露、依赖风险和高危代码模式排查。
- 对第三方仓库、外包代码或历史遗留项目做快速风险摸底，缩小人工复核范围。
- 作为安全团队或研发团队的辅助平台，用来整理发现、查看证据并导出审计结果。

## 漏洞挖掘方式

VulHunter 默认按“编排 -> 初筛 -> 深挖 -> 验证”的方式工作：

1. **Multi-Agent 编排**：由编排 Agent 拆解任务，协调侦察、分析和验证阶段。
2. **静态扫描初筛**：结合规则扫描、依赖审计和密钥检测，快速定位高风险入口。
3. **RAG 语义召回**：对仓库代码建立向量索引，用语义检索补充上下文和相似模式线索。
4. **LLM 深度分析**：结合代码上下文、数据流线索和安全知识，对可疑点进行进一步推理。
5. **PoC 沙箱验证（可选）**：在 Docker 隔离环境中执行验证脚本，帮助确认漏洞真实性并过滤误报。

这套方式适合仓库级、跨模块、需要同时兼顾“扫描效率”和“分析深度”的代码审计任务。

## 快速部署

### 1. 克隆仓库

```bash
git clone https://github.com/unbengable12/AuditTool.git
cd AuditTool
```

### 2. 配置后端环境变量

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

至少补充你的模型相关配置，例如 `LLM_API_KEY`、`LLM_PROVIDER`、`LLM_MODEL`。不要把真实密钥提交到仓库。

所有 Dockerfile、runner 镜像构建文件和 Docker 用环境文件现在统一放在 `docker/`。

### 3. 启动服务

默认推荐直接使用 Docker Compose：

```bash
docker compose up
```

Windows 请使用 Docker Desktop + Linux containers。

如需显式执行全量本地构建，请叠加 `docker-compose.full.yml`：

```bash
./scripts/compose-up-local-build.sh

# 或保留原始 compose 命令
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

默认 `docker compose up` 为远程镜像模式，只拉起常驻服务；基础 compose 上追加 `--build` 不会把主服务切成本地构建。
如需切到本地构建，请显式叠加 `docker-compose.full.yml`。
默认远程镜像地址可通过 `GHCR_REGISTRY`、`VULHUNTER_IMAGE_NAMESPACE`、`NEXUS_WEB_IMAGE_NAMESPACE`、`VULHUNTER_IMAGE_TAG`、`NEXUS_WEB_IMAGE_TAG` 覆盖。
默认远程模式按匿名可拉取设计；如果你使用自有命名空间，请确保对应 GHCR 包对匿名拉取开放，或直接通过 `*_IMAGE` 环境变量覆盖完整镜像地址。

默认 `docker compose up` 的 compose 层只拉起常驻服务，compose 不再声明一次性 runner 预热 / 自检服务。
backend 启动时会自行执行 runner preflight，校验 `SCANNER_*_IMAGE` / `FLOW_PARSER_RUNNER_IMAGE` 指向的镜像和命令是否可用；真正执行扫描时，backend 仍会通过 Docker SDK 按镜像名动态拉起临时 runner 容器。

如需查看可选的 legacy 包装脚本说明，请参考 [`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md)。

### 4. 访问服务

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`
- OpenAPI：`http://localhost:8000/docs`

相关文档：
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
[`docs/AGENT_AUDIT.md`](docs/AGENT_AUDIT.md) ·
[`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md)

## Linux 一键部署（Ubuntu / Debian）

针对 Ubuntu / Debian 系统，仓库提供统一的 Linux 部署入口脚本 [`scripts/deploy-linux.sh`](scripts/deploy-linux.sh)，支持两种模式：

| 模式 | 说明 |
|------|------|
| **docker** | 全功能默认模式，所有服务均跑在 Docker Compose 容器内（推荐） |
| **local** | 前端、后端、nexus-web 在宿主机本地运行；PostgreSQL/Redis 使用本机服务；扫描 runner、flow parser、PoC 沙箱**仍依赖 Docker daemon** |

> **注意**：`local` 模式并非"完全无 Docker"，扫描相关容器仍需 Docker Engine 在宿主机可用。

### 使用方法

```bash
# 交互式菜单（无参数）
./scripts/deploy-linux.sh

# 直接指定模式
./scripts/deploy-linux.sh docker   # Docker 模式启动
./scripts/deploy-linux.sh local    # Local 模式启动

# 查看运行状态（同时覆盖 docker + local 两种启动结果）
./scripts/deploy-linux.sh status

# 停止所有服务
./scripts/deploy-linux.sh stop
```

### Local 模式说明

- 自动安装：`git`、`curl`、`python3`、`uv`、`nodejs ≥20`、`pnpm`、`postgresql`、`redis-server`、`docker.io`
- 自动生成 `backend/.env.local`，覆盖数据库/Redis 连接为 localhost
- 执行 `alembic upgrade head` 完成数据库迁移
- frontend 使用构建后预览模式（`pnpm build` → `vite preview`），端口 3000
- nexus-web 首次部署自动拉取到 `nexus-web/src`，后续更新执行 `git fetch`
- 进程 PID 写入 `.deploy/pids/`，日志写入 `.deploy/logs/`

### 常见排查

| 问题 | 解决方法 |
|------|---------|
| 端口被占用 | `./scripts/deploy-linux.sh stop` 后重试，或手动释放端口 |
| `docker: permission denied` | 执行 `newgrp docker` 或重新登录，使 docker 组生效 |
| nexus-web 拉取超时 | 设置环境变量 `NEXUS_WEB_GIT_MIRROR_PREFIX=` 为空以直连，或配置代理 |
| backend 迁移失败 | 检查 PostgreSQL 是否运行：`sudo systemctl status postgresql` |
