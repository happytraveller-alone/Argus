"""PMD 静态扫描模型。"""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class PmdScanTask(Base):
    """PMD 扫描任务。"""

    __tablename__ = "pmd_scan_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(
        String,
        default="pending",
        comment="pending, running, completed, failed, interrupted",
    )
    target_path = Column(String, nullable=False, comment="扫描目标路径")
    ruleset = Column(String, nullable=False, default="security", comment="PMD ruleset")
    total_findings = Column(Integer, default=0, comment="发现总数")
    high_count = Column(Integer, default=0, comment="高优先级问题数")
    medium_count = Column(Integer, default=0, comment="中优先级问题数")
    low_count = Column(Integer, default=0, comment="低优先级问题数")
    scan_duration_ms = Column(Integer, default=0, comment="扫描耗时(毫秒)")
    files_scanned = Column(Integer, default=0, comment="扫描文件数")
    error_message = Column(Text, nullable=True, comment="失败/中断错误信息")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_pmd_tasks_project_created_at", "project_id", created_at.desc()),
        Index(
            "ix_pmd_tasks_project_lower_status_created_at",
            "project_id",
            func.lower(status),
            created_at.desc(),
        ),
    )

    project = relationship("Project", back_populates="pmd_scan_tasks")
    findings = relationship(
        "PmdFinding", back_populates="scan_task", cascade="all, delete-orphan"
    )


class PmdFinding(Base):
    """PMD 扫描发现。"""

    __tablename__ = "pmd_findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_task_id = Column(String, ForeignKey("pmd_scan_tasks.id"), nullable=False)
    file_path = Column(String, nullable=False)
    begin_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    rule = Column(String, nullable=True)
    ruleset = Column(String, nullable=True)
    priority = Column(Integer, nullable=True)
    message = Column(Text, nullable=False)
    status = Column(String, default="open", comment="open, verified, false_positive")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "ix_pmd_findings_scan_task_status_created",
            "scan_task_id",
            "status",
            created_at.desc(),
        ),
        Index(
            "ix_pmd_findings_scan_task_file_line",
            "scan_task_id",
            "file_path",
            "begin_line",
        ),
        Index("ix_pmd_findings_scan_task_priority", "scan_task_id", "priority"),
    )

    scan_task = relationship("PmdScanTask", back_populates="findings")
