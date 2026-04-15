# Current State And Ledger

## 当前快照

- `backend_old` 根目录 Python：`0`
- `backend_old/app` 非 API Python：`172`

## Rust 已接管的主表面

- `/api/v1/projects/*`
- `/api/v1/system-config/*`
- `/api/v1/search/*`
- `/api/v1/skills/*`
- `/api/v1/agent-tasks/*`
- `/api/v1/agent-test/*`
- `/api/v1/static-tasks/*`

## 仍保留的 Python cluster

- db / alembic / schema snapshot gate
- scanner / bootstrap / queue / workspace / tracking
- tool runtime core：`runtime.py`、`router.py`、`health_probe.py`、`write_scope.py`
- agent core retained cluster
- knowledge retained cluster
- llm / llm_rule retained cluster

## 当前最重要的 open item

`config.prompt_skills` 的 live producer owner 仍未明确。

## 原始 ledger

详细历史账本与 raw reference 保留在：

- [archive/legacy-ledgers/backend-old-python-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/archive/legacy-ledgers/backend-old-python-ledger.md)
- [reference/README.md](/home/xyf/audittool_personal/plan/rust_full_takeover/reference/README.md)
