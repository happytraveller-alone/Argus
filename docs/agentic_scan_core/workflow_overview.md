# 智能扫描与混合扫描全流程总览

## 阅读定位

- **文档类型**：Explanation。
- **目标读者**：需要先看懂智能扫描 / 混合扫描主线，再回到代码细节的开发者。
- **阅读目标**：明确任务模型、创建差异、bootstrap 作用、阶段推进顺序和结果沉淀方式。
- **建议前置**：如果你还不熟悉系统全貌，先读 [../architecture.md](../architecture.md)；如果你要继续看角色边界，再读 [agent_tools.md](./agent_tools.md)。
- **术语入口**：如果你对 `seed finding`、`risk point`、`vuln_queue` 这些词还不稳定，先看 [../glossary.md](../glossary.md)。

## 先记住三条判断

- 智能扫描和混合扫描共用同一个主任务模型：`AgentTask`。
- 混合扫描的差异不在于“换了一套工作流”，而在于是否把静态候选注入主流程。
- 全流程的阶段推进由 workflow 保持确定性，LLM 负责的是单阶段内部判断。

## 1. 系统边界

当前产品层面有三类扫描任务：

- 静态扫描
- 智能扫描
- 混合扫描

其中：

- 智能扫描和混合扫描都统一使用 `AgentTask` 作为主任务模型。
- 混合扫描不是第四套独立执行框架，而是“智能扫描主流程 + 静态 bootstrap 注入”。
- 静态扫描仍是并行产品能力，但它不是混合扫描的主任务对象；混合扫描不会先创建一组独立静态任务再切换到另一套 Agent 模型，而是在 `AgentTask` 内部内嵌预扫并生成后续 seed。

这也是为什么当前链路里需要同时看：

- `backend/app/api/v1/endpoints/agent_tasks_execution.py`
- `backend/app/api/v1/endpoints/agent_tasks_bootstrap.py`
- `backend/app/models/agent_task.py`

## 2. 创建阶段

前端创建入口在 `frontend/src/components/scan/CreateProjectScanDialog.tsx`。该页面在创建智能类任务时，不再区分两套后端 API，而是统一调用 `createAgentTask(...)`。

关键契约有两个：

- `CreateAgentTaskRequest`
- `audit_scope.static_bootstrap`

前端创建 payload 时的核心差异只有一个：

- 智能扫描：`audit_scope.static_bootstrap.mode = "disabled"`
- 混合扫描：`audit_scope.static_bootstrap.mode = "embedded"`

除此之外，前端还会通过任务描述中的 marker 帮助后端识别来源模式：

- `HYBRID_TASK_NAME_MARKER = "[HYBRID]"`
- `INTELLIGENT_TASK_NAME_MARKER = "[INTELLIGENT]"`

后端在 `agent_tasks_bootstrap.py` 中通过 `_resolve_agent_task_source_mode(...)` 和 `_resolve_static_bootstrap_config(...)` 做最终归一化判断，所以真正的模式来源是：

1. 任务名称/描述中的 marker
2. `audit_scope.static_bootstrap`

## 3. 执行准备阶段

`backend/app/api/v1/endpoints/agent_tasks_execution.py` 中的 `_execute_agent_task(task_id)` 是智能扫描和混合扫描的统一执行入口。执行准备阶段大致分为以下步骤：

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

## 4. 混合扫描 bootstrap 阶段

只有当 `static_bootstrap.mode = embedded` 时，任务才会进入内嵌静态预扫逻辑。实现位于 `agent_tasks_bootstrap.py` 的 `_prepare_embedded_bootstrap_findings(...)`。

### 4.1 支持的预扫来源

当前 embedded bootstrap 支持以下来源：

- `OpenGrep`
- `Bandit`
- `Gitleaks`
- `PHPStan`
- `YASA`

这些来源不是为了直接生成最终漏洞，而是为了给后续 Agent 工作流提供“优先入口点”。

### 4.2 候选筛选规则

内嵌静态预扫返回的结果会经过统一归一化和筛选，当前文档层面需要记住两条规则：

- 只保留 `severity = ERROR`
- 只保留 `confidence = HIGH / MEDIUM`

因此 bootstrap 的输出不是“静态扫描所有命中”，而是“适合进入后续 Agent 流水线的高优先候选”。

### 4.3 seed 与最终漏洞的区别

bootstrap 输出会继续被转换成 `seed_findings`，再作为后续 Analysis 阶段的固定优先候选输入。这里有两个边界必须分清：

- bootstrap candidate：静态预扫归一化后的候选
- seed finding：喂给后续智能体的入口种子
- final finding：经过分析、验证、报告收敛后的漏洞结论

bootstrap candidate 和 seed finding 都不是最终漏洞。

### 4.4 回退机制

如果：

- 当前模式不是 embedded
- 或 embedded 预扫没有筛出有效候选

系统不会直接放弃，而是走入口点回退流程：

1. `_discover_entry_points_deterministic(...)` 发现入口点
2. `_build_seed_from_entrypoints(...)` 构造 seed

这样即便没有有效静态候选，智能扫描主流程仍然可以继续。

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

### 5.2 混合扫描如何影响阶段推进

混合扫描在有 bootstrap 候选时可以跳过常规 `RECON`，这是当前实现里最容易误解的地方。

实际行为是：

- 当 `audit_source_mode == "hybrid"`
- 且 `static_bootstrap_candidate_count > 0`
- 且 `skip_recon_when_bootstrap_available == true`

`AuditWorkflowEngine` 会把 bootstrap seeds 注入 `recon_queue`，然后跳过常规 `RECON` 阶段。

这意味着混合扫描并不是把静态结果直接当最终结论，而是把静态结果变成“Analysis 的优先输入”。

### 5.3 双轨并存

当前工作流里有两条并存轨道：

- 常规代码安全轨：`Recon -> Analysis -> Verification -> Report`
- 业务逻辑轨：`BusinessLogicRecon -> BusinessLogicAnalysis -> Verification -> Report`

两条轨道在验证前汇聚到统一的 `vuln_queue`，所以：

- Verification 阶段是共享的
- Report 阶段也是共享的

### 5.4 队列的权威性

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

`AgentFinding` 是最终结果视图的核心实体，但它不是 bootstrap 直接产物，而是经过：

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

导出阶段不会再沿用“仅 confirmed/likely 才可见”的旧假设，而是默认汇总当前任务下全部可导出的三态结果。

## 8. 前端为什么能展示“过程 + 结果”

智能扫描 / 混合扫描结果页之所以和静态扫描体验不同，是因为它消费的不是单一“任务结束后结果”，而是两类并存数据：

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
