# Tool: `universal_vuln_test`

## Tool Purpose
通用漏洞测试工具，支持多种漏洞类型的自动化测试。

支持的漏洞类型:
- command_injection (cmd/rce): 命令注入
- sql_injection (sqli): SQL 注入
- xss: 跨站脚本
- path_traversal (lfi/rfi): 路径遍历
- ssti: 服务端模板注入
- deserialization: 不安全反序列化

输入:
- target_file: 目标文件路径
- vuln_type: 漏洞类型
- param_name: 参数名
- payload: 自定义 payload (可选)
- language: 语言 (auto 自动检测)

示例:
1. 命令注入: {"target_file": "api.php", "vuln_type": "command_injection", "param_name": "cmd"}
2. SQL 注入: {"target_file": "login.php", "vuln_type": "sql_injection", "param_name": "username", "payload": "admin'--"}
3. XSS: {"target_file": "search.php", "vuln_type": "xss", "param_name": "q"}

## Goal
执行非武器化验证步骤并收集可复现实验信号。

## Task List
- 构造安全可控的测试输入。
- 观察返回、日志与行为差异。
- 输出验证结果与证据摘要。


## Inputs
- `target_file` (string, required): 目标文件路径
- `vuln_type` (string, required): 漏洞类型: command_injection, sql_injection, xss, path_traversal, ssti, deserialization
- `param_name` (string, optional): 参数名
- `payload` (any, optional): 自定义 payload
- `language` (string, optional): 语言


### Example Input
```json
{
  "target_file": "<text>",
  "vuln_type": "<text>",
  "param_name": "input"
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
