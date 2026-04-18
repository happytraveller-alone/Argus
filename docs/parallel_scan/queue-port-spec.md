# Queue Port 实施规格

> 2026-04-18 更新：本文中的 `InMemoryBusinessLogicRiskQueue` / `RedisBusinessLogicRiskQueue` 等 Python 实现描述保留为历史 queue-port 规格参考，不再表示当前 live runtime ownership。当前 authoritative 迁移状态以 `plan/rust_full_takeover/*` 为准。

## 阅读定位

- **文档类型**：Reference（实施规格）。
- **目标读者**：准备把三类现有队列收口成统一 Queue Port 语义的开发者。
- **阅读目标**：固定 `QueuePort`、`QueueClaim`、重复发布语义、lease 语义、统计 schema 和三类队列到统一契约的映射关系。
- **建议前置**：先读 [./redis-db-workspace-worker-sequence.md](./redis-db-workspace-worker-sequence.md) 理解目标模型，再读本文定接口。
- **本文不覆盖**：Redis 键设计、跨进程 worker claim、公平调度算法。

## 1. 规范状态

- **当前已存在**
  - `InMemoryVulnerabilityQueue` / `RedisVulnerabilityQueue`
  - `InMemoryReconRiskQueue` / `RedisReconRiskQueue`
  - `InMemoryBusinessLogicRiskQueue` / `RedisBusinessLogicRiskQueue`
- **Phase 1 新引入**
  - `QueuePort`
  - `QueueClaim`
  - in-memory queue adapter
- **明确延后**
  - Redis 主链路接线
  - 真正的跨进程 lease 抢占
  - dead-letter 的产品级 UI

## 2. 当前代码差异必须先被承认

当前三类队列并没有统一接口。

| 当前队列 | 当前公开方法 | 当前关键差异 |
| --- | --- | --- |
| vuln queue | `enqueue_finding`、`dequeue_finding`、`peek_finding`、`get_queue_size`、`peek_queue`、`contains_finding`、`clear_queue`、`get_queue_stats` | `contains_finding` 是 pending membership |
| recon queue | `enqueue`、`enqueue_batch`、`dequeue`、`peek`、`size`、`stats`、`contains`、`clear` | `contains` 是 dedupe membership |
| business logic queue | `enqueue`、`enqueue_batch`、`dequeue`、`peek`、`size`、`stats`、`contains`、`clear` | `contains` 是 dedupe membership |

因此，Phase 1 不是“简单重命名方法”，而是 **先统一语义，再通过 adapter 映射现有类**。

## 3. `QueuePort`

`QueuePort` 是 Phase 1 的统一队列规范名。三类队列都必须表现为相同的方法语义。

### 3.1 队列种类

`queue_kind` 固定为以下三种之一：

- `recon`
- `business_logic`
- `vuln`

### 3.2 最小方法集

```python
class QueuePort:
    def publish(
        self,
        *,
        queue_kind: str,
        task_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]: ...

    def publish_batch(
        self,
        *,
        queue_kind: str,
        task_id: str,
        payloads: list[dict[str, object]],
    ) -> dict[str, object]: ...

    def claim(
        self,
        *,
        queue_kind: str,
        task_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> "QueueClaim | None": ...

    def ack(self, claim: "QueueClaim") -> dict[str, object]: ...
    def retry(
        self,
        claim: "QueueClaim",
        *,
        reason: str,
        retry_after_seconds: int = 0,
    ) -> dict[str, object]: ...

    def extend_lease(
        self,
        claim: "QueueClaim",
        *,
        lease_seconds: int,
    ) -> "QueueClaim": ...

    def peek(
        self,
        *,
        queue_kind: str,
        task_id: str,
        limit: int = 10,
    ) -> list[dict[str, object]]: ...

    def stats(
        self,
        *,
        queue_kind: str,
        task_id: str,
    ) -> dict[str, object]: ...

    def clear(
        self,
        *,
        queue_kind: str,
        task_id: str,
    ) -> dict[str, object]: ...

    def dead_letter(
        self,
        claim: "QueueClaim",
        *,
        reason: str,
    ) -> dict[str, object]: ...
```

## 4. `QueueClaim`

`QueueClaim` 返回结构固定包含下面这些字段，不得删改名称：

```python
{
    "queue_kind": "recon" | "business_logic" | "vuln",
    "task_id": str,
    "item_id": str,
    "lease_id": str,
    "lease_expires_at": str,
    "attempt": int,
    "payload": dict[str, object],
}
```

补充约束：

- `lease_expires_at` 必须是 ISO 8601 文本，不得暴露 bytes 或 datetime 实例。
- `attempt` 从 `1` 开始计数。
- `payload` 是当前队列项的业务内容；Phase 1 不再把 claim 包装成老式 `dequeue*` 返回值。

## 5. 统一语义

### 5.1 发布语义

`publish(...)` 与 `publish_batch(...)` 的重复发布语义固定为：

- 相同指纹重复发布是 **幂等 no-op**
- 不重复入队
- 返回结果中必须带 `duplicate: true`
- 统计中必须累加 `total_deduplicated`

不得把重复项解释为“报错失败”，也不得悄悄吞掉而不更新统计。

### 5.2 `contains*` 不再是规范名词

Phase 1 不再暴露裸 `contains` / `contains_finding` 作为正式接口。必须拆成两种语义理解：

- **pending membership**
  - 含义：当前 item 是否仍在 pending 队列中
- **dedupe membership**
  - 含义：当前指纹是否已经进过去重集合

这两种查询如果实现上仍然需要存在，只允许作为 adapter 内部 helper 或 route 兼容 helper，不得再作为 `QueuePort` 的公开规范名。

### 5.3 lease 语义

即使 Phase 1 仍使用 in-memory adapter，也必须按 lease 语义实现：

- `claim(...)` 不等价于“永久移出队列”
- `ack(...)` 才代表本次 claim 被消费完成
- `retry(...)` 代表当前 claim 放回可重试状态
- `extend_lease(...)` 只能延长当前 `lease_id` 的有效期
- `dead_letter(...)` 代表当前 claim 被转入终止重试状态

## 6. `stats(...)` 返回 schema

`stats(...)` 的返回结构在 Phase 1 固定为：

```python
{
    "queue_kind": str,
    "task_id": str,
    "pending_count": int,
    "claimed_count": int,
    "dead_letter_count": int,
    "total_published": int,
    "total_claimed": int,
    "total_acked": int,
    "total_retried": int,
    "total_deduplicated": int,
    "last_published_at": str | None,
    "last_claimed_at": str | None,
    "last_acked_at": str | None,
}
```

约束如下：

- 所有计数字段必须是整数。
- 所有时间字段必须是文本或 `null`。
- 不允许从 Redis adapter 向上泄漏 bytes。
- route 层如果仍然需要兼容旧字段名，兼容转换必须发生在 route 层，不得污染 `QueuePort`。

## 7. 当前三类队列到统一 QueuePort 的映射表

| 当前旧方法 | 统一 QueuePort 语义 | 迁移规则 |
| --- | --- | --- |
| `enqueue_finding(...)` | `publish(queue_kind="vuln", ...)` | Phase 1 允许保留 legacy shim，但 workflow 不得再直接使用 |
| `dequeue_finding(...)` | `claim(queue_kind="vuln", ...)` | workflow / executor 迁到 claim + ack/retry |
| `get_queue_size(...)` | `stats(...).pending_count` | route 层兼容转换 |
| `get_queue_stats(...)` | `stats(...)` | route 层兼容旧响应字段 |
| `enqueue(...)` | `publish(queue_kind="recon" / "business_logic", ...)` | workflow / tools 改为统一术语 |
| `enqueue_batch(...)` | `publish_batch(...)` | 统计与去重语义统一到新契约 |
| `dequeue(...)` | `claim(...)` | workflow / executor 迁到 claim + ack/retry |
| `peek(...)` / `peek_queue(...)` | `peek(...)` | 兼容层内部转换即可 |
| `clear(...)` / `clear_queue(...)` | `clear(...)` | 统一返回结构 |

## 8. 调用点迁移规则

### 8.1 必须迁移的内部调用点

- `backend/app/services/agent/workflow/engine.py`
- `backend/app/services/agent/workflow/parallel_executor.py`
- `backend/app/services/agent/workflow/workflow_orchestrator.py`

这些模块必须以 `QueuePort` 为主语义，不再直接写 `enqueue*` / `dequeue*`。

### 8.2 可保留短期兼容层的调用点

- `backend/app/api/v1/endpoints/agent_tasks_routes_results.py`
- `backend/app/services/agent/tools/queue_tools.py`
- `backend/app/services/agent/tools/recon_queue_tools.py`
- `backend/app/services/agent/tools/business_logic_recon_queue_tools.py`

这些位置 Phase 1 允许短期通过 compatibility shim 适配，但不得新增新的 legacy 依赖。

## 9. 明确延后的能力

- 真正的 Redis claim 争抢
- 基于 lease timeout 的自动 requeue
- distributed dead-letter processor
- 按 worker 权重做公平调度

## 10. 关联文档

- [Phase 1 实施总规格](./phase1-implementation-spec.md)
- [Runtime / Control Plane 实施规格](./runtime-control-plane-spec.md)
- [Execution Contracts 实施规格](./execution-contracts-spec.md)
