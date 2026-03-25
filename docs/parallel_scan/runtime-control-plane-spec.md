# Runtime / Control Plane 实施规格

## 阅读定位

- **文档类型**：Reference（实施规格）。
- **目标读者**：准备把 runtime 真相、取消、SSE、终态收敛和运行态查询从模块级全局表收口成内部服务边界的开发者。
- **阅读目标**：固定 `TaskRuntimeRegistry` 与 `TaskControlPlanePort` 的职责、最小方法集、迁移表和非目标。
- **建议前置**：先读 [./control-plane-execution-plane-boundary.md](./control-plane-execution-plane-boundary.md) 理解边界，再读本文编码。
- **本文不覆盖**：远程 control plane 协议、跨进程租约心跳、前端 SSE UI。

## 1. 规范状态

- **当前已存在**
  - `_running_tasks`
  - `_running_queue_services`
  - `_running_recon_queue_services`
  - `_running_bl_queue_services`
  - `_running_orchestrators`
  - `_running_event_managers`
  - `_cancelled_tasks`
  - `_finalize_task_terminal_state(...)`
- **Phase 1 新引入**
  - `TaskRuntimeRegistry`
  - `TaskControlPlanePort`
- **明确延后**
  - 远程 `TaskControlPlane` API
  - 跨进程 heartbeat 协议
  - 多 backend 实例共享 runtime state

## 2. 当前代码证据

下面这些现有访问点必须被 Phase 1 新边界接住。

| 当前访问点 | 当前行为 | Phase 1 替换目标 |
| --- | --- | --- |
| `agent_tasks_execution.py` | 直接写 `_running_event_managers`、`_running_queue_services`、`_running_orchestrators`、`_running_tasks` | `TaskRuntimeRegistry.register_task(...)`、`bind_*` |
| `agent_tasks_execution.py` | 多处调用 `is_task_cancelled(task_id)` | `TaskControlPlanePort.cancel_task(...)` / `TaskRuntimeRegistry.is_cancelled(...)` |
| `agent_tasks_routes_tasks.py` 的 `cancel_agent_task(...)` | 直接写 `_cancelled_tasks`，并从 `_running_*` 取 runner / orchestrator | `TaskControlPlanePort.cancel_task(...)` |
| `agent_tasks_routes_tasks.py` 的 `stream_agent_with_thinking(...)` | 直接读 `_running_event_managers` 获取内存事件流 | `TaskRuntimeRegistry.snapshot(...)` 后取当前 event manager ref |
| `agent_tasks_routes_results.py` | 直接读 `_running_*queue_services` 提供 queue status / peek / clear | `TaskRuntimeRegistry.snapshot(...)` 后取 queue bundle |
| `agent_tasks_access.py` | 直接读 `_running_orchestrators` 做运行态访问 | `TaskRuntimeRegistry.snapshot(...)` |
| `agent_tasks_runtime.py` 中 `_finalize_task_terminal_state(...)` | 统一做终态收敛 | `TaskControlPlanePort.finalize_terminal_state(...)` |

## 3. Phase 1 新接口

## 3.1 `TaskRuntimeRegistry`

`TaskRuntimeRegistry` 是 **Phase 1 唯一 runtime 真相入口**。它是 backend 内部服务，不对外暴露 HTTP / RPC。

最小方法集固定为：

```python
class TaskRuntimeRegistry:
    def register_task(self, task_id: str, *, asyncio_task: object | None = None) -> None: ...
    def bind_orchestrator(self, task_id: str, orchestrator: object) -> None: ...
    def bind_event_manager(self, task_id: str, event_manager: object) -> None: ...
    def bind_queue_bundle(self, task_id: str, queue_bundle: dict[str, object]) -> None: ...
    def mark_cancelled(self, task_id: str) -> None: ...
    def is_cancelled(self, task_id: str) -> bool: ...
    def snapshot(self, task_id: str) -> dict[str, object]: ...
    def cleanup(self, task_id: str) -> None: ...
```

### 方法职责

| 方法 | 责任边界 | 当前调用方 | 迁移后调用方 | 替换旧访问点 |
| --- | --- | --- | --- | --- |
| `register_task` | 注册 task 的运行态槽位，并记录当前 asyncio task | `_execute_agent_task(...)` | `_execute_agent_task(...)` | `_running_tasks[...] = ...` |
| `bind_orchestrator` | 绑定当前运行中的 orchestrator 引用 | `_execute_agent_task(...)` | `_execute_agent_task(...)` | `_running_orchestrators[...] = ...` |
| `bind_event_manager` | 绑定当前运行中的 event manager 引用 | `_execute_agent_task(...)` | `_execute_agent_task(...)` | `_running_event_managers[...] = ...` |
| `bind_queue_bundle` | 绑定当前 task 的 queue bundle | `_execute_agent_task(...)` | `_execute_agent_task(...)` | `_running_queue_services[...]`、`_running_recon_queue_services[...]`、`_running_bl_queue_services[...]` |
| `mark_cancelled` | 标记取消，不负责 DB 写入 | `cancel_agent_task(...)` | `TaskControlPlanePort.cancel_task(...)` | `_cancelled_tasks.add(task_id)` |
| `is_cancelled` | 返回当前 task 是否已被标记取消 | `_execute_agent_task(...)`、runtime helpers | `_execute_agent_task(...)`、queue/worker 调用链 | `is_task_cancelled(task_id)` |
| `snapshot` | 返回当前 task 的内部运行态快照 | route 层 | route 层 | 直接读取 `_running_*` |
| `cleanup` | 清理当前 task 的全部运行态引用 | `_execute_agent_task(...)` finally | `_execute_agent_task(...)` finally | `_running_*.pop(...)`、`_cancelled_tasks.discard(...)` |

### `snapshot(...)` 返回结构

`snapshot(task_id)` 的返回结构在 Phase 1 固定为：

```python
{
    "task_id": str,
    "is_registered": bool,
    "is_cancelled": bool,
    "asyncio_task": object | None,
    "orchestrator": object | None,
    "event_manager": object | None,
    "queue_bundle": {
        "vuln": object | None,
        "recon": object | None,
        "business_logic": object | None,
    },
}
```

这是 backend 内部快照结构，不是外部 API schema。

## 3.2 `TaskControlPlanePort`

`TaskControlPlanePort` 是 **backend 内部稳定边界**。它负责把取消、事件发射、状态推进、终态收敛收口到一处。

最小方法集固定为：

```python
class TaskControlPlanePort:
    async def emit_event(
        self,
        task_id: str,
        *,
        event_type: str,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> None: ...

    async def update_task_state(
        self,
        task_id: str,
        *,
        status: str | None = None,
        phase: str | None = None,
        step: str | None = None,
        progress: float | None = None,
    ) -> None: ...

    async def finalize_terminal_state(
        self,
        task_id: str,
        *,
        desired_status: str,
        success_payload: dict[str, object] | None = None,
        failure_message: str | None = None,
        failure_metadata: dict[str, object] | None = None,
    ) -> dict[str, object]: ...

    async def cancel_task(
        self,
        task_id: str,
        *,
        origin: str,
    ) -> None: ...
```

### 方法职责

| 方法 | 责任边界 | 当前调用方 | 迁移后调用方 | 替换旧访问点 |
| --- | --- | --- | --- | --- |
| `emit_event` | 发事件到 event manager，并保留当前 SSE/DB 逻辑 | `event_emitter.emit_*` 分散调用 | 执行主链路、phase result 收口逻辑 | 分散的 `event_emitter.emit_*` 调用 |
| `update_task_state` | 更新 `AgentTask` 的状态/phase/step/progress | `_execute_agent_task(...)` 直接写 task 字段 | `_execute_agent_task(...)`、workflow 结果收口 | 分散的 `task.status = ...`、`task.current_phase = ...` |
| `finalize_terminal_state` | 统一成功/失败/取消终态收敛 | `_finalize_task_terminal_state(...)` | `_execute_agent_task(...)` | 裸 helper 调用 |
| `cancel_task` | 负责 mark cancelled、取消 asyncio task、更新 DB 终态 | `cancel_agent_task(...)` | `cancel_agent_task(...)` | `_cancelled_tasks.add(...)` + `_running_tasks.get(...)` + `_running_asyncio_tasks.get(...)` 的手工组合 |

## 4. 迁移规则

### 4.1 允许保留的旧实现

在 Phase 1 期间，下面这些旧符号允许保留，但只能存在于 registry / control plane 的本地实现内部：

- `_running_tasks`
- `_running_queue_services`
- `_running_recon_queue_services`
- `_running_bl_queue_services`
- `_running_orchestrators`
- `_running_event_managers`
- `_cancelled_tasks`

### 4.2 禁止新增的旧用法

Phase 1 起，禁止新增下面这些写法：

- 在 route 层直接访问 `_running_*`
- 在 workflow / executor 层直接调用 `is_task_cancelled(task_id)`
- 在业务逻辑中直接手写 `task.status = ...` / `task.current_phase = ...` 作为正式状态推进边界

### 4.3 旧访问点到新边界的替换

| 旧写法 | 新写法 |
| --- | --- |
| `_running_orchestrators.get(task_id)` | `registry.snapshot(task_id)["orchestrator"]` |
| `_running_event_managers.get(task_id)` | `registry.snapshot(task_id)["event_manager"]` |
| `_running_queue_services.get(task_id)` | `registry.snapshot(task_id)["queue_bundle"]["vuln"]` |
| `_cancelled_tasks.add(task_id)` | `await control_plane.cancel_task(task_id, origin=...)` |
| `is_task_cancelled(task_id)` | `registry.is_cancelled(task_id)` |
| `_finalize_task_terminal_state(...)` | `await control_plane.finalize_terminal_state(...)` |

## 5. Phase 1 明确不做的能力

- 不把 `TaskRuntimeRegistry` 持久化到 DB 或 Redis。
- 不把 `TaskControlPlanePort` 变成远程服务。
- 不要求多个 backend 进程共享同一个 registry。
- 不重新设计 `AgentEvent` 数据模型。
- 不在本轮把 thinking token 复盘能力从“运行时可见”升级成“必然可回放”。

## 6. 与其他规格的关系

- queue 的权威接口以 [Queue Port 实施规格](./queue-port-spec.md) 为准。
- workspace / phase result / finding persistence 的权威接口以 [Execution Contracts 实施规格](./execution-contracts-spec.md) 为准。
- 整体交付顺序与验收矩阵以 [Phase 1 实施总规格](./phase1-implementation-spec.md) 为准。
