"""YASA static scan models."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class YasaScanTask(Base):
    """YASA 扫描任务。"""

    __tablename__ = "yasa_scan_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(
        String,
        default="pending",
        comment="pending, running, completed, failed, interrupted",
    )
    target_path = Column(String, nullable=False, comment="扫描目标路径")
    language = Column(String, nullable=False, default="python")
    checker_pack_ids = Column(String, nullable=True, comment="逗号分隔 checker pack")
    checker_ids = Column(Text, nullable=True, comment="逗号分隔 checker id")
    rule_config_file = Column(String, nullable=True, comment="rule config 文件路径")
    total_findings = Column(Integer, default=0, comment="发现总数")
    scan_duration_ms = Column(Integer, default=0, comment="扫描耗时(毫秒)")
    files_scanned = Column(Integer, default=0, comment="扫描文件数")
    diagnostics_summary = Column(Text, nullable=True, comment="诊断日志摘要")
    error_message = Column(Text, nullable=True, comment="失败/中断错误信息")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_yasa_tasks_project_created_at", "project_id", created_at.desc()),
        Index(
            "ix_yasa_tasks_project_lower_status_created_at",
            "project_id",
            func.lower(status),
            created_at.desc(),
        ),
    )

    project = relationship("Project", back_populates="yasa_scan_tasks")
    findings = relationship(
        "YasaFinding", back_populates="scan_task", cascade="all, delete-orphan"
    )


class YasaFinding(Base):
    """YASA 扫描发现。"""

    __tablename__ = "yasa_findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_task_id = Column(String, ForeignKey("yasa_scan_tasks.id"), nullable=False)
    rule_id = Column(String, nullable=True)
    rule_name = Column(String, nullable=True)
    level = Column(String, nullable=False, default="warning")
    message = Column(Text, nullable=False)
    file_path = Column(String, nullable=False)
    start_line = Column(Integer, nullable=True)
    end_line = Column(Integer, nullable=True)
    status = Column(String, default="open", comment="open, verified, false_positive")
    raw_payload = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "ix_yasa_findings_scan_task_status_created",
            "scan_task_id",
            "status",
            created_at.desc(),
        ),
        Index(
            "ix_yasa_findings_scan_task_file_line",
            "scan_task_id",
            "file_path",
            "start_line",
        ),
        Index("ix_yasa_findings_scan_task_level", "scan_task_id", "level"),
    )

    scan_task = relationship("YasaScanTask", back_populates="findings")
