# Argus Slim Release

<p align="center">
  <strong>简体中文</strong> | <a href="README_EN.md">English</a>
</p>

该发布分支只保留 slim-source 运行所需文件。默认/推荐启动方式（rootless Podman，无宿主 Docker socket）：

```bash
./argus-bootstrap.sh --wait-exit -- default
```

当前 compose 链路已统一为 `Rust backend + TypeScript frontend`，不再包含旧的 Python backend 双后端链路。

## 启动前准备

1. 推荐安装 rootless Podman 并启用用户级 Podman socket（`podman info --format '{{.Host.Security.Rootless}}'` 应为 `true`）。Docker Compose 仍可作为本地/dev fallback。
2. 保留根目录 `env.example` 和 `llm.env.example`。首次运行 `./argus-bootstrap.sh` 时，脚本会生成 `.env`（SECRET_KEY/高级覆盖）并复制 `llm.env.example` 为 `.argus-llm.env`，提示你填写 LLM 配置后退出。
3. 填写 `.argus-llm.env` 中的 LLM 配置后，再次运行 `./argus-bootstrap.sh`；也可以先运行 `./scripts/validate-llm-config.sh --env-file ./.argus-llm.env` 确认 LLM 配置无误。普通用户通常只需要改 `.argus-llm.env`，其它配置走默认。

`argus-bootstrap.sh` 会在任何 Docker 清理或启动动作前调用 `scripts/validate-llm-config.sh --env-file ./.argus-llm.env` 校验 LLM 配置。校验失败时脚本会退出并提示重新配置。

> CubeSandbox 路径已于 2026-05-07 归档至 `docs/archive/cubesandbox/`，扫描统一走 a3s sandbox。

默认情况下，Compose 会把前端发布到宿主机 `13000` 端口、后端发布到 `18000` 端口，以避免和常见本地开发服务的 `3000` / `8000` 端口冲突。如需恢复旧端口，启动时设置 `Argus_FRONTEND_PORT=3000 Argus_BACKEND_PORT=8000`。

后端会读取根目录 `.env`。默认推荐部署路径是 rootless Podman：bootstrap 会构建 OpenGrep runner 镜像，挂载用户级 rootless Podman API socket（不是宿主 Docker socket），并把 `OPENGREP_RUNNER_RUNTIME=podman` 注入 backend；runner 执行前会做 rootless proof，任务容器使用 `--network none`、source `ro`、rules `ro`、output `rw`，仍是一任务一容器、结束即删除。该推荐是安全/可靠性取向，不是速度承诺；本机 Docker/Podman benchmark 见 `.omx/research/podman-opengrep-runner-benchmark-20260519.md`。Docker Compose 路径保留为显式本地/dev fallback：`./argus-bootstrap.sh --runtime docker --wait-exit -- default`，继续挂载 `${DOCKER_SOCKET_PATH:-/var/run/docker.sock}` 并固定 `OPENGREP_RUNNER_RUNTIME=docker`。

## Repo-local Codex / OMX

- 本仓库的 repo-local Codex 配置位于 `.codex/config.toml`；启动本项目内的 Codex/OMX 会话时，显式设置 `CODEX_HOME=$PWD/.codex`，避免落到全局 `~/.codex`。
- 首次在本仓库使用 Codex 时，先执行一次 bootstrap：`CODEX_HOME=$PWD/.codex codex login`，或在确认风险后手动把 `~/.codex/auth.json` 复制到 `.codex/auth.json`。
- 项目级 agent 指令由 `AGENTS.md` 统一承载；repo-local skills 从 `.codex/skills/` 加载。里程碑收尾可使用 `neat-freak` 同步项目文档与 agent 知识。
- `.gitignore` 会忽略 `.codex/`；如果需要让其他环境复用某个本地 skill，请重新安装该 skill 或显式调整版本控制策略。

> CubeSandbox 路径已于 2026-05-07 归档至 `docs/archive/cubesandbox/`，扫描统一走 a3s sandbox。

## GHCR 镜像命名

- GHCR 镜像地址格式是 `ghcr.io/<GitHub用户或组织>/<image>:<tag>`。
- `audittool` 是仓库名，不是 GHCR owner；默认镜像前缀使用当前仓库 owner `happytraveller-alone`。
- `.github/workflows/docker-publish.yml` 统一处理 backend、frontend 和 OpenGrep runner 容器镜像的构建与发布；CodeQL 扫描走 a3s sandbox，不发布 CodeQL runner 容器。
- OpenGrep runner 发布时显式使用 OCI image media types；本地 `runner-build` / `rebuild-opengrep-runner-verify.sh` 仍使用 Docker daemon 本地镜像路径验证运行能力。
- GitHub Actions 默认会把 GHCR 包设为 public，并验证匿名拉取。
- 人工触发的多镜像发布也统一通过 `.github/workflows/docker-publish.yml` 选择需要构建的镜像。

## 三个受支持的命令

### 1. 默认/推荐启动（Podman）

```bash
./argus-bootstrap.sh --wait-exit -- default
```

用途：
校验 LLM env、用 rootless Podman 构建并启动服务，默认 Opengrep `dockerfile_container` runner 也走 rootless Podman。

### 2. Docker fallback 启动

```bash
./argus-bootstrap.sh --runtime docker --wait-exit -- default
```

用途：
校验 LLM env、通过 Docker Compose 构建并启动所有服务，等待前后端就绪后退出。该路径是 dev fallback；推荐优先使用 `./argus-bootstrap.sh --runtime podman --wait-exit -- default`。

## 访问地址

- Frontend: `http://localhost:13000`
- Backend: `http://localhost:18000`
- OpenAPI: `http://localhost:18000/docs`
