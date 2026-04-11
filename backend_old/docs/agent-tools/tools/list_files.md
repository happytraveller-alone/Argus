# Tool: `list_files`

## Tool Purpose
列出目录中的文件。

使用场景:
- 了解项目结构
- 查找特定类型的文件
- 浏览目录内容

输入:
- directory: 目录路径 (相对于项目根目录)
- pattern: 可选，文件名模式
- recursive: 是否递归
- max_files: 最大文件数
- recursive_mode: 可选，shallow/deep，兼容更明确的递归模式
- max_entries: 可选，最大返回条目数（优先覆盖 max_files）

## Goal
定位目标代码、函数上下文与证据位置。

## Task List
- 读取代码文件并定位行号上下文。
- 快速检索关键词并筛选有效命中。
- 提取函数级上下文供后续验证链路使用。


## Inputs
- `directory` (string, optional): 目录路径（相对于项目根目录）
- `pattern` (any, optional): 文件名模式，如 *.py
- `recursive` (boolean, optional): 是否递归列出子目录
- `max_files` (integer, optional): 最大文件数
- `recursive_mode` (any, optional): shallow/deep，兼容更明确的递归模式
- `max_entries` (any, optional): 最大返回条目数


### Example Input
```json
{
  "directory": ".",
  "pattern": null,
  "recursive": false
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“定位目标代码、函数上下文与证据位置。”时触发。
- 常见阶段: `analysis, business_logic_analysis, business_logic_recon, orchestrator, recon, report, verification`。
- 分类: `代码读取与定位`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
