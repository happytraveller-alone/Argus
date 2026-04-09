# VulHunter Release

该分支是由 `main` 自动生成的最新 slim-source 发布快照，只支持以下两种启动方式：

```bash
docker compose up
```

```bash
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
```

## 启动前准备

首次启动前先准备 backend Docker 环境文件：

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

至少配置以下变量：

- `LLM_API_KEY`
- `LLM_PROVIDER`
- `LLM_MODEL`

## 两种启动方式的区别

- `docker compose up`：`backend`、`frontend`、runner、sandbox 继续使用云端镜像；`nexus-web` 与 `nexus-itemDetail` 因静态产物随 release 一起分发，仍在本地构建极简 Nginx 镜像。
- `docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build`：在默认链路基础上，额外把 `frontend` 和 `backend` 切到本地构建；`nexus-web` 与 `nexus-itemDetail` 仍沿用基础 compose 的本地构建例外。

## Nexus 静态产物说明

- release 快照保留 `nexus-web/dist/**`、`nexus-web/nginx.conf`、`nexus-itemDetail/dist/**`、`nexus-itemDetail/nginx.conf`
- slim release 不恢复旧的 release artifact / deploy 脚本体系
- `nexus-web` 默认监听 `http://localhost:5174`
- `nexus-itemDetail` 默认监听 `http://localhost:5175`

## 访问地址

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

更多启动细节见 [`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md)。
