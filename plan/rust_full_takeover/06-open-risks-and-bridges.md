# Open Risks And Bridges

## 仍保留的 bridge

- projects mirror
- system-config mirror
- prompt skill mirror

## 当前主要风险

### Route ownership != runtime ownership

`agent-tasks`、`agent-test`、`static-tasks` 的 Rust 路由表面已在，
但 retained Python runtime 本体并未完全退掉。

### Prompt Skill Runtime Producer 未明确

当前最重要的 open item：

- 谁在 live 链路里把 Rust-side prompt skill 状态产生成 `config.prompt_skills`

### DB / Alembic Final Gate 仍未过

`backend_old/app/db`、`backend_old/alembic`、schema snapshot 相关内容
仍不能直接删。
