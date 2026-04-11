# Tool Playbook

> 目标：让所有 Agent 按需直接调用标准工具，避免无效参数和错误路由。

## 1) 工具总览矩阵

| 标准工具名 | Tool Provider | Runtime Tool | 必填参数 | 典型输出 |
| --- | --- | --- | --- | --- |
| `search_code` | `local` | `FileSearchTool` | 公开输入 `keyword`；优先补充 `directory/file_pattern` 缩小范围 | 命中位置（含 file_path 与 line） |
| `read_file` | `local` | `read_file` | `file_path + start_line/end_line` | 窗口化代码片段 |
| `list_files` | `local` | `ListFilesTool` | `directory/path` | 文件列表 |
| `locate_enclosing_function` | `local` | `LocateEnclosingFunctionTool` | `file_path/path` + `line_start/line`（或 `file_path:line`） | 所属函数、范围与诊断 |
| `get_symbol_body` | `local` | `SymbolBodyTool` | `file_path`, `symbol_name` | 函数代码 |

## 2) 文件读取链路（强约束）

1. 先 `search_code` 定位：拿到 `file_path:line`。
2. 再 `read_file` 窗口读取：优先 `line-60 ~ line+99`（最多 200 行）。
3. 需要函数级证据时：调用 `locate_enclosing_function`，再按需 `get_symbol_body`。

## 3) 最小调用模板

```json
{
  "tool": "search_code",
  "input": {
    "keyword": "auth bypass",
    "directory": "src",
    "file_pattern": "*.py",
    "max_results": 5
  }
}
```

## 4) 常见误用与纠偏

- 误用：`read_file` 不带行号直接读全文。
  - 纠偏：先 `search_code`；若仍无法定位且已给定 `file_path`，仅允许读取 `1..120` 文件头窗口。
- 误用：`search_code` 用泛化关键词（如 `function`, `user`）。
  - 纠偏：优先用符号名/常量名，并补 `directory` 与 `file_pattern` 缩小范围。
- 误用：使用虚拟工具名（如 `code_search`、`rag_query`）直接执行。
  - 纠偏：改用标准工具名（`search_code`, `read_file`, `list_files` 等）。

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
