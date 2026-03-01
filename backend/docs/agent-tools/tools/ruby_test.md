# Tool: `ruby_test`

## Tool Purpose
在沙箱执行 Ruby 代码，支持 Rails 请求参数模拟。

## Inputs
- `code` (string, optional) 或 `file_path` (string, optional): 二选一
- `params` (object, optional): 模拟参数
- `rails_mode` (boolean, optional): 是否模拟 Rails params
- `env_vars` (object, optional): 环境变量
- `timeout` (integer, optional): 超时秒数，默认 30

### Example Input
```json
{
  "file_path": "app/controllers/user_controller.rb",
  "params": {"cmd": "id"},
  "rails_mode": true
}
```

```json
{
  "code": "system(ARGV[0])",
  "params": {"cmd": "whoami"}
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 执行结果摘要（包含 stdout/stderr、退出码、漏洞信号）
- `metadata` (object):
  - `exit_code` (int): 退出码
  - `is_vulnerable` (bool): 是否检测到漏洞信号
  - `evidence` (string|null): 漏洞证据
  - `language`: `"Ruby"`

## Typical Triggers
- Ruby/Rails 命令执行、SSTI、代码注入等漏洞验证
- 测试 Rails 应用的输入处理
- 验证用户输入是否进入危险函数（system, eval, exec, Marshal.load 等）

## Pitfalls And Forbidden Use
- rails_mode 仅模拟 params 对象，不启动完整的 Rails 应用
- 沙箱环境可能缺少某些 Ruby gems
- 不要执行破坏性命令
