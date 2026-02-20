# Tool: `extract_function`

## Tool Purpose
从源文件中提取指定函数的代码

用于构建 Fuzzing Harness 时获取目标函数代码。

输入：
- file_path: 源文件路径
- function_name: 要提取的函数名
- include_imports: 是否包含文件开头的 import 语句（默认 true）

返回：
- 函数代码
- 相关的 import 语句
- 函数参数列表

示例：
{"file_path": "app/api.py", "function_name": "process_command"}

## Goal
定位目标代码、函数上下文与证据位置。

## Task List
- 读取代码文件并定位行号上下文。
- 快速检索关键词并筛选有效命中。
- 提取函数级上下文供后续验证链路使用。


## Inputs
- `file_path` (string, required): 源文件路径
- `function_name` (string, required): 要提取的函数名
- `include_imports` (boolean, optional): 是否包含 import 语句


### Example Input
```json
{
  "file_path": "<text>",
  "function_name": "<text>",
  "include_imports": true
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
- 常见阶段: `verification`。
- 分类: `代码读取与定位`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
