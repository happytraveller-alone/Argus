# AuditTool（DeepAudit）前后端架构梳理与对齐指南

> 目的：建立一份“可落地”的架构对齐文档，帮助后续快速做接口与 UI 的增删改查（CRUD），减少前后端口径偏差。

## 1. 项目定位与演进背景

- 当前仓库目录名为 `AuditTool`，代码与文档历史命名仍大量保留 `DeepAudit`。
- 项目已从“单一审计链路”演进为 **三条并行审计链路**：
  1. 传统审计（`/tasks` + `/scan`，LLM 扫描）
  2. Agent 审计（`/agent-tasks`，多 Agent + 流式事件）
  3. 静态规则审计（`/static-tasks`，Opengrep + Gitleaks）
- 这三条链路共享核心实体 `Project`，在仪表盘与项目详情页做聚合展示。

---

## 2. 总体架构（运行时）

```text
React + TypeScript (frontend)
        |
        |  HTTP / SSE  (/api/v1/*)
        v
FastAPI (backend/app/main.py)
        |
        +-- API Routers (backend/app/api/v1/endpoints/*.py)
        +-- Services     (backend/app/services/**)
        +-- SQLAlchemy   (backend/app/models/**)
        +-- Alembic      (backend/alembic/versions/**)
        v
PostgreSQL
```

关键入口：

- 后端应用入口：`backend/app/main.py`
- API 路由聚合：`backend/app/api/v1/api.py`
- 前端 API Client：`frontend/src/shared/api/serverClient.ts`（`baseURL = /api/v1`）
- 前端路由配置：`frontend/src/app/routes.tsx`

---

## 3. 后端架构分层

## 3.1 API 层（Router）

- 所有 v1 API 在 `backend/app/api/v1/endpoints/`。
- 由 `backend/app/api/v1/api.py` 统一挂载到 `/api/v1`。

已挂载的业务域：

- `/users`
- `/projects`（含成员接口）
- `/tasks`（传统审计任务）
- `/scan`（即时分析/ZIP 扫描）
- `/config`
- `/prompts`
- `/rules`
- `/agent-tasks`
- `/embedding`
- `/ssh-keys`
- `/static-tasks`

## 3.2 Service 层

目录：`backend/app/services/`

- `scanner.py`：传统仓库扫描主流程
- `llm/`：LLM 适配器、工厂、缓存
- `agent/`：多 Agent 核心（agents/tools/streaming/knowledge）
- `upload/`：压缩文件处理、语言识别、项目统计
- `rag/`：向量检索与索引

## 3.3 数据模型层

目录：`backend/app/models/`

核心关系（简化）：

```text
Project
 ├─ AuditTask         ─┬─ AuditIssue
 ├─ AgentTask         ├─ AgentEvent
 │                     └─ AgentFinding
 ├─ OpengrepScanTask  ─┬─ OpengrepFinding
 └─ GitleaksScanTask  ─┬─ GitleaksFinding

ProjectMember, User, UserConfig, ProjectInfo, PromptTemplate, AuditRuleSet/AuditRule...
```

数据库变更入口：`backend/alembic/versions/`

---

## 4. 前端架构分层

## 4.1 路由与页面

- 路由定义：`frontend/src/app/routes.tsx`
- 主要页面：
  - `frontend/src/pages/Dashboard.tsx`
  - `frontend/src/pages/Projects.tsx`
  - `frontend/src/pages/ProjectDetail.tsx`
  - `frontend/src/pages/AgentAudit/index.tsx`
  - `frontend/src/pages/OpengrepRules.tsx`
  - `frontend/src/pages/StaticAnalysis.tsx`

## 4.2 API 层（前端）

目录：`frontend/src/shared/api/`

- `serverClient.ts`：axios 实例
- `database.ts`：兼容层（保留旧 deepaudit 的调用习惯）
- `agentTasks.ts` / `agentStream.ts`
- `opengrep.ts` / `gitleaks.ts`
- `rules.ts` / `prompts.ts`
- `sshKeys.ts`

## 4.3 组件与状态

- `components/`：通用 UI 与业务组件
- `shared/stores/opengrepRulesStore.ts`：本地规则缓存
- `shared/config/database.ts`：把 `api` 兼容导出到旧调用点

---

## 5. 前后端对齐矩阵（最重要）

| 业务域 | 后端前缀 | 前端 API 文件 | 主要页面/UI |
|---|---|---|---|
| 项目管理 | `/projects` | `shared/api/database.ts` | `Projects.tsx`、`ProjectDetail.tsx`、`CreateTaskDialog.tsx` |
| 项目成员 | `/projects/{id}/members` | `shared/api/database.ts` | 项目相关弹窗/管理 |
| 传统任务 | `/tasks` + `/scan` | `shared/api/database.ts`、`features/projects/services/repoZipScan.ts` | Dashboard、ProjectDetail、IntelligentAudit |
| Agent 任务 | `/agent-tasks` | `shared/api/agentTasks.ts`、`shared/api/agentStream.ts` | AgentAudit、Dashboard、ProjectDetail |
| 静态扫描任务 | `/static-tasks/tasks` + `/static-tasks/gitleaks/*` | `shared/api/opengrep.ts`、`shared/api/gitleaks.ts` | StaticAnalysis、Dashboard、ProjectDetail、CreateTaskDialog |
| 静态规则库 | `/static-tasks/rules` | `shared/api/opengrep.ts` | OpengrepRules、CreateTaskDialog |
| 审计规则集 | `/rules` | `shared/api/rules.ts` | Dashboard（统计）、配置页 |
| 提示词模板 | `/prompts` | `shared/api/prompts.ts` | 暂无活跃前端入口、Dashboard（统计） |
| 系统配置 | `/config`、`/embedding` | `shared/api/database.ts` + 局部 `apiClient` | SystemConfig、EmbeddingConfig |
| SSH 能力 | `/ssh-keys` | `shared/api/sshKeys.ts` | 项目接入/配置流程 |

---

## 6. 三条审计链路的职责边界

## 6.1 传统审计链路（历史兼容）

- 核心接口：`/projects/{id}/scan`、`/scan/upload-zip`、`/tasks/*`
- 模型：`AuditTask` / `AuditIssue`
- 适合：快速 LLM 扫描、历史数据兼容

## 6.2 Agent 审计链路（主力）

- 核心接口：`/agent-tasks/*`
- 模型：`AgentTask` / `AgentEvent` / `AgentFinding`
- 特点：SSE/流式日志、Agent 树、检查点、报告导出

## 6.3 静态规则审计链路（规则驱动）

- 核心接口：`/static-tasks/*`
- 模型：`Opengrep*` / `Gitleaks*`
- 特点：规则管理、批量规则启停、静态结果状态回写

---

## 7. 新增一个 CRUD 业务的标准流程（推荐模板）

## 7.1 后端（必须）

1. **Model**：`backend/app/models/<domain>.py`
2. **Migration**：`backend/alembic/versions/<revision>_<domain>.py`
3. **Schema**：`backend/app/schemas/<domain>.py`
4. **Endpoint**：`backend/app/api/v1/endpoints/<domain>.py`
5. **Router 挂载**：`backend/app/api/v1/api.py`
6. **测试**：`backend/tests/test_<domain>*.py`

推荐响应约定（便于前端复用）：

- 列表：`{ items: T[], total: number, skip, limit }`（或统一明确为数组）
- 详情：`T`
- 创建：`T`
- 更新：`T`
- 删除：`{ message, id }`

## 7.2 前端（必须）

1. 在 `frontend/src/shared/api/<domain>.ts` 新增类型与请求函数
2. 页面/组件 **只依赖 shared/api**，避免散落 `apiClient` 直调
3. 页面状态统一管理加载态、错误态、空态
4. 如需跨组件共享，补 `shared/stores/<domain>Store.ts`
5. 在 `routes.tsx` 增加页面路由（如有新页面）

## 7.3 UI 对齐 Checklist

- 字段命名与后端 schema 完全一致（大小写/枚举值）
- 列表筛选参数与后端 query 参数一致
- 状态流转按钮只提交后端允许值
- 导出/下载接口声明 `responseType` 正确
- 国际化文本有中英文 fallback

---

## 8. 当前架构对齐风险（建议优先治理）

1. **兼容层过厚**：`shared/api/database.ts` 承担了大量旧接口适配，建议逐步按业务拆分。
2. **调用风格不统一**：部分页面直接 `apiClient.get(...)`，部分走 `shared/api/*`，建议统一。
3. **响应结构不统一**：有的列表返回数组，有的返回 `{items,total}`，建议统一规范。
4. **命名历史包袱**：DeepAudit/AuditTool 混用，建议统一品牌层与代码层命名策略。
5. **链路并存复杂度高**：传统/Agent/静态三套任务体系并存，建议在 UI 上明确来源标签与生命周期。

---

## 9. 推荐的后续治理顺序（两周可落地）

### 第 1 阶段（接口契约统一）

- 建立统一 API Contract 规范（列表、分页、错误码、枚举）
- 为 `shared/api/*` 补齐“唯一调用入口”约束，减少页面直调

### 第 2 阶段（领域拆分与类型收敛）

- 将 `shared/api/database.ts` 中混合职责拆分到领域 API
- 统一前端 `shared/types` 与后端 schema 字段语义

### 第 3 阶段（CRUD 模板化）

- 新增脚手架文档：`model + migration + endpoint + shared/api + page` 模板
- 对新增功能执行 checklist（接口、状态、UI、i18n、测试）

---

## 10. 一句话原则

**后端 schema 是唯一真相，前端只消费 `shared/api` 的契约类型；新增 CRUD 按“领域化 + 模板化”推进。**
