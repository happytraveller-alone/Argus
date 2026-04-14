from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class ProjectManagementMetrics(Base):
    __tablename__ = "project_management_metrics"

    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    archive_size_bytes = Column(BigInteger, default=0)
    archive_original_filename = Column(String, nullable=True)
    archive_uploaded_at = Column(DateTime(timezone=True), nullable=True)

    total_tasks = Column(Integer, default=0)
    completed_tasks = Column(Integer, default=0)
    running_tasks = Column(Integer, default=0)

    agent_tasks = Column(Integer, default=0)
    opengrep_tasks = Column(Integer, default=0)
    gitleaks_tasks = Column(Integer, default=0)
    bandit_tasks = Column(Integer, default=0)
    phpstan_tasks = Column(Integer, default=0)

    critical = Column(Integer, default=0)
    high = Column(Integer, default=0)
    medium = Column(Integer, default=0)
    low = Column(Integer, default=0)
    verified_critical = Column(Integer, default=0)
    verified_high = Column(Integer, default=0)
    verified_medium = Column(Integer, default=0)
    verified_low = Column(Integer, default=0)

    last_completed_task_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(String, default="pending", nullable=False)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    project = relationship(
        "Project",
        back_populates="management_metrics",
    )
