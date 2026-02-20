# Tool: `query_security_knowledge`

## Tool Purpose
查询安全知识库，获取漏洞类型、检测方法、修复建议等专业知识。

使用场景：
- 需要了解某种漏洞类型的详细信息
- 查找安全最佳实践
- 获取修复建议
- 了解特定技术的安全考量

示例查询：
- "SQL injection detection methods"
- "XSS prevention best practices"
- "SSRF vulnerability patterns"
- "hardcoded credentials"

## Goal
快速发现候选漏洞与高风险模式。

## Task List
- 批量扫描候选风险点。
- 按漏洞类型或语义检索相关代码。
- 为后续验证阶段提供优先级线索。


## Inputs
- `query` (string, required): 搜索查询，如漏洞类型、技术名称、安全概念等
- `category` (any, optional): 知识类别过滤: vulnerability, best_practice, remediation, code_pattern, compliance
- `top_k` (integer, optional): 返回结果数量


### Example Input
```json
{
  "query": "<text>",
  "category": null,
  "top_k": 3
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
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
