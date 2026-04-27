# Argus 源代码漏洞智能审计 AgentFlow 功能需求与实施计划

> 文档版本：v6.4
> 更新日期：2026-04-27
> 适用项目：Argus 当前代码库
> 状态：AgentFlow 新功能开发计划；本文是实施唯一权威文档
> 来源：已吸收《源代码漏洞智能审计平台_需求规格说明书》草案的可执行要求；源规格书不再作为并行需求源保留

## 1. 目标

Argus 智能审计能力采用“Argus 控制面 + AgentFlow 执行面”的实现方式。Argus 继续负责项目、任务、Prompt Skill、系统配置、漏洞详情和报告导出；AgentFlow 负责智能审计执行图、节点调度、并行分析、复核闭环、artifact 产出和结构化结果输出。智能审计与静态审计是两条独立任务链路，智能审计不采用静态审计任务、Opengrep findings 或静态扫描结果作为候选输入。

## 2. 当前基线

| 能力 | 当前触点 | 后续处理 |
| --- | --- | --- |
| 智能任务管理 | `/tasks/intelligent`、`TaskManagementIntelligent.tsx` | 保留，接入 AgentFlow 任务状态 |
| 智能任务详情 | `/agent-audit/:taskId`、`frontend/src/pages/AgentAudit/TaskDetailPage.tsx` | 保留，展示 AgentFlow node DAG |
| 智能任务 API | `backend/src/routes/agent_tasks.rs` | 保留路由，接入 AgentFlow runner |
| 任务状态 | `TaskStateSnapshot.agent_tasks` | 保留为产品主状态 |
| 漏洞模型 | `AgentFindingRecord` | 保留，作为 AgentFlow finding schema 目标 |
| 事件模型 | `AgentEventRecord` | 保留，导入 AgentFlow node/runner 事件 |
| Checkpoint | `AgentCheckpointRecord` | 保留，记录 AgentFlow 阶段状态 |
| Prompt Skill | `/api/v1/skills/*` | 保留，注入 AgentFlow prompt context |
| LLM preflight | `/api/v1/system-config/*` | 保留，用于 agent 可用性预检 |
| Opengrep | 静态任务、规则、finding | 保留为独立静态审计能力；不作为智能审计输入或候选来源 |

当前智能审计执行面尚未实现。启动智能审计任务时应明确进入 failed 状态并返回 AgentFlow 未配置错误；不得静默成功。

## 3. 总体架构

```text
React UI
  /tasks/intelligent
  /agent-audit/:taskId
  /finding-detail/:source/:taskId/:findingId
        |
        v
Rust Axum backend
  /api/v1/agent-tasks/*
  /api/v1/skills/*
  /api/v1/system-config/*
        |
        v
backend/src/runtime/agentflow
  build_input()
  render_pipeline()
  validate_pipeline()
  run_pipeline()
  import_result()
        |
        v
agentflow-runner container
  python >= 3.10
  pinned AgentFlow commit/version
  agentflow validate
  agentflow run --output json/json-summary
        |
        v
AgentFlow Graph
  context_prepare
  scope_recon
  candidate_fanout
  vulnerability_analysis
  verification_loop
  merge_findings
  report
```

### 3.1 需求规格采纳边界

本计划采纳需求规格书中自动化审计、智能体协作、通信可观测、资源控制、动态演化、结果追踪和报告展示等目标，但以 Argus 当前代码库的落地边界执行：

- Argus 是唯一权威控制面、数据面、API 面和 UI 面；项目、任务、finding、checkpoint、event、report 的最终状态必须进入 Argus 后端模型。
- AgentFlow、agent 容器和 Scratchboard 只作为执行面、事件日志和 artifact 通道；不得替代 Argus 数据库或直接成为前端数据源。
- P1 只交付固定 AgentFlow pipeline 的最小闭环，但必须输出可映射为 `env-inter`、`vuln-reasoner`、`audit-reporter` 三类角色的 node metadata/events。
- P2 交付智能审计独立结果归一、risk lifecycle 和废弃原因码归一。
- P3 才允许 HarnessOpt 风格动态演化，且只允许后端预定义规则表执行受控动作。
- 规格中的容器资源、Scratchboard/Jinja、Docker 生命周期和实时可观测性要求必须转化为第 10、11 节中的验收项。
- 需求规格书中的论文调研、部署草案和研究型 API 只作为设计来源；后续实现以本文的 Argus 原生路由、状态模型、runner 合同和验收项为准。

### 3.2 端到端交付闭环

本计划执行完成后的 P1 用户承诺是：用户只需要在 Argus 中配置可用模型 API，选择已导入项目和审计范围，启动智能审计任务，最后即可在 Argus 中看到智能审计报告和漏洞详情。

闭环路径：

1. 用户在系统配置或智能审计创建弹窗中配置模型 API，包括 provider、base URL、model、apiKey 和可选 custom headers。
2. Argus 后端通过 `test-llm` 和 `agent-preflight` 验证模型配置、凭据、模型可达性和 AgentFlow runner 前置条件。
3. 用户在 `/tasks/intelligent` 选择项目、目标文件或排除模式、目标漏洞类型、验证等级、Prompt Skill 和资源限制。
4. 后端创建 `AgentTaskRecord`，保存项目与审计范围快照；启动时根据该快照生成 runner input，不读取静态审计任务或 Opengrep findings。
5. AgentFlow runner 执行固定 P1 pipeline，输出 Argus 约定 JSON。
6. 后端导入 events、checkpoints、agent tree、findings 和 report summary。
7. 前端在 `/tasks/intelligent` 展示任务状态，在 `/agent-audit/:taskId` 展示执行图、报告摘要和发现列表。
8. 用户点击任一智能审计 finding，进入统一漏洞详情页 `/finding-detail/agent/:taskId/:findingId` 查看证据、影响、修复建议和 AgentFlow 来源。

P1 不要求单独建设报告详情页或 PDF 导出页；报告 MVP 可以先由 `/agent-audit/:taskId` 的报告摘要、finding 列表和统一漏洞详情页共同承载。

## 4. 功能需求

### 4.1 创建智能审计任务

用户应能在 Argus 中创建智能审计任务，并配置：

- 模型 API 配置状态；若未配置或未通过测试，创建弹窗应引导用户完成配置，启动时后端仍必须重新 preflight。
- 项目。
- 目标文件或排除模式。
- 目标漏洞类型。
- 验证等级。
- 是否启用 Prompt Skill。
- 最大迭代次数、超时和资源限制。

后端必须在任务创建时保存完整审计范围快照，避免后续配置变更影响已创建任务。

智能审计创建表单不得包含静态审计任务选择器，也不得提交静态 finding 候选字段。后端必须拒绝以下字段出现在创建、启动或 runner import 输入中：

- `static_task_id`
- `opengrep_task_id`
- `candidate_finding_ids`
- `static_findings`
- `bootstrap_task_id`
- `bootstrap_candidate_count`
- `candidate_findings`
- 任何把静态审计、Opengrep、Bandit、Gitleaks、Phpstan 或 PMD finding 作为智能审计候选的 payload。

### 4.2 启动智能审计任务

启动任务时，后端应：

1. 加载任务和项目快照。
2. 加载并脱敏解析当前有效模型 API 配置。
3. 执行 `agent-preflight`，确认模型 API、凭据、模型、runner、pipeline 和资源预算可用。
4. 生成 AgentFlow runner input。
5. 渲染或选择 pipeline。
6. 执行 runner preflight。
7. 调用 runner。
8. 导入 events、checkpoints、agent tree、findings 和 report。
9. 将失败原因记录为用户可读错误事件。

运行时不可用、pipeline validate 失败、凭据缺失、runner 异常退出或输出无法解析时，任务必须进入 failed。

### 4.3 查看任务进度

Argus 前端应展示：

- 当前阶段、当前步骤、进度比例。
- AgentFlow node DAG。
- 每个 node 的状态、耗时、token、工具调用和输出摘要。
- 事件日志。
- Checkpoint 列表。
- 发现的漏洞统计和验证状态。

前端不得假设固定 node 数量或固定角色名称。

### 4.4 查看漏洞详情

智能审计发现应复用 Argus 统一漏洞详情体验：

- 文件路径、行号、代码片段。
- 漏洞类型、严重级别、置信度。
- 可达性、真实性、验证结论。
- 证据、影响、修复建议。
- AgentFlow node 来源和 artifact 引用。
- 智能审计自身执行图、node 来源和 artifact 引用。

### 4.5 导出报告

报告应支持 Markdown、PDF 或 Argus 现有导出格式，并包含：

- 任务摘要。
- 执行图摘要。
- 高风险发现列表。
- 每个漏洞的证据、影响和修复建议。
- 智能审计执行范围。
- 运行诊断和失败原因。

P1 的最低要求不是文件导出，而是用户在 Argus 内可见报告：`/agent-audit/:taskId` 展示报告摘要和高风险发现列表，每个 finding 通过统一漏洞详情页查看完整证据。Markdown、PDF 或其他导出格式可放入 P2。

### 4.6 端到端用户路径

P1 必须支持以下用户路径：

1. 用户进入系统配置，填写模型 API 信息并点击连接测试；成功后配置保存为 Argus 后端可读取的 LLM effective config。
2. 用户进入 `/tasks/intelligent`，点击创建智能审计任务。
3. 创建弹窗展示模型 API 状态；若未通过测试，可在弹窗中跳转或快速配置，但最终启动仍以后端 preflight 为准。
4. 用户选择一个已导入项目，设置审计范围、目标文件、排除模式、漏洞类型、验证等级和 Prompt Skill。
5. 用户创建并启动任务；如果模型 API 或 runner 不可用，任务进入 failed 并展示中文可读错误。
6. 任务运行中，用户可在任务列表和任务详情页看到阶段、事件、checkpoint、执行图和诊断。
7. 任务完成后，用户在 `/agent-audit/:taskId` 看到报告摘要、漏洞统计和发现列表。
8. 用户点击漏洞项进入 `/finding-detail/agent/:taskId/:findingId`，复用统一漏洞详情页查看证据、影响和修复建议。

该路径是后续代码实施的 P1 完成定义；如果该路径不能跑通，则不得宣称 AgentFlow 智能审计 P1 完成。

## 5. 后端实施需求

### 5.1 新增模块

新增 `backend/src/runtime/agentflow`：

| 文件 | 职责 |
| --- | --- |
| `mod.rs` | 导出 AgentFlow runtime |
| `contracts.rs` | runner input/output、node summary、finding schema |
| `pipeline.rs` | 渲染或选择 AgentFlow pipeline |
| `runner.rs` | 调用 runner 容器或本地命令 |
| `importer.rs` | 将 runner output 导入 `AgentTaskRecord` |
| `preflight.rs` | validate、doctor、凭据和资源检查 |

### 5.2 Runner Input

Runner input 至少包含：

```json
{
  "task_id": "string",
  "project_id": "string",
  "project_path": "string",
  "audit_scope": {},
  "target_files": [],
  "exclude_patterns": [],
  "target_vulnerabilities": [],
  "verification_level": "string",
  "prompt_skill_runtime": {},
  "llm_effective_config": {},
  "output_dir": "string",
  "limits": {
    "timeout_seconds": 0,
    "max_iterations": 0,
    "max_parallel_nodes": 0
  }
}
```

### 5.3 Runner Output

Runner output 必须为 Argus 可解析 JSON：

```json
{
  "runtime": "agentflow",
  "run_id": "string",
  "status": "completed|failed|cancelled",
  "agent_tree": [],
  "events": [],
  "findings": [],
  "checkpoints": [],
  "report": {
    "summary": "string",
    "sections": []
  },
  "diagnostics": {}
}
```

要求：

- `findings` 可映射到 `AgentFindingRecord`。
- `events` 可映射到 `AgentEventRecord`，并保持递增 sequence。
- `checkpoints` 可映射到 `AgentCheckpointRecord`。
- `agent_tree` 从 AgentFlow node DAG 生成。
- 失败输出必须包含中文可读错误，不得静默成功。

### 5.3.1 Runner Output 完整字段约束

P1 runner output 必须通过 `backend/agentflow/schemas/runner_output.schema.json` 校验后才能导入。最小结构：

```json
{
  "runtime": "agentflow",
  "run_id": "uuid-or-stable-string",
  "task_id": "string",
  "topology_version": 1,
  "status": "completed|failed|cancelled",
  "started_at": "ISO8601",
  "completed_at": "ISO8601|null",
  "agent_tree": [],
  "events": [],
  "findings": [],
  "checkpoints": [],
  "report": {
    "summary": "string",
    "sections": [],
    "statistics": {},
    "discard_summary": {},
    "timeline": []
  },
  "diagnostics": {
    "stdout_tail": "string",
    "stderr_tail": "string",
    "reason_code": "string|null",
    "message": "string|null"
  },
  "feedback_bundle": {},
  "artifact_index": []
}
```

导入失败条件：

- `runtime` 不是 `agentflow`。
- `task_id` 与 Argus 任务不一致。
- `events[].sequence` 不递增或重复。
- event 缺少 `role`、`node_id`、`type`、`timestamp`、`visibility` 或 `correlation_id`。
- `visibility` 不属于 `ALL|ORCHESTRATOR_ONLY|AGENTS_ONLY`。
- finding 缺少 title、severity、vulnerability_type、confidence、source location 或 evidence。
- artifact 路径不是任务隔离输出目录下的规范化相对路径。
- output 含明文 apiKey、Authorization、Cookie、customHeaders、宿主机敏感路径或 Docker socket 路径。

任一失败条件命中时，任务必须进入 `failed`，并写入 `runner_output_invalid` 事件、`import_failed` checkpoint 和中文可读 `error_message`。

### 5.3.2 Importer 映射矩阵

`backend/src/runtime/agentflow/importer.rs` 必须按下表导入 runner output：

| Runner 字段 | Argus 目标 | 说明 |
| --- | --- | --- |
| `runtime` | `AgentTaskRecord.audit_scope.agentflow.runtime` 或新增 `runtime` 字段 | P1 固定为 `agentflow` |
| `run_id` | `AgentTaskRecord.audit_scope.agentflow.run_id` 或新增 `run_id` 字段 | `/agent-audit/:taskId` 诊断展示和 artifact 索引用 |
| `topology_version` | `AgentTaskRecord.audit_scope.agentflow.topology_version`、event/checkpoint metadata | P1 默认为 1；P3 拓扑变更递增 |
| `status` | `AgentTaskRecord.status` | `completed|failed|cancelled` 映射到 Argus 状态 |
| `started_at` / `completed_at` | `AgentTaskRecord.started_at` / `completed_at` | 缺失时以后端导入时间兜底 |
| `agent_tree[]` | `AgentTaskRecord.agent_tree` | node 必须含 `node_id`、`role`、`status`、`parent_node_id`、`findings_count`、`duration_ms` |
| `events[]` | `AgentTaskRecord.events` | event metadata 保留 `runtime`、`run_id`、`topology_version`、`node_id`、`role`、`correlation_id`、`visibility`、`artifact_refs` |
| `checkpoints[]` | `AgentTaskRecord.checkpoints` | checkpoint metadata 保留资源、heartbeat、阶段状态和 topology 信息 |
| `findings[]` | `AgentTaskRecord.findings` | finding 必须可被 `/finding-detail/agent/:taskId/:findingId` 渲染 |
| `report.summary` | `AgentTaskRecord.report` | P1 生成 Markdown 摘要，完整结构保留到 report snapshot metadata |
| `report.sections[]` | finding `report` 或 task report snapshot | 用于后续 Markdown/PDF 导出 |
| `report.statistics` | `AgentTaskRecord.*_count` 和 summary API | 导入后刷新聚合计数 |
| `diagnostics` | `AgentTaskRecord.error_message`、events metadata、checkpoint metadata | stdout/stderr 必须截断脱敏 |
| `feedback_bundle` | `AgentTaskRecord.audit_scope.agentflow.feedback_bundle` 或新增 `feedback_bundle` 字段 | P2/P3 HarnessOpt 诊断输入 |
| `artifact_index[]` | `AgentTaskRecord.audit_scope.agentflow.artifact_index`、event/finding `artifact_refs` | 只允许任务输出目录内相对路径 |

### 5.4 启动流程

`backend/src/routes/agent_tasks.rs::start_agent_task` 目标流程：

1. 加载 `AgentTaskRecord`。
2. 加载项目快照、审计范围和当前有效 LLM 配置。
3. 执行 LLM 和 AgentFlow preflight；缺少 apiKey、模型不可达、runner 不存在或 pipeline validate 失败都必须返回用户可读错误。
4. 生成 AgentFlow input。
5. 调用 `try_agentflow_dispatch`。
6. 成功则导入输出并完成任务。
7. 失败则记录错误事件、checkpoint 和诊断信息。
8. 保存任务快照。

`start_agent_task` 不接受静态审计任务 id，也不从静态 finding 表读取候选数据。

### 5.5 取消与超时

- 用户取消任务时，后端必须终止 runner。
- runner 超时后，任务进入 failed 或 cancelled，并保留诊断。
- 取消和超时都应产生明确事件。
- 临时 artifact 应按任务隔离目录清理或保留可审计索引。

### 5.6 HarnessOpt 演化控制

HarnessOpt 五维空间只作为后端可审计配置模型进入计划：

| 维度 | 含义 | Argus 约束 |
| --- | --- | --- |
| `A` | agent 角色集 | P1 固定三类语义角色；P3 只能从后端模板库添加专家节点 |
| `G` | 通信拓扑 | P1 固定 DAG；P3 只能通过白名单规则调整 fanout/merge 或补充边 |
| `Sigma` | Jinja 消息模式 | 模板由版本化文件或后端内置模板提供，用户不能提交任意模板 |
| `Phi` | 工具绑定 | 工具集由镜像和模板声明决定，LLM 不得生成可执行工具绑定 |
| `Psi` | 协调协议 | 超时、重试、并发和终止条件由 Argus 任务配置及后端规则控制 |

阶段约束：

- P1：不做拓扑 mutation；只记录足够的 node/event/checkpoint 支持后续诊断。
- P2：生成 `feedback_bundle`，记录覆盖率、废弃率、验证通过率、队列积压、耗时和失败原因。
- P3：后端根据静态规则表执行 `add_expert`、`scale_out`、`fix_config` 三类动作；LLM 只能输出诊断标签，不得输出 Docker 命令、Compose 片段或任意代码。

### 5.7 动态节点生命周期

P3 动态节点必须由后端统一管理生命周期：

1. 模板注册：专家节点镜像、资源预算、工具集、允许位置和最大副本数在后端模板库登记。
2. 创建或扩缩：由规则表触发，后端通过 Docker API 或 Compose 适配层创建容器并写入 `topology_change` 事件。
3. 健康检查：结合 Docker 状态、heartbeat 事件和超时策略判定节点健康。
4. 销毁：会话结束或规则判定不再需要时停止动态节点；Scratchboard 和 artifact 仍按任务索引保留或清理。
5. 禁止项：不得删除 `env-inter`、`vuln-reasoner`、`audit-reporter` 三类基础角色；不得修改网络边界或挂载宿主机敏感目录。

### 5.8 端到端代码交付清单

P1 实施时至少覆盖以下代码面：

| 模块 | 必须完成的能力 |
| --- | --- |
| `backend/src/routes/system_config.rs` | 保存、读取、测试模型 API；`test-llm` 和 `agent-preflight` 能区分缺凭据、模型不可达和配置非法 |
| `backend/src/routes/agent_tasks.rs` | 创建、启动、列表、详情、finding 详情；启动时强制 LLM/runner preflight；不接受静态任务候选 |
| `backend/src/runtime/agentflow/contracts.rs` | 定义 runner input/output、report、finding、event、checkpoint 和诊断 schema |
| `backend/src/runtime/agentflow/preflight.rs` | 校验模型配置、runner 可执行性、pipeline validate、输出目录和资源预算 |
| `backend/src/runtime/agentflow/runner.rs` | 调用 AgentFlow runner 或 P1 schema-compatible smoke runner，并收集脱敏 stdout/stderr |
| `backend/src/runtime/agentflow/importer.rs` | 将 runner JSON 导入 `AgentTaskRecord`、`AgentFindingRecord`、events、checkpoints 和 report summary |
| `backend/src/db/task_state.rs` | 持久化智能审计 task/finding/event/checkpoint/report 所需字段，保证统一漏洞详情所需字段齐备 |
| `frontend/src/components/system/SystemConfig.tsx` | 支持模型 API 保存、测试和错误展示 |
| `frontend/src/components/scan/CreateProjectScanDialog.tsx` | 在智能审计创建路径展示模型 API 状态和快速配置入口 |
| `/tasks/intelligent` 页面 | 创建项目级智能审计任务，不展示静态任务选择器 |
| `/agent-audit/:taskId` 页面 | 展示 AgentFlow 执行图、报告摘要、漏洞统计、finding 列表和失败诊断 |
| `/finding-detail/agent/:taskId/:findingId` 页面 | 作为 P1 漏洞报告详情入口，展示智能审计 finding 的证据、影响、修复建议和 AgentFlow 来源 |

如果真实 AgentFlow CLI 集成在 P1 初期不可用，允许先接入受控的 schema-compatible smoke runner，但该 runner 必须走同一 input/output schema、preflight、importer、report 和统一漏洞详情链路；不得绕过后端状态模型或前端真实页面。

### 5.9 P1 Argus 原生实现合同

P1 不新增第二套编排后端 API，不暴露规格书中的 `/api/agents/*` 研究型接口。所有可见状态都落在 Argus 既有 `/api/v1/agent-tasks/*`、`/api/v1/system-config/*` 和统一 finding 详情路由上。

#### 5.9.1 `system_config.rs` preflight 合同

`/api/v1/system-config/agent-preflight` 必须从当前 LLM-only 检查扩展为：

| 检查 | 失败 reason_code | 前端行为 |
| --- | --- | --- |
| 未保存专属配置 | `default_config` | 引导保存模型 API 配置 |
| provider/model/baseUrl/apiKey 缺失 | `missing_fields` | 标出缺失字段 |
| 自定义 header 非法 | `invalid_custom_headers` | 阻止启动 |
| 模型端点不可达或认证失败 | `model_unreachable` / `auth_failed` | 展示可读错误 |
| runner 镜像或命令不可用 | `runner_missing` | 任务不可启动 |
| pipeline validate 失败 | `pipeline_invalid` | 展示 validate 摘要 |
| 输出目录不可写或路径非法 | `output_dir_unwritable` | 阻止启动 |
| 资源预算不足 | `resource_unavailable` | 排队或拒绝启动 |

preflight 返回体必须继续兼容现有 `ok/stage/message/reason_code/missing_fields/effective_config/saved_config`，新增字段放入 `metadata`，不得回传明文 apiKey。

#### 5.9.2 `agent_tasks.rs` 启动合同

`start_agent_task` 当前的 AgentFlow 未配置失败路径是正确基线。接入实现时只能替换为以下顺序：

1. 验证请求不含第 4.1 节禁止字段。
2. 加载任务、项目、审计范围快照和 LLM effective config。
3. 调用 agent preflight；失败则进入 `failed` 并写入 `preflight_failed` event。
4. 调用 `runtime::agentflow::build_input` 生成 runner input，并记录 input digest。
5. 调用 `runtime::agentflow::run_pipeline`。
6. 调用 `runtime::agentflow::import_result`。
7. 刷新 task 聚合计数、report summary、agent tree 和 checkpoint。
8. 保存 `TaskStateSnapshot`。

任何 panic、timeout、cancel、runner exit code 非 0、schema invalid、import invalid 都必须落成失败事件和 checkpoint，不得只返回 HTTP 错误而不保存任务状态。

#### 5.9.3 `task_state.rs` 状态吸收合同

实现时优先通过 `serde(default)` 增加可选字段，避免破坏已有快照；如果短期不加字段，必须按下表写入现有 `audit_scope`、`metadata` 或 `report`。

| Argus 结构 | P1 必须保存的信息 | 推荐落点 |
| --- | --- | --- |
| `AgentTaskRecord` | `runtime`、`run_id`、`topology_version`、project/scope snapshot、runner input digest、report snapshot、artifact index、feedback_bundle | 新增可选字段；或 `audit_scope.agentflow.*` |
| `AgentEventRecord` | envelope、message type、node_id、role、correlation_id、visibility、payload summary、artifact_refs | `metadata` |
| `AgentFindingRecord` | source node/role、artifact_refs、risk lifecycle status、discard reason/stage、confidence_history、data_flow、impact、remediation、verification conclusion | 新增可选字段；或 `trigger_flow.agentflow` / `poc_trigger_chain.agentflow` / `report` |
| `AgentCheckpointRecord` | node state、heartbeat、resource usage、stage timing、topology_version、feedback_bundle ref | `metadata` / `state_data` |
| `agent_tree` | DAG node id、role、parent/children、status、duration、tokens、tool_calls、findings count | `AgentTaskRecord.agent_tree` |

P1 接口返回必须保持现有 frontend 类型基本兼容；新增字段允许前端渐进消费。

#### 5.9.4 禁止静态输入测试合同

后端测试必须覆盖：

- 创建智能审计任务时包含 `static_task_id` / `opengrep_task_id` / `static_findings` / `candidate_finding_ids` / `bootstrap_task_id` 返回 `400 Bad Request`。
- 启动智能审计任务时，已有任务 `audit_scope` 中如含这些字段，任务进入 `failed`，并写入 `forbidden_static_input` event。
- runner output 如包含 `static_findings` 或 `candidate_origin=opengrep|static`，importer 拒绝导入。

前端测试必须覆盖：

- 智能审计创建弹窗不渲染静态审计任务选择器。
- `/tasks/intelligent` 的 create payload 不包含禁止字段。
- 旧的 bootstrap/Opengrep metadata 如果存在，只作为历史诊断显示，不作为任务启动输入或 finding 候选来源。

## 6. AgentFlow Runner 需求

新增 `agentflow-runner` 镜像或等价受控脚本：

- 固定 AgentFlow commit、版本或镜像 digest。
- 保留 license 信息。
- 不使用动态安装脚本作为生产路径。
- 支持 `agentflow validate`。
- 支持 `agentflow run`。
- 输出 Argus 约定 JSON。
- 将 `.agentflow/runs/<run_id>` artifacts 放入任务隔离输出目录。
- stdout/stderr 需要截断、脱敏后进入诊断。

建议新增：

```text
backend/agentflow/
  pipelines/
    intelligent_audit.py
  prompts/
    system_context.md
    finding_schema.md
  schemas/
    runner_input.schema.json
    runner_output.schema.json
```

### 6.1 Scratchboard 与 Jinja 通信契约

runner 或 agent 容器输出的每条可观测事件都必须带统一 envelope，后端导入后再推送给前端：

```json
{
  "session_id": "string",
  "run_id": "string",
  "topology_version": 1,
  "node_id": "string",
  "role": "env-inter|vuln-reasoner|audit-reporter|expert",
  "type": "clue|analysis|validation|discard|supplementary_request|supplementary_response|control|heartbeat|topology_change",
  "correlation_id": "string",
  "sequence": 1,
  "timestamp": "2026-04-27T00:00:00Z",
  "visibility": "ALL|ORCHESTRATOR_ONLY|AGENTS_ONLY",
  "payload": {}
}
```

要求：

- `sequence` 在同一 `run_id` 内递增，导入失败时任务进入 failed 并记录中文错误。
- `visibility=AGENTS_ONLY` 的记录不得进入前端；`ALL` 和 `ORCHESTRATOR_ONLY` 可被后端用于状态、诊断和审计。
- Jinja 模板只能引用已声明 node、session、topology 和 Scratchboard 字段；pipeline validate 必须在 runner 启动前检查引用合法性。
- 前端只能消费 Argus 后端导入后的 events/SSE，不直接读取 Scratchboard、Redis、JSONL 或 `.agentflow` 目录。

#### 6.1.1 消息类型与 Argus 吸收规则

| type | payload 最小字段 | Argus 吸收规则 |
| --- | --- | --- |
| `clue` | `clue_id`、`file_path`、`line_start`、`risk_type`、`confidence`、`code_snippet` | 写入 `AgentEventRecord(event_type=clue)`；必要时形成 pending finding |
| `analysis` | `clue_id`、`cwe_id`、`impact`、`data_flow`、`confidence`、`remediation` | 更新 finding 分析字段和 confidence history |
| `validation` | `clue_id`、`status`、`poc_result`、`fingerprint`、`evidence` | 更新 finding `status/is_verified/verdict/verification_evidence` |
| `discard` | `clue_id`、`stage`、`reason_code`、`confidence_change`、`reason_description` | 更新 finding 生命周期为 `DISCARDED`，保留废弃原因 |
| `supplementary_request` | `clue_id`、`needs[]`、`context` | 写入 event/checkpoint，前端展示为补充证据请求 |
| `supplementary_response` | `clue_id`、`evidence[]`、`timestamp` | 写入 event，并附加到 finding evidence |
| `control` | `target_threads`、`cpu_target`、`action` | P1 只记录；P3 才允许触发资源调整 |
| `heartbeat` | `agent_id`、`status`、`current_task`、`timestamp` | 写入 checkpoint metadata，驱动节点健康展示 |
| `topology_change` | `action`、`target`、`topology_version`、`reason_code` | P3 写入 event/checkpoint，并刷新 `agent_tree` |

`AGENTS_ONLY` 消息不得进入前端 API 响应，但导入器可用其更新内部 checkpoint 或诊断；`ORCHESTRATOR_ONLY` 可进入 backend 状态，不直接展示原始 payload。

### 6.2 Runner 安全输出与脱敏

- stdout/stderr 进入诊断前必须按大小截断并做 apiKey、customHeaders、token、Authorization、Cookie 脱敏。
- artifacts、events、reports 中不得出现明文凭据或宿主机敏感路径。
- runner output 必须先经过 JSON schema 校验，再导入 `AgentTaskRecord`。
- schema 校验失败、事件 sequence 断裂、role 缺失、visibility 非法或 payload 无法解析时，任务必须 failed。
- stdout/stderr tail 默认各保留最后 64 KB；超过限制必须截断并写入 `truncated=true`。
- artifact index 只记录相对路径、类型、大小、sha256、producer node 和 created_at，不记录宿主机绝对路径。

## 7. Pipeline 需求

### 7.1 基础节点

| 节点 | 类型 | 职责 |
| --- | --- | --- |
| `context_prepare` | python 或 shell | 汇总项目路径、目标文件、Prompt Skill 和任务范围快照 |
| `scope_recon` | agent | 只读理解项目结构、入口、调用链和风险面 |
| `candidate_fanout` | fanout | 按目标文件、模块、目标漏洞类型或项目结构分片 |
| `vulnerability_analysis` | agent | 并行分析漏洞真实性、可达性、影响 |
| `verification_loop` | agent 或 graph loop | 复核风险线索，证据不足时返回补充分析 |
| `merge_findings` | merge | 去重并按 schema 归一化 finding |
| `report` | agent | 生成中文报告、证据、危害和修复建议 |

### 7.2 Pipeline 生成策略

P1 固定一条 `intelligent_audit.py`。P2 以后支持：

- 按项目语言选择节点模板。
- 按目标文件、模块、目标漏洞类型和项目规模 fanout。
- 按文件数量和风险等级调整并行度。
- 按用户验证等级启用更严格复核。

### 7.3 初始化三节点与动态节点边界

P1 的固定 pipeline 可以由多个 AgentFlow node 实现，但对 Argus 必须暴露三类语义角色：

| 规格角色 | P1 映射 | P3 容器化方向 |
| --- | --- | --- |
| `env-inter` | `context_prepare`、`scope_recon`、任务范围整理和补充证据采集事件 | 独立环境交互容器，负责编译、测试、覆盖率、Sanitizer 和补充扫描 |
| `vuln-reasoner` | `candidate_fanout`、`vulnerability_analysis`、`verification_loop` | 可 fan-out 的漏洞推理容器或专家组合 |
| `audit-reporter` | `merge_findings`、`report`、诊断聚合事件 | 独立报告容器，负责简报、废弃说明、完整报告和 `feedback_bundle` |

执行要求：

- P1 不要求真实拆成三个容器，但 `agent_tree`、events、checkpoints 必须携带 `role`，使 UI 和后端不依赖固定 AgentFlow 内部 node 名。
- P3 才允许将这些角色物化为独立容器和动态专家节点。

### 7.4 演化规则库

P3 只允许使用静态规则表驱动演化：

| 诊断标签 | 条件示例 | 允许动作 | 目标 |
| --- | --- | --- | --- |
| `low-coverage` | 覆盖率低于阈值或长期停滞 | `fix_config` | 调整 `env-inter` 编译、测试或覆盖率配置 |
| `high-discard-rate` | 废弃率高或误报集中 | `add_expert` | 添加 `fp-filter` 或 `taint-expert` |
| `low-poc-success` | PoC 验证通过率低 | `add_expert` | 添加 `poc-expert` 或 `sandbox-expert` |
| `vuln-reasoner-backlog` | 待分析队列积压 | `scale_out` | 扩容 `vuln-reasoner` |
| `compile-slow` | 编译或测试阶段超时 | `scale_out` 或 `fix_config` | 调整 `env-inter` 并发或配置 |

规则表必须包含最大副本数、资源预算、允许拓扑位置和回滚方式。规则未匹配时只记录诊断，不执行容器操作。

## 8. 智能审计独立结果归一

智能审计不采用静态审计任务作为候选，也不读取 Opengrep findings 作为 fanout 输入。Opengrep 和静态审计继续作为 Argus 的独立产品能力存在，但与智能审计任务在创建、启动、执行、结果归一和报告导出上保持解耦。

独立执行方式：

1. 用户创建智能审计任务时，只选择项目、审计范围、目标文件或排除模式、目标漏洞类型、验证等级、Prompt Skill 和资源限制。
2. 后端根据智能审计任务范围生成 runner input，不查询、不绑定、不压缩静态审计任务结果。
3. AgentFlow 根据项目结构、目标文件、目标漏洞类型和运行时反馈进行 fanout。
4. AI 独立分析漏洞真实性、可达性、触发条件、业务影响和误报概率。
5. 智能审计确报、废弃和报告只回写 Argus `AgentFindingRecord` / events / checkpoints / report。
6. 前端统一漏洞详情体验可以同时支持静态审计和智能审计来源，但两类任务结果不互相作为候选或前置条件。

### 8.1 风险点生命周期与废弃原因码

智能审计 risk point 必须归一为 Argus `AgentFindingRecord`，并保留可审计生命周期：

- `RECEIVED` / `ANALYZING` / `VALIDATING` / `CONFIRMED` / `DISCARDED` / `REPORTED` 状态进入 events 或 checkpoints。
- 置信度变化、废弃阶段、废弃原因、来源 node 和 artifact 引用必须可追踪。
- 与需求规格附录 A 对齐，废弃原因码统一采用：

| 前缀 | 阶段 | 示例 |
| --- | --- | --- |
| `E-xxx` | `env-inter` 环境交互阶段 | 编译期消除、模式误触发 |
| `R-xxx` | `vuln-reasoner` 推理阶段 | 数据流安全、长度校验存在 |
| `V-xxx` | 专家验证阶段 | PoC 执行失败、运行时保护 |
| `A-xxx` | `audit-reporter` 审计报告阶段 | 报告聚合、去重或合规过滤类原因 |

旧草案中 `R/A` 前缀含义不一致的写法以后续实现一律按本节为准。

核心废弃原因码：

| 码 | 阶段 | 名称 | 触发场景 | 诊断信号 |
| --- | --- | --- | --- | --- |
| `E-001` | `env-inter` | 编译期消除 | 编译器、类型系统或构建配置已消除风险 | 环境阶段废弃 |
| `E-002` | `env-inter` | 模式误触发 | 代码语义安全但初始线索误触发 | 环境误报高 |
| `R-001` | `vuln-reasoner` | 数据流安全 | 污点路径存在净化或不可达 | 推理废弃率高 |
| `R-002` | `vuln-reasoner` | 长度校验存在 | 上游存在有效边界或长度校验 | 推理废弃率高 |
| `V-001` | 专家验证 | PoC 执行失败 | 沙箱或测试中未触发预期漏洞 | 验证通过率低 |
| `V-002` | 专家验证 | 运行时保护 | ASLR、DEP、StackCanary 或框架保护阻止利用 | 验证通过率低 |

状态转换矩阵：

| 当前状态 | 允许下一状态 | 触发事件 |
| --- | --- | --- |
| `RECEIVED` | `ANALYZING`、`DISCARDED` | `clue` 接收；env-inter 废弃 |
| `ANALYZING` | `VALIDATING`、`DISCARDED` | `analysis` 完成；vuln-reasoner 废弃 |
| `VALIDATING` | `CONFIRMED`、`DISCARDED` | `validation` 通过；专家验证废弃 |
| `CONFIRMED` | `REPORTED` | `report` 聚合 |
| `DISCARDED` | `REPORTED` | 废弃说明进入报告 |
| `REPORTED` | 终态 | 无 |

非法倒退或跨越状态必须作为 importer 校验错误处理，除非事件 metadata 中明确 `override_reason=manual_review`。

### 8.2 报告与统一漏洞详情 MVP

P1 报告 MVP 由三部分组成：

1. `AgentTaskRecord.report` 或等价 report snapshot 保存任务级摘要、执行范围、风险统计、高风险 finding 索引和失败诊断。
2. `AgentFindingRecord` 保存每个漏洞的标题、类型、严重级别、置信度、文件位置、证据、影响、修复建议、验证结论、来源 node 和 artifact 引用。
3. 前端 `/agent-audit/:taskId` 展示 report summary 与 finding 列表，并将每个 finding 链接到 `/finding-detail/agent/:taskId/:findingId`。

统一漏洞详情页是 P1 的漏洞报告详情承载页。该页必须能展示智能审计 finding 的完整信息，并能标识来源为 AgentFlow / 智能审计执行图。专用报告页面、Markdown/PDF 导出、按章节折叠报告和批量下载可作为 P2 增强，但不得阻塞 P1 的“用户可看到漏洞报告”闭环。

P1 统一详情最低字段：

| 展示区域 | 必需字段 |
| --- | --- |
| 标题与等级 | `title`、`display_title`、`severity`、`vulnerability_type`、`cwe_id` |
| 代码位置 | `file_path`、`line_start`、`line_end`、`code_snippet`、`context_start_line`、`context_end_line` |
| 证据 | `verification_evidence`、`ai_explanation`、event `artifact_refs` |
| 影响 | `description_markdown`、`impact` metadata、`flow_call_chain` |
| 修复 | `suggestion`、`fix_code`、`remediation` metadata |
| 验证 | `status`、`is_verified`、`verdict`、`confidence`、`confidence_history` |
| AgentFlow 来源 | `source_role`、`source_node_id`、`run_id`、`topology_version`、`artifact_refs` |

`/agent-audit/:taskId` 报告摘要必须包含执行摘要、已确认漏洞、废弃风险点汇总、覆盖或扫描范围、阶段时间线和诊断数据。若 finding 为空，报告也必须展示“未发现可确认漏洞”或失败诊断，而不是空白页面。

## 9. 前端需求

前端不重做产品结构，只做 AgentFlow 语义对齐：

- 系统配置页和智能审计创建弹窗必须能表达模型 API 已配置、测试中、测试成功、测试失败和需要重新配置的状态。
- `/tasks/intelligent` 继续作为智能审计任务管理页。
- `/tasks/intelligent` 的创建流程只选择项目和智能审计范围，不展示静态审计任务选择器。
- `/agent-audit/:taskId` 继续作为智能审计任务详情页。
- Agent 树展示动态 AgentFlow node DAG。
- 运行时标签统一使用 “AgentFlow” 或 “智能审计执行图”。
- 如果任务失败，展示 validate、runner、credential、pipeline 的具体失败原因。
- 不在前端直接调用 `agentflow serve`。
- 漏洞报告 MVP 先由 `/agent-audit/:taskId` 的报告摘要和 `/finding-detail/agent/:taskId/:findingId` 的统一漏洞详情页承载。

需要重点检查：

- `frontend/src/pages/AgentAudit/TaskDetailPage.tsx` 是否能接受动态 node 数。
- 任务详情统计是否能接受动态 node 状态。
- 事件日志是否能展示 node id、agent kind、artifact path。
- 漏洞详情和项目详情是否继续复用统一 finding 展示。

### 9.1 实时事件与可观测性展示

前端实时能力必须经由 Argus 后端导入后的事件和 SSE：

- `/agent-audit/:taskId` 展示 node DAG、`topology_version`、role、node 状态、heartbeat、资源摘要、事件日志和 artifact 引用。
- `/tasks/intelligent` 展示任务运行态、失败原因、最近阶段和实时简报状态。
- 废弃风险点按 `reason_code` 分组展示，并能跳转到统一漏洞详情或废弃说明。
- SSE 断开、runner validate 失败、credential 缺失、pipeline 错误和 schema 导入失败必须显示为用户可读错误。
- 前端不得假设固定 node 数量、固定角色名称或固定拓扑深度。

## 10. 安全与隔离

- runner 只能挂载当前任务项目目录、必要 prompt/config 和输出目录。
- 用户不能提交任意 pipeline path。
- `agentflow serve` 不作为生产默认服务暴露。
- AgentFlow remote target 默认关闭，启用必须管理员显式配置。
- apiKey/customHeaders 不写入 artifacts、报告、events。
- artifacts 下载必须经 Argus 后端鉴权和路径规范化。
- runner stdout/stderr 必须截断并脱敏后入库。
- runner 输出 JSON 必须经过 schema 校验。
- 任务目录必须防止路径穿越。

### 10.1 Docker 与资源隔离约束

- 项目源码默认只读挂载；需要构建写入时必须写入任务隔离 workspace，不得写回原项目目录。
- 输出、Scratchboard、runner artifacts 和临时文件必须按 `task_id/run_id` 隔离。
- agent 容器默认只加入内部网络；只有 Argus 后端和前端按现有部署边界暴露服务。
- Docker socket 访问只允许 Argus 后端或受控 runner 管理面使用，agent 节点不得直接挂载宿主机 Docker socket。
- AgentFlow remote target 默认关闭；SSH/EC2/ECS 类远程能力必须作为管理员显式配置和单独安全评审项。
- P1 runner 可作为单容器或本地受控命令执行；P3 动态专家节点才允许使用 Docker API/Compose scale。
- 容器心跳超过 180 秒未更新时判定节点异常；P1 记录失败，P3 可按规则重启。
- OOM kill、exit code 非 0、健康检查失败必须写入 `runner_failed` event 和 `failed` checkpoint。
- 会话完成后默认保留 artifact index 与报告，清理可重建临时 workspace；完整清理必须可审计。

### 10.2 资源预算

后续实现必须以单机 32GB 内存、20 核 CPU 的默认部署为约束：

| 组件 | CPU | 内存 | 磁盘 | 镜像 |
| --- | --- | --- | --- | --- |
| `env-inter` | 4 核 | 4 GB | 20 GB | <= 2 GB |
| `vuln-reasoner` | 8 核 | 4 GB | 4 GB | <= 2 GB |
| `audit-reporter` | 1 核 | 1 GB | 4 GB | <= 2 GB |
| expert 节点 | 2-4 核 | 2 GB | 4 GB | <= 2 GB |
| frontend | 2 核 | 1 GB | 4 GB | <= 2 GB |

验收时必须确认默认并发不会超过机器资源预算；当剩余资源不足时应排队或拒绝扩容，而不是继续启动新节点。

运行阈值：

| 指标 | 阈值 | P1 行为 | P3 行为 |
| --- | --- | --- | --- |
| CPU 使用率 | > 85% 持续 2 分钟 | 记录 warning，限制新任务启动 | 降低线程或 scale_out |
| 内存使用率 | > 90% 持续 1 分钟 | 队列化或拒绝启动 | 队列化、重试或迁移 |
| 磁盘使用率 | > 85% | 阻止 runner 启动 | 清理旧 artifact 后重试 |
| 心跳超时 | > 180 秒 | 任务 failed | 按规则重启或替换节点 |
| GPU 显存 | 默认不启用 | 不检查 | 启用本地推理时单独验收 |

本地 GPU 推理默认关闭。只有管理员显式启用并完成 NVIDIA runtime、模型显存预算和数据合规评审后，才允许使用 24GB 显存路径；该能力不得阻塞 P1 外部模型 API 模式。

## 11. 验收标准

### 11.1 后端验收

建议命令：

```bash
cargo test --manifest-path backend/Cargo.toml agentflow
cargo test --manifest-path backend/Cargo.toml agent_tasks
```

覆盖：

- 模型 API 配置保存、读取和脱敏。
- `test-llm` / `agent-preflight` 成功、缺凭据、模型不可达和配置非法。
- 缺少或未通过模型 API preflight 时，智能审计任务启动失败且错误可读。
- AgentFlow input 生成。
- runner preflight 成功和失败。
- runner 成功输出导入。
- runner 失败输出导入。
- cancel 终止 runner。
- findings/events/checkpoints/report 聚合。
- agent finding 详情接口返回统一漏洞详情所需字段。
- 输出 schema 校验失败时任务 failed。
- 智能审计创建和启动 payload 不包含静态审计任务 id 或静态 finding 候选字段。
- 禁止字段 `static_task_id`、`opengrep_task_id`、`candidate_finding_ids`、`static_findings`、`bootstrap_task_id` 在 create/start/import 路径均被拒绝或失败落库。
- importer mapping 覆盖 `runtime/run_id/topology_version/events/findings/checkpoints/report/diagnostics/feedback_bundle/artifact_index`。
- 风险点状态转换非法时任务 failed，并产生 `invalid_lifecycle_transition` 事件。

### 11.2 Runner 验收

```bash
docker compose build agentflow-runner
docker compose run --rm agentflow-runner agentflow --help
docker compose run --rm agentflow-runner agentflow validate /app/backend/agentflow/pipelines/intelligent_audit.py
```

验收：

- runner 可构建。
- AgentFlow CLI 可执行。
- pipeline 可 validate。
- 缺凭据或 validate 失败时任务 failed。
- runner output 通过 JSON schema 校验。
- runner output 含非法 visibility、断裂 sequence、明文凭据或越界 artifact path 时导入失败。
- schema-compatible smoke runner 与真实 AgentFlow runner 使用同一 input/output schema。

### 11.3 前端验收

```bash
pnpm --dir frontend test:node -- agent
pnpm --dir frontend type-check
pnpm --dir frontend lint
```

覆盖：

- 系统配置或快速配置可保存、测试并展示模型 API 状态。
- 创建智能审计任务 payload 不破坏。
- 创建智能审计任务只需要项目和智能审计范围，不需要静态审计任务。
- 任务详情展示动态 AgentFlow node。
- `/agent-audit/:taskId` 展示报告摘要、漏洞统计和 finding 列表。
- 项目详情、仪表盘、统一漏洞详情仍能跳转智能审计结果。
- 点击智能审计 finding 能进入 `/finding-detail/agent/:taskId/:findingId`。
- 智能审计创建 payload 不包含静态审计任务选择或静态 finding 候选字段。
- 失败任务展示明确 runner 或 pipeline 错误。
- 旧 bootstrap/Opengrep metadata 如存在，仅作为历史诊断展示，不作为智能审计创建或启动输入。
- 统一漏洞详情页展示 AgentFlow 来源 node/role、artifact refs、证据、影响、修复建议和验证结论。

### 11.4 端到端 Smoke

使用已导入项目或 `argus_backend_uploads` 中可用项目：

1. `docker compose up --build`。
2. 在系统配置中填写模型 API 并通过连接测试。
3. 打开 `/tasks/intelligent`，选择已导入项目和审计范围创建智能审计任务。
4. 启动任务。
5. 等待完成或明确失败。
6. 查看 `/tasks/intelligent` 的状态、阶段和失败诊断。
7. 查看 `/agent-audit/:taskId` 的执行图、报告摘要、漏洞统计和 finding 列表。
8. 若存在 finding，打开 `/finding-detail/agent/:taskId/:findingId` 查看统一漏洞详情。
9. 检查任务状态快照中存在 AgentFlow run id、events、findings、checkpoints 和 report summary。

### 11.5 文档契约验收

执行实施前，计划文档必须能被逐项检查：

- 已明确 Argus 控制面和 AgentFlow 执行面的边界。
- 已明确 P1 三类语义角色和 P3 容器化动态节点边界。
- 已定义统一 realtime event envelope。
- 已规定前端只能消费后端导入后的 events/SSE。
- 已统一废弃原因码命名空间为 `E/R/V/A`。
- 已给出 HarnessOpt 白名单动作、资源预算、安全隔离和验收命令。
- 已明确模型 API 配置、项目扫描、智能审计执行、报告摘要和统一漏洞详情的 P1 闭环。
- 已明确 P1 报告可先复用 `/agent-audit/:taskId` 和 `/finding-detail/agent/:taskId/:findingId`，不强制独立报告页。
- 已明确 P1 Argus 原生实现合同、runner importer 映射矩阵和状态吸收位置。
- 已明确源规格书所有独有内容的吸收、后移或拒绝结论。

### 11.6 部署前置验收

执行 P1/P3 前需要补充或验证：

```bash
docker version
docker compose version
docker buildx version
cargo test --manifest-path backend/Cargo.toml agentflow
```

覆盖：

- Docker/Compose/Buildx 可用，支持资源限制和多阶段构建。
- LLM preflight 可明确区分缺凭据、模型不可达和配置非法。
- 本地 GPU 推理默认不启用；启用时必须单独验证 NVIDIA runtime 和显存预算。
- agentflow-runner 镜像大小、挂载目录、网络和输出目录符合第 10 节。
- 单机 32GB/20 核资源预算下默认 P1 并发不会超过预算。
- Docker socket 仅由 Argus 后端或受控 runner 管理面访问，agent 节点不得直接挂载。

## 12. 分阶段路线

### P1：AgentFlow 最小闭环

- 打通模型 API 配置、测试和 `agent-preflight`。
- 打通项目级智能审计创建流程，输入只来自项目和智能审计范围。
- 拒绝所有静态审计候选输入字段并补齐回归测试。
- 新增 runner 镜像。
- 新增 `runtime/agentflow` adapter。
- 接入 `start_agent_task`。
- 完成一条固定 pipeline 的 validate/run/import。
- 完成 runner output schema、importer mapping 和 Argus 状态吸收。
- 固定 pipeline 必须输出 Scratchboard-compatible event envelope，并暴露 `env-inter`、`vuln-reasoner`、`audit-reporter` 三类语义 role。
- 导入 report summary 和 finding 列表，并在 `/agent-audit/:taskId` 可见。
- 每个智能审计 finding 必须可跳转 `/finding-detail/agent/:taskId/:findingId`。
- 完成后端聚焦测试。

### P2：智能审计结果归一

- 完成智能审计 finding、event、checkpoint、report 的独立归一。
- 支持按目标文件、模块、目标漏洞类型和项目规模 fanout。
- 将智能审计结果与统一漏洞详情、项目详情和仪表盘展示打通。
- 增强报告导出为 Markdown、PDF 或 Argus 既有导出格式。
- 完成 risk lifecycle、废弃原因码、artifact 引用和 `feedback_bundle` 记录。
- 将 P1 metadata 中稳定的字段提升为显式后端字段或数据库列。

### P3：动态编排与可靠性

- 根据项目规模动态生成 fanout。
- 增量导入 AgentFlow node 状态。
- 支持取消、超时、artifact 限制。
- 远程 target 作为管理员受控能力评估。
- 引入规则表驱动的动态专家模板、资源感知扩缩、`topology_change` 事件、节点健康检查和恢复策略。
- 支持 Docker stats 采样、OOM/restart policy、资源阈值动作和动态专家节点生命周期审计。

## 13. Agent 编组建议

### `$ralph` 顺序执行

适合先做 P1 最小闭环：

```text
$ralph 按 plan/ai_audit/sourcecode_agent_audit_plan.md 执行 P1：打通模型 API 配置、项目级智能审计、AgentFlow runner/runtime adapter、报告摘要和统一漏洞详情闭环，并按文档第 11 节验证
```

### `$team` 并行执行

适合拆分为多 lane：

| Lane | Agent 类型 | 范围 | 推理建议 |
| --- | --- | --- | --- |
| 后端 runtime | executor | `backend/src/runtime/agentflow/*`、`agent_tasks.rs` | high |
| runner/compose | build-fixer 或 executor | `docker/*agentflow*`、`docker-compose.yml` | high |
| 测试 | test-engineer | backend/frontend tests、smoke script | medium |
| 前端 | executor | AgentFlow node 展示与文案 | medium |
| 安全 | security-reviewer | mount、artifact、credentials、serve 禁用 | medium |
| 验证 | verifier | 端到端 smoke 和契约验证 | high |

建议启动语句：

```text
$team 按 plan/ai_audit/sourcecode_agent_audit_plan.md 并行执行 AgentFlow 独立智能审计 P1，严格保留 Argus 产品/API，最终验证模型 API 配置、项目扫描、报告摘要和统一漏洞详情闭环
```

## 14. 非目标

- 不让普通用户配置任意 AgentFlow pipeline path。
- 不采用静态审计任务、Opengrep findings 或静态扫描结果作为智能审计候选输入。
- 不把 `.agentflow` 目录作为 Argus 主数据库。
- 不默认启用 EC2/ECS/SSH remote target。
- 不要求 GPU 本地推理。
- 不重建前端产品体系。
- 不保留独立“智能体平台”控制面；规格书中的 `/api/agents/*` 管理接口统一折叠为 Argus 后端内部 runtime 能力。

## 15. 源规格吸收清单

《源代码漏洞智能审计平台_需求规格说明书》草案已按下表吸收、后移或拒绝。后续实施只引用本文。

| 源规格范围 | 处理结论 | 本文落点 |
| --- | --- | --- |
| 1.1 硬件环境、32GB/20 核、可选 24GB GPU | 已吸收 | 10.2 资源预算与运行阈值 |
| 1.2 G-001 ~ G-007 核心目标 | 已吸收并分期 | 3.1、12 |
| 1.2 G-008 风险点生命周期和详情状态 | 已吸收 | 8.1、8.2 |
| 1.2 G-009 漏洞报告和统一详情展示 | 已吸收 | 8.2、9、11.3 |
| 1.2 G-010 静态 findings 融合作为智能审计候选 | 明确拒绝；智能审计是独立任务链路，禁止静态候选输入 | 4.1、5.9.4、8、14 |
| 1.2 G-011 AgentFlow 输出与执行产物导入 | 由 runner/importer 合同吸收并取代源草案接口 | 5.3.1、5.3.2、6.2 |
| 1.2 G-012 本地 GPU、远程执行或动态专家扩展 | 默认后移或关闭；管理员显式启用后单独验收 | 10.2、12、14 |
| 1.3 设计原则 | 已吸收为 Argus/AgentFlow 边界 | 1、3.1、10 |
| 2 系统架构、三类节点、通信拓扑 | 已吸收并 Argus 化 | 3、7.3、9.1 |
| 3 AgentFlow/HarnessOpt 调研 | 已压缩为设计约束 | 5.6、7.4、12 |
| 3.2.4 Scratchboard、Jinja | 已吸收为事件 envelope 和 message type | 6.1、6.1.1 |
| 3.4 容器编排适配层 | P1 内部 runner，P3 扩展 | 5.7、10.1、12 |
| 4 动态智能体节点设计 | P3 后移 | 5.6、5.7、7.4、12 |
| 5 env-inter/vuln-reasoner/audit-reporter 详细设计 | 已吸收为角色职责和输出字段 | 7.3、8.2、5.9 |
| 5.4 专家节点模板 | P3 后移，白名单规则控制 | 7.4、12 |
| 6 通信协议规范 | 已吸收 | 6.1、6.1.1 |
| 7 RiskPoint / ScanSession 数据模型 | 已映射到 Argus task/finding/event/checkpoint | 5.3.2、5.9.3、8.1 |
| 8 编排后端管理接口 `/api/agents/*` | 拒绝作为外部 API；折叠为内部 runtime | 5.9、14 |
| 9 性能与资源需求 | 已吸收 | 10.2、11.6 |
| 10 容器化部署规范 | 关键约束已吸收；大段 Docker 模板不保留 | 10.1、10.2、11.6 |
| 10 / P1 静态融合、Opengrep findings 候选输入 | 明确拒绝；原因是智能审计独立任务链路和 forbidden static input contract | 1、4.1、5.9.4、8、11 |
| 10.7 GPU 本地推理 | 默认关闭，管理员显式启用 | 10.2、14 |
| 附录 A 废弃原因码 | 已吸收并修正为 `E/R/V/A` | 8.1 |
| 附录 B 演化规则库 | 已吸收为 P3 白名单动作 | 7.4、12 |
| 附录 C Scratchboard 消息格式 | 已吸收 | 6.1、6.1.1 |
| 附录 D 状态转换矩阵 | 已吸收 | 8.1 |

删除源规格书的条件：

- 本文包含可执行实现合同、验收项和分期路线。
- 源规格中的独有条款已在上表归档。
- 被拒绝或后移的内容已有明确理由。
- 删除后不会丢失实施所需接口、状态、runner、资源、安全或验收信息。

本版本满足上述条件，源规格书可删除，避免与本文形成双需求源。

## 16. 术语表

| 术语 | 含义 |
| --- | --- |
| Argus | 当前源代码审计平台 |
| AgentFlow | 智能审计执行编排框架 |
| AgentFlow runner | Argus 控制下执行 AgentFlow CLI 的容器或脚本 |
| Agent Task | Argus 后端管理的智能审计任务 |
| Prompt Skill | Argus 中可配置的 prompt 注入能力 |
| Opengrep | Argus 静态审计规则引擎 |
| Finding | 漏洞发现记录 |
| Checkpoint | 阶段性执行快照 |
| Agent Tree | AgentFlow node DAG 映射到 Argus 的展示树 |
| Preflight | 创建或启动前的 LLM、runner、pipeline 检查 |
