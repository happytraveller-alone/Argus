# Tool: `get_symbol_body`

## Tool Purpose
提取函数/方法主体源码，只负责源码提取，不负责语义解释。

输入:
- file_path: 文件路径（相对于项目根目录）
- symbol_name: 目标符号名（函数/方法名）

## Goal
定位目标代码、函数上下文与证据位置。

## Task List
- 读取代码文件并定位行号上下文。
- 快速检索关键词并筛选有效命中。
- 提取函数级上下文供后续验证链路使用。


## Inputs
- `file_path` (string, required): 文件路径（相对于项目根目录）
- `symbol_name` (string, required): 目标符号名


### Example Input
```json
{
  "file_path": "<text>",
  "symbol_name": "<text>"
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
