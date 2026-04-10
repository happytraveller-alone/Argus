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

- `docker compose up`：`backend`、`frontend`、runner、sandbox 使用发布镜像启动，不再依赖额外的第三页面服务。
- `docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build`：在默认链路基础上，额外把 `frontend` 和 `backend` 切到本地构建。

## 运行说明

- slim release 不恢复旧的 release artifact / deploy 脚本体系
- release 快照不再包含额外的 Nexus 静态运行时

## 访问地址

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

更多启动细节见 [`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md)。
