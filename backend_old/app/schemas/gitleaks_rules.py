from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class GitleaksRuleBase(BaseModel):
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
            item_text = str(item).strip()
            if item_text:
                cleaned.append(item_text)
        return cleaned


class GitleaksRuleCreateRequest(GitleaksRuleBase):
    pass


class GitleaksRuleUpdateRequest(BaseModel):
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
    rule_ids: Optional[List[str]] = None
    source: Optional[str] = None
    keyword: Optional[str] = None
    current_is_active: Optional[bool] = None
    is_active: bool


class GitleaksRuleResponse(GitleaksRuleBase):
    id: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
