"""Frozen schema snapshot for Alembic revision 5b0f3c9a6d7e.

This module copies the ORM table definitions that existed when the squashed
baseline revision was created. Alembic must import this snapshot instead of the
live application models so later schema changes do not leak into the baseline.
"""

from sqlalchemy.orm import as_declarative, declared_attr


@as_declarative()
class Base:
    id: str
    __name__: str

    @declared_attr
    def __tablename__(cls) -> str:
        return cls.__name__.lower() + "s"


import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Index
from sqlalchemy.sql import func

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, index=True)
    is_active = Column(Boolean(), default=True)
    is_superuser = Column(Boolean(), default=False)
    
    # Profile fields
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

"""
用户配置模型 - 存储用户的LLM和其他配置
"""

import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship


class UserConfig(Base):
    """用户配置表"""
    __tablename__ = "user_configs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    
    # LLM配置（JSON格式存储）
    llm_config = Column(Text, default="{}")
    
    # 其他配置（JSON格式存储）
    other_config = Column(Text, default="{}")
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="config")

import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text, Index, UniqueConstraint, text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, index=True, nullable=False)
    description = Column(Text, nullable=True)
    
    # 项目来源类型: 'repository' (远程仓库) 或 'zip' (ZIP上传)
    source_type = Column(String(20), default="repository", nullable=False)
    
    # 仓库相关字段 (仅 source_type='repository' 时使用)
    repository_url = Column(String, nullable=True)
    repository_type = Column(String, default="other")  # github, gitlab, gitea, other
    default_branch = Column(String, default="main")
    
    programming_languages = Column(Text, default="[]")  # Stored as JSON string
    
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

    # Relationships
    owner = relationship("User", backref="projects")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    tasks = relationship("AuditTask", back_populates="project", cascade="all, delete-orphan")
    agent_tasks = relationship("AgentTask", back_populates="project", cascade="all, delete-orphan")
    infos = relationship("ProjectInfo", back_populates="project", cascade="all, delete-orphan")
    opengrep_scan_tasks = relationship(
        "OpengrepScanTask", back_populates="project", cascade="all, delete-orphan"
    )
    gitleaks_scan_tasks = relationship(
        "GitleaksScanTask", back_populates="project", cascade="all, delete-orphan"
    )
    # Bandit 静态扫描任务关系（新增）
    bandit_scan_tasks = relationship(
        "BanditScanTask", back_populates="project", cascade="all, delete-orphan"
    )
    # PHPStan 静态扫描任务关系（新增）
    phpstan_scan_tasks = relationship(
        "PhpstanScanTask", back_populates="project", cascade="all, delete-orphan"
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

    # Relationships
    project = relationship("Project", back_populates="members")
    user = relationship("User", backref="project_memberships")

from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime, JSON, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
from sqlalchemy.sql import func


class ProjectInfo(Base):
    __tablename__ = "project_info"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    language_info = Column(JSON, nullable=True, comment="项目所用编程语言信息, JSON格式")
    description = Column(String, nullable=True, comment="项目描述, 由大模型生成")
    status = Column(String, default="pending", comment="信息状态: pending, completed, failed")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="创建时间")

    __table_args__ = (
        UniqueConstraint("project_id", name="uq_project_info_project_id"),
        Index("ix_project_info_project_created_at", "project_id", created_at.desc()),
    )

    # Relationships
    project = relationship("Project", back_populates="infos")

import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Float, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship


class AuditTask(Base):
    __tablename__ = "audit_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    created_by = Column(String, ForeignKey("users.id"), nullable=False)
    
    task_type = Column(String, nullable=False)
    status = Column(String, default="pending", index=True)
    branch_name = Column(String, nullable=True)
    
    exclude_patterns = Column(Text, default="[]")
    scan_config = Column(Text, default="{}")
    
    # Stats
    total_files = Column(Integer, default=0)
    scanned_files = Column(Integer, default=0)
    total_lines = Column(Integer, default=0)
    issues_count = Column(Integer, default=0)
    quality_score = Column(Float, default=0.0)
    
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_audit_tasks_created_by_created_at", "created_by", created_at.desc()),
        Index(
            "ix_audit_tasks_project_status_created_at",
            "project_id",
            "status",
            created_at.desc(),
        ),
    )

    # Relationships
    project = relationship("Project", back_populates="tasks")
    creator = relationship("User", foreign_keys=[created_by])
    issues = relationship("AuditIssue", back_populates="task", cascade="all, delete-orphan")


class AuditIssue(Base):
    __tablename__ = "audit_issues"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String, ForeignKey("audit_tasks.id"), nullable=False)
    
    file_path = Column(String, nullable=False)
    line_number = Column(Integer, nullable=True)
    column_number = Column(Integer, nullable=True)
    issue_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)  # critical, high, medium, low
    
    # 问题信息
    title = Column(String, nullable=True)  # 问题标题
    message = Column(Text, nullable=True)  # 兼容旧字段，同title
    description = Column(Text, nullable=True)  # 详细描述
    suggestion = Column(Text, nullable=True)  # 修复建议
    code_snippet = Column(Text, nullable=True)  # 问题代码片段
    ai_explanation = Column(Text, nullable=True)  # AI解释（JSON格式的xai字段）
    
    status = Column(String, default="open")  # open, resolved, false_positive
    resolved_by = Column(String, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_audit_issues_task_status", "task_id", "status"),
        Index("ix_audit_issues_task_severity", "task_id", "severity"),
    )

    # Relationships
    task = relationship("AuditTask", back_populates="issues")
    resolver = relationship("User", foreign_keys=[resolved_by])

import uuid
from sqlalchemy import Column, String, Integer, DateTime, Float, Text, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

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

"""
提示词模板模型 - 存储自定义审计提示词
"""

import uuid
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Boolean, Integer, Index, text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship


class PromptTemplate(Base):
    """提示词模板表"""
    __tablename__ = "prompt_templates"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)  # 模板名称
    description = Column(Text, nullable=True)  # 模板描述
    
    # 模板类型: system(系统提示词), user(用户提示词), analysis(分析提示词)
    template_type = Column(String(50), default="system")
    
    # 提示词内容（支持中英文）
    content_zh = Column(Text, nullable=True)  # 中文提示词
    content_en = Column(Text, nullable=True)  # 英文提示词
    
    # 模板变量说明（JSON格式）
    variables = Column(Text, default="{}")  # {"language": "编程语言", "code": "代码内容"}
    
    # 状态标记
    is_default = Column(Boolean, default=False)  # 是否默认模板
    is_system = Column(Boolean, default=False)  # 是否系统内置（不可删除）
    is_active = Column(Boolean, default=True)  # 是否启用
    
    # 排序权重
    sort_order = Column(Integer, default=0)
    
    # 创建者（系统模板为空）
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_prompt_templates_active_type_sort", "is_active", "template_type", "sort_order"),
        Index(
            "ix_prompt_templates_name_trgm",
            text("lower(name) gin_trgm_ops"),
            postgresql_using="gin",
        ),
    )

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

"""
审计规则模型 - 存储自定义审计规范
"""

import uuid
from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    Integer,
    Float,
    Index,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship


class AuditRuleSet(Base):
    """审计规则集表"""
    __tablename__ = "audit_rule_sets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)  # 规则集名称
    description = Column(Text, nullable=True)  # 规则集描述
    
    # 适用语言: all, python, javascript, java, go, etc.
    language = Column(String(50), default="all")
    
    # 规则集类型: security(安全), quality(质量), performance(性能), custom(自定义)
    rule_type = Column(String(50), default="custom")
    
    # 严重程度权重配置（JSON格式）
    # {"critical": 10, "high": 5, "medium": 2, "low": 1}
    severity_weights = Column(Text, default='{"critical": 10, "high": 5, "medium": 2, "low": 1}')
    
    # 状态标记
    is_default = Column(Boolean, default=False)  # 是否默认规则集
    is_system = Column(Boolean, default=False)  # 是否系统内置
    is_active = Column(Boolean, default=True)  # 是否启用
    
    # 排序权重
    sort_order = Column(Integer, default=0)
    
    # 创建者
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index(
            "ix_audit_rule_sets_active_language_type",
            "is_active",
            "language",
            "rule_type",
        ),
    )

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    rules = relationship("AuditRule", back_populates="rule_set", cascade="all, delete-orphan")


class AuditRule(Base):
    """审计规则表"""
    __tablename__ = "audit_rules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_set_id = Column(String, ForeignKey("audit_rule_sets.id"), nullable=False)
    
    # 规则标识（唯一标识符，如 SEC001, PERF002）
    rule_code = Column(String(50), nullable=False)
    
    # 规则名称
    name = Column(String(200), nullable=False)
    
    # 规则描述
    description = Column(Text, nullable=True)
    
    # 规则类别: security, bug, performance, style, maintainability
    category = Column(String(50), nullable=False)
    
    # 默认严重程度: critical, high, medium, low
    severity = Column(String(20), default="medium")
    
    # 自定义检测提示词（可选，用于增强LLM检测）
    custom_prompt = Column(Text, nullable=True)
    
    # 修复建议模板
    fix_suggestion = Column(Text, nullable=True)
    
    # 参考链接（如CWE、OWASP链接）
    reference_url = Column(String(500), nullable=True)
    
    # 是否启用
    enabled = Column(Boolean, default=True)
    
    # 排序权重
    sort_order = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("rule_set_id", "rule_code", name="uq_audit_rules_rule_set_code"),
        Index("ix_audit_rules_rule_set_enabled_sort", "rule_set_id", "enabled", "sort_order"),
    )

    # Relationships
    rule_set = relationship("AuditRuleSet", back_populates="rules")

"""
Agent 审计任务模型
支持 AI Agent 自主漏洞挖掘和验证
"""

import uuid
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import (
    Column, String, Integer, Float, Text, Boolean, 
    DateTime, ForeignKey, Enum as SQLEnum, JSON, Index, text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


if TYPE_CHECKING:
    from .project import Project


class AgentTaskStatus:
    """Agent 任务状态"""
    PENDING = "pending"           # 等待执行
    INITIALIZING = "initializing" # 初始化中
    RUNNING = "running"           # 运行中
    PLANNING = "planning"         # 规划阶段
    INDEXING = "indexing"         # 索引阶段
    ANALYZING = "analyzing"       # 分析阶段
    VERIFYING = "verifying"       # 验证阶段
    REPORTING = "reporting"       # 报告生成
    COMPLETED = "completed"       # 已完成
    FAILED = "failed"             # 失败
    CANCELLED = "cancelled"       # 已取消
    INTERRUPTED = "interrupted"   # 服务中断
    PAUSED = "paused"             # 已暂停


class AgentTaskPhase:
    """Agent 执行阶段"""
    PLANNING = "planning"
    INDEXING = "indexing"
    RECONNAISSANCE = "reconnaissance"
    ANALYSIS = "analysis"
    VERIFICATION = "verification"
    REPORTING = "reporting"


class AgentTask(Base):
    """Agent 审计任务"""
    __tablename__ = "agent_tasks"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    
    # 任务基本信息
    name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    task_type = Column(String(50), default="agent_audit")
    
    # 任务配置
    audit_scope = Column(JSON, nullable=True)  # 审计范围配置
    target_vulnerabilities = Column(JSON, nullable=True)  # 目标漏洞类型
    verification_level = Column(String(50), default="analysis_with_poc_plan")  # unified mode: analysis + PoC plan
    
    # 分支信息（仓库项目）
    branch_name = Column(String(255), nullable=True)
    
    # 排除模式
    exclude_patterns = Column(JSON, nullable=True)
    
    # 文件范围
    target_files = Column(JSON, nullable=True)  # 指定扫描的文件列表
    
    # LLM 配置
    llm_config = Column(JSON, nullable=True)  # LLM 配置
    
    # Agent 配置
    agent_config = Column(JSON, nullable=True)  # Agent 特定配置
    max_iterations = Column(Integer, default=50)  # 最大迭代次数
    token_budget = Column(Integer, default=100000)  # Token 预算
    timeout_seconds = Column(Integer, default=1800)  # 超时时间（秒）
    
    # 状态
    status = Column(String(20), default=AgentTaskStatus.PENDING)
    current_phase = Column(String(50), nullable=True)
    current_step = Column(String(255), nullable=True)  # 当前执行步骤描述
    error_message = Column(Text, nullable=True)
    
    # 进度统计
    total_files = Column(Integer, default=0)
    indexed_files = Column(Integer, default=0)
    analyzed_files = Column(Integer, default=0)  # 实际扫描过的文件数
    files_with_findings = Column(Integer, default=0)  # 有漏洞发现的文件数
    total_chunks = Column(Integer, default=0)  # 代码块总数
    
    # Agent 统计
    total_iterations = Column(Integer, default=0)  # Agent 迭代次数
    tool_calls_count = Column(Integer, default=0)  # 工具调用次数
    tokens_used = Column(Integer, default=0)  # 已使用 Token 数
    
    # 发现统计
    findings_count = Column(Integer, default=0)  # 发现总数
    verified_count = Column(Integer, default=0)  # 已验证数
    false_positive_count = Column(Integer, default=0)  # 误报数
    
    # 严重程度统计
    critical_count = Column(Integer, default=0)
    high_count = Column(Integer, default=0)
    medium_count = Column(Integer, default=0)
    low_count = Column(Integer, default=0)
    
    # 质量评分
    quality_score = Column(Float, default=0.0)
    security_score = Column(Float, default=0.0)
    
    # 审计计划
    audit_plan = Column(JSON, nullable=True)  # Agent 生成的审计计划
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # 创建者
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)

    __table_args__ = (
        Index(
            "ix_agent_tasks_project_status_created",
            "project_id",
            "status",
            created_at.desc(),
        ),
        Index("ix_agent_tasks_created_by_created", "created_by", created_at.desc()),
    )
    
    # 关联关系
    project = relationship("Project", back_populates="agent_tasks")
    events = relationship("AgentEvent", back_populates="task", cascade="all, delete-orphan", order_by="AgentEvent.created_at")
    findings = relationship("AgentFinding", back_populates="task", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<AgentTask {self.id} - {self.status}>"
    
    @property
    def progress_percentage(self) -> float:
        """计算进度百分比"""
        if self.status == AgentTaskStatus.COMPLETED:
            return 100.0
        
        phase_weights = {
            AgentTaskPhase.PLANNING: 5,
            AgentTaskPhase.INDEXING: 15,
            AgentTaskPhase.RECONNAISSANCE: 10,
            AgentTaskPhase.ANALYSIS: 50,
            AgentTaskPhase.VERIFICATION: 15,
            AgentTaskPhase.REPORTING: 5,
        }
        
        completed_weight = 0
        current_found = False
        
        for phase, weight in phase_weights.items():
            if phase == self.current_phase:
                current_found = True
                # 估算当前阶段进度
                if phase == AgentTaskPhase.INDEXING and self.total_files > 0:
                    completed_weight += weight * (self.indexed_files / self.total_files)
                elif phase == AgentTaskPhase.ANALYSIS and self.total_files > 0:
                    completed_weight += weight * (self.analyzed_files / self.total_files)
                else:
                    completed_weight += weight * 0.5
                break
            elif not current_found:
                completed_weight += weight
        
        return min(completed_weight, 99.0)


class AgentEventType:
    """Agent 事件类型"""
    # 系统事件
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_ERROR = "task_error"
    TASK_CANCEL = "task_cancel"
    
    # 阶段事件
    PHASE_START = "phase_start"
    PHASE_COMPLETE = "phase_complete"
    
    # Agent 思考
    THINKING = "thinking"
    PLANNING = "planning"
    DECISION = "decision"
    
    # 工具调用
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"

    # 发现相关
    FINDING_NEW = "finding_new"
    FINDING_UPDATE = "finding_update"
    FINDING_VERIFIED = "finding_verified"
    FINDING_FALSE_POSITIVE = "finding_false_positive"
    
    # 沙箱相关
    SANDBOX_START = "sandbox_start"
    SANDBOX_EXEC = "sandbox_exec"
    SANDBOX_RESULT = "sandbox_result"
    SANDBOX_ERROR = "sandbox_error"
    
    # 进度
    PROGRESS = "progress"
    
    # 日志
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    DEBUG = "debug"


class AgentEvent(Base):
    """Agent 执行事件（用于实时日志和回放）"""
    __tablename__ = "agent_events"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 事件信息
    event_type = Column(String(50), nullable=False, index=True)
    phase = Column(String(50), nullable=True)
    
    # 事件内容
    message = Column(Text, nullable=True)
    
    # 工具调用相关
    tool_name = Column(String(100), nullable=True)
    tool_input = Column(JSON, nullable=True)
    tool_output = Column(JSON, nullable=True)
    tool_duration_ms = Column(Integer, nullable=True)  # 工具执行时长（毫秒）
    
    # 关联的发现
    finding_id = Column(String(36), nullable=True)
    
    # Token 消耗
    tokens_used = Column(Integer, default=0)
    
    # 元数据
    event_metadata = Column(JSON, nullable=True)
    
    # 序号（用于排序）
    sequence = Column(Integer, default=0, index=True)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_agent_events_task_sequence", "task_id", "sequence"),
        Index("ix_agent_events_task_created_at", "task_id", created_at.desc()),
        Index("ix_agent_events_task_type_sequence", "task_id", "event_type", "sequence"),
    )
    
    # 关联关系
    task = relationship("AgentTask", back_populates="events")
    
    def __repr__(self):
        return f"<AgentEvent {self.event_type} - {self.message[:50] if self.message else ''}>"
    
    def to_sse_dict(self) -> dict:
        """转换为 SSE 事件格式"""
        return {
            "id": self.id,
            "type": self.event_type,
            "phase": self.phase,
            "message": self.message,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": self.tool_output,
            "tool_duration_ms": self.tool_duration_ms,
            "finding_id": self.finding_id,
            "tokens_used": self.tokens_used,
            "metadata": self.event_metadata,
            "sequence": self.sequence,
            "timestamp": self.created_at.isoformat() if self.created_at else None,
        }


class VulnerabilitySeverity:
    """漏洞严重程度"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VulnerabilityType:
    """漏洞类型"""
    SQL_INJECTION = "sql_injection"
    NOSQL_INJECTION = "nosql_injection"
    XSS = "xss"
    COMMAND_INJECTION = "command_injection"
    CODE_INJECTION = "code_injection"
    PATH_TRAVERSAL = "path_traversal"
    FILE_INCLUSION = "file_inclusion"
    SSRF = "ssrf"
    XXE = "xxe"
    DESERIALIZATION = "deserialization"
    AUTH_BYPASS = "auth_bypass"
    IDOR = "idor"
    SENSITIVE_DATA_EXPOSURE = "sensitive_data_exposure"
    HARDCODED_SECRET = "hardcoded_secret"
    WEAK_CRYPTO = "weak_crypto"
    RACE_CONDITION = "race_condition"
    BUSINESS_LOGIC = "business_logic"
    MEMORY_CORRUPTION = "memory_corruption"
    OTHER = "other"


class FindingStatus:
    """发现状态"""
    NEW = "new"               # 新发现
    ANALYZING = "analyzing"   # 分析中
    VERIFIED = "verified"     # 已验证（confirmed 或 likely 状态）
    UNCERTAIN = "uncertain"   # 不确定（信息不足，需进一步验证）
    FALSE_POSITIVE = "false_positive"  # 误报
    NEEDS_REVIEW = "needs_review"      # 需要人工审核
    FIXED = "fixed"           # 已修复
    WONT_FIX = "wont_fix"     # 不修复
    DUPLICATE = "duplicate"   # 重复


class AgentFinding(Base):
    """Agent 发现的漏洞"""
    __tablename__ = "agent_findings"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # 漏洞基本信息
    vulnerability_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    
    # 位置信息
    file_path = Column(Text, nullable=True, index=True)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    column_start = Column(Integer, nullable=True)
    column_end = Column(Integer, nullable=True)
    function_name = Column(String(255), nullable=True)
    class_name = Column(String(255), nullable=True)
    
    # 代码片段
    code_snippet = Column(Text, nullable=True)
    code_context = Column(Text, nullable=True)  # 更多上下文
    
    # 数据流信息
    source = Column(Text, nullable=True)  # 污点源
    sink = Column(Text, nullable=True)    # 危险函数
    dataflow_path = Column(JSON, nullable=True)  # 数据流路径
    
    # 验证信息
    status = Column(String(30), default=FindingStatus.NEW, index=True)
    is_verified = Column(Boolean, default=False)
    verification_method = Column(Text, nullable=True)
    verification_result = Column(JSON, nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    
    # PoC
    has_poc = Column(Boolean, default=False)
    poc_code = Column(Text, nullable=True)
    poc_description = Column(Text, nullable=True)
    poc_steps = Column(JSON, nullable=True)  # 复现步骤
    
    # 修复建议
    suggestion = Column(Text, nullable=True)
    fix_code = Column(Text, nullable=True)
    fix_description = Column(Text, nullable=True)
    references = Column(JSON, nullable=True)  # 参考链接 CWE, OWASP 等
    
    # AI 解释
    ai_explanation = Column(Text, nullable=True)
    ai_confidence = Column(Float, nullable=True)  # AI 置信度 0-1
    report = Column(Text, nullable=True)  # ReportAgent 生成的漏洞详情报告（Markdown）
    
    # 验证 Agent 的标准化结果（与 VerificationResultModel 对应）
    verdict = Column(String(20), nullable=True, index=True)  # confirmed|likely|uncertain|false_positive
    confidence = Column(Float, nullable=True)  # 验证置信度 [0.0-1.0]
    reachability = Column(String(30), nullable=True)  # reachable|likely_reachable|unknown|unreachable
    verification_evidence = Column(Text, nullable=True)  # 验证证据
    
    # XAI (可解释AI)
    xai_what = Column(Text, nullable=True)
    xai_why = Column(Text, nullable=True)
    xai_how = Column(Text, nullable=True)
    xai_impact = Column(Text, nullable=True)
    
    # 关联规则
    matched_rule_code = Column(String(100), nullable=True)
    matched_pattern = Column(Text, nullable=True)
    
    # CVSS 评分（可选）
    cvss_score = Column(Float, nullable=True)
    cvss_vector = Column(String(100), nullable=True)
    
    # 元数据
    finding_metadata = Column(JSON, nullable=True)
    tags = Column(JSON, nullable=True)
    
    # 去重标识
    fingerprint = Column(String(64), nullable=True, index=True)  # 用于去重的指纹
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_agent_findings_task_status_created", "task_id", "status", created_at.desc()),
        Index(
            "ix_agent_findings_task_verified_created",
            "task_id",
            "is_verified",
            created_at.desc(),
        ),
        Index(
            "ix_agent_findings_task_severity_created_active",
            "task_id",
            "severity",
            created_at.desc(),
            postgresql_where=text("status <> 'false_positive'"),
        ),
    )
    
    # 关联关系
    task = relationship("AgentTask", back_populates="findings")
    
    def __repr__(self):
        return f"<AgentFinding {self.vulnerability_type} - {self.severity} - {self.file_path}>"
    
    def generate_fingerprint(self) -> str:
        """生成去重指纹"""
        import hashlib
        components = [
            self.vulnerability_type or "",
            self.file_path or "",
            str(self.line_start or 0),
            self.function_name or "",
            (self.code_snippet or "")[:200],
        ]
        content = "|".join(components)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "vulnerability_type": self.vulnerability_type,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "code_snippet": self.code_snippet,
            "status": self.status,
            "is_verified": self.is_verified,
            "has_poc": self.has_poc,
            "poc_code": self.poc_code,
            "suggestion": self.suggestion,
            "fix_code": self.fix_code,
            "ai_explanation": self.ai_explanation,
            "ai_confidence": self.ai_confidence,
            "report": self.report,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentCheckpoint(Base):
    """
    Agent 检查点
    
    用于持久化 Agent 状态，支持：
    - 任务恢复
    - 状态回滚
    - 执行历史追踪
    """
    __tablename__ = "agent_checkpoints"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Agent 信息
    agent_id = Column(String(50), nullable=False, index=True)
    agent_name = Column(String(255), nullable=False)
    agent_type = Column(String(50), nullable=False)
    parent_agent_id = Column(String(50), nullable=True)
    
    # 状态数据（JSON 序列化的 AgentState）
    state_data = Column(Text, nullable=False)
    
    # 执行状态
    iteration = Column(Integer, default=0)
    status = Column(String(30), nullable=False)
    
    # 统计信息
    total_tokens = Column(Integer, default=0)
    tool_calls = Column(Integer, default=0)
    findings_count = Column(Integer, default=0)
    
    # 检查点类型
    checkpoint_type = Column(String(30), default="auto")  # auto, manual, error, final
    checkpoint_name = Column(String(255), nullable=True)
    
    # 元数据
    checkpoint_metadata = Column(JSON, nullable=True)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (
        Index("ix_agent_checkpoints_task_created", "task_id", created_at.desc()),
        Index(
            "ix_agent_checkpoints_task_agent_created",
            "task_id",
            "agent_id",
            created_at.desc(),
        ),
    )
    
    def __repr__(self):
        return f"<AgentCheckpoint {self.agent_id} - iter {self.iteration}>"
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "parent_agent_id": self.parent_agent_id,
            "iteration": self.iteration,
            "status": self.status,
            "total_tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "findings_count": self.findings_count,
            "checkpoint_type": self.checkpoint_type,
            "checkpoint_name": self.checkpoint_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentTreeNode(Base):
    """
    Agent 树节点
    
    记录动态 Agent 树的结构，用于：
    - 可视化 Agent 树
    - 追踪 Agent 间关系
    - 分析执行流程
    """
    __tablename__ = "agent_tree_nodes"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Agent 信息
    agent_id = Column(String(50), nullable=False, unique=True, index=True)
    agent_name = Column(String(255), nullable=False)
    agent_type = Column(String(50), nullable=False)
    
    # 树结构
    parent_agent_id = Column(String(50), nullable=True, index=True)
    depth = Column(Integer, default=0)  # 树深度
    
    # 任务信息
    task_description = Column(Text, nullable=True)
    knowledge_modules = Column(JSON, nullable=True)
    
    # 执行状态
    status = Column(String(30), default="created")
    
    # 执行结果
    result_summary = Column(Text, nullable=True)
    findings_count = Column(Integer, default=0)
    
    # 统计
    iterations = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    tool_calls = Column(Integer, default=0)
    duration_ms = Column(Integer, nullable=True)
    
    # 时间戳
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_agent_tree_nodes_task_depth_created", "task_id", "depth", "created_at"),
    )
    
    def __repr__(self):
        return f"<AgentTreeNode {self.agent_name} ({self.agent_id})>"
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_type": self.agent_type,
            "parent_agent_id": self.parent_agent_id,
            "depth": self.depth,
            "task_description": self.task_description,
            "knowledge_modules": self.knowledge_modules,
            "status": self.status,
            "result_summary": self.result_summary,
            "findings_count": self.findings_count,
            "iterations": self.iterations,
            "tokens_used": self.tokens_used,
            "tool_calls": self.tool_calls,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

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
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func



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

    __table_args__ = (
        Index("ix_gitleaks_tasks_project_created_at", "project_id", created_at.desc()),
        Index(
            "ix_gitleaks_tasks_project_lower_status_created_at",
            "project_id",
            func.lower(status),
            created_at.desc(),
        ),
    )

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

    __table_args__ = (
        Index(
            "ix_gitleaks_findings_scan_task_status_created",
            "scan_task_id",
            "status",
            created_at.desc(),
        ),
        Index(
            "ix_gitleaks_findings_scan_task_file_line",
            "scan_task_id",
            "file_path",
            "start_line",
        ),
        Index("ix_gitleaks_findings_fingerprint", "fingerprint"),
    )

    # Relationships
    scan_task = relationship("GitleaksScanTask", back_populates="findings")


class GitleaksRule(Base):
    """Gitleaks 规则定义（结构化字段，运行时渲染为 TOML）"""

    __tablename__ = "gitleaks_rules"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    rule_id = Column(String, nullable=False, comment="gitleaks 规则 ID")
    secret_group = Column(Integer, nullable=False, default=0)
    regex = Column(Text, nullable=False)
    keywords = Column(JSON, nullable=False, default=list)
    path = Column(Text, nullable=True)
    tags = Column(JSON, nullable=False, default=list)
    entropy = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    source = Column(String, nullable=False, default="custom")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("name", name="uq_gitleaks_rules_name"),
        UniqueConstraint("rule_id", name="uq_gitleaks_rules_rule_id"),
        Index("ix_gitleaks_rules_is_active", "is_active"),
        Index("ix_gitleaks_rules_rule_id", "rule_id"),
        Index("ix_gitleaks_rules_source_active", "source", "is_active"),
    )

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
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func



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

    __table_args__ = (
        Index("ix_opengrep_tasks_project_created_at", "project_id", created_at.desc()),
        Index(
            "ix_opengrep_tasks_project_lower_status_created_at",
            "project_id",
            func.lower(status),
            created_at.desc(),
        ),
    )

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

"""
Bandit 静态扫描模型

用途：
- 持久化 Bandit 静态扫描任务元数据（bandit_scan_tasks）
- 持久化 Bandit 扫描发现明细（bandit_findings）
"""

import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship



class BanditScanTask(Base):
    """Bandit 扫描任务"""

    __tablename__ = "bandit_scan_tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String, ForeignKey("projects.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(
        String,
        default="pending",
        comment="pending, running, completed, failed, interrupted",
    )
    target_path = Column(String, nullable=False, comment="扫描目标路径")
    severity_level = Column(String, default="medium", comment="low, medium, high")
    confidence_level = Column(String, default="medium", comment="low, medium, high")
    total_findings = Column(Integer, default=0, comment="发现总数")
    high_count = Column(Integer, default=0, comment="HIGH 严重度数量")
    medium_count = Column(Integer, default=0, comment="MEDIUM 严重度数量")
    low_count = Column(Integer, default=0, comment="LOW 严重度数量")
    scan_duration_ms = Column(Integer, default=0, comment="扫描耗时(毫秒)")
    files_scanned = Column(Integer, default=0, comment="扫描文件数")
    error_message = Column(Text, nullable=True, comment="失败/中断错误信息")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_bandit_tasks_project_created_at", "project_id", created_at.desc()),
        Index(
            "ix_bandit_tasks_project_lower_status_created_at",
            "project_id",
            func.lower(status),
            created_at.desc(),
        ),
    )

    project = relationship("Project", back_populates="bandit_scan_tasks")
    findings = relationship(
        "BanditFinding", back_populates="scan_task", cascade="all, delete-orphan"
    )


class BanditFinding(Base):
    """Bandit 扫描发现"""

    __tablename__ = "bandit_findings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_task_id = Column(String, ForeignKey("bandit_scan_tasks.id"), nullable=False)
    test_id = Column(String, nullable=False, comment="Bandit 规则ID，例如 B602")
    test_name = Column(String, nullable=False, comment="Bandit 规则名称")
    issue_severity = Column(String, nullable=False, comment="HIGH, MEDIUM, LOW")
    issue_confidence = Column(String, nullable=False, comment="HIGH, MEDIUM, LOW")
    file_path = Column(String, nullable=False)
    line_number = Column(Integer, nullable=True)
    code_snippet = Column(Text, nullable=True)
    issue_text = Column(Text, nullable=True)
    more_info = Column(String, nullable=True)
    status = Column(String, default="open", comment="open, verified, false_positive, fixed")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "ix_bandit_findings_scan_task_status_created",
            "scan_task_id",
            "status",
            created_at.desc(),
        ),
        Index(
            "ix_bandit_findings_scan_task_file_line",
            "scan_task_id",
            "file_path",
            "line_number",
        ),
        Index(
            "ix_bandit_findings_scan_task_severity",
            "scan_task_id",
            "issue_severity",
        ),
    )

    scan_task = relationship("BanditScanTask", back_populates="findings")

"""
PHPStan 静态扫描模型

用途：
- 持久化 PHPStan 静态扫描任务元数据（phpstan_scan_tasks）
- 持久化 PHPStan 扫描发现明细（phpstan_findings）
"""

import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Index
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship



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
    status = Column(String, default="open", comment="open, verified, false_positive, fixed")
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

metadata = Base.metadata
