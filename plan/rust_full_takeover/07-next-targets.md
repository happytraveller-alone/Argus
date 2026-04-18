# Next Targets

## 文档定位

- 类型：How-to
- 目标读者：需要直接接手下一轮功能接管的开发者

## 当前优先级

### 1. Scanner / Queue / Runner 主链

目标文件：

- `backend_old/app/services/agent/recon_risk_queue.py`
- `backend_old/app/services/agent/vulnerability_queue.py`
- `backend_old/app/services/agent/scanner_runner.py`
- `backend_old/app/services/agent/scope_filters.py`

完成标准：

- Rust 拿到 queue 语义、runner orchestration、scope filtering 的 source of truth
- Python cluster 删除
- 新增或更新 retirement guard

### 2. Agent Orchestration / State / Payload 主链

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

### 3. Flow / Logic 主链

目标范围：

- `backend_old/app/services/agent/core/flow/*`
- `backend_old/app/services/agent/logic/*`

完成标准：

- flow parser、callgraph、definition lookup、authz logic 由 Rust 承担
- Python flow runner / lightweight analysis 不再处于主链

### 4. Tool Runtime + Support Glue

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

### 5. Knowledge + LLM + Rule Runtime

目标范围：

- `backend_old/app/services/agent/knowledge/*`
- `backend_old/app/services/llm/*`
- `backend_old/app/services/llm_rule/*`

完成标准：

- Rust 成为 knowledge、provider、prompt cache、rule repo / validator 的主运行时

### 6. Models / DB / Alembic / Ops Tail Final Gate

目标范围：

- `backend_old/app/models/*`
- `backend_old/app/db/schema_snapshots/*`
- `backend_old/alembic/*`
- `backend_old/scripts/flow_parser_runner.py`
- `scripts/release-templates/runner_preflight.py`

完成标准：

- legacy schema / mirror / preflight 不再阻止 Python 退役
- runtime tail 有明确删除或降级结论

## 当前执行原则

1. 优先接管仍在主链上的 runtime cluster，不回头做低收益的历史壳层清理。
2. 每完成一个功能 slice，就补 guard、跑验证、更新文档并提交一次 commit。
3. 如果某块只能做到 Rust 外壳而不能切换 source of truth，就不要把它记成“已接管”。
