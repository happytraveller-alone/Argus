# AuditTool 文档术语表

## 使用方式

- 这份术语表只收录在当前 `docs/` 中反复出现、且容易混淆的核心概念。
- 每个术语都尽量给出“它是什么”和“它不是什么”，帮助不同文档保持同一套口径。
- 如果你是第一次进入这个仓库，建议先读这份术语表，再读 [architecture.md](./architecture.md)。

## 系统级对象

### `Project`

- **是什么**：整个系统的中心工作空间，承接仓库来源、文件归档、扫描任务和聚合结果。
- **不是什么**：单次扫描任务本身；扫描任务是挂在 `Project` 下的。
- **相关文档**：[architecture.md](./architecture.md)

### 静态扫描

- **是什么**：由多个静态引擎并列执行、在产品层聚合展示的一类扫描体验。
- **不是什么**：单一后端模型；代码里仍保留各引擎自己的 task / finding 边界。
- **相关文档**：[architecture.md](./architecture.md)

### 智能扫描

- **是什么**：以 `AgentTask` 为主任务模型，由 Agent 做侦察、分析、验证和报告生成的扫描流程。
- **不是什么**：简单的规则扫描或静态引擎包装层。
- **相关文档**：[architecture.md](./architecture.md), [agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md)

## Agent 扫描主线术语

### `AgentTask`

- **是什么**：智能扫描的主任务实体。
- **不是什么**：仅代表某一个子智能体的一次执行。
- **相关文档**：[architecture.md](./architecture.md), [agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md)

### `AgentEvent`

- **是什么**：任务运行过程中的实时事件，用于支撑 SSE 流和过程回放。
- **不是什么**：最终漏洞结论。
- **相关文档**：[architecture.md](./architecture.md), [agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md)

### `AgentFinding`

- **是什么**：经过分析、验证和报告收敛后的漏洞结果实体。
- **不是什么**：bootstrap 候选或侦察阶段风险点。
- **相关文档**：[architecture.md](./architecture.md), [agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md)

### bootstrap candidate

- **是什么**：内嵌静态预扫归一化后的高优先候选结果。
- **不是什么**：最终漏洞，也不是一定会进入结果页的 finding。
- **相关文档**：[agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md)

### seed finding

- **是什么**：喂给后续分析阶段的入口种子，可能来自 bootstrap candidate，也可能来自入口点发现回退流程。
- **不是什么**：最终验证完成的 finding。
- **相关文档**：[agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md)

### risk point

- **是什么**：侦察阶段发现、尚待深挖的可疑入口点。
- **不是什么**：已经确认可利用的漏洞。
- **相关文档**：[agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md), [agentic_scan_core/agent_tools.md](./agentic_scan_core/agent_tools.md)

### `recon_queue`

- **是什么**：常规代码安全风险点的权威输入队列。
- **不是什么**：任意智能体都能跳过的临时缓存。
- **相关文档**：[agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md), [agentic_scan_core/agent_tools.md](./agentic_scan_core/agent_tools.md)

### `business_logic_queue`

- **是什么**：业务逻辑风险点的权威输入队列。
- **不是什么**：常规代码安全风险点的别名队列。
- **相关文档**：[agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md), [agentic_scan_core/agent_tools.md](./agentic_scan_core/agent_tools.md)

### `vuln_queue`

- **是什么**：待验证漏洞候选的权威输入队列。
- **不是什么**：报告阶段的最终结果存储。
- **相关文档**：[agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md), [agentic_scan_core/agent_tools.md](./agentic_scan_core/agent_tools.md)

## DeerFlow Runtime 改造术语

### host session

- **是什么**：某个 host agent 在自身生命周期内持有的主会话状态。
- **不是什么**：worker 的隔离上下文副本。
- **相关文档**：[deer-flow-runtime-phases/phase1-session-runtime-and-middleware.md](./deer-flow-runtime-phases/phase1-session-runtime-and-middleware.md)

### worker profile

- **是什么**：隔离 worker 的稳定运行配置名，用于约束工具、并发、历史模式和写权限。
- **不是什么**：`AgentType` 的简单别名。
- **相关文档**：[deer-flow-runtime-phases/phase0-runtime-contracts-and-guardrails.md](./deer-flow-runtime-phases/phase0-runtime-contracts-and-guardrails.md), [deer-flow-runtime-phases/phase3-isolated-subagent-runtime.md](./deer-flow-runtime-phases/phase3-isolated-subagent-runtime.md)

### `HandoffEnvelope`

- **是什么**：父线程向 worker 交接任务时使用的结构化交接体。
- **不是什么**：任意 `dict` 透传。
- **相关文档**：[deer-flow-runtime-phases/phase0-runtime-contracts-and-guardrails.md](./deer-flow-runtime-phases/phase0-runtime-contracts-and-guardrails.md), [deer-flow-runtime-phases/phase3-isolated-subagent-runtime.md](./deer-flow-runtime-phases/phase3-isolated-subagent-runtime.md)

### unified skill catalog

- **是什么**：对 `scan_core`、registry manifest、`skills.md`、`shared.md` 等多源技能资产的统一视图。
- **不是什么**：再新增一套与现有视图并列的 skill 来源。
- **相关文档**：[deer-flow-runtime-phases/phase2-skills-progressive-loading.md](./deer-flow-runtime-phases/phase2-skills-progressive-loading.md)

### thread checkpoint

- **是什么**：以 thread envelope 为中心的恢复快照，保存运行时恢复所需摘要与引用。
- **不是什么**：queue 实体副本，或对 `AgentCheckpoint` 的简单重命名。
- **相关文档**：[deer-flow-runtime-phases/phase4-thread-checkpoint-and-recovery.md](./deer-flow-runtime-phases/phase4-thread-checkpoint-and-recovery.md)

## 阅读路线建议

- 想先看系统全貌：读 [architecture.md](./architecture.md)。
- 想看智能扫描主线：读 [agentic_scan_core/README.md](./agentic_scan_core/README.md)。
- 想看 DeerFlow runtime 改造计划：读 [deer-flow-runtime-phases/README.md](./deer-flow-runtime-phases/README.md)。
