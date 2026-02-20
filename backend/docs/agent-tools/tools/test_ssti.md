# Tool: `test_ssti`

## Tool Purpose
专门测试 SSTI (服务端模板注入) 漏洞的工具。

支持模板引擎: Jinja2, Twig, Freemarker, Velocity, Smarty

输入:
- target_file: 目标文件路径
- param_name: 注入参数名
- payload: SSTI payload (默认 "{{7*7}}")
- template_engine: 模板引擎类型

常用 Payload:
- Jinja2/Twig: {{7*7}}, {{config}}
- Freemarker: ${7*7}
- Velocity: #set($x=7*7)$x
- Smarty: {7*7}

示例:
{"target_file": "render.py", "param_name": "name", "payload": "{{7*7}}", "template_engine": "jinja2"}

## Goal
执行非武器化验证步骤并收集可复现实验信号。

## Task List
- 构造安全可控的测试输入。
- 观察返回、日志与行为差异。
- 输出验证结果与证据摘要。


## Inputs
- `target_file` (string, required): 目标文件路径
- `param_name` (string, optional): 注入参数名
- `payload` (string, optional): SSTI payload
- `template_engine` (string, optional): 模板引擎: auto, jinja2, twig, freemarker, velocity, smarty


### Example Input
```json
{
  "target_file": "<text>",
  "param_name": "name",
  "payload": "{{7*7}}"
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
- 常见阶段: `verification`。
- 分类: `漏洞验证与 PoC 规划`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
