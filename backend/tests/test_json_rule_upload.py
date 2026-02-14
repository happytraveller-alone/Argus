"""
测试 JSON 上传单条规则功能
"""
import os

import pytest

# Integration test: requires a running backend server and auth token.
if os.environ.get("RUN_API_INTEGRATION_TESTS") != "1":
    pytest.skip(
        "Set RUN_API_INTEGRATION_TESTS=1 (and provide base_url/token fixtures) to run.",
        allow_module_level=True,
    )

import json
import requests
import yaml


# 示例规则数据
EXAMPLE_RULES = [
    {
        "name": "sql-injection-python",
        "pattern_yaml": yaml.dump({
            "rules": [
                {
                    "id": "sql-injection-python",
                    "languages": ["python"],
                    "severity": "ERROR",
                    "message": "检测 SQL 注入漏洞",
                    "pattern": "execute",
                    "metadata": {
                        "cwe": "CWE-89",
                        "references": ["https://owasp.org/www-community/attacks/SQL_Injection"],
                    }
                }
            ]
        }, allow_unicode=True),
        "language": "python",
        "severity": "ERROR",
        "source": "json",
        "patch": "https://example.com/sql-injection-fix",
        "correct": True,
        "is_active": True,
    },
    {
        "name": "xss-vulnerability-javascript",
        "pattern_yaml": yaml.dump({
            "rules": [
                {
                    "id": "xss-vulnerability-javascript",
                    "languages": ["javascript"],
                    "severity": "WARNING",
                    "message": "检测潜在的 XSS 漏洞",
                    "pattern": "innerHTML",
                    "metadata": {
                        "cwe": "CWE-79",
                        "references": ["https://owasp.org/www-community/attacks/xss/"],
                    }
                }
            ]
        }, allow_unicode=True),
        "language": "javascript",
        "severity": "WARNING",
        "source": "json",
        "correct": True,
        "is_active": True,
    },
    {
        "name": "path-traversal-java",
        "pattern_yaml": yaml.dump({
            "rules": [
                {
                    "id": "path-traversal-java",
                    "languages": ["java"],
                    "severity": "ERROR",
                    "message": "检测路径遍历漏洞",
                    "pattern": "../../",
                    "metadata": {
                        "cwe": "CWE-22",
                        "references": ["https://owasp.org/www-community/attacks/Path_Traversal"],
                    }
                }
            ]
        }, allow_unicode=True),
        "language": "java",
        "severity": "ERROR",
        "source": "json",
        "correct": True,
        "is_active": True,
    },
]


def test_json_upload_rule(base_url: str, token: str):
    """测试通过 JSON 上传单条规则"""
    print("\n🧪 测试 JSON 上传单条规则...\n")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    for rule_data in EXAMPLE_RULES:
        print(f"📤 上传规则: {rule_data['name']}")

        response = requests.post(
            f"{base_url}/api/v1/static-tasks/rules/upload/json",
            json=rule_data,
            headers=headers,
        )

        if response.status_code == 200:
            result = response.json()
            print(f"  ✅ 成功")
            print(f"     规则 ID: {result['rule_id']}")
            print(f"     语言: {result['language']}")
            print(f"     严重程度: {result['severity']}")
            print(f"     创建时间: {result['created_at']}")
        elif response.status_code == 400:
            error = response.json()
            print(f"  ⚠️  验证失败: {error.get('detail', '未知错误')}")
        else:
            print(f"  ❌ 请求失败 (HTTP {response.status_code})")
            print(f"     {response.text}")
        print()


def generate_curl_examples():
    """生成 curl 命令示例"""
    print("\n📝 curl 命令示例\n")

    rule_example = {
        "name": "custom-security-rule",
        "pattern_yaml": "rules:\n  - id: my-custom-rule\n    languages:\n      - python\n    severity: ERROR\n    message: Custom security check\n    pattern: dangerous_function",
        "language": "python",
        "severity": "ERROR",
        "source": "json",
        "patch": "https://example.com/patch",
        "correct": True,
        "is_active": True,
    }

    json_str = json.dumps(rule_example, ensure_ascii=False, indent=2)

    print("curl -X POST http://localhost:8000/api/v1/static-tasks/rules/upload/json \\")
    print('  -H "Authorization: Bearer YOUR_TOKEN" \\')
    print('  -H "Content-Type: application/json" \\')
    print(f"  -d '{json.dumps(rule_example)}'")


def show_request_format():
    """显示请求格式说明"""
    print("\n📋 JSON 请求格式\n")

    print("""
字段说明：
  - name (必需): 规则名称，字符串
  - pattern_yaml (必需): 规则的 YAML 内容，字符串
  - language (必需): 编程语言，如 python, java, javascript, go 等
  - severity (可选): 严重程度，ERROR/WARNING/INFO，默认为 WARNING
  - source (可选): 规则来源，默认为 json
  - patch (可选): 补丁或相关链接，可为 null
  - correct (可选): 规则是否正确，布尔值，默认为 true
  - is_active (可选): 规则是否启用，布尔值，默认为 true

YAML 格式要求：
  1. 必须包含 rules 字段（数组）
  2. 每个规则对象必须有 id 字段
  3. languages 字段应包含支持的编程语言列表
  4. severity 字段（可选），默认为 ERROR/WARNING/INFO
  5. message 字段（可选），规则的描述

示例 YAML：
  rules:
    - id: my-rule
      languages:
        - python
      severity: ERROR
      message: "检测潜在漏洞"
      pattern: "dangerous_pattern"
      metadata:
        cwe: "CWE-89"
        references:
          - "https://example.com"
""")


def show_response_format():
    """显示响应格式说明"""
    print("\n📤 JSON 响应格式\n")

    example_response = {
        "rule_id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "sql-injection-python",
        "language": "python",
        "severity": "ERROR",
        "source": "json",
        "is_active": True,
        "created_at": "2025-02-03T12:34:56.789012",
        "message": "规则上传成功"
    }

    print("成功响应 (HTTP 200):")
    print(json.dumps(example_response, ensure_ascii=False, indent=2))

    print("\n\n错误响应示例：\n")
    print("格式错误 (HTTP 400):")
    print(json.dumps({
        "detail": "YAML 格式错误: 某个具体错误信息"
    }, ensure_ascii=False, indent=2))

    print("\n\n重复规则 (HTTP 400):")
    print(json.dumps({
        "detail": "规则已存在（重复），现有规则 ID: 550e8400-e29b-41d4-a716-446655440000"
    }, ensure_ascii=False, indent=2))

    print("\n\n服务器错误 (HTTP 500):")
    print(json.dumps({
        "detail": "上传失败: 某个具体错误信息"
    }, ensure_ascii=False, indent=2))


def show_validation_rules():
    """显示验证规则"""
    print("\n✅ 验证规则\n")

    print("""
1. YAML 格式验证
   - YAML 内容必须是有效的 YAML 格式
   - 不能为空或无效

2. 必需字段检查
   - pattern_yaml 中必须包含 rules 字段
   - rules 必须是非空数组
   - 数组中的规则必须是对象
   - 规则对象必须有 id 字段

3. 严重程度验证
   - 必须为 ERROR, WARNING, INFO 之一（不区分大小写）
   - 会自动转换为大写

4. 去重检查
   - 如果 pattern_yaml 完全相同，则视为重复
   - 重复的规则会被拒绝，返回现有规则 ID

5. 语言字段验证
   - language 字段是必需的
   - 可以是任何字符串值，如 python, java, javascript, go 等

错误处理：
   - 返回 HTTP 400: 请求格式错误或验证失败
   - 返回 HTTP 500: 服务器错误
""")


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 Opengrep 规则 JSON 上传 API 测试指南")
    print("=" * 60)

    show_request_format()
    show_response_format()
    show_validation_rules()
    generate_curl_examples()

    print("\n" + "=" * 60)
    print("📌 使用说明")
    print("=" * 60)
    print("""
1. 直接使用 curl 命令上传：
   curl -X POST http://localhost:8000/api/v1/static-tasks/rules/upload/json \\
     -H "Authorization: Bearer YOUR_TOKEN" \\
     -H "Content-Type: application/json" \\
     -d '{"name": "rule-name", "pattern_yaml": "...", "language": "python", ...}'

2. 使用 Python requests 库：
   import requests
   response = requests.post(
       'http://localhost:8000/api/v1/static-tasks/rules/upload/json',
       headers={'Authorization': f'Bearer {token}'},
       json={
           'name': 'rule-name',
           'pattern_yaml': '规则内容',
           'language': 'python',
           'severity': 'ERROR'
       }
   )

3. 使用前端 JavaScript：
   fetch('/api/v1/static-tasks/rules/upload/json', {
       method: 'POST',
       headers: {
           'Authorization': `Bearer ${token}`,
           'Content-Type': 'application/json'
       },
       body: JSON.stringify({
           name: 'rule-name',
           pattern_yaml: '规则内容',
           language: 'python',
           severity: 'ERROR'
       })
   })
   .then(r => r.json())
   .then(data => console.log(data))
""")

    print("\n✅ 文档生成完成！")
