# Tool: `search_code`

## Tool Purpose
在项目代码中搜索关键字或模式。

使用场景:
- 查找特定函数的所有调用位置
- 搜索特定的 API 使用
- 查找包含特定模式的代码

输入:
- keyword: 搜索关键字或正则表达式
- file_pattern: 可选，文件名模式（如 *.py）
- directory: 可选，搜索目录 (相对路径)
- case_sensitive: 是否区分大小写
- is_regex: 是否使用正则表达式

这是一个快速搜索工具，结果包含匹配行和上下文。

## Goal
定位目标代码、函数上下文与证据位置。

## Task List
- 读取代码文件并定位行号上下文。
- 快速检索关键词并筛选有效命中。
- 提取函数级上下文供后续验证链路使用。


## Inputs
- `keyword` (string, required): 搜索关键字或正则表达式
- `file_pattern` (any, optional): 文件名模式，如 *.py, *.js
- `directory` (any, optional): 搜索目录（相对路径）
- `case_sensitive` (boolean, optional): 是否区分大小写
- `max_results` (integer, optional): 最大结果数
- `is_regex` (boolean, optional): 是否使用正则表达式


### Example Input
```json
{
  "keyword": "<text>",
  "file_pattern": null,
  "directory": null
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
- 常见阶段: `analysis, recon, verification`。
- 分类: `代码读取与定位`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
