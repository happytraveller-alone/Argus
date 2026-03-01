# Tool: `vuln_test`

## Tool Purpose
通用漏洞测试工具，支持多种漏洞类型的自动化测试，自动选择合适的专门测试器。

## Inputs
- `target_file` (string, required): 目标文件路径
- `vuln_type` (string, required): 漏洞类型
  - `"command_injection"` / `"cmd"` / `"rce"`: 命令注入
  - `"sql_injection"` / `"sqli"`: SQL 注入
  - `"xss"`: 跨站脚本
  - `"path_traversal"` / `"lfi"` / `"rfi"`: 路径遍历
  - `"ssti"`: 服务端模板注入
  - `"deserialization"`: 不安全反序列化
- `param_name` (string, optional): 参数名，默认 `"input"`
- `payload` (string, optional): 自定义 payload（可选，有默认值）
- `language` (string, optional): 语言类型，默认 `"auto"`

### Example Input
```json
{
  "target_file": "api.php",
  "vuln_type": "command_injection",
  "param_name": "cmd",
  "language": "php"
}
```

```json
{
  "target_file": "login.php",
  "vuln_type": "sql_injection",
  "param_name": "username",
  "payload": "admin'--"
}
```

```json
{
  "target_file": "search.php",
  "vuln_type": "xss",
  "param_name": "q"
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 测试结果摘要（具体格式取决于漏洞类型）
- `metadata` (object): 包含漏洞特定的元数据
  - `vulnerability_type` (string): 漏洞类型
  - `is_vulnerable` (bool): 是否确认漏洞
  - `evidence` (string|null): 漏洞证据
  - `poc` (string|null): PoC 命令
  - 其他字段根据漏洞类型而定

## Typical Triggers
- 需要快速测试某个漏洞类型但不确定用哪个专门工具
- 验证阶段需要批量测试多种漏洞类型
- Orchestrator 需要根据分析结果自动选择测试方法

## Pitfalls And Forbidden Use
- 这是统一入口工具，实际执行由各专门测试器完成
- 不支持的漏洞类型会返回错误
- 自定义 payload 需要符合对应漏洞类型的格式要求
- 优先使用专门工具以获得更精细的控制
