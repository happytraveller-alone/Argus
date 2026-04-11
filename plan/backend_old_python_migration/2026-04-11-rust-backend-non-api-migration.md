# 2026-04-11 Rust Backend Non-API Python Migration

## 结论

- 目标仍未完成。
- 当前纳入本计划的 Python 存量一共 `255` 个文件：
  - `backend_old` 根目录 `4` 个
  - `backend_old/app` 下除 `api` 外 `251` 个
- Rust backend 目前只明确接管了控制面的一小块：
  - `projects`
  - `system-config`
  - `search`
  - `skills`
  - `/api/v1/*` fallback proxy
- 真正决定“Python 是否被吃掉”的非 API 内核还主要在 Python：
  - bootstrap / config / db
  - domain models / schemas
  - runtime / launcher / scanner orchestration
  - upload / report / project shared services
  - LLM / llm_rule
  - agent / tool runtime / workflow / streaming / knowledge

## 核心判断

### [Core Judgment]

值得做。现在的问题不是“还有几个 API 没迁”，而是 Rust 还没有拿到后端内核 ownership。继续零散迁路由，只会把系统做成 Rust 路由壳 + Python 运行时内核的拼接物。

### [Key Insights]

- Data structures:
  - Rust 还没有自己的完整 domain layer，`task / finding / rule / prompt-skill / runtime state` 仍主要活在 Python model、schema、service 组合里。
  - 现在的 Rust `projects/system-config/skills` 已经在做 Python mirror，这说明 source of truth 迁移和运行时迁移没有同步闭环。
- Complexity:
  - 现在最大的复杂度不是代码行数，而是 ownership 分裂。
  - 如果继续按目录或路由零散搬，会一直保留 Rust 写控制面、Python 执行主链路的双写和代理特殊分支。
- Risk points:
  - `static-tasks`、`agent-tasks` 仍依赖 Python runtime 和 Python service graph。
  - 如果先删 Python non-API 模块，会直接打断代理链路和 mirror 读取链路。

### [Linus-Style Plan]

1. 先把 data ownership 写清楚，不再假装“API 迁完就算迁完”。
2. 先迁底座，再迁服务，再迁运行时，再迁 agent/llm 最大块。
3. 允许临时 compat bridge，但每一条桥都必须记 owner、删除条件、删除阶段。
4. 只有当 Rust 成为 source of truth 且主链路不再调用对应 Python 文件，才算“吃掉”。

## 当前 Rust Ownership 快照

### Rust 已 owned 的控制面

- `backend/src/routes/projects.rs`
- `backend/src/routes/system_config.rs`
- `backend/src/routes/search.rs`
- `backend/src/routes/skills.rs`
- `backend/src/proxy.rs`

### 需要明确写死的现状修正

- `projects`
  - Rust 已经是项目主数据面的 source of truth
  - 但写路径仍会同步 legacy `projects / project_info / project_management_metrics`
- `system-config`
  - Rust 已经是系统配置主存储
  - 但保存/删除仍会同步 legacy `user_configs`
- `skills`
  - 不能算“已吃掉”
  - custom prompt skills 在 DB 模式下仍直接读写 legacy `prompt_skills`
  - builtin prompt state 仍直接绑在 `user_configs.other_config`
- `search`
  - 不能算整体完成
  - 当前只有 project search 真正 Rust-owned
  - `tasks / findings` 仍只是 Rust 空壳，不是完整迁移

### 当前仍存在的迁移期桥

- `projects` Python mirror
  - Rust 文件：`backend/src/routes/projects.rs`
  - 删除前置条件：项目元数据、ZIP、任务绑定读链路不再依赖 Python 旧表/旧文件
- `system-config` Python mirror
  - Rust 文件：`backend/src/routes/system_config.rs`
  - 删除前置条件：LLM / agent preflight / task runtime 全部改为只读 Rust config
- `skills` mirror
  - Rust 文件：`backend/src/routes/skills.rs`
  - 更准确地说：legacy `prompt_skills` / `user_configs.other_config` 仍是主存储
  - 删除前置条件：prompt skill storage、builtin prompt state、agent workflow / skill test runner 全部改为 Rust-owned
- `/api/v1/*` proxy fallback
  - Rust 文件：`backend/src/proxy.rs`
  - 当前仍在 proxy 后的主战场：
    - Phase A: `config` old path compat
    - Phase B: `users` / `projects members`
    - Phase D: `static-tasks`
    - Phase E: `prompts` / `rules` / `agent-tasks` / `agent-test`
  - 删除前置条件：`static-tasks`、`agent-tasks` 以及剩余 Python API 路由都完成 Rust 接管

## Inventory Summary

### 状态总览

| 状态 | 文件数 | 含义 |
| --- | ---: | --- |
| `migrate_now` | 54 | 必须先迁，属于 Rust 底座或已被 Rust 控制面直接依赖的共享能力 |
| `migrate_with_api` | 191 | 和 `static-tasks` / `agent-tasks` 或扫描运行时强绑定，需联动迁移 |
| `retire` | 3 | 不做 Python 等价翻译，改为淘汰或收敛到 Rust CLI / shell wrapper |
| `compat_only` | 7 | 只允许短期保留作兼容桥，不允许继续承接新增业务 |

### 按大类归桶

| 大类 | 文件数 | 默认归类 | 目标 phase | Rust 落点 |
| --- | ---: | --- | --- | --- |
| `root bootstrap / diagnostics` | 4 | `1 migrate_now`, `3 retire` | A + F | `backend/src/main.rs`, 后续 `backend/src/bin/*` 或 `scripts/` |
| `core + db + models + schemas` | 39 | `39 migrate_now` | A + B | `backend/src/core/*`, `backend/src/db/*`, `backend/src/domain/*` |
| `runtime + launchers` | 18 | `18 migrate_with_api` | D | `backend/src/runtime/*`, `backend/src/scan/*` |
| `services/upload` | 6 | `6 migrate_now` | C + D | `backend/src/upload/*`, `backend/src/projects/*` |
| `services/llm + llm_rule` | 23 | `23 migrate_with_api` | E | `backend/src/llm/*` |
| `services/agent` | 142 | `142 migrate_with_api` | E | `backend/src/agent/*` |
| `services/scan/search/report/project` | 19 | `8 migrate_now`, `8 migrate_with_api`, `3 compat_only` | C + D + Batch 5 | `backend/src/scan/*`, `backend/src/search/*`, `backend/src/projects/*`, `backend/src/report/*` |
| `utils` | 4 | `4 compat_only` | Batch 5 | 吸收到 `backend/src/core/*` 或具体模块内部 |

## 分桶明细

### 1. `root bootstrap / diagnostics` (`4`)

#### `migrate_now`

- `backend_old/main.py`

#### `retire`

- `backend_old/verify_llm.py`
- `backend_old/check_docker_direct.py`
- `backend_old/check_sandbox.py`

#### 迁移要求

- Rust 成为唯一启动入口和状态恢复入口。
- 诊断类脚本不再复制成 Python replacement。
- 若还有开发者本地价值，迁成 Rust CLI 子命令或 `scripts/` wrapper。

### 2. `core + db + models + schemas` (`39`)

#### `migrate_now`

- `backend_old/app/__init__.py`
- `backend_old/app/main.py`
- `backend_old/app/core/*`
- `backend_old/app/db/*`
- `backend_old/app/models/*`
- `backend_old/app/schemas/*`

#### 迁移要求

- Rust 必须拥有自己的配置、安全、加密、错误、DB session、schema migration 入口。
- Rust 必须拥有完整 typed domain / DTO：
  - project
  - task
  - finding
  - rule
  - prompt skill
  - user/system config
- 禁止新增 Python `models` / `schemas` 依赖点。

### 3. `runtime + launchers` (`18`)

#### `migrate_with_api`

- `backend_old/app/runtime/*`
- `backend_old/app/services/scanner.py`
- `backend_old/app/services/scanner_runner.py`
- `backend_old/app/services/flow_parser_runner.py`
- `backend_old/app/services/flow_parser_runtime.py`
- `backend_old/app/services/yasa_runtime.py`
- `backend_old/app/services/yasa_runtime_config.py`
- `backend_old/app/services/yasa_language.py`
- `backend_old/app/services/opengrep_confidence.py`
- `backend_old/app/services/sandbox_runner.py`
- `backend_old/app/services/sandbox_runner_client.py`
- `backend_old/app/services/backend_venv.py`

#### 迁移要求

- Rust 直接调度 launcher / runner / scanner，不再经 Python runtime 中转。
- 启动恢复、preflight、外部工具探测统一收到 Rust runtime 抽象。
- 只有当 Rust 主链路不再调用 Python runtime 和 launcher，才算完成。

### 4. `services/upload` (`6`)

#### `migrate_now`

- `backend_old/app/services/upload/*`

#### 迁移要求

- 上传、解压、语言识别、压缩策略、项目统计要先收口到 Rust。
- Rust `projects` / `static-tasks` 后续不能继续回调 Python upload service。

### 5. `services/llm + llm_rule` (`23`)

#### `migrate_with_api`

- `backend_old/app/services/llm/*`
- `backend_old/app/services/llm_rule/*`

#### 迁移要求

- Rust 自己拥有 provider registry、adapter、tokenizer、prompt cache、memory compressor。
- `llm_rule` 的 repo cache、patch processor、rule validator 不再依赖 Python sidecar。
- 删除 `system-config` mirror 前，这一块必须已经只读 Rust config。

### 6. `services/agent` (`142`)

#### `migrate_with_api`

- `backend_old/app/services/agent/agents/*`
- `backend_old/app/services/agent/bootstrap/*`
- `backend_old/app/services/agent/core/*`
- `backend_old/app/services/agent/flow/*`
- `backend_old/app/services/agent/knowledge/*`
- `backend_old/app/services/agent/logic/*`
- `backend_old/app/services/agent/memory/*`
- `backend_old/app/services/agent/prompts/*`
- `backend_old/app/services/agent/skills/*`
- `backend_old/app/services/agent/streaming/*`
- `backend_old/app/services/agent/telemetry/*`
- `backend_old/app/services/agent/tool_runtime/*`
- `backend_old/app/services/agent/tools/*`
- `backend_old/app/services/agent/utils/*`
- `backend_old/app/services/agent/workflow/*`
- `backend_old/app/services/agent/*.py`

#### 迁移要求

- 这是最后的主战场，不和控制面小修混做。
- 必须联动迁移：
  - orchestration
  - workflow engine
  - tool runtime
  - streaming
  - knowledge
  - prompt skill merge
  - skill test runner
- `agent-tasks` 只有在这块 Rust-owned 后才算真正完成。

### 7. `services/scan/search/report/project` (`19`)

#### `migrate_now` (`8`)

- `backend_old/app/services/search_service.py`
- `backend_old/app/services/project_metrics.py`
- `backend_old/app/services/project_transfer_service.py`
- `backend_old/app/services/zip_storage.py`
- `backend_old/app/services/zip_cache_manager.py`
- `backend_old/app/services/json_safe.py`
- `backend_old/app/services/report_generator.py`
- `backend_old/app/services/runner_preflight.py`

#### `migrate_with_api` (`8`)

- `backend_old/app/services/init_templates.py`
- `backend_old/app/services/seed_archive.py`
- `backend_old/app/services/gitleaks_rules_seed.py`
- `backend_old/app/services/pmd_rulesets.py`
- `backend_old/app/services/parser.py`
- `backend_old/app/services/rule.py`
- `backend_old/app/services/bandit_rules_snapshot.py`
- `backend_old/app/services/yasa_rules_snapshot.py`

#### `compat_only` (`3`)

- `backend_old/app/services/git_mirror.py`
- `backend_old/app/services/chat2rule/__init__.py`
- `backend_old/app/services/chat2rule/context.py`

#### 迁移要求

- 先把已被 Rust 控制面直接或间接需要的共享服务迁回 Rust。
- `compat_only` 只允许做过渡桥，不允许再加业务逻辑。
- `chat2rule` 和长尾 helper 放到 Batch 5 清理，不抢前面大块的迁移节奏。

### 8. `utils` (`4`)

#### `compat_only`

- `backend_old/app/utils/*`

#### 迁移要求

- 只允许临时存在。
- 后续要么吸收到具体 Rust 模块，要么直接删除。
- 禁止新增对 `backend_old/app/utils/*` 的依赖。

## 执行顺序

### Phase A, 根入口和共用底座

- 处理：
  - `backend_old/main.py`
  - `backend_old/app/main.py`
  - `backend_old/app/core/*`
  - `backend_old/app/db/*`
- 目标：
  - Rust 成为唯一启动入口和状态恢复入口
  - Python 不再承担启动主流程

### Phase B, 数据模型与持久化内核

- 处理：
  - `backend_old/app/models/*`
  - `backend_old/app/schemas/*`
- 目标：
  - Rust 自己拥有 typed domain / DTO 层
  - 不再新增 Python model/schema 依赖点

### Phase C, 通用服务层

- 处理：
  - `search_service`
  - `project_metrics`
  - `project_transfer_service`
  - `zip_storage`
  - `zip_cache_manager`
  - `json_safe`
  - `report_generator`
  - `runner_preflight`
  - `upload/*`
- 目标：
  - Rust 控制面依赖的共享服务不再落回 Python

### Phase D, 扫描运行时与 launcher

- 处理：
  - `runtime/container_startup.py`
  - `runtime/launchers/*`
  - `scanner*`
  - `yasa_runtime*`
  - `flow_parser*`
- 目标：
  - Rust 直接调度外部扫描器和 runner

### Phase E, LLM 与 Agent 内核

- 处理：
  - `services/llm/*`
  - `services/llm_rule/*`
  - `services/agent/*`
- 目标：
  - Rust 拿回 agent orchestration、tool runtime、streaming、knowledge、workflow、prompt skill merge、skill test runner

### Phase F, 根目录残余脚本收尾

- 处理：
  - `verify_llm.py`
  - `check_docker_direct.py`
  - `check_sandbox.py`
- 目标：
  - 能 retire 的直接 retire
  - 必须保留的只保留 Rust CLI / shell wrapper

## 推荐执行批次

### Batch 1

- `root bootstrap / diagnostics`
- `core + db + shared config/state`

### Batch 2

- `models + schemas + project/search/skill shared services`

### Batch 3

- `runtime + upload + scan launcher + project/report utilities`

### Batch 4

- `llm + agent + tool runtime + workflow`

### Batch 5

- 清理 `utils`、`chat2rule`、长尾 helper，删除已退休 Python 文件

## 固定执行标准

### 每一阶段都必须做的三件事

1. 先把对应 Python 文件在 inventory 标成当前阶段 owner。
2. 再迁最小 Rust 实现和 compat bridge。
3. 最后把对应 Python 文件标成 `retired` 或 `compat_only`。

### compat bridge 规则

- 允许短期保留 Python shadow write / adapter。
- 但每一条桥都必须在 `plan/wait_correct/` 记录：
  - owner
  - 删除前置条件
  - 删除阶段
- 禁止新业务继续落到 Python 非 API 模块。

### “吃掉”的判定标准

- 只有当 Rust 已接管该能力的 source of truth，
- 并且运行主链路不再调用对应 Python 文件，
- 才算完成。

仅仅是路由不再直连，不算完成。

## 验收与回写

### 每次执行后必须重跑

- `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l`
- `find backend_old/app -path 'backend_old/app/api' -prune -o -type f -name '*.py' -print | wc -l`

### 每次执行后必须回写

- 本计划文件
- `plan/wait_correct/non-api-python/non-api-python-summary.md`
- 对应的 `plan/wait_correct/waves/*.md`

## 本次基线

- 统计日期：`2026-04-11`
- `backend_old` 根目录 Python 文件：`4`
- `backend_old/app` 非 API Python 文件：`251`
- 本计划 inventory 总数：`255`

## 执行记录

### 2026-04-11 Batch 1 / Slice 1

- 已完成：
  - Rust 新增 `backend/src/bootstrap/mod.rs`
  - `backend/src/main.rs` 在 `serve` 前执行 bootstrap
  - `/health` 新增 bootstrap 状态回报
  - Rust bootstrap 的 DB 检查只盯 Rust 自己依赖的表，不再盯 Python `alembic_version`
  - Rust 新增 startup orchestration 子模块：
    - `backend/src/bootstrap/init.rs`
    - `backend/src/bootstrap/recovery.rs`
    - `backend/src/bootstrap/preflight.rs`
  - startup recovery 和 runner preflight 的编排位置已从 Python `app.main` 迁到 Rust bootstrap
  - Rust control-plane init 不再在 file-mode 下空转：
    - 会初始化默认 `system_config`
    - 会初始化空的 `rust-projects.json`
    - 不会导入 demo 用户、旧规则、旧用户态数据
  - Rust 已显式定义 startup init policy：
    - allowlist:
      - `default_rust_system_config`
      - `empty_rust_project_store`
      - `rust_scan_rule_asset_sync`
    - denylist:
      - `demo_user_bootstrap`
      - `demo_project_seed`
      - `legacy_user_table_mutation`
      - `legacy_project_seed_download`
      - `legacy_rule_table_import`
      - `legacy_prompt_template_seed`
    - defer until rust-owned:
      - `agent_task_seed_data`
      - `static_scan_task_seed_data`
      - `legacy_rule_projection_tables`
      - `legacy_prompt_template_projection`
      - `seed_project_archive_download`
      - `legacy_user_config_backfill`
  - Rust 新增 `rust_scan_rule_assets` 规则资产库：
    - 会把 `backend_old/app/db` 下扫描引擎规则资产导入 Rust 自己维护的数据库
    - 当前覆盖：
      - `rules/`
      - `rules_from_patches/`
      - `patches/`
      - `gitleaks_builtin/`
      - `bandit_builtin/`
      - `rules_phpstan/`
      - `rules_pmd/`
      - `yasa_builtin/`
  - 已打通首条规则消费链路：
    - Gitleaks 会从 Rust 规则资产库读取 builtin TOML
    - Rust 会 materialize 成 `gitleaks.toml`
    - Rust preflight 会把该 config 挂载进容器并传给 `gitleaks detect --config`
  - 已打通第二条规则消费链路：
    - Opengrep 会从 Rust 规则资产库读取 `internal_rule + patch_rule`
    - Rust 会 materialize 成 `opengrep-rules/`
    - Rust preflight 会把该规则目录挂载进容器并执行 `opengrep --config /work/opengrep-rules --validate`
  - `backend/tests/bootstrap_startup.rs` 覆盖：
    - 文件存储根创建
    - 无 DB 时 file-mode control-plane init
    - DB 不可达时 degraded/error 状态
    - 文件存储根不可创建时启动失败
- 当前意义：
  - Rust public backend 不再只是 router 壳，已经开始拥有自己的启动前检查与状态报告
  - Rust DB 启动检查已经和 Python 旧 DB 语义解耦，Python 只保留参考价值
  - Rust 已开始 owner startup init / recovery / preflight 的 orchestration 外壳
  - Rust 在 file-mode 下已经能独立自举最小 control-plane 状态
  - `backend_old/app/db` 中仍有价值的扫描引擎规则资产，已经开始迁入 Rust 自有库，不再依赖 Python 侧灌库
  - Rust startup init 的“该做/不该做”已经是自己的 policy，不再让 Python demo/user 初始化影子带偏设计
  - 至少已有一个扫描引擎开始真正消费 Rust 自己维护的规则资产
  - `opengrep` 已进入 Rust 真消费阶段，最大的规则资产源开始脱离 Python 旧链路
  - 这是 Batch 1 的第一刀，不是 Batch 1 完成
- 仍未完成：
  - Python `app/main.py` 中的 schema version orchestration、`init_db()` 的完整语义仍未迁走
  - startup recovery 虽已由 Rust 编排接手，但恢复目标仍是 legacy task tables，属于迁移期桥
  - runner preflight 虽已迁到 Rust，但仍是启动前 runner 可用性检查，不是 runtime 迁移完成
  - 扫描规则资产虽然已进 Rust DB，但后续各引擎的 Rust-native 读取与使用链路还没全部接上
  - 当前已打通 `gitleaks + opengrep`，`bandit / phpstan / pmd / yasa` 仍待接入
  - `backend_old/app/core/*`、`backend_old/app/db/*` 仍未被 Rust 完整替代
- 下一刀：
  - 继续迁 Phase A 剩余底座，把 DB/schema/init 流程的 source of truth 从 Python 挪到 Rust
