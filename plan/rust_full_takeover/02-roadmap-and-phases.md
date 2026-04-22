# Roadmap And Phases

## 文档定位

- 类型：How-to
- 目标读者：继续执行 takeover slice 的开发者

## 总路线

| Phase | 主题 | 目标 |
| --- | --- | --- |
| A | Bootstrap / Core / DB Foundation | Rust 拿到启动、配置、安全、schema 检查和最低控制面基础 |
| B | Models / Schemas / Domain | Rust 拿到 domain / DTO / persistence 结构 |
| C | Shared Services / Contract Stabilization | Rust 拿到项目、搜索、报告等共享服务，并固定前端 contract |
| D | Runtime / Scanner / Launcher | Rust 拿到扫描运行时、queue、workspace、runner orchestration |
| E | Agent / Tool Runtime / Knowledge / LLM | Rust 拿到 agent orchestration、tool runtime、prompt / knowledge、LLM 主链 |
| F | Final Retirement / Ops Tail | 删除剩余 Python、清空 compat bridge，并收掉 alembic / scripts / release preflight |

## 当前阶段

Phase A-C 已完成，Phase D 大部分完成（runtime 计算内核全部 Rust 化）。
当前工作重心位于 Phase E（Agent 智能层，66 个 Python 文件）。
知识库、外部扫描引擎等已决定不做 Rust 接管，直接删除。

现阶段的判断标准：

- Agent 框架是最大单体，需要按功能域整体接管而非逐文件切片
- Tool 系统先于 Agent 框架接管（Agent 依赖 Tool）
- Flow/AST pipeline 已有 Rust bridge，Python 层主要是胶水

## 当前执行顺序

建议按以下顺序推进 Phase E：

1. ORM / Task Models（纯数据结构，Rust DB 层已有对应 schema）
2. Event Manager / Streaming（SSE 事件推送）
3. Config / Runtime Settings / JSON 工具
4. Tool Base + Runtime Coordinator
5. Queue / Recon / File / Code Analysis Tools
6. Flow / AST Pipeline
7. Agent 框架 + 类型实现（最后接管）
8. Prompts / Skills / Memory / Logic

## 单个 Slice 的标准动作

每做一块功能接管，都按同一模板执行：

1. 先盘点 live caller，再决定是否删除 Python 文件。
2. 先让 Rust 拿到 source of truth，再删 Python bridge。
3. 先补 retirement guard 或 contract test，再删目标文件。
4. 完成最小验证闭环后，再回写 canonical 文档。
5. 每完成一个功能 slice，单独提交一个 commit。

## 不再建议的做法

- 不要继续把 canonical 文档写成逐次操作流水账。
- 不要优先清理只剩历史价值的 helper，而放着仍在主链上的 runtime cluster。
- 不要把 route ownership 误判成 runtime ownership；Rust route 已在，不等于 Python runtime 已退役。
