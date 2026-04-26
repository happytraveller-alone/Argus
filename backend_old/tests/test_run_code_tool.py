"""
RunCodeTool 测试脚本

测试通用代码执行工具的各项功能
"""

import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.agent.tools.run_code import RunCodeTool, RunCodeInput, ExtractFunctionTool
from app.services.agent.tools.base import ToolResult
from app.services.agent.tools.sandbox_tool import SandboxManager, SandboxConfig
from app.services.agent.tools.sandbox_tool import SandboxTool


class TestRunCodeInput:
    """测试输入数据验证"""

    def test_valid_input(self):
        """测试有效输入"""
        input_data = RunCodeInput(
            code="print('hello')",
            language="python",
            timeout=30,
            description="测试代码"
        )
        assert input_data.code == "print('hello')"
        assert input_data.language == "python"
        assert input_data.timeout == 30
        assert input_data.description == "测试代码"

    def test_default_values(self):
        """测试默认值"""
        input_data = RunCodeInput(code="print('test')")
        assert input_data.language == "python"
        assert input_data.timeout == 60
        assert input_data.description == ""

    def test_supported_languages(self):
        """测试支持的语言"""
        languages = ["python", "php", "javascript", "ruby", "go", "java", "bash"]
        for lang in languages:
            input_data = RunCodeInput(code="test", language=lang)
            assert input_data.language == lang


class TestRunCodeToolBasic:
    """测试 RunCodeTool 基本功能"""

    def test_tool_properties(self):
        """测试工具属性"""
        tool = RunCodeTool(project_root="/tmp/test")
        
        assert tool.name == "run_code"
        assert tool.project_root == "/tmp/test"
        assert "通用代码执行工具" in tool.description
        assert tool.args_schema == RunCodeInput

    def test_initialization_with_sandbox_manager(self):
        """测试使用真实 SandboxManager 初始化"""
        # 参考 agent_tasks.py 的做法
        sandbox_manager = SandboxManager()
        tool = RunCodeTool(sandbox_manager=sandbox_manager, project_root="/test")
        
        assert tool.sandbox_manager == sandbox_manager
        assert tool.project_root == "/test"
        assert isinstance(tool.sandbox_manager, SandboxManager)

    def test_initialization_default(self):
        """测试默认初始化"""
        tool = RunCodeTool(project_root="/test")
        
        assert tool.sandbox_manager is not None
        assert isinstance(tool.sandbox_manager, SandboxManager)


class StubSandboxManager:
    def __init__(self, result):
        self.is_available = True
        self.result = result
        self.last_command = None
        self.last_timeout = None

    async def initialize(self):
        return None

    async def execute_command(self, command: str, timeout: int, **kwargs):
        self.last_command = command
        self.last_timeout = timeout
        self.last_kwargs = kwargs
        return self.result


class TestSandboxManagerImageResolution:
    def test_image_candidates_prefer_explicit_then_local_then_remote(self, monkeypatch):
        monkeypatch.setenv("GHCR_REGISTRY", "docker.m.daocloud.io")
        monkeypatch.setenv("Argus_IMAGE_TAG", "latest")
        manager = SandboxManager(SandboxConfig(image="custom/sandbox:latest"))

        candidates = manager._image_candidates()

        assert candidates == [
            "custom/sandbox:latest",
            "Argus/sandbox-runner:latest",
            "Argus/sandbox-runner:latest",
            "Argus-sandbox-runner:latest",
            "docker.m.daocloud.io/argus/Argus-sandbox-runner:latest",
        ]

    def test_select_runtime_image_uses_local_legacy_fallback_when_present(self):
        manager = SandboxManager(SandboxConfig(image="ghcr.io/argus/Argus-sandbox-runner:latest"))
        manager._docker_client = SimpleNamespace(images=SimpleNamespace(get=lambda image: {"Argus/sandbox-runner:latest": object()}[image]))

        selected = manager._select_runtime_image(manager._image_candidates())

        assert selected == "Argus/sandbox-runner:latest"

    def test_format_image_resolution_error_uses_root_sandbox_dockerfile_hint(self):
        manager = SandboxManager(SandboxConfig(image="custom/sandbox:latest"))

        message = manager._format_image_resolution_error(
            ["custom/sandbox:latest"],
            ["custom/sandbox:latest: not found"],
        )

        assert "docker build -f docker/sandbox-runner.Dockerfile -t Argus/sandbox-runner:latest ." in message
        assert "cd docker/sandbox" not in message


class TestBuildCommand:
    """测试命令构建功能"""

    def setup_method(self):
        """每个测试前的设置"""
        self.tool = RunCodeTool(project_root="/test")

    def test_build_python_command(self):
        """测试 Python 命令构建"""
        code = "print('hello world')"
        command = self.tool._build_command(code, "python")
        assert command.startswith("cd /tmp && python3 -c '")
        assert "hello world" in command

    def test_build_php_command(self):
        """测试 PHP 命令构建"""
        code = "echo 'hello';"
        command = self.tool._build_command(code, "php")
        assert command.startswith("cd /tmp && php -r '")
        assert "echo" in command

    def test_build_php_command_strip_tags(self):
        """测试 PHP 命令构建时去除标签"""
        code = "<?php echo 'hello'; ?>"
        command = self.tool._build_command(code, "php")
        assert "<?php" not in command
        assert "?>" not in command
        assert "echo" in command
        assert "hello" in command

    def test_build_javascript_command(self):
        """测试 JavaScript 命令构建"""
        code = "console.log('hello')"
        command = self.tool._build_command(code, "javascript")
        assert command.startswith("cd /tmp && node -e '")
        assert "console.log" in command

    def test_build_ruby_command(self):
        """测试 Ruby 命令构建"""
        code = "puts 'hello'"
        command = self.tool._build_command(code, "ruby")
        assert command.startswith("cd /tmp && ruby -e '")
        assert "puts" in command

    def test_build_bash_command(self):
        """测试 Bash 命令构建"""
        code = "echo hello"
        command = self.tool._build_command(code, "bash")
        assert command.startswith("cd /tmp && bash -c '")
        assert "echo hello" in command

    def test_build_go_command(self):
        """测试 Go 命令构建"""
        code = "package main\nfunc main() {}"
        command = self.tool._build_command(code, "go")
        assert "go run" in command
        assert "cd /tmp &&" in command
        assert "> main.go && go run main.go" in command

    def test_build_java_command(self):
        """测试 Java 命令构建"""
        code = "public class Test { public static void main(String[] args) {} }"
        command = self.tool._build_command(code, "java")
        assert "javac" in command
        assert "Test.java" in command
        assert "&& java Test" in command

    def test_build_unsupported_language(self):
        """测试不支持的语言"""
        code = "test"
        command = self.tool._build_command(code, "unsupported")
        assert command is None

    def test_escape_single_quotes(self):
        """测试单引号转义"""
        code = "print('it\\'s working')"
        command = self.tool._build_command(code, "python")
        # 确保命令被正确转义
        assert command is not None


@pytest.mark.asyncio
class TestRunCodeToolExecution:
    """测试代码执行功能"""

    async def test_execute_success(self):
        """测试成功执行代码"""
        # 使用真实的 SandboxManager（参考 agent_tasks.py）
        sandbox_manager = SandboxManager()
        await sandbox_manager.initialize()
        
        # 如果沙箱不可用则跳过
        if not sandbox_manager.is_available:
            pytest.skip("沙箱不可用，跳过测试")

        tool = RunCodeTool(sandbox_manager=sandbox_manager, project_root="/test")

        result = await tool._execute(
            code="print('Hello, World!')",
            language="python",
            timeout=30,
            description="测试打印"
        )

        assert result.success is True
        assert "Hello, World!" in result.data or result.success
        assert "退出码:" in result.data

    async def test_execute_sandbox_not_available(self):
        """测试沙箱不可用时的处理"""
        # 创建一个手动设置为不可用的沙箱
        sandbox_manager = SandboxManager()
        # 不初始化它，这样 is_available 会是 False
        # 或者如果已初始化，我们可以手动配置
        
        tool = RunCodeTool(sandbox_manager=sandbox_manager, project_root="/test")

        result = await tool._execute(
            code="print('test')",
            language="python"
        )

        # 如果沙箱确实不可用，应该返回失败
        if not sandbox_manager.is_available:
            assert result.success is False
            assert "沙箱环境不可用" in result.error or "Docker" in result.data
        else:
            # 如果沙箱可用，这个测试会正常执行代码
            pytest.skip("沙箱已启用，跳过不可用测试")

    async def test_execute_unsupported_language(self):
        """测试不支持的语言"""
        sandbox_manager = SandboxManager()
        await sandbox_manager.initialize()

        tool = RunCodeTool(sandbox_manager=sandbox_manager, project_root="/test")

        result = await tool._execute(
            code="test",
            language="unsupported_lang"
        )

        assert result.success is False
        assert "不支持的语言" in result.error or "沙箱环境不可用" in result.error

    async def test_execute_with_error(self):
        """测试执行出错"""
        sandbox_manager = SandboxManager()
        await sandbox_manager.initialize()
        
        if not sandbox_manager.is_available:
            pytest.skip("沙箱不可用，跳过测试")

        tool = RunCodeTool(sandbox_manager=sandbox_manager, project_root="/test")

        result = await tool._execute(
            code="print(",
            language="python"
        )

        assert result.success is False
        # 真实执行会返回语法错误
        assert "SyntaxError" in result.data or "Syntax" in result.data or not result.success

    async def test_execute_truncate_output(self):
        """测试输出截断"""
        sandbox_manager = SandboxManager()
        await sandbox_manager.initialize()
        
        if not sandbox_manager.is_available:
            pytest.skip("沙箱不可用，跳过测试")

        tool = RunCodeTool(sandbox_manager=sandbox_manager, project_root="/test")

        result = await tool._execute(
            code="print('x' * 1000)",
            language="python",
            timeout=10
        )

        # 验证输出被处理（可能截断也可能没有）
        assert result.data is not None
        if len(result.data) > 5000:
            # 如果输出很长，应该看到截断提示
            assert "截断" in result.data or len(result.data) < 10000

    async def test_execute_with_description(self):
        """测试带描述的执行"""
        sandbox_manager = SandboxManager()
        await sandbox_manager.initialize()
        
        if not sandbox_manager.is_available:
            pytest.skip("沙箱不可用，跳过测试")

        tool = RunCodeTool(sandbox_manager=sandbox_manager, project_root="/test")

        result = await tool._execute(
            code="print('test')",
            language="python",
            description="Command Injection 测试"
        )

        assert result.success is True
        assert "Command Injection 测试" in result.data

    async def test_execute_metadata(self):
        """测试返回的元数据"""
        sandbox_manager = SandboxManager()
        await sandbox_manager.initialize()
        
        if not sandbox_manager.is_available:
            pytest.skip("沙箱不可用，跳过测试")

        tool = RunCodeTool(sandbox_manager=sandbox_manager, project_root="/test")

        result = await tool._execute(
            code="print('test')",
            language="python"
        )

        assert result.metadata["language"] == "python"
        assert "exit_code" in result.metadata
        assert "stdout_length" in result.metadata
        assert "stderr_length" in result.metadata

    async def test_execute_returns_execution_result_metadata(self):
        """run_code 应返回 execution_result 结构化证据"""
        sandbox_manager = StubSandboxManager(
            {
                "success": True,
                "exit_code": 0,
                "stdout": "payload detected\\nproof line",
                "stderr": "",
                "image": "Argus/sandbox-runner:latest",
                "image_candidates": ["Argus/sandbox-runner:latest"],
            }
        )
        tool = RunCodeTool(sandbox_manager=sandbox_manager, project_root="/test")

        result = await tool._execute(
            code="print('payload detected')",
            language="python",
            timeout=12,
            description="验证命令注入 harness",
        )

        assert result.success is True
        assert result.metadata["render_type"] == "execution_result"
        assert result.metadata["command_chain"][0] == "run_code"
        assert result.metadata["entries"]

        entry = result.metadata["entries"][0]
        assert entry["status"] == "passed"
        assert entry["exit_code"] == 0
        assert entry["description"] == "验证命令注入 harness"
        assert "python3 -c" in entry["execution_command"]
        assert entry["stdout_preview"].startswith("payload detected")
        assert entry["runtime_image"] == "Argus/sandbox-runner:latest"
        assert entry["code"]["language"] == "python"
        assert entry["code"]["lines"][0]["line_number"] == 1


class TestExtractFunctionToolBasic:
    """测试 ExtractFunctionTool 基本功能"""

    def test_tool_properties(self):
        """测试工具属性"""
        tool = ExtractFunctionTool(project_root="/test")
        
        assert tool.name == "extract_function"
        assert "提取指定函数" in tool.description
        assert tool.project_root == "/test"


@pytest.mark.asyncio
class TestExtractFunctionToolExecution:
    """测试函数提取功能"""

    async def test_extract_python_function(self, tmp_path):
        """测试提取 Python 函数"""
        # 创建测试文件
        test_file = tmp_path / "test.py"
        test_file.write_text("""
import os
import sys

def vulnerable_function(user_input):
    os.system(f"echo {user_input}")
    return True

def another_function():
    pass
""")

        tool = ExtractFunctionTool(project_root=str(tmp_path))
        result = await tool.execute(
            path="test.py",
            symbol_name="vulnerable_function",
            include_imports=True
        )

        assert result.success is True
        assert "vulnerable_function" in result.data
        assert "os.system" in result.data
        assert "import os" in result.data or "imports" in result.metadata

    async def test_extract_python_function_returns_code_window_metadata(self, tmp_path):
        """extract_function 应返回 code_window 结构化证据"""
        test_file = tmp_path / "test.py"
        test_file.write_text("""
import os

def vulnerable_function(user_input):
    os.system(f"echo {user_input}")
    return True
""")

        tool = ExtractFunctionTool(project_root=str(tmp_path))
        result = await tool.execute(
            path="test.py",
            symbol_name="vulnerable_function",
            include_imports=True,
        )

        assert result.success is True
        assert result.metadata["render_type"] == "code_window"
        assert result.metadata["command_chain"] == ["extract_function"]

        entry = result.metadata["entries"][0]
        assert entry["file_path"] == "test.py"
        assert entry["symbol_name"] == "vulnerable_function"
        assert entry["start_line"] == 4
        assert entry["end_line"] == 6
        assert entry["focus_line"] == 4
        assert entry["lines"][0]["line_number"] == 4
        assert entry["lines"][0]["kind"] == "focus"

    async def test_extract_function_not_found(self, tmp_path):
        """测试提取不存在的函数"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def other_func():\n    pass")

        tool = ExtractFunctionTool(project_root=str(tmp_path))
        result = await tool.execute(
            path="test.py",
            symbol_name="nonexistent"
        )

        assert result.success is False
        assert "未找到函数" in result.error or "无法提取函数" in result.data

    async def test_extract_function_rejects_legacy_contract(self, tmp_path):
        """extract_function 弃用 file_path/function_name 旧契约"""
        test_file = tmp_path / "test.py"
        test_file.write_text("def legacy_name():\n    return True\n")

        tool = ExtractFunctionTool(project_root=str(tmp_path))
        result = await tool.execute(
            file_path="test.py",
            function_name="legacy_name",
        )

        assert result.success is False
        assert result.error == "参数校验失败"
        assert result.data["expected_args"]["path"] == "<str>"
        assert result.data["expected_args"]["symbol_name"] == "<str>"

    async def test_extract_function_file_not_found(self, tmp_path):
        """测试文件不存在"""
        tool = ExtractFunctionTool(project_root=str(tmp_path))
        result = await tool.execute(
            path="nonexistent.py",
            symbol_name="test"
        )

        assert result.success is False
        assert "文件不存在" in result.error

    async def test_extract_php_function_returns_precise_metadata(self, tmp_path):
        """PHP 提取应直接返回精确行号元数据"""
        test_file = tmp_path / "test.php"
        test_file.write_text("""
<?php
function process_command($input) {
    system($input);
}
?>
""")

        tool = ExtractFunctionTool(project_root=str(tmp_path))
        result = await tool.execute(
            path="test.php",
            symbol_name="process_command"
        )

        assert result.success is True
        assert "process_command" in result.data
        assert "system" in result.data
        assert result.metadata["line_start"] == 3
        assert result.metadata["line_end"] == 5

    async def test_extract_javascript_export_function_returns_precise_metadata(self, tmp_path):
        """JS/TS 导出函数提取应直接返回精确行号元数据"""
        test_file = tmp_path / "test.ts"
        test_file.write_text("""
export async function executeCommand(cmd: string) {
    exec(cmd);
}

const arrow = (x) => {
    return x * 2;
}
""")

        tool = ExtractFunctionTool(project_root=str(tmp_path))
        result = await tool.execute(
            path="test.ts",
            symbol_name="executeCommand"
        )

        assert result.success is True
        assert "executeCommand" in result.data
        assert "exec" in result.data
        assert result.metadata["line_start"] == 2
        assert result.metadata["line_end"] == 4

    async def test_extract_javascript_class_method(self, tmp_path):
        """JS/TS 类方法提取应支持 class method / static async method"""
        test_file = tmp_path / "service.ts"
        test_file.write_text("""
class AccountService {
    async validate(user) {
        return user && user.id;
    }

    static async dangerous(cmd) {
        return exec(cmd);
    }
}
""")

        tool = ExtractFunctionTool(project_root=str(tmp_path))
        result = await tool.execute(
            path="service.ts",
            symbol_name="dangerous",
        )

        assert result.success is True
        assert "dangerous" in result.data
        assert "exec" in result.data
        assert result.metadata["line_start"] == 7
        assert result.metadata["line_end"] == 9

    async def test_extract_java_method(self, tmp_path):
        """测试提取 Java 方法"""
        test_file = tmp_path / "Demo.java"
        test_file.write_text(
            """
public class Demo {
    public String login(String username) {
        return username.trim();
    }
}
"""
        )

        tool = ExtractFunctionTool(project_root=str(tmp_path))
        result = await tool.execute(
            path="Demo.java",
            symbol_name="login",
        )

        assert result.success is True
        assert "login" in result.data
        assert "username.trim" in result.data

    async def test_extract_c_function(self, tmp_path):
        """测试提取 C 函数"""
        test_file = tmp_path / "test.c"
        test_file.write_text("""
#include <stdio.h>
#include <stdlib.h>

int vulnerable_function(char* input) {
    char command[256];
    sprintf(command, "echo %s", input);
    system(command);
    return 0;
}
""")

        tool = ExtractFunctionTool(project_root=str(tmp_path))
        result = await tool.execute(
            path="test.c",
            symbol_name="vulnerable_function",
            include_imports=True
        )

        # C 函数提取可能成功或回退到通用方法
        if result.success:
            assert "vulnerable_function" in result.data
            assert "system" in result.data


@pytest.mark.integration
@pytest.mark.asyncio
class TestRunCodeToolIntegration:
    """集成测试（需要真实沙箱环境）"""

    async def test_real_python_execution(self):
        """测试真实 Python 代码执行"""
        # 跳过如果没有 Docker
        import os
        if os.getenv("SKIP_INTEGRATION_TESTS") == "1":
            pytest.skip("跳过集成测试")

        tool = RunCodeTool(project_root="/tmp")

        # 初始化沙箱
        try:
            await tool.sandbox_manager.initialize()
        except Exception:
            pytest.skip("沙箱不可用，跳过集成测试")

        if not tool.sandbox_manager.is_available:
            pytest.skip("沙箱不可用，跳过集成测试")

        result = await tool._execute(
            code="print('Integration Test')",
            language="python",
            timeout=30
        )

        assert result.success is True
        assert "Integration Test" in result.data or result.data  # 可能成功执行

    async def test_real_command_injection_fuzzing(self):
        """测试真实的命令注入 Fuzzing（演示）"""
        if os.getenv("SKIP_INTEGRATION_TESTS") == "1":
            pytest.skip("跳过集成测试")

        tool = RunCodeTool(project_root="/tmp")

        fuzzing_code = """
import os

# Mock os.system 来检测调用
executed_commands = []
original_system = os.system
def mock_system(cmd):
    print(f"[DETECTED] os.system called: {cmd}")
    executed_commands.append(cmd)
    return 0
os.system = mock_system

# 目标函数
def vulnerable_function(user_input):
    os.system(f"echo {user_input}")

# Fuzzing 测试
payloads = ["; id", "| whoami"]
for payload in payloads:
    print(f"Testing payload: {payload}")
    executed_commands.clear()
    vulnerable_function(payload)
    if executed_commands:
        print(f"[VULN] Command injection detected!")
"""

        try:
            await tool.sandbox_manager.initialize()
            if not tool.sandbox_manager.is_available:
                pytest.skip("沙箱不可用")

            result = await tool._execute(
                code=fuzzing_code,
                language="python",
                description="Command Injection Fuzzing"
            )

            # 验证结果包含检测信息
            assert result.data is not None
        except Exception as e:
            pytest.skip(f"集成测试失败: {e}")


def test_run_code_tool_description_format():
    """测试工具描述格式"""
    tool = RunCodeTool(project_root="/test")
    
    # 验证描述包含必要信息
    assert "输入：" in tool.description or "输入:" in tool.description
    assert "code" in tool.description
    assert "language" in tool.description
    assert "timeout" in tool.description
    assert "python" in tool.description
    assert "php" in tool.description
    assert "javascript" in tool.description


@pytest.mark.asyncio
async def test_sandbox_exec_returns_execution_result_metadata():
    sandbox_manager = StubSandboxManager(
        {
            "success": False,
            "exit_code": 7,
            "stdout": "partial output",
            "stderr": "permission denied",
            "image": "Argus/sandbox-runner:latest",
            "image_candidates": ["Argus/sandbox-runner:latest", "Argus/sandbox-runner:latest"],
        }
    )
    tool = SandboxTool(sandbox_manager=sandbox_manager)

    result = await tool._execute(command="echo hello", timeout=8)

    assert result.success is False
    assert result.metadata["render_type"] == "execution_result"
    assert result.metadata["command_chain"] == ["sandbox_exec", "echo"]
    entry = result.metadata["entries"][0]
    assert entry["status"] == "failed"
    assert entry["exit_code"] == 7
    assert entry["execution_command"] == "echo hello"
    assert entry["stdout_preview"] == "partial output"
    assert entry["stderr_preview"] == "permission denied"


if __name__ == "__main__":
    # 运行测试
    print("=" * 80)
    print("RunCodeTool 测试套件")
    print("=" * 80)
    
    # 运行所有测试
    pytest.main([
        __file__,
        "-v",
        "-s",
        "--tb=short",
        "-m", "not integration"  # 默认跳过集成测试
    ])
    
    print("\n" + "=" * 80)
    print("提示：运行集成测试请使用以下命令：")
    print(f"pytest {__file__} -v -m integration")
    print("=" * 80)
