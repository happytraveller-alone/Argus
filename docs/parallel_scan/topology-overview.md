# 智能扫描并行化拓扑总览

> 2026-04-18 更新：文中的 `business_logic_queue`、`InMemoryBusinessLogicRiskQueue` 等 Python runtime 术语属于历史拓扑描述，不再表示当前 live 主链。当前 authoritative 迁移状态以 `plan/rust_full_takeover/*` 为准；Rust 已承接现有对外 business-logic surface。

## 阅读定位

- **文档类型**：Explanation。
- **目标读者**：准备理解或改造智能扫描 / 混合扫描执行拓扑的开发者。
- **阅读目标**：看清当前真实执行链路、共享队列关系、关键耦合点，以及更现实的 Phase 1 演进顺序。
- **建议前置**：先读 [../agentic_scan_core/workflow_overview.md](../agentic_scan_core/workflow_overview.md) 建立主流程认知，再读本文。
- **本文不覆盖**：接口逐字段定义、数据库设计、最终部署拓扑。

## 文档标注约定

本文会显式区分三类信息：

- **[现状事实]**：当前仓库代码已经存在并参与主链路的实现。
- **[Phase 1 决策]**：本轮必须定型的边界或收口顺序。
- **[未来目标态]**：Phase 1 不做，但后续架构演进要对齐的方向。

如果你现在要真正改代码，请把本文与下面这些规格文档配合阅读：

- [Phase 1 实施总规格](./phase1-implementation-spec.md)
- [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)
- [Queue Port 实施规格](./queue-port-spec.md)
- [Execution Contracts 实施规格](./execution-contracts-spec.md)

## 先记住三条判断

- **[现状事实]** 当前主链路不是多个独立服务协作，而是单个 backend 进程内完成运行时装配。
- **[现状事实]** 当前真正的阻力不是“没有队列”，而是编排、状态、工具实例和持久化仍然以本地对象图为中心。
- **[Phase 1 决策]** 更现实的演进路线不是一步拆成 6 类 agent service，而是先收口内部边界，再逐层外提 execution plane。

## 1. 当前真实拓扑

### 1.1 运行入口

**[现状事实]**

当前智能扫描和混合扫描都从 `backend/app/api/v1/endpoints/agent_tasks_execution.py` 中的 `_execute_agent_task(task_id)` 进入。

这个入口在单个任务协程里完成整套装配：

- 创建 `EventManager`
- 初始化 3 类队列
- 初始化工具集合
- 创建 6 个子智能体
- 创建 `WorkflowOrchestratorAgent`
- 启动 `AuditWorkflowEngine`

因此，任务启动时拿到的不是“远端服务地址集合”，而是一组彼此持有引用的本地对象。

### 1.2 当前主链路

**[现状事实]**

从执行拓扑上看，当前有两条并存轨道：

- 常规代码安全轨：`RECON -> ANALYSIS -> VERIFICATION -> REPORT`
- 业务逻辑轨：`BUSINESS_LOGIC_RECON -> BUSINESS_LOGIC_ANALYSIS -> VERIFICATION -> REPORT`

两条轨道在验证前汇聚到同一个 `vuln_queue`，因此：

- `VERIFICATION` 是共享阶段
- `REPORT` 也是共享阶段

### 1.3 当前队列的位置

**[现状事实]**

当前队列不是“可有可无的缓存”，而是跨阶段交接边界：

- `recon_queue`：常规风险点权威输入源
- `business_logic_queue`：业务逻辑风险点权威输入源
- `vuln_queue`：待验证 finding 权威输入源

但当前主链路默认实例化的是：

- `InMemoryReconRiskQueue`
- `InMemoryBusinessLogicRiskQueue`
- `InMemoryVulnerabilityQueue`

仓库里虽然已经有 Redis 版本队列类，但它们 **还不是主链路能力**。

## 2. 当前已经具备什么并行能力

**[现状事实]**

“当前完全串行”并不准确。当前系统已经具备单进程内部的并发能力，核心体现在：

- `WorkflowOrchestratorAgent`
- `AuditWorkflowEngine`
- `ParallelPhaseExecutor`
- `WorkflowConfig` 中的并发 worker 配置

更准确的说法是：

**当前已经具备单进程内部的并发执行能力，但还没有形成可恢复、可外提、可替换的 execution plane 边界。**

## 3. 为什么现在不适合直接拆成多个独立容器

### 3.1 runtime 真相仍然是进程内全局表

**[现状事实]**

当前取消、SSE、运行态查询、队列查询都依赖 `agent_tasks_runtime.py` 里的模块级全局表，例如：

- `_running_tasks`
- `_running_queue_services`
- `_running_recon_queue_services`
- `_running_bl_queue_services`
- `_running_orchestrators`
- `_running_event_managers`
- `_cancelled_tasks`

### 3.2 orchestrator / workflow 仍然是对象图耦合

**[现状事实]**

`AuditWorkflowEngine` 与 `ParallelPhaseExecutor` 仍然直接读写 orchestrator 私有字段，例如：

- `_all_findings`
- `_agent_results`
- `_verified_queue_fingerprints`
- `_last_recon_risk_point`

这说明今天的系统边界还不是协议边界，而是对象图边界。

### 3.3 worker 仍然是进程内对象克隆

**[现状事实]**

`ParallelPhaseExecutor` 会克隆 worker agent，但它复用的仍然是：

- 同一个 `llm_service`
- 同一个 `tools`
- 同一个 `event_emitter`
- 同一个 `_mcp_runtime`
- 同一个取消回调链

因此当前 worker 不是“独立执行单元”，而是“共享工具集的并发会话”。

### 3.4 finding 持久化仍是 callback 注入

**[现状事实]**

verification / report 阶段的持久化仍依赖任务执行前注入的私有 callback：

- `save_verification_result`
- `update_vulnerability_finding`

这在单进程里能跑，但不是未来 execution plane 可复用的正式边界。

## 4. Phase 1 先收口什么

**[Phase 1 决策]**

Phase 1 先收口的不是“容器怎么拆”，而是下面 5 层边界：

1. runtime 真相入口
2. queue port
3. finding store port
4. workspace 引用层
5. phase 输入输出契约

对应实施文档分别是：

- [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)
- [Queue Port 实施规格](./queue-port-spec.md)
- [Execution Contracts 实施规格](./execution-contracts-spec.md)

## 5. 更合理的演进顺序

### 第一步：保留 backend 作为 control plane

**[Phase 1 决策]**

backend 继续承接：

- 任务创建
- 状态推进
- 取消与终态收敛
- 事件归档与 SSE
- finding 最终收口

### 第二步：先把内部边界定型

**[Phase 1 决策]**

本轮优先交付：

- `TaskRuntimeRegistry`
- `TaskControlPlanePort`
- `QueuePort`
- `FindingStorePort`
- `WorkspaceRef / SnapshotRef / ArtifactRef`
- `PhaseRunnerInput / PhaseRunnerResult / PhaseResultPort`

### 第三步：再考虑 execution plane 外提

**[未来目标态]**

真正拆 execution plane 的优先顺序应是：

1. 先拆 scanner / sandbox executor
2. 再拆整条 workflow worker
3. 最后才考虑更细粒度的 phase / agent service

## 6. 实现者应直接跳转阅读什么

如果你下一步要改代码，请先按下面的顺序读：

1. 当前入口与运行态：
   - `backend/app/api/v1/endpoints/agent_tasks_execution.py`
   - `backend/app/api/v1/endpoints/agent_tasks_runtime.py`
2. 当前 workflow 与并发执行：
   - `backend/app/services/agent/workflow/workflow_orchestrator.py`
   - `backend/app/services/agent/workflow/engine.py`
   - `backend/app/services/agent/workflow/parallel_executor.py`
3. 当前队列与持久化工具：
   - `backend/app/services/agent/vulnerability_queue.py`
   - `backend/app/services/agent/recon_risk_queue.py`
   - `backend/app/services/agent/business_logic_risk_queue.py`
   - `backend/app/services/agent/tools/verification_result_tools.py`
4. 对应规格文档：
   - [Phase 1 实施总规格](./phase1-implementation-spec.md)
   - [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)
   - [Queue Port 实施规格](./queue-port-spec.md)
   - [Execution Contracts 实施规格](./execution-contracts-spec.md)

## 7. 一句话总结

这轮并行扫描改造的核心不是“把服务拆出去”，而是：

**先把今天只能在单进程对象图里成立的隐式边界，改造成未来可迁移的显式边界。**
