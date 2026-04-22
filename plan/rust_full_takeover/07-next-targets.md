# Next Targets

## 文档定位

- 类型：How-to
- 目标读者：需要直接接手下一轮功能接管的开发者

## 当前优先级

### Phase A 尾巴子进度

- `backend_old/app/core/security.py`、`backend_old/app/core/encryption.py`、`backend_old/app/core/config.py` 已全部退役；`backend_old/app/core` 现已清零。
- `backend_old/app/db/schema_snapshots/baseline_5b0f3c9a6d7e.py` 与 `backend_old/alembic/*` 已整体退役；Phase A 尾巴完成。
- flow/lightweight 与 sandbox/base/preflight importer 已切到 `app.services.agent.runtime_settings`，核心配置读取不再依赖 `app.core`。

### Scanner / Queue 主链收口（已完成）

- `backend_old/app/services/agent/scope_filters.py` 已退役。
- Rust `backend/src/scan/scope_filters.rs` + `backend-runtime-startup scan-scope` 现在承担 legacy ignored-scope path / bootstrap finding filter 语义。
- `backend_old/app/services/agent/task_findings.py` 已切到 Rust bridge。
- 本收口不等于 SmartScanTool 或全局 scope filtering 已全部统一 Rust；其并行 exclude 逻辑仍留在后续 slice。

### 1. Agent Orchestration / State / Payload 主链

目标范围：

- `backend_old/app/services/agent/agents/*`
- `backend_old/app/services/agent/core/{context,errors,executor,logging,message,registry,state}.py`
- `backend_old/app/services/agent/event_manager.py`
- `backend_old/app/services/agent/config.py`
- `backend_old/app/services/agent/json_parser.py`
- `backend_old/app/services/agent/json_safe.py`
- `backend_old/app/services/agent/push_finding_payload.py`
- `backend_old/app/services/agent/task_findings.py`
- `backend_old/app/services/agent/write_scope.py`

完成标准：

- agent 执行、状态、消息和 finding payload 主链由 Rust 承担
- Python orchestrator 退到 0 或降级为非运行时资产

### 2. Flow / Logic 主链

目标范围：

- `backend_old/app/services/agent/core/flow/*`
- `backend_old/app/services/agent/logic/*`

完成标准：

- flow parser、callgraph、definition lookup、authz logic 由 Rust 承担
- Python flow runner / lightweight analysis 不再处于主链

### 3. Tool Runtime + Support Glue

目标范围：

- `backend_old/app/services/agent/tools/*`
- `backend_old/app/services/agent/tools/runtime/*`
- `backend_old/app/services/agent/memory/markdown_memory.py`
- `backend_old/app/services/agent/prompts/system_prompts.py`
- `backend_old/app/services/agent/skills/scan_core.py`
- `backend_old/app/services/agent/streaming/*`
- `backend_old/app/services/agent/utils/vulnerability_naming.py`

完成标准：

- Rust 拿到工具执行主链、streaming glue、prompt / memory 宿主
- Python 只剩 archive / tooling，不再承载 live tool runtime

### 4. Knowledge + LLM + Rule Runtime

目标范围：

- `backend_old/app/services/agent/knowledge/*`
- `backend_old/app/services/llm/*`
- `backend/src/llm_rule/*`

完成标准：

- Rust 成为 knowledge、provider、prompt cache、rule repo / validator 的主运行时

当前子进度：

- provider/config registry 语义已迁到 Rust `backend/src/llm/{providers,config}.rs`；`backend_old/app/services/llm/{config_utils,provider_registry}.py` 已退役。
- request/response shell、prompt-cache policy、service/adapters cluster 的 Rust 宿主已迁到 `backend/src/llm/{types,prompt_cache,runtime}.rs`；`backend_old/app/services/llm/{service,factory,types,base_adapter,prompt_cache,adapters/*}.py` 已退役。
- tokenizer / memory compression 语义已迁到 Rust `backend/src/llm/{tokenizer,compression}.rs`；`backend_old/app/services/llm/{tokenizer,memory_compressor}.py` 已退役。
- `agent/base.py` 已切走对 Python llm tokenizer/compression 模块的依赖，`backend_old/app/services/llm/*` 现已清零。
- generic opengrep rule YAML normalize / validate 已迁到 Rust `backend/src/llm_rule/*` 与 `static_tasks` route。
- HTTPS-only / git mirror candidate 与 patch filename / diff language parsing 已迁到 Rust `backend/src/llm_rule/{git,patch}.rs`。
- `backend_old/app/services/llm_rule/*` 与 `backend_old/app/services/rule.py` 已退役，剩余工作改为 Rust 侧 repo cache -> rule validator / manager -> generation flow 填补。

### Shared Helpers 子进度

- scan path normalization / archive-member resolution 已迁到 Rust `backend/src/scan/path_utils.rs`；`backend_old/app/services/scan_path_utils.py` 已退役。
- sandbox spec/result shell 已迁到 Rust `backend/src/runtime/sandbox.rs`；`backend_old/app/services/sandbox_runner.py` 已退役。
- `backend_old/app/services` 根目录现已清零，不再有 retained shared helper Python 文件。

### 5. Models / Ops Tail Final Gate

目标范围：

- `backend_old/app/models/*`
- `backend_old/scripts/flow_parser_runner.py`
- `scripts/release-templates/runner_preflight.py`

完成标准：

- legacy mirror / preflight 不再阻止 Python 退役
- runtime tail 有明确删除或降级结论

当前子进度：

- `backend_old/app/models/{prompt_skill,user_config,prompt_template,audit_rule}.py` 已确认无 live Python importer，并已完成退役。
- prompt skill CRUD / backfill / mirror 与 builtin prompt template surface 继续由 Rust `backend/src/{db/prompt_skills.rs,routes/skills.rs}` 承担；`user_config` 仅保留 legacy table compat，不再保留 Python ORM shell。
- `backend_old/app/models/{project_info,project_management_metrics}.py` 已确认无 live Python importer，并已完成退役；`backend_old/app/models/project.py` 已切掉对这两个 optional shell 的 relationship 依赖。
- `backend_old/app/models/analysis.py` 已确认无 live ORM caller，并已完成退役；verification dataflow 常量已迁到 `app.services.agent.verification_dataflow`。
- `backend_old/app/models/{user,project,opengrep}.py` 已完成测试侧兼容下沉并退役；运行时不再直接依赖这些 shell。
- `backend_old/app/models/base.py` 已退役；声明式 ORM base 已迁到 `app.services.agent.orm_base`。
- `backend_old/app/models/agent_task.py` 已迁到 `app.services.agent.task_models`；`backend_old/app/models` 现已清零，接下来转入 agent orchestration/state/tool 主链。

## 当前执行原则

1. 优先接管仍在主链上的 runtime cluster，不回头做低收益的历史壳层清理。
2. 每完成一个功能 slice，就补 guard、跑验证、更新文档并提交一次 commit。
3. 如果某块只能做到 Rust 外壳而不能切换 source of truth，就不要把它记成“已接管”。

## 最近完成

- `backend_old/alembic/*` 与 `backend_old/app/db/schema_snapshots/baseline_5b0f3c9a6d7e.py` 已完成 Python 退役；Rust bootstrap/runtime 不再保留 legacy schema / Alembic 兼容路径。
- `backend_old/app/core/security.py` 与 `backend_old/app/core/encryption.py` 已完成 Python 退役；Rust `backend/src/core/{security,encryption}.rs` 继续承担唯一语义宿主，retirement guard 已补。
- `scanner_runner.py` 已完成 Rust 接管并退役。
- `recon_risk_queue.py` 与 `vulnerability_queue.py` 已完成 Rust 接管并退役。
- generic opengrep rule YAML 校验已完成 Rust 接管，Python `validate_generic_rule()` helper 已退役。
- llm_rule 的 git mirror policy 与 patch parser 已完成 Rust 接管，patch route shell 开始消费 Rust patch 元数据。
- `backend_old/app/services/rule.py` 与 `backend_old/app/services/llm_rule/*` 已完成 Python 退役，retirement guard 已补。
- `backend_old/app/services/llm/{config_utils,provider_registry}.py` 已完成 Python 退役；`system-config` route 现由 Rust LLM provider/config module 提供 catalog 与 normalize 语义。
- `backend_old/app/models/{prompt_skill,user_config,prompt_template,audit_rule}.py` 已完成 Python 退役；新增 retirement guard 防止 model shell 与 direct importer 回流。
- `backend_old/app/models/{project_info,project_management_metrics}.py` 已完成 Python 退役；新增 mapper/usability guard，确保 `Project` 在没有这两个 legacy shell 的情况下仍可配置和实例化。
- `backend_old/app/models/analysis.py` 已完成 Python 退役；新增 helper 常量模块承接 verification dataflow gate，schema perf index expectation 已同步移除 instant_analyses 遗留索引。
- `backend_old/app/models/{user,project,opengrep}.py` 已完成 Python 退役；测试侧关系模型已迁到 `tests.support.legacy_orm_models`，并补充兼容配置 guard。
- `backend_old/app/models/base.py` 已完成 Python 退役；新增 `app.services.agent.orm_base` 承接声明式 base，retirement guard 已覆盖 base shell。
- `backend_old/app/models/agent_task.py` 已完成 Python 退役；运行时 ORM 与常量已迁到 `app.services.agent.task_models`，测试/运行时 direct importer 已切换，`app/models` 目录清零。
