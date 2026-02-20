# Tool: `test_deserialization`

## Tool Purpose
测试不安全反序列化漏洞的工具。

支持语言: PHP (unserialize), Python (pickle, yaml), Java, Ruby (Marshal)

输入:
- target_file: 目标文件路径
- language: 语言
- payload_type: payload 类型 (detect 自动检测)

检测模式:
- 分析代码中是否存在危险的反序列化调用
- 检测用户可控数据是否进入反序列化函数

危险函数:
- PHP: unserialize()
- Python: pickle.loads(), yaml.load(), eval()
- Java: ObjectInputStream.readObject()
- Ruby: Marshal.load()

示例:
{"target_file": "api.py", "language": "python"}

## Goal
执行非武器化验证步骤并收集可复现实验信号。

## Task List
- 构造安全可控的测试输入。
- 观察返回、日志与行为差异。
- 输出验证结果与证据摘要。


## Inputs
- `target_file` (string, required): 目标文件路径
- `language` (string, optional): 语言: auto, php, python, java, ruby
- `payload_type` (string, optional): payload 类型: detect, pickle, yaml, php_serialize


### Example Input
```json
{
  "target_file": "<text>",
  "language": "auto",
  "payload_type": "detect"
}
```

## Outputs
- `success` (bool): 执行是否成功。
- `data` (any): 工具主结果载荷。
- `error` (string|null): 失败时错误信息。
- `duration_ms` (int): 执行耗时（毫秒）。
- `metadata` (object): 补充上下文信息。

## Typical Triggers
- 当 Agent 需要完成“执行非武器化验证步骤并收集可复现实验信号。”时触发。
- 常见阶段: `verification`。
- 分类: `漏洞验证与 PoC 规划`。
- 可选工具: `否`。

## Pitfalls And Forbidden Use
- 不要在输入缺失关键参数时盲目调用。
- 不要将该工具输出直接当作最终结论，必须结合上下文复核。
- 不要在权限不足或路径不合法时重复重试同一输入。
