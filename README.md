# Argus Slim Release

<p align="center">
  <strong>简体中文</strong> | <a href="README_EN.md">English</a>
</p>

该发布分支只保留 slim-source 运行所需文件，启动方式：

```bash
docker compose up --build
```

当前 compose 链路已统一为 `Rust backend + TypeScript frontend`，不再包含旧的 Python backend 双后端链路。

## 启动前准备

1. 确保本机已安装 Docker Compose，并且 Docker daemon 可访问。

默认情况下，Compose 会把前端发布到宿主机 `13000` 端口、后端发布到 `18000` 端口，以避免和常见本地开发服务的 `3000` / `8000` 端口冲突。如需恢复旧端口，启动时设置 `Argus_FRONTEND_PORT=3000 Argus_BACKEND_PORT=8000`。

后端会把 `${DOCKER_SOCKET_PATH:-/var/run/docker.sock}` 挂载给扫描 runner。本工作区的本地 `.env` 可将它覆盖为 `/run/docker-local.sock`；其他环境按需设置 `DOCKER_SOCKET_PATH`。

## Repo-local Codex / OMX

- 本仓库的 repo-local Codex 配置位于 `.codex/config.toml`；启动本项目内的 Codex/OMX 会话时，显式设置 `CODEX_HOME=$PWD/.codex`，避免落到全局 `~/.codex`。
- 首次在本仓库使用 Codex 时，先执行一次 bootstrap：`CODEX_HOME=$PWD/.codex codex login`，或在确认风险后手动把 `~/.codex/auth.json` 复制到 `.codex/auth.json`。
- 项目级 agent 指令由 `AGENTS.md` 统一承载；repo-local skills 从 `.codex/skills/` 加载。里程碑收尾可使用 `neat-freak` 同步项目文档与 agent 知识。
- `.gitignore` 会忽略 `.codex/`；如果需要让其他环境复用某个本地 skill，请重新安装该 skill 或显式调整版本控制策略。

## GHCR 镜像命名

- GHCR 镜像地址格式是 `ghcr.io/<GitHub用户或组织>/<image>:<tag>`。
- `audittool` 是仓库名，不是 GHCR owner；默认镜像前缀使用当前仓库 owner `happytraveller-alone`。
- `.github/workflows/docker-publish.yml` 统一处理 backend、frontend、OpenGrep runner、flow/parser runner 和 sandbox runner 容器镜像的构建与发布。
- GitHub Actions 默认会把 GHCR 包设为 public，并验证匿名拉取。
- 人工触发的多镜像发布也统一通过 `.github/workflows/docker-publish.yml` 选择需要构建的镜像。

## 三个受支持的命令

### 1. 默认镜像启动

```bash
docker compose up --build
```

用途：
全量本地构建并启动所有服务。

## 访问地址

- Frontend: `http://localhost:13000`
- Backend: `http://localhost:18000`
- OpenAPI: `http://localhost:18000/docs`
