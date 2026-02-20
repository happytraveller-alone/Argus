# Tool: `think`

## Tool Purpose
深度思考工具。用于：
1. 分析复杂的代码逻辑或安全问题
2. 规划下一步的分析策略
3. 评估发现的漏洞是否真实存在
4. 决定是否需要深入调查某个方向

使用此工具记录你的推理过程，这有助于保持分析的连贯性。

参数:
- thought: 你的思考内容
- category: 思考类别 (analysis/planning/evaluation/decision)

## Goal
在 analysis/orchestrator/recon/verification 阶段支撑审计编排和结果产出。

## Task List
- 协助 Agent 制定下一步行动。
- 沉淀中间结论与可追溯信息。
- 保障任务收敛与结果可交付性。


## Inputs
- `thought` (string, required): 思考内容，可以是分析、规划、评估等
- `category` (any, optional): 思考类别: analysis(分析), planning(规划), evaluation(评估), decision(决策)


### Example Input
```json
{
  "thought": "<text>",
  "category": "general"
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
