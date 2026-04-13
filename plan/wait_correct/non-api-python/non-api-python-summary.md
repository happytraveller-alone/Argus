# Non-API Python Migration Summary

- Total inventory: `211`
- `backend_old` root Python: `0`
- `backend_old/app` non-API Python: `211`
- `migrate_now`: `54`
- `migrate_with_api`: `191`
- `retire`: `3`
- `compat_only`: `7`

- Source migration plan:
  - `/Users/apple/Project/AuditTool_private/plan/backend_old_python_migration/2026-04-11-rust-backend-non-api-migration.md`

## Active Ledger

## 2026-04-11 Snapshot Refresh (Repo Facts)

- Route inventory (from `python-endpoints-inventory.csv`):
  - total: `179`
  - proxy: `114`
  - migrate: `38`
  - retire: `20`
  - defer: `7`
- Rust route ownership 已在 gateway 显式挂载：
  - `/api/v1/agent-tasks/*`
  - `/api/v1/agent-test/*`
  - `/api/v1/static-tasks/*`
- Rust proxy bridge 现状：
  - `backend/src/proxy.rs` 不存在
  - `backend/src/app.rs` 使用 `fallback 404`，不是 Python upstream proxy
- Compose 收口现状（Rust backend bridge 变量层）：
  - `docker-compose.yml` / `docker-compose.hybrid.yml` / `docker-compose.full.yml` 对 `backend-py` 无命中
  - `docker-compose.yml` / `docker-compose.hybrid.yml` / `docker-compose.full.yml` 对 `PYTHON_UPSTREAM_BASE_URL` 无命中
- 新 gate:
  - 三条 compose 链路清零 `backend-py` 与 `PYTHON_UPSTREAM_BASE_URL`
  - `rg -n "backend-py|PYTHON_UPSTREAM_BASE_URL" docker-compose*.yml backend/src -S` 不得出现 Python backend bridge 命中


### 1. non-api python inventory is not yet migrated

- current state:
  - Rust 已 owned `projects / system-config / search / skills`、`agent-tasks / agent-test / static-tasks` 路由组，以及新的 startup bootstrap shell
  - Python 仍拥有 schema/init_db/recovery/preflight、db/model/schema、runtime、upload、scan orchestration、llm、agent 主链路
- scope:
  - `backend_old/*.py`
  - `backend_old/app/**` except `backend_old/app/api/**`
- owner: Rust migration
- target phases:
  - A: bootstrap + core/db
  - B: models/schemas
  - C: shared services + upload
  - D: runtime + launchers
  - E: llm + agent
  - F: retire root diagnostics
- delete gate:
  - Rust 成为 source of truth
  - 运行主链路不再调用对应 Python 文件
  - `projects/system-config/skills` 的 Python mirror 已删除
  - `backend-py` service 与 `PYTHON_UPSTREAM_BASE_URL` 从 default/hybrid/full compose 全部删除

### 1a. Rust startup bootstrap is now partially owned

- current state:
  - `backend/src/bootstrap/mod.rs` 已负责最小启动检查
  - `backend/src/main.rs` 已在 `serve` 前执行 bootstrap
  - `/health` 已暴露 bootstrap 状态
  - Rust DB bootstrap 已同时具备两层状态判断：
    - Rust 自己依赖表是否齐全
    - legacy Python schema version 是否与 `backend_old/alembic/versions/*.py` 推导出的 expected heads 对齐
  - startup recovery / runner preflight 的 orchestration 已进入 Rust bootstrap
  - file-mode 下 Rust 已会初始化默认 control-plane config 和空项目存储
  - `backend/assets/scan_rule_assets/` 已成为 Rust 规则资产 root，并导入 `rust_scan_rule_assets`
  - Rust 已开始为当前 Rust-owned 控制面桥接所需的 legacy mirror 表执行 schema 兜底创建：
    - `users`
    - `user_configs`
    - `projects`
    - `project_info`
    - `project_management_metrics`
    - `prompt_skills`
  - startup init allowlist / denylist / defer-list 已显式写入 Rust policy
  - Gitleaks 已开始实际消费 Rust 规则资产库中的 builtin config
  - Opengrep 已开始实际消费 Rust 规则资产库中的 internal / patch 规则目录
  - Bandit 已开始实际消费 Rust 规则资产库中的 builtin snapshot
  - PMD 已开始实际消费 Rust 规则资产库中的 builtin XML rulesets
  - `/health` 中 `bootstrap.database.legacy_schema` 已会报告：
    - `expected_heads`
    - `current_versions`
    - `matches_expected_heads`
    - `error`
- still missing:
  - Rust 只接管了 legacy schema version 的检查与报告，还没有接管 migration 执行策略
  - Rust 目前只替代了当前 Rust-owned bridge 所需的一小部分 legacy schema，不是整个 `backend_old/alembic`
  - demo user / seed project / legacy rule bootstrap 的剩余 Rust 收口
  - recovery 对 legacy task tables 的依赖删除
  - runner preflight 后续与 Rust runtime 的进一步打通
  - 扫描引擎对 Rust 规则资产库的完整消费链路
  - `phpstan` 的规则消费接入
  - `yasa` 已从后续 Rust 迁移目标中移除，Rust 侧不再维护其规则资产和引擎调用
- owner: Rust migration
- target phase:
  - A now in progress

### 1b. Rust core config/security/encryption is now partially owned

- current state:
  - Rust 新增：
    - `backend/src/core/security.rs`
    - `backend/src/core/encryption.rs`
  - Rust `backend/src/config.rs` 已开始承接 core 级配置语义：
    - `SECRET_KEY` / `ALGORITHM` / `ACCESS_TOKEN_EXPIRE_MINUTES`
    - LLM 默认 provider/model/base URL 与超时/并发
    - provider 专属 API key 默认值
  - Rust `/api/v1/system-config/defaults` 已从 `AppConfig` 取默认值，不再散落硬编码
  - Rust 写 legacy `user_configs` mirror 时，敏感 LLM key 字段已按 Rust 加密逻辑落密文，而不是继续明文 shadow write
- still missing:
  - Python 运行时仍直接 import：
    - `backend_old/app/core/config.py`
    - `backend_old/app/core/security.py`
    - `backend_old/app/core/encryption.py`
  - 当前直接依赖方仍包括：
    - `backend_old/app/db/session.py`
    - `backend_old/app/services/user_config_service.py`
    - `backend_old/app/services/llm/*`
    - `backend_old/app/services/agent/*`
    - `backend_old/app/services/*runner*`
    - 多个 `static-tasks` / `agent-tasks` Python 端点
- delete gate:
  - Python runtime / llm / agent / init_db / db session 不再 import 这些 core 模块
  - Rust 成为 token/hash/encryption/default-config 的唯一 live source of truth
  - legacy `user_configs` mirror 不再被 Python runtime 当作主读路径
- owner: Rust migration
- target phase:
  - A now in progress

### 1c. Rust-owned scan rule assets now serve Python db consumers

- current state:
  - Python `backend_old/app/db` 资产读取已开始优先走 Rust 资产根：
    - `backend/assets/scan_rule_assets/rules_opengrep`
    - `backend/assets/scan_rule_assets/rules_from_patches`
    - `backend/assets/scan_rule_assets/patches`
    - `backend/assets/scan_rule_assets/gitleaks_builtin`
    - `backend/assets/scan_rule_assets/bandit_builtin`
    - `backend/assets/scan_rule_assets/rules_pmd`
  - `backend_old/app/db/__init__.py` 已新增统一 helper，供 Python live caller 读取 Rust-owned 资产根
  - 已切到 helper 的 Python 消费方包括：
    - `backend_old/app/services/gitleaks_rules_seed.py`
    - `backend_old/app/services/bandit_rules_snapshot.py`
    - `backend_old/app/services/pmd_rulesets.py`
  - 已删除 `backend_old/app/db` 下重复资产目录：
    - `rules`
    - `rules_from_patches`
    - `patches`
    - `gitleaks_builtin`
    - `bandit_builtin`
    - `rules_pmd`
- still missing:
  - `rules_phpstan` 仍由 Python static-tasks 直接消费，Rust 尚未接管 phpstan 运行链路，不能删
  - `yasa_builtin` 仍仅由 Python `yasa_rules_snapshot.py` 消费，Rust 明确未继续接管，不能删
  - `schema_snapshots/*` 仍是 Alembic baseline 兼容件，不能删
  - `base.py` / `session.py` 仍是 Python live 入口，不能删；路径归一化逻辑已迁入 `backend_old/app/services/scan_path_utils.py`
- delete gate:
  - `rules_phpstan` 只有在 Rust 真正接管 phpstan scanner/runtime 后才能删
  - `yasa_builtin` 只有在 YASA 彻底退出 Python live 路径或被完全 retire 后才能删
  - `schema_snapshots/*` 只有在 `backend_old/alembic` 不再依赖 baseline snapshot 时才能删
- owner: Rust migration
- target phase:
  - A / C in progress

### backend_old/app/db 迁移清单

为 Rust 完整替代 `backend_old/app/db`，需要依序过下列八个门。前两个门（env/config DB 拆分 与 startup/migration/health 分离）已经由 Rust 侧完成，但目录仍被多个 Python live 路径 import，所以尚不能删。

1. 环境/配置 DB 拆分（已完成）：Rust/Python 的 DB 环境 plumbing 已分离，`PYTHON_DB_*`、`PYTHON_ALEMBIC_ENABLED` 仅在 Python runtime 内使用，Rust 通过 `AppConfig` 直接读取 `DATABASE_URL` 并执行 schema 检查。
2. 启动/迁移/健康分离（已完成）：Rust `bootstrap` 负责 startup preflight、legacy schema 对齐与 `/health` 报告，Python 只再负责未迁出的 runtime 功能，确认 `bootstrap` 状态暴露与迁移 gating 覆盖后即可认定该门。
3. 替换 `app.db.base` ownership：验证命令是 `rg -n "from app\\.db\\.base import Base|from app\\.db\\.base import|app\\.db\\.base" backend_old/alembic backend_old/app backend_old/tests`。当前 blocker 是 `backend_old/alembic/env.py`、`backend_old/tests/conftest.py` 和 `backend_old/app/models/*`。翻门条件是这些命中清零或只剩待删历史文件；owner 是 Rust migration Phase A/B。
4. 替换 `app.db.session` 调用者：验证命令是 `rg -n "from app\\.db\\.session import|app\\.db\\.session import|get_db|AsyncSessionLocal|async_session_factory" backend_old/app backend_old/tests backend_old/scripts`。当前 blocker 已清零，说明 live Python 路径已不再依赖 `app.db.session`；后续只需继续用退休守门测试和 Rust 合同测试守住该状态；owner 是 Rust migration Phase A/D。
5. `init_db` 语义迁入 Rust：验证命令是 `rg -n "from app\\.db\\.init_db|import init_db|init_db\\(" backend_old/app backend_old/tests backend_old/scripts`。当前 blocker 已清零，说明 demo user、seed project、legacy rule seed、schema bootstrap 不再依赖 Python `init_db.py`；后续只需继续用 Rust bootstrap/preflight 合同测试守住该语义；owner 是 Rust migration Phase A。
6. 路径归一化 helper迁新家：验证命令是 `rg -n "scan_path_utils|normalize_scan_file_path|resolve_scan_finding_location" backend_old/app backend_old/tests`。当前 blocker 是 `agent_tasks_bootstrap.py`、`app/services/agent/bootstrap/phpstan.py`、`bandit.py`、`opengrep.py` 和 `tests/test_scan_path_utils.py`，它们都该 import `backend_old/app/services/scan_path_utils.py`；旧 `static_finding_paths.py` 不再命中；owner 是 Rust migration Phase C/D。
7. Alembic/schema_snapshots Removal Gate：验证命令是 `rg -n "schema_snapshots|baseline_5b0f3c9a6d7e|normalize_static_finding_paths" backend_old/alembic backend_old/tests`。当前 blocker 是 `backend_old/alembic/versions/5b0f3c9a6d7e_squashed_baseline.py`、`backend_old/alembic/versions/7f8e9d0c1b2a_normalize_static_finding_paths.py`、`backend_old/tests/test_alembic_project.py`。翻门条件是 Rust 完成 legacy baseline/schema compatibility 替代，命令不再命中 `schema_snapshots/*` 或 static-finding normalization 迁移，测试改写或删除；owner 是 Rust migration legacy-schema owner。
8. backend_old/app/db 最终删除门：验证命令依次是 `rg -n "app\\.db\\." backend_old/app backend_old/tests backend_old/alembic backend_old/scripts` 与 `rg --files backend_old/app/db`。当前 blocker 仍包括 `static_scan_runtime.py`、`agent_tasks_bootstrap.py`（执行/mixed-test helper 残留，scope filtering、bootstrap policy、bootstrap findings、Bandit bootstrap rule 选择、bootstrap seeds、bootstrap entrypoint fallback、Gitleaks bootstrap runtime 已迁入 `backend_old/app/services/agent/{scope_filters,bootstrap_policy,bootstrap_findings,bandit_bootstrap_rules,bootstrap_seeds,bootstrap_entrypoints,bootstrap_gitleaks_runner}.py`）、`backend_old/alembic/env.py` 和相关测试。翻门条件是第一条命令在 live 路径清零，第二条命令不再列出 live 模块，并且 Rust-only startup smoke/health 通过；owner 是整个 Rust migration owner。

Checklist 说明：`backend_old/app/db` 当前仍被 static/agent services、部分 FastAPI endpoints、测试等 import，因此该目录还不安全删除。

### 1d. phpstan db assets are now Rust-owned, YASA retirement is in progress

- current state:
  - Rust 已新增 `backend/src/scan/phpstan.rs` 并实际消费 `rules_phpstan/*`
  - Rust phpstan preflight 已通过 materialized asset 目录校验 snapshot 与 `rule_sources/`
  - `backend_old/app/db/rules_phpstan` 已删除，Python 继续从 Rust 资产根读取 phpstan snapshot / source files
  - YASA 相关 DB 资产、模型、service、launcher、route 已大幅删除
- still missing:
  - phpstan live API/runtime 仍由 Python 端持有
  - frontend live path 已完成去 YASA，但少量 mixed tests / inventory / 文本文档仍有残留
- delete gate:
  - phpstan 只有在 live runtime/API 也迁到 Rust 后，才算整条链完成
  - YASA 只有在 mixed tests、compose/build/inventory 文本残留全部清理后，才算 retire 完成
- owner: Rust migration
- target phase:
  - C / D in progress

### 1e. `backend_old/app/utils` fully retired from runtime

- current state:
  - Rust `backend/src/core/date_utils` 已直接替代原 Python `backend_old/app/utils/date_utils.py`，原 `backend_old/tests/test_date_utils.py` 已从树中删掉。
  - `repo_utils` 被正式 retire，远程仓库 handling no longer has a live runtime entry point to support it.
  - `utils/security` forwarding wrapper 退役，核心安全责任完全落到 Rust `backend/src/core/security.rs` 和 `backend/src/core/encryption.rs`。
  - `backend_old/app/utils` 目录已从 live Python runtime 中删除；唯一残留的 `app.utils` 文字仅藏在离线扫描规则补丁资产 `backend/assets/scan_rule_assets/patches/vuln-halo-d59877a9.patch`，那只是静态文本补丁，不会出现在运行时依赖路径。
  - operational verification:
    - `rg -n "app\\.utils|repo_utils|app\\.utils\\.security" backend_old/app backend_old/tests backend/src backend/assets/scan_rule_assets/patches`
    - expected state 是 live runtime/test 路径 `backend_old/app`、`backend_old/tests`、`backend/src` 全部 `0` 命中；唯一允许保留的命中是离线 patch 资产 `backend/assets/scan_rule_assets/patches/vuln-halo-d59877a9.patch`
- still missing:
  - none; 实际运行时 surface 已剥离。
- owner: Rust migration
- delete gate:
  - 运行时已确认无 `backend_old/app/utils` 依赖，剩余的文本只是离线 patch asset，不构成 runtime breakage。
  - 如果后续要清理这条 patch 文本残留，仍由 Rust migration owner 在 Phase F / retire cleanup 处理，不应把它误算成 live runtime blocker。
- target phase:
  - F / retire cleanup

### 1f. `backend_old/app/schemas` package retired; only `api/v1/schemas` survives as transitional DTO host

- current state:
  - `backend_old/app/schemas` package 已整体移除，`search`、`token`、`user`、`audit_rule`、`prompt_template` 以及 legacy `opengrep/gitleaks` schema 定义不再出现在 live Python tree。
  - 目前仍需要留存的 live rule-flow DTOs 暂存于 `backend_old/app/api/v1/schemas/rule_flows.py`，以 endpoint-local/API-local 方式承接过渡契约。
  - 这不等于 `static-tasks` 已被 Rust 全面接管；静态任务功能链路仍经由 Python runtime/bridge，因此 schema 的 retire 只是 ledger 记录，并不代表 static-tasks ownership 已完成。
  - operational verification:
    - `find backend_old/app -type d -name schemas -print | sort`
    - expected output: 仅 `backend_old/app/api/v1/schemas`，证明 `backend_old/app/schemas` 已经不在 live tree。
- still missing:
  - rule-flow DTOs 什么时候真正迁至 Rust 或可以在 Rust-owned bridge 被删除之前，`backend_old/app/api/v1/schemas/rule_flows.py` 还要继续作为过渡宿主。
- delete gate:
  - rule-flow DTOs 入 Rust 之后，重新执行 `find backend_old/app -type d -name schemas -print` 可以确认 transitional package 是否 safe to drop。
- owner: Rust migration

### 1g. `backend_old/app/runtime` removed; Rust runtime entrypoints now own the live startup/launcher surface

- current state:
  - `backend_old/app/runtime` 目录已删除
  - Rust 已新增：
    - `backend/src/runtime/bootstrap.rs`
    - `backend/src/bin/backend_runtime_startup.rs`
    - `backend/src/bin/opengrep_launcher.rs`
    - `backend/src/bin/phpstan_launcher.rs`
  - `docker/backend_old.Dockerfile` 与 `scripts/release-templates/backend.Dockerfile`
    已切到 `/usr/local/bin/backend-runtime-startup`
  - `docker/opengrep-runner.Dockerfile` 与 `docker/phpstan-runner.Dockerfile`
    已切到 Rust launcher binaries
  - Rust 测试 `backend/tests/runtime_env_bootstrap.rs` 已覆盖旧 `container_startup` 的 env bootstrap 语义
- operational verification:
  - `find backend_old/app -type d -name runtime -print`
  - `rg -n "app\\.runtime\\.|from app\\.runtime|import app\\.runtime|container_startup\\.py|opengrep_launcher\\.py|phpstan_launcher\\.py" backend_old backend docker scripts .github`
  - expected state:
    - 不再存在 `backend_old/app/runtime`
    - live runtime / Docker / tests 不再命中旧 Python runtime 路径
- still missing:
  - `scanner*`、`flow_parser*`、其余 runtime orchestration 仍主要在 Python 侧
  - `backend-py` 兼容服务仍存在，不能误判为 Python runtime 全量退休
- delete gate:
  - `app/runtime` 目录本身已经达到删除门
  - Phase D 其余 runtime/service 文件仍需继续迁
- owner: Rust migration
- target phase:
  - D in progress

### 1g. `backend_old/app/runtime` removed; Rust runtime entrypoints now own the live startup/launcher surface

- current state:
  - `backend_old/app/runtime` 目录已删除
  - Rust 已新增：
    - `backend/src/runtime/bootstrap.rs`
    - `backend/src/bin/backend_runtime_startup.rs`
    - `backend/src/bin/opengrep_launcher.rs`
    - `backend/src/bin/phpstan_launcher.rs`
  - `docker/backend_old.Dockerfile` 与 `scripts/release-templates/backend.Dockerfile`
    已切到 `/usr/local/bin/backend-runtime-startup`
  - `docker/opengrep-runner.Dockerfile` 与 `docker/phpstan-runner.Dockerfile`
    已切到 Rust launcher binaries
  - Rust 测试 `backend/tests/runtime_env_bootstrap.rs` 已覆盖旧 `container_startup` 的 env bootstrap 语义
- operational verification:
  - `find backend_old/app -type d -name runtime -print`
  - `rg -n "app\\.runtime\\.|from app\\.runtime|import app\\.runtime|container_startup\\.py|opengrep_launcher\\.py|phpstan_launcher\\.py" backend_old backend docker scripts .github`
  - expected state:
    - 不再存在 `backend_old/app/runtime`
    - live runtime / Docker / tests 不再命中旧 Python runtime 路径
- still missing:
  - `scanner*`、`flow_parser*`、其余 runtime orchestration 仍主要在 Python 侧
  - `backend-py` 兼容服务仍存在，不能误判为 Python runtime 全量退休
- delete gate:
  - `app/runtime` 目录本身已经达到删除门
  - Phase D 其余 runtime/service 文件仍需继续迁
- owner: Rust migration
- target phase:
  - D in progress

### 1h. project file-content cache is now Rust-owned; `zip_cache_manager.py` retired

- current state:
  - Rust 新增 `backend/src/project_file_cache.rs`
    - 提供 project file-content cache 的 TTL / LRU / memory stats / clear / invalidate
  - `backend/src/state.rs` 已挂载全局 `project_file_cache`
  - `backend/src/routes/projects.rs` 现在会对
    - `GET /projects/{id}/files/{*file_path}`
    - `GET /projects/cache/stats`
    - `POST /projects/cache/clear`
    - `POST /projects/{id}/cache/invalidate`
    执行真实 cache 行为，而不是返回固定占位值
  - archive 更新/删除会主动失效项目缓存
  - `backend_old/app/services/zip_cache_manager.py` 已删除
  - `backend_old/tests/test_zip_cache_manager.py` 已删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 `zip_cache_manager.py` 退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `4`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `229`
    - `rg -n "zip_cache_manager|ZipCacheManager" backend/src backend_old/app backend_old/tests -S`
      只剩退休守门测试命中
- still missing:
  - `zip_storage.py` 仍是 bridge：
    - `backend_old/app/services/upload/project_stats.py`
    - `backend_old/app/services/static_scan_runtime.py`
      仍依赖 ZIP 磁盘布局与 `ZIP_STORAGE_PATH`
  - frontend/upload contract 仍允许 `.tar/.tar.gz/.tar.bz2/.7z/.rar`，
    Rust `projects` 还只是 zip-only
  - `project_stats.py` 的 cloc / suffix fallback / LLM description 语义仍未被 Rust 等价接住
  - Rust 合同测试需要更高 toolchain；当前本机 `rustc 1.85.0` 无法跑通 `cargo test`
- delete gate:
  - `zip_cache_manager.py` 已达到删除门并已退休
  - broader upload/archive shared bridge 尚未达到删除门，不能把 `zip_storage.py`、
    `upload/*`、`project_stats.py` 误算成同一波退休
- owner: Rust migration
- target phase:
  - C in progress

### 1i. root diagnostics retired; `backend_old` root now only keeps `main.py`

- current state:
  - 已删除：
    - `backend_old/verify_llm.py`
    - `backend_old/check_docker_direct.py`
    - `backend_old/check_sandbox.py`
  - `backend_old/tests/test_legacy_backend_main_retired.py`
    已补 root diagnostics 退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `1`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `229`
    - `rg -n "verify_llm.py|check_docker_direct.py|check_sandbox.py" backend_old plan backend docker scripts .github -S`
      只剩退休守门测试与迁移文档命中
- still missing:
  - `backend_old/main.py` 仍存在，root bootstrap / diagnostics 还没有彻底清零
- delete gate:
  - 三条 diagnostics script 已达到删除门并已退休
  - `backend_old/main.py` 需要等 root bootstrap responsibility 全部收口到 Rust 后才能删
- owner: Rust migration
- target phase:
  - F in progress

### 1j. `backend_old/main.py` retired; root Python live surface is now zero

- current state:
  - `backend_old/main.py` 已删除
  - `backend_old/tests/test_legacy_backend_main_retired.py`
    已补 root `main.py` 退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `229`
    - `rg -n "backend_old/main.py|Hello from VulHunter-backend" backend_old backend docker scripts .github frontend plan -S`
      只剩迁移文档命中
- still missing:
  - non-API migration 主战场仍在 `app/core`、`app/db`、`upload`、`llm`、`agent`
- delete gate:
  - `backend_old/main.py` 已达到删除门并已退休
  - `backend_old` 根目录 Python live surface 已归零
- owner: Rust migration
- target phase:
  - F in progress

### 1k. `search_service.py` and `report_generator.py` retired from live tree

- current state:
  - 已删除：
    - `backend_old/app/services/search_service.py`
    - `backend_old/app/services/report_generator.py`
  - 已删除旧专属测试：
    - `backend_old/tests/test_search_service.py`
    - `backend_old/tests/test_report_generator_contract.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `227`
    - `rg -n "search_service.py|report_generator.py|SearchService|ReportGenerator" backend_old backend frontend plan -S`
      只剩退休守门测试、离线规则文本与迁移文档命中
- still missing:
  - Rust `search` 仍只有 project search 真正 owned，tasks/findings search 仍是空壳
  - `zip_storage.py`、`json_safe.py`、`runner_preflight.py` 仍在 `migrate_now` 集合
- delete gate:
  - `search_service.py` / `report_generator.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - C in progress

### 1l. `runner_preflight.py` retired; live preflight ownership stays in Rust bootstrap

- current state:
  - `backend_old/app/services/runner_preflight.py` 已删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `226`
    - `rg -n "runner_preflight.py|run_configured_runner_preflights|get_configured_runner_preflight_specs|RunnerPreflightSpec" backend_old backend plan scripts -S`
      live runtime 命中只剩 Rust `backend/src/bootstrap/preflight.rs` 与 release template helper
- still missing:
  - `zip_storage.py` 与 `json_safe.py` 仍在 `migrate_now` 集合
  - release template helper `scripts/release-templates/runner_preflight.py` 仍存在，但不属于 `backend_old` live service
- delete gate:
  - `runner_preflight.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - C in progress

### 1m. `opengrep_confidence.py` and `init_templates.py` retired from live tree

- current state:
  - 已删除：
    - `backend_old/app/services/opengrep_confidence.py`
    - `backend_old/app/services/init_templates.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `224`
    - `rg -n "opengrep_confidence.py|init_templates.py|init_templates_and_rules|normalize_confidence|extract_rule_lookup_keys" backend_old backend frontend plan -S`
      live caller 只剩 `agent/bootstrap/opengrep.py` 内联后的 confidence helper 与迁移文档命中
- still missing:
  - `zip_storage.py` 与 `json_safe.py` 仍在 `migrate_now`
  - `seed_archive.py`、`parser.py`、`rule.py`、`gitleaks_rules_seed.py`、`pmd_rulesets.py`、
    `bandit_rules_snapshot.py` 等仍在 `migrate_with_api`
- delete gate:
  - `opengrep_confidence.py` / `init_templates.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - C / D in progress

### 1n. `seed_archive.py` retired from live tree

- current state:
  - `backend_old/app/services/seed_archive.py` 已删除
  - `backend_old/tests/test_seed_archive.py` 已删除
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `223`
    - `rg -n "seed_archive.py|build_seed_archive_candidates|download_seed_archive" backend_old backend frontend plan -S`
      只剩退休守门测试与迁移文档命中
- still missing:
  - `zip_storage.py` 与 `json_safe.py` 仍在 `migrate_now`
  - `gitleaks_rules_seed.py`、`pmd_rulesets.py`、`parser.py`、`rule.py`、
    `bandit_rules_snapshot.py` 等仍在 `migrate_with_api`
- delete gate:
  - `seed_archive.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - C in progress

### 1o. `zip_storage.py` and `upload/*` retired from live tree

- current state:
  - 已删除：
    - `backend_old/app/services/zip_storage.py`
    - `backend_old/app/services/upload/compression_factory.py`
    - `backend_old/app/services/upload/compression_handlers.py`
    - `backend_old/app/services/upload/compression_strategy.py`
    - `backend_old/app/services/upload/language_detection.py`
    - `backend_old/app/services/upload/project_stats.py`
    - `backend_old/app/services/upload/upload_manager.py`
  - 已删除旧专属测试：
    - `backend_old/tests/test_llm_description.py`
    - `backend_old/tests/test_cloc_stats.py`
    - `backend_old/tests/test_project_stats_suffix_fallback.py`
    - `backend_old/tests/test_file_upload_compress.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `216`
    - `rg -n "zip_storage.py|get_project_zip_path|project_stats.py|generate_project_description|get_cloc_stats_from_archive|UploadManager|CompressionStrategyFactory|compression_handlers.py|compression_strategy.py|language_detection.py" backend_old backend frontend plan -S`
      live caller 命中只剩 Rust `projects` 路由、退休守门测试与迁移文档
- still missing:
  - frontend 当前仍允许非 zip archive 后缀，但 Rust `projects` 仍是 zip-only contract
  - `json_safe.py` 仍在 `migrate_now`
- delete gate:
  - `zip_storage.py` / `upload/*` / `project_stats.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - C in progress

### 1p. `scanner.py` and `gitleaks_rules_seed.py` retired from live tree

- current state:
  - 已删除：
    - `backend_old/app/services/scanner.py`
    - `backend_old/app/services/gitleaks_rules_seed.py`
  - 已删除旧专属测试：
    - `backend_old/tests/test_file_selection.py`
    - `backend_old/tests/test_file_selection_e2e.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `214`
    - `rg -n "from app\\.services\\.scanner import|import app\\.services\\.scanner|is_text_file\\(|should_exclude\\(|EXCLUDE_PATTERNS|from app\\.services\\.gitleaks_rules_seed import|import app\\.services\\.gitleaks_rules_seed|ensure_builtin_gitleaks_rules\\(" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已清零，只剩退休守门测试与迁移文档
- still missing:
  - `json_safe.py`、`parser.py`、`flow_parser_runtime.py`、`flow_parser_runner.py`、
    `scanner_runner.py`、`static_scan_runtime.py` 等仍有 live caller
- delete gate:
  - `scanner.py` / `gitleaks_rules_seed.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - C / D in progress

### 1q. `project_test_service.py` retired; helper absorbed into `skill_test_runner.py`

- current state:
  - `backend_old/app/services/project_test_service.py` 已删除
  - `normalize_extracted_project_root` 已回收到
    `backend_old/app/services/agent/skill_test_runner.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已改为要求 `skill_test_runner.py` 本地持有该 helper
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
    - `rg -n "project_test_service|normalize_extracted_project_root" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已收口到 `skill_test_runner.py` 与退休守门测试
- still missing:
  - `json_safe.py`、`parser.py`、`flow_parser_runtime.py`、`flow_parser_runner.py`、
    `scanner_runner.py`、`static_scan_runtime.py`、`user_config_service.py` 等仍有 live caller
- delete gate:
  - `project_test_service.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - E cleanup in progress

### 1r. `flow_parser_runtime.py` retired; provider absorbed into `agent/flow/lightweight`

- current state:
  - `backend_old/app/services/flow_parser_runtime.py` 已删除
  - definition-provider 逻辑已迁入
    `backend_old/app/services/agent/flow/lightweight/definition_provider.py`
  - `backend_old/app/services/agent/flow/lightweight/ast_index.py`
    已改为从 lightweight 域内 import provider
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
    - `rg -n "flow_parser_runtime|get_default_definition_provider|DefinitionProvider|HybridDefinitionProvider|RunnerDefinitionProvider|LocalDefinitionProvider" backend_old/app backend_old/tests -S`
      live caller 已收口到 `agent/flow/lightweight` 域内
- still missing:
  - `parser.py`、`flow_parser_runner.py`、`scanner_runner.py`、`static_scan_runtime.py` 等仍有 live caller
- delete gate:
  - `flow_parser_runtime.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - D / E cleanup in progress

### 1s. `parser.py` retired; tree-sitter parser absorbed into `agent/flow/lightweight`

- current state:
  - `backend_old/app/services/parser.py` 已删除
  - `TreeSitterParser` 已迁入
    `backend_old/app/services/agent/flow/lightweight/tree_sitter_parser.py`
  - `ast_index.py`、`function_locator.py`、`definition_provider.py`
    已改为从 lightweight 域内 import
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
    - `rg -n "from app\\.services\\.parser import|import app\\.services\\.parser|TreeSitterParser" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已收口到 `agent/flow/lightweight` 域内
- still missing:
  - `flow_parser_runner.py`、`scanner_runner.py`、`static_scan_runtime.py`、`json_safe.py`、`user_config_service.py` 等仍有 live caller
- delete gate:
  - `parser.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - D / E cleanup in progress

### 1t. `sandbox_runner_client.py` retired from top-level; helper absorbed into `agent/tools`

- current state:
  - 顶层 `backend_old/app/services/sandbox_runner_client.py` 已迁入
    `backend_old/app/services/agent/tools/sandbox_runner_client.py`
  - `sandbox_tool.py` 已改为从 agent/tools 域内 import
  - `backend_old/tests/test_sandbox_runner_client.py`
    已同步指向新模块路径
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
    - `rg -n "sandbox_runner_client|SandboxRunnerClient" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已收口到 `agent/tools` 域内与测试
- still missing:
  - `scanner_runner.py`、`static_scan_runtime.py`、`json_safe.py`、`user_config_service.py` 等仍有 live caller
- delete gate:
  - 顶层 `sandbox_runner_client.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - D / E cleanup in progress

### 1u. `backend_venv.py` retired; helper absorbed into `static_scan_runtime.py`

- current state:
  - `backend_old/app/services/backend_venv.py` 已删除
  - helper 已内聚回 `backend_old/app/services/static_scan_runtime.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `212`
    - `rg -n "backend_venv|build_backend_venv_env|resolve_backend_venv_executable|get_backend_venv_path|get_backend_venv_bin_dir" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已收口到 `static_scan_runtime.py`、退休守门测试与 Rust runtime/bootstrap
- still missing:
  - `scanner_runner.py`、`static_scan_runtime.py`、`json_safe.py`、`user_config_service.py` 等仍有 live caller
- delete gate:
  - `backend_venv.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - D cleanup in progress

### 1v. `user_config_service.py` retired; helper absorbed into `static_scan_runtime.py`

- current state:
  - `backend_old/app/services/user_config_service.py` 已删除
  - 用户配置默认值/解密/清洗/effective merge 逻辑已内聚回
    `backend_old/app/services/static_scan_runtime.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已改为要求 `static_scan_runtime.py` 本地持有 `_load_effective_user_config`
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
    - `rg -n "user_config_service|load_effective_user_config|_load_effective_user_config|sanitize_other_config|strip_runtime_config|_default_user_config" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已收口到 `static_scan_runtime.py` 与退休守门测试
- still missing:
  - `scanner_runner.py`、`static_scan_runtime.py`、`json_safe.py` 等仍有 live caller
- delete gate:
  - `user_config_service.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - D / config cleanup in progress

### 1w. `json_safe.py` retired from top-level; helper absorbed into `agent/`

- current state:
  - 顶层 `backend_old/app/services/json_safe.py` 已迁入
    `backend_old/app/services/agent/json_safe.py`
  - agent caller 已改为域内 import
  - `backend_old/tests/test_json_safe.py` 已同步指向新模块路径
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
    - `rg -n "from app\\.services\\.json_safe import|import app\\.services\\.json_safe|dump_json_safe|normalize_json_safe" backend_old/app backend_old/tests -S`
      live caller 已收口到 agent 域内与测试
- still missing:
  - `flow_parser_runner.py`、`scanner_runner.py`、`static_scan_runtime.py` 等仍有 live caller
- delete gate:
  - 顶层 `json_safe.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - E cleanup in progress

### 2. current Rust mirrors and proxy remain transitional

- current state:
  - `backend/src/routes/projects.rs` 仍有 Python project mirror
  - `backend/src/routes/system_config.rs` 仍有 Python user-config mirror
  - `backend/src/routes/skills.rs` 不是简单 mirror，legacy `prompt_skills` 和 `user_configs.other_config` 仍是主存储
  - `backend/src/proxy.rs` 仍承接未迁移 `/api/v1/*`
- owner: Rust migration
- delete gate:
  - `static-tasks` / `agent-tasks` 以及对应 runtime、llm、agent 内核全部 Rust-owned

### 3. search is only partially migrated

- current state:
  - project search 已 Rust-owned
  - agent/static task 与 finding search 已接到 Rust task-state 数据，不再是空壳
  - rule 维度搜索仍未进入 Rust search 结果
- owner: Rust migration
- delete gate:
  - 任务、finding、规则等搜索索引和查询模型迁到 Rust domain / db 层
