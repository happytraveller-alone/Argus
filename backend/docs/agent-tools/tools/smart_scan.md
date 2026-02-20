# Tool: `smart_scan`

## Tool Purpose
🚀 智能批量安全扫描工具 - 一次调用完成多项检查

这是 Analysis Agent 的首选工具！在分析开始时优先使用此工具获取项目安全概览。

功能：
- 自动识别高风险文件
- 批量检测多种漏洞模式
- 按严重程度汇总结果
- 支持快速模式和完整模式

使用示例:
- 快速全面扫描: {"target": ".", "quick_mode": true}
- 扫描特定目录: {"target": "src/api", "scan_types": ["pattern"]}
- 聚焦特定漏洞: {"target": ".", "focus_vulnerabilities": ["sql_injection", "xss"]}

扫描类型:
- pattern: 危险代码模式匹配
- secret: 密钥泄露检测
- all: 所有类型（默认）

输出：按风险级别分类的发现汇总，可直接用于制定进一步分析策略。

## Goal
快速发现候选漏洞与高风险模式。

## Task List
- 批量扫描候选风险点。
- 按漏洞类型或语义检索相关代码。
- 为后续验证阶段提供优先级线索。


## Inputs
- `target` (string, optional): 扫描目标：可以是目录路径、文件路径或文件模式（如 '*.py'）
- `scan_types` (any, optional): 扫描类型列表。可选: pattern, secret, dependency, all。默认为 all
- `focus_vulnerabilities` (any, optional): 重点关注的漏洞类型，如 ['sql_injection', 'xss', 'command_injection']
- `max_files` (integer, optional): 最大扫描文件数
- `quick_mode` (boolean, optional): 快速模式：只扫描高风险文件


### Example Input
```json
{
  "target": ".",
  "scan_types": null,
  "focus_vulnerabilities": null
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
