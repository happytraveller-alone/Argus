# Tool: `java_test`

## Tool Purpose
在沙箱编译并执行 Java 测试代码，适配函数级验证场景。

## Inputs
- `code` (string, optional) 或 `file_path` (string, optional): 二选一
- `params` (object, optional): 模拟参数（作为命令行参数或 Map）
- `env_vars` (object, optional): 环境变量
- `timeout` (integer, optional): 超时秒数，默认 60（Java 编译需要较长时间）

### Example Input
```json
{
  "code": "Runtime.getRuntime().exec(args[0]);",
  "params": {"arg": "whoami"},
  "timeout": 60
}
```

```json
{
  "file_path": "src/main/java/Vuln.java",
  "params": {"cmd": "id"}
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 编译/执行结果摘要（包含 stdout/stderr、退出码、漏洞信号）
- `metadata` (object):
  - `exit_code` (int): 退出码
  - `is_vulnerable` (bool): 是否检测到漏洞信号
  - `evidence` (string|null): 漏洞证据
  - `language`: `"Java"`

## Typical Triggers
- Java 命令执行、输入拼接相关漏洞验证
- 测试 Servlet/Spring 应用的输入处理
- 验证反序列化、XXE、SSRF 等漏洞

## Pitfalls And Forbidden Use
- 需要完整的类结构，工具会自动包装 main 方法
- 编译时间较长，建议设置 timeout >= 60
- 沙箱环境可能缺少某些 Java 库或框架
- 不要执行破坏性命令
