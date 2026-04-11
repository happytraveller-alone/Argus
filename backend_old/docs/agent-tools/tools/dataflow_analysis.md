# Tool: `dataflow_analysis`

## Tool Purpose
分析代码中的数据流，追踪变量从源（如用户输入）到汇（如危险函数）的路径。

使用场景:
- 追踪用户输入如何流向危险函数
- 分析变量是否经过净化处理
- 识别污点传播路径

输入:
- source_code: 包含数据源的代码（与 file_path 二选一）
- sink_code: 包含数据汇的代码（可选）
- variable_name: 要追踪的变量名
- file_path: 文件路径（source_code 为空时可直接读取文件）
- start_line/end_line: 可选，限定分析片段
- source_hints/sink_hints: 可选，补充语义提示

## Goal
追踪污点从 Source 到 Sink 的传播链路，识别净化器与高风险汇点。

## Task List
- 分析源到汇的数据流链路。
- 标记 taint_steps、source_nodes、sink_nodes 与置信度。
- 判断是否存在有效净化或缺失校验。


## Inputs
- `source_code` (any, optional): 包含数据源的代码
- `sink_code` (any, optional): 包含数据汇的代码（如危险函数）
- `variable_name` (string, optional): 要追踪的变量名
- `file_path` (string, optional): 文件路径
- `start_line` (any, optional): 源码起始行
- `end_line` (any, optional): 源码结束行
- `source_hints` (any, optional): Source 提示词列表
- `sink_hints` (any, optional): Sink 提示词列表
- `language` (any, optional): 编程语言
- `max_hops` (integer, optional): 最大传播步数


### Example Input
```json
{
  "file_path": "src/time64.c",
  "start_line": 120,
  "end_line": 180,
  "variable_name": "result",
  "sink_hints": ["sprintf"],
  "max_hops": 8
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
- 常见阶段: `analysis, report`。
- 分类: `可达性与逻辑分析`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 必须提供 `source_code`，或提供可读取的 `file_path`（可选 `start_line/end_line`）。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
