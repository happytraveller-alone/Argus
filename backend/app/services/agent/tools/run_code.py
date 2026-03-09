"""
通用代码执行工具 - LLM 驱动的漏洞验证

核心理念：
- LLM 是验证的大脑，工具只提供执行能力
- 不硬编码 payload、检测规则
- LLM 自己决定测试策略、编写测试代码、分析结果

使用场景：
- LLM 编写 Fuzzing Harness 进行局部测试
- LLM 构造 PoC 验证漏洞
- LLM 编写 mock 代码隔离测试函数
"""

import asyncio
import logging
import os
import tempfile
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

from .base import AgentTool, ToolResult
from .sandbox_tool import SandboxManager, SandboxConfig

logger = logging.getLogger(__name__)


class RunCodeInput(BaseModel):
    """代码执行输入"""
    code: str = Field(..., description="要执行的代码")
    language: str = Field(default="python", description="编程语言: python, php, javascript, ruby, go, java, bash")
    timeout: int = Field(default=60, description="超时时间（秒），复杂测试可设置更长")
    description: str = Field(default="", description="简短描述这段代码的目的（用于日志）")


class RunCodeTool(AgentTool):
    """
    通用代码执行工具

    让 LLM 自由编写测试代码，在沙箱中执行。

    LLM 可以：
    - 编写 Fuzzing Harness 隔离测试单个函数
    - 构造 mock 对象模拟依赖
    - 设计各种 payload 进行测试
    - 分析执行结果判断漏洞

    工具不做任何假设，完全由 LLM 控制测试逻辑。
    """

    def __init__(self, sandbox_manager: Optional[SandboxManager] = None, project_root: str = "."):
        super().__init__()
        # 使用更宽松的沙箱配置
        config = SandboxConfig(
            timeout=120,
            memory_limit="1g",  # 更大内存
        )
        self.sandbox_manager = sandbox_manager or SandboxManager(config)
        self.project_root = project_root

    @property
    def name(self) -> str:
        return "run_code"

    @property
    def description(self) -> str:
        return """🔥 通用代码执行工具 - 在沙箱中运行你编写的测试代码

这是你进行漏洞验证的核心工具。你可以：
1. 编写 Fuzzing Harness 隔离测试单个函数
2. 构造 mock 对象模拟数据库、HTTP 请求等依赖
3. 设计各种 payload 进行漏洞测试
4. 编写完整的 PoC 验证脚本

输入：
- code: 你编写的测试代码（完整可执行）
- language: python, php, javascript, ruby, go, java, bash
- timeout: 超时秒数（默认60，复杂测试可设更长）
- description: 简短描述代码目的

支持的语言和执行方式：
- python: python3 -c 'code'
- php: php -r 'code'  (注意：不需要 <?php 标签)
- javascript: node -e 'code'
- ruby: ruby -e 'code'
- go: go run (需写完整 package main)
- java: javac + java (需写完整 class)
- bash: bash -c 'code'

示例 - 命令注入 Fuzzing Harness:
```python
# 提取目标函数并构造测试
import os

# Mock os.system 来检测是否被调用
executed_commands = []
original_system = os.system
def mock_system(cmd):
    print(f"[DETECTED] os.system called: {cmd}")
    executed_commands.append(cmd)
    return 0
os.system = mock_system

# 目标函数（从项目代码复制）
def vulnerable_function(user_input):
    os.system(f"echo {user_input}")

# Fuzzing 测试
payloads = ["; id", "| whoami", "$(cat /etc/passwd)", "`id`"]
for payload in payloads:
    print(f"\\nTesting payload: {payload}")
    executed_commands.clear()
    try:
        vulnerable_function(payload)
        if executed_commands:
            print(f"[VULN] Command injection detected!")
    except Exception as e:
        print(f"Error: {e}")
```

⚠️ 重要提示：
- 代码在 Docker 沙箱中执行，与真实环境隔离
- 你需要自己 mock 依赖（数据库、HTTP、文件系统等）
- 你需要自己设计 payload 和检测逻辑
- 你需要自己分析输出判断漏洞是否存在"""

    @property
    def args_schema(self):
        return RunCodeInput

    async def _execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = 60,
        description: str = "",
        **kwargs
    ) -> ToolResult:
        """执行用户编写的代码"""

        # 初始化沙箱
        try:
            await self.sandbox_manager.initialize()
        except Exception as e:
            logger.warning(f"Sandbox init failed: {e}")

        if not self.sandbox_manager.is_available:
            return ToolResult(
                success=False,
                error="沙箱环境不可用 (Docker 未运行)",
                data="请确保 Docker 已启动。如果无法使用沙箱，你可以通过静态分析代码来验证漏洞。"
            )

        # 构建执行命令
        language = language.lower().strip()
        command = self._build_command(code, language)

        if command is None:
            return ToolResult(
                success=False,
                error=f"不支持的语言: {language}",
                data=f"支持的语言: python, php, javascript, ruby, go, java, bash"
            )

        # 在沙箱中执行
        result = await self.sandbox_manager.execute_command(
            command=command,
            timeout=timeout,
        )

        # 格式化输出
        output_parts = [f"🔬 代码执行结果"]
        if description:
            output_parts.append(f"目的: {description}")
        output_parts.append(f"语言: {language}")
        if result.get("image"):
            output_parts.append(f"镜像: {result['image']}")
        if result.get("image_candidates"):
            output_parts.append(f"镜像候选: {', '.join(result['image_candidates'])}")
        output_parts.append(f"退出码: {result['exit_code']}")

        if result.get("stdout"):
            stdout = result["stdout"]
            if len(stdout) > 5000:
                stdout = stdout[:5000] + f"\n... (截断，共 {len(result['stdout'])} 字符)"
            output_parts.append(f"\n输出:\n```\n{stdout}\n```")

        if result.get("stderr"):
            stderr = result["stderr"]
            if len(stderr) > 2000:
                stderr = stderr[:2000] + "\n... (截断)"
            output_parts.append(f"\n错误输出:\n```\n{stderr}\n```")

        if result.get("error"):
            output_parts.append(f"\n执行错误: {result['error']}")

        # 提示 LLM 分析结果
        output_parts.append("\n---")
        output_parts.append("请根据上述输出分析漏洞是否存在。")

        # 🔥 修复：当工具执行失败时，确保 error 字段包含有意义的错误信息
        # 如果 result['error'] 为空但执行失败，从 stderr 中提取错误
        error_message = result.get("error")
        if not error_message and not result.get("success", False):
            # 执行失败但没有 error 字段，尝试从 stderr 提取
            stderr = result.get("stderr", "")
            if stderr:
                # 取 stderr 的前 500 字符作为 error 摘要
                error_message = stderr[:500] if len(stderr) > 500 else stderr
            elif result.get("exit_code", 0) != 0:
                error_message = f"代码执行失败，退出码: {result.get('exit_code')}"

        return ToolResult(
            success=result.get("success", False),
            data="\n".join(output_parts),
            error=error_message,  # 确保 error 字段有值
            metadata={
                "language": language,
                "exit_code": result.get("exit_code", -1),
                "stdout_length": len(result.get("stdout", "")),
                "stderr_length": len(result.get("stderr", "")),
                "image": result.get("image"),
                "image_candidates": result.get("image_candidates") or [],
            }
        )

    def _build_command(self, code: str, language: str) -> Optional[str]:
        """根据语言构建执行命令"""

        # 转义单引号的通用方法
        def escape_for_shell(s: str) -> str:
            return s.replace("'", "'\"'\"'")

        if language == "python":
            # 在 /tmp 执行，避免工作目录权限问题（__pycache__ 写入等）
            escaped = escape_for_shell(code)
            return f"cd /tmp && python3 -c '{escaped}'"

        elif language == "php":
            # PHP: php -r 不需要 <?php 标签
            # 在 /tmp 执行，避免工作目录权限问题（session、临时文件等）
            clean_code = code.strip()
            if clean_code.startswith("<?php"):
                clean_code = clean_code[5:].strip()
            if clean_code.startswith("<?"):
                clean_code = clean_code[2:].strip()
            if clean_code.endswith("?>"):
                clean_code = clean_code[:-2].strip()
            escaped = escape_for_shell(clean_code)
            return f"cd /tmp && php -r '{escaped}'"

        elif language in ["javascript", "js", "node"]:
            # 在 /tmp 执行，避免工作目录权限问题（模块缓存等）
            escaped = escape_for_shell(code)
            return f"cd /tmp && node -e '{escaped}'"

        elif language == "ruby":
            # 在 /tmp 执行，避免工作目录权限问题（字节码缓存等）
            escaped = escape_for_shell(code)
            return f"cd /tmp && ruby -e '{escaped}'"

        elif language == "bash":
            # 在 /tmp 执行，避免工作目录权限问题（用户代码可能创建文件）
            escaped = escape_for_shell(code)
            return f"cd /tmp && bash -c '{escaped}'"

        elif language == "go":
            # Go 需要完整的 package main
            # 切换到 /tmp 目录执行，避免工作目录权限问题
            escaped = escape_for_shell(code).replace("\\", "\\\\")
            return f"cd /tmp && echo '{escaped}' > main.go && go run main.go"

        elif language == "java":
            # Java 需要完整的 class
            # 切换到 /tmp 目录执行，避免工作目录权限问题
            escaped = escape_for_shell(code).replace("\\", "\\\\")
            # 提取类名
            import re
            class_match = re.search(r'public\s+class\s+(\w+)', code)
            class_name = class_match.group(1) if class_match else "Test"
            return f"cd /tmp && echo '{escaped}' > {class_name}.java && javac {class_name}.java && java {class_name}"

        return None


class ExtractFunctionInput(BaseModel):
    """函数提取输入"""
    file_path: str = Field(..., description="源文件路径")
    function_name: str = Field(..., description="要提取的函数名")
    include_imports: bool = Field(default=True, description="是否包含 import 语句")


class ExtractFunctionTool(AgentTool):
    """
    函数提取工具

    从源文件中提取指定函数及其依赖，用于构建 Fuzzing Harness
    """

    def __init__(self, project_root: str = "."):
        super().__init__()
        self.project_root = project_root

    @property
    def name(self) -> str:
        return "extract_function"

    @property
    def description(self) -> str:
        return """从源文件中提取指定函数的代码

用于构建 Fuzzing Harness 时获取目标函数代码。

输入：
- file_path: 源文件路径
- function_name: 要提取的函数名
- include_imports: 是否包含文件开头的 import 语句（默认 true）

返回：
- 函数代码
- 相关的 import 语句
- 函数参数列表

示例：
{"file_path": "app/api.py", "function_name": "process_command"}"""

    @property
    def args_schema(self):
        return ExtractFunctionInput

    async def _execute(
        self,
        file_path: str,
        function_name: str,
        include_imports: bool = True,
        **kwargs
    ) -> ToolResult:
        """提取函数代码"""
        full_path = os.path.join(self.project_root, file_path)
        if not os.path.exists(full_path):
            return ToolResult(success=False, error=f"文件不存在: {file_path}")

        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        # 检测语言
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".py":
            result = self._extract_python(code, function_name, include_imports)
        elif ext == ".php":
            result = self._extract_php(code, function_name)
        elif ext in [".js", ".ts"]:
            result = self._extract_javascript(code, function_name)
        elif ext in [
            ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh",
            ".java", ".cs", ".kt", ".kts",
        ]:
            result = self._extract_c_like(code, function_name, include_imports)
            if not result.get("success"):
                result = self._extract_generic(code, function_name)
        else:
            result = self._extract_generic(code, function_name)

        if result["success"]:
            output_parts = [f"📦 函数提取结果\n"]
            output_parts.append(f"文件: {file_path}")
            output_parts.append(f"函数: {function_name}")

            if result.get("imports"):
                output_parts.append(f"\n相关 imports:\n```\n{result['imports']}\n```")

            if result.get("parameters"):
                output_parts.append(f"\n参数: {', '.join(result['parameters'])}")

            output_parts.append(f"\n函数代码:\n```\n{result['code']}\n```")

            output_parts.append("\n---")
            output_parts.append("你现在可以使用这段代码构建 Fuzzing Harness")

            return ToolResult(
                success=True,
                data="\n".join(output_parts),
                metadata=result
            )
        else:
            return ToolResult(
                success=False,
                error=result.get("error", "提取失败"),
                data=f"无法提取函数 '{function_name}'。你可以使用 read_file 工具直接读取文件，手动定位函数代码。"
            )

    def _extract_python(self, code: str, function_name: str, include_imports: bool) -> Dict:
        """提取 Python 函数"""
        import ast

        try:
            tree = ast.parse(code)
        except SyntaxError:
            # 降级到正则提取
            return self._extract_generic(code, function_name)

        # 收集 imports
        imports = []
        if include_imports:
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.append(ast.unparse(node))
                elif isinstance(node, ast.ImportFrom):
                    imports.append(ast.unparse(node))

        # 查找函数
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == function_name:
                    lines = code.split('\n')
                    func_code = '\n'.join(lines[node.lineno - 1:node.end_lineno])
                    params = [arg.arg for arg in node.args.args]

                    return {
                        "success": True,
                        "code": func_code,
                        "imports": '\n'.join(imports) if imports else None,
                        "parameters": params,
                        "line_start": node.lineno,
                        "line_end": node.end_lineno,
                    }

        return {"success": False, "error": f"未找到函数 '{function_name}'"}

    def _extract_php(self, code: str, function_name: str) -> Dict:
        """提取 PHP 函数（支持类方法、独立函数）"""
        import re

        # 支持类方法（访问修饰符 + static/abstract/final）和独立函数
        # 匹配: public static function name(...): returnType { 或 function name(...) {
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

    def _extract_javascript(self, code: str, function_name: str) -> Dict:
        """提取 JavaScript 函数"""
        import re

        patterns = [
            rf'function\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{',
            rf'(?:const|let|var)\s+{re.escape(function_name)}\s*=\s*function\s*\([^)]*\)\s*\{{',
            rf'(?:const|let|var)\s+{re.escape(function_name)}\s*=\s*\([^)]*\)\s*=>\s*\{{',
            rf'async\s+function\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{',
        ]

        for pattern in patterns:
            match = re.search(pattern, code)
            if match:
                start_pos = match.start()
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

                return {
                    "success": True,
                    "code": func_code,
                }

        return {"success": False, "error": f"未找到函数 '{function_name}'"}

    @staticmethod
    def _find_matching_delimiter(code: str, start_pos: int, opener: str, closer: str) -> int:
        """查找匹配的结束分隔符（忽略字符串/注释）。"""
        if start_pos < 0 or start_pos >= len(code) or code[start_pos] != opener:
            return -1

        depth = 0
        i = start_pos
        in_single = False
        in_double = False
        in_line_comment = False
        in_block_comment = False
        escape = False

        while i < len(code):
            ch = code[i]
            nxt = code[i + 1] if i + 1 < len(code) else ""

            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
                i += 1
                continue

            if in_block_comment:
                if ch == "*" and nxt == "/":
                    in_block_comment = False
                    i += 2
                    continue
                i += 1
                continue

            if in_single:
                if ch == "\\" and not escape:
                    escape = True
                    i += 1
                    continue
                if ch == "'" and not escape:
                    in_single = False
                escape = False
                i += 1
                continue

            if in_double:
                if ch == "\\" and not escape:
                    escape = True
                    i += 1
                    continue
                if ch == '"' and not escape:
                    in_double = False
                escape = False
                i += 1
                continue

            if ch == "/" and nxt == "/":
                in_line_comment = True
                i += 2
                continue
            if ch == "/" and nxt == "*":
                in_block_comment = True
                i += 2
                continue
            if ch == "'":
                in_single = True
                i += 1
                continue
            if ch == '"':
                in_double = True
                i += 1
                continue

            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    return i

            i += 1

        return -1

    @staticmethod
    def _skip_c_whitespace_and_comments(code: str, start_pos: int) -> int:
        pos = start_pos
        while pos < len(code):
            if code[pos].isspace():
                pos += 1
                continue
            if code.startswith("//", pos):
                newline = code.find("\n", pos + 2)
                if newline == -1:
                    return len(code)
                pos = newline + 1
                continue
            if code.startswith("/*", pos):
                end_comment = code.find("*/", pos + 2)
                if end_comment == -1:
                    return len(code)
                pos = end_comment + 2
                continue
            break
        return pos

    @staticmethod
    def _extract_c_parameters(params_block: str) -> list[str]:
        import re

        params: list[str] = []
        current: list[str] = []
        depth = 0
        for ch in params_block:
            if ch == "," and depth == 0:
                segment = "".join(current).strip()
                if segment:
                    params.append(segment)
                current = []
                continue
            if ch == "(":
                depth += 1
            elif ch == ")" and depth > 0:
                depth -= 1
            current.append(ch)

        tail = "".join(current).strip()
        if tail:
            params.append(tail)

        normalized: list[str] = []
        for raw in params:
            clean = re.sub(r"/\*[\s\S]*?\*/", "", raw).strip()
            if not clean or clean == "void":
                continue
            clean = clean.split("=")[0].strip()
            name_match = re.search(r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*$", clean)
            normalized.append(name_match.group(1) if name_match else clean)

        return normalized

    def _extract_c_like(self, code: str, function_name: str, include_imports: bool) -> Dict:
        """提取 C/C++ 风格函数定义。"""
        import re

        function_pattern = re.compile(rf"\b{re.escape(function_name)}\s*\(")

        for match in function_pattern.finditer(code):
            name_start = match.start()
            prev_idx = name_start - 1
            while prev_idx >= 0 and code[prev_idx].isspace():
                prev_idx -= 1
            if prev_idx >= 0 and code[prev_idx] in {".", ">"}:
                # Skip method calls like obj.fn(...) / ptr->fn(...)
                continue

            paren_pos = match.end() - 1
            close_paren = self._find_matching_delimiter(code, paren_pos, "(", ")")
            if close_paren == -1:
                continue

            body_start = self._skip_c_whitespace_and_comments(code, close_paren + 1)
            if body_start >= len(code) or code[body_start] != "{":
                continue

            body_end = self._find_matching_delimiter(code, body_start, "{", "}")
            if body_end == -1:
                continue

            # Try to include multi-line return type/qualifier lines above function name.
            signature_start = code.rfind("\n", 0, name_start) + 1
            while signature_start > 0:
                prev_line_end = signature_start - 1
                prev_line_start = code.rfind("\n", 0, prev_line_end) + 1
                prev_line = code[prev_line_start:prev_line_end].strip()
                if not prev_line:
                    break
                if prev_line.startswith("#") or prev_line.endswith(("{", "}", ";")):
                    break
                signature_start = prev_line_start

            func_code = code[signature_start:body_end + 1]
            imports = None
            if include_imports:
                include_lines = [
                    line.strip()
                    for line in code.splitlines()
                    if line.strip().startswith("#include")
                ]
                imports = "\n".join(include_lines) if include_lines else None

            parameters = self._extract_c_parameters(code[paren_pos + 1:close_paren])

            return {
                "success": True,
                "code": func_code,
                "imports": imports,
                "parameters": parameters,
                "line_start": code.count("\n", 0, signature_start) + 1,
                "line_end": code.count("\n", 0, body_end) + 1,
            }

        return {"success": False, "error": f"未找到函数 '{function_name}'"}

    def _extract_generic(self, code: str, function_name: str) -> Dict:
        """通用函数提取（正则）"""
        import re

        # 尝试多种模式
        patterns = [
            rf'def\s+{re.escape(function_name)}\s*\([^)]*\)\s*:',  # Python
            # PHP: 支持类方法（访问修饰符 + static）和独立函数，包含返回类型声明
            rf'(?:(?:public|protected|private|abstract|final)\s+)*(?:static\s+)?function\s+{re.escape(function_name)}\s*\([^{{;]*?\)(?:[^{{;]*?)(?:\{{|;)',
            rf'function\s+{re.escape(function_name)}\s*\([^)]*\)',  # PHP/JS 独立函数（简化版）
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
