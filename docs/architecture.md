# AuditTool / Argus 开发者架构指南

> 2026-04-18 更新：当前产品扫描模式已收口为静态审计与智能审计。历史兼容字段与迁移背景请以 `plan/rust_full_takeover/` 下的文档为准。

> 这份文档不是接口清单，也不是目录罗列。它的目标只有一个：让第一次接手这个项目的开发者，能在最短时间内看懂系统主线，并知道应该从哪里开始读代码。

## 阅读定位

- **文档类型**：以 Explanation 为主，兼顾入门阶段最常用的 Reference 索引。
- **目标读者**：第一次接手 AuditTool / Argus 的前端、后端或全栈开发者。
- **阅读目标**：快速建立系统主线，理解两类扫描模式的边界，并知道该从哪些代码入口开始定位问题。
- **建议搭配**：如果你接下来主要改智能审计，再继续阅读 [agentic_scan_core/README.md](./agentic_scan_core/README.md)。
- **术语入口**：如果你对 `Project`、`AgentTask`、bootstrap、finding 这些词还不熟，先看 [glossary.md](./glossary.md)。
- **本文不覆盖**：接口字段逐项解释、数据库逐表说明、未来规划设计。

## 建议阅读方式

按下面的顺序阅读，最容易形成稳定心智模型：

1. 先看“这个系统是什么”和“两类扫描任务”，建立产品级边界。
2. 再看“核心运行模型”和“请求怎么流动”，理解对象关系与执行主线。
3. 最后按“代码从哪里读”和“常见开发任务怎么定位”回到具体文件。

## 先看懂系统

### 这个系统是什么

AuditTool 是一个面向代码仓库安全扫描的平台。仓库名叫 `AuditTool`，代码和历史文档里仍大量保留 `Argus` 这个名字，两者指向的是同一个系统。

从实现上看，它是一个标准的前后端分离应用：

- 前端：React + Vite 单页应用
- 后端：FastAPI 单体服务
- 数据层：PostgreSQL
- 运行期辅助能力：Redis、Docker sandbox、LLM、可选 RAG

如果只记一句话，可以这样理解它：

**它是一个以 `Project` 为中心，把两类扫描任务统一组织起来的安全扫描工作台。**

### 先记住两类扫描任务

当前产品视角下，系统只有两类主任务：

#### 1. 静态审计

静态审计是多引擎任务的统一产品视图。  
它负责快速给出规则命中、密钥泄露、语言级静态分析结果。

当前静态引擎包括：

- Opengrep
- Gitleaks
- Bandit
- PHPStan
- YASA

这些引擎在后端是多套并列任务模型，但在前端会被聚合成一类“静态审计”体验。

#### 2. 智能审计

智能审计由 `AgentTask` 主导。  
它不是简单跑一遍规则，而是让 Agent 做文件侦察、漏洞分析、验证和报告生成。

如果你看到：

- `AgentTask`
- `AgentEvent`
- `AgentFinding`
- SSE 实时流

它们基本都属于智能审计主链路。

## 核心运行模型

### `Project` 是整个系统的中心

后端模型入口：`backend/app/models/project.py`

系统里几乎所有能力都围绕 `Project` 展开。你可以把它理解成“一个待扫描代码仓库的工作空间”。

`Project` 负责承接：

- 项目来源信息：远程仓库或 ZIP 包
- 项目成员与归属
- 代码文件与压缩包归档
- 两类扫描任务
- 项目级统计与结果聚合

所以你在定位任何功能时，都可以先问自己一句：

**这个功能是不是挂在某个项目之下？**

大多数时候答案都是“是”。

### 智能审计的核心对象

如果你要理解智能审计，只需要先看四个对象：

- `AgentTask`
  - 一次智能审计任务
- `AgentEvent`
  - 任务运行过程中的实时事件
- `AgentFinding`
  - Agent 最终沉淀的漏洞发现
- `AgentTreeNode`
  - Agent 树与子 Agent 关系

它们定义在：`backend/app/models/agent_task.py`

这套模型解释了为什么智能审计页面不仅能展示结果，还能展示：

- 当前阶段
- 实时日志
- 工具调用
- 验证状态
- 报告内容

### 静态审计的核心对象

静态审计不是一个总模型，而是多套引擎模型并列存在。

最重要的模型文件是：

- `backend/app/models/opengrep.py`
- `backend/app/models/gitleaks.py`
- `backend/app/models/bandit.py`
- `backend/app/models/phpstan.py`
- `backend/app/models/yasa.py`

共同特点很简单：

- 每个引擎都有自己的 task
- 每个引擎都有自己的 finding
- 都挂在 `Project` 下

产品层把它们视作“一类静态审计”，代码层则保留各引擎自己的执行和存储边界。

### 实时事件为什么重要

智能审计的“过程可见”并不是页面自己拼出来的，而是后端专门维护了一套事件流。

关键实现入口：

- 后端事件管理：`backend/app/services/agent/event_manager.py`
- 前端流式消费：`frontend/src/shared/api/agentStream.ts`

如果你遇到这些问题：

- 为什么页面上能实时刷出 Agent 思考过程？
- 为什么工具调用能逐条展示？
- 为什么任务结束后还能回看完整过程？

答案基本都在这条链路里。

---

## 请求怎么流动

### 从创建项目到可扫描项目

创建项目的入口主要在：

- 后端：`backend/app/api/v1/endpoints/projects.py`
- 前端：`frontend/src/shared/api/database.ts`

如果项目来自 ZIP：

1. 前端创建 `Project`
2. 后端保存项目元数据
3. 压缩包进入上传存储
4. 后续文件树、文件内容、静态审计、智能审计都基于这份归档

所以“项目上传”不是附属功能，而是后续扫描能力成立的前提。

### 静态审计怎么创建

前端入口：`frontend/src/components/scan/CreateProjectScanDialog.tsx`

创建静态审计时，前端会按勾选的引擎分别调用静态接口，例如：

- Opengrep
- Gitleaks
- Bandit
- PHPStan
- YASA

后端总入口在：

- `backend/app/api/v1/endpoints/static_tasks.py`

你可以把这个文件理解成静态审计的“总装配层”：

- 对外提供统一前缀
- 对内把请求分发到各引擎实现

### 智能审计怎么创建

前端入口仍然是：`frontend/src/components/scan/CreateProjectScanDialog.tsx`

当模式是“智能审计”时，前端会直接创建一个 `AgentTask`。

后端主执行入口是：

- `backend/app/api/v1/endpoints/agent_tasks_execution.py`

这里会完成：

1. 准备项目根目录
2. 校验 LLM 配置
3. 初始化工具、沙箱和运行时
4. 启动 Agent 工作流
5. 持续写入事件和发现

### 智能审计创建后的关键入口

当前产品只暴露单一的智能审计创建入口，因此创建后的定位重点是：

- 前端创建逻辑：`frontend/src/components/scan/CreateProjectScanDialog.tsx`
- 后端执行入口：`backend/app/api/v1/endpoints/agent_tasks_execution.py`

如果你是在排查历史兼容字段、旧种子注入链路或 Python 旧 runtime 的迁移细节，再回到 `plan/rust_full_takeover/` 和相关归档文档。

### 结果如何回到前端

前端结果展示主要分两类：

#### 静态审计结果

- 页面：`/static-analysis/:taskId`
- 聚合逻辑：`frontend/src/features/tasks/services/taskActivities.ts`

#### 智能审计结果

- 页面：`/agent-audit/:taskId`
- 契约：`frontend/src/shared/api/agentTasks.ts`
- 实时流：`frontend/src/shared/api/agentStream.ts`

你可以把它理解成：

- 静态审计更偏“任务结果列表”
- 智能审计更偏“任务执行过程 + 结果回放”

---

## 代码从哪里读

### 后端先看这几个入口

如果你刚接手后端，不要一开始就扎进大量 services。建议按这个顺序读：

#### 1. `backend/app/main.py`

先看系统怎么启动。  
它会告诉你这个服务除了起 FastAPI 之外，还依赖哪些运行期假设，比如：

- 数据库迁移检查
- 默认初始化
- 中断任务恢复
- Docker / Redis / Agent 环境检查

#### 2. `backend/app/api/v1/api.py`

再看后端暴露了哪些主业务域。  
这一步的作用不是记接口，而是建立系统边界感。

#### 3. `backend/app/api/v1/endpoints/projects.py`

再看项目聚合入口。  
因为这个项目里，大多数能力最终都落回 `Project`。

#### 4. `backend/app/api/v1/endpoints/static_tasks.py`

如果你关心静态审计，从这里切入。  
它能帮助你快速理解静态引擎是如何被统一组织起来的。

#### 5. `backend/app/api/v1/endpoints/agent_tasks_execution.py`

如果你关心智能审计，从这里切入。
它是任务真正执行起来的地方。

#### 6. `backend/app/api/v1/endpoints/agent_tasks_bootstrap.py`

如果你要追历史兼容或旧种子注入链路，从这里切入。
这类代码主要用于理解迁移背景，而不是当前产品模式。

### 前端先看这几个入口

如果你刚接手前端，建议按这个顺序读：

#### 1. `frontend/src/app/routes.tsx`

先搞清楚系统有哪些页面，以及它们在产品上的分组方式。

#### 2. `frontend/src/components/scan/CreateProjectScanDialog.tsx`

这是最值得优先阅读的前端入口。  
它把静态审计与智能审计如何映射到后端能力，讲得最直白。

#### 3. `frontend/src/pages/ProjectDetail.tsx`

如果你想理解“为什么项目页能把不同结果汇总在一起”，看这里。

#### 4. `frontend/src/shared/api/agentTasks.ts`

如果你想理解智能审计的前后端契约，看这里。

#### 5. `frontend/src/features/tasks/services/taskActivities.ts`

如果你想理解前端是怎么把多种任务统一成一个产品视图的，看这里。

这层很关键，因为它体现的是“产品视角下的聚合口径”，而不只是后端原始结构。

---

## 常见开发任务怎么定位

### 如果你要改扫描创建入口

优先看：

- `frontend/src/components/scan/CreateProjectScanDialog.tsx`

这是两种扫描模式的统一入口。
大多数“为什么创建逻辑不一样”的问题，都是从这里开始。

### 如果你要改智能审计创建或初始种子行为

优先看：

- `frontend/src/components/scan/CreateProjectScanDialog.tsx`
- `backend/app/api/v1/endpoints/agent_tasks_execution.py`

原因很简单：

- 前端决定任务如何创建
- execution 决定任务如何真正运行

如果你需要追历史兼容链路，再补读 `backend/app/api/v1/endpoints/agent_tasks_bootstrap.py` 和迁移文档。

### 如果你要改智能审计运行过程

优先看：

- `backend/app/api/v1/endpoints/agent_tasks_execution.py`
- `backend/app/services/agent/agents/`
- `backend/app/services/agent/workflow/`
- `backend/app/services/agent/tools/`

如果你只改页面展示，不必立刻深入所有 Agent 实现；先看事件和契约通常更快。

### 如果你要改 Agent 实时流

优先看：

- `backend/app/services/agent/event_manager.py`
- `frontend/src/shared/api/agentStream.ts`

一个管事件生产和广播，一个管事件消费和重连，基本就是完整链路。

### 如果你要改静态审计聚合展示

优先看：

- `frontend/src/features/tasks/services/taskActivities.ts`
- `frontend/src/pages/TaskManagementStatic.tsx`
- `frontend/src/pages/StaticAnalysis.tsx`

原因是静态审计在后端是多引擎并列，在前端才被聚合成统一体验。

### 如果你要新增或修改静态引擎

优先看：

- `backend/app/api/v1/endpoints/static_tasks.py`
- 对应的 `backend/app/api/v1/endpoints/static_tasks_<engine>.py`
- 对应的 `backend/app/models/<engine>.py`
- 对应的 `frontend/src/shared/api/<engine>.ts`

这条路径基本就是一条完整的“从后端执行到前端接入”的链路。

---

## 一组最值得记住的代码锚点

如果你只想保留最少但最有用的定位点，记住下面这些就够了：

- 后端启动入口：`backend/app/main.py`
- 后端 API 总入口：`backend/app/api/v1/api.py`
- 智能审计执行入口：`backend/app/api/v1/endpoints/agent_tasks_execution.py`
- 历史兼容 / 种子注入入口：`backend/app/api/v1/endpoints/agent_tasks_bootstrap.py`
- 静态审计聚合入口：`backend/app/api/v1/endpoints/static_tasks.py`
- 前端扫描创建入口：`frontend/src/components/scan/CreateProjectScanDialog.tsx`
- 前端任务聚合入口：`frontend/src/features/tasks/services/taskActivities.ts`

这几个文件合起来，基本就能覆盖你第一次接手项目时最常见的理解路径。

## 继续阅读

- 想继续看智能审计主线：读 [agentic_scan_core/workflow_overview.md](./agentic_scan_core/workflow_overview.md)。
- 想继续看智能体职责和工具边界：读 [agentic_scan_core/agent_tools.md](./agentic_scan_core/agent_tools.md)。
- 想统一术语理解：回看 [glossary.md](./glossary.md)。

---

## 附录：已退役链路说明

旧的早期审计链路已经从运行时代码中移除：

- `AuditTask` / `AuditIssue`
- `/api/v1/tasks/*`
- `/api/v1/scan/*`

当前系统只保留两类有效扫描模式：

- 静态审计
- 智能审计

如果你在迁移历史、基线 schema 快照或专项清理文档里看到旧名称，把它们视为历史记录，而不是可继续接入的主流程。

---
