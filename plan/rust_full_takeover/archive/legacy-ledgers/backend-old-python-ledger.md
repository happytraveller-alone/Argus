# 2026-04-11 Rust Backend Non-API Python Migration

## 结论

- 目标仍未完成。
- 当前纳入本计划的 Python 存量一共 `211` 个文件：
  - `backend_old` 根目录 `0` 个
  - `backend_old/app` 下除 `api` 外 `211` 个
- Rust backend 当前已直接挂载并承接以下路由组：
  - `/api/v1/agent-tasks/*`
  - `/api/v1/agent-test/*`
  - `/api/v1/static-tasks/*`
  - `projects / system-config / search / skills`
- Rust `/api/v1/*` fallback proxy 已不在 live 代码路径：
  - `backend/src/proxy.rs` 不存在
  - `backend/src/app.rs` 为 `fallback 404`，不是转发到 Python backend
- Docker 三链路 (`default/hybrid/full`) 的 Python backend bridge 已从 compose 变量层清零：
  - `backend-py` 无命中
  - `PYTHON_UPSTREAM_BASE_URL` 无命中
- 真正决定“Python 是否被吃掉”的非 API 内核还主要在 Python：
  - bootstrap / config / db
  - domain models / schemas
  - runtime / launcher / scanner orchestration
  - upload / report / project shared services
  - LLM / llm_rule
  - agent / tool runtime / workflow / streaming / knowledge

## 2026-04-11 仓库事实刷新（二次核对）

- read-only evidence:
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
  - `awk -F, 'NR>1{...}' plan/wait_correct/route-inventory/python-endpoints-inventory.csv` =>
    `total=179`, `proxy=114`, `migrate=38`, `retire=20`, `defer=7`
  - `rg -n 'nest\\("/api/v1/(agent-tasks|agent-test|static-tasks)' backend/src/routes -S`
    命中 `backend/src/routes/mod.rs`
  - `rg -n 'backend-py|PYTHON_UPSTREAM_BASE_URL' docker-compose*.yml -S`
    无命中（exit code 1）
  - `rg -n 'PYTHON_UPSTREAM_BASE_URL|backend-py|/api/v1/\\{\\*path\\}|proxy\\.rs' backend/src -S`
    无 gateway/proxy 命中（仅 `opengrep_launcher` 的 `http_proxy` 环境变量命中）

## 新 Gate（Rust 全接管硬门槛）

- Gate R1: `backend/src/proxy.rs` 必须保持不存在，`backend/src/app.rs` 不允许重新引入 `/api/v1/{*path}` proxy fallback。
- Gate R2: `docker-compose.yml` 必须删除 `backend-py` service。
- Gate R3: `docker-compose.yml`、`docker-compose.hybrid.yml`、`docker-compose.full.yml` 必须清零 `PYTHON_UPSTREAM_BASE_URL`。
- Gate R4: `rg -n "backend-py|PYTHON_UPSTREAM_BASE_URL" docker-compose*.yml backend/src -S` 结果只允许出现非后端迁移语义的 `http_proxy/https_proxy` 文本，不允许出现 Python backend bridge 命中。

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
  - 当前 project search 已 Rust-owned
  - agent/static task 与 finding search 已接到 Rust task-state 数据
  - 但 rule 维度搜索仍未完成，不算整体迁移完成

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
| `root bootstrap / diagnostics` | 4 | `4 retired_after_rust_takeover` | A + F | `backend/src/main.rs`, 后续 `backend/src/bin/*` 或 `scripts/` |
| `core + db + models + schemas` | 39 | `39 migrate_now` | A + B | `backend/src/core/*`, `backend/src/db/*`, `backend/src/domain/*` |
| `runtime + launchers` | 18 | `15 migrate_with_api`, `3 retired_after_rust_takeover` | D | `backend/src/runtime/*`, `backend/src/scan/*` |
| `services/upload` | 5 | `5 retired_after_rust_takeover` | C + D | `backend/src/upload/*`, `backend/src/projects/*` |
| `services/llm + llm_rule` | 23 | `23 migrate_with_api` | E | `backend/src/llm/*` |
| `services/agent` | 142 | `142 migrate_with_api` | E | `backend/src/agent/*` |
| `services/scan/search/report/project` | 17 | `1 migrate_now`, `5 migrate_with_api`, `3 compat_only`, `8 retired_after_rust_takeover` | C + D + Batch 5 | `backend/src/scan/*`, `backend/src/search/*`, `backend/src/projects/*`, `backend/src/report/*` |
| `utils` | 4 | `4 compat_only` | Batch 5 | 吸收到 `backend/src/core/*` 或具体模块内部 |

## 分桶明细

### 1. `root bootstrap / diagnostics` (`4`)

#### `retired_after_rust_takeover`

- `backend_old/main.py`
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
- `backend_old/app/core/*`
- `backend_old/app/db/*`
- `backend_old/app/models/*`
- `backend_old/app/schemas/*`

#### `retired_in_wave_a`

- `backend_old/app/main.py`

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
- `backend_old/app/schemas` 已退出运行时：`search`、`token`、`user`、`audit_rule`、`prompt_template` 以及 legacy `opengrep/gitleaks` schema package 被 retired；`backend_old/app/api/v1/schemas/rule_flows.py` 也已删除，`OpengrepRuleCreateRequest` 改由非 API 路径 `backend_old/app/services/rule_contracts.py` 承接。
- 这并不意味着 `static-tasks` 已经完全 Rust-owned；静态任务功能链路仍沿用 Python runtime/compat bridge。
- operational verification：`find backend_old/app -type d -name schemas -print` 不应再列出 live Python schema package；若目录仍存在，也不应再包含 `rule_flows.py` 或 `__init__.py`。

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
- `backend_old/app/services/sandbox_runner.py`
- `backend_old/app/services/sandbox_runner_client.py`
- `backend_old/app/services/backend_venv.py`

#### `retired_after_rust_takeover` (`4`)

- `backend_old/app/services/opengrep_confidence.py`
- `backend_old/app/services/scanner.py`
- `backend_old/app/services/flow_parser_runtime.py`
- `backend_old/app/services/backend_venv.py`

#### 迁移要求

- Rust 直接调度 launcher / runner / scanner，不再经 Python runtime 中转。
- 启动恢复、preflight、外部工具探测统一收到 Rust runtime 抽象。
- 只有当 Rust 主链路不再调用 Python runtime 和 launcher，才算完成。
- 当前进展：
  - `backend_old/app/runtime` 已从 live tree 删除。
  - Rust 已新增 runtime 接管入口：
    - `backend/src/runtime/bootstrap.rs`
    - `backend/src/bin/backend_runtime_startup.rs`
    - `backend/src/bin/opengrep_launcher.rs`
    - `backend/src/bin/phpstan_launcher.rs`
  - `docker/backend_old.Dockerfile`、`scripts/release-templates/backend.Dockerfile`
    已切到 `/usr/local/bin/backend-runtime-startup`
  - `docker/opengrep-runner.Dockerfile`、`docker/phpstan-runner.Dockerfile`
    已切到 Rust launcher binaries
  - `backend/tests/runtime_env_bootstrap.rs` 已取代旧的
    `backend_old/tests/test_backend_container_startup_env_bootstrap.py`
  - operational verification:
    - `find backend_old/app -type d -name runtime -print`
    - `rg -n "app\\.runtime\\.|from app\\.runtime|import app\\.runtime|container_startup\\.py|opengrep_launcher\\.py|phpstan_launcher\\.py" backend_old backend docker scripts .github`
    - 预期结果：
      - `backend_old/app/runtime` 不再存在
      - live runtime / Dockerfile / tests 不再引用旧 Python runtime 路径
  - 边界说明：
    - 这表示 `app/runtime` 目录已被 Rust runtime entrypoints 接管并可删除
    - 这不等于 `backend-py` 兼容服务整体退休，也不等于 `scanner*` / `flow_parser*` / 其它 runtime orchestration 已全部 Rust-owned
- 当前进展：
  - `backend_old/app/runtime` 已从 live tree 删除。
  - Rust 已新增 runtime 接管入口：
    - `backend/src/runtime/bootstrap.rs`
    - `backend/src/bin/backend_runtime_startup.rs`
    - `backend/src/bin/opengrep_launcher.rs`
    - `backend/src/bin/phpstan_launcher.rs`
  - `docker/backend_old.Dockerfile`、`scripts/release-templates/backend.Dockerfile`
    已切到 `/usr/local/bin/backend-runtime-startup`
  - `docker/opengrep-runner.Dockerfile`、`docker/phpstan-runner.Dockerfile`
    已切到 Rust launcher binaries
  - `backend/tests/runtime_env_bootstrap.rs` 已取代旧的
    `backend_old/tests/test_backend_container_startup_env_bootstrap.py`
  - operational verification:
    - `find backend_old/app -type d -name runtime -print`
    - `rg -n "app\\.runtime\\.|from app\\.runtime|import app\\.runtime|container_startup\\.py|opengrep_launcher\\.py|phpstan_launcher\\.py" backend_old backend docker scripts .github`
    - 预期结果：
      - `backend_old/app/runtime` 不再存在
      - live runtime / Dockerfile / tests 不再引用旧 Python runtime 路径
  - 边界说明：
    - 这表示 `app/runtime` 目录已被 Rust runtime entrypoints 接管并可删除
    - 这不等于 `backend-py` 兼容服务整体退休，也不等于 `scanner*` / `flow_parser*` / 其它 runtime orchestration 已全部 Rust-owned

### 4. `services/upload` (`5`)

#### `retired_after_rust_takeover`

- `backend_old/app/services/upload/*`

#### 迁移要求

- Rust `projects` 已承接 live upload / description / archive HTTP surface。
- Python `upload/*` 当前确认无 live caller，仅剩 legacy tests / 参考语义。
- 这不等于 Rust 已全量等价旧 Python upload 语义；只表示这组 Python 实现不再 live。

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

### 7. `services/scan/search/report/project` (`18`)

#### `migrate_now` (`1`)

- `backend_old/app/services/json_safe.py`

#### `retired_after_rust_takeover` (`8`)

- `backend_old/app/services/zip_cache_manager.py`
- `backend_old/app/services/zip_storage.py`
- `backend_old/app/services/search_service.py`
- `backend_old/app/services/report_generator.py`
- `backend_old/app/services/runner_preflight.py`
- `backend_old/app/services/init_templates.py`
- `backend_old/app/services/seed_archive.py`
- `backend_old/app/services/gitleaks_rules_seed.py`

#### `migrate_with_api` (`5`)

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

#### `retire`

- Rust `backend/src/core/date_utils` 现在直接替代原 Python `backend_old/app/utils/date_utils.py` 的行为，配套 `backend_old/tests/test_date_utils.py` 已删除。
- `repo_utils` 被淘汰，因为远程仓库 handling 逻辑在当前架构中已无可支持的 runtime 入口。
- `utils/security` 的 forwarding wrapper 退役，核心安全责任完全落到 Rust `backend/src/core/security.rs` / `backend/src/core/encryption.rs`。
- `backend_old/app/utils` 目录已从 live Python runtime 中删除，唯一残留的 `app.utils` 字串出现在离线扫描规则补丁资产 `backend/assets/scan_rule_assets/patches/vuln-halo-d59877a9.patch`，那只是文本替换，不属于运行时依赖。
- 运行态核查命令固定为：
  - `rg -n "app\\.utils|repo_utils|app\\.utils\\.security" backend_old/app backend_old/tests backend/src backend/assets/scan_rule_assets/patches`
  - 预期结果：
    - `backend_old/app`、`backend_old/tests`、`backend/src` 这三类 live runtime/test 路径命中数必须为 `0`
    - 唯一允许剩下的命中是 `backend/assets/scan_rule_assets/patches/vuln-halo-d59877a9.patch`
  - 如果将来要清掉这条离线 patch 文本残留，owner 仍是 Rust migration，目标阶段记到 Phase F / Batch 5 retire cleanup，不应回流成 runtime 清理任务。

#### `compat_only`

- 暂无 live compat-only 依赖（目录已从 runtime 中剥离，后续仅留离线 patch 文本）。

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
  - `backend_old/app/schemas/*`（dead/retired schemas：`search`、`token`、`user`、`audit_rule`、`prompt_template` 以及 legacy `opengrep/gitleaks` schema package 已被移除；`rule_flows.py` DTO 已迁离 API 路径）
- 目标：
  - Rust 自己拥有 typed domain / DTO 层
  - 不再新增 Python model/schema 依赖点

### Phase C, 通用服务层

- 处理：
  - `search_service`
  - `project_metrics`
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

### 原子迁移纪律

- 后续迁移按“小任务”推进，每个小任务必须满足：
  - 只收敛一个明确能力边界
  - Rust 接管后，立刻删除对应 Python 执行入口、live router 挂载或已失效测试
  - 同一能力在同一时刻只能保留一处实际执行代码
- 每完成一个小任务必须立刻单独提交：
  - 禁止把多个迁移切片混在同一个 commit
  - commit 必须能对应到 `plan/wait_correct/waves/*.md` 中的一条明确记录
- 如果某段 Python 代码暂时不能删，必须明确说明它还是 bridge：
  - 谁在读
  - 删除前置条件
  - 预计在哪个 slice 删除

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
- 并且对应 Python live entry / adapter / dead test 已删除或降为明确 bridge，
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
    - 会把 `backend/assets/scan_rule_assets/` 下扫描引擎规则资产导入 Rust 自己维护的数据库
    - 当前覆盖：
      - `rules/`
      - `rules_from_patches/`
      - `patches/`
      - `gitleaks_builtin/`
      - `bandit_builtin/`
      - `rules_phpstan/`
      - `rules_pmd/`
  - 已打通首条规则消费链路：
    - Gitleaks 会从 Rust 规则资产库读取 builtin TOML
    - Rust 会 materialize 成 `gitleaks.toml`
    - Rust preflight 会把该 config 挂载进容器并传给 `gitleaks detect --config`
  - 已打通第二条规则消费链路：
    - Opengrep 会从 Rust 规则资产库读取 `internal_rule + patch_rule`
    - Rust 会 materialize 成 `opengrep-rules/`
    - Rust preflight 会把该规则目录挂载进容器并执行 `opengrep --config /work/opengrep-rules --validate`
  - 已打通第三条规则消费链路：
    - Bandit 会从 Rust 规则资产库读取 builtin snapshot
    - Rust 会选择 active test ids 并生成 `bandit -t ...`
    - Rust preflight 会用该规则选择真正执行 Bandit 扫描命令
  - 已打通第四条规则消费链路：
    - PMD 会从 Rust 规则资产库读取 builtin XML rulesets
    - Rust 会 materialize 成 `pmd-rules/`
    - Rust preflight 会选择 ruleset 并执行 `pmd check -R ...`
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
  - 扫描引擎规则资产现在以 `backend/assets/scan_rule_assets/` 为 Rust owner root，不再依赖 `backend_old/app/db`
  - Rust startup init 的“该做/不该做”已经是自己的 policy，不再让 Python demo/user 初始化影子带偏设计
  - 至少已有一个扫描引擎开始真正消费 Rust 自己维护的规则资产
  - `opengrep` 已进入 Rust 真消费阶段，最大的规则资产源开始脱离 Python 旧链路
  - `bandit + pmd` 也已进入 Rust 真消费阶段，Rust 规则资产库开始形成体系化收益
  - 这是 Batch 1 的第一刀，不是 Batch 1 完成
- 仍未完成：
  - Python `app/main.py` 中的 schema version orchestration 已迁走，剩余是更细的 DB/model 收口
  - startup recovery 虽已由 Rust 编排接手，但恢复目标仍是 legacy task tables，属于迁移期桥
  - runner preflight 虽已迁到 Rust，但仍是启动前 runner 可用性检查，不是 runtime 迁移完成
  - 扫描规则资产虽然已进 Rust DB，但后续各引擎的 Rust-native 读取与使用链路还没全部接上
  - 当前已打通 `gitleaks + opengrep + bandit + pmd`，`phpstan` 仍待接入
  - `yasa` 已不再列为后续目标，不再投入新增迁移工作
  - `backend_old/app/core/*`、`backend_old/app/db/*` 仍未被 Rust 完整替代
- 下一刀：
  - 继续迁 Phase A 剩余底座，把 DB/schema/init 流程的 source of truth 从 Python 挪到 Rust

### 2026-04-11 Batch 1 / Slice 2

- 已完成：
  - Rust 新增 `backend/src/bootstrap/legacy_schema.rs`
  - Rust bootstrap 会直接解析 `backend_old/alembic/versions/*.py`，识别 legacy Alembic migration graph 的 expected heads
  - parser 已兼容：
    - `revision = "..."`
    - `revision: Union[...] = "..."`
    - `down_revision` 的单行与多行表达式
  - Rust database bootstrap report 新增 `legacy_schema` 结构化状态：
    - `status`
    - `versions_dir`
    - `expected_heads`
    - `current_versions`
    - `matches_expected_heads`
    - `error`
  - `/health` 已暴露 `bootstrap.database.legacy_schema`
  - DB 可达时，Rust 会直接读取 `alembic_version.version_num`
  - 若 `alembic_version` 缺失或当前版本与 expected heads 不一致，Rust 会把 bootstrap 标成 `degraded`
  - DB 不可达或超时时，服务仍可启动，但 `legacy_schema` 会和整体 DB 状态一起诚实暴露降级/超时
  - file-mode 下 `legacy_schema` 明确为 `skipped`
  - `backend/tests/bootstrap_startup.rs` 与 `backend/src/bootstrap/mod.rs` 单测已补齐：
    - typed/plain assignment 解析
    - 多行 `down_revision` merge 解析
    - 非法 `down_revision` 显式报错，不再静默当 root
    - current versions 与 expected heads 的 match / missing / mismatch 降级语义
- 当前意义：
  - Rust 已开始接管 legacy schema version 的认知权，不再完全依赖 Python `app.main` 才知道数据库迁移是否落后
  - `/health` 对“Rust 自身表是否齐全”和“Python legacy schema 是否对齐”都能给出结构化状态
  - 这一步没有引入重型 migration 执行，符合“启动只做检查与诚实报告，不在 Rust 启动里跑 alembic”的边界
  - Phase A 里 “schema version orchestration” 已从 Python-only 变成 Rust 具备检查与判定能力，但还没完全替掉 Python 的启动策略
- 仍未完成：
  - Rust 还不会执行或接管 legacy schema migration，只负责识别与报告
  - Rust bootstrap 已接手 init/seed 语义，剩余工作转向 DB/model 收口
  - startup recovery 仍指向 legacy task tables，属于迁移期桥
  - runner preflight 仍是启动期 runner 可用性检查，不是 runtime ownership 完成
  - `backend_old/app/core/*`、`backend_old/app/db/*` 仍未被 Rust 完整替代
  - `phpstan` 的 Rust 规则消费链路仍未接入
- 下一刀：
  - 继续迁 Phase A / Phase C 交界处，把 Rust 对 schema/init 的 ownership 继续向 `db/session`、legacy models 和 Alembic baseline 收口

### 2026-04-11 Batch 1 / Slice 3

- 已完成：
  - Rust 新增 `backend/src/bootstrap/legacy_mirror_schema.rs`
  - Rust startup init 在 DB 模式下会显式创建当前 Rust 已 owned 控制面所依赖的 legacy mirror 表：
    - `users`
    - `user_configs`
    - `projects`
    - `project_info`
    - `project_management_metrics`
    - `prompt_skills`
  - Rust startup init policy 新增 allowlist 项：
    - `legacy_control_plane_mirror_schema_sync`
  - `backend/src/bootstrap/init.rs` 已在 `scan_rule_assets` 同步前执行 mirror schema sync
  - 新增 Rust 单测覆盖：
    - legacy mirror schema spec 范围是否覆盖当前 Rust-owned bridge
    - startup init policy 是否显式允许该动作
- 当前意义：
  - 对于 Rust 已经在写入的 legacy compat bridge，schema 创建责任不再继续完全绑死在 `backend_old/alembic`
  - 至少 `system-config / projects / skills builtin/custom prompt state` 这几条已迁控制面的 legacy mirror 表，Rust 已开始自己兜底
  - 这是对 `backend_old/alembic` 的部分替代，不是全量替代
- 仍未完成：
  - `backend_old/alembic` 仍未整体被 Rust 替代
  - Python runtime / static-tasks / agent-tasks 依赖的大量 legacy 表仍未迁到 Rust schema ownership
  - 目前只能说 Rust 已开始接管“它自己还在桥接写入的 legacy 表”的 schema，不等于 Python 运行时全量表都已可由 Rust 生成
- 删除条件：
  - 只有当 Python runtime 不再依赖 `backend_old/alembic/env.py` 和对应 legacy versions 里的剩余表迁移
  - 并且 Rust 已接管剩余 legacy task / finding / rule config / agent runtime 表 schema
  - 才能删除 `backend_old/alembic`
- 下一刀：
  - 继续沿 “Alembic 被 Rust 替代” 这条主线，优先收口当前仍由 Python runtime 强依赖、但与 Rust bridge 最接近的 legacy 表族

### 2026-04-11 Batch 1 / Slice 4

- 已完成：
  - Rust 新增 `backend/src/core/security.rs`
    - 已实现 JWT access token 创建
    - 已实现 bcrypt 密码 hash / verify
    - 已补 Python 生成 JWT / bcrypt hash 的兼容测试
  - Rust 新增 `backend/src/core/encryption.rs`
    - 已实现基于 `SECRET_KEY` 派生的 Fernet-compatible 加解密
    - 已补 Python 生成 Fernet token 的兼容测试
    - 已补敏感 LLM key 字段选择性加密测试
  - Rust `backend/src/config.rs` 已开始承接 core 级配置语义：
    - `SECRET_KEY`
    - `ALGORITHM`
    - `ACCESS_TOKEN_EXPIRE_MINUTES`
    - LLM 默认 provider/model/base URL/timeout/max tokens
    - provider 专属 API key 默认值
  - Rust `/api/v1/system-config/defaults` 已改为从 `AppConfig` 生成默认值
  - Rust 向 legacy `user_configs` 做 shadow write 时，敏感 LLM key 字段已按 Rust 加密逻辑落密文，不再继续写明文 mirror
  - Rust 新增回归测试：
    - `backend/src/core/security.rs` 模块测试
    - `backend/src/core/encryption.rs` 模块测试
    - `backend/src/routes/system_config.rs` 模块测试
    - `backend/tests/system_config_api.rs`
- 当前意义：
  - Rust 不再只有一个“能启动服务”的 `config.rs` 壳，已经开始拥有自己的 core config/security/encryption 原语
  - `system-config` 这条 Rust-owned 控制面链路的默认值与敏感字段处理，不再继续完全依赖 Python core 模块
  - 这一步解决的是 ownership 补齐，不是假删 Python 文件
- 仍未完成：
  - `backend_old/app/core/config.py` 仍被 Python runtime / llm / agent / runner / db session 广泛 import
  - `backend_old/app/core/security.py` 仍被测试与若干 Python service 调用
  - `backend_old/app/core/encryption.py` 仍被 `user_config_service.py` 及其上游 Python 端点调用
  - 所以 `backend_old/app/core/*` 现在只能说“Rust 已部分 owned，Python 仍是 bridge”，还不能删除 live 文件
- 删除条件：
  - Python runtime / llm / agent / init_db / db session 不再 import `backend_old/app/core/config.py`
  - Python side 不再调用 `backend_old/app/core/security.py`
  - Python `user_config_service.py` 与相关 live endpoint 不再调用 `backend_old/app/core/encryption.py`
  - Rust 成为 token/hash/encryption/default-config 的唯一 live source of truth
- 下一刀：
  - 继续沿 Phase A 往前推，把仍直接 import `backend_old/app/core/*` 的 Python live caller 收口，优先处理 `user_config_service.py`、`db/session.py` 和 runtime/runner 公共入口

### 2026-04-11 Batch 1 / Slice 5

- 已完成：
  - `backend_old/app/db/__init__.py` 新增统一 asset helper，Python DB 侧读取 scan 相关资产时会优先走 Rust owner root：
    - `backend/assets/scan_rule_assets/rules_opengrep`
    - `backend/assets/scan_rule_assets/rules_from_patches`
    - `backend/assets/scan_rule_assets/patches`
    - `backend/assets/scan_rule_assets/gitleaks_builtin`
    - `backend/assets/scan_rule_assets/bandit_builtin`
    - `backend/assets/scan_rule_assets/rules_pmd`
  - 已切换到 helper 的 Python 消费方：
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
  - 已补/更新回归测试：
    - `backend_old/tests/test_pmd_rules_service.py`
    - `backend_old/tests/test_bandit_rules_snapshot.py`
    - `backend_old/tests/test_external_tools_manual.py`
  - 已验证：
    - `cd backend_old && ./.venv/bin/pytest tests/test_pmd_rules_service.py tests/test_bandit_rules_snapshot.py tests/test_external_tools_manual.py -q`
- 当前意义：
  - Rust 已经在真实消费的 scan rule assets，不再需要在 `backend_old/app/db` 再维护一份重复副本
  - Python live caller 继续保留，但其资产 source of truth 已开始收敛到 Rust owner root
  - 这一步是真删除，不是只写台账
- 仍未完成：
  - `backend_old/app/models/*`、`backend_old/alembic/env.py` 与 `backend_old/tests/conftest.py`
    仍在使用 SQLAlchemy `Base.metadata`，但宿主已从 `app.db.base` 迁到
    `app.models.base`
  - `backend_old/app/db/session.py` 已在后续 slice 中退休；live Python 路径不再依赖该 DB session shell
  - 路径归一化 helper已迁入 `backend_old/app/services/scan_path_utils.py`，`static_finding_paths.py` 不再出现在 live tree，agent_tasks_bootstrap、phpstan、bandit、opengrep 皆在调用新 helper
  - `backend_old/app/db/schema_snapshots/*` 仍被 Alembic baseline 兼容迁移使用
  - `backend_old/app/db/rules_phpstan` 仍由 Python static-tasks 直接消费，Rust 尚未接管 phpstan 运行链路
  - `backend_old/app/db/yasa_builtin` 仍由 Python YASA snapshot/service 直接消费，Rust 未接管
- 删除条件：
  - `app.db.base` import blocker 已清零并完成退休；后续只需继续收口 `app.models.base` /
    Alembic / tests 对 `Base.metadata` 的依赖，再决定何时整体退休 ORM
  - `session.py` 已在 live caller 清零后退休；路径归一化逻辑已迁入 `backend_old/app/services/scan_path_utils.py`
  - `schema_snapshots/*` 只有在 `backend_old/alembic` 不再依赖 baseline snapshot 后才能删
  - `rules_phpstan` 只有在 Rust 真正接管 phpstan scanner/runtime 后才能删
  - `yasa_builtin` 只有在 YASA 被彻底 retire 或迁离 Python live 路径后才能删
- 下一刀：
  - 继续 Phase A / C，优先处理 `base.py` 与其余 DB/model live caller 的收口

## backend_old/app/db 迁移清单

Rust 替代 `backend_old/app/db` 的全部 ownership 需要按照以下八个门依序完成。第 1、2 项的 Rust 侧实现已经落地，但目录当前仍被 Python 模块 live import，因而不能直接删。

1. 环境/配置 DB 拆分（已完成）：Rust/Python 的 DB 环境配置 plumbing 已分离，`PYTHON_DB_*` 和 `PYTHON_ALEMBIC_ENABLED` 只作用于 Python runtime；Rust 通过 `DATABASE_URL`/`AppConfig` 直接构建自己的 schema 检查，后续只需确认没有 bridge 共享 env 即可。
2. 启动/迁移/健康分离（已完成）：Rust `bootstrap` 负责 startup preflight、legacy schema 对齐、`/health` 报表与迁移 gating，Python 只继续运行未迁出的模块；校验 Rust 的 `bootstrap` 状态暴露与迁移检查覆盖面后即可认定本项完成。
3. 替换 `app.db.base`（已完成）：验证命令是 `rg -n "from app\\.db\\.base import Base|from app\\.db\\.base import|app\\.db\\.base" backend_old/alembic backend_old/app backend_old/tests`。当前该命令已清零；`Base` 宿主已迁到 `backend_old/app/models/base.py`，`backend_old/app/db/base.py` 已退休。owner 是 Rust migration Phase A/B。
4. 替换 `app.db.session` 调用者：验证命令是 `rg -n "from app\\.db\\.session import|app\\.db\\.session import|get_db|AsyncSessionLocal|async_session_factory" backend_old/app backend_old/tests backend_old/scripts`。当前 live blockers 已清零，说明 live Python 路径已不再依赖 `app.db.session`；后续只需继续用退休守门测试和 Rust 合同测试守住该状态；owner 是 Rust migration Phase A/D。
5. 将 `init_db` 语义移入 Rust：验证命令是 `rg -n "from app\\.db\\.init_db|import init_db|init_db\\(" backend_old/app backend_old/tests backend_old/scripts`。当前 blockers 已清零，说明 demo user、seed project、legacy rule seed、schema bootstrap 不再依赖 Python `init_db.py`；后续只需继续用 Rust bootstrap/preflight 合同测试守住该语义；owner 是 Rust migration Phase A。
6. 路径归一化 helper迁新家：验证命令是 `rg -n "scan_path_utils|normalize_scan_file_path|resolve_scan_finding_location" backend_old/app backend_old/tests`。当前 live caller 包括 `backend_old/app/api/v1/endpoints/agent_tasks_bootstrap.py`、`backend_old/app/services/agent/bootstrap/phpstan.py`、`backend_old/app/services/agent/bootstrap/bandit.py`、`backend_old/app/services/agent/bootstrap/opengrep.py` 与 `backend_old/tests/test_scan_path_utils.py`，它们都应 import 自 `backend_old/app/services/scan_path_utils.py`，不再提旧的 `static_finding_paths.py`。翻门条件是 `backend_old/app` 和 `backend_old/tests` 只剩 `scan_path_utils` 相关命中，旧 helper 字串彻底下架；owner 是 Rust migration Phase C/D。
7. Alembic/schema_snapshots 清理门：验证命令是 `rg -n "schema_snapshots|baseline_5b0f3c9a6d7e|normalize_static_finding_paths" backend_old/alembic backend_old/tests`。当前 blockers 是 `backend_old/alembic/versions/5b0f3c9a6d7e_squashed_baseline.py`、`backend_old/alembic/versions/7f8e9d0c1b2a_normalize_static_finding_paths.py`、`backend_old/tests/test_alembic_project.py`。翻门条件是 Rust 已覆盖 legacy baseline/schema compatibility，这个命令不再命中 `schema_snapshots/*` 或 static-finding normalization 迁移，`test_alembic_project.py` 删除或改写为 Rust migration contract；owner 是 Rust migration Phase A legacy-schema owner。
8. backend_old/app/db 最终删除门：验证命令先跑 `rg -n "app\\.db\\." backend_old/app backend_old/tests backend_old/alembic backend_old/scripts`，再跑 `rg --files backend_old/app/db`。当前阻塞集合至少包括 `agent_tasks_bootstrap.py`（执行/mixed-test helper 残留，scope filtering、bootstrap policy、bootstrap findings、Bandit bootstrap rule 选择、bootstrap seeds、bootstrap entrypoint fallback、Gitleaks bootstrap runtime 已迁入 `backend_old/app/services/agent/{scope_filters,bootstrap_policy,bootstrap_findings,bandit_bootstrap_rules,bootstrap_seeds,bootstrap_entrypoints,bootstrap_gitleaks_runner}.py`）、`backend_old/alembic/env.py` 与相关测试。`static_scan_runtime.py` 已在 2026-04-14 Batch 4 / Slice 12 依据 repo 内无 live caller 证据退休，不再计入当前 blocker。翻门条件是第一条命令在 live 路径返回 `0`，第二条命令不再列出需要保留的 live 模块，并且 Rust-only startup smoke/health 已通过；owner 是整个 Rust migration owner，签字条件是确认 `backend_old/app/db` 不再被任何 live Python 路径依赖。

当前 `backend_old/app/db` 仍被 static/agent services、部分 FastAPI endpoints、测试等活跃路径 import，因此该目录尚不安全删除。

### 2026-04-11 Batch 1 / Slice 6

  - 已完成：
    - Rust 新增 `backend/src/scan/phpstan.rs`
      - 已能从 Rust 资产库读取 `rules_phpstan/*`
      - 已能 materialize `phpstan_rules_combined.json` 与 `rule_sources/`
      - 已补模块测试
  - Rust `backend/src/bootstrap/preflight.rs` 已把 `phpstan` preflight 接到 Rust 资产 materialize 链路
  - Python `backend_old/app/db/rules_phpstan` 已物理删除
  - 已验证：
    - `cargo test`
    - `cd backend_old && ./.venv/bin/pytest tests/test_phpstan_static_tasks.py tests/test_phpstan_bootstrap_scanner.py -q`
- 当前意义：
  - `rules_phpstan` 不再只是“放在 Rust 目录里”，而是已经进入 Rust 真消费链路
  - `backend_old/app/db/rules_phpstan` 的重复副本已经删除，phpstan DB 资产 source of truth 收口到 Rust
- 仍未完成：
  - `phpstan_scan_tasks` / `phpstan_findings` / `phpstan_rule_states` 仍由 legacy runtime 链路持有
  - 这一步完成的是 phpstan DB 资产接管，不是 phpstan 整条运行时接管
- 已开始但未完成：
  - YASA 退役已进入执行态，后端已移除大部分模型/服务/launcher/route 主体
  - frontend live path 已完成去 YASA：
    - 移除 `yasaTaskId` / `tool=yasa` 路由参数拼装
    - 移除 `Yasa*` 前端类型、详情页分支、任务活动/项目预览聚合
    - 移除创建扫描对话框与混合扫描 bootstrap 中的 YASA 配置入口
    - 前端相关回归测试已同步改为无 YASA 口径
  - 当前主要残留已收缩到少量 mixed tests / inventory / 文本文档残项
- 下一刀：
  - 清完剩余 mixed tests / inventory / 文本残项，并确认 Python live bridge 不再被前端间接引用

### 2026-04-13 Batch 3 / Slice 1

- 已完成：
  - Rust 新增 `backend/src/project_file_cache.rs`
    - 已实现 project file-content cache 的 TTL / LRU / memory stats / clear / invalidate
    - 已补模块测试，覆盖过期清理与 expired-on-read 行为
  - `backend/src/state.rs` 已挂载全局 `project_file_cache`
  - `backend/src/routes/projects.rs` 已把下列 route 从 cache 空壳改为真实行为：
    - `GET /api/v1/projects/{id}/files/{*file_path}`
    - `GET /api/v1/projects/cache/stats`
    - `POST /api/v1/projects/cache/clear`
    - `POST /api/v1/projects/{id}/cache/invalidate`
  - archive 更新/删除时会主动失效项目 file-content cache：
    - `upload_project_zip`
    - `upload_project_directory`
    - `delete_project_zip`
    - `delete_project`
  - Python `backend_old/app/services/zip_cache_manager.py` 已物理删除
  - Python 旧专属测试 `backend_old/tests/test_zip_cache_manager.py` 已删除
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `4`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `229`
    - `rg -n "zip_cache_manager|ZipCacheManager" backend/src backend_old/app backend_old/tests -S`
      只剩退休守门测试命中
- 当前意义：
  - Rust `projects` 路由组不再只是暴露 cache endpoint 的空壳，而是已接住 `zip_cache_manager` 对应的真实行为
  - `backend_old/app/services/zip_cache_manager.py` 这条 Python service 已达到删除门：无 live caller、无主链路依赖、Rust 已接管运行时行为
  - 这一步是 project file-content cache 接管，不是整个 upload/archive shared service 全量完成
- 仍未完成：
  - `backend_old/app/services/zip_storage.py` 仍不能删
    - `backend_old/app/services/upload/project_stats.py`
      仍通过 ZIP 磁盘布局 / `ZIP_STORAGE_PATH` 读旧 bridge
  - `backend_old/app/services/upload/*` 与 `project_stats.py` 仍不能一起宣告退休
    - frontend 当前仍允许 `.tar/.tar.gz/.tar.bz2/.7z/.rar` 上传后缀
    - Rust `projects` 目前仍是 zip-only contract
  - `create-with-zip` / description 相关语言画像仍未等价接住 Python `project_stats.py`
    的 cloc / suffix fallback / LLM 描述语义
  - Rust 合同测试当前无法在本机完成：
    - `cargo test --manifest-path backend/Cargo.toml --test projects_api projects_domain_endpoints_cover_files_stats_and_transfer -- --exact`
    - 失败原因是本机 `rustc 1.85.0` 低于 lockfile 依赖要求（`time/zip/home/icu_*` 需要 `1.86~1.88`）
- 删除条件：
  - `zip_cache_manager.py`：已删除，本 slice 完成
  - `zip_storage.py`：只有在 Python upload/static-scan bridge 不再通过 ZIP 文件根读取项目归档时才能删
  - `upload/*`：只有在 frontend upload contract 明确收口到 zip-only，或 Rust 补齐非 zip archive 支持后才能删
- 下一刀：
  - 在 `zip-only` vs `multi-archive` contract 上做决策
  - 再决定是继续迁 `zip_storage` bridge，还是补齐 `upload/project_stats` 语义

### 2026-04-13 Batch 3 / Slice 2

- 已完成：
  - Python root diagnostics 已物理删除：
    - `backend_old/verify_llm.py`
    - `backend_old/check_docker_direct.py`
    - `backend_old/check_sandbox.py`
  - 退休守门测试已补到 `backend_old/tests/test_legacy_backend_main_retired.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `1`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `229`
    - `rg -n "verify_llm.py|check_docker_direct.py|check_sandbox.py" backend_old plan backend docker scripts .github -S`
      只剩退休守门测试与迁移文档命中
- 当前意义：
  - `root bootstrap / diagnostics` 里的三条纯诊断脚本已经从 live tree 清掉
  - `backend_old` 根目录现在只剩 `main.py` 这一条 Python 文件待后续 migration/retire 判定
  - 这一步是 Phase F 的 diagnostics retirement，不涉及 runtime/compose 主链路
- 仍未完成：
  - `backend_old/main.py` 仍在 root live tree 中，尚未达到删除门
  - 当前 plan 顶部 inventory 数字已刷新，但整个非 API migration 目标远未完成
- 删除条件：
  - `verify_llm.py` / `check_docker_direct.py` / `check_sandbox.py`：已删除，本 slice 完成
  - `backend_old/main.py`：只有在 root bootstrap / startup responsibility 全部收口到 Rust 后才能删
- 下一刀：
  - 继续收口 root `main.py` 与剩余 Phase C shared service / bridge

### 2026-04-13 Batch 3 / Slice 3

- 已完成：
  - Python root entry `backend_old/main.py` 已物理删除
  - `backend_old/tests/test_legacy_backend_main_retired.py`
    已补 root `main.py` 退休守门测试
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `229`
    - `rg -n "backend_old/main.py|Hello from VulHunter-backend" backend_old backend docker scripts .github frontend plan -S`
      只剩迁移文档命中
- 当前意义：
  - `backend_old` 根目录 Python live surface 已清零
  - `root bootstrap / diagnostics` 这一桶现在全部从 live tree 中退出
  - root Python 入口责任已经完全收口到 Rust / 现有 Docker 启动链路
- 仍未完成：
  - 整体 non-API migration 目标仍远未完成，主战场还在 `app/core`、`app/db`、`upload`、`llm`、`agent`
- 删除条件：
  - `backend_old/main.py`：已删除，本 slice 完成
- 下一刀：
  - 回到 Phase C / Phase A 主线，继续收口真实 bridge，而不是只清 dead entry

### 2026-04-13 Batch 3 / Slice 4

- 已完成：
  - Python dead service 已物理删除：
    - `backend_old/app/services/search_service.py`
    - `backend_old/app/services/report_generator.py`
  - Python 旧专属测试已删除：
    - `backend_old/tests/test_search_service.py`
    - `backend_old/tests/test_report_generator_contract.py`
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `227`
    - `rg -n "search_service.py|report_generator.py|SearchService|ReportGenerator" backend_old backend frontend plan -S`
      只剩退休守门测试、离线规则文本与迁移文档命中
- 当前意义：
  - `search_service.py` 与 `report_generator.py` 已确认不在 live caller 链路里，只剩 legacy tests 依赖
  - 这两条 shared service 已从 `migrate_now` 资产表移出，转为已退休 dead service
  - 当前 `services/scan/search/report/project` 桶中的真实 `migrate_now` 剩余项进一步收缩到：
    - `zip_storage.py`
    - `json_safe.py`
    - `runner_preflight.py`
- 仍未完成：
  - Rust `search` 仍只有 project search 真正 owned，tasks/findings search 仍是空壳
  - `zip_storage.py`、`runner_preflight.py` 以及 upload/project bridge 仍是活跃收口对象
- 删除条件：
  - `search_service.py` / `report_generator.py`：已删除，本 slice 完成
- 下一刀：
  - 回到仍有 live bridge 的 `zip_storage.py` / `runner_preflight.py` / upload contract

### 2026-04-13 Batch 3 / Slice 5

- 已完成：
  - Python dead service 已物理删除：
    - `backend_old/app/services/runner_preflight.py`
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `226`
    - `rg -n "runner_preflight.py|run_configured_runner_preflights|get_configured_runner_preflight_specs|RunnerPreflightSpec" backend_old backend plan scripts -S`
      live runtime 命中只剩 Rust `backend/src/bootstrap/preflight.rs` 与 release template helper
- 当前意义：
  - runner preflight 的 live ownership 已明确在 Rust bootstrap，Python `runner_preflight.py` 不再作为运行时实现保留
  - `services/scan/search/report/project` 桶中的真实 `migrate_now` 继续收缩到：
    - `zip_storage.py`
    - `json_safe.py`
- 仍未完成：
  - `zip_storage.py` 仍是活 bridge
  - `json_safe.py` 仍被 Python agent/event manager live caller 使用
  - release template helper `scripts/release-templates/runner_preflight.py` 仍存在，它不是 `backend_old` live service
- 删除条件：
  - `runner_preflight.py`：已删除，本 slice 完成
- 下一刀：
  - 继续收口真正仍有 live caller 的 `zip_storage.py` / `json_safe.py` / upload bridge

### 2026-04-13 Batch 3 / Slice 6

- 已完成：
  - Python dead helper/service 已物理删除：
    - `backend_old/app/services/opengrep_confidence.py`
    - `backend_old/app/services/init_templates.py`
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `224`
    - `rg -n "opengrep_confidence.py|init_templates.py|init_templates_and_rules|normalize_confidence|extract_rule_lookup_keys" backend_old backend frontend plan -S`
      live caller 只剩 `agent/bootstrap/opengrep.py` 内联后的 confidence helper 与迁移文档命中
- 当前意义：
  - `opengrep_confidence.py` 已确认不再承担 live runtime 职责，相关 confidence 逻辑已内联到
    `backend_old/app/services/agent/bootstrap/opengrep.py`
  - `init_templates.py` 已确认没有 live caller，不再作为待迁共享服务保留
  - `services/scan/search/report/project` 桶里的 `migrate_with_api` 集合继续收缩
- 仍未完成：
  - `zip_storage.py` 与 `json_safe.py` 仍在 `migrate_now`
  - `seed_archive.py`、`parser.py`、`rule.py`、`gitleaks_rules_seed.py`、`pmd_rulesets.py`、
    `bandit_rules_snapshot.py` 等仍在 `migrate_with_api`
- 删除条件：
  - `opengrep_confidence.py` / `init_templates.py`：已删除，本 slice 完成
- 下一刀：
  - 回到仍有 live caller 的 `zip_storage.py` / `json_safe.py` / 其余 runtime bridge

### 2026-04-13 Batch 3 / Slice 7

- 已完成：
  - Python dead helper/service 已物理删除：
    - `backend_old/app/services/seed_archive.py`
  - 旧专属测试已删除：
    - `backend_old/tests/test_seed_archive.py`
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `223`
    - `rg -n "seed_archive.py|build_seed_archive_candidates|download_seed_archive" backend_old backend frontend plan -S`
      只剩退休守门测试与迁移文档命中
- 当前意义：
  - `seed_archive.py` 已确认没有 live caller，不再作为待迁 helper 保留
  - `services/scan/search/report/project` 桶中的 `migrate_with_api` 继续收缩
- 仍未完成：
  - `zip_storage.py` 与 `json_safe.py` 仍在 `migrate_now`
  - `gitleaks_rules_seed.py`、`pmd_rulesets.py`、`parser.py`、`rule.py`、
    `bandit_rules_snapshot.py` 等仍在 `migrate_with_api`
- 删除条件：
  - `seed_archive.py`：已删除，本 slice 完成
- 下一刀：
  - 继续筛剩余 dead service，或回到 `zip_storage.py` / `json_safe.py` 这类活桥

### 2026-04-13 Batch 3 / Slice 8

- 已完成：
  - Python dead implementation 已物理删除：
    - `backend_old/app/services/zip_storage.py`
    - `backend_old/app/services/upload/compression_factory.py`
    - `backend_old/app/services/upload/compression_handlers.py`
    - `backend_old/app/services/upload/compression_strategy.py`
    - `backend_old/app/services/upload/language_detection.py`
    - `backend_old/app/services/upload/project_stats.py`
    - `backend_old/app/services/upload/upload_manager.py`
  - 旧专属测试已删除：
    - `backend_old/tests/test_llm_description.py`
    - `backend_old/tests/test_cloc_stats.py`
    - `backend_old/tests/test_project_stats_suffix_fallback.py`
    - `backend_old/tests/test_file_upload_compress.py`
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `216`
    - `rg -n "zip_storage.py|get_project_zip_path|project_stats.py|generate_project_description|get_cloc_stats_from_archive|UploadManager|CompressionStrategyFactory|compression_handlers.py|compression_strategy.py|language_detection.py" backend_old backend frontend plan -S`
      live caller 命中只剩 Rust `projects` 路由、退休守门测试与迁移文档
- 当前意义：
  - Rust `projects` 已承接 live upload / archive / description HTTP surface；旧 Python `zip_storage.py` 和 `upload/*` 仅剩参考实现与测试依赖，现已整体退休
  - 这一步是 dead implementation retirement，不代表 Rust 已全量等价旧 Python upload 语义
  - `services/upload` 整桶已从 live tree 清空；`services/scan/search/report/project` 里的 `migrate_now` 继续收缩到只剩 `json_safe.py`
- 仍未完成：
  - frontend 当前仍允许非 zip archive 后缀，但 Rust `projects` 仍是 zip-only contract
  - `json_safe.py` 仍被 Python agent/event manager live caller 使用
  - `gitleaks_rules_seed.py`、`pmd_rulesets.py`、`parser.py`、`rule.py`、`bandit_rules_snapshot.py` 等仍在 `migrate_with_api`
- 删除条件：
  - `zip_storage.py` / `upload/*` / `project_stats.py`：已删除，本 slice 完成
- 下一刀：
  - 回到真正仍有 live caller 的 `json_safe.py` / `parser.py` / runtime bridge

### 2026-04-13 Batch 3 / Slice 9

- 已完成：
  - Python dead implementation 已物理删除：
    - `backend_old/app/services/scanner.py`
    - `backend_old/app/services/gitleaks_rules_seed.py`
  - 旧专属测试已删除：
    - `backend_old/tests/test_file_selection.py`
    - `backend_old/tests/test_file_selection_e2e.py`
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `214`
    - `rg -n "from app\\.services\\.scanner import|import app\\.services\\.scanner|is_text_file\\(|should_exclude\\(|EXCLUDE_PATTERNS|from app\\.services\\.gitleaks_rules_seed import|import app\\.services\\.gitleaks_rules_seed|ensure_builtin_gitleaks_rules\\(" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已清零，只剩退休守门测试与迁移文档
- 当前意义：
  - `scanner.py` 与 `gitleaks_rules_seed.py` 已确认没有 live caller，不再作为待迁 implementation 保留
  - runtime / project-service 两个桶里的 dead implementation 继续收缩
- 仍未完成：
  - `json_safe.py`、`parser.py`、`flow_parser_runtime.py`、`flow_parser_runner.py`、`scanner_runner.py`、
    `static_scan_runtime.py`、`user_config_service.py` 等仍有 live caller
- 删除条件：
  - `scanner.py` / `gitleaks_rules_seed.py`：已删除，本 slice 完成
- 下一刀：
  - 转入真正还有 live caller 的桥，优先 `json_safe.py` 或 `parser.py`

### 2026-04-13 Batch 4 / Slice 1

- 已完成：
  - Rust `backend/src/routes/search.rs` 已把下列 route 从空壳补成真实实现：
    - `GET /api/v1/search/tasks/search`
    - `GET /api/v1/search/findings/search`
    - `GET /api/v1/search/search` 里的 `tasks/findings` 聚合
  - 搜索数据源已接到 Rust `task_state` snapshot：
    - agent task 搜索匹配 `name/description/task_type/status/created_at`
    - static task 搜索匹配 `name/engine/status/target_path/created_at`
    - agent/static finding 搜索匹配 `title/description/vulnerability_type/file_path/code_snippet|match`
  - `backend/tests/search_api.rs` 已从“断言空数组”改为要求真实 task/finding 命中
  - 当前测试通过公开路由创建 agent/static task，并验证分页 total 与 task/finding 命中
- 当前意义：
  - Rust `search` 不再只有 project search 真正可用；task/finding search 已不再是空壳
  - 这一步补的是 Rust own route 语义，不涉及新的 Python 文件删除
- 仍未完成：
  - rule 维度搜索仍未进入 Rust search 结果
  - `search` 整体仍不能算 fully migrated
  - 本机仍无法执行 `cargo test --test search_api`，因为 `rustc 1.85.0` 低于依赖要求
- 删除条件：
  - 本 slice 无直接 Python 文件删除门；这是 Rust route 语义补全
- 下一刀：
  - 继续补 static task / finding search，或转入 `json_safe.py` / `parser.py` 这类 live bridge 迁移

### 2026-04-13 Batch 4 / Slice 2

- 已完成：
  - `backend_old/app/services/project_test_service.py` 已物理删除
  - `normalize_extracted_project_root` 已内聚回
    `backend_old/app/services/agent/skill_test_runner.py`
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已改为要求 `skill_test_runner.py` 本地持有该 helper
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
    - `rg -n "project_test_service|normalize_extracted_project_root" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已收口到 `skill_test_runner.py` 与退休守门测试
- 当前意义：
  - 单点 helper 不再挂在顶层 `app/services`，而是回到唯一实际使用它的 agent 域内
  - 这是顶层 helper 内聚退休，不涉及新的 Rust route/DB ownership
- 仍未完成：
  - `json_safe.py`、`parser.py`、`flow_parser_runtime.py`、`flow_parser_runner.py`、
    `scanner_runner.py`、`static_scan_runtime.py`、`user_config_service.py` 等仍有 live caller
- 删除条件：
  - `project_test_service.py`：已删除，本 slice 完成
- 下一刀：
  - 继续收口顶层 helper，或转入真正的 live bridge 迁移

### 2026-04-13 Batch 4 / Slice 3

- 已完成：
  - `backend_old/app/services/parser.py` 已物理删除
  - `TreeSitterParser` 已迁入
    `backend_old/app/services/agent/flow/lightweight/tree_sitter_parser.py`
  - 下列 caller 已改为从 lightweight 域内 import：
    - `backend_old/app/services/agent/flow/lightweight/ast_index.py`
    - `backend_old/app/services/agent/flow/lightweight/function_locator.py`
    - `backend_old/app/services/agent/flow/lightweight/definition_provider.py`
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
    - `rg -n "from app\\.services\\.parser import|import app\\.services\\.parser|TreeSitterParser" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已收口到 `agent/flow/lightweight` 域内
- 当前意义：
  - `parser.py` 不再以顶层 service 形式存在，tree-sitter parser 已内聚到实际消费它的 lightweight flow 域
  - 这是顶层 parser helper 内聚退休，不涉及新的 Rust route/DB ownership
- 仍未完成：
  - `flow_parser_runner.py`、`scanner_runner.py`、`static_scan_runtime.py`、`json_safe.py`、`user_config_service.py` 等仍有 live caller
- 删除条件：
  - `parser.py`：已删除，本 slice 完成
- 下一刀：
  - 继续收口顶层 flow/runtime helper，或转入真正的 live bridge 迁移

### 2026-04-13 Batch 4 / Slice 4

- 已完成：
  - `backend_old/app/services/sandbox_runner_client.py` 已迁入
    `backend_old/app/services/agent/tools/sandbox_runner_client.py`
  - `backend_old/app/services/agent/tools/sandbox_tool.py`
    已改为从 agent/tools 域内 import
  - `backend_old/tests/test_sandbox_runner_client.py`
    已同步指向新模块路径
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
    - `rg -n "sandbox_runner_client|SandboxRunnerClient" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已收口到 `agent/tools` 域内与测试
- 当前意义：
  - `sandbox_runner_client.py` 不再作为顶层 service 保留，而是下沉到唯一实际消费它的 agent/tools 域
  - 这是顶层 sandbox helper 内聚退休，不涉及新的 Rust route/DB ownership
- 仍未完成：
  - `scanner_runner.py`、`static_scan_runtime.py`、`json_safe.py`、`user_config_service.py` 等仍有 live caller
- 删除条件：
  - 顶层 `sandbox_runner_client.py`：已退休，本 slice 完成
- 下一刀：
  - 继续收口顶层 runtime/agent helper，或转入真正的 live bridge 迁移

### 2026-04-13 Batch 4 / Slice 5

- 已完成：
  - `backend_old/app/services/backend_venv.py` 已物理删除
  - helper 已内聚回 `backend_old/app/services/static_scan_runtime.py`
    - `_build_backend_venv_env`
    - `_resolve_backend_venv_executable`
    - `_get_backend_venv_path`
    - `_get_backend_venv_bin_dir`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `212`
    - `rg -n "backend_venv|build_backend_venv_env|resolve_backend_venv_executable|get_backend_venv_path|get_backend_venv_bin_dir" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已收口到 `static_scan_runtime.py`、退休守门测试与 Rust runtime/bootstrap
- 当前意义：
  - `backend_venv.py` 不再作为顶层 runtime helper 保留，而是回到唯一实际消费它的 `static_scan_runtime.py`
  - 这是顶层 runtime helper 内聚退休，不涉及新的 Rust route/DB ownership
- 仍未完成：
  - `scanner_runner.py`、`static_scan_runtime.py`、`json_safe.py`、`user_config_service.py` 等仍有 live caller
- 删除条件：
  - `backend_venv.py`：已删除，本 slice 完成
- 下一刀：
  - 继续收口顶层 runtime helper，或转入真正的 live bridge 迁移

### 2026-04-13 Batch 4 / Slice 6

- 已完成：
  - `backend_old/app/services/user_config_service.py` 已物理删除
  - 用户配置默认值/解密/清洗/effective merge 逻辑已内聚回
    `backend_old/app/services/static_scan_runtime.py`
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补退休守门测试
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已改为要求 `static_scan_runtime.py` 本地持有 `_load_effective_user_config`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
    - `rg -n "from app\\.services\\.scanner_runner import|import app\\.services\\.scanner_runner|from app\\.services import scanner_runner" backend_old/app backend_old/tests -S`
      => no matches
    - `rg -n "user_config_service|load_effective_user_config|_load_effective_user_config|sanitize_other_config|strip_runtime_config|_default_user_config" backend_old/app backend_old/tests backend/src frontend -S`
      live caller 已收口到 `static_scan_runtime.py` 与退休守门测试
- 当前意义：
  - `user_config_service.py` 不再作为顶层 helper 保留，而是回到唯一实际消费它的 `static_scan_runtime.py`
  - 这是顶层 config/helper 内聚退休，不涉及新的 Rust route/DB ownership
- 仍未完成：
  - `scanner_runner.py`、`static_scan_runtime.py`、`json_safe.py` 等仍有 live caller
- 删除条件：
  - `user_config_service.py`：已删除，本 slice 完成
- 下一刀：
  - 继续收口顶层 runtime helper，或转入真正的 live bridge 迁移

### 2026-04-13 Batch 4 / Slice 7

- 已完成：
  - 顶层 `backend_old/app/services/json_safe.py` 已迁入
    `backend_old/app/services/agent/json_safe.py`
  - 下列 agent caller 已改为域内 import：
    - `agent/event_manager.py`
    - `agent/agents/analysis.py`
    - `agent/agents/recon.py`
    - `agent/agents/base.py`
    - `agent/agents/verification.py`
  - `backend_old/tests/test_json_safe.py` 已同步指向新模块路径
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
    - `rg -n "from app\\.services\\.json_safe import|import app\\.services\\.json_safe|dump_json_safe|normalize_json_safe" backend_old/app backend_old/tests -S`
      live caller 已收口到 agent 域内与测试
- 当前意义：
  - `json_safe.py` 不再作为顶层 helper 保留，而是下沉到唯一实际消费它的 agent 域
  - 这是顶层 agent helper 内聚退休，不涉及新的 Rust route/DB ownership
- 仍未完成：
  - `flow_parser_runner.py`、`scanner_runner.py`、`static_scan_runtime.py` 等仍有 live caller
- 删除条件：
  - 顶层 `json_safe.py`：已退休，本 slice 完成
- 下一刀：
  - 继续收口顶层 runtime helper，或进入 `static_scan_runtime.py` / `scanner_runner.py` 这类 live bridge

### 2026-04-13 Batch 4 / Slice 8

- 已完成：
  - 顶层 `backend_old/app/services/flow_parser_runner.py` 已迁入
    `backend_old/app/services/agent/flow/flow_parser_runner.py`
  - 下列 caller 已改为域内 import：
    - `agent/skill_test_runner.py`
    - `agent/flow/lightweight/function_locator.py`
    - `agent/flow/lightweight/callgraph_code2flow.py`
    - `agent/flow/lightweight/definition_provider.py`
  - `backend_old/tests/test_flow_parser_runner_client.py`
    已同步指向新模块路径
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
    - `rg -n "from app\\.services\\.flow_parser_runner import|import app\\.services\\.flow_parser_runner|get_flow_parser_runner_client|FlowParserRunnerClient" backend_old/app backend_old/tests -S`
      live caller 已收口到 agent/flow 域内与测试
- 当前意义：
  - `flow_parser_runner.py` 不再作为顶层 service 保留，而是下沉到唯一实际消费它的 agent/flow 域
  - 这是顶层 flow runner helper 内聚退休，不涉及新的 Rust route/DB ownership
- 仍未完成：
  - `scanner_runner.py`、`static_scan_runtime.py`、`json_safe.py`（已下沉）、`user_config_service.py`（已内聚）之外，
    仍有 `scanner_runner.py` / `static_scan_runtime.py` 这类 runtime bridge
- 删除条件：
  - 顶层 `flow_parser_runner.py`：已退休，本 slice 完成
- 下一刀：
  - 继续收口顶层 runtime helper，优先 `scanner_runner.py`

### 2026-04-14 Batch 4 / Slice 9

- 已完成：
  - 顶层 `backend_old/app/services/scanner_runner.py` 已迁入
    `backend_old/app/services/agent/scanner_runner.py`
  - 下列 live caller 已改为域内 import：
    - `agent/bootstrap/bandit.py`
    - `agent/bootstrap/opengrep.py`
    - `agent/bootstrap/phpstan.py`
    - `agent/bootstrap_gitleaks_runner.py`
    - `agent/flow/flow_parser_runner.py`
    - `agent/tools/external_tools.py`
    - `static_scan_runtime.py`
  - `backend_old/tests/test_scanner_runner.py` 已同步指向新模块路径
  - `backend_old/tests/test_flow_parser_runner_client.py`
    已改为 monkeypatch live `agent/flow/flow_parser_runner.py` 模块路径
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    已补 `scanner_runner.py` 退休守门测试
  - `stop_scanner_container_sync()` 缺失容器分支改为运行时读取
    `docker.errors.NotFound`，保留原有行为但修复 monkeypatch 不生效问题
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
- 当前意义：
  - `scanner_runner.py` 不再作为顶层 runtime bridge 保留，而是下沉到实际消费它的 agent 域
  - `run_scanner_container*` / `stop_scanner_container*`、`ScannerRunSpec` /
    `ScannerRunResult`、`SCANNER_MOUNT_PATH="/scan"`、workspace volume/root rewrite、
    `logs/` 与 `meta/runner.json` 语义均保持不变
- 仍未完成：
  - `static_scan_runtime.py` 仍是顶层 live runtime bridge
- 删除条件：
  - 顶层 `scanner_runner.py`：已退休，本 slice 完成
- 下一刀：
  - 继续收口顶层 runtime helper，优先 `static_scan_runtime.py`

### 2026-04-14 Batch 4 / Slice 10

- 已完成：
  - `static_scan_runtime.py` 顶部 workspace/helper cluster 已迁入
    `backend_old/app/services/agent/scan_workspace.py`：
    - `_scan_workspace_root`
    - `ensure_scan_workspace`
    - `ensure_scan_project_dir`
    - `ensure_scan_output_dir`
    - `ensure_scan_logs_dir`
    - `ensure_scan_meta_dir`
    - `cleanup_scan_workspace`
    - `copy_project_tree_to_scan_dir`
  - 下列 live caller 已改为从 agent 域共享模块 import：
    - `agent/bootstrap/bandit.py`
    - `agent/bootstrap/opengrep.py`
    - `agent/bootstrap/phpstan.py`
    - `agent/bootstrap_gitleaks_runner.py`
  - `backend_old/tests/test_static_scan_runtime.py`
    已改为直接覆盖 `agent/scan_workspace.py` 的 workspace helper 契约
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已补 bootstrap caller import guard，防止 workspace helper 回流到
    `static_scan_runtime.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `212`
    - `rg -n "from app\\.services\\.static_scan_runtime import|import app\\.services\\.static_scan_runtime|static_scan_runtime\\.(ensure_scan_workspace|ensure_scan_project_dir|ensure_scan_output_dir|ensure_scan_logs_dir|ensure_scan_meta_dir|cleanup_scan_workspace|copy_project_tree_to_scan_dir)" backend_old/app backend_old/tests -S`
      只剩 `backend_old/tests/test_config_internal_callers_use_service_layer.py`
      里的负向守门断言文本，不再有 live caller 命中
- 当前意义：
  - `static_scan_runtime.py` 不再拥有 scan workspace root、目录树创建/清理与
    project tree staging 这组纯文件系统 helper
  - 这一步是顶层 live bridge 的 ownership shrinkage，不是 Rust takeover，
    也不代表 `static_scan_runtime.py` 已退休
  - `backend_old/app` non-API Python 文件数本 slice 临时从 `211` 增至 `212`，
    原因是把单文件里的 helper cluster 拆成独立 agent 共享模块；
    这是结构收口，不是迁移回退
- 仍未完成：
  - `static_scan_runtime.py` 仍持有：
    - ZIP bridge / `_get_project_root`
    - backend venv helper
    - process/container cancel & tracking
    - progress store
    - user config / LLM validation
- 删除条件：
  - `agent/scan_workspace.py`：作为当前 live shared module 保留
  - `static_scan_runtime.py`：只有在剩余 ZIP/runtime/config 状态机能力继续拆空后，
    才能进入退休门
- 下一刀：
  - 继续收口 `static_scan_runtime.py` 剩余 capability cluster，
    优先避免触碰 ZIP contract 与 task/progress API 契约

### 2026-04-14 Batch 4 / Slice 11

- 已完成：
  - `static_scan_runtime.py` 中 task-tracking / cancellation cluster 已迁入
    `backend_old/app/services/agent/scan_tracking.py`：
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
    已改为从 `agent/scan_tracking.py` 显式 import 这一整组 helper/state，
    不再本地定义或持有第二份 tracking state
  - `backend_old/tests/test_static_scan_runtime.py`
    与 `backend_old/tests/test_background_task_launch_refactor.py`
    已改为直接覆盖 `agent/scan_tracking.py` 的 shared-state / cancel / background-job 契约
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    已补 AST import/ownership guard，要求 `static_scan_runtime.py`
    从 `app.services.agent.scan_tracking` 导入整组符号，防止 helper/state 回流
  - 验证命令：
    - `uv run --project . pytest -s tests/test_static_scan_runtime.py tests/test_background_task_launch_refactor.py tests/test_config_internal_callers_use_service_layer.py tests/test_scanner_runner.py`
      => `22 passed`
    - `rg -n "static_scan_runtime\\.(?:_scan_task_key|_register_static_background_job|_pop_static_background_job|_get_static_background_job|_launch_static_background_job|_shutdown_static_background_jobs|_is_scan_task_cancelled|_clear_scan_task_cancel|_register_scan_container|_pop_scan_container|_stop_scan_container|_request_scan_task_cancel|_is_scan_process_active|_terminate_scan_process|_run_subprocess_with_tracking)|from app\\.services\\.static_scan_runtime import|import app\\.services\\.static_scan_runtime" backend_old/app backend_old/tests -S`
      => 无命中（不只是不再有 live caller，连当前测试中的负向断言文本也未命中这条模式）
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
- 当前意义：
  - `static_scan_runtime.py` 不再拥有任务追踪、后台任务注册、进程/容器取消与 subprocess tracking 这一整组 runtime helper
  - 单例共享状态语义保持不变：共享 lock / dict / set 现在只存在于
    `agent/scan_tracking.py`，`static_scan_runtime.py` 只是兼容消费方
  - `_scan_task_key` 格式、`_request_scan_task_cancel()` 布尔返回语义、
    `_run_subprocess_with_tracking()` / `_terminate_scan_process()` /
    `_shutdown_static_background_jobs()` / `_stop_scan_container()` 行为契约保持不变
  - 这一步仍然是顶层 live runtime bridge 的 ownership shrinkage，
    不是 Rust takeover，也不表示 `static_scan_runtime.py` 已退休
  - `backend_old/app` non-API Python 文件数本 slice 临时从 `212` 增至 `213`，
    原因是把单文件中的 tracking/cancel cluster 拆成独立 agent shared module；
    这是结构收口，不是迁移回退
- 仍未完成：
  - `static_scan_runtime.py` 仍持有：
    - ZIP bridge / `_get_project_root`
    - backend venv helper
    - progress store
    - user config / LLM validation
- 删除条件：
  - `agent/scan_tracking.py`：作为当前 live shared module 保留
  - `static_scan_runtime.py`：只有在剩余 ZIP/runtime/config 能力继续拆空后，
    才能进入退休门
- 下一刀：
  - 继续收口 `static_scan_runtime.py` 剩余 capability cluster，
    优先 progress store 或 ZIP/config 之外、且不改变 API/runtime contract 的内部 helper

### 2026-04-14 Batch 4 / Slice 12

- repo 内退休证据：
  - `rg -n "from app\\.services\\.static_scan_runtime import|import app\\.services\\.static_scan_runtime|static_scan_runtime\\." backend_old/app backend_old/tests -S`
    在删除前只剩测试命中，没有 repo 内 direct live caller
  - 更宽口径检索
    `rg -n "importlib\\.(import_module|__import__)\\(|__import__\\(|app\\.services\\.static_scan_runtime|services/static_scan_runtime\\.py|static_scan_runtime" backend_old/app backend_old/scripts backend_old/tests -S`
    也只剩测试与迁移文本，没有动态导入或脚本入口证据
  - `backend_old/app/api/v1/api.py` 的 `api_router` 仍为空，本 slice 不改 route inventory
- 已完成：
  - 删除 `backend_old/app/services/static_scan_runtime.py`
  - `backend_old/tests/test_static_scan_runtime.py`
    保留为 `agent/scan_workspace.py` 与 `agent/scan_tracking.py` 的 shared helper 契约测试
  - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    改为守住“repo 内 live Python 模块不得再 import `static_scan_runtime`”
  - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    新增 service-module retirement guard，要求该文件物理不存在
  - 验证命令：
    - `uv run --project . pytest -s tests/test_static_scan_runtime.py tests/test_background_task_launch_refactor.py tests/test_config_internal_callers_use_service_layer.py tests/test_scanner_runner.py tests/test_api_router_rust_owned_routes_removed.py`
      => `54 passed, 1 warning`
    - warning 备注：
      `app/services/agent/knowledge/vulnerabilities/open_redirect.py:12`
      存在未触及的既有 `DeprecationWarning: invalid escape sequence '\/'`
- 当前意义：
  - 这是 Python 顶层 dead shell 退休：该文件在 repo 内已无 live caller，删除的是残留壳，不是新的 Rust takeover
  - 本 slice 不改 Rust 路由 ownership，不改 route inventory，也不改静态任务返回 shape（`status/progress/file_path/resolved_*`）
  - 这条记录覆盖前文仍把 `static_scan_runtime.py` 视为 live bridge 的临时判断；那些表述应视为历史快照，而非当前事实
- 仍未完成：
  - ZIP bridge、progress store、LLM/user-config 等能力如果还需要运行时承载，其当前 owner 仍需在后续 slice 中逐项核验；本 slice 只证明它们不再由 `static_scan_runtime.py` 承载

### 2026-04-13 Batch 4 / Slice 3

- 已完成：
  - `backend_old/app/services/flow_parser_runtime.py` 已物理删除
  - 其 definition-provider 逻辑已迁入
    `backend_old/app/services/agent/flow/lightweight/definition_provider.py`
  - `backend_old/app/services/agent/flow/lightweight/ast_index.py`
    已改为从 lightweight 域内 import provider
  - 退休守门测试已补到 `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
  - repo facts refresh：
    - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
    - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
    - `rg -n "flow_parser_runtime|get_default_definition_provider|DefinitionProvider|HybridDefinitionProvider|RunnerDefinitionProvider|LocalDefinitionProvider" backend_old/app backend_old/tests -S`
      live caller 已收口到 `agent/flow/lightweight` 域内
- 当前意义：
  - `flow_parser_runtime.py` 不再以顶层 service 形式存在，definition-provider 已内聚到实际消费它的 lightweight flow 域
  - 这是顶层 runtime helper 内聚退休，不涉及新的 Rust route/DB ownership
- 仍未完成：
  - `parser.py`、`flow_parser_runner.py`、`scanner_runner.py`、`static_scan_runtime.py` 等仍有 live caller
- 删除条件：
  - `flow_parser_runtime.py`：已删除，本 slice 完成
- 下一刀：
  - 继续收口顶层 flow/runtime helper，或转入 `json_safe.py` 等 live bridge

### 2026-04-15 Batch 4 / Slice 13

- 已完成：
  - Rust `GET /api/v1/skills/catalog` 默认语义已从
    `scan-core + prompt-builtin/custom resource list`
    切到 `scan-core + prompt-<agent_key>@effective` unified catalog
  - Rust `GET /api/v1/skills/catalog?resource_mode=external_tools`
    继续保留前端外部工具页所依赖的 compat resource shape：
    - scan-core resource
    - `prompt-builtin`
    - `prompt-custom`
  - Rust `GET /api/v1/skills/{skill_id}` 已支持：
    - `prompt-recon@effective`
    - `prompt-business_logic_recon@effective`
    - `prompt-analysis@effective`
    - `prompt-business_logic_analysis@effective`
    - `prompt-verification@effective`
  - prompt-effective detail 现已返回并显式区分：
    - `display_name`
    - `kind=prompt`
    - `source=prompt_effective`
    - `agent_key`
    - `runtime_ready`
    - `reason`
    - `load_mode`
    - `effective_content`
    - `prompt_sources`
  - effective prompt 合成顺序已固定为：
    - builtin template
    - active global custom prompt
    - active agent-specific custom prompt
  - custom prompt 合并顺序不再依赖存储后端返回顺序：
    - 先按 `created_at` 升序
    - 再按 `id` 做 tie-break
  - Rust 测试已补：
    - unified catalog 暴露五个 prompt-effective entry
    - `resource_mode=external_tools` compat contract
    - prompt-effective detail merge
    - `no_active_prompt_sources` 降级
    - merge 排序稳定性单测
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
- 验证命令：
  - `cd backend && cargo test --test skills_api`
    => `6 passed`
  - `cd backend && cargo test routes::skills::tests::build_prompt_effective_skill_sorts_custom_prompts_deterministically`
    => `1 passed`
  - `cd backend && cargo build --bin backend-rust`
    => exit `0`
  - `cd backend && cargo test`
    => exit `0`
  - gate 修正：
    - `backend/tests/projects_api.rs` 的 multipart test helper
      已补 quoted-string 转义，避免把带引号的 UTF-8 文件名
      组装成无效 `Content-Disposition` header
    - 复跑：
      `cd backend && cargo test --test projects_api download_project_archive_supports_utf8_filenames -- --exact --nocapture`
      => `1 passed`
- 当前意义：
  - 这一步把 Rust `skills` 默认 HTTP contract 往
    `prompt-effective unified catalog/detail` 推进了一刀
  - 这一步显式拆开了：
    - 默认 unified catalog
    - 前端 external-tools compat resource catalog
  - 这一步仍然只是 Rust `skills` surface contract 收口，
    不是 prompt skill storage ownership 完成
  - backend gate 现已恢复为绿色，可继续推进下一 slice
  - legacy `prompt_skills` 与 `user_configs.other_config.promptSkillBuiltinState`
    仍是当前 DB 模式下的 live 读路径
- 仍未完成：
  - prompt skill storage 尚未迁成 Rust-native source of truth
  - builtin prompt state 尚未迁成 Rust-native source of truth
  - `use_prompt_skills -> config.prompt_skills` 的 live 生产链路 owner
    还未完全收口到 Rust
  - `/skills/{id}/test` 与 `/tool-test` 仍是 scan-core SSE compat stub，
    不是 prompt-effective runtime/skill-test takeover
  - `skill_selection` / runtime session / guard / workflow registry
    仍不在本 slice 范围
- 删除条件：
  - `skills` 只有在 prompt skill storage、builtin prompt state、
    runtime injection producer、skill test runner / workflow contract
    都完成 Rust-owned 后，才能算“吃掉”
- 下一刀：
  - 优先收回 prompt skill persistence boundary：
    - custom prompt skill storage
    - builtin prompt state
  - 并把 legacy `prompt_skills` /
    `user_configs.other_config.promptSkillBuiltinState`
    降级为可删 compat mirror

### 2026-04-15 Batch 4 / Slice 14

- 已完成：
  - Rust 已新增 prompt skill Rust-native 主存储：
    - `rust_prompt_skills`
    - `rust_prompt_skill_builtin_states`
  - Rust 已新增：
    - `backend/src/db/prompt_skills.rs`
  - `backend/src/db/mod.rs` 已显式挂载 `prompt_skills`
  - `bootstrap::ensure_rust_schema()` 已创建这两张 Rust-native 表
  - `REQUIRED_RUST_TABLES` 与对应 bootstrap 测试已把这两张表纳入 Rust hard dependency
  - startup init allowlist 已新增：
    - `rust_prompt_skill_compat_backfill`
  - startup init 已在 Rust DB ready 时执行幂等 compat backfill：
    - 仅当 Rust-native prompt skill store 为空时，从 legacy `prompt_skills` 导入
    - 仅当 Rust-native builtin state 为空时，从 legacy
      `user_configs.other_config.promptSkillBuiltinState` 导入
    - 导入前后都做“only if empty”检查，不覆盖已有 Rust-native 数据
  - `backend/src/routes/skills.rs` 的 DB mode steady-state 主读路径已切到 Rust-native store：
    - custom prompt skills 读取不再直接查 legacy `prompt_skills`
    - builtin prompt state 读取不再直接查 legacy `user_configs.other_config`
  - `backend/src/routes/skills.rs` 的 DB mode mutation 已收口到记录级 helper：
    - create
    - update
    - delete
    - builtin toggle
  - 上述 DB mode mutation 现在在单个事务里同时写：
    - Rust-native 主存储
    - legacy compat mirror
  - `routes/skills.rs` 的 DB mode 不再走
    `load full set -> mutate in memory -> delete all + reinsert all`
    这一整套旧模式
  - `skills` 分页元数据已修正：
    - `total` 现在表示分页前总匹配数
    - 不再错误等于当前页 `items.len()`
  - Rust 测试已补：
    - `db::prompt_skills` backfill/owner/helper 纯逻辑测试
    - `skills_api` 分页 total 回归测试
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `213`
- 验证命令：
  - `cd backend && cargo test --test skills_api`
    => `7 passed`
  - `cd backend && cargo build --bin backend-rust`
    => exit `0`
  - `cd backend && cargo test`
    => exit `0`
    - `64 passed`
- 当前意义：
  - 这一步把 prompt-skill persistence boundary 从
    “Rust route + legacy DB 主存储” 推进到
    “Rust route + Rust-native DB 主存储 + legacy compat mirror”
  - 这一步把 custom prompt skills / builtin prompt state 的
    steady-state read owner 收回到 Rust
  - 这一步仍未完成 runtime 注入 owner 收口：
    `use_prompt_skills -> config.prompt_skills`
    的 live producer 还没有明确迁到 Rust
- 仍未完成：
  - legacy `prompt_skills` / `user_configs.other_config.promptSkillBuiltinState`
    仍需保留一轮 compat mirror
  - prompt skill runtime producer 仍未明确收口到 Rust
  - Python agents 当前仍直接消费 `config.prompt_skills`
    结果，而不是直接消费 Rust runtime session/protocol
  - `skill_selection` / runtime session / guard / workflow registry
    仍不在本 slice 范围
- 删除条件：
  - 只有当：
    - compat mirror 不再被任何 live 路径依赖
    - `config.prompt_skills` producer 改为 Rust-owned
    - prompt skill runtime 主链路不再需要 Python helper
    才能删除 legacy `prompt_skills` / builtin state mirror
- 下一刀：
  - 定位并收口
    `use_prompt_skills -> config.prompt_skills`
    的 live producer owner
  - 目标是把 Python agents 对 prompt skill 的消费前置到
    Rust runtime/task setup，而不是继续依赖 legacy Python helper

### 2026-04-15 Batch 4 / Slice 15

- 已完成：
  - `backend_old/app/services/agent/skills/prompt_skills.py`
    已物理删除
  - `backend_old/app/services/agent/skills/__init__.py`
    已移除对 retired helper 的导出依赖
  - `backend_old/tests/test_prompt_skills_module.py`
    已删除；该文件只验证 dead helper 内部实现，不再代表 live contract
  - `backend_old/tests/agent/test_prompt_skills_injection.py`
    已改为局部 fixture，不再 import retired helper
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `212`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k prompt_skills tests/test_config_internal_callers_use_service_layer.py -k prompt_skills`
    => `2 passed`
  - `cd backend_old && uv run --project . pytest -s tests/agent/test_prompt_skills_injection.py -k 'not verification' tests/test_api_router_rust_owned_routes_removed.py tests/test_config_internal_callers_use_service_layer.py`
    => `63 passed, 2 deselected, 4 warnings`
  - warning 备注：
    `app/services/agent/knowledge/vulnerabilities/open_redirect.py:12`
    存在未触及的既有 `DeprecationWarning: invalid escape sequence '\/'`
- 当前意义：
  - 这是 dead helper retirement，不是新的 Rust runtime takeover
  - Python agents 仍消费 `config.prompt_skills`，但不再依赖
    `app.services.agent.skills.prompt_skills` 这个 helper 模块
  - 这一步进一步证明 prompt skill helper 在 Python live 路径中已不再是 owner
- 仍未完成：
  - `use_prompt_skills -> config.prompt_skills`
    的 live producer 还未定位并收口
  - prompt skill runtime 主链路仍未完全 Rust-owned
- 删除条件：
  - `prompt_skills.py`：已删除，本 slice 完成
- 下一刀：
  - 继续定位并收口
    `use_prompt_skills -> config.prompt_skills`
    的 live producer owner

### 2026-04-15 Batch 4 / Slice 16

- 已完成：
  - `backend_old/app/services/agent/skills/resource_catalog.py`
    已物理删除
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `211`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'prompt_skills or resource_catalog' tests/test_config_internal_callers_use_service_layer.py -k 'prompt_skills or resource_catalog'`
    => `4 passed, 52 deselected, 2 warnings`
- 当前意义：
  - 这是 dead helper retirement，不是新的 Rust route/runtime takeover
  - 这一步进一步证明 `agent/skills` 目录里只剩 live scan-core surface 和空 package 壳
- 仍未完成：
  - `use_prompt_skills -> config.prompt_skills`
    的 live producer 仍未定位并收口
  - `skill_test_runner.py` 是否仍属 retained live helper
    还需要单独核验
- 删除条件：
  - `resource_catalog.py`：已删除，本 slice 完成
- 下一刀：
  - 核验 `skill_test_runner.py` 是否仍有 live caller；
    若已退化成 dead shell/测试资产，可继续收口

### 2026-04-15 Batch 4 / Slice 17

- 已完成：
  - `backend_old/app/services/agent/skill_test_runner.py`
    已物理删除
  - 只覆盖该 dead helper 的测试已删除：
    - `backend_old/tests/test_skill_test_project_lifecycle.py`
    - `backend_old/tests/test_structured_tool_test_runner.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `210`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'prompt_skills or resource_catalog or skill_test_runner' tests/test_config_internal_callers_use_service_layer.py -k 'prompt_skills or resource_catalog or skill_test_runner'`
    => `6 passed, 51 deselected, 3 warnings`
- 当前意义：
  - 这是 dead helper / dead test retirement，不是新的 Rust runtime takeover
  - 这一步说明 `skill_test_runner.py` 在 repo 内已经没有 live caller，
    当前只剩 dead tests 在消费它
  - Rust `/api/v1/skills/{id}/test` 与 `/tool-test`
    当前仍只是 compat stub；本 slice 不把它们记成等价替代
- 仍未完成：
  - skill test runtime 是否要补成真正 Rust-owned 能力仍待后续单独评估
  - `use_prompt_skills -> config.prompt_skills`
    的 live producer 仍未定位并收口
- 删除条件：
  - `skill_test_runner.py`：已删除，本 slice 完成
- 下一刀：
  - 继续定位 live Python runtime 中实际仍有 caller 的 retained helper；
    若无，则转入 `config.prompt_skills` producer owner 定位

### 2026-04-15 Batch 4 / Slice 18

- 已完成：
  - `backend_old/app/services/agent/workflow/__init__.py`
    已物理删除
  - 两个原本依赖 package convenience import 的测试
    已改为直引具体模块：
    - `backend_old/tests/test_parallel_workflow.py`
    - `backend_old/tests/test_workflow_engine.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - 为保证 workflow 测试自给性：
    - `test_parallel_workflow.py`
      已改为运行时写入临时 fixture，不再依赖已退役的 repo 内测试项目文件
    - `recon` stub 已改为返回真实 `risk_points` 形状
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `209`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_parallel_workflow.py tests/test_workflow_engine.py`
    => `36 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k workflow tests/test_config_internal_callers_use_service_layer.py -k workflow`
    => `2 passed, 57 deselected, 1 warning`
- 当前意义：
  - 这是 dead package convenience module retirement，不是新的 Rust workflow takeover
  - workflow live 模块仍保留：
    - `engine.py`
    - `models.py`
    - `workflow_orchestrator.py`
    - `parallel_executor.py`
    - `memory_monitor.py`
  - 这一步只证明 package init 壳已不再是 live owner
- 仍未完成：
  - workflow / orchestrator / parallel executor 本体仍属于 retained Python runtime
  - `config.prompt_skills` producer owner 仍未明确
- 删除条件：
  - `workflow/__init__.py`：已删除，本 slice 完成
- 下一刀：
  - 继续审计 retained Python runtime 中是否还存在
    “仅被 tests / package export 消费”的 dead shell
  - 若没有，再转回更难的 runtime producer owner 定位

### 2026-04-15 Batch 4 / Slice 19

- 已完成：
  - `backend_old/app/services/agent/telemetry/tracer.py`
    已物理删除
  - `backend_old/app/services/agent/telemetry/__init__.py`
    已物理删除
  - `backend_old/app/services/agent/__init__.py`
    已移除 retired telemetry lazy exports：
    - `Tracer`
    - `get_global_tracer`
    - `set_global_tracer`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `207`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k telemetry tests/test_config_internal_callers_use_service_layer.py -k telemetry`
    => `3 passed, 59 deselected, 1 warning`
- 当前意义：
  - 这是 dead telemetry shell retirement，不是新的 Rust runtime takeover
  - 这一步只证明 repo 内没有 live Python importer 消费 telemetry package / tracer symbols
  - `orchestrator` / `finish_tool` / `workflow_orchestrator`
    仍保留对 `tracer` 对象的可选参数位，但不再依赖 telemetry 模块定义
- 仍未完成：
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- 删除条件：
  - telemetry shell：已删除，本 slice 完成
- 下一刀：
  - 继续审计空 package 壳与 retained helper
  - 若 dead shell 收口告一段落，再转回 runtime producer owner 定位

### 2026-04-15 Batch 4 / Slice 20

- 已完成：
  - `backend_old/app/services/agent/skills/__init__.py`
    已物理删除
  - 已验证删除后 direct submodule import 仍正常：
    - `from app.services.agent.skills.scan_core import SCAN_CORE_LOCAL_SKILL_IDS`
      仍可导入，输出 `17`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `206`
- 验证命令：
  - `cd backend_old && uv run --project . python -c "from app.services.agent.skills.scan_core import SCAN_CORE_LOCAL_SKILL_IDS; print(len(SCAN_CORE_LOCAL_SKILL_IDS))"`
    => `17`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'skills' tests/test_config_internal_callers_use_service_layer.py -k 'skills'`
    => `4 passed, 60 deselected, 2 warnings`
- 当前意义：
  - 这是空 package shell retirement，不是新的 Rust scan-core takeover
  - 这一步说明 `agent/skills` 下的空 package 壳已不再是 live owner；
    live surface 已收口到 `scan_core.py`
- 仍未完成：
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- 删除条件：
  - `skills/__init__.py`：已删除，本 slice 完成
- 下一刀：
  - dead shell 收口已接近告一段落；
    下一步应回到 retained live helper / runtime producer owner 审计

### 2026-04-15 Batch 4 / Slice 21

- 已完成：
  - `backend_old/app/services/agent/__init__.py`
    已物理删除
  - 原先依赖 package convenience import 的测试
    已改为直引具体子模块：
    - `backend_old/tests/test_agent_tasks_module_layout.py`
    - `backend_old/tests/test_static_scan_runtime.py`
    - `backend_old/tests/test_agent_event_payload_limits.py`
    - `backend_old/tests/test_background_task_launch_refactor.py`
    - `backend_old/tests/test_scanner_runner.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `205`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_agent_tasks_module_layout.py tests/test_static_scan_runtime.py tests/test_agent_event_payload_limits.py tests/test_background_task_launch_refactor.py tests/test_scanner_runner.py`
    => `23 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py tests/test_config_internal_callers_use_service_layer.py -k 'agent and package'`
    => `7 passed, 59 deselected, 3 warnings`
- 当前意义：
  - 这是 convenience package shell retirement，不是新的 Rust agent runtime takeover
  - 这一步说明 repo 内测试已不再依赖 `app.services.agent`
    这层 lazy-export 壳，活测试均改为直引 retained helper/module
  - dead shell 清理线到这里已经基本收口，后续再继续删文件的收益明显下降
- 仍未完成：
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
  - retained live helper 审计仍未完成
- 删除条件：
  - `agent/__init__.py`：已删除，本 slice 完成
- 下一刀：
  - 从 dead shell 清理转回 retained live helper / runtime producer owner 审计

### 2026-04-15 Batch 4 / Slice 22

- 已完成：
  - 以下 7 个 zero-caller Python subpackage shell 已物理删除：
    - `backend_old/app/services/agent/core/__init__.py`
    - `backend_old/app/services/agent/knowledge/frameworks/__init__.py`
    - `backend_old/app/services/agent/knowledge/vulnerabilities/__init__.py`
    - `backend_old/app/services/agent/memory/__init__.py`
    - `backend_old/app/services/agent/prompts/__init__.py`
    - `backend_old/app/services/agent/streaming/__init__.py`
    - `backend_old/app/services/agent/tool_runtime/__init__.py`
  - retirement guard 已补到：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
  - 这一步明确保留：
    - `backend_old/app/services/agent/bootstrap/__init__.py`
    - `backend_old/app/services/agent/tools/runtime/__init__.py`
    因为它们仍有 repo 内 caller
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `197`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'core or frameworks or vulnerabilities or memory or prompts or streaming or tool_runtime' tests/test_config_internal_callers_use_service_layer.py -k 'core or frameworks or vulnerabilities or memory or prompts or streaming or tool_runtime'`
    => `15 passed, 68 deselected, 7 warnings`
- 当前意义：
  - 这是 zero-caller subpackage shell cleanup，不是新的 Rust runtime takeover
  - 这一步把 `services/agent` 下多层 package shell 基本压扁到 retained live surface
  - dead shell 清理到这里已接近收益递减点
- 仍未完成：
  - retained Python runtime 本体仍在
  - `bootstrap` / `tools.runtime` package shell 仍有 repo 内 caller
  - `config.prompt_skills` producer owner 仍未明确
- 删除条件：
  - 上述 7 个 package shell：已删除，本 slice 完成
- 下一刀：
  - 从 dead shell 清理切回 retained live helper / runtime producer owner 审计

### 2026-04-15 Batch 4 / Slice 23

- 已完成：
  - `backend_old/app/services/agent/knowledge/__init__.py`
    已物理删除
  - 两个 retained live caller 已改为直引具体模块：
    - `backend_old/app/services/agent/agents/base.py`
    - `backend_old/app/services/agent/tools/agent_tools.py`
    - 二者都从 `..knowledge.loader` 直接导入 `knowledge_loader`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `196`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k knowledge tests/test_config_internal_callers_use_service_layer.py -k knowledge`
    => `3 passed, 66 deselected, 1 warning`
- 当前意义：
  - 这是 retained convenience module retirement，不是新的 Rust knowledge/runtime takeover
  - 这一步把 live internal caller 从 package shell 收口到具体 loader 模块，进一步压平 retained Python 依赖层级
- 仍未完成：
  - `knowledge.loader` / `knowledge.tools` / `rag_knowledge` 本体仍在
  - retained Python runtime 主链仍未退出
- 删除条件：
  - `knowledge/__init__.py`：已删除，本 slice 完成
- 下一刀：
  - 继续收口仅剩测试 caller 的 package shell，优先 `bootstrap/__init__.py`

### 2026-04-15 Batch 4 / Slice 24

- 已完成：
  - `backend_old/app/services/agent/bootstrap/__init__.py`
    已物理删除
  - 3 个仅剩测试 caller 已改成直引具体子模块：
    - `backend_old/tests/test_bandit_bootstrap_scanner.py`
    - `backend_old/tests/test_opengrep_bootstrap_scanner.py`
    - `backend_old/tests/test_phpstan_bootstrap_scanner.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `193`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_bandit_bootstrap_scanner.py tests/test_opengrep_bootstrap_scanner.py tests/test_phpstan_bootstrap_scanner.py`
    => `17 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k bootstrap tests/test_config_internal_callers_use_service_layer.py -k bootstrap`
    => `4 passed, 87 deselected, 1 warning`
- 当前意义：
  - 这是 retained package shell retirement，不是新的 Rust bootstrap takeover
  - 当前保留的是 bootstrap 子模块本体，而不是 package shell
- 仍未完成：
  - `tools/runtime/__init__.py` 仍不能直接删，因为 `tools/base.py`
    仍有 live caller
  - retained Python runtime 本体仍在
- 删除条件：
  - `bootstrap/__init__.py`：已删除，本 slice 完成
- 下一刀：
  - 迁走 `tools/base.py` 对 `tools.runtime` package shell 的 live caller，
    然后退休 `tools/runtime/__init__.py`

### 2026-04-15 Batch 4 / Slice 25

- 已完成：
  - `backend_old/app/services/agent/tools/runtime/__init__.py`
    已物理删除
  - live caller 已改为直引具体模块：
    - `backend_old/app/services/agent/tools/base.py`
      现已直接从 `.runtime.coordinator`
      导入 `ToolExecutionCoordinator`
    - `backend_old/tests/test_tool_runtime_coordinator.py`
      已改为直引 `app.services.agent.tools.runtime.coordinator`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
    - 已额外覆盖相对 `from .runtime import ...` 这种 live caller 形式
  - `prompts` package shell retirement 引发的导入链断裂已同步修正：
    - `analysis.py`
    - `verification.py`
    - `orchestrator.py`
    都已改为直引 `prompts/system_prompts.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `192`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_tool_runtime_coordinator.py`
    => `5 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tool_runtime tests/test_config_internal_callers_use_service_layer.py -k tool_runtime`
    => `3 passed, 91 deselected, 1 warning`
- 当前意义：
  - 这是 retained package shell retirement，不是新的 Rust tool runtime takeover
  - 这一步把 `tools.runtime` 的唯一 live internal caller
    从 package shell 收口到具体 coordinator 模块
  - 至此 dead shell / convenience package 清理线基本只剩少量仍有 retained caller 的壳层
- 仍未完成：
  - `tools/__init__.py` 仍有少量 caller
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- 删除条件：
  - `tools/runtime/__init__.py`：已删除，本 slice 完成
- 下一刀：
  - 若继续沿 dead shell 线推进，优先评估 `tools/__init__.py`
    是否值得做最后一轮 convenience export 收口
  - 否则应转回 retained live helper / runtime producer owner 审计

### 2026-04-15 Batch 4 / Slice 26

- 已完成：
  - `backend_old/app/services/agent/tools/__init__.py`
    已物理删除
  - direct package caller 已改为直引具体子模块或 symbol：
    - `backend_old/app/services/agent/bootstrap_entrypoints.py`
    - `backend_old/tests/agent/test_agents.py`
    - `backend_old/tests/agent/test_file_tool_evidence_protocol.py`
    - `backend_old/tests/agent/test_tools.py`
    - `backend_old/tests/test_pmd_rules_service.py`
    - `backend_old/tests/test_pmd_runner_tool.py`
    - `backend_old/tests/test_refactored_business_logic_scan.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `191`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_tool_runtime_coordinator.py`
    => `5 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tool_runtime tests/test_config_internal_callers_use_service_layer.py -k tool_runtime`
    => `3 passed, 91 deselected, 1 warning`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tools tests/test_config_internal_callers_use_service_layer.py -k tools`
    => `5 passed`
  - 说明：
    - caller 改造关联的更大一组测试中，
      `tests/test_refactored_business_logic_scan.py`
      仍有既有环境依赖（要求 `.env` 存在），本 slice 不处理
- 当前意义：
  - 这是 retained convenience package retirement，不是新的 Rust tool/runtime takeover
  - 这一步把 `tools` package root 从 retained caller 链里拿掉，
    只留下具体 tool 模块本体
  - 至此 dead shell / convenience package 清理线基本收口
- 仍未完成：
  - retained Python runtime 模块本体仍在
  - `config.prompt_skills` producer owner 仍未明确
  - 后续推进应更多转向 retained live helper / runtime producer owner，而不是继续优先删壳
- 删除条件：
  - `tools/__init__.py`：已删除，本 slice 完成
- 下一刀：
  - 从 convenience shell 清理切回 retained live helper / runtime producer owner 审计

### 2026-04-15 Batch 4 / Slice 27

- 已完成：
  - `backend_old/app/services/agent/workflow/engine.py`
    已物理删除
  - `backend_old/app/services/agent/workflow/models.py`
    已物理删除
  - `backend_old/app/services/agent/workflow/parallel_executor.py`
    已物理删除
  - `backend_old/app/services/agent/workflow/memory_monitor.py`
    已物理删除
  - `backend_old/app/services/agent/workflow/workflow_orchestrator.py`
    已物理删除
  - 只覆盖该 retained test-only cluster 的测试已删除：
    - `backend_old/tests/test_parallel_workflow.py`
    - `backend_old/tests/test_workflow_engine.py`
    - `backend_old/tests/test_parallel_executor.py`
    - `backend_old/tests/test_agent_memory_isolation.py`
    - `backend_old/tests/test_business_logic_pipeline.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `186`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k workflow tests/test_config_internal_callers_use_service_layer.py -k workflow`
    => `8 passed, 94 deselected`
- 当前意义：
  - 这是 retained test-only workflow cluster retirement，不是新的 Rust workflow takeover
  - 这一步说明 repo 内 app/scripts 已不再依赖该 workflow cluster
- 仍未完成：
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- 删除条件：
  - 上述 workflow cluster：已删除，本 slice 完成
- 下一刀：
  - 继续收口 retained convenience package / test-only pair
    或转向 retained live helper 审计

### 2026-04-15 Batch 4 / Slice 28

- 已完成：
  - `backend_old/app/services/agent/tools/__init__.py`
    已物理删除
  - direct package caller 已改为直引具体子模块或 symbol：
    - `backend_old/app/services/agent/bootstrap_entrypoints.py`
    - `backend_old/tests/agent/test_agents.py`
    - `backend_old/tests/agent/test_file_tool_evidence_protocol.py`
    - `backend_old/tests/agent/test_tools.py`
    - `backend_old/tests/test_pmd_rules_service.py`
    - `backend_old/tests/test_pmd_runner_tool.py`
    - `backend_old/tests/test_refactored_business_logic_scan.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `191`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_tool_runtime_coordinator.py`
    => `5 passed`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tool_runtime tests/test_config_internal_callers_use_service_layer.py -k tool_runtime`
    => `3 passed, 91 deselected, 1 warning`
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k tools tests/test_config_internal_callers_use_service_layer.py -k tools`
    => `5 passed`
  - 说明：
    - 关联的大测试组中 `tests/test_refactored_business_logic_scan.py`
      仍有 `.env` 环境依赖，本 slice 不处理
- 当前意义：
  - 这是 retained convenience package retirement，不是新的 Rust tool/runtime takeover
  - 这一步把 `tools` package root 从 retained caller 链里移除，只保留具体 tool 模块
- 仍未完成：
  - retained Python runtime 模块本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- 删除条件：
  - `tools/__init__.py`：已删除，本 slice 完成
- 下一刀：
  - 若继续沿 retained runtime 线推进，可切 test-only pair / retained helper cluster

### 2026-04-15 Batch 4 / Slice 29

- 已完成：
  - `backend_old/app/services/agent/tools/business_logic_scan_tool.py`
    已物理删除
  - `backend_old/app/services/agent/agents/business_logic_scan.py`
    已物理删除
  - `backend_old/app/services/agent/agents/__init__.py`
    已移除 `BusinessLogicScanAgent` re-export
  - 只覆盖这对 retained pair 的测试已删除：
    - `backend_old/tests/test_refactored_business_logic_scan.py`
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `184`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'business_logic_scan' tests/test_config_internal_callers_use_service_layer.py -k 'business_logic_scan'`
    => `4 passed, 102 deselected, 2 warnings`
- 当前意义：
  - 这是 retained test-only pair retirement，不是新的 Rust business-logic-scan takeover
  - 这一步说明该 pair 在 repo 内已经退化成测试资产 + package re-export，不再是 live owner
- 仍未完成：
  - retained Python runtime 本体仍在
  - `config.prompt_skills` producer owner 仍未明确
- 删除条件：
  - `business_logic_scan` pair：已删除，本 slice 完成
- 下一刀：
  - 从 dead shell / test-only pair 清理进一步转回 retained live helper 审计

### 2026-04-15 Batch 4 / Slice 30

- 已完成：
  - `backend_old/app/services/agent/knowledge/tools.py`
    已物理删除
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `180`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'knowledge and tools' tests/test_config_internal_callers_use_service_layer.py -k 'knowledge and tools'`
    => `2 passed, 112 deselected, 1 warning`
- 当前意义：
  - 这是 orphan module retirement，不是新的 Rust knowledge takeover
  - 这一步说明 `knowledge/tools.py` 在 repo 内已无 direct live caller；
    base.py 中仅剩 tool-name fallback 字符串，不构成模块依赖
- 仍未完成：
  - `knowledge.loader` / `rag_knowledge` / `base` 仍在 retained Python runtime
  - retained Python runtime 本体仍在
- 删除条件：
  - `knowledge/tools.py`：已删除，本 slice 完成
- 下一刀：
  - 继续审计 orphan / test-only retained模块；
    若收益下降，则切回 retained live helper / runtime producer owner

### 2026-04-15 Batch 4 / Slice 31

- 已完成：
  - `backend_old/app/services/agent/tool_runtime/probe_specs.py`
    已物理删除
  - `backend_old/app/services/agent/tool_runtime/protocol_verify.py`
    已物理删除
  - `backend_old/app/services/agent/tool_runtime/virtual_tools.py`
    已物理删除
  - retirement guard 已补：
    - `backend_old/tests/test_api_router_rust_owned_routes_removed.py`
    - `backend_old/tests/test_config_internal_callers_use_service_layer.py`
- repo facts refresh：
  - `find backend_old -maxdepth 1 -type f -name '*.py' | wc -l` => `0`
  - `find backend_old/app -type f -name '*.py' ! -path 'backend_old/app/api/*' | wc -l` => `180`
- 验证命令：
  - `cd backend_old && uv run --project . pytest -s tests/test_api_router_rust_owned_routes_removed.py -k 'probe_specs or protocol_verify or virtual_tools' tests/test_config_internal_callers_use_service_layer.py -k 'probe_specs or protocol_verify or virtual_tools'`
    => `6 passed, 108 deselected, 3 warnings`
- 当前意义：
  - 这是 orphan cluster retirement，不是新的 Rust tool runtime takeover
  - 这一步说明这 3 个 `tool_runtime` 边缘模块在 repo 内已无 direct live caller
- 仍未完成：
  - `tool_runtime/runtime.py` / `router.py` / `health_probe.py` / `write_scope.py`
    仍在 retained Python runtime 中
  - retained Python runtime 本体仍在
- 删除条件：
  - 上述 orphan cluster：已删除，本 slice 完成
- 下一刀：
  - 继续盘点 remaining retained模块的 direct caller，
    优先挑 test-only pair / orphan cluster
