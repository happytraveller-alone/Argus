# Wave A Log

## Completed in this turn

- `business_logic` Python runtime cluster 已退役：
  - `backend_old/app/services/agent/business_logic_risk_queue.py`、`agents/business_logic_recon.py`、`agents/business_logic_analysis.py`、`tools/business_logic_recon_queue_tools.py` 已删除
  - 新增 `backend_old/tests/test_business_logic_runtime_retired.py` guard
  - `backend_old/tests/test_queue_tool_duplicate_semantics.py` 收缩为只覆盖 recon queue 幂等语义
  - `backend_old/tests/test_agent_prompt_contracts.py` 已移除 retired business-logic agents 的 prompt 合同断言
  - Rust `backend/tests/task_routes_api.rs` 已补 business-logic `queue_snapshot` contract 覆盖
  - `backend_old/app` runtime core 计数 `137 -> 133`
  - `agent orchestration / state / payload` 计数 `24 -> 22`
  - `scanner / bootstrap / queue / workspace / tracking` 计数 `5 -> 4`
  - `tools / tool_runtime` 计数 `27 -> 26`
- `scan_tracking.py` 已退役：
  - `backend_old/app/services/agent/scan_tracking.py` 已删除
  - 新增 `backend_old/tests/test_scan_tracking_retired.py` guard
  - `backend_old/tests/test_static_scan_runtime.py` 与 `backend_old/tests/test_background_task_launch_refactor.py` 已删除
  - `backend_old/app` runtime core 计数 `138 -> 137`
  - `scanner / bootstrap / queue / workspace / tracking` 计数 `6 -> 5`
- `scan_workspace.py` 已退役：
  - `backend_old/app/services/agent/scan_workspace.py` 已删除
  - 新增 `backend_old/tests/test_scan_workspace_retired.py` guard
  - `backend_old/tests/test_static_scan_runtime.py` 收缩为只覆盖 `scan_tracking` shared helper 契约
  - `backend_old/app` runtime core 计数 `139 -> 138`
  - `scanner / bootstrap / queue / workspace / tracking` 计数 `7 -> 6`
- `bootstrap/base.py` / `bootstrap/opengrep.py` 已退役：
  - `backend_old/app/services/agent/bootstrap/base.py` 与 `bootstrap/opengrep.py` 已删除
  - 新增 `backend_old/tests/test_opengrep_bootstrap_helpers_retired.py` guard
  - `backend_old/app` runtime core 计数 `141 -> 139`
  - `scanner / bootstrap / queue / workspace / tracking` 计数 `9 -> 7`
- `bootstrap_findings.py` 已退役：
  - `backend_old/app/services/agent/bootstrap_findings.py` 已删除
  - 新增 `backend_old/tests/test_bootstrap_findings_retired.py` guard
  - `backend_old/app` runtime core 计数 `142 -> 141`
  - `scanner / bootstrap / queue / workspace / tracking` 计数 `10 -> 9`
- `bootstrap_entrypoints.py` / `bootstrap_seeds.py` 已退役：
  - `backend_old/app/services/agent/bootstrap_entrypoints.py` 与 `bootstrap_seeds.py` 已删除
  - 新增 `backend_old/tests/test_bootstrap_entrypoint_helpers_retired.py` guard
  - `backend_old/app` runtime core 计数 `144 -> 142`
  - `scanner / bootstrap / queue / workspace / tracking` 计数 `12 -> 10`
- `bootstrap_policy.py` 已退役：
  - `backend_old/app/services/agent/bootstrap_policy.py` 已删除
  - 新增 `backend_old/tests/test_bootstrap_policy_retired.py` guard
  - `backend_old/app` runtime core 计数 `145 -> 144`
  - `scanner / bootstrap / queue / workspace / tracking` 计数 `13 -> 12`
- `pmd` 已按 `opengrep-only` 方针退役：
  - Rust `static-tasks` / preflight / recovery / `scan::pmd` 不再保留 `pmd` route/runtime
  - Python `pmd.py`、`pmd_scan.py`、`pmd_rulesets.py`、`PMDTool` 已删除
  - 新增 `backend_old/tests/test_pmd_engine_retired.py` guard
  - `backend_old/app` runtime core 计数 `148 -> 145`
  - `models / persistence mirror` 计数 `14 -> 12`
  - `shared helpers` 计数 `4 -> 3`
- `phpstan` 已按 `opengrep-only` 方针退役：
  - Rust `static-tasks` / preflight / recovery 不再保留 `phpstan` route/runtime
  - Python `phpstan.py`、`bootstrap/phpstan.py`、`PHPStanTool` 已删除
  - 新增 `backend_old/tests/test_phpstan_engine_retired.py` guard
  - `backend_old/app` runtime core 计数 `150 -> 148`
  - `models / persistence mirror` 计数 `15 -> 14`
  - `scanner / bootstrap / queue / workspace / tracking` 计数 `14 -> 13`
- `gitleaks` 已按 `opengrep-only` 方针退役：
  - Rust `static-tasks` / preflight / recovery 不再保留 `gitleaks` route/runtime
  - Python `gitleaks.py`、`bootstrap_gitleaks_runner.py`、`GitleaksTool` 及其专用 helper 已删除
  - 新增 `backend_old/tests/test_gitleaks_engine_retired.py` guard
  - `backend_old/app` runtime core 计数 `152 -> 150`
  - `models / persistence mirror` 计数 `16 -> 15`
  - `scanner / bootstrap / queue / workspace / tracking` 计数 `15 -> 14`
- `bandit` 已按 `opengrep-only` 方针退役：
  - Rust `static-tasks` / preflight 不再保留 `bandit` route/runtime
  - Python `bandit.py`、`bandit_rules_snapshot.py`、`bandit_bootstrap_rules.py`、`bootstrap/bandit.py` 已删除
  - 新增 `backend/tests/opengrep_only_static_tasks.rs` 与 `backend_old/tests/test_bandit_engine_retired.py` guard
  - `backend_old/app` runtime core 计数 `156 -> 152`
  - `models / persistence mirror` 计数 `17 -> 16`
  - `shared helpers` 计数 `5 -> 4`
  - `scanner / bootstrap / queue / workspace / tracking` 计数 `17 -> 15`
- `backend_old/app/services/git_mirror.py` 已退役：
  - mirror candidate 逻辑已内联到 `llm_rule/git_manager.py`
  - 新增 `backend_old/tests/test_git_mirror_retired.py` guard
  - `backend_old/app` runtime core 计数 `157 -> 156`
  - `shared helpers` 计数 `6 -> 5`
- `backend_old/app/services/rule_contracts.py` 已退役：
  - `OpengrepRuleCreateRequest` 已内联到 `rule.py`
  - 新增 `backend_old/tests/test_rule_contracts_retired.py` guard
  - `backend_old/app` runtime core 计数 `158 -> 157`
  - `shared helpers` 计数 `7 -> 6`
- `backend_old/app/__init__.py`、`backend_old/app/db/schema_snapshots/__init__.py`、`backend_old/app/services/agent/core/flow/lightweight/__init__.py`、`backend_old/app/services/llm/adapters/__init__.py` 已退役：
  - `llm.factory` 与 `test_llm_stream_empty_handling.py` 改为 direct-module imports
  - 新增 `backend_old/tests/test_namespace_package_shells_retired.py` guard
  - `backend_old/app` runtime core 计数 `162 -> 158`
  - `app root / core / config / security` 计数 `4 -> 3`
  - `db / schema snapshot gate` 计数 `2 -> 1`
  - `flow / logic` 计数 `14 -> 13`
  - `llm` 计数 `14 -> 13`
- `backend_old/app/core/__init__.py` 与 `backend_old/app/models/__init__.py` 已退役：
  - Alembic `env.py` 改为显式导入各 model module
  - 新增 `backend_old/tests/test_top_level_package_shells_retired.py` guard
  - `backend_old/app` runtime core 计数 `164 -> 162`
  - `app root / core / config / security` 计数 `5 -> 4`
  - `models / persistence mirror` 计数 `18 -> 17`
- `app.services.agent.flow` live caller 已切到 `app.services.agent.core.flow`，相关 agent/tool/test import 与 monkeypatch target 全部同步
- `backend_old/app/services/llm/__init__.py` 与 `backend_old/app/services/agent/agents/__init__.py` 已退役：
  - 新增 `backend_old/tests/test_service_package_shells_retired.py` guard
  - `backend_old/app` runtime core 计数 `166 -> 164`
  - `agent orchestration / state / payload` 计数 `25 -> 24`
  - `llm` 计数 `15 -> 14`
- `backend_old/app/db/__init__.py` 已退役：
  - `bandit_rules_snapshot.py` 与 `pmd_rulesets.py` 直接读取 Rust-owned `backend/assets/scan_rule_assets/*`
  - 新增 `backend_old/tests/test_db_package_shell_retired.py` guard
  - `db / schema snapshot gate` 计数 `3 -> 2`，`backend_old/app` runtime core 计数 `167 -> 166`
- `backend_old/scripts/package_source_selector.py` 已退役：
  - Rust `backend/src/runtime/bootstrap.rs` 原生接管 PyPI candidate probe / 排序，不再调用 Python selector
  - `backend_old/scripts/dev-entrypoint.sh`、`docker/backend_old.Dockerfile`、`docker/flow-parser-runner.Dockerfile` 改成 shell 内按配置顺序去重选择镜像源
  - 新增 `backend_old/tests/test_package_source_selector_retired.py` guard；`backend_old/scripts` Python 计数 `2 -> 1`
- `wait_correct` 文档树已继续裁剪为最小 raw reference：
  - 保留 `route-inventory/*`、`api-contract/README.md`、`waves/wave-a-log.md`
  - 删除 `behavior-diff/`、`perf/`、`stability/`、`tooling/`、`non-api-python/` 等仅剩模板/占位说明的陈旧文档
  - 删除 `contract-diff-template.md`、`route-inventory-template.csv`、`wave-template.md`
- `rust_full_takeover/archive/skill-runtime/*` 专门 skill-runtime 长计划已删除，相关结论已并入 canonical 文档
- Canonical 迁移文档已重构为 `plan/rust_full_takeover/*` 主索引：
  - 统计口径明确拆成 `backend_old/app` runtime core 与 `alembic / scripts / release preflight` retirement tail
  - `08-remaining-python-function-inventory.md` 改成自洽的功能分组台账
  - frontend / API invariants、retired route consumer debt、operations / readiness gate 已写入 canonical 文档
  - raw ledger 增加“历史快照、非 authoritative”提示
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
  - `backend_old/app/api/v1/api.py` 已从 repo 物理删除；此前残留的空 `APIRouter()` 壳不再保留
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py` 与 `backend_old/tests/test_agent_tasks_module_layout.py` 已改为守住该 router shell 不得回流
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
  - 静态扫描 helper 已先从 `app/api/deps.py` 收口到 service / agent shared modules；后续 `static_scan_runtime.py` 也在单独 slice 中退休
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

### 13. `backend_old/app/schemas` package retired; API-local DTO pod later removed too

- endpoint / feature: Python schema definition bundle (`backend_old/app/schemas/*`)
- Python 旧行为: schema module 集中提供 `search/token/user/audit_rule/prompt_template` 等 DTO definitions 供 Python runtime/endpoint 共享。
- Rust 当前行为:
  - `backend_old/app/schemas` package 已从 live tree 中移除；`search`、`token`、`user`、`audit_rule`、`prompt_template` 以及 legacy `opengrep/gitleaks` schema set 都已 retired。
  - `backend_old/app/api/v1/schemas/rule_flows.py` 后续也已删除，`OpengrepRuleCreateRequest` 改由 `backend_old/app/services/rule_contracts.py` 承接。
  - 这不意味着 `static-tasks` 已经完全 Rust-owned；static-tasks runtime 仍翻到 Python bridge，schema cleanup 只是记录 ownership shrinkage。
  - operational verification: `find backend_old/app -type d -name schemas -print | sort`
  - expected output: 不再出现 live Python schema package；若目录仍存在，也不应再包含 `rule_flows.py` 或 `__init__.py`
- 是否影响前端: 否；schema cleanup 只影响迁移 ledger，不改变 HTTP contract。
- 后续修复波次: Wave A 后续 / API surface cleanup
- owner: Rust migration
- delete gate:
  - `rg -n "app\\.api\\.v1\\.schemas\\.rule_flows|from app\\.api\\.v1\\.schemas import" backend_old/app backend_old/tests backend_old/scripts -S` 为空

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
- Rust 当前行为: project search 已 Rust-owned，agent task/finding search 已接到 Rust task-state 数据；skills 先提供前端主路径所需最小契约，但 custom prompt skills 和 builtin prompt state 仍绑在 Python 旧存储
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
  - 路径归一化 helper已转至 `backend_old/app/services/scan_path_utils.py`，旧 `static_finding_paths.py` 不再 live
- 是否影响前端: 否，Python static-tasks / seed / rules 页继续可用，只是资产根收敛到 Rust owner root
- 后续修复波次: Wave A 后续 / Phase A-C db asset cleanup
- owner: Rust migration

### backend_old/app/db 迁移清单

- Rust 要接管并最终删掉 `backend_old/app/db`，必须依序通过下列八个门。第 1、2 项的 Rust 侧实现已完成，但本目录仍被 live Python 模块 import，因此还不能删除。
- 1. 环境/配置 DB 拆分（已完成）：Rust 与 Python DB env/config plumbing 已分离，`PYTHON_DB_*` 与 `PYTHON_ALEMBIC_ENABLED` 仅留给 Python runtime，Rust `AppConfig`/`bootstrap` 直接读 `DATABASE_URL` 并自行检查 schema。
- 2. 启动/迁移/健康分离（已完成）：Rust `bootstrap` 负责 startup preflight、legacy schema 校验与 `/health` 报告，Python 只服务尚未迁出的 runtime 功能，确认 Rust 的健康态覆盖这部分即可认定该门已过。
- 3. 替换 `app.db.base` ownership（已完成）：验证命令是 `rg -n "from app\\.db\\.base import Base|from app\\.db\\.base import|app\\.db\\.base" backend_old/alembic backend_old/app backend_old/tests`。当前该命令已清零；`Base` 宿主已迁到 `backend_old/app/models/base.py`，`backend_old/app/db/base.py` 已退休；owner 是 Rust migration Phase A/B。
- 4. 替换 `app.db.session` 调用者：验证命令是 `rg -n "from app\\.db\\.session import|app\\.db\\.session import|get_db|AsyncSessionLocal|async_session_factory" backend_old/app backend_old/tests backend_old/scripts`。当前 blocker 已清零，说明 live Python 路径已不再依赖 `app.db.session`；后续只需继续用退休守门测试和 Rust 合同测试守住该状态；owner 是 Rust migration Phase A/D。
- 5. `init_db` 语义迁入 Rust：验证命令是 `rg -n "from app\\.db\\.init_db|import init_db|init_db\\(" backend_old/app backend_old/tests backend_old/scripts`。当前 blocker 已清零，说明 demo user、seed project、legacy rule seed、schema bootstrap 不再依赖 Python `init_db.py`；后续只需继续用 Rust bootstrap/preflight 合同测试守住该语义；owner 是 Rust migration Phase A。
- 6. 路径归一化 helper迁新家：验证命令是 `rg -n "scan_path_utils|normalize_scan_file_path|resolve_scan_finding_location" backend_old/app backend_old/tests`。当前 blocker 是 `agent_tasks_bootstrap.py`、`app/services/agent/bootstrap/phpstan.py`、`bandit.py`、`opengrep.py` 和 `tests/test_scan_path_utils.py`，它们都该 import `backend_old/app/services/scan_path_utils.py`；旧 `static_finding_paths.py` 不再命中；owner 是 Rust migration Phase C/D。
- 7. Alembic/schema_snapshots 移除门：验证命令是 `rg -n "schema_snapshots|baseline_5b0f3c9a6d7e|normalize_static_finding_paths" backend_old/alembic backend_old/tests`。当前 blocker 是 `backend_old/alembic/versions/5b0f3c9a6d7e_squashed_baseline.py`、`backend_old/alembic/versions/7f8e9d0c1b2a_normalize_static_finding_paths.py`、`backend_old/tests/test_alembic_project.py`。翻门条件是 Rust 完成 legacy baseline/schema compatibility 替代，命令不再命中 `schema_snapshots/*` 或 static-finding normalization 迁移，测试改写或删除；owner 是 Rust migration legacy-schema owner。
- 8. backend_old/app/db 最终删除门：验证命令依次是 `rg -n "app\\.db\\." backend_old/app backend_old/tests backend_old/alembic backend_old/scripts` 与 `rg --files backend_old/app/db`。当前 blocker 仍包括 `agent_tasks_bootstrap.py`（执行/mixed-test helper 残留，scope filtering、bootstrap policy、bootstrap findings、Bandit bootstrap rule 选择、bootstrap seeds、bootstrap entrypoint fallback、Gitleaks bootstrap runtime 已迁入 `backend_old/app/services/agent/{scope_filters,bootstrap_policy,bootstrap_findings,bandit_bootstrap_rules,bootstrap_seeds,bootstrap_entrypoints,bootstrap_gitleaks_runner}.py`）、`backend_old/alembic/env.py` 和相关测试。`static_scan_runtime.py` 已在 2026-04-14 的 dead-shell retirement slice 中删除，不再计入当前 blocker。翻门条件是第一条命令在 live 路径清零，第二条命令不再列出 live 模块，并且 Rust-only startup smoke/health 通过；owner 是整个 Rust migration owner。
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

### 44. default `skills` catalog/detail now expose prompt-effective, while external-tools compat remains intact

- endpoint / feature:
  - `GET /api/v1/skills/catalog`
  - `GET /api/v1/skills/{skill_id}`
  - `GET /api/v1/skills/catalog?resource_mode=external_tools`
- Python 旧行为:
  - Python 时代的 prompt skill 逻辑没有 unified prompt-effective catalog/detail surface
  - 当前前端外部工具页仍依赖 builtin/custom prompt resource 语义与 `/skills/resources/*`
- Rust 当前行为:
  - 默认 `skills/catalog` 已返回：
    - scan-core entries
    - `prompt-<agent_key>@effective` unified prompt entries
  - `resource_mode=external_tools` 继续返回前端 compat resource list：
    - scan-core resource
    - `prompt-builtin`
    - `prompt-custom`
  - `skills/{id}` 已支持 prompt-effective detail，并返回：
    - `display_name`
    - `kind=prompt`
    - `source=prompt_effective`
    - `agent_key`
    - `runtime_ready`
    - `reason`
    - `load_mode`
    - `effective_content`
    - `prompt_sources`
  - custom prompt merge 顺序已显式稳定：
    - `created_at` 升序
    - `id` tie-break
  - 默认 unified catalog 中的 prompt-effective entry 不再带可被前端 fallback 误消费的 `tool_type/tool_id`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `213`
  - `cd backend && cargo test --test skills_api`
    => `6 passed`
  - `cd backend && cargo test routes::skills::tests::build_prompt_effective_skill_sorts_custom_prompts_deterministically`
    => `1 passed`
  - `cd backend && cargo build --bin backend-rust`
    => exit `0`
  - `cd backend && cargo test`
    => exit `0`
  - gate hygiene:
    - `backend/tests/projects_api.rs`
      的 multipart helper 已补 quoted-string 转义，避免把带引号的 UTF-8 文件名
      拼成无效 `Content-Disposition` header
    - `cd backend && cargo test --test projects_api download_project_archive_supports_utf8_filenames -- --exact --nocapture`
      => `1 passed`
- 边界说明:
  - 这一步推进的是 Rust `skills` HTTP contract，不是 prompt skill persistence ownership 完成
  - legacy `prompt_skills` 与 `user_configs.other_config.promptSkillBuiltinState`
    仍是当前 DB 模式下的 live 读路径
  - 这一步不改 frontend 页面，不移除 `/skills/resources/*`，也不把 workflow registry / runtime session 带入本 slice
  - 当前 backend 全量 gate 已恢复绿色；后续 slice 可以继续推进
- 后续修复波次:
  - Wave E / prompt-skill persistence boundary
- owner: Rust migration

### 45. prompt-skill persistence boundary moved to Rust-native storage

- endpoint / feature:
  - `GET /api/v1/skills/prompt-skills`
  - `POST /api/v1/skills/prompt-skills`
  - `PUT /api/v1/skills/prompt-skills/{prompt_skill_id}`
  - `DELETE /api/v1/skills/prompt-skills/{prompt_skill_id}`
  - `PUT /api/v1/skills/prompt-skills/builtin/{agent_key}`
  - Rust startup init / bootstrap required tables
- Python 旧行为:
  - Rust `skills` route 虽然已接管 HTTP 面，但 DB mode 读路径仍直接查 legacy
    `prompt_skills`
    与 `user_configs.other_config.promptSkillBuiltinState`
  - mutation 后再额外 mirror 回 legacy，真正的 source of truth 仍在旧表/旧 JSON 字段
- Rust 当前行为:
  - Rust 已新增 `backend/src/db/prompt_skills.rs`
  - Rust DB required tables 新增：
    - `rust_prompt_skills`
    - `rust_prompt_skill_builtin_states`
  - Rust startup init allowlist 新增：
    - `rust_prompt_skill_compat_backfill`
  - startup init 在 Rust-native store 为空时，会做一次 compat backfill：
    - legacy `prompt_skills` -> `rust_prompt_skills`
    - legacy `user_configs.other_config.promptSkillBuiltinState`
      -> `rust_prompt_skill_builtin_states`
    - backfill before import / in-transaction import 都再次检查 empty，避免覆盖已有 Rust-native 数据
  - Rust `skills` route 的 DB mode steady-state 读写已切到 Rust-native store
  - DB mode create / update / delete / builtin toggle 已改为记录级 helper
  - Rust-native 与 legacy mirror 写入已收进单事务，避免主写成功而 mirror 失败造成 split-brain
  - `skills` 分页响应中的 `total` 已修正为分页前总匹配数
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `213`
  - `cd backend && cargo test --test skills_api`
    => `7 passed`
  - `cd backend && cargo build --bin backend-rust`
    => exit `0`
  - `cd backend && cargo test`
    => exit `0`
    - `64 passed`
- 边界说明:
  - 这一步收回的是 persistence boundary，不是 runtime injection boundary
  - Python agents 仍消费 `config.prompt_skills`，所以 prompt skill runtime 主链路还没有完全 Rust-owned
  - legacy `prompt_skills` / `user_configs.other_config` 仍保留 compat mirror，不可立即删除
- 后续修复波次:
  - Wave E / prompt runtime producer ownership
- owner: Rust migration

### 46. dead Python prompt-skill helper retired

- endpoint / feature:
  - Python helper:
    - `backend_old/app/services/agent/skills/prompt_skills.py`
  - related test-only surface:
    - `backend_old/tests/test_prompt_skills_module.py`
- Python 旧行为:
  - helper 提供 builtin prompt template、scope 和 merge 逻辑
  - 但 repo 内 live caller 已不存在，只剩测试和 package export
- Rust 当前行为:
  - prompt skill persistence boundary 已由 Rust-owned
    `db::prompt_skills` 承接
  - Python agents 仍只消费 `config.prompt_skills`，不再需要这个 helper 模块存在
- current behavior:
  - `backend_old/app/services/agent/skills/prompt_skills.py` 已从 repo 删除
  - `backend_old/app/services/agent/skills/__init__.py`
    已移除 retired helper 的导出
  - `backend_old/tests/test_prompt_skills_module.py`
    已删除
  - `backend_old/tests/agent/test_prompt_skills_injection.py`
    改为局部 fixture，不再 import retired helper
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `212`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k prompt_skills tests/test_config_internal_callers_use_service_layer.py -k prompt_skills`
    => `2 passed`
  - `cd backend_old && uv run --project . pytest -s tests/agent/test_prompt_skills_injection.py -k 'not verification' tests/test_api_router_rust_owned_routes_removed.py tests/test_config_internal_callers_use_service_layer.py`
    => `63 passed, 2 deselected, 4 warnings`
- 边界说明:
  - 这是 dead helper retirement，不是新的 Rust runtime takeover
  - 当前只能说明该 helper 不再是 live owner，不能说明
    `config.prompt_skills` producer 已经 Rust-owned
- 后续修复波次:
  - Wave E / prompt runtime producer ownership
- owner: Rust migration

### 47. dead Python skill resource catalog helper retired

- endpoint / feature:
  - Python helper:
    - `backend_old/app/services/agent/skills/resource_catalog.py`
- Python 旧行为:
  - helper 提供 external-tool / prompt resource catalog 的纯拼装函数
  - 当前 repo 内已无 live import 命中
- Rust 当前行为:
  - `skills` catalog/resource surface 已由 Rust `backend/src/routes/skills.rs` 承接
  - 该 Python helper 不再是 live owner
- current behavior:
  - `backend_old/app/services/agent/skills/resource_catalog.py` 已从 repo 删除
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `211`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'prompt_skills or resource_catalog' tests/test_config_internal_callers_use_service_layer.py -k 'prompt_skills or resource_catalog'`
    => `4 passed, 52 deselected, 2 warnings`
- 边界说明:
  - 这是 dead helper retirement，不是新的 Rust runtime takeover
  - 当前只能说明该 helper 不再是 live owner，不能说明 prompt runtime 主链路已 Rust-owned
- 后续修复波次:
  - Wave E / prompt runtime producer ownership
- owner: Rust migration

### 48. dead Python skill-test runner helper retired

- endpoint / feature:
  - Python helper:
    - `backend_old/app/services/agent/skill_test_runner.py`
  - dead tests:
    - `backend_old/tests/test_skill_test_project_lifecycle.py`
    - `backend_old/tests/test_structured_tool_test_runner.py`
- Python 旧行为:
  - helper 曾承接单技能测试/结构化工具测试的 Python runner 逻辑
  - 当前 repo 内已无 live import，只剩测试资产
- Rust 当前行为:
  - Rust `/api/v1/skills/{id}/test` 与 `/tool-test`
    继续承接 HTTP surface
  - 这不等于真正 Rust skill-test runtime 等价；当前仅说明 Python helper 已脱离 live caller
- current behavior:
  - `backend_old/app/services/agent/skill_test_runner.py` 已从 repo 删除
  - 只覆盖该 dead helper 的测试已删除
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `210`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'prompt_skills or resource_catalog or skill_test_runner' tests/test_config_internal_callers_use_service_layer.py -k 'prompt_skills or resource_catalog or skill_test_runner'`
    => `6 passed, 51 deselected, 3 warnings`
- 边界说明:
  - 这是 dead helper / dead test retirement，不是新的 Rust runtime takeover
  - 当前只能证明 repo 内无 live caller，不能把 Rust stub route 当成等价 skill-test runtime 实现
- 后续修复波次:
  - Wave E / runtime producer ownership or retained live helper audit
- owner: Rust migration

### 49. dead Python workflow package convenience module retired

- endpoint / feature:
  - Python package convenience module:
    - `backend_old/app/services/agent/workflow/__init__.py`
- Python 旧行为:
  - package init 仅提供 convenience export
  - repo 内命中已收口到测试
- Rust 当前行为:
  - 无直接对应 Rust 变更；这是 Python dead shell cleanup
- current behavior:
  - `backend_old/app/services/agent/workflow/__init__.py` 已从 repo 删除
  - 原本依赖 package import 的测试已改为直引具体模块：
    - `backend_old/tests/test_parallel_workflow.py`
    - `backend_old/tests/test_workflow_engine.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - `test_parallel_workflow.py`
    已改为 runtime fixture，不再依赖 repo 内已退役测试项目文件
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `209`
  - `cd backend_old && uv run --project . pytest -s tests/test_parallel_workflow.py tests/test_workflow_engine.py`
    => `36 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k workflow tests/test_config_internal_callers_use_service_layer.py -k workflow`
    => `2 passed, 57 deselected, 1 warning`
- 边界说明:
  - 这是 dead package convenience module retirement，不是新的 Rust workflow takeover
  - 当前只能说明 package init 不再是 live owner，workflow engine/orchestrator 本体仍在 Python retained runtime 中
- 后续修复波次:
  - Wave E / retained runtime helper audit
- owner: Rust migration

### 50. dead Python telemetry shell retired

- endpoint / feature:
  - Python telemetry shell:
    - `backend_old/app/services/agent/telemetry/tracer.py`
    - `backend_old/app/services/agent/telemetry/__init__.py`
  - agent package lazy exports:
    - `Tracer`
    - `get_global_tracer`
    - `set_global_tracer`
- Python 旧行为:
  - telemetry package 对外暴露 tracer class / global tracer helper
  - 当前 repo 内已无 live importer
- Rust 当前行为:
  - 无直接对应 Rust 变更；这是 Python dead shell cleanup
- current behavior:
  - telemetry shell 文件已从 repo 删除
  - `backend_old/app/services/agent/__init__.py`
    已移除 telemetry 相关 lazy exports
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `207`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k telemetry tests/test_config_internal_callers_use_service_layer.py -k telemetry`
    => `3 passed, 59 deselected, 1 warning`
- 边界说明:
  - 这是 dead telemetry shell retirement，不是新的 Rust runtime takeover
  - 当前只能说明 repo 内无 live importer 消费 telemetry 包和 tracer symbol
- 后续修复波次:
  - Wave E / retained runtime helper audit
- owner: Rust migration

### 51. empty Python agent-skills package shell retired

- endpoint / feature:
  - Python package shell:
    - `backend_old/app/services/agent/skills/__init__.py`
- Python 旧行为:
  - package init 只剩空壳，不再承接 helper export
- Rust 当前行为:
  - 无直接对应 Rust 变更；这是 Python dead shell cleanup
- current behavior:
  - `backend_old/app/services/agent/skills/__init__.py` 已从 repo 删除
  - direct submodule import 已验证仍正常：
    - `from app.services.agent.skills.scan_core import SCAN_CORE_LOCAL_SKILL_IDS`
      => `17`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `206`
  - `cd backend_old && uv run --project . python -c "from app.services.agent.skills.scan_core import SCAN_CORE_LOCAL_SKILL_IDS; print(len(SCAN_CORE_LOCAL_SKILL_IDS))"`
    => `17`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'skills' tests/test_config_internal_callers_use_service_layer.py -k 'skills'`
    => `4 passed, 60 deselected, 2 warnings`
- 边界说明:
  - 这是空 package shell retirement，不是新的 Rust scan-core takeover
  - 当前只能说明 package shell 不再是 live owner，`scan_core.py` 仍是 Python retained live surface
- 后续修复波次:
  - Wave E / retained runtime helper audit
- owner: Rust migration

### 52. dead Python agent convenience package shell retired

- endpoint / feature:
  - Python package convenience module:
    - `backend_old/app/services/agent/__init__.py`
- Python 旧行为:
  - package root 通过 lazy export 对 tests/consumers 暴露多个子模块
  - 当前 repo 内 live usage 已收口到 tests
- Rust 当前行为:
  - 无直接对应 Rust 变更；这是 Python dead shell cleanup
- current behavior:
  - `backend_old/app/services/agent/__init__.py` 已从 repo 删除
  - 原先依赖 package convenience import 的测试
    已改为直引具体子模块
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `205`
  - `cd backend_old && uv run --project . pytest -s tests/test_agent_tasks_module_layout.py tests/test_static_scan_runtime.py tests/test_agent_event_payload_limits.py tests/test_background_task_launch_refactor.py tests/test_scanner_runner.py`
    => `23 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py tests/test_config_internal_callers_use_service_layer.py -k 'agent and package'`
    => `7 passed, 59 deselected, 3 warnings`
- 边界说明:
  - 这是 convenience package shell retirement，不是新的 Rust runtime takeover
  - 当前只能说明 package root 不再是 live owner，retained helper 本体仍在 Python runtime 中
- 后续修复波次:
  - Wave E / retained runtime helper audit
- owner: Rust migration

### 53. zero-caller Python agent subpackage shells retired in batch

- endpoint / feature:
  - Python subpackage shells:
    - `core/__init__.py`
    - `knowledge/frameworks/__init__.py`
    - `knowledge/vulnerabilities/__init__.py`
    - `memory/__init__.py`
    - `prompts/__init__.py`
    - `streaming/__init__.py`
    - `tool_runtime/__init__.py`
- Python 旧行为:
  - 这些 package shell 提供 convenience export，但 repo 内已无 direct package-shell caller
- Rust 当前行为:
  - 无直接对应 Rust 变更；这是 Python dead shell cleanup
- current behavior:
  - 上述 7 个 `__init__.py` 已从 repo 删除
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - 明确保留：
    - `bootstrap/__init__.py`
    - `tools/runtime/__init__.py`
    因为仍有 repo 内 caller
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `197`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'core or frameworks or vulnerabilities or memory or prompts or streaming or tool_runtime' tests/test_config_internal_callers_use_service_layer.py -k 'core or frameworks or vulnerabilities or memory or prompts or streaming or tool_runtime'`
    => `15 passed, 68 deselected, 7 warnings`
- 边界说明:
  - 这是 zero-caller subpackage shell cleanup，不是新的 Rust runtime takeover
  - 当前只能说明这些 package shell 不再是 live owner，retained live modules 本体仍在 Python runtime 中
- 后续修复波次:
  - Wave E / retained runtime helper audit
- owner: Rust migration

### 54. retained knowledge package convenience module retired

- endpoint / feature:
  - Python package convenience module:
    - `backend_old/app/services/agent/knowledge/__init__.py`
- Python 旧行为:
  - package root 对 internal caller 暴露 `knowledge_loader`
- current behavior:
  - `backend_old/app/services/agent/knowledge/__init__.py` 已从 repo 删除
  - internal live caller 已改为直引具体模块：
    - `backend_old/app/services/agent/agents/base.py`
    - `backend_old/app/services/agent/tools/agent_tools.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `196`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k knowledge tests/test_config_internal_callers_use_service_layer.py -k knowledge`
    => `3 passed, 66 deselected, 1 warning`
- 边界说明:
  - 这是 retained convenience module retirement，不是新的 Rust runtime takeover
  - 当前仅说明 internal caller 已不再依赖 knowledge package root
- 后续修复波次:
  - Wave E / retained runtime helper audit
- owner: Rust migration

### 55. retained bootstrap package shell retired

- endpoint / feature:
  - Python package shell:
    - `backend_old/app/services/agent/bootstrap/__init__.py`
- Python 旧行为:
  - package shell 仅被 3 个测试直接引用
- current behavior:
  - `backend_old/app/services/agent/bootstrap/__init__.py` 已从 repo 删除
  - 3 个测试已改为直引具体子模块：
    - `test_bandit_bootstrap_scanner.py`
    - `test_opengrep_bootstrap_scanner.py`
    - `test_phpstan_bootstrap_scanner.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `193`
  - `cd backend_old && uv run --project . pytest -s tests/test_bandit_bootstrap_scanner.py tests/test_opengrep_bootstrap_scanner.py tests/test_phpstan_bootstrap_scanner.py`
    => `17 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k bootstrap tests/test_config_internal_callers_use_service_layer.py -k bootstrap`
    => `4 passed, 87 deselected, 1 warning`
- 边界说明:
  - 这是 retained package shell retirement，不是新的 Rust bootstrap takeover
  - 当前保留的是 bootstrap 子模块本体，不是 package shell
- 后续修复波次:
  - Wave E / retained runtime helper audit
- owner: Rust migration

### 56. retained tools.runtime package shell retired

- endpoint / feature:
  - Python package shell:
    - `backend_old/app/services/agent/tools/runtime/__init__.py`
- Python 旧行为:
  - package shell 对 internal caller 暴露 `ToolExecutionCoordinator` 等 runtime helper
- current behavior:
  - `backend_old/app/services/agent/tools/runtime/__init__.py`
    已从 repo 删除
  - live caller 已改为直引具体模块：
    - `backend_old/app/services/agent/tools/base.py`
      -> `.runtime.coordinator`
    - `backend_old/tests/test_tool_runtime_coordinator.py`
      -> `app.services.agent.tools.runtime.coordinator`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    - guard 额外覆盖相对 `from .runtime import ...` 形式
  - `prompts` package shell 删除后暴露的导入链断裂已同步修到：
    - `analysis.py`
    - `verification.py`
    - `orchestrator.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `192`
  - `cd backend_old && uv run --project . pytest -s tests/test_tool_runtime_coordinator.py`
    => `5 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tool_runtime tests/test_config_internal_callers_use_service_layer.py -k tool_runtime`
    => `3 passed, 91 deselected, 1 warning`
- 边界说明:
  - 这是 retained package shell retirement，不是新的 Rust tool runtime takeover
  - 当前仅说明 `tools.runtime` package root 不再是 live owner，runtime 子模块本体仍保留
- 后续修复波次:
  - Wave E / retained runtime helper audit
- owner: Rust migration

### 57. retained tools convenience package retired

- endpoint / feature:
  - Python convenience package:
    - `backend_old/app/services/agent/tools/__init__.py`
- Python 旧行为:
  - package root 对 internal/test caller 暴露大量 tool symbol
- current behavior:
  - `backend_old/app/services/agent/tools/__init__.py` 已从 repo 删除
  - direct package caller 已改为直引具体子模块或 symbol
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `191`
  - `cd backend_old && uv run --project . pytest -s tests/test_tool_runtime_coordinator.py`
    => `5 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tool_runtime tests/test_config_internal_callers_use_service_layer.py -k tool_runtime`
    => `3 passed, 91 deselected, 1 warning`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tools tests/test_config_internal_callers_use_service_layer.py -k tools`
    => `5 passed`
- 边界说明:
  - 这是 retained convenience package retirement，不是新的 Rust tool/runtime takeover
  - 当前保留的是具体 tool 模块本体，不再保留 package root
  - 相关更大测试组里仍有既有 `.env` 环境依赖，本 slice 不处理
- 后续修复波次:
  - Wave E / retained runtime helper audit
- owner: Rust migration

### 58. retained workflow cluster retired as test-only code

- endpoint / feature:
  - Python retained workflow cluster:
    - `workflow/engine.py`
    - `workflow/models.py`
    - `workflow/parallel_executor.py`
    - `workflow/memory_monitor.py`
    - `workflow/workflow_orchestrator.py`
- Python 旧行为:
  - 该 cluster 在 repo 内已只剩测试 caller
- current behavior:
  - 上述 5 个源文件已从 repo 删除
  - 对应 5 个测试文件已删除
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `186`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k workflow tests/test_config_internal_callers_use_service_layer.py -k workflow`
    => `8 passed, 94 deselected`
- 边界说明:
  - 这是 retained test-only workflow cluster retirement，不是新的 Rust workflow takeover
- 后续修复波次:
  - Wave E / retained live helper audit
- owner: Rust migration

### 59. retained business-logic-scan pair retired

- endpoint / feature:
  - Python retained pair:
    - `agents/business_logic_scan.py`
    - `tools/business_logic_scan_tool.py`
- Python 旧行为:
  - 该 pair 在 repo 内已只剩测试 caller + package re-export
- current behavior:
  - 上述 2 个源文件已从 repo 删除
  - `agents/__init__.py` 已移除 `BusinessLogicScanAgent` re-export
  - 对应测试 `test_refactored_business_logic_scan.py` 已删除
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `184`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'business_logic_scan' tests/test_config_internal_callers_use_service_layer.py -k 'business_logic_scan'`
    => `4 passed, 102 deselected, 2 warnings`
- 边界说明:
  - 这是 retained test-only pair retirement，不是新的 Rust business-logic-scan takeover
- 后续修复波次:
  - Wave E / retained live helper audit
- owner: Rust migration

### 60. orphan knowledge tools module retired

- endpoint / feature:
  - Python orphan module:
    - `backend_old/app/services/agent/knowledge/tools.py`
- Python 旧行为:
  - 提供安全知识查询工具定义
  - 当前 repo 内已无 direct module caller
- current behavior:
  - `backend_old/app/services/agent/knowledge/tools.py`
    已从 repo 删除
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `180`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'knowledge and tools' tests/test_config_internal_callers_use_service_layer.py -k 'knowledge and tools'`
    => `2 passed, 112 deselected, 1 warning`
- 边界说明:
  - 这是 orphan module retirement，不是新的 Rust knowledge takeover
  - 当前仅说明该工具定义模块已无 repo 内 direct caller
- 后续修复波次:
  - Wave E / retained live helper audit
- owner: Rust migration

### 61. orphan tool_runtime edge cluster retired

- endpoint / feature:
  - Python orphan cluster:
    - `tool_runtime/probe_specs.py`
    - `tool_runtime/protocol_verify.py`
    - `tool_runtime/virtual_tools.py`
- Python 旧行为:
  - 这些模块在 repo 内已无 direct caller
- current behavior:
  - 上述 3 个模块已从 repo 删除
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
    => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l`
    => `180`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'probe_specs or protocol_verify or virtual_tools' tests/test_config_internal_callers_use_service_layer.py -k 'probe_specs or protocol_verify or virtual_tools'`
    => `6 passed, 108 deselected, 3 warnings`
- 边界说明:
  - 这是 orphan cluster retirement，不是新的 Rust tool runtime takeover
  - 当前仅说明这 3 个边缘模块已无 direct caller
- 后续修复波次:
  - Wave E / retained live helper audit
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
  - `zip_storage.py`、`upload/project_stats.py` 仍依赖 ZIP 文件根 / bridge 语义，不能跟着一起删
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

### 17. `backend_old/main.py` retired; root Python live surface is zero

- endpoint / feature:
  - Python root entry: `backend_old/main.py`
- Python 旧行为:
  - root stub 只输出 `Hello from VulHunter-backend!`
  - 不承接 HTTP surface、runtime bootstrap、compose 启动或 Docker entrypoint
- Rust 当前行为:
  - `backend_old/main.py` 已从 repo 物理删除
  - `backend_old/tests/test_legacy_backend_main_retired.py`
    已补 root `main.py` 退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `229`
  - `rg -n "backend_old/main.py|Hello from VulHunter-backend" backend_old backend docker scripts .github frontend plan -S`
    只剩迁移文档命中
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖 root `main.py`
- 边界说明:
  - 这一步清空了 `backend_old` 根目录 Python live surface
  - 但不意味着 non-API migration 主战场已经完成
- 后续修复波次: Wave F / phase-mainline cleanup
- owner: Rust migration

### 18. `search_service.py` and `report_generator.py` retired from live tree

- endpoint / feature:
  - Python dead services:
    - `backend_old/app/services/search_service.py`
    - `backend_old/app/services/report_generator.py`
- Python 旧行为:
  - `search_service.py` 提供 legacy project/task/finding search 组合查询
  - `report_generator.py` 提供 WeasyPrint PDF 报告生成
  - 当前仓库里二者已无 live caller，只剩 legacy tests
- Rust 当前行为:
  - 两个 service 文件已从 repo 物理删除
  - `backend_old/tests/test_search_service.py` 与 `backend_old/tests/test_report_generator_contract.py`
    已删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `227`
  - `rg -n "search_service.py|report_generator.py|SearchService|ReportGenerator" backend_old backend frontend plan -S`
    只剩退休守门测试、离线规则文本与迁移文档命中
- 是否影响前端:
  - 当前不影响前端 live path；前端没有 active caller 直接依赖这两个 Python service
- 边界说明:
  - `search_service.py` 退休不代表 Rust `tasks/findings` search 已完成，只表示 Python service 本身不再 live
  - `report_generator.py` 退休不代表所有导出/report 语义已完全收口到 Rust，只表示这个 Python 实现不再 live
- 后续修复波次: Wave C / shared-service cleanup
- owner: Rust migration

### 19. `runner_preflight.py` retired; live preflight ownership is Rust bootstrap

- endpoint / feature:
  - Python dead service: `backend_old/app/services/runner_preflight.py`
- Python 旧行为:
  - `runner_preflight.py` 承担 runner image 自检 / warmup
  - 当前仓库里已无 Python live caller 依赖它
- Rust 当前行为:
  - live preflight 由 `backend/src/bootstrap/preflight.rs` 承接
  - Python `runner_preflight.py` 已从 repo 物理删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `226`
  - `rg -n "runner_preflight.py|run_configured_runner_preflights|get_configured_runner_preflight_specs|RunnerPreflightSpec" backend_old backend plan scripts -S`
    live runtime 命中只剩 Rust `backend/src/bootstrap/preflight.rs` 与 release template helper
- 是否影响前端:
  - 不影响，前端不直接依赖 runner preflight service
- 边界说明:
  - 退休的是 `backend_old` Python service，不是 release template helper
  - Rust bootstrap 仍是这条能力的唯一 live owner
- 后续修复波次: Wave C / shared-service cleanup
- owner: Rust migration

### 20. `opengrep_confidence.py` and `init_templates.py` retired from live tree

- endpoint / feature:
  - Python dead helper/service:
    - `backend_old/app/services/opengrep_confidence.py`
    - `backend_old/app/services/init_templates.py`
- Python 旧行为:
  - `opengrep_confidence.py` 提供 Opengrep confidence normalization / aggregation helper
  - `init_templates.py` 提供 legacy prompt template / audit rule 初始化
  - 当前仓库里二者都已无 live caller
- Rust 当前行为:
  - 两个文件已从 repo 物理删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - Opengrep confidence 相关逻辑已收口到
    `backend_old/app/services/agent/bootstrap/opengrep.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `224`
  - `rg -n "opengrep_confidence.py|init_templates.py|init_templates_and_rules|normalize_confidence|extract_rule_lookup_keys" backend_old backend frontend plan -S`
    live caller 只剩 `agent/bootstrap/opengrep.py` 内联后的 helper 与迁移文档命中
- 是否影响前端:
  - 不影响，前端没有 active caller 直接依赖这两个 Python 文件
- 边界说明:
  - `opengrep_confidence.py` 退休不代表 Opengrep finding/report 全语义都已完成 Rust 迁移
  - `init_templates.py` 退休不代表所有模板/规则初始化语义都已在 Rust 全量等价覆盖
- 后续修复波次: Wave C / shared-service cleanup
- owner: Rust migration

### 21. `seed_archive.py` retired from live tree

- endpoint / feature:
  - Python dead helper/service: `backend_old/app/services/seed_archive.py`
- Python 旧行为:
  - `seed_archive.py` 提供 seed archive URL 组装、探测与下载 helper
  - 当前仓库里已无 live caller，只剩旧专属测试
- Rust 当前行为:
  - `seed_archive.py` 已从 repo 物理删除
  - `backend_old/tests/test_seed_archive.py` 已删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `223`
  - `rg -n "seed_archive.py|build_seed_archive_candidates|download_seed_archive" backend_old backend frontend plan -S`
    只剩退休守门测试与迁移文档命中
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖 seed archive helper
- 边界说明:
  - 退休的是 dead helper，不代表所有 seed/download 语义都已在 Rust 全量等价覆盖
- 后续修复波次: Wave C / shared-service cleanup
- owner: Rust migration

### 22. `zip_storage.py` and `upload/*` retired from live tree

- endpoint / feature:
  - Python dead implementation:
    - `backend_old/app/services/zip_storage.py`
    - `backend_old/app/services/upload/compression_factory.py`
    - `backend_old/app/services/upload/compression_handlers.py`
    - `backend_old/app/services/upload/compression_strategy.py`
    - `backend_old/app/services/upload/language_detection.py`
    - `backend_old/app/services/upload/project_stats.py`
    - `backend_old/app/services/upload/upload_manager.py`
- Python 旧行为:
  - `zip_storage.py` 提供 ZIP 文件路径/元数据 helper
  - `upload/*` 提供压缩包策略、cloc/项目描述、语言识别与解压 helper
  - 当前仓库里已无 live caller，只剩旧专属测试
- Rust 当前行为:
  - 上述文件已从 repo 物理删除
  - `backend_old/tests/test_llm_description.py`、`test_cloc_stats.py`、
    `test_project_stats_suffix_fallback.py`、`test_file_upload_compress.py` 已删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - live upload / archive / description HTTP surface 继续由 `backend/src/routes/projects.rs` 承接
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `216`
  - `rg -n "zip_storage.py|get_project_zip_path|project_stats.py|generate_project_description|get_cloc_stats_from_archive|UploadManager|CompressionStrategyFactory|compression_handlers.py|compression_strategy.py|language_detection.py" backend_old backend frontend plan -S`
    live caller 命中只剩 Rust `projects` 路由、退休守门测试与迁移文档
- 是否影响前端:
  - 当前不影响前端 live path；前端访问的是 Rust `projects` 路由
  - 但这不代表 Rust 已等价覆盖旧 Python upload 语义；前端仍允许非 zip archive 后缀，Rust 仍是 zip-only contract
- 边界说明:
  - 本次退休的是 dead implementation，不是“upload 语义已全部迁完”的宣告
- 后续修复波次: Wave C / upload-contract cleanup
- owner: Rust migration

### 23. `scanner.py` and `gitleaks_rules_seed.py` retired from live tree

- endpoint / feature:
  - Python dead implementation:
    - `backend_old/app/services/scanner.py`
    - `backend_old/app/services/gitleaks_rules_seed.py`
- Python 旧行为:
  - `scanner.py` 提供 legacy ZIP 文件筛选 helper
  - `gitleaks_rules_seed.py` 提供 builtin Gitleaks 规则初始化 helper
  - 当前仓库里都已无 live caller
- Rust 当前行为:
  - 上述文件已从 repo 物理删除
  - `backend_old/tests/test_file_selection.py` 与 `test_file_selection_e2e.py` 已删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `214`
  - `rg -n "from app\\.services\\.scanner import|import app\\.services\\.scanner|is_text_file\\(|should_exclude\\(|EXCLUDE_PATTERNS|from app\\.services\\.gitleaks_rules_seed import|import app\\.services\\.gitleaks_rules_seed|ensure_builtin_gitleaks_rules\\(" backend_old/app backend_old/tests backend/src frontend -S`
    live caller 已清零，只剩退休守门测试与迁移文档
- 是否影响前端:
  - 不影响，前端没有 active caller 直接依赖这两个 Python 文件
- 边界说明:
  - 退休的是 dead implementation，不代表 scanner/runtime 全语义已完成 Rust 迁移
- 后续修复波次: Wave C / shared-service cleanup
- owner: Rust migration

### 24. Rust search now serves task and finding matches

- endpoint / feature:
  - Rust search routes:
    - `GET /api/v1/search/tasks/search`
    - `GET /api/v1/search/findings/search`
    - `GET /api/v1/search/search`
- Python 旧行为:
  - legacy `search_service.py` 已退休；此前 Rust 只真正支持 project search
- Rust 当前行为:
  - `backend/src/routes/search.rs` 已接入 Rust `task_state` snapshot
  - agent/static task 搜索会匹配 `name/description|target_path/task_type|engine/status/created_at`
  - agent/static finding 搜索会匹配 `title/description/vulnerability_type/file_path/code_snippet|match`
  - global search 的 `tasks/findings` 聚合不再固定为空
  - `backend/tests/search_api.rs` 已改为断言 agent/static task 与 finding 命中，并覆盖分页 total 语义
- operational verification:
  - 当前因本机 `rustc 1.85.0` 低于依赖要求，无法执行 `cargo test --test search_api`
  - 但 route/test 合同与实现已经同步更新
- 是否影响前端:
  - 当前前端没有 active caller 依赖这条搜索路由；这一步主要是 Rust ownership 补全
- 边界说明:
  - 目前补的是 task/finding search
  - rule 搜索仍未完成，因此 `search` 整体仍是 partially migrated
- 后续修复波次: Wave C / search parity cleanup
- owner: Rust migration

### 25. `project_test_service.py` retired; helper absorbed into `skill_test_runner.py`

- endpoint / feature:
  - Python top-level helper: `backend_old/app/services/project_test_service.py`
- Python 旧行为:
  - 只提供 `normalize_extracted_project_root`
  - 当前唯一 live caller 是 `agent/skill_test_runner.py`
- Rust / current behavior:
  - `project_test_service.py` 已从 repo 物理删除
  - `normalize_extracted_project_root` 已内聚到
    `backend_old/app/services/agent/skill_test_runner.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已改为要求 helper 本地存在于 `skill_test_runner.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
  - `rg -n "project_test_service|normalize_extracted_project_root" backend_old/app backend_old/tests backend/src frontend -S`
    live caller 已收口到 `skill_test_runner.py` 与退休守门测试
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖该 helper
- 边界说明:
  - 这是顶层 helper 内聚退休，不代表 `skill_test_runner` 已完成 Rust 迁移
- 后续修复波次: Wave E / agent surface cleanup
- owner: Rust migration

### 26. `flow_parser_runtime.py` retired; provider absorbed into `agent/flow/lightweight`

- endpoint / feature:
  - Python top-level helper: `backend_old/app/services/flow_parser_runtime.py`
- Python 旧行为:
  - 提供 DefinitionProvider / HybridDefinitionProvider glue
  - 当前唯一 live caller 是 `agent/flow/lightweight/ast_index.py`
- Rust / current behavior:
  - `flow_parser_runtime.py` 已从 repo 物理删除
  - definition-provider 逻辑已迁入
    `backend_old/app/services/agent/flow/lightweight/definition_provider.py`
  - `backend_old/app/services/agent/flow/lightweight/ast_index.py`
    已改为域内 import
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
  - `rg -n "flow_parser_runtime|get_default_definition_provider|DefinitionProvider|HybridDefinitionProvider|RunnerDefinitionProvider|LocalDefinitionProvider" backend_old/app backend_old/tests -S`
    live caller 已收口到 `agent/flow/lightweight` 域内
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖该 helper
- 边界说明:
  - 这是顶层 runtime helper 内聚退休，不代表 flow-parser 能力已完成 Rust 迁移
- 后续修复波次: Wave D / flow helper cleanup
- owner: Rust migration

### 27. `parser.py` retired; tree-sitter parser absorbed into `agent/flow/lightweight`

- endpoint / feature:
  - Python top-level helper: `backend_old/app/services/parser.py`
- Python 旧行为:
  - 提供 `TreeSitterParser`
  - 当前 live caller 已收缩到 `agent/flow/lightweight` 域
- Rust / current behavior:
  - `parser.py` 已从 repo 物理删除
  - `TreeSitterParser` 已迁入
    `backend_old/app/services/agent/flow/lightweight/tree_sitter_parser.py`
  - `ast_index.py`、`function_locator.py`、`definition_provider.py`
    已改为域内 import
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
  - `rg -n "from app\\.services\\.parser import|import app\\.services\\.parser|TreeSitterParser" backend_old/app backend_old/tests backend/src frontend -S`
    live caller 已收口到 `agent/flow/lightweight` 域内
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖该 helper
- 边界说明:
  - 这是顶层 parser helper 内聚退休，不代表 flow-parser 能力已完成 Rust 迁移
- 后续修复波次: Wave D / flow helper cleanup
- owner: Rust migration

### 28. `sandbox_runner_client.py` retired from top-level; helper absorbed into `agent/tools`

- endpoint / feature:
  - Python top-level helper: `backend_old/app/services/sandbox_runner_client.py`
- Python 旧行为:
  - 提供 SandboxRunnerClient
  - 当前 live caller 已收缩到 `agent/tools/sandbox_tool.py`
- Rust / current behavior:
  - 顶层 `sandbox_runner_client.py` 已迁入
    `backend_old/app/services/agent/tools/sandbox_runner_client.py`
  - `sandbox_tool.py` 已改为域内 import
  - `backend_old/tests/test_sandbox_runner_client.py`
    已同步指向新模块路径
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
  - `rg -n "sandbox_runner_client|SandboxRunnerClient" backend_old/app backend_old/tests backend/src frontend -S`
    live caller 已收口到 `agent/tools` 域内与测试
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖该 helper
- 边界说明:
  - 这是顶层 sandbox helper 内聚退休，不代表 sandbox runtime 已完成 Rust 迁移
- 后续修复波次: Wave D / sandbox helper cleanup
- owner: Rust migration

### 29. `backend_venv.py` retired; helper absorbed into `static_scan_runtime.py`

- endpoint / feature:
  - Python top-level helper: `backend_old/app/services/backend_venv.py`
- Python 旧行为:
  - 提供 backend venv path / env / executable helper
  - 当前唯一 live caller 是 `static_scan_runtime.py`
- Rust / current behavior:
  - `backend_venv.py` 已从 repo 物理删除
  - helper 已内聚回 `backend_old/app/services/static_scan_runtime.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `212`
  - `rg -n "backend_venv|build_backend_venv_env|resolve_backend_venv_executable|get_backend_venv_path|get_backend_venv_bin_dir" backend_old/app backend_old/tests backend/src frontend -S`
    live caller 已收口到 `static_scan_runtime.py`、退休守门测试与 Rust runtime/bootstrap
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖该 helper
- 边界说明:
  - 这是顶层 runtime helper 内聚退休，不代表 `static_scan_runtime.py` 已完成 Rust 迁移
- 后续修复波次: Wave D / runtime helper cleanup
- owner: Rust migration

### 30. `user_config_service.py` retired; helper absorbed into `static_scan_runtime.py`

- endpoint / feature:
  - Python top-level helper: `backend_old/app/services/user_config_service.py`
- Python 旧行为:
  - 提供用户配置默认值、解密、sanitize 与 effective merge helper
  - 当前唯一 live caller 是 `static_scan_runtime.py`
- Rust / current behavior:
  - `user_config_service.py` 已从 repo 物理删除
  - 相关 helper 已内聚回 `backend_old/app/services/static_scan_runtime.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已改为要求 `_load_effective_user_config` 本地存在于 `static_scan_runtime.py`
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
  - `rg -n "user_config_service|load_effective_user_config|_load_effective_user_config|sanitize_other_config|strip_runtime_config|_default_user_config" backend_old/app backend_old/tests backend/src frontend -S`
    live caller 已收口到 `static_scan_runtime.py` 与退休守门测试
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖该 helper
- 边界说明:
  - 这是顶层 config/helper 内聚退休，不代表 `static_scan_runtime.py` 已完成 Rust 迁移
- 后续修复波次: Wave D / runtime helper cleanup
- owner: Rust migration

### 31. `static_scan_runtime.py` retired as a dead shell

- endpoint / feature:
  - Python top-level helper shell: `backend_old/app/services/static_scan_runtime.py`
- repo evidence before deletion:
  - `rg -n "from app\\.services\\.static_scan_runtime import|import app\\.services\\.static_scan_runtime|static_scan_runtime\\." backend_old/app backend_old/tests -S`
    只剩测试命中，没有 repo 内 direct live caller
  - `rg -n "importlib\\.(import_module|__import__)\\(|__import__\\(|app\\.services\\.static_scan_runtime|services/static_scan_runtime\\.py|static_scan_runtime" backend_old/app backend_old/scripts backend_old/tests -S`
    只剩测试与迁移文本，没有动态导入或脚本入口证据
- current behavior:
  - `backend_old/app/services/static_scan_runtime.py` 已从 repo 物理删除
  - `backend_old/tests/test_static_scan_runtime.py`
    仅保留 `agent/scan_workspace.py` 与 `agent/scan_tracking.py` 的 shared helper 契约覆盖
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    改为 guard repo 内 live Python 模块不得再 import `static_scan_runtime`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 service-module retirement guard
- operational verification:
  - `uv run --project . pytest -s tests/test_static_scan_runtime.py tests/test_background_task_launch_refactor.py tests/test_config_internal_callers_use_service_layer.py tests/test_scanner_runner.py tests/test_api_router_rust_owned_routes_removed.py`
    => `54 passed, 1 warning`
  - warning 备注：
    `app/services/agent/knowledge/vulnerabilities/open_redirect.py:12`
    存在未触及的既有 `DeprecationWarning: invalid escape sequence '\/'`
- 是否影响前端:
  - 不影响；本 slice 不改静态任务返回 shape，也不改 route inventory
- 边界说明:
  - 这是 dead shell retirement，不是 Rust takeover 里程碑
  - 如果仓外还有未登记调用方，本台账无法单独证明它们不存在；当前结论仅基于 repo 内证据
- 后续修复波次: Wave D / runtime helper cleanup
- owner: Rust migration

### 32. `json_safe.py` retired from top-level; helper absorbed into `agent/`

- endpoint / feature:
  - Python top-level helper: `backend_old/app/services/json_safe.py`
- Python 旧行为:
  - 提供 `dump_json_safe` / `normalize_json_safe`
  - 当前 live caller 已收缩到 agent 域
- Rust / current behavior:
  - 顶层 `json_safe.py` 已迁入 `backend_old/app/services/agent/json_safe.py`
  - agent caller 已改为域内 import
  - `backend_old/tests/test_json_safe.py` 已同步指向新模块路径
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
  - `rg -n "from app\\.services\\.json_safe import|import app\\.services\\.json_safe|dump_json_safe|normalize_json_safe" backend_old/app backend_old/tests -S`
    live caller 已收口到 agent 域内与测试
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖该 helper
- 边界说明:
  - 这是顶层 agent helper 内聚退休，不代表 agent 内核已完成 Rust 迁移
- 后续修复波次: Wave E / agent helper cleanup
- owner: Rust migration

### 33. `flow_parser_runner.py` retired from top-level; helper absorbed into `agent/flow`

- endpoint / feature:
  - Python top-level helper: `backend_old/app/services/flow_parser_runner.py`
- Python 旧行为:
  - 提供 FlowParserRunnerClient
  - 当前 live caller 已收缩到 agent/flow 与 skill-test 域
- Rust / current behavior:
  - 顶层 `flow_parser_runner.py` 已迁入
    `backend_old/app/services/agent/flow/flow_parser_runner.py`
  - agent/flow 与 skill-test caller 已改为域内 import
  - `backend_old/tests/test_flow_parser_runner_client.py`
    已同步指向新模块路径
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
- operational verification:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
  - `rg -n "from app\\.services\\.flow_parser_runner import|import app\\.services\\.flow_parser_runner|get_flow_parser_runner_client|FlowParserRunnerClient" backend_old/app backend_old/tests -S`
    live caller 已收口到 agent/flow 域内与测试
- 是否影响前端:
  - 不影响，前端没有 active caller 依赖该 helper
- 边界说明:
  - 这是顶层 flow runner helper 内聚退休，不代表 flow-parser/runtime 能力已完成 Rust 迁移
- 后续修复波次: Wave D / flow runner cleanup
- owner: Rust migration

### 34. `backend_old/app/api/v1/api.py` retired as an empty API router shell

- endpoint / feature:
  - Python API router shell: `backend_old/app/api/v1/api.py`
- repo evidence before deletion:
  - 文件内容仅剩空 `APIRouter()`，不再挂载任何 route group
  - `rg -n "from app\\.api\\.v1\\.api import api_router|app\\.api\\.v1\\.api|api_router\\.routes" backend_old/app backend_old/tests backend_old/scripts -S`
    只剩 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    与 `backend_old/tests/test_agent_tasks_module_layout.py` 两处测试命中
- current behavior:
  - `backend_old/app/api/v1/api.py` 已从 repo 物理删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    改为守住 API router module 物理不存在
  - `backend_old/tests/test_agent_tasks_module_layout.py`
    改为守住 agent-tasks 相关 layout 不再依赖 Python API router shell
- operational verification:
  - `uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py tests/test_agent_tasks_module_layout.py`
- 是否影响前端:
  - 不影响；本 slice 不改 Rust 路由、前端 API base、route inventory 或返回 shape
- 边界说明:
  - 这是 API dead shell retirement，不是新的 Rust route takeover
  - `agent_tasks*.py` 模块仍作为 Python library surface 保留，本 slice 不处理它们
- 后续修复波次: Wave A / API shell cleanup
- owner: Rust migration

### 35. `_initialize_tools` dead tooling retired after `agent_tasks_execution.py` removal

- endpoint / feature:
  - Python dead tooling:
    - `backend_old/scripts/generate_runtime_tool_docs.py`
    - `backend_old/scripts/validate_runtime_tool_docs.py`
    - `backend_old/tests/test_agent_tool_registry.py`
    - `backend_old/tests/test_runtime_tool_docs_coverage.py`
- repo evidence before deletion:
  - `uv run --project . pytest -s tests/test_agent_tool_registry.py tests/test_runtime_tool_docs_coverage.py`
    在当前 `main` 上直接 collection error：
    `ImportError: cannot import name '_initialize_tools' from 'app.api.v1.endpoints.agent_tasks'`
  - `_initialize_tools` 与 `_collect_project_info` 原本来自已退休的
    `agent_tasks_execution.py`，当前 facade `agent_tasks.py` 已不再 re-export
- current behavior:
  - 上述两个脚本与两个测试已从 repo 物理删除
  - `backend_old/tests/test_agent_tasks_module_layout.py`
    已补负向守门，要求 `agent_tasks` facade 不得重新 re-export
    `_initialize_tools`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 runtime tool docs script retirement guard
- operational verification:
  - `uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py tests/test_agent_tasks_module_layout.py`
  - `rg -n "from app\\.api\\.v1\\.endpoints\\.agent_tasks import _initialize_tools|from scripts\\.generate_runtime_tool_docs import" backend_old/tests backend_old/scripts -S`
- 边界说明:
  - 这是 dead tooling retirement，不是把 `_initialize_tools` 等旧 Python 执行逻辑重新接回
  - 本 slice 不修改 `agent_tasks*.py` 存活 helper 的语义，也不改 Rust 路由或 route inventory
- 后续修复波次: Wave E / agent facade cleanup
- owner: Rust migration

### 36. `agent_tasks_runtime.py` dead tests retired after runtime helper removal

- endpoint / feature:
  - Python dead tests:
    - `backend_old/tests/test_agent_task_verification_gate.py`
    - `backend_old/tests/test_agent_task_retry_classification.py`
    - `backend_old/tests/test_agent_task_cancel_preserve_stats.py`
- repo evidence before deletion:
  - `uv run --project . pytest -s tests/test_agent_task_verification_gate.py tests/test_agent_task_retry_classification.py tests/test_agent_task_cancel_preserve_stats.py`
    在当前 `main` 上直接 collection error：
    - `_compute_verification_pending_gate`
    - `_classify_retry_error`
    - `_snapshot_runtime_stats_to_task`
    均已无法从 `app.api.v1.endpoints.agent_tasks` 导入
  - 上述 3 个 helper 原本来自已退休的 `agent_tasks_runtime.py`
- current behavior:
  - 上述 3 条 dead tests 已从 repo 物理删除
  - `backend_old/tests/test_agent_tasks_module_layout.py`
    已补负向守门，要求 `agent_tasks` facade 不得重新 re-export
    `_compute_verification_pending_gate` / `_classify_retry_error` /
    `_snapshot_runtime_stats_to_task`
- operational verification:
  - `uv run --project . pytest -s tests/test_agent_tasks_module_layout.py tests/test_api_router_rust_owned_routes_removed.py`
  - `rg -n "from app\\.api\\.v1\\.endpoints\\.agent_tasks import (_compute_verification_pending_gate|_classify_retry_error|_snapshot_runtime_stats_to_task)" backend_old/tests -S`
- 边界说明:
  - 这是 dead test retirement，不是把旧 runtime helper 接回 Python facade
  - 本 slice 不处理 `get_agent_finding` / `_collect_project_info` 这两组独立 broken import
- 后续修复波次: Wave E / agent facade cleanup
- owner: Rust migration

### 37. `get_agent_finding` and `_collect_project_info` dead tests retired after route/execution removal

- endpoint / feature:
  - Python dead tests:
    - `backend_old/tests/test_agent_finding_detail_endpoint.py`
    - `backend_old/tests/test_agent_core_scope_filtering.py` 中仅依赖 `_collect_project_info` 的用例
- repo evidence before deletion:
  - `uv run --project . pytest -s tests/test_agent_finding_detail_endpoint.py tests/test_agent_core_scope_filtering.py`
    在当前 `main` 上直接 collection error：
    - `get_agent_finding`
    - `_collect_project_info`
    均已无法从 `app.api.v1.endpoints.agent_tasks` 导入
  - `get_agent_finding` 原本来自已退休的 `agent_tasks_routes_results.py`
  - `_collect_project_info` 原本来自已退休的 `agent_tasks_execution.py`
- current behavior:
  - `backend_old/tests/test_agent_finding_detail_endpoint.py` 已从 repo 物理删除
  - `backend_old/tests/test_agent_core_scope_filtering.py`
    仅移除依赖 `_collect_project_info` 的 dead 用例，保留
    `_filter_bootstrap_findings` / `_discover_entry_points_deterministic` /
    `SmartScanTool._collect_files` 的 live helper coverage
  - `backend_old/tests/test_agent_tasks_module_layout.py`
    已补负向守门，要求 `agent_tasks` facade 不得重新 re-export
    `_collect_project_info` / `get_agent_finding`
- operational verification:
  - `uv run --project . pytest -s tests/test_agent_tasks_module_layout.py tests/test_api_router_rust_owned_routes_removed.py`
  - `rg -n "from app\\.api\\.v1\\.endpoints\\.agent_tasks import (_collect_project_info|get_agent_finding)" backend_old/tests -S`
- 边界说明:
  - 这是 dead test retirement，不是把旧 execution/results helper 接回 Python facade
  - 本 slice 不处理 `agent_tasks_findings.py` 里仍存活的 `_save_findings` / structured title helper
- 后续修复波次: Wave E / agent facade cleanup
- owner: Rust migration

### 38. C `__attribute__` function fallback fixed for retained function locator

- endpoint / feature:
  - Retained Python helper:
    - `backend_old/app/services/agent/flow/lightweight/function_locator_cli.py`
- repo evidence before fix:
  - `uv run --project . pytest -s tests/test_function_locator_tree_sitter.py -q`
    在当前环境里失败：
    `c_result["function"] == None`
  - 同一根因会连带打坏
    `tests/test_agent_result_consistency.py::test_save_findings_filters_pseudo_c_attribute_function_name`
- current behavior:
  - C/CPP regex fallback 现在会从同一行的多个 `name(` 候选里选择最后一个非伪函数名，
    从而跳过 `__attribute__` / `unused` 并命中真实函数名 `parse_node`
- operational verification:
  - `uv run --project . pytest -s tests/test_function_locator_tree_sitter.py -q`
  - `uv run --project . pytest -s tests/test_agent_result_consistency.py -k "pseudo_c_attribute_function_name"`
- 边界说明:
  - 这是 retained live helper correctness fix，不是新的 Rust takeover slice
  - 本 slice 不处理 `_save_findings` 里 status 归一或 function-range diagnostics 的其他失败
- 后续修复波次: Wave E / retained helper correctness
- owner: Rust migration

### 39. `_save_findings` keeps `likely` status and missing-range diagnostics for retained findings helper

- endpoint / feature:
  - Retained Python helper:
    - `backend_old/app/api/v1/endpoints/agent_tasks_findings.py`
- repo evidence before fix:
  - `uv run --project . pytest -s tests/test_agent_result_consistency.py -k "normalizes_legacy_uncertain_status_to_likely_and_keeps_rich_fields or skips_hit_line_correction_when_function_range_missing"`
    失败：
    - legacy `status="uncertain"` 被压成 `needs_review`
    - `function_range_validation.hit_line_correction_skipped_reason`
      未保留 `missing_function_range`
- current behavior:
  - `normalized_status == FindingStatus.LIKELY` 时，`db_status` 与
    `verification_result["status"]` 都保留为 `likely`
  - 当上游未提供 function range 且本次没有发生 hit-line correction 时，
    `function_range_validation.hit_line_correction_skipped_reason`
    会显式记录为 `missing_function_range`
- operational verification:
  - `uv run --project . pytest -s tests/test_agent_result_consistency.py -k "normalizes_legacy_uncertain_status_to_likely_and_keeps_rich_fields or skips_hit_line_correction_when_function_range_missing"`
  - `uv run --project . pytest -s tests/test_function_locator_tree_sitter.py tests/test_agent_result_consistency.py`
- 边界说明:
  - 这是 retained live helper correctness fix，不是新的 Rust takeover slice
  - 本 slice 不处理 `test_tool_skills_memory_sync.py` 里的 skill snapshot 期望漂移
- 后续修复波次: Wave E / retained helper correctness
- owner: Rust migration

### 40. `backend_old/app/api/v1/endpoints/agent_tasks.py` facade retired

- endpoint / feature:
  - Python API facade shell:
    - `backend_old/app/api/v1/endpoints/agent_tasks.py`
- repo evidence before deletion:
  - `rg -n "from app\\.api\\.v1\\.endpoints\\.agent_tasks import|from app\\.api\\.v1\\.endpoints import agent_tasks" backend_old/tests backend_old/scripts backend_old/app -S`
    只剩测试命中，无 script/runtime caller
  - facade 文件本体仅做 wildcard re-export 与空 `APIRouter()` 壳，不再承载 live route mount
- current behavior:
  - `backend_old/app/api/v1/endpoints/agent_tasks.py` 已从 repo 物理删除
  - 仍存活的 helper 测试已改为直连真实模块：
    - `agent_tasks_findings.py`
    - `agent_tasks_tool_runtime.py`
    - `agent_tasks_bootstrap.py`
    - `agent_tasks_contracts.py`
  - `backend_old/tests/test_agent_tasks_module_layout.py`
    改为守住 split modules 直接暴露关键符号，以及 facade 文件不得回流
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 facade-module retirement guard
- operational verification:
  - `uv run --project . pytest -s tests/test_agent_tasks_module_layout.py tests/test_api_router_rust_owned_routes_removed.py tests/test_agent_findings_persistence.py tests/test_agent_findings_strict_validation.py tests/test_agent_result_consistency.py tests/test_report_finding_update_flow.py tests/test_tool_catalog_memory_sync.py tests/test_tool_skills_memory_sync.py tests/test_agent_title_normalization.py`
- 边界说明:
  - 这是 API facade retirement，不是新的 Rust route takeover
  - 本 slice 不改 `agent_tasks_bootstrap.py` / `agent_tasks_findings.py` /
    `agent_tasks_tool_runtime.py` / `agent_tasks_contracts.py` 的 helper 语义
- 后续修复波次: Wave A / API facade cleanup
- owner: Rust migration

### 41. `agent_tasks_tool_runtime.py` retired as dead API-local tooling

- endpoint / feature:
  - Python API-local tooling shell:
    - `backend_old/app/api/v1/endpoints/agent_tasks_tool_runtime.py`
  - Associated dead tests:
    - `backend_old/tests/test_tool_catalog_memory_sync.py`
    - `backend_old/tests/test_tool_skills_memory_sync.py`
- repo evidence before deletion:
  - `rg -n "from app\\.api\\.v1\\.endpoints\\.agent_tasks_tool_runtime|build_task_write_scope_guard|_run_task_llm_connection_test|_sync_tool_catalog_to_memory|_sync_tool_playbook_to_memory|_build_tool_skills_snapshot|_sync_tool_skills_to_memory" backend_old/app backend_old/tests backend_old/scripts -S`
    只剩模块本体与测试命中，没有 app/runtime/script caller
- current behavior:
  - `backend_old/app/api/v1/endpoints/agent_tasks_tool_runtime.py` 已从 repo 物理删除
  - 上述两条 dead tests 已删除
  - `backend_old/tests/test_agent_tasks_module_layout.py`
    改为不再要求 split modules 中存在 `agent_tasks_tool_runtime.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补该 module retirement guard
- operational verification:
  - `uv run --project . pytest -s tests/test_agent_tasks_module_layout.py tests/test_api_router_rust_owned_routes_removed.py tests/test_agent_findings_persistence.py tests/test_agent_findings_strict_validation.py tests/test_agent_result_consistency.py tests/test_report_finding_update_flow.py tests/test_agent_title_normalization.py`
  - `rg -n "from app\\.api\\.v1\\.endpoints\\.agent_tasks_tool_runtime" backend_old/tests backend_old/scripts backend_old/app -S`
- 边界说明:
  - 这是 API-local dead tooling retirement，不是把 write-scope / LLM test / tool docs sync 接回其他 Python facade
  - 本 slice 不处理 `agent_tasks_bootstrap.py` / `agent_tasks_findings.py` / `agent_tasks_contracts.py`
- 后续修复波次: Wave A / API facade cleanup
- owner: Rust migration

### 42. `agent_tasks_bootstrap.py` retired as dead API-local bootstrap shell

- endpoint / feature:
  - Python API-local bootstrap shell:
    - `backend_old/app/api/v1/endpoints/agent_tasks_bootstrap.py`
- repo evidence before deletion:
  - `rg -n "from app\\.api\\.v1\\.endpoints\\.agent_tasks_bootstrap|app\\.api\\.v1\\.endpoints\\.agent_tasks_bootstrap" backend_old/app backend_old/tests backend_old/scripts -S`
    只剩 `test_agent_tasks_module_layout.py` 的模块存在性/alias 断言命中，没有 app/runtime/script caller
  - 模块内容主要是对 `app.services.agent.*` bootstrap helper 的 API-local re-export
- current behavior:
  - `backend_old/app/api/v1/endpoints/agent_tasks_bootstrap.py` 已从 repo 物理删除
  - `backend_old/tests/test_agent_tasks_module_layout.py`
    不再把它列为 split module，并新增 retirement guard
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 bootstrap-module retirement guard
- operational verification:
  - `uv run --project . pytest -s tests/test_agent_tasks_module_layout.py tests/test_api_router_rust_owned_routes_removed.py tests/test_agent_findings_persistence.py tests/test_agent_findings_strict_validation.py tests/test_agent_result_consistency.py tests/test_report_finding_update_flow.py tests/test_agent_title_normalization.py`
  - `rg -n "from app\\.api\\.v1\\.endpoints\\.agent_tasks_bootstrap|app\\.api\\.v1\\.endpoints\\.agent_tasks_bootstrap" backend_old/app backend_old/tests backend_old/scripts -S`
- 边界说明:
  - 这是 API-local bootstrap shell retirement，不是把 bootstrap helper 语义从 `services/agent/*` 回流到别处
  - 本 slice 不处理 `agent_tasks_contracts.py` / `agent_tasks_findings.py` / `rule_flows.py`
- 后续修复波次: Wave A / API facade cleanup
- owner: Rust migration

### 44. `agent_tasks_contracts.py` retired; `AgentFindingResponse` moved into findings module

- endpoint / feature:
  - Python API-local contracts shell:
    - `backend_old/app/api/v1/endpoints/agent_tasks_contracts.py`
- repo evidence before deletion:
  - `rg -n "AgentTaskCreate|AgentTaskResponse|AgentEventResponse|TaskSummaryResponse" backend_old/app backend_old/tests backend_old/scripts -S`
    只剩 contracts module 本体与 module-layout test 命中
  - `AgentFindingResponse` 的唯一活 caller 是 `agent_tasks_findings.py`
- current behavior:
  - `backend_old/app/api/v1/endpoints/agent_tasks_contracts.py` 已从 repo 物理删除
  - `AgentFindingResponse` 已内联到 `backend_old/app/api/v1/endpoints/agent_tasks_findings.py`
  - `backend_old/tests/test_agent_tasks_module_layout.py`
    改为直接守住 `AgentFindingResponse` 由 findings module 承载，并补 contracts-module retirement guard
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 contracts-module retirement guard
- operational verification:
  - `uv run --project . pytest -s tests/test_agent_tasks_module_layout.py tests/test_api_router_rust_owned_routes_removed.py tests/test_agent_findings_persistence.py tests/test_agent_findings_strict_validation.py tests/test_agent_result_consistency.py tests/test_report_finding_update_flow.py tests/test_agent_title_normalization.py`
- 边界说明:
  - 这是 API-local contracts shell retirement，不是新的 Rust takeover
  - 本 slice 不处理 `agent_tasks_findings.py` 的 helper 语义，只改变 response model 宿主位置
- 后续修复波次: Wave A / API facade cleanup
- owner: Rust migration

### 45. Empty `api/v1` package init shells retired

- endpoint / feature:
  - Python package shells:
    - `backend_old/app/api/v1/__init__.py`
    - `backend_old/app/api/v1/endpoints/__init__.py`
- repo evidence before deletion:
  - 两个文件均为空壳，不承载代码或导出
  - 仓内活引用已直接指向模块级路径，如
    `app.api.v1.endpoints.agent_tasks_findings`
- current behavior:
  - 两个 `__init__.py` 已从 repo 物理删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 package-shell retirement guard
- operational verification:
  - `uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py tests/test_agent_tasks_module_layout.py`
- 边界说明:
  - 这是空包壳退休，不是新的 Rust takeover
  - 本 slice 不改 `agent_tasks_findings.py` 的活逻辑与测试语义
- 后续修复波次: Wave A / API package cleanup
- owner: Rust migration

### 47. Empty `app/api/__init__.py` shell retired

- endpoint / feature:
  - Python package shell:
    - `backend_old/app/api/__init__.py`
- repo evidence before deletion:
  - 文件为空壳
  - 仓内未检到 `from app.api import ...` 或 `import app.api` 的活引用
- current behavior:
  - `backend_old/app/api/__init__.py` 已从 repo 物理删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已把 `app/api/__init__.py` 纳入退休守门
- operational verification:
  - `uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py`
- 边界说明:
  - 这是空包壳退休，不是新的 Rust takeover
  - 本 slice 不改 `backend_old/app/services/agent/task_findings.py` 或其他存活 helper
- 后续修复波次: Wave A / API package cleanup
- owner: Rust migration

### 48. `app/db/session.py` retired after DB-session caller set reached zero

- endpoint / feature:
  - Python DB session shell:
    - `backend_old/app/db/session.py`
- repo evidence before deletion:
  - `rg -n "from app\\.db\\.session import|app\\.db\\.session import|get_db|AsyncSessionLocal|async_session_factory" backend_old/app backend_old/tests backend_old/scripts -S`
    已经清零，说明 repo 内 live Python 路径不再依赖该模块
- current behavior:
  - `backend_old/app/db/session.py` 已从 repo 物理删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 DB session retirement guard
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已补“repo 内 live Python 模块不得再 import app.db.session”守门
- operational verification:
  - `uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py tests/test_config_internal_callers_use_service_layer.py`
  - `rg -n "from app\\.db\\.session import|app\\.db\\.session import|get_db|AsyncSessionLocal|async_session_factory" backend_old/app backend_old/tests backend_old/scripts -S`
- 边界说明:
  - 这是 dead DB session shell retirement，不是 `app.db.base` / Alembic ownership 已完成的信号
  - 本 slice 不处理 `backend_old/app/db/base.py`、`backend_old/alembic/env.py` 或 models 对 `Base` 的依赖
- 后续修复波次: Wave A / db shell cleanup
- owner: Rust migration

### 49. `app.db.base` import blocker cleared and shell retired

- endpoint / feature:
  - Python DB base shell:
    - `backend_old/app/db/base.py`
- repo evidence before deletion:
  - `rg -n "from app\\.db\\.base import Base|from app\\.db\\.base import|app\\.db\\.base" backend_old/alembic backend_old/app backend_old/tests -S`
    在切片前只剩 `backend_old/alembic/env.py`、`backend_old/tests/conftest.py` 与 `backend_old/app/models/*` 命中
- current behavior:
  - `Base` 宿主已迁到 `backend_old/app/models/base.py`
  - models、`alembic/env.py` 与 `tests/conftest.py` 已改为从 `app.models.base` 导入
  - `backend_old/app/db/base.py` 已从 repo 物理删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 DB base retirement guard
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已补“repo 内 live Python 模块不得再 import app.db.base”守门
- operational verification:
  - `uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py tests/test_config_internal_callers_use_service_layer.py`
  - `rg -n "from app\\.db\\.base import Base|from app\\.db\\.base import|app\\.db\\.base" backend_old/alembic backend_old/app backend_old/tests backend_old/scripts -S`
  - 已知主干历史问题：
    - `tests/test_alembic_project.py` 中对 linearized revision/head 的期望仍与当前仓库 revision 集合不一致；这是 Alembic 迁移链条既有差异，不是本 slice 的 import 回归
- 边界说明:
  - 这是 `app.db.base` import blocker 清零，不是整个 ORM / Alembic ownership 已完成
  - 本 slice 不处理 `schema_snapshots/*`、`backend_old/alembic/versions/*` 或 models 对 `Base.metadata` 的长期退休策略
- 后续修复波次: Wave A / db shell cleanup
- owner: Rust migration

### 46. `agent_tasks_findings.py` moved out of API path into `services/agent/task_findings.py`

- endpoint / feature:
  - Retained Python findings helper:
    - old path: `backend_old/app/api/v1/endpoints/agent_tasks_findings.py`
    - new path: `backend_old/app/services/agent/task_findings.py`
- repo evidence before move:
  - 源码已迁出后，仓内测试仍通过旧 import path 命中，
    进一步排查发现依赖的是 `backend_old/app/api/v1/endpoints/__pycache__/agent_tasks_findings.cpython-311.pyc`
    这类陈旧字节码，而不是 live source file
- current behavior:
  - `backend_old/app/api/v1/endpoints/agent_tasks_findings.py` 已从 repo 物理删除
  - 相关活测试已改为直连 `app.services.agent.task_findings`
  - `backend_old/tests/test_agent_tasks_module_layout.py`
    改为守住 retained findings helper 现在位于 `services/agent/task_findings.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 findings-module retirement guard
  - `backend_old/app/api/v1/endpoints/__pycache__` 已清理，避免 stale `.pyc` 造成假绿
- operational verification:
  - `uv run --project . pytest -s tests/test_agent_tasks_module_layout.py tests/test_api_router_rust_owned_routes_removed.py tests/test_agent_findings_persistence.py tests/test_agent_findings_strict_validation.py tests/test_agent_result_consistency.py tests/test_report_finding_update_flow.py tests/test_agent_title_normalization.py`
- 边界说明:
  - 这是 retained helper path migration，不是新的 Rust takeover
  - 本 slice 不改 `task_findings.py` 的 helper 语义，只修正宿主路径与测试引用
- 后续修复波次: Wave E / retained helper path cleanup
- owner: Rust migration

### 43. `rule_flows.py` transitional DTO host retired from API path

- endpoint / feature:
  - API-local transitional DTO host:
    - `backend_old/app/api/v1/schemas/rule_flows.py`
    - `backend_old/app/api/v1/schemas/__init__.py`
  - dead manual script:
    - `backend_old/tests/test_rule.py`
- repo evidence before deletion:
  - `rg -n "from app\\.api\\.v1\\.schemas\\.rule_flows import|app\\.api\\.v1\\.schemas" backend_old/app backend_old/tests backend_old/scripts -S`
    只剩 `app/services/rule.py` 与 `tests/test_rule.py` 的 `OpengrepRuleCreateRequest` 命中
  - `tests/test_rule.py` 是无断言的手工脚本式文件，不是稳定单元测试
- current behavior:
  - `OpengrepRuleCreateRequest` 已迁入 `backend_old/app/services/rule_contracts.py`
  - `backend_old/app/services/rule.py` 已改为从非 API 路径导入
  - `backend_old/app/api/v1/schemas/rule_flows.py` 与 `__init__.py` 已从 repo 物理删除
  - `backend_old/tests/test_rule.py` 已删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 `rule_flows.py` / `schemas/__init__.py` retirement guard
- operational verification:
  - `rg -n "from app\\.api\\.v1\\.schemas\\.rule_flows import|app\\.api\\.v1\\.schemas" backend_old/app backend_old/tests backend_old/scripts -S`
- 边界说明:
  - 这是 transitional DTO host retirement，不是新的 Rust rule-flow takeover
  - 本 slice 不处理 `app/services/rule.py` 的业务逻辑，只改 DTO 承载位置
- 后续修复波次: Wave A / API schema cleanup
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
