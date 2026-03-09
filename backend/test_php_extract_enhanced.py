#!/usr/bin/env python3
"""测试增强后的 PHP 函数提取功能"""

import re
import sys
from typing import Dict


class SimpleExtractFunctionTool:
    """简化版的 PHP 函数提取工具（用于测试）"""
    
    def _extract_php(self, code: str, function_name: str) -> Dict:
        """提取 PHP 函数（支持类方法、独立函数）"""
        import re

        # 支持类方法（访问修饰符 + static/abstract/final）和独立函数
        # 匹配: public static function name(...) 或 function name(...)
        # 使用更宽松的模式来处理类型提示和返回类型
        pattern = rf'(?:(?:public|protected|private|abstract|final)\s+)*(?:static\s+)?function\s+{re.escape(function_name)}\s*\([^{{;]*?\)(?:[^{{;]*?)(?:\{{|;)'
        match = re.search(pattern, code, re.DOTALL)

        if not match:
            return {"success": False, "error": f"未找到函数 '{function_name}'"}

        # 检查是否为接口/抽象方法（以分号结尾）
        matched_text = match.group(0)
        is_abstract = matched_text.rstrip().endswith(';')
        
        start_pos = match.start()
        
        if is_abstract:
            # 接口/抽象方法，到分号结束
            end_pos = match.end()
            func_code = code[start_pos:end_pos]
        else:
            # 有函数体的方法，需要找到匹配的右花括号
            brace_count = 0
            end_pos = match.end() - 1

            for i, char in enumerate(code[match.end() - 1:], start=match.end() - 1):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_pos = i + 1
                        break

            func_code = code[start_pos:end_pos]

        # 提取参数
        param_match = re.search(r'function\s+\w+\s*\(([^)]*)\)', func_code)
        params = []
        if param_match:
            params_str = param_match.group(1)
            params = [p.strip().split('=')[0].strip().replace('$', '')
                     for p in params_str.split(',') if p.strip()]

        return {
            "success": True,
            "code": func_code,
            "parameters": params,
        }
    
    def _extract_generic(self, code: str, function_name: str) -> Dict:
        """通用函数提取（正则）"""
        import re

        # 尝试多种模式
        patterns = [
            rf'def\s+{re.escape(function_name)}\s*\([^)]*\)\s*:',  # Python
            # PHP: 支持类方法（访问修饰符 + static）和独立函数
            rf'(?:(?:public|protected|private|abstract|final)\s+)*(?:static\s+)?function\s+{re.escape(function_name)}\s*\([^)]*\)',
            rf'function\s+{re.escape(function_name)}\s*\([^)]*\)',  # PHP/JS 独立函数
            rf'func\s+{re.escape(function_name)}\s*\([^)]*\)',  # Go
        ]

        for pattern in patterns:
            match = re.search(pattern, code, re.MULTILINE)
            if match:
                start_line = code[:match.start()].count('\n')
                lines = code.split('\n')

                # 尝试找到函数结束
                end_line = start_line + 1
                indent = len(lines[start_line]) - len(lines[start_line].lstrip())

                for i in range(start_line + 1, min(start_line + 100, len(lines))):
                    line = lines[i]
                    if line.strip() and not line.startswith(' ' * (indent + 1)):
                        if not line.strip().startswith('#'):
                            end_line = i
                            break
                    end_line = i + 1

                func_code = '\n'.join(lines[start_line:end_line])

                return {
                    "success": True,
                    "code": func_code,
                }

        return {"success": False, "error": f"未找到函数 '{function_name}'"}


def test_php_class_method_extraction():
    """测试 PHP 类方法提取"""
    
    # 模拟 RunScriptCommand.php 中的代码
    php_code = """<?php

namespace Pimcore\\Bundle\\CoreBundle\\Command;

use Symfony\\Component\\Console\\Command\\Command;
use Symfony\\Component\\Console\\Input\\InputInterface;
use Symfony\\Component\\Console\\Output\\OutputInterface;

class RunScriptCommand extends Command
{
    protected function configure()
    {
        $this->setName('pimcore:run-script')
             ->setDescription('Run a custom PHP script');
    }

    public function execute(InputInterface $input, OutputInterface $output): int
    {
        $scriptPath = $input->getArgument('script');
        
        if (!file_exists($scriptPath)) {
            $output->writeln('<error>Script not found</error>');
            return Command::FAILURE;
        }
        
        include $scriptPath;
        
        return Command::SUCCESS;
    }
    
    private static function validateScript($path)
    {
        return is_file($path) && is_readable($path);
    }
}
"""
    
    tool = SimpleExtractFunctionTool()
    
    # 测试 1: 提取 public 方法
    print("测试 1: 提取 public function execute(...)")
    result = tool._extract_php(php_code, "execute")
    if result["success"]:
        print("✓ 成功提取")
        print(f"  参数: {result.get('parameters', [])}")
        print(f"  代码长度: {len(result['code'])} 字符")
        # 验证提取的代码包含关键内容
        assert "public function execute" in result["code"]
        assert "Command::SUCCESS" in result["code"]
    else:
        print(f"✗ 失败: {result.get('error')}")
        return False
    
    # 测试 2: 提取 protected 方法
    print("\n测试 2: 提取 protected function configure(...)")
    result = tool._extract_php(php_code, "configure")
    if result["success"]:
        print("✓ 成功提取")
        assert "protected function configure" in result["code"]
    else:
        print(f"✗ 失败: {result.get('error')}")
        return False
    
    # 测试 3: 提取 private static 方法
    print("\n测试 3: 提取 private static function validateScript(...)")
    result = tool._extract_php(php_code, "validateScript")
    if result["success"]:
        print("✓ 成功提取")
        assert "private static function validateScript" in result["code"]
    else:
        print(f"✗ 失败: {result.get('error')}")
        return False
    
    # 测试 4: 测试接口方法（抽象方法）
    print("\n测试 4: 提取接口方法")
    interface_code = """<?php
interface CommandInterface
{
    public function execute(InputInterface $input, OutputInterface $output): int;
    
    public function getName(): string;
}
"""
    result = tool._extract_php(interface_code, "execute")
    if result["success"]:
        print("✓ 成功提取接口方法")
        assert "public function execute" in result["code"]
        assert result["code"].strip().endswith(";")
    else:
        print(f"✗ 失败: {result.get('error')}")
        return False
    
    # 测试 5: 测试独立函数（向后兼容）
    print("\n测试 5: 提取独立函数（向后兼容）")
    standalone_code = """<?php
function processData($data) {
    return array_map('trim', $data);
}

function execute($command) {
    return shell_exec($command);
}
"""
    result = tool._extract_php(standalone_code, "execute")
    if result["success"]:
        print("✓ 成功提取独立函数")
        assert "function execute" in result["code"]
    else:
        print(f"✗ 失败: {result.get('error')}")
        return False
    
    print("\n" + "="*60)
    print("所有测试通过! ✓")
    print("="*60)
    return True


def test_generic_fallback():
    """测试通用提取的降级策略"""
    
    print("\n" + "="*60)
    print("测试通用提取降级策略")
    print("="*60)
    
    tool = SimpleExtractFunctionTool()
    
    # 测试通用提取也能处理 PHP 类方法
    php_code = """<?php
class TestClass {
    public function execute() {
        echo "test";
    }
}
"""
    
    result = tool._extract_generic(php_code, "execute")
    if result["success"]:
        print("✓ 通用提取也能处理 PHP 类方法")
        assert "execute" in result["code"]
    else:
        print(f"✗ 通用提取失败: {result.get('error')}")
        return False
    
    return True


if __name__ == "__main__":
    try:
        success = test_php_class_method_extraction()
        if success:
            success = test_generic_fallback()
        
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
