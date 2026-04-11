from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GitleaksRuleBase(BaseModel):
    """Shared fields for gitleaks rule DTOs."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    rule_id: str = Field(..., min_length=1, max_length=255)
    secret_group: int = Field(0, ge=0)
    regex: str = Field(..., min_length=1)
    keywords: List[str] = Field(default_factory=list)
    path: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    entropy: Optional[float] = Field(None, ge=0)
    is_active: bool = True
    source: str = Field(default="custom", min_length=1, max_length=64)

    @field_validator("name", "rule_id", "regex", "source")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("字段不能为空")
        return cleaned

    @field_validator("keywords", "tags")
    @classmethod
    def _clean_string_list(cls, value: List[str]) -> List[str]:
        cleaned: List[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned


class GitleaksRuleCreateRequest(GitleaksRuleBase):
    """Payload used to create a Gitleaks rule."""

    pass


class GitleaksRuleUpdateRequest(BaseModel):
    """Fields supported when updating a Gitleaks rule."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    rule_id: Optional[str] = Field(None, min_length=1, max_length=255)
    secret_group: Optional[int] = Field(None, ge=0)
    regex: Optional[str] = Field(None, min_length=1)
    keywords: Optional[List[str]] = None
    path: Optional[str] = None
    tags: Optional[List[str]] = None
    entropy: Optional[float] = Field(None, ge=0)
    is_active: Optional[bool] = None
    source: Optional[str] = Field(None, min_length=1, max_length=64)


class GitleaksRuleBatchUpdateRequest(BaseModel):
    """Payload used for toggling batches of Gitleaks rules."""

    rule_ids: Optional[List[str]] = None
    source: Optional[str] = None
    keyword: Optional[str] = None
    current_is_active: Optional[bool] = None
    is_active: bool


class GitleaksRuleResponse(GitleaksRuleBase):
    """Response serialization for Gitleaks rules."""

    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OpengrepRuleCreateRequest(BaseModel):
    """Payload used when generating Opengrep rules from patches."""

    repo_owner: str
    repo_name: str
    commit_hash: str
    commit_content: str


class OpengrepRuleValidation(BaseModel):
    """Wraps the validation result for LLM-generated rules."""

    is_valid: bool = Field(..., description="规则是否通过验证")
    message: Optional[str] = Field(None, description="验证失败原因或提示信息")


class OpengrepRuleAttempt(BaseModel):
    """Represents one generation attempt made by the rule generator."""

    attempt: int = Field(..., description="尝试序号")
    rule: Optional[Dict[str, Any]] = Field(None, description="本次尝试生成的规则")
    validation: OpengrepRuleValidation


class OpengrepRulePatchResponse(BaseModel):
    """Response returned from the patch-to-rule API."""

    rule: Optional[Dict[str, Any]]
    validation: OpengrepRuleValidation
    attempts: List[OpengrepRuleAttempt]
    meta: Optional[Dict[str, Any]] = None


class OpengrepRuleTextCreateRequest(BaseModel):
    """Payload used when creating a user-supplied rule YAML."""

    rule_yaml: str


class OpengrepRuleTextResponse(BaseModel):
    """Response for a custom rule validation."""

    rule: Optional[Dict[str, Any]] = None
    validation: OpengrepRuleValidation
    test_yaml: Optional[str] = None
    rule_id: Optional[str] = None


class OpengrepRuleUpdateRequest(BaseModel):
    """Fields accepted when editing an existing Opengrep rule."""

    name: Optional[str] = Field(None, description="规则名称")
    pattern_yaml: Optional[str] = Field(None, description="规则YAML文本")
    language: Optional[str] = Field(None, description="编程语言")
    severity: Optional[str] = Field(None, description="严重程度: ERROR, WARNING, INFO")
    is_active: Optional[bool] = Field(None, description="是否启用")


class OpengrepRuleResponse(BaseModel):
    """Basic Opengrep rule payload used in the API."""

    id: str
    name: str
    pattern_yaml: str
    language: str
    severity: str
    source: str
    is_active: bool
    created_at: datetime
