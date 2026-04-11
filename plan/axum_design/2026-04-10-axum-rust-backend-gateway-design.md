# Axum Rust Backend Gateway Design

## 背景

当前后端是 `backend_old/app/main.py` 驱动的 FastAPI 单体服务，对外暴露 `/api/v1/*`。项目规模已经大到不适合继续在 Python 单体里硬补，所以本次迁移不再追求“原地翻修”，而是新增一套 Rust 后端逐步夺回接口控制权。

这次设计已经锁定以下前提：

- 新后端框架使用 `Axum`
- 不删除旧 Python 后端
- Rust 先成为统一入口网关，再逐步接管接口
- 首批接管范围是 `health`、`config`、`projects`
- Rust 内外都去用户化，不再保留用户管理语义
- 允许为 Rust 新建独立的去用户化 schema 和配置存储
- 显式删除仓库中的 `nexus-web` 服务、构建和首页嵌入

## 核心结论

### 1. Rust 成为唯一公开入口

Rust 服务接管当前对外后端端口，统一接受前端请求。

- Rust 已迁移的路由，直接在 Axum 内处理
- Rust 未迁移的路由，反向代理到内部 Python 服务
- Python 不再直接面向前端，只作为迁移期上游

这能保证前端永远只连一个后端，不把“双栈状态机”塞进浏览器。

同时，前端不再依赖 `nexus-web` 这类第三页面服务；首页和本地部署拓扑统一收敛为 `frontend + backend/backend_old`。

### 2. 去用户化不是补丁，而是重新定义边界

现有 Python “鉴权”本质上只是读取数据库里第一个用户，这种东西没有迁移价值。Rust 新后端按单租户内网系统设计：

- 不提供登录、登出、token、权限控制
- 不要求 `current_user`
- `Project`、系统配置、ZIP 归档都视为系统级资源

用户相关的旧接口和旧表，不在 Rust 首批设计中复刻。

### 3. 首批不是整个 `projects` 大杂烩，而是可接管的最小子集

`projects` 路由组现在混杂了 CRUD、ZIP 上传、文件浏览、统计、导入导出、成员管理和描述生成。首批只迁真正适合先拿下的部分，剩余内容继续代理到 Python。

## Rust 首批拥有的公开接口

### 健康检查

- `GET /health`

保持简单稳定，返回 Rust 网关自身状态，不再依赖 Python。

### 系统配置

Rust 不再沿用 `/config/me` 这套假“当前用户配置”命名，改成系统级配置接口：

- `GET /api/v1/system-config/defaults`
- `GET /api/v1/system-config`
- `PUT /api/v1/system-config`
- `DELETE /api/v1/system-config`
- `GET /api/v1/system-config/llm-providers`
- `POST /api/v1/system-config/test-llm`
- `POST /api/v1/system-config/fetch-llm-models`
- `POST /api/v1/system-config/agent-preflight`

外部契约不再包含：

- `user_id`
- `id`
- “当前用户”语义

### 项目

Rust 首批直接拥有这些项目接口：

- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `GET /api/v1/projects/{id}`
- `PUT /api/v1/projects/{id}`
- `GET /api/v1/projects/info/{id}`
- `POST /api/v1/projects/create-with-zip`
- `GET /api/v1/projects/{id}/zip`
- `POST /api/v1/projects/{id}/zip`
- `DELETE /api/v1/projects/{id}/zip`

这些接口足够覆盖：

- 项目列表页基础加载
- 项目创建与更新
- ZIP 项目主流程
- 基础项目信息查看

## 继续代理给 Python 的接口

首批不碰下面这些高耦合或高风险路径，Rust 统一透传：

- `/api/v1/agent-tasks/*`
- `/api/v1/static-tasks/*`
- `/api/v1/search/*`
- `/api/v1/skills/*`
- `/api/v1/prompts/*`
- `/api/v1/users/*`
- `/api/v1/projects/{id}/files*`
- `/api/v1/projects/stats`
- `/api/v1/projects/dashboard-snapshot`
- `/api/v1/projects/static-scan-overview`
- `/api/v1/projects/export`
- `/api/v1/projects/import`
- `/api/v1/projects/*/members*`
- 旧 `/api/v1/config/*`

注意：首批迁移后，前端会改连新的 `system-config` 路径；旧 `config` 路径保留给尚未切换的内部逻辑或回退路径，不作为新前端契约。

## Rust 存储设计

Rust 不复用 Python 现有 `users`、`user_configs`、`projects.owner_id` 这类历史包袱，直接建立自己的 schema。

### 建议表

#### `system_configs`

单行或小表设计，保存系统级配置：

- `id`
- `llm_config_json`
- `other_config_json`
- `created_at`
- `updated_at`

#### `rust_projects`

保存去用户化项目元数据：

- `id`
- `name`
- `description`
- `source_type`
- `repository_type`
- `default_branch`
- `programming_languages_json`
- `is_active`
- `created_at`
- `updated_at`

首批固定只支持 `zip` 项目，`repository_url` 不进入新模型。

#### `rust_project_archives`

保存 ZIP 元信息和存储定位：

- `project_id`
- `original_filename`
- `storage_path`
- `sha256`
- `file_size`
- `created_at`
- `updated_at`

ZIP 二进制本体继续放文件卷，不塞进数据库。

## 运行与部署设计

### Compose 拓扑

迁移后 Compose 角色调整为：

- `backend`：Rust Axum 网关，对外暴露 `8000`
- `backend-py`：旧 Python FastAPI，仅容器内访问，例如 `8001`
- `frontend`：继续只连 `backend`

Rust 通过环境变量指向 Python 上游，例如：

- `PYTHON_UPSTREAM_BASE_URL=http://backend-py:8001`

### 文件卷

Rust 与 Python 可以共享现有上传卷，但首批只要求 Rust 自己能读写其项目 ZIP 目录。共享卷的目的是避免迁移期把文件存储也拆成两套孤岛。

## Axum 内部结构

Rust 服务按“网关壳 + 领域模块”组织，不做第二个单体泥球。

建议目录：

- `backend/src/main.rs`
- `backend/src/app.rs`
- `backend/src/config.rs`
- `backend/src/state.rs`
- `backend/src/error.rs`
- `backend/src/proxy.rs`
- `backend/src/routes/health.rs`
- `backend/src/routes/system_config.rs`
- `backend/src/routes/projects.rs`
- `backend/src/db/system_config.rs`
- `backend/src/db/projects.rs`

职责边界：

- 路由层只做参数解析和响应组装
- `db/*` 只做 SQLx 访问
- `proxy.rs` 只做未迁移请求转发
- 共享错误、配置、状态集中放在根模块

## 前端契约变化

这次不再伪装成旧的“用户配置”模型，前端要一起改：

- `frontend/src/shared/api/database.ts`
- `frontend/src/shared/types/index.ts`
- `frontend/src/components/system/SystemConfig.tsx`
- `frontend/src/pages/projects/data/*`

重点变化：

- `/config/me` 改为 `/system-config`
- 配置响应去掉 `id`、`user_id`
- 项目响应去掉 `owner_id`
- 不再展示或操作成员管理入口

## 迁移原则

### 1. 不做 Python 逻辑逐行翻译

Rust 只对齐必要的 HTTP 行为和前端需要的数据形状，不去复制 Python 内部的坏结构。

### 2. 不在首批里碰高风险实时链路

首批禁止把这些东西一起卷进来：

- SSE
- AgentTask 执行
- 静态扫描调度
- Docker runner 调度
- 旧项目文件浏览缓存体系

### 3. 网关必须默认安全回退

只要某条路由还没被 Rust 明确拥有，就直接代理给 Python，不要做“半实现”。

## 风险与控制

### 风险 1：前端仍引用旧路径或旧字段

控制方式：

- 首批同时改 API client 和类型
- 为新路径补前端契约测试
- 不依赖“运行时猜字段”

### 风险 2：Rust 项目与 Python 项目数据分裂

控制方式：

- 明确接受首批为 Rust 新存储，不做跨库自动同步
- 首批只让已切换前端消费 Rust 项目数据
- 后续如果要导入历史 Python 项目，再单独做迁移工具

### 风险 3：网关回退逻辑把流式/上传请求搞坏

控制方式：

- 反向代理层单独写集成测试
- 首批重点覆盖 JSON、multipart、错误码透传
- SSE 路径虽然继续代理，但要在网关层显式支持流式透传

## 分阶段落地

### Phase 1

- 搭建 Axum 网关壳
- 接管 `/health`
- 接入反向代理到 Python
- 保证未迁移接口不回归

### Phase 2

- 落地 `system-config` 新接口和新存储
- 前端系统配置页切到 Rust 新契约

### Phase 3

- 落地 `projects` 首批 ZIP CRUD 接口
- 前端项目页切到 Rust 数据源

### Phase 4

- 扩展更多项目接口
- 视情况再处理文件浏览、统计、扫描总览

## 非目标

这次明确不做：

- 用户体系重建
- Python 数据表兼容层
- `AgentTask` Rust 化
- 静态扫描引擎 Rust 化
- 全量接口一次性迁移
