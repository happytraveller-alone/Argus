# Open Risks And Bridges

## 仍保留的 bridge

- projects mirror
- system-config mirror
- prompt skill mirror（Rust `upsert_legacy_prompt_skill` / `compat_backfill_from_legacy_if_empty` 仍在，用于 alembic legacy 表的 schema 支撑；`prompt_skill_runtime` -> `config.prompt_skills` compat projection 已对称退役，不再在此列）
- legacy schema / prompt-skill compat backfill
- runner preflight / startup 中仍保留的 Python-aware 兼容逻辑

## 当前主要风险

### Route ownership != runtime ownership

`agent-tasks`、`agent-test`、`static-tasks` 的 Rust 路由表面已在，
但 retained Python runtime 本体并未完全退掉。

### Retired route consumer debt

route inventory 里被放进 `retire` 的 `/users/*`、`/projects/*/members*`
仍不能直接视为“前端消费者已清零”。

后续如果继续删除这批 route，对应 frontend caller 需要先清零或显式桥接。

### Behavioral narrowing risk

Rust `projects` surface 当前是 ZIP-only。

这属于 contract narrowing，不只是内部实现细节。
如果要继续沿着这个方向收口，文档、前端类型和验证门都必须同步。

### Prompt Skill Runtime Compat Projection 已收口（2026-04-18）

对称退役完成：
- Rust 未落地的 `legacy_python_config` 字段连同投影 helper 撤销
- Python 5 个 agent 的 `config.prompt_skills` 注入块删除
- Rust mirror / backfill 保留，用于 alembic legacy 表的 schema 支撑（后续 DB final gate slice 处理）

### Health 200 != Ready

当前容器 healthcheck 仍可能只证明 `/health` 可以返回 HTTP `200`，
并不等于 bootstrap / preflight / legacy schema gate 全部已通过。

### DB / Alembic Final Gate 仍未过

`backend_old/app/db`、`backend_old/alembic`、schema snapshot 相关内容
仍不能直接删。

## Final Python Retirement Checklist

只有下面这些项同时过门，才可以把“Rust 已接管全部 Python”当成接近完成：

1. agent-task creation 写入 Rust-owned `prompt_skill_runtime` snapshot；`config.prompt_skills` compat projection 已对称退役（已完成，2026-04-18），剩余仅 Rust mirror / backfill 用于 alembic 兼容。
2. `tool_runtime`、scanner/bootstrap、agent orchestration 主链不再依赖 retained Python。
3. `/health` JSON 为 `ok`，而不是仅 HTTP `200`。
4. agent/static 真路径 smoke 与 runner preflight 成功。
5. `PYTHON_ALEMBIC_ENABLED`、legacy mirror、compat backfill 的退出路径明确且可验证。
6. `/users/*`、`/projects/*/members*` 这类 retired route 没有剩余 frontend caller。
7. `backend_old/alembic`、`backend_old/scripts`、release preflight 的 Python 尾巴完成删除或被明确声明为非运行时资产。
