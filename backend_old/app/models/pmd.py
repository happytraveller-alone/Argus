"""PMD 自定义 ruleset 配置模型。"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.sql import func

from app.models.base import Base


class PmdRuleConfig(Base):
    """持久化用户导入的 PMD XML ruleset。"""

    __tablename__ = "pmd_rule_configs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    filename = Column(String, nullable=False)
    xml_content = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_pmd_rule_configs_created_at", "created_at"),
        Index("ix_pmd_rule_configs_is_active", "is_active"),
        Index("ix_pmd_rule_configs_is_active_created_at", "is_active", "created_at"),
    )
