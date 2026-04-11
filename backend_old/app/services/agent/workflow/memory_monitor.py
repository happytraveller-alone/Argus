"""
Agent 内存监控工具

用于追踪 Workflow 执行过程中的 Agent 内存使用情况，
帮助检测内存泄漏和验证内存隔离效果。
"""

import logging
import psutil
import os
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class MemorySnapshot:
    """内存快照"""
    timestamp: str
    phase: str
    iteration: Optional[int] = None
    agent_name: Optional[str] = None
    rss_mb: float = 0.0  # 实际内存占用 (MB)
    vms_mb: float = 0.0  # 虚拟内存占用 (MB)
    percent: float = 0.0  # 内存占用百分比
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryReport:
    """内存使用报告"""
    snapshots: List[MemorySnapshot] = field(default_factory=list)
    peak_rss_mb: float = 0.0
    peak_vms_mb: float = 0.0
    process_id: int = field(default_factory=os.getpid)
    
    def add_snapshot(self, snapshot: MemorySnapshot) -> None:
        """添加内存快照"""
        self.snapshots.append(snapshot)
        self.peak_rss_mb = max(self.peak_rss_mb, snapshot.rss_mb)
        self.peak_vms_mb = max(self.peak_vms_mb, snapshot.vms_mb)
    
    def get_summary(self) -> Dict[str, Any]:
        """获取内存使用摘要"""
        if not self.snapshots:
            return {
                "total_snapshots": 0,
                "peak_rss_mb": 0.0,
                "peak_vms_mb": 0.0,
                "process_id": self.process_id,
            }
        
        start_rss = self.snapshots[0].rss_mb if self.snapshots else 0.0
        end_rss = self.snapshots[-1].rss_mb if self.snapshots else 0.0
        growth_mb = end_rss - start_rss
        
        return {
            "total_snapshots": len(self.snapshots),
            "start_rss_mb": start_rss,
            "end_rss_mb": end_rss,
            "growth_mb": growth_mb,
            "peak_rss_mb": self.peak_rss_mb,
            "peak_vms_mb": self.peak_vms_mb,
            "process_id": self.process_id,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "snapshots": [s.to_dict() for s in self.snapshots],
            "summary": self.get_summary(),
        }


class MemoryMonitor:
    """
    Agent 内存监控器
    
    用法：
        monitor = MemoryMonitor()
        monitor.take_snapshot(phase="analysis", iteration=1, agent_name="analysis")
        # ... 执行任务
        monitor.take_snapshot(phase="analysis", iteration=1, agent_name="analysis")
        report = monitor.get_report()
    """
    
    def __init__(self):
        self.report = MemoryReport()
        self.process = psutil.Process(os.getpid())
    
    def take_snapshot(
        self,
        phase: str,
        iteration: Optional[int] = None,
        agent_name: Optional[str] = None,
    ) -> MemorySnapshot:
        """
        获取内存快照
        
        Args:
            phase: 当前阶段 (recon/analysis/verification/complete)
            iteration: 迭代次数
            agent_name: Agent 名称
            
        Returns:
            MemorySnapshot 对象
        """
        try:
            mem_info = self.process.memory_info()
            memory_percent = self.process.memory_percent()
            
            snapshot = MemorySnapshot(
                timestamp=datetime.now().isoformat(),
                phase=phase,
                iteration=iteration,
                agent_name=agent_name,
                rss_mb=mem_info.rss / 1024 / 1024,
                vms_mb=mem_info.vms / 1024 / 1024,
                percent=memory_percent,
            )
            
            self.report.add_snapshot(snapshot)
            
            logger.debug(
                f"[MemoryMonitor] Snapshot: phase={phase}, iteration={iteration}, "
                f"rss={snapshot.rss_mb:.2f}MB, vms={snapshot.vms_mb:.2f}MB"
            )
            
            return snapshot
        except Exception as e:
            logger.warning(f"[MemoryMonitor] Failed to take snapshot: {e}")
            return MemorySnapshot(
                timestamp=datetime.now().isoformat(),
                phase=phase,
                iteration=iteration,
                agent_name=agent_name,
            )
    
    def get_report(self) -> MemoryReport:
        """获取内存使用报告"""
        return self.report
    
    def log_summary(self) -> None:
        """输出内存使用摘要到日志"""
        summary = self.report.get_summary()
        logger.info(
            f"[MemoryMonitor] Summary: "
            f"snapshots={summary['total_snapshots']}, "
            f"start={summary.get('start_rss_mb', 0):.2f}MB, "
            f"end={summary.get('end_rss_mb', 0):.2f}MB, "
            f"growth={summary.get('growth_mb', 0):.2f}MB, "
            f"peak_rss={summary['peak_rss_mb']:.2f}MB"
        )


class AgentMemoryTracker:
    """
    Agent 内存追踪器 - 用于追踪单个 Agent 的内存状态
    
    用法：
        tracker = AgentMemoryTracker("analysis")
        tracker.mark_before_run()
        # ... 执行 Agent.run()
        tracker.mark_after_run()
        if tracker.detect_leak():
            logger.warning(f"Possible memory leak detected: {tracker.get_delta():.2f}MB")
    """
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.process = psutil.Process(os.getpid())
        self.before_rss_mb: float = 0.0
        self.after_rss_mb: float = 0.0
        self.baseline_rss_mb: float = 0.0
    
    def mark_baseline(self) -> None:
        """标记基线内存"""
        try:
            self.baseline_rss_mb = self.process.memory_info().rss / 1024 / 1024
        except Exception as e:
            logger.warning(f"[AgentMemoryTracker] Failed to mark baseline: {e}")
    
    def mark_before_run(self) -> None:
        """标记 run() 前的内存"""
        try:
            self.before_rss_mb = self.process.memory_info().rss / 1024 / 1024
        except Exception as e:
            logger.warning(f"[AgentMemoryTracker] Failed to mark before_run: {e}")
    
    def mark_after_run(self) -> None:
        """标记 run() 后的内存"""
        try:
            self.after_rss_mb = self.process.memory_info().rss / 1024 / 1024
        except Exception as e:
            logger.warning(f"[AgentMemoryTracker] Failed to mark after_run: {e}")
    
    def get_delta(self) -> float:
        """获取 run() 前后的内存差异 (MB)"""
        return self.after_rss_mb - self.before_rss_mb
    
    def detect_leak(self, threshold_mb: float = 10.0) -> bool:
        """
        检测是否可能存在内存泄漏
        
        Args:
            threshold_mb: 内存增长阈值，超过此值则判定为可能泄漏
            
        Returns:
            True 表示可能存在泄漏
        """
        delta = self.get_delta()
        return delta > threshold_mb
    
    def log_summary(self) -> None:
        """输出追踪摘要到日志"""
        delta = self.get_delta()
        status = "LEAK" if self.detect_leak() else "OK"
        logger.info(
            f"[AgentMemoryTracker] {self.agent_name}: "
            f"before={self.before_rss_mb:.2f}MB, "
            f"after={self.after_rss_mb:.2f}MB, "
            f"delta={delta:+.2f}MB [{status}]"
        )
