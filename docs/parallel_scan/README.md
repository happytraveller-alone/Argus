# 并行扫描架构文档索引

## 阅读定位

- **文档类型**：Explanation 索引。
- **目标读者**：准备理解、评审或实施并行扫描 Phase 1 改造的开发者。
- **阅读目标**：把这组文档分成“认知层”“实施层”“附录层”三层来读，避免把现状、Phase 1 决策和未来目标态继续混在一起。
- **建议前置**：先读 [../architecture.md](../architecture.md) 和 [../agentic_scan_core/workflow_overview.md](../agentic_scan_core/workflow_overview.md) 建立主线认知。
- **本文不覆盖**：数据库逐字段设计、最终部署拓扑、Redis 键结构、HTTP/RPC 线协议。

## 这组文档现在怎么用

本目录中的文档已经按三层职责重组：

1. **认知层（Explanation）**
   作用是帮助开发者看懂当前真实拓扑、Phase 1 为什么这样收口、以及未来目标态要解决什么问题。
2. **实施层（Reference / 实施规格）**
   作用是让开发者可以直接照着改代码，不再自己脑补接口名、迁移顺序和验收标准。
3. **附录层（Appendix Explanation）**
   作用是保留与本轮改造相关、但不属于核心实施规范的补充说明。

阅读时请默认遵守下面这条规则：

- 认知层负责回答“为什么”。
- 实施层负责回答“具体怎么改”。
- 如果认知层与实施层出现表述粒度差异，以实施层为准。

## 两条阅读路径

### 路径 A：先理解现状和目标态

适合第一次接手并行扫描改造的开发者。

1. [智能审计并行化拓扑总览](./topology-overview.md)
2. [Phase 1 边界收口范围说明](./phase1-boundary-scope.md)
3. [Control Plane 与 Execution Plane 边界说明](./control-plane-execution-plane-boundary.md)
4. [Redis、DB、Workspace 与 Worker 交互时序](./redis-db-workspace-worker-sequence.md)

### 路径 B：直接进入 Phase 1 实施

适合已经理解主流程、现在要改代码的开发者。

1. [Phase 1 实施总规格](./phase1-implementation-spec.md)
2. [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)
3. [Queue Port 实施规格](./queue-port-spec.md)
4. [Execution Contracts 实施规格](./execution-contracts-spec.md)

## 认知层文档

### 1. `topology-overview.md`

回答：

- 当前真实执行链路到底长什么样？
- 哪些环节已经并行，哪些环节仍然强依赖单进程对象图？
- 为什么 Phase 1 先收口边界，而不是直接拆多个 worker / service？

对应实施文档：

- [Phase 1 实施总规格](./phase1-implementation-spec.md)
- [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)

### 2. `phase1-boundary-scope.md`

回答：

- 本轮必须做什么，明确不做什么？
- 哪些内容这轮就要定型，哪些内容必须延后？
- 交付顺序为什么是 runtime -> queue -> store -> workspace -> contract？

对应实施文档：

- [Phase 1 实施总规格](./phase1-implementation-spec.md)

### 3. `control-plane-execution-plane-boundary.md`

回答：

- 哪些职责必须留在 backend？
- 哪些职责属于 execution plane，但这轮只先抽接口不拆进程？
- `TaskRuntimeRegistry`、`TaskControlPlanePort`、`FindingStorePort` 这些名字在 Phase 1 中到底扮演什么角色？

对应实施文档：

- [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)
- [Execution Contracts 实施规格](./execution-contracts-spec.md)

### 4. `redis-db-workspace-worker-sequence.md`

回答：

- 未来双平面模型中的参与者如何协作？
- 为什么 Redis 负责调度、DB 负责真相、Workspace 负责执行上下文？
- Phase 1 在不真正上 Redis worker 的情况下，应该先把哪些语义在进程内定型？

对应实施文档：

- [Queue Port 实施规格](./queue-port-spec.md)
- [Execution Contracts 实施规格](./execution-contracts-spec.md)

## 实施层文档

### 1. `phase1-implementation-spec.md`

这是 Phase 1 的总规格。它固定：

- 目标与非目标
- 当前代码锚点
- 交付顺序
- 影响范围
- 外部接口不变约束
- 实施验收矩阵
- 风险与回滚边界

### 2. `runtime-control-plane-spec.md`

这是 runtime/control plane 的规范入口。它固定：

- `TaskRuntimeRegistry`
- `TaskControlPlanePort`
- `_running_*` / `_cancelled_tasks` 到新边界的替换关系
- 取消、SSE、终态收敛、运行态查询的迁移方式

### 3. `queue-port-spec.md`

这是 queue 契约的规范入口。它固定：

- `QueuePort`
- `QueueClaim`
- `publish / claim / ack / retry / extend_lease` 等统一术语
- 三类现有队列到统一契约的映射关系

### 4. `execution-contracts-spec.md`

这是 execution side 输入输出契约的规范入口。它固定：

- `WorkspaceRef`
- `SnapshotRef`
- `ArtifactRef`
- `WorkspaceResolver`
- `FindingStorePort`
- `PhaseRunnerInput`
- `PhaseRunnerResult`
- `PhaseResultPort`

## 附录层文档

### `browser-validation-page.md`

这是附录，不是实施规范。它只保留：

- 历史上的浏览器验证思路
- 为什么当时需要最小验证页
- 如果后续要正式化该夹具，还需要补哪些仓库资产和暴露方式

它**不**属于 Phase 1 核心实施阅读链路。

## 文档维护规则

后续维护时，请按下面的规则更新：

- 解释“现状 / 原因 / 取舍”时，改认知层文档。
- 固定接口名、字段、迁移顺序、验收标准时，改实施层文档。
- 记录一次性验证思路或历史背景时，改附录层文档。
- 不要把“未来目标态”直接写成“当前已存在的实现事实”。
- 不要把“Phase 1 决策”只写成口号，必须在实施层文档中给出精确接口或迁移表。
