# MCP Tool Playbook

> 目标：让所有 Agent 按需直接调用标准 MCP 工具，避免无效参数和错误路由。

## 1) 工具总览矩阵

| 标准工具名 | MCP Server | MCP Tool | 必填参数 | 典型输出 |
| --- | --- | --- | --- | --- |
| `search_code` | `code_index` (fallback `filesystem`) | `search_code_advanced` (`search_files`) | `keyword/pattern` | 命中位置（含 file_path 与 line） |
| `read_file` | `filesystem` | `read_file` | `file_path + start_line/end_line` | 窗口化代码片段 |
| `list_files` | `code_index` | `find_files` | `directory/path` | 文件列表 |
| `locate_enclosing_function` | `code_index` | `get_file_summary` | `file_path`, `line_start` | 所属函数与范围 |
| `extract_function` | `code_index` | `get_symbol_body` | `file_path`, `function_name/symbol_name` | 函数代码 |
| `qmd_query` | `qmd` | `deep_search` | `query/searches` | 语义检索结果 |
| `qmd_get` | `qmd` | `get` | `doc_id/id` | 文档详情 |
| `qmd_multi_get` | `qmd` | `multi_get` | `ids` | 批量文档结果 |
| `qmd_status` | `qmd` | `status` | 无 | 集合与索引状态 |
| `sequential_thinking` / `reasoning_trace` | `sequentialthinking` | `sequentialthinking` | `thought` | 分步推理轨迹 |

## 2) 文件读取链路（强约束）

1. 先 `search_code` 定位：拿到 `file_path:line`。
2. 再 `read_file` 窗口读取：优先 `line-60 ~ line+99`（最多 200 行）。
3. 需要函数级证据时：调用 `locate_enclosing_function`，再按需 `extract_function`。

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
- 误用：使用虚拟工具名（如 `code_search`、`rag_query`）直接执行。
  - 纠偏：改用标准工具名（`search_code`, `read_file`, `qmd_query` 等）。

## 5) 可复制 Action Input 示例

```json
{
  "action": "search_code",
  "action_input": {
    "keyword": "TM64_ASCTIME_FORMAT",
    "directory": "src",
    "file_pattern": "time64*",
    "max_results": 8
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
