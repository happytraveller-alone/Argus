# Next Targets

## 当前最优先 7 项

### 1. 定位 `config.prompt_skills` 的 live producer owner

这是当前最重要的 open item，因为 prompt skill persistence 已 Rust-owned，但 runtime producer 还没明确 Rust-owned。

### 2. 审计 retained `tool_runtime` 核心 cluster

目标：

- `runtime.py`
- `router.py`
- `health_probe.py`
- `write_scope.py`
- `catalog.py`

### 3. 审计 retained `agent/core` cluster

目标：

- `agents/*`
- `core/*`
- `event_manager.py`
- `config.py`
- `json_parser.py`
- `json_safe.py`
- `push_finding_payload.py`
- `task_findings.py`
- `write_scope.py`

### 4. 审计 scanner / queue / workspace / tracking cluster

目标：

- `scanner_runner.py`
- `scan_workspace.py`
- `scan_tracking.py`
- bootstrap scanners
- queue / event manager

### 5. 审计 support / prompt / stream / memory cluster

目标：

- `memory/markdown_memory.py`
- `prompts/system_prompts.py`
- `skills/scan_core.py`
- `streaming/*`
- `utils/vulnerability_naming.py`

### 6. 审计 knowledge / flow / logic / llm cluster

目标：

- `knowledge/*`
- `flow/*`
- `logic/*`
- `services/llm/*`
- `services/llm_rule/*`

### 7. 准备 final gate：`db` / `alembic` / scripts / frontend consumer debt

目标：

- 重新跑 import 图
- 更新 blocker 清单
- 缩小 alembic / snapshot retained surface
- 清理 `/users/*` 与 `/projects/*/members*` 的 frontend caller debt
- 把 `backend_old/scripts/*` 与 release preflight 放进最终删除/保留判定

## 执行顺序建议

如果后续继续按功能逐一接管，建议按照下面顺序推进：

1. prompt skill runtime producer
2. tool runtime retained core
3. scanner / workspace / queue / bootstrap retained runtime
4. agent orchestration / state / support runtime
5. knowledge / flow / logic retained runtime
6. llm / llm_rule retained runtime
7. models / db / alembic / scripts / release preflight final gate

并行关注的 contract blocker：

- `/users/*` 与 `/projects/*/members*` 的 frontend consumer debt
- `projects` ZIP-only contract 是否继续保留

具体功能块和文件清单见：

- [08-remaining-python-function-inventory.md](/home/xyf/audittool_personal/plan/rust_full_takeover/08-remaining-python-function-inventory.md)
