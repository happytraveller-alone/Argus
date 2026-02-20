# Tool: `test_sql_injection`

## Tool Purpose
专门测试 SQL 注入漏洞的工具。

支持数据库: MySQL, PostgreSQL, SQLite, Oracle, MSSQL

输入:
- target_file: 目标文件路径
- param_name: 注入参数名 (默认 'id')
- payload: SQL 注入 payload (默认 "1' OR '1'='1")
- language: 语言 (auto 自动检测)
- db_type: 数据库类型 (默认 mysql)

常用 Payload:
- 布尔盲注: "1' AND '1'='1"
- 联合查询: "1' UNION SELECT 1,2,3--"
- 报错注入: "1' AND extractvalue(1,concat(0x7e,version()))--"
- 时间盲注: "1' AND SLEEP(5)--"

示例:
{"target_file": "login.php", "param_name": "username", "payload": "admin'--"}

## Goal
执行非武器化验证步骤并收集可复现实验信号。

## Task List
- 构造安全可控的测试输入。
- 观察返回、日志与行为差异。
- 输出验证结果与证据摘要。


## Inputs
- `target_file` (string, required): 目标文件路径
- `param_name` (string, optional): 注入参数名
- `payload` (string, optional): SQL 注入 payload
- `language` (string, optional): 语言: auto, php, python, javascript, java, go, ruby
- `db_type` (string, optional): 数据库类型: mysql, postgresql, sqlite, oracle, mssql


### Example Input
```json
{
  "target_file": "<text>",
  "param_name": "id",
  "payload": "1' OR '1'='1"
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
