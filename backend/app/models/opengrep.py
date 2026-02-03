"""
Opengrep 静态分析模型 - 数据库表定义
包括扫描任务、发现结果、规则管理、规则集、Patch分析等
"""

import uuid
from datetime import datetime
from typing import Optional, List, Any
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    JSON,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class OpengrepScanTask(Base):
    __tablename__ = "opengrep_scan_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, default="pending", comment="pending, running, completed, failed")
    target_path = Column(String, nullable=False)
    rulesets = Column(JSON, default="[]", comment="应用的规则集列表")
    total_findings = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    scan_duration_ms = Column(Integer, default=0)
    files_scanned = Column(Integer, default=0)
    lines_scanned = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="opengrep_scan_tasks")
    findings = relationship(
        "OpengrepFinding", back_populates="scan_task", cascade="all, delete-orphan"
    )


class OpengrepFinding(Base):
    __tablename__ = "opengrep_findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_task_id = Column(String, ForeignKey("opengrep_scan_tasks.id"), nullable=False)
    rule = Column(JSON, default={})
    description = Column(Text, nullable=True, comment="漏洞描述")
    file_path = Column(String, nullable=False)
    start_line = Column(Integer, nullable=True)
    code_snippet = Column(Text, nullable=True)
    severity = Column(
        String, nullable=False, comment="ERROR, WARNING, INFO"
    )  # error, warning, info
    status = Column(String, default="open", comment="open, verified, false_positive")

    # Relationships
    scan_task = relationship("OpengrepScanTask", back_populates="findings")


class OpengrepRule(Base):
    __tablename__ = "opengrep_rules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    pattern_yaml = Column(Text, nullable=False)
    language = Column(String, nullable=False)
    severity = Column(String, nullable=False, comment="ERROR, WARNING, INFO")
    confidence = Column(String, nullable=True, comment="置信度: HIGH, MEDIUM, LOW")
    description = Column(Text, nullable=True, comment="规则描述，对应YAML中的message字段")
    cwe = Column(JSON, nullable=True, comment="CWE列表，对应YAML中的cwe字段")
    source = Column(String, nullable=False, comment="internal, patch, json")
    patch = Column(String, nullable=True)
    correct = Column(Boolean, default=False, comment="是否是正确的语法")
    is_active = Column(Boolean, default=True, comment="是否启用")
    create_at = Column(DateTime(timezone=True), server_default=func.now())
