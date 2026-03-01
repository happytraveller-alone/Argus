# Tool: `test_command_injection`

## Tool Purpose
专门测试命令注入（Command Injection / RCE）漏洞的工具，支持多语言自动化测试。

## Inputs
- `target_file` (string, required): 目标文件路径
- `param_name` (string, optional): 注入参数名，默认 `"cmd"`
- `test_command` (string, optional): 测试命令，默认 `"id"`
  - `"id"` - 显示用户ID
  - `"whoami"` - 显示用户名
  - `"cat /etc/passwd"` - 读取密码文件
  - `"echo VULN_TEST"` - 输出测试字符串
- `language` (string, optional): 语言类型，默认 `"auto"`（支持 php, python, javascript, java, go, ruby, shell）
- `injection_point` (string, optional): 注入点描述

### Example Input
```json
{
  "target_file": "app/api.php",
  "param_name": "cmd",
  "test_command": "whoami",
  "language": "auto"
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 测试结果摘要（包含退出码、命令输出、漏洞确认状态）
- `metadata` (object):
  - `vulnerability_type`: `"command_injection"`
  - `is_vulnerable` (bool): 是否确认漏洞
  - `evidence` (string|null): 漏洞证据描述
  - `poc` (string|null): PoC 命令
  - `language` (string): 检测到的语言

## Typical Triggers
- 分析阶段发现可疑的命令执行函数（shell_exec, exec, system, subprocess, eval 等）
- 验证阶段需要确认命令注入漏洞是否可利用
- 需要构造 PoC 证明命令执行成功

## Pitfalls And Forbidden Use
- 不要在未确认注入点的情况下盲目测试
- 测试命令应保持非破坏性（避免 rm -rf 等危险操作）
- 如果测试失败，不代表漏洞不存在，可能是沙箱环境限制
- 务必在沙箱环境中测试，不要在生产环境执行
