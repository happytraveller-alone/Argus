# MCP Tool Playbook

> 目标：让所有 Agent 按需直接调用标准 MCP 工具，避免无效参数和错误路由。

## 1) 工具总览矩阵

| 标准工具名 | MCP Server | MCP Tool | 必填参数 | 典型输出 |
| --- | --- | --- | --- | --- |
| `search_code` | `local` | `FileSearchTool` | 公开输入 `keyword`；优先补充 `directory/file_pattern` 缩小范围 | 命中位置（含 file_path 与 line） |
| `read_file` | `filesystem` | `read_file` | `file_path + start_line/end_line` | 窗口化代码片段 |
| `list_files` | `code_index` | `find_files` | `directory/path` | 文件列表 |
| `locate_enclosing_function` | `code_index` | `get_file_summary` | `file_path`, `line_start` | 所属函数与范围 |
| `extract_function` | `code_index` | `get_symbol_body` | `file_path`, `function_name/symbol_name` | 函数代码 |
| `push_finding_to_queue` | local queue tool | `push_finding_to_queue` | `file_path`, `line_start`, `title`, `description`, `vulnerability_type` | 入队结果与队列大小 |
| `get_recon_risk_queue_status` | local queue tool | `get_recon_risk_queue_status` | 无 | `pending_count` 与统计快照 |
| `qmd_query` | `qmd` | `deep_search` | `query/searches` | 语义检索结果 |
| `qmd_get` | `qmd` | `get` | `doc_id/id` | 文档详情 |
| `qmd_multi_get` | `qmd` | `multi_get` | `ids` | 批量文档结果 |
| `qmd_status` | `qmd` | `status` | 无 | 集合与索引状态 |
| `sequential_thinking` / `reasoning_trace` | `sequentialthinking` | `sequentialthinking` | `thought` | 分步推理轨迹 |

## 2) 文件读取链路（强约束）

1. 先 `search_code` 定位：拿到 `file_path:line`。
2. 再 `read_file` 窗口读取：优先 `line-60 ~ line+99`（最多 200 行）。
3. 需要函数级证据时：调用 `locate_enclosing_function`，再按需 `extract_function`。

### `search_code` 的 MCP 精确调用规则

- 公共 `action_input` 仍然写 `keyword`，不要直接伪造 `pattern`。
- 2026-03-08 日志表明：当 `search_code` 路由到 `code_index/search_code_advanced` 时，普通关键字模式可能触发 `pattern Field required`。
- 当前稳定调用方式：`keyword` 写成简单正则，并显式设置 `is_regex: true`，让 router 自动补齐 MCP 所需的 `pattern`。
- 始终附带 `directory` 与 `file_pattern` 缩小搜索域。
- 若出现 `Potentially unsafe regex pattern`，立即简化模式或拆成多次更小搜索，不要重放原样输入。

## 3) QMD / SequentialThinking 最小调用模板

```json
{
  "tool": "qmd_query",
  "input": {
    "query": "查找与认证绕过相关的入口函数",
    "top_k": 5
  }
}
```

```json
{
  "tool": "sequential_thinking",
  "input": {
    "thought": "先定位入口，再验证可达性，再评估影响",
    "thoughtNumber": 1,
    "totalThoughts": 3,
    "nextThoughtNeeded": true
  }
}
```

## 4) 常见误用与纠偏

- 误用：`read_file` 不带行号直接读全文。
  - 纠偏：先 `search_code`；若仍无法定位且已给定 `file_path`，仅允许读取 `1..120` 文件头窗口。
- 误用：`search_code` 用泛化关键词（如 `function`, `user`）。
  - 纠偏：优先用符号名/常量名，并补 `directory` 与 `file_pattern` 缩小范围。
- 误用：`search_code` 在 `code_index` 路由下仍使用 keyword-only 调用。
  - 纠偏：显式设置 `is_regex: true`，保持 `keyword` 为简单 regex，让 router 自动生成 `pattern`。
- 误用：`search_code` 使用复杂正则，随后命中 `Potentially unsafe regex pattern`。
  - 纠偏：改成简单 alternation / 简单字面量，必要时拆成多次搜索。
- 误用：使用虚拟工具名（如 `code_search`、`rag_query`）直接执行。
  - 纠偏：改用标准工具名（`search_code`, `read_file`, `qmd_query` 等）。

## 5) 队列工具调用模板（Analysis/Orchestrator）

`push_finding_to_queue`（标准扁平契约）

```json
{
  "action": "push_finding_to_queue",
  "action_input": {
    "file_path": "src/auth/login.py",
    "line_start": 88,
    "line_end": 96,
    "title": "src/auth/login.py中login函数SQL注入漏洞",
    "description": "用户输入拼接 SQL 且未参数化。",
    "vulnerability_type": "sql_injection",
    "severity": "high",
    "confidence": 0.9
  }
}
```

兼容历史输入：

```json
{
  "action": "push_finding_to_queue",
  "action_input": {
    "finding": {
      "file_path": "src/auth/login.py",
      "line_start": 88,
      "title": "src/auth/login.py中login函数SQL注入漏洞",
      "description": "用户输入拼接 SQL 且未参数化。",
      "vulnerability_type": "sql_injection"
    }
  }
}
```

`get_recon_risk_queue_status`（轮询）

```json
{
  "action": "get_recon_risk_queue_status",
  "action_input": {}
}
```

## 6) 失败分流（熔断判定）

- 业务输入错误（不计入 adapter 熔断）：
  - 例：`read_file` 的 `ENOENT` / `No such file or directory` / 参数缺失。
  - 处理：修正参数，保留 strict MCP，不触发 adapter disable。
- 基础设施故障（计入 adapter 熔断）：
  - 例：`server disconnected`, `RemoteProtocolError`, `connection refused`, `status_502/503/504`。
  - 处理：增加失败计数，达到阈值后 `adapter_disabled_after_failures`。

## 7) 可复制 Action Input 示例

```json
{
  "action": "search_code",
  "action_input": {
    "keyword": "TM64_ASCTIME_FORMAT",
    "directory": "src",
    "file_pattern": "time64*",
    "is_regex": true,
    "max_results": 8
  }
}
```

```json
{
  "action": "search_code",
  "action_input": {
    "keyword": "pickle|fromstring\\(|subprocess",
    "directory": ".",
    "file_pattern": "dsvw.py",
    "is_regex": true,
    "max_results": 12
  }
}
```

```json
{
  "action": "read_file",
  "action_input": {
    "file_path": "src/time64.c",
    "start_line": 760,
    "end_line": 840,
    "max_lines": 120
  }
}
```
