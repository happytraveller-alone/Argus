# Roadmap And Phases

## 文档定位

- 类型：Implementation Plan
- 目标读者：后续接手实现的开发者

## 总路线

| Phase | 主题 | 目标 |
| --- | --- | --- |
| A | Bootstrap / Core / DB Foundation | Rust 拿到启动、配置、安全、schema 检查和最低控制面基础 |
| B | Models / Schemas / Domain | Rust 拿到完整 domain / DTO / persistence 结构 |
| C | Shared Services | Rust 拿到项目、上传、搜索、报告等共享服务 |
| D | Runtime / Scanner / Launcher | Rust 拿到扫描运行时、launcher、workspace、runner orchestration |
| E | Agent / Tool Runtime / Knowledge / LLM | Rust 拿到 agent orchestration、tool runtime、prompt skill、knowledge、LLM 主链 |
| F | Final Retirement | 删除剩余 Python、清空 compat bridge、统一文档与仓库结构 |

## 当前阶段

当前已跨过 A 的主要基础门，正在 E / F 交界处推进：

- `skills` 默认 contract 已改成 Rust-owned unified surface
- prompt skill persistence boundary 已迁到 Rust-native store
- 大量 dead shell / convenience package / test-only helper 已退休
- retained live Python runtime 仍未完全退出

## 当前阶段重点

1. caller 盘点优先于删除
2. source of truth 优先于 helper 清理
3. dead shell 收益开始下降，后续更应转向 retained live cluster
