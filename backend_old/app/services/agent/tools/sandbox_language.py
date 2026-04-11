"""
多语言代码测试工具
支持 PHP, Python, JavaScript, Java, Go, Ruby 等语言的沙箱测试
"""

import asyncio
import json
import logging
import os
import tempfile
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from dataclasses import dataclass

from .base import AgentTool, ToolResult
from .sandbox_tool import SandboxManager

logger = logging.getLogger(__name__)


# ============ 通用语言测试基类 ============

class LanguageTestInput(BaseModel):
    """语言测试通用输入"""
    code: Optional[str] = Field(default=None, description="要执行的代码（与 file_path 二选一）")
    file_path: Optional[str] = Field(default=None, description="项目中的文件路径（与 code 二选一）")
    params: Optional[Dict[str, str]] = Field(default=None, description="模拟的请求参数")
    env_vars: Optional[Dict[str, str]] = Field(default=None, description="环境变量")
    timeout: int = Field(default=30, description="超时时间（秒）")


class BaseLanguageTestTool(AgentTool):
    """语言测试工具基类"""

    LANGUAGE_NAME = "unknown"
    LANGUAGE_CMD = "echo"
    FILE_EXTENSION = ".txt"

    def __init__(self, sandbox_manager: Optional[SandboxManager] = None, project_root: str = "."):
        super().__init__()
        self.sandbox_manager = sandbox_manager or SandboxManager()
        self.project_root = project_root

    @property
    def args_schema(self):
        return LanguageTestInput

    def _read_file(self, file_path: str) -> Optional[str]:
        """读取文件内容"""
        full_path = os.path.join(self.project_root, file_path)
        if not os.path.exists(full_path):
            return None
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def _build_wrapper_code(self, code: str, params: Optional[Dict[str, str]]) -> str:
        """构建包装代码 - 子类实现"""
        raise NotImplementedError

    def _build_command(self, code: str) -> str:
        """构建执行命令 - 子类实现"""
        raise NotImplementedError

    def _analyze_output(self, result: Dict[str, Any], params: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """分析输出结果"""
        is_vulnerable = False
        evidence = None

        if result["exit_code"] == 0 and result.get("stdout"):
            stdout = result["stdout"].strip().lower()

            # 通用漏洞特征检测
            vuln_indicators = [
                ("uid=", "命令执行成功 (uid)"),
                ("root:", "命令执行成功 (passwd)"),
                ("www-data", "命令执行成功 (www-data)"),
                ("nobody", "命令执行成功 (nobody)"),
                ("daemon", "命令执行成功 (daemon)"),
                ("/bin/", "路径泄露"),
                ("/etc/", "敏感路径访问"),
                ("sql syntax", "SQL 错误"),
                ("mysql", "数据库信息泄露"),
                ("postgresql", "数据库信息泄露"),
                ("sqlite", "数据库信息泄露"),
                ("syntax error", "代码执行错误"),
                ("stack trace", "堆栈跟踪泄露"),
                ("exception", "异常信息泄露"),
            ]

            for indicator, desc in vuln_indicators:
                if indicator in stdout:
                    is_vulnerable = True
                    evidence = f"{desc}: 输出包含 '{indicator}'"
                    break

            # 检查参数是否被执行
            if params and not is_vulnerable:
                for key, value in params.items():
                    if value.lower() in stdout:
                        is_vulnerable = True
                        evidence = f"参数 '{key}' 的值出现在输出中"
                        break

        return {
            "is_vulnerable": is_vulnerable,
            "evidence": evidence,
        }

    async def _execute(
        self,
        code: Optional[str] = None,
        file_path: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        **kwargs
    ) -> ToolResult:
        """执行语言测试"""
        try:
            await self.sandbox_manager.initialize()
        except Exception as e:
            logger.warning(f"Sandbox init failed: {e}")

        if not self.sandbox_manager.is_available:
            return ToolResult(
                success=False,
                error="沙箱环境不可用 (Docker Unavailable)",
            )

        # 获取代码
        if file_path:
            code = self._read_file(file_path)
            if code is None:
                return ToolResult(
                    success=False,
                    error=f"文件不存在: {file_path}",
                )

        if not code:
            return ToolResult(
                success=False,
                error="必须提供 code 或 file_path",
            )

        # 构建包装代码
        wrapped_code = self._build_wrapper_code(code, params)

        # 构建命令
        command = self._build_command(wrapped_code)

        # 执行
        result = await self.sandbox_manager.execute_command(
            command=command,
            timeout=timeout,
            env=env_vars,
        )

        # 分析结果
        analysis = self._analyze_output(result, params)

        # 格式化输出
        output_parts = [f"🔬 {self.LANGUAGE_NAME} 测试结果\n"]

        if file_path:
            output_parts.append(f"文件: {file_path}")
        if params:
            output_parts.append(f"参数: {json.dumps(params, ensure_ascii=False)}")

        output_parts.append(f"\n退出码: {result['exit_code']}")

        if result["stdout"]:
            stdout = result["stdout"][:3000]
            output_parts.append(f"\n输出:\n```\n{stdout}\n```")

        if result["stderr"]:
            stderr = result["stderr"][:1000]
            output_parts.append(f"\n错误:\n```\n{stderr}\n```")

        if analysis["is_vulnerable"]:
            output_parts.append(f"\n🔴 **漏洞确认**: {analysis['evidence']}")
        else:
            output_parts.append(f"\n🟡 未能确认漏洞")

        return ToolResult(
            success=True,
            data="\n".join(output_parts),
            metadata={
                "exit_code": result["exit_code"],
                "is_vulnerable": analysis["is_vulnerable"],
                "evidence": analysis["evidence"],
                "language": self.LANGUAGE_NAME,
            }
        )


# ============ PHP 测试工具 ============

class PhpTestTool(BaseLanguageTestTool):
    """PHP 代码测试工具"""

    LANGUAGE_NAME = "PHP"
    LANGUAGE_CMD = "php"
    FILE_EXTENSION = ".php"

    @property
    def name(self) -> str:
        return "php_test"

    @property
    def description(self) -> str:
        return """在沙箱中测试 PHP 代码，支持模拟 $_GET/$_POST/$_REQUEST 参数。

输入:
- code: PHP 代码（与 file_path 二选一）
- file_path: 项目中的 PHP 文件路径
- params: 模拟参数，如 {"cmd": "whoami", "id": "1"}
- timeout: 超时秒数

示例:
1. 测试文件: {"file_path": "vuln.php", "params": {"cmd": "whoami"}}
2. 测试代码: {"code": "<?php echo shell_exec($_GET['cmd']); ?>", "params": {"cmd": "id"}}"""

    def _build_wrapper_code(self, code: str, params: Optional[Dict[str, str]]) -> str:
        """构建 PHP 包装代码

        注意: php -r 不需要 <?php 标签，所以这里生成的是纯 PHP 代码
        """
        wrapper_parts = []

        # 模拟超全局变量
        if params:
            for key, value in params.items():
                escaped_value = value.replace("'", "\\'")
                wrapper_parts.append(f"$_GET['{key}'] = '{escaped_value}';")
                wrapper_parts.append(f"$_POST['{key}'] = '{escaped_value}';")
                wrapper_parts.append(f"$_REQUEST['{key}'] = '{escaped_value}';")

        # 清理原代码的 PHP 标签（因为 php -r 不需要它们）
        clean_code = code.strip()
        if clean_code.startswith("<?php"):
            clean_code = clean_code[5:].strip()
        elif clean_code.startswith("<?"):
            clean_code = clean_code[2:].strip()
        if clean_code.endswith("?>"):
            clean_code = clean_code[:-2].strip()

        wrapper_parts.append(clean_code)

        return "\n".join(wrapper_parts)

    def _build_command(self, code: str) -> str:
        """构建 PHP 执行命令"""
        escaped_code = code.replace("'", "'\"'\"'")
        return f"php -r '{escaped_code}'"


# ============ Python 测试工具 ============

class PythonTestInput(LanguageTestInput):
    """Python 测试输入"""
    flask_mode: bool = Field(default=False, description="是否模拟 Flask 请求环境")
    django_mode: bool = Field(default=False, description="是否模拟 Django 请求环境")


class PythonTestTool(BaseLanguageTestTool):
    """Python 代码测试工具"""

    LANGUAGE_NAME = "Python"
    LANGUAGE_CMD = "python3"
    FILE_EXTENSION = ".py"

    @property
    def name(self) -> str:
        return "python_test"

    @property
    def description(self) -> str:
        return """在沙箱中测试 Python 代码，支持模拟 Flask/Django 请求参数。

输入:
- code: Python 代码（与 file_path 二选一）
- file_path: 项目中的 Python 文件路径
- params: 模拟参数，如 {"cmd": "whoami", "user_id": "1"}
- flask_mode: 是否模拟 Flask request.args/form
- django_mode: 是否模拟 Django request.GET/POST
- timeout: 超时秒数

示例:
1. Flask 模式: {"file_path": "app.py", "params": {"cmd": "id"}, "flask_mode": true}
2. 命令行参数: {"code": "import os; os.system(input())", "params": {"input": "whoami"}}"""

    @property
    def args_schema(self):
        return PythonTestInput

    def _build_wrapper_code(self, code: str, params: Optional[Dict[str, str]],
                           flask_mode: bool = False, django_mode: bool = False) -> str:
        """构建 Python 包装代码"""
        wrapper_parts = []

        if params:
            if flask_mode:
                # 模拟 Flask request
                wrapper_parts.append("""
class MockMultiDict(dict):
    def get(self, key, default=None, type=None):
        value = super().get(key, default)
        if type and value is not None:
            try:
                return type(value)
            except:
                return default
        return value
    def getlist(self, key):
        value = self.get(key)
        return [value] if value else []

class MockRequest:
    def __init__(self, params):
        self.args = MockMultiDict(params)
        self.form = MockMultiDict(params)
        self.values = MockMultiDict(params)
        self.data = params
        self.json = params
        self.method = 'GET'
        self.path = '/'
        self.headers = {}
    def get_json(self, force=False, silent=False):
        return self.json

import sys
sys.modules['flask'] = type(sys)('flask')
""")
                params_str = json.dumps(params)
                wrapper_parts.append(f"request = MockRequest({params_str})")

            elif django_mode:
                # 模拟 Django request
                wrapper_parts.append("""
class MockQueryDict(dict):
    def get(self, key, default=None):
        return super().get(key, default)
    def getlist(self, key):
        value = self.get(key)
        return [value] if value else []

class MockRequest:
    def __init__(self, params):
        self.GET = MockQueryDict(params)
        self.POST = MockQueryDict(params)
        self.method = 'GET'
        self.path = '/'
        self.META = {}
        self.body = b''
""")
                params_str = json.dumps(params)
                wrapper_parts.append(f"request = MockRequest({params_str})")
            else:
                # 普通模式：设置命令行参数和环境变量
                wrapper_parts.append("import sys, os")
                args = ["script.py"] + list(params.values())
                wrapper_parts.append(f"sys.argv = {args}")
                for key, value in params.items():
                    wrapper_parts.append(f"os.environ['{key.upper()}'] = '{value}'")

        wrapper_parts.append(code)
        return "\n".join(wrapper_parts)

    def _build_command(self, code: str) -> str:
        """构建 Python 执行命令"""
        escaped_code = code.replace("'", "'\"'\"'")
        return f"python3 -c '{escaped_code}'"

    async def _execute(
        self,
        code: Optional[str] = None,
        file_path: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        flask_mode: bool = False,
        django_mode: bool = False,
        **kwargs
    ) -> ToolResult:
        """执行 Python 测试"""
        try:
            await self.sandbox_manager.initialize()
        except Exception as e:
            logger.warning(f"Sandbox init failed: {e}")

        if not self.sandbox_manager.is_available:
            return ToolResult(success=False, error="沙箱环境不可用")

        if file_path:
            code = self._read_file(file_path)
            if code is None:
                return ToolResult(success=False, error=f"文件不存在: {file_path}")

        if not code:
            return ToolResult(success=False, error="必须提供 code 或 file_path")

        wrapped_code = self._build_wrapper_code(code, params, flask_mode, django_mode)
        command = self._build_command(wrapped_code)

        result = await self.sandbox_manager.execute_command(
            command=command,
            timeout=timeout,
            env=env_vars,
        )

        analysis = self._analyze_output(result, params)

        output_parts = [f"🐍 Python 测试结果\n"]
        if file_path:
            output_parts.append(f"文件: {file_path}")
        if flask_mode:
            output_parts.append("模式: Flask")
        elif django_mode:
            output_parts.append("模式: Django")
        if params:
            output_parts.append(f"参数: {json.dumps(params, ensure_ascii=False)}")

        output_parts.append(f"\n退出码: {result['exit_code']}")

        if result["stdout"]:
            output_parts.append(f"\n输出:\n```\n{result['stdout'][:3000]}\n```")
        if result["stderr"]:
            output_parts.append(f"\n错误:\n```\n{result['stderr'][:1000]}\n```")

        if analysis["is_vulnerable"]:
            output_parts.append(f"\n🔴 **漏洞确认**: {analysis['evidence']}")
        else:
            output_parts.append(f"\n🟡 未能确认漏洞")

        return ToolResult(
            success=True,
            data="\n".join(output_parts),
            metadata={
                "exit_code": result["exit_code"],
                "is_vulnerable": analysis["is_vulnerable"],
                "evidence": analysis["evidence"],
                "language": "Python",
            }
        )
    def _analyze_output(self, result: Dict[str, Any], params: Optional[Dict]) -> Dict[str, Any]:
        """分析沙箱输出，判定漏洞是否存在"""
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        combined_output = (stdout + stderr).lower()
    
        is_vulnerable = False
        evidence = None
    
        # 1. 检查常见的系统权限信号 (针对命令注入)
        vulnerable_patterns = ["uid=", "root:", "www-data", "nobody", "daemon"]
        for pattern in vulnerable_patterns:
            if pattern in combined_output:
                is_vulnerable = True
                evidence = f"Match system signal: {pattern}"
                break
            
        # 2. 如果提供了 params，检查是否有输入反射 (针对 XSS/SSTI)
        if not is_vulnerable and params:
            for val in params.values():
                if str(val).lower() in combined_output and len(str(val)) > 3:
                    is_vulnerable = True
                    evidence = f"Input value '{val}' reflected in output"
                    break

        # 3. 检查是否存在 Python 特有的异常信号 (辅助判断)
        if "render_template_string" in combined_output or "pickle.load" in combined_output:
            is_vulnerable = True
            evidence = "Dangerous function execution detected in output"

        return {
            "is_vulnerable": is_vulnerable,
            "evidence": evidence
        }


# ============ JavaScript/Node.js 测试工具 ============

class JavaScriptTestInput(LanguageTestInput):
    """JavaScript 测试输入"""
    express_mode: bool = Field(default=False, description="是否模拟 Express.js 请求环境")
    client_ip: Optional[str] = Field(default=None, description="模拟的客户端来源 IP") # 添加这一行


class JavaScriptTestTool(BaseLanguageTestTool):
    """JavaScript/Node.js 代码测试工具"""

    LANGUAGE_NAME = "JavaScript"
    LANGUAGE_CMD = "node"
    FILE_EXTENSION = ".js"

    @property
    def name(self) -> str:
        return "javascript_test"

    @property
    def description(self) -> str:
        return """在沙箱中测试 JavaScript/Node.js 代码，支持模拟 Express.js 请求。

输入:
- code: JavaScript 代码（与 file_path 二选一）
- file_path: 项目中的 JS 文件路径
- params: 模拟参数，如 {"cmd": "whoami", "id": "1"}
- express_mode: 是否模拟 Express req 对象
- timeout: 超时秒数

示例:
1. Express 模式: {"file_path": "route.js", "params": {"cmd": "id"}, "express_mode": true}
2. 普通模式: {"code": "require('child_process').execSync(process.argv[2])", "params": {"arg": "whoami"}}"""

    @property
    def args_schema(self):
        return JavaScriptTestInput

    def _build_wrapper_code(self, code: str, params: Optional[Dict[str, str]],
                           express_mode: bool = False, client_ip: Optional[str] = None) -> str:
        """构建 JavaScript 包装代码,仅在需要时注入 IP"""
        wrapper_parts = []

        if params:
            params_json = json.dumps(params, ensure_ascii=False)
            if express_mode:
                # 使用 client_ip 动态生成配置，如果未提供则为 undefined
                ip_value = f"'{client_ip}'" if client_ip else "undefined"
                # 模拟 Express request 对象
                wrapper_parts.append(f"""
const req = {{
    query: {params_json},
    body: {params_json},
    params: {params_json},
    headers: {{'user-agent': 'VulHunter-Scanner/1.0', 'content-type': 'application/json','x-forwarded-for': {ip_value}}},
    get: function(h) {{ return this.headers[h.toLowerCase()]; }},
    header: function(h) {{ return this.headers[h.toLowerCase()]; }},
    method: 'GET',
    url: '/',
    path: '/',
    ip: {ip_value}, // 动态注入，不再硬编码
    ips: {ip_value} ? [{ip_value}] : [],
    protocol: 'http',
    secure: false
}};
const res = {{
    send: function(data) {{ console.log(data); return this; }},
    json: function(data) {{ console.log(JSON.stringify(data)); return this; }},
    status: function(code) {{ this.statusCode = code;return this; }},
    set: function() {{ return this; }},
    end: function() {{ return this; }},
}};
""")
            else:
                # 普通模式：设置进程参数
                wrapper_parts.append(f"const params = {params_json};")
                args = ["node", "script.js"] + list(params.values())
                wrapper_parts.append(f"process.argv = {json.dumps(args)};")

        wrapper_parts.append("// --- Original Code ---")
        wrapper_parts.append(code)
        return "\n".join(wrapper_parts)

    def _build_command(self, code: str) -> str:
        """构建 Node.js 执行命令"""
        escaped_code = code.replace("'", "'\"'\"'")
        return f"node -e '{escaped_code}'"

    async def _execute(
        self,
        code: Optional[str] = None,
        file_path: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        express_mode: bool = False,
        client_ip: Optional[str] = None, # 这里默认为 None
        **kwargs
    ) -> ToolResult:
        """执行 JavaScript 测试，支持动态 IP 注入"""
        try:
            await self.sandbox_manager.initialize()
        except Exception as e:
            logger.warning(f"Sandbox init failed: {e}")

        if not self.sandbox_manager.is_available:
            return ToolResult(success=False, error="沙箱环境不可用")

        if file_path:
            code = self._read_file(file_path)
            if code is None:
                return ToolResult(success=False, error=f"文件不存在: {file_path}")

        if not code:
            return ToolResult(success=False, error="必须提供 code 或 file_path")

        wrapped_code = self._build_wrapper_code(code, params, express_mode, client_ip)
        command = self._build_command(wrapped_code)

        result = await self.sandbox_manager.execute_command(
            command=command,
            timeout=timeout,
            env=env_vars,
        )

        analysis = self._analyze_output(result, params)

        output_parts = [f"📜 JavaScript 测试结果\n"]
        output_parts.append(f"模式: {'Express.js' if express_mode else 'Standard Node'}")
        if client_ip:
            output_parts.append(f"模拟客户端 IP: {client_ip}")
        if file_path:
            output_parts.append(f"文件: {file_path}")
        if express_mode:
            output_parts.append("模式: Express.js")
        if params:
            output_parts.append(f"参数: {json.dumps(params, ensure_ascii=False)}")

        output_parts.append(f"\n退出码: {result['exit_code']}")

        if result["stdout"]:
            output_parts.append(f"\n输出:\n```\n{result['stdout'][:3000]}\n```")
        if result["stderr"]:
            output_parts.append(f"\n错误:\n```\n{result['stderr'][:1000]}\n```")

        if analysis["is_vulnerable"]:
            output_parts.append(f"\n🔴 **漏洞确认**: {analysis['evidence']}")
        else:
            output_parts.append(f"\n🟡 未能确认漏洞")

        return ToolResult(
            success=True,
            data="\n".join(output_parts),
            metadata={
                "exit_code": result["exit_code"],
                "is_vulnerable": analysis["is_vulnerable"],
                "evidence": analysis["evidence"],
                "language": "JavaScript",
            }
        )


# ============ Java 测试工具 ============

class JavaTestTool(BaseLanguageTestTool):
    """Java 代码测试工具"""

    LANGUAGE_NAME = "Java"
    FILE_EXTENSION = ".java"

    @property
    def name(self) -> str:
        return "java_test"

    @property
    def description(self) -> str:
        return """在沙箱中测试 Java 代码，支持模拟 Servlet 请求参数。

输入:
- code: Java 代码（与 file_path 二选一）
- file_path: 项目中的 Java 文件路径
- params: 模拟参数，如 {"cmd": "whoami"}
- timeout: 超时秒数

示例:
{"code": "Runtime.getRuntime().exec(args[0])", "params": {"arg": "whoami"}}

注意: Java 代码会被包装在 main 方法中执行。"""

    def _build_wrapper_code(self, code: str, params: Optional[Dict[str, str]]) -> str:
        """构建 Java 包装代码，增强 Mock 仿真度"""
        # 检测是否是完整类
        if "class " in code and "public static void main" in code:
            return code

        # 构建模拟请求参数
        param_init = ""
        if params:
            map_puts = "\n".join([f'        request.put("{k}", "{v}");' for k, v in params.items()])
            args_values = ", ".join([f'"{v}"' for v in params.values()])
            param_init = f"""
        // 模拟 Servlet/Spring 的请求参数 Map
        Map<String, String> request = new HashMap<>();
        {map_puts}
        String[] args = new String[]{{{args_values}}};
"""

        wrapper = f"""
import java.io.*;
import java.util.*;
import java.net.*;

public class Test {{
    public static void main(String[] argv) throws Exception {{
        {param_init}
        try {{
            {code}
        }} catch (Exception e) {{
            System.err.println("Execution Exception: " + e.getMessage());
            e.printStackTrace();
        }}
    }}
}}
"""
        return wrapper

    def _build_command(self, code: str) -> str:
        """构建 Java 编译与执行命令"""
        # Java 需要先编译再执行
        escaped_code = code.replace("\\", "\\\\").replace("'", "'\"'\"'")
        return (
            f"mkdir -p /tmp/test_java && "
            f"echo '{escaped_code}' > /tmp/test_java/Test.java && "
            f"javac /tmp/test_java/Test.java && "
            f"java -cp /tmp/test_java Test"
        )

    async def _execute(
        self,
        code: Optional[str] = None,
        file_path: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 60,  # Java 编译需要更长时间
        **kwargs
    ) -> ToolResult:
        """执行 Java 测试，适配函数级验证"""
        try:
            await self.sandbox_manager.initialize()
        except Exception as e:
            logger.warning(f"Sandbox init failed: {e}")

        if not self.sandbox_manager.is_available:
            return ToolResult(success=False, error="沙箱环境不可用")

        if file_path:
            code = self._read_file(file_path)
            if code is None:
                return ToolResult(success=False, error=f"文件不存在: {file_path}")

        if not code:
            return ToolResult(success=False, error="必须提供 code 或 file_path")

        wrapped_code = self._build_wrapper_code(code, params)
        command = self._build_command(wrapped_code)

        result = await self.sandbox_manager.execute_command(
            command=command,
            timeout=timeout,
            env=env_vars,
        )

        analysis = self._analyze_output(result, params)

        output_parts = [f"☕ Java 测试结果\n"]
        if file_path:
            output_parts.append(f"文件: {file_path}")
        if params:
            output_parts.append(f"模拟输入: {json.dumps(params, ensure_ascii=False)}")

        output_parts.append(f"状态: {'编译/执行成功' if result['exit_code'] == 0 else '执行失败'}")
        output_parts.append(f"\n退出码: {result['exit_code']}")

        if result["stdout"]:
            output_parts.append(f"\n标准输出:\n```\n{result['stdout'][:3000]}\n```")
        if result["stderr"]:
            label = "编译/运行错误" if result['exit_code'] != 0 else "标准错误"
            output_parts.append(f"\n{label}:\n```\n{result['stderr'][:1000]}\n```")

        if analysis["is_vulnerable"]:
            output_parts.append(f"\n🔴 **漏洞确认**: {analysis['evidence']}")
        else:
            output_parts.append(f"\n🟡 未能确认漏洞")

        return ToolResult(
            success=True,
            data="\n".join(output_parts),
            metadata={
                "exit_code": result["exit_code"],
                "is_vulnerable": analysis["is_vulnerable"],
                "evidence": analysis["evidence"],
                "language": "Java",
            }
        )


# ============ Go 测试工具 ============

class GoTestTool(BaseLanguageTestTool):
    """Go 代码测试工具"""

    LANGUAGE_NAME = "Go"
    FILE_EXTENSION = ".go"

    @property
    def name(self) -> str:
        return "go_test"

    @property
    def description(self) -> str:
        return """在沙箱中测试 Go 代码。

输入:
- code: Go 代码（与 file_path 二选一）
- file_path: 项目中的 Go 文件路径
- params: 模拟参数（作为命令行参数或环境变量）
- timeout: 超时秒数

示例:
{"code": "exec.Command(os.Args[1]).Output()", "params": {"cmd": "whoami"}}"""

    def _build_wrapper_code(self, code: str, params: Optional[Dict[str, str]]) -> str:
        """构建 Go 包装代码，处理未使用导入报错并增强 Mock"""
        # 检测是否是完整包
        if "package main" in code and "func main()" in code:
            return code

        imports = ["fmt", "os", "os/exec", "io", "net/http"]
        if "exec." in code:
            imports.append("os/exec")
        if "http." in code:
            imports.append("net/http")
        if "io" in code:
            imports.append("io")

        imports_str = "\n".join([f'    "{imp}"' for imp in imports])
        unused_placeholders = "\n".join([f'    _ = {imp.split("/")[-1]}.Args' if "os" in imp else f'    _ = {imp.split("/")[-1]}.EOF' if "io" in imp else "" for imp in imports if "/" not in imp or "os/" in imp])
        # 针对 net/http 特殊处理
        unused_placeholders += '\n    _ = http.MethodGet'

        # 模拟参数
        param_code = ""
        if params:
            args = ["program"] + list(params.values())
            args_str = ', '.join([f'"{a}"' for a in args])
            param_code += f'    os.Args = []string{{{args_str}}}\n'
            # param_code = f"    os.Args = []string{{{', '.join([f'\"{a}\"' for a in args])}}}\n"
            for key, value in params.items():
                param_code += f'    os.Setenv("{key.upper()}", "{value}")\n'

        wrapper = f"""package main

import (
{imports_str}
)

func main() {{
// 强制占位防止 Unused Import 错误
{unused_placeholders}
// --- Mock 数据注入 ---
{param_code}
// --- 用户代码开始 ---
    {code}
}}
"""
        return wrapper

    def _build_command(self, code: str) -> str:
        """构建 Go 执行命令"""
        escaped_code = code.replace("\\", "\\\\").replace("'", "'\"'\"'")
        return (
            f"mkdir -p /tmp/go_test && "
            f"echo '{escaped_code}' > /tmp/go_test/main.go && "
            f"cd /tmp/go_test && go run main.go"
        )

    async def _execute(
        self,
        code: Optional[str] = None,
        file_path: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 60,
        **kwargs
    ) -> ToolResult:
        """执行 Go 测试，适配命令执行与逻辑验证"""
        try:
            await self.sandbox_manager.initialize()
        except Exception as e:
            logger.warning(f"Sandbox init failed: {e}")

        if not self.sandbox_manager.is_available:
            return ToolResult(success=False, error="沙箱环境不可用")

        if file_path:
            code = self._read_file(file_path)
            if code is None:
                return ToolResult(success=False, error=f"文件不存在: {file_path}")

        if not code:
            return ToolResult(success=False, error="必须提供 code 或 file_path")

        wrapped_code = self._build_wrapper_code(code, params)
        command = self._build_command(wrapped_code)

        result = await self.sandbox_manager.execute_command(
            command=command,
            timeout=timeout,
            env=env_vars,
        )

        analysis = self._analyze_output(result, params)

        output_parts = [f"🔵 Go 测试结果\n"]
        if file_path:
            output_parts.append(f"文件: {file_path}")
        if params:
            output_parts.append(f"参数: {json.dumps(params, ensure_ascii=False)}")

        output_parts.append(f"状态: {'运行成功' if result['exit_code'] == 0 else '编译或执行失败'}")
        output_parts.append(f"\n退出码: {result['exit_code']}")

        if result["stdout"]:
            output_parts.append(f"\n标准输出:\n```\n{result['stdout'][:3000]}\n```")
        if result["stderr"]:
            output_parts.append(f"\n标准错误/编译信息:\n```\n{result['stderr'][:1000]}\n```")

        if analysis["is_vulnerable"]:
            output_parts.append(f"\n🔴 **漏洞确认**: {analysis['evidence']}")
        else:
            output_parts.append(f"\n🟡 未能确认漏洞")

        return ToolResult(
            success=True,
            data="\n".join(output_parts),
            metadata={
                "exit_code": result["exit_code"],
                "is_vulnerable": analysis["is_vulnerable"],
                "evidence": analysis["evidence"],
                "language": "Go",
            }
        )


# ============ Ruby 测试工具 ============

class RubyTestInput(LanguageTestInput):
    """Ruby 测试输入"""
    rails_mode: bool = Field(default=False, description="是否模拟 Rails 请求环境")


class RubyTestTool(BaseLanguageTestTool):
    """Ruby 代码测试工具"""

    LANGUAGE_NAME = "Ruby"
    LANGUAGE_CMD = "ruby"
    FILE_EXTENSION = ".rb"

    @property
    def name(self) -> str:
        return "ruby_test"

    @property
    def description(self) -> str:
        return """在沙箱中测试 Ruby 代码，支持模拟 Rails 请求参数。

输入:
- code: Ruby 代码（与 file_path 二选一）
- file_path: 项目中的 Ruby 文件路径
- params: 模拟参数，如 {"cmd": "whoami"}
- rails_mode: 是否模拟 Rails params
- timeout: 超时秒数

示例:
1. Rails 模式: {"file_path": "controller.rb", "params": {"cmd": "id"}, "rails_mode": true}
2. 普通模式: {"code": "system(ARGV[0])", "params": {"cmd": "whoami"}}"""

    @property
    def args_schema(self):
        return RubyTestInput

    def _build_wrapper_code(self, code: str, params: Optional[Dict[str, str]],
                           rails_mode: bool = False) -> str:
        """构建 Ruby 包装代码"""
        wrapper_parts = []

        if params:
            if rails_mode:
                # 模拟 Rails params
                params_ruby = "{ " + ", ".join([f'"{k}" => "{v}"' for k, v in params.items()]) + " }"
                wrapper_parts.append(f"""
class HashWithIndifferentAccess < Hash
  def [](key)
    super(key.to_s) || super(key.to_sym)
  end
end

def params
  @params ||= HashWithIndifferentAccess.new.merge({params_ruby})
end

class Request
  attr_accessor :params, :method, :path
  def initialize(p)
    @params = p
    @method = 'GET'
    @path = '/'
  end
end

request = Request.new(params)
""")
            else:
                # 普通模式
                for i, (key, value) in enumerate(params.items()):
                    wrapper_parts.append(f'ARGV[{i}] = "{value}"')
                    wrapper_parts.append(f'ENV["{key.upper()}"] = "{value}"')

        wrapper_parts.append(code)
        return "\n".join(wrapper_parts)

    def _build_command(self, code: str) -> str:
        """构建 Ruby 执行命令"""
        escaped_code = code.replace("'", "'\"'\"'")
        return f"ruby -e '{escaped_code}'"

    async def _execute(
        self,
        code: Optional[str] = None,
        file_path: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        rails_mode: bool = False,
        **kwargs
    ) -> ToolResult:
        """执行 Ruby 测试"""
        try:
            await self.sandbox_manager.initialize()
        except Exception as e:
            logger.warning(f"Sandbox init failed: {e}")

        if not self.sandbox_manager.is_available:
            return ToolResult(success=False, error="沙箱环境不可用")

        if file_path:
            code = self._read_file(file_path)
            if code is None:
                return ToolResult(success=False, error=f"文件不存在: {file_path}")

        if not code:
            return ToolResult(success=False, error="必须提供 code 或 file_path")

        wrapped_code = self._build_wrapper_code(code, params, rails_mode)
        command = self._build_command(wrapped_code)

        result = await self.sandbox_manager.execute_command(
            command=command,
            timeout=timeout,
            env=env_vars,
        )

        analysis = self._analyze_output(result, params)

        output_parts = [f"💎 Ruby 测试结果\n"]
        if file_path:
            output_parts.append(f"文件: {file_path}")
        if rails_mode:
            output_parts.append("模式: Rails")
        if params:
            output_parts.append(f"参数: {json.dumps(params, ensure_ascii=False)}")

        output_parts.append(f"\n退出码: {result['exit_code']}")

        if result["stdout"]:
            output_parts.append(f"\n输出:\n```\n{result['stdout'][:3000]}\n```")
        if result["stderr"]:
            output_parts.append(f"\n错误:\n```\n{result['stderr'][:1000]}\n```")

        if analysis["is_vulnerable"]:
            output_parts.append(f"\n🔴 **漏洞确认**: {analysis['evidence']}")
        else:
            output_parts.append(f"\n🟡 未能确认漏洞")

        return ToolResult(
            success=True,
            data="\n".join(output_parts),
            metadata={
                "exit_code": result["exit_code"],
                "is_vulnerable": analysis["is_vulnerable"],
                "evidence": analysis["evidence"],
                "language": "Ruby",
            }
        )


# ============ Bash/Shell 测试工具 ============

class ShellTestTool(BaseLanguageTestTool):
    """Shell/Bash 脚本测试工具"""

    LANGUAGE_NAME = "Shell"
    LANGUAGE_CMD = "bash"
    FILE_EXTENSION = ".sh"

    @property
    def name(self) -> str:
        return "shell_test"

    @property
    def description(self) -> str:
        return """在沙箱中测试 Shell/Bash 脚本。

输入:
- code: Shell 代码（与 file_path 二选一）
- file_path: 项目中的 Shell 脚本路径
- params: 模拟参数（作为位置参数 $1, $2... 或环境变量）
- timeout: 超时秒数

示例:
{"code": "eval $1", "params": {"1": "whoami"}}"""

    def _build_wrapper_code(self, code: str, params: Optional[Dict[str, str]]) -> str:
        """构建 Shell 包装代码"""
        wrapper_parts = ["#!/bin/bash"]

        if params:
            # 分离位置参数 (数字键) 和环境变量 (字母键)
            positional_args = {}
            env_vars = {}
            for key, value in params.items():
                # 设置位置参数和环境变量
                if key.isdigit():
                    # 位置参数需要特殊处理
                    positional_args[int(key)] = value
                else:
                    env_vars[key.upper()] = value
                    
            # 1. 注入环境变量
            for key, value in env_vars.items():
                # 对值进行转义，防止双引号注入
                safe_val = value.replace('"', '\\"')
                wrapper_parts.append(f'export {key}="{safe_val}"')
            # 2. 注入位置参数 ($1, $2...)
            if positional_args:
                # 按照数字顺序排列参数
                max_idx = max(positional_args.keys())
                args_list = []
                for i in range(1, max_idx + 1):
                    # 如果中间有缺失的数字，补空字符串
                    val = positional_args.get(i, "")
                    safe_arg = val.replace('"', '\\"')
                    args_list.append(f'"{safe_arg}"')
                
                # set -- "arg1" "arg2" 会重置当前 shell 的 $1, $2...
                wrapper_parts.append(f"set -- {' '.join(args_list)}")

        wrapper_parts.append("# --- User Code Start ---")
        wrapper_parts.append(code)
        return "\n".join(wrapper_parts)

    def _build_command(self, code: str) -> str:
        """构建 Shell 执行命令"""
        # 对代码中的反斜杠和单引号进行转义
        escaped_code = code.replace("\\", "\\\\").replace("'", "'\"'\"'")
        # 写入临时脚本并执行，这样比直接 bash -c 更稳定
        return (
            f"mkdir -p /tmp/shell_test && "
            f"echo '{escaped_code}' > /tmp/shell_test/test.sh && "
            f"bash /tmp/shell_test/test.sh"
        )
    async def _execute(
        self,
        code: Optional[str] = None,
        file_path: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 30,
        **kwargs
    ) -> ToolResult:
        """执行 Shell 测试，适配脚本级验证场景"""
        try:
            await self.sandbox_manager.initialize()
        except Exception as e:
            logger.warning(f"Sandbox init failed: {e}")

        if not self.sandbox_manager.is_available:
            return ToolResult(success=False, error="沙箱环境不可用")

        if file_path:
            code = self._read_file(file_path)
            if code is None:
                return ToolResult(success=False, error=f"文件不存在: {file_path}")

        if not code:
            return ToolResult(success=False, error="必须提供 code 或 file_path")

        wrapped_code = self._build_wrapper_code(code, params)
        command = self._build_command(wrapped_code)

        result = await self.sandbox_manager.execute_command(
            command=command,
            timeout=timeout,
            env=env_vars,
        )

        analysis = self._analyze_output(result, params)

        output_parts = [f"🐚 Shell 测试结果\n"]
        if file_path: output_parts.append(f"脚本: {file_path}")
        if params: output_parts.append(f"模拟参数: {json.dumps(params, ensure_ascii=False)}")
        
        output_parts.append(f"状态: {'执行成功' if result['exit_code'] == 0 else '执行失败'}")
        output_parts.append(f"退出码: {result['exit_code']}")

        if result["stdout"]:
            output_parts.append(f"\n标准输出:\n```\n{result['stdout'][:3000]}\n```")
        if result["stderr"]:
            output_parts.append(f"\n标准错误:\n```\n{result['stderr'][:1000]}\n```")

        if analysis["is_vulnerable"]:
            output_parts.append(f"\n🔴 **漏洞确认**: {analysis['evidence']}")
        else:
            output_parts.append(f"\n🟡 未能确认漏洞")

        return ToolResult(
            success=True,
            data="\n".join(output_parts),
            metadata={
                "exit_code": result["exit_code"],
                "is_vulnerable": analysis["is_vulnerable"],
                "evidence": analysis["evidence"],
                "language": "Shell",
            }
        )


# ============ 通用多语言测试工具 ============

class UniversalCodeTestInput(BaseModel):
    """通用代码测试输入"""
    language: str = Field(..., description="编程语言: php, python, javascript, java, go, ruby, shell")
    code: Optional[str] = Field(default=None, description="要执行的代码")
    file_path: Optional[str] = Field(default=None, description="文件路径")
    params: Optional[Dict[str, str]] = Field(default=None, description="模拟参数")
    framework_mode: Optional[str] = Field(default=None, description="框架模式: flask, django, express, rails")
    timeout: int = Field(default=30, description="超时秒数")


class UniversalCodeTestTool(AgentTool):
    """通用多语言代码测试工具 - 已对齐统一参数名与 Mock 逻辑"""

    def __init__(self, sandbox_manager: Optional[SandboxManager] = None, project_root: str = "."):
        super().__init__()
        self.sandbox_manager = sandbox_manager or SandboxManager()
        self.project_root = project_root

        # 初始化所有语言测试器，确保它们共享同一个沙箱管理器
        self._testers = {
            "php": PhpTestTool(self.sandbox_manager, project_root),
            "python": PythonTestTool(self.sandbox_manager, project_root),
            "javascript": JavaScriptTestTool(self.sandbox_manager, project_root),
            "js": JavaScriptTestTool(self.sandbox_manager, project_root),
            "node": JavaScriptTestTool(self.sandbox_manager, project_root),
            "java": JavaTestTool(self.sandbox_manager, project_root),
            "go": GoTestTool(self.sandbox_manager, project_root),
            "golang": GoTestTool(self.sandbox_manager, project_root),
            "ruby": RubyTestTool(self.sandbox_manager, project_root),
            "rb": RubyTestTool(self.sandbox_manager, project_root),
            "shell": ShellTestTool(self.sandbox_manager, project_root),
            "bash": ShellTestTool(self.sandbox_manager, project_root),
        }

    @property
    def name(self) -> str:
        # 对齐 universal_code_test.md 中的外部标识符
        return "universal_code_test"

    @property
    def description(self) -> str:
        return """通用多语言代码测试工具，支持通过统一接口验证多语言漏洞。

输入:
- language: 编程语言 (php, python, javascript, java, go, ruby, shell)
- code: 代码内容
- params: 模拟请求参数 (自动注入 GET/POST/REQUEST)
- framework_mode: 框架模式 (flask, django, express, rails)
- timeout: 超时秒数"""

    @property
    def args_schema(self):
        return UniversalCodeTestInput

    async def _execute(
        self,
        language: str,
        code: Optional[str] = None,
        file_path: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
        framework_mode: Optional[str] = None,
        timeout: int = 30,
        **kwargs
    ) -> ToolResult:
        """执行通用代码测试并转发至对应语言测试器"""
        language = language.lower().strip()

        tester = self._testers.get(language)
        if not tester:
            return ToolResult(
                success=False,
                error=f"不支持的语言: {language}。支持: {list(self._testers.keys())}",
            )

        # 核心转发参数：确保参数名与子工具修改后的 _execute 签名完全一致
        test_kwargs = {
            "code": code,           # 统一使用 code
            "file_path": file_path,
            "params": params,       # 统一使用 params，触发子工具 Mock 注入
            "timeout": timeout,
        }

        # 处理框架模式映射：将 framework_mode 转换为子工具的布尔开关
        if framework_mode:
            fm = framework_mode.lower()
            if fm == "flask":
                test_kwargs["flask_mode"] = True
            elif fm == "django":
                test_kwargs["django_mode"] = True
            elif fm == "express":
                test_kwargs["express_mode"] = True
            elif fm == "rails":
                test_kwargs["rails_mode"] = True

        # 调用对应语言子工具的 _execute 方法
        return await tester._execute(**test_kwargs)
