# VulHunter Slim Release

<p align="center">
  <strong>简体中文</strong> | <a href="README_EN.md">English</a>
</p>

该发布分支只保留 slim-source 运行所需文件，支持三种启动方式：

```bash
docker compose up --build
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

## 启动前准备

1. 复制后端环境文件：

```bash
cp docker/env/backend/env.example docker/env/backend/.env
```

2. 至少填写这些配置：
   `LLM_API_KEY`、`LLM_PROVIDER`、`LLM_MODEL`

3. 确保本机已安装 Docker Compose，并且 Docker daemon 可访问。

## 三个受支持的命令

### 1. 默认镜像启动

```bash
docker compose up --build
```

用途：
默认 compose 栈启动；如果基础服务本身带有可构建上下文，会同步按当前仓库配置构建。

### 2. 本地构建 frontend/backend

```bash
docker compose -f docker-compose.yml -f docker-compose.hybrid.yml up --build
```

用途：
仅对当前分支里的 `frontend` 和 `backend` 源码执行本地构建；数据库、Redis、runner 和 sandbox 继续使用镜像。

### 3. 全量本地构建

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml up --build
```

用途：
对 `frontend`、`backend` 以及 full 覆盖层中定义的本地构建目标执行完整本地构建，适合需要全量联调的场景。

## 访问地址

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
