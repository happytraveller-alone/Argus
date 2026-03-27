# 智能扫描 / 混合扫描 Skill 与 Evidence 对齐实施方案

## 阅读定位

- **文档类型**：Implementation reference。
- **目标读者**：正在修改 scan-core skill catalog、配置页外部工具展示、AgentAudit evidence 视图的实现者。
- **阅读目标**：把“运行时真实会触发的 skill”“配置页实际展示的 skill”“新版 evidence 视图能展示的 skill”收敛成一套单一事实源。
- **建议前置**：先读 [../workflow_overview.md](../workflow_overview.md) 和 [../agent_tools.md](../agent_tools.md)。
- **术语入口**：如果你还没统一 `AgentTask`、智能扫描、混合扫描、unified skill catalog 等词，先读 [../../glossary.md](../../glossary.md)。

## 1. 背景与目标

本方案只处理当前 `AgentTask` 体系下的智能扫描 / 混合扫描，不扩展到独立静态扫描或通用 workflow skill catalog。

当前实现里，运行时真实 skill 的真相源已经很明确：

- scan-core catalog 定义在 `backend/app/services/agent/skills/scan_core.py:6`
- 智能扫描 / 混合扫描真实工具注入在 `backend/app/api/v1/endpoints/agent_tasks_execution.py:1864`、`1880`、`1985`

因此这次对齐的目标不是“再补一套说明文档”，而是把以下三处收敛成同一集合：

1. 智能扫描 / 混合扫描运行时真实会触发的 scan-core skill。
2. 配置页 `/scan-config/external-tools` 和详情页实际展示的 skill。
3. `AgentAudit` 新版 evidence 视图可以原生渲染的 tool result。

本次统一后的展示范围固定为 17 个 runtime-visible scan-core skills：

- 基础读代码 / 定位：`list_files`、`search_code`、`get_code_window`、`get_file_outline`、`get_function_summary`、`get_symbol_body`、`locate_enclosing_function`
- 分析：`smart_scan`、`quick_audit`、`pattern_match`、`dataflow_analysis`、`controlflow_analysis_light`、`logic_authz_analysis`
- 验证 / 报告：`run_code`、`sandbox_exec`、`verify_vulnerability`、`create_vulnerability_report`

这 17 个 skill 才是配置页展示集合。`read_file`、`extract_function` 仅保留历史 evidence 兼容解析；`think`、`reflect` 不属于当前 runtime scan-core skill，不进入配置页展示集合。

自 `tool_evidence_protocol = native_v1` 起，`tool_result` 的正式协议固定为：

- `tool_output.result`：时间线 / 导出使用的文本结果
- `tool_output.truncated`：是否截断
- `tool_output.metadata`：原生结构化 evidence，包含 `render_type`、`display_command`、`command_chain`、`entries`
- `event_metadata`：只保留 `tool_status`、`tool_call_id`、`validation_error`、`input_repaired`、`mcp_*`、`cache_*`、`write_scope_*` 等运行态字段

历史任务不会再做旧文本回填；若任务仍标记为 `legacy` 且未保存原生 evidence，前端只提示“需要重跑任务才能查看结构化详情”。

## 2. 当前不一致点与 Skill 对齐矩阵

当前主要分叉点有 3 处：

- 配置页列表仍把后端 catalog 和前端静态 catalog 混在一起：
  - `frontend/src/pages/intelligent-scan/SkillToolsPanel.tsx:37`
  - `frontend/src/pages/intelligent-scan/externalToolsViewModel.ts:45`
- 配置页详情仍依赖本地静态说明和示例提示词：
  - `frontend/src/pages/ScanConfigExternalToolDetail.tsx:31`
  - `frontend/src/pages/ScanConfigExternalToolDetail.tsx:326`
- 前端静态 catalog 仍把 `think` / `reflect` 当作可展示 skill：
  - `frontend/src/pages/intelligent-scan/skillToolsCatalog.ts:206`

与之相对，scan-core 真正可展示的 skill 集合只来自 `backend/app/services/agent/skills/scan_core.py:6`，当前文件中并没有 `think` / `reflect`。

### Skill 对齐矩阵

| `skill_id` | runtime phase | 当前返回位置 | 目标 `evidence_render_type` | 配置页是否展示 |
| --- | --- | --- | --- | --- |
| `list_files` | base / recon / analysis / verification / orchestrator / report | `backend/app/services/agent/tools/file_tool.py:1850` | `file_list` | 是 |
| `search_code` | base / recon / analysis / verification / orchestrator / report | 现有新协议工具返回，前端已在 `toolEvidence.ts` 中支持 | `search_hits` | 是 |
| `get_code_window` | base / recon / analysis / verification / orchestrator / report | 现有新协议工具返回，前端已在 `toolEvidence.ts` 中支持 | `code_window` | 是 |
| `get_file_outline` | base / recon / analysis / verification / orchestrator / report | 现有新协议工具返回，前端已在 `toolEvidence.ts` 中支持 | `outline_summary` | 是 |
| `get_function_summary` | base / recon / analysis / verification / orchestrator / report | 现有新协议工具返回，前端已在 `toolEvidence.ts` 中支持 | `function_summary` | 是 |
| `get_symbol_body` | base / recon / analysis / verification / orchestrator / report | 现有新协议工具返回，前端已在 `toolEvidence.ts` 中支持 | `symbol_body` | 是 |
| `locate_enclosing_function` | base / recon / analysis / verification / orchestrator | `backend/app/services/agent/tools/file_tool.py:2451` | `locator_result` | 是 |
| `smart_scan` | analysis | `backend/app/services/agent/tools/smart_scan_tool.py:442` | `analysis_summary` | 是 |
| `quick_audit` | analysis | `backend/app/services/agent/tools/smart_scan_tool.py:648` | `analysis_summary` | 是 |
| `pattern_match` | analysis | `backend/app/services/agent/tools/pattern_tool.py:649` | `analysis_summary` | 是 |
| `dataflow_analysis` | analysis / report | `backend/app/services/agent/tools/code_analysis_tool.py:300` | `flow_analysis` | 是 |
| `controlflow_analysis_light` | analysis | `backend/app/services/agent/tools/control_flow_tool.py:111` | `flow_analysis` | 是 |
| `logic_authz_analysis` | analysis | `backend/app/services/agent/tools/logic_authz_tool.py:57` | `flow_analysis` | 是 |
| `run_code` | verification | 现有新协议工具返回，前端已在 `toolEvidence.ts` 中支持 | `execution_result` | 是 |
| `sandbox_exec` | verification | 现有新协议工具返回，前端已在 `toolEvidence.ts` 中支持 | `execution_result` | 是 |
| `verify_vulnerability` | verification | `backend/app/services/agent/tools/sandbox_tool.py:1087` | `verification_summary` | 是 |
| `create_vulnerability_report` | verification | `backend/app/services/agent/tools/reporting_tool.py:248` | `report_summary` | 是 |

这个矩阵是本方案的硬边界：

- 矩阵内 skill 必须同时在运行时、配置页、evidence 视图中可被解释。
- 不在矩阵内的旧工具或辅助工具，不能再由配置页作为 scan-core 展示集合对外暴露。

## 3. 统一后的展示协议

统一后的单一展示元数据源落在 `backend/app/services/agent/skills/scan_core.py:83` 这一层，也就是 `_base_detail(...)` 返回值，不再由前端静态 catalog 补关键字段。

scan-core skill detail 至少要扩展以下展示字段：

- `category`
- `goal`
- `task_list`
- `input_checklist`
- `example_input`
- `pitfalls`
- `sample_prompts`
- `display_type`
- `phase_bindings`
- `mode_bindings`
- `evidence_view_support`
- `evidence_render_type`
- `legacy_visible`

对应接口层同步扩展：

- `backend/app/api/v1/endpoints/skills.py:31`
  - `SkillCatalogItem` 需要暴露配置页列表所需的展示字段，至少包括 `display_type`、`category`、`phase_bindings`、`mode_bindings`、`evidence_view_support`
- `backend/app/api/v1/endpoints/skills.py:52`
  - `SkillDetailResponse` 需要完整暴露详情页字段，替代前端 `skillToolsCatalog.ts` 中的本地说明

配置页可用性视图继续由 scan-core 元数据导出，而不是从前端静态常量反推：

- `backend/app/api/v1/endpoints/config.py:532`

这里的统一原则只有 3 条：

1. scan-core metadata 是配置页和详情页的唯一展示真相源。
2. `skillAvailability` 只负责 readiness，不再偷偷承担展示字段补全。
3. `legacy_visible=false` 的兼容工具可以被旧日志解析，但不能重新出现在配置页列表。

## 4. 前端配置页收口方案

前端当前的问题不是“数据缺一点”，而是“展示真相源有两套”。这次要把配置页列表与详情页都收回到后端 metadata。

### 列表页

修改入口：

- `frontend/src/pages/intelligent-scan/SkillToolsPanel.tsx:37`
- `frontend/src/pages/intelligent-scan/externalToolsViewModel.ts:45`

落地要求：

- `SkillToolsPanel` 继续请求 `/api/v1/skills/catalog?namespace=scan-core`，但不再把返回结果和 `SKILL_TOOLS_CATALOG` merge。
- `buildExternalToolRows(...)` 直接从后端返回字段构建 `capabilities`、`displayType`、`summary`、`category` 等列表展示信息。
- `think` / `reflect` 随着后端 catalog 不再出现，自然从列表消失。

### 详情页

修改入口：

- `frontend/src/pages/ScanConfigExternalToolDetail.tsx:31`
- `frontend/src/pages/ScanConfigExternalToolDetail.tsx:114`
- `frontend/src/pages/ScanConfigExternalToolDetail.tsx:326`

落地要求：

- `SkillOverview` 不再依赖本地 `goal`、`taskList`、`inputChecklist`、`pitfalls`。
- 示例提问 `sample_prompts` 由后端 detail 返回，替换 `buildSkillExamplePrompts(...)` 的本地 hardcode。
- `resolveToolName(...)` 与 detail 页标题直接以 `/skills/{id}` 返回的 metadata 为准。

`frontend/src/pages/intelligent-scan/skillToolsCatalog.ts` 在本次改造后不再充当展示真相源；如果暂时保留，也只能承担兼容兜底，不能继续决定配置页展示集合。

## 5. Evidence 协议扩展与返回值改造锚点

当前前端 evidence 解析入口在：

- `frontend/src/pages/AgentAudit/toolEvidence.ts:1`
- `frontend/src/pages/AgentAudit/components/ToolEvidencePreview.tsx:11`

现有 render type 只覆盖：

- `code_window`
- `search_hits`
- `execution_result`
- `outline_summary`
- `function_summary`
- `symbol_body`

这还不足以承接配置页应展示的全部 17 个 scan-core skill，因此要新增 6 个 render type：

- `file_list`
- `locator_result`
- `analysis_summary`
- `flow_analysis`
- `verification_summary`
- `report_summary`

### 必须改造的 legacy/raw 返回值锚点

- `smart_scan`
  - `backend/app/services/agent/tools/smart_scan_tool.py:442`
- `quick_audit`
  - `backend/app/services/agent/tools/smart_scan_tool.py:648`
- `pattern_match`
  - `backend/app/services/agent/tools/pattern_tool.py:649`
- `dataflow_analysis`
  - `backend/app/services/agent/tools/code_analysis_tool.py:300`
- `controlflow_analysis_light`
  - `backend/app/services/agent/tools/control_flow_tool.py:111`
- `logic_authz_analysis`
  - `backend/app/services/agent/tools/logic_authz_tool.py:57`
- `verify_vulnerability`
  - `backend/app/services/agent/tools/sandbox_tool.py:1087`
- `create_vulnerability_report`
  - `backend/app/services/agent/tools/reporting_tool.py:248`
- `list_files`
  - `backend/app/services/agent/tools/file_tool.py:1850`
- `locate_enclosing_function`
  - `backend/app/services/agent/tools/file_tool.py:2451`

### 渲染协议要求

- `list_files -> file_list`
  - 返回目录、pattern、是否递归、总条目数、前 N 条路径和截断状态。
- `locate_enclosing_function -> locator_result`
  - 返回 `file_path`、目标行、包围函数名、起止行、签名、参数、返回类型、定位引擎与置信度。
- `smart_scan` / `quick_audit` / `pattern_match -> analysis_summary`
  - 返回 severity 汇总、命中数量、重点文件、前 N 条摘要和下一步建议。
  - `pattern_match` 不回退成 `search_hits`，因为这里还要承载 `patterns_checked`、按严重级别统计和命中摘要。
- `dataflow_analysis` / `controlflow_analysis_light` / `logic_authz_analysis -> flow_analysis`
  - 返回 source/sink 或入口点、关键路径摘要、阻断条件、reachability / confidence / engine 等结构化字段。
- `verify_vulnerability -> verification_summary`
  - 返回漏洞类型、目标、payload 摘要、验证 verdict、证据文本、HTTP 状态码或运行状态。
- `create_vulnerability_report -> report_summary`
  - 返回 `report_id`、标题、严重级别、文件位置、验证状态、修复建议摘要。

兼容边界也必须保持明确：

- `read_file`、`extract_function` 继续留在 `toolEvidence.ts` 兼容集合中，只用于历史日志解析。
- 它们不能重新回流到配置页展示集合。
- `push_finding_to_queue`、`save_verification_result`、`update_vulnerability_finding` 属于工作流写回工具，不属于配置页外部工具展示范围。

## 6. 测试计划与验收标准

### 后端测试

- 更新 `backend/tests/test_skill_registry_api.py`
  - 断言 `/skills/catalog` 返回的展示集合等于 17 个 runtime-visible scan-core skills。
  - 断言结果中不包含 `think`、`reflect`、`read_file`、`extract_function`。
- 为 evidence protocol validator 增加 6 个新 render type 的解析 / 校验测试。
- 为每类新 render type 至少补 1 个工具结果测试，确保工具 metadata 已输出新协议，而不是原始 blob。

### 前端测试

- 更新：
  - `frontend/tests/externalToolsViewModel.test.ts`
  - `frontend/tests/scanConfigExternalToolsLayout.test.tsx`
  - `frontend/tests/scanConfigExternalToolDetail.test.tsx`
- 断言配置页列表与详情页仅由后端 skill metadata 驱动，静态 catalog 不再决定展示集合。
- 为 `frontend/src/pages/AgentAudit/toolEvidence.ts`、`ToolEvidencePreview.tsx`、详情弹窗对应组件增加 6 个新 render type 的 parse / render 用例。
- 保留一个历史兼容回归：旧 `read_file` / `extract_function` 事件仍可在新版 evidence 视图中解析展示。

### 验收标准

- 新专题已从 [../README.md](../README.md) 可达。
- 本文档包含完整 17-skill 对齐矩阵。
- 文档中每个关键改造点都附带具体代码锚点，不出现“前端适配一下”“后端补协议”这类模糊描述。
- 配置页最终展示集合、运行时 skill 集合、evidence render 覆盖集合三者口径一致。
