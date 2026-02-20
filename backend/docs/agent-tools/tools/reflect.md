# Tool: `reflect`

## Tool Purpose
反思工具。用于回顾当前的分析进展：
1. 总结已经发现的问题
2. 评估当前分析的覆盖度
3. 识别可能遗漏的方向
4. 决定是否需要调整策略

参数:
- summary: 当前进展总结
- findings_so_far: 目前发现的问题数量
- coverage: 分析覆盖度评估 (low/medium/high)
- next_steps: 建议的下一步行动

## Goal
在 analysis/orchestrator/recon/verification 阶段支撑审计编排和结果产出。

## Task List
- 协助 Agent 制定下一步行动。
- 沉淀中间结论与可追溯信息。
- 保障任务收敛与结果可交付性。


## Inputs
- 无显式参数（工具内部处理）。


### Example Input
```json
{}
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
