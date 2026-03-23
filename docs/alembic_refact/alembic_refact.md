# Alembic Refact Spec

## 阅读定位

- **文档类型**：Explanation 型设计规格文档。
- **目标读者**：负责实施本次 Alembic 迁移整理的后端开发者。
- **阅读目标**：理解为什么要把 `backend/alembic/versions` 从多分支兼容历史改写为单链历史，以及改写后的目标结构、约束和验证标准。
- **范围包含**：迁移链重排原则、文件保留/删除/改写边界、测试与验证策略、风险说明。
- **范围排除**：逐步执行 checklist、任务拆分、历史数据库处置脚本、提交策略。

## Background

当前 [`backend/alembic/versions`](/home/xyf/AuditTool/backend/alembic/versions) 的迁移历史同时承载了三类诉求：

1. 记录真实的 schema / data 业务变更。
2. 为旧 revision continuity 保留兼容 bridge。
3. 为并发开发期间出现的多头历史保留 merge revision。

这种历史结构在兼容旧环境时有价值，但它已经不适合当前项目的维护目标。现状中存在以下问题：

- 存在两个 base revision：`5b0f3c9a6d7e` 与 `c4b1a7e8d9f0`。
- 存在多处 tuple 型 `down_revision`，迁移图不是严格单链。
- 存在纯粹用于收敛历史的 no-op merge / compatibility bridge 脚本。
- 新环境从空库升级时，必须依赖历史 merge 顺序正确才能避免运行时错误。
- 测试需要显式维护多 base、多 branch、多 merge 的存在，认知成本高。

本次重构明确改变维护策略：项目不再追求对旧 revision 图的前向兼容，而是追求一条表达当前产品演进语义的、可读性强且可验证的单链迁移历史。

## Goals

本次 Alembic 重构的目标如下：

- 将迁移目录整理为**唯一 base + 唯一 head** 的单链历史。
- 保留现有业务变更语义，不把所有变化折叠成一个全新基线。
- 删除只为旧历史兼容服务的 bridge revision 和 merge revision。
- 让所有保留迁移的 `down_revision` 都为单值字符串或 `None`。
- 保证空数据库执行 `alembic upgrade head` 时能够稳定得到当前期望 schema。
- 让迁移测试围绕“单链历史”建立断言，而不是围绕旧兼容结构建立断言。

## Non-Goals

以下内容不在本次设计目标内：

- 不保证旧数据库从历史多分支 revision 图平滑升级到新图。
- 不保留旧 revision id continuity。
- 不改变当前最终 schema 的业务含义。
- 不在本规格中展开实现计划或执行任务列表。
- 不尝试借这次改造顺带清理无关 schema、模型或接口设计问题。

## Current Migration Inventory

### 唯一应保留的 baseline

- `5b0f3c9a6d7e_squashed_baseline.py`

该迁移已经代表压缩后的基础 schema，应继续作为新单链的唯一起点。

### 表达真实业务变更的迁移

以下迁移虽然当前处于分支或 merge 图中，但本质上表达了真实 schema / data 语义，应该保留并改写为单链历史的一部分：

- `6c8d9e0f1a2b_finalize_projects_zip_file_hash.py`
- `7f8e9d0c1b2a_normalize_static_finding_paths.py`
- `8c1d2e3f4a5b_add_agent_finding_identity.py`
- `9a7b6c5d4e3f_enforce_agent_finding_task_uniqueness.py`
- `9d3e4f5a6b7c_add_bandit_rule_states.py`
- `a1b2c3d4e5f6_add_phpstan_rule_states.py`
- `b2c3d4e5f6a7_add_bandit_rule_soft_delete.py`
- `c3d4e5f6a7b8_add_phpstan_rule_soft_delete.py`
- `e5f6a7b8c9d0_add_project_management_metrics.py`
- `b7e8f9a0b1c2_add_yasa_scan_tables.py`
- `a8f1c2d3e4b5_add_agent_tasks_report_column.py`
- `b9d8e7f6a5b4_drop_legacy_audit_tables.py`
- `f6a7b8c9d0e1_remove_fixed_static_finding_status.py`

### 应删除的兼容或合并迁移

以下迁移不表达新的 schema 业务语义，只是为了旧图兼容、收敛多头或保留 continuity，应在单链重写中移除：

- `c4b1a7e8d9f0_legacy_agent_findings_report_bridge.py`
- `d4e5f6a7b8c9_merge_phpstan_and_agent_heads.py`
- `5f6a7b8c9d0e_merge_project_metrics_and_yasa_phpstan_heads.py`
- `90a71996ac03_add_project_management_metrics_table.py`

## Target Linear History

目标状态下，迁移历史应表达为一条顺序明确、依赖关系单向的链。逻辑顺序如下：

1. `baseline`
   由 `5b0f3c9a6d7e` 提供唯一基础 schema。
2. `zip_file_hash` 完成基线后的结构收敛。
3. `static finding path normalization`
   对既有静态扫描表做路径归一化处理。
4. `agent finding identity`
   引入 agent finding 身份标识字段。
5. `agent finding uniqueness`
   对 agent finding 唯一性约束做收敛。
6. `bandit/phpstan rule states`
   按顺序加入规则状态表。
7. `bandit/phpstan soft delete`
   按顺序加入软删除标记。
8. `project_management_metrics`
   作为普通业务迁移串接到主链，而不是独立分支。
9. `yasa scan tables`
   在 metrics 之后加入，避免后续数据迁移访问未创建的表。
10. `agent_tasks.report`
    为 `agent_tasks` 增加报告字段。
11. `drop legacy audit tables`
    删除旧审计表及相关遗留字段。
12. `remove fixed static finding status`
    作为最终 head，对历史状态做数据归一化。

该顺序不要求完全保留当前文件的创建时间顺序，而是强调如下原则：

- 先建立结构依赖，再执行数据归一化。
- 原先依赖 merge 汇合的变化改写为显式顺序串接。
- 任何会访问某张表的数据迁移，都必须位于该表创建之后。
- 当前最终 schema 语义必须与重构前保持一致。

## File-Level Refactor Rules

### Baseline 规则

- `5b0f3c9a6d7e_squashed_baseline.py` 继续保留。
- 它必须成为唯一 `down_revision = None` 的迁移文件。
- 与其配套的 snapshot 相关测试，需要改为围绕“唯一 base”断言。

### 保留迁移的改写规则

对所有保留的真实业务迁移，统一采用以下规则：

- 每个文件只保留一个父 revision。
- 不再使用 tuple 型 `down_revision`。
- 文件名、revision id 可以重写，以反映新的线性历史顺序。
- 迁移内部 SQL / Alembic 操作应尽量保持原有业务语义，不在重排过程中顺带改变行为。
- 若某个迁移此前因兼容历史而引入无意义注释、说明或桥接语义，应在改写时清理，使其只表达当前真实变化。

### 删除迁移的处理规则

对于 merge / bridge / compatibility 文件：

- 从迁移目录中直接删除。
- 测试中不再断言这些文件存在。
- 代码与文档中若有写死这些 revision id 的引用，也应一并移除或改写。

### 文件命名规则

单链重写后，文件名与 revision id 不需要保留旧值，但应遵循以下原则：

- 文件名仍保持 `revision_slug_description.py` 形式。
- 描述应对应真实业务变化，而不是“merge”、“bridge”、“compatibility”。
- 同一链条上的文件名与 revision id 应清晰反映其线性顺序。

## Test And Verification Strategy

[`backend/tests/test_alembic_project.py`](/home/xyf/AuditTool/backend/tests/test_alembic_project.py) 需要从“验证兼容迁移图”重写为“验证单链迁移图”。核心断言应改为：

- 只有一个 base revision。
- 只有一个 head revision。
- 所有 `down_revision` 要么是 `None`，要么是单个字符串。
- 不再存在 tuple 型 `down_revision`。
- 不再断言 merge / bridge / compatibility 文件存在。
- 断言新的线性顺序符合设计预期。

除静态图测试外，还需要保留并强化以下验证：

- 在空数据库上执行 `alembic upgrade head` 成功。
- 执行 `alembic current` 返回新的唯一 head。
- 后端启动过程中的迁移版本检查通过。
- 重构后的最终 schema 与当前产品代码期望一致。

如果仓库中存在任何写死旧 revision id 的测试、启动检查或脚本，也应纳入本次验证范围。

## Risks

### 风险 1：代码或测试仍依赖旧 revision id

重写迁移历史后，所有以旧 revision id 为稳定标识的断言都可能失效。需要在实施时对仓库进行全量搜索，识别是否仍有逻辑依赖旧 id。

### 风险 2：线性重排引入隐式依赖错误

原多分支图中，某些依赖通过 merge revision 被动满足。改成单链后，如果排序不当，可能出现“数据迁移早于建表迁移”的问题。因此排序必须以 schema 依赖为先，而不是以旧时间戳为先。

### 风险 3：历史数据库不再可直接升级

这是本次改造的显式代价，不属于意外副作用。文档、测试和实施说明都应明确这一点，避免后续维护者错误地假设新图仍兼容历史库。

### 风险 4：baseline 语义被误扩张

本次目标不是生成一个新的“当前最终 schema 基线”，而是保留现有业务变更边界。实施时应避免把后续业务变化偷偷吸入 baseline，导致语义边界消失。

## Acceptance Criteria

本设计完成实施后，应满足以下验收条件：

- [`backend/alembic/versions`](/home/xyf/AuditTool/backend/alembic/versions) 中仅存在一个 base revision。
- 迁移目录中仅存在一个 head revision。
- 所有保留迁移的 `down_revision` 都是单值字符串或 `None`。
- 目录中不存在 merge、bridge 或 compatibility 性质的 no-op 迁移。
- 空数据库执行 `alembic upgrade head` 成功。
- `alembic current` 返回新的唯一 head。
- 后端启动期间的数据库迁移版本检查通过。
- 当前最终 schema 语义与重构前一致。
- 迁移图测试不再依赖旧兼容分支结构。

## Out Of Scope Follow-Up

本规格之外，仍可在后续单独文档中补充以下内容：

- 具体实施计划与任务拆分。
- 旧数据库或旧环境的迁移处置方案。
- revision id 重命名策略的执行细则。
- 实施过程中的提交与回滚策略。
