# Tool: `sandbox_exec`

## Tool Purpose
在 Docker 沙箱中执行受限命令，验证命令执行/环境行为。

## Inputs
- `command` (string, required): 要执行的命令
- `timeout` (integer, optional): 超时秒数，默认 `30`

### Example Input
```json
{
  "command": "python3 -c 'print(1)'",
  "timeout": 30
}
```

## Outputs
- `success` / `error`
- `data`: 命令、退出码、stdout/stderr
- `metadata`: `command`, `exit_code`

## Typical Triggers
- 验证命令注入可达性
- 快速执行 shell 级探针

## Pitfalls And Forbidden Use
- 只允许白名单命令，超出会被拒绝
- 不要将沙箱结果等同于生产环境结果
