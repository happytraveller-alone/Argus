# Chat2Rule 实现规划

## 1. 目标与结论

目标场景是：用户在某个 `Project` 中圈定一段或几段代码，和大模型多轮对话，让系统产出一个可以直接保存、验证、复用的规则草案，例如 Opengrep 规则，后续再扩展到 CodeQL。

基于 [architecture.md](../architecture.md) 和代码现状，我的核心结论是：

1. 这个功能应该建在 `Project` 之下，而不是单独挂在全局规则页。
2. 它不适合直接复用 `AgentTask` 主链路，因为它的核心对象不是 finding，而是“会话 + 规则草案 + 校验结果 + 发布动作”。
3. 它也不适合直接复用 `AuditRuleSet/AuditRule`，因为那套模型更像 LLM 审计提示词，不是可执行引擎规则。
4. 首版应优先落地 `Opengrep`，同时把引擎抽象设计好；`CodeQL` 先保留接口层抽象，不建议在 MVP 里硬落，因为仓内目前还没有真正落地的 `CodeQL` model/API/runtime。

## 2. 现有架构里可复用的部分

### 2.1 可以直接复用

- `Project` 中心模型已经成立，适合作为 Chat2Rule 的挂载点。
- `projects_files.py` 已经能提供项目文件树和文件内容读取。
- `ProjectCodeBrowser.tsx` 已经有代码浏览、搜索、预览能力，是最自然的前端入口。
- `LLMService` 已经同时支持普通 completion 和 stream completion。
- `static_tasks_opengrep_rules.py` 已经有：
  - Opengrep YAML 校验
  - 规则创建/编辑/上传
  - `validate_generic_rule(...)`
- `OpengrepRule` 表已经能保存真正可执行的 Opengrep 规则。

### 2.2 当前明显缺口

- `projects_files.py` 当前实际上只支持 `source_type == "zip"` 的项目文件读取；仓库型项目还没有统一文件读取链路。
- 当前没有“项目内多轮会话 + 规则草案版本 + 草案发布”的数据模型。
- 当前没有“用户圈选片段”到后端的标准协议。
- 当前没有“规则草案”和“正式规则”分离的生命周期。
- 当前没有真实可用的 `CodeQL` 后端实现，只有部署规划文档 [codeql_platform_deploy.md](../security/codeql_platform_deploy.md)。

## 3. 产品与架构定位

### 3.1 推荐定位

我建议把 Chat2Rule 定位成：

`Project` 下的一条“规则创作工作流”，而不是扫描任务、也不是全局规则库页面的附属按钮。

它的核心闭环应该是：

1. 用户进入项目代码浏览页面。
2. 选择一个或多个代码片段。
3. 发起会话并描述要检测的风险模式。
4. LLM 生成规则草案和解释。
5. 后端立即做引擎级校验。
6. 用户继续追问或修正规则。
7. 用户确认后再“发布”为正式规则。
8. 可选地立即对当前项目做一次 smoke scan。

### 3.2 为什么不直接复用 `AgentTask`

`AgentTask` 适合“长时扫描执行 + SSE 过程流 + finding 持久化”，而 Chat2Rule 更像“短会话规则创作器”。两者虽然都调用 LLM，但对象完全不同：

- `AgentTask` 的产物是 finding/report。
- Chat2Rule 的产物是 draft/published rule。

如果直接复用 `AgentTask`，会导致：

- 事件模型过重
- finding 语义不匹配
- 草案版本和发布动作无处安放

更合适的方式是单独建一条轻量链路，必要时只复用 `LLMService`、SSE 和规则校验能力。

## 4. MVP 范围建议

### 4.1 MVP 必做

- 仅支持 `zip` 项目
- 仅支持 `Opengrep` 规则生成与验证
- 支持多段代码圈选
- 支持多轮对话
- 每轮都返回“自然语言解释 + 规则草案 + 校验结果”
- 支持将草案发布到 `OpengrepRule`
- 支持从项目页进入工作流

### 4.2 MVP 不做

- 不在首版做 CodeQL 真正执行
- 不把 Chat2Rule 混入 `AgentTask`
- 不自动把每一轮草案都写入正式规则库
- 不在首版做跨项目共享会话

## 5. 推荐的数据模型

为了控制复杂度，首版建议增加 3 张表，而不是把选择片段也拆成单独表。

### 5.1 `chat2rule_sessions`

建议字段：

- `id`
- `project_id`
- `created_by`
- `engine_type`
  - `opengrep | codeql`
- `status`
  - `active | completed | archived | failed`
- `title`
- `goal`
- `current_selection_snapshot`
  - JSON，保存当前圈选的 canonical ranges
- `latest_artifact_id`
- `created_at`
- `updated_at`

### 5.2 `chat2rule_messages`

建议字段：

- `id`
- `session_id`
- `role`
  - `user | assistant | system`
- `content`
- `selection_snapshot`
  - JSON，保留每轮输入快照，便于复现
- `llm_usage`
  - JSON
- `error_message`
- `created_at`

### 5.3 `chat2rule_artifacts`

建议字段：

- `id`
- `session_id`
- `message_id`
- `engine_type`
- `version`
- `title`
- `rule_text`
- `normalized_rule_text`
- `explanation`
- `assumptions`
  - JSON
- `limitations`
  - JSON
- `validation_status`
  - `pending | valid | invalid | unsupported`
- `validation_result`
  - JSON
- `publish_status`
  - `draft | published | rejected`
- `published_rule_ref`
  - 先用于 `OpengrepRule.id`
- `created_at`

### 5.4 为什么不单独建 selection 表

首版更重要的是“每轮输入可复现”，而不是“按 file_path 查所有选择历史”。  
所以更建议把 selection 快照存在 `session/message` 上，确保：

- 对话回放稳定
- 草案对应的输入快照稳定
- migration 成本更低

如果后面要做“片段复用/推荐/统计”，再把 selection 单独拆表也不晚。

## 6. 后端设计

### 6.1 新服务分层

建议新增目录：

- `backend/app/services/chat2rule/`

推荐拆分：

- `context.py`
  - 选择片段规范化、锚点格式化、预算裁剪
- `content_service.py`
  - 从项目中拿文件内容和上下文窗口
- `prompting.py`
  - 组装 system/user prompt
- `engines/base.py`
  - 引擎适配器接口
- `engines/opengrep.py`
  - Opengrep 专用校验/发布逻辑
- `service.py`
  - 会话主流程

### 6.2 引擎适配器接口

推荐抽象一个 `RuleEngineAdapter`：

- `engine_type`
- `build_system_prompt(...)`
- `normalize_llm_artifact(...)`
- `validate_artifact(...)`
- `publish_artifact(...)`
- `build_smoke_test_request(...)`

首版只实现：

- `OpengrepChat2RuleAdapter`

它直接复用：

- `validate_generic_rule(...)`
- `OpengrepRule`
- 现有 `/static-tasks/rules/*` 的校验语义

`CodeQLChat2RuleAdapter` 先只保留接口或 feature flag，不做真正执行。

### 6.3 选择片段处理原则

后端不能直接信任前端传来的“片段文本”，只能信任：

- `file_path`
- `start_line`
- `end_line`

正确流程应是：

1. 前端提交选择范围。
2. 后端规范化 ranges。
3. 后端重新读取项目文件内容。
4. 后端生成 canonical snippet bundle：
   - `file_path`
   - `start_line`
   - `end_line`
   - `selected_text`
   - `before_context`
   - `after_context`
   - `content_hash`
   - `language`
5. 再把 bundle 喂给 LLM。

这样做的好处：

- 防止前端伪造代码内容
- 减少重复片段
- 降低 prompt token 浪费
- 后续回放时可复现

本次我补的原型测试已经验证了一个关键点：同文件重叠/相邻 ranges 必须先在服务端合并，否则 prompt 会重复塞上下文。

### 6.4 Prompt 结构建议

推荐让 LLM 返回严格 JSON，而不是自由文本。建议结构：

```json
{
  "assistant_message": "我根据你提供的片段生成了一个 Opengrep 规则草案，当前重点覆盖 shell=True 的命令注入场景。",
  "artifacts": [
    {
      "engine": "opengrep",
      "title": "Python subprocess shell 注入检测",
      "rule_text": "rules:\n  - id: ...",
      "explanation": "该规则匹配 ...",
      "assumptions": ["输入可控", "目标语言为 python"],
      "limitations": ["暂不处理跨函数数据流"]
    }
  ]
}
```

后端流程：

1. 发送严格 JSON 提示词
2. 解析响应
3. 用 adapter 做 normalize
4. 做引擎级 validation
5. 把 assistant message 和 artifact 分开持久化

### 6.5 API 设计

建议新增前缀：

- `/api/v1/projects/{project_id}/chat2rule/...`

建议接口：

1. `POST /sessions`
   - 创建会话
   - 接收首批 selection 和目标 engine

2. `GET /sessions`
   - 列出项目下会话

3. `GET /sessions/{session_id}`
   - 返回会话、消息、最新 artifact

4. `POST /sessions/{session_id}/messages`
   - 提交一轮用户消息
   - 同时允许更新 selection snapshot
   - 返回 assistant message + artifact + validation

5. `POST /sessions/{session_id}/messages/stream`
   - 可选，后续复用 `LLMService.chat_completion_stream`

6. `POST /artifacts/{artifact_id}/validate`
   - 手动重新校验

7. `POST /artifacts/{artifact_id}/publish`
   - 发布到 `OpengrepRule`

8. `POST /artifacts/{artifact_id}/smoke-scan`
   - 可选，对当前项目选中文件做快速验证

### 6.6 请求示例

```json
{
  "engine_type": "opengrep",
  "goal": "我想检测 Flask 场景里用户输入最终进入 subprocess.run(shell=True) 的模式",
  "selections": [
    {
      "file_path": "app/routes.py",
      "start_line": 42,
      "end_line": 66
    },
    {
      "file_path": "app/utils/command.py",
      "start_line": 8,
      "end_line": 22
    }
  ]
}
```

### 6.7 发布策略

重要原则：

- 草案 != 正式规则
- 只有发布动作才写入 `OpengrepRule`

发布时：

1. 重新做一次 validation
2. 写入 `OpengrepRule`
3. `source` 建议新增 `chat2rule`
   - 如果暂时不改 enum 语义，也可先复用 `upload`
4. 在 artifact 上记录 `published_rule_ref`

## 7. 前端设计

### 7.1 推荐入口

最合适的入口不是全局规则页，而是：

- `ProjectCodeBrowser.tsx`

原因：

- 用户天然在这里选代码
- 已有树、搜索、代码预览能力
- 不需要先做一次“跳转到另一个完全陌生页面再找代码”

### 7.2 推荐页面结构

建议新增页面：

- `frontend/src/pages/ProjectChat2Rule.tsx`

推荐三区布局：

1. 左侧：项目文件树/已选片段列表
2. 中间：聊天区
3. 右侧：规则草案与校验结果

入口方式：

- 在 `ProjectCodeBrowser` 增加“加入 Chat2Rule”按钮
- 或在项目详情页增加“代码选段生成规则” CTA，跳到 `/projects/:id/chat2rule`

### 7.3 前端状态建议

建议新增：

- `frontend/src/shared/api/chat2rule.ts`
- `frontend/src/pages/chat2rule/*`
- 可选 store：`chat2ruleStore.ts`

前端最关键的状态：

- 当前项目
- 当前 session
- 当前 selection ranges
- message list
- latest artifact
- validation status
- publish status

### 7.4 代码选择交互建议

不要要求用户手输行号。推荐交互：

- 在代码 gutter 支持拖拽/点击起止行
- 支持“添加到当前会话”
- 支持跨文件添加多个片段
- 片段列表支持删除和重新排序

首版可以先做：

- 单文件行范围选择
- 多文件片段累积

后面再做更高级的：

- 函数级一键选中
- 从 finding 反向导入片段

## 8. 推荐实现步骤

### Phase 0：地基

1. 新建 `chat2rule` backend package
2. 抽出 selection normalization/context bundling
3. 先补单元测试

### Phase 1：后端 MVP

1. 增加 SQLAlchemy models
2. 增加 migration
3. 增加 schemas
4. 增加 `projects/{id}/chat2rule` routes
5. 实现 `OpengrepChat2RuleAdapter`
6. 接入 `LLMService.chat_completion_raw`

### Phase 2：前端 MVP

1. 增加新路由 `/projects/:id/chat2rule`
2. 从 `ProjectCodeBrowser` 进入
3. 实现代码片段选择状态
4. 实现聊天消息发送
5. 实现右侧规则草案预览
6. 实现“重新校验 / 发布规则”

### Phase 3：联调与验证

1. mock LLM 联调
2. 发布到 `OpengrepRule`
3. 快速扫描验证
4. 错误态与空态补齐

### Phase 4：增强

1. 支持流式返回
2. 支持 artifact version diff
3. 支持从历史 rule 召回 few-shot 示例
4. 统一引擎抽象，给 CodeQL 预留接入口

## 9. 需要修改/新增的文件建议

### 后端

- `backend/app/models/chat2rule.py`
- `backend/app/schemas/chat2rule.py`
- `backend/app/api/v1/endpoints/projects_chat2rule.py`
- `backend/app/api/v1/endpoints/projects.py`
- `backend/app/api/v1/api.py`
- `backend/app/services/chat2rule/context.py`
- `backend/app/services/chat2rule/content_service.py`
- `backend/app/services/chat2rule/prompting.py`
- `backend/app/services/chat2rule/service.py`
- `backend/app/services/chat2rule/engines/base.py`
- `backend/app/services/chat2rule/engines/opengrep.py`
- `backend/alembic/versions/*_add_chat2rule_tables.py`

### 前端

- `frontend/src/app/routes.tsx`
- `frontend/src/pages/ProjectCodeBrowser.tsx`
- `frontend/src/pages/ProjectChat2Rule.tsx`
- `frontend/src/pages/chat2rule/components/*`
- `frontend/src/shared/api/chat2rule.ts`

## 10. 测试策略

### 10.1 单元测试

- selection normalization
- context bundle 构建
- prompt parser
- Opengrep adapter validation
- publish 行为

### 10.2 API 测试

- 创建 session
- 多轮消息往返
- 非法路径拒绝
- 无 LLM 配置时返回可读错误
- validation 失败不允许发布

### 10.3 前端测试

- 多片段选择状态
- 切换文件后 selection 保持
- artifact 展示与重新校验动作

### 10.4 E2E

建议补一条最小闭环：

1. 上传 zip 项目
2. 打开 chat2rule
3. 选中一段 Python 代码
4. mock LLM 返回 Opengrep 规则
5. 校验成功
6. 发布到 `OpengrepRule`

## 11. 风险与对应决策

### 风险 1：仓库型项目当前拿不到统一文件内容

建议决策：

- MVP 只开放给 `zip` 项目
- UI 上明确提示
- 后续抽象统一 `ProjectContentService`

### 风险 2：LLM 生成的规则会污染正式规则库

建议决策：

- 草案与正式规则强分离
- 只有 publish 才落 `OpengrepRule`

### 风险 3：多段代码会迅速吃掉 token

建议决策：

- 服务端先做 range merge
- 每段只附带有限上下文窗口
- 对历史消息做摘要，不无限回放全文

### 风险 4：CodeQL 目标容易导致范围失控

建议决策：

- 首版只做 Opengrep 真落地
- CodeQL 只保留 adapter 抽象和 feature flag

## 12. 推荐的首个落地里程碑

我建议第一阶段只做下面这条最短闭环：

1. `zip` 项目
2. `ProjectCodeBrowser` 里选择 1~N 段代码
3. 创建一个 `Opengrep` 类型 Chat2Rule session
4. 发 1 轮消息
5. 后端返回 1 个规则草案
6. 立即调用 `validate_generic_rule`
7. 用户点击“发布”
8. 写入 `OpengrepRule`

只要这条链能跑通，后面的 SSE、历史召回、CodeQL、规则 diff 都是增量能力。
