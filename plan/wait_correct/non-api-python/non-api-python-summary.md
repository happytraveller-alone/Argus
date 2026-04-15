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
  - `app.models.base` / Alembic / tests 仍在持有 SQLAlchemy metadata；`session.py` 已在 live caller 清零后退休；路径归一化逻辑已迁入 `backend_old/app/services/scan_path_utils.py`
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
3. 替换 `app.db.base` ownership（已完成）：验证命令是 `rg -n "from app\\.db\\.base import Base|from app\\.db\\.base import|app\\.db\\.base" backend_old/alembic backend_old/app backend_old/tests`。当前该命令已清零；`Base` 宿主已迁到 `backend_old/app/models/base.py`，`backend_old/app/db/base.py` 已退休；owner 是 Rust migration Phase A/B。
4. 替换 `app.db.session` 调用者：验证命令是 `rg -n "from app\\.db\\.session import|app\\.db\\.session import|get_db|AsyncSessionLocal|async_session_factory" backend_old/app backend_old/tests backend_old/scripts`。当前 blocker 已清零，说明 live Python 路径已不再依赖 `app.db.session`；后续只需继续用退休守门测试和 Rust 合同测试守住该状态；owner 是 Rust migration Phase A/D。
5. `init_db` 语义迁入 Rust：验证命令是 `rg -n "from app\\.db\\.init_db|import init_db|init_db\\(" backend_old/app backend_old/tests backend_old/scripts`。当前 blocker 已清零，说明 demo user、seed project、legacy rule seed、schema bootstrap 不再依赖 Python `init_db.py`；后续只需继续用 Rust bootstrap/preflight 合同测试守住该语义；owner 是 Rust migration Phase A。
6. 路径归一化 helper迁新家：验证命令是 `rg -n "scan_path_utils|normalize_scan_file_path|resolve_scan_finding_location" backend_old/app backend_old/tests`。当前 blocker 是 `agent_tasks_bootstrap.py`、`app/services/agent/bootstrap/phpstan.py`、`bandit.py`、`opengrep.py` 和 `tests/test_scan_path_utils.py`，它们都该 import `backend_old/app/services/scan_path_utils.py`；旧 `static_finding_paths.py` 不再命中；owner 是 Rust migration Phase C/D。
7. Alembic/schema_snapshots Removal Gate：验证命令是 `rg -n "schema_snapshots|baseline_5b0f3c9a6d7e|normalize_static_finding_paths" backend_old/alembic backend_old/tests`。当前 blocker 是 `backend_old/alembic/versions/5b0f3c9a6d7e_squashed_baseline.py`、`backend_old/alembic/versions/7f8e9d0c1b2a_normalize_static_finding_paths.py`、`backend_old/tests/test_alembic_project.py`。翻门条件是 Rust 完成 legacy baseline/schema compatibility 替代，命令不再命中 `schema_snapshots/*` 或 static-finding normalization 迁移，测试改写或删除；owner 是 Rust migration legacy-schema owner。
8. backend_old/app/db 最终删除门：验证命令依次是 `rg -n "app\\.db\\." backend_old/app backend_old/tests backend_old/alembic backend_old/scripts` 与 `rg --files backend_old/app/db`。当前 blocker 仍包括 `agent_tasks_bootstrap.py`（执行/mixed-test helper 残留，scope filtering、bootstrap policy、bootstrap findings、Bandit bootstrap rule 选择、bootstrap seeds、bootstrap entrypoint fallback、Gitleaks bootstrap runtime 已迁入 `backend_old/app/services/agent/{scope_filters,bootstrap_policy,bootstrap_findings,bandit_bootstrap_rules,bootstrap_seeds,bootstrap_entrypoints,bootstrap_gitleaks_runner}.py`）、`backend_old/alembic/env.py` 和相关测试。`static_scan_runtime.py` 已在 2026-04-14 的 dead-shell retirement slice 中退休，不再计入当前 blocker。翻门条件是第一条命令在 live 路径清零，第二条命令不再列出 live 模块，并且 Rust-only startup smoke/health 通过；owner 是整个 Rust migration owner。

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

### 1f. `backend_old/app/schemas` package retired; API-local `rule_flows.py` host also retired

- current state:
  - `backend_old/app/schemas` package 已整体移除，`search`、`token`、`user`、`audit_rule`、`prompt_template` 以及 legacy `opengrep/gitleaks` schema 定义不再出现在 live Python tree。
  - `backend_old/app/api/v1/schemas/rule_flows.py` 也已删除；仍存活的 `OpengrepRuleCreateRequest` 已迁入 `backend_old/app/services/rule_contracts.py`，不再作为 API-local DTO 宿主保留。
  - 这不等于 `static-tasks` 已被 Rust 全面接管；静态任务功能链路仍经由 Python runtime/bridge，因此 schema host 的 retire 只是 ledger 记录，并不代表 static-tasks ownership 已完成。
  - operational verification:
    - `find backend_old/app -type d -name schemas -print | sort`
    - expected output: 不再出现 live Python schema package；若目录仍存在，也不应再包含 `rule_flows.py` 或 `__init__.py`
- still missing:
  - none for this transitional host；后续若有 rule-flow DTO 需求，应直接落到非 API 路径或 Rust-owned contract。
- delete gate:
  - `rg -n "app\\.api\\.v1\\.schemas\\.rule_flows|from app\\.api\\.v1\\.schemas import" backend_old/app backend_old/tests backend_old/scripts -S` 持续为空。
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
    - `rg -n "from app\\.services\\.scanner_runner import|import app\\.services\\.scanner_runner|from app\\.services import scanner_runner" backend_old/app backend_old/tests -S`
      => no matches
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

### 1x. `flow_parser_runner.py` retired from top-level; helper absorbed into `agent/flow`

- current state:
  - 顶层 `backend_old/app/services/flow_parser_runner.py` 已迁入
    `backend_old/app/services/agent/flow/flow_parser_runner.py`
  - agent/flow 与 skill-test caller 已改为域内 import
  - `backend_old/tests/test_flow_parser_runner_client.py`
    已同步指向新模块路径
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
    - `rg -n "from app\\.services\\.flow_parser_runner import|import app\\.services\\.flow_parser_runner|get_flow_parser_runner_client|FlowParserRunnerClient" backend_old/app backend_old/tests -S`
      live caller 已收口到 agent/flow 域内与测试
- still missing:
  - `scanner_runner.py`、`static_scan_runtime.py` 等仍有 live caller
- delete gate:
  - 顶层 `flow_parser_runner.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - D / E cleanup in progress

### 1y. `scanner_runner.py` retired from top-level; helper absorbed into `agent/`

- current state:
  - 顶层 `backend_old/app/services/scanner_runner.py` 已迁入
    `backend_old/app/services/agent/scanner_runner.py`
  - bandit / opengrep / phpstan / gitleaks bootstrap、
    `agent/flow/flow_parser_runner.py`、`agent/tools/external_tools.py`、
    `static_scan_runtime.py` 已改为域内 import
  - `backend_old/tests/test_scanner_runner.py`
    已同步指向新模块路径
  - `backend_old/tests/test_flow_parser_runner_client.py`
    已改为 monkeypatch live agent.flow 模块路径
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
- still missing:
  - `static_scan_runtime.py` 等仍有 live caller
- delete gate:
  - 顶层 `scanner_runner.py` 已达到删除门并已退休
- owner: Rust migration
- target phase:
  - D / E cleanup in progress

### 1z. workspace helper cluster extracted from `static_scan_runtime.py` into `agent/scan_workspace.py`

- current state:
  - `static_scan_runtime.py` 顶部 workspace/helper cluster 已迁入
    `backend_old/app/services/agent/scan_workspace.py`
  - 已迁移的 helper 包括：
    - `_scan_workspace_root`
    - `ensure_scan_workspace`
    - `ensure_scan_project_dir`
    - `ensure_scan_output_dir`
    - `ensure_scan_logs_dir`
    - `ensure_scan_meta_dir`
    - `cleanup_scan_workspace`
    - `copy_project_tree_to_scan_dir`
  - live caller 已改为 agent 域共享 import：
    - `agent/bootstrap/bandit.py`
    - `agent/bootstrap/opengrep.py`
    - `agent/bootstrap/phpstan.py`
    - `agent/bootstrap_gitleaks_runner.py`
  - `backend_old/tests/test_static_scan_runtime.py`
    已直接覆盖新模块的 helper 契约
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已补 import guard，防止 workspace helper 回流到 `static_scan_runtime.py`
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `212`
    - `rg -n "from app\\.services\\.static_scan_runtime import|import app\\.services\\.static_scan_runtime|static_scan_runtime\\.(ensure_scan_workspace|ensure_scan_project_dir|ensure_scan_output_dir|ensure_scan_logs_dir|ensure_scan_meta_dir|cleanup_scan_workspace|copy_project_tree_to_scan_dir)" backend_old/app backend_old/tests -S`
      只剩 `test_config_internal_callers_use_service_layer.py` 的负向断言文本
- still missing:
  - `static_scan_runtime.py` 仍是 live runtime bridge，尚未迁出的能力至少包括：
    - ZIP bridge / `_get_project_root`
    - backend venv helper
    - process/container cancel & tracking
    - progress store
    - user config / LLM validation
- delete gate:
  - `agent/scan_workspace.py` 当前是 live shared module，不进入删除门
  - `static_scan_runtime.py` 只有在剩余 runtime/config/ZIP 能力继续拆空后，才可进入退休门
- owner: Rust migration
- target phase:
  - D / E cleanup in progress

### 1aa. task-tracking and cancellation cluster extracted from `static_scan_runtime.py` into `agent/scan_tracking.py`

- current state:
  - `static_scan_runtime.py` 中 task-tracking / cancellation cluster 已迁入
    `backend_old/app/services/agent/scan_tracking.py`
  - 已迁移的 helper/state 包括：
    - `_static_scan_process_lock`
    - `_static_running_scan_processes`
    - `_static_running_scan_containers`
    - `_static_cancelled_scan_tasks`
    - `_static_background_jobs`
    - `_scan_task_key`
    - `_register_static_background_job`
    - `_pop_static_background_job`
    - `_get_static_background_job`
    - `_launch_static_background_job`
    - `_shutdown_static_background_jobs`
    - `_is_scan_task_cancelled`
    - `_clear_scan_task_cancel`
    - `_register_scan_container`
    - `_pop_scan_container`
    - `_stop_scan_container`
    - `_request_scan_task_cancel`
    - `_is_scan_process_active`
    - `_terminate_scan_process`
    - `_run_subprocess_with_tracking`
  - `backend_old/app/services/static_scan_runtime.py`
    已改为显式 import 该 cluster，不再本地持有 duplicate state
  - `backend_old/tests/test_static_scan_runtime.py`
    与 `backend_old/tests/test_background_task_launch_refactor.py`
    已直接覆盖 `agent/scan_tracking.py` 契约
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已补 AST import/ownership guard，要求 `static_scan_runtime.py`
    从 `app.services.agent.scan_tracking` 导入整组 helper/state
  - verification:
    - `uv run --project . pytest -s tests/test_static_scan_runtime.py tests/test_background_task_launch_refactor.py tests/test_config_internal_callers_use_service_layer.py tests/test_scanner_runner.py`
      => `22 passed`
    - `rg -n "static_scan_runtime\\.(?:_scan_task_key|_register_static_background_job|_pop_static_background_job|_get_static_background_job|_launch_static_background_job|_shutdown_static_background_jobs|_is_scan_task_cancelled|_clear_scan_task_cancel|_register_scan_container|_pop_scan_container|_stop_scan_container|_request_scan_task_cancel|_is_scan_process_active|_terminate_scan_process|_run_subprocess_with_tracking)|from app\\.services\\.static_scan_runtime import|import app\\.services\\.static_scan_runtime" backend_old/app backend_old/tests -S`
      => `0` live matches
  - repo facts refresh:
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
- still missing:
  - `static_scan_runtime.py` 仍是 live runtime bridge，尚未迁出的能力至少包括：
    - ZIP bridge / `_get_project_root`
    - backend venv helper
    - progress store
    - user config / LLM validation
- delete gate:
  - `agent/scan_tracking.py` 当前是 live shared module，不进入删除门
  - `static_scan_runtime.py` 只有在剩余 runtime/config/ZIP 能力继续拆空后，才可进入退休门
- owner: Rust migration
- target phase:
  - D / E cleanup in progress

### 1ab. `static_scan_runtime.py` retired as a dead shell, not as a Rust takeover milestone

- current state:
  - repo 内删除前证据显示：
    - `rg -n "from app\\.services\\.static_scan_runtime import|import app\\.services\\.static_scan_runtime|static_scan_runtime\\." backend_old/app backend_old/tests -S`
      只剩测试命中，没有 live Python caller
    - `rg -n "importlib\\.(import_module|__import__)\\(|__import__\\(|app\\.services\\.static_scan_runtime|services/static_scan_runtime\\.py|static_scan_runtime" backend_old/app backend_old/scripts backend_old/tests -S`
      只剩测试与迁移文本，没有动态导入或脚本入口证据
  - `backend_old/app/services/static_scan_runtime.py` 已删除
  - `backend_old/tests/test_static_scan_runtime.py`
    继续覆盖 `agent/scan_workspace.py` 与 `agent/scan_tracking.py` 契约，不再 import 退休模块
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    现在守住“repo 内 live Python 模块不得 import `static_scan_runtime`”
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    现在守住 `backend_old/app/services/static_scan_runtime.py` 物理不存在
  - verification:
    - `uv run --project . pytest -s tests/test_static_scan_runtime.py tests/test_background_task_launch_refactor.py tests/test_config_internal_callers_use_service_layer.py tests/test_scanner_runner.py tests/test_api_router_rust_owned_routes_removed.py`
      => `54 passed, 1 warning`
    - warning 备注：
      `app/services/agent/knowledge/vulnerabilities/open_redirect.py:12`
      存在未触及的既有 `DeprecationWarning: invalid escape sequence '\/'`
- current meaning:
  - 这是 dead shell retirement：删除的是一个已经脱离 repo 内 live runtime 的顶层 Python 壳
  - 这不表示 Rust 新接管了 `static-tasks` runtime，也不表示 route inventory 或静态任务响应契约发生变化
  - 本条覆盖 1z/1aa 中“`static_scan_runtime.py` 仍是 live runtime bridge”的旧判断；那些判断保留为历史切片，不再代表当前事实
- delete gate:
  - 当前删除门只基于 repo 内证据成立；如果仓外还有未登记调用方，需要开发者另行指出
- owner: Rust migration
- target phase:
  - D / E cleanup in progress

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

### 4. default skills catalog/detail now expose prompt-effective, while external-tools compat remains separate

- current state:
  - Rust `GET /api/v1/skills/catalog` 默认返回：
    - scan-core entries
    - `prompt-<agent_key>@effective` unified prompt entries
  - Rust `GET /api/v1/skills/catalog?resource_mode=external_tools`
    继续返回前端外部工具页当前依赖的 compat resource list：
    - scan-core resource
    - `prompt-builtin`
    - `prompt-custom`
  - Rust `GET /api/v1/skills/{id}` 已支持 prompt-effective detail：
    - `display_name`
    - `kind=prompt`
    - `source=prompt_effective`
    - `agent_key`
    - `runtime_ready`
    - `reason`
    - `load_mode`
    - `effective_content`
    - `prompt_sources`
  - effective prompt merge 现已固定：
    - builtin template
    - active global custom prompt
    - active agent-specific custom prompt
  - custom prompt merge 顺序已去存储后端耦合：
    - `created_at` 升序
    - `id` tie-break
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
- verification:
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
      的 multipart helper 已补 quoted-string 转义
    - `cd backend && cargo test --test projects_api download_project_archive_supports_utf8_filenames -- --exact --nocapture`
      => `1 passed`
- current meaning:
  - 这一步推进的是 Rust `skills` surface contract，不是 prompt skill storage ownership 完成
  - 默认 unified catalog 与 external-tools compat catalog 现在边界明确，不再混成同一份 prompt 资源列表
  - 这一步让 prompt-effective 进入 Rust 默认 detail surface，但并未改变 frontend 仍依赖 `/skills/resources/*` 的事实
  - 当前 backend gate 已恢复绿色，后续 slice 可以继续在此基线上推进
- still missing:
  - DB 模式下 custom prompt skills 仍直接读 legacy `prompt_skills`
  - DB 模式下 builtin prompt state 仍直接读 `user_configs.other_config`
  - `use_prompt_skills -> config.prompt_skills` 的 live producer owner 仍未完全收口到 Rust
  - `/skills/{id}/test` 与 `/tool-test` 仍只是 scan-core compat stub
  - `skill_selection` / runtime session / guard / workflow registry 仍未进入 live code path
- owner: Rust migration
- target phase:
  - E in progress

### 5. prompt-skill persistence boundary is now Rust-native, with legacy storage downgraded to compat mirror

- current state:
  - Rust 已新增 Rust-native 主存储：
    - `rust_prompt_skills`
    - `rust_prompt_skill_builtin_states`
  - Rust 已新增：
    - `backend/src/db/prompt_skills.rs`
  - `backend/src/routes/skills.rs` 在 DB mode 下：
    - custom prompt skills 读取已改走 Rust-native store
    - builtin prompt state 读取已改走 Rust-native store
    - create / update / delete / builtin toggle
      已改走记录级 DB helper
    - Rust-native 写入与 legacy mirror 写回
      已收进同一事务
  - startup init 现在会在 Rust DB ready 且 Rust-native 为空时做一次 compat backfill：
    - 从 legacy `prompt_skills` 导入 custom prompt skills
    - 从 legacy `user_configs.other_config.promptSkillBuiltinState`
      导入 builtin state
    - 已有 Rust-native 数据时不覆盖
  - bootstrap required rust tables 现已包含：
    - `rust_prompt_skills`
    - `rust_prompt_skill_builtin_states`
  - `skills` 分页 total 现已改成分页前总匹配数，不再等于当前页条数
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
- verification:
  - `cd backend && cargo test --test skills_api`
    => `7 passed`
  - `cd backend && cargo build --bin backend-rust`
    => exit `0`
  - `cd backend && cargo test`
    => exit `0`
    - `64 passed`
- current meaning:
  - 这一步把 custom prompt skills / builtin prompt state 的 steady-state DB read owner 收回到 Rust
  - 这一步把 legacy `prompt_skills` / `user_configs.other_config` 从主存储降级成 compat mirror
  - 这一步仍未让 Python agent runtime 直接退出 prompt skill 消费链；它们仍读取 `config.prompt_skills`
- still missing:
  - `use_prompt_skills -> config.prompt_skills` 的 live producer 还没有明确迁到 Rust
  - compat mirror 仍未删除
  - 真正的 runtime session / skill_selection / guard 仍未进入 live code path
- owner: Rust migration
- target phase:
  - E in progress

### 6. dead Python prompt-skill helper has been retired

- current state:
  - `backend_old/app/services/agent/skills/prompt_skills.py`
    已删除
  - `backend_old/app/services/agent/skills/__init__.py`
    不再转出 retired helper
  - `backend_old/tests/test_prompt_skills_module.py`
    已删除；其原本只覆盖 dead helper 内部实现
  - `backend_old/tests/agent/test_prompt_skills_injection.py`
    已改为局部 fixture，不再 import retired helper
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `212`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k prompt_skills tests/test_config_internal_callers_use_service_layer.py -k prompt_skills`
    => `2 passed`
  - `cd backend_old && uv run --project . pytest -s tests/agent/test_prompt_skills_injection.py -k 'not verification' tests/test_api_router_rust_owned_routes_removed.py tests/test_config_internal_callers_use_service_layer.py`
    => `63 passed, 2 deselected, 4 warnings`
- current meaning:
  - 这是 dead helper retirement，不是新的 Rust runtime takeover
  - Python agents 仍读取 `config.prompt_skills`，但不再依赖 `app.services.agent.skills.prompt_skills` helper
- still missing:
  - `use_prompt_skills -> config.prompt_skills` 的 live producer 仍未明确
  - prompt skill runtime 主链路仍未完全 Rust-owned
- owner: Rust migration
- target phase:
  - E in progress

### 7. dead Python skill resource catalog helper has been retired

- current state:
  - `backend_old/app/services/agent/skills/resource_catalog.py`
    已删除
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'prompt_skills or resource_catalog' tests/test_config_internal_callers_use_service_layer.py -k 'prompt_skills or resource_catalog'`
    => `4 passed, 52 deselected, 2 warnings`
- current meaning:
  - 这是 dead helper retirement，不是新的 Rust runtime takeover
  - `agent/skills` 目录里进一步收口，只剩 live scan-core surface 与 package 壳
- still missing:
  - `use_prompt_skills -> config.prompt_skills` 的 live producer 仍未明确
  - `skill_test_runner.py` 是否还属于 retained live helper 仍待核验
- owner: Rust migration
- target phase:
  - E in progress

### 8. dead Python skill-test runner helper has been retired

- current state:
  - `backend_old/app/services/agent/skill_test_runner.py`
    已删除
  - 只覆盖该 dead helper 的测试已删除：
    - `backend_old/tests/test_skill_test_project_lifecycle.py`
    - `backend_old/tests/test_structured_tool_test_runner.py`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `210`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'prompt_skills or resource_catalog or skill_test_runner' tests/test_config_internal_callers_use_service_layer.py -k 'prompt_skills or resource_catalog or skill_test_runner'`
    => `6 passed, 51 deselected, 3 warnings`
- current meaning:
  - 这是 dead helper / dead test retirement，不是新的 Rust runtime takeover
  - 只能说明 repo 内已无 live caller，不说明 Rust skill-test runtime 已等价接管
- still missing:
  - skill-test runtime 是否要做真正 Rust-owned 实现仍待后续单独判定
  - `config.prompt_skills` producer owner 仍未明确
- owner: Rust migration
- target phase:
  - E in progress

### 9. dead Python workflow package convenience module has been retired

- current state:
  - `backend_old/app/services/agent/workflow/__init__.py`
    已删除
  - 原先从 package import 的测试已改为直引具体模块：
    - `backend_old/tests/test_parallel_workflow.py`
    - `backend_old/tests/test_workflow_engine.py`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - `test_parallel_workflow.py`
    已改为 runtime fixture，不再依赖 repo 内已退役测试项目文件
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `209`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_parallel_workflow.py tests/test_workflow_engine.py`
    => `36 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k workflow tests/test_config_internal_callers_use_service_layer.py -k workflow`
    => `2 passed, 57 deselected, 1 warning`
- current meaning:
  - 这是 dead package convenience module retirement，不是新的 Rust workflow takeover
  - 只能说明 `workflow/__init__.py` 不再是 live owner，不能说明 workflow engine/orchestrator 已退出 Python 主链
- still missing:
  - workflow retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- owner: Rust migration
- target phase:
  - E in progress

### 10. dead Python telemetry shell has been retired

- current state:
  - `backend_old/app/services/agent/telemetry/tracer.py`
    已删除
  - `backend_old/app/services/agent/telemetry/__init__.py`
    已删除
  - `backend_old/app/services/agent/__init__.py`
    不再 lazy export：
    - `Tracer`
    - `get_global_tracer`
    - `set_global_tracer`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `207`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k telemetry tests/test_config_internal_callers_use_service_layer.py -k telemetry`
    => `3 passed, 59 deselected, 1 warning`
- current meaning:
  - 这是 dead telemetry shell retirement，不是新的 Rust runtime takeover
  - 当前只能说明 repo 内无 live importer 消费 telemetry package / tracer symbols
- still missing:
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- owner: Rust migration
- target phase:
  - E in progress

### 11. empty Python agent-skills package shell has been retired

- current state:
  - `backend_old/app/services/agent/skills/__init__.py`
    已删除
  - direct submodule import 已验证仍正常：
    - `from app.services.agent.skills.scan_core import SCAN_CORE_LOCAL_SKILL_IDS`
      => `17`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `206`
- verification:
  - `cd backend_old && uv run --project . python -c "from app.services.agent.skills.scan_core import SCAN_CORE_LOCAL_SKILL_IDS; print(len(SCAN_CORE_LOCAL_SKILL_IDS))"`
    => `17`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'skills' tests/test_config_internal_callers_use_service_layer.py -k 'skills'`
    => `4 passed, 60 deselected, 2 warnings`
- current meaning:
  - 这是空 package shell retirement，不是新的 Rust scan-core takeover
  - 当前只能说明 `agent/skills` 空壳已不再是 live owner，不能说明 scan-core 本体已退出 Python retained runtime
- still missing:
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- owner: Rust migration
- target phase:
  - E in progress

### 12. dead Python agent convenience package shell has been retired

- current state:
  - `backend_old/app/services/agent/__init__.py`
    已删除
  - 原先依赖 package convenience import 的测试
    已改为直引具体子模块
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `205`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_agent_tasks_module_layout.py tests/test_static_scan_runtime.py tests/test_agent_event_payload_limits.py tests/test_background_task_launch_refactor.py tests/test_scanner_runner.py`
    => `23 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py tests/test_config_internal_callers_use_service_layer.py -k 'agent and package'`
    => `7 passed, 59 deselected, 3 warnings`
- current meaning:
  - 这是 convenience package shell retirement，不是新的 Rust runtime takeover
  - 只能说明 package root 已不再是 live owner，不能说明 retained helper 本体已退出 Python runtime
- still missing:
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- owner: Rust migration
- target phase:
  - E in progress

### 13. zero-caller Python agent subpackage shells have been retired in batch

- current state:
  - 以下 7 个 zero-caller subpackage shell 已删除：
    - `app/services/agent/core/__init__.py`
    - `app/services/agent/knowledge/frameworks/__init__.py`
    - `app/services/agent/knowledge/vulnerabilities/__init__.py`
    - `app/services/agent/memory/__init__.py`
    - `app/services/agent/prompts/__init__.py`
    - `app/services/agent/streaming/__init__.py`
    - `app/services/agent/tool_runtime/__init__.py`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - 明确保留：
    - `bootstrap/__init__.py`
    - `tools/runtime/__init__.py`
    因为它们仍有 repo 内 caller
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `197`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'core or frameworks or vulnerabilities or memory or prompts or streaming or tool_runtime' tests/test_config_internal_callers_use_service_layer.py -k 'core or frameworks or vulnerabilities or memory or prompts or streaming or tool_runtime'`
    => `15 passed, 68 deselected, 7 warnings`
- current meaning:
  - 这是 zero-caller subpackage shell cleanup，不是新的 Rust runtime takeover
  - `services/agent` 的 package shell 到这里基本只剩 retained live surface
- still missing:
  - retained Python runtime 本体仍在
  - `bootstrap` / `tools.runtime` package shell 仍有 caller
  - `config.prompt_skills` producer owner 仍未明确
- owner: Rust migration
- target phase:
  - E in progress

### 14. retained knowledge package convenience module has been retired

- current state:
  - `backend_old/app/services/agent/knowledge/__init__.py`
    已删除
  - retained live caller 已改为直引 `knowledge.loader`：
    - `backend_old/app/services/agent/agents/base.py`
    - `backend_old/app/services/agent/tools/agent_tools.py`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `196`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k knowledge tests/test_config_internal_callers_use_service_layer.py -k knowledge`
    => `3 passed, 66 deselected, 1 warning`
- current meaning:
  - 这是 retained convenience module retirement，不是新的 Rust runtime takeover
  - 这一步把 live internal caller 从 package root 收口到具体 loader 模块
- still missing:
  - `knowledge.loader` / `knowledge.tools` / `rag_knowledge` 本体仍在 retained Python runtime
- owner: Rust migration
- target phase:
  - E in progress

### 15. retained bootstrap package shell has been retired

- current state:
  - `backend_old/app/services/agent/bootstrap/__init__.py`
    已删除
  - 3 个仅剩测试 caller 已改为直引具体子模块
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `193`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_bandit_bootstrap_scanner.py tests/test_opengrep_bootstrap_scanner.py tests/test_phpstan_bootstrap_scanner.py`
    => `17 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k bootstrap tests/test_config_internal_callers_use_service_layer.py -k bootstrap`
    => `4 passed, 87 deselected, 1 warning`
- current meaning:
  - 这是 retained package shell retirement，不是新的 Rust bootstrap takeover
  - 当前保留的是 bootstrap 子模块本体，不是 package shell
- still missing:
  - `tools/runtime/__init__.py` 仍有 live caller，不能直接删
  - retained Python runtime 本体仍在
- owner: Rust migration
- target phase:
  - E in progress

### 16. retained tools.runtime package shell has been retired

- current state:
  - `backend_old/app/services/agent/tools/runtime/__init__.py`
    已删除
  - live caller 已改为直引具体模块：
    - `backend_old/app/services/agent/tools/base.py`
      -> `.runtime.coordinator`
    - `backend_old/tests/test_tool_runtime_coordinator.py`
      -> `app.services.agent.tools.runtime.coordinator`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    - 并额外覆盖相对 `from .runtime import ...` 形式
  - `prompts` package shell删除后暴露的导入链断裂已修到：
    - `backend_old/app/services/agent/agents/analysis.py`
    - `backend_old/app/services/agent/agents/verification.py`
    - `backend_old/app/services/agent/agents/orchestrator.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `192`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_tool_runtime_coordinator.py`
    => `5 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tool_runtime tests/test_config_internal_callers_use_service_layer.py -k tool_runtime`
    => `3 passed, 91 deselected, 1 warning`
- current meaning:
  - 这是 retained package shell retirement，不是新的 Rust tool runtime takeover
  - 这一步把 `tools.runtime` 的唯一 live internal caller 收口到具体 coordinator 模块
- still missing:
  - `tools/__init__.py` 仍有少量 caller
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- owner: Rust migration
- target phase:
  - E in progress

### 17. retained tools convenience package has been retired

- current state:
  - `backend_old/app/services/agent/tools/__init__.py`
    已删除
  - direct package caller 已改为直引具体子模块或 symbol
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `191`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_tool_runtime_coordinator.py`
    => `5 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tool_runtime tests/test_config_internal_callers_use_service_layer.py -k tool_runtime`
    => `3 passed, 91 deselected, 1 warning`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tools tests/test_config_internal_callers_use_service_layer.py -k tools`
    => `5 passed`
- current meaning:
  - 这是 retained convenience package retirement，不是新的 Rust tool/runtime takeover
  - 当前保留的是具体 tool 模块本体，不再保留 `tools` package root
- still missing:
  - retained Python runtime 模块本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- owner: Rust migration
- target phase:
  - E in progress

### 18. retained workflow cluster has been retired as test-only code

- current state:
  - 以下 workflow cluster 文件已删除：
    - `workflow/engine.py`
    - `workflow/models.py`
    - `workflow/parallel_executor.py`
    - `workflow/memory_monitor.py`
    - `workflow/workflow_orchestrator.py`
  - 只覆盖该 cluster 的测试已删除：
    - `test_parallel_workflow.py`
    - `test_workflow_engine.py`
    - `test_parallel_executor.py`
    - `test_agent_memory_isolation.py`
    - `test_business_logic_pipeline.py`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `186`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k workflow tests/test_config_internal_callers_use_service_layer.py -k workflow`
    => `8 passed, 94 deselected`
- current meaning:
  - 这是 retained test-only workflow cluster retirement，不是新的 Rust workflow takeover
- still missing:
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- owner: Rust migration
- target phase:
  - E in progress

### 19. retained business-logic-scan pair has been retired

- current state:
  - `tools/business_logic_scan_tool.py`
    已删除
  - `agents/business_logic_scan.py`
    已删除
  - `agents/__init__.py`
    已移除 `BusinessLogicScanAgent` re-export
  - 只覆盖该 pair 的测试已删除：
    - `tests/test_refactored_business_logic_scan.py`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `184`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'business_logic_scan' tests/test_config_internal_callers_use_service_layer.py -k 'business_logic_scan'`
    => `4 passed, 102 deselected, 2 warnings`
- current meaning:
  - 这是 retained test-only pair retirement，不是新的 Rust business-logic-scan takeover
- still missing:
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- owner: Rust migration
- target phase:
  - E in progress

### 20. orphan knowledge tools module has been retired

- current state:
  - `backend_old/app/services/agent/knowledge/tools.py`
    已删除
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `180`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'knowledge and tools' tests/test_config_internal_callers_use_service_layer.py -k 'knowledge and tools'`
    => `2 passed, 112 deselected, 1 warning`
- current meaning:
  - 这是 orphan module retirement，不是新的 Rust knowledge takeover
  - 当前只说明 `knowledge/tools.py` 在 repo 内已无 direct live caller
- still missing:
  - `knowledge.loader` / `rag_knowledge` / `base` 仍在 retained Python runtime
  - retained Python runtime 本体仍在
- owner: Rust migration
- target phase:
  - E in progress

### 21. orphan tool_runtime edge cluster has been retired

- current state:
  - 以下 3 个 orphan 模块已删除：
    - `tool_runtime/probe_specs.py`
    - `tool_runtime/protocol_verify.py`
    - `tool_runtime/virtual_tools.py`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `180`
- verification:
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'probe_specs or protocol_verify or virtual_tools' tests/test_config_internal_callers_use_service_layer.py -k 'probe_specs or protocol_verify or virtual_tools'`
    => `6 passed, 108 deselected, 3 warnings`
- current meaning:
  - 这是 orphan cluster retirement，不是新的 Rust tool runtime takeover
  - 当前只说明这 3 个 `tool_runtime` 边缘模块已无 direct live caller
- still missing:
  - `tool_runtime/runtime.py` / `router.py` / `health_probe.py` / `write_scope.py` 仍在 retained Python runtime
  - retained Python runtime 本体仍在
- owner: Rust migration
- target phase:
  - E in progress
