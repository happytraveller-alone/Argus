# Tool: `universal_vuln_test`

## Tool Purpose
该工具已下线，仅用于兼容历史调用。

## Goal
执行非武器化验证步骤并收集可复现实验信号。

## Task List
- 构造安全可控的测试输入。
- 观察返回、日志与行为差异。
- 输出验证结果与证据摘要。


## Inputs
- `reason` (any, optional): 兼容占位参数


### Example Input
```json
{
  "reason": null
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“执行非武器化验证步骤并收集可复现实验信号。”时触发。
- 常见阶段: `analysis, orchestrator, recon, verification`。
- 分类: `漏洞验证与 PoC 规划`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
