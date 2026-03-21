# DeerFlow Runtime 能力吸收调研报告

一句话结论：当前仓库应继续保留 `WorkflowOrchestrator + AuditWorkflowEngine + 队列权威模型` 作为审计内核，只选择性吸收 DeerFlow 在 runtime 层的 4 类能力，不建议走全量替换。

## 摘要

| 能力 | 结论 | 原因 |
| --- | --- | --- |
| `sub-agent` 隔离上下文 | 条件吸收 | 值得吸收的是“隔离执行壳 + 工具白名单 + 并发批次控制”，不应把审计主流程交回给 lead-agent 自由编排。 |
| `checkpointer` | 条件吸收 | DeerFlow 的重点是统一线程态恢复；当前仓库已有 checkpoint，但仍偏 `AgentState` 快照。 |
| `summarization / tool-error middleware` | 优先吸收 | 与当前仓库最兼容，几乎可以在不动审计主流程的前提下 runtime 化。 |
| `skills` 渐进加载 | 优先吸收（基础版） | 当前仓库已经有 `scan_core + agent-tools docs + skills.md snapshot` 雏形，缺的是正式 catalog、按需发现、按需注入。 |

## 0. 调研方法与证据边界

### 0.1 DeerFlow 拉取信息

| 项目 | 结果 |
| --- | --- |
| 仓库地址 | `https://github.com/bytedance/deer-flow` |
| 拉取时间 | `2026-03-21T16:08:24+08:00` |
| 分析分支 | `main` |
| commit hash | `9dbcca579dff84eaafac8d2629097e5f9bd739a2` |
| HEAD 提交信息 | `2026-03-21T10:37:32+08:00 docs: add Japanese README (#1209)` |
| 本地只读分析目录 | `/tmp/deer-flow-codex-eOQznp` |

### 0.2 调研对象

- DeerFlow 仅分析 4 个能力：`sub-agent` 隔离上下文、`checkpointer`、`summarization / tool-error middleware`、`skills` 渐进加载。
- AuditTool 对照范围固定为：`workflow`、`agent core`、`memory`、`MCP/runtime`、`skills/docs`。
- 代码摘录遵循“最小闭环”原则，只保留接口定义、关键控制流、状态结构、中间件注册、核心 guard，不粘贴大段样板代码。

### 0.3 README 表述与源码事实

| 主题 | README 表述 | 源码事实 | 判断 |
| --- | --- | --- | --- |
| Skills 渐进加载 | `README_zh.md:337-343` 说“只有任务确实需要时才加载” | `skills/loader.py:22-98` 实际会先扫描 `public/custom` 下所有 `SKILL.md` 元数据；真正按需的是技能正文读取与 deferred tool schema 暴露 | README 讲的是“内容层渐进加载”，不是“零成本发现” |
| Sub-agent 独立上下文 | `README_zh.md:395-419` 说每个 sub-agent 有独立上下文、工具、终止条件 | `subagents/executor.py:164-201` 使用独立 `ThreadState` 和过滤后的工具，但仍会继承父级 `sandbox_state / thread_data / model` | “独立”成立，但更准确地说是“逻辑线程态隔离”，不是完全独立运行时 |

### 0.4 证据边界

- 本文只基于官方仓库 `main` 分支源码与当前 AuditTool 工作区源码。
- 本轮不 vendor DeerFlow 源码，不讨论 UI、Gateway、外部部署拓扑。
- 报告的目标是给后续架构改造提供可直接落地的设计输入，而不是做“能不能跑起来”的泛泛介绍。

## 1. 当前项目基线

当前仓库本质上不是通用 agent shell，而是“带 LLM 的审计执行系统”。核心特征有四个：

1. 调度内核是确定性的。`backend/app/services/agent/workflow/workflow_orchestrator.py:97-154` 会优先走 `AuditWorkflowEngine`，而 `backend/app/services/agent/workflow/engine.py:1-158` 明确把 `Recon -> Analysis -> Verification -> Report` 固化为队列权威的审计流程。
2. 记忆已经项目化。`backend/app/services/agent/memory/markdown_memory.py:16-23` 把 `shared / orchestrator / recon / analysis / verification / skills` 拆成固定 Markdown 文件；`load_bundle()` 只把摘要片段注入 prompt，说明仓库已经具备“上下文压缩 + 长期沉淀”的基本形态。
3. runtime 已带强约束。`backend/app/services/agent/mcp/write_scope.py:32-220` 用证据绑定、项目内路径归一化、目录级写入禁止和可写文件数上限约束工具写入；这决定了 DeerFlow 的通用工具 runtime 不能直接照搬。
4. `skills` 已有雏形但还不是 runtime。`backend/app/services/agent/skills/scan_core.py:6-162` 已有静态 skill catalog；`backend/docs/agent-tools/SKILLS_INDEX.md:1-13` 和 `skills.md` snapshot 也在持续沉淀，但它们更像 prompt 资料库，不是 DeerFlow 那种“catalog + progressive loading + deferred tool discovery”运行时。

基于这四点，结论不是“当前架构缺 agent 能力”，而是“已有能力散落在 workflow、base agent、memory、MCP runtime 里，还没抽象成清晰的 runtime 组件”。

## 2. 能力一：Sub-Agent 隔离上下文

本节结论：可以吸收 DeerFlow 的“隔离上下文执行壳、工具 allow/deny list、并发批次控制”，但不能把审计主流程改成 lead-agent 自由拆解式 orchestration。

### 2.1 DeerFlow 用 prompt 把 lead agent 约束成“分批并发 delegator”

来源：`deer-flow: backend/packages/harness/deerflow/agents/lead_agent/prompt.py:7-37,81-91`

```python
def _build_subagent_section(max_concurrent: int) -> str:
    n = max_concurrent
    return f"""<subagent_system>
    ...
    **⛔ HARD CONCURRENCY LIMIT: MAXIMUM {n} `task` CALLS PER RESPONSE.**
    - Each response, you may include **at most {n}** `task` tool calls.
    - If count > {n}: **Pick the {n} most important ... for this turn.**
    - Turn 1: Launch sub-tasks 1-{n} in parallel -> wait for results
    - Turn 2: Launch next batch in parallel -> wait for results
    ...
    **CRITICAL WORKFLOW**:
    1. COUNT
    2. PLAN BATCHES
    3. EXECUTE
    4. REPEAT
    5. SYNTHESIZE
    </subagent_system>"""
```

#### 这段代码做了什么

它不是在实现 sub-agent，而是在 prompt 层把 lead agent 训练成一个“并发批次受限的 delegator”。DeerFlow 的设计假设是：复杂任务优先拆成多个平行子任务，再由 lead agent 汇总；并发上限不是软建议，而是 prompt 明说的硬约束。

#### 对当前仓库意味着什么

AuditTool 当前的主流程不是“自由拆解任务”，而是 `WorkflowOrchestrator + AuditWorkflowEngine` 的确定性阶段推进。也就是说，DeerFlow 这里最有价值的不是“让大模型决定流程”，而是“把并发批次控制、子任务切分规则、禁止滥用 sub-agent 的条件”写成显式 runtime policy。

#### 建议如何吸收

- 保留当前 `Recon -> Analysis -> Verification` 的固定阶段顺序。
- 仅在阶段内部引入 `sub-agent batch policy`，例如让 `analysis` 或 `verification` 子任务在同一阶段内按风险点并行。
- 把“每轮最多发起多少个子任务、哪些场景禁止再拆”从 prompt 经验规则提升为配置化 runtime 限制。

### 2.2 DeerFlow 的 `task` 工具把委派变成独立执行路径，并显式阻止递归 task

来源：`deer-flow: backend/packages/harness/deerflow/tools/builtins/task_tool.py:60-118`

```python
config = get_subagent_config(subagent_type)

skills_section = get_skills_prompt_section()
if skills_section:
    overrides["system_prompt"] = config.system_prompt + "\n\n" + skills_section

if runtime is not None:
    sandbox_state = runtime.state.get("sandbox")
    thread_data = runtime.state.get("thread_data")
    thread_id = runtime.context.get("thread_id")
    metadata = runtime.config.get("metadata", {})
    parent_model = metadata.get("model_name")

from deerflow.tools import get_available_tools

tools = get_available_tools(model_name=parent_model, subagent_enabled=False)

executor = SubagentExecutor(
    config=config,
    tools=tools,
    parent_model=parent_model,
    sandbox_state=sandbox_state,
    thread_data=thread_data,
    thread_id=thread_id,
    trace_id=trace_id,
)
task_id = executor.execute_async(prompt, task_id=tool_call_id)
```

#### 这段代码做了什么

`task_tool` 做了三件关键事：

1. 从父 runtime 提取必要的共享上下文，比如 sandbox、thread data、model、trace。
2. 用 `subagent_enabled=False` 重新拿一份工具集，显式阻止子 agent 再拿到 `task` 工具形成递归。
3. 不把子任务当普通函数调用，而是交给 `SubagentExecutor` 走独立执行链路。

#### 对当前仓库意味着什么

AuditTool 的子 Agent 更像“动态创建一个代理然后立即跑”，但缺少统一的“隔离执行壳”。这意味着当前系统能做子任务分工，却没有 DeerFlow 这种标准化的 delegated runtime：什么上下文能继承、什么工具能继承、是否允许递归再派生、trace 如何传递，很多逻辑仍然分散。

#### 建议如何吸收

- 在当前仓库新增统一的 `IsolatedSubAgentRuntime`，把“从父上下文抽取哪些字段”收敛成固定接口。
- 默认禁止 sub-agent 持有 `create_sub_agent` 或任何可再次派发 worker 的工具，除非显式白名单。
- 保留当前 trace / task_id 传播，但把“上下文继承”从自由 `dict` 透传改成结构化 `handoff payload`。

### 2.3 DeerFlow 用工具过滤、独立 `ThreadState` 和 denylist 把 sub-agent 变成标准执行壳

来源：

- `deer-flow: backend/packages/harness/deerflow/subagents/executor.py:78-105,155-201`
- `deer-flow: backend/packages/harness/deerflow/subagents/builtins/general_purpose.py:43-46`

```python
def _filter_tools(all_tools, allowed, disallowed):
    filtered = all_tools
    if allowed is not None:
        filtered = [t for t in filtered if t.name in set(allowed)]
    if disallowed is not None:
        filtered = [t for t in filtered if t.name not in set(disallowed)]
    return filtered

self.tools = _filter_tools(tools, config.tools, config.disallowed_tools)

middlewares = build_subagent_runtime_middlewares(lazy_init=True)
return create_agent(
    model=model,
    tools=self.tools,
    middleware=middlewares,
    system_prompt=self.config.system_prompt,
    state_schema=ThreadState,
)

state = {"messages": [HumanMessage(content=task)]}
if self.sandbox_state is not None:
    state["sandbox"] = self.sandbox_state
if self.thread_data is not None:
    state["thread_data"] = self.thread_data

GENERAL_PURPOSE_CONFIG = SubagentConfig(
    tools=None,
    disallowed_tools=["task", "ask_clarification", "present_files"],
    model="inherit",
    max_turns=50,
)
```

#### 这段代码做了什么

这里把“隔离执行壳”补全了：

- 工具层：支持 allowlist 和 denylist。
- 状态层：sub-agent 自己的 `ThreadState` 从一条新的 `HumanMessage(task)` 开始，不复用父消息历史。
- 运行时层：复用共享 middleware，但不复用父 agent 的整段上下文。
- 行为层：通过 denylist 禁止递归 `task`、禁止澄清、禁止某些展示型工具。

#### 对当前仓库意味着什么

这正是 AuditTool 当前缺的部分。现在仓库里有“子 agent 的业务分工”，但没有标准化“子线程执行壳”。`ExecutionContext.child_context()` 更偏 trace 派生，`CreateSubAgentTool` 更偏动态创建/执行，而不是 DeerFlow 这种明确隔离消息历史、工具集、终止条件的子线程模型。

#### 建议如何吸收

- 给每个子 agent 增加独立的短历史缓存，不默认继承父对话记录。
- 用角色级工具白名单替代“全部工具继承再局部禁用”的策略。
- 为 `analysis`、`verification`、`report` 等 phase 预定义不同的 `SubAgentConfig`，而不是统一靠 prompt 控制。

### 2.4 AuditTool 当前更像“编排对象 + 上下文透传”，还不是标准化隔离子线程

来源：

- `AuditTool: backend/app/services/agent/workflow/workflow_orchestrator.py:97-147`
- `AuditTool: backend/app/services/agent/core/context.py:124-149`
- `AuditTool: backend/app/services/agent/tools/agent_tools.py:174-188`

```python
# workflow_orchestrator.py
if self._recon_queue_service is None or self._vuln_queue_service is None:
    return await super().run(input_data)

engine = AuditWorkflowEngine(
    recon_queue_service=self._recon_queue_service,
    vuln_queue_service=self._vuln_queue_service,
    task_id=task_id,
    orchestrator=self,
)

# context.py
def child_context(self, agent_id: str, agent_name: str) -> "ExecutionContext":
    return ExecutionContext(
        correlation_id=self.correlation_id,
        task_id=self.task_id,
        parent_agent_id=self.current_agent_id,
        current_agent_id=agent_id,
        current_agent_name=agent_name,
        trace_path=[*self.trace_path, agent_name],
        depth=self.depth + 1,
        metadata=self.metadata.copy(),
    )

# agent_tools.py
if execute_immediately:
    exec_context = context or {}
    exec_context["knowledge_modules"] = modules
    exec_result = await executor.create_and_run_sub_agent(
        agent_type=agent_type if agent_type in ["analysis", "verification"] else "analysis",
        task=task.strip(),
        context=exec_context,
        knowledge_modules=modules,
    )
```

#### 这段代码做了什么

AuditTool 当前对子 agent 的定位是：在确定性 workflow 下，按阶段调起不同代理；上下文通过 `ExecutionContext` 和自由 `context` 字典向下传递；子 agent 的执行本质上是“创建后运行”。

#### 对当前仓库意味着什么

这说明仓库已经有 sub-agent 编排能力，但它主要服务“审计阶段分工”，不是“通用隔离子线程执行”。因此 DeerFlow 可吸收的是 runtime 壳层，而不是把整个 orchestrator 心智切换成通用多 agent OS。

#### 建议如何吸收

- 在 `workflow` 保持权威的前提下，为阶段内子任务增加标准化 `spawn_isolated_subagent()` 接口。
- 让 `ExecutionContext.child_context()` 继续负责 trace，但另起一层 `SubAgentThreadState` 负责消息、summary、tool counters。
- 审计主流程仍由队列和 workflow 驱动，不允许 lead-agent 自由改变阶段顺序、跳过入队漏洞或自定义审计终态。

### 2.5 小结

- 可直接吸收：隔离上下文、工具白名单、并发批次控制、禁止递归 task。
- 不应直接照搬：lead-agent 自由编排主审计流程。
- 最合适的落点：作为 `analysis / verification / report` 阶段内部的“隔离 worker runtime”，而不是新的顶层 orchestrator。

### 2.6 源码索引

- `deer-flow: backend/packages/harness/deerflow/agents/lead_agent/agent.py:248-253`
- `deer-flow: backend/packages/harness/deerflow/README_zh.md:391-419`
- `AuditTool: backend/app/services/agent/workflow/engine.py:31-158`

## 3. 能力二：Checkpointer

本节结论：当前仓库并不是“没有 checkpoint”，问题在于 checkpoint 还主要服务 `AgentState` 恢复，尚未统一建模 thread 级状态、对话摘要、标题、待办与 runtime 计数器。

### 3.1 DeerFlow 先把 checkpointer 视为统一线程态后端，再用配置决定持久化介质

来源：

- `deer-flow: backend/packages/harness/deerflow/config/checkpointer_config.py:7-46`
- `deer-flow: config.example.yaml:403-434`

```python
CheckpointerType = Literal["memory", "sqlite", "postgres"]

class CheckpointerConfig(BaseModel):
    type: CheckpointerType = Field(...)
    connection_string: str | None = Field(default=None, ...)

_checkpointer_config: CheckpointerConfig | None = None

def load_checkpointer_config_from_dict(config_dict: dict) -> None:
    global _checkpointer_config
    _checkpointer_config = CheckpointerConfig(**config_dict)
```

```yaml
# Configure state persistence for the embedded DeerFlowClient.
# ... enabling multi-turn conversations to persist across process restarts.
checkpointer:
  type: sqlite
  connection_string: checkpoints.db

# postgres:
#   type: postgres
#   connection_string: postgresql://user:password@localhost:5432/deerflow
```

#### 这段代码做了什么

DeerFlow 的 checkpointer 首先是“统一状态持久化接口”，其次才是 `memory/sqlite/postgres` 的后端切换。配置上没有绑定任何业务对象，绑定的是线程态持久化机制。

#### 对当前仓库意味着什么

AuditTool 现在的 checkpoint 配置也不少，但更多是在控制“多久存一次 agent state”。DeerFlow 这里提醒我们：真正值得吸收的不是存储介质，而是“线程态是否有统一恢复模型”。

#### 建议如何吸收

- 引入 `ThreadCheckpointEnvelope` 概念，把 `messages/summary/title/todos/tool loop counters/runtime context refs` 打成一个统一对象。
- 存储后端可以继续复用现有文件或数据库，不必先追求 PostgreSQL 化。
- `memory/sqlite/postgres` 的选择可以后置，先统一状态模型。

### 3.2 DeerFlow 在 `create_agent` 时直接注入 checkpointer，使其成为 agent runtime 的一等公民

来源：`deer-flow: backend/packages/harness/deerflow/client.py:184-220`

```python
kwargs = {
    "model": create_chat_model(...),
    "tools": self._get_tools(...),
    "middleware": _build_middlewares(config, model_name=model_name),
    "system_prompt": apply_prompt_template(...),
    "state_schema": ThreadState,
}
checkpointer = self._checkpointer
if checkpointer is None:
    from deerflow.agents.checkpointer import get_checkpointer
    checkpointer = get_checkpointer()
if checkpointer is not None:
    kwargs["checkpointer"] = checkpointer

self._agent = create_agent(**kwargs)
```

#### 这段代码做了什么

这里的关键信号是：checkpointer 不是外围工具，而是 `create_agent()` 的组成部分。换句话说，agent 的状态机天生就是“可恢复”的。

#### 对当前仓库意味着什么

AuditTool 现在的持久化更多发生在 agent 运行过程中或阶段完成后；而 DeerFlow 的方式更接近“把恢复能力嵌进 runtime”。这对长链路审计尤其重要，因为它允许 UI thread、交互 thread 和运行 thread 共享同一个恢复语义。

#### 建议如何吸收

- 在 BaseAgent 或统一 runtime builder 层引入 `thread_checkpoint_manager`，而不是让各类 agent 自己决定怎么存。
- 让 checkpoint 对消息历史、标题、摘要、todos、loop counters 负责；让审计领域状态继续由队列和 workflow 负责。
- 恢复时优先恢复 thread runtime，再附着到已有 `WorkflowState / queue snapshot`。

### 3.3 AuditTool 已有 checkpoint，但仍主要围绕 `AgentState` 快照

来源：

- `AuditTool: backend/app/services/agent/core/persistence.py:24-129,233-315`
- `AuditTool: backend/app/services/agent/config.py:218-238`

```python
class AgentStatePersistence:
    def save_state(self, state: AgentState, checkpoint_name: Optional[str] = None) -> str:
        state_dict = self._serialize_state(state)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, ensure_ascii=False, indent=2)

    def load_latest_checkpoint(self, agent_id: str) -> Optional[AgentState]:
        pattern = f"{agent_id}_*.json"
        checkpoints = list(self.persist_dir.glob(pattern))
        latest = max(checkpoints, key=lambda p: p.stat().st_mtime)
        return self.load_state(str(latest))

    async def save_state_to_db(self, state: AgentState, task_id: str) -> bool:
        checkpoint = AgentCheckpoint(
            task_id=task_id,
            agent_id=state.agent_id,
            agent_name=state.agent_name,
            state_data=state.model_dump_json(),
            iteration=state.iteration,
            status=state.status,
        )
```

```python
checkpoint_enabled: bool = Field(default=True)
checkpoint_interval_iterations: int = Field(default=5)
checkpoint_on_tool_complete: bool = Field(default=False)
checkpoint_on_phase_complete: bool = Field(default=True)
max_checkpoints_per_task: int = Field(default=50)
```

#### 这段代码做了什么

当前仓库已经有文件和数据库两类 checkpoint，支持自动间隔保存、按 phase 保存、按 task/agent 查询，能力并不弱。

#### 对当前仓库意味着什么

缺口不在“能不能保存”，而在“保存的中心对象是谁”。当前中心对象是 `AgentState`，而不是 DeerFlow/LangGraph 那种统一线程态。结果就是：agent 可以恢复，但一条会话的标题、摘要、待办、中间 runtime 决策是否统一恢复，还不够明确。

#### 建议如何吸收

- 保留现有 `AgentStatePersistence`，把它下沉为 `thread checkpoint` 的一个字段或子对象。
- 新增 thread 级 envelope，统一保存 `agent state refs + messages summary + tool runtime meta + todo/title`。
- 不要让统一 checkpoint 替代 `WorkflowState` 或队列数据库；审计队列仍然是领域真相源。

### 3.4 小结

- DeerFlow 的启发点不是“SQLite/Postgres 支持”，而是“线程态统一可恢复”。
- 当前仓库已经具备 checkpoint 基础设施，改造成本主要在状态模型统一，而不是持久化技术栈替换。
- 推荐路线是：保留审计特有 state 与队列权威模型，只在交互 runtime 层吸收 LangGraph 风格的线程态持久化思路。

### 3.5 源码索引

- `deer-flow: backend/packages/harness/deerflow/agents/thread_state.py`
- `AuditTool: backend/app/services/agent/workflow/models.py`
- `AuditTool: backend/app/services/agent/workflow/engine.py`

## 4. 能力三：Summarization / Tool-Error Middleware

本节结论：这是 4 项里最适合优先吸收的一项。当前仓库已经有摘要压缩、重试短路、写保护、工具异常回填，但它们大多散落在 `BaseAgent` 和 MCP/runtime 中，不够清晰、可插拔、可验证。

### 4.1 DeerFlow 把摘要压缩做成可配置 middleware，而不是 BaseAgent 内部 helper

来源：

- `deer-flow: backend/packages/harness/deerflow/config/summarization_config.py:21-74`
- `deer-flow: backend/packages/harness/deerflow/agents/lead_agent/agent.py:40-79`

```python
class SummarizationConfig(BaseModel):
    enabled: bool = Field(default=False)
    model_name: str | None = Field(default=None)
    trigger: ContextSize | list[ContextSize] | None = Field(default=None)
    keep: ContextSize = Field(default_factory=lambda: ContextSize(type="messages", value=20))
    trim_tokens_to_summarize: int | None = Field(default=4000)
    summary_prompt: str | None = Field(default=None)
```

```python
def _create_summarization_middleware() -> SummarizationMiddleware | None:
    config = get_summarization_config()
    if not config.enabled:
        return None

    kwargs = {"model": model, "trigger": trigger, "keep": keep}
    if config.trim_tokens_to_summarize is not None:
        kwargs["trim_tokens_to_summarize"] = config.trim_tokens_to_summarize
    if config.summary_prompt is not None:
        kwargs["summary_prompt"] = config.summary_prompt
    return SummarizationMiddleware(**kwargs)
```

#### 这段代码做了什么

DeerFlow 把“什么时候压缩、保留多少历史、用什么模型压缩、压缩 prompt 是什么”都做成配置，而不是写死在 agent 实现里。这让 summarization 变成真正的 runtime 组件。

#### 对当前仓库意味着什么

AuditTool 现在已经会做上下文压缩，但它主要表现为 `BaseAgent.compress_messages_if_needed()` 这样的调用点。功能上已经接近，差的是可组合性和统一插拔点。

#### 建议如何吸收

- 新建 `ConversationSummarizationMiddleware`，把触发阈值、保留窗口、摘要模板从 `BaseAgent` 中抽出来。
- 摘要结果必须携带审计对象标识，例如 `task_id / finding_id / queue fingerprint`，避免把证据压成不可追溯自然语言。
- 可先只在 orchestrator 和 analysis agent 开启，逐步扩展到 verification/report。

### 4.2 DeerFlow 明确规定 middleware 链顺序，把摘要、工具错误、循环保护、澄清控制放进同一条 runtime pipeline

来源：`deer-flow: backend/packages/harness/deerflow/agents/lead_agent/agent.py:197-259`

```python
# SummarizationMiddleware should be early to reduce context before other processing
# ToolErrorHandlingMiddleware should be before ClarificationMiddleware
def _build_middlewares(config, model_name, agent_name=None):
    middlewares = build_lead_runtime_middlewares(lazy_init=True)

    summarization_middleware = _create_summarization_middleware()
    if summarization_middleware is not None:
        middlewares.append(summarization_middleware)

    middlewares.append(TitleMiddleware())
    middlewares.append(MemoryMiddleware(agent_name=agent_name))

    if app_config.tool_search.enabled:
        middlewares.append(DeferredToolFilterMiddleware())

    if subagent_enabled:
        middlewares.append(SubagentLimitMiddleware(max_concurrent=max_concurrent_subagents))

    middlewares.append(LoopDetectionMiddleware())
    middlewares.append(ClarificationMiddleware())
    return middlewares
```

#### 这段代码做了什么

这里最重要的不是“有哪些 middleware”，而是“顺序是显式的”。DeerFlow 把摘要压缩、title、memory、deferred tool 过滤、subagent 限流、循环检测、澄清拦截串成一个可解释的 pipeline。

#### 对当前仓库意味着什么

AuditTool 当前的 runtime 保护已经不少，但不少逻辑深埋在工具执行路径、MCP 适配路径和 BaseAgent 中，导致行为很强、结构却不够清晰。随着能力增多，这会增加验证成本和回归风险。

#### 建议如何吸收

- 先定义 AuditTool 自己的 middleware 契约，不必照搬 LangGraph 接口。
- 第一批 middleware 建议固定为：`Summarization`、`ToolErrorDowngrade`、`LoopShortCircuit`、`Clarification/Interrupt`、`WriteScopeAuditTrail`。
- 明确 middleware 顺序，尤其是“摘要在前、错误降级在澄清前、循环保护在工具执行之后”的位置关系。

### 4.3 DeerFlow 把工具异常降级为 `ToolMessage`，同时保留控制流异常

来源：`deer-flow: backend/packages/harness/deerflow/agents/middlewares/tool_error_handling_middleware.py:19-112`

```python
class ToolErrorHandlingMiddleware(AgentMiddleware[AgentState]):
    def _build_error_message(self, request, exc: Exception) -> ToolMessage:
        content = (
            f"Error: Tool '{tool_name}' failed with {exc.__class__.__name__}: {detail}. "
            "Continue with available context, or choose an alternative tool."
        )
        return ToolMessage(..., status="error")

    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            return self._build_error_message(request, exc)

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            return self._build_error_message(request, exc)
```

#### 这段代码做了什么

它把“工具失败”从 runtime 级异常，改造成对模型可见、对流程可继续的 `ToolMessage(status="error")`；同时保留 `GraphBubbleUp` 这类控制流信号，不把暂停、恢复、打断误判成普通错误。

#### 对当前仓库意味着什么

这非常适合 AuditTool。当前仓库里，工具失败有的直接回字符串，有的写 event，有的在异常块里拼接 markdown，大量逻辑是“能工作”，但不是统一协定。随着 MCP、RAG、本地工具越来越多，这会逐步变成维护负担。

#### 建议如何吸收

- 引入统一 `ToolFailureEnvelope`，把失败类型、可恢复性、建议下一步、write scope 元数据封装起来。
- 保留 `asyncio.CancelledError`、人工中断、phase 切换等控制流异常，不要被普通错误中间件吞掉。
- 对模型暴露的错误消息要短、结构化、可继续推理，不要直接抛长堆栈。

### 4.4 AuditTool 已有压缩、写保护、失败短路和异常回填，但都散落在 `BaseAgent`

来源：

- `AuditTool: backend/app/services/agent/agents/base.py:1711-1768`
- `AuditTool: backend/app/services/agent/agents/base.py:4341-4408`
- `AuditTool: backend/app/services/agent/agents/base.py:4439-4474`
- `AuditTool: backend/app/services/agent/agents/base.py:5202-5230`

```python
def compress_messages_if_needed(self, messages, max_tokens=None):
    compressor = MemoryCompressor(max_total_tokens=effective_max_tokens)
    if compressor.should_compress(messages):
        compressed = compressor.compress_history(messages)
        return compressed
    return messages

repaired_input, write_scope_metadata, write_scope_error = self._enforce_write_scope(
    resolved_tool_name, repaired_input,
)
if write_scope_error:
    await self.emit_tool_result(..., tool_status="failed", extra_metadata=write_scope_metadata or None)
    return "写入策略校验失败 ..."

if retry_guard_key and deterministic_fail_count >= 2:
    await self.emit_tool_result(..., tool_status="failed", extra_metadata=short_circuit_metadata or None)
    return "工具调用已短路 ..."

except asyncio.CancelledError:
    return "任务已取消"
except Exception as e:
    await self.emit_tool_result(..., tool_status="failed", extra_metadata=...)
    return f"工具执行异常 ... **错误类型**: {type(e).__name__}"
```

#### 这段代码做了什么

当前仓库实际上已经具备 DeerFlow middleware 想解决的大部分问题：

- 会自动压缩历史。
- 会在工具执行前做写入策略校验。
- 会对重复确定性失败短路。
- 会对取消和普通异常分流处理，并把结果回写到事件流。

#### 对当前仓库意味着什么

这说明优先级不在“新增能力”，而在“把已有能力 runtime 化、模块化”。换句话说，AuditTool 已经做出了很多正确的事，只是缺一个统一的 middleware pipeline 来管理它们。

#### 建议如何吸收

- 第一阶段不要大改功能，只做搬运和抽象：把现有 `BaseAgent` 内逻辑抽成 runtime middleware。
- 在抽象时保留 `write_scope_metadata`、`deterministic_failure_count` 等审计特有字段，不要为了“通用”而丢掉安全审计上下文。
- 验收标准应以“行为不变 + 位置可插拔 + 可测试”来定义，而不是“代码看起来更像 DeerFlow”。

### 4.5 小结

- 这是最适合优先吸收的能力。
- 目标不是模仿 DeerFlow 的 LangGraph 接口，而是把当前仓库已有 runtime 保护抽成可组合 middleware。
- 在不改变审计主流程的前提下，完全可以先把“摘要压缩、工具错误降级、循环保护、澄清/中断控制” runtime 化。

### 4.6 源码索引

- `deer-flow: backend/packages/harness/deerflow/agents/middlewares/deferred_tool_filter_middleware.py:1-60`
- `AuditTool: backend/app/services/agent/mcp/runtime.py:748-860`
- `AuditTool: backend/app/services/agent/mcp/write_scope.py:32-220`

## 5. 能力四：Skills 渐进加载

本节结论：DeerFlow 的 skills 不是单纯“把更多文档塞进 prompt”，而是一套“元数据发现 -> 按需读取 skill 主文件 -> 按需加载引用资源 -> 对工具 schema 做 deferred exposure”的组合机制。当前仓库已经有 catalog 和 snapshot，但还缺正式 runtime。

### 5.1 DeerFlow 会先扫描 skill 元数据，并从扩展配置里判定启停

来源：

- `deer-flow: backend/packages/harness/deerflow/skills/loader.py:22-98`
- `deer-flow: backend/packages/harness/deerflow/skills/parser.py:7-65`

```python
def load_skills(skills_path=None, use_config: bool = True, enabled_only: bool = False):
    ...
    for category in ["public", "custom"]:
        for current_root, dir_names, file_names in os.walk(category_path):
            if "SKILL.md" not in file_names:
                continue
            skill_file = Path(current_root) / "SKILL.md"
            skill = parse_skill_file(skill_file, category=category, relative_path=relative_path)
            if skill:
                skills.append(skill)

    extensions_config = ExtensionsConfig.from_file()
    for skill in skills:
        skill.enabled = extensions_config.is_skill_enabled(skill.name, skill.category)
```

```python
def parse_skill_file(skill_file: Path, category: str, relative_path: Path | None = None):
    content = skill_file.read_text(encoding="utf-8")
    front_matter_match = re.match(r"^---\\s*\\n(.*?)\\n---\\s*\\n", content, re.DOTALL)
    ...
    return Skill(
        name=name,
        description=description,
        license=license_text,
        skill_dir=skill_file.parent,
        skill_file=skill_file,
        relative_path=relative_path or Path(skill_file.parent.name),
        category=category,
        enabled=True,
    )
```

#### 这段代码做了什么

DeerFlow 启动时并不是把 skill 内容全部读进上下文，而是先构建一个 skill metadata 列表：名称、描述、目录位置、启用状态。换句话说，它先解决“知道有什么”，再决定“什么时候真读内容”。

#### 对当前仓库意味着什么

这和 AuditTool 当前的 `scan_core` 很接近。说明仓库离“skills runtime”并不远，真正缺的是把 catalog、启停、路径、载入协议统一起来，而不是缺一堆文档。

#### 建议如何吸收

- 用 `scan_core.py` 为基础，扩展成统一 `SkillCatalog`，至少包含 `skill_id / summary / source / entrypoint / enabled / load_path`。
- 启停状态不要只靠文档是否存在，而要有明确配置或数据库状态。
- 第一阶段只做 metadata catalog，不急着引入外部 marketplace。

### 5.2 DeerFlow 的“渐进加载”真正体现在 prompt 协议：先暴露 skill 列表，再要求模型按需读主文件

来源：

- `deer-flow: backend/packages/harness/deerflow/agents/lead_agent/prompt.py:370-411`
- `deer-flow: README_zh.md:337-343`

```python
def get_skills_prompt_section(available_skills: set[str] | None = None) -> str:
    skills = load_skills(enabled_only=True)
    ...
    return f"""<skill_system>
You have access to skills ...

**Progressive Loading Pattern:**
1. When a user query matches a skill's use case, immediately call `read_file`
2. Read and understand the skill's workflow and instructions
3. The skill file contains references to external resources under the same folder
4. Load referenced resources only when needed during execution
5. Follow the skill's instructions precisely
...
</skill_system>"""
```

```markdown
README_zh.md:
Skills 采用按需渐进加载，不会一次性把所有内容都塞进上下文。
只有任务确实需要时才加载，这样能把上下文窗口控制得更干净。
```

#### 这段代码做了什么

源码与 README 一起看，逻辑就清楚了：DeerFlow 的“渐进加载”不是不扫描 skills，而是不把 `SKILL.md` 正文、引用资源、相关工具 schema 一次性塞给模型；先给目录和说明，再在任务命中时用 `read_file` 真正读取正文。

#### 对当前仓库意味着什么

AuditTool 现在的 `skills.md` snapshot 更接近“启动时就把部分技能说明写入长期记忆”。这有价值，但它和 DeerFlow 的 progressive loading 不是一回事。前者是资料沉淀，后者是 runtime 按需注入。

#### 建议如何吸收

- 把当前的 `skills.md` snapshot 从“长期记忆正文”改造成“catalog 快照 + 热门 skill 摘要”，不要继续承担完整 skill 正文注入职责。
- prompt 中只暴露 skill 名称、摘要、入口路径；真正命中时再读取 skill 正文和引用资源。
- 对复杂 skill 采用“主文件 + references/ + scripts/”结构，便于以后渐进加载。

### 5.3 DeerFlow 对工具 schema 也做渐进暴露：先隐藏 deferred tools，再通过 `tool_search` 按需取回

来源：

- `deer-flow: backend/packages/harness/deerflow/tools/tools.py:23-100`
- `deer-flow: backend/packages/harness/deerflow/agents/middlewares/deferred_tool_filter_middleware.py:23-60`
- `deer-flow: backend/packages/harness/deerflow/tools/builtins/tool_search.py:38-168`
- `deer-flow: backend/packages/harness/deerflow/config/tool_search_config.py:6-35`

```python
def get_available_tools(..., subagent_enabled: bool = False):
    ...
    reset_deferred_registry()
    if include_mcp:
        ...
        if config.tool_search.enabled:
            registry = DeferredToolRegistry()
            for t in mcp_tools:
                registry.register(t)
            set_deferred_registry(registry)
            builtin_tools.append(tool_search_tool)
```

```python
class DeferredToolFilterMiddleware(AgentMiddleware[AgentState]):
    def _filter_tools(self, request: ModelRequest) -> ModelRequest:
        registry = get_deferred_registry()
        deferred_names = {e.name for e in registry.entries}
        active_tools = [t for t in request.tools if getattr(t, "name", None) not in deferred_names]
        return request.override(tools=active_tools)
```

```python
class DeferredToolRegistry:
    def register(self, tool: BaseTool) -> None: ...
    def search(self, query: str) -> list[BaseTool]: ...

@tool
def tool_search(query: str) -> str:
    matched_tools = registry.search(query)
    tool_defs = [convert_to_openai_function(t) for t in matched_tools[:MAX_RESULTS]]
    return json.dumps(tool_defs, indent=2, ensure_ascii=False)
```

#### 这段代码做了什么

这组代码说明 DeerFlow 的渐进加载并不只作用于技能文档，也作用于工具 schema：

- MCP 工具先注册到 deferred registry。
- middleware 把这些工具 schema 从模型绑定里移除。
- 模型只在需要时调用 `tool_search`，再把目标工具的完整 schema 拉回来。

#### 对当前仓库意味着什么

这对 AuditTool 的启发很大。当前仓库工具数量已经在增长，未来一旦把 `scan_core`、RAG、MCP、验证 harness、报告工具全部注入 prompt，上下文很快会膨胀。DeerFlow 这里提供了一个非常实用的 runtime 分层思路。

#### 建议如何吸收

- 第一阶段先做 `skill_search / tool_search` 的轻量版，不必一上来就 deferred 全部 MCP tools。
- 让模型默认只看到“常用工具 + 搜索入口”，按 query 动态拉取长 schema。
- 对 AuditTool 来说，最该 deferred 的是解释成本高、参数复杂、调用频率低的工具，而不是所有工具一刀切。

### 5.4 DeerFlow 通过 `/mnt/skills` 暴露只读技能目录；AuditTool 目前仍是“静态 catalog + 文档快照”

来源：

- `deer-flow: backend/packages/harness/deerflow/sandbox/tools.py:27-102`
- `AuditTool: backend/app/services/agent/memory/markdown_memory.py:16-23,180-216`
- `AuditTool: backend/app/services/agent/skills/scan_core.py:6-162`
- `AuditTool: backend/docs/agent-tools/SKILLS_INDEX.md:1-13`

```python
_DEFAULT_SKILLS_CONTAINER_PATH = "/mnt/skills"

def _get_skills_host_path() -> str | None:
    config = get_app_config()
    skills_path = config.skills.get_skills_path()
    if skills_path.exists():
        value = str(skills_path)
        return value

def _resolve_skills_path(path: str) -> str:
    skills_container = _get_skills_container_path()
    skills_host = _get_skills_host_path()
    relative = path[len(skills_container):].lstrip("/")
    return str(Path(skills_host) / relative) if relative else skills_host
```

```python
MEMORY_FILES = {
    "shared": "shared.md",
    "orchestrator": "orchestrator.md",
    "recon": "recon.md",
    "analysis": "analysis.md",
    "verification": "verification.md",
    "skills": "skills.md",
}

def load_bundle(self, *, max_chars: int = 8000, skills_max_lines: int = 180) -> Dict[str, str]:
    ...
    bundle["skills"] = self._read_head_lines(self._path("skills"), ...)

_SCAN_CORE_SKILLS = [
    {"skill_id": "search_code", "name": "search_code", "summary": "..."},
    {"skill_id": "smart_scan", "name": "smart_scan", "summary": "..."},
    {"skill_id": "verify_vulnerability", "name": "verify_vulnerability", "summary": "..."},
]
```

```markdown
# Agent Tool Skills Index
- `dynamic_verification` -> `docs/agent-tools/skills/dynamic_verification.skill.md`
- `read_file` -> `docs/agent-tools/skills/read_file.skill.md`
- `search_code` -> `docs/agent-tools/skills/search_code.skill.md`
```

#### 这段代码做了什么

DeerFlow 通过 `/mnt/skills` 给 agent 一个稳定的只读技能命名空间；AuditTool 则已经有：

- 项目级 `skills.md` 快照。
- 静态 `scan_core` catalog。
- `docs/agent-tools` 文档入口。

换句话说，AuditTool 不是没有技能资产，而是这些资产还没被统一成一个 runtime catalog。

#### 对当前仓库意味着什么

这正适合走“渐进升级”而不是“推倒重来”路线。现有 skill 文档和 scan_core 元数据完全可以直接转成第一版 `SkillCatalog`，只需要补足目录协议、启停、按需载入与工具发现。

#### 建议如何吸收

- 把 `backend/docs/agent-tools/skills/*.skill.md`、`SKILLS_INDEX.md`、`scan_core.py` 三类资产统一编目。
- 在 runtime 中只注入 `name + summary + load_path + source`，需要时再把 skill 主文档和补充材料读入。
- 外部 skill pack、marketplace、压缩包安装可以后置；先把内置 catalog 跑通。

### 5.5 小结

- DeerFlow 的 skills 渐进加载，本质上是“元数据先行、正文后读、工具 schema 延迟暴露”。
- 当前仓库已有足够多的 skill 资产，不需要从零发明一套内容体系。
- 最值得优先做的是“按需发现 + 按需注入”，而不是先做 marketplace。

### 5.6 源码索引

- `deer-flow: README_zh.md:349-360`
- `deer-flow: backend/packages/harness/deerflow/agents/lead_agent/prompt.py:422-445`
- `AuditTool: docs/AGENT_TOOLS.md`

## 6. 综合判断与架构建议

### 6.1 至少三类不能直接照搬的点

1. 审计主流程不能退回 lead-agent 自由编排。当前仓库的 `queue-authoritative workflow` 是安全审计正确性的基础，不能被 DeerFlow 风格的开放式 task decomposition 替代。
2. DeerFlow 的用户长期记忆不能替代项目审计记忆。AuditTool 的 `MarkdownMemoryStore` 与队列状态是项目证据导向的，不应退化成通用偏好记忆。
3. 通用 tool runtime 不能绕过当前证据绑定写入保护。`TaskWriteScopeGuard` 的项目内路径、证据绑定、可写范围限制必须继续生效。
4. sub-agent 不能默认继承全部工具和全部上下文。越是安全审计场景，越需要按 phase、按任务范围裁剪可见工具与历史。

### 6.2 总体对照表

| DeerFlow 能力 | 当前项目现状 | 吸收价值 | 直接照搬风险 | 推荐落点 |
| --- | --- | --- | --- | --- |
| sub-agent 独立 `ThreadState` + 工具过滤 + 并发限额 | 已有 workflow 分工与 child context，但缺标准化隔离执行壳 | 高 | 把主流程交给 lead-agent；递归派生 worker 失控 | 在 phase 内新增隔离 sub-agent runtime |
| checkpointer 统一线程态持久化 | 已有 `AgentStatePersistence` 与 checkpoint 配置 | 中高 | 把领域队列状态错误地折叠进通用 thread state | 新增 thread checkpoint envelope，底层复用现有 persistence |
| summarization / tool-error middleware | 已有压缩、短路、异常处理、写保护，但分散在 `BaseAgent` | 最高 | 摘要丢失证据引用；中断/取消被错误吞掉 | 先抽 middleware pipeline，再逐步迁移逻辑 |
| skills catalog + progressive loading + deferred tools | 已有 `scan_core`、技能文档、`skills.md` snapshot | 高 | 一次性注入全量文档与全量工具 schema，导致上下文膨胀 | 先做内置 skill catalog 和按需读取，再做工具发现 |

### 6.3 推荐的总体架构动作

- 审计内核不动：`WorkflowOrchestrator`、`AuditWorkflowEngine`、风险队列、漏洞队列仍是领域权威。
- runtime 抽象上浮：把当前散落在 `BaseAgent`、`memory`、`MCP runtime` 中的控制逻辑上浮成统一 middleware / checkpoint / skill runtime。
- sub-agent 只做 phase 内 worker，不做顶层 orchestrator。
- 技能资产沿用现有文档与 `scan_core`，不需要重新发明一套内容系统。

## 7. 落地蓝图

### Phase 1：Middleware runtime 化

- 目标：把现有的历史压缩、工具错误降级、循环短路、澄清/中断控制整理成统一 middleware pipeline。
- 影响模块：`backend/app/services/agent/agents/base.py`、`backend/app/services/agent/mcp/runtime.py`、`backend/app/services/agent/llm/memory_compressor.py`、新增 `backend/app/services/agent/runtime/middlewares/*`。
- 不动的审计内核：`workflow/engine.py`、队列服务、finding 归一化逻辑、写保护规则本身。
- 验收标准：摘要触发阈值可配置；工具失败统一转成结构化失败对象；取消/中断仍按控制流处理；重复确定性失败仍可短路。

### Phase 2：Sub-Agent 隔离执行壳

- 目标：给 `analysis / verification / report` 等阶段引入标准化隔离 worker，支持独立消息历史、工具白名单、最大轮次和并发配额。
- 影响模块：新增 `backend/app/services/agent/runtime/subagents/*`，改造 `backend/app/services/agent/tools/agent_tools.py`、`backend/app/services/agent/core/context.py`、必要时补充 `workflow/orchestrator.py` handoff 接口。
- 不动的审计内核：阶段顺序、队列出入队规则、主 orchestrator 的确定性推进。
- 验收标准：同一阶段可并发多个隔离 worker；worker 默认不持有递归派生能力；父线程与子线程的消息历史隔离；trace 仍可追踪。

### Phase 3：统一 checkpoint 线程态

- 目标：在保留 `AgentStatePersistence` 的前提下，引入统一 `ThreadCheckpointEnvelope`，把 thread runtime 恢复能力补齐。
- 影响模块：`backend/app/services/agent/core/persistence.py`、新增 `backend/app/services/agent/core/thread_checkpoint.py`、必要时改造 `memory/markdown_memory.py` 与 `workflow/models.py`。
- 不动的审计内核：风险队列、漏洞队列、`WorkflowState` 的领域权威地位。
- 验收标准：进程重启后可恢复 thread 标题、摘要、todo、tool loop 计数与最近 agent state；恢复不会篡改队列真相源。

### Phase 4：Skills 渐进加载与工具发现

- 目标：把 `scan_core + docs/agent-tools + skills.md snapshot` 升级为正式 skill catalog，先支持按需发现和按需注入，再逐步引入 deferred tool schema。
- 影响模块：`backend/app/services/agent/skills/scan_core.py`、新增 `backend/app/services/agent/skills/catalog.py`、`backend/docs/agent-tools/*`、prompt builder、agent runtime。
- 不动的审计内核：证据绑定写保护、MCP 路由安全规则、审计 workflow。
- 验收标准：默认 prompt 只暴露 skill 摘要；命中 skill 后再加载主文档；复杂工具支持通过搜索入口按需拉 schema；上下文大小明显优于全量注入方案。

## 结论

DeerFlow 不适合替代当前项目的智能体架构，但非常适合作为 runtime 设计样本。最值得优先吸收的是 `summarization / tool-error middleware`，其次是 `skills` 渐进加载，再之后是 `sub-agent` 隔离执行壳与统一 thread-state checkpoint。正确姿势不是“把 AuditTool 改造成 DeerFlow”，而是“保留审计内核，把 DeerFlow 的 runtime 工程化经验接入现有审计系统”。
