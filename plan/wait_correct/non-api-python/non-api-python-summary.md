# Non-API Python Migration Summary

- Total inventory: `255`
- `backend_old` root Python: `4`
- `backend_old/app` non-API Python: `251`
- `migrate_now`: `54`
- `migrate_with_api`: `191`
- `retire`: `3`
- `compat_only`: `7`

- Source migration plan:
  - `/Users/apple/Project/AuditTool_private/plan/backend_old_python_migration/2026-04-11-rust-backend-non-api-migration.md`

## Active Ledger

### 1. non-api python inventory is not yet migrated

- current state:
  - Rust 已 owned `projects / system-config / search / skills`、gateway/proxy，以及新的 startup bootstrap shell
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
  - `/api/v1/*` fallback 不再承接相关能力

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
  - `init_db()` 的完整 Rust 版本
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
    - `backend_old/app/main.py`
    - `backend_old/app/db/session.py`
    - `backend_old/app/db/init_db.py`
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
    - `backend_old/app/db/init_db.py`
    - `backend_old/app/services/gitleaks_rules_seed.py`
    - `backend_old/app/services/bandit_rules_snapshot.py`
    - `backend_old/app/services/pmd_rulesets.py`
    - `backend_old/app/api/v1/endpoints/static_tasks_phpstan.py`
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
  - `base.py` / `session.py` / `init_db.py` / `static_finding_paths.py` 仍是 Python live 入口，不能删
- delete gate:
  - `rules_phpstan` 只有在 Rust 真正接管 phpstan scanner/runtime 后才能删
  - `yasa_builtin` 只有在 YASA 彻底退出 Python live 路径或被完全 retire 后才能删
  - `schema_snapshots/*` 只有在 `backend_old/alembic` 不再依赖 baseline snapshot 时才能删
- owner: Rust migration
- target phase:
  - A / C in progress

### 1d. phpstan db assets are now Rust-owned, YASA retirement is in progress

- current state:
  - Rust 已新增 `backend/src/scan/phpstan.rs` 并实际消费 `rules_phpstan/*`
  - Rust phpstan preflight 已通过 materialized asset 目录校验 snapshot 与 `rule_sources/`
  - `backend_old/app/db/rules_phpstan` 已删除，Python 继续从 Rust 资产根读取 phpstan snapshot / source files
  - YASA 相关 DB 资产与部分服务/导出已进入退役中间态
- still missing:
  - phpstan live API/runtime 仍由 Python 端持有
  - YASA 仍有多个 live caller 未删完，当前不能宣称“YASA 全量退役完成”
- delete gate:
  - phpstan 只有在 live runtime/API 也迁到 Rust 后，才算整条链完成
  - YASA 只有在剩余 live caller 和测试全部清理后，才算 retire 完成
- owner: Rust migration
- target phase:
  - C / D in progress

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
  - tasks / findings search 仍只是 Rust 空壳，不应记为“搜索已完成迁移”
- owner: Rust migration
- delete gate:
  - 任务、finding、规则等搜索索引和查询模型迁到 Rust domain / db 层
