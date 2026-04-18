# Agentic Scan Core 文档导读

`docs/agentic_scan_core` 只描述当前 `AgentTask` 体系下的智能扫描。

## 阅读定位

- **文档类型**：以 Explanation 为主，辅以运行时 Reference。
- **目标读者**：已经知道 `Project` / `AgentTask` 是什么，但还没看懂智能扫描如何真正协同的开发者。
- **阅读目标**：搞清楚主任务模型、阶段编排、工具注入和各智能体职责边界。
- **建议前置**：如果你还不熟悉整个系统，先读 [../architecture.md](../architecture.md)。
- **术语入口**：如果你想先统一 `bootstrap candidate`、`risk point`、`AgentFinding` 这些概念，先读 [../glossary.md](../glossary.md)。

## 目录目的

这组文档回答 4 个问题：

1. 当前项目里的智能扫描主任务模型是什么。
2. 真实运行时是由谁负责编排、谁负责分析、谁负责验证、谁负责出报告。
3. 每个智能体到底能调哪些工具、边界在哪里、上下游怎么交接。
4. 当前运行时真实会触发的 skill，如何和配置页展示、evidence 视图展示保持一致。

## 当前扫描模式

- 智能扫描：`AgentTask`

## 当前真实主线

- 前端创建入口：`frontend/src/components/scan/CreateProjectScanDialog.tsx`
- 后端执行入口：Rust `backend/src/routes/agent_tasks.rs`
- 编排核心：`backend/app/services/agent/workflow/workflow_orchestrator.py`
- 确定性工作流引擎：`backend/app/services/agent/workflow/engine.py`

需要特别注意的一点是：当前主链路并不是“纯 LLM 自由调度整个流程”，而是：

- `WorkflowOrchestratorAgent` 负责挂接运行时、队列和子智能体
- `AuditWorkflowEngine` 负责确定性推进阶段顺序
- 各子智能体内部仍然使用 LLM + ReAct 决定如何读代码、选工具、形成判断

## 每篇文档分别解决什么问题

| 文档 | 主要回答的问题 | 文档类型 |
| --- | --- | --- |
| [workflow_overview.md](./workflow_overview.md) | 智能扫描的执行主线到底怎么流动 | Explanation |
| [agent_tools.md](./agent_tools.md) | 每个智能体负责什么，真实可用工具是什么 | Reference |
| [skill-evidence-alignment/README.md](./skill-evidence-alignment/README.md) | skill 真相源、配置页展示和 evidence 视图如何对齐 | Implementation reference |
| [../architecture.md](../architecture.md) | 这些链路放回整个系统里时，该从哪里读代码 | Explanation / onboarding reference |

## 建议阅读顺序

1. 先读 [workflow_overview.md](./workflow_overview.md)，先把主线看顺。
2. 再读 [agent_tools.md](./agent_tools.md)，把角色边界和工具边界补齐。
3. 如果你正在改配置页或 evidence 视图，再读 [skill-evidence-alignment/README.md](./skill-evidence-alignment/README.md)，把展示边界和协议对齐。
4. 需要补更大范围背景时，再回看 [../architecture.md](../architecture.md)。

## 文档边界

- 这里解释的是“当前实现”，不是未来规划。
- 这里说的 bootstrap 候选、seed、risk point 都不是最终漏洞结论。
- 这里默认读者已经知道 `Project` / `AgentTask` / `AgentFinding` 是什么，但不知道它们在智能扫描链路里如何协同。

## 继续阅读

- 要先把执行主线看顺：读 [workflow_overview.md](./workflow_overview.md)。
- 要查具体角色和工具边界：读 [agent_tools.md](./agent_tools.md)。
- 要对齐 skill 展示和 evidence 视图：读 [skill-evidence-alignment/README.md](./skill-evidence-alignment/README.md)。
- 要回到系统级背景：读 [../architecture.md](../architecture.md)。
