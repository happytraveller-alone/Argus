# Tool: `security_search`

## Tool Purpose
搜索可能存在安全漏洞的代码。
专门针对特定漏洞类型进行搜索。

支持的漏洞类型:
- sql_injection: SQL 注入
- xss: 跨站脚本
- command_injection: 命令注入
- path_traversal: 路径遍历
- ssrf: 服务端请求伪造
- deserialization: 不安全的反序列化
- auth_bypass: 认证绕过
- hardcoded_secret: 硬编码密钥

## Goal
快速发现候选漏洞与高风险模式。

## Task List
- 批量扫描候选风险点。
- 按漏洞类型或语义检索相关代码。
- 为后续验证阶段提供优先级线索。


## Inputs
- `vulnerability_type` (string, required): 漏洞类型: sql_injection, xss, command_injection, path_traversal, ssrf, deserialization, auth_bypass, hardcoded_secret
- `top_k` (integer, optional): 返回结果数量


### Example Input
```json
{
  "vulnerability_type": "<text>",
  "top_k": 20
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“快速发现候选漏洞与高风险模式。”时触发。
- 常见阶段: `analysis`。
- 分类: `候选发现与模式扫描`。
- 可选工具: `是`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
