# Control Plane 与 Execution Plane 边界说明

## 阅读定位

- **文档类型**：Explanation。
- **目标读者**：准备设计并行扫描服务边界、任务控制面和执行面的开发者。
- **阅读目标**：明确哪些职责应该留在 backend，哪些职责属于 execution plane，以及本轮必须先抽出来的内部接口层。
- **建议前置**：先读 [./topology-overview.md](./topology-overview.md) 理解当前拓扑，再读本文。
- **本文不覆盖**：远程协议选型、最终部署拓扑、服务发现方案。

## 文档标注约定

- **[现状事实]**：当前代码已经存在的职责分布。
- **[Phase 1 决策]**：这轮必须落成的内部边界。
- **[未来目标态]**：边界稳定后才能讨论的下一阶段外提。

真正编码时，请以 [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md) 和 [Execution Contracts 实施规格](./execution-contracts-spec.md) 为准。

## 先记住三条判断

- **[Phase 1 决策]** `control plane` 的核心职责是维护全局真相，而不是执行具体 phase。
- **[Phase 1 决策]** `execution plane` 的核心职责是执行 phase、调用工具、产出结果，而不是自己决定任务全局生命周期。
- **[现状事实]** 当前系统最大的问题不是“平面没分开”，而是“职责已经混在一起，但代码仍按单进程对象图组织”。

## 1. 为什么要先画这条边界

**[现状事实]**

今天的 backend 进程里同时混着下面这些能力：

- 任务创建与状态机推进
- 事件流与 SSE 输出
- queue 初始化与消费
- 工具集装配
- 子智能体执行
- finding 持久化 callback

这意味着当我们讨论“是否把智能体拆成独立 worker”时，实际上不是在拆“智能体”，而是在拆一组互相共享内部对象的职责。

因此更合理的第一步不是切容器，而是先问：

**哪些职责本质上属于 control plane，哪些职责本质上属于 execution plane？**

## 2. 当前代码已经给出的证据

### 2.1 control plane 相关职责目前散在 backend 各处

**[现状事实]**

当前 runtime / control 相关职责散落在：

- `agent_tasks_execution.py`
- `agent_tasks_runtime.py`
- `agent_tasks_routes_tasks.py`
- `agent_tasks_routes_results.py`

表现为：

- `_running_*` 与 `_cancelled_tasks` 保存运行态
- `cancel_agent_task(...)` 手工组合取消逻辑
- `stream_agent_with_thinking(...)` 直接读 `_running_event_managers`
- queue status / peek / clear route 直接读 `_running_*queue_services`

### 2.2 execution 相关职责目前主要在 workflow / executor / tools

**[现状事实]**

执行侧职责主要散在：

- `workflow/workflow_orchestrator.py`
- `workflow/engine.py`
- `workflow/parallel_executor.py`
- `tools/verification_result_tools.py`
- 具体 queue 类与工具类

但它们并没有通过正式 port 协作，而是经常直接访问彼此的私有状态。

## 3. Control Plane 在 Phase 1 中必须负责什么

### 3.1 任务生命周期

**[Phase 1 决策]**

control plane 必须拥有任务生命周期的唯一 authoritative view，包括：

- 创建任务
- 更新状态
- 切换阶段
- 取消任务
- 终态收敛

### 3.2 runtime 真相入口

**[Phase 1 决策]**

control plane 必须通过：

- `TaskRuntimeRegistry`
- `TaskControlPlanePort`

来统一接住运行态，而不是继续让调用方直接访问 `_running_*` 与 `_cancelled_tasks`。

### 3.3 事件入口与 SSE 对外出口

**[Phase 1 决策]**

worker / phase runner 只负责提交结构化事件；control plane 继续负责：

- 事件归档
- SSE 对外输出
- 运行态事件路由

### 3.4 finding 最终收口

**[Phase 1 决策]**

verification / report 可以提交结构化结果，但最终的 finding patch、幂等和最终写入仍由 control plane 统一裁决。

## 4. Execution Plane 在 Phase 1 中必须负责什么

### 4.1 只负责执行和回传

**[Phase 1 决策]**

execution plane 的角色在本轮必须被限定为：

- 读取 `PhaseRunnerInput`
- 解析 `WorkspaceRef` / `SnapshotRef`
- 执行工具与 LLM 推理
- 生成 `PhaseRunnerResult`
- 通过 `PhaseResultPort` 回传

### 4.2 不负责全局生命周期裁决

**[Phase 1 决策]**

execution plane 不负责：

- 决定任务最终状态
- 决定下一阶段是否生成
- 直接写全局 finding 真相
- 直接对外发 SSE

## 5. 本轮必须先抽出的接口层

### 5.1 `TaskRuntimeRegistry`

**[Phase 1 新引入]**

这是 runtime 真相源。规范细节见 [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)。

### 5.2 `TaskControlPlanePort`

**[Phase 1 新引入]**

这是 backend 内部 control plane 边界。它不是远程 API，而是内部 service port。

### 5.3 `QueuePort`

**[Phase 1 新引入]**

这是 execution 与 queue 交接的统一语义层。规范细节见 [Queue Port 实施规格](./queue-port-spec.md)。

### 5.4 `WorkspaceRef / SnapshotRef / ArtifactRef / WorkspaceResolver`

**[Phase 1 新引入]**

这是 execution side 的上下文定位层。规范细节见 [Execution Contracts 实施规格](./execution-contracts-spec.md)。

### 5.5 `FindingStorePort`

**[Phase 1 新引入]**

这是替换私有 callback 注入模型的正式持久化边界。

### 5.6 `PhaseRunnerInput / PhaseRunnerResult / PhaseResultPort`

**[Phase 1 新引入]**

这是 execution plane 输入输出的正式契约层。

## 6. 本轮明确延后的边界讨论

下面这些内容要等 Phase 1 边界稳定以后再讨论：

- 是否把 control plane 做成远程 HTTP / RPC
- 是否把整条 workflow 外提成独立 worker
- 是否把 scanner executor、sandbox executor 单独服务化
- 是否继续细拆成 `recon-service`、`analysis-service`、`verification-service`

## 7. 一句话总结

这条边界的核心不是“把服务拆开”，而是：

**让 control plane 拥有全局真相，让 execution plane 只负责执行和回传。**
