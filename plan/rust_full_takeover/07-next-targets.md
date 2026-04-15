# Next Targets

## 当前最优先 5 项

### 1. 定位 `config.prompt_skills` 的 live producer owner

这是当前最重要的 open item，因为 prompt skill persistence 已 Rust-owned，但 runtime producer 还没明确 Rust-owned。

### 2. 审计 retained `tool_runtime` 核心 cluster

目标：

- `runtime.py`
- `router.py`
- `health_probe.py`
- `write_scope.py`

### 3. 审计 retained `agent/core` cluster

目标：

- `state.py`
- `registry.py`
- `context.py`
- `logging.py`

### 4. 审计 scanner / queue / workspace / tracking cluster

目标：

- `scanner_runner.py`
- `scan_workspace.py`
- `scan_tracking.py`
- bootstrap scanners
- queue / event manager

### 5. 准备 `backend_old/app/db` 最终删除门

目标：

- 重新跑 import 图
- 更新 blocker 清单
- 缩小 alembic / snapshot retained surface
