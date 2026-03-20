# MCP Tool Playbook

## 目标
- 为 Agent 提供稳定的 MCP / 本地路由工具使用约定。
- 优先使用结构化参数，减少因别名、占位输入或路径污染导致的失败。

## 通用规则
- 先传核心字段，再补证据字段。
- 路径统一使用项目相对路径。
- 工具失败时优先检查输入契约，不要盲目重复调用。

## `push_finding_to_queue`
- 核心字段: `file_path`, `line_start`, `title`, `description`, `vulnerability_type`
- 常见富证据字段: `function_name`, `code_snippet`, `source`, `sink`, `suggestion`, `evidence_chain`, `attacker_flow`
- 兼容别名: `line`, `start_line`, `end_line`, `type`, `code`, `recommendation`

## `search_code`
- 先定位 `file_path:line`，再读窗口。
- 正则搜索时显式传 `is_regex=true`。

## `get_code_window`
- 只读取最小必要窗口。
- 必须基于具体锚点行，不要全文件兜底。
