# Tool: `universal_code_test`

## Tool Purpose
统一多语言测试入口：按 `language` 自动选择 PHP/Python/JS/Java/Go/Ruby/Shell 测试器。

**注意**：此工具在代码内部的名称为 `code_test`，但在 Agent 工具注册表中以 `universal_code_test` 暴露。

## Inputs
- `language` (string, required): 编程语言
  - `php` - PHP 代码测试
  - `python` - Python 代码测试
  - `javascript` / `js` / `node` - JavaScript/Node.js 测试
  - `java` - Java 代码测试
  - `go` / `golang` - Go 代码测试
  - `ruby` / `rb` - Ruby 代码测试
  - `shell` / `bash` - Shell 脚本测试
- `code` (string, optional) 或 `file_path` (string, optional): 二选一
- `params` (object, optional): 模拟参数
- `framework_mode` (string, optional): 框架模式
  - `flask` - Flask request.args/form
  - `django` - Django request.GET/POST
  - `express` - Express req.query/body/params
  - `rails` - Rails params
- `timeout` (integer, optional): 超时秒数，默认 30

### Example Input
```json
{
  "language": "python",
  "file_path": "app/api.py",
  "params": {"cmd": "id"},
  "framework_mode": "flask",
  "timeout": 30
}
```

```json
{
  "language": "php",
  "code": "<?php echo shell_exec($_GET['cmd']); ?>",
  "params": {"cmd": "whoami"}
}
```

```json
{
  "language": "javascript",
  "code": "const {exec} = require('child_process'); exec(req.query.cmd);",
  "params": {"cmd": "id"},
  "framework_mode": "express"
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 执行结果摘要（包含 stdout/stderr、退出码、漏洞信号）
- `metadata` (object):
  - `exit_code` (int): 退出码
  - `is_vulnerable` (bool): 是否检测到漏洞信号
  - `evidence` (string|null): 漏洞证据
  - `language` (string): 检测到的语言

## Typical Triggers
- 不确定应使用哪个语言测试工具时
- 需要统一编排多语言验证策略时
- 快速测试不同语言的代码片段

## Pitfalls And Forbidden Use
- 这是统一入口工具，实际执行由各语言专门测试器完成
- 不支持的语言会返回错误
- 框架模式仅模拟请求对象，不启动完整的 Web 应用
- 沙箱环境可能缺少某些语言的库或扩展
- 优先使用专门工具（如 php_test, python_test）以获得更精细的控制
