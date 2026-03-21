# AuditTool / VulHunter 开发者架构指南

> 这份文档不是接口清单，也不是目录罗列。它的目标只有一个：让第一次接手这个项目的开发者，能在最短时间内看懂系统主线，并知道应该从哪里开始读代码。

## 先看懂系统

### 这个系统是什么

AuditTool 是一个面向代码仓库安全扫描的平台。仓库名叫 `AuditTool`，代码和历史文档里仍大量保留 `VulHunter` 这个名字，两者指向的是同一个系统。

从实现上看，它是一个标准的前后端分离应用：

- 前端：React + Vite 单页应用
- 后端：FastAPI 单体服务
- 数据层：PostgreSQL
- 运行期辅助能力：Redis、Docker sandbox、LLM、可选 RAG

如果只记一句话，可以这样理解它：

**它是一个以 `Project` 为中心，把三类扫描任务统一组织起来的安全扫描工作台。**

### 先记住三类扫描任务

当前产品视角下，系统只有三类主任务：

#### 1. 静态扫描

静态扫描是多引擎任务的统一产品视图。  
它负责快速给出规则命中、密钥泄露、语言级静态分析结果。

当前静态引擎包括：

- Opengrep
- Gitleaks
- Bandit
- PHPStan
- YASA

这些引擎在后端是多套并列任务模型，但在前端会被聚合成一类“静态扫描”体验。

#### 2. 智能扫描

智能扫描由 `AgentTask` 主导。  
它不是简单跑一遍规则，而是让 Agent 做文件侦察、漏洞分析、验证和报告生成。

如果你看到：

- `AgentTask`
- `AgentEvent`
- `AgentFinding`
- SSE 实时流

它们基本都属于智能扫描主链路。

#### 3. 混合扫描

混合扫描本质上仍然是 `AgentTask` 主导的智能扫描。  
它和普通智能扫描的区别只有一个：

**它会先把静态扫描结果作为漏洞入口点侦查输入，再交给 Agent 做后续分析和验证。**

也就是说，混合扫描不是一套独立的第四种任务模型，而是：

**智能扫描主流程 + 静态 bootstrap 结果注入**

---

## 核心运行模型

### `Project` 是整个系统的中心

后端模型入口：`backend/app/models/project.py`

系统里几乎所有能力都围绕 `Project` 展开。你可以把它理解成“一个待扫描代码仓库的工作空间”。

`Project` 负责承接：

- 项目来源信息：远程仓库或 ZIP 包
- 项目成员与归属
- 代码文件与压缩包归档
- 三类扫描任务
- 项目级统计与结果聚合

所以你在定位任何功能时，都可以先问自己一句：

**这个功能是不是挂在某个项目之下？**

大多数时候答案都是“是”。

### 智能扫描的核心对象

如果你要理解智能扫描，只需要先看四个对象：

- `AgentTask`
  - 一次智能扫描或混合扫描任务
- `AgentEvent`
  - 任务运行过程中的实时事件
- `AgentFinding`
  - Agent 最终沉淀的漏洞发现
- `AgentTreeNode`
  - Agent 树与子 Agent 关系

它们定义在：`backend/app/models/agent_task.py`

这套模型解释了为什么智能扫描页面不仅能展示结果，还能展示：

- 当前阶段
- 实时日志
- 工具调用
- 验证状态
- 报告内容

### 静态扫描的核心对象

静态扫描不是一个总模型，而是多套引擎模型并列存在。

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

产品层把它们视作“一类静态扫描”，代码层则保留各引擎自己的执行和存储边界。

### 实时事件为什么重要

智能扫描的“过程可见”并不是页面自己拼出来的，而是后端专门维护了一套事件流。

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
4. 后续文件树、文件内容、静态扫描、混合扫描都基于这份归档

所以“项目上传”不是附属功能，而是后续扫描能力成立的前提。

### 静态扫描怎么创建

前端入口：`frontend/src/components/scan/CreateProjectScanDialog.tsx`

创建静态扫描时，前端会按勾选的引擎分别调用静态接口，例如：

- Opengrep
- Gitleaks
- Bandit
- PHPStan
- YASA

后端总入口在：

- `backend/app/api/v1/endpoints/static_tasks.py`

你可以把这个文件理解成静态扫描的“总装配层”：

- 对外提供统一前缀
- 对内把请求分发到各引擎实现

### 智能扫描怎么创建

前端入口仍然是：`frontend/src/components/scan/CreateProjectScanDialog.tsx`

当模式是“智能扫描”时，前端会创建一个 `AgentTask`，并关闭静态 bootstrap。

后端主执行入口是：

- `backend/app/api/v1/endpoints/agent_tasks_execution.py`

这里会完成：

1. 准备项目根目录
2. 校验 LLM 配置
3. 初始化工具、沙箱和运行时
4. 启动 Agent 工作流
5. 持续写入事件和发现

### 混合扫描怎么创建

混合扫描最值得注意的地方，是它的后端模型并没有变。

前端仍然创建 `AgentTask`，但会把：

- `audit_scope.static_bootstrap.mode = embedded`

写入任务配置。

相关入口：

- 前端创建逻辑：`frontend/src/components/scan/CreateProjectScanDialog.tsx`
- 后端 bootstrap 逻辑：`backend/app/api/v1/endpoints/agent_tasks_bootstrap.py`

这条链路的真实含义是：

1. 先从静态引擎收集候选漏洞入口点
2. 把这些候选结果喂给 Agent
3. 再由 Agent 继续做分析、验证和报告

如果你要改“混合扫描为什么和智能扫描行为不同”，优先看这里，而不是先去看静态任务页面。

### 结果如何回到前端

前端结果展示主要分两类：

#### 静态扫描结果

- 页面：`/static-analysis/:taskId`
- 聚合逻辑：`frontend/src/features/tasks/services/taskActivities.ts`

#### 智能/混合扫描结果

- 页面：`/agent-audit/:taskId`
- 契约：`frontend/src/shared/api/agentTasks.ts`
- 实时流：`frontend/src/shared/api/agentStream.ts`

你可以把它理解成：

- 静态扫描更偏“任务结果列表”
- 智能/混合扫描更偏“任务执行过程 + 结果回放”

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

如果你关心静态扫描，从这里切入。  
它能帮助你快速理解静态引擎是如何被统一组织起来的。

#### 5. `backend/app/api/v1/endpoints/agent_tasks_execution.py`

如果你关心智能扫描或混合扫描，从这里切入。  
它是任务真正执行起来的地方。

#### 6. `backend/app/api/v1/endpoints/agent_tasks_bootstrap.py`

如果你关心混合扫描和智能扫描的差异，从这里切入。  
这就是“静态结果如何变成入口点侦查输入”的核心实现。

### 前端先看这几个入口

如果你刚接手前端，建议按这个顺序读：

#### 1. `frontend/src/app/routes.tsx`

先搞清楚系统有哪些页面，以及它们在产品上的分组方式。

#### 2. `frontend/src/components/scan/CreateProjectScanDialog.tsx`

这是最值得优先阅读的前端入口。  
它把静态扫描、智能扫描、混合扫描三种模式如何映射到后端能力，讲得最直白。

#### 3. `frontend/src/pages/ProjectDetail.tsx`

如果你想理解“为什么项目页能把不同结果汇总在一起”，看这里。

#### 4. `frontend/src/shared/api/agentTasks.ts`

如果你想理解智能扫描的前后端契约，看这里。

#### 5. `frontend/src/features/tasks/services/taskActivities.ts`

如果你想理解前端是怎么把多种任务统一成一个产品视图的，看这里。

这层很关键，因为它体现的是“产品视角下的聚合口径”，而不只是后端原始结构。

---

## 常见开发任务怎么定位

### 如果你要改扫描创建入口

优先看：

- `frontend/src/components/scan/CreateProjectScanDialog.tsx`

这是三种扫描模式的统一入口。  
大多数“为什么创建逻辑不一样”的问题，都是从这里开始。

### 如果你要改混合扫描行为

优先看：

- `frontend/src/components/scan/CreateProjectScanDialog.tsx`
- `backend/app/api/v1/endpoints/agent_tasks_bootstrap.py`
- `backend/app/api/v1/endpoints/agent_tasks_execution.py`

原因很简单：

- 前端决定任务以什么模式创建
- bootstrap 决定静态结果如何注入
- execution 决定任务如何真正运行

### 如果你要改智能扫描运行过程

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

### 如果你要改静态扫描聚合展示

优先看：

- `frontend/src/features/tasks/services/taskActivities.ts`
- `frontend/src/pages/TaskManagementStatic.tsx`
- `frontend/src/pages/StaticAnalysis.tsx`

原因是静态扫描在后端是多引擎并列，在前端才被聚合成统一体验。

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
- 智能扫描执行入口：`backend/app/api/v1/endpoints/agent_tasks_execution.py`
- 混合扫描 bootstrap 入口：`backend/app/api/v1/endpoints/agent_tasks_bootstrap.py`
- 静态扫描聚合入口：`backend/app/api/v1/endpoints/static_tasks.py`
- 前端扫描创建入口：`frontend/src/components/scan/CreateProjectScanDialog.tsx`
- 前端任务聚合入口：`frontend/src/features/tasks/services/taskActivities.ts`

这几个文件合起来，基本就能覆盖你第一次接手项目时最常见的理解路径。

---

## 附录：已退役链路说明

旧的早期审计链路已经从运行时代码中移除：

- `AuditTask` / `AuditIssue`
- `/api/v1/tasks/*`
- `/api/v1/scan/*`

当前系统只保留三类有效扫描模式：

- 静态扫描
- 智能扫描
- 混合扫描

如果你在迁移历史、基线 schema 快照或专项清理文档里看到旧名称，把它们视为历史记录，而不是可继续接入的主流程。

---
