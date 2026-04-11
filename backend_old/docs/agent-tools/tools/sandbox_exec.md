# Tool: `sandbox_exec`

## Tool Purpose
在安全沙箱中执行命令或代码。
用于验证漏洞、测试 PoC 或执行安全检查。

安全限制:
- 命令在 Docker 容器中执行
- 网络默认隔离
- 资源有限制
- 只允许特定命令

允许的命令: python, python3, node, curl, cat, grep, find, ls, echo, id

使用场景:
- 验证命令注入漏洞
- 执行 PoC 代码
- 测试 payload 效果

## Goal
在 verification 阶段支撑审计编排和结果产出。

## Task List
- 协助 Agent 制定下一步行动。
- 沉淀中间结论与可追溯信息。
- 保障任务收敛与结果可交付性。


## Inputs
- `command` (string, required): 要执行的命令
- `timeout` (integer, optional): 超时时间（秒）


### Example Input
```json
{
  "command": "<text>",
  "timeout": 30
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“在 verification 阶段支撑审计编排和结果产出。”时触发。
- 常见阶段: `verification`。
- 分类: `报告与协作编排`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
