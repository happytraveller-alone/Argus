# Remaining Python Function Inventory

## 文档定位

- 类型：Reference
- 目标读者：需要按文件面继续拆 takeover slice 的开发者
- 阅读目标：快速知道现在还有哪些 Python 功能没被 Rust 接管，以及它们应落到哪一类 Rust 模块

## 统计口径

- `backend_old` 根目录 Python：`0`
- `backend_old/app/api` Python：`0`
- `backend_old/app` 非 API Python：`97`
- `backend_old/alembic`：`0`
- `backend_old/scripts`：`1`
- `scripts/release-templates/runner_preflight.py`：`1`

`97` 是当前 runtime core 主计数。

它不包含 `scripts/migration/*.py` 这类 inventory / diff tooling；
这类文件默认不算 runtime blocker，但需要与 canonical 文档保持一致。

## 分组总览

| 功能组 | 当前文件数 | 当前责任 | 推荐 Rust 落点 |
| --- | ---: | --- | --- |
| app root / core / config / security | 0 | Python core runtime 已退役 | `backend/src/config.rs`, `backend/src/core/*` |
| db / schema snapshot gate | 0 | Python db/schema snapshot 已退役 | `backend/src/db/*` |
| models / persistence mirror | 5 | retained domain / persistence mirror | `backend/src/domain/*`, `backend/src/db/*` |
| shared helpers | 0 | Python 已退役，剩余 fill-in 在 Rust runtime / tool caller | `backend/src/*` 对应 shared service |
| agent orchestration / state / payload | 22 | agent 执行、状态、消息、payload 归一化 | `backend/src/agent/*`, `backend/src/runtime/*` |
| scanner / queue / workspace / tracking | 1 | scope filtering | `backend/src/scan/*`, `backend/src/runtime/*` |
| flow / logic | 13 | flow parser、callgraph、AST / authz 分析 | `backend/src/flow/*`, `backend/src/graph/*` |
| knowledge | 21 | knowledge loader、framework / vuln knowledge | `backend/src/knowledge/*` |
| tools + tool runtime | 26 | retained tool execution 主链 | `backend/src/tools/*`, `backend/src/runtime/*` |
| support assets | 7 | memory、prompt、streaming、scan-core 元数据 | `backend/src/agent/*`, `backend/src/runtime/*` |
| llm | 0 | Python 已退役，剩余 fill-in 在 Rust `backend/src/llm/*` | `backend/src/llm/*` |
| llm_rule | 0 | Python 已退役，剩余 fill-in 在 Rust `backend/src/llm_rule/*` | `backend/src/llm_rule/*` |
| repo-adjacent ops tail | 2 | flow parser script host、release preflight | bootstrap / DB gate replacement or retire |

## 详细功能块

### 1. App Root / Core / Config / Security (`0`)

目标状态：

- Rust 已成为安全、加密与配置读取的 source of truth
- Python runtime 不再 import retired core 模块

当前状态：

- Rust `backend/src/core/security.rs` 已承担 password hashing / JWT 语义宿主。
- Rust `backend/src/core/encryption.rs` 已承担 sensitive-field encryption 语义宿主。
- `backend_old/app/core/security.py` 与 `backend_old/app/core/encryption.py` 已退役，并有 guard 防止 direct importer 回流。
- `backend_old/app/core/config.py` 已退役；flow/lightweight 与 sandbox/base/preflight Python caller 已切到 `app.services.agent.runtime_settings`。

文件：

```text
```

### 2. DB Gate / Schema Snapshot (`0`)

当前状态：

- `backend_old/app/db/schema_snapshots/baseline_5b0f3c9a6d7e.py` 已退役。
- 数据库前向兼容不再保留，Rust bootstrap 也已删除 legacy schema / Alembic 兼容路径。

剩余工作：

- DB 相关剩余项只在 Rust mirror / domain / query plan 收口中，不再是 `app/db` Python blocker。

### 3. Models / Persistence Mirror (`5`)

当前责任：

- retained domain / persistence mirror

目标状态：

- Rust domain / persistence 完全替代
- Python model 不再承担主读写职责

文件：

```text
backend_old/app/models/agent_task.py
backend_old/app/models/base.py
backend_old/app/models/opengrep.py
backend_old/app/models/project.py
backend_old/app/models/user.py
```

已完成收口：

- `backend_old/app/models/{prompt_skill,user_config,prompt_template,audit_rule}.py` 已退役。
- prompt skill CRUD / backfill / mirror 与 builtin prompt template surface 已由 Rust `backend/src/{db/prompt_skills.rs,routes/skills.rs}` 承担。
- `user_config` 仍保留 legacy table compat，但该兼容不再需要 Python ORM shell。
- `backend_old/app/models/{project_info,project_management_metrics}.py` 已退役。
- Rust `backend/src/routes/projects.rs` 与 `backend/src/bootstrap/legacy_mirror_schema.rs` 已承担其 DB/route surface；Python `Project` model 已切掉对这两个 optional shell 的 relationship 依赖。
- `backend_old/app/models/analysis.py` 已退役。
- verification dataflow gate 常量已迁到 `backend_old/app/services/agent/verification_dataflow.py`；`instant_analyses` 遗留 Python ORM shell 不再保留。

### 4. Shared Service Retained Helpers (`0`)

当前状态：

- `backend_old/app/services/scan_path_utils.py` 已退役。
- Rust `backend/src/scan/path_utils.rs` 已接管 scan finding location、zip member candidate、archive path normalize 语义宿主。
- `backend_old/app/services/sandbox_runner.py` 已退役。
- Rust `backend/src/runtime/sandbox.rs` 已接管 sandbox spec/result shell 宿主。

剩余工作：

- shared helper 相关剩余工作不再是 Python runtime blocker，而是 Rust caller / parity backlog。

### 5. Agent Orchestration / State / Payload (`22`)

当前责任：

- agent 实际执行
- 状态、消息和上下文管理
- finding / payload 归一化

目标状态：

- Rust 拿到 agent orchestration / prompt injection / task execution 主链

文件：

```text
backend_old/app/services/agent/agents/analysis.py
backend_old/app/services/agent/agents/base.py
backend_old/app/services/agent/agents/orchestrator.py
backend_old/app/services/agent/agents/react_parser.py
backend_old/app/services/agent/agents/recon.py
backend_old/app/services/agent/agents/report.py
backend_old/app/services/agent/agents/verification.py
backend_old/app/services/agent/agents/verification_table.py
backend_old/app/services/agent/config.py
backend_old/app/services/agent/core/context.py
backend_old/app/services/agent/core/errors.py
backend_old/app/services/agent/core/executor.py
backend_old/app/services/agent/core/logging.py
backend_old/app/services/agent/core/message.py
backend_old/app/services/agent/core/registry.py
backend_old/app/services/agent/core/state.py
backend_old/app/services/agent/event_manager.py
backend_old/app/services/agent/json_parser.py
backend_old/app/services/agent/json_safe.py
backend_old/app/services/agent/push_finding_payload.py
backend_old/app/services/agent/task_findings.py
backend_old/app/services/agent/write_scope.py
```

### 6. Scanner / Queue / Workspace / Tracking (`1`)

当前责任：

- scope filtering glue

目标状态：

- Rust scan/runtime cluster 完全接替

文件：

```text
backend_old/app/services/agent/scope_filters.py
```

已完成收口：

- `backend_old/app/services/agent/scanner_runner.py` 已退役。
- Rust `backend-runtime-startup runner execute|stop` 已接管 scanner runner contract。
- Rust `backend/src/runtime/queue.rs` 已接管 recon / vulnerability queue fingerprint 与 queue snapshot 语义。
- `backend_old/app/services/agent/recon_risk_queue.py` 与 `backend_old/app/services/agent/vulnerability_queue.py` 已退役。
- `backend_old/app/services/agent/core/flow/flow_parser_runner.py` 不再 import `app.services.agent.scanner_runner`。

### 7. Flow / Logic Retained Runtime (`13`)

当前责任：

- flow parser runner
- lightweight definition / AST / callgraph 分析
- authz graph / rule engine

目标状态：

- Rust flow / graph / authz analysis 替代

文件：

```text
backend_old/app/services/agent/core/flow/flow_parser_runner.py
backend_old/app/services/agent/core/flow/lightweight/ast_index.py
backend_old/app/services/agent/core/flow/lightweight/callgraph_code2flow.py
backend_old/app/services/agent/core/flow/lightweight/definition_provider.py
backend_old/app/services/agent/core/flow/lightweight/function_locator.py
backend_old/app/services/agent/core/flow/lightweight/function_locator_cli.py
backend_old/app/services/agent/core/flow/lightweight/function_locator_payload.py
backend_old/app/services/agent/core/flow/lightweight/path_scorer.py
backend_old/app/services/agent/core/flow/lightweight/tree_sitter_parser.py
backend_old/app/services/agent/core/flow/models.py
backend_old/app/services/agent/core/flow/pipeline.py
backend_old/app/services/agent/logic/authz_graph_builder.py
backend_old/app/services/agent/logic/authz_rules.py
```

### 8. Knowledge Retained Runtime (`21`)

当前责任：

- knowledge documents
- loader / RAG
- vulnerability / framework knowledge sources

目标状态：

- Rust knowledge / prompt / doc surface 替代，或明确声明这些知识不再作为 runtime 代码存在

文件：

```text
backend_old/app/services/agent/knowledge/base.py
backend_old/app/services/agent/knowledge/frameworks/django.py
backend_old/app/services/agent/knowledge/frameworks/express.py
backend_old/app/services/agent/knowledge/frameworks/fastapi.py
backend_old/app/services/agent/knowledge/frameworks/flask.py
backend_old/app/services/agent/knowledge/frameworks/react.py
backend_old/app/services/agent/knowledge/frameworks/supabase.py
backend_old/app/services/agent/knowledge/loader.py
backend_old/app/services/agent/knowledge/rag_knowledge.py
backend_old/app/services/agent/knowledge/vulnerabilities/auth.py
backend_old/app/services/agent/knowledge/vulnerabilities/business_logic.py
backend_old/app/services/agent/knowledge/vulnerabilities/crypto.py
backend_old/app/services/agent/knowledge/vulnerabilities/csrf.py
backend_old/app/services/agent/knowledge/vulnerabilities/deserialization.py
backend_old/app/services/agent/knowledge/vulnerabilities/injection.py
backend_old/app/services/agent/knowledge/vulnerabilities/open_redirect.py
backend_old/app/services/agent/knowledge/vulnerabilities/path_traversal.py
backend_old/app/services/agent/knowledge/vulnerabilities/race_condition.py
backend_old/app/services/agent/knowledge/vulnerabilities/ssrf.py
backend_old/app/services/agent/knowledge/vulnerabilities/xss.py
backend_old/app/services/agent/knowledge/vulnerabilities/xxe.py
```

### 9. Tools / Tool Runtime (`26`)

当前责任：

- tool definitions
- tool runtime coordinator / contracts
- sandbox / code analysis / queue / reporting 等工具主链

目标状态：

- Rust tool runtime / tool implementations 完全替代 retained Python

文件：

```text
backend_old/app/services/agent/tools/agent_tools.py
backend_old/app/services/agent/tools/base.py
backend_old/app/services/agent/tools/code_analysis_tool.py
backend_old/app/services/agent/tools/control_flow_tool.py
backend_old/app/services/agent/tools/evidence_protocol.py
backend_old/app/services/agent/tools/external_tools.py
backend_old/app/services/agent/tools/file_tool.py
backend_old/app/services/agent/tools/finish_tool.py
backend_old/app/services/agent/tools/kunlun_tool.py
backend_old/app/services/agent/tools/logic_authz_tool.py
backend_old/app/services/agent/tools/pattern_tool.py
backend_old/app/services/agent/tools/queue_tools.py
backend_old/app/services/agent/tools/recon_file_tree_tool.py
backend_old/app/services/agent/tools/recon_queue_tools.py
backend_old/app/services/agent/tools/reporting_tool.py
backend_old/app/services/agent/tools/run_code.py
backend_old/app/services/agent/tools/runtime/context.py
backend_old/app/services/agent/tools/runtime/contracts.py
backend_old/app/services/agent/tools/runtime/coordinator.py
backend_old/app/services/agent/tools/runtime/hooks.py
backend_old/app/services/agent/tools/sandbox_language.py
backend_old/app/services/agent/tools/sandbox_runner_client.py
backend_old/app/services/agent/tools/sandbox_tool.py
backend_old/app/services/agent/tools/sandbox_vuln.py
backend_old/app/services/agent/tools/smart_scan_tool.py
backend_old/app/services/agent/tools/verification_result_tools.py
```

### 10. Agent Support Assets (`7`)

当前责任：

- markdown memory
- system prompt 宿主
- local skill / scan-core 元数据
- SSE / token / tool streaming glue
- vulnerability naming helper

目标状态：

- Rust 侧吸收这些 runtime glue，或在上游功能被 Rust 接管后整体删除

文件：

```text
backend_old/app/services/agent/memory/markdown_memory.py
backend_old/app/services/agent/prompts/system_prompts.py
backend_old/app/services/agent/skills/scan_core.py
backend_old/app/services/agent/streaming/stream_handler.py
backend_old/app/services/agent/streaming/token_streamer.py
backend_old/app/services/agent/streaming/tool_stream.py
backend_old/app/services/agent/utils/vulnerability_naming.py
```

### 11. LLM Retained Runtime (`0`)

当前状态：

- Rust `backend/src/llm/{providers,config}.rs` 已接管 provider/config registry 语义。
- Rust `backend/src/llm/{types,prompt_cache,runtime}.rs` 已接管 request/response shell、prompt-cache policy 与 stream-empty diagnostics 宿主。
- Rust `backend/src/llm/{tokenizer,compression}.rs` 已接管 token heuristic / message compression 宿主。
- `backend_old/app/services/llm/{service,factory,types,base_adapter,prompt_cache,adapters/*}.py` 已退役。
- `backend_old/app/services/llm/{tokenizer,memory_compressor}.py` 已退役。
- `backend_old/app/services/agent/agents/base.py` 已切走对 Python llm tokenizer/compression 模块的依赖。

剩余工作：

- LLM 相关剩余工作不再是 Python runtime blocker，而是 Rust fill-in / parity backlog。

### 12. LLM Rule Retained Runtime (`0`)

当前状态：

- `backend_old/app/services/rule.py` 与 `backend_old/app/services/llm_rule/*` 已整体退役。
- generic rule YAML 校验、git mirror policy、patch filename / diff language parsing 已迁到 Rust `backend/src/llm_rule/*`。

剩余工作：

- repo cache
- rule validator / manager
- generation flow 的剩余语义填补

这些剩余项已经不再计入 Python runtime inventory，而是 Rust fill-in backlog。

### 13. Repo-Adjacent Operational Python Surfaces (`2`)

当前责任：

- flow parser script host
- release / ops preflight helper

目标状态：

- 这些 Python 文件不再承担 live runtime / deploy 责任
- 如果保留，也必须被明确降级为 tooling，而不是被误算成仍依赖 Python backend

文件：

```text
backend_old/scripts/flow_parser_runner.py
scripts/release-templates/runner_preflight.py
```
