# VulHunter - 面向仓库级代码安全与合规审计的智能分析平台

<p align="center">
  <strong>简体中文</strong> | <a href="README_EN.md">English</a>
</p>

<div align="center">
  <img src="frontend/public/images/logo.png" alt="VulHunter Logo" width="420" />
</div>

<div align="center">

[![Version](https://img.shields.io/badge/version-3.0.4-blue.svg)](CHANGELOG.md)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE)
[![React](https://img.shields.io/badge/React-18-61dafb.svg)](https://reactjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.7-3178c6.svg)](https://www.typescriptlang.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab.svg)](https://www.python.org/)

</div>

VulHunter 是一个面向仓库级项目的智能审计平台，基于 **Multi-Agent（编排/侦察/分析/验证）** 协作架构，结合：

- **LLM（逻辑推理）**：漏洞分析、推理与修复建议
- **RAG（向量索引 / 代码向量化）**：对代码做向量索引化，支撑语义检索与上下文召回

并可在 Docker 沙箱中执行 PoC 验证（可选）。

## 📸 界面预览

<div align="center">

### 🤖 智能审计入口

<img src="frontend/public/images/README-show/Agent审计入口（首页）.png" alt="VulHunter 智能审计入口" width="90%">

*从首页快速进入 Multi-Agent 智能审计*

</div>

<table>
<tr>
<td width="50%" align="center">
<strong>📋 事件日志</strong><br/><br/>
<img src="frontend/public/images/README-show/审计流日志.png" alt="事件日志" width="95%"><br/>
<em>实时查看 Agent 思考与执行过程</em>
</td>
<td width="50%" align="center">
<strong>🎛️ 仪表盘</strong><br/><br/>
<img src="frontend/public/images/README-show/仪表盘.png" alt="仪表盘" width="95%"><br/>
<em>一眼掌握项目安全态势</em>
</td>
</tr>
<tr>
<td width="50%" align="center">
<strong>⚡ 即时分析</strong><br/><br/>
<img src="frontend/public/images/README-show/即时分析.png" alt="即时分析" width="95%"><br/>
<em>粘贴代码 / 上传文件，秒出结果</em>
</td>
<td width="50%" align="center">
<strong>🗂️ 项目管理</strong><br/><br/>
<img src="frontend/public/images/README-show/项目管理.png" alt="项目管理" width="95%"><br/>
<em>导入仓库或上传 ZIP，多项目协同管理</em>
</td>
</tr>
</table>

<div align="center">

### 📊 报告导出

<img src="frontend/public/images/README-show/审计报告示例.png" alt="审计报告" width="90%">

*支持导出 PDF / Markdown / JSON*

</div>

## ✨ 核心能力

- **智能审计（Agent 审计）**：Multi-Agent 协作，自主编排审计策略
- **潜在缺陷**：统一展示缺陷列表，严重度使用中文分级：严重 / 高危 / 中危 / 低危
- **LLM + RAG 分离配置**：LLM 负责逻辑推理，RAG 负责向量索引与语义检索
- **沙箱 PoC 验证（可选）**：在 Docker 隔离环境执行验证脚本（需挂载 Docker socket）
- **静态规则审计**：规则扫描与结果聚合（如 Opengrep、Gitleaks）
- **报告导出**：PDF / Markdown / JSON 一键导出

## 🏗️ 系统架构（简述）

```text
React + TypeScript (frontend)
        |
        |  HTTP / SSE (/api/v1/*)
        v
FastAPI (backend)
        |
        v
PostgreSQL + Redis + Docker Sandbox(optional)
```

更多细节见：`docs/ARCHITECTURE.md`。

## 🚀 快速开始（Docker Compose，推荐）

### 1) 克隆仓库

```bash
git clone https://github.com/unbengable12/AuditTool.git
cd AuditTool
```

### 2) 配置后端环境变量

```bash
cp backend/env.example backend/.env
# 编辑 backend/.env，填入你的 LLM_API_KEY / LLM_PROVIDER / LLM_MODEL 等
```

注意：不要将真实 API Key 提交到仓库。

### 3) 一键启动（后台运行，默认本地源码构建）

```bash
./scripts/compose-up-with-fallback.sh
```

如需使用预构建镜像部署（生产/快速拉起）：

```bash
docker compose -f docker-compose.prod.yml up -d
# 或（国内加速版）
docker compose -f docker-compose.prod.cn.yml up -d
```

### Windows 用户特别说明

Windows 用户可以使用以下方式启动：

#### 方式 1：PowerShell（推荐，支持自动镜像选择）
```powershell
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1
```

#### 方式 2：批处理文件（简单快速）
```cmd
scripts\compose-up-with-fallback.bat
```

#### 方式 3：直接使用 docker compose
```cmd
docker compose up -d --build
```

**注意**：
- 确保 Docker Desktop for Windows 已安装并正在运行
- PowerShell 脚本支持自动镜像源选择和延迟测试
- 批处理文件使用默认镜像源（中国镜像），不进行测速
- 详细说明请参考：`scripts/README-COMPOSE.md`

**环境变量配置示例（PowerShell）**：
```powershell
$env:DOCKERHUB_LIBRARY_MIRROR="docker.m.daocloud.io/library"
$env:GHCR_REGISTRY="ghcr.nju.edu.cn"
powershell -ExecutionPolicy Bypass -File scripts\compose-up-with-fallback.ps1
```


### 4) 访问服务

- 前端：http://localhost:3000
- 后端：http://localhost:8000 （OpenAPI： http://localhost:8000/docs）

### 重要说明

- 后端需要访问 Docker，用于沙箱验证，因此默认会挂载 `/var/run/docker.sock`。生产环境请评估权限边界与隔离策略。
- 默认开发流程使用 `docker-compose.yml` 本地构建业务镜像；`docker-compose.prod.yml` / `docker-compose.prod.cn.yml` 用于预构建镜像部署。
- `docker-compose.prod.yml` 与 `docker-compose.prod.cn.yml` 默认使用南京大学 GHCR 镜像站（`ghcr.nju.edu.cn/lintsinghua/*`）加速拉取。如需生产镜像部署，可替换为你们自己的镜像地址/私有仓库。
- 开发构建链路默认使用 `./scripts/compose-up-with-fallback.sh`：先对候选镜像源测速并按延迟排序，再按排序分阶段重试构建（不再固定“国内→官方”两段式）。
- Docker 镜像拉取（DockerHub/GHCR）测速采用并行探测，失败候选会自动降到排序末位，不阻塞其他可用源。
- DockerHub 默认候选池：`docker.m.daocloud.io/library,docker.1ms.run/library,docker.io/library`；GHCR 默认候选池：`ghcr.nju.edu.cn,ghcr.m.daocloud.io,ghcr.io`。
- DockerHub 官方源测速会使用 `registry-1.docker.io`，避免直接探测 `docker.io` 带来的误差。
- 脚本默认启用 BuildKit（`DOCKER_BUILDKIT=1`、`COMPOSE_DOCKER_CLI_BUILD=1`），可按需覆盖。
- 如需切换为自建代理/其他镜像站，可覆盖环境变量：`DOCKERHUB_LIBRARY_MIRROR`、`SANDBOX_IMAGE`。
- DockerHub/GHCR 候选池优先级：`*_CANDIDATES` > `CN_*` 复数变量（`CN_DOCKERHUB_LIBRARY_MIRRORS` / `CN_GHCR_REGISTRIES`）> 旧单数变量（`CN_DOCKERHUB_LIBRARY_MIRROR` / `CN_GHCR_REGISTRY`）> 内置默认池。
- 可通过 `*_CANDIDATES`（逗号分隔）扩展测速候选源；也可直接显式指定 `*_PRIMARY` / `*_FALLBACK` 跳过对应类别测速。
- 后端 Node/pnpm 构建支持镜像优先+官方回退，可覆盖：`BACKEND_NPM_REGISTRY_PRIMARY`、`BACKEND_NPM_REGISTRY_FALLBACK`、`BACKEND_PNPM_VERSION`。
- 本地 Compose 默认关闭 pnpm optional 依赖安装（`BACKEND_PNPM_INSTALL_OPTIONAL=0`），可显著减少 `node-llama-cpp` 相关下载重试；如需完整 optional 依赖可设为 `1`。
- 本地 Compose 默认跳过 CJK 字体安装（`BACKEND_INSTALL_CJK_FONTS=0`）以加快构建；如需中文字体渲染可设置为 `1`。
- 直接执行 `docker compose up -d --build` 不包含自动切换镜像源逻辑。
- GitHub 源码同步与任务仓库下载/克隆默认走双代理：`https://gh-proxy.org` -> `https://v6.gh-proxy.org`。
- 默认不回源 GitHub（`GIT_MIRROR_FALLBACK_TO_ORIGIN=false`）；仅在排障时建议临时开启回源。
- MCP 源码同步默认采用“首次下载后持久化缓存”策略：`MCP_SOURCE_UPDATE_ON_STARTUP=false`（已有缓存时跳过更新，提升启动稳定性）。
- 如需临时强制刷新 MCP 源码，可设置：`MCP_SOURCE_UPDATE_ON_STARTUP=true`（或 `MCP_SOURCE_FORCE_REFRESH=true`）。

示例：

```bash
DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library \
SANDBOX_IMAGE=ghcr.nju.edu.cn/lintsinghua/vulhunter-sandbox:latest \
./scripts/compose-up-with-fallback.sh
```

自定义 DockerHub/GHCR 国内候选池示例：

```bash
CN_DOCKERHUB_LIBRARY_MIRRORS=docker.m.daocloud.io/library,docker.1ms.run/library \
CN_GHCR_REGISTRIES=ghcr.nju.edu.cn,ghcr.m.daocloud.io \
./scripts/compose-up-with-fallback.sh
```

后端 Node/pnpm 镜像回退示例：

```bash
BACKEND_NPM_REGISTRY_PRIMARY=https://registry.npmmirror.com \
BACKEND_NPM_REGISTRY_FALLBACK=https://registry.npmjs.org \
BACKEND_PNPM_VERSION=9.15.4 \
BACKEND_PNPM_INSTALL_OPTIONAL=0 \
BACKEND_INSTALL_CJK_FONTS=0 \
./scripts/compose-up-with-fallback.sh
```

GitHub 代理链路示例：

```bash
GIT_MIRROR_PREFIXES=https://gh-proxy.org,https://v6.gh-proxy.org \
GIT_MIRROR_FALLBACK_TO_ORIGIN=false \
./scripts/compose-up-with-fallback.sh
```

强制刷新 MCP 源码示例：

```bash
MCP_SOURCE_UPDATE_ON_STARTUP=true \
./scripts/compose-up-with-fallback.sh
```

### 常见启动报错：`Can't locate revision identified by 'xxx'`

这通常是数据库卷里的 Alembic 版本记录与当前后端镜像迁移文件不一致导致的（例如从预构建镜像切换到本地源码构建）。

建议按以下顺序处理：

1. 先确保使用本地源码构建启动：

```bash
./scripts/compose-up-with-fallback.sh
```

2. 若仍报错，且你确认可以丢弃本地测试数据，再执行一次性清理 PostgreSQL 卷后重建：

```bash
docker compose down
docker volume rm audittool_postgres_data
./scripts/compose-up-with-fallback.sh
```

⚠️ 以上会删除本地数据库数据；请先备份重要数据。

## 🧑‍💻 源码开发

### 前端（Vite）

```bash
cd frontend
cp .env.example .env
pnpm install
pnpm dev
```

### 后端（uv + FastAPI）

```bash
cd backend
cp env.example .env
uv sync
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 沙箱（可选）

- 开发模式通常由 `docker compose` 负责构建/使用沙箱镜像，镜像定义见 `docker/sandbox/`。

## 📚 文档索引

- `docs/ARCHITECTURE.md`：架构与关键链路说明
- `docs/CONFIGURATION.md`：配置项与运行时配置
- `docs/DEPLOYMENT.md`：部署建议
- `docs/AGENT_AUDIT.md`：智能审计（Agent 审计）说明

> 说明：`docs/` 内可能仍出现 `AuditTool` / `deepaudit` 等历史命名，它们属于代码层/部署层命名遗留，不代表产品品牌名称。

## 🤝 贡献

- `CONTRIBUTING.md`：贡献指南
- `SECURITY.md`：安全政策与漏洞报告
- Issues：`https://github.com/unbengable12/AuditTool/issues`

## 📄 许可证

本项目采用 [AGPL-3.0 License](LICENSE) 开源。

## ⚠️ 安全与合规提示

- 禁止在未授权目标上进行漏洞测试/渗透测试。
- 详细安全声明与免责声明见：`DISCLAIMER.md`、`SECURITY.md`。

## Known Gaps（已知问题）

- `backend/pyproject.toml` 中 `license = MIT` 与仓库根 `LICENSE (AGPL-3.0)` 当前不一致，后续需要统一口径（本次仅改 README，不改代码与许可证文件）。

## 命名历史

本仓库文档与代码中可能存在历史命名（例如 `deepaudit`），属于演进过程中的遗留。仅用于背景说明，不影响当前 VulHunter 的功能与使用。
