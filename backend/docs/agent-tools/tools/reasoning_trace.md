# Tool: `reasoning_trace`

## Tool Purpose
通过 SequentialThinking MCP 生成推理轨迹。

## Goal
在 analysis/orchestrator/recon/verification 阶段支撑审计编排和结果产出。

## Task List
- 协助 Agent 制定下一步行动。
- 沉淀中间结论与可追溯信息。
- 保障任务收敛与结果可交付性。


## Inputs
- `query` (any, optional): 查询内容（可选）
- `path` (any, optional): 路径（可选）
- `file_path` (any, optional): 文件路径（可选）
- `line_start` (any, optional): 起始行号（可选）
- `line_end` (any, optional): 结束行号（可选）
- `function_name` (any, optional): 函数名（可选）
- `keyword` (any, optional): 关键词（可选）
- `searches` (any, optional): QMD 搜索表达式（可选）
- `collections` (any, optional): QMD 集合（可选）


### Example Input
```json
{
  "query": null,
  "path": null,
  "file_path": null
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“在 analysis/orchestrator/recon/verification 阶段支撑审计编排和结果产出。”时触发。
- 常见阶段: `analysis, orchestrator, recon, verification`。
- 分类: `报告与协作编排`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
