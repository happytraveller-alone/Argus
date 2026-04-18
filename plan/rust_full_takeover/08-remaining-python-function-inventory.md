# Remaining Python Function Inventory

## 文档定位

- 类型：Reference
- 目标读者：需要逐块接管 Python retained runtime 的开发者
- 阅读目标：清楚知道现在还有哪些 Python 功能没被 Rust 接管，以及建议从哪一块开始

## 统计口径

- `backend_old` 根目录 Python：`0`
- `backend_old/app/api` Python：`0`
- `backend_old/app` 非 API Python：`162`

`162` 是当前 runtime core 主计数。

它不包含下面这些仍会阻止“Python 全退役”的运行/运维尾巴：

- `backend_old/alembic`：`21`
- `backend_old/scripts`：`1`
- `scripts/release-templates/runner_preflight.py`：`1`

另外还有 `scripts/migration/*.py`：`2`，它们属于 inventory / diff tooling，
默认不算 runtime blocker，但需要与 canonical 文档保持一致。

## 分组总览

### `backend_old/app` runtime core（共 `162`）

| 功能组 | 当前文件数 | 当前状态 | 推荐 Rust 落点 |
| --- | ---: | --- | --- |
| `app root + core/*` | 4 | retained live core config/security | `backend/src/core/*` |
| `db/*` | 2 | retained DB gate / schema snapshot | `backend/src/db/*`, bootstrap/alembic replacement |
| `models/*` | 17 | retained domain/persistence mirror | `backend/src/domain/*`, `backend/src/db/*` |
| `services/shared/*` | 7 | mixed retained helper | `backend/src/*` 对应 shared service |
| `services/agent` orchestration / state | 24 | retained live runtime 主链 | `backend/src/agent/*`, `backend/src/runtime/*` |
| `services/agent` bootstrap / scan / queue | 17 | retained scanner/runtime 主链 | `backend/src/scan/*`, `backend/src/runtime/*` |
| `services/agent` flow / logic | 14 | retained analysis/runtime 主链 | `backend/src/flow/*`, `backend/src/graph/*` |
| `services/agent` knowledge | 21 | retained prompt/knowledge runtime | `backend/src/knowledge/*` |
| `services/agent` tools + tool_runtime | 27 | retained tool execution 主链 | `backend/src/tools/*`, `backend/src/runtime/*` |
| `services/agent` support assets | 7 | retained stream/prompt/memory glue | `backend/src/agent/*`, `backend/src/runtime/*` |
| `services/llm/*` | 14 | retained live runtime | `backend/src/llm/*` |
| `services/llm_rule/*` | 8 | retained live runtime | `backend/src/llm_rule/*` or rule-engine equivalent |

### repo-adjacent retirement tail（不计入 `167`）

| 功能组 | 当前文件数 | 当前状态 | 推荐 Rust 落点 |
| --- | ---: | --- | --- |
| `backend_old/alembic/*` | 21 | legacy schema / migration compatibility tail | Rust bootstrap + schema gate replacement |
| `backend_old/scripts/*` | 1 | runtime-adjacent helper scripts | `backend/src/flow/*`, Rust bootstrap helper or retire |
| `scripts/release-templates/runner_preflight.py` | 1 | release / ops preflight Python helper | Rust or shell-based release preflight |
| `scripts/migration/*.py` | 2 | inventory / diff tooling | 可保留为 tooling，但必须与 canonical 文档同步 |

## 详细功能块

### 1. App Root / Core / Config / Security

目标文件：

- `backend_old/app/__init__.py`
- `backend_old/app/core/__init__.py`
- `backend_old/app/core/config.py`
- `backend_old/app/core/encryption.py`
- `backend_old/app/core/security.py`

当前责任：

- Python retained runtime 的设置读取
- legacy 安全、加密、token 等兼容逻辑

目标状态：

- Rust 成为唯一配置、安全、加密 source of truth
- Python runtime 不再 import 这些 core 模块

已完成收口：

- `backend_old/app/core/__init__.py` 已于 2026-04-18 退役。

### 2. DB Gate / Schema Snapshot

目标文件：

- `backend_old/app/db/schema_snapshots/__init__.py`
- `backend_old/app/db/schema_snapshots/baseline_5b0f3c9a6d7e.py`

当前责任：

- legacy schema snapshot / alembic 兼容门

已完成收口：

- `backend_old/app/db/__init__.py` 已于 2026-04-18 退役。
- `services/bandit_rules_snapshot.py` 与 `services/pmd_rulesets.py` 直接读取 Rust-owned `backend/assets/scan_rule_assets/*`，不再通过 `app.db` package shell 桥接。

目标状态：

- Rust bootstrap / schema gate 完全替代
- `backend_old/app/db` 整体删除

### 3. Models / Persistence Mirror

目标文件：

- `backend_old/app/models/*`

主要内容：

- project / user / user_config / prompt_skill
- agent_task / finding / checkpoint 相关模型
- 各 scanner / rule 相关模型

目标状态：

- Rust domain / persistence 完全替代
- Python model 不再承担主读写职责

已完成收口：

- `backend_old/app/models/__init__.py` 已于 2026-04-18 退役。
- Alembic `env.py` 改为显式导入各 model module，不再通过 `app.models` package shell 触发表元数据注册。

### 4. Shared Service Retained Helpers

目标文件：

- `services/bandit_rules_snapshot.py`
- `services/git_mirror.py`
- `services/pmd_rulesets.py`
- `services/rule.py`
- `services/rule_contracts.py`
- `services/sandbox_runner.py`
- `services/scan_path_utils.py`

当前责任：

- 规则资产、git mirror、rule contract、sandbox helper、路径归一化

目标状态：

- 能迁的迁进 Rust shared service
- 只剩 schema / contract 归档，不再参与主运行链

### 5. Agent Orchestration / State / Payload

目标文件：

- `services/agent/agents/*`
- `services/agent/core/*`
- `services/agent/event_manager.py`
- `services/agent/config.py`
- `services/agent/json_parser.py`
- `services/agent/json_safe.py`
- `services/agent/push_finding_payload.py`
- `services/agent/task_findings.py`
- `services/agent/write_scope.py`

当前责任：

- agent 实际执行、消息、finding 归一化、上下文、状态、执行器

当前关键 open item：

- Rust 已在 agent-task creation 侧生成 `prompt_skill_runtime` snapshot；
- retained Python consumer 的 `config.prompt_skills` compat projection 已于 2026-04-18 对称退役（5 个 agent 注入块删除、测试删除、Rust WIP 投影字段撤销）。Rust mirror / backfill 保留以支撑 alembic legacy 表，归入后续 DB final gate slice。

目标状态：

- Rust 拿到 agent orchestration / prompt injection / task execution 主链

已完成收口：

- `backend_old/app/services/agent/agents/__init__.py` 已于 2026-04-18 退役。
- live caller 已统一从旧 `app.services.agent.flow` 路径切到 `app.services.agent.core.flow`。

### 6. Scanner / Queue / Workspace / Tracking / Bootstrap

目标文件：

- `services/agent/bootstrap/*`
- `services/agent/bootstrap_entrypoints.py`
- `services/agent/bootstrap_findings.py`
- `services/agent/bootstrap_gitleaks_runner.py`
- `services/agent/bootstrap_policy.py`
- `services/agent/bootstrap_seeds.py`
- `services/agent/bandit_bootstrap_rules.py`
- `services/agent/recon_risk_queue.py`
- `services/agent/business_logic_risk_queue.py`
- `services/agent/vulnerability_queue.py`
- `services/agent/scan_workspace.py`
- `services/agent/scan_tracking.py`
- `services/agent/scanner_runner.py`
- `services/agent/scope_filters.py`

当前责任：

- retained scanner bootstrap
- risk queue / vulnerability queue
- workspace / tracking / runner glue

目标状态：

- Rust scan/runtime cluster 完全接替

### 7. Flow / Logic Retained Runtime

目标文件：

- `services/agent/flow/flow_parser_runner.py`
- `services/agent/flow/models.py`
- `services/agent/flow/pipeline.py`
- `services/agent/flow/lightweight/*`
- `services/agent/logic/authz_graph_builder.py`
- `services/agent/logic/authz_rules.py`

当前责任：

- flow parser runner retained helper
- lightweight definition / AST / callgraph 分析
- logic authz graph / rule engine

目标状态：

- Rust flow / graph / authz analysis 替代

### 8. Knowledge Retained Runtime

目标文件：

- `services/agent/knowledge/base.py`
- `services/agent/knowledge/loader.py`
- `services/agent/knowledge/rag_knowledge.py`
- `services/agent/knowledge/frameworks/*.py`
- `services/agent/knowledge/vulnerabilities/*.py`

当前责任：

- knowledge documents
- loader / RAG
- vulnerability / framework knowledge sources

当前状态：

- `knowledge/tools.py` 已退休
- `knowledge` package root 已退休
- retained 内容已收口到 loader / rag / documents 本体

目标状态：

- Rust knowledge / prompt / doc surface 替代，或明确声明这些知识不再作为 runtime 代码存在

### 9. Tools / Tool Runtime

目标文件：

- `services/agent/tools/base.py`
- `services/agent/tools/agent_tools.py`
- `services/agent/tools/business_logic_recon_queue_tools.py`
- `services/agent/tools/code_analysis_tool.py`
- `services/agent/tools/control_flow_tool.py`
- `services/agent/tools/evidence_protocol.py`
- `services/agent/tools/external_tools.py`
- `services/agent/tools/file_tool.py`
- `services/agent/tools/finish_tool.py`
- `services/agent/tools/kunlun_tool.py`
- `services/agent/tools/logic_authz_tool.py`
- `services/agent/tools/pattern_tool.py`
- `services/agent/tools/queue_tools.py`
- `services/agent/tools/recon_file_tree_tool.py`
- `services/agent/tools/recon_queue_tools.py`
- `services/agent/tools/reporting_tool.py`
- `services/agent/tools/run_code.py`
- `services/agent/tools/runtime/context.py`
- `services/agent/tools/runtime/contracts.py`
- `services/agent/tools/runtime/coordinator.py`
- `services/agent/tools/runtime/hooks.py`
- `services/agent/tools/sandbox_language.py`
- `services/agent/tools/sandbox_runner_client.py`
- `services/agent/tools/sandbox_tool.py`
- `services/agent/tools/sandbox_vuln.py`
- `services/agent/tools/smart_scan_tool.py`
- `services/agent/tools/verification_result_tools.py`

当前状态：

- `tools` package root 已退休
- `tools/runtime` package shell 已退休
- `business_logic_scan_tool.py` 已退休
- `tool_runtime` retained core 整组 2026-04-18 退役
- `tool_runtime` orphan edge cluster 已退休：
  - `probe_specs.py`
  - `protocol_verify.py`
  - `virtual_tools.py`

目标状态：

- Rust tool runtime / tool implementations 完全替代 retained Python

### 10. Agent Support Assets

目标文件：

- `services/agent/memory/markdown_memory.py`
- `services/agent/prompts/system_prompts.py`
- `services/agent/skills/scan_core.py`
- `services/agent/streaming/stream_handler.py`
- `services/agent/streaming/token_streamer.py`
- `services/agent/streaming/tool_stream.py`
- `services/agent/utils/vulnerability_naming.py`

当前责任：

- markdown memory
- system prompt 宿主
- local skill / scan-core 元数据
- SSE / token / tool streaming glue
- vulnerability naming helper

目标状态：

- Rust 侧吸收这些 runtime glue，或在上游功能被 Rust 接管后整体删除

### 11. LLM Retained Runtime

目标文件：

- `services/llm/*`
- `services/llm/adapters/*`

当前责任：

- provider registry
- adapter selection
- prompt cache / tokenizer / memory compression
- actual LLM runtime behavior

已完成收口：

- `backend_old/app/services/llm/__init__.py` 已于 2026-04-18 退役。
- 剩余 caller 改为 direct-module imports（例如 `memory_compressor`、`tokenizer`）。

目标状态：

- Rust LLM stack 接管主链

### 12. LLM Rule Retained Runtime

目标文件：

- `services/llm_rule/*`

当前责任：

- rule repo cache
- patch processor
- rule validator / manager / client

目标状态：

- Rust rule pipeline 或明确废弃替代

### 13. Repo-Adjacent Operational Python Surfaces

目标文件：

- `backend_old/alembic/env.py`
- `backend_old/alembic/versions/*.py`
- `backend_old/scripts/flow_parser_runner.py`
- `scripts/release-templates/runner_preflight.py`

当前责任：

- legacy schema compatibility / revision chain
- flow parser script host
- release / ops preflight Python helper

已完成收口：

- `backend_old/scripts/package_source_selector.py` 已于 2026-04-18 退役。
- Rust `backend/src/runtime/bootstrap.rs` 现在原生执行 PyPI candidate probe / 排序。
- `backend_old/scripts/dev-entrypoint.sh` 与相关 Dockerfile 改为 shell 内按配置顺序去重选择，不再调用 Python selector。
- package source probing
- release / runner preflight

目标状态：

- 这些 Python 文件不再承担 live runtime / deploy 责任
- 如果保留，也必须被明确降级为 tooling，而不是被误算成仍依赖 Python backend

## 当前推荐推进顺序

1. `tool_runtime` retained core
2. `scanner / queue / workspace / bootstrap`
3. `agent orchestration / state / support`
4. `knowledge` + `flow` + `logic`
5. `llm` / `llm_rule`
6. `models` / `db` / `alembic` / scripts / release preflight 最终门

（`prompt_skill_runtime` compat projection / consumer cutover 已于 2026-04-18 对称退役。）

并行关注：

- `/users/*`、`/projects/*/members*` 的 frontend consumer debt
- `projects` ZIP-only contract 的显式确认与验证
