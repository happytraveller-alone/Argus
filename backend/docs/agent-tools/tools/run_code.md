# Tool: `run_code`

## Tool Purpose
在沙箱中执行自定义测试代码（Fuzzing Harness / PoC 脚本），用于动态验证漏洞。

## Inputs
- `code` (string, required): 可执行代码
- `language` (string, optional): `python|php|javascript|ruby|go|java|bash`，默认 `python`
- `timeout` (integer, optional): 超时秒数，默认 `60`
- `description` (string, optional): 本次执行目的

### Example Input
```json
{
  "code": "print('hello')",
  "language": "python",
  "timeout": 60,
  "description": "sanity check"
}
```

## Outputs
- `success` / `error`
- `data`: stdout/stderr 摘要
- `metadata`: `language`, `exit_code`, 输出长度

## Typical Triggers
- 构建并执行漏洞验证 Harness
- 需要动态验证而项目无法整体运行时

## Pitfalls And Forbidden Use
- 不要在未读取目标代码前直接执行无关脚本
- 不要把一次失败直接当作“漏洞不存在”
- PoC 建议保持非武器化、可审计

### 命令注入 Fuzzing Harness 示例 (Python)
```python
import os
import subprocess

# === Mock 危险函数来检测调用 ===
executed_commands = []
original_system = os.system

def mock_system(cmd):
    print(f"[DETECTED] os.system called: {cmd}")
    executed_commands.append(cmd)
    return 0

os.system = mock_system

# === 目标函数（从项目代码复制） ===
def vulnerable_function(user_input):
    os.system(f"echo {user_input}")

# === Fuzzing 测试 ===
payloads = [
    "test",           # 正常输入
    "; id",           # 命令连接符
    "| whoami",       # 管道
    "$(cat /etc/passwd)",  # 命令替换
    "`id`",           # 反引号
    "&& ls -la",      # AND 连接
]

print("=== Fuzzing Start ===")
for payload in payloads:
    print(f"\\nPayload: {payload}")
    executed_commands.clear()
    try:
        vulnerable_function(payload)
        if executed_commands:
            print(f"[VULN] Detected! Commands: {executed_commands}")
    except Exception as e:
        print(f"[ERROR] {e}")
```

### SQL 注入 Fuzzing Harness 示例 (Python)
```python
# === Mock 数据库 ===
class MockCursor:
    def __init__(self):
        self.queries = []

    def execute(self, query, params=None):
        print(f"[SQL] Query: {query}")
        print(f"[SQL] Params: {params}")
        self.queries.append((query, params))

        # 检测 SQL 注入特征
        if params is None and ("'" in query or "OR" in query.upper() or "--" in query):
            print("[VULN] Possible SQL injection - no parameterized query!")

class MockDB:
    def cursor(self):
        return MockCursor()

# === 目标函数 ===
def get_user(db, user_id):
    cursor = db.cursor()
    cursor.execute(f"SELECT * FROM users WHERE id = '{user_id}'")  # 漏洞！

# === Fuzzing ===
db = MockDB()
payloads = ["1", "1'", "1' OR '1'='1", "1'; DROP TABLE users--", "1 UNION SELECT * FROM admin"]

for p in payloads:
    print(f"\\n=== Testing: {p} ===")
    get_user(db, p)
```

### PHP 命令注入 Fuzzing Harness 示例
```php
// 注意：php -r 不需要 <?php 标签

// Mock $_GET
$_GET['cmd'] = '; id';
$_POST['cmd'] = '; id';
$_REQUEST['cmd'] = '; id';

// 目标代码（从项目复制）
$output = shell_exec($_GET['cmd']);
echo "Output: " . $output;

// 如果有输出，说明命令被执行
if ($output) {
    echo "\\n[VULN] Command executed!";
}
```

### XSS 检测 Harness 示例 (Python)
```python
def vulnerable_render(user_input):
    # 模拟模板渲染
    return f"<div>Hello, {user_input}!</div>"

payloads = [
    "test",
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "{{7*7}}",  # SSTI
]

for p in payloads:
    output = vulnerable_render(p)
    print(f"Input: {p}")
    print(f"Output: {output}")
    # 检测：payload 是否原样出现在输出中
    if p in output and ("<" in p or "{{" in p):
        print("[VULN] XSS - input not escaped!")
```