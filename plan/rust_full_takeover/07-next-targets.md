# Next Targets

## 当前最优先 6 项

### ~~1. 收口 `prompt_skill_runtime` -> `config.prompt_skills` 的 compat projection / consumer cutover~~

✅ 已完成（2026-04-18）。Rust 未落地的 `legacy_python_config` 投影撤销，Python 5 个 agent 注入块全部删除，`test_prompt_skills_injection.py` 删除。Rust mirror / backfill 保留用于 alembic 兼容，归入后续 DB final gate slice。

### ~~1. 审计 retained `tool_runtime` 核心 cluster~~

✅ 已完成（2026-04-18）。`runtime.py`、`router.py`、`health_probe.py`、`write_scope.py`、`catalog.py` 已整组退役，`base.py` 的 dead `TYPE_CHECKING` import 已清理，retirement guard 已上线。

目标：

- `runtime.py`
- `router.py`
- `health_probe.py`
- `write_scope.py`
- `catalog.py`

### 2. 审计 retained `agent/core` cluster

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

### 3. 审计 scanner / queue / workspace / tracking cluster

目标：

- `scanner_runner.py`
- `scan_workspace.py`
- `scan_tracking.py`
- bootstrap scanners
- queue / event manager

### 4. 审计 support / prompt / stream / memory cluster

目标：

- `memory/markdown_memory.py`
- `prompts/system_prompts.py`
- `skills/scan_core.py`
- `streaming/*`
- `utils/vulnerability_naming.py`

### 5. 审计 knowledge / flow / logic / llm cluster

目标：

- `knowledge/*`
- `flow/*`
- `logic/*`
- `services/llm/*`
- `services/llm_rule/*`

### 6. 准备 final gate：`db` / `alembic` / scripts / frontend consumer debt

目标：

- 重新跑 import 图
- 更新 blocker 清单
- 缩小 alembic / snapshot retained surface
- 清理 `/users/*` 与 `/projects/*/members*` 的 frontend caller debt
- 把 `backend_old/scripts/*` 与 release preflight 放进最终删除/保留判定

## 执行顺序建议

如果后续继续按功能逐一接管，建议按照下面顺序推进：

1. scanner / workspace / queue / bootstrap retained runtime
2. agent orchestration / state / support runtime
3. knowledge / flow / logic retained runtime
4. llm / llm_rule retained runtime
5. models / db / alembic / scripts / release preflight final gate

（prompt skill runtime compat projection 已于 2026-04-18 对称退役。）

并行关注的 contract blocker：

- `/users/*` 与 `/projects/*/members*` 的 frontend consumer debt
- `projects` ZIP-only contract 是否继续保留

具体功能块和文件清单见：

- [08-remaining-python-function-inventory.md](/home/xyf/audittool_personal/plan/rust_full_takeover/08-remaining-python-function-inventory.md)
