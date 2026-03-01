# Tool: `python_test`

## Tool Purpose
在沙箱执行 Python 代码/文件，支持 Flask/Django 请求上下文模拟。

## Inputs
- `code` (string, optional) 或 `file_path` (string, optional): 二选一
- `params` (object, optional): 模拟的请求参数
- `flask_mode` (boolean, optional): 是否模拟 Flask request.args/form
- `django_mode` (boolean, optional): 是否模拟 Django request.GET/POST
- `env_vars` (object, optional): 环境变量
- `timeout` (integer, optional): 超时秒数，默认 30

### Example Input
```json
{
  "file_path": "app/views.py",
  "params": {"cmd": "id"},
  "flask_mode": true,
  "timeout": 30
}
```

```json
{
  "code": "import os; os.system(request.args.get('cmd'))",
  "params": {"cmd": "whoami"},
  "flask_mode": true
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 执行结果摘要（包含 stdout/stderr、退出码、漏洞信号）
- `metadata` (object):
  - `exit_code` (int): 退出码
  - `is_vulnerable` (bool): 是否检测到漏洞信号
  - `evidence` (string|null): 漏洞证据
  - `language`: `"Python"`

## Typical Triggers
- Python Web 路由/函数的动态验证
- 测试 Flask/Django 应用的输入处理
- 验证命令执行、SSTI、反序列化等漏洞

## Pitfalls And Forbidden Use
- flask_mode 和 django_mode 互斥，只能选一个
- 沙箱环境可能缺少某些 Python 包
- 框架模式仅模拟 request 对象，不启动完整的 Flask/Django 应用
- 不要执行破坏性命令
