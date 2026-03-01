# Tool: `php_test`

## Tool Purpose
在沙箱执行 PHP 代码/文件，支持模拟 `$_GET/$_POST/$_REQUEST` 参数。

## Inputs
- `code` (string, optional) 或 `file_path` (string, optional): 二选一
- `params` (object, optional): 模拟的请求参数，如 `{"cmd": "whoami"}`
- `env_vars` (object, optional): 环境变量
- `timeout` (integer, optional): 超时秒数，默认 30

### Example Input
```json
{
  "file_path": "app/vuln.php",
  "params": {"cmd": "whoami"},
  "timeout": 30
}
```

```json
{
  "code": "<?php echo shell_exec($_GET['cmd']); ?>",
  "params": {"cmd": "id"}
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 执行结果摘要（包含 stdout/stderr、退出码、漏洞信号）
- `metadata` (object):
  - `exit_code` (int): 退出码
  - `is_vulnerable` (bool): 是否检测到漏洞信号
  - `evidence` (string|null): 漏洞证据
  - `language`: `"PHP"`

## Typical Triggers
- PHP 命令注入/SQL 注入/XSS 候选验证
- 需要模拟 HTTP 请求参数测试 PHP 脚本
- 验证用户输入是否进入危险函数（shell_exec, system, eval, unserialize 等）

## Pitfalls And Forbidden Use
- 注意 `php -r` 模式不需要 `<?php` 标签，工具会自动处理
- 沙箱环境可能缺少某些 PHP 扩展或数据库连接
- 漏洞信号检测基于 stdout 特征匹配（uid=, root, www-data 等）
- 不要执行破坏性命令
