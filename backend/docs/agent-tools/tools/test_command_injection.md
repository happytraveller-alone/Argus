# Tool: `test_command_injection`

## Tool Purpose
专门测试命令注入漏洞的工具。

支持语言: PHP, Python, JavaScript, Java, Go, Ruby, Shell

输入:
- target_file: 目标文件路径
- param_name: 注入参数名 (默认 'cmd')
- test_command: 测试命令 (默认 'id')
  - 'id' - 显示用户ID
  - 'whoami' - 显示用户名
  - 'cat /etc/passwd' - 读取密码文件
  - 'echo VULN_TEST' - 输出测试字符串
- language: 语言 (auto 自动检测)

示例:
1. PHP: {"target_file": "vuln.php", "param_name": "cmd", "test_command": "whoami"}
2. Python: {"target_file": "app.py", "param_name": "cmd", "language": "python"}
3. 自定义: {"target_file": "api.js", "test_command": "echo PWNED"}

漏洞确认条件:
- 命令输出包含预期结果 (uid=, root, www-data 等)
- 或自定义 echo 内容出现在输出中

## Goal
执行非武器化验证步骤并收集可复现实验信号。

## Task List
- 构造安全可控的测试输入。
- 观察返回、日志与行为差异。
- 输出验证结果与证据摘要。


## Inputs
- `target_file` (string, required): 目标文件路径
- `param_name` (string, optional): 注入参数名
- `test_command` (string, optional): 测试命令: id, whoami, echo test, cat /etc/passwd
- `language` (string, optional): 语言: auto, php, python, javascript, java, go, ruby, shell
- `injection_point` (any, optional): 注入点描述，如 'shell_exec($_GET[cmd])'


### Example Input
```json
{
  "target_file": "<text>",
  "param_name": "cmd",
  "test_command": "id"
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
