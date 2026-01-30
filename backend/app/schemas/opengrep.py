"""
Opengrep API 数据模型 - Pydantic Schemas
用于API请求和响应序列化
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class OpengrepRuleCreateRequest(BaseModel):
    repo_owner: str
    repo_name: str
    commit_hash: str
    commit_content: str


class OpengrepRuleValidation(BaseModel):
    is_valid: bool = Field(..., description="规则是否通过验证")
    message: Optional[str] = Field(None, description="验证失败原因或提示信息")


class OpengrepRuleAttempt(BaseModel):
    attempt: int = Field(..., description="尝试序号")
    rule: Optional[Dict[str, Any]] = Field(None, description="本次尝试生成的规则")
    validation: OpengrepRuleValidation


class OpengrepRulePatchRequest(BaseModel):
    repo_owner: str
    repo_name: str
    commit_hash: str
    commit_content: str


class OpengrepRulePatchResponse(BaseModel):
    rule: Optional[Dict[str, Any]]
    validation: OpengrepRuleValidation
    attempts: List[OpengrepRuleAttempt]
    meta: Optional[Dict[str, Any]] = None


class OpengrepRuleResponse(BaseModel):
    id: str
    name: str
    pattern_yaml: str
    language: str
    severity: str
    source: str
    is_active: bool
    created_at: datetime
