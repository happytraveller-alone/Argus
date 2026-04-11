#!/usr/bin/env python3
"""
简单测试：验证 run_code 错误处理逻辑

直接测试错误消息提取的核心逻辑，无需加载整个应用。
"""


def extract_error_from_result(result_dict):
    """
    模拟 run_code 工具中的错误提取逻辑
    
    这是修复后的逻辑：当工具执行失败时，如果 result['error'] 为空，
    从 stderr 中提取错误信息。
    """
    error_message = result_dict.get("error")
    
    if not error_message and not result_dict.get("success", False):
        # 执行失败但没有 error 字段，尝试从 stderr 提取
        stderr = result_dict.get("stderr", "")
        if stderr:
            # 取 stderr 的前 500 字符作为 error 摘要
            error_message = stderr[:500] if len(stderr) > 500 else stderr
        elif result_dict.get("exit_code", 0) != 0:
            error_message = f"代码执行失败，退出码: {result_dict.get('exit_code')}"
    
    return error_message


def test_error_extraction():
    """测试错误提取逻辑"""
    print("=" * 60)
    print("测试 run_code 错误提取逻辑")
    print("=" * 60)
    
    # 测试用例1: 有 stderr 但 error 为空
    print("\n【测试1】stderr 有内容，error 为空")
    result1 = {
        "success": False,
        "exit_code": 1,
        "stdout": "",
        "stderr": '''Traceback (most recent call last):
  File "<string>", line 12, in <module>
  File "/usr/local/lib/python3.12/http/server.py", line 526, in send_header
    if self.request_version != 'HTTP/0.9':
       ^^^^^^^^^^^^^^^^^^^^
AttributeError: 'BaseHTTPRequestHandler' object has no attribute 'request_version'.
''',
        "error": None
    }
    
    extracted = extract_error_from_result(result1)
    print(f"提取的错误: {extracted[:100]}...")
    
    if extracted and "AttributeError" in extracted:
        print("成功：从 stderr 提取了 AttributeError")
    else:
        print("失败：未能提取错误信息")
        return False
    
    # 测试用例2: error 字段已有内容
    print("\n【测试2】error 字段有内容")
    result2 = {
        "success": False,
        "exit_code": 1,
        "stdout": "",
        "stderr": "Some output",
        "error": "Execution failed: something went wrong"
    }
    
    extracted2 = extract_error_from_result(result2)
    print(f"提取的错误: {extracted2}")
    
    if extracted2 == "Execution failed: something went wrong":
        print("成功：保留原有 error 字段")
    else:
        print("失败：error 字段被覆盖")
        return False
    
    # 测试用例3: 执行成功
    print("\n【测试3】执行成功")
    result3 = {
        "success": True,
        "exit_code": 0,
        "stdout": "Hello world",
        "stderr": "",
        "error": None
    }
    
    extracted3 = extract_error_from_result(result3)
    print(f"提取的错误: {extracted3}")
    
    if not extracted3:
        print("成功：执行成功时 error 为空")
    else:
        print("失败：不应该有错误信息")
        return False
    
    # 测试用例4: 仅有非零退出码
    print("\n【测试4】仅有非零退出码，无 stderr")
    result4 = {
        "success": False,
        "exit_code": 137,
        "stdout": "",
        "stderr": "",
        "error": None
    }
    
    extracted4 = extract_error_from_result(result4)
    print(f"提取的错误: {extracted4}")
    
    if extracted4 and "退出码" in extracted4 and "137" in extracted4:
        print("成功：从退出码生成错误信息")
    else:
        print("失败：未能从退出码生成错误")
        return False
    
    # 测试用例5: stderr 很长（超过 500 字符）
    print("\n【测试5】stderr 超过 500 字符")
    long_stderr = "Error: " + "x" * 600
    result5 = {
        "success": False,
        "exit_code": 1,
        "stdout": "",
        "stderr": long_stderr,
        "error": None
    }
    
    extracted5 = extract_error_from_result(result5)
    print(f"提取的错误长度: {len(extracted5 or '')}")
    
    if extracted5 and len(extracted5) == 500:
        print("成功：stderr 被截断到 500 字符")
    else:
        print(f"失败：长度应该是 500，实际是 {len(extracted5 or '')}")
        return False
    
    print("\n" + "=" * 60)
    print("所有测试通过！")
    print("=" * 60)
    return True


if __name__ == "__main__":
    import sys
    success = test_error_extraction()
    sys.exit(0 if success else 1)
