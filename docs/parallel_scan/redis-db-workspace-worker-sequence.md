# Redis、DB、Workspace 与 Worker 交互时序

## 阅读定位

- **文档类型**：Explanation。
- **目标读者**：准备为并行扫描设计任务协议、队列语义和执行面交互方式的开发者。
- **阅读目标**：理解一个更稳妥的双平面目标架构中，Redis、DB、Workspace 和 Worker 分别如何参与任务流转，以及 Phase 1 应先在进程内定型哪些语义。
- **建议前置**：先读 [./control-plane-execution-plane-boundary.md](./control-plane-execution-plane-boundary.md) 理解边界，再读本文。
- **本文不覆盖**：Redis 键结构、消息序列化细节、对象存储选型。

## 非常重要的提醒

本文描述的是 **目标时序模型**，不是当前仓库已经接通的主链路。

如果你现在要真正改代码，请以这两篇规格文档为准：

- [Queue Port 实施规格](./queue-port-spec.md)
- [Execution Contracts 实施规格](./execution-contracts-spec.md)

它们定义了当前代码与本文目标模型之间的 **Phase 1 in-memory 映射规则**。

## 先记住三条判断

- Redis 更适合承接调度和重试，不适合替代 DB 成为最终真相源。
- Workspace 不能再只是隐式本地路径，而必须成为正式执行上下文引用。
- Worker 可以产出结果，但 finding 的最终收口更适合继续由 control plane 承担。

## 1. 参与者分别负责什么

### Control Plane

负责：

- 创建任务
- 推进状态机
- 记录事件
- 收口 finding
- 对前端输出 SSE / 查询结果

### Redis

负责：

- job queue
- claim / lease
- retry
- dead-letter

### DB

负责：

- 任务真相
- finding 真相
- 事件归档
- 阶段统计和最终报告索引

### Workspace

负责：

- 代码快照
- artifact 存储
- 证据文件
- 报告中间产物

### Worker

负责：

- 执行具体 phase
- 调用工具
- 产出结构化结果
- 回传 metrics 和 artifact ref

## 2. 目标时序主线

### 2.1 创建任务

目标模型中，第一步由 control plane 发起：

1. 接收前端请求，生成 `task_id`
2. 写入 DB 中的任务主记录和配置快照
3. 生成 `WorkspaceRef`
4. 把第一阶段 job 写入 Redis
5. 向前端返回 accepted

### 2.2 Worker claim 任务

第二步由 worker 从 Redis claim：

1. claim 一个可执行 job
2. Redis 返回 `lease_id` 与 `lease_expires_at`
3. worker 根据 payload 确定要跑哪个 phase
4. control plane 更新任务运行态

### 2.3 执行 phase

第三步是 worker 正式执行：

1. 根据 `WorkspaceRef` / `SnapshotRef` 解析代码快照
2. 读取前序阶段产物
3. 执行工具与 LLM 推理
4. 生成 `PhaseRunnerResult`

### 2.4 回传结果

第四步是 worker 提交结果：

1. 把证据、报告草稿、日志等写成 `ArtifactRef`
2. 调用 `PhaseResultPort`
3. control plane 根据结果：
   - 发事件
   - 更新状态
   - 调用 `FindingStorePort`
   - 决定是否推进下一阶段

### 2.5 失败恢复与 retry

第五步是失败恢复：

1. lease 超时或 worker 显式 `retry`
2. control plane 记录失败诊断
3. DB 记录最后状态与重试次数
4. queue 把任务重新变成可 claim
5. 新 worker 基于同一个 `WorkspaceRef` 继续执行

## 3. Phase 1 与目标时序的映射关系

如果这轮只做边界收口、不真正拆 worker，那么本文中的参与者在 Phase 1 中必须映射成：

- `Redis`
  - 先映射为支持 lease 语义的 in-memory `QueuePort` adapter
- `Worker`
  - 先映射为当前 backend 内本地执行的 phase runner
- `Workspace`
  - 先映射为 `WorkspaceRef / SnapshotRef / ArtifactRef` 加本地 `WorkspaceResolver`
- `Phase result API`
  - 先映射为 backend 内部 `PhaseResultPort`
- `Control Plane`
  - 继续由当前 backend 唯一承接

这一步的目的不是“伪装成已经分布式”，而是先让未来真正要外提的语义稳定下来。

## 4. 为什么 Redis 不能替代 DB

Redis 更适合：

- 高速调度
- lease
- retry
- dead-letter

但它不适合成为：

- 任务最终状态的唯一来源
- finding 审计记录的唯一来源
- 报告归档的唯一来源

更合理的分工始终是：

- Redis 管“任务怎么跑”
- DB 管“最终发生了什么”

## 5. 为什么 Workspace 必须显式成一层

当前代码里，很多调用仍然隐式依赖裸 `project_root`。

一旦要跨 worker 执行，立刻会出现三个问题：

1. 不同 worker 如何确认自己看到的是同一份代码快照？
2. 证据文件、报告草稿、PoC 产物放在哪里？
3. retry 以后，新 worker 如何复用前序产物？

因此 Workspace 必须升级成正式契约，Phase 1 对应的规范见 [Execution Contracts 实施规格](./execution-contracts-spec.md)。

## 6. 为什么 Worker 不建议直接写 DB

如果让 worker 直接写 DB，很快会遇到这些问题：

- 多 worker 并发 patch finding，谁优先？
- 同一 finding 的状态迁移规则放在哪里？
- verification worker 与 report worker 冲突时如何裁决？
- 前端到底该信 worker 原始结果，还是信最终收口后的 finding 视图？

因此更稳妥的模型是：

- worker 负责提交结果
- control plane 负责裁决和最终写入

## 7. 一句话总结

在更合理的并行扫描架构里：

- Redis 负责调度
- DB 负责真相
- Workspace 负责执行上下文
- Worker 负责执行
- Control Plane 负责收口

而在 Phase 1，这五者的职责先通过 **backend 内部边界** 定型，不通过真实分布式接线来定型。
