# Tool: `run_code`

## Tool Purpose
在沙箱中执行自定义测试代码（Fuzzing Harness / PoC 脚本），用于动态验证漏洞。

## Inputs
- `code` (string, required): 可执行代码
- `language` (string, optional): `python|php|javascript|ruby|go|java|bash`，默认 `python`
- `timeout` (integer, optional): 超时秒数，默认 `60`
- `description` (string, optional): 本次执行目的

### Example Input
```json
{
  "code": "print('hello')",
  "language": "python",
  "timeout": 60,
  "description": "sanity check"
}
```

## Outputs
- `success` / `error`
- `data`: stdout/stderr 摘要
- `metadata`: `language`, `exit_code`, 输出长度

## Typical Triggers
- 构建并执行漏洞验证 Harness
- 需要动态验证而项目无法整体运行时

## Pitfalls And Forbidden Use
- 不要在未读取目标代码前直接执行无关脚本
- 不要把一次失败直接当作“漏洞不存在”
- PoC 建议保持非武器化、可审计
