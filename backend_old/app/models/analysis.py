import uuid
from typing import Tuple

from sqlalchemy import Column, String, Integer, DateTime, Float, Text, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.base import Base


# 业务逻辑漏洞推送时，必须具备的 source/sink 真实性校验字段
REAL_DATAFLOW_REQUIRED_FIELDS: Tuple[str, ...] = (
    "source",
    "sink",
    "sink_reachable",
    "upstream_call_chain",
    "sink_trigger_condition",
    "attacker_flow",
)

# 用于后续验证的数据流佐证字段（建议强制补齐）
REAL_DATAFLOW_EVIDENCE_LIST_FIELDS: Tuple[str, ...] = (
    "taint_flow",
    "evidence_chain",
)

# source/sink 占位符黑名单（分析与验证阶段需保持一致）
REAL_DATAFLOW_PLACEHOLDER_VALUES: Tuple[str, ...] = (
    "source",
    "sink",
    "input",
    "user_input",
    "todo",
    "none",
    "null",
    "unknown",
    "n/a",
    "na",
    "-",
)


class InstantAnalysis(Base):
    __tablename__ = "instant_analyses"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True) # Can be anonymous? Logic says usually logged in, but localDB allowed check.
    
    language = Column(String, nullable=False)
    code_content = Column(Text, default="") 
    analysis_result = Column(Text, default="{}")
    issues_count = Column(Integer, default=0)
    quality_score = Column(Float, default=0.0)
    analysis_time = Column(Float, default=0.0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_instant_analyses_user_created_at", "user_id", created_at.desc()),
    )

    # Relationships
    user = relationship("User", backref="instant_analyses")



