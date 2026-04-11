"""
PHPStan 静态扫描模型

用途：
- 持久化 PHPStan 静态扫描任务元数据（phpstan_scan_tasks）
- 持久化 PHPStan 扫描发现明细（phpstan_findings）
- 持久化 PHPStan 规则启停状态（phpstan_rule_states）
"""

import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Index, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.base import Base


class PhpstanScanTask(Base):
    """PHPStan 扫描任务"""

    __tablename__ = "phpstan_scan_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(
        String,
        default="pending",
        comment="pending, running, completed, failed, interrupted",
    )
    target_path = Column(String, nullable=False, comment="扫描目标路径")
    level = Column(Integer, default=5, comment="PHPStan 分析级别（0-9）")
    total_findings = Column(Integer, default=0, comment="发现总数")
    scan_duration_ms = Column(Integer, default=0, comment="扫描耗时(毫秒)")
    files_scanned = Column(Integer, default=0, comment="扫描文件数")
    error_message = Column(Text, nullable=True, comment="失败/中断错误信息")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_phpstan_tasks_project_created_at", "project_id", created_at.desc()),
        Index(
            "ix_phpstan_tasks_project_lower_status_created_at",
            "project_id",
            func.lower(status),
            created_at.desc(),
        ),
    )

    project = relationship("Project", back_populates="phpstan_scan_tasks")
    findings = relationship(
        "PhpstanFinding", back_populates="scan_task", cascade="all, delete-orphan"
    )


class PhpstanFinding(Base):
    """PHPStan 扫描发现"""

    __tablename__ = "phpstan_findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_task_id = Column(String, ForeignKey("phpstan_scan_tasks.id"), nullable=False)
    file_path = Column(String, nullable=False)
    line = Column(Integer, nullable=True)
    message = Column(Text, nullable=False)
    identifier = Column(String, nullable=True)
    tip = Column(Text, nullable=True)
    status = Column(String, default="open", comment="open, verified, false_positive")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "ix_phpstan_findings_scan_task_status_created",
            "scan_task_id",
            "status",
            created_at.desc(),
        ),
        Index(
            "ix_phpstan_findings_scan_task_file_line",
            "scan_task_id",
            "file_path",
            "line",
        ),
        Index(
            "ix_phpstan_findings_scan_task_identifier",
            "scan_task_id",
            "identifier",
        ),
    )

    scan_task = relationship("PhpstanScanTask", back_populates="findings")


class PhpstanRuleState(Base):
    """PHPStan 规则启停状态（仅用于前端规则页展示，不影响扫描命令）。"""

    __tablename__ = "phpstan_rule_states"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id = Column(String, nullable=False, unique=True, comment="规则唯一键")
    is_active = Column(Boolean, nullable=False, default=True, comment="规则是否启用")
    is_deleted = Column(Boolean, nullable=False, default=False, comment="规则是否软删除")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_phpstan_rule_states_rule_id", "rule_id"),
        Index("ix_phpstan_rule_states_is_active", "is_active"),
        Index("ix_phpstan_rule_states_is_deleted", "is_deleted"),
    )
