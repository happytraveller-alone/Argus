# Tool: `get_function_summary`

## Tool Purpose
解释单个函数的职责、输入输出、关键调用与风险点，不返回大段源码。

输入:
- file_path: 文件路径（相对于项目根目录）
- function_name: 可选，目标函数名
- line: 可选，函数内任意锚点行（当 function_name 缺失时用于定位）

## Goal
在 analysis/business_logic_analysis/business_logic_recon/orchestrator/recon/report/verification 阶段支撑审计编排和结果产出。

## Task List
- 协助 Agent 制定下一步行动。
- 沉淀中间结论与可追溯信息。
- 保障任务收敛与结果可交付性。


## Inputs
- `file_path` (string, required): 文件路径（相对于项目根目录）
- `function_name` (any, optional): 目标函数名
- `line` (any, optional): 函数内任意锚点行


### Example Input
```json
{
  "file_path": "<text>",
  "function_name": null,
  "line": null
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“在 analysis/business_logic_analysis/business_logic_recon/orchestrator/recon/report/verification 阶段支撑审计编排和结果产出。”时触发。
- 常见阶段: `analysis, business_logic_analysis, business_logic_recon, orchestrator, recon, report, verification`。
- 分类: `报告与协作编排`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
