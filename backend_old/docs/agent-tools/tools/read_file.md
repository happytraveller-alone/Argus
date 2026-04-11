# Tool: `read_file`

## Tool Purpose
读取项目中的文件内容。

使用场景:
- 查看完整的源代码文件
- 查看特定行范围的代码
- 获取配置文件内容

输入:
- file_path: 文件路径（相对于项目根目录）
- start_line: 可选，起始行号
- end_line: 可选，结束行号
- max_lines: 最大返回行数（默认500）

输出格式: 每行代码前带有文件中的原始行号，格式为 `行号| 代码`，例如：
```
   4| def world():
   5|     return 42
```
可直接引用行号定位代码位置。

注意: 为避免输出过长，建议指定行范围搜索定位代码。

## Goal
定位目标代码、函数上下文与证据位置。

## Task List
- 读取代码文件并定位行号上下文。
- 快速检索关键词并筛选有效命中。
- 提取函数级上下文供后续验证链路使用。


## Inputs
- `file_path` (string, required): 文件路径（相对于项目根目录）
- `start_line` (any, optional): 起始行号（从1开始）
- `end_line` (any, optional): 结束行号
- `max_lines` (integer, optional): 最大返回行数
- `project_scope` (boolean, optional): 允许基于项目范围补全 basename 路径


### Example Input
```json
{
  "file_path": "<text>",
  "start_line": null,
  "end_line": null
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
