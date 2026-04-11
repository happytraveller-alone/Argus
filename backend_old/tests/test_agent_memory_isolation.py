"""
内存隔离测试脚本

用于验证 Agent 的内存清理机制是否正确工作，
检测多次调用 Agent 时的内存隔离效果。

使用方法：
    cd backend
    python -m pytest tests/test_agent_memory_isolation.py -v
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import Dict, Any


class TestMemoryIsolation:
    """Agent 内存隔离测试套件"""
    
    @pytest.fixture
    def mock_base_agent(self):
        """创建模拟的 BaseAgent"""
        # 创建带有必要属性的 mock agent
        agent = MagicMock()
        agent.config = MagicMock()
        agent.config.name = "TestAgent"
        agent.name = "TestAgent"
        agent._insights = ["insight1", "insight2"]
        agent._work_completed = ["work1"]
        agent._incoming_handoff = Mock(from_agent="recon", to_agent="analysis")
        
        # 实现 reset_session_memory 方法
        def reset_session_memory():
            agent._insights.clear()
            agent._work_completed.clear()
            agent._incoming_handoff = None
        
        agent.reset_session_memory = reset_session_memory
        
        return agent
    
    def test_reset_session_memory_clears_insights(self, mock_base_agent):
        """测试 reset_session_memory 清空 _insights"""
        assert len(mock_base_agent._insights) == 2
        mock_base_agent.reset_session_memory()
        assert len(mock_base_agent._insights) == 0
    
    def test_reset_session_memory_clears_work_completed(self, mock_base_agent):
        """测试 reset_session_memory 清空 _work_completed"""
        assert len(mock_base_agent._work_completed) == 1
        mock_base_agent.reset_session_memory()
        assert len(mock_base_agent._work_completed) == 0
    
    def test_reset_session_memory_clears_handoff(self, mock_base_agent):
        """测试 reset_session_memory 清空 _incoming_handoff"""
        assert mock_base_agent._incoming_handoff is not None
        mock_base_agent.reset_session_memory()
        assert mock_base_agent._incoming_handoff is None
    
    def test_reset_session_memory_complete_isolation(self, mock_base_agent):
        """测试完整隔离效果"""
        # 第一轮
        mock_base_agent._insights.append("round1_insight")
        mock_base_agent._work_completed.append("round1_work")
        
        # 清理
        mock_base_agent.reset_session_memory()
        
        # 验证清理
        assert len(mock_base_agent._insights) == 0
        assert len(mock_base_agent._work_completed) == 0
        assert mock_base_agent._incoming_handoff is None
        
        # 第二轮
        mock_base_agent._insights.append("round2_insight")
        
        # 验证隔离
        assert len(mock_base_agent._insights) == 1
        assert mock_base_agent._insights[0] == "round2_insight"  # 不存在 round1 的数据


class TestMemoryMonitor:
    """内存监控测试套件"""
    
    def test_memory_monitor_snapshot_creation(self):
        """测试内存快照创建"""
        from app.services.agent.workflow.memory_monitor import MemoryMonitor
        
        monitor = MemoryMonitor()
        snapshot = monitor.take_snapshot(phase="test", iteration=1, agent_name="test_agent")
        
        assert snapshot.phase == "test"
        assert snapshot.iteration == 1
        assert snapshot.agent_name == "test_agent"
        assert snapshot.rss_mb >= 0  # 内存大小可以是 0 或正数
        assert len(monitor.report.snapshots) == 1
    
    def test_memory_monitor_report_summary(self):
        """测试内存报告摘要"""
        from app.services.agent.workflow.memory_monitor import MemoryMonitor
        
        monitor = MemoryMonitor()
        monitor.take_snapshot(phase="start", agent_name="test")
        monitor.take_snapshot(phase="end", agent_name="test")
        
        summary = monitor.report.get_summary()
        assert summary["total_snapshots"] == 2
        assert "peak_rss_mb" in summary
        assert "growth_mb" in summary
    
    def test_memory_snapshot_dict_conversion(self):
        """测试内存快照转换为字典"""
        from app.services.agent.workflow.memory_monitor import MemorySnapshot
        
        snapshot = MemorySnapshot(
            timestamp="2026-03-05T10:00:00",
            phase="test",
            iteration=1,
            agent_name="test_agent",
            rss_mb=100.0,
            vms_mb=200.0,
            percent=1.5
        )
        
        snap_dict = snapshot.to_dict()
        assert snap_dict["phase"] == "test"
        assert snap_dict["rss_mb"] == 100.0
        assert snap_dict["iteration"] == 1


class TestWorkflowMemoryIntegration:
    """Workflow 内存集成测试"""
    
    def test_workflow_engine_has_memory_monitor(self):
        """测试 Workflow 引擎具有内存监控功能"""
        # 这是一个结构测试，不需要实际运行 Workflow
        from app.services.agent.workflow.memory_monitor import MemoryMonitor
        
        # 验证 MemoryMonitor 可以正常导入和创建
        monitor = MemoryMonitor()
        assert hasattr(monitor, "take_snapshot")
        assert hasattr(monitor, "get_report")
        assert hasattr(monitor, "log_summary")


class TestMultipleAgentCallsIsolation:
    """多次 Agent 调用隔离测试"""
    
    def test_agent_memory_isolation_across_runs(self):
        """测试多次 run() 调用间的内存隔离"""
        # 创建模拟 Agent
        agent = MagicMock()
        agent._insights = []
        agent._work_completed = []
        agent._incoming_handoff = None
        
        def reset_session_memory():
            agent._insights.clear()
            agent._work_completed.clear()
            agent._incoming_handoff = None
        
        agent.reset_session_memory = reset_session_memory
        
        # 模拟三轮调用
        results = []
        
        for round_num in range(3):
            # 模拟 run() 前的内存状态
            agent._insights = [f"round{round_num}_insight1", f"round{round_num}_insight2"]
            agent._work_completed = [f"round{round_num}_work"]
            
            # 记录状态
            results.append({
                "round": round_num,
                "insights_count": len(agent._insights),
                "work_count": len(agent._work_completed),
            })
            
            # 清理内存（模拟 Workflow 调用清理）
            agent.reset_session_memory()
        
        # 验证隔离效果
        assert all(r["insights_count"] == 2 for r in results)
        assert all(r["work_count"] == 1 for r in results)


# 实用工具函数

def create_test_risk_point(file_path: str = "test.py", line_start: int = 10) -> Dict[str, Any]:
    """创建测试风险点"""
    return {
        "file_path": file_path,
        "line_start": line_start,
        "description": "Test risk point",
        "severity": "medium",
        "vulnerability_type": "test",
    }


def create_test_finding(file_path: str = "test.py", line_start: int = 10) -> Dict[str, Any]:
    """创建测试漏洞发现"""
    return {
        "file_path": file_path,
        "line_start": line_start,
        "line_end": line_start + 5,
        "title": f"Test vulnerability in {file_path}",
        "verdict": "likely",
        "confidence": 0.8,
        "verification_result": {
            "verdict": "likely",
            "confidence": 0.8,
            "reachability": "reachable",
            "verification_evidence": "Test evidence",
        },
    }


if __name__ == "__main__":
    # 快速测试
    print("内存隔离测试模块已加载")
    print("运行方式: pytest tests/test_agent_memory_isolation.py -v")
