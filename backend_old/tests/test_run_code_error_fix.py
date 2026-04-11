#!/usr/bin/env python3
"""
测试 run_code 工具的错误返回修复

验证当代码执行失败时，error 字段是否包含有意义的错误信息。
"""

import asyncio
import sys
import os

# 添加 backend 目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.agent.tools.run_code import RunCodeTool


async def test_run_code_error_handling():
    """测试 run_code 的错误处理"""
    print("=" * 60)
    print("测试 run_code 工具的错误返回修复")
    print("=" * 60)
    
    tool = RunCodeTool()
    
    # 测试用例1: Python 代码执行失败（AttributeError）
    print("\n【测试1】Python 代码执行失败（AttributeError）")
    print("-" * 60)
    
    test_code = '''
from http.server import BaseHTTPRequestHandler

# 尝试直接创建实例会失败，因为缺少必要的初始化
handler = BaseHTTPRequestHandler(None, None, None)
handler.send_header('Content-Type', 'text/html\\r\\nX-Injected: malicious')
'''
    
    result = await tool._execute(
        code=test_code,
        language="python",
        description="测试 HTTP 头注入漏洞验证"
    )
    
    print(f"success: {result.success}")
    print(f"error 字段: {result.error}")
    print(f"\ndata 字段预览:")
    print(result.data[:500] if result.data else "None")
    
    # 验证修复效果
    print("\n【验证结果】")
    if result.success:
        print("失败：工具应该返回 success=False")
        return False
    
    if not result.error:
        print("失败：error 字段为空（修复未生效）")
        return False
    
    if "AttributeError" in str(result.error):
        print("成功：error 字段包含 AttributeError 信息")
    else:
        print(f" 警告：error 字段未包含 AttributeError")
        print(f"   实际内容: {result.error[:200]}")
    
    # 测试用例2: 简单的 Python 语法错误
    print("\n" + "=" * 60)
    print("【测试2】Python 语法错误")
    print("-" * 60)
    
    syntax_error_code = '''
print("hello world"
# 缺少右括号
'''
    
    result2 = await tool._execute(
        code=syntax_error_code,
        language="python",
        description="测试语法错误处理"
    )
    
    print(f"success: {result2.success}")
    print(f"error 字段: {result2.error}")
    
    if not result2.success and result2.error:
        print("成功：语法错误被正确捕获并填充到 error 字段")
    else:
        print("失败：语法错误处理异常")
        return False
    
    # 测试用例3: 正常执行成功的情况
    print("\n" + "=" * 60)
    print("【测试3】正常执行成功")
    print("-" * 60)
    
    success_code = 'print("Hello from test")'
    
    result3 = await tool._execute(
        code=success_code,
        language="python",
        description="测试正常执行"
    )
    
    print(f"success: {result3.success}")
    print(f"error 字段: {result3.error}")
    print(f"是否包含输出: {'Hello from test' in str(result3.data)}")
    
    if result3.success and not result3.error:
        print("成功：正常执行时 error 为空")
    else:
        print("失败：正常执行的返回值异常")
        return False
    
    print("\n" + "=" * 60)
    print("所有测试通过！修复生效。")
    print("=" * 60)
    return True


async def main():
    try:
        success = await test_run_code_error_handling()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n测试执行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
