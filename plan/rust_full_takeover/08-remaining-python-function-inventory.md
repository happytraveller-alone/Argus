# Remaining Python Function Inventory

## 文档定位

- 类型：Reference
- 目标读者：需要按文件面继续拆 takeover slice 的开发者
- 阅读目标：快速知道现在还有哪些 Python 功能没被 Rust 接管，以及它们应落到哪一类 Rust 模块

## 统计口径

- `backend_old` 根目录 Python：`0`
- `backend_old/app/api` Python：`0`
- `backend_old/app` 非 API Python：`133`
- `backend_old/alembic`：`21`
- `backend_old/scripts`：`1`
- `scripts/release-templates/runner_preflight.py`：`1`

`133` 是当前 runtime core 主计数。

它不包含 `scripts/migration/*.py` 这类 inventory / diff tooling；
这类文件默认不算 runtime blocker，但需要与 canonical 文档保持一致。

## 分组总览

| 功能组 | 当前文件数 | 当前责任 | 推荐 Rust 落点 |
| --- | ---: | --- | --- |
| app root / core / config / security | 3 | retained config / encryption / security core | `backend/src/core/*` |
| db / schema snapshot gate | 1 | legacy schema snapshot / final DB gate | `backend/src/db/*` |
| models / persistence mirror | 12 | retained domain / persistence mirror | `backend/src/domain/*`, `backend/src/db/*` |
| shared helpers | 3 | rule、sandbox、path normalization | `backend/src/*` 对应 shared service |
| agent orchestration / state / payload | 22 | agent 执行、状态、消息、payload 归一化 | `backend/src/agent/*`, `backend/src/runtime/*` |
| scanner / queue / workspace / tracking | 4 | queue 语义、runner orchestration、scope filtering | `backend/src/scan/*`, `backend/src/runtime/*` |
| flow / logic | 13 | flow parser、callgraph、AST / authz 分析 | `backend/src/flow/*`, `backend/src/graph/*` |
| knowledge | 21 | knowledge loader、framework / vuln knowledge | `backend/src/knowledge/*` |
| tools + tool runtime | 26 | retained tool execution 主链 | `backend/src/tools/*`, `backend/src/runtime/*` |
| support assets | 7 | memory、prompt、streaming、scan-core 元数据 | `backend/src/agent/*`, `backend/src/runtime/*` |
| llm | 13 | provider / adapter / tokenizer / cache runtime | `backend/src/llm/*` |
| llm_rule | 8 | rule repo、patch、validator、manager | `backend/src/llm_rule/*` |
| repo-adjacent ops tail | 23 | alembic、flow parser script host、release preflight | bootstrap / DB gate replacement or retire |

## 详细功能块

### 1. App Root / Core / Config / Security (`3`)

当前责任：

- Python retained runtime 的设置读取
- legacy 加密 / 安全 / token 兼容逻辑

目标状态：

- Rust 成为唯一配置、安全、加密 source of truth
- Python runtime 不再 import 这些 core 模块

文件：

```text
backend_old/app/core/config.py
backend_old/app/core/encryption.py
backend_old/app/core/security.py
```

### 2. DB Gate / Schema Snapshot (`1`)

当前责任：

- legacy schema snapshot / alembic 最终门

目标状态：

- Rust bootstrap / schema gate 完全替代
- `backend_old/app/db` 整体删除

文件：

```text
backend_old/app/db/schema_snapshots/baseline_5b0f3c9a6d7e.py
```

### 3. Models / Persistence Mirror (`12`)

当前责任：

- retained domain / persistence mirror

目标状态：

- Rust domain / persistence 完全替代
- Python model 不再承担主读写职责

文件：

```text
backend_old/app/models/agent_task.py
backend_old/app/models/analysis.py
backend_old/app/models/audit_rule.py
backend_old/app/models/base.py
backend_old/app/models/opengrep.py
backend_old/app/models/project.py
backend_old/app/models/project_info.py
backend_old/app/models/project_management_metrics.py
backend_old/app/models/prompt_skill.py
backend_old/app/models/prompt_template.py
backend_old/app/models/user.py
backend_old/app/models/user_config.py
```

### 4. Shared Service Retained Helpers (`3`)

当前责任：

- 规则资产
- sandbox helper
- 路径归一化

目标状态：

- 能迁的迁进 Rust shared service
- Python helper 不再参与主运行链

文件：

```text
backend_old/app/services/rule.py
backend_old/app/services/sandbox_runner.py
backend_old/app/services/scan_path_utils.py
```

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

### 6. Scanner / Queue / Workspace / Tracking (`4`)

当前责任：

- retained risk queue / vulnerability queue
- runner orchestration
- scope filtering glue

目标状态：

- Rust scan/runtime cluster 完全接替

文件：

```text
backend_old/app/services/agent/recon_risk_queue.py
backend_old/app/services/agent/scanner_runner.py
backend_old/app/services/agent/scope_filters.py
backend_old/app/services/agent/vulnerability_queue.py
```

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

### 11. LLM Retained Runtime (`13`)

当前责任：

- provider registry
- adapter selection
- prompt cache / tokenizer / memory compression
- actual LLM runtime behavior

目标状态：

- Rust LLM stack 接管主链

文件：

```text
backend_old/app/services/llm/adapters/baidu_adapter.py
backend_old/app/services/llm/adapters/doubao_adapter.py
backend_old/app/services/llm/adapters/litellm_adapter.py
backend_old/app/services/llm/adapters/minimax_adapter.py
backend_old/app/services/llm/base_adapter.py
backend_old/app/services/llm/config_utils.py
backend_old/app/services/llm/factory.py
backend_old/app/services/llm/memory_compressor.py
backend_old/app/services/llm/prompt_cache.py
backend_old/app/services/llm/provider_registry.py
backend_old/app/services/llm/service.py
backend_old/app/services/llm/tokenizer.py
backend_old/app/services/llm/types.py
```

### 12. LLM Rule Retained Runtime (`8`)

当前责任：

- rule repo cache
- patch processor
- rule validator / manager / client

目标状态：

- Rust rule pipeline 接管，或被明确废弃替代

文件：

```text
backend_old/app/services/llm_rule/cache_manager.py
backend_old/app/services/llm_rule/config.py
backend_old/app/services/llm_rule/git_manager.py
backend_old/app/services/llm_rule/llm_client.py
backend_old/app/services/llm_rule/patch_processor.py
backend_old/app/services/llm_rule/repo_cache_manager.py
backend_old/app/services/llm_rule/rule_manager.py
backend_old/app/services/llm_rule/rule_validator.py
```

### 13. Repo-Adjacent Operational Python Surfaces (`23`)

当前责任：

- legacy schema compatibility / revision chain
- flow parser script host
- release / ops preflight helper

目标状态：

- 这些 Python 文件不再承担 live runtime / deploy 责任
- 如果保留，也必须被明确降级为 tooling，而不是被误算成仍依赖 Python backend

文件：

```text
backend_old/alembic/env.py
backend_old/alembic/versions/1f2e3d4c5b6a_add_verified_project_management_metrics.py
backend_old/alembic/versions/5b0f3c9a6d7e_squashed_baseline.py
backend_old/alembic/versions/6c8d9e0f1a2b_finalize_projects_zip_file_hash.py
backend_old/alembic/versions/7f8e9d0c1b2a_normalize_static_finding_paths.py
backend_old/alembic/versions/8c1d2e3f4a5b_add_agent_finding_identity.py
backend_old/alembic/versions/9a7b6c5d4e3f_enforce_agent_finding_task_uniqueness.py
backend_old/alembic/versions/9d3e4f5a6b7c_add_bandit_rule_states.py
backend_old/alembic/versions/a1b2c3d4e5f6_add_phpstan_rule_states.py
backend_old/alembic/versions/a8f1c2d3e4b5_add_agent_tasks_report_column.py
backend_old/alembic/versions/b2c3d4e5f6a7_add_bandit_rule_soft_delete.py
backend_old/alembic/versions/b7e8f9a0b1c2_add_yasa_scan_tables.py
backend_old/alembic/versions/b9d8e7f6a5b4_drop_legacy_audit_tables.py
backend_old/alembic/versions/c3d4e5f6a7b8_add_phpstan_rule_soft_delete.py
backend_old/alembic/versions/c9d0e1f2a3b4_add_yasa_rule_configs_and_task_binding.py
backend_old/alembic/versions/d4e5f6a7b8c9_add_prompt_skills_table.py
backend_old/alembic/versions/da4e5f6a7b8c_add_pmd_rule_configs.py
backend_old/alembic/versions/e1f2a3b4c5d6_add_pmd_scan_tables.py
backend_old/alembic/versions/e5f6a7b8c9d0_add_project_management_metrics.py
backend_old/alembic/versions/f1e2d3c4b5a6_scope_agent_tree_nodes_per_task.py
backend_old/alembic/versions/f6a7b8c9d0e1_remove_fixed_static_finding_status.py
backend_old/scripts/flow_parser_runner.py
scripts/release-templates/runner_preflight.py
```
