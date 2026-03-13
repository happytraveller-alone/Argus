"""
Agent 工具单元测试
测试各种安全分析工具的功能
"""

import pytest
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch

# 导入工具
from app.services.agent.tools import (
    FileReadTool, FileSearchTool, ListFilesTool,
    PatternMatchTool, ExtractFunctionTool, CreateVulnerabilityReportTool,
    DataFlowAnalysisTool, ControlFlowAnalysisLightTool,
)
from app.services.agent.tools.base import ToolResult


class TestFileTools:
    """文件操作工具测试"""
    
    @pytest.mark.asyncio
    async def test_file_read_tool_success(self, temp_project_dir):
        """测试文件读取工具 - 成功读取"""
        tool = FileReadTool(temp_project_dir)
        
        result = await tool.execute(file_path="src/sql_vuln.py")
        
        assert result.success is True
        assert "SELECT * FROM users" in result.data
        assert "sql_injection" in result.data.lower() or "cursor.execute" in result.data
    
    @pytest.mark.asyncio
    async def test_file_read_tool_not_found(self, temp_project_dir):
        """测试文件读取工具 - 文件不存在"""
        tool = FileReadTool(temp_project_dir)
        
        result = await tool.execute(file_path="nonexistent.py")
        
        assert result.success is False
        assert "不存在" in result.error or "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_file_read_tool_path_traversal_blocked(self, temp_project_dir):
        """测试文件读取工具 - 路径遍历被阻止"""
        tool = FileReadTool(temp_project_dir)
        
        result = await tool.execute(file_path="../../../etc/passwd")
        
        assert result.success is False
        assert "安全" in result.error or "security" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_file_search_tool(self, temp_project_dir):
        """测试文件搜索工具"""
        tool = FileSearchTool(temp_project_dir)
        
        result = await tool.execute(keyword="cursor.execute")
        
        assert result.success is True
        assert "sql_vuln.py" in result.data

    @pytest.mark.asyncio
    async def test_file_search_tool_supports_multi_file_patterns(self, temp_project_dir):
        """测试文件搜索工具 - 支持多 file_pattern 分隔符"""
        tool = FileSearchTool(temp_project_dir)

        result = await tool.execute(
            keyword="def ",
            file_pattern="*.py|*.h",
            directory="src",
        )

        assert result.success is True
        assert result.metadata.get("files_searched", 0) > 0
        assert result.metadata.get("normalized_file_patterns") == ["*.py", "*.h"]

    @pytest.mark.asyncio
    async def test_file_search_tool_auto_scope_fallback_to_project_root(self, temp_project_dir):
        """测试文件搜索工具 - 子目录无命中时自动扩域到项目根目录"""
        tool = FileSearchTool(temp_project_dir)

        result = await tool.execute(
            keyword="class Config",
            file_pattern="*.py",
            directory="src",
        )

        assert result.success is True
        assert result.metadata.get("scope_fallback_applied") is True
        assert result.metadata.get("effective_directory") == "."
        assert "config/settings.py" in str(result.data)

    @pytest.mark.asyncio
    async def test_file_search_tool_single_file_mode_with_file_path(self, temp_project_dir):
        """测试文件搜索工具 - 支持 file_path 单文件搜索"""
        tool = FileSearchTool(temp_project_dir)

        result = await tool.execute(
            keyword="cursor.execute",
            file_path="src/sql_vuln.py",
        )

        assert result.success is True
        assert result.metadata.get("single_file_mode") is True
        assert result.metadata.get("target_file") == "src/sql_vuln.py"
        assert result.metadata.get("files_searched") == 1
        assert result.metadata.get("normalized_file_patterns") == ["sql_vuln.py"]
        assert "src/sql_vuln.py" in str(result.data)

    @pytest.mark.asyncio
    async def test_file_search_tool_infers_single_file_from_path_like_file_pattern(self, temp_project_dir):
        """测试文件搜索工具 - file_pattern=src/foo.py 自动转单文件模式"""
        tool = FileSearchTool(temp_project_dir)

        result = await tool.execute(
            keyword="cursor.execute",
            file_pattern="src/sql_vuln.py",
        )

        assert result.success is True
        assert result.metadata.get("single_file_mode") is True
        assert result.metadata.get("target_file") == "src/sql_vuln.py"
        assert result.metadata.get("files_searched") == 1
        assert result.metadata.get("normalized_file_patterns") == ["sql_vuln.py"]
        assert "src/sql_vuln.py" in str(result.data)

    @pytest.mark.asyncio
    async def test_file_search_tool_engine_fallback_to_python(self, temp_project_dir):
        """测试文件搜索工具 - rg/grep 不可用时回退 Python 引擎"""
        tool = FileSearchTool(temp_project_dir)

        with patch("app.services.agent.tools.file_tool.shutil.which", return_value=None):
            result = await tool.execute(
                keyword="cursor.execute",
                directory="src",
            )

        assert result.success is True
        assert result.metadata.get("engine") == "python"
        assert result.metadata.get("matches", 0) >= 1

    @pytest.mark.asyncio
    async def test_file_read_tool_supports_line_range_in_file_path(self, temp_project_dir):
        """测试文件读取工具 - 支持 file_path:line-start-end 简写"""
        tool = FileReadTool(temp_project_dir)

        result = await tool.execute(file_path="src/sql_vuln.py:3-6")

        assert result.success is True
        assert result.metadata.get("start_line") == 3
        assert result.metadata.get("end_line") == 6

    @pytest.mark.asyncio
    async def test_file_read_tool_project_scope_resolves_basename(self, temp_project_dir):
        """测试文件读取工具 - 基于全项目补全 basename 路径"""
        os.makedirs(os.path.join(temp_project_dir, "src", "nested"), exist_ok=True)
        target_file = os.path.join(temp_project_dir, "src", "nested", "flow_target.c")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write("int flow_target(int x) { return x + 1; }\n")

        tool = FileReadTool(temp_project_dir)
        result = await tool.execute(file_path="flow_target.c", project_scope=True)

        assert result.success is True
        assert result.metadata.get("file_path") == "src/nested/flow_target.c"
        assert "flow_target" in str(result.data)

    @pytest.mark.asyncio
    async def test_file_read_tool_hides_absolute_path_in_response(self, temp_project_dir):
        """测试文件读取工具 - 绝对路径输入时输出仍为相对路径"""
        tool = FileReadTool(temp_project_dir)
        absolute_path = os.path.join(temp_project_dir, "src", "sql_vuln.py")

        result = await tool.execute(file_path=absolute_path, start_line=1, end_line=2)

        assert result.success is True
        assert result.metadata.get("file_path") == "src/sql_vuln.py"
        assert absolute_path not in str(result.data)
    
    @pytest.mark.asyncio
    async def test_list_files_tool(self, temp_project_dir):
        """测试文件列表工具"""
        tool = ListFilesTool(temp_project_dir)
        
        result = await tool.execute(directory=".", recursive=True)
        
        assert result.success is True
        assert "sql_vuln.py" in result.data
        assert "requirements.txt" in result.data
    
    @pytest.mark.asyncio
    async def test_list_files_tool_pattern(self, temp_project_dir):
        """测试文件列表工具 - 文件模式过滤"""
        tool = ListFilesTool(temp_project_dir)
        
        result = await tool.execute(directory="src", pattern="*.py")
        
        assert result.success is True
        assert "sql_vuln.py" in result.data


class TestPatternMatchTool:
    """模式匹配工具测试"""
    
    @pytest.mark.asyncio
    async def test_pattern_match_sql_injection(self, temp_project_dir):
        """测试模式匹配 - SQL 注入检测"""
        tool = PatternMatchTool(temp_project_dir)
        
        # 读取有漏洞的代码
        with open(os.path.join(temp_project_dir, "src", "sql_vuln.py")) as f:
            code = f.read()
        
        result = await tool.execute(
            code=code,
            file_path="src/sql_vuln.py",
            pattern_types=["sql_injection"],
            language="python"
        )
        
        assert result.success is True
        # 应该检测到 SQL 注入模式
        if result.data:
            assert "sql" in str(result.data).lower() or len(result.metadata.get("matches", [])) > 0
    
    @pytest.mark.asyncio
    async def test_pattern_match_command_injection(self, temp_project_dir):
        """测试模式匹配 - 命令注入检测"""
        tool = PatternMatchTool(temp_project_dir)
        
        with open(os.path.join(temp_project_dir, "src", "cmd_vuln.py")) as f:
            code = f.read()
        
        result = await tool.execute(
            code=code,
            file_path="src/cmd_vuln.py",
            pattern_types=["command_injection"],
            language="python"
        )
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_pattern_match_xss(self, temp_project_dir):
        """测试模式匹配 - XSS 检测"""
        tool = PatternMatchTool(temp_project_dir)
        
        with open(os.path.join(temp_project_dir, "src", "xss_vuln.py")) as f:
            code = f.read()
        
        result = await tool.execute(
            code=code,
            file_path="src/xss_vuln.py",
            pattern_types=["xss"],
            language="python"
        )
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_pattern_match_hardcoded_secrets(self, temp_project_dir):
        """测试模式匹配 - 硬编码密钥检测"""
        tool = PatternMatchTool(temp_project_dir)
        
        with open(os.path.join(temp_project_dir, "src", "secrets.py")) as f:
            code = f.read()
        
        result = await tool.execute(
            code=code,
            file_path="src/secrets.py",
            pattern_types=["hardcoded_secret"],
        )
        
        assert result.success is True
    
    @pytest.mark.asyncio
    async def test_pattern_match_safe_code(self, temp_project_dir):
        """测试模式匹配 - 安全代码应该没有问题"""
        tool = PatternMatchTool(temp_project_dir)
        
        with open(os.path.join(temp_project_dir, "src", "safe_code.py")) as f:
            code = f.read()
        
        result = await tool.execute(
            code=code,
            file_path="src/safe_code.py",
            pattern_types=["sql_injection"],
            language="python"
        )
        
        assert result.success is True
        # 安全代码使用参数化查询，不应该有 SQL 注入漏洞
        # 检查结果数据，如果有 matches 字段
        matches = result.metadata.get("matches", [])
        if isinstance(matches, list):
            # 参数化查询不应该被误报为 SQL 注入
            sql_injection_count = sum(
                1 for m in matches 
                if isinstance(m, dict) and "sql" in m.get("pattern_type", "").lower()
            )
            # 安全代码的 SQL 注入匹配应该很少或没有
            assert sql_injection_count <= 1  # 允许少量误报

    @pytest.mark.asyncio
    async def test_pattern_match_supports_directory_scan(self, temp_project_dir):
        """测试模式匹配 - scan_file 传目录时自动递归扫描"""
        tool = PatternMatchTool(temp_project_dir)

        c_file = os.path.join(temp_project_dir, "src", "hardcoded.c")
        with open(c_file, "w", encoding="utf-8") as f:
            f.write(
                "const char *api_key = \"sk-123456789012345678901234567890123456789012345678\";\n"
            )

        result = await tool.execute(
            scan_file="src",
            pattern_types="hardcoded_secret|xss",
            language="c",
        )

        assert result.success is True
        assert isinstance(result.metadata, dict)
        assert result.metadata.get("files_scanned", 0) > 0
        assert result.metadata.get("matches", 0) >= 1


class TestToolRegressions:
    """工具回归测试"""

    @pytest.mark.asyncio
    async def test_extract_function_supports_c_definition(self, temp_project_dir):
        """extract_function 应支持提取 C 风格函数定义。"""
        tool = ExtractFunctionTool(temp_project_dir)

        c_file = os.path.join(temp_project_dir, "src", "time64.c")
        with open(c_file, "w", encoding="utf-8") as f:
            f.write(
                "#include <stdio.h>\n\n"
                "char *asctime64_r(const struct TM* date, char *result) {\n"
                '    sprintf(result, "demo:%d", date->tm_year);\n'
                "    return result;\n"
                "}\n"
            )

        result = await tool.execute(
            path="src/time64.c",
            symbol_name="asctime64_r",
        )

        assert result.success is True
        assert isinstance(result.metadata, dict)
        assert "asctime64_r" in result.metadata.get("code", "")
        assert "sprintf" in result.metadata.get("code", "")
        assert isinstance(result.metadata.get("line_start"), int)
        assert isinstance(result.metadata.get("line_end"), int)

    @pytest.mark.asyncio
    async def test_create_vulnerability_report_accepts_confidence_label(self, temp_project_dir):
        """create_vulnerability_report 可容错 confidence 字符串等级。"""
        tool = CreateVulnerabilityReportTool(project_root=temp_project_dir)

        result = await tool.execute(
            title="Buffer overflow risk",
            vulnerability_type="buffer_overflow",
            severity="high",
            description="Potential overflow in snprintf call",
            file_path="src/sql_vuln.py",
            confidence="high",
            cvss_score=7.5,
        )

        assert result.success is True
        assert isinstance(result.metadata, dict)
        assert result.metadata.get("vulnerability_type") == "buffer_overflow"
        assert isinstance(result.metadata.get("confidence"), float)
        assert 0.0 <= result.metadata["confidence"] <= 1.0
        assert result.metadata.get("cvss_score") == 7.5
        assert "[" in result.data["message"]

    @pytest.mark.asyncio
    async def test_create_vulnerability_report_accepts_numeric_strings(self, temp_project_dir):
        """create_vulnerability_report 可容错数字字符串 confidence/cvss。"""
        tool = CreateVulnerabilityReportTool(project_root=temp_project_dir)

        result = await tool.execute(
            title="Confidence string parsing",
            vulnerability_type="buffer_overflow",
            severity="medium",
            description="Numeric string coercion test",
            file_path="src/sql_vuln.py",
            confidence="0.76",
            cvss_score="7.5",
        )

        assert result.success is True
        assert isinstance(result.metadata, dict)
        assert result.metadata.get("confidence") == pytest.approx(0.76, rel=1e-6)
        assert result.metadata.get("cvss_score") == pytest.approx(7.5, rel=1e-6)


class _StubFlowLLM:
    async def analyze_code_with_custom_prompt(self, **kwargs):
        _ = kwargs
        return {
            "source_nodes": ["http_request_input"],
            "sink_nodes": ["stack_overflow_risk"],
            "sanitizers": [],
            "taint_steps": ["source -> user_input", "user_input -> sprintf"],
            "risk_level": "high",
            "confidence": 0.88,
            "evidence_lines": [2, 3],
            "next_actions": ["补齐 controlflow_analysis_light 验证。"],
        }


class _TimeoutFlowLLM:
    async def analyze_code_with_custom_prompt(self, **kwargs):
        _ = kwargs
        raise asyncio.TimeoutError()


class TestFlowTools:
    @pytest.mark.asyncio
    async def test_dataflow_analysis_source_code_mode_returns_structured_metadata(self):
        tool = DataFlowAnalysisTool(llm_service=_StubFlowLLM())
        source_code = (
            "char *copy_user(char *input, char *dst) {\n"
            "    sprintf(dst, \"%s\", input);\n"
            "    return dst;\n"
            "}\n"
        )

        result = await tool.execute(
            source_code=source_code,
            file_path="src/time64.c",
            variable_name="input",
            sink_hints=["sprintf"],
        )

        assert result.success is True
        assert isinstance(result.metadata, dict)
        analysis = result.metadata.get("analysis")
        assert isinstance(analysis, dict)
        expected_keys = {
            "source_nodes",
            "sink_nodes",
            "sanitizers",
            "taint_steps",
            "risk_level",
            "confidence",
            "evidence_lines",
            "next_actions",
        }
        assert expected_keys.issubset(set(analysis.keys()))
        assert analysis.get("risk_level") in {"high", "medium", "low", "none"}
        assert isinstance(analysis.get("taint_steps"), list)

    @pytest.mark.asyncio
    async def test_dataflow_analysis_file_path_line_mode_reads_code(self, temp_project_dir):
        tool = DataFlowAnalysisTool(llm_service=_StubFlowLLM(), project_root=temp_project_dir)

        c_file = os.path.join(temp_project_dir, "src", "flow_target.c")
        with open(c_file, "w", encoding="utf-8") as f:
            f.write(
                "char *copy_user(char *input, char *dst) {\n"
                "    sprintf(dst, \"%s\", input);\n"
                "    return dst;\n"
                "}\n"
            )

        result = await tool.execute(
            file_path="src/flow_target.c",
            start_line=1,
            end_line=3,
            variable_name="input",
        )

        assert result.success is True
        assert result.metadata.get("start_line") == 1
        assert result.metadata.get("end_line") == 3
        assert isinstance(result.metadata.get("analysis"), dict)

    @pytest.mark.asyncio
    async def test_dataflow_analysis_marks_fallback_when_llm_times_out(self):
        tool = DataFlowAnalysisTool(llm_service=_TimeoutFlowLLM())
        source_code = (
            "char *copy_user(char *input, char *dst) {\n"
            "    sprintf(dst, \"%s\", input);\n"
            "    return dst;\n"
            "}\n"
        )

        result = await tool.execute(
            source_code=source_code,
            file_path="src/time64.c",
            variable_name="input",
            sink_hints=["sprintf"],
        )

        assert result.success is True
        assert result.metadata.get("fallback_used") is True
        assert isinstance(result.metadata.get("analysis"), dict)

    @pytest.mark.asyncio
    async def test_controlflow_analysis_light_supports_file_path_line_shorthand(self, temp_project_dir):
        tool = ControlFlowAnalysisLightTool(project_root=temp_project_dir)
        tool.pipeline.analyze_finding = AsyncMock(
            return_value={
                "flow": {
                    "path_found": True,
                    "path_score": 0.91,
                    "call_chain": ["main -> asctime64_r"],
                    "blocked_reasons": [],
                    "entry_inferred": True,
                }
            }
        )

        result = await tool.execute(file_path="src/sql_vuln.py:8")

        assert result.success is True
        assert result.metadata.get("line_start") == 8
        assert "path_found=True" in result.metadata.get("summary", "")

    @pytest.mark.asyncio
    async def test_controlflow_analysis_light_uses_function_name_fallback(self, temp_project_dir):
        tool = ControlFlowAnalysisLightTool(project_root=temp_project_dir)
        tool.pipeline.analyze_finding = AsyncMock(return_value={"flow": {"path_found": False, "path_score": 0.0}})
        tool._resolve_line_start_by_function = MagicMock(return_value=12)

        result = await tool.execute(
            file_path="src/sql_vuln.py",
            function_name="get_user",
        )

        assert result.success is True
        assert result.metadata.get("line_start") == 12

    @pytest.mark.asyncio
    async def test_controlflow_analysis_light_returns_actionable_error_when_location_missing(self, temp_project_dir):
        tool = ControlFlowAnalysisLightTool(project_root=temp_project_dir)

        result = await tool.execute(file_path="src/sql_vuln.py")

        assert result.success is False
        assert "line_start" in result.error
        assert "function_name" in result.error

    @pytest.mark.asyncio
    async def test_controlflow_analysis_light_summary_mentions_code2flow_diagnosis(self, temp_project_dir):
        tool = ControlFlowAnalysisLightTool(project_root=temp_project_dir)
        tool.pipeline.analyze_finding = AsyncMock(
            return_value={
                "flow": {
                    "path_found": False,
                    "path_score": 0.12,
                    "blocked_reasons": ["code2flow_not_installed", "auto_install_failed"],
                    "entry_inferred": True,
                }
            }
        )

        result = await tool.execute(file_path="src/sql_vuln.py:8")

        assert result.success is True
        summary = result.metadata.get("summary", "")
        assert "code2flow" in summary
        assert "auto_install_failed" in summary


class TestToolResult:
    """工具结果测试"""
    
    def test_tool_result_success(self):
        """测试成功的工具结果"""
        result = ToolResult(success=True, data="test data")
        
        assert result.success is True
        assert result.data == "test data"
        assert result.error is None
    
    def test_tool_result_failure(self):
        """测试失败的工具结果"""
        result = ToolResult(success=False, error="test error")
        
        assert result.success is False
        assert result.error == "test error"
    
    def test_tool_result_to_string(self):
        """测试工具结果转字符串"""
        result = ToolResult(success=True, data={"key": "value"})
        
        string = result.to_string()
        
        assert "key" in string
        assert "value" in string
    
    def test_tool_result_to_string_truncate(self):
        """测试工具结果字符串截断"""
        long_data = "x" * 10000
        result = ToolResult(success=True, data=long_data)
        
        string = result.to_string(max_length=100)
        
        assert len(string) < len(long_data)
        assert "truncated" in string.lower()


class TestToolMetadata:
    """工具元数据测试"""
    
    @pytest.mark.asyncio
    async def test_tool_call_count(self, temp_project_dir):
        """测试工具调用计数"""
        tool = ListFilesTool(temp_project_dir)
        
        await tool.execute(directory=".")
        await tool.execute(directory="src")
        
        assert tool._call_count == 2
    
    @pytest.mark.asyncio
    async def test_tool_duration_tracking(self, temp_project_dir):
        """测试工具执行时间跟踪"""
        tool = ListFilesTool(temp_project_dir)
        
        result = await tool.execute(directory=".")
        
        assert result.duration_ms >= 0
        assert tool._total_duration_ms >= 0
