# Open Risks And Bridges

> 最后更新：2026-04-22

## 文档定位

- 类型：Explanation
- 目标读者：需要判断"为什么现在还不能宣布完成"的开发者

## 仍需明确处理的 bridge

### Subprocess Bridge 层（Python → Rust）

Python Agent 通过 `subprocess.run(backend-runtime-startup ...)` 调用 Rust 计算内核。这些 bridge 文件本身不含核心逻辑，但在 Agent 框架 Rust 化之前必须保留：

- `finding_payload_runtime.py` → `finding-payload normalize`
- `flow_parser_runtime.py` → `flow-parser definitions-batch/locate-enclosing-function`
- `callgraph_code2flow.py` → `code2flow`
- `sandbox_runner_client.py` → `runner execute/stop`
- `task_findings.py`（部分）→ `scan-scope build-patterns/is-ignored/filter-bootstrap-findings`
- `queue_tools.py` / `recon_queue_tools.py` → Rust queue 数据结构

### Script Host

- `scripts/flow_parser_runner.py` 仍承担 Docker 容器内 flow parser 脚本宿主角色

## 当前主要风险

### Route Ownership != Runtime Ownership

Rust 拥有全部 HTTP 路由，但 `agent-tasks/start` 触发的实际审计工作仍由 Python Agent 执行。Rust route 只是接收请求并转发给 Python runtime。

### Agent 框架是最大单体

66 个 Python 文件构成紧耦合的 Agent 系统（5 个 Agent 类型 + 15 个工具文件 + 11 个流分析文件 + 运行时协调）。不适合逐文件切片，需要按功能域整体接管。

### Behavioral Narrowing Risk

Rust 接管 Agent 层时，可能会顺带收窄 LLM 交互行为。必须同步写清 contract、前端影响和验证结论。

### Health 200 != Ready

容器 healthcheck 返回 HTTP 200 不等于 bootstrap / preflight gate 全部通过。

## Final Python Retirement Checklist

1. Agent 框架（5 个 Agent 类型 + BaseAgent + ReAct parser）不再依赖 Python
2. 工具系统（15 个工具文件 + 4 个运行时协调）不再依赖 Python
3. 流分析 pipeline（11 个文件）不再依赖 Python
4. Subprocess bridge 层全部退役
5. `scripts/flow_parser_runner.py` 完成 Rust 化或明确降级
6. `/health` JSON 为 `ok`，agent/static 真路径 smoke 成功
7. `backend_old/app` 目录为空或仅含 archive 标记
