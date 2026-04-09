# Slim Release Compose Guide

这个 slim release 只支持两个 compose 入口：

```bash
docker compose up
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
```

## 环境引导

先复制后端环境模板：

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

至少配置：
`LLM_API_KEY`、`LLM_PROVIDER`、`LLM_MODEL`

## 命令说明

### `docker compose up`

- 默认使用已发布镜像启动 `backend`、`frontend`、runner 和 sandbox
- `db` 与 `redis` 仍由当前 compose 文件拉起

### `docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build`

- 仅本地构建 `backend` 与 `frontend`
- `db`、`redis`、runner 和 sandbox 继续使用镜像
- 适合在 slim release 树内对交付源码做最小改动后重新启动

## 访问地址

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
