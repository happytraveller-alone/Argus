# Docker Compose 快速参考

## 文件结构

```
根目录/
├── docker-compose.yml              # 主配置 (日常开发)
├── docker-compose.full.yml         # 完整构建
└── docker/
    ├── docker-compose.yasa-host.yml        # YASA 主机模式
    └── docker-compose.sandbox-runner.yml   # Sandbox Runner
```

## 快速启动

### 日常开发 (推荐)

```bash
# 使用预构建镜像,快速启动
docker compose up --build
```

### 完整本地构建

```bash
# 本地构建所有 scanner runners
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  up --build
```

## 扩展配置使用

### Sandbox Runner

```bash
# 构建 sandbox-runner 镜像
docker compose -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  build sandbox-runner

# 测试
docker compose -f docker-compose.yml \
  -f docker/docker-compose.sandbox-runner.yml \
  up sandbox-runner
```

### YASA 主机模式

```bash
# 使用主机上的 YASA (需要先安装)
YASA_HOST_PATH=/path/to/yasa \
docker compose -f docker-compose.yml \
  -f docker/docker-compose.yasa-host.yml \
  up --build
```

## 常用命令

### 启动服务

```bash
# 前台运行 (查看日志)
docker compose up

# 后台运行
docker compose up -d

# 重新构建并启动
docker compose up --build
```

### 停止服务

```bash
# 停止但保留容器
docker compose stop

# 停止并删除容器
docker compose down

# 停止并删除容器、卷、镜像
docker compose down -v --rmi local
```

### 查看日志

```bash
# 所有服务
docker compose logs

# 特定服务
docker compose logs backend

# 实时跟踪
docker compose logs -f backend

# 最近 100 行
docker compose logs --tail=100 backend
```

### 重启服务

```bash
# 重启所有服务
docker compose restart

# 重启特定服务
docker compose restart backend
```

## 构建命令

### 构建特定服务

```bash
# 只构建 backend
docker compose build backend

# 无缓存构建
docker compose build --no-cache backend

# 并行构建
docker compose build --parallel
```

### 完整构建流程

```bash
# 1. 清理旧环境
docker compose down -v

# 2. 完整构建
docker compose -f docker-compose.yml \
  -f docker-compose.full.yml \
  build --no-cache

# 3. 启动验证
docker compose up -d

# 4. 查看状态
docker compose ps
```

## 常见场景

### 场景 1: 首次启动

```bash
# 1. 复制环境变量文件
cp docker/env/backend/env.example docker/env/backend/.env

# 2. 编辑配置
vim docker/env/backend/.env

# 3. 启动
docker compose up --build
```

### 场景 2: 更新代码后重启

```bash
# 后端代码更新 (自动重载,无需重启)
# 前端代码更新
docker compose restart frontend
```

### 场景 3: 数据库迁移

```bash
# 进入 backend 容器
docker compose exec backend bash

# 运行迁移
cd backend
alembic upgrade head
```

### 场景 4: 清理并重新开始

```bash
# 完全清理
docker compose down -v --rmi local

# 重新构建
docker compose up --build
```

## 环境变量

### 常用配置

编辑 `docker/env/backend/.env`:

```bash
# LLM 配置
LLM_PROVIDER=openai
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4

# Sandbox 配置
SANDBOX_RUNNER_ENABLED=true
SANDBOX_RUNNER_IMAGE=vulhunter/sandbox-runner:latest

# 数据库
POSTGRES_DB=vulhunter
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

### 镜像源配置

```bash
# 使用国内镜像源
DOCKERHUB_LIBRARY_MIRROR=docker.m.daocloud.io/library
BACKEND_APT_MIRROR_PRIMARY=mirrors.aliyun.com
BACKEND_PYPI_INDEX_PRIMARY=https://mirrors.aliyun.com/pypi/simple/
```

## 故障排查

### 服务无法启动

```bash
# 检查服务状态
docker compose ps

# 查看详细日志
docker compose logs backend

# 检查配置
docker compose config
```

### 端口冲突

```bash
# 修改 .env 中的端口
VULHUNTER_BACKEND_PORT=8001  # 默认 8000
VULHUNTER_FRONTEND_PORT=3001  # 默认 3000
```

### 数据库连接失败

```bash
# 检查数据库状态
docker compose ps db

# 查看数据库日志
docker compose logs db

# 重启数据库
docker compose restart db
```

### 镜像拉取失败

```bash
# 检查网络
ping mirrors.aliyun.com

# 使用代理
export HTTP_PROXY=http://proxy:8080
docker compose up --build
```

## 性能优化

### 加速构建

```bash
# 使用 BuildKit
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# 并行构建
docker compose build --parallel
```

### 减少资源占用

```bash
# 限制资源
docker compose up --scale worker=1

# 定期清理
docker system prune -a
```

## 详细文档

- 📖 [完整扩展配置说明](docker/COMPOSE_EXTENSIONS.md)
- 🏗️ [Sandbox Runner 构建指南](docker/BUILD_SANDBOX_RUNNER.md)
- 📘 [Sandbox Runner 使用文档](docker/SANDBOX_RUNNER.md)
- 🔧 [主项目 README](README.md)

## 快速链接

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Database: localhost:5432
- Redis: localhost:6379
