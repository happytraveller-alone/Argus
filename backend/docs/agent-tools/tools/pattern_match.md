# Tool: `pattern_match`

## Tool Purpose
🔍 快速扫描代码中的危险模式和常见漏洞。

支持两种使用方式：
1. ⭐ 推荐：直接扫描文件 - 使用 scan_file 参数指定文件路径
2. 传入代码内容 - 使用 code 参数传入已读取的代码

支持的漏洞类型: sql_injection, xss, command_injection, path_traversal, ssrf, deserialization, hardcoded_secret, weak_crypto

使用示例:
- 方式1（推荐）: {"scan_file": "app/views.py", "pattern_types": ["sql_injection", "xss"]}
- 方式2: {"code": "...", "file_path": "app/views.py"}

输入参数:
- scan_file (推荐): 要扫描的文件路径（相对于项目根目录）
- code: 要扫描的代码内容（与 scan_file 二选一）
- file_path: 文件路径（用于上下文，如果使用 code 模式）
- pattern_types: 要检测的漏洞类型列表
- language: 指定编程语言（通常自动检测）

这是一个快速扫描工具，发现的问题需要进一步分析确认。

## Goal
快速发现候选漏洞与高风险模式。

## Task List
- 批量扫描候选风险点。
- 按漏洞类型或语义检索相关代码。
- 为后续验证阶段提供优先级线索。


## Inputs
- `code` (any, optional): 要扫描的代码内容（与 scan_file 二选一）
- `scan_file` (any, optional): 要扫描的文件路径（相对于项目根目录，与 code 二选一）
- `file_path` (string, optional): 文件路径（用于上下文）
- `pattern_types` (any, optional): 要检测的漏洞类型列表，如 ['sql_injection', 'xss']。为空则检测所有类型
- `language` (any, optional): 编程语言，用于选择特定模式


### Example Input
```json
{
  "code": null,
  "scan_file": null,
  "file_path": "unknown"
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
