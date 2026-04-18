# Current State And Ledger

## 当前快照

- `backend_old` 根目录 Python：`0`
- `backend_old/app/api` Python：`0`
- `backend_old/app` 非 API Python：`157`
- `backend_old/alembic` Python：`21`
- `backend_old/scripts` Python：`1`
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

- app root / core / config / security：`3`
- db / schema snapshot gate：`1`
- models / persistence mirror：`17`
- shared helpers：`6`
- agent orchestration / state / payload：`24`
- scanner / bootstrap / queue / workspace / tracking：`17`
- flow / logic：`13`
- knowledge：`21`
- tools / tool runtime：`27`
- agent support assets（memory / prompts / streaming / local-skill metadata）：`7`
- llm：`13`
- llm_rule：`8`
- repo-adjacent ops tail：
  - `backend_old/alembic/*`
  - `backend_old/scripts/*`
  - `scripts/release-templates/runner_preflight.py`

## 当前最重要的 open items

- `prompt_skill_runtime` compat projection 已收口（2026-04-18）：Rust `legacy_python_config` 投影从未落地（WIP 已撤销），Python 5 个 agent（recon / analysis / verification / business_logic_recon / business_logic_analysis）的 `config.prompt_skills` 注入块全部删除，`test_prompt_skills_injection.py` 已删。Rust `upsert_legacy_prompt_skill` / `compat_backfill_from_legacy_if_empty` 仍保留以支撑 alembic legacy 表，属于后续 DB final gate slice 的目标。
- `tool_runtime` retained core（`runtime` / `router` / `health_probe` / `write_scope` / `catalog`）2026-04-18 整组退役。
- `backend_old/scripts/package_source_selector.py` 已于 2026-04-18 退役：Rust `runtime/bootstrap.rs` 原生接管 PyPI candidate probe / 排序，`dev-entrypoint.sh` 与相关 Dockerfile 改为 shell 内按配置顺序去重回退；`backend_old/scripts` Python 计数 `2 -> 1`。
- `backend_old/app/db/__init__.py` 已于 2026-04-18 退役：`bandit_rules_snapshot.py` 与 `pmd_rulesets.py` 直接读取 Rust-owned scan-rule asset root，`db / schema snapshot gate` 分组计数 `3 -> 2`，`backend_old/app` runtime core 计数 `167 -> 166`。
- `backend_old/app/services/llm/__init__.py` 与 `backend_old/app/services/agent/agents/__init__.py` 已于 2026-04-18 退役：live importer 已改为 direct-module imports，且 flow live caller 已从旧 `agent.flow` 路径切到 `agent.core.flow`；`backend_old/app` runtime core 计数 `166 -> 164`，`agent orchestration / state / payload` 计数 `25 -> 24`，`llm` 计数 `15 -> 14`。
- `backend_old/app/core/__init__.py` 与 `backend_old/app/models/__init__.py` 已于 2026-04-18 退役：Alembic `env.py` 改为显式导入各 model module 完成 metadata 注册；`backend_old/app` runtime core 计数 `164 -> 162`，`app root / core / config / security` 计数 `5 -> 4`，`models / persistence mirror` 计数 `18 -> 17`。
- `backend_old/app/__init__.py`、`backend_old/app/db/schema_snapshots/__init__.py`、`backend_old/app/services/agent/core/flow/lightweight/__init__.py`、`backend_old/app/services/llm/adapters/__init__.py` 已于 2026-04-18 退役：residual namespace/package shell 清零，`backend_old/app` runtime core 计数 `162 -> 158`，`app root / core / config / security` 计数 `4 -> 3`，`db / schema snapshot gate` 计数 `2 -> 1`，`flow / logic` 计数 `14 -> 13`，`llm` 计数 `14 -> 13`。
- `backend_old/app/services/rule_contracts.py` 已于 2026-04-18 退役：`OpengrepRuleCreateRequest` 已内联到 `rule.py`，`backend_old/app` runtime core 计数 `158 -> 157`，`shared helpers` 计数 `7 -> 6`。
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
