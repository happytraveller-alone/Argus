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
  - Rust DB bootstrap 只检查 Rust 自己依赖的表，不再盯 Python `alembic_version`
  - startup recovery / runner preflight 的 orchestration 已进入 Rust bootstrap
  - file-mode 下 Rust 已会初始化默认 control-plane config 和空项目存储
- still missing:
  - Python `app.main` 内的 schema version orchestration
  - `init_db()` 的完整 Rust 版本
  - recovery 对 legacy task tables 的依赖删除
  - runner preflight 后续与 Rust runtime 的进一步打通
- owner: Rust migration
- target phase:
  - A now in progress

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
