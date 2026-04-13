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
- Gitleaks Python endpoint surface retired:
  - 删除 `backend_old/app/api/v1/endpoints/static_tasks_gitleaks.py`
  - `backend_old/app/api/v1/endpoints/static_tasks.py` 已移除 `_gitleaks` import、router include、runtime bind、schema alias 与 re-export
  - inventory 中 `/api/v1/static-tasks/gitleaks/*` 已从 Python proxy 改为 Rust-owned (`migrate`)
- Bandit Python endpoint surface retired:
  - 删除 `backend_old/app/api/v1/endpoints/static_tasks_bandit.py`
  - `backend_old/app/api/v1/endpoints/static_tasks.py` 已移除 `_bandit` import、router include、runtime bind、schema alias、helper alias 与 re-export
  - inventory 中 `/api/v1/static-tasks/bandit/*` 已从 Python proxy 改为 Rust-owned (`migrate`)
- PMD Python endpoint surface retired:
  - 删除 `backend_old/app/api/v1/endpoints/static_tasks_pmd.py`
  - `backend_old/app/api/v1/endpoints/static_tasks.py` 已移除 `_pmd` import、router include、runtime bind、schema alias、helper alias 与 re-export
  - inventory 中 `/api/v1/static-tasks/pmd/*` 已从 Python proxy 改为 Rust-owned (`migrate`)
- Opengrep rules Python endpoint surface retired:
  - 删除 `backend_old/app/api/v1/endpoints/static_tasks_opengrep_rules.py`
  - `backend_old/app/api/v1/endpoints/static_tasks.py` 已移除 `_opengrep_rules` import、router include、schema alias、helper alias 与 re-export
  - inventory 中 `/api/v1/static-tasks/rules*` 已从 Python proxy 改为 Rust-owned (`migrate`)
- Opengrep tasks Python endpoint surface retired:
  - 删除 `backend_old/app/api/v1/endpoints/static_tasks_opengrep.py`
  - `backend_old/app/api/v1/endpoints/static_tasks.py` 已移除 `_opengrep` import、router include、schema alias、helper alias 与 re-export
  - inventory 中 `/api/v1/static-tasks/tasks*` 与 `/api/v1/static-tasks/findings/{finding_id}/status` 已从 Python proxy 改为 Rust-owned (`migrate`)
- Agent-test Python endpoint surface retired:
  - 删除 `backend_old/app/api/v1/endpoints/agent_test.py`
  - `backend_old/app/api/v1/api.py` 已移除 `agent_test` import 与 `api_router.include_router(..., prefix="/agent-test")` 挂载
  - inventory 中 `/api/v1/agent-test/*` 已从 Python proxy 改为 Rust-owned (`migrate`)
- Agent-task reporting Python endpoint surface retired:
  - 删除 `backend_old/app/api/v1/endpoints/agent_tasks_reporting.py`
  - `backend_old/app/api/v1/endpoints/agent_tasks.py` 已移除 reporting import/re-export 与 reporting router 挂载
  - Rust `backend/src/routes/agent_tasks.rs` 已覆盖 `/api/v1/agent-tasks/{task_id}/report` 与 `/api/v1/agent-tasks/{task_id}/findings/{finding_id}/report`
  - inventory 中两条 agent-task report export route 已登记为 Rust-owned (`migrate`)
- Agent-task results Python endpoint surface retired:
  - 删除 `backend_old/app/api/v1/endpoints/agent_tasks_routes_results.py`
  - `backend_old/app/api/v1/endpoints/agent_tasks.py` 已移除 results import/re-export 与 results router 挂载
  - Rust `backend/src/routes/agent_tasks.rs` 已覆盖 `/api/v1/agent-tasks/{task_id}/findings*`、`/summary`、`/agent-tree`、`/checkpoints*`
  - inventory 中七条 agent-task result route 已登记为 Rust-owned (`migrate`)
- Agent-task lifecycle Python endpoint surface retired:
  - 删除 `backend_old/app/api/v1/endpoints/agent_tasks_routes_tasks.py`
  - `backend_old/app/api/v1/endpoints/agent_tasks.py` 已移除 tasks import/re-export 与 tasks router 挂载
  - Rust `backend/src/routes/agent_tasks.rs` 已覆盖 `/api/v1/agent-tasks`、`/{task_id}`、`/{task_id}/cancel`、`/{task_id}/events*`
  - inventory 中七条 agent-task lifecycle route 已登记为 Rust-owned (`migrate`)
- Python v1 API router mounts retired:
  - `backend_old/app/api/v1/api.py` 已移除 `agent_tasks` / `static_tasks` include_router，`api_router` 仅保留空 APIRouter 壳
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py` 与 `backend_old/tests/test_agent_tasks_module_layout.py` 已改为断言 router 无 mounted paths
- Stale top-level search/rules proxy inventory retired:
  - `backend_old/app/api/v1/endpoints/search.py` 与 `backend_old/app/api/v1/endpoints/rules.py` 当前仓库不存在
  - inventory 中 legacy `/api/v1/findings/search`、`/api/v1/tasks/search`、`/api/v1/rules*` 已由 `proxy` 切换为 `retire`
  - Python inventory 现已满足 `proxy = 0`
- Legacy runtime startup wrapper no longer jumps back to Python app entry:
  - `backend/src/runtime/bootstrap.rs` 已移除 `app.main:app` / uvicorn exec，改为直接 exec Rust backend binary
  - `docker/backend_old.Dockerfile` 的 runtime-entrypoints 现会同时构建并复制 `backend-rust`
  - legacy `backend-runtime-startup` 保留为兼容 wrapper，但最终 server process 已切到 Rust backend
- Python FastAPI main entry module retired:
  - 删除 `backend_old/app/main.py`
  - 删除只服务旧 Python main 入口的测试：
    - `backend_old/tests/test_startup_schema_migration.py`
    - `backend_old/tests/test_startup_interrupted_recovery.py`
    - `backend_old/tests/test_runner_preflight.py`
    - `backend_old/tests/test_database_route_retired.py`
  - Rust 侧已有 `backend/tests/bootstrap_startup.rs`、`backend/tests/runtime_env_bootstrap.rs`、`backend/tests/http_smoke.rs` 承担启动/bootstrap/health 合同覆盖
- Legacy FastAPI deps module retired:
  - 删除 `backend_old/app/api/deps.py`
  - 静态扫描 helper 已迁到 `backend_old/app/services/static_scan_runtime.py`，并在 service 模块内保持无 `deps` import
  - `app.db.session` / `core.security` blocker 列表已同步去掉 `api/deps.py`
- Legacy static-tasks facade retired:
  - 删除 `backend_old/app/api/v1/endpoints/static_tasks.py`
  - 删除只服务该 facade 的旧 Python 测试：
    - `backend_old/tests/test_static_tasks_split_contract.py`
    - `backend_old/tests/test_phpstan_rules_snapshot.py`
    - `backend_old/tests/test_phpstan_rules_api.py`
    - `backend_old/tests/test_static_tri_state_statuses.py`
- Legacy static reset helper retired:
  - 删除 `backend_old/scripts/reset_static_scan_tables.py`
  - `backend_old/scripts/dev-entrypoint.sh` 已改为跳过 Python reset 脚本，声明 Rust 规则 bootstrap 为 authoritative
  - `backend/src/runtime/bootstrap.rs` 的 `run_optional_resets()` 已不再 shell out 到 Python script
  - `init_db` blocker 列表已同步去掉 `reset_static_scan_tables.py`
- Legacy project transfer service retired:
  - 删除 `backend_old/app/services/project_transfer_service.py`
  - 删除 `backend_old/tests/test_project_transfer_service.py`
  - `app.db.base` / `init_db` / `backend_old/app/db` blocker 列表已同步去掉 project transfer service 与对应旧测试
- Legacy agent runtime/access/metrics helpers retired:
  - 删除 `backend_old/app/api/v1/endpoints/agent_tasks_runtime.py`
  - 删除 `backend_old/app/api/v1/endpoints/agent_tasks_access.py`
  - 删除 `backend_old/app/services/project_metrics.py`
  - 删除对应旧测试：
    - `backend_old/tests/test_agent_tree_persistence.py`
    - `backend_old/tests/test_agent_task_terminal_finalization.py`
    - `backend_old/tests/test_agent_task_retry_abort.py`
    - `backend_old/tests/test_agent_task_cancel_origin_retry.py`
    - `backend_old/tests/test_project_metrics_service.py`
  - `agent_tasks.py` facade 与 module-layout 检查已移除 runtime/access re-export 预期

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

### 15. phpstan endpoint surface retired from Python static tasks router

- endpoint / feature: `/api/v1/static-tasks/phpstan/*`
- Python 旧行为:
  - `backend_old/app/api/v1/endpoints/static_tasks.py` 通过 `_phpstan` include/runtime bind/schema alias/helper alias/re-export 暴露 phpstan endpoint
  - `backend_old/app/api/v1/endpoints/static_tasks_phpstan.py` 承载完整 phpstan route surface
- Rust 当前行为:
  - `backend/src/routes/static_tasks.rs` 已提供 Rust-owned `/api/v1/static-tasks/phpstan/*`
  - Python `static_tasks.py` 已移除 `_phpstan` import、`router.include_router(_phpstan.router)`、runtime bind、schema alias、helper alias、re-export
  - `backend_old/app/api/v1/endpoints/static_tasks_phpstan.py` 已删除
- inventory 更新:
  - `python-endpoints-inventory.csv` 中 `/api/v1/static-tasks/phpstan/*` 全部由 `proxy` 切换为 `migrate`
  - source/owner 切换为 `static_tasks_rust` + `backend/src/routes/static_tasks.rs`
  - 汇总计数更新为 `migrate=90`、`proxy=62`，task-group `proxy=49`
- 后续修复波次: Wave A static engine endpoint retirement
- owner: Rust migration

### 16. pmd endpoint surface retired from Python static tasks router

- endpoint / feature: `/api/v1/static-tasks/pmd/*`
- Python 旧行为:
  - `backend_old/app/api/v1/endpoints/static_tasks.py` 通过 `_pmd` include/runtime bind/schema alias/helper alias/re-export 暴露 pmd endpoint
  - `backend_old/app/api/v1/endpoints/static_tasks_pmd.py` 承载完整 pmd route surface
- Rust 当前行为:
  - `backend/src/routes/static_tasks.rs` 已提供 Rust-owned `/api/v1/static-tasks/pmd/*`
  - Python `static_tasks.py` 已移除 `_pmd` import、`router.include_router(_pmd.router)`、runtime bind、schema alias、helper alias、re-export
  - `backend_old/app/api/v1/endpoints/static_tasks_pmd.py` 已删除
- inventory 更新:
  - `python-endpoints-inventory.csv` 中 `/api/v1/static-tasks/pmd/*` 全部由 `proxy` 切换为 `migrate`
  - source/owner 切换为 `static_tasks_rust` + `backend/src/routes/static_tasks.rs`
  - 汇总计数更新为 `migrate=106`、`proxy=46`，task-group `proxy=33`
- 后续修复波次: Wave A static engine endpoint retirement
- owner: Rust migration

### 17. opengrep-rules endpoint surface retired from Python static tasks router

- endpoint / feature: `/api/v1/static-tasks/rules*`
- Python 旧行为:
  - `backend_old/app/api/v1/endpoints/static_tasks.py` 通过 `_opengrep_rules` include/schema alias/helper alias/re-export 暴露 opengrep-rules endpoint
  - `backend_old/app/api/v1/endpoints/static_tasks_opengrep_rules.py` 承载完整 opengrep-rules route surface
- Rust 当前行为:
  - `backend/src/routes/static_tasks.rs` 已提供 Rust-owned `/api/v1/static-tasks/rules*`
  - Python `static_tasks.py` 已移除 `_opengrep_rules` import、`router.include_router(_opengrep_rules.router)`、schema alias、helper alias、re-export
  - `backend_old/app/api/v1/endpoints/static_tasks_opengrep_rules.py` 已删除
- inventory 更新:
  - `python-endpoints-inventory.csv` 中 `/api/v1/static-tasks/rules*` 全部由 `proxy` 切换为 `migrate`
  - source/owner 切换为 `static_tasks_rust` + `backend/src/routes/static_tasks.rs`
  - 汇总计数更新为 `migrate=120`、`proxy=32`，task-group `proxy=19`
- 后续修复波次: Wave A static engine endpoint retirement
- owner: Rust migration

### 18. opengrep-tasks endpoint surface retired from Python static tasks router

- endpoint / feature: `/api/v1/static-tasks/tasks*`, `/api/v1/static-tasks/findings/{finding_id}/status`
- Python 旧行为:
  - `backend_old/app/api/v1/endpoints/static_tasks.py` 通过 `_opengrep` include/schema alias/helper alias/re-export 暴露 opengrep task execution endpoint
  - `backend_old/app/api/v1/endpoints/static_tasks_opengrep.py` 承载完整 opengrep task execution route surface
- Rust 当前行为:
  - `backend/src/routes/static_tasks.rs` 已提供 Rust-owned `/api/v1/static-tasks/tasks*` 与 `/api/v1/static-tasks/findings/{finding_id}/status`
  - Python `static_tasks.py` 已移除 `_opengrep` import、`router.include_router(_opengrep.router)`、schema alias、helper alias、re-export
  - `backend_old/app/api/v1/endpoints/static_tasks_opengrep.py` 已删除
- inventory 更新:
  - `python-endpoints-inventory.csv` 中 `/api/v1/static-tasks/tasks*` 与 `/api/v1/static-tasks/findings/{finding_id}/status` 全部由 `proxy` 切换为 `migrate`
  - source/owner 切换为 `static_tasks_rust` + `backend/src/routes/static_tasks.rs`
  - 汇总计数更新为 `migrate=130`、`proxy=22`，task-group `proxy=9`
- 后续修复波次: Wave A static engine endpoint retirement
- owner: Rust migration

### 19. agent-test endpoint surface retired from Python API router

- endpoint / feature: `/api/v1/agent-test/*`
- Python 旧行为:
  - `backend_old/app/api/v1/api.py` 通过 `api_router.include_router(agent_test.router, prefix="/agent-test")` 挂载 agent-test route group
  - `backend_old/app/api/v1/endpoints/agent_test.py` 承载完整 agent-test SSE/streaming route surface
- Rust 当前行为:
  - `backend/src/routes/mod.rs` 已显式挂载 Rust-owned `/api/v1/agent-test`
  - Python `backend_old/app/api/v1/api.py` 已移除 `agent_test` import 和 router 挂载
  - `backend_old/app/api/v1/endpoints/agent_test.py` 已删除
- inventory 更新:
  - `python-endpoints-inventory.csv` 中 `/api/v1/agent-test/*` 全部由 `proxy` 切换为 `migrate`
  - source/owner 切换为 `agent_test_rust` + `backend/src/routes/agent_test.rs`
  - 汇总计数更新为 `migrate=136`、`proxy=16`，task-group `proxy=3`
- 后续修复波次: Wave A task route retirement
- owner: Rust migration

### 20. static-tasks-cache endpoint surface retired from Python static tasks router

- endpoint / feature: `/api/v1/static-tasks/cache/*`
- Python 旧行为:
  - `backend_old/app/api/v1/endpoints/static_tasks.py` 通过 `_cache` include/re-export 暴露 static-tasks-cache endpoint
  - `backend_old/app/api/v1/endpoints/static_tasks_cache.py` 承载 cache stats/cleanup/clear route surface
- Rust 当前行为:
  - `backend/src/routes/static_tasks.rs` 已提供 Rust-owned `/api/v1/static-tasks/cache/*`
  - Python `static_tasks.py` 已移除 `_cache` import、`router.include_router(_cache.router)`、`get_repo_cache_stats/cleanup_unused_cache/clear_all_cache` re-export
  - `backend_old/app/api/v1/endpoints/static_tasks_cache.py` 已删除
- inventory 更新:
  - `python-endpoints-inventory.csv` 中 `/api/v1/static-tasks/cache/*` 全部由 `proxy` 切换为 `migrate`
  - source/owner 切换为 `static_tasks_rust` + `backend/src/routes/static_tasks.rs`
- 汇总计数更新为 `migrate=139`、`proxy=13`，task-group `proxy=0`
- 后续修复波次: Wave A static tasks cache retirement
- owner: Rust migration

### 21. agent-task-reporting endpoint surface retired from Python agent tasks router

- endpoint / feature: `/api/v1/agent-tasks/{task_id}/report`, `/api/v1/agent-tasks/{task_id}/findings/{finding_id}/report`
- Python 旧行为:
  - `backend_old/app/api/v1/endpoints/agent_tasks.py` 通过 `agent_tasks_reporting` 暴露 report export route
  - `backend_old/app/api/v1/endpoints/agent_tasks_reporting.py` 承载 task report 与 finding report 导出逻辑
- Rust 当前行为:
  - `backend/src/routes/agent_tasks.rs` 已接管 task/finding report export，并支持 `format`、`include_code_snippets`、`include_remediation`、`include_metadata`、`compact_mode`
  - Rust 导出提供 project-based 下载文件名，同时包含 `filename*` UTF-8 Content-Disposition
  - Python `agent_tasks.py` 已移除 reporting 聚合入口，`agent_tasks_reporting.py` 已删除
- inventory 更新:
  - `python-endpoints-inventory.csv` 新增并登记两条 agent-task report route 为 `migrate`
  - 汇总计数更新为 `migrate=141`、`proxy=13`，task-group `proxy=0`
- 后续修复波次: Wave A task route retirement
- owner: Rust migration

### 12. `backend_old/app/utils` runtime artifacts retired; only offline patch text remains

- endpoint / feature: `backend_old/app/utils/*`, `backend_old/tests/test_date_utils.py`
- Python 旧行为:
  - `backend_old/app/utils/date_utils.py` 提供 date formatting/relative helpers used across Python runtime tests.
  - `backend_old/app/utils/repo_utils.py` 支持 remote repository handling paths。
  - `backend_old/app/utils/security.py` 只是 forwarding wrapper，把 runtime JWT/bcrypt/encryption 责任再转给 core。
- Rust 当前行为:
  - Rust `backend/src/core/date_utils` 直接替代了 Python date helper，`backend_old/tests/test_date_utils.py` 已从 repo 中删除。
  - `repo_utils` 被 retiroed，因为当前架构没有 live remote repository handling entry point。
  - `utils/security` forwarding wrapper 已 retire，核心安全逻辑完全由 Rust `backend/src/core/security.rs` / `backend/src/core/encryption.rs` 担当。
  - `backend_old/app/utils` 目录已从 live runtime 中删掉；唯一包含 `app.utils` 字符的产物是离线扫描规则补丁资产 `backend/assets/scan_rule_assets/patches/vuln-halo-d59877a9.patch`，那只是静态文本替换，不是 runtime 依赖。
- 是否影响前端: 否；Rust backend 已接管相关 helper，Python runtime 不再运行这些代码。
- 后续修复波次: Wave A 后续 / Wave F retire cleanup
- owner: Rust migration
- delete gate:
  - 运行时已确认无 `backend_old/app/utils` 依赖，剩余的 `app.utils` 文本只是 offline patch asset，不构成 run-time breakage。

### 13. `backend_old/app/schemas` package retired; only API-local DTO pod remains

- endpoint / feature: Python schema definition bundle (`backend_old/app/schemas/*`)
- Python 旧行为: schema module 集中提供 `search/token/user/audit_rule/prompt_template` 等 DTO definitions 供 Python runtime/endpoint 共享。
- Rust 当前行为:
  - `backend_old/app/schemas` package 已从 live tree 中移除；`search`、`token`、`user`、`audit_rule`、`prompt_template` 以及 legacy `opengrep/gitleaks` schema set 都已 retired。
  - 当前还需要暴露的 rule-flow DTOs 暂存于 `backend_old/app/api/v1/schemas/rule_flows.py`，保持 endpoint-local/API-local 过渡契约。
  - 这不意味着 `static-tasks` 已经完全 Rust-owned；static-tasks runtime 仍翻到 Python bridge，schema cleanup 只是记录 ownership shrinkage。
  - operational verification: `find backend_old/app -type d -name schemas -print | sort`
  - expected output: 仅 `backend_old/app/api/v1/schemas`，证明 `backend_old/app/schemas` 不在 live tree。
- 是否影响前端: 否；schema cleanup 只影响迁移 ledger，不改变 HTTP contract。
- 后续修复波次: Wave A 后续 / API surface cleanup
- owner: Rust migration
- delete gate:
  - rule-flow DTOs 完全迁入 Rust 或 transitional package 被删除之后，重新执行 `find backend_old/app -type d -name schemas -print | sort` 可确认是否 safe to drop。

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

### 6. Rust startup bootstrap shell is now owned, and Python startup internals are being retired

- endpoint / feature: `backend/src/bootstrap/mod.rs`, `/health`, Rust server startup path
- Python 旧行为: Python `app.main` 曾在 lifespan 内负责 schema version check、`init_db()`、中断任务恢复、runner preflight
- Rust 当前行为: Rust 启动前已经执行 bootstrap，负责文件存储根检查、DB 可用性检查、Rust 自身依赖表检查，并接管 startup init / recovery / runner preflight 的 orchestration，同时把状态暴露到 `/health`
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
  - `static_scan_runtime.py`
  - `agent_test.py`
  - `static_tasks_opengrep_rules.py`
    已改为从 service 层读取 effective user config，不再反向 import `app.api.v1.endpoints.config`
- Rust 当前行为补充: Python live router 已不再挂载 `/config`，live 配置入口默认收敛到 Rust `/system-config`
- Rust 当前行为补充: `config.py` 已物理删除，`/config` 旧 Python endpoint 完整退场
- Rust 当前行为补充: 与 `config.py` 强绑定、且不再承担 bridge 职责的旧 service / 测试也已删除：
  - `backend_old/app/services/llm_provider_service.py`
  - `backend_old/app/services/llm_config_runtime_service.py`
  - `backend_old/tests/test_llm_provider_catalog_and_aliases.py`
  - `backend_old/tests/test_llm_strict_config.py`
  - `backend_old/tests/test_config_mcp_backend_owned.py`
  - `backend_old/tests/test_chinese_only_config.py`
  - `backend_old/tests/test_legacy_cleanup.py`
- Rust 当前行为补充: 保留的 `backend_old/app/services/user_config_service.py` 与 `backend_old/app/services/project_test_service.py` 仍有 Python 运行时调用，属于过渡期 service，不属于 dead code
- Rust 当前行为补充: 新增/保留回归测试：
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- Rust 当前行为补充: Python live router 已不再挂载 `/prompts` 与 `/rules`
- Rust 当前行为补充: `prompts.py` 与 `rules.py` 已物理删除，旧模板/审计规则 live endpoint 完整退场
- Rust 当前行为补充: 已新增 `backend/src/bootstrap/legacy_mirror_schema.rs`，在 DB 模式下由 Rust startup init 兜底创建当前 Rust-owned bridge 所依赖的 legacy mirror 表
- Rust 当前行为补充: 当前由 Rust schema 兜底的 legacy mirror 表包括：
  - `users`
  - `user_configs`
  - `projects`
  - `project_info`
  - `project_management_metrics`
  - `prompt_skills`
- Rust 当前行为补充: 这意味着 `backend_old/alembic` 对当前 Rust 已 owned 控制面桥接表不再是唯一 schema 来源，但整个 Alembic 目录仍未到可删除状态
- 是否影响前端: 否，前端应继续走 Rust backend；这一步只是缩小 Python live surface
- 后续修复波次: Wave A 后续 / API surface cleanup
- owner: Rust migration

### 9. Rust now owns core security/encryption primitives and part of core config defaults

- endpoint / feature: `backend/src/core/security.rs`, `backend/src/core/encryption.rs`, `backend/src/config.rs`, `/api/v1/system-config/*`
- Python 旧行为:
  - `backend_old/app/core/security.py` 负责 JWT access token、bcrypt hash/verify
  - `backend_old/app/core/encryption.py` 负责基于 `SECRET_KEY` 派生 Fernet 密钥，对敏感 LLM key 字段加解密
  - `backend_old/app/core/config.py` 负责 Python runtime 的 core 级环境配置
- Rust 当前行为:
  - Rust 已新增自己的 JWT / bcrypt 原语
  - Rust 已新增自己的 Fernet-compatible 加解密原语
  - Rust `AppConfig` 已开始承接 secret/token、LLM 默认值、workspace/cache/path、flow/function-locator 等 core 配置
  - Rust `/api/v1/system-config/defaults` 已从 `AppConfig` 生成默认值
  - Rust 向 legacy `user_configs` 做 shadow write 时，敏感字段已按 Rust 加密逻辑落密文
- 对应 Python 哪些执行入口已删除:
  - 本次没有删除 `backend_old/app/core/config.py`
  - 本次没有删除 `backend_old/app/core/security.py`
  - 本次没有删除 `backend_old/app/core/encryption.py`
- 仍然只是 bridge 的 Python 代码:
  - `backend_old/app/db/session.py`
  - `backend_old/app/services/user_config_service.py`
  - `backend_old/app/services/llm/*`
  - `backend_old/app/services/agent/*`
  - `backend_old/app/services/*runner*`
  - 多个 `static-tasks` / `agent-tasks` Python 端点
- 是否影响前端: 否，`/api/v1/system-config/*` 契约保持可用，默认值来源更集中
- 后续修复波次: Wave A 后续 / Phase A core 收口
- owner: Rust migration

### 10. Python db asset readers now point at Rust-owned scan_rule_assets root

- endpoint / feature: `backend_old/app/db/*` asset readers, `backend/assets/scan_rule_assets/*`
- Python 旧行为:
  - Python `gitleaks_rules_seed.py`、`bandit_rules_snapshot.py`、`pmd_rulesets.py`
    直接从 `backend_old/app/db/*` 读取 builtin rules、patch rules、patch artifacts、PMD XML 等资产
- Rust 当前行为:
  - Rust 已经把下列资产作为 rule store/source of truth 实际消费：
    - `rules_opengrep`
    - `rules_from_patches`
    - `patches`
    - `gitleaks_builtin`
    - `bandit_builtin`
    - `rules_pmd`
  - Python 现已通过 `backend_old/app/db/__init__.py` helper 优先读取 `backend/assets/scan_rule_assets/*`
- 对应 Python 哪些执行入口已删除:
  - 已删除重复资产目录：
    - `backend_old/app/db/rules`
    - `backend_old/app/db/rules_from_patches`
    - `backend_old/app/db/patches`
    - `backend_old/app/db/gitleaks_builtin`
    - `backend_old/app/db/bandit_builtin`
    - `backend_old/app/db/rules_pmd`
- 仍然只是 bridge 的 Python 代码:
  - `backend_old/app/services/gitleaks_rules_seed.py`
  - `backend_old/app/services/bandit_rules_snapshot.py`
  - `backend_old/app/services/pmd_rulesets.py`
  - `backend_old/app/db/rules_phpstan`
  - `backend_old/app/db/yasa_builtin`
  - `backend_old/app/db/schema_snapshots/*`
  - `backend_old/app/db/base.py`
  - `backend_old/app/db/session.py`
  - 路径归一化 helper已转至 `backend_old/app/services/scan_path_utils.py`，旧 `static_finding_paths.py` 不再 live
- 是否影响前端: 否，Python static-tasks / seed / rules 页继续可用，只是资产根收敛到 Rust owner root
- 后续修复波次: Wave A 后续 / Phase A-C db asset cleanup
- owner: Rust migration

### backend_old/app/db 迁移清单

- Rust 要接管并最终删掉 `backend_old/app/db`，必须依序通过下列八个门。第 1、2 项的 Rust 侧实现已完成，但本目录仍被 live Python 模块 import，因此还不能删除。
- 1. 环境/配置 DB 拆分（已完成）：Rust 与 Python DB env/config plumbing 已分离，`PYTHON_DB_*` 与 `PYTHON_ALEMBIC_ENABLED` 仅留给 Python runtime，Rust `AppConfig`/`bootstrap` 直接读 `DATABASE_URL` 并自行检查 schema。
- 2. 启动/迁移/健康分离（已完成）：Rust `bootstrap` 负责 startup preflight、legacy schema 校验与 `/health` 报告，Python 只服务尚未迁出的 runtime 功能，确认 Rust 的健康态覆盖这部分即可认定该门已过。
- 3. 替换 `app.db.base` ownership：验证命令是 `rg -n "from app\\.db\\.base import Base|from app\\.db\\.base import|app\\.db\\.base" backend_old/alembic backend_old/app backend_old/tests`。当前 blocker 是 `backend_old/alembic/env.py`、`backend_old/tests/conftest.py` 和 `backend_old/app/models/*`。翻门条件是这些命中清零或只剩待删历史文件；owner 是 Rust migration Phase A/B。
- 4. 替换 `app.db.session` 调用者：验证命令是 `rg -n "from app\\.db\\.session import|app\\.db\\.session import|get_db|AsyncSessionLocal|async_session_factory" backend_old/app backend_old/tests backend_old/scripts`。当前 blocker 已清零，说明 live Python 路径已不再依赖 `app.db.session`；后续只需继续用退休守门测试和 Rust 合同测试守住该状态；owner 是 Rust migration Phase A/D。
- 5. `init_db` 语义迁入 Rust：验证命令是 `rg -n "from app\\.db\\.init_db|import init_db|init_db\\(" backend_old/app backend_old/tests backend_old/scripts`。当前 blocker 已清零，说明 demo user、seed project、legacy rule seed、schema bootstrap 不再依赖 Python `init_db.py`；后续只需继续用 Rust bootstrap/preflight 合同测试守住该语义；owner 是 Rust migration Phase A。
- 6. 路径归一化 helper迁新家：验证命令是 `rg -n "scan_path_utils|normalize_scan_file_path|resolve_scan_finding_location" backend_old/app backend_old/tests`。当前 blocker 是 `agent_tasks_bootstrap.py`、`app/services/agent/bootstrap/phpstan.py`、`bandit.py`、`opengrep.py` 和 `tests/test_scan_path_utils.py`，它们都该 import `backend_old/app/services/scan_path_utils.py`；旧 `static_finding_paths.py` 不再命中；owner 是 Rust migration Phase C/D。
- 7. Alembic/schema_snapshots 移除门：验证命令是 `rg -n "schema_snapshots|baseline_5b0f3c9a6d7e|normalize_static_finding_paths" backend_old/alembic backend_old/tests`。当前 blocker 是 `backend_old/alembic/versions/5b0f3c9a6d7e_squashed_baseline.py`、`backend_old/alembic/versions/7f8e9d0c1b2a_normalize_static_finding_paths.py`、`backend_old/tests/test_alembic_project.py`。翻门条件是 Rust 完成 legacy baseline/schema compatibility 替代，命令不再命中 `schema_snapshots/*` 或 static-finding normalization 迁移，测试改写或删除；owner 是 Rust migration legacy-schema owner。
- 8. backend_old/app/db 最终删除门：验证命令依次是 `rg -n "app\\.db\\." backend_old/app backend_old/tests backend_old/alembic backend_old/scripts` 与 `rg --files backend_old/app/db`。当前 blocker 仍包括 `static_scan_runtime.py`、`agent_tasks_bootstrap.py`（执行/mixed-test helper 残留，scope filtering、bootstrap policy、bootstrap findings、Bandit bootstrap rule 选择、bootstrap seeds、bootstrap entrypoint fallback、Gitleaks bootstrap runtime 已迁入 `backend_old/app/services/agent/{scope_filters,bootstrap_policy,bootstrap_findings,bandit_bootstrap_rules,bootstrap_seeds,bootstrap_entrypoints,bootstrap_gitleaks_runner}.py`）、`backend_old/alembic/env.py` 和相关测试。翻门条件是第一条命令在 live 路径清零，第二条命令不再列出 live 模块，并且 Rust-only startup smoke/health 通过；owner 是整个 Rust migration owner。
- 当前现状：`backend_old/app/db` 仍被 static/agent services、部分 FastAPI endpoints、测试等活跃路径 import，delete gate 还没打开。

### 11. phpstan db assets are now Rust-owned; YASA retirement has started but is not finished

- endpoint / feature: `rules_phpstan/*`, Rust `scan/phpstan`, YASA db/runtime retirement
- Python 旧行为:
  - Python static-tasks/phpstan 完全从 `backend_old/app/db/rules_phpstan` 读取 snapshot 与源码目录
  - YASA 仍有独立 db asset、模型、service、launcher、route 与 bootstrap 链路
- Rust 当前行为:
  - Rust 已新增 `backend/src/scan/phpstan.rs` 并实际消费 `rules_phpstan/*`
  - Rust `phpstan` preflight 已使用 materialized snapshot + `rule_sources/`
  - `backend_old/app/db/rules_phpstan` 已删除，Python 继续读 Rust 资产根
- 对应 Python 哪些执行入口已删除:
  - `backend_old/app/db/rules_phpstan/*`
  - 已从聚合入口移除 YASA 的导出/聚合依赖：
    - `backend_old/app/services/agent/bootstrap/__init__.py`
  - 已从模型聚合导出与项目关系中移除 YASA 依赖：
    - `backend_old/app/models/__init__.py`
    - `backend_old/app/models/project.py`
  - 已删除 YASA DB / service / launcher / route 主体：
    - `backend_old/app/api/v1/endpoints/static_tasks_yasa.py`
    - `backend_old/app/models/yasa.py`
    - `backend_old/app/services/yasa_runtime.py`
    - `backend_old/app/services/yasa_runtime_config.py`
    - `backend_old/app/services/yasa_rules_snapshot.py`
    - `backend_old/app/services/yasa_language.py`
    - `backend_old/app/db/yasa_builtin/yasa_rules_snapshot.json`
    - `backend_old/app/runtime/launchers/yasa_*`
- 仍然只是 bridge / 未完成清理的 YASA 代码:
  - `backend_old/app/api/v1/endpoints/agent_tasks_bootstrap.py` 的 mixed tests 对应残留
- frontend 本轮已完成去 YASA：
  - `CreateScanTaskDialog` / `CreateProjectScanDialog` / `StaticEngineConfigDialog` 不再暴露 YASA
  - `FindingDetail`、`taskActivities`、`projectCardPreview`、`static-analysis` 聚合口径已移除 `Yasa*` 与 `tool=yasa`
  - 相关前端与 mixed-table 测试已改为无 YASA 口径
- 是否影响前端: phpstan 不受影响；YASA 前端 live path 已退净，剩余是 mixed tests / inventory / 文本文档收尾
- 后续修复波次: Wave A 后续 / YASA residual cleanup
- owner: Rust migration

### 12. `backend_old/app/utils` retirement must be verified as runtime-clean, not text-clean

- endpoint / feature: `backend_old/app/utils/*`, `backend_old/tests/test_date_utils.py`, offline patch residue under `backend/assets/scan_rule_assets/patches`
- Python 旧行为:
  - `backend_old/app/utils/date_utils.py` 提供 date helper
  - `repo_utils.py` 承接 remote repository handling
  - `utils/security.py` 只是 security forwarding wrapper
- Rust 当前行为:
  - Rust `backend/src/core/date_utils` 已替代 date helper 行为，`backend_old/tests/test_date_utils.py` 已删除
  - `repo_utils` 已 retire，因为 remote repository handling 不再有 live runtime 入口
  - `utils/security` forwarding wrapper 已 retire，核心安全逻辑由 Rust `backend/src/core/security.rs` / `backend/src/core/encryption.rs` 承接
  - `backend_old/app/utils` 整个目录已不在 live Python runtime 中
- operational verification:
  - `rg -n "app\\.utils|repo_utils|app\\.utils\\.security" backend_old/app backend_old/tests backend/src backend/assets/scan_rule_assets/patches`
  - 预期结果是 `backend_old/app`、`backend_old/tests`、`backend/src` 三类 live runtime/test 路径没有任何命中
  - 唯一允许剩下的命中是离线 patch 资产 `backend/assets/scan_rule_assets/patches/vuln-halo-d59877a9.patch`
- runtime vs offline distinction:
  - 上述 patch 文件只是离线扫描规则文本，不是运行时 import、module 依赖或测试依赖
  - 所以它属于文本文档/资产残留，不属于 runtime blocker
- 后续修复波次: Wave F / retire cleanup
- owner: Rust migration
- offline residue cleanup owner:
  - 如果未来要清掉这条 patch 文本残留，由 Rust migration owner 在 Wave F / retire cleanup 处理

### 13. `backend_old/app/runtime` removed; Rust entrypoints own startup/launcher surface

- endpoint / feature: `backend_old/app/runtime/*`, backend-py image startup, opengrep/phpstan runner launchers
- Python 旧行为:
  - `app.runtime.container_startup` 负责 backend-py 容器启动前的 env/bootstrap、uv sync、DB wait、migration、reset、uvicorn exec
  - `app.runtime.launchers.opengrep_launcher` / `phpstan_launcher` 负责 runner wrapper
- Rust 当前行为:
  - Rust 已新增：
    - `backend/src/runtime/bootstrap.rs`
    - `backend/src/bin/backend_runtime_startup.rs`
    - `backend/src/bin/opengrep_launcher.rs`
    - `backend/src/bin/phpstan_launcher.rs`
  - `docker/backend_old.Dockerfile` 与 `scripts/release-templates/backend.Dockerfile`
    已改用 `/usr/local/bin/backend-runtime-startup`
  - `docker/opengrep-runner.Dockerfile` 与 `docker/phpstan-runner.Dockerfile`
    已改用 Rust launcher binaries
  - `backend_old/tests/test_backend_container_startup_env_bootstrap.py` 已删除，Rust 测试 `backend/tests/runtime_env_bootstrap.rs` 接管
  - `backend_old/app/runtime` 目录已物理删除
- operational verification:
  - `find backend_old/app -type d -name runtime -print`
  - `rg -n "app\\.runtime\\.|from app\\.runtime|import app\\.runtime|container_startup\\.py|opengrep_launcher\\.py|phpstan_launcher\\.py" backend_old backend docker scripts .github`
  - expected state:
    - `backend_old/app/runtime` 不再存在
    - live runtime / Dockerfile / tests 不再引用旧 Python runtime 路径
- 边界说明:
  - 这是 `app/runtime` 目录退役，不是 Phase D 全量完成
  - `scanner*`、`flow_parser*` 和其它 runtime/service 链路仍在 Python 侧
- 后续修复波次: Wave D / runtime orchestration cleanup
- owner: Rust migration

### 14. Ledger refresh: Rust task routes are mounted, compose bridge vars are cleared

- endpoint / feature:
  - Rust: `/api/v1/agent-tasks/*`, `/api/v1/agent-test/*`, `/api/v1/static-tasks/*`
  - Deploy chain gate set: `backend-py`, `PYTHON_UPSTREAM_BASE_URL`
- 仓库事实:
  - `backend/src/routes/mod.rs` 已 `nest` 三个 task 路由组
  - `backend/src/proxy.rs` 不存在，Rust gateway 未保留 Python catch-all proxy 文件入口
  - `backend/src/app.rs` fallback 是 `404 route not owned by rust gateway`，不是转发 upstream
  - `rg -n "backend-py|PYTHON_UPSTREAM_BASE_URL" docker-compose*.yml -S` 无命中（exit code 1）
- inventory 刷新:
  - `python-endpoints-inventory.csv` 当前总量 `179`
  - 分类：`proxy=114`、`migrate=38`、`retire=20`、`defer=7`
  - `backend_old` 根目录 Python: `4`
  - `backend_old/app` 非 API Python: `226`
- 是否影响前端:
  - 当前不阻断主路径，compose 变量层已满足 Rust backend bridge 清零；后续关键风险在 Python runtime live surface
- 新 gate:
  - default/hybrid/full compose 渲染结果中必须不存在 `backend-py`
  - default/hybrid/full compose 渲染结果中必须不存在 `PYTHON_UPSTREAM_BASE_URL`
  - `rg -n "backend-py|PYTHON_UPSTREAM_BASE_URL|proxy\\.rs" docker-compose*.yml backend/src -S` 不得出现 Python backend bridge 命中
- 后续修复波次: Wave B+（deploy chain cleanup）
- owner: Rust migration

### 15. project file-content cache is Rust-owned; `zip_cache_manager.py` is retired

- endpoint / feature:
  - Rust: `GET /api/v1/projects/{id}/files/{*file_path}`
  - Rust: `GET /api/v1/projects/cache/stats`
  - Rust: `POST /api/v1/projects/cache/clear`
  - Rust: `POST /api/v1/projects/{id}/cache/invalidate`
  - Python retired service: `backend_old/app/services/zip_cache_manager.py`
- Python 旧行为:
  - `zip_cache_manager.py` 提供 TTL / LRU / memory limit / stats / invalidate / clear
  - `backend_old/tests/test_zip_cache_manager.py` 覆盖 expired prune 与 expired-on-read
- Rust 当前行为:
  - 新增 `backend/src/project_file_cache.rs`
  - `backend/src/state.rs` 已挂载全局 `project_file_cache`
  - `backend/src/routes/projects.rs` 不再返回固定 cache 占位值：
    - file content 第二次读取会命中 cache 并返回 `is_cached=true`
    - cache stats / clear / invalidate 现在会返回真实条目统计
    - archive 更新与删除会主动失效项目缓存
  - `backend/tests/projects_api.rs` 已从“只看 200”提升为断言真实 cache 行为
  - `backend_old/app/services/zip_cache_manager.py` 已删除
  - `backend_old/tests/test_zip_cache_manager.py` 已删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `4`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `229`
  - `rg -n "zip_cache_manager|ZipCacheManager" backend/src backend_old/app backend_old/tests -S`
    只剩退休守门测试命中
  - `cargo test --manifest-path backend/Cargo.toml --test projects_api projects_domain_endpoints_cover_files_stats_and_transfer -- --exact`
    当前因本机 `rustc 1.85.0` 低于 lockfile 依赖要求而失败；这是 toolchain gate，不是本 slice
- 是否影响前端:
  - 前端当前没有 active caller 依赖 `projects` cache 管理 endpoint 的旧占位行为
  - `is_cached` 字段继续保留，代码浏览器 file-content contract 不受破坏
  - frontend upload contract 仍允许非 zip archive，这一块不在本 slice 内处理
- 边界说明:
  - 本次退休的是 `zip_cache_manager.py`，不是整个 upload/archive shared bridge
  - `zip_storage.py`、`upload/project_stats.py`、`static_scan_runtime.py` 仍依赖 ZIP 文件根 / bridge 语义，不能跟着一起删
- 后续修复波次: Wave C / project archive shared services
- owner: Rust migration

### 16. root diagnostics retired; `backend_old` root keeps only `main.py`

- endpoint / feature:
  - Python root diagnostics:
    - `backend_old/verify_llm.py`
    - `backend_old/check_docker_direct.py`
    - `backend_old/check_sandbox.py`
- Python 旧行为:
  - 三者都只是开发/诊断脚本，不承接 HTTP surface、runtime bootstrap 或 compose 主链路
- Rust 当前行为:
  - 这些 root diagnostics 已从 repo 物理删除
  - `backend_old/tests/test_legacy_backend_main_retired.py`
    已补 root diagnostics 退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `1`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `229`
  - `rg -n "verify_llm.py|check_docker_direct.py|check_sandbox.py" backend_old plan backend docker scripts .github -S`
    只剩退休守门测试与迁移文档命中
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖这些脚本
- 边界说明:
  - 这一步只退休 root diagnostics，不代表 `backend_old/main.py` 已可删除
  - root Python live surface 现在只剩 `backend_old/main.py`
- 后续修复波次: Wave F / root bootstrap cleanup
- owner: Rust migration

### 13. `backend_old/app/runtime` removed; Rust entrypoints own startup/launcher surface

- endpoint / feature: `backend_old/app/runtime/*`, backend-py image startup, opengrep/phpstan runner launchers
- Python 旧行为:
  - `app.runtime.container_startup` 负责 backend-py 容器启动前的 env/bootstrap、uv sync、DB wait、migration、reset、uvicorn exec
  - `app.runtime.launchers.opengrep_launcher` / `phpstan_launcher` 负责 runner wrapper
- Rust 当前行为:
  - Rust 已新增：
    - `backend/src/runtime/bootstrap.rs`
    - `backend/src/bin/backend_runtime_startup.rs`
    - `backend/src/bin/opengrep_launcher.rs`
    - `backend/src/bin/phpstan_launcher.rs`
  - `docker/backend_old.Dockerfile` 与 `scripts/release-templates/backend.Dockerfile`
    已改用 `/usr/local/bin/backend-runtime-startup`
  - `docker/opengrep-runner.Dockerfile` 与 `docker/phpstan-runner.Dockerfile`
    已改用 Rust launcher binaries
  - `backend_old/tests/test_backend_container_startup_env_bootstrap.py` 已删除，Rust 测试 `backend/tests/runtime_env_bootstrap.rs` 接管
  - `backend_old/app/runtime` 目录已物理删除
- operational verification:
  - `find backend_old/app -type d -name runtime -print`
  - `rg -n "app\\.runtime\\.|from app\\.runtime|import app\\.runtime|container_startup\\.py|opengrep_launcher\\.py|phpstan_launcher\\.py" backend_old backend docker scripts .github`
  - expected state:
    - `backend_old/app/runtime` 不再存在
    - live runtime / Dockerfile / tests 不再引用旧 Python runtime 路径
- 边界说明:
  - 这是 `app/runtime` 目录退役，不是 Phase D 全量完成
  - `scanner*`、`flow_parser*` 和其它 runtime/service 链路仍在 Python 侧
- 后续修复波次: Wave D / runtime orchestration cleanup
- owner: Rust migration
