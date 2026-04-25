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

1. 复制后端环境文件：

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

2. 至少填写这些配置：
   `LLM_API_KEY`、`LLM_PROVIDER`、`LLM_MODEL`

3. 确保本机已安装 Docker Compose，并且 Docker daemon 可访问。

## Repo-local Codex

- 本仓库的 repo-local Codex 配置位于 `.codex/config.toml`，按 `codex-cli 0.118.0` 的仓库级配置约定收敛为最小必需字段。
- 首次在本仓库使用 Codex 时，先执行一次 bootstrap：`CODEX_HOME=$PWD/.codex.local codex login`，或在确认风险后手动把 `~/.codex/auth.json` 复制到 `.codex.local/auth.json`。
- 完成 bootstrap 后，统一通过 `./scripts/codex-project.sh` 启动 Codex；直接运行裸 `codex` 不保证仓库隔离。

## GHCR 镜像命名

- GHCR 镜像地址格式是 `ghcr.io/<GitHub用户或组织>/<image>:<tag>`。
- `audittool` 是仓库名，不是 GHCR owner；默认镜像前缀使用当前仓库 owner `happytraveller-alone`。
- `.github/workflows/docker-publish.yml` 仍然是 reusable leaf builder；它默认使用当前仓库 owner 作为 namespace，并继续接受 `image_namespace` 和 `package_visibility`。
- 如需覆盖 namespace，调用 `.github/workflows/docker-publish.yml` 时传入 `image_namespace`；如果覆盖到其他组织或账号，需要同时提供 `GHCR_USERNAME` 和 `GHCR_TOKEN`。
- GitHub Actions 默认会把 GHCR 包设为 public，并验证匿名拉取；只要 `package_visibility` 不是 `public`，workflow 就会跳过匿名拉取校验。
- 人工触发的多镜像发布只保留 `.github/workflows/docker-publish-runtime-images.yml` 这一处。

## 三个受支持的命令

### 1. 默认镜像启动

```bash
docker compose up --build
```

用途：
全量本地构建并启动所有服务。

## 访问地址

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
