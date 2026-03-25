# PMD 扫描引擎页接入 Implementation Plan

> **For agentic workers:** REQUIRED: Use `superpowers:subagent-driven-development` (if subagents available) or `superpowers:executing-plans` to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有扫描引擎配置页中新增 `pmd` 页签，提供内置 PMD XML ruleset 浏览、preset 展示、自定义 XML 导入与复用能力，并与已经落地的 PMD runner / `PMDTool` 执行语义保持一致。

**Architecture:** 保持现有 PMD 扫描执行链路不变，新增一层“页面配置管理”能力。后端新增 PMD 共享 ruleset 服务、`static_tasks_pmd.py` 配置接口、自定义 ruleset 持久化模型；前端新增 `PmdRules.tsx`、PMD API client 和 loader，并把扫描引擎页与各规则页的引擎切换器统一扩展到 `pmd`。Preset alias 必须从同一份共享模块导出，避免页面展示与 `PMDTool` 实际执行不一致。

**Tech Stack:** React, TypeScript, TanStack Table, FastAPI, SQLAlchemy, Alembic, `xml.etree.ElementTree`, existing `scanner_runner` PMD runtime, `uv`, `pnpm`

---

## Execution Notes

- 本计划直接覆盖 `docs/add_pmd/pmd-scan-engine-page-plan.md`，不再额外创建新的 plan 文件。
- 当前仓库里与 PMD runner 相关的基础能力已经落地，不要重复实现：
  - `backend/app/services/agent/tools/external_tools.py`
  - `backend/app/core/config.py`
  - `backend/tests/test_pmd_runner_tool.py`
  - `backend/tests/test_pmd_runner_contracts.py`
- 本次只做“扫描引擎配置页接入”，不新增 PMD 扫描任务表、不改 Dashboard、不碰 PMD finding 页面。
- Python 相关命令统一走 `uv run`，Python 测试统一走 `uv run --project . ...`。
- 前端现有测试栈以 `node:test` + SSR / API 映射测试为主；本计划不为了 PMD 页面单独引入 React Testing Library。

## Current Baseline

### 已有能力

- `backend/app/services/agent/tools/external_tools.py` 中的 `PMDTool` 已切换到 `run_scanner_container(...)`，并且已经支持：
  - `security` / `quickstart` / `all` preset alias
  - 项目内 XML ruleset 直接挂载
  - 项目外 XML ruleset staging 到 `/scan/meta/rules`
  - `report.json` 读取与路径归一化
- `backend/app/core/config.py` 已有 `SCANNER_PMD_IMAGE`。
- `backend/app/db/rules_pmd/` 已存在内置 XML ruleset 文件，可直接作为页面内置数据源。
- `frontend/src/pages/ScanConfigEngines.tsx` 与 5 个现有规则页已形成成熟的页面/切换器结构。

### 明确缺口

- `frontend/src/pages/ScanConfigEngines.tsx` 仍只支持 `opengrep | gitleaks | bandit | phpstan | yasa`。
- 各规则页内部的 `EngineTab` union 和 `SelectItem` 选项是重复硬编码，新增 `pmd` 需要统一收口。
- 后端没有 PMD 页面专用配置接口，也没有自定义 PMD XML ruleset 的数据库模型。
- preset alias 仍定义在 `external_tools.py` 内，页面若直接复制一份会产生双写风险。

### 实现参考

- 页面交互和“内置 + 自定义配置”模式优先参考：
  - `frontend/src/pages/YasaRules.tsx`
  - `frontend/src/pages/yasaRulesLoader.ts`
- DataTable、统计卡片、详情弹窗风格优先参考：
  - `frontend/src/pages/BanditRules.tsx`
  - `frontend/src/pages/PhpstanRules.tsx`
- 后端“规则页接口 + 持久化状态/配置”的接口组织优先参考：
  - `backend/app/api/v1/endpoints/static_tasks_yasa.py`
  - `backend/app/api/v1/endpoints/static_tasks_bandit.py`
  - `backend/app/api/v1/endpoints/static_tasks_phpstan.py`

## Scope

### In Scope

- 扫描引擎页增加 `pmd` tab
- 新增 PMD 页面组件、API client、loader
- 新增 PMD 页面接口
- 新增自定义 PMD ruleset 持久化模型和 migration
- 抽取 PMD preset / builtin ruleset / XML 解析共享服务
- 补齐前后端测试与手工验收步骤

### Out Of Scope

- PMD 扫描任务创建页
- PMD findings 持久化模型与详情页
- Dashboard / 项目概览 PMD 聚合统计
- 自定义 XML 在线编辑
- 混合表格上的批量启停/批量删除
- 改造现有 PMD runner 运行契约

## File Structure

- Create: `backend/app/services/pmd_rulesets.py`
  - PMD 共享模块；负责 preset alias、preset 展示文案、内置 ruleset 发现、XML 解析、ruleset 摘要构造。
- Create: `backend/app/api/v1/endpoints/static_tasks_pmd.py`
  - PMD 页面接口；只处理 preset、内置 ruleset、自定义 ruleset CRUD。
- Create: `backend/app/models/pmd.py`
  - `PmdRuleConfig` 模型；只持久化自定义 XML ruleset。
- Create: `backend/alembic/versions/<revision>_add_pmd_rule_configs.py`
  - 创建 `pmd_rule_configs` 表和索引。
- Create: `backend/tests/test_pmd_rules_service.py`
  - 共享 PMD service 的 XML 解析、preset 对齐、builtin ruleset 发现测试。
- Create: `backend/tests/test_pmd_rules_api.py`
  - PMD 页面接口的过滤、导入、更新、删除测试。
- Modify: `backend/app/services/agent/tools/external_tools.py`
  - 改为从 PMD 共享模块导入 preset alias，移除本地重复定义。
- Modify: `backend/app/api/v1/endpoints/static_tasks.py`
  - 挂载 PMD router，并暴露 `_pmd` / API facade 供测试复用。
- Modify: `backend/app/models/__init__.py`
  - 导出 `PmdRuleConfig`，让 Alembic 和模型聚合入口看到新表。
- Create: `frontend/src/shared/constants/scanEngines.ts`
  - 统一维护 `EngineTab`、`SCAN_ENGINE_TABS`、selector options，避免 6 个页面重复硬编码。
- Create: `frontend/src/shared/api/pmd.ts`
  - PMD 页面 API client。
- Create: `frontend/src/pages/pmdRulesLoader.ts`
  - 聚合 `presets`、`builtinRulesets`、`customRuleConfigs` 的加载逻辑与降级策略。
- Create: `frontend/src/pages/PmdRules.tsx`
  - PMD 页面主体。
- Create: `frontend/tests/pmdRulesApi.test.ts`
  - PMD API client URL 映射测试。
- Create: `frontend/tests/pmdRulesLoader.test.ts`
  - PMD loader 的成功/局部失败降级测试。
- Create: `frontend/tests/scanConfigEnginesPmdTab.test.tsx`
  - `/scan-config/engines?tab=pmd` SSR 渲染测试。
- Modify: `frontend/src/pages/ScanConfigEngines.tsx`
  - 接入 `pmd` tab 和 `PmdRules` 页面。
- Modify: `frontend/src/pages/OpengrepRules.tsx`
  - 使用共享 engine constants，加入 `pmd` selector option。
- Modify: `frontend/src/pages/GitleaksRules.tsx`
  - 使用共享 engine constants，加入 `pmd` selector option。
- Modify: `frontend/src/pages/BanditRules.tsx`
  - 使用共享 engine constants，加入 `pmd` selector option。
- Modify: `frontend/src/pages/PhpstanRules.tsx`
  - 使用共享 engine constants，加入 `pmd` selector option。
- Modify: `frontend/src/pages/YasaRules.tsx`
  - 使用共享 engine constants，加入 `pmd` selector option。

## Task 1: Extract The Shared PMD Ruleset Service

**Files:**
- Create: `backend/app/services/pmd_rulesets.py`
- Create: `backend/tests/test_pmd_rules_service.py`
- Modify: `backend/app/services/agent/tools/external_tools.py`

- [ ] **Step 1: Write the failing PMD service tests**

在 `backend/tests/test_pmd_rules_service.py` 新增至少这些测试：

```python
def test_build_pmd_presets_matches_tool_alias_contract(): ...
def test_list_builtin_pmd_rulesets_reads_repo_xml_and_returns_metadata(): ...
def test_parse_pmd_ruleset_tolerates_namespace_and_ref_rules(): ...
def test_parse_pmd_ruleset_rejects_xml_without_rule_nodes(): ...
```

关键断言：

- `security` / `quickstart` / `all` 的 alias 值与 `PMDTool` 当前契约完全一致。
- 内置 ruleset 来源目录固定为 `backend/app/db/rules_pmd`。
- `ruleset_name`、`rule_count`、`languages`、`priorities`、`external_info_urls`、`raw_xml` 都能返回。
- XML namespace 差异不会导致 `<rule>` 节点丢失。
- 只含 `<rule ref="...">` 的场景仍算合法 ruleset。

- [ ] **Step 2: Run the service tests to verify they fail**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_rules_service.py tests/test_pmd_runner_tool.py -v
```

Expected:
- FAIL because `pmd_rulesets.py` 还不存在，alias 仍在 `external_tools.py` 本地维护。

- [ ] **Step 3: Create `backend/app/services/pmd_rulesets.py`**

实现要求：

- 导出单一真相源：
  - `PMD_RULESET_ALIASES`
  - `PMD_PRESET_SUMMARIES`
- 提供最少这些 helper：
  - `get_pmd_builtin_ruleset_dir()`
  - `list_builtin_pmd_rulesets(...)`
  - `get_builtin_pmd_ruleset_detail(...)`
  - `parse_pmd_ruleset_xml(...)`
- 使用标准库 `xml.etree.ElementTree`，不要新增第三方 XML 依赖。
- 查询 XML 节点时使用 namespace-agnostic 选择方式，例如 `".//{*}rule"`。
- `rule` 级别至少抽出：
  - `name`
  - `ref`
  - `language`
  - `message`
  - `class_name`
  - `priority`
  - `since`
  - `external_info_url`
  - `description`
- builtin ruleset 的稳定标识使用文件名（包含 `.xml` 后缀）。
- builtin ruleset 允许用 `lru_cache` 缓存；自定义 ruleset 读取时实时解析。

- [ ] **Step 4: Update `external_tools.py` to consume the shared aliases**

具体要求：

- 删掉 `external_tools.py` 中本地的 `PMD_RULESET_ALIASES` 定义。
- 从 `backend/app/services/pmd_rulesets.py` 导入 alias 常量。
- 不改动 `PMDTool` 的 runner 行为、输出格式、workspace 契约和现有测试断言。

- [ ] **Step 5: Re-run the PMD service and runner tests**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_rules_service.py tests/test_pmd_runner_tool.py -v
```

Expected:
- PASS for shared preset alias contract and XML parsing coverage.

- [ ] **Step 6: Commit the shared PMD service baseline**

Run:

```bash
cd /home/xyf/AuditTool
git add backend/app/services/pmd_rulesets.py backend/app/services/agent/tools/external_tools.py backend/tests/test_pmd_rules_service.py
git commit -m "refactor: extract shared PMD ruleset service"
```

## Task 2: Add PMD Ruleset Persistence And Static Tasks API

**Files:**
- Create: `backend/app/models/pmd.py`
- Create: `backend/alembic/versions/<revision>_add_pmd_rule_configs.py`
- Create: `backend/app/api/v1/endpoints/static_tasks_pmd.py`
- Create: `backend/tests/test_pmd_rules_api.py`
- Modify: `backend/app/api/v1/endpoints/static_tasks.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Write the failing PMD API tests**

在 `backend/tests/test_pmd_rules_api.py` 新增至少这些测试：

```python
async def test_list_pmd_presets_returns_shared_service_payload(...): ...
async def test_list_builtin_pmd_rulesets_filters_keyword_and_language(...): ...
async def test_get_builtin_pmd_ruleset_returns_raw_xml_and_rule_details(...): ...
async def test_import_pmd_rule_config_validates_xml_and_persists_record(...): ...
async def test_update_pmd_rule_config_only_updates_metadata_fields(...): ...
async def test_delete_pmd_rule_config_removes_record(...): ...
```

关键断言：

- preset 接口直接复用共享 service 的 alias / description / categories。
- builtin list 支持 `keyword`、`language`、`limit`。
- custom import 要求 `.xml` 且至少含一个 `<rule>`。
- `PATCH` 仅允许更新 `name` / `description` / `is_active`。
- `PATCH` 不能改 `xml_content` / `filename`。

- [ ] **Step 2: Run the PMD API tests to verify they fail**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_rules_api.py -v
```

Expected:
- FAIL because `static_tasks_pmd.py`、`PmdRuleConfig` 和路由挂载都还不存在。

- [ ] **Step 3: Create `backend/app/models/pmd.py` and the Alembic migration**

模型约束：

- 表名：`pmd_rule_configs`
- 字段：
  - `id`
  - `name`
  - `description`
  - `filename`
  - `xml_content`
  - `is_active`
  - `created_by`
  - `created_at`
  - `updated_at`
- 索引：
  - `created_at`
  - `is_active`
  - `(is_active, created_at)`

实现边界：

- 只持久化自定义 XML ruleset。
- 不新增 PMD 扫描任务表、finding 表。
- 不把解析后的 rule 展平入库；读取接口时再解析 XML。

- [ ] **Step 4: Create `backend/app/api/v1/endpoints/static_tasks_pmd.py`**

实现这些接口：

- `GET /pmd/presets`
- `GET /pmd/builtin-rulesets`
- `GET /pmd/builtin-rulesets/{ruleset_id}`
- `POST /pmd/rule-configs/import`
- `GET /pmd/rule-configs`
- `GET /pmd/rule-configs/{rule_config_id}`
- `PATCH /pmd/rule-configs/{rule_config_id}`
- `DELETE /pmd/rule-configs/{rule_config_id}`

接口实现要求：

- 与现有 `static_tasks_yasa.py` 一样走：
  - `db: AsyncSession = Depends(get_db)`
  - `current_user: User = Depends(deps.get_current_user)`
- custom import 使用 `Form(...)` + `UploadFile`。
- 导入成功后返回解析后的 ruleset 摘要，而不是只回 DB 原始行。
- custom list / detail 响应中要包含：
  - `id`
  - `name`
  - `description`
  - `filename`
  - `is_active`
  - `source`
  - `ruleset_name`
  - `rule_count`
  - `languages`
  - `priorities`
  - `external_info_urls`
  - `rules`
  - `raw_xml`
- builtin 与 custom 的响应字段尽量对齐，方便前端表格合并。
- 第一版不做软删除，`DELETE` 直接删记录。

- [ ] **Step 5: Wire the PMD router and exports into `static_tasks.py`**

要求：

- `from app.api.v1.endpoints import static_tasks_pmd as _pmd`
- `router.include_router(_pmd.router)`
- 暴露测试会直接复用的 facade：
  - `list_pmd_presets`
  - `list_builtin_pmd_rulesets`
  - `get_builtin_pmd_ruleset`
  - `import_pmd_rule_config`
  - `list_pmd_rule_configs`
  - `get_pmd_rule_config`
  - `update_pmd_rule_config`
  - `delete_pmd_rule_config`

- [ ] **Step 6: Register the model aggregation**

在 `backend/app/models/__init__.py` 中导出：

```python
from .pmd import PmdRuleConfig
```

不要修改 `backend/app/main.py` 的中断恢复逻辑，因为本次没有新增 PMD scan task。

- [ ] **Step 7: Run migration and backend API tests**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . alembic upgrade head
uv run --project . pytest tests/test_pmd_rules_service.py tests/test_pmd_rules_api.py tests/test_pmd_runner_tool.py -v
```

Expected:
- Alembic upgrade 成功创建 `pmd_rule_configs`。
- PMD service / API / runner tests 全部 PASS。

- [ ] **Step 8: Commit the PMD ruleset API layer**

Run:

```bash
cd /home/xyf/AuditTool
git add backend/app/models/pmd.py backend/app/models/__init__.py backend/app/api/v1/endpoints/static_tasks_pmd.py backend/app/api/v1/endpoints/static_tasks.py backend/alembic/versions backend/tests/test_pmd_rules_api.py
git commit -m "feat: add PMD ruleset management API"
```

## Task 3: Add The Frontend PMD API Client And Loader

**Files:**
- Create: `frontend/src/shared/api/pmd.ts`
- Create: `frontend/src/pages/pmdRulesLoader.ts`
- Create: `frontend/tests/pmdRulesApi.test.ts`
- Create: `frontend/tests/pmdRulesLoader.test.ts`

- [ ] **Step 1: Write the failing frontend API and loader tests**

在 `frontend/tests/pmdRulesApi.test.ts` 覆盖：

```ts
getPmdPresets()
getPmdBuiltinRulesets(...)
getPmdBuiltinRuleset(...)
importPmdRuleConfig(...)
getPmdRuleConfigs(...)
getPmdRuleConfig(...)
updatePmdRuleConfig(...)
deletePmdRuleConfig(...)
```

在 `frontend/tests/pmdRulesLoader.test.ts` 覆盖：

```ts
loadPmdRulesPageData()
```

关键断言：

- URL 与后端路由一一对应。
- loader 使用 `Promise.allSettled` 风格的局部降级。
- builtin rules 加载失败时，页面主表格进入错误态。
- presets / custom rules 加载失败时，页面仍能展示其余数据并回传 fallback 文案。

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run:

```bash
cd /home/xyf/AuditTool/frontend
pnpm test:node tests/pmdRulesApi.test.ts tests/pmdRulesLoader.test.ts
```

Expected:
- FAIL because PMD API client 与 loader 还不存在。

- [ ] **Step 3: Create `frontend/src/shared/api/pmd.ts`**

接口定义建议：

- `PmdPreset`
- `PmdRulesetSummary`
- `PmdRuleConfig`

实现要求：

- query 参数命名与后端完全一致：
  - `keyword`
  - `language`
  - `is_active`
  - `skip`
  - `limit`
- `GET /static-tasks/pmd/builtin-rulesets/{id}` 与 `GET /static-tasks/pmd/rule-configs/{id}` 都用 `encodeURIComponent(...)`。
- `importPmdRuleConfig(...)` 使用 `FormData` 上传：
  - `name`
  - `description`
  - `xml_file`

- [ ] **Step 4: Create `frontend/src/pages/pmdRulesLoader.ts`**

loader 返回结构建议：

```ts
interface PmdRulesLoaderResult {
  presets: PmdPreset[];
  builtinRulesets: PmdRulesetSummary[];
  customRuleConfigs: PmdRuleConfig[];
  builtinLoadError: string | null;
  presetsLoadError: string | null;
  customConfigsLoadError: string | null;
}
```

实现边界：

- 只负责数据聚合和错误归一化，不拼 UI row。
- fallback 文案风格参考 `frontend/src/pages/yasaRulesLoader.ts`。

- [ ] **Step 5: Re-run the frontend API and loader tests**

Run:

```bash
cd /home/xyf/AuditTool/frontend
pnpm test:node tests/pmdRulesApi.test.ts tests/pmdRulesLoader.test.ts
```

Expected:
- PASS for PMD API client URL mapping and loader degradation behavior.

- [ ] **Step 6: Commit the frontend data layer**

Run:

```bash
cd /home/xyf/AuditTool
git add frontend/src/shared/api/pmd.ts frontend/src/pages/pmdRulesLoader.ts frontend/tests/pmdRulesApi.test.ts frontend/tests/pmdRulesLoader.test.ts
git commit -m "feat: add PMD frontend data layer"
```

## Task 4: Build The PMD Page And Wire The Engine Tabs

**Files:**
- Create: `frontend/src/shared/constants/scanEngines.ts`
- Create: `frontend/src/pages/PmdRules.tsx`
- Create: `frontend/tests/scanConfigEnginesPmdTab.test.tsx`
- Modify: `frontend/src/pages/ScanConfigEngines.tsx`
- Modify: `frontend/src/pages/OpengrepRules.tsx`
- Modify: `frontend/src/pages/GitleaksRules.tsx`
- Modify: `frontend/src/pages/BanditRules.tsx`
- Modify: `frontend/src/pages/PhpstanRules.tsx`
- Modify: `frontend/src/pages/YasaRules.tsx`

- [ ] **Step 1: Write the failing PMD tab SSR test**

在 `frontend/tests/scanConfigEnginesPmdTab.test.tsx` 新增：

```ts
test("ScanConfigEngines renders pmd rules page when tab=pmd", () => { ... })
```

关键断言：

- 页面出现 `PMD 预设组合`
- 页面出现 `导入 XML ruleset`
- 页面出现 `内置 ruleset`

- [ ] **Step 2: Run the SSR test to verify it fails**

Run:

```bash
cd /home/xyf/AuditTool/frontend
pnpm test:node tests/scanConfigEnginesPmdTab.test.tsx
```

Expected:
- FAIL because `ScanConfigEngines.tsx` 还不能识别 `tab=pmd`。

- [ ] **Step 3: Create shared scan engine constants**

在 `frontend/src/shared/constants/scanEngines.ts` 中收口：

```ts
export const SCAN_ENGINE_TABS = ["opengrep", "gitleaks", "bandit", "phpstan", "yasa", "pmd"] as const;
export type EngineTab = (typeof SCAN_ENGINE_TABS)[number];
export const SCAN_ENGINE_OPTIONS = ...
```

目标：

- 不再让 6 个页面各自维护 `EngineTab` union。
- 不再在每个 selector 里手写 6 个 `SelectItem`。

- [ ] **Step 4: Create `frontend/src/pages/PmdRules.tsx`**

页面结构固定为三段：

1. 顶部统计卡片
2. preset 说明区
3. ruleset DataTable

实现要求：

- 数据加载走 `loadPmdRulesPageData()`。
- 统计卡片至少展示：
  - 内置 ruleset 数量
  - 自定义 ruleset 数量
  - 已启用自定义 ruleset 数量
  - preset 数量
- preset 说明区只读，不放进表格。
- 表格 row 合并 builtin + custom，建议 view model 统一为：
  - `id`
  - `name`
  - `source`
  - `filename`
  - `languages`
  - `ruleCount`
  - `priorities`
  - `activeStatus`
  - `rawXml`
  - `rules`
- builtin row 只显示“查看详情”。
- custom row 显示：
  - 查看详情
  - 编辑元数据
  - 启用/禁用
  - 删除
- 第一版不做混合批量操作，`selection` 可直接关闭或只保留导入按钮。
- 详情弹窗展示：
  - ruleset 名称
  - 来源
  - 文件名
  - 语言集合
  - rule 数量
  - priority 集合
  - externalInfoUrl 汇总
  - 子规则列表
  - raw XML
- 导入弹窗字段：
  - `name`
  - `description`
  - `xml file`
- 前端先做一层轻校验：
  - 文件后缀必须是 `.xml`
  - `name` 不能为空

- [ ] **Step 5: Wire `pmd` into `ScanConfigEngines.tsx` and all engine selectors**

具体要求：

- `ScanConfigEngines.tsx` 引入 `PmdRules`。
- `tab=pmd` 时渲染 `PmdRules`。
- `OpengrepRules.tsx`
- `GitleaksRules.tsx`
- `BanditRules.tsx`
- `PhpstanRules.tsx`
- `YasaRules.tsx`

这 5 个页面都改成复用共享 `EngineTab` 与 options，确保 selector 中出现 `pmd`。

- [ ] **Step 6: Re-run the PMD frontend tests**

Run:

```bash
cd /home/xyf/AuditTool/frontend
pnpm test:node tests/pmdRulesApi.test.ts tests/pmdRulesLoader.test.ts tests/scanConfigEnginesPmdTab.test.tsx
```

Expected:
- PASS for PMD API, loader, and tab-level SSR coverage.

- [ ] **Step 7: Manual smoke check the PMD page**

手工验证步骤：

1. 启动前后端本地环境。
2. 访问 `/scan-config/engines?tab=pmd`。
3. 确认 selector 中可切换到 `pmd`。
4. 确认 preset 卡片与 builtin ruleset 列表正常显示。
5. 复制一份内置 XML 作为上传样本，例如：

```bash
cp /home/xyf/AuditTool/backend/app/db/rules_pmd/HardCodedCryptoKey.xml /tmp/pmd-custom.xml
```

6. 通过页面导入 `/tmp/pmd-custom.xml`。
7. 刷新页面，确认自定义 ruleset 仍存在，并可启用/禁用、删除、查看 raw XML。

- [ ] **Step 8: Commit the PMD page integration**

Run:

```bash
cd /home/xyf/AuditTool
git add frontend/src/shared/constants/scanEngines.ts frontend/src/pages/PmdRules.tsx frontend/src/pages/ScanConfigEngines.tsx frontend/src/pages/OpengrepRules.tsx frontend/src/pages/GitleaksRules.tsx frontend/src/pages/BanditRules.tsx frontend/src/pages/PhpstanRules.tsx frontend/src/pages/YasaRules.tsx frontend/tests/scanConfigEnginesPmdTab.test.tsx
git commit -m "feat: add PMD scan engine page"
```

## Task 5: Final Verification And Handoff

**Files:**
- Modify: `docs/add_pmd/pmd-scan-engine-page-plan.md`

- [ ] **Step 1: Run the backend verification set**

Run:

```bash
cd /home/xyf/AuditTool/backend
uv run --project . pytest tests/test_pmd_rules_service.py tests/test_pmd_rules_api.py tests/test_pmd_runner_tool.py tests/test_pmd_runner_contracts.py -v
```

Expected:
- PASS for shared service, page API, existing PMD runner contract.

- [ ] **Step 2: Run the frontend verification set**

Run:

```bash
cd /home/xyf/AuditTool/frontend
pnpm test:node tests/pmdRulesApi.test.ts tests/pmdRulesLoader.test.ts tests/scanConfigEnginesPmdTab.test.tsx
```

Expected:
- PASS for PMD frontend coverage.

- [ ] **Step 3: Confirm no accidental scope expansion**

人工核对以下文件未发生与本计划无关的扩展：

- `backend/app/main.py`
- `backend/tests/test_pmd_runner_tool.py`
- `backend/tests/test_pmd_runner_contracts.py`
- `backend/docker/pmd-runner.Dockerfile`
- `docker-compose.yml`
- `docker-compose.full.yml`

- [ ] **Step 4: Commit the final integration state**

Run:

```bash
cd /home/xyf/AuditTool
git status --short
git commit -m "docs: finalize PMD scan engine page implementation plan"
```

## Acceptance Checklist

- [ ] `/scan-config/engines?tab=pmd` 能正常打开 PMD 页面。
- [ ] 页面视觉与现有扫描引擎配置页保持一致。
- [ ] 页面能展示内置 PMD XML ruleset 列表。
- [ ] 页面能展示 `security` / `quickstart` / `all` preset 说明，且内容与 `PMDTool` 实际 alias 一致。
- [ ] 页面支持上传自定义 XML ruleset。
- [ ] 自定义 XML ruleset 刷新后仍可见。
- [ ] builtin ruleset 只允许查看详情。
- [ ] custom ruleset 支持查看详情、编辑元数据、启用/禁用、删除。
- [ ] 详情弹窗能展示 raw XML 与解析出的 rule 信息。
- [ ] 前后端测试命令都能通过。

## Risks And Guardrails

- PMD 是 ruleset 驱动，不要把这次需求膨胀成“单条 rule 管理平台”。
- builtin 与 custom 混合表格容易诱发批量操作歧义，第一版不要补批量启停/删除。
- XML 解析必须容忍 namespace、`rule ref`、缺失描述字段等真实文件差异。
- 自定义 ruleset 的 `PATCH` 不要开放 `xml_content` 在线编辑，否则会把校验、diff、回滚复杂度一并引入。
- 若后续需要把页面配置直接接入扫描任务创建流程，应另起一份“参数模型统一”方案，不在本计划内叠加。
