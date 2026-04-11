"""
Agent 测试配置和 Fixtures
提供测试所需的公共设施
"""

import pytest
import asyncio
import tempfile
import shutil
import os
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass


# ============ 测试配置 ============

@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_project_dir():
    """创建临时项目目录，包含测试代码"""
    temp_dir = tempfile.mkdtemp(prefix="VulHunter_test_")
    
    # 创建测试项目结构
    os.makedirs(os.path.join(temp_dir, "src"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "config"), exist_ok=True)
    
    # 创建有漏洞的测试代码 - SQL 注入
    sql_vuln_code = '''
import sqlite3

def get_user(user_id):
    """危险：SQL 注入漏洞"""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    # 直接拼接用户输入，存在 SQL 注入风险
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    cursor.execute(query)
    return cursor.fetchone()

def search_users(name):
    """危险：SQL 注入漏洞"""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE name LIKE '%" + name + "%'")
    return cursor.fetchall()
'''
    
    # 创建有漏洞的测试代码 - 命令注入
    cmd_vuln_code = '''
import os
import subprocess

def run_command(user_input):
    """危险：命令注入漏洞"""
    # 直接执行用户输入
    os.system(f"echo {user_input}")
    
def execute_script(script_name):
    """危险：命令注入漏洞"""
    subprocess.call(f"bash {script_name}", shell=True)
'''
    
    # 创建有漏洞的测试代码 - XSS
    xss_vuln_code = '''
from flask import Flask, request, render_template_string

app = Flask(__name__)

@app.route("/greet")
def greet():
    """危险：XSS 漏洞"""
    name = request.args.get("name", "")
    # 直接将用户输入嵌入 HTML，存在 XSS 风险
    return f"<h1>Hello, {name}!</h1>"

@app.route("/search")
def search():
    """危险：XSS 漏洞"""
    query = request.args.get("q", "")
    html = f"<p>搜索结果: {query}</p>"
    return render_template_string(html)
'''
    
    # 创建有漏洞的测试代码 - 路径遍历
    path_vuln_code = '''
import os

def read_file(filename):
    """危险：路径遍历漏洞"""
    # 没有验证文件路径
    filepath = os.path.join("/app/data", filename)
    with open(filepath, "r") as f:
        return f.read()

def download_file(user_path):
    """危险：路径遍历漏洞"""
    # 直接使用用户输入作为文件路径
    with open(user_path, "rb") as f:
        return f.read()
'''
    
    # 创建有漏洞的测试代码 - 硬编码密钥
    secret_vuln_code = '''
# 配置文件
DATABASE_URL = "postgresql://user:password123@localhost/db"
API_KEY = "sk-1234567890abcdef1234567890abcdef"
SECRET_KEY = "super_secret_key_dont_share"
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

def connect_database():
    password = "admin123"  # 硬编码密码
    return f"mysql://root:{password}@localhost/mydb"
'''
    
    # 创建安全的代码（用于对比）
    safe_code = '''
import sqlite3
from typing import Optional

def get_user_safe(user_id: int) -> Optional[dict]:
    """安全：使用参数化查询"""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()

def validate_input(user_input: str) -> str:
    """输入验证"""
    import re
    if not re.match(r'^[a-zA-Z0-9_]+$', user_input):
        raise ValueError("Invalid input")
    return user_input
'''
    
    # 创建配置文件
    config_code = '''
import os

class Config:
    """安全配置"""
    DATABASE_URL = os.environ.get("DATABASE_URL")
    SECRET_KEY = os.environ.get("SECRET_KEY")
    DEBUG = False
'''
    
    # 创建 requirements.txt
    requirements = '''
flask>=2.0.0
sqlalchemy>=2.0.0
requests>=2.28.0
'''
    
    # 写入文件
    with open(os.path.join(temp_dir, "src", "sql_vuln.py"), "w") as f:
        f.write(sql_vuln_code)
    
    with open(os.path.join(temp_dir, "src", "cmd_vuln.py"), "w") as f:
        f.write(cmd_vuln_code)
    
    with open(os.path.join(temp_dir, "src", "xss_vuln.py"), "w") as f:
        f.write(xss_vuln_code)
    
    with open(os.path.join(temp_dir, "src", "path_vuln.py"), "w") as f:
        f.write(path_vuln_code)
    
    with open(os.path.join(temp_dir, "src", "secrets.py"), "w") as f:
        f.write(secret_vuln_code)
    
    with open(os.path.join(temp_dir, "src", "safe_code.py"), "w") as f:
        f.write(safe_code)
    
    with open(os.path.join(temp_dir, "config", "settings.py"), "w") as f:
        f.write(config_code)
    
    with open(os.path.join(temp_dir, "requirements.txt"), "w") as f:
        f.write(requirements)
    
    yield temp_dir
    
    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_llm_service():
    """模拟 LLM 服务"""
    service = MagicMock()
    service.chat_completion_raw = AsyncMock(return_value={
        "content": "测试响应",
        "usage": {"total_tokens": 100},
    })

    # Agents use streaming API in BaseAgent.stream_llm_call. Provide a minimal async stream
    # that yields a single "done" chunk with a ReAct-shaped response.
    def _chat_completion_stream(*, messages, temperature=None, max_tokens=None, **kwargs):
        system_prompt = ""
        for m in messages or []:
            if isinstance(m, dict) and m.get("role") == "system":
                system_prompt = str(m.get("content") or "")
                break

        if "侦察 Agent" in system_prompt:
            content = (
                "Thought: 已识别到这是一个 Python 项目，包含若干高风险文件。\n"
                "Final Answer: ```json\n"
                "{\n"
                '  "project_structure": {},\n'
                '  "tech_stack": {"languages": ["Python"], "frameworks": [], "databases": []},\n'
                '  "recommended_tools": {"must_use": ["read_file", "search_code"], "reason": "需要证据定位风险点"},\n'
                '  "entry_points": [{"type": "route", "file": "src/app.py", "line": 1, "method": "GET"}],\n'
                '  "high_risk_areas": ["src/sql_vuln.py:1 - 可能存在 SQL 注入风险"],\n'
                '  "initial_findings": [{"title": "可疑 SQL 拼接", "file_path": "src/sql_vuln.py", "line_start": 1, "description": "检测到 SQL 字符串拼接，可能可控输入进入查询。", "confidence": 0.7}],\n'
                '  "summary": "已完成基础侦察。"\n'
                "}\n"
                "```\n"
            )
        elif "漏洞分析 Agent" in system_prompt:
            content = (
                "Thought: 将基于高风险文件给出结构化 findings。\n"
                "Final Answer: ```json\n"
                "{\n"
                '  "findings": [\n'
                "    {\n"
                '      "vulnerability_type": "sql_injection",\n'
                '      "severity": "high",\n'
                '      "title": "疑似 SQL 注入",\n'
                '      "description": "发现可控输入参与 SQL 拼接，可能导致 SQL 注入。",\n'
                '      "file_path": "src/sql_vuln.py",\n'
                '      "line_start": 1,\n'
                '      "code_snippet": "cursor.execute(\\\"SELECT ...\\\" + user_input)",\n'
                '      "confidence": 0.8,\n'
                '      "needs_verification": true\n'
                "    }\n"
                "  ],\n"
                '  "summary": "完成基础分析。"\n'
                "}\n"
                "```\n"
            )
        elif "验证 Agent" in system_prompt:
            content = (
                "Thought: 将对候选项进行最小化验证并输出。\n"
                "Final Answer: ```json\n"
                "{\n"
                '  "findings": [],\n'
                '  "summary": "在单元测试中跳过实际验证。"\n'
                "}\n"
                "```\n"
            )
        else:
            content = "Thought: ok\nFinal Answer: ```json\n{\"ok\": true}\n```\n"

        async def _gen():
            yield {"type": "done", "content": content, "usage": {"total_tokens": 100}}

        return _gen()

    service.chat_completion_stream = _chat_completion_stream
    return service


@pytest.fixture
def mock_event_emitter():
    """模拟事件发射器"""
    emitter = MagicMock()
    emitter.emit_info = AsyncMock()
    emitter.emit_warning = AsyncMock()
    emitter.emit_error = AsyncMock()
    emitter.emit_thinking = AsyncMock()
    emitter.emit_tool_call = AsyncMock()
    emitter.emit_tool_result = AsyncMock()
    emitter.emit_finding = AsyncMock()
    emitter.emit_progress = AsyncMock()
    emitter.emit_phase_start = AsyncMock()
    emitter.emit_phase_complete = AsyncMock()
    emitter.emit_task_complete = AsyncMock()
    emitter.emit = AsyncMock()
    return emitter


@pytest.fixture
def mock_db_session():
    """模拟数据库会话"""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.get = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    return session


@dataclass
class MockProject:
    """模拟项目"""
    id: str = "test-project-id"
    name: str = "Test Project"
    description: str = "Test project for unit tests"


@dataclass
class MockAgentTask:
    """模拟 Agent 任务"""
    id: str = "test-task-id"
    project_id: str = "test-project-id"
    project: MockProject = None
    name: str = "Test Agent Task"
    status: str = "pending"
    current_phase: str = "planning"
    target_vulnerabilities: list = None
    verification_level: str = "analysis_with_poc_plan"
    exclude_patterns: list = None
    target_files: list = None
    max_iterations: int = 50
    timeout_seconds: int = 1800
    
    def __post_init__(self):
        if self.project is None:
            self.project = MockProject()
        if self.target_vulnerabilities is None:
            self.target_vulnerabilities = []
        if self.exclude_patterns is None:
            self.exclude_patterns = []
        if self.target_files is None:
            self.target_files = []


@pytest.fixture
def mock_task():
    """创建模拟任务"""
    return MockAgentTask()


# ============ 测试辅助函数 ============

def assert_finding_valid(finding: Dict[str, Any]):
    """验证漏洞发现的格式"""
    required_fields = ["title", "severity", "vulnerability_type"]
    for field in required_fields:
        assert field in finding, f"Missing required field: {field}"
    
    valid_severities = ["critical", "high", "medium", "low", "info"]
    assert finding["severity"] in valid_severities, f"Invalid severity: {finding['severity']}"


def count_findings_by_type(findings: list, vuln_type: str) -> int:
    """统计特定类型的漏洞数量"""
    return sum(1 for f in findings if f.get("vulnerability_type") == vuln_type)


def count_findings_by_severity(findings: list, severity: str) -> int:
    """统计特定严重程度的漏洞数量"""
    return sum(1 for f in findings if f.get("severity") == severity)
