# Argus Slim Release

<p align="center">
  <strong>简体中文</strong> | <a href="README_EN.md">English</a>
</p>

该发布分支只保留 slim-source 运行所需文件。推荐启动方式：

```bash
./argus-bootstrap.sh --wait-exit -- default
```

当前 compose 链路已统一为 `Rust backend + TypeScript frontend`，不再包含旧的 Python backend 双后端链路。

## 启动前准备

1. 确保本机已安装 Docker Compose，并且 Docker daemon 可访问。
2. 保留根目录 `env.example`。首次运行 `./argus-bootstrap.sh` 时，如果根目录 `.env` 不存在，脚本会复制 `env.example` 为 `.env`，自动生成 `SECRET_KEY`，提示你填写配置后退出。
3. 填写 `.env` 中的 LLM 配置后，再次运行 `./argus-bootstrap.sh`；也可以先运行 `./scripts/validate-llm-config.sh --env-file ./.env` 确认 LLM 配置无误。

`argus-bootstrap.sh` 会在任何 Docker 清理或启动动作前调用 `scripts/validate-llm-config.sh --env-file ./.env` 校验 env/LLM 配置。校验失败时脚本会退出并提示重新配置。

默认情况下，Compose 会把前端发布到宿主机 `13000` 端口、后端发布到 `18000` 端口，以避免和常见本地开发服务的 `3000` / `8000` 端口冲突。如需恢复旧端口，启动时设置 `Argus_FRONTEND_PORT=3000 Argus_BACKEND_PORT=8000`。

后端会读取根目录 `.env`，并把 `${DOCKER_SOCKET_PATH:-/var/run/docker.sock}` 挂载给扫描 runner。本工作区的本地 `.env` 可将它覆盖为 `/run/docker-local.sock`；其他环境按需设置 `DOCKER_SOCKET_PATH`。

## Repo-local Codex / OMX

- 本仓库的 repo-local Codex 配置位于 `.codex/config.toml`；启动本项目内的 Codex/OMX 会话时，显式设置 `CODEX_HOME=$PWD/.codex`，避免落到全局 `~/.codex`。
- 首次在本仓库使用 Codex 时，先执行一次 bootstrap：`CODEX_HOME=$PWD/.codex codex login`，或在确认风险后手动把 `~/.codex/auth.json` 复制到 `.codex/auth.json`。
- 项目级 agent 指令由 `AGENTS.md` 统一承载；repo-local skills 从 `.codex/skills/` 加载。里程碑收尾可使用 `neat-freak` 同步项目文档与 agent 知识。
- `.gitignore` 会忽略 `.codex/`；如果需要让其他环境复用某个本地 skill，请重新安装该 skill 或显式调整版本控制策略。

## CubeSandbox Python / C++ / CodeQL 试运行

CubeSandbox 需要 WSL2 原生 KVM/QEMU，并通过独立开发 VM 跑 E2B-compatible API；它不属于 Argus 默认 compose 主线，也不再通过 Docker helper 容器运行 QEMU。按 [docs/cubesandbox-python-quickstart.md](docs/cubesandbox-python-quickstart.md) 使用 `scripts/cubesandbox-quickstart.sh` 配置和运行 Python、C、C++、Make、CMake、CodeQL smoke。脚本默认把 CubeSandbox API 转发到 `127.0.0.1:23000`，避免占用 Argus 前端默认端口 `13000`；所有 GitHub 地址默认走 `https://v6.gh-proxy.org/https://github.com/...` 镜像，Docker Hub 镜像可显式替换为 `m.daocloud.io/docker.io/...`。

## GHCR 镜像命名

- GHCR 镜像地址格式是 `ghcr.io/<GitHub用户或组织>/<image>:<tag>`。
- `audittool` 是仓库名，不是 GHCR owner；默认镜像前缀使用当前仓库 owner `happytraveller-alone`。
- `.github/workflows/docker-publish.yml` 统一处理 backend、frontend 和 OpenGrep runner 容器镜像的构建与发布；CodeQL 扫描主路径走 CubeSandbox 模板，不发布 CodeQL runner 容器。
- OpenGrep runner 发布时显式使用 OCI image media types；本地 `runner-build` / `rebuild-opengrep-runner-verify.sh` 仍使用 Docker daemon 本地镜像路径验证运行能力。
- GitHub Actions 默认会把 GHCR 包设为 public，并验证匿名拉取。
- 人工触发的多镜像发布也统一通过 `.github/workflows/docker-publish.yml` 选择需要构建的镜像。

## 三个受支持的命令

### 1. 默认镜像启动

```bash
./argus-bootstrap.sh --wait-exit -- default
```

用途：
校验 LLM env、构建并启动所有服务，等待前后端就绪后退出。

## 访问地址

- Frontend: `http://localhost:13000`
- Backend: `http://localhost:18000`
- OpenAPI: `http://localhost:18000/docs`
