# Tool: `test_deserialization`

## Tool Purpose
检测不安全反序列化漏洞的工具，支持多语言静态分析。

## Inputs
- `target_file` (string, required): 目标文件路径
- `language` (string, optional): 语言类型，默认 `"auto"`（支持 php, python, java, ruby）
- `payload_type` (string, optional): payload 类型，默认 `"detect"`（支持 detect, pickle, yaml, php_serialize）

### Example Input
```json
{
  "target_file": "app/api.py",
  "language": "python",
  "payload_type": "detect"
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 检测结果摘要（包含危险函数调用列表）
- `metadata` (object):
  - `vulnerability_type`: `"deserialization"`
  - `language` (string): 检测到的语言
  - `is_vulnerable` (bool): 是否确认漏洞风险
  - `evidence` (string|null): 漏洞证据
  - `dangerous_calls` (array): 危险函数调用列表

## Typical Triggers
- 分析阶段发现反序列化函数调用（unserialize, pickle.loads, readObject 等）
- 验证阶段需要评估反序列化风险
- 检测用户可控数据是否进入反序列化函数

## Pitfalls And Forbidden Use
- 这是静态分析工具，主要检测危险模式而非实际执行
- 发现危险调用不一定意味着可利用（需要检查数据来源）
- 不同语言的反序列化利用链差异很大
- 建议避免反序列化不可信数据，改用 JSON 等安全格式
