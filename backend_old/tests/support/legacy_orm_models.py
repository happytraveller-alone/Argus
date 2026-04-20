import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.services.agent.orm_base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, index=True)
    is_active = Column(Boolean(), default=True)
    is_superuser = Column(Boolean(), default=False)
    phone = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    role = Column(String, default="member")
    github_username = Column(String, nullable=True)
    gitlab_username = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index(
            "ix_users_role_active_created_at",
            "role",
            "is_active",
            created_at.desc(),
        ),
    )


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    source_type = Column(String(20), default="repository", nullable=False)
    repository_url = Column(String, nullable=True)
    repository_type = Column(String, default="other")
    default_branch = Column(String, default="main")
    programming_languages = Column(Text, default="[]")
    zip_file_hash = Column(String(64), nullable=True, unique=True, index=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean(), default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index(
            "ix_projects_owner_active_created_at",
            "owner_id",
            "is_active",
            created_at.desc(),
        ),
        Index("ix_projects_active_updated_at", "is_active", updated_at.desc()),
        Index(
            "ix_projects_name_trgm",
            text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    owner = relationship("User", backref="projects")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    agent_tasks = relationship("AgentTask", back_populates="project", cascade="all, delete-orphan")
    opengrep_scan_tasks = relationship(
        "OpengrepScanTask", back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    __tablename__ = "project_members"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    role = Column(String, default="member")
    permissions = Column(Text, default="{}")
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        Index("ix_project_members_project_joined_at", "project_id", joined_at.desc()),
        Index("ix_project_members_user_project", "user_id", "project_id"),
    )

    project = relationship("Project", back_populates="members")
    user = relationship("User", backref="project_memberships")


class OpengrepScanTask(Base):
    __tablename__ = "opengrep_scan_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, default="pending")
    target_path = Column(String, nullable=False)
    rulesets = Column(JSON, default="[]")
    total_findings = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    scan_duration_ms = Column(Integer, default=0)
    files_scanned = Column(Integer, default=0)
    lines_scanned = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_opengrep_tasks_project_created_at", "project_id", created_at.desc()),
        Index(
            "ix_opengrep_tasks_project_lower_status_created_at",
            "project_id",
            func.lower(status),
            created_at.desc(),
        ),
    )

    project = relationship("Project", back_populates="opengrep_scan_tasks")
    findings = relationship(
        "OpengrepFinding", back_populates="scan_task", cascade="all, delete-orphan"
    )


class OpengrepFinding(Base):
    __tablename__ = "opengrep_findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_task_id = Column(String, ForeignKey("opengrep_scan_tasks.id"), nullable=False)
    rule = Column(JSON, default={})
    description = Column(Text, nullable=True)
    file_path = Column(String, nullable=False)
    start_line = Column(Integer, nullable=True)
    code_snippet = Column(Text, nullable=True)
    severity = Column(String, nullable=False)
    status = Column(String, default="open")

    __table_args__ = (
        Index("ix_opengrep_findings_scan_task_status", "scan_task_id", "status"),
        Index(
            "ix_opengrep_findings_scan_task_sev_status_line",
            "scan_task_id",
            "severity",
            "status",
            "start_line",
        ),
    )

    scan_task = relationship("OpengrepScanTask", back_populates="findings")


class OpengrepRule(Base):
    __tablename__ = "opengrep_rules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    pattern_yaml = Column(Text, nullable=False)
    language = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    confidence = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    cwe = Column(JSON, nullable=True)
    source = Column(String, nullable=False)
    patch = Column(String, nullable=True)
    correct = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    create_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("name", name="uq_opengrep_rules_name"),
        Index(
            "ix_opengrep_rules_active_filters",
            "is_active",
            "language",
            "source",
            "severity",
            "confidence",
        ),
        Index("ix_opengrep_rules_source_correct", "source", "correct"),
        Index(
            "ix_opengrep_rules_name_trgm",
            text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )
