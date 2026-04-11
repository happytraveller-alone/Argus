"""Prompt skill model for user-managed global/agent-specific prompt snippets."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


class PromptSkill(Base):
    """User-defined prompt skill snippets."""

    __tablename__ = "prompt_skills"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String(120), nullable=False)
    content = Column(Text, nullable=False)
    scope = Column(String(32), nullable=False, default="global")
    agent_key = Column(String(64), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_prompt_skills_user_scope_active", "user_id", "scope", "is_active"),
        Index("ix_prompt_skills_user_created_at", "user_id", "created_at"),
    )

    user = relationship("User", foreign_keys=[user_id])
