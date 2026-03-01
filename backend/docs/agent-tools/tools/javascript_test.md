# Tool: `javascript_test`

## Tool Purpose
在沙箱执行 JavaScript/Node.js 代码，支持 Express 请求对象模拟。

## Inputs
- `code` (string, optional) 或 `file_path` (string, optional): 二选一
- `params` (object, optional): 模拟的请求参数
- `express_mode` (boolean, optional): 是否模拟 Express req 对象
- `env_vars` (object, optional): 环境变量
- `timeout` (integer, optional): 超时秒数，默认 30

### Example Input
```json
{
  "file_path": "src/routes/user.js",
  "params": {"cmd": "id"},
  "express_mode": true
}
```

```json
{
  "code": "const {exec} = require('child_process'); exec(req.query.cmd);",
  "params": {"cmd": "whoami"},
  "express_mode": true
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 执行结果摘要（包含 stdout/stderr、退出码、漏洞信号）
- `metadata` (object):
  - `exit_code` (int): 退出码
  - `is_vulnerable` (bool): 是否检测到漏洞信号
  - `evidence` (string|null): 漏洞证据
  - `language`: `"JavaScript"`

## Typical Triggers
- Node.js/Express 注入与反射类漏洞验证
- 测试命令执行、原型链污染、代码注入等
- 验证用户输入是否进入危险函数（exec, eval, Function, vm.runInContext 等）

## Pitfalls And Forbidden Use
- express_mode 仅模拟 req 对象，不启动完整的 Express 应用
- 沙箱环境可能缺少某些 npm 包
- 不要执行破坏性命令
