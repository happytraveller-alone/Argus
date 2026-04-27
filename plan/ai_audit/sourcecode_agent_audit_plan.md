# Argus 源代码漏洞智能审计 AgentFlow 功能需求与实施计划

> 文档版本：v6.0
> 更新日期：2026-04-27
> 适用项目：Argus 当前代码库
> 状态：AgentFlow 新功能开发计划

## 1. 目标

Argus 智能审计能力采用“Argus 控制面 + AgentFlow 执行面”的实现方式。Argus 继续负责项目、任务、静态审计、Prompt Skill、系统配置、漏洞详情和报告导出；AgentFlow 负责智能审计执行图、节点调度、并行分析、复核闭环、artifact 产出和结构化结果输出。

## 2. 当前基线

| 能力 | 当前触点 | 后续处理 |
| --- | --- | --- |
| 智能任务管理 | `/tasks/intelligent`、`TaskManagementIntelligent.tsx` | 保留，接入 AgentFlow 任务状态 |
| 智能任务详情 | `/agent-audit/:taskId`、`AgentAudit/TaskDetailPage.tsx` | 保留，展示 AgentFlow node DAG |
| 智能任务 API | `backend/src/routes/agent_tasks.rs` | 保留路由，接入 AgentFlow runner |
| 任务状态 | `TaskStateSnapshot.agent_tasks` | 保留为产品主状态 |
| 漏洞模型 | `AgentFindingRecord` | 保留，作为 AgentFlow finding schema 目标 |
| 事件模型 | `AgentEventRecord` | 保留，导入 AgentFlow node/runner 事件 |
| Checkpoint | `AgentCheckpointRecord` | 保留，记录 AgentFlow 阶段状态 |
| Prompt Skill | `/api/v1/skills/*` | 保留，注入 AgentFlow prompt context |
| LLM preflight | `/api/v1/system-config/*` | 保留，用于 agent 可用性预检 |
| Opengrep | 静态任务、规则、finding | 保留，作为智能审计候选输入 |

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
  /api/v1/static-tasks/*
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

## 4. 功能需求

### 4.1 创建智能审计任务

用户应能在 Argus 中创建智能审计任务，并配置：

- 项目。
- 目标文件或排除模式。
- 目标漏洞类型。
- 验证等级。
- 是否启用 Prompt Skill。
- 可选静态审计任务作为候选输入。
- 最大迭代次数、超时和资源限制。

后端必须在任务创建时保存完整审计范围快照，避免后续配置变更影响已创建任务。

### 4.2 启动智能审计任务

启动任务时，后端应：

1. 加载任务和项目快照。
2. 生成 AgentFlow runner input。
3. 渲染或选择 pipeline。
4. 执行 runner preflight。
5. 调用 runner。
6. 导入 events、checkpoints、agent tree、findings 和 report。
7. 将失败原因记录为用户可读错误事件。

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
- 与静态审计发现的关联关系。

### 4.5 导出报告

报告应支持 Markdown、PDF 或 Argus 现有导出格式，并包含：

- 任务摘要。
- 执行图摘要。
- 高风险发现列表。
- 每个漏洞的证据、影响和修复建议。
- 静态审计输入来源。
- 运行诊断和失败原因。

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
  "static_findings": [],
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

### 5.4 启动流程

`backend/src/routes/agent_tasks.rs::start_agent_task` 目标流程：

1. 加载 `AgentTaskRecord`。
2. 生成 AgentFlow input。
3. 执行 preflight。
4. 调用 `try_agentflow_dispatch`。
5. 成功则导入输出并完成任务。
6. 失败则记录错误事件、checkpoint 和诊断信息。
7. 保存任务快照。

### 5.5 取消与超时

- 用户取消任务时，后端必须终止 runner。
- runner 超时后，任务进入 failed 或 cancelled，并保留诊断。
- 取消和超时都应产生明确事件。
- 临时 artifact 应按任务隔离目录清理或保留可审计索引。

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

## 7. Pipeline 需求

### 7.1 基础节点

| 节点 | 类型 | 职责 |
| --- | --- | --- |
| `context_prepare` | python 或 shell | 汇总项目路径、目标文件、Prompt Skill、静态发现 |
| `scope_recon` | agent | 只读理解项目结构、入口、调用链和风险面 |
| `candidate_fanout` | fanout | 按目标文件、模块、静态发现或规则分片 |
| `vulnerability_analysis` | agent | 并行分析漏洞真实性、可达性、影响 |
| `verification_loop` | agent 或 graph loop | 复核候选，证据不足时返回补充分析 |
| `merge_findings` | merge | 去重并按 schema 归一化 finding |
| `report` | agent | 生成中文报告、证据、危害和修复建议 |

### 7.2 Pipeline 生成策略

P1 固定一条 `intelligent_audit.py`。P2 以后支持：

- 按项目语言选择节点模板。
- 按静态审计发现 fanout。
- 按文件数量和风险等级调整并行度。
- 按用户验证等级启用更严格复核。

## 8. 静态审计融合

Opengrep 是智能审计的重要输入来源。

融合方式：

1. 用户创建智能审计任务时，可选择最近一次或指定静态审计任务作为输入。
2. 后端将 Opengrep findings 压缩为候选清单。
3. AgentFlow 根据候选清单 fanout。
4. AI 复核静态命中的可达性、触发条件、业务影响和误报概率。
5. 确报和误报状态回写 Argus `AgentFindingRecord`。
6. 静态发现详情与智能审计详情保持统一跳转体验。

## 9. 前端需求

前端不重做产品结构，只做 AgentFlow 语义对齐：

- `/tasks/intelligent` 继续作为智能审计任务管理页。
- `/agent-audit/:taskId` 继续作为智能审计任务详情页。
- Agent 树展示动态 AgentFlow node DAG。
- 运行时标签统一使用 “AgentFlow” 或 “智能审计执行图”。
- 如果任务失败，展示 validate、runner、credential、pipeline 的具体失败原因。
- 不在前端直接调用 `agentflow serve`。

需要重点检查：

- `AgentAudit/TaskDetailPage.tsx` 是否能接受动态 node 数。
- 任务详情统计是否能接受动态 node 状态。
- 事件日志是否能展示 node id、agent kind、artifact path。
- 漏洞详情和项目详情是否继续复用统一 finding 展示。

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

## 11. 验收标准

### 11.1 后端验收

建议命令：

```bash
cargo test --manifest-path backend/Cargo.toml agentflow
cargo test --manifest-path backend/Cargo.toml agent_tasks
```

覆盖：

- AgentFlow input 生成。
- runner preflight 成功和失败。
- runner 成功输出导入。
- runner 失败输出导入。
- cancel 终止 runner。
- findings/events/checkpoints/report 聚合。
- 输出 schema 校验失败时任务 failed。

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

### 11.3 前端验收

```bash
pnpm --dir frontend test:node -- agent
pnpm --dir frontend type-check
pnpm --dir frontend lint
```

覆盖：

- 创建智能审计任务 payload 不破坏。
- 任务详情展示动态 AgentFlow node。
- 项目详情、仪表盘、统一漏洞详情仍能跳转智能审计结果。
- 失败任务展示明确 runner 或 pipeline 错误。

### 11.4 端到端 Smoke

使用已导入项目或 `argus_backend_uploads` 中可用项目：

1. `docker compose up --build`。
2. 创建智能审计任务。
3. 启动任务。
4. 等待完成或明确失败。
5. 查看 `/tasks/intelligent`。
6. 查看 `/agent-audit/:taskId`。
7. 检查任务状态快照中存在 AgentFlow run id、events、findings、checkpoints。

## 12. 分阶段路线

### P1：AgentFlow 最小闭环

- 新增 runner 镜像。
- 新增 `runtime/agentflow` adapter。
- 接入 `start_agent_task`。
- 完成一条固定 pipeline 的 validate/run/import。
- 完成后端聚焦测试。

### P2：静态审计融合

- 支持指定 Opengrep 任务作为输入。
- 支持按静态 findings fanout。
- 将智能复核结果与静态详情统一展示。

### P3：动态编排与可靠性

- 根据项目规模动态生成 fanout。
- 增量导入 AgentFlow node 状态。
- 支持取消、超时、artifact 限制。
- 远程 target 作为管理员受控能力评估。

## 13. Agent 编组建议

### `$ralph` 顺序执行

适合先做 P1 最小闭环：

```text
$ralph 按 plan/ai_audit/sourcecode_agent_audit_plan.md 执行 P1：新增 AgentFlow runner/runtime adapter，保留 Argus 产品/API/状态层，并按文档第 11 节验证
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
$team 按 plan/ai_audit/sourcecode_agent_audit_plan.md 并行执行 AgentFlow 融合 P1，严格保留 Argus 产品/API，最终用第 11 节验证闭环
```

## 14. 非目标

- 不让普通用户配置任意 AgentFlow pipeline path。
- 不把 `.agentflow` 目录作为 Argus 主数据库。
- 不默认启用 EC2/ECS/SSH remote target。
- 不要求 GPU 本地推理。
- 不重建前端产品体系。

## 15. 术语表

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
