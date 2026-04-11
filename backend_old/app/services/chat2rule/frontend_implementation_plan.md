# Chat2Rule Frontend 实现规划

> 这份文档是 `docs/chat2rule/implementation_plan.md` 的前端补充版，专门回答“现有 React 前端应该怎么落 Chat2Rule”。

## 1. 先说结论

前端最合理的落地方式不是把 Chat2Rule 塞进全局规则页，而是新增一个项目内页面：

- 路由建议：`/projects/:id/chat2rule`

它应该复用现有 `ProjectCodeBrowser` 的文件树、搜索、代码预览能力，再在右侧增加：

- 会话消息区
- 规则草案区
- 校验 / 发布动作区

但要注意一个关键事实：

**当前前端最大的缺口不是“聊天 UI”，而是“代码预览组件没有行范围选择能力”。**

所以前端实施顺序应该是：

1. 先把代码预览升级为“可选择代码行”
2. 再搭 Chat2Rule 页面骨架
3. 再接会话 API
4. 最后再补流式体验和高级编辑

## 2. 现有前端可复用的部分

### 2.1 页面与路由

可以直接复用的入口与模式：

- `frontend/src/app/routes.tsx`
- `frontend/src/pages/ProjectDetail.tsx`
- `frontend/src/pages/ProjectCodeBrowser.tsx`

现状说明：

- `ProjectDetail` 已经是项目级聚合页，适合加 CTA。
- `ProjectCodeBrowser` 已经是完整的“项目代码浏览”页面。
- `ProjectCodeBrowserWorkspace` 已经导出，后续可以被新页面复用。

### 2.2 文件树 / 搜索 / 文件内容读取

现有代码浏览链路已经很完整：

- `frontend/src/shared/api/database.ts`
  - `getProjectFiles(...)`
  - `getProjectFileContent(...)`
- `frontend/src/pages/project-code-browser/model.ts`
  - 文件树构建
  - 文件/内容搜索
  - 预览装饰
- `frontend/src/pages/ProjectCodeBrowser.tsx`
  - 页面状态编排

这意味着前端不需要重新发明：

- 文件树
- 代码搜索
- 文件预览
- ZIP 根目录剥离逻辑

### 2.3 代码展示组件

可复用核心组件：

- `frontend/src/pages/AgentAudit/components/FindingCodeWindow.tsx`

优点：

- 已支持语法高亮
- 已支持 focus/highlight line
- 已支持 project-browser 展示模式

缺点：

- 只能展示，不能选择
- 没有行点击、拖拽、shift 选区、区间标记
- 没有“已选片段 overlay”

这会是 Chat2Rule 前端的第一处必要改造。

### 2.4 流式 hook 模式

仓里已经有两套轻量流式实现，可直接借鉴：

- `frontend/src/pages/agent-test/useAgentTestStream.ts`
- `frontend/src/pages/skill-test/useSkillTestStream.ts`

Chat2Rule 不需要一开始就接入复杂的 `AgentStream`；首版完全可以参考这两套：

- `fetch + ReadableStream + TextDecoder`
- 前端自己解析 SSE chunk
- 消息事件累积到本地 state

### 2.5 布局基础设施

仓里已存在：

- `frontend/src/components/ui/resizable.tsx`

这非常适合 Chat2Rule 的三栏或四栏布局，前端不需要新造 splitter。

### 2.6 规则编辑习惯

规则编辑页已有成熟交互，可参考：

- `frontend/src/pages/OpengrepRules.tsx`

特别适合复用的点：

- YAML 文本编辑区
- 规则详情/编辑对话框
- 校验失败时的错误提示习惯

## 3. 当前前端缺口

从落地角度看，前端现在缺 5 块能力：

1. 项目代码中的“多段代码选择”
2. Chat2Rule 专用页面与状态模型
3. Chat2Rule API client
4. 会话消息 + 规则草案联动展示
5. 从项目页 / 代码浏览页进入 Chat2Rule 的路径

其中第 1 点是关键前置项。

## 4. 推荐的页面信息架构

## 4.1 页面入口

建议增加两个入口：

### 入口 A：项目详情页 CTA

在 `ProjectDetail.tsx` 顶部按钮区增加：

- `代码生成规则`

行为：

- 跳转到 `/projects/:id/chat2rule`

适合用户：

- 先想进入创作工作台，再去找代码

### 入口 B：代码浏览页 CTA

在 `ProjectCodeBrowser.tsx` 顶部增加：

- `发起 Chat2Rule`
- `将当前选择加入会话`

适合用户：

- 已经在看代码，想直接开始圈选

## 4.2 推荐路由

建议新增：

- `frontend/src/pages/ProjectChat2Rule.tsx`
- `frontend/src/app/routes.tsx` 中新增路由：
  - `/projects/:id/chat2rule`

`sessionId` 不建议放 path param 的第一版实现里，优先放 search param：

- `/projects/:id/chat2rule?session=<sessionId>`

原因：

- 改动更小
- 与现有 `ProjectCodeBrowser` 的返回逻辑更容易兼容
- 深链仍然成立

## 4.3 页面布局

桌面端推荐四块区域：

1. 左侧 rail：模式切换 / 新建会话 / 会话列表
2. 左中：文件树 / 文件搜索
3. 中间：代码预览 + 选择交互
4. 右侧：聊天区 + 规则草案区

推荐用法：

- 外层 `ResizablePanelGroup horizontal`
- 右侧再嵌套一层 `ResizablePanelGroup vertical`

也就是：

- 左列：文件导航
- 中列：代码区
- 右列上半：消息流
- 右列下半：规则草案

移动端 / 窄屏建议退化为：

1. 顶部会话信息
2. 代码区
3. 聊天区
4. 草案区

首版不要强求移动端支持复杂拖拽，移动端只支持“点起点 + 点终点”即可。

## 5. 推荐的前端组件拆分

建议新增目录：

- `frontend/src/pages/chat2rule/`

推荐结构：

- `ProjectChat2Rule.tsx`
  - 页面容器
- `components/Chat2RuleSessionRail.tsx`
  - 会话列表、新建会话、会话标题
- `components/Chat2RuleCodePanel.tsx`
  - 代码预览上层容器，持有选择交互
- `components/Chat2RuleSelectionBar.tsx`
  - 已选片段列表、清空、删除、重新排序
- `components/Chat2RuleComposer.tsx`
  - 输入框、发送、停止、附带当前选择摘要
- `components/Chat2RuleMessageList.tsx`
  - 对话消息展示
- `components/Chat2RuleArtifactPanel.tsx`
  - 规则草案、校验状态、发布动作
- `components/Chat2RuleArtifactEditor.tsx`
  - YAML 文本编辑与手动修正
- `components/Chat2RuleValidationBadge.tsx`
  - valid/invalid/pending 状态展示
- `state.ts`
  - reducer、state types
- `selectors.ts`
  - 视图层派生数据

## 6. 代码选择交互的实现建议

## 6.1 为什么优先改选择能力

当前 `FindingCodeWindow` 只能做：

- 行号显示
- 高亮区间显示
- focus line 自动滚动

但 Chat2Rule 需要的是：

- 用户主动选行
- 多段范围保存
- 当前拖拽中的临时范围可视化
- 已保存范围可删除/复用

所以第一步要扩展 `FindingCodeWindow`。

## 6.2 推荐的组件改造方式

不建议另写一个平行的代码渲染器。  
更合适的是在 `FindingCodeWindow` 上增加“可选模式”。

建议新增 props：

```ts
interface FindingCodeWindowSelectionRange {
  id: string;
  startLine: number;
  endLine: number;
  tone?: "primary" | "muted";
}

interface FindingCodeWindowSelectionConfig {
  enabled: boolean;
  ranges: FindingCodeWindowSelectionRange[];
  draftRange?: { startLine: number; endLine: number } | null;
  onLinePointerDown?: (lineNumber: number) => void;
  onLinePointerEnter?: (lineNumber: number) => void;
  onLinePointerUp?: (lineNumber: number) => void;
  onLineClick?: (lineNumber: number, event: MouseEvent) => void;
}
```

实现建议：

- 不改基础高亮逻辑
- 只在每一行外层 `<div>` 增加 pointer handlers
- 将“已选范围”和“临时范围”都映射成额外背景 class
- gutter 区域和 code 区域都支持点击

## 6.3 推荐的选择交互

桌面端：

- 单击一行：选中单行
- `Shift + Click`：从锚点扩展到当前行
- 鼠标按下拖拽：形成临时范围
- `Cmd/Ctrl + Click`：向已有选择追加新范围

移动端：

- 第一次点击设起点
- 第二次点击设终点
- 再点一次“加入片段”

## 6.4 前端选择状态模型

建议在页面级 reducer 中维护：

```ts
type Chat2RuleLineRange = {
  id: string;
  filePath: string;
  startLine: number;
  endLine: number;
  source: "manual" | "search_jump";
};

type DraftSelection = {
  filePath: string;
  anchorLine: number;
  currentLine: number;
} | null;
```

关键原则：

- 多文件范围允许并存
- 同文件重叠范围先在前端 merge，减小 UI 噪音
- 最终仍以服务端 normalization 为准

## 6.5 已选片段条带

代码区上方建议增加 `Chat2RuleSelectionBar`：

- 展示每个片段的 `file_path:start-end`
- 支持删除单个片段
- 支持“仅保留当前文件片段”
- 支持“清空全部”
- 支持“跳转到该片段”

这里不需要一开始就支持拖拽排序，首版按加入顺序展示即可。

## 7. 推荐的页面状态管理方式

## 7.1 不建议直接上全局 store

首版不建议引入新的 Zustand store。  
更稳妥的是：

- `ProjectChat2Rule.tsx` 用 `useReducer`
- 本页局部状态全部收敛到 reducer

原因：

- 状态强依赖单个项目与当前会话
- 逻辑复杂但作用域局部
- 后续若真的跨页共享，再抽 store

## 7.2 页面级 state 建议

```ts
interface Chat2RulePageState {
  project: Project | null;
  files: ProjectCodeBrowserFileEntry[];
  tree: ProjectCodeBrowserTreeNode[];
  selectedFilePath: string | null;
  fileStates: Record<string, ProjectCodeBrowserFileViewState>;
  browserMode: "files" | "search";
  searchQuery: string;
  includeFileQuery: string;
  excludeFileQuery: string;
  previewDecorations: Record<string, ProjectCodeBrowserPreviewDecoration | undefined>;

  sessionList: Chat2RuleSessionSummary[];
  activeSessionId: string | null;
  messages: Chat2RuleMessage[];
  latestArtifact: Chat2RuleArtifact | null;

  selections: Chat2RuleLineRange[];
  draftSelection: DraftSelection;

  composerText: string;
  sending: boolean;
  validating: boolean;
  publishing: boolean;
}
```

## 7.3 应拆成 hook 的部分

为了避免 `ProjectChat2Rule.tsx` 变成巨型文件，建议拆两个 hook：

- `useProjectCodeBrowserState(projectId)`
  - 复用 `ProjectCodeBrowser` 当前的文件加载、搜索、预览逻辑
- `useChat2RuleSession(projectId, sessionId)`
  - 负责会话列表、消息、artifact、发送动作

这一步也有利于后续让 `ProjectCodeBrowser.tsx` 和 `ProjectChat2Rule.tsx` 共享逻辑，而不是复制一份。

## 8. 推荐的 API client 设计

建议新增：

- `frontend/src/shared/api/chat2rule.ts`

### 8.1 类型建议

```ts
export interface Chat2RuleSelectionPayload {
  file_path: string;
  start_line: number;
  end_line: number;
}

export interface Chat2RuleSessionSummary {
  id: string;
  project_id: string;
  engine_type: "opengrep" | "codeql";
  title: string;
  status: "active" | "completed" | "archived" | "failed";
  updated_at: string;
}

export interface Chat2RuleMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
}

export interface Chat2RuleArtifact {
  id: string;
  engine_type: "opengrep" | "codeql";
  version: number;
  title: string;
  rule_text: string;
  explanation?: string | null;
  validation_status: "pending" | "valid" | "invalid" | "unsupported";
  validation_result?: Record<string, unknown> | null;
  publish_status: "draft" | "published" | "rejected";
}
```

### 8.2 方法建议

- `listChat2RuleSessions(projectId)`
- `createChat2RuleSession(projectId, payload)`
- `getChat2RuleSession(projectId, sessionId)`
- `sendChat2RuleMessage(projectId, sessionId, payload)`
- `streamChat2RuleMessage(projectId, sessionId, payload)`
- `validateChat2RuleArtifact(projectId, artifactId)`
- `publishChat2RuleArtifact(projectId, artifactId)`

## 9. 聊天区与草案区如何实现

## 9.1 聊天区

聊天区不需要做成通用 IM，重点是“面向规则创作”的消息流。

推荐内容：

- 用户消息气泡
- 助手消息气泡
- 每条助手消息可折叠“生成说明”
- 若本轮生成了 artifact，消息尾部显示：
  - `已生成 Opengrep 草案 v3`

交互上建议：

- 输入框默认保留当前文本
- 发送时把当前 selections 摘要展示在 composer 上方
- 若无任何 selection，仍允许发送，但按钮给出弱提示

## 9.2 草案区

草案区建议拆成 3 个区块：

1. 顶部元信息
   - 引擎
   - 版本号
   - 校验状态
   - 发布时间
2. 中部 YAML 编辑器
   - `Textarea` 即可，首版不强求 Monaco
3. 底部动作区
   - 重新校验
   - 覆盖保存
   - 发布规则
   - 可选 smoke scan

首版不要上 Monaco 的理由：

- 仓里没有现成 Monaco 集成
- `Textarea + monospace + 高度可拖` 已足够验证流程
- 复杂度更低

## 9.3 校验反馈展示

建议把校验结果拆成两层：

- Badge：`通过 / 未通过 / 待校验`
- Detail Panel：展示错误详情或规范化结果

例如：

- YAML 语法错误
- 缺少 `rules`
- `languages` 不合法
- 规则被 normalize 后的最终版本

## 10. 流式实现建议

## 10.1 MVP 建议先做同步

MVP 可以先只做：

- `POST /messages`
- 返回完整 assistant message + artifact

因为用户的核心痛点是“能不能生成规则”，不是“能不能逐 token 看生成过程”。

## 10.2 Phase 2 再接 stream

若后端增加 `/messages/stream`，建议新增：

- `frontend/src/pages/chat2rule/useChat2RuleStream.ts`

直接参考：

- `useSkillTestStream.ts`
- `useAgentTestStream.ts`

事件建议：

- `assistant_delta`
- `artifact_created`
- `artifact_updated`
- `validation_started`
- `validation_finished`
- `done`
- `error`

前端行为：

- assistant delta 逐步拼消息
- artifact 更新时覆盖当前草案
- validation 完成后刷新 badge

## 11. 与现有页面的集成建议

## 11.1 ProjectDetail 集成

建议在 `ProjectDetail.tsx` 头部按钮区增加：

- `代码浏览`
- `Chat2Rule`

如果只想先加一个按钮，优先加：

- `Chat2Rule`

并在页面内提示：

- 仅 ZIP 项目支持

## 11.2 ProjectCodeBrowser 集成

建议新增一个轻量入口：

- 顶部按钮：`进入 Chat2Rule`

可附带当前文件路径作为 search param：

- `/projects/:id/chat2rule?file=src/auth.py`

如果当前已有 selections：

- 可额外附带 `from=code-browser`
- 真正的 selection 内容不要放 URL，交由页面 state 或 session storage

## 11.3 返回路径

建议沿用当前项目页/代码页已有的 `location.state.from` 习惯。

Chat2Rule 页面进入来源建议保留：

- `from=/projects/:id`
- `from=/projects/:id/code-browser`

这样返回行为会更自然。

## 12. 推荐的实现顺序

## Phase A：基础重构

1. 抽出 `useProjectCodeBrowserState(projectId)`
2. 让 `ProjectCodeBrowser.tsx` 改为复用该 hook
3. 给 `FindingCodeWindow` 增加 selection props
4. 补选择能力的测试

## Phase B：页面骨架

1. 新增 `ProjectChat2Rule.tsx`
2. 新增路由
3. 接入文件树、搜索、预览
4. 右侧先用假数据渲染消息区和草案区

## Phase C：会话接线

1. 新增 `shared/api/chat2rule.ts`
2. 接入创建 session / 获取 session / 发送消息
3. 接入 artifact 展示
4. 接入 validate / publish 动作

## Phase D：体验增强

1. 会话列表
2. 选择条带
3. 从代码浏览页一键跳转
4. 流式生成
5. 错误态与空态优化

## 13. 建议修改/新增的前端文件

### 必改

- `frontend/src/app/routes.tsx`
- `frontend/src/pages/ProjectDetail.tsx`
- `frontend/src/pages/ProjectCodeBrowser.tsx`
- `frontend/src/pages/AgentAudit/components/FindingCodeWindow.tsx`
- `frontend/src/pages/project-code-browser/model.ts`
- `frontend/src/shared/api/database.ts`

### 建议新增

- `frontend/src/pages/ProjectChat2Rule.tsx`
- `frontend/src/pages/chat2rule/state.ts`
- `frontend/src/pages/chat2rule/selectors.ts`
- `frontend/src/pages/chat2rule/useChat2RuleSession.ts`
- `frontend/src/pages/chat2rule/useChat2RuleSelection.ts`
- `frontend/src/pages/chat2rule/components/Chat2RuleSessionRail.tsx`
- `frontend/src/pages/chat2rule/components/Chat2RuleCodePanel.tsx`
- `frontend/src/pages/chat2rule/components/Chat2RuleSelectionBar.tsx`
- `frontend/src/pages/chat2rule/components/Chat2RuleComposer.tsx`
- `frontend/src/pages/chat2rule/components/Chat2RuleMessageList.tsx`
- `frontend/src/pages/chat2rule/components/Chat2RuleArtifactPanel.tsx`
- `frontend/src/pages/chat2rule/components/Chat2RuleArtifactEditor.tsx`
- `frontend/src/shared/api/chat2rule.ts`

## 14. 测试计划

仓里已有前端 node 测试体系和大量 `.test.ts/.test.tsx`，所以 Chat2Rule 前端应直接补到 `frontend/tests/`。

### 14.1 建议先补的测试

- `frontend/tests/chat2ruleSelectionReducer.test.ts`
  - 合并、删除、清空 ranges
- `frontend/tests/findingCodeWindowSelection.test.tsx`
  - 点击/拖拽/shift 选区
- `frontend/tests/projectChat2RulePage.test.tsx`
  - ZIP 项目正常展示工作台
- `frontend/tests/chat2ruleApi.test.ts`
  - API contract
- `frontend/tests/chat2ruleArtifactPanel.test.tsx`
  - valid/invalid/published 状态显示

### 14.2 关键回归测试

- `ProjectCodeBrowser` 现有浏览功能不能被 selection 改坏
- 搜索结果跳转高亮仍然正常
- `FindingCodeWindow` 在非交互场景下表现不变

## 15. 前端落地时最容易踩的坑

### 坑 1：把 Chat2Rule 做成一个完全平行的新代码浏览器

不建议。  
这样会复制：

- 文件树逻辑
- 搜索逻辑
- 文件读取逻辑
- 代码预览逻辑

正确方向是复用 `ProjectCodeBrowser` 的状态和模型。

### 坑 2：先做聊天区，后补选择能力

不建议。  
因为这样前端只能临时用“手输文件名 + 行号”的假交互，后面还得推翻。

### 坑 3：一开始就上 Monaco

不建议。  
Chat2Rule 的关键难点不是 YAML 编辑器，而是代码选择与会话编排。

### 坑 4：首版就强依赖流式

不建议。  
先打通同步闭环更稳。

## 16. 推荐的首个前端里程碑

第一阶段最小可交付建议是：

1. 新路由 `/projects/:id/chat2rule`
2. 复用现有代码浏览数据加载
3. 代码区支持选择单段/多段行范围
4. 右侧有基础聊天输入框
5. 调后端 mock / 真接口返回 1 个 artifact
6. 草案区显示 YAML 和校验状态

只要这条链跑通，后面的会话列表、流式输出、规则发布优化都可以按增量方式加上去。
