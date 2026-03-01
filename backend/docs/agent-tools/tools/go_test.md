# Tool: `go_test`

## Tool Purpose
在沙箱执行 Go 代码，支持命令行参数和环境变量模拟。

## Inputs
- `code` (string, optional) 或 `file_path` (string, optional): 二选一
- `params` (object, optional): 模拟参数（作为命令行参数或环境变量）
- `env_vars` (object, optional): 环境变量
- `timeout` (integer, optional): 超时秒数，默认 60

### Example Input
```json
{
  "code": "cmd := exec.Command(os.Args[1]); cmd.Run()",
  "params": {"cmd": "whoami"},
  "timeout": 60
}
```

```json
{
  "file_path": "handlers/user.go",
  "params": {"id": "1"}
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 执行结果摘要（包含 stdout/stderr、退出码、漏洞信号）
- `metadata` (object):
  - `exit_code` (int): 退出码
  - `is_vulnerable` (bool): 是否检测到漏洞信号
  - `evidence` (string|null): 漏洞证据
  - `language`: `"Go"`

## Typical Triggers
- Go 命令执行、SQL 注入、路径遍历等漏洞验证
- 测试 Gin/Echo 等框架的输入处理
- 验证用户输入是否进入危险函数（exec.Command, os.OpenFile, db.Exec 等）

## Pitfalls And Forbidden Use
- 需要完整的包结构，工具会自动包装 main 函数
- 编译时间较长，建议设置 timeout >= 60
- 沙箱环境可能缺少某些 Go 模块
- 不要执行破坏性命令
