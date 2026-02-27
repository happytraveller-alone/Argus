# Tool: `controlflow_analysis_light`

## Tool Purpose
轻量控制流/数据流分析：基于 tree-sitter 和 code2flow 推断从入口到漏洞位置的调用链、控制条件和可达性分值。适用于不完整代码和不可编译项目。

## Goal
判断漏洞是否可达、是否受逻辑/授权路径约束。

## Task List
- 分析源到汇的数据流链路。
- 计算控制流可达路径与关键条件。
- 验证授权边界和业务逻辑约束。


## Inputs
- `file_path` (string, required): 目标文件路径
- `line_start` (any, optional): 目标起始行
- `line_end` (any, optional): 目标结束行
- `severity` (any, optional): 漏洞严重度
- `confidence` (any, optional): 漏洞置信度 0-1
- `entry_points` (any, optional): 候选入口函数
- `function_name` (any, optional): 目标函数名（缺少 line_start 时可选）
- `vulnerability_type` (any, optional): 漏洞类型
- `call_chain_hint` (any, optional): 已知调用链提示
- `control_conditions_hint` (any, optional): 已知控制条件提示
- `entry_points_hint` (any, optional): 入口函数提示


### Example Input
```json
{
  "file_path": "<text>",
  "line_start": null,
  "line_end": null
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
- 常见阶段: `analysis, verification`。
- 分类: `可达性与逻辑分析`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
