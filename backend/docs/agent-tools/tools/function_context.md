# Tool: `function_context`

## Tool Purpose
查找函数的上下文信息，包括定义、调用者和被调用的函数。
用于追踪数据流和理解函数的使用方式。

输入:
- function_name: 要查找的函数名
- file_path: 可选，限定文件路径
- include_callers: 是否查找调用此函数的代码
- include_callees: 是否查找此函数调用的其他函数

## Goal
定位目标代码、函数上下文与证据位置。

## Task List
- 读取代码文件并定位行号上下文。
- 快速检索关键词并筛选有效命中。
- 提取函数级上下文供后续验证链路使用。


## Inputs
- `function_name` (string, required): 函数名称
- `file_path` (any, optional): 文件路径
- `include_callers` (boolean, optional): 是否包含调用者
- `include_callees` (boolean, optional): 是否包含被调用的函数


### Example Input
```json
{
  "function_name": "<text>",
  "file_path": null,
  "include_callers": true
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
- 常见阶段: `analysis`。
- 分类: `代码读取与定位`。
- 可选工具: `是`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
