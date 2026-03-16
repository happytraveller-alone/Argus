"""
测试 Opengrep 规则上传功能
"""
import asyncio
import os
import tempfile
import zipfile
from pathlib import Path

import pytest
import yaml


def create_test_yaml_rule(rule_id: str, language: str = "python") -> str:
    """创建测试用的 YAML 规则内容"""
    rule_content = {
        "rules": [
            {
                "id": rule_id,
                "languages": [language],
                "severity": "WARNING",
                "message": f"Test rule {rule_id}",
                "pattern": "test_pattern",
                "metadata": {
                    "source": "test",
                    "source-url": f"https://example.com/{rule_id}",
                },
            }
        ]
    }
    return yaml.dump(rule_content, allow_unicode=True)


def test_create_yaml_rule():
    """测试 YAML 规则创建"""
    content = create_test_yaml_rule("test-rule-001", "python")
    assert "test-rule-001" in content
    assert "python" in content
    assert "WARNING" in content
    print("YAML 规则创建测试通过")


def test_create_zip_with_rules():
    """测试创建包含规则的 ZIP 文件"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # 创建临时 ZIP 文件
        zip_path = os.path.join(temp_dir, "test_rules.zip")

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 添加多个规则文件
            for i in range(5):
                rule_id = f"test-rule-{i:03d}"
                content = create_test_yaml_rule(rule_id, "python")
                zf.writestr(f"rules/{rule_id}.yml", content)

        # 验证 ZIP 文件
        assert os.path.exists(zip_path)
        assert os.path.getsize(zip_path) > 0

        # 验证内容
        with zipfile.ZipFile(zip_path, "r") as zf:
            files = zf.namelist()
            assert len(files) == 5
            assert all(f.endswith(".yml") for f in files)

        print(f"ZIP 文件创建测试通过：{len(files)} 个规则文件")


def test_yaml_parsing():
    """测试 YAML 解析"""
    content = create_test_yaml_rule("test-rule-001", "java")
    data = yaml.safe_load(content)

    assert "rules" in data
    assert isinstance(data["rules"], list)
    assert len(data["rules"]) > 0

    rule = data["rules"][0]
    assert rule["id"] == "test-rule-001"
    assert "java" in rule["languages"]
    assert rule["severity"] == "WARNING"

    print("YAML 解析测试通过")


def test_duplicate_detection():
    """测试重复检测（MD5）"""
    import hashlib

    content1 = create_test_yaml_rule("test-rule-001", "python")
    content2 = create_test_yaml_rule("test-rule-001", "python")
    content3 = create_test_yaml_rule("test-rule-002", "python")

    md5_1 = hashlib.md5(content1.encode("utf-8")).hexdigest()
    md5_2 = hashlib.md5(content2.encode("utf-8")).hexdigest()
    md5_3 = hashlib.md5(content3.encode("utf-8")).hexdigest()

    # 相同内容应该有相同的 MD5
    assert md5_1 == md5_2
    # 不同内容应该有不同的 MD5
    assert md5_1 != md5_3

    print("MD5 重复检测测试通过")


def create_sample_zip_file(output_path: str, num_rules: int = 10):
    """创建示例 ZIP 文件用于手动测试"""
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 创建多语言规则
        languages = ["python", "java", "javascript", "go", "c"]

        for i in range(num_rules):
            rule_id = f"test-rule-{i:03d}"
            language = languages[i % len(languages)]
            content = create_test_yaml_rule(rule_id, language)
            zf.writestr(f"rules/{language}/{rule_id}.yml", content)

        # 添加一个格式错误的文件
        zf.writestr("rules/invalid.yml", "invalid: yaml: content:")

        # 添加一个空文件
        zf.writestr("rules/empty.yml", "")

    print(f"创建示例 ZIP 文件: {output_path}")
    print(f"   - {num_rules} 个有效规则")
    print(f"   - 1 个无效规则")
    print(f"   - 1 个空文件")


if __name__ == "__main__":
    print("🧪 开始测试 Opengrep 规则上传功能...\n")

    # 运行基础测试
    test_create_yaml_rule()
    test_create_zip_with_rules()
    test_yaml_parsing()
    test_duplicate_detection()

    # 创建示例文件
    print("\n创建示例测试文件...")
    sample_zip_path = "/tmp/test_opengrep_rules.zip"
    create_sample_zip_file(sample_zip_path, num_rules=20)

    print("\n所有测试通过！")
    print(f"\n💡 可以使用以下命令测试上传功能：")
    print(f"   curl -X POST http://localhost:8000/api/v1/static-tasks/rules/upload \\")
    print(f"        -H 'Authorization: Bearer YOUR_TOKEN' \\")
    print(f"        -F 'file=@{sample_zip_path}'")
