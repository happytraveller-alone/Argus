"""
Gitleaks 密钥泄露检测模型 - 数据库表定义
包括扫描任务和发现的密钥泄露结果
"""

import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    Column,
    String,
    Integer,
    Text,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class GitleaksScanTask(Base):
    """Gitleaks 扫描任务"""
    __tablename__ = "gitleaks_scan_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, default="pending", comment="pending, running, completed, failed")
    target_path = Column(String, nullable=False, comment="扫描的目标路径")
    no_git = Column(String, default="true", comment="是否不使用 git history")
    total_findings = Column(Integer, default=0, comment="发现的密钥泄露总数")
    scan_duration_ms = Column(Integer, default=0, comment="扫描耗时(毫秒)")
    files_scanned = Column(Integer, default=0, comment="已扫描文件数")
    error_message = Column(Text, nullable=True, comment="错误信息")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="gitleaks_scan_tasks")
    findings = relationship(
        "GitleaksFinding", back_populates="scan_task", cascade="all, delete-orphan"
    )


class GitleaksFinding(Base):
    """Gitleaks 发现的密钥泄露"""
    __tablename__ = "gitleaks_findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_task_id = Column(String, ForeignKey("gitleaks_scan_tasks.id"), nullable=False)
    rule_id = Column(String, nullable=False, comment="规则 ID (如 aws-access-token)")
    description = Column(Text, nullable=True, comment="密钥描述")
    file_path = Column(String, nullable=False, comment="文件路径")
    start_line = Column(Integer, nullable=True, comment="起始行号")
    end_line = Column(Integer, nullable=True, comment="结束行号")
    secret = Column(Text, nullable=True, comment="密钥内容(已脱敏)")
    match = Column(Text, nullable=True, comment="匹配的完整文本")
    commit = Column(String, nullable=True, comment="Git commit SHA (如果有)")
    author = Column(String, nullable=True, comment="作者 (如果有)")
    email = Column(String, nullable=True, comment="邮箱 (如果有)")
    date = Column(String, nullable=True, comment="日期 (如果有)")
    fingerprint = Column(String, nullable=True, comment="Gitleaks 指纹")
    status = Column(String, default="open", comment="open, verified, false_positive, fixed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    scan_task = relationship("GitleaksScanTask", back_populates="findings")
