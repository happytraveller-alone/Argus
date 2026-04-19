# Open Risks And Bridges

## 文档定位

- 类型：Explanation
- 目标读者：需要判断“为什么现在还不能宣布完成”的开发者

## 仍需明确处理的 bridge

- Rust route surface 背后仍可能存在 retained Python runtime
- `backend_old/scripts/flow_parser_runner.py` 仍承担 flow parser script host 角色
- startup / preflight 仍有 Python-aware 运维尾巴

## 当前主要风险

### Route Ownership != Runtime Ownership

`agent-tasks`、`agent-test`、`static-tasks` 的 Rust 路由表面已在，
但 retained Python runtime 本体仍然存在。

### Retired Route Consumer Debt

route inventory 里被放进 `retire` 的 `/users/*`、`/projects/*/members*`
不能直接视为“前端消费者已清零”。

### Behavioral Narrowing Risk

Rust 接管某些 surface 时，可能会顺带收窄行为。
这不是纯内部实现细节，必须同步写清 contract、前端影响和验证结论。

### Health 200 != Ready

容器 healthcheck 可以返回 HTTP `200`，
但这并不等于 bootstrap / preflight gate 全部通过。

### Deletion-Only False Positive

如果只看到 Python 文件数下降，而没有验证：

- Rust source of truth 已接管
- 真实调用链已经切换
- smoke / contract / guard 全通过

那么就不能把该 slice 当成“完成接管”。

## Final Python Retirement Checklist

只有下面这些项同时过门，才可以把“Rust 已接管全部 Python”视为接近完成：

1. scanner / queue / runner 主链不再依赖 retained Python。
2. agent orchestration / flow / tools / knowledge / llm 主链不再依赖 retained Python。
3. `/health` JSON 为 `ok`，而不是仅 HTTP `200`。
4. agent / static 真路径 smoke 与 runner preflight 成功。
5. startup compat bridge 的退出路径明确且可验证。
6. `/users/*`、`/projects/*/members*` 这类 retired route 没有剩余 frontend caller。
7. `backend_old/scripts`、release preflight 的 Python 尾巴完成删除或被明确降级为非运行时资产。
