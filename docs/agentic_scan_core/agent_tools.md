# 智能体职责与工具矩阵

> 2026-04-18 更新：本文只描述当前智能审计职责矩阵。历史模式差异与迁移背景请以 `plan/rust_full_takeover/` 下的文档为准。

本文档整理当前智能审计真实运行态中各智能体的职责边界、输入输出和工具注入情况。

## 阅读定位

- **文档类型**：Reference。
- **目标读者**：已经知道工作流阶段顺序，但还没搞清楚“谁负责什么、谁能调什么工具”的开发者。
- **阅读目标**：把角色边界、输入输出和队列交接关系看成一张稳定矩阵，避免把不同责任层混写在一起。
- **建议前置**：先读 [workflow_overview.md](./workflow_overview.md)，再回来看这份矩阵会更容易对齐主线。
- **术语入口**：如果你需要先确认 `recon_queue`、`business_logic_queue`、`vuln_queue` 的定义，先看 [../glossary.md](../glossary.md)。

## 如何使用这份矩阵

- 先看“总览”，确定目标智能体在整条链路里的位置。
- 再看对应章节的“负责范围”和“交接关系”，判断改动应该落在哪一层。
- 最后看“可调用工具”，确认某个行为到底是 prompt 描述，还是当前运行时真实注入能力。

## 1. 文档范围

这里的事实来源只有两类：

- 工具构建入口：`backend/app/api/v1/endpoints/agent_tasks_execution.py` 中的 `_initialize_tools(...)`
- 智能体装配入口：`backend/app/api/v1/endpoints/agent_tasks_execution.py` 中创建各 Agent 并交给 `WorkflowOrchestratorAgent`

本文档只写当前运行时真实注入的工具，不按 prompt 中出现过但当前未实际注入的旧工具名来写。

## 2. 总览

| 智能体 | 工具来源键 | 主要职责 |
| --- | --- | --- |
| `WorkflowOrchestratorAgent` | `tools["orchestrator"]` | 确定性编排、阶段推进、队列消费、汇总统计 |
| `ReconAgent` | `tools["recon"]` | 常规代码安全风险点侦察并推入 `recon_queue` |
| `BusinessLogicReconAgent` | `tools["business_logic_recon"]` | 业务逻辑风险点侦察并推入 `business_logic_queue` |
| `AnalysisAgent` | `tools["analysis"]` | 对单个常规风险点深挖，并把确认 finding 推入 `vuln_queue` |
| `BusinessLogicAnalysisAgent` | `tools["business_logic_analysis"]` | 对单个业务逻辑风险点深挖，并把确认 finding 推入 `vuln_queue` |
| `VerificationAgent` | `tools["verification"]` | 对单个 finding 做验证、PoC/Harness、结论持久化 |
| `ReportAgent` | `tools["report"]` | 对已验证 finding 复审、补证据、生成详情报告与项目级风险报告 |

## 3. 共享基础工具

以下工具由 `_initialize_tools()` 的 `base_tools` 提供，多个智能体复用：

- `list_files`
- `search_code`
- `get_code_window`
- `get_file_outline`
- `get_function_summary`
- `get_symbol_body`
- `locate_enclosing_function`

这组工具体现了当前运行时的一个重要转向：Agent 读代码时不再以旧的 `read_file` / `extract_function` 为主，而是以“极小代码窗口 + 文件概览 + 函数总结 + 符号主体”这组更细粒度的工具为核心。

### 3.1 基础工具的职责边界

- `get_code_window`
  围绕锚点返回极小代码窗口，是当前最重要的“真实代码取证”工具。
- `get_file_outline`
  先给文件级结构概览，帮助 Agent 知道应该往哪个函数或区块继续深挖。
- `get_function_summary`
  给出单函数职责、输入输出和关键风险摘要，适合快速建立语义理解。
- `get_symbol_body`
  提取目标函数或符号的主体源码，用于需要完整函数体时的精读。
- `search_code`
  用于全项目找调用点、危险模式、入口点或护栏逻辑。
- `list_files`
  用于快速枚举目录与候选文件范围。
- `locate_enclosing_function`
  用于从 `file_path + line` 回到所属函数，帮助补齐证据和定位。

## 4. 旧工具名与当前运行时的关系

部分智能体 prompt 或历史文档里仍会出现以下旧名字：

- `read_file`
- `extract_function`
- `think`
- `reflect`

但在当前 `_initialize_tools()` 里，这些名字并不是主运行时注入工具。文档和排障时应以当前真实工具名为准：

- `read_file` 的主要替代组合是 `get_code_window` / `get_file_outline` / `get_function_summary`
- `extract_function` 的主要替代工具是 `get_symbol_body`

## 5. 各智能体职责矩阵

### 5.1 `WorkflowOrchestratorAgent`

**角色定位**

工作流总控层。它不是“自由审计一切”的分析者，而是把子智能体、队列、工作流引擎和统计粘合在一起的编排入口。

**执行功能**

- 驱动 `AuditWorkflowEngine` 进入各阶段
- 维护运行时上下文、统计、事件汇总
- 消费 Recon / Business Logic / Vulnerability 三类队列
- 控制并行分析、并行验证、并行报告

**负责范围**

- 阶段推进
- 队列消费
- 子智能体调度
- 汇总最终 findings、workflow state 和 project risk report

**典型输入**

- `project_info`
- `config`
- `project_root`
- `task_id`

**典型输出**

- `workflow_state`
- 汇总后的 `findings`
- `project_risk_report`
- 运行统计信息

**可调用工具**

基础工具：

- `list_files`
- `search_code`
- `get_code_window`
- `get_file_outline`
- `get_function_summary`
- `get_symbol_body`
- `locate_enclosing_function`

漏洞队列工具：

- `get_queue_status`
- `dequeue_finding`

Recon 队列工具：

- `get_recon_risk_queue_status`
- `dequeue_recon_risk_point`
- `peek_recon_risk_queue`
- `clear_recon_risk_queue`
- `is_recon_risk_point_in_queue`

业务逻辑队列工具：

- `get_bl_risk_queue_status`
- `dequeue_bl_risk_point`
- `peek_bl_risk_queue`
- `clear_bl_risk_queue`
- `is_bl_risk_point_in_queue`

**与上下游的交接关系**

- 上游：任务执行入口 `_execute_agent_task(...)`
- 下游：调度 `Recon / Analysis / Verification / Report / BusinessLogicRecon / BusinessLogicAnalysis`
- 交接介质：三类队列 + `WorkflowState`

**在当前智能审计中的位置**

- 当前智能审计：通常从常规 Recon 开始，并把风险点写入 `recon_queue`

### 5.2 `ReconAgent`

**角色定位**

常规代码安全侦察层，负责先找可疑风险点，不直接下最终漏洞结论。

**执行功能**

- 枚举项目结构和关键代码入口
- 搜索危险模式、敏感接口、关键调用
- 构造风险点并写入 `recon_queue`

**负责范围**

- 常规代码安全风险点识别
- 生成后续 Analysis 的输入

**典型输入**

- 项目根目录与文件树
- 配置中的目标文件、排除模式、目标漏洞类型

**典型输出**

- 推入 `recon_queue` 的 risk point

**可调用工具**

基础工具：

- `list_files`
- `search_code`
- `get_code_window`
- `get_file_outline`
- `get_function_summary`
- `get_symbol_body`
- `locate_enclosing_function`

队列工具：

- `push_risk_point_to_queue`
- `push_risk_points_to_queue`

**与上下游的交接关系**

- 上游：`WorkflowOrchestratorAgent`
- 下游：`AnalysisAgent`
- 交接介质：`recon_queue`

**在当前智能审计中的位置**

- 当前智能审计：正常执行，承担常规代码安全侦察入口的职责

### 5.3 `BusinessLogicReconAgent`

**角色定位**

业务逻辑专项侦察层，聚焦 IDOR、权限提升、状态机绕过、支付金额篡改、竞态条件等问题。

**执行功能**

- 判断项目是否具有业务入口
- 枚举 API / Webhook / RPC / 消息处理等入口
- 构造业务逻辑风险点并写入 `business_logic_queue`

**负责范围**

- 业务逻辑风险点发现
- 业务入口与敏感操作梳理

**典型输入**

- 文件树
- 路由、控制器、Webhook、回调、消费者代码

**典型输出**

- 推入 `business_logic_queue` 的 BL risk point

**可调用工具**

基础工具：

- `list_files`
- `search_code`
- `get_code_window`
- `get_file_outline`
- `get_function_summary`
- `get_symbol_body`
- `locate_enclosing_function`

业务逻辑队列工具：

- `push_bl_risk_point_to_queue`
- `push_bl_risk_points_to_queue`
- `get_bl_risk_queue_status`
- `is_bl_risk_point_in_queue`

**与上下游的交接关系**

- 上游：`WorkflowOrchestratorAgent`
- 下游：`BusinessLogicAnalysisAgent`
- 交接介质：`business_logic_queue`

**在当前智能审计中的位置**

- 当前智能审计：业务逻辑侦察轨独立运行，并把结果写入 `business_logic_queue`

### 5.4 `AnalysisAgent`

**角色定位**

常规漏洞分析层。它处理的是“单个风险点”，不是全项目自由漫游。

**执行功能**

- 读取风险点附近上下文
- 深挖调用链、数据流、控制流、鉴权条件
- 对高风险点形成确认 finding
- 把确认 finding 推入 `vuln_queue`

**负责范围**

- 常规代码安全漏洞确认
- 高危漏洞证据强化

**典型输入**

- 单个常规 risk point

**典型输出**

- 推入 `vuln_queue` 的 finding

**可调用工具**

基础工具：

- `list_files`
- `search_code`
- `get_code_window`
- `get_file_outline`
- `get_function_summary`
- `get_symbol_body`
- `locate_enclosing_function`

分析工具：

- `smart_scan`
- `quick_audit`
- `pattern_match`
- `dataflow_analysis`
- `controlflow_analysis_light`
- `logic_authz_analysis`

漏洞队列工具：

- `push_finding_to_queue`
- `is_finding_in_queue`

**与上下游的交接关系**

- 上游：`ReconAgent` 或 bootstrap seed 注入后的 `recon_queue`
- 下游：`VerificationAgent`
- 交接介质：`vuln_queue`

**在当前智能审计中的位置**

- 当前智能审计：通常消费 Recon 发现的风险点，并把确认 finding 推入 `vuln_queue`

### 5.5 `BusinessLogicAnalysisAgent`

**角色定位**

业务逻辑漏洞分析层，处理来自 `business_logic_queue` 的单个业务逻辑风险点。

**执行功能**

- 深挖授权链、对象归属、状态机、金额流转、竞态窗口
- 判断是否形成真实可利用的业务逻辑漏洞
- 把确认 finding 推入统一 `vuln_queue`

**负责范围**

- IDOR
- 权限提升
- 状态机绕过
- 支付 / 金额篡改
- TOCTOU / 竞态类问题

**典型输入**

- 单个 BL risk point

**典型输出**

- 推入 `vuln_queue` 的业务逻辑 finding

**可调用工具**

基础工具：

- `list_files`
- `search_code`
- `get_code_window`
- `get_file_outline`
- `get_function_summary`
- `get_symbol_body`
- `locate_enclosing_function`

漏洞队列工具：

- `push_finding_to_queue`
- `is_finding_in_queue`

**与上下游的交接关系**

- 上游：`BusinessLogicReconAgent`
- 下游：`VerificationAgent`
- 交接介质：统一 `vuln_queue`

**在当前智能审计中的位置**

- 当前智能审计：它始终走业务逻辑双轨，并在统一 `vuln_queue` 前汇合

### 5.6 `VerificationAgent`

**角色定位**

漏洞验证层，对单个 finding 给出更严格的真实性结论，并负责结果持久化。

**执行功能**

- 读取关键函数或代码窗口
- 编写/执行 Harness 或 PoC
- 通过沙箱验证运行时行为
- 收敛 verdict、reachability、evidence、confidence
- 调用 `save_verification_result` 持久化验证结论

**负责范围**

- 动态或半动态验证
- 误报排除
- 结论持久化

**典型输入**

- 单个待验证 finding

**典型输出**

- 已更新 verdict 的 finding
- 持久化后的 verification result

**可调用工具**

基础工具：

- `list_files`
- `search_code`
- `get_code_window`
- `get_file_outline`
- `get_function_summary`
- `get_symbol_body`
- `locate_enclosing_function`

验证工具：

- `sandbox_exec`
- `verify_vulnerability`
- `run_code`
- `create_vulnerability_report`

回写工具：

- `save_verification_result`

**与上下游的交接关系**

- 上游：`AnalysisAgent` 与 `BusinessLogicAnalysisAgent`
- 下游：`ReportAgent`
- 交接介质：`vuln_queue` 消费结果 + 持久化 finding

**在当前智能审计中的位置**

- 当前智能审计：统一消费 `vuln_queue`，负责验证收敛与结果持久化

### 5.7 `ReportAgent`

**角色定位**

报告与二次复审层。它不只是“美化输出”，还会对已验证 finding 做二次代码核对并在必要时修正 finding。

**执行功能**

- 读取代码并再次审查 finding 准确性
- 追踪攻击路径与数据流
- 生成单漏洞 Markdown 详情报告
- 调用 `update_vulnerability_finding` 修正错误字段
- 生成项目级风险评估报告

**负责范围**

- 单漏洞详情报告
- 项目级风险报告
- finding 结构化字段纠偏

**典型输入**

- 单个已验证 finding
- 或全部非误报 finding 的集合

**典型输出**

- `vulnerability_report`
- `project_risk_report`
- 必要时被修正的 finding

**可调用工具**

基础工具：

- `list_files`
- `search_code`
- `get_code_window`
- `get_file_outline`
- `get_function_summary`
- `get_symbol_body`

分析工具：

- `dataflow_analysis`

回写工具：

- `update_vulnerability_finding`

**与上下游的交接关系**

- 上游：`VerificationAgent`
- 下游：任务级 report 展示与 finding 详情展示
- 交接介质：更新后的 `AgentFinding` + task.report

**在当前智能审计中的位置**

- 当前智能审计：共用统一的 report 阶段，负责报告生成与二次复审

## 6. 工具分组速查

### 6.1 基础读码工具

- `list_files`
- `search_code`
- `get_code_window`
- `get_file_outline`
- `get_function_summary`
- `get_symbol_body`
- `locate_enclosing_function`

### 6.2 深度分析工具

- `smart_scan`
- `quick_audit`
- `pattern_match`
- `dataflow_analysis`
- `controlflow_analysis_light`
- `logic_authz_analysis`

## 继续阅读

- 要回到阶段推进和结果沉淀主线：读 [workflow_overview.md](./workflow_overview.md)。
- 要补系统级背景：读 [../architecture.md](../architecture.md)。
- 要统一队列和 finding 术语：回看 [../glossary.md](../glossary.md)。

### 6.3 验证工具

- `run_code`
- `sandbox_exec`
- `verify_vulnerability`
- `create_vulnerability_report`

### 6.4 队列工具

- `push_risk_point_to_queue`
- `push_risk_points_to_queue`
- `push_bl_risk_point_to_queue`
- `push_bl_risk_points_to_queue`
- `push_finding_to_queue`
- `get_queue_status`
- `dequeue_finding`
- `get_recon_risk_queue_status`
- `dequeue_recon_risk_point`
- `peek_recon_risk_queue`
- `clear_recon_risk_queue`
- `is_recon_risk_point_in_queue`
- `get_bl_risk_queue_status`
- `dequeue_bl_risk_point`
- `peek_bl_risk_queue`
- `clear_bl_risk_queue`
- `is_bl_risk_point_in_queue`
- `is_finding_in_queue`

### 6.5 回写工具

- `save_verification_result`
- `update_vulnerability_finding`

## 7. 维护建议

- 新增或移除工具时，优先同步更新本文件和 `workflow_overview.md`，保证“阶段说明”和“工具矩阵”一致。
- 如果 `_initialize_tools()` 中的真实注入发生变化，应以该函数为准更新文档，而不是沿用 prompt 中的旧工具名。
- 若新增新的工作流角色，先补总览表，再按统一模板增加角色章节，避免文档结构失衡。
