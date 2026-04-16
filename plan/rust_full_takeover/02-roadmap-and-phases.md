# Roadmap And Phases

## 文档定位

- 类型：Implementation Plan
- 目标读者：后续接手实现的开发者

## 总路线

| Phase | 主题 | 目标 |
| --- | --- | --- |
| A | Bootstrap / Core / DB Foundation | Rust 拿到启动、配置、安全、schema 检查和最低控制面基础 |
| B | Models / Schemas / Domain | Rust 拿到完整 domain / DTO / persistence 结构 |
| C | Shared Services / Contract Stabilization | Rust 拿到项目、上传、搜索、报告等共享服务，并固定前端可见 contract |
| D | Runtime / Scanner / Launcher | Rust 拿到扫描运行时、launcher、workspace、runner orchestration |
| E | Agent / Tool Runtime / Knowledge / LLM | Rust 拿到 agent orchestration、tool runtime、prompt skill、knowledge、LLM 主链 |
| F | Final Retirement / Ops Tail | 删除剩余 Python、清空 compat bridge，并收掉 alembic / scripts / release preflight 等运维尾巴 |

## 当前阶段

当前已跨过 A 的主要基础门，正在 E / F 交界处推进：

- `skills` 默认 contract 已改成 Rust-owned unified surface
- prompt skill persistence boundary 已迁到 Rust-native store
- agent-task creation 已写入 Rust-owned `prompt_skill_runtime` snapshot
- 大量 dead shell / convenience package / test-only helper 已退休
- retained live Python runtime 仍未完全退出
- frontend / deploy 层面的最终 cutover gate 还没有被完整写进 canonical 文档

## 当前阶段重点

1. caller 盘点优先于删除
2. source of truth 优先于 helper 清理
3. API invariants 优先于 route retire
4. dead shell 收益开始下降，后续更应转向 retained live cluster
5. `backend_old/app` 清零之前，不得误判为“Python 已全退役”；`alembic / scripts / release preflight` 仍属于最终门
