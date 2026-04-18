# Phase 1 边界收口范围说明

> 2026-04-18 更新：本文提到的 `business_logic_*` Python queue / agent / tool 设计仅代表历史 Phase 1 方案，不再表示当前 live runtime ownership。当前 authoritative 迁移状态以 `plan/rust_full_takeover/*` 为准；对外 business-logic route / skill surface 已由 Rust 承接。

## 阅读定位

- **文档类型**：Explanation。
- **目标读者**：准备把并行扫描改造计划真正落地到当前仓库的开发者。
- **阅读目标**：明确这轮改造到底做什么、不做什么，以及为什么必须先这样收口。
- **建议前置**：先读 [./topology-overview.md](./topology-overview.md) 理解现状，再读本文锁定 Phase 1 范围。
- **本文不覆盖**：具体字段定义、完整类图、最终部署拓扑。

## 文档标注约定

- **[现状事实]**：当前代码已经存在的实现现实。
- **[Phase 1 决策]**：这轮必须落地、不能继续模糊的边界。
- **[未来目标态]**：这轮明确延后，只作为后续方向。

真正执行时，请以 [Phase 1 实施总规格](./phase1-implementation-spec.md) 为准。

## 先记住四条判断

- **[Phase 1 决策]** Phase 1 不是上分布式 worker，而是先把边界从单进程对象图里拔出来。
- **[Phase 1 决策]** Queue Port 这轮就按未来可恢复任务模型定型，但先只交付 in-memory adapter。
- **[Phase 1 决策]** Workspace 这轮只做逻辑引用层，不做对象存储、manifest 服务或远端 artifact store。
- **[Phase 1 决策]** backend 继续是唯一 control plane，所有对外 SSE / 状态查询 / finding 真相都不外移。

## 1. 为什么要先单独锁这一层

**[现状事实]**

当前文档和代码最容易让实现跑偏的地方，是三种粒度混在一起：

1. 已存在的实现事实
2. 本轮应该落地的边界收口
3. 后续双平面 / 多 worker / 多服务的目标态

如果不先把这三层拆开，开发时就会发生两种偏差：

- 把目标态当现状，误以为 Redis queue、worker claim、workspace ref 已经主链路可用
- 把 Phase 1 做成过度设计，一次性想把 worker、调度、状态恢复全做完

本文的作用，就是给实现者划清施工围栏。

## 2. 当前代码里的硬约束

### 2.1 主执行入口仍然硬编码使用内存队列

**[现状事实]**

`_execute_agent_task(task_id)` 直接实例化：

- `InMemoryVulnerabilityQueue`
- `InMemoryReconRiskQueue`
- `InMemoryBusinessLogicRiskQueue`

这意味着当前并没有一个已经接通主链路的可替换 queue port。

### 2.2 runtime 真相仍然散落在进程内全局表

**[现状事实]**

取消、SSE、运行态查询、队列查询都依赖：

- `_running_*`
- `_cancelled_tasks`

所以今天真正要先收口的，不是“容器怎么拆”，而是“运行态权威入口在哪里”。

### 2.3 workflow / executor 仍然直读直写私有状态

**[现状事实]**

当前 workflow 层仍直接依赖 orchestrator 私有字段，例如：

- `_all_findings`
- `_agent_results`
- `_verified_queue_fingerprints`
- `_last_recon_risk_point`

这说明当前还没有形成稳定的 phase contract。

### 2.4 持久化仍然是私有 callback 注入

**[现状事实]**

verification / report 阶段仍然依赖：

- `save_verification_result`
- `update_vulnerability_finding`

背后的私有 callback 注入来完成持久化，这不是未来 execution plane 可迁移的正式接口。

## 3. 本轮必须交付的内容

### 3.1 先做边界，不拆 worker

**[Phase 1 决策]**

本轮必须先收口 backend 内部边界，不得把 `recon / analysis / verification / report` 拆成独立进程或独立服务。

### 3.2 Queue Port 直接按租约语义定型

**[Phase 1 决策]**

即使底层仍然是 in-memory adapter，本轮也必须先把 queue 语义定为：

- `publish`
- `publish_batch`
- `claim`
- `ack`
- `retry`
- `extend_lease`
- `peek`
- `stats`
- `clear`
- `dead_letter`

规范细节见 [Queue Port 实施规格](./queue-port-spec.md)。

### 3.3 Workspace 必须升成逻辑引用层

**[Phase 1 决策]**

这轮不能继续把裸 `project_root` 当执行侧唯一上下文。必须引入：

- `WorkspaceRef`
- `SnapshotRef`
- `ArtifactRef`
- `WorkspaceResolver`

规范细节见 [Execution Contracts 实施规格](./execution-contracts-spec.md)。

### 3.4 Finding 持久化必须改成正式 store port

**[Phase 1 决策]**

这轮必须把 verification / report 持久化收口成：

- `FindingStorePort`

而不是继续把工具私有 callback 当正式边界。

### 3.5 Control plane 必须先收口成 backend 内部服务

**[Phase 1 决策]**

这轮必须形成：

- `TaskRuntimeRegistry`
- `TaskControlPlanePort`

但它们首先是 backend 内部稳定边界，不是远程 API。

规范细节见 [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)。

## 4. 本轮明确不做的事

以下内容在本轮一律不进入实施：

- 不真正接入 Redis 调度主链路
- 不把整条 workflow 外提成独立 worker 进程
- 不按 phase 或 agent 粒度拆服务
- 不让 worker 直接写 DB
- 不把 workspace 做成完整 manifest / artifact store
- 不改前端对 SSE、任务状态查询、结果查询的外部接口形态

这些事情不是不重要，而是必须建立在本轮边界已稳定的前提上。

## 5. 推荐交付顺序

**[Phase 1 决策]**

本轮交付顺序必须固定为：

1. 先收口 runtime 真相源
2. 再统一 Queue Port
3. 再替换 Finding Store Port
4. 再引入 Workspace Resolver
5. 最后补 Phase Runner Contract

每一步的完成标准和回滚边界见 [Phase 1 实施总规格](./phase1-implementation-spec.md)。

## 6. 这轮完成后，系统才算具备什么前提

**[Phase 1 决策]**

只有完成本轮，系统才算具备下面这些前提：

- backend 内部有单一的 runtime / control plane 入口
- queue 语义不再绑死在 `pop` 风格方法名上
- finding 持久化入口已经正式化
- workspace 已经有逻辑引用层，而不是到处裸传路径
- phase 输入输出可以被独立 worker 复用

## 7. 一句话总结

Phase 1 的核心不是“把并行扫描拆出去”，而是：

**先把今天只能在单进程对象图里成立的隐式边界，改造成未来可迁移的显式边界。**
