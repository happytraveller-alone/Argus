# Tool: `test_sql_injection`

## Tool Purpose
专门测试 SQL 注入漏洞的工具，支持多种数据库类型和注入 payload。

## Inputs
- `target_file` (string, required): 目标文件路径
- `param_name` (string, optional): 注入参数名，默认 `"id"`
- `payload` (string, optional): SQL 注入 payload，默认 `"1' OR '1'='1"`
  - 布尔盲注: `"1' AND '1'='1"`
  - 联合查询: `"1' UNION SELECT 1,2,3--"`
  - 报错注入: `"1' AND extractvalue(1,concat(0x7e,version()))--"`
  - 时间盲注: `"1' AND SLEEP(5)--"`
- `language` (string, optional): 语言类型，默认 `"auto"`
- `db_type` (string, optional): 数据库类型，默认 `"mysql"`（支持 mysql, postgresql, sqlite, oracle, mssql）

### Example Input
```json
{
  "target_file": "app/login.php",
  "param_name": "username",
  "payload": "admin'--",
  "db_type": "mysql"
}
```

## Outputs
- `success` (bool): 执行是否成功
- `data` (string): 测试结果摘要（包含输出、SQL 错误信息、漏洞确认状态）
- `metadata` (object):
  - `vulnerability_type`: `"sql_injection"`
  - `is_vulnerable` (bool): 是否确认漏洞
  - `evidence` (string|null): 漏洞证据（SQL 错误特征或数据泄露）
  - `poc` (string|null): PoC 命令
  - `db_type` (string): 数据库类型

## Typical Triggers
- 分析阶段发现 SQL 查询拼接用户输入
- 验证阶段需要确认 SQL 注入是否可利用
- 检测是否存在 SQL 错误信息泄露

## Pitfalls And Forbidden Use
- payload 应避免破坏性操作（DROP, DELETE, UPDATE）
- 不要使用真实密码或敏感数据
- SQL 错误不一定意味着漏洞可利用，需要进一步分析
- 注意转义字符和特殊符号的处理
