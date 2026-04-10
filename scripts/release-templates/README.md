# VulHunter Release

该分支是由 `main` 自动生成的最新 slim-source 发布快照，只支持以下三种启动方式：

```bash
docker compose up --build
```

```bash
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
```

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
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

## 三种启动方式的区别

- `docker compose up --build`：默认 compose 栈启动，基础定义里可构建的服务按当前仓库配置构建。
- `docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build`：在默认链路基础上，额外把 `frontend` 和 `backend` 切到本地构建。
- `docker compose -f docker-compose.yml -f docker-compose.full.yml up --build`：启用 full 覆盖层，做全量本地构建联调。

## 运行说明

- slim release 不恢复旧的 release artifact / deploy 脚本体系
- release 快照不再包含额外的 Nexus 静态运行时

## 访问地址

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
