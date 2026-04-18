# Current State And Ledger

## 文档定位

- 类型：Reference
- 目标读者：需要快速判断“现状”和“剩余面”的开发者

## 当前快照

- `backend_old` 根目录 Python：`0`
- `backend_old/app/api` Python：`0`
- `backend_old/app` 非 API Python：`130`
- `backend_old/alembic` Python：`21`
- `backend_old/scripts` Python：`1`
- `scripts/release-templates/runner_preflight.py`：`1`

## 剩余功能组总览

| 功能组 | 当前文件数 | 仍承担的责任 |
| --- | ---: | --- |
| app root / core / config / security | 3 | retained config / encryption / security core |
| db / schema snapshot gate | 1 | legacy schema snapshot / final DB gate |
| models / persistence mirror | 12 | retained domain / persistence mirror |
| shared helpers | 3 | rule、sandbox、path normalization |
| agent orchestration / state / payload | 22 | agent 执行、状态、消息、payload 归一化 |
| scanner / queue / workspace / tracking | 1 | scope filtering、剩余 scanner 主链 |
| flow / logic | 13 | flow parser、callgraph、AST / authz 逻辑 |
| knowledge | 21 | knowledge loader、framework / vuln knowledge |
| tools + tool runtime | 26 | retained tool execution 主链 |
| support assets | 7 | memory、prompt、streaming、scan-core 元数据 |
| llm | 13 | provider / adapter / cache / tokenizer runtime |
| llm_rule | 8 | rule repo、patch、validator、manager |
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
3. `core/flow/*`、`logic/*`、`tools/*`、`knowledge/*`、`llm/*` 仍是大块 live Python runtime。
4. `backend_old/alembic/*`、`backend_old/scripts/flow_parser_runner.py`、`scripts/release-templates/runner_preflight.py` 仍阻止最终退休。
5. retired route 的 frontend caller debt 与最终 readiness gate 还没有被完全验证。

## 最近完成的 slice

- `backend_old/app/services/agent/scanner_runner.py` 已退役。
- Rust `backend-runtime-startup runner execute|stop` 现在承担 scanner runner contract。
- Python `flow_parser_runner.py` 已改为直接调用 Rust runner bridge，不再 import `app.services.agent.scanner_runner`。
- `backend_old/app/services/agent/recon_risk_queue.py` 与 `backend_old/app/services/agent/vulnerability_queue.py` 已退役。
- Rust `backend/src/runtime/queue.rs` 现在承担 agent-test queue snapshot 与 queue fingerprint 语义宿主。

## 本目录内的使用方式

- 要看优先级：去 [07-next-targets.md](/home/xyf/audittool_personal/plan/rust_full_takeover/07-next-targets.md)
- 要看验证门：去 [05-validation-and-gates.md](/home/xyf/audittool_personal/plan/rust_full_takeover/05-validation-and-gates.md)
- 要看精确文件清单：去 [08-remaining-python-function-inventory.md](/home/xyf/audittool_personal/plan/rust_full_takeover/08-remaining-python-function-inventory.md)
- 要看原始证据入口：去 [reference/README.md](/home/xyf/audittool_personal/plan/rust_full_takeover/reference/README.md)
