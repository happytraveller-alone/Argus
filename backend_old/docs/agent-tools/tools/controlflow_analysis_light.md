# Tool: `controlflow_analysis_light`

## Tool Purpose
轻量控制流/数据流分析：基于 tree-sitter 和 code2flow 推断从入口到漏洞位置的调用链、控制条件和可达性分值。

输入:
- file_path: 目标文件路径；支持 `path/to/file:line` 形式内嵌行号
- line_start: 可选，目标起始行（缺失时可从 file_path:line 或 function_name 推断）
- line_end: 可选，目标结束行（默认与 line_start 相同）
- severity: 可选，漏洞严重度（用于辅助评分）
- confidence: 可选，漏洞置信度 0-1（用于辅助评分）
- entry_points: 可选，候选入口函数列表
- function_name: 可选，目标函数名（缺少 line_start 时用于定位）
- vulnerability_type: 可选，漏洞类型
- call_chain_hint: 可选，已知调用链提示
- control_conditions_hint: 可选，已知控制条件提示
- entry_points_hint: 可选，入口函数提示（entry_points 为空时作为回退）

输出:
- data: FlowEvidencePipeline 的结构化分析结果（含 flow/path 信息）
- metadata.summary: `path_found/path_score/blocked_reasons` 摘要

适用于不完整代码和不可编译项目。

## Goal
判断漏洞是否可达、是否受逻辑/授权路径约束。

## Task List
- 计算入口到目标点的可达路径与 path_score。
- 识别关键控制条件、分支守卫和阻断原因。
- 结合调用链提示验证是否存在可绕过路径。


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
  "file_path": "src/time64.c:120",
  "vulnerability_type": "buffer_overflow",
  "call_chain_hint": ["main"]
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
- 优先提供 `file_path:line` 或显式 `line_start`；缺少行号时可用 `function_name` 作为回退定位。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
