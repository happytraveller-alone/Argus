"""
全局搜索 Schema
支持跨 Project、AgentTask、AgentFinding 的统一搜索
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


# ============ 请求和响应基础模型 ============


class SearchRequest(BaseModel):
    """搜索请求"""
    keyword: str = Field(..., min_length=1, max_length=500, description="搜索关键词")
    limit: int = Field(default=50, ge=1, le=200, description="返回结果数量(每个类型)")
    offset: int = Field(default=0, ge=0, description="分页偏移")
    sort_by: str = Field(default="created_at", description="排序字段: created_at, relevance")
    sort_order: str = Field(default="desc", description="排序顺序: asc, desc")


# ============ Project 相关模型 ============


class SearchProjectItem(BaseModel):
    """搜索结果中的项目信息"""
    id: str
    name: str
    description: Optional[str] = None
    source_type: str  # repository, zip
    repository_url: Optional[str] = None
    repository_type: Optional[str] = None
    owner_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============ AgentTask 相关模型 ============


class SearchAgentTaskItem(BaseModel):
    """搜索结果中的 Agent 任务信息"""
    id: str
    project_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    task_type: str
    status: str
    current_phase: Optional[str] = None
    total_files: int = 0
    total_iterations: int = 0
    tokens_used: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============ AgentFinding 相关模型 ============


class SearchAgentFindingItem(BaseModel):
    """搜索结果中的发现信息"""
    id: str
    task_id: str
    vulnerability_type: str
    severity: str
    title: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    line_start: Optional[int] = None
    status: str
    is_verified: bool = False
    has_poc: bool = False
    ai_confidence: Optional[float] = None
    verdict: Optional[str] = None  # confirmed, likely, uncertain, false_positive
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============ 搜索统计 ============


class SearchStats(BaseModel):
    """搜索统计信息"""
    findings_total: int = 0
    tasks_total: int = 0
    projects_total: int = 0

    model_config = ConfigDict(from_attributes=True)


# ============ 统一搜索响应 ============


class SearchResponse(BaseModel):
    """统一搜索响应"""
    findings: List[SearchAgentFindingItem] = Field(default_factory=list)
    tasks: List[SearchAgentTaskItem] = Field(default_factory=list)
    projects: List[SearchProjectItem] = Field(default_factory=list)
    total: SearchStats = Field(default_factory=SearchStats)
    keyword: str
    limit: int
    offset: int

    model_config = ConfigDict(from_attributes=True)
