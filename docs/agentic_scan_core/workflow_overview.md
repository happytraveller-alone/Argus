# 智能扫描全流程总览

> 2026-04-18 更新：本文只描述当前产品可见的智能扫描主链路。历史兼容字段、Python 旧 runtime 与迁移背景请以 `plan/rust_full_takeover/` 下的迁移文档为准。

## 阅读定位

- **文档类型**：Explanation。
- **目标读者**：需要先看懂智能扫描主线，再回到代码细节的开发者。
- **阅读目标**：明确任务模型、创建入口、阶段推进顺序和结果沉淀方式。
- **建议前置**：如果你还不熟悉系统全貌，先读 [../architecture.md](../architecture.md)；如果你要继续看角色边界，再读 [agent_tools.md](./agent_tools.md)。
- **术语入口**：如果你对 `seed finding`、`risk point`、`vuln_queue` 这些词还不稳定，先看 [../glossary.md](../glossary.md)。

## 先记住三条判断

- 智能扫描的主任务模型是 `AgentTask`。
- 全流程的阶段推进由 workflow 保持确定性，LLM 负责的是单阶段内部判断。
- 前端展示的“过程 + 结果”来自 `AgentEvent`、`AgentFinding` 和 task 级报告的组合，而不是单一结果表。

## 1. 系统边界

当前产品层面只有两类扫描任务：

- 静态扫描
- 智能扫描

其中：

- 智能扫描统一使用 `AgentTask` 作为主任务模型。
- 静态扫描仍是并行产品能力，但它有自己独立的任务与结果模型。
- 如果你要理解智能扫描主线，优先看 `AgentTask` 如何驱动队列、阶段和结果沉淀，而不是把注意力放在历史来源模式上。

当前链路里最值得先看的三个锚点是：

- `backend/app/api/v1/endpoints/agent_tasks_execution.py`
- `backend/app/services/agent/workflow/`
- `backend/app/models/agent_task.py`

## 2. 创建阶段

前端创建入口在 `frontend/src/components/scan/CreateProjectScanDialog.tsx`。该页面在创建智能类任务时，统一调用 `createAgentTask(...)`。

当前创建阶段最重要的契约有：

- `CreateAgentTaskRequest`
- `target_vulnerabilities`
- `verification_level`
- `target_files` / `exclude_patterns`

也就是说，当前产品视角下，智能扫描的创建重点是：

1. 选择项目
2. 选择审计范围与排除项
3. 选择目标漏洞类型和验证策略
4. 生成一条 `AgentTask`

前端不再暴露额外的来源模式切换。对接智能扫描时，应该默认它是一条单一的 `AgentTask` 主链路。

## 3. 执行准备阶段

`backend/app/api/v1/endpoints/agent_tasks_execution.py` 中的 `_execute_agent_task(task_id)` 是当前智能扫描的统一执行入口。执行准备阶段大致分为以下步骤：

1. 读取 `AgentTask` 与 `Project`
2. 准备项目根目录
3. 校验并测试 LLM 配置
4. 初始化工具集合
5. 初始化 MCP 运行时并做 required MCP 门禁检查
6. 初始化 3 类队列
7. 创建各子智能体与 `WorkflowOrchestratorAgent`

这一阶段涉及的关键运行时对象包括：

- `AgentTask`
- `AgentEvent`
- `AgentFinding`
- `WorkflowState`

队列初始化是后续编排的关键，因为智能体之间不是直接共享全部内部状态，而是通过显式队列交接：

- `recon_queue`
- `vuln_queue`
- `business_logic_queue`

## 4. 初始种子与入口发现

当前智能扫描不会依赖一个独立的前端模式切换来决定主链路，而是在统一任务入口下构造后续分析所需的初始输入。

文档层面最重要的是记住三点：

- 初始输入的目标是为后续 Analysis 提供稳定的优先调查入口。
- 这些输入不是最终漏洞结论，只是后续阶段消费的候选线索。
- 即使某些历史兼容逻辑仍存在于旧 runtime 或迁移文档中，当前产品主线也只暴露单一的智能扫描入口。

### 4.1 当前输入来源

当前智能扫描的初始输入主要来自：

- 项目文件树与目录结构
- 目标文件、排除规则与项目元数据
- 入口点发现与确定性 seed 构造

### 4.2 候选与最终漏洞的区别

这里有两个边界必须分清：

- risk point：供后续分析消费的风险点
- final finding：经过分析、验证、报告收敛后的漏洞结论

risk point 不是最终漏洞，seed finding 也不是最终漏洞。真正面向用户的结果，始终要经过后续阶段收敛。

## 5. 编排阶段

当前主链路的关键事实是：全流程顺序不是由旧式 LLM Orchestrator 自由决定，而是由 `AuditWorkflowEngine` 进行确定性推进。

运行时组合关系是：

- `WorkflowOrchestratorAgent`：挂接子智能体、队列、运行时和统计
- `AuditWorkflowEngine`：推进阶段顺序、消费队列、控制并行
- 各子智能体：在单阶段内部做 LLM + ReAct 推理

### 5.1 固定阶段顺序

当前 `AuditWorkflowEngine` 的真实阶段顺序是：

`RECON -> BUSINESS_LOGIC_RECON -> ANALYSIS + BUSINESS_LOGIC_ANALYSIS -> VERIFICATION -> REPORT -> COMPLETE`

阶段含义如下：

- `RECON`
  常规代码安全风险点侦察，产出进入 `recon_queue` 的风险点。
- `BUSINESS_LOGIC_RECON`
  业务逻辑风险点侦察，产出进入 `business_logic_queue` 的风险点。
- `ANALYSIS`
  逐条消费 `recon_queue`，对常规风险点深挖并把确认 finding 推入 `vuln_queue`。
- `BUSINESS_LOGIC_ANALYSIS`
  逐条消费业务逻辑风险点，并把确认 finding 推入同一个 `vuln_queue`。
- `VERIFICATION`
  逐条消费 `vuln_queue`，做验证、PoC/Harness、结论持久化。
- `REPORT`
  为运行期已收敛的 finding 生成漏洞报告素材，并生成项目级风险评估报告。

### 5.2 当前阶段推进约束

当前产品主线里，常规代码安全轨与业务逻辑轨并行存在，但它们都要遵守同一套队列与阶段推进规则：

- 常规代码安全轨：`Recon -> Analysis -> Verification -> Report`
- 业务逻辑轨：`BusinessLogicRecon -> BusinessLogicAnalysis -> Verification -> Report`

两条轨道在验证前汇聚到统一的 `vuln_queue`，所以：

- `VERIFICATION` 阶段是共享的
- `REPORT` 阶段也是共享的

### 5.3 队列的权威性

当前实现中，队列不是“辅助缓存”，而是跨智能体交接的权威通道：

- `recon_queue` 是常规风险点的权威输入源
- `business_logic_queue` 是业务逻辑风险点的权威输入源
- `vuln_queue` 是待验证漏洞的权威输入源

特别是 `VERIFICATION` 阶段，工作流明确以 `vuln_queue` 为准，而不是凭子智能体临时上下文批量跳过。

## 6. 当前基于 LLM 的工作方法

如果只用一句话概括当前实现：

**LLM 负责“单智能体内部如何思考和调用工具”，Workflow 负责“全流程何时推进到下一阶段”。**

### 6.1 LLM 负责什么

LLM 的职责主要集中在每个子智能体内部：

- 基于 prompt 与上下文决定下一步动作
- 选择合适工具读代码、查调用链、做流分析
- 基于工具返回的真实结果形成风险点、finding、验证结论或报告内容

也就是说，LLM 主要解决“局部审计判断”问题，而不是“全局阶段推进”问题。

### 6.2 Workflow Engine 负责什么

`AuditWorkflowEngine` 负责：

- 阶段顺序
- 队列消费
- worker 并行控制
- report 阶段批处理
- 项目级风险报告汇总
- 运行统计和 `WorkflowState` 更新

这套机制替代了“让 Orchestrator 纯靠 LLM 自己决定所有调度顺序”的不确定性。

### 6.3 队列与结论收敛

在当前方法里，队列和收敛工具一起构成了 Agent 间协作边界：

- Recon 只负责推风险点，不负责下最终漏洞结论
- Analysis 负责确认 finding，但不负责最终落库结论收敛
- Verification 负责验证与 `save_verification_result`
- Report 负责二次复审、补证据、`update_vulnerability_finding` 与 Markdown 报告

因此“发现”“验证”“报告”是三个不同的责任层，不应在文档中混写成一步。

## 7. 结果沉淀

### 7.1 运行过程沉淀为 `AgentEvent`

任务执行期间，后端会持续写入 `AgentEvent`，前端再通过 SSE 流展示实时过程。因此页面能看到：

- 当前阶段
- 实时日志
- 工具调用
- 错误与警告
- 报告生成进度

### 7.2 漏洞结果沉淀为 `AgentFinding`

`AgentFinding` 是最终结果视图的核心实体，但它不是侦察阶段的直接产物，而是经过：

1. Analysis 或 BusinessLogicAnalysis 推入候选 finding
2. Verification 收敛 verdict / reachability / confidence / evidence
3. Report 补充报告与必要字段修正

之后才形成用户可消费的结果。

### 7.3 报告分为两层

当前 `REPORT` 阶段会生成两类输出：

- 单漏洞详情报告：挂在 finding 维度
- 项目级风险评估报告：挂在 task 维度

也就是说，ReportAgent 负责生成运行期存量 Markdown 素材；真正导出给用户的报告，会在导出阶段按当前 findings 重新做三态归一化：

- `确报`
- `待确认`
- `误报`

## 8. 前端为什么能展示“过程 + 结果”

智能扫描结果页之所以和静态扫描体验不同，是因为它消费的不是单一“任务结束后结果”，而是两类并存数据：

- 过程数据：`AgentEvent` + SSE 流
- 结果数据：`AgentFinding` + task 级 report

因此前端结果页本质上展示的是：

- 一个可回放的工作流执行过程
- 一组经过验证和报告收敛后的结果

这也是为什么智能扫描页面天然更像“执行过程 + 结果回放”，而不是静态扫描那种“任务结果列表”。

## 继续阅读

- 要看谁负责什么、谁能调哪些工具：读 [agent_tools.md](./agent_tools.md)。
- 要回到整个系统的阅读路径：读 [../architecture.md](../architecture.md)。
- 要统一术语理解：回看 [../glossary.md](../glossary.md)。
