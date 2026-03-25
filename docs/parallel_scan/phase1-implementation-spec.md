# Phase 1 实施总规格

## 阅读定位

- **文档类型**：Reference（实施规格）。
- **目标读者**：准备在当前仓库内落地并行扫描 Phase 1 边界收口的后端开发者。
- **阅读目标**：在不改变外部接口形态、不引入远端 worker 的前提下，把 runtime、queue、finding persistence、workspace、phase contract 五层边界一次性定型。
- **建议前置**：先读 [./phase1-boundary-scope.md](./phase1-boundary-scope.md) 理解为什么这样收口，再回到本文实施。
- **本文不覆盖**：Redis 真接线、跨进程协议、对象存储、前端页面改版。

## 使用规则

本文中的术语按下面三种状态解释：

- **当前已存在**：仓库中已经存在并参与主链路的实现。
- **Phase 1 新引入**：这轮必须新增或收口的接口、类型或模块边界。
- **明确延后**：本轮不做，后续阶段再讨论。

如果说明文档与本文出现粒度差异，以本文为准。

## 1. 目标与非目标

### 1.1 本轮目标

本轮必须同时满足以下 5 个目标：

1. 让 backend 内部只有一个明确的 runtime 真相入口，而不是继续散落访问 `_running_*` 与 `_cancelled_tasks`。
2. 让三类队列先收口到统一 `QueuePort` 语义，即使底层仍然是 in-memory adapter。
3. 让 verification / report 阶段不再依赖工具私有 `_save_callback` / `_update_callback` 作为正式边界。
4. 让执行侧拿到的是 `WorkspaceRef` / `SnapshotRef` / `ArtifactRef`，而不是继续裸传 `project_root`。
5. 让 phase 输入输出形成固定契约，以便下一阶段再外提 execution plane。

### 1.2 本轮非目标

本轮明确不做下面这些事情：

- 不把 Redis 接入 agent 主执行链路。
- 不把 `recon / analysis / verification / report` 拆成独立进程或独立服务。
- 不定义远程 `TaskControlPlane` HTTP / RPC 协议。
- 不让 worker 直接写 DB。
- 不把 workspace 升级成对象存储、manifest 服务或远端 artifact store。
- 不修改前端任务创建、SSE 消费、状态查询、结果查询的外部接口形态。

## 2. 当前代码锚点总表

下表中的文件是 Phase 1 必须直接对齐的当前代码锚点。

| 代码锚点 | 当前角色 | Phase 1 必须完成的收口 |
| --- | --- | --- |
| `backend/app/api/v1/endpoints/agent_tasks_execution.py` | 主执行入口；初始化 event manager、队列、工具、orchestrator | 改成通过 `TaskRuntimeRegistry`、`TaskControlPlanePort`、`QueuePort`、`FindingStorePort`、`WorkspaceResolver` 进行装配 |
| `backend/app/api/v1/endpoints/agent_tasks_runtime.py` | 保存 `_running_*`、`_cancelled_tasks`、终态收敛逻辑 | 抽成 `TaskRuntimeRegistry` 与 `TaskControlPlanePort` 的本地实现入口 |
| `backend/app/api/v1/endpoints/agent_tasks_routes_tasks.py` | 取消任务、SSE 流接口 | 不改外部路由形态，但内部改为通过 registry / control plane 取运行态 |
| `backend/app/api/v1/endpoints/agent_tasks_routes_results.py` | 队列状态、progress、结果查询 | 不改外部返回形态，但内部改为通过 `QueuePort` / registry 查询 |
| `backend/app/services/agent/workflow/workflow_orchestrator.py` | workflow 驱动 orchestrator | 不再假定具体 queue 类方法名；改依赖统一 queue / phase result 契约 |
| `backend/app/services/agent/workflow/engine.py` | 阶段推进和队列消费 | 从 `dequeue*` 迁到 `claim / ack / retry` 语义 |
| `backend/app/services/agent/workflow/parallel_executor.py` | 并行 worker 克隆和阶段执行 | 输入改为 `PhaseRunnerInput`，结果改为 `PhaseRunnerResult` |
| `backend/app/services/agent/tools/verification_result_tools.py` | verification/report 持久化工具 | 用 `FindingStorePort` 替代私有 `_save_callback` / `_update_callback` |
| `backend/app/services/agent/vulnerability_queue.py` | 当前 vuln queue 实现 | 通过 adapter 暴露统一 `QueuePort` 语义 |
| `backend/app/services/agent/recon_risk_queue.py` | 当前 recon queue 实现 | 通过 adapter 暴露统一 `QueuePort` 语义 |
| `backend/app/services/agent/business_logic_risk_queue.py` | 当前业务逻辑 risk queue 实现 | 通过 adapter 暴露统一 `QueuePort` 语义 |
| `backend/app/api/v1/endpoints/static_tasks_shared.py` | 当前本地 scan workspace 辅助函数 | 作为 `WorkspaceResolver` 的本地路径语义来源 |
| `backend/app/services/scanner_runner.py` | 当前 scanner 容器挂载 `/scan` 的执行器 | 作为 `ArtifactRef` / workspace 映射的执行侧约束来源 |

## 3. Phase 1 交付顺序

交付顺序必须固定为下面 5 步；后一步不得跳过前一步直接实现。

### 第 1 步：收口 runtime 真相源

交付物：

- `TaskRuntimeRegistry`
- `TaskControlPlanePort`

完成标准：

- 新代码不得再直接读写 `_running_*` 与 `_cancelled_tasks`。
- 取消、SSE、运行态查询、队列查询都能通过 registry / control plane 完成。
- `_finalize_task_terminal_state(...)` 的行为被 control plane 接住，而不是继续作为裸 helper 散落调用。

### 第 2 步：统一 QueuePort

交付物：

- `QueuePort`
- `QueueClaim`
- in-memory queue adapter
- 兼容现有三类队列的 adapter 映射

完成标准：

- workflow / executor 内部以 `publish / claim / ack / retry / extend_lease` 为主语义。
- route 层仍保留现有对外接口，但内部查询改走统一 queue port。
- 新增代码不再直接依赖 `enqueue`、`dequeue`、`enqueue_finding`、`dequeue_finding`。

### 第 3 步：替换 FindingStorePort

交付物：

- `FindingStorePort`
- verification / report 持久化适配层

完成标准：

- `SaveVerificationResultTool` 和 `UpdateVulnerabilityFindingTool` 不再把私有 callback 当正式边界。
- verification 保存与 report 修正都通过统一 store port 落地。

### 第 4 步：引入 WorkspaceResolver

交付物：

- `WorkspaceRef`
- `SnapshotRef`
- `ArtifactRef`
- `WorkspaceResolver`

完成标准：

- phase input 不再裸传 `project_root` 作为唯一上下文定位方式。
- resolver 能把 ref 映射到当前 `<SCAN_WORKSPACE_ROOT>/<scan_type>/<task_id>/{project,output,logs,meta}` 布局。
- retry 在同一 task 内复用同一 `WorkspaceRef`。

### 第 5 步：定型 phase 输入输出契约

交付物：

- `PhaseRunnerInput`
- `PhaseRunnerResult`
- `PhaseResultPort`

完成标准：

- `ParallelPhaseExecutor` 组装 worker 输入时走固定字段，而不是继续堆 ad hoc dict。
- control plane 收口 phase result；worker 只提交结构化结果，不直接裁决全局 finding 真相。

## 4. 影响文件与模块范围

### 4.1 必改的现有模块

- `backend/app/api/v1/endpoints/agent_tasks_execution.py`
- `backend/app/api/v1/endpoints/agent_tasks_runtime.py`
- `backend/app/api/v1/endpoints/agent_tasks_routes_tasks.py`
- `backend/app/api/v1/endpoints/agent_tasks_routes_results.py`
- `backend/app/services/agent/workflow/workflow_orchestrator.py`
- `backend/app/services/agent/workflow/engine.py`
- `backend/app/services/agent/workflow/parallel_executor.py`
- `backend/app/services/agent/tools/verification_result_tools.py`
- `backend/app/services/agent/vulnerability_queue.py`
- `backend/app/services/agent/recon_risk_queue.py`
- `backend/app/services/agent/business_logic_risk_queue.py`

### 4.2 规范化新增模块的默认落点

为避免实现时重复讨论文件放哪里，Phase 1 默认按下面的目录布局新增内部边界：

- `backend/app/services/agent/ports/`
  - `task_control_plane_port.py`
  - `queue_port.py`
  - `workspace_resolver.py`
  - `finding_store_port.py`
  - `phase_result_port.py`
  - `phase_runner_contracts.py`
- `backend/app/services/agent/runtime/`
  - `task_runtime_registry.py`
  - `local_task_control_plane.py`
  - `in_memory_queue_port.py`
  - `local_workspace_resolver.py`
  - `db_finding_store.py`
  - `local_phase_result_port.py`

如果实现者需要调整文件名，可以调整；但接口类型名必须保持与本文一致，不得自定义新名词替换。

## 5. 外部接口不变约束

Phase 1 期间，下面这些对外行为必须保持兼容：

- 任务创建接口不改。
- SSE 路由不改。
- 任务状态查询接口形态不改。
- 结果查询接口形态不改。
- progress 接口形态不改。
- 现有 `AgentFinding` 与 `AgentEvent` 的产品层含义不改。

允许变化的只有 backend 内部装配方式、内部接口边界和内部运行态访问路径。

## 6. 实施验收矩阵

| 验收项 | 必须满足的条件 |
| --- | --- |
| Runtime 真相源 | 外部 route 和执行主链路都不再直接依赖 `_running_*` / `_cancelled_tasks` |
| Control plane | 取消、状态更新、事件发射、终态收敛都有统一内部入口 |
| Queue 契约 | 三类队列在主链路上表现为同一组方法语义；统计输出类型统一 |
| Finding persistence | verification / report 的正式边界是 `FindingStorePort`，不是工具私有 callback |
| Workspace 契约 | phase 输入包含 `WorkspaceRef` / `SnapshotRef`；resolver 可映射到当前本地目录布局 |
| Phase contract | worker 输入输出字段固定；control plane 根据 `PhaseRunnerResult` 推进状态 |
| 外部兼容性 | 现有前端和对外 API 无需随 Phase 1 同步改动 |
| 非目标收口 | 没有把 Redis、远端 worker、对象存储、远程 control plane 一起拉进本轮 |

## 7. 风险与回滚边界

### 7.1 主要风险

- runtime 新边界引入后，如果 route 仍绕过 registry 读旧全局表，会形成双真相源。
- queue 迁移如果只做方法重命名、不补 lease/ack/retry 语义，会把旧问题换个名字保留下来。
- `FindingStorePort` 如果仍透传私有 callback，只是“换壳不换边界”。
- workspace 如果只新增 `workspace_ref` 字段，但调用方仍以裸 `project_root` 为准，执行面不会真正去耦。

### 7.2 回滚边界

Phase 1 回滚仅允许回滚内部装配，不允许破坏外部接口：

- 如果新的 registry / control plane 方案失败，允许临时回退到旧 `_running_*` 实现，但必须通过兼容层，而不是恢复散落调用。
- 如果新的 queue port 未完成全链路迁移，允许短期保留 legacy shim，但 shim 只作为过渡层，不得新增调用点。
- 如果 `WorkspaceRef` / `PhaseRunnerInput` 尚未完全落地，允许在本地 adapter 内同时保留解析出的 `project_root`，但不得把它重新定义为正式规范字段。

## 8. 关联文档

- [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)
- [Queue Port 实施规格](./queue-port-spec.md)
- [Execution Contracts 实施规格](./execution-contracts-spec.md)
- [Phase 1 边界收口范围说明](./phase1-boundary-scope.md)
