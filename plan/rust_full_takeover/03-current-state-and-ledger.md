# Current State And Ledger

## 文档定位

- 类型：Reference
- 目标读者：需要快速判断“现状”和“剩余面”的开发者

## 当前快照

- `backend_old` 根目录 Python：`0`
- `backend_old/app/api` Python：`0`
- `backend_old/app` 非 API Python：`104`
- `backend_old/alembic` Python：`21`
- `backend_old/scripts` Python：`1`
- `scripts/release-templates/runner_preflight.py`：`1`

## 剩余功能组总览

| 功能组 | 当前文件数 | 仍承担的责任 |
| --- | ---: | --- |
| app root / core / config / security | 1 | retained config core；security/encryption 已退役 |
| db / schema snapshot gate | 1 | legacy schema snapshot / final DB gate |
| models / persistence mirror | 12 | retained domain / persistence mirror |
| shared helpers | 0 | Python shared helpers 已退役 |
| agent orchestration / state / payload | 22 | agent 执行、状态、消息、payload 归一化 |
| scanner / queue / workspace / tracking | 1 | scope filtering、剩余 scanner 主链 |
| flow / logic | 13 | flow parser、callgraph、AST / authz 逻辑 |
| knowledge | 21 | knowledge loader、framework / vuln knowledge |
| tools + tool runtime | 26 | retained tool execution 主链 |
| support assets | 7 | memory、prompt、streaming、scan-core 元数据 |
| llm | 0 | Python llm runtime 已退役，剩余 fill-in 只在 Rust `backend/src/llm/*` |
| llm_rule | 0 | Python rule runtime 已退役，剩余 fill-in 折到 Rust `backend/src/llm_rule/*` |
| repo-adjacent ops tail | 23 | alembic、flow parser script host、release preflight |

## Rust 已拿到的外层表面

目前 Rust 已经承担了主要 route surface，至少包括：

- `/api/v1/projects/*`
- `/api/v1/system-config/*`
- `/api/v1/search/*`
- `/api/v1/skills/*`
- `/api/v1/agent-tasks/*`
- `/api/v1/agent-test/*`
- `/api/v1/static-tasks/*`

这只能证明 route ownership 已迁到 Rust，不能证明 Python runtime 已经退出。

## 当前最重要的 blocker

1. `scope_filters.py` 仍在控制 retained scanner 主链；queue service source of truth 已切到 Rust `runtime::queue`。
2. `services/agent/agents/*`、`core/*`、`event_manager.py` 等仍承担 agent orchestration / state 主链。
3. `core/flow/*`、`logic/*`、`tools/*`、`knowledge/*` 仍是大块 live Python runtime；`llm/*` Python runtime 已清零。
4. `backend_old/app/core/config.py` 与 `backend_old/app/db/schema_snapshots/baseline_5b0f3c9a6d7e.py` 已成为当前 core/db 尾巴；它们仍被 flow/tool/alembic 依赖，尚不能误记为已退役。
5. `backend_old/alembic/*`、`backend_old/scripts/flow_parser_runner.py`、`scripts/release-templates/runner_preflight.py` 仍阻止最终退休。
6. retired route 的 frontend caller debt 与最终 readiness gate 还没有被完全验证。

## 最近完成的 slice

- Rust `backend/src/core/{security,encryption}.rs` 已成为 password hashing / JWT 与 sensitive-field encryption 的唯一语义宿主。
- `backend_old/app/core/security.py` 与 `backend_old/app/core/encryption.py` 已退役；Python 测试侧 direct importer 已清零。
- 新增 `backend_old/tests/test_core_security_encryption_retired.py` guard；`backend_old/tests/conftest.py` 不再 import `app.core.security`，`test_startup_runtime_warnings.py` 已改为校验 retired module 的正确失败模式。
- `backend_old/app/services/agent/scanner_runner.py` 已退役。
- Rust `backend-runtime-startup runner execute|stop` 现在承担 scanner runner contract。
- Python `flow_parser_runner.py` 已改为直接调用 Rust runner bridge，不再 import `app.services.agent.scanner_runner`。
- `backend_old/app/services/agent/recon_risk_queue.py` 与 `backend_old/app/services/agent/vulnerability_queue.py` 已退役。
- Rust `backend/src/runtime/queue.rs` 现在承担 agent-test queue snapshot 与 queue fingerprint 语义宿主。
- Rust `backend/src/llm_rule/mod.rs` 现在承担 generic opengrep rule YAML 的规范化与 schema 校验语义。
- `/api/v1/static-tasks/rules/create-generic`、`/rules/upload/json` 与 rule update 已切到 Rust 校验链，不再依赖 `backend_old/app/services/rule.py` 里的 `validate_generic_rule()` helper。
- Rust `backend/src/llm_rule/git.rs` 已拿到 HTTPS-only / git mirror candidate 语义宿主。
- Rust `backend/src/llm_rule/patch.rs` 已拿到 patch 文件名与 diff 语言分组解析；`/api/v1/static-tasks/rules/create` 开始消费这些 patch 元数据来生成 rule shell。
- `backend_old/app/services/rule.py` 与 `backend_old/app/services/llm_rule/*` 已整体退役；Python 侧新增 retirement guard 防止旧 importer 回流。
- Rust `backend/src/llm/{providers,config}.rs` 已接管 provider alias / catalog、runtime provider metadata、base URL normalize 与 custom header parsing；`/api/v1/system-config/{llm-providers,fetch-llm-models}` 不再依赖 Python `config_utils.py` / `provider_registry.py`。
- Rust `backend/src/llm/{types,prompt_cache,runtime}.rs` 已接管 llm request/response shell、prompt-cache policy 与 stream-empty diagnostics 宿主；`backend_old/app/services/llm/{service,factory,types,base_adapter,prompt_cache,adapters/*}.py` 已退役。
- Rust `backend/src/llm/{tokenizer,compression}.rs` 已接管 token heuristic / message compression 宿主；`backend_old/app/services/llm/{tokenizer,memory_compressor}.py` 已退役。
- `backend_old/app/services/agent/agents/base.py` 已切走对 Python llm tokenizer/compression 模块的依赖，`backend_old/app/services/llm/*` 现已清零。
- Rust `backend/src/scan/path_utils.rs` 已接管 scan path normalization / archive member resolution 语义；`backend_old/app/services/scan_path_utils.py` 已退役。
- Rust `backend/src/runtime/sandbox.rs` 已接管 sandbox spec/result shell；`backend_old/app/services/sandbox_runner.py` 已退役，live Python caller 已收束到 `sandbox_runner_client.py`。

## 本目录内的使用方式

- 要看优先级：去 [07-next-targets.md](/home/xyf/audittool_personal/plan/rust_full_takeover/07-next-targets.md)
- 要看验证门：去 [05-validation-and-gates.md](/home/xyf/audittool_personal/plan/rust_full_takeover/05-validation-and-gates.md)
- 要看精确文件清单：去 [08-remaining-python-function-inventory.md](/home/xyf/audittool_personal/plan/rust_full_takeover/08-remaining-python-function-inventory.md)
- 要看原始证据入口：去 [reference/README.md](/home/xyf/audittool_personal/plan/rust_full_takeover/reference/README.md)
