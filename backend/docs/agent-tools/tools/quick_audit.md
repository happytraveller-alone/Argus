# Tool: `quick_audit`

## Tool Purpose
快速文件审计工具 - 对单个文件进行全面安全分析

当 smart_scan 发现高风险文件后，使用此工具进行深入审计。

功能：
- 全面的模式匹配
- 代码结构分析
- 风险评估和优先级排序
- 具体的修复建议

使用示例:
- {"file_path": "app/views.py", "deep_analysis": true}

适用场景：
- smart_scan 发现的高风险文件
- 需要详细分析的可疑代码
- 生成具体的修复建议

## Goal
快速发现候选漏洞与高风险模式。

## Task List
- 批量扫描候选风险点。
- 按漏洞类型或语义检索相关代码。
- 为后续验证阶段提供优先级线索。


## Inputs
- `file_path` (string, required): 要审计的文件路径
- `deep_analysis` (boolean, optional): 是否进行深度分析（包括上下文和数据流分析）


### Example Input
```json
{
  "file_path": "<text>",
  "deep_analysis": true
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
