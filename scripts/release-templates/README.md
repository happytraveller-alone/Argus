# Argus 使用说明

这是面向最终用户的发布分支。你只需要完成配置，然后启动服务即可。

## 1. 环境要求

- 已安装 Docker
- 已安装 Docker Compose
- Docker daemon 处于可用状态

## 2. 首次配置

保留根目录 `env.example`。如果根目录 `.env` 不存在，运行 bootstrap 会复制模板、自动生成 `SECRET_KEY` 并退出：

```bash
./argus-bootstrap.sh --wait-exit -- default
```

打开根目录 `.env`，至少填写以下配置：

- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_MODEL`

常见示例：

```env
LLM_PROVIDER=openai
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4o-mini
```

说明：

- `LLM_PROVIDER`：选择你要使用的大模型提供方
- `LLM_API_KEY`：对应提供方的 API Key
- `LLM_MODEL`：模型名称
- `SECRET_KEY`：bootstrap 会自动生成，通常不需要手动填写

可先运行校验脚本确认 LLM 配置无误：

```bash
./scripts/validate-llm-config.sh --env-file ./.env
```

默认情况下，Compose 会把前端发布到宿主机 `13000` 端口、后端发布到 `18000` 端口，以避免和常见本地开发服务的 `3000` / `8000` 端口冲突。如需恢复旧端口，启动时设置 `Argus_FRONTEND_PORT=3000 Argus_BACKEND_PORT=8000`。

## 3. 启动服务

推荐直接使用默认命令：

```bash
./argus-bootstrap.sh --wait-exit -- default
```

首次启动会拉取镜像并初始化数据库，时间可能较长。

如果你之前已经用 PostgreSQL 15 启动过这套发布分支，请先处理旧的 `postgres_data` 数据卷，再切换到当前默认的 PostgreSQL 18 镜像。

- 保留数据：先按你自己的流程完成 PG15 -> PG18 迁移，再启动当前版本。注意，PostgreSQL 18 官方镜像的卷挂载点也调整为 `/var/lib/postgresql`，不再继续使用旧的 `/var/lib/postgresql/data` 挂载方式。
- 不保留数据：直接删除旧卷后重新初始化。

最直接的重建方式：

```bash
docker compose down -v
docker compose up --build
```

如果想在后台运行：

```bash
docker compose up -d --build
```

## 4. 访问系统

启动成功后可通过以下地址访问：

- Web 界面：`http://localhost:13000`
- 后端接口：`http://localhost:18000`
- OpenAPI 文档：`http://localhost:18000/docs`

## 5. 常用命令

查看日志：

```bash
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

停止服务并删除数据卷：

```bash
docker compose down -v
```

说明：

- 这条命令也会删除旧的 `postgres_data` 卷。
- 如果该卷来自 PostgreSQL 15，而你又不准备做数据迁移，这是切到 PostgreSQL 18 默认镜像前最安全的重建路径。

## 6. 其他启动文件

仓库中还提供了其他 compose 覆盖文件，但默认用户通常不需要使用。若你只是部署和使用系统，执行：

```bash
docker compose up --build
```

即可。
