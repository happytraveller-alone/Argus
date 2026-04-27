# Argus 源代码漏洞智能审计 AgentFlow 融合计划

> 文档版本：v5.0
> 更新日期：2026-04-27
> 适用项目：Argus 当前代码库
> 状态：AgentFlow 转向版 / Hermes 退役执行前计划

## 1. 结论

Argus 智能审计后续全面转向 AgentFlow。Hermes manifest、固定四角色 handoff、`docker exec hermes chat`、`HERMES_*` 环境变量、mock completed 降级路径均不再作为目标架构保留。

本计划采用“Argus 控制面 + AgentFlow 执行面”：

- Argus 保留：React 前端、Rust Axum API、`agent_tasks` 生命周期、任务状态快照、Prompt Skill、LLM 配置预检、Opengrep 静态审计输入、统一漏洞详情、报告导出。
- AgentFlow 接管：智能审计 DAG、fanout/merge、迭代复核、agent node 执行、运行 artifacts、结构化审计输出。
- Hermes 历史代码允许删除：执行阶段可以删除 Argus 中与 Hermes 运行时绑定的历史代码和配置，避免为新框架保留兼容包袱。

## 2. RALPLAN-DR 摘要

### 2.1 原则

1. 不重建 Argus 产品壳，替换运行时即可。
2. 不保留长期 Hermes/AgentFlow 双运行时。
3. 运行时失败必须真实失败，不能 mock success。
4. AgentFlow 输出必须归一化为 Argus 现有任务、事件、漏洞、checkpoint 和报告模型。
5. 删除历史代码优先于适配历史抽象，但不得删除仍承载产品体验的智能审计 API/UI。

### 2.2 决策驱动

| 驱动 | 说明 |
| --- | --- |
| 用户方向 | 明确要求舍弃 Hermes，参考 AgentFlow，允许删除历史智能审计代码 |
| 可执行性 | AgentFlow 已提供 Graph DSL、CLI、validate/run、fanout/merge、失败回边 |
| 产品连续性 | Argus 已有任务管理、详情页、Prompt Skill、LLM preflight、Opengrep 和报告能力 |

### 2.3 可选方案

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| A. 保留 Argus 产品层，删除 Hermes 运行时，新增 AgentFlow runner | 采用 | 迁移面清晰，能复用现有 UI/API，并移除历史包袱 |
| B. 在 Hermes 外包一层 AgentFlow adapter | 拒绝 | 仍需维护 Hermes manifest/role/handoff，违背全面转向 |
| C. 前端直接调用 `agentflow serve` | 拒绝 | 绕过 Argus 鉴权、任务状态和项目隔离 |
| D. 重建独立 AgentFlow 审计平台 | 拒绝 | 会丢失 Argus 现有项目、静态审计、漏洞详情和报告能力 |

## 3. 当前事实

### 3.1 当前保留价值

| 能力 | 当前触点 | 迁移后处理 |
| --- | --- | --- |
| 智能任务管理 | `/tasks/intelligent`、`TaskManagementIntelligent.tsx` | 保留 |
| 智能任务详情 | `/agent-audit/:taskId`、`AgentAudit/TaskDetailPage.tsx` | 保留，展示 AgentFlow node |
| 智能任务 API | `backend/src/routes/agent_tasks.rs` | 保留路由，替换 start 运行时 |
| 任务状态 | `TaskStateSnapshot.agent_tasks` | 保留为产品主状态 |
| 漏洞模型 | `AgentFindingRecord` | 保留，作为 AgentFlow finding schema 目标 |
| 事件模型 | `AgentEventRecord` | 保留，导入 AgentFlow node/runner 事件 |
| Checkpoint | `AgentCheckpointRecord` | 保留，记录 AgentFlow 阶段状态 |
| Prompt Skill | `/api/v1/skills/*` | 保留，注入 AgentFlow prompt/Jinja context |
| LLM preflight | `/api/v1/system-config/*` | 保留，用于 AgentFlow agent 可用性预检 |
| Opengrep | 静态任务、规则、finding | 保留，作为 AgentFlow 候选输入 |

### 3.2 当前应退役内容

| 历史内容 | 当前触点 | 处理 |
| --- | --- | --- |
| Hermes Rust 模块 | `backend/src/runtime/hermes/*` | 删除 |
| Hermes 模块导出 | `backend/src/runtime/mod.rs` 中 `pub mod hermes` | 删除并替换为 `agentflow` |
| Hermes dispatch | `try_hermes_dispatch`、`HermesDispatchOutcome` | 删除并替换为 `try_agentflow_dispatch` |
| Hermes mock success | `finalize_agent_task_mock_completed` | 删除；运行时不可用必须 failed/preflight failed |
| Hermes agent manifests/scripts | `backend/agents/*` | 删除或迁移为 AgentFlow pipeline/prompt 资源 |
| Hermes compose 配置 | `HERMES_*`、`./backend/agents` mount | 删除并新增 AgentFlow runner 配置 |
| Hermes 测试假设 | `HERMES_AGENTS_BASE_PATH` 相关测试 | 改写为 AgentFlow runner contract 测试 |
| 文档中的 Hermes 目标架构 | 本文件旧版第 9/15 节等 | 删除 |

### 3.3 不应删除内容

以下不是“历史代码”，是 Argus 智能审计产品壳，应保留并接入 AgentFlow：

- `backend/src/routes/agent_tasks.rs` 的路由、查询、finding、event、checkpoint、report 能力。
- `backend/src/db/task_state.rs` 的 `AgentTaskRecord`、`AgentFindingRecord`、`AgentEventRecord`、`AgentCheckpointRecord`。
- `frontend/src/pages/TaskManagementIntelligent.tsx`。
- `frontend/src/pages/AgentAudit/*`。
- `frontend/src/shared/api/agentTasks.ts`。
- `/finding-detail/:source/:taskId/:findingId` 的 agent/static 统一详情体验。
- Prompt Skill、LLM 配置、Opengrep 静态审计和项目上传能力。

## 4. 目标架构

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

## 5. AgentFlow 运行时设计

### 5.1 Runner 形态

新增 `agentflow-runner` 镜像或等价受控脚本，职责：

- 固定 AgentFlow commit、版本或镜像 digest。
- 保留 AgentFlow license 信息。
- 不使用 `curl | bash` 动态安装。
- 运行 `agentflow validate`。
- 运行 `agentflow run`。
- 输出 Argus 约定 JSON。
- 将 `.agentflow/runs/<run_id>` artifacts 放入任务隔离输出目录。

### 5.2 Pipeline 存放

建议新增：

```text
backend/agentflow/
  pipelines/
    intelligent_audit.py
  prompts/
    system_context.md
    finding_schema.md
  schemas/
    runner_output.schema.json
```

P0 允许固定一条 `intelligent_audit.py`，P1 再支持按项目规模和静态发现动态生成 fanout。

### 5.3 Pipeline 节点

| 节点 | AgentFlow 类型 | 职责 |
| --- | --- | --- |
| `context_prepare` | `python` 或 `shell` | 汇总项目路径、目标文件、Prompt Skill、Opengrep findings |
| `scope_recon` | `codex` | 只读理解项目结构、入口、调用链和风险面 |
| `candidate_fanout` | `fanout` | 按目标文件、模块、静态发现或规则分片 |
| `vulnerability_analysis` | `codex` / `claude` / `pi` | 并行分析漏洞真实性、可达性、影响 |
| `verification` | `codex` / `claude` | 复核候选；证据不足时失败回边 |
| `merge_findings` | `merge` + agent node | 汇总 finding，去重，按 schema 归一化 |
| `report` | `codex` | 生成中文报告、危害、证据、修复建议 |

### 5.4 输出契约

AgentFlow runner 必须输出 Argus 可解析 JSON：

```json
{
  "runtime": "agentflow",
  "agentflow_run_id": "string",
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

- `findings` 必须可映射到 `AgentFindingRecord`。
- `events` 必须可映射到 `AgentEventRecord`，并保持递增 sequence。
- `checkpoints` 必须可映射到 `AgentCheckpointRecord`。
- `agent_tree` 可以从 AgentFlow node DAG 生成，不再固定四个 Hermes role。
- 失败输出必须包含中文可读错误，不得静默成功。

## 6. 后端迁移计划

### 6.1 新增模块

新增 `backend/src/runtime/agentflow`：

| 文件 | 职责 |
| --- | --- |
| `mod.rs` | 导出 AgentFlow runtime |
| `contracts.rs` | runner input/output、node summary、finding schema |
| `pipeline.rs` | 渲染/选择 AgentFlow pipeline |
| `runner.rs` | 调用 runner 容器或本地命令 |
| `importer.rs` | 将 runner output 导入 `AgentTaskRecord` |
| `preflight.rs` | validate/doctor/凭据检查 |

### 6.2 替换启动路径

`backend/src/routes/agent_tasks.rs::start_agent_task` 目标流程：

1. 加载 `AgentTaskRecord`。
2. 生成 AgentFlow input：
   - project id/path。
   - target files。
   - Prompt Skill runtime snapshot。
   - LLM effective config。
   - Opengrep task/finding 摘要。
3. 调用 `try_agentflow_dispatch`。
4. 成功则导入 events/findings/checkpoints/report/agent_tree。
5. 失败则任务进入 failed，写入错误事件和 checkpoint。
6. 不再调用 `finalize_agent_task_mock_completed`。

### 6.3 删除历史代码

执行阶段可以删除：

- `backend/src/runtime/hermes/*`
- `backend/agents/*`
- `HermesDispatchOutcome`
- `try_hermes_dispatch`
- `finalize_agent_task_mock_completed`
- Hermes manifest discovery/handoff/executor imports
- `HERMES_AGENTS_BASE_PATH`
- `HERMES_RECON_CONTAINER`
- `HERMES_ANALYSIS_CONTAINER`
- `HERMES_VERIFICATION_CONTAINER`
- `HERMES_REPORT_CONTAINER`
- `./backend/agents:/app/backend/agents:ro` compose mount

删除后必须新增或改写测试，证明这些符号不再是活跃运行时依赖。

## 7. 前端迁移计划

前端不重做产品结构，只做运行时语义对齐：

- `/tasks/intelligent` 继续作为智能审计任务管理页。
- `/agent-audit/:taskId` 继续作为智能审计任务详情页。
- Agent 树展示从固定 Hermes role 改为 AgentFlow node DAG。
- 运行时标签统一使用 “AgentFlow” 或 “智能审计执行图”。
- 如果任务失败，展示 AgentFlow validate/runner/credential/pipeline 的具体失败原因。
- 不在前端直接调用 `agentflow serve`。

需要重点检查：

- `AgentAudit/TaskDetailPage.tsx` 是否假设固定 `recon/analysis/verification/report`。
- 任务详情统计是否能接受动态 node 数。
- 事件日志是否能展示 AgentFlow node id、agent kind、artifact path。
- 漏洞详情和项目详情是否继续复用统一 finding 展示。

## 8. 静态审计融合

Opengrep 不删除。它是 AgentFlow 智能审计的重要输入来源。

融合方式：

1. 用户创建智能审计任务时，可选择最近一次或指定静态审计任务作为输入。
2. 后端将 Opengrep findings 压缩为候选清单。
3. AgentFlow 根据候选清单 fanout。
4. AI 复核静态命中的可达性、触发条件、业务影响和误报概率。
5. 确报/误报状态回写 Argus `AgentFindingRecord`。
6. 静态发现详情与智能审计详情保持统一跳转体验。

## 9. 安全与隔离

- runner 只能挂载当前任务项目目录、必要 prompt/config、输出目录。
- 用户不能提交任意 pipeline path。
- `agentflow serve` 不作为生产默认服务暴露。
- AgentFlow remote target 默认关闭，启用必须管理员显式配置。
- apiKey/customHeaders 不写入 artifacts、报告、events。
- artifacts 下载必须经 Argus 后端鉴权和路径规范化。
- runner stdout/stderr 必须截断并脱敏后入库。

## 10. 验收标准

### 10.1 删除验收

执行完成后：

```bash
rg -n "try_hermes_dispatch|HermesDispatchOutcome|HERMES_|runtime/hermes|docker exec hermes|hermes chat" backend docker-compose.yml frontend plan
```

不得命中活跃运行时代码。历史说明若保留，必须标注 retired。

### 10.2 新框架验收

```bash
rg -n "AgentFlow|agentflow|try_agentflow_dispatch|runtime/agentflow|agentflow-runner" backend docker-compose.yml frontend plan
```

必须命中：

- 后端 AgentFlow runtime。
- runner/compose。
- 计划文档。
- 必要前端运行时展示。

### 10.3 Runner 验收

```bash
docker compose build agentflow-runner
docker compose run --rm agentflow-runner agentflow --help
docker compose run --rm agentflow-runner agentflow validate /app/backend/agentflow/pipelines/intelligent_audit.py
```

验收：

- runner 可构建。
- AgentFlow CLI 可执行。
- pipeline 可 validate。
- 缺凭据或 validate 失败时任务 failed，不 mock completed。

### 10.4 后端验收

建议命令：

```bash
cargo test -p argus_backend agentflow
cargo test -p argus_backend agent_tasks
```

覆盖：

- AgentFlow input 生成。
- runner 成功输出导入。
- runner 失败输出导入。
- cancel 终止 runner。
- findings/events/checkpoints/report 聚合。
- Hermes 活跃路径缺失测试。

### 10.5 前端验收

建议命令：

```bash
pnpm --dir frontend test:node -- agent
pnpm --dir frontend type-check
pnpm --dir frontend lint
```

覆盖：

- 创建智能审计任务 payload 不破坏。
- 任务详情展示动态 AgentFlow node。
- 页面不再把活跃运行时称为 Hermes。
- 项目详情、仪表盘、统一漏洞详情仍能跳转智能审计结果。

### 10.6 端到端 smoke

使用已导入项目或 `argus_backend_uploads` 中可用项目：

1. `docker compose up --build`。
2. 创建智能审计任务。
3. 启动任务。
4. 等待完成或明确失败。
5. 查看 `/tasks/intelligent`。
6. 查看 `/agent-audit/:taskId`。
7. 检查任务状态快照中存在 AgentFlow run id、events、findings、checkpoints。

## 11. 分阶段路线

### P0：文档与删除边界

- 本文档切换为 AgentFlow 方向。
- 明确保留/删除清单。
- 新增执行计划和测试规格。

### P1：AgentFlow 最小闭环

- 新增 runner 镜像。
- 新增 `runtime/agentflow` adapter。
- 替换 `start_agent_task` 的 Hermes dispatch。
- 删除 Hermes runtime 和 compose 活跃配置。
- 完成一条固定 pipeline 的 validate/run/import。

### P2：静态审计融合

- 支持指定 Opengrep 任务作为输入。
- 支持按静态 findings fanout。
- 将智能复核结果与静态详情统一展示。

### P3：动态编排与可靠性

- 根据项目规模动态生成 fanout。
- 增量导入 AgentFlow node 状态。
- 支持取消、超时、artifact 限制。
- 远程 target 作为管理员受控能力评估。

## 12. ADR

### Decision

Argus 智能审计运行时从 Hermes 全面迁移到 AgentFlow。删除历史 Hermes 运行时代码，保留 Argus 产品/API/状态层。

### Drivers

- 用户明确要求全面转向 AgentFlow。
- AgentFlow 原生支持 DAG、fanout、merge、迭代和多 agent。
- Argus 已有成熟产品入口和数据模型，不需要重建。
- 历史 Hermes code path 会阻碍新框架融合。

### Alternatives Considered

- 保留 Hermes 并增加 AgentFlow 兼容层：拒绝，形成双运行时。
- 前端直连 AgentFlow serve：拒绝，安全边界错误。
- 重建独立 AgentFlow 平台：拒绝，浪费现有 Argus 能力。
- Rust 进程内嵌 Python：拒绝，部署和故障边界复杂。

### Consequences

- 后端会新增 Python runner/容器构建链。
- 测试需要从 Hermes role contract 改为 AgentFlow runner output contract。
- 文档和前端运行时文案需要更新。
- 删除历史代码后不再兼容 Hermes manifests。

### Follow-ups

- 固定 AgentFlow commit/版本/digest。
- 设计 runner output JSON schema。
- 实现 `runtime/agentflow`。
- 删除 Hermes 活跃路径。
- 做端到端 smoke。

## 13. Agent 编组建议

### `$ralph` 顺序执行

适合先做 P0/P1 最小闭环：

```text
$ralph 按 plan/ai_audit/sourcecode_agent_audit_plan.md 执行 P1：新增 AgentFlow runner/runtime adapter，删除 Hermes 活跃运行时路径，保留 Argus 产品/API/状态层，并按文档第 10 节验证
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
| 验证 | verifier | 端到端 smoke 和删除契约 | high |

建议启动语句：

```text
$team 按 plan/ai_audit/sourcecode_agent_audit_plan.md 并行执行 AgentFlow 融合 P1，严格保留 Argus 产品/API，删除 Hermes 活跃路径，最终用第 10 节验证闭环
```

## 14. 非目标

- 不保留 Hermes 长期兼容。
- 不让普通用户配置任意 AgentFlow pipeline path。
- 不把 `.agentflow` 目录作为 Argus 主数据库。
- 不默认启用 EC2/ECS/SSH remote target。
- 不要求 GPU 本地推理。
- 不重建前端产品体系。

## 15. 术语表

| 术语 | 含义 |
| --- | --- |
| Argus | 当前源代码审计平台 |
| AgentFlow | 新智能审计执行编排框架 |
| AgentFlow runner | Argus 控制下执行 AgentFlow CLI 的容器或脚本 |
| Agent Task | Argus 后端管理的智能审计任务 |
| Prompt Skill | Argus 中可配置的 prompt 注入能力 |
| Opengrep | Argus 静态审计规则引擎 |
| Finding | 漏洞发现记录 |
| Checkpoint | 阶段性执行快照 |
| Agent Tree | AgentFlow node DAG 映射到 Argus 的展示树 |
| Preflight | 创建或启动前的 LLM/runner/pipeline 检查 |
| Hermes | 已退役的历史智能体运行时方向 |
