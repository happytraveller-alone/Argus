# Tool: `test_xss`

## Tool Purpose
专门测试 XSS (跨站脚本) 漏洞的工具。

支持类型: Reflected XSS, Stored XSS, DOM XSS

输入:
- target_file: 目标文件路径
- param_name: 注入参数名 (默认 'input')
- payload: XSS payload (默认 "<script>alert('XSS')</script>")
- xss_type: XSS 类型 (reflected, stored, dom)

常用 Payload:
- Script 标签: <script>alert('XSS')</script>
- 事件处理: <img src=x onerror=alert('XSS')>
- SVG: <svg onload=alert('XSS')>

示例:
{"target_file": "search.php", "param_name": "q", "payload": "<script>alert(1)</script>"}

## Goal
执行非武器化验证步骤并收集可复现实验信号。

## Task List
- 构造安全可控的测试输入。
- 观察返回、日志与行为差异。
- 输出验证结果与证据摘要。


## Inputs
- `target_file` (string, required): 目标文件路径
- `param_name` (string, optional): 注入参数名
- `payload` (string, optional): XSS payload
- `xss_type` (string, optional): XSS 类型: reflected, stored, dom
- `language` (string, optional): 语言: auto, php, python, javascript


### Example Input
```json
{
  "target_file": "<text>",
  "param_name": "input",
  "payload": "<script>alert('XSS')</script>"
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
