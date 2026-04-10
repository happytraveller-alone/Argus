# Dataflow Analysis Tool Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复现有 `dataflow_analysis` 与 `controlflow_analysis_light` 的高频调用失败问题，并以并行迁移方式新增基于 Joern 的 `joern_dataflow_analysis` 工具，为后续统一数据流分析能力打基础。

**Architecture:** 本轮只做“旧工具稳定化 + 新工具并行接入”，不做默认入口切换。旧工具先统一定位输入、返回语义和容器依赖，再新增独立的 `joern_dataflow_analysis` 并打通 backend、agent、外部工具可见面。Joern v1 严格限制在单文件、单次调用、行号锚点驱动的 reachability 判断，不引入服务化 CPG、规则持久化或自动替换验证流水线。

**Tech Stack:** FastAPI、Pydantic、Docker 多阶段构建、Python agent tool runtime、tree-sitter、code2flow、Joern CLI、pytest、uv、pnpm

---

## 1. 可行性结论

结论：**阶段一和阶段二可行，但当前文档需要按代码现状做边界收缩与任务重排；阶段三应明确为独立研究交付，不阻塞前两阶段上线。**

### 1.1 已验证的前提

- `code2flow` 已经在 [`backend/pyproject.toml`](/home/xyf/AuditTool/backend/pyproject.toml) 中声明为 Python 依赖，不是“完全未接入”状态。
- runtime 镜像已复制 builder 产出的 `/opt/backend-venv`，理论上可以直接交付 `code2flow`，但当前缺少显式构建探测与统一诊断。
- runtime 镜像已安装 `openjdk-21-jre-headless`，Joern CLI 的 Java 运行时前提已具备。
- [`backend/app/services/agent/tools/control_flow_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/control_flow_tool.py) 已接受 `file_path:line`、`line_start/line_end`、`function_name` 回退；[`backend/app/services/agent/tools/code_analysis_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/code_analysis_tool.py) 仍以 `start_line/end_line`、`source_code`、`variable_name` 为主，存在明显 schema 漂移。
- [`backend/app/services/agent/agents/base.py`](/home/xyf/AuditTool/backend/app/services/agent/agents/base.py) 中已经存在对 `dataflow_analysis` / `controlflow_analysis_light` 的输入修复逻辑和验证流水线调用逻辑，因此“只改工具文件不改 agent 层”不可行。
- 新工具的“外部工具可见面”不止 backend registry，还包括 [`backend/app/services/agent/skills/scan_core.py`](/home/xyf/AuditTool/backend/app/services/agent/skills/scan_core.py)、配置接口返回的 `skillAvailability`、以及前端静态目录 [`frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`](/home/xyf/AuditTool/frontend/src/pages/intelligent-scan/skillToolsCatalog.ts)。

### 1.2 需要调整的关键点

1. 旧方案中“安装 `code2flow`”不是核心问题，**核心问题是 build-time delivery probe、runtime 可执行探测、blocked reason 语义统一**。
2. 旧方案想把两个旧工具统一到 `file_path + line_start + line_end`，方向正确，但必须采用**兼容迁移**，不能直接删除 `start_line/end_line`。
3. Joern 工具接入后，**本轮不要自动改写 `AgentBase._verify_reachability` 的默认链路**；否则一轮改动同时覆盖旧工具修复和新引擎替换，风险过高。
4. 当前 [`backend/docs/agent-tools/INDEX.md`](/home/xyf/AuditTool/backend/docs/agent-tools/INDEX.md) 与 [`backend/docs/agent-tools/TOOL_SHARED_CATALOG.md`](/home/xyf/AuditTool/backend/docs/agent-tools/TOOL_SHARED_CATALOG.md) 仍列出 `read_file`、`extract_function`、`reflect`、`think` 等已退场/不应暴露的工具，**文档基线本身不一致**，必须与本次工具文档同步清理。
5. Joern v1 必须再收窄：**验收只要求单文件、单次 source_line -> sink_line reachability 判断，以及基于固定夹具的真实调用验证**；不要求跨文件、跨项目、跨过程全量图分析。

## 2. 当前代码状态核对

### 2.1 与数据流/控制流工具直接相关的现有实现

- [`backend/app/services/agent/tools/code_analysis_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/code_analysis_tool.py)
- [`backend/app/services/agent/tools/control_flow_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/control_flow_tool.py)
- [`backend/app/services/agent/flow/pipeline.py`](/home/xyf/AuditTool/backend/app/services/agent/flow/pipeline.py)
- [`backend/app/services/agent/flow/lightweight/callgraph_code2flow.py`](/home/xyf/AuditTool/backend/app/services/agent/flow/lightweight/callgraph_code2flow.py)
- [`backend/app/services/agent/agents/base.py`](/home/xyf/AuditTool/backend/app/services/agent/agents/base.py)
- [`backend/app/api/v1/endpoints/agent_tasks_execution.py`](/home/xyf/AuditTool/backend/app/api/v1/endpoints/agent_tasks_execution.py)
- [`backend/app/api/v1/endpoints/agent_test.py`](/home/xyf/AuditTool/backend/app/api/v1/endpoints/agent_test.py)
- [`backend/app/services/agent/mcp/router.py`](/home/xyf/AuditTool/backend/app/services/agent/mcp/router.py)
- [`backend/app/services/agent/skills/scan_core.py`](/home/xyf/AuditTool/backend/app/services/agent/skills/scan_core.py)

### 2.2 当前问题重新归类

当前问题应拆成五类，而不是原文中的四类：

1. **旧工具 schema 漂移**
   - `dataflow_analysis` 公开输入偏向 `source_code/start_line/end_line`
   - `controlflow_analysis_light` 公开输入偏向 `file_path:line/line_start`
   - agent prompt、输入修复、前端目录示例没有统一

2. **旧工具结果语义不统一**
   - `dataflow_analysis` 主要返回文本 + metadata
   - `controlflow_analysis_light` 返回结构化 `data` + `metadata.summary`
   - agent 只能依赖文本观察做二次推断，稳定性有限

3. **`code2flow` 交付与诊断不完整**
   - 依赖虽然声明了，但镜像构建和运行时缺少显式可执行探测
   - 仍残留 `CODE2FLOW_AUTO_INSTALL_FAILED` 这类历史语义，和当前“构建时交付”模式不匹配

4. **Joern 接入链路为空**
   - 没有 runtime 安装逻辑
   - 没有工具封装
   - 没有注册、目录、测试与前端可见面

5. **文档与目录基线已过期**
   - backend 工具索引列出已退场工具
   - frontend 静态 catalog 示例仍按旧风格展示部分工具输入
   - 如果不先修基线，后续开发者会参考错误文档继续扩大漂移

## 3. 范围重定义

### 3.1 本次范围

- 修复并保留现有 `dataflow_analysis`
- 修复并保留现有 `controlflow_analysis_light`
- 为 backend 镜像增加 `code2flow` 和 Joern 的显式 build-time probe
- 新增 `joern_dataflow_analysis`
- 打通 backend、agent、scan-core catalog、frontend 静态目录的可见面
- 补齐工具文档、共享目录、prompt 示例、测试夹具与验收命令
- 输出后续规则研究清单

### 3.2 非目标

- 本轮不删除 `controlflow_analysis_light`
- 本轮不把 `dataflow_analysis` 直接改成 Joern 内核
- 本轮不把 `AgentBase._verify_reachability` 默认链路切到 `joern_dataflow_analysis`
- 本轮不做全项目级的 Joern 图数据库服务化
- 本轮不做规则持久化、规则抓取任务、数据库表或前端规则展示
- 本轮不承诺“所有 Joern 支持语言都可稳定工作”；验收夹具先以单语言夹具为准

## 4. 目标状态

完成本计划后，仓库应满足以下状态：

- backend 容器内 `code2flow` 与 `joern` 都可以直接执行探测命令
- `dataflow_analysis` 与 `controlflow_analysis_light` 对外都推荐使用 `file_path + line_start + line_end`
- `dataflow_analysis` 兼容 `start_line/end_line`，但文档、prompt、示例不再推荐旧字段
- 两个旧工具都能稳定区分“输入/运行失败”和“分析结果为否”
- `joern_dataflow_analysis` 已完成 backend 注册、scan-core 暴露和前端目录同步
- `joern_dataflow_analysis` v1 能完成单文件行号锚点 reachability 判断
- backend 文档索引、共享 catalog、frontend 静态目录、tool registry、tests 与实际实现一致

## 5. 核心设计决策

### 5.1 旧工具公共定位契约

`dataflow_analysis` 与 `controlflow_analysis_light` 对外统一推荐以下主输入：

- `file_path`: 必填，项目内相对路径
- `line_start`: 必填，分析起始行
- `line_end`: 选填，默认等于 `line_start`
- `function_name`: 选填，用于补充定位与展示
- `language`: 选填，仅在扩展名无法稳定推断时使用

### 5.2 旧工具兼容策略

`dataflow_analysis` 仍兼容以下旧字段，但只作为兼容层，不再作为公开示例：

- `start_line`
- `end_line`
- `source_code`
- `sink_code`
- `variable_name`
- `source_hints`
- `sink_hints`
- `max_hops`

`controlflow_analysis_light` 保留以下增强字段：

- `entry_points`
- `entry_points_hint`
- `vulnerability_type`
- `call_chain_hint`
- `control_conditions_hint`
- `severity`
- `confidence`

要求：

- 缺少增强字段不能影响基础调用成功
- 缺少定位字段必须返回明确错误
- 文档、schema、示例、测试统一使用 `line_start/line_end`
- 兼容字段只能作为输入别名，不能继续当主文档示例

### 5.3 统一错误语义

三个相关工具统一遵循以下语义：

- `success=False`
  - 缺少必要定位字段
  - 文件不可读
  - 行号非法
  - 运行时依赖不可执行
  - 查询执行异常
  - Joern 不支持当前语言或当前锚点无法生成查询

- `success=True`
  - 工具成功执行，但 `reachable=False`
  - 工具成功执行，但结论是 `inconclusive`
  - 工具成功执行，返回了正向路径

建议统一 metadata 字段：

- `engine`
- `file_path`
- `line_start`
- `line_end`
- `result_state`: `reachable` / `not_reachable` / `inconclusive`
- `diagnostics`
- `summary`

### 5.4 `joern_dataflow_analysis` v1 契约

输入字段：

- `file_path`: 必填，项目内相对路径
- `source_line`: 必填
- `sink_line`: 必填
- `source_symbol`: 选填
- `sink_symbol`: 选填
- `language`: 选填
- `query_mode`: 选填，默认 `intra_file_reachability`
- `timeout_sec`: 选填，默认 30

输出字段：

- `reachable`: 布尔值
- `path_count`: 路径数量
- `paths`: 路径数组
- `summary`: 给 agent 直接消费的摘要
- `engine`: 固定为 `joern`
- `diagnostics`: CLI 调用、脚本路径、解析状态、语言支持情况、stderr 摘要

V1 约束：

- 仅支持单文件分析
- 不要求改写现有 verification 默认流水线
- 不要求全局 source/sink 规则库
- 验收只要求基于固定夹具跑通真实调用

## 6. 文件与职责映射

### 6.1 运行时依赖与镜像

- 修改 [`backend/Dockerfile`](/home/xyf/AuditTool/backend/Dockerfile)
  - 为 `code2flow` 增加显式 probe
  - 安装 Joern CLI
  - 为 Joern 增加架构识别、缓存与 wrapper

### 6.2 旧工具修复

- 修改 [`backend/app/services/agent/tools/code_analysis_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/code_analysis_tool.py)
  - `dataflow_analysis` 输入归一
  - `metadata` 统一
- 修改 [`backend/app/services/agent/tools/control_flow_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/control_flow_tool.py)
  - `summary/diagnostics/result_state` 统一
- 修改 [`backend/app/services/agent/flow/lightweight/callgraph_code2flow.py`](/home/xyf/AuditTool/backend/app/services/agent/flow/lightweight/callgraph_code2flow.py)
  - 删除历史 auto-install 语义
  - 补齐 `code2flow` 诊断
- 修改 [`backend/app/services/agent/agents/base.py`](/home/xyf/AuditTool/backend/app/services/agent/agents/base.py)
  - 工具输入修复与默认调用方式对齐

### 6.3 Joern 工具接入

- 新增 [`backend/app/services/agent/tools/joern_dataflow_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/joern_dataflow_tool.py)
  - Joern CLI 封装
  - 查询模板生成
  - JSON 结果解析
- 修改 [`backend/app/services/agent/tools/__init__.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/__init__.py)
  - 导出新工具
- 修改 [`backend/app/api/v1/endpoints/agent_tasks_execution.py`](/home/xyf/AuditTool/backend/app/api/v1/endpoints/agent_tasks_execution.py)
  - 注册到 analysis/report surface
- 修改 [`backend/app/api/v1/endpoints/agent_test.py`](/home/xyf/AuditTool/backend/app/api/v1/endpoints/agent_test.py)
  - 调试/测试入口补齐新工具注入
- 修改 [`backend/app/services/agent/mcp/router.py`](/home/xyf/AuditTool/backend/app/services/agent/mcp/router.py)
  - 增加本地路由
- 修改 [`backend/app/services/agent/skills/scan_core.py`](/home/xyf/AuditTool/backend/app/services/agent/skills/scan_core.py)
  - 增加 scan-core skill 暴露

### 6.4 文档与前端可见面同步

- 修改 [`backend/docs/agent-tools/tools/dataflow_analysis.md`](/home/xyf/AuditTool/backend/docs/agent-tools/tools/dataflow_analysis.md)
- 修改 [`backend/docs/agent-tools/tools/controlflow_analysis_light.md`](/home/xyf/AuditTool/backend/docs/agent-tools/tools/controlflow_analysis_light.md)
- 新增 [`backend/docs/agent-tools/tools/joern_dataflow_analysis.md`](/home/xyf/AuditTool/backend/docs/agent-tools/tools/joern_dataflow_analysis.md)
- 修改 [`backend/docs/agent-tools/INDEX.md`](/home/xyf/AuditTool/backend/docs/agent-tools/INDEX.md)
- 修改 [`backend/docs/agent-tools/TOOL_SHARED_CATALOG.md`](/home/xyf/AuditTool/backend/docs/agent-tools/TOOL_SHARED_CATALOG.md)
- 修改 [`backend/app/services/agent/prompts/system_prompts.py`](/home/xyf/AuditTool/backend/app/services/agent/prompts/system_prompts.py)
- 修改 [`frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`](/home/xyf/AuditTool/frontend/src/pages/intelligent-scan/skillToolsCatalog.ts)

### 6.5 测试

- 修改 [`backend/tests/agent/test_tools.py`](/home/xyf/AuditTool/backend/tests/agent/test_tools.py)
- 修改 [`backend/tests/test_agent_tool_registry.py`](/home/xyf/AuditTool/backend/tests/test_agent_tool_registry.py)
- 修改 [`backend/tests/test_mcp_catalog.py`](/home/xyf/AuditTool/backend/tests/test_mcp_catalog.py)
- 新增 [`backend/tests/agent/test_joern_dataflow_tool.py`](/home/xyf/AuditTool/backend/tests/agent/test_joern_dataflow_tool.py)
- 修改 [`frontend/tests/scanConfigExternalToolDetail.test.tsx`](/home/xyf/AuditTool/frontend/tests/scanConfigExternalToolDetail.test.tsx)

## 7. 分阶段实施计划

### 阶段 0：基线对齐

目标：在动代码前，把“当前真实行为”和“本轮要统一的契约”钉死，避免边改边漂移。

#### Task 0: 固定公共契约与可见面边界

**Files:**
- Modify: `docs/dataflow_analysis_tool/dataflow_analysis_tool_overview.md`
- Read/Verify: `backend/app/services/agent/tools/code_analysis_tool.py`
- Read/Verify: `backend/app/services/agent/tools/control_flow_tool.py`
- Read/Verify: `backend/app/services/agent/agents/base.py`
- Read/Verify: `backend/app/services/agent/skills/scan_core.py`
- Read/Verify: `frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`

- [ ] 明确本轮公共定位输入以 `line_start/line_end` 为准。
- [ ] 明确 `dataflow_analysis` 只保留旧字段兼容，不再对外推荐。
- [ ] 明确 `joern_dataflow_analysis` 只做并行新入口，不改默认 verification 流水线。
- [ ] 明确 frontend 静态 catalog 也属于交付面，不允许只改 backend。

### 阶段 1：修复旧工具并统一旧契约

目标：先把 agent 高频调用失败压下去，并让旧工具的公开输入与错误语义稳定下来。

#### Task 1: 归一 `dataflow_analysis` 的公开 schema 与兼容层

**Files:**
- Modify: `backend/app/services/agent/tools/code_analysis_tool.py`
- Modify: `backend/app/services/agent/agents/base.py`
- Modify: `backend/docs/agent-tools/tools/dataflow_analysis.md`
- Modify: `frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`
- Test: `backend/tests/agent/test_tools.py`

- [ ] 将 `DataFlowAnalysisInput` 的公开主字段改为 `file_path`、`line_start`、`line_end`、`function_name`、`language`。
- [ ] 保留 `start_line/end_line`、`source_code`、`sink_code`、`variable_name` 的兼容输入。
- [ ] 在工具内部先做 location normalize，再决定是否读文件或使用直接传入代码。
- [ ] 为缺少定位信息、文件不可读、行号非法返回稳定错误文本。
- [ ] 为成功执行结果统一补充 `engine/result_state/diagnostics/summary`。
- [ ] 更新 [`backend/app/services/agent/agents/base.py`](/home/xyf/AuditTool/backend/app/services/agent/agents/base.py) 中对 `dataflow_analysis` 的 repair 与默认调用，让 agent 优先生成 `line_start/line_end`。
- [ ] 测试同时覆盖新字段与旧字段别名。

#### Task 2: 统一 `controlflow_analysis_light` 的诊断与错误语义

**Files:**
- Modify: `backend/app/services/agent/tools/control_flow_tool.py`
- Modify: `backend/app/services/agent/flow/lightweight/callgraph_code2flow.py`
- Modify: `backend/docs/agent-tools/tools/controlflow_analysis_light.md`
- Test: `backend/tests/agent/test_tools.py`

- [ ] 保留当前 `file_path:line`、`line_start`、`function_name` 回退逻辑。
- [ ] 统一输出 metadata：至少包含 `engine/result_state/diagnostics/summary`。
- [ ] 在 [`backend/app/services/agent/flow/lightweight/callgraph_code2flow.py`](/home/xyf/AuditTool/backend/app/services/agent/flow/lightweight/callgraph_code2flow.py) 中移除对 `CODE2FLOW_AUTO_INSTALL_FAILED` 的主流程依赖。
- [ ] 将 `code2flow` 诊断改为真实运行态信息，例如 `binary_path`、`probe_command`、`stderr_excerpt`。
- [ ] 对“无路径”“依赖缺失”“执行失败”给出可区分 blocked reason。

#### Task 3: 为 `code2flow` 增加显式镜像探测

**Files:**
- Modify: `backend/Dockerfile`
- Test: `backend/tests/agent/test_tools.py`

- [ ] 不再重复添加 Python 依赖；`code2flow` 已在 `backend/pyproject.toml` 中声明。
- [ ] 在 `runtime` 和 `dev-runtime` 阶段复制 venv 后加入 `code2flow --help` 或 `python -m code2flow --help` 探测。
- [ ] 如果探测失败，让镜像构建直接失败，而不是把问题留到运行时。
- [ ] 保持现有 APT/PyPI fallback 与 cache 逻辑，不新造下载模式。

#### Task 4: 同步旧工具文档、prompt 与目录

**Files:**
- Modify: `backend/app/services/agent/prompts/system_prompts.py`
- Modify: `backend/docs/agent-tools/INDEX.md`
- Modify: `backend/docs/agent-tools/TOOL_SHARED_CATALOG.md`
- Modify: `frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`

- [ ] 将 prompt 中对 `dataflow_analysis` 的示例改为定位优先模式。
- [ ] backend 文档索引中移除本轮不应继续暴露的历史工具条目。
- [ ] 共享 catalog 与 frontend 静态 catalog 保持同一套工具输入示例。
- [ ] 明确 `dataflow_analysis` / `controlflow_analysis_light` 只是“流证据工具”，不是最终 verdict。

### 阶段 2：新增 `joern_dataflow_analysis`

目标：并行接入 Joern，新工具可独立调用，但不抢旧默认入口。

#### Task 5: 为镜像引入 Joern CLI

**Files:**
- Modify: `backend/Dockerfile`

- [ ] 采用和 `opengrep/phpstan/YASA` 同风格的下载缓存、代理回退与架构分支。
- [ ] 为 `amd64` 与 `arm64` 明确产物选择逻辑。
- [ ] 将 Joern 安装到固定目录，例如 `/opt/joern`，并提供 `/usr/local/bin/joern` wrapper。
- [ ] 设置 `JOERN_HOME`、`JOERN_BIN`，避免工具代码写死临时路径。
- [ ] 在镜像构建时执行最小探测：`joern --help`。

#### Task 6: 实现 `joern_dataflow_analysis` 工具封装

**Files:**
- Create: `backend/app/services/agent/tools/joern_dataflow_tool.py`
- Modify: `backend/app/services/agent/tools/__init__.py`
- Test: `backend/tests/agent/test_joern_dataflow_tool.py`

- [ ] 工具入参只接受单文件相对路径 + `source_line` + `sink_line`。
- [ ] 在工具内部解析绝对路径，防止越界读取项目外文件。
- [ ] 先按扩展名做语言判定，不支持的语言直接返回稳定错误。
- [ ] 使用固定查询模板，不做自由拼接查询。
- [ ] 优先输出结构化 `data`，不要只返回大段文本。
- [ ] 对以下场景补齐稳定返回：
  - 文件不存在
  - 行号非法
  - CLI 不可执行
  - Joern 解析失败
  - source/sink 锚点未命中
  - reachable / not reachable

#### Task 7: 将新工具注册到 backend、scan-core 与前端目录

**Files:**
- Modify: `backend/app/api/v1/endpoints/agent_tasks_execution.py`
- Modify: `backend/app/api/v1/endpoints/agent_test.py`
- Modify: `backend/app/services/agent/mcp/router.py`
- Modify: `backend/app/services/agent/skills/scan_core.py`
- Modify: `frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`
- Test: `backend/tests/test_agent_tool_registry.py`
- Test: `backend/tests/test_mcp_catalog.py`
- Test: `frontend/tests/scanConfigExternalToolDetail.test.tsx`

- [ ] 将 `joern_dataflow_analysis` 注册到 `analysis`。
- [ ] 如外部工具详情页需要展示，也同步注册到 `report` 或静态 catalog。
- [ ] 更新 `scan_core.py` 的 `_SCAN_CORE_SKILLS` 与测试白名单/禁用原因映射。
- [ ] 更新前端静态 catalog，确保详情页能显示新工具输入与目标。
- [ ] 明确新工具是并行工具，不自动替换 `dataflow_analysis` 或 `controlflow_analysis_light`。

#### Task 8: 完成第二阶段文档同步

**Files:**
- Create: `backend/docs/agent-tools/tools/joern_dataflow_analysis.md`
- Modify: `backend/docs/agent-tools/INDEX.md`
- Modify: `backend/docs/agent-tools/TOOL_SHARED_CATALOG.md`
- Modify: `backend/app/services/agent/prompts/system_prompts.py`

- [ ] 新增 Joern 工具文档，说明 v1 只支持单文件 reachability。
- [ ] 在共享 catalog 中把它归类到“可达性与逻辑分析”。
- [ ] 如果 prompt 中提到它，要明确“这是额外可选工具，不是默认替代旧工具”。

#### Task 9: Joern 容器验收

**Files:**
- Test: `backend/tests/agent/test_joern_dataflow_tool.py`
- Test: `backend/tests/test_agent_tool_registry.py`

- [ ] 在 backend 容器内确认 `joern` 可执行。
- [ ] 跑一条真实工具调用，返回结构化结果。
- [ ] 至少覆盖一个 reachable 与一个 not reachable 夹具。
- [ ] 确认 agent 调试入口与 scan-core 暴露面都可见该工具。

### 阶段 3：规则研究清单

目标：为后续 Joern 规则体系提供输入，但不阻塞前两阶段发布。

#### Task 10: 输出规则来源与格式分类

**Files:**
- Create: `docs/dataflow_analysis_tool/joern_rule_research.md`

- [ ] 调研公开 source/sink 规则来源。
- [ ] 区分“可直接转为行号锚点 reachability 输入”的规则与“仍需人工建模”的规则。
- [ ] 只输出研究结论与建议字段，不写数据库/前端/抓取任务实现。

## 8. 测试与验证矩阵

### 8.1 Backend 单元测试

- `dataflow_analysis`
  - 新主字段 `line_start/line_end`
  - 旧字段 `start_line/end_line`
  - 缺参错误
  - 文件读取模式
  - 稳定 metadata

- `controlflow_analysis_light`
  - `file_path:line`
  - 标准 `line_start/line_end`
  - `function_name` 回退
  - `code2flow` 缺失/执行失败诊断

- `joern_dataflow_analysis`
  - 行号校验
  - CLI 失败
  - 解析失败
  - reachable / not reachable

### 8.2 Registry / Catalog 测试

- backend 工具注册包含新工具
- `skillAvailability` 包含新工具
- frontend 静态目录能展示新工具
- backend docs index / shared catalog 不再列出本轮已退场的历史工具

### 8.3 容器验证

必须优先做容器内验证，而不是只停留在 pytest：

- backend 镜像内 `code2flow` 可执行
- backend 镜像内 `joern` 可执行
- 旧两个工具可在容器环境中被真实调用
- 新 Joern 工具可在容器环境中被真实调用

建议命令（WSL/bash 环境）：

```bash
uv run --directory backend pytest -s \
  backend/tests/agent/test_tools.py \
  backend/tests/agent/test_joern_dataflow_tool.py \
  backend/tests/test_agent_tool_registry.py \
  backend/tests/test_mcp_catalog.py
```

```bash
pnpm --dir frontend test:node
```

```bash
docker build -f backend/Dockerfile -t audittool-backend-flow ./backend
docker run --rm audittool-backend-flow code2flow --help
docker run --rm audittool-backend-flow joern --help
```

## 9. 风险与控制

### 风险 1：Schema 改动误伤旧调用

控制：

- `dataflow_analysis` 保留旧字段兼容
- 先改工具接受能力，再改 prompt 与示例
- 测试同时覆盖新旧字段

### 风险 2：`code2flow` 问题被误判为算法问题

控制：

- 用 build-time probe 提前暴露
- 用真实 blocked reason + diagnostics 区分“未安装”“执行失败”“无路径”
- 删除历史 auto-install 残留语义

### 风险 3：Joern v1 范围膨胀

控制：

- 明确只做单文件 reachability
- 不接入默认 verification 流水线
- 验收只要求固定夹具真实调用

### 风险 4：backend 与 frontend 目录不同步

控制：

- `scan_core.py`、backend docs、frontend `skillToolsCatalog.ts` 同一阶段一起改
- 把 frontend 目录测试纳入验收

## 10. 验收标准

以下条件全部满足，才算本计划前两阶段完成：

1. backend 容器中 `code2flow` 与 `joern` 均可执行。
2. `dataflow_analysis` 与 `controlflow_analysis_light` 的公开推荐输入统一为 `file_path + line_start + line_end`。
3. `dataflow_analysis` 仍兼容 `start_line/end_line`，但文档、prompt、示例不再推荐旧字段。
4. 旧两个工具都能稳定区分输入错误、依赖错误、执行失败和“无可达路径”。
5. `joern_dataflow_analysis` 已完成 backend 注册、scan-core 暴露与 frontend 静态目录同步。
6. Joern v1 已完成至少一组 reachable / not reachable 真实夹具验证。
7. backend docs index、shared catalog、prompt、skill availability、frontend 静态目录与实际实现一致。

## 11. 开发执行顺序

为避免返工，建议严格按以下顺序落地：

1. 先改 `dataflow_analysis` 兼容层与 agent repair。
2. 再改 `controlflow_analysis_light` 诊断与 `code2flow` probe。
3. 完成 backend 文档、prompt、frontend 静态目录同步。
4. 再引入 Joern CLI 与 `joern_dataflow_analysis`。
5. 最后补 registry/catalog/tests/容器验收。

不要反过来先接 Joern 再回头修旧工具，否则很容易把“旧工具未修稳”误判为“新工具集成问题”。

## 12. 逐任务执行 Checklist

本节用于开发执行时逐项勾选。粒度按“单个明确动作”拆分，默认在 WSL bash 环境中执行；Python 校验统一使用 `uv run --directory backend`，前端校验使用 `pnpm --dir frontend`。

### Task 0 Checklist: 固定公共契约与边界

- [ ] 阅读 [`backend/app/services/agent/tools/code_analysis_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/code_analysis_tool.py)，记录 `DataFlowAnalysisInput` 当前字段与默认值。
- [ ] 阅读 [`backend/app/services/agent/tools/control_flow_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/control_flow_tool.py)，记录 `ControlFlowAnalysisLightInput` 当前字段与回退逻辑。
- [ ] 阅读 [`backend/app/services/agent/agents/base.py`](/home/xyf/AuditTool/backend/app/services/agent/agents/base.py) 中 `dataflow_analysis` / `controlflow_analysis_light` repair 逻辑，列出别名映射。
- [ ] 阅读 [`backend/app/services/agent/skills/scan_core.py`](/home/xyf/AuditTool/backend/app/services/agent/skills/scan_core.py) 与 [`frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`](/home/xyf/AuditTool/frontend/src/pages/intelligent-scan/skillToolsCatalog.ts)，确认外部可见面字段名。
- [ ] 在本文件中确认公共主输入统一为 `file_path + line_start + line_end`。
- [ ] 在本文件中确认 `start_line/end_line` 仅为 `dataflow_analysis` 兼容字段。
- [ ] 在本文件中确认 Joern v1 不改默认 verification 流水线。

**完成判据**

- 方案文档中的“核心设计决策”“分阶段实施计划”“验收标准”三处表述一致。

### Task 1 Checklist: `dataflow_analysis` 公开 schema 与兼容层

- [ ] 在 [`backend/app/services/agent/tools/code_analysis_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/code_analysis_tool.py) 中给 `DataFlowAnalysisInput` 增加 `line_start`、`line_end`、`function_name`。
- [ ] 保留 `start_line`、`end_line` 字段或等效兼容读取逻辑，避免历史调用直接失效。
- [ ] 在 `_execute()` 开头新增 location normalize 步骤，优先读取 `line_start/line_end`，再回退到 `start_line/end_line`。
- [ ] 统一 `file_path` 判空、行号正整数校验、`line_end >= line_start` 校验。
- [ ] 如果仅提供 `file_path + line_start`，确保可以从文件读取对应窗口，不要求必须提供 `source_code`。
- [ ] 如果只提供旧字段 `start_line/end_line`，确保行为与新字段一致。
- [ ] 如果既没有代码也没有可定位文件，返回稳定 `success=False` 错误。
- [ ] 补齐 `metadata.engine`、`metadata.result_state`、`metadata.summary`、`metadata.diagnostics`。
- [ ] 将 `metadata.start_line/end_line` 统一成 `line_start/line_end` 或同时保留并注明兼容。
- [ ] 更新 [`backend/app/services/agent/agents/base.py`](/home/xyf/AuditTool/backend/app/services/agent/agents/base.py) 中 repair 逻辑，让模型输出优先落到 `line_start/line_end`。
- [ ] 更新 [`backend/docs/agent-tools/tools/dataflow_analysis.md`](/home/xyf/AuditTool/backend/docs/agent-tools/tools/dataflow_analysis.md) 示例输入。
- [ ] 更新 [`frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`](/home/xyf/AuditTool/frontend/src/pages/intelligent-scan/skillToolsCatalog.ts) 中 `dataflow_analysis` 示例。
- [ ] 在 [`backend/tests/agent/test_tools.py`](/home/xyf/AuditTool/backend/tests/agent/test_tools.py) 中新增或更新以下测试：
- [ ] 新字段 `line_start/line_end` 可成功调用。
- [ ] 旧字段 `start_line/end_line` 仍可成功调用。
- [ ] 缺少定位字段时报错稳定。
- [ ] 文件不存在时报错稳定。

**建议验证命令**

```bash
uv run --directory backend pytest -s backend/tests/agent/test_tools.py -k "dataflow_analysis"
```

**完成判据**

- 文档、tool schema、agent repair、frontend 示例都以 `line_start/line_end` 为主。
- `dataflow_analysis` 旧调用不回归。

### Task 2 Checklist: `controlflow_analysis_light` 诊断与错误语义

- [ ] 在 [`backend/app/services/agent/tools/control_flow_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/control_flow_tool.py) 中明确 `result_state` 生成规则。
- [ ] `path_found=True` 时输出 `result_state=reachable`。
- [ ] `path_found=False` 且工具成功执行时输出 `result_state=not_reachable` 或 `inconclusive`。
- [ ] `summary` 中保留 `path_found/path_score/blocked_reasons`，但不要只靠字符串表达所有诊断。
- [ ] 在 `metadata.diagnostics` 中补充来自 pipeline / code2flow 的结构化诊断。
- [ ] 在 [`backend/app/services/agent/flow/lightweight/callgraph_code2flow.py`](/home/xyf/AuditTool/backend/app/services/agent/flow/lightweight/callgraph_code2flow.py) 中删除历史 `auto_install` 语义分支或降级为兼容注释。
- [ ] 对 “binary not found / module import failed / subprocess non-zero / dot read failed / no edges” 输出独立 blocked reason。
- [ ] 在诊断中补充 `command`、`stderr`、`edge_count`、`node_count` 等字段。
- [ ] 更新 [`backend/docs/agent-tools/tools/controlflow_analysis_light.md`](/home/xyf/AuditTool/backend/docs/agent-tools/tools/controlflow_analysis_light.md) 的输出说明。
- [ ] 在 [`backend/tests/agent/test_tools.py`](/home/xyf/AuditTool/backend/tests/agent/test_tools.py) 中覆盖：
- [ ] `file_path:line` 调用成功。
- [ ] `function_name` 回退成功。
- [ ] 缺少定位信息时报错。
- [ ] `code2flow` 缺失/失败时 summary 与 diagnostics 可区分。

**建议验证命令**

```bash
uv run --directory backend pytest -s backend/tests/agent/test_tools.py -k "controlflow_analysis_light"
```

**完成判据**

- `controlflow_analysis_light` 能稳定表达“工具成功但无路径”和“工具执行失败”的区别。

### Task 3 Checklist: `code2flow` 镜像探测

- [ ] 检查 [`backend/pyproject.toml`](/home/xyf/AuditTool/backend/pyproject.toml) 中 `code2flow` 依赖声明是否保留。
- [ ] 在 [`backend/Dockerfile`](/home/xyf/AuditTool/backend/Dockerfile) 的 `dev-runtime` 阶段添加 `code2flow` 可执行探测。
- [ ] 在 [`backend/Dockerfile`](/home/xyf/AuditTool/backend/Dockerfile) 的 `runtime` 阶段添加同样探测。
- [ ] 优先使用 `code2flow --help`，若 wrapper 不稳定则回退 `python -m code2flow --help`。
- [ ] 探测失败时直接 `exit 1`，不要吞掉错误。
- [ ] 保持现有 cache / mirror / fallback 模式，不为 `code2flow` 新增单独下载逻辑。

**建议验证命令**

```bash
docker build -f backend/Dockerfile -t audittool-backend-flow ./backend
docker run --rm audittool-backend-flow code2flow --help
```

**完成判据**

- 新构建出的镜像在运行前就能暴露 `code2flow` 交付问题。

### Task 4 Checklist: 旧工具文档、prompt 与目录同步

- [ ] 更新 [`backend/app/services/agent/prompts/system_prompts.py`](/home/xyf/AuditTool/backend/app/services/agent/prompts/system_prompts.py) 中与流分析相关的推荐调用方式。
- [ ] 将 `dataflow_analysis` 的示例输入改为 `file_path + line_start + line_end`。
- [ ] 检查 prompt 中是否还在暗示模型生成 `source_code/variable_name/start_line` 作为首选。
- [ ] 更新 [`backend/docs/agent-tools/INDEX.md`](/home/xyf/AuditTool/backend/docs/agent-tools/INDEX.md)，移除已退场或不应暴露的工具条目。
- [ ] 更新 [`backend/docs/agent-tools/TOOL_SHARED_CATALOG.md`](/home/xyf/AuditTool/backend/docs/agent-tools/TOOL_SHARED_CATALOG.md)，统一工具分类与用途描述。
- [ ] 更新 [`frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`](/home/xyf/AuditTool/frontend/src/pages/intelligent-scan/skillToolsCatalog.ts) 中 `dataflow_analysis` / `controlflow_analysis_light` 的 input checklist 与 example input。

**建议验证命令**

```bash
pnpm --dir frontend test:node
```

**完成判据**

- backend prompt、backend docs、frontend 静态目录三处示例一致。

### Task 5 Checklist: Joern CLI 镜像接入

- [ ] 在 [`backend/Dockerfile`](/home/xyf/AuditTool/backend/Dockerfile) 中新增 `JOERN_HOME`、`JOERN_BIN` 环境变量。
- [ ] 参考 `opengrep/phpstan/YASA` 下载逻辑实现 Joern 产物下载缓存。
- [ ] 为 `amd64` 与 `arm64` 添加产物分支。
- [ ] 将产物解压到固定目录，例如 `/opt/joern`。
- [ ] 新增 `/usr/local/bin/joern` wrapper，屏蔽代理与工作目录差异。
- [ ] 在 `runtime` 和 `dev-runtime` 阶段执行 `joern --help` 探测。
- [ ] 确认与现有 `openjdk-21-jre-headless` 不冲突，不重复安装 Java。

**建议验证命令**

```bash
docker build -f backend/Dockerfile -t audittool-backend-flow ./backend
docker run --rm audittool-backend-flow joern --help
```

**完成判据**

- 镜像内 `joern` 可稳定执行，路径固定，后续工具封装不需要猜测安装位置。

### Task 6 Checklist: `joern_dataflow_analysis` 工具封装

- [ ] 新建 [`backend/app/services/agent/tools/joern_dataflow_tool.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/joern_dataflow_tool.py)。
- [ ] 定义输入 schema：`file_path/source_line/sink_line/source_symbol/sink_symbol/language/query_mode/timeout_sec`。
- [ ] 定义内部路径解析方法，确保只能读取项目根目录内文件。
- [ ] 定义扩展名到语言的映射，无法识别时允许显式 `language` 覆盖。
- [ ] 定义固定 Joern 查询模板，禁止将用户输入直接拼成任意脚本。
- [ ] 定义 CLI 执行器，统一处理 timeout、return code、stderr 截断。
- [ ] 定义输出解析器，将 CLI 输出转为 `reachable/path_count/paths/summary/diagnostics`。
- [ ] 对 source/sink 行号不合法返回 `success=False`。
- [ ] 对 CLI 异常返回 `success=False`。
- [ ] 对查询成功但无路径返回 `success=True + reachable=False`。
- [ ] 在 [`backend/app/services/agent/tools/__init__.py`](/home/xyf/AuditTool/backend/app/services/agent/tools/__init__.py) 导出新工具。
- [ ] 在 [`backend/tests/agent/test_joern_dataflow_tool.py`](/home/xyf/AuditTool/backend/tests/agent/test_joern_dataflow_tool.py) 中覆盖：
- [ ] 文件不存在。
- [ ] 行号非法。
- [ ] CLI 执行失败。
- [ ] reachable 场景。
- [ ] not reachable 场景。

**建议验证命令**

```bash
uv run --directory backend pytest -s backend/tests/agent/test_joern_dataflow_tool.py
```

**完成判据**

- 新工具具备独立、稳定、可测试的结构化输出，不依赖旧工具文本结果。

### Task 7 Checklist: 新工具注册到 backend、scan-core 与前端目录

- [ ] 在 [`backend/app/api/v1/endpoints/agent_tasks_execution.py`](/home/xyf/AuditTool/backend/app/api/v1/endpoints/agent_tasks_execution.py) 的 `analysis` 工具集中注册 `joern_dataflow_analysis`。
- [ ] 评估 `report` 面是否也需要注入；若需要则同步加入。
- [ ] 在 [`backend/app/api/v1/endpoints/agent_test.py`](/home/xyf/AuditTool/backend/app/api/v1/endpoints/agent_test.py) 的 analysis/debug 构造函数中注入新工具。
- [ ] 在 [`backend/app/services/agent/mcp/router.py`](/home/xyf/AuditTool/backend/app/services/agent/mcp/router.py) 的 `_route_map` 中加入本地路由。
- [ ] 在 [`backend/app/services/agent/skills/scan_core.py`](/home/xyf/AuditTool/backend/app/services/agent/skills/scan_core.py) 的 `_SCAN_CORE_SKILLS` 中增加新条目。
- [ ] 为新工具定义 test policy；若暂不开放 skill test，给出禁用原因。
- [ ] 在 [`frontend/src/pages/intelligent-scan/skillToolsCatalog.ts`](/home/xyf/AuditTool/frontend/src/pages/intelligent-scan/skillToolsCatalog.ts) 中加入新工具详情。
- [ ] 在 [`backend/tests/test_agent_tool_registry.py`](/home/xyf/AuditTool/backend/tests/test_agent_tool_registry.py) 中断言新工具出现在正确 surface。
- [ ] 在 [`backend/tests/test_mcp_catalog.py`](/home/xyf/AuditTool/backend/tests/test_mcp_catalog.py) 中断言 `skillAvailability` 包含新工具。
- [ ] 在 [`frontend/tests/scanConfigExternalToolDetail.test.tsx`](/home/xyf/AuditTool/frontend/tests/scanConfigExternalToolDetail.test.tsx) 中补充详情页断言。

**建议验证命令**

```bash
uv run --directory backend pytest -s \
  backend/tests/test_agent_tool_registry.py \
  backend/tests/test_mcp_catalog.py
```

```bash
pnpm --dir frontend test:node
```

**完成判据**

- 新工具在 backend registry、skill availability、frontend 详情页三处都可见。

### Task 8 Checklist: Joern 文档同步

- [ ] 新建 [`backend/docs/agent-tools/tools/joern_dataflow_analysis.md`](/home/xyf/AuditTool/backend/docs/agent-tools/tools/joern_dataflow_analysis.md)。
- [ ] 写清楚工具目标、适用范围、输入字段、输出字段、失败语义。
- [ ] 在示例输入中体现 `file_path/source_line/sink_line`。
- [ ] 在示例说明中强调“单文件 v1，不是默认替代旧工具”。
- [ ] 更新 [`backend/docs/agent-tools/INDEX.md`](/home/xyf/AuditTool/backend/docs/agent-tools/INDEX.md) 加入新条目。
- [ ] 更新 [`backend/docs/agent-tools/TOOL_SHARED_CATALOG.md`](/home/xyf/AuditTool/backend/docs/agent-tools/TOOL_SHARED_CATALOG.md) 加入新工具分类。
- [ ] 更新 [`backend/app/services/agent/prompts/system_prompts.py`](/home/xyf/AuditTool/backend/app/services/agent/prompts/system_prompts.py) 中的工具说明。

**完成判据**

- 新工具在单工具文档、索引、共享目录、prompt 中都有对应说明，且表述一致。

### Task 9 Checklist: Joern 容器验收

- [ ] 构建 backend 镜像。
- [ ] 在容器内执行 `joern --help`。
- [ ] 在容器内执行最小真实 `joern_dataflow_analysis` 调用。
- [ ] 使用固定夹具验证一个 reachable 场景。
- [ ] 使用固定夹具验证一个 not reachable 场景。
- [ ] 通过 `agent_test` 或等效调试入口确认新工具可被调用。
- [ ] 记录一次失败样例输出，确认 diagnostics 便于排查。

**建议验证命令**

```bash
docker build -f backend/Dockerfile -t audittool-backend-flow ./backend
```

```bash
uv run --directory backend pytest -s backend/tests/agent/test_joern_dataflow_tool.py
```

**完成判据**

- Joern 从镜像、工具、调试入口三个层面都已跑通。

### Task 10 Checklist: 规则研究清单

- [ ] 新建 [`docs/dataflow_analysis_tool/joern_rule_research.md`](/home/xyf/AuditTool/docs/dataflow_analysis_tool/joern_rule_research.md)。
- [ ] 列出候选规则来源类别。
- [ ] 为每类规则记录字段丰富度、维护成本、可迁移性。
- [ ] 区分“可直接转成 reachability 输入模板”和“需要人工建模”的规则。
- [ ] 明确本阶段不进入数据库设计、不进入前端展示设计。
- [ ] 给出下一阶段研究建议，不绑定本轮代码改动。

**完成判据**

- 研究文档可独立交付，不阻塞前两阶段上线。

### 收尾 Checklist

- [ ] 运行 backend 相关测试子集。
- [ ] 运行 frontend 测试子集。
- [ ] 完成一次 backend Docker 构建。
- [ ] 记录未完成项、阻塞项、已知风险。
- [ ] 回看文档中的路径、命令、工具名是否与代码一致。

## 13. 四条并行工作流排期

本节将任务按“后端 / 文档 / 前端 / 验收”四条工作流重新编排。原则：

- 可以并行的尽量并行，但要显式标出依赖门。
- 后端工作流是主关键路径，文档与前端围绕后端契约推进。
- 验收工作流从第一天就介入，但完整容器验收放在后端主改动合流后执行。

### 13.1 工作流总览

| 工作流 | 目标 | 主要任务 | 可启动时机 | 关键依赖 |
| --- | --- | --- | --- | --- |
| 后端工作流 | 稳定旧工具并接入 Joern | Task 1、Task 2、Task 3、Task 5、Task 6、Task 7（backend 部分） | 立即开始 | 无 |
| 文档工作流 | 统一 backend docs / prompt / shared catalog | Task 4、Task 8、Task 10 | Task 0 完成后即可开始；Task 8 需等 Joern schema 初版稳定 | 依赖后端公开契约 |
| 前端工作流 | 同步静态工具目录与详情页展示 | Task 4（frontend 部分）、Task 7（frontend 部分） | Task 1 的新旧字段命名确定后即可开始 | 依赖后端公开输入/输出字段 |
| 验收工作流 | 持续回归与最终容器验收 | Task 3 验收、Task 7 测试、Task 9、收尾 Checklist | 立即开始测试准备；正式验收在后端合流后 | 依赖后端和前端改动完成 |

### 13.2 后端工作流

**负责人目标**

- 把 `dataflow_analysis` / `controlflow_analysis_light` 的公开契约和运行时语义修稳。
- 完成 Joern CLI 接入、新工具实现和 backend registry 打通。

**推荐执行顺序**

1. Task 0 中与后端相关的基线确认
2. Task 1: `dataflow_analysis` schema 与兼容层
3. Task 2: `controlflow_analysis_light` 诊断统一
4. Task 3: `code2flow` 镜像探测
5. Task 5: Joern CLI 镜像接入
6. Task 6: `joern_dataflow_analysis` 工具封装
7. Task 7: backend registry / mcp / scan-core 注册

**后端工作流内部里程碑**

- M1: 旧工具契约统一
  - 完成标志：Task 1 + Task 2 完成，旧工具测试通过
- M2: 旧依赖交付稳定
  - 完成标志：Task 3 完成，镜像内 `code2flow` 可执行
- M3: Joern 基础能力落地
  - 完成标志：Task 5 + Task 6 完成，工具可本地调用
- M4: Backend 暴露面打通
  - 完成标志：Task 7 的 backend 部分完成

**后端工作流交付物**

- 修改后的 backend 工具代码
- 修改后的 backend Docker 构建逻辑
- 新增 `joern_dataflow_analysis` backend 能力

### 13.3 文档工作流

**负责人目标**

- 确保 backend docs、prompt、shared catalog 与实际代码一致。
- 让开发者、agent、前端目录消费方看到的是同一套契约。

**推荐执行顺序**

1. 基于 Task 0 确认公共命名
2. 跟随后端 M1，完成 Task 4 中 backend docs / prompt 同步
3. 跟随后端 M3，完成 Task 8 中 Joern 文档同步
4. 独立推进 Task 10 研究文档

**文档工作流内部里程碑**

- M1: 旧工具文档统一
  - 完成标志：`dataflow_analysis` / `controlflow_analysis_light` 文档和 prompt 一致
- M2: Joern 文档补齐
  - 完成标志：新工具单文档、索引、shared catalog、prompt 一致
- M3: 研究文档独立交付
  - 完成标志：`joern_rule_research.md` 可单独评审

**文档工作流注意事项**

- 文档不得先于后端契约拍脑袋定字段。
- 如果后端 schema 仍在变化，文档工作流先更新“草案表述”，待后端合流后统一收口。

### 13.4 前端工作流

**负责人目标**

- 让 frontend 静态目录、详情页测试和 backend 暴露面保持同步。
- 不参与定义契约，只消费已冻结的字段名和工具目标。

**推荐执行顺序**

1. 等后端 M1 完成后，更新 `dataflow_analysis` / `controlflow_analysis_light` 静态目录
2. 等后端 M4 完成后，加入 `joern_dataflow_analysis`
3. 更新前端详情页测试与视图模型测试

**前端工作流内部里程碑**

- M1: 旧工具静态目录同步
  - 完成标志：旧工具 example input 改为定位优先模式
- M2: 新工具详情页可见
  - 完成标志：`joern_dataflow_analysis` 出现在前端目录与详情页测试中

**前端工作流注意事项**

- 不要在后端未确认 `line_start/line_end` 之前提前改死示例。
- 不要自行推断 Joern 输出结构，必须以 backend 工具返回结构为准。

### 13.5 验收工作流

**负责人目标**

- 提前布置测试与容器验证，不把验收堆到最后一天。
- 在每个里程碑完成后及时回归，避免大批量返工。

**推荐执行顺序**

1. 在 Task 1/2 开始时同步更新 backend 单测
2. 在 Task 3 完成后立即做 `code2flow` 镜像验收
3. 在 Task 7 完成后做 registry / catalog / frontend 回归
4. 在 Task 9 完成后做完整 Joern 容器验收
5. 执行收尾 Checklist

**验收工作流内部里程碑**

- M1: 旧工具回归通过
  - 完成标志：`backend/tests/agent/test_tools.py` 中旧工具相关用例通过
- M2: 可见面回归通过
  - 完成标志：registry、skillAvailability、frontend 测试通过
- M3: 容器级最终验收通过
  - 完成标志：镜像构建成功，`code2flow` / `joern` 均可执行，Joern 夹具真实调用通过

### 13.6 并行协作节奏

推荐按以下节奏安排：

#### Wave 1: 契约冻结

- 后端：Task 0、Task 1、Task 2
- 文档：同步标记旧工具字段基线，准备改 prompt 与 docs
- 前端：只做阅读，不提交依赖 schema 的改动
- 验收：补旧工具测试，准备回归命令

#### Wave 2: 旧工具稳定化

- 后端：Task 3
- 文档：Task 4
- 前端：Task 4 的 frontend 部分
- 验收：执行旧工具测试与 `code2flow` 镜像验收

#### Wave 3: Joern 接入

- 后端：Task 5、Task 6、Task 7 的 backend 部分
- 文档：Task 8 草稿
- 前端：等待新工具字段冻结
- 验收：准备 Joern 夹具与测试框架

#### Wave 4: 暴露面与最终验收

- 后端：Task 7 收尾
- 文档：Task 8、Task 10
- 前端：Task 7 的 frontend 部分
- 验收：Task 9 + 收尾 Checklist

### 13.7 PR 建议分组

为减少冲突，建议按工作流与依赖门拆 PR：

- PR 1: 后端旧工具契约统一
  - 包含：Task 1、Task 2
- PR 2: `code2flow` 镜像探测 + 旧文档同步
  - 包含：Task 3、Task 4
- PR 3: Joern CLI + backend 工具封装
  - 包含：Task 5、Task 6
- PR 4: 新工具可见面打通
  - 包含：Task 7、Task 8 的必要部分
- PR 5: 最终验收与研究文档
  - 包含：Task 9、Task 10、收尾 Checklist

### 13.8 阻塞关系

- 前端工作流阻塞于后端 M1 和 M4。
- 文档工作流中的 Joern 文档阻塞于后端 M3。
- 验收工作流中的最终容器验收阻塞于后端 M4 与前端 M2。
- Task 10 不阻塞任何代码合流，可独立排后。
