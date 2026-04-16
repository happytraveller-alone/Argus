# Current State And Ledger

## 当前快照

- `backend_old` 根目录 Python：`0`
- `backend_old/app/api` Python：`0`
- `backend_old/app` 非 API Python：`172`
- `backend_old/alembic` Python：`21`
- `backend_old/scripts` Python：`2`
- `scripts/release-templates` 运行相关 Python：`1`

## Rust 已接管的主表面

- `/api/v1/projects/*`
- `/api/v1/system-config/*`
- `/api/v1/search/*`
- `/api/v1/skills/*`
- `/api/v1/agent-tasks/*`
- `/api/v1/agent-test/*`
- `/api/v1/static-tasks/*`

## 仍保留的 Python cluster

- app root / core / config / security：`5`
- db / schema snapshot gate：`3`
- models / persistence mirror：`18`
- shared helpers：`7`
- agent orchestration / state / payload：`25`
- scanner / bootstrap / queue / workspace / tracking：`17`
- flow / logic：`14`
- knowledge：`21`
- tools / tool runtime：`32`
- agent support assets（memory / prompts / streaming / local-skill metadata）：`7`
- llm：`15`
- llm_rule：`8`
- repo-adjacent ops tail：
  - `backend_old/alembic/*`
  - `backend_old/scripts/*`
  - `scripts/release-templates/runner_preflight.py`

## 当前最重要的 open items

- `config.prompt_skills` 已不再是 owner 未明确的问题；Rust 已在 agent-task creation 侧写入 `prompt_skill_runtime` snapshot，剩余 open item 收窄为 retained Python consumer 的 compat projection / cutover。
- `retire` bucket 里的 `/users/*` 与 `/projects/*/members*` 仍存在 frontend caller debt，不能被默认为“消费者已清零”。
- `/health` HTTP `200` 不是最终 readiness 证据；最终 cutover 仍缺 JSON-level health / runner smoke / legacy DB gate。

## 待接管功能清单入口

完整的按功能分组的剩余 Python 功能清单见：

- [08-remaining-python-function-inventory.md](/home/xyf/audittool_personal/plan/rust_full_takeover/08-remaining-python-function-inventory.md)

API 路由历史分桶与 raw route inventory 见：

- [wait_correct/route-inventory/python-endpoints-summary.md](/home/xyf/audittool_personal/plan/wait_correct/route-inventory/python-endpoints-summary.md)

## 原始 ledger

详细历史账本与 raw reference 保留在：

- [archive/legacy-ledgers/backend-old-python-ledger.md](/home/xyf/audittool_personal/plan/rust_full_takeover/archive/legacy-ledgers/backend-old-python-ledger.md)
- [reference/README.md](/home/xyf/audittool_personal/plan/rust_full_takeover/reference/README.md)
