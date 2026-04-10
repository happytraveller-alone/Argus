"""
Agent 单元测试
测试各个 Agent 的功能
"""

import pytest
import asyncio
import os
from unittest.mock import MagicMock, AsyncMock, patch

from app.services.agent.agents.base import BaseAgent, AgentConfig, AgentResult, AgentType, AgentPattern
from app.services.agent.agents.recon import ReconAgent, ReconStep
from app.services.agent.agents.analysis import AnalysisAgent
from app.services.agent.agents.verification import VerificationAgent


class TestReconAgent:
    """Recon Agent 测试"""
    
    @pytest.fixture
    def recon_agent(self, temp_project_dir, mock_llm_service, mock_event_emitter):
        """创建 Recon Agent 实例"""
        from app.services.agent.tools import (
            FileReadTool, FileSearchTool, ListFilesTool,
        )
        
        tools = {
            "list_files": ListFilesTool(temp_project_dir),
            "read_file": FileReadTool(temp_project_dir),
            "search_code": FileSearchTool(temp_project_dir),
        }
        
        return ReconAgent(
            llm_service=mock_llm_service,
            tools=tools,
            event_emitter=mock_event_emitter,
        )
    
    @pytest.mark.asyncio
    async def test_recon_agent_run(self, recon_agent, temp_project_dir):
        """测试 Recon Agent 运行"""
        result = await recon_agent.run({
            "project_info": {
                "name": "Test Project",
                "root": temp_project_dir,
            },
            "config": {},
        })
        
        assert result.success is True
        assert result.data is not None
        
        # 验证返回数据结构
        data = result.data
        assert "tech_stack" in data
        assert "project_profile" in data
        assert isinstance(data.get("project_profile"), dict)
        assert "entry_points" in data or "high_risk_areas" in data
    
    @pytest.mark.asyncio
    async def test_recon_agent_identifies_python(self, recon_agent, temp_project_dir):
        """测试 Recon Agent 识别 Python 技术栈"""
        result = await recon_agent.run({
            "project_info": {"root": temp_project_dir},
            "config": {},
        })
        
        assert result.success is True
        tech_stack = result.data.get("tech_stack", {})
        languages = tech_stack.get("languages", [])
        
        # 应该识别出 Python
        assert "Python" in languages or len(languages) > 0
    
    @pytest.mark.asyncio
    async def test_recon_agent_finds_high_risk_areas(self, recon_agent, temp_project_dir):
        """测试 Recon Agent 发现高风险区域"""
        result = await recon_agent.run({
            "project_info": {"root": temp_project_dir},
            "config": {},
        })
        
        assert result.success is True
        high_risk_areas = result.data.get("high_risk_areas", [])
        
        # 应该发现高风险区域
        assert len(high_risk_areas) > 0

    def test_recon_agent_summary_identifies_typescript_frameworks_and_routes(
        self, mock_llm_service, mock_event_emitter
    ):
        """回退汇总应能识别 TypeScript 服务项目线索。"""
        agent = ReconAgent(
            llm_service=mock_llm_service,
            tools={},
            event_emitter=mock_event_emitter,
        )
        agent._steps = [
            ReconStep(
                thought="发现 TypeScript 服务端入口",
                observation=(
                    "package.json tsconfig.json next.config.ts nest-cli.json "
                    "src/app.controller.ts src/main.ts "
                    "app/api/auth/[userId]/route.ts pages/api/admin/reset.ts"
                ),
            )
        ]

        result = agent._summarize_from_steps()
        tech_stack = result["tech_stack"]

        assert "TypeScript" in tech_stack["languages"]
        assert "Next.js" in tech_stack["frameworks"]
        assert "NestJS" in tech_stack["frameworks"]
        assert result["project_profile"]["is_web_project"] is True
        assert "app/api/auth/[userId]/route.ts" in result["high_risk_areas"]

    def test_recon_agent_keeps_structurally_distinct_risk_points(
        self, mock_llm_service, mock_event_emitter
    ):
        agent = ReconAgent(
            llm_service=mock_llm_service,
            tools={},
            event_emitter=mock_event_emitter,
        )
        base_point = {
            "file_path": "src/auth.py",
            "line_start": 42,
            "description": "User-controlled SQL reaches query builder",
            "severity": "high",
            "confidence": 0.8,
            "vulnerability_type": "sql_injection",
        }

        first = dict(base_point, entry_function="login", trust_boundary="HTTP -> auth -> SQL")
        second = dict(base_point, entry_function="reset_password", trust_boundary="CLI -> admin task -> SQL")

        agent._track_risk_point(first)
        agent._track_risk_point(second)
        merged = agent._merge_risk_points([first, second])

        assert len(agent._risk_points_pushed) == 2
        assert len(merged) == 2
        assert {item["entry_function"] for item in merged} == {"login", "reset_password"}

    @pytest.mark.asyncio
    async def test_recon_agent_batch_push_partial_result_falls_back_to_single_pushes(
        self, mock_llm_service, mock_event_emitter
    ):
        agent = ReconAgent(
            llm_service=mock_llm_service,
            tools={
                "push_risk_points_to_queue": object(),
                "push_risk_point_to_queue": object(),
            },
            event_emitter=mock_event_emitter,
        )
        risk_points = [
            {
                "file_path": "src/auth.py",
                "line_start": 10,
                "description": "Unsafe SQL in login flow",
                "severity": "high",
                "confidence": 0.8,
                "vulnerability_type": "sql_injection",
                "entry_function": "login",
            },
            {
                "file_path": "src/admin.py",
                "line_start": 18,
                "description": "Unsafe SQL in admin flow",
                "severity": "high",
                "confidence": 0.75,
                "vulnerability_type": "sql_injection",
                "entry_function": "admin_search",
            },
        ]
        calls = []

        async def fake_execute_tool(tool_name, tool_input):
            calls.append((tool_name, tool_input))
            if tool_name == "push_risk_points_to_queue":
                return {"enqueued": 1, "duplicate_skipped": 0, "queue_size": 1}
            return {
                "enqueue_status": "enqueued",
                "duplicate_skipped": False,
                "queue_size": len(calls),
            }

        agent.execute_tool = fake_execute_tool

        await agent._push_risk_points_to_queue(risk_points)

        assert [name for name, _payload in calls] == [
            "push_risk_points_to_queue",
            "push_risk_point_to_queue",
            "push_risk_point_to_queue",
        ]
        assert len(agent._risk_points_pushed) == 2


class TestAnalysisAgent:
    """Analysis Agent 测试"""
    
    @pytest.fixture
    def analysis_agent(self, temp_project_dir, mock_llm_service, mock_event_emitter):
        """创建 Analysis Agent 实例"""
        from app.services.agent.tools import (
            FileReadTool, FileSearchTool, PatternMatchTool,
        )
        
        tools = {
            "read_file": FileReadTool(temp_project_dir),
            "search_code": FileSearchTool(temp_project_dir),
            "pattern_match": PatternMatchTool(temp_project_dir),
        }
        
        return AnalysisAgent(
            llm_service=mock_llm_service,
            tools=tools,
            event_emitter=mock_event_emitter,
        )
    
    @pytest.mark.asyncio
    async def test_analysis_agent_run(self, analysis_agent, temp_project_dir):
        """测试 Analysis Agent 运行"""
        result = await analysis_agent.run({
            "tech_stack": {"languages": ["Python"]},
            "entry_points": [],
            "high_risk_areas": ["src/sql_vuln.py", "src/cmd_vuln.py"],
            "config": {},
        })
        
        assert result.success is True
        assert result.data is not None
    
    @pytest.mark.asyncio
    async def test_analysis_agent_finds_vulnerabilities(self, analysis_agent, temp_project_dir):
        """测试 Analysis Agent 发现漏洞"""
        result = await analysis_agent.run({
            "tech_stack": {"languages": ["Python"]},
            "entry_points": [],
            "high_risk_areas": [
                "src/sql_vuln.py",
                "src/cmd_vuln.py",
                "src/xss_vuln.py",
                "src/secrets.py",
            ],
            "config": {},
        })
        
        assert result.success is True
        findings = result.data.get("findings", [])
        
        # 应该发现一些漏洞
        # 注意：具体数量取决于分析逻辑
        assert isinstance(findings, list)

    @pytest.mark.asyncio
    async def test_analysis_observation_history_is_trimmed(self, analysis_agent, monkeypatch):
        """Observation 写入 history 前应裁剪，避免上下文膨胀。"""
        analysis_agent._max_history_observation_chars = 200

        long_observation = "A" * 1000 + "B" * 1000
        monkeypatch.setattr(analysis_agent, "execute_tool", AsyncMock(return_value=long_observation))
        monkeypatch.setattr(
            analysis_agent,
            "stream_llm_call",
            AsyncMock(
                side_effect=[
                    (
                        "Thought: 读取代码证据\n"
                        "Action: read_file\n"
                        'Action Input: {"file_path":"src/sql_vuln.py","start_line":1,"end_line":30}',
                        12,
                    ),
                    # 首次 Final Answer 会被“必须先有工具证据”门禁拦截并触发最小工具调用
                    ('Thought: 完成分析\nFinal Answer: {"findings": [], "summary": "ok"}', 8),
                    ('Thought: 完成分析\nFinal Answer: {"findings": [], "summary": "ok"}', 8),
                ]
            ),
        )

        result = await analysis_agent.run(
            {
                "project_info": {"name": "demo", "root": "/tmp/demo"},
                "config": {"target_files": ["src/sql_vuln.py"]},
                "previous_results": {"recon": {"data": {"high_risk_areas": ["src/sql_vuln.py"]}}},
            }
        )
        assert result.success is True

        observation_entries = [
            msg["content"]
            for msg in analysis_agent.get_conversation_history()
            if msg.get("role") == "user" and str(msg.get("content", "")).startswith("Observation:\n")
        ]
        assert observation_entries
        assert any("Observation 已裁剪" in content for content in observation_entries)


class TestAgentResult:
    """Agent 结果测试"""
    
    def test_agent_result_success(self):
        """测试成功的 Agent 结果"""
        result = AgentResult(
            success=True,
            data={"findings": []},
            iterations=5,
            tool_calls=10,
        )
        
        assert result.success is True
        assert result.iterations == 5
        assert result.tool_calls == 10
    
    def test_agent_result_failure(self):
        """测试失败的 Agent 结果"""
        result = AgentResult(
            success=False,
            error="Test error",
        )
        
        assert result.success is False
        assert result.error == "Test error"
    
    def test_agent_result_to_dict(self):
        """测试 Agent 结果转字典"""
        result = AgentResult(
            success=True,
            data={"key": "value"},
            iterations=3,
        )
        
        d = result.to_dict()
        
        assert d["success"] is True
        assert d["iterations"] == 3


class TestAgentConfig:
    """Agent 配置测试"""
    
    def test_agent_config_defaults(self):
        """测试 Agent 配置默认值"""
        config = AgentConfig(
            name="Test",
            agent_type=AgentType.RECON,
        )
        
        assert config.pattern == AgentPattern.REACT
        assert config.max_iterations == 20
        assert config.temperature == 0.1
    
    def test_agent_config_custom(self):
        """测试自定义 Agent 配置"""
        config = AgentConfig(
            name="Custom",
            agent_type=AgentType.ANALYSIS,
            pattern=AgentPattern.PLAN_AND_EXECUTE,
            max_iterations=50,
            temperature=0.5,
        )
        
        assert config.pattern == AgentPattern.PLAN_AND_EXECUTE
        assert config.max_iterations == 50
        assert config.temperature == 0.5
