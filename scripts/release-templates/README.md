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

- `docker compose up`：前后端和扫描相关服务全部使用云端镜像。
- `docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build`：只在本地构建 `frontend` 和 `backend`，其余 runner / sandbox / infra 继续使用云端镜像。

## 访问地址

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

更多启动细节见 [`scripts/README-COMPOSE.md`](scripts/README-COMPOSE.md)。
