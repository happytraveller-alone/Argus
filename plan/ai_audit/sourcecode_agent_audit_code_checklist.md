# Argus AgentFlow 智能审计业务代码清单

> 文档版本：v1.0  
> 更新日期：2026-04-27  
> 上游权威计划：`plan/ai_audit/sourcecode_agent_audit_plan.md` v6.4  
> AgentFlow 源码核对：`/tmp/argus-agentflow-src`，commit `1667fa35ed99e3c1583a7d60cac8e3406cafd3ee`  
> 适用范围：P1 AgentFlow 最小闭环编码执行清单；P2/P3 只作为边界和预留约束

## 0. 权威边界

`sourcecode_agent_audit_plan.md` 是唯一需求源。本文不是第二份需求规格，而是把上游计划转换为开发者可逐项编码、测试和验收的业务代码清单。

冲突处理规则：

- 当本文与 `sourcecode_agent_audit_plan.md` 冲突时，以上游计划为准。
- 当 AgentFlow 原生能力与 Argus 产品合同冲突时，以 Argus 产品合同为准。
- P1 只交付模型 API 配置、项目级智能审计、AgentFlow runner/runtime adapter、报告摘要和统一漏洞详情闭环。
- P1 不实现动态专家节点、不启用远程 target、不暴露 `agentflow serve` 给前端或普通用户。
- P1 不采用静态审计任务、Opengrep findings 或静态扫描结果作为智能审计候选输入。

## 1. RALPLAN-DR 摘要

### Principles

1. Argus 是唯一控制面、数据面、API 面和 UI 面。
2. AgentFlow 只作为执行面和 artifact/event 来源，不能替代 Argus 状态模型。
3. 智能审计任务输入必须来自项目、审计范围、目标文件、目标漏洞类型、验证等级、Prompt Skill 和资源限制。
4. 所有失败必须落入 Argus task state，并展示中文可读错误。
5. P1 清单必须可测试、可回滚、可分工，不把 P2/P3 能力混入最小闭环。

### Decision Drivers

1. 开发者需要按文件和验收项直接编码，不能在 1000 行计划中重新推导实现顺序。
2. AgentFlow 原生 `RunRecord`/`RunEvent` 不是 Argus finding/report schema，必须有 adapter/importer。
3. 当前 Argus 已有智能审计产品面，P1 应接入既有页面、路由和状态模型，而不是重建新平台。

### Options

| 方案 | 结论 | 理由 |
| --- | --- | --- |
| 新增独立代码清单文档 | 采用 | 保持上游计划权威，同时提供可执行编码控制面 |
| 追加到上游计划末尾 | 不采用 | 上游计划已很长，继续膨胀会降低实施可读性 |
| 拆成 backend/frontend/runner 多个清单 | 不采用 | 当前阶段容易形成多文档漂移，P1 先保持单一编码清单 |

### ADR

Decision: 新增 `plan/ai_audit/sourcecode_agent_audit_code_checklist.md`，作为上游计划的 P1 编码控制清单。

Drivers: 降低开发者重新解读成本；固定 Argus/AgentFlow 映射；明确禁止静态输入；把测试和失败行为绑定到每个代码面。

Alternatives considered: 追加到上游计划、多文档拆分。

Consequences: 后续 `$ralph` 或 `$team` 可直接按清单执行；清单维护时必须同步检查上游计划版本和 AgentFlow 源码变化。

Follow-ups: P1 完成后再为 P2 结果归一和 P3 动态编排生成新清单，不在本文提前展开。

## 2. 清单项格式

每个可执行项必须能回答“改哪里、怎么改、怎么验、失败怎么落库”。新增或修改清单时使用以下字段：

| 字段 | 要求 |
| --- | --- |
| ID | 稳定编号，例如 `BE-START-01` |
| Owner | 推荐执行角色或 lane，例如 backend、runner、frontend、test |
| Files | 主要代码文件或目录 |
| Plan refs | 上游计划章节或合同来源 |
| AgentFlow refs | AgentFlow 源码或文档依据；不相关则写 `N/A` |
| Implementation contract | 必须实现的行为，不写泛泛目标 |
| Acceptance | 可观察验收结果 |
| Tests | 必须新增或执行的测试命令 |
| Failure behavior | 失败时的状态、event、checkpoint 或 UI 表现 |
| Boundary | P1/P2/P3 边界，明确“不在 P1 做什么” |

## 3. 当前基线差异表

| Surface | 当前基线 | P1 必须达到 |
| --- | --- | --- |
| `backend/src/routes/agent_tasks.rs` | 已有 create/list/detail/start/cancel/events/findings/report 路由；启动路径目前应失败并提示 AgentFlow runtime 未配置 | create/start/import 拒绝静态候选字段；start 执行 preflight -> build_input -> validate/run -> import_result；所有失败落库 |
| `backend/src/routes/system_config.rs` | 已有 LLM config、`test-llm`、`agent-preflight` 基线 | `agent-preflight` 扩展到 LLM、runner、pipeline、输出目录和资源预算，不回传明文密钥 |
| `backend/src/db/task_state.rs` | 已有 `AgentTaskRecord`、`AgentFindingRecord`、`AgentEventRecord`、`AgentCheckpointRecord` | 保存 runtime、run_id、topology_version、artifact_index、feedback_bundle、source node/role、report snapshot |
| `backend/src/runtime/agentflow/*` | P1 前不存在或未接入 | 新增 contracts/preflight/pipeline/runner/importer，并由 `agent_tasks.rs` 调用 |
| `backend/agentflow/*` | P1 前不存在或未固定 | 新增 schemas、pipeline、prompts；schema-compatible smoke runner 和真实 runner 使用同一合同 |
| `docker-compose.yml` / runner image | 无稳定 AgentFlow runner 服务 | 增加受控 runner 构建/调用路径；固定 AgentFlow commit/version；不使用动态安装脚本作为生产路径 |
| `frontend/src/pages/TaskManagementIntelligent.tsx` | 已有智能审计任务管理入口 | 创建任务只提交项目和智能审计范围；不渲染静态审计任务选择器 |
| `frontend/src/pages/AgentAudit/TaskDetailPage.tsx` | 已有任务详情和事件/发现展示基础 | 展示动态 AgentFlow node DAG、报告摘要、finding 列表、失败诊断和 artifact 引用 |
| `frontend/src/pages/FindingDetail.tsx` | 已支持 `/finding-detail/:source/:taskId/:findingId` | `source=agent` 时展示 AgentFlow 来源、证据、影响、修复建议和验证结论 |
| `frontend/src/shared/api/agentTasks.ts` | 已有 agent task API client | 类型增加渐进字段，保持旧字段兼容；payload 不含禁止字段 |

## 4. 产品不变量与静态输入门禁

### P1 不变量

- 用户先配置模型 API，并通过 `test-llm` 或 `agent-preflight` 得到可读结果。
- 用户在 `/tasks/intelligent` 选择项目、审计范围、目标文件/排除模式、漏洞类型、验证等级、Prompt Skill 和资源限制。
- 后端根据智能审计任务快照生成 runner input，不读取静态任务或 Opengrep finding 作为候选。
- AgentFlow runner 输出先进入 Argus adapter，再导入 Argus task/finding/event/checkpoint/report。
- 前端只消费 Argus API/SSE，不直接读取 `.agentflow`、Scratchboard、JSONL 或 AgentFlow web API。

### 禁止字段

以下字段在 create、start、audit_scope、runner input、runner output 和 frontend payload 中均不得作为智能审计输入：

- `static_task_id`
- `opengrep_task_id`
- `candidate_finding_ids`
- `static_findings`
- `bootstrap_task_id`
- `bootstrap_candidate_count`
- `candidate_findings`
- `candidate_origin=opengrep|static`
- `candidate_origin=bandit|gitleaks|phpstan|pmd`
- `source_engine=opengrep|static|bandit|gitleaks|phpstan|pmd`
- 任何静态扫描、静态 finding、外部 scanner bootstrap 来源

| ID | Owner | Files | Contract | Acceptance | Tests | Failure behavior | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GATE-STATIC-01 | backend | `backend/src/routes/agent_tasks.rs` | create payload 和 `audit_scope` 递归扫描禁止字段 | 命中禁止字段返回 `400 Bad Request` | `cargo test --manifest-path backend/Cargo.toml agent_tasks` | 不创建任务，不写入误导性 running 状态 | P1 必做 |
| GATE-STATIC-02 | backend | `backend/src/routes/agent_tasks.rs`、`runtime/agentflow/importer.rs` | start 时如历史 task scope 含禁止字段，任务 failed | 写入 `forbidden_static_input` event | 同上 | task status=`failed`，中文错误进入 `error_message` | P1 必做 |
| GATE-STATIC-03 | runner/importer | `backend/src/runtime/agentflow/importer.rs` | runner output 含静态来源时拒绝导入 | 写入 `runner_output_invalid` event 和 `import_failed` checkpoint | importer fixture test | task failed，不产生 finding | P1 必做 |
| GATE-STATIC-04 | frontend | `TaskManagementIntelligent.tsx`、创建弹窗相关文件 | 智能审计创建 UI 不渲染静态任务选择器，payload 不含禁止字段 | 浏览器/单测 payload 快照不含禁止字段 | `pnpm --dir frontend test:node -- agent` | 前端不提供错误输入入口 | P1 必做 |

## 5. 后端编码清单

### 5.1 System Config 与 Preflight

| ID | Owner | Files | Plan refs | AgentFlow refs | Implementation contract | Acceptance | Tests | Failure behavior | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BE-PREFLIGHT-01 | backend | `backend/src/routes/system_config.rs` | 5.9.1、11.1 | `agentflow/cli.py` `validate`/`doctor` 命令 | `agent-preflight` 在 LLM-only 基础上增加 runner、pipeline、output_dir、resource 检查 | 返回仍兼容 `ok/stage/message/reason_code/missing_fields/effective_config/saved_config`，新增信息放 `metadata` | `cargo test --manifest-path backend/Cargo.toml agentflow system_config` | 缺字段、认证失败、runner missing、pipeline invalid、output unwritable、resource unavailable 均有中文 message | P1 必做；P2 才扩展更多 provider |
| BE-PREFLIGHT-02 | backend | `system_config.rs`、`db/system_config.rs` | 4.1、5.9.1 | `agentflow/specs.py` `ProviderConfig` | 不回传明文 `apiKey`、Authorization、Cookie、customHeaders | API 响应和日志中只出现脱敏值 | 单测断言响应不含密钥样例 | preflight 失败不泄露凭据 | P1 必做 |

### 5.2 Agent Task 生命周期

| ID | Owner | Files | Plan refs | AgentFlow refs | Implementation contract | Acceptance | Tests | Failure behavior | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BE-CREATE-01 | backend | `backend/src/routes/agent_tasks.rs` | 4.1、5.9.4 | N/A | 创建任务保存项目和审计范围快照，递归拒绝禁止字段 | 新任务 status 初始稳定，scope 中无静态候选 | `cargo test --manifest-path backend/Cargo.toml agent_tasks` | 非法 payload 返回 400 | P1 必做 |
| BE-START-01 | backend | `agent_tasks.rs` | 5.4、5.9.2 | `agentflow/cli.py` `run` | `start_agent_task` 顺序固定：load task -> preflight -> build_input -> run_pipeline -> import_result -> refresh aggregates -> save snapshot | 成功任务进入 completed，失败任务进入 failed/cancelled；不出现静默成功 | `cargo test --manifest-path backend/Cargo.toml agent_tasks agentflow` | panic/timeout/exit code/schema/import 失败均写 event/checkpoint/error_message | P1 必做 |
| BE-CANCEL-01 | backend | `agent_tasks.rs`、`runtime/agentflow/runner.rs` | 5.5、11.1 | `agentflow/cli.py` `cancel`、`orchestrator.cancel` | 用户取消时终止 runner 子进程或调用受控 cancellation 路径 | 任务进入 cancelled 或 failed-with-cancel-diagnostic | cancel 单测 | 写入取消事件和 checkpoint | P1 必做；可选 AgentFlow RunStore cancel，不能依赖前端直接调用 |
| BE-DETAIL-01 | backend | `agent_tasks.rs` | 4.3、4.4、8.2 | N/A | detail/findings/report endpoints 返回统一漏洞详情所需字段 | `/agent-audit/:taskId` 和 `/finding-detail/agent/:taskId/:findingId` 均可渲染 | route/API 单测 | 缺字段不应导致前端空白 | P1 必做 |

### 5.3 Task State 吸收

| ID | Owner | Files | Plan refs | AgentFlow refs | Implementation contract | Acceptance | Tests | Failure behavior | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BE-STATE-01 | backend | `backend/src/db/task_state.rs` | 5.9.3 | `agentflow/specs.py` `RunRecord` | 通过可选字段或 `audit_scope.agentflow.*` 保存 `runtime/run_id/topology_version/input_digest/artifact_index/report_snapshot/feedback_bundle` | 旧快照可反序列化，新快照字段齐备 | task_state serde/default 单测 | 反序列化失败阻断启动并给出迁移诊断 | P1 必做；P2 可提升稳定字段为显式列 |
| BE-STATE-02 | backend | `task_state.rs` | 8.1、8.2 | `agentflow/specs.py` `NodeResult` | finding 保存 source node/role、artifact refs、risk lifecycle、confidence history、data_flow、impact、remediation、verification | 统一详情页能展示 P1 最低字段 | finding detail API 单测 | 缺必需 finding 字段时 importer 拒绝 | P1 必做 |

### 5.4 Runtime Adapter 模块

| ID | Owner | Files | Plan refs | AgentFlow refs | Implementation contract | Acceptance | Tests | Failure behavior | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BE-RUNTIME-01 | backend | `backend/src/runtime/agentflow/mod.rs`、`contracts.rs` | 5.1、5.2、5.3.1 | `agentflow/specs.py` | 定义 Argus runner input/output、event envelope、finding、checkpoint、report、diagnostics 结构 | schema 与计划字段一致 | contract/schema 单测 | schema invalid 时 task failed | P1 必做 |
| BE-RUNTIME-02 | backend | `pipeline.rs` | 7.1、7.3 | `agentflow/dsl.py` `Graph`/`fanout`/`merge` | 渲染固定 P1 pipeline，暴露 `env-inter`、`vuln-reasoner`、`audit-reporter` 三类语义 role | validate 通过，node metadata 有 role | pipeline render test + `agentflow validate` | pipeline invalid -> `pipeline_invalid` | P1 固定 DAG；P3 才拓扑 mutation |
| BE-RUNTIME-03 | backend | `preflight.rs` | 5.9.1、10.2、11.6 | `agentflow/cli.py` `validate`/`doctor` | 检查 runner 命令、pipeline validate、output_dir、资源预算、凭据可达性 | reason_code 粒度符合计划 | preflight 单测 | 阻止启动并保存 failed task | P1 必做 |
| BE-RUNTIME-04 | backend | `runner.rs` | 5.4、6、6.2 | `agentflow/cli.py` `run`、`store.py` | 受控调用 runner，收集 exit code、stdout/stderr tail、run_dir；默认各 tail 64KB 并脱敏 | 成功/失败均返回结构化 outcome | runner fake process tests | runner exit 非 0 -> failed | P1 使用 CLI/container；不启用 `serve` |
| BE-RUNTIME-05 | backend | `importer.rs` | 5.3.2、6.1、8.1 | `RunRecord`/`RunEvent`/`NodeResult` | 将 Argus business output 导入 task/events/checkpoints/findings/report；可参考 AgentFlow native artifacts，但不能直接当 finding | 聚合计数、report summary、agent_tree 刷新 | importer fixture tests | import invalid -> failed + `import_failed` checkpoint | P1 必做 |

## 6. Runner 与 AgentFlow Adapter 清单

### 6.1 AgentFlow 源码事实

本轮核对的 AgentFlow 源码事实用于约束 P1 adapter：

- Python 包名 `agentflow`，版本 `0.1.0`，要求 Python `>=3.10`。
- CLI 入口为 `agentflow = agentflow.cli:app`。
- P1 允许使用的 CLI：`agentflow validate`、`agentflow run`、必要时 `agentflow inspect`、`agentflow doctor`、`agentflow smoke`。
- P1 禁止把 `agentflow serve` 暴露为 Argus 前端或普通用户调用路径。
- `RunStore` 默认将状态写入 `.agentflow/runs/<run_id>/run.json` 和 `events.jsonl`。
- 原生 `RunEvent` 结构为 `timestamp/run_id/type/node_id/data`，不满足 Argus event envelope 的 `sequence/role/visibility/correlation_id/topology_version` 要求。
- `Graph/DAG` 支持 `concurrency`、`max_iterations`、`scratchboard`、`fanout`、`merge`、`on_failure`。
- target 支持 `local/container/ssh/ec2/ecs`；P1 只允许 local 或受控 container。

### 6.2 Runner 执行合同

| ID | Owner | Files | Plan refs | AgentFlow refs | Implementation contract | Acceptance | Tests | Failure behavior | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RUN-SOURCE-01 | runner | runner Dockerfile/script、lock file | 6、11.2 | `pyproject.toml`、`LICENSE` | 固定 AgentFlow commit/version/digest，保留 license，不使用生产动态安装脚本 | 镜像内可输出版本/commit 信息 | `docker compose build agentflow-runner` | build 失败不得启动任务 | P1 必做 |
| RUN-CMD-01 | runner/backend | `runner.rs`、runner entrypoint | 6、11.2 | `agentflow/cli.py` | P1 顺序为 `agentflow validate <pipeline>` 后 `agentflow run <pipeline> --output json`；`--output json-summary` 只用于诊断摘要，不作为业务 output | validate 和 run 结果均被保存/脱敏 | runner integration/smoke | validate fail -> `pipeline_invalid` | P1 禁止 `serve` |
| RUN-OUTPUT-01 | runner/backend | `backend/agentflow/schemas/runner_output.schema.json`、`importer.rs` | 5.3.1、6.2 | `store.py`、`specs.py` | runner 最终必须产出 Argus 约定 JSON；AgentFlow native `run.json/events.jsonl` 只能作为 adapter 输入和诊断 | output 通过 schema 后才导入 | schema fixture tests | schema invalid -> failed | P1 必做 |
| RUN-ARTIFACT-01 | runner/backend | output dir、artifact index code | 6.2、10.1 | `store.py` artifact paths | artifact index 只记录任务输出目录内相对路径、type、size、sha256、producer node、created_at | 越界路径被拒绝 | path traversal tests | `runner_output_invalid` | P1 必做 |
| RUN-REDACT-01 | runner/backend | `runner.rs`、`importer.rs` | 6.2、10 | AgentFlow launch artifacts may contain env | stdout/stderr/events/report/artifacts 导入前脱敏 apiKey、Authorization、Cookie、customHeaders、host sensitive path、Docker socket | 测试 fixture 中密钥不出现在 task state | redaction tests | 命中泄露则拒绝导入 | P1 必做 |

## 7. AgentFlow 到 Argus 映射矩阵

| AgentFlow 原生来源 | 原生含义 | Argus P1 目标 | 导入规则 |
| --- | --- | --- | --- |
| `RunRecord.id` | AgentFlow run id | `AgentTaskRecord.audit_scope.agentflow.run_id` 或显式 `run_id` | 只作诊断和 artifact 索引，不当 task id |
| `RunRecord.status` | queued/running/completed/failed/cancelled | `AgentTaskRecord.status` | completed/failed/cancelled 映射；queued/running 只用于中间事件 |
| `RunRecord.started_at/finished_at` | 原生时间 | task started/completed | 缺失时后端导入时间兜底 |
| `RunRecord.pipeline.nodes` | 展开后的 node spec | `agent_tree` | 必须补充 Argus role、topology_version、duration、finding count |
| `NodeResult.status` | node 状态 | checkpoint 和 agent_tree node status | P1 前端不得假设固定 node 数量 |
| `NodeResult.output/final_response` | node 文本输出 | event summary、report source、diagnostics | 不直接解析为 finding，除非 adapter 输出符合 Argus schema |
| `NodeResult.stdout_lines/stderr_lines` | 原生日志 | diagnostics stdout/stderr tail | 截断 64KB，脱敏后保存 |
| `RunEvent` | timestamp/type/node_id/data | `AgentEventRecord` | 必须补齐 sequence、role、visibility、correlation_id、topology_version |
| `trace.jsonl` | agent trace | artifact refs / diagnostics | P1 默认索引，不直接展示完整原文 |
| `scratchboard.md` | 共享上下文 | diagnostics/artifact refs | 前端不得直接读取 |
| Argus runner output JSON | adapter 业务输出 | findings/events/checkpoints/report | 唯一可导入业务结果源；必须 schema 校验 |

## 8. 前端编码清单

| ID | Owner | Files | Plan refs | AgentFlow refs | Implementation contract | Acceptance | Tests | Failure behavior | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FE-CONFIG-01 | frontend | `frontend/src/components/system/SystemConfig.tsx`、API client | 4.1、9 | N/A | 展示模型 API 未配置、测试中、成功、失败、需重新配置状态 | 用户可保存并测试模型配置 | `pnpm --dir frontend test:node -- agent` | 后端 reason_code 显示中文可读提示 | P1 必做 |
| FE-CREATE-01 | frontend | `TaskManagementIntelligent.tsx`、创建弹窗 | 4.1、4.6、9 | N/A | 创建智能审计任务只选择项目和智能审计范围；payload 不含禁止字段 | UI 不出现静态任务选择器 | frontend test payload snapshot | 后端 400 显示可读错误 | P1 必做 |
| FE-TASKS-01 | frontend | `/tasks/intelligent` 页面 | 4.3、9.1 | N/A | 列表展示任务运行态、失败原因、最近阶段和实时简报状态 | failed/running/completed 均能扫描阅读 | frontend node tests | SSE 断开展示非阻塞诊断 | P1 必做 |
| FE-DETAIL-01 | frontend | `AgentAudit/TaskDetailPage.tsx` | 4.3、8.2、9.1 | AgentFlow node status names | 展示动态 node DAG、role、heartbeat、事件、checkpoint、report summary、finding list、artifact refs | 不依赖固定 node 数量/角色名称 | `pnpm --dir frontend test:node -- agent` | schema/import/runner 失败展示原因 | P1 必做 |
| FE-FINDING-01 | frontend | `FindingDetail.tsx`、`finding-detail/*`、`findingRoute.ts` | 4.4、8.2 | N/A | `/finding-detail/agent/:taskId/:findingId` 展示标题、等级、位置、证据、影响、修复、验证、AgentFlow 来源 | 点击 finding 能跳转并看到完整字段 | route/view model tests | 缺 finding 显示 not found，不空白 | P1 必做 |

## 9. 安全与资源清单

| ID | Owner | Files | Plan refs | AgentFlow refs | Implementation contract | Acceptance | Tests | Failure behavior | Boundary |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SEC-SERVE-01 | backend/runner | runner config、compose | 9、10、14 | `agentflow/app.py` | P1 不启动或暴露 `agentflow serve`；不设置 `AGENTFLOW_API_ALLOW_PIPELINE_PATH=1` | compose/env 中无该开放路径 | `rg -n "AGENTFLOW_API_ALLOW_PIPELINE_PATH|agentflow serve"` | 发现配置即阻断验收 | P1 必做 |
| SEC-MOUNT-01 | backend/runner | runner Docker/compose | 10.1 | `runners/container.py` | 项目源码只读挂载；写入任务隔离 workspace/output dir | runner 无法写回原项目目录 | smoke/manual mount check | 写入越界 -> failed | P1 必做 |
| SEC-SOCKET-01 | backend/runner | compose/runtime | 10.1 | AgentFlow container target | agent 节点不得直接挂载宿主机 Docker socket | compose 中只有 Argus 后端或受控管理面访问 socket | compose grep/check | 违反则阻断启动 | P1 必做 |
| RES-BUDGET-01 | backend | `preflight.rs`、resource config | 10.2、11.6 | `Graph(concurrency)` | 默认单机 32GB/20 核预算下限制并发；资源不足排队或拒绝 | preflight reason_code=`resource_unavailable` | resource budget unit tests | 不继续启动新 runner | P1 基础检查；P3 才动态扩缩 |
| SEC-PATH-01 | backend | `importer.rs`、artifact download route | 10 | N/A | artifact 下载经 Argus 鉴权和路径规范化 | `../`、绝对路径、socket path 被拒绝 | path traversal tests | 拒绝导入或返回 403/404 | P1 必做 |

## 10. Fixture 与测试矩阵

### Backend fixtures

| Fixture | 目的 | 必须断言 |
| --- | --- | --- |
| `agentflow_runner_success.json` | happy path 导入 | task completed；events/checkpoints/findings/report/agent_tree 聚合正确 |
| `agentflow_runner_empty_findings.json` | 无漏洞完成 | task completed；report 显示未发现可确认漏洞；页面不空白 |
| `agentflow_runner_failed.json` | runner 失败 | task failed；`runner_failed` event；中文 error_message |
| `agentflow_runner_invalid_schema.json` | schema invalid | task failed；`runner_output_invalid` event；`import_failed` checkpoint |
| `agentflow_forbidden_static_input.json` | 静态来源禁止 | importer 拒绝；不产生 finding |
| `agentflow_forbidden_static_engine_origins.json` | 扩展静态引擎来源禁止 | `opengrep/static/bandit/gitleaks/phpstan/pmd` 和任意 static scan/finding bootstrap origin 均被拒绝 |
| `agentflow_native_runrecord_only.json` | 负面证明 | 原生 RunRecord 不能直接导入为业务 finding |
| `agentflow_native_runevent_only.jsonl` | 负面证明 | 原生 RunEvent 缺 sequence/role/visibility 时必须经 adapter 补齐或拒绝 |
| `agentflow_native_noderesult_only.json` | 负面证明 | NodeResult output 不能直接当漏洞报告 |

### Verification commands

```bash
cargo test --manifest-path backend/Cargo.toml agentflow
cargo test --manifest-path backend/Cargo.toml agent_tasks
pnpm --dir frontend test:node -- agent
pnpm --dir frontend type-check
pnpm --dir frontend lint
docker compose build agentflow-runner
docker compose run --rm agentflow-runner agentflow --help
docker compose run --rm agentflow-runner agentflow validate /app/backend/agentflow/pipelines/intelligent_audit.py
```

### Manual smoke

1. `docker compose up --build`。
2. 在系统配置中填写模型 API 并通过连接测试。
3. 打开 `/tasks/intelligent`，选择已导入项目和审计范围创建智能审计任务。
4. 启动任务。
5. 等待 completed 或明确 failed。
6. 查看 `/tasks/intelligent` 状态、阶段和失败诊断。
7. 查看 `/agent-audit/:taskId` 执行图、报告摘要、漏洞统计和 finding 列表。
8. 如存在 finding，打开 `/finding-detail/agent/:taskId/:findingId`。
9. 检查 task state 存在 AgentFlow run id、events、findings、checkpoints 和 report summary。

## 11. 状态与失败转换表

| 场景 | Trigger | Task status | Event | Checkpoint | UI 要求 |
| --- | --- | --- | --- | --- | --- |
| 模型配置缺失 | `agent-preflight` missing fields | failed | `preflight_failed` | `preflight_failed` | 引导配置模型 API |
| runner 缺失 | runner command/image missing | failed | `runner_missing` | `preflight_failed` | 展示 runner 不可用 |
| pipeline invalid | `agentflow validate` exit non-zero | failed | `pipeline_invalid` | `preflight_failed` | 展示 validate 摘要 |
| 输出目录不可写 | output dir check fail | failed | `output_dir_unwritable` | `preflight_failed` | 展示目录诊断 |
| 资源不足 | resource budget fail | queued 或 failed | `resource_unavailable` | `preflight_failed` 或 `queued` | 明确排队或拒绝 |
| runner exit 非 0 | child process fail | failed | `runner_failed` | `runner_failed` | 展示 stdout/stderr tail |
| runner output schema invalid | schema validation fail | failed | `runner_output_invalid` | `import_failed` | 展示 schema 错误摘要 |
| import invalid | event sequence/path/lifecycle invalid | failed | `import_failed` | `import_failed` | 展示导入失败原因 |
| 用户取消 | cancel request | cancelled 或 failed | `task_cancelled` | `cancelled` | 展示已取消 |
| 无 finding 完成 | valid completed empty findings | completed | `report_generated` | `completed` | 展示未发现可确认漏洞 |

## 12. Definition of Done

P1 只有在以下条件全部满足时才算完成：

- 模型 API 配置、连接测试和 `agent-preflight` 可区分缺凭据、模型不可达、配置非法、runner 缺失和 pipeline invalid。
- 智能审计创建和启动路径完全拒绝静态任务/finding 候选输入。
- `start_agent_task` 走 AgentFlow runtime adapter，不再以未配置失败作为最终实现路径。
- runner 使用固定 AgentFlow 来源，执行 `validate` 后再 `run`，并将输出导入 Argus。
- Argus task state 中存在 run id、agent_tree、events、checkpoints、findings、report summary、diagnostics。
- `/tasks/intelligent`、`/agent-audit/:taskId`、`/finding-detail/agent/:taskId/:findingId` 路径可完成用户可见闭环。
- 失败路径落库且中文可读，不出现静默成功或空白页面。
- Backend、frontend、runner 和 manual smoke 验证均完成并记录结果。

## 13. Team Execution Runbook

本节是 `$team` 执行入口。Team leader 必须先冻结共享合同，再分派 lane。任何 worker 不得跨出自己的独占写入范围；如必须改共享文件，先向 leader 报告 contract delta，由 leader 调整 lane ownership。

### 13.1 Team 执行原则

- 先合同，后实现：`contracts/schema` lane 先冻结 runner input/output、event envelope、finding/report view model、reason_code 和禁止字段。
- 独占写入：每个 lane 只写自己的 scope；共享文件必须指定单一 owner。
- 并行不抢接口：frontend、runner、importer 只能依赖冻结后的 schema/API view model。
- 验证独立收口：verification lane 不负责补功能，只负责执行证据收集；发现失败后把修复派回对应 owner。
- 非目标不协商：禁止静态/Opengrep 候选输入，禁止暴露 `agentflow serve`，禁止 remote target，禁止 P2/P3 动态专家能力。

### 13.2 Freeze Points

| Freeze | Owner | 内容 | 解冻条件 | 阻塞的 lane |
| --- | --- | --- | --- | --- |
| Freeze A | team leader + contracts/schema | P1 非目标、禁止字段、静态输入门禁、`agentflow serve` 禁用、target 限制 | section 4/9 无冲突，所有 lane ACK | 全部 lane |
| Freeze B | contracts/schema | runner input/output JSON schema、Argus event envelope、checkpoint/finding/report schema | schema fixture 通过，importer/frontend ACK | backend lifecycle、runtime/importer、runner/compose、frontend |
| Freeze C | backend lifecycle | `AgentTaskRecord`、event、checkpoint、finding detail view model、reason_code | backend route 和 task_state 单测通过 | frontend、verification |
| Freeze D | frontend | API client 类型、route params、页面 view model | frontend payload/view tests 通过 | verification |
| Freeze E | verification | section 10 命令、manual smoke、DoD 证据格式 | 全 lane 合并后命令清单稳定 | final sign-off |

### 13.3 Lane 拓扑

```text
Freeze A/B: contracts/schema
  -> fanout:
     - backend lifecycle
     - runtime/importer
     - runner/compose
     - tests/fixtures
  -> Freeze C: backend API + task state contract
  -> frontend
  -> Freeze D: frontend API client + view model
  -> Freeze E: verification command and smoke path
  -> verification
```

允许并行规则：

- `backend lifecycle` 和 `runtime/importer` 可在 Freeze B 后并行，但 `start_agent_task` 集成点由 backend lifecycle owner 最终合并。
- `runner/compose` 可在 Freeze B 后并行，但不得更改 Rust task state 或 frontend 类型。
- `frontend` 只能在 Freeze C 后实现 API/view model 绑定；Freeze C 前只允许读文件和准备测试计划。
- `tests/fixtures` 可在 Freeze B 后准备 fixture，但生产合同变更必须回到对应 owner。
- `verification` 在所有 lane 完成前只维护命令清单和证据模板，不改业务实现。

### 13.4 Lane Ownership Table

| Lane | Agent 类型 | 独占写入范围 | 不得修改 | Depends On | 必交付物 | 推理建议 |
| --- | --- | --- | --- | --- | --- | --- |
| contracts/schema | architect 或 executor | `backend/src/runtime/agentflow/contracts.rs`、`backend/agentflow/schemas/*`、schema fixture skeleton | frontend pages、compose、route handler 业务流程 | Freeze A | frozen runner input/output、event envelope、checkpoint/finding/report schema、禁止字段常量 | high |
| backend lifecycle | executor | `backend/src/routes/agent_tasks.rs`、`backend/src/routes/system_config.rs`、`backend/src/db/task_state.rs` 中 task/event/finding/checkpoint 字段 | runner Docker/compose、frontend UI、pipeline 文件 | Freeze B | create/start/cancel/detail/preflight 生命周期、task_state serde/default 测试 | high |
| runtime/importer | executor | `backend/src/runtime/agentflow/{mod,preflight,pipeline,runner,importer}.rs`、backend runtime 单测 | frontend UI、compose、system config 页面 | Freeze B、backend lifecycle 接口 ACK | fake runner、pipeline render、importer fixture、redaction/path traversal 测试 | high |
| runner/compose | build-fixer 或 executor | runner Dockerfile/script、runner entrypoint、`docker-compose.yml` runner service、`backend/agentflow/pipelines/*`、prompt files | Rust task state model、frontend API client | Freeze B | fixed AgentFlow source、`agentflow --help`、`validate`、runner smoke 证据 | high |
| frontend | executor | `frontend/src/pages/TaskManagementIntelligent.tsx`、`frontend/src/pages/AgentAudit/TaskDetailPage.tsx`、`frontend/src/pages/FindingDetail.tsx`、`frontend/src/shared/api/agentTasks.ts`、相关 test/view model 文件 | backend Rust runtime、runner/compose | Freeze C、Freeze D draft | payload snapshot、task/detail/finding 页面测试、中文失败提示 | medium |
| tests/fixtures | test-engineer | backend fixture files、frontend fixture files、test harness、manual smoke notes | production contracts，除非 owner 明确授权 | Freeze B、Freeze C | section 10 fixture matrix 全部落地，负面 fixture 覆盖 native RunRecord/RunEvent/NodeResult | medium |
| verification | verifier | verification notes、evidence summary、必要的测试 harness 修复 | feature implementation files，除非 leader 回派 | 所有 lane | final command log、manual smoke evidence、DoD checklist | high |

### 13.5 Worker Packet Template

Team leader 给每个 worker 的任务说明必须使用此模板，避免 worker 自行扩展范围：

```text
Lane: <lane name>
Goal: <one-sentence lane goal>
Exclusive write scope: <files/dirs>
Must not edit: <files/dirs>
Depends on: <Freeze/Lane>
Contracts to preserve:
- no static/Opengrep candidate input
- no exposed agentflow serve
- no remote target
- no P2/P3 dynamic expert work
Required checklist IDs: <IDs from this document>
Required tests: <commands or fixture tests>
Handoff report:
- changed files
- contracts changed
- tests run and result
- blocked dependencies
- remaining risk
```

### 13.6 Shared Contract Handoff

每个 lane 结束时必须回报以下内容；缺任一项不得进入集成：

- Changed files：只列自己实际改过的文件。
- Contracts changed：schema/API/event/reason_code/task_state/view model 是否变化；无变化写 `none`。
- Tests run：命令、结果和失败摘要。
- Blocked dependencies：依赖哪个 lane 的哪个 freeze 或文件。
- Remaining risk：不能用“无”掩盖未跑测试；未验证项必须写清楚。

### 13.7 Merge Gates

| Gate | 条件 | 不满足时动作 |
| --- | --- | --- |
| Gate 1: Contract freeze | Freeze A/B 完成，禁止字段和 runner output schema 有测试或 fixture | 停止 backend/frontend/runner 业务实现，回 contracts/schema |
| Gate 2: Backend lifecycle | create/start/preflight/cancel/detail 状态迁移可测试，失败均落库 | 回 backend lifecycle 或 runtime/importer |
| Gate 3: Runner/import | `agentflow validate` 和 fake/real runner output 都经过 schema/importer | 回 runner/compose 或 runtime/importer |
| Gate 4: Frontend binding | API client 类型和页面 view model 与 Freeze C/D 一致 | 回 frontend 或 backend lifecycle |
| Gate 5: Static-input defense | create/start/import/frontend payload 四层禁止字段均有测试，且覆盖 `opengrep/static/bandit/gitleaks/phpstan/pmd` 和任意 static scan/finding bootstrap origin | 回对应 owner；不得进入 smoke |
| Gate 6: Final verification | section 10 命令、manual smoke、section 12 DoD 全部有证据 | 回失败 lane 修复后重跑 |

### 13.8 Conflict Rules

- `agent_tasks.rs` 最终集成 owner 是 backend lifecycle lane；runtime/importer 只能通过明确函数接口接入。
- `contracts.rs` 和 `backend/agentflow/schemas/*` 最终 owner 是 contracts/schema lane；其他 lane 发现 schema 缺口时提交 contract delta，不直接扩写。
- `agentTasks.ts` 最终 owner 是 frontend lane；backend 不直接改前端类型。
- `docker-compose.yml` runner service owner 是 runner/compose lane；其他 lane 不调整 runner 镜像、env 或 mount。
- 测试 lane 可以新增 failing fixture；生产代码修复必须派回 owner。

### 13.9 Team Verification Path

Verification lane 按以下顺序收口：

1. 运行 backend targeted tests：`cargo test --manifest-path backend/Cargo.toml agentflow`。
2. 运行 backend route/state tests：`cargo test --manifest-path backend/Cargo.toml agent_tasks`。
3. 运行 frontend targeted tests：`pnpm --dir frontend test:node -- agent`。
4. 运行 frontend static checks：`pnpm --dir frontend type-check`、`pnpm --dir frontend lint`。
5. 构建 runner：`docker compose build agentflow-runner`。
6. 验证 runner CLI：`docker compose run --rm agentflow-runner agentflow --help`。
7. 验证 pipeline：`docker compose run --rm agentflow-runner agentflow validate /app/backend/agentflow/pipelines/intelligent_audit.py`。
8. 执行 section 10 manual smoke。
9. 对照 section 12 Definition of Done 标记 pass/fail；fail 项必须回派到 lane owner。

### 13.10 `$team` 启动语句

`$team` 必须从已 attach 的 tmux OMX CLI shell 启动，便于 leader 观察 worker 输出、mailbox、status 和 shutdown。当前 `N:agent-type` 形式通常表示同一 worker prompt 下启动 N 个 worker；除非当前 runtime 明确支持按 worker 分配不同 agent type，否则 `architect`、`build-fixer`、`test-engineer`、`verifier` 在本文中是 lane function，不是强制不同 runtime agent type。

推荐启动 hint：

```bash
omx team 7:executor "按 plan/ai_audit/sourcecode_agent_audit_code_checklist.md 的 Team Execution Runbook 执行 AgentFlow 智能审计 P1。先冻结 Freeze A/B，再按 lane 独占写入范围并行实现。禁止静态/Opengrep/Bandit/Gitleaks/PHPStan/PMD 或任何静态扫描候选输入，禁止暴露 agentflow serve，禁止 remote target，禁止 P2/P3 动态专家能力。每个 worker 必须使用 Worker Packet Template，并回报 changed files、contracts changed、tests run、blocked dependencies、remaining risk。verification lane 最终按 section 10、section 12、section 13.9、section 13.11 收集证据。"
```

等价 keyword 入口：

```text
$team 7:executor "按 plan/ai_audit/sourcecode_agent_audit_code_checklist.md 的 Team Execution Runbook 执行 AgentFlow 智能审计 P1。先冻结 Freeze A/B，再按 lane 独占写入范围并行实现。禁止静态/Opengrep/Bandit/Gitleaks/PHPStan/PMD 或任何静态扫描候选输入，禁止暴露 agentflow serve，禁止 remote target，禁止 P2/P3 动态专家能力。每个 worker 必须使用 Worker Packet Template，并回报 changed files、contracts changed、tests run、blocked dependencies、remaining risk。verification lane 最终按 section 10、section 12、section 13.9、section 13.11 收集证据。"
```

Worker 映射：

| Worker | Lane function | Worker Packet 要点 |
| --- | --- | --- |
| worker-1 | contracts/schema | Freeze A/B、schema、禁止字段常量、event/finding/report contract |
| worker-2 | backend lifecycle | create/start/cancel/detail/preflight、task state、reason_code |
| worker-3 | runtime/importer | preflight/pipeline/runner/importer、fake runner、redaction/path traversal |
| worker-4 | runner/compose | fixed AgentFlow source、runner image、compose、pipeline validate/run |
| worker-5 | frontend | `/tasks/intelligent`、`/agent-audit`、finding detail、API client types |
| worker-6 | tests/fixtures | backend/frontend fixtures、native RunRecord/RunEvent/NodeResult negative fixtures、static-engine negative fixtures |
| worker-7 | verification | command evidence、manual smoke、DoD、team lifecycle evidence |

### 13.11 Team Lifecycle Evidence

Verification lane 必须同时验证 `$team` 编排本身，避免只验证代码而漏掉 worker 未完成或未关闭：

| Lifecycle gate | 必须证据 | 失败处理 |
| --- | --- | --- |
| Team startup | tmux session/pane 或 OMX team 启动输出；7 个 worker 已创建；leader 已发布 section 13.5 packet | 未启动齐全则不得开始实现 |
| Worker ACK/mailbox | 每个 worker 明确 ACK 自己的 lane、exclusive write scope、must-not-edit、depends-on、required tests | 未 ACK 的 worker 重新派发 packet |
| Periodic status/await | leader 周期性记录 `status`/`await` 摘要，至少覆盖 Freeze B、Freeze C/D、final verification 前 | 状态缺失时暂停合并，先确认 worker 结果 |
| Terminal task counts | shutdown 前统计 7 个 lane 的 completed/blocked/failed；blocked/failed 必须有回派或明确剩余风险 | 不允许在未知 worker 状态下宣称完成 |
| Shutdown evidence | team 关闭或转交证据；无仍在运行的实现 worker；verification lane 保存最终 evidence summary | 未关闭时不得结束交付 |

## 14. 后续执行分工

### `$ralph` 顺序执行建议

```text
$ralph 按 plan/ai_audit/sourcecode_agent_audit_code_checklist.md 执行 P1，先完成 backend runtime/agentflow 与 importer，再接 runner/preflight，最后接前端展示和 smoke 验证
```

适合一个 owner 严格按依赖顺序推进。推荐 reasoning：high。

### `$team` 并行执行建议

优先使用 section 13 的 Team Execution Runbook。本小节只保留简短 staffing 摘要。

| Lane | Agent 类型 | 范围 | 推理建议 | 输出 |
| --- | --- | --- | --- | --- |
| contracts/schema | architect 或 executor | shared contracts 和 schema | high | Freeze A/B |
| backend lifecycle | executor | `agent_tasks.rs`、`system_config.rs`、`task_state.rs` | high | create/start/preflight/state tests |
| runtime/importer | executor | `backend/src/runtime/agentflow/*`、schemas/importer | high | contracts/runner/importer tests |
| runner/compose | build-fixer 或 executor | runner image、compose、pipeline validate/run | high | build and runner smoke |
| frontend | executor | `/tasks/intelligent`、`/agent-audit`、finding detail | medium | frontend tests |
| tests/fixtures | test-engineer | backend fixtures、frontend payload tests | medium | fixture matrix |
| verification | verifier | commands and manual smoke evidence | high | final evidence summary |

建议启动语句：

```text
$team 7:executor "按 plan/ai_audit/sourcecode_agent_audit_code_checklist.md 的 section 13 Team Execution Runbook 并行执行 AgentFlow 智能审计 P1，先冻结 Freeze A/B，再按 worker-1..worker-7 映射分派 lane，严格保留 Argus 控制面，禁止任何静态扫描候选输入，最终按 section 13.9/13.11 验证模型 API 配置到统一漏洞详情闭环和 team 生命周期证据。"
```

## 15. P2/P3 预留边界

P2 可做：

- 智能审计结果归一增强。
- Markdown/PDF 或既有导出格式。
- 稳定 metadata 提升为显式字段或数据库列。
- `feedback_bundle` 指标化。

P3 可做：

- 动态 fanout 和拓扑变更。
- 规则表驱动 `add_expert`、`scale_out`、`fix_config`。
- Docker stats 采样、资源阈值动作、动态专家节点生命周期审计。
- 管理员显式启用的 remote target 或 GPU 本地推理。

P2/P3 不得阻塞 P1 的模型配置、项目扫描、runner/import、报告摘要和统一漏洞详情闭环。
