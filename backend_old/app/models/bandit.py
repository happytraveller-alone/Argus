"""
Bandit 静态扫描模型

用途：
- 持久化 Bandit 静态扫描任务元数据（bandit_scan_tasks）
- 持久化 Bandit 扫描发现明细（bandit_findings）
- 持久化 Bandit 规则启停状态（bandit_rule_states）
"""

import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Index, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.models.base import Base


class BanditScanTask(Base):
    """Bandit 扫描任务"""

    __tablename__ = "bandit_scan_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(
        String,
        default="pending",
        comment="pending, running, completed, failed, interrupted",
    )
    target_path = Column(String, nullable=False, comment="扫描目标路径")
    severity_level = Column(String, default="medium", comment="low, medium, high")
    confidence_level = Column(String, default="medium", comment="low, medium, high")
    total_findings = Column(Integer, default=0, comment="发现总数")
    high_count = Column(Integer, default=0, comment="HIGH 严重度数量")
    medium_count = Column(Integer, default=0, comment="MEDIUM 严重度数量")
    low_count = Column(Integer, default=0, comment="LOW 严重度数量")
    scan_duration_ms = Column(Integer, default=0, comment="扫描耗时(毫秒)")
    files_scanned = Column(Integer, default=0, comment="扫描文件数")
    error_message = Column(Text, nullable=True, comment="失败/中断错误信息")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_bandit_tasks_project_created_at", "project_id", created_at.desc()),
        Index(
            "ix_bandit_tasks_project_lower_status_created_at",
            "project_id",
            func.lower(status),
            created_at.desc(),
        ),
    )

    project = relationship("Project", back_populates="bandit_scan_tasks")
    findings = relationship(
        "BanditFinding", back_populates="scan_task", cascade="all, delete-orphan"
    )


class BanditFinding(Base):
    """Bandit 扫描发现"""

    __tablename__ = "bandit_findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_task_id = Column(String, ForeignKey("bandit_scan_tasks.id"), nullable=False)
    test_id = Column(String, nullable=False, comment="Bandit 规则ID，例如 B602")
    test_name = Column(String, nullable=False, comment="Bandit 规则名称")
    issue_severity = Column(String, nullable=False, comment="HIGH, MEDIUM, LOW")
    issue_confidence = Column(String, nullable=False, comment="HIGH, MEDIUM, LOW")
    file_path = Column(String, nullable=False)
    line_number = Column(Integer, nullable=True)
    code_snippet = Column(Text, nullable=True)
    issue_text = Column(Text, nullable=True)
    more_info = Column(String, nullable=True)
    status = Column(String, default="open", comment="open, verified, false_positive")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "ix_bandit_findings_scan_task_status_created",
            "scan_task_id",
            "status",
            created_at.desc(),
        ),
        Index(
            "ix_bandit_findings_scan_task_file_line",
            "scan_task_id",
            "file_path",
            "line_number",
        ),
        Index(
            "ix_bandit_findings_scan_task_severity",
            "scan_task_id",
            "issue_severity",
        ),
    )

    scan_task = relationship("BanditScanTask", back_populates="findings")


class BanditRuleState(Base):
    """Bandit 规则启停状态（仅用于前端规则页展示，不影响扫描命令）。"""

    __tablename__ = "bandit_rule_states"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    test_id = Column(String, nullable=False, unique=True, comment="Bandit 规则ID，例如 B602")
    is_active = Column(Boolean, nullable=False, default=True, comment="规则是否启用")
    is_deleted = Column(Boolean, nullable=False, default=False, comment="规则是否软删除")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_bandit_rule_states_test_id", "test_id"),
        Index("ix_bandit_rule_states_is_active", "is_active"),
        Index("ix_bandit_rule_states_is_deleted", "is_deleted"),
    )
