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

当前已跨过 A-C 的主体迁移，正在 D / E 两条主线并行推进，F 仍未到收尾条件。

现阶段的判断标准很简单：

- 还能独立承担 runtime 行为的 Python 文件，优先级高于 package shell / namespace 清理
- 能直接切换 source of truth 的 slice，优先级高于纯 helper 收纳
- 未进入 `backend_old/app == 0` 之前，不得宣称“Python 已基本完成退役”

## 当前执行顺序

建议按下面顺序继续推进：

1. scanner / queue / runner retained runtime
2. agent orchestration / state / payload
3. flow / logic retained runtime
4. tool runtime + support glue
5. knowledge + llm + llm_rule
6. models / db / alembic / scripts / release preflight 最终门

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
