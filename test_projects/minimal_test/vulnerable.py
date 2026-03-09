"""
最小测试项目 - 包含几个简单的安全漏洞
"""

import os
import subprocess

def sql_injection_vuln(user_input):
    """SQL注入漏洞"""
    query = f"SELECT * FROM users WHERE name = '{user_input}'"
    return query

def command_injection_vuln(filename):
    """命令注入漏洞"""
    os.system(f"cat {filename}")

def path_traversal_vuln(filepath):
    """路径遍历漏洞"""
    with open(f"/var/data/{filepath}", 'r') as f:
        return f.read()

def xss_vuln(user_content):
    """XSS漏洞"""
    html = f"<div>{user_content}</div>"
    return html
