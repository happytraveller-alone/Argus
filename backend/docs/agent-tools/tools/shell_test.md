# Tool: `shell_test`

## Tool Purpose
在沙箱执行 Shell/Bash 脚本，支持位置参数和环境变量模拟。

## Inputs
- `code` (string, optional) 或 `file_path` (string, optional): 二选一
- `params` (object, optional): 模拟参数（作为位置参数 $1, $2... 或环境变量）
- `env_vars` (object, optional): 环境变量
- `timeout` (integer, optional): 超时秒数，默认 30

### Example Input
```json
{
  "code": "eval $1",
  "params": {"1": "whoami"}
}
```

```json
{
  "file_path": "scripts/deploy.sh",
  "params": {"TARGET": "/tmp", "CMD": "ls"}
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 执行结果摘要（包含 stdout/stderr、退出码、漏洞信号）
- `metadata` (object):
  - `exit_code` (int): 退出码
  - `is_vulnerable` (bool): 是否检测到漏洞信号
  - `evidence` (string|null): 漏洞证据
  - `language`: `"Shell"`

## Typical Triggers
- Shell 脚本命令注入、路径遍历等漏洞验证
- 测试部署脚本、维护脚本的输入处理
- 验证用户输入是否进入危险函数（eval, exec, source 等）

## Pitfalls And Forbidden Use
- 参数键为数字（如 "1", "2"）时会作为位置参数
- 参数键为字符串时会作为环境变量
- Shell 脚本特别容易出现命令注入，需要格外小心
- 不要执行破坏性命令
