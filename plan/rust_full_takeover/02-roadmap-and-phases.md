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
| E | ACP-aligned Agent / Tool Runtime / Knowledge / LLM | Rust 拿到 `agent_tasks` runtime lifecycle、tool runtime、prompt / knowledge、LLM 主链 |
| F | Final Retirement / Ops Tail | 删除剩余 Python、清空 compat bridge，并收掉 alembic / scripts / release preflight |

## 当前阶段

Phase A-C 已完成，Phase D 大部分完成（runtime 计算内核全部 Rust 化）。
当前工作重心位于 Phase E（Agent 智能层，66 个 Python 文件）。
当前主线不再是宽泛的“逐模块扫平”，而是先完成 **ACP + Rust runtime for `agent_tasks`**。
知识库、外部扫描引擎等已决定不做 Rust 接管，直接删除。

现阶段的判断标准：

- Agent 框架仍是最大单体，但当前更优先的是先把 `agent_tasks` runtime 真接管。
- `task_models`、event manager / streaming、tool runtime、core state / executor 是当前主线的一阶依赖。
- ACP SDK 接入不等于 ACP wire cutover；协议 adapter 必须先内聚在 Rust runtime 边界内。

## 当前执行顺序

建议按以下顺序推进当前主线：

1. Contract Freeze / Ownership Ledger
   - 冻结现有 `agent_tasks` / frontend-visible contract
   - 明确当前 live 状态是 Rust route + synthetic runtime，而不是 Python runtime 真执行
2. Runtime Core + ACP Adapter Boundary
   - 在 `backend/src/runtime/*` 下建立本地 runtime 模块与 ACP adapter 边界
3. Real Start / Stream / Cancel Lifecycle
   - 先移除 immediate-complete，再做 live + replayable stream
4. Real Artifact Projection
   - 让 findings / tree / checkpoints / report 来自真实 runtime
5. Capability Mapping
   - 把 `skills` / prompt-skill runtime 对齐到内部 ACP-aligned capability 表示
6. First Real Product Flow
   - 落一条真实 Rust-owned `agent_tasks` 真路径

## 主线之后的剩余顺序

在 `agent_tasks` runtime 真接管之后，再按下面顺序继续扫尾：

1. Event Manager / Streaming cluster
2. ORM / Task Models
3. Tool Base + Runtime Coordinator
4. Queue / Recon / File / Code Analysis Tools
5. Flow / AST Pipeline
6. Agent 框架 + 类型实现
7. Prompts / Skills / Memory / Logic

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
- 不要把 ACP SDK 接入误判成“前端现在就该改讲 ACP”；当前主线先做内部 runtime ownership。
