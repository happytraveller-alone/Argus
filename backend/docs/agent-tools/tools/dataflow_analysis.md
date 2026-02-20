# Tool: `dataflow_analysis`

## Tool Purpose
分析代码中的数据流，追踪变量从源（如用户输入）到汇（如危险函数）的路径。

使用场景:
- 追踪用户输入如何流向危险函数
- 分析变量是否经过净化处理
- 识别污点传播路径

输入:
- source_code: 包含数据源的代码
- sink_code: 包含数据汇的代码（可选）
- variable_name: 要追踪的变量名
- file_path: 文件路径

## Goal
判断漏洞是否可达、是否受逻辑/授权路径约束。

## Task List
- 分析源到汇的数据流链路。
- 计算控制流可达路径与关键条件。
- 验证授权边界和业务逻辑约束。


## Inputs
- `source_code` (string, required): 包含数据源的代码
- `sink_code` (any, optional): 包含数据汇的代码（如危险函数）
- `variable_name` (string, required): 要追踪的变量名
- `file_path` (string, optional): 文件路径


### Example Input
```json
{
  "source_code": "<text>",
  "sink_code": null,
  "variable_name": "<text>"
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“判断漏洞是否可达、是否受逻辑/授权路径约束。”时触发。
- 常见阶段: `analysis`。
- 分类: `可达性与逻辑分析`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
