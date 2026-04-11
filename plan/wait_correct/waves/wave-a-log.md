# Wave A Log

## Completed in this turn

- 新增 Rust 迁移控制面：
  - 路由 inventory 生成脚本
  - Python vs Rust 合同对比脚本
  - `plan/wait_correct/` 基础目录和模板
- Rust control-plane 从 `MemoryStore` 切到真实持久化路径：
  - `system-config`
  - `projects`
- Rust 已接管 `search`：
  - global search
  - projects search
  - tasks search
  - findings search
- Rust 已接管 `skills`：
  - catalog
  - prompt-skills CRUD
  - builtin prompt toggle
  - resources
  - skill detail
  - skill test / tool-test SSE
- `projects` 全域已补齐首批 owned 路由：
  - files / file-content / files-tree
  - upload preview / directory upload
  - stats / dashboard snapshot / static scan overview
  - export / import
  - cache stats / clear / invalidate
- 兼容过渡保留 Python mirror 同步：
  - `system-config`
  - `projects`
- `backend-migration-smoke.yml` 改为 Rust 主导的 smoke

## Wait Correct Entries

### 1. Project metadata persistence falls back to files only when no database pool is configured

- endpoint / feature: `/api/v1/projects/*`
- Python 旧行为: FastAPI + Postgres 持久化
- Rust 当前行为: `DATABASE_URL` 存在时写 `rust_projects` / `rust_project_archives`，缺省时退回文件持久化用于本地测试与迁移期收口
- 是否影响前端: 否，当前 HTTP 契约保持可用
- 后续修复波次: Wave A 后续 / Slice 1
- owner: Rust backend

### 2. Python compatibility mirror is transitional and must be deleted after task engines migrate

- endpoint / feature: `/api/v1/system-config/*`, `/api/v1/projects/*`
- Python 旧行为: Python 直接处理并读自己的表
- Rust 当前行为: Rust 为 source of truth，同时向 Python 旧表做 shadow write，确保代理到 Python 的扫描/任务链路还能读到配置和项目元数据
- 是否影响前端: 否
- 后续修复波次: Wave B / C
- owner: Rust migration

### 3. Static tasks and agent tasks are still not Rust-owned

- endpoint / feature: `/api/v1/static-tasks/*`, `/api/v1/agent-tasks/*`
- Python 旧行为: Python 直接处理
- Rust 当前行为: 仍通过 proxy 回退到 Python
- 是否影响前端: 否，迁移期依然可用
- 后续修复波次: Wave A/B/C
- owner: Rust migration

### 4. Search 和 skills 当前是最小可用契约，不是 Python 旧行为的逐字段复刻

- endpoint / feature: `/api/v1/search/*`, `/api/v1/skills/*`
- Python 旧行为: 依赖旧搜索服务、scan-core 元数据和复杂 DB 关联，以及 legacy `prompt_skills` / `user_configs`
- Rust 当前行为: project search 已 Rust-owned，但 tasks/findings 仍是空壳；skills 先提供前端主路径所需最小契约，但 custom prompt skills 和 builtin prompt state 仍绑在 Python 旧存储
- 是否影响前端: 当前主路径不受影响
- 后续修复波次: Wave A 后续 / Wave B
- owner: Rust migration

### 5. non-api python inventory is not yet migrated

- endpoint / feature: `backend_old/*.py`, `backend_old/app/**` except `backend_old/app/api/**`
- Python 旧行为: Python 直接承载 bootstrap、db/model/schema、runtime、upload、scan orchestration、llm、agent 主链路
- Rust 当前行为: Rust 只接管了控制面的一部分，核心 non-API runtime 仍主要由 Python 承担
- 是否影响前端: 当前主路径可用，但迁移目标未完成，mirror 和 proxy 仍必须保留
- 后续修复波次: Wave B / C / D / E / F
- owner: Rust migration

### 6. Rust startup bootstrap shell is now owned, but Python startup internals remain

- endpoint / feature: `backend/src/bootstrap/mod.rs`, `/health`, Rust server startup path
- Python 旧行为: Python `app.main` 在 lifespan 内负责 schema version check、`init_db()`、中断任务恢复、runner preflight
- Rust 当前行为: Rust 启动前已经执行 bootstrap，负责文件存储根检查、DB 可用性检查、Rust 自身依赖表检查，并开始接管 startup init / recovery / runner preflight 的 orchestration，同时把状态暴露到 `/health`
- Rust 当前行为补充: `backend/assets/scan_rule_assets/` 已成为扫描规则资产 root，并开始导入 Rust 自己维护的 `rust_scan_rule_assets`
- Rust 当前行为补充: Gitleaks preflight 已经开始消费 Rust materialize 出来的 builtin config
- Rust 当前行为补充: Opengrep preflight 已经开始消费 Rust materialize 出来的 internal / patch 规则目录
- Rust 当前行为补充: Bandit preflight 已经开始消费 Rust snapshot 选出的 test ids
- Rust 当前行为补充: PMD preflight 已经开始消费 Rust materialize 出来的 builtin rulesets
- 是否影响前端: 否，HTTP 主路径保持可用；健康态变得更诚实
- 后续修复波次: Wave A 后续 / Batch 1 Slice 2
- owner: Rust migration

### 7. Rust now reports legacy schema version status itself

- endpoint / feature: `backend/src/bootstrap/legacy_schema.rs`, `bootstrap.database.legacy_schema`, `/health`
- Python 旧行为: 只有 Python `app.main` 知道 `alembic_version` 是否落后，并决定是否自动跑 `alembic upgrade head`
- Rust 当前行为: Rust 会直接解析 `backend_old/alembic/versions/*.py` 推导 expected heads，并在 DB 可达时读取 `alembic_version.version_num`；缺失或不匹配时对 bootstrap 报 `degraded`
- Rust 当前行为补充: parser 已兼容 typed/plain assignment 和多行 `down_revision`
- Rust 当前行为补充: Rust 只接管可观测性与判定，不在启动期执行重型 migration
- 是否影响前端: 否，新增的是健康态细节，不破坏旧字段
- 后续修复波次: Wave A 后续 / Batch 1 Slice 3
- owner: Rust migration

### 8. backend_old live router no longer mounts Rust-owned routes

- endpoint / feature: `backend_old/app/api/v1/api.py`
- Python 旧行为: Python live router 同时挂载 `/search`、`/projects`、`/skills`，即使这些路径已由 Rust backend 接管
- Rust 当前行为: Rust 继续承接 `/api/v1/search/*`、`/api/v1/projects/*`、`/api/v1/skills/*`，Python live router 只保留仍未迁移的 `users / projects members / config / prompts / rules / agent-tasks / agent-test / static-tasks`
- Rust 当前行为补充: 已删除不再 live-mounted 的 Python endpoint 文件：
  - `backend_old/app/api/v1/endpoints/search.py`
  - `backend_old/app/api/v1/endpoints/skills.py`
- Rust 当前行为补充: 已删除不再 live-mounted 的 Python projects 聚合壳：
  - `backend_old/app/api/v1/endpoints/projects.py`
- Rust 当前行为补充: 已删除不再承担 bridge 职责的 Python projects 执行子模块：
  - `backend_old/app/api/v1/endpoints/projects_crud.py`
  - `backend_old/app/api/v1/endpoints/projects_files.py`
  - `backend_old/app/api/v1/endpoints/projects_insights.py`
  - `backend_old/app/api/v1/endpoints/projects_transfer.py`
  - `backend_old/app/api/v1/endpoints/projects_uploads.py`
  - `backend_old/app/api/v1/endpoints/projects_shared.py`
- Rust 当前行为补充: 已删除只覆盖这两个旧 endpoint 的 Python 专属测试：
  - `backend_old/tests/test_prompt_skills_api.py`
  - `backend_old/tests/test_skill_registry_api.py`
  - `backend_old/tests/test_skill_test_endpoint.py`
- Rust 当前行为补充: 已删除只通过 `projects.py` 聚合壳 import 的旧测试：
  - `backend_old/tests/test_dashboard_snapshot_query_params.py`
  - `backend_old/tests/test_dashboard_snapshot_v2.py`
  - `backend_old/tests/test_project_file_content.py`
  - `backend_old/tests/test_projects_crud_archive_download.py`
  - `backend_old/tests/test_projects_dashboard_snapshot_bandit.py`
  - `backend_old/tests/test_projects_description_generate.py`
  - `backend_old/tests/test_projects_response_serialization.py`
  - `backend_old/tests/test_projects_static_scan_overview.py`
  - `backend_old/tests/test_projects_zip_only_visibility.py`
  - `backend_old/tests/test_remote_repository_scan_removal.py`
  - `backend_old/tests/test_repository_https_only.py`
  - `backend_old/tests/test_file_tree.py`
- Rust 当前行为补充: 已删除只绑定旧 `projects_*` Python 执行子模块的测试：
  - `backend_old/tests/test_projects_create_with_zip.py`
  - `backend_old/tests/test_yasa_rules_api.py`
- Rust 当前行为补充: 新增回归测试 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`，防止这些已迁路径重新挂回 Python
- Rust 当前行为补充: 按“内网部署、无多用户管理”前提，已删除用户块旧 live endpoint：
  - `backend_old/app/api/v1/endpoints/users.py`
  - `backend_old/app/api/v1/endpoints/members.py`
- Rust 当前行为补充: Python live router 已不再挂载 `/users` 与 `/projects/*/members`
- Rust 当前行为补充: config 内部调用已开始去 endpoint 化：
  - 新增 `backend_old/app/services/user_config_service.py`
  - `agent_tasks_execution.py`
  - `static_tasks_shared.py`
  - `agent_test.py`
  - `static_tasks_opengrep_rules.py`
    已改为从 service 层读取 effective user config，不再反向 import `app.api.v1.endpoints.config`
- Rust 当前行为补充: `config.py` 当前保留 HTTP 契约，但核心默认配置/用户配置载入逻辑已通过 service 封装复用
- Rust 当前行为补充: 新增回归测试 `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- Rust 当前行为补充: Python live router 已不再挂载 `/config`，live 配置入口默认收敛到 Rust `/system-config`
- Rust 当前行为补充: `config.py` 当前只保留过渡 helper / 测试承载，不再承担 Python live API surface
- 是否影响前端: 否，前端应继续走 Rust backend；这一步只是缩小 Python live surface
- 后续修复波次: Wave A 后续 / API surface cleanup
- owner: Rust migration
