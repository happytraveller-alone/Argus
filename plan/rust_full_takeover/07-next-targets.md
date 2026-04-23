# Next Targets

> 最后更新：2026-04-23

## 当前阶段判断

Rust 已完成 Phase A-C（基础设施 + DB + 路由 + 共享服务），Phase D 大部分完成（runtime 计算内核全部 Rust 化，Python 仅保留 subprocess bridge 调用层）。

剩余工作集中在 Phase E（Agent 智能层）和 Phase F（最终收口）。

当前主线已明确为：**ACP + Rust runtime for `agent_tasks`**。

## Phase E：Agent / Tool Runtime（主战场）

Python 66 个文件全部集中在 `app/services/agent/`，构成完整的 LLM 驱动审计 Agent 系统。这是最大也是最复杂的接管目标。

### 当前主线切片顺序

1. **Contract Freeze / Ownership Ledger**
   - 冻结现有 `agent_tasks` / frontend-visible contract
2. **Runtime Core + ACP Adapter Boundary**
   - 在 Rust 内部建立 runtime 状态机与 ACP adapter
3. **Real Start / Stream / Cancel Lifecycle**
   - 先去掉 immediate-complete，再做 live + replayable stream
4. **Real Artifact Projection**
   - findings / tree / checkpoints / report 改为真实 runtime 投影
5. **Capability Mapping**
   - 把 `skills` / prompt-skill runtime 对齐到内部 ACP-aligned capability 表示
6. **First Real Product Flow**
   - 落一条真实 Rust-owned `agent_tasks` 真路径

### 关键依赖

- `task_models`、event manager / streaming、tool runtime、core state / executor 是当前主线的一阶依赖。
- Agent 框架依赖几乎所有其他模块，仍不适合一上来全量接管。
- Flow/AST pipeline 已有 Rust bridge，Python 层主要是胶水，可在 runtime core 稳定后继续收口。
- ACP 官方 Rust SDK 只负责降低协议/lifecycle 建模成本，不替代产品 contract projection。

### 主线之后的剩余顺序

在 `agent_tasks` runtime 真接管之后，再按下面顺序继续扫尾：

1. Event Manager / Streaming cluster
2. ORM / Task Models
3. Tool Base + Runtime Coordinator
4. Queue / Recon / File / Code Analysis Tools
5. Flow / AST Pipeline
6. Agent 框架 + 类型实现
7. Prompts / Skills / Memory / Logic

## Phase F：最终收口

- `scripts/flow_parser_runner.py` — 需要 Rust 化或确认为永久保留的外部脚本
- `scripts/dev-entrypoint.sh` — 开发环境入口，非 Python
- 清空所有 `__init__.py` 空壳
- 删除 `backend_old/tests/` 剩余测试（随对应模块一起退役）
