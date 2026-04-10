from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.db.session import get_db
from app.models.prompt_skill import PromptSkill
from app.models.user_config import UserConfig
from app.models.user import User
from app.services.agent.skills.prompt_skills import (
    DEFAULT_PROMPT_SKILL_TEMPLATES,
    PROMPT_SKILL_AGENT_KEYS,
    PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY,
    PROMPT_SKILL_SCOPE_AGENT_SPECIFIC,
    PROMPT_SKILL_SCOPE_GLOBAL,
    build_prompt_skill_builtin_state,
    resolve_prompt_skill_scope_agent_key,
)
from app.services.agent.skills.resource_catalog import (
    RESOURCE_MODE_EXTERNAL_TOOLS,
    RESOURCE_MODE_SCAN_CORE_ONLY,
    RESOURCE_TOOL_TYPE_PROMPT_BUILTIN,
    RESOURCE_TOOL_TYPE_PROMPT_CUSTOM,
    RESOURCE_TOOL_TYPE_SKILL,
    build_prompt_builtin_catalog_item,
    build_prompt_custom_catalog_item,
    build_scan_core_catalog_item,
    build_status_label,
    filter_catalog_items,
    paginate_catalog_items,
)
from app.services.agent.skills.scan_core import (
    get_scan_core_skill_detail,
    search_scan_core_skills,
)


router = APIRouter()


class SkillCatalogItem(BaseModel):
    skill_id: str
    tool_type: Optional[Literal["skill", "prompt-builtin", "prompt-custom"]] = None
    tool_id: Optional[str] = None
    name: str
    namespace: str
    summary: str
    category: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    entrypoint: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    has_scripts: bool = False
    has_bin: bool = False
    has_assets: bool = False
    status_label: Optional[str] = None
    is_enabled: Optional[bool] = None
    is_available: Optional[bool] = None
    resource_kind_label: Optional[str] = None
    detail_supported: bool = True
    agent_key: Optional[str] = None
    scope: Optional[Literal["global", "agent_specific"]] = None


class SkillCatalogResponse(BaseModel):
    enabled: bool = True
    total: int = 0
    limit: int = 20
    offset: int = 0
    supported_agent_keys: List[str] = Field(default_factory=list)
    items: List[SkillCatalogItem] = Field(default_factory=list)
    error: Optional[str] = None


class SkillDetailResponse(BaseModel):
    enabled: bool = True
    skill_id: str
    name: str
    namespace: str
    summary: str
    category: str = ""
    goal: str = ""
    task_list: List[str] = Field(default_factory=list)
    input_checklist: List[str] = Field(default_factory=list)
    example_input: str = ""
    pitfalls: List[str] = Field(default_factory=list)
    sample_prompts: List[str] = Field(default_factory=list)
    entrypoint: str
    mirror_dir: str = ""
    source_root: str = ""
    source_dir: str = ""
    source_skill_md: str = ""
    aliases: List[str] = Field(default_factory=list)
    has_scripts: bool = False
    has_bin: bool = False
    has_assets: bool = False
    files_count: int = 0
    workflow_content: Optional[str] = None
    workflow_truncated: Optional[bool] = None
    workflow_error: Optional[str] = None
    test_supported: bool = False
    test_mode: Literal["single_skill_strict", "structured_tool", "disabled"] = "disabled"
    test_reason: Optional[str] = None
    default_test_project_name: Literal["libplist"] = "libplist"
    tool_test_preset: Optional["ToolTestPreset"] = None


class SkillTestRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000, description="自然语言测试输入")
    max_iterations: int = Field(default=4, ge=1, le=20)


class ToolTestPreset(BaseModel):
    project_name: Literal["libplist"] = "libplist"
    file_path: str = Field(..., min_length=1, description="目标文件路径")
    function_name: str = Field(..., min_length=1, description="目标函数名")
    line_start: Optional[int] = Field(default=None, ge=1, description="目标起始行")
    line_end: Optional[int] = Field(default=None, ge=1, description="目标结束行")
    tool_input: Dict[str, Any] = Field(default_factory=dict, description="工具输入预置")


class StructuredToolTestRequest(BaseModel):
    file_path: str = Field(..., min_length=1, description="目标文件路径")
    function_name: str = Field(..., min_length=1, description="目标函数名")
    line_start: Optional[int] = Field(default=None, ge=1, description="目标起始行")
    line_end: Optional[int] = Field(default=None, ge=1, description="目标结束行")
    tool_input: Dict[str, Any] = Field(default_factory=dict, description="工具执行参数")


class PromptSkillItemResponse(BaseModel):
    id: str
    name: str
    content: str
    scope: Literal["global", "agent_specific"] = "global"
    agent_key: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PromptSkillBuiltinItemResponse(BaseModel):
    agent_key: str
    content: str
    is_active: bool = True


class PromptSkillListResponse(BaseModel):
    enabled: bool = True
    total: int = 0
    limit: int = 200
    offset: int = 0
    supported_agent_keys: List[str] = Field(default_factory=lambda: list(PROMPT_SKILL_AGENT_KEYS))
    builtin_items: List[PromptSkillBuiltinItemResponse] = Field(default_factory=list)
    items: List[PromptSkillItemResponse] = Field(default_factory=list)


class PromptSkillCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="技能名称")
    content: str = Field(..., min_length=1, max_length=4000, description="技能内容")
    scope: Literal["global", "agent_specific"] = Field(default="global", description="作用域")
    agent_key: Optional[str] = Field(default=None, description="智能体 key")
    is_active: bool = Field(default=True, description="是否启用")


class PromptSkillUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120, description="技能名称")
    content: Optional[str] = Field(default=None, min_length=1, max_length=4000, description="技能内容")
    scope: Optional[Literal["global", "agent_specific"]] = Field(default=None, description="作用域")
    agent_key: Optional[str] = Field(default=None, description="智能体 key")
    is_active: Optional[bool] = Field(default=None, description="是否启用")


class PromptSkillBuiltinUpdateRequest(BaseModel):
    is_active: bool = Field(default=True, description="是否启用内置 Prompt Skill")


class SkillResourceDetailResponse(BaseModel):
    tool_type: Literal["skill", "prompt-builtin", "prompt-custom"]
    tool_id: str
    name: str
    summary: str
    status_label: str
    is_enabled: bool
    is_available: bool
    resource_kind_label: str
    detail_supported: bool = True
    namespace: str
    entrypoint: Optional[str] = None
    agent_key: Optional[str] = None
    scope: Optional[Literal["global", "agent_specific"]] = None
    content: Optional[str] = None
    is_builtin: Optional[bool] = None
    can_toggle: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    scan_core_detail: Optional[SkillDetailResponse] = None


SkillDetailResponse.model_rebuild()


def _normalize_scope_agent_or_400(scope: Any, agent_key: Any) -> tuple[str, str | None]:
    try:
        return resolve_prompt_skill_scope_agent_key(scope, agent_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _normalize_non_empty_text_or_400(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail=f"{field} 不能为空")
    return normalized


def _to_prompt_skill_item(item: PromptSkill) -> PromptSkillItemResponse:
    return PromptSkillItemResponse(
        id=str(item.id),
        name=str(item.name or ""),
        content=str(item.content or ""),
        scope=str(item.scope or PROMPT_SKILL_SCOPE_GLOBAL),
        agent_key=str(item.agent_key or "").strip() or None,
        is_active=bool(item.is_active),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _to_prompt_skill_builtin_item(agent_key: str, is_active: bool) -> PromptSkillBuiltinItemResponse:
    return PromptSkillBuiltinItemResponse(
        agent_key=agent_key,
        content=str(DEFAULT_PROMPT_SKILL_TEMPLATES.get(agent_key) or "").strip(),
        is_active=bool(is_active),
    )


def _status_label(is_enabled: bool) -> str:
    return build_status_label(is_enabled=bool(is_enabled))


def _build_scan_core_catalog_item(item: Dict[str, Any]) -> SkillCatalogItem:
    return SkillCatalogItem(**build_scan_core_catalog_item(item))


def _build_builtin_prompt_catalog_item(*, agent_key: str, is_active: bool) -> SkillCatalogItem:
    return SkillCatalogItem(
        **build_prompt_builtin_catalog_item(
            agent_key=agent_key,
            content=str(DEFAULT_PROMPT_SKILL_TEMPLATES.get(agent_key) or "").strip(),
            is_active=is_active,
        )
    )


def _build_custom_prompt_catalog_item(item: PromptSkillItemResponse) -> SkillCatalogItem:
    prompt_row = PromptSkill(
        id=item.id,
        name=item.name,
        content=item.content,
        scope=item.scope,
        agent_key=item.agent_key,
        is_active=item.is_active,
    )
    return SkillCatalogItem(**build_prompt_custom_catalog_item(prompt_row))


async def _list_custom_prompt_skill_items(
    *,
    db: AsyncSession,
    current_user: User,
) -> list[PromptSkillItemResponse]:
    result = await db.execute(
        select(PromptSkill)
        .where(PromptSkill.user_id == str(current_user.id))
        .order_by(PromptSkill.created_at.desc())
    )
    items = result.scalars().all()
    return [_to_prompt_skill_item(item) for item in items]


async def _build_external_tool_catalog_payload(
    *,
    db: AsyncSession,
    current_user: User,
    query: str,
    namespace: Optional[str],
    limit: int,
    offset: int,
) -> SkillCatalogResponse:
    builtin_state = await _load_user_builtin_prompt_skill_state(
        db=db,
        user_id=str(current_user.id),
    )
    custom_items = await _list_custom_prompt_skill_items(db=db, current_user=current_user)
    scan_core_payload = search_scan_core_skills(query="", namespace=None, limit=500, offset=0)

    all_items: list[SkillCatalogItem] = [
        *[_build_scan_core_catalog_item(item) for item in scan_core_payload["items"]],
        *[
            _build_builtin_prompt_catalog_item(
                agent_key=agent_key,
                is_active=builtin_state.get(agent_key, True),
            )
            for agent_key in PROMPT_SKILL_AGENT_KEYS
        ],
        *[_build_custom_prompt_catalog_item(item) for item in custom_items],
    ]

    filtered_items = filter_catalog_items(
        [item.model_dump() for item in all_items],
        query=query,
        namespace=namespace,
    )
    payload = paginate_catalog_items(filtered_items, limit=limit, offset=offset)
    payload["supported_agent_keys"] = list(PROMPT_SKILL_AGENT_KEYS)
    return SkillCatalogResponse(**payload)


async def _load_prompt_skill_or_404(
    *,
    db: AsyncSession,
    current_user: User,
    prompt_skill_id: str,
) -> PromptSkill:
    result = await db.execute(
        select(PromptSkill).where(
            PromptSkill.id == prompt_skill_id,
            PromptSkill.user_id == str(current_user.id),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Prompt Skill 不存在")
    return item


async def _build_skill_resource_detail(
    *,
    tool_type: str,
    tool_id: str,
    db: AsyncSession,
    current_user: User,
) -> SkillResourceDetailResponse:
    normalized_tool_type = str(tool_type or "").strip()
    normalized_tool_id = str(tool_id or "").strip()

    if normalized_tool_type == RESOURCE_TOOL_TYPE_SKILL:
        detail = get_scan_core_skill_detail(skill_id=normalized_tool_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Skill '{normalized_tool_id}' not found")
        skill_detail = SkillDetailResponse(enabled=True, **detail)
        return SkillResourceDetailResponse(
            tool_type=RESOURCE_TOOL_TYPE_SKILL,
            tool_id=normalized_tool_id,
            name=skill_detail.name,
            summary=skill_detail.summary,
            status_label=build_status_label(is_enabled=True),
            is_enabled=True,
            is_available=True,
            resource_kind_label="Scan Core",
            detail_supported=True,
            namespace=skill_detail.namespace,
            entrypoint=skill_detail.entrypoint,
            is_builtin=False,
            can_toggle=False,
            can_edit=False,
            can_delete=False,
            scan_core_detail=skill_detail,
        )

    if normalized_tool_type == RESOURCE_TOOL_TYPE_PROMPT_BUILTIN:
        if normalized_tool_id not in PROMPT_SKILL_AGENT_KEYS:
            raise HTTPException(status_code=404, detail="Builtin Prompt Skill 不存在")
        builtin_state = await _load_user_builtin_prompt_skill_state(
            db=db,
            user_id=str(current_user.id),
        )
        is_active = builtin_state.get(normalized_tool_id, True)
        content = str(DEFAULT_PROMPT_SKILL_TEMPLATES.get(normalized_tool_id) or "").strip()
        return SkillResourceDetailResponse(
            tool_type=RESOURCE_TOOL_TYPE_PROMPT_BUILTIN,
            tool_id=normalized_tool_id,
            name=normalized_tool_id,
            summary=content,
            status_label=_status_label(is_active),
            is_enabled=bool(is_active),
            is_available=True,
            resource_kind_label="Builtin Prompt Skill",
            detail_supported=True,
            namespace="prompt-skill",
            agent_key=normalized_tool_id,
            scope=None,
            content=content,
            is_builtin=True,
            can_toggle=True,
            can_edit=False,
            can_delete=False,
        )

    if normalized_tool_type == RESOURCE_TOOL_TYPE_PROMPT_CUSTOM:
        item = await _load_prompt_skill_or_404(
            db=db,
            current_user=current_user,
            prompt_skill_id=normalized_tool_id,
        )
        prompt_item = _to_prompt_skill_item(item)
        return SkillResourceDetailResponse(
            tool_type=RESOURCE_TOOL_TYPE_PROMPT_CUSTOM,
            tool_id=prompt_item.id,
            name=prompt_item.name,
            summary=prompt_item.content,
            status_label=_status_label(prompt_item.is_active),
            is_enabled=bool(prompt_item.is_active),
            is_available=True,
            resource_kind_label="Custom Prompt Skill",
            detail_supported=True,
            namespace="prompt-skill",
            agent_key=prompt_item.agent_key,
            scope=prompt_item.scope,
            content=prompt_item.content,
            is_builtin=False,
            can_toggle=True,
            can_edit=True,
            can_delete=True,
        )

    raise HTTPException(status_code=404, detail="资源类型不存在")


def _parse_other_config_payload(raw_value: Any) -> Dict[str, Any]:
    if isinstance(raw_value, dict):
        return dict(raw_value)
    raw_text = str(raw_value or "").strip()
    if not raw_text:
        return {}
    try:
        payload = json.loads(raw_text)
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


async def _load_user_builtin_prompt_skill_state(
    *,
    db: AsyncSession,
    user_id: str,
) -> dict[str, bool]:
    result = await db.execute(select(UserConfig).where(UserConfig.user_id == user_id))
    record = result.scalar_one_or_none()
    other_config = _parse_other_config_payload(getattr(record, "other_config", None))
    return build_prompt_skill_builtin_state(other_config.get(PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY))


async def _save_user_builtin_prompt_skill_state(
    *,
    db: AsyncSession,
    user_id: str,
    builtin_state: Any,
) -> dict[str, bool]:
    normalized_state = build_prompt_skill_builtin_state(builtin_state)
    result = await db.execute(select(UserConfig).where(UserConfig.user_id == user_id))
    record = result.scalar_one_or_none()

    if record is None:
        payload: Dict[str, Any] = {PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY: normalized_state}
        record = UserConfig(
            user_id=user_id,
            llm_config="{}",
            other_config=json.dumps(payload, ensure_ascii=False),
        )
        db.add(record)
    else:
        payload = _parse_other_config_payload(record.other_config)
        payload[PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY] = normalized_state
        record.other_config = json.dumps(payload, ensure_ascii=False)

    await db.commit()
    return normalized_state


@router.get("/catalog", response_model=SkillCatalogResponse)
async def get_skill_catalog(
    q: str = Query(default="", description="Keyword query for skill search."),
    namespace: Optional[str] = Query(default=None, description="Filter by namespace."),
    resource_mode: Literal["scan_core_only", "external_tools"] = Query(default=RESOURCE_MODE_SCAN_CORE_ONLY),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> SkillCatalogResponse:
    if resource_mode == RESOURCE_MODE_EXTERNAL_TOOLS:
        return await _build_external_tool_catalog_payload(
            db=db,
            current_user=current_user,
            query=q,
            namespace=namespace,
            limit=limit,
            offset=offset,
        )
    payload = search_scan_core_skills(query=q, namespace=namespace, limit=limit, offset=offset)
    return SkillCatalogResponse(**payload)


@router.get("/prompt-skills", response_model=PromptSkillListResponse)
async def list_prompt_skills(
    scope: Optional[Literal["global", "agent_specific"]] = Query(default=None, description="作用域过滤"),
    agent_key: Optional[str] = Query(default=None, description="智能体 key 过滤"),
    is_active: Optional[bool] = Query(default=None, description="启用状态过滤"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> PromptSkillListResponse:
    normalized_scope: Optional[str] = None
    normalized_agent_key: Optional[str] = None

    if scope is not None:
        normalized_scope, normalized_agent_key = _normalize_scope_agent_or_400(scope, agent_key)
    elif agent_key:
        normalized_scope, normalized_agent_key = _normalize_scope_agent_or_400(
            PROMPT_SKILL_SCOPE_AGENT_SPECIFIC,
            agent_key,
        )

    builtin_state = await _load_user_builtin_prompt_skill_state(
        db=db,
        user_id=str(current_user.id),
    )

    query = select(PromptSkill).where(PromptSkill.user_id == str(current_user.id))
    if normalized_scope is not None:
        query = query.where(PromptSkill.scope == normalized_scope)
    if normalized_scope == PROMPT_SKILL_SCOPE_AGENT_SPECIFIC and normalized_agent_key:
        query = query.where(PromptSkill.agent_key == normalized_agent_key)
    if is_active is not None:
        query = query.where(PromptSkill.is_active.is_(bool(is_active)))

    query = query.order_by(PromptSkill.created_at.desc())
    count_query = select(sql_func.count()).select_from(query.subquery())
    total = int((await db.execute(count_query)).scalar() or 0)

    result = await db.execute(query.offset(offset).limit(limit))
    items = result.scalars().all()

    return PromptSkillListResponse(
        enabled=True,
        total=total,
        limit=limit,
        offset=offset,
        builtin_items=[
           _to_prompt_skill_builtin_item(key, builtin_state.get(key, True))
            for key in PROMPT_SKILL_AGENT_KEYS
        ],
        items=[_to_prompt_skill_item(item) for item in items],
    )


@router.put("/prompt-skills/builtin/{agent_key}", response_model=PromptSkillBuiltinItemResponse)
async def update_builtin_prompt_skill(
    agent_key: str,
    request: PromptSkillBuiltinUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> PromptSkillBuiltinItemResponse:
    normalized_agent_key = str(agent_key or "").strip()
    if normalized_agent_key not in PROMPT_SKILL_AGENT_KEYS:
        raise HTTPException(status_code=400, detail=f"agent_key must be one of {PROMPT_SKILL_AGENT_KEYS}")

    current_state = await _load_user_builtin_prompt_skill_state(
        db=db,
        user_id=str(current_user.id),
    )
    current_state[normalized_agent_key] = bool(request.is_active)
    saved_state = await _save_user_builtin_prompt_skill_state(
        db=db,
        user_id=str(current_user.id),
        builtin_state=current_state,
    )
    return _to_prompt_skill_builtin_item(
        normalized_agent_key,
        saved_state.get(normalized_agent_key, True),
    )


@router.post("/prompt-skills", response_model=PromptSkillItemResponse)
async def create_prompt_skill(
    request: PromptSkillCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> PromptSkillItemResponse:
    scope, agent_key = _normalize_scope_agent_or_400(request.scope, request.agent_key)
    item = PromptSkill(
        user_id=str(current_user.id),
        name=_normalize_non_empty_text_or_400(request.name, field="name"),
        content=_normalize_non_empty_text_or_400(request.content, field="content"),
        scope=scope,
        agent_key=agent_key,
        is_active=bool(request.is_active),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _to_prompt_skill_item(item)


@router.put("/prompt-skills/{prompt_skill_id}", response_model=PromptSkillItemResponse)
async def update_prompt_skill(
    prompt_skill_id: str,
    request: PromptSkillUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> PromptSkillItemResponse:
    result = await db.execute(
        select(PromptSkill).where(
            PromptSkill.id == prompt_skill_id,
            PromptSkill.user_id == str(current_user.id),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Prompt Skill 不存在")

    if request.name is not None:
        item.name = _normalize_non_empty_text_or_400(request.name, field="name")
    if request.content is not None:
        item.content = _normalize_non_empty_text_or_400(request.content, field="content")
    if request.is_active is not None:
        item.is_active = bool(request.is_active)

    if request.scope is not None or request.agent_key is not None:
        scope_input = request.scope if request.scope is not None else item.scope
        if request.agent_key is not None:
            agent_key_input = request.agent_key
        elif request.scope is not None:
            agent_key_input = item.agent_key
        else:
            agent_key_input = item.agent_key
        scope, agent_key = _normalize_scope_agent_or_400(scope_input, agent_key_input)
        item.scope = scope
        item.agent_key = agent_key

    await db.commit()
    await db.refresh(item)
    return _to_prompt_skill_item(item)


@router.delete("/prompt-skills/{prompt_skill_id}")
async def delete_prompt_skill(
    prompt_skill_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Dict[str, Any]:
    result = await db.execute(
        select(PromptSkill).where(
            PromptSkill.id == prompt_skill_id,
            PromptSkill.user_id == str(current_user.id),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Prompt Skill 不存在")

    await db.delete(item)
    await db.commit()
    return {"message": "Prompt Skill 已删除", "id": prompt_skill_id}


@router.get("/{skill_id}", response_model=SkillDetailResponse)
async def get_skill_detail(
    skill_id: str,
    include_workflow: bool = Query(default=False, description="Include SKILL.md workflow content."),
    current_user: User = Depends(deps.get_current_user),
) -> SkillDetailResponse:
    _ = current_user
    _ = include_workflow
    detail = get_scan_core_skill_detail(skill_id=skill_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    payload = dict(detail)
    payload["enabled"] = True
    return SkillDetailResponse(**payload)


@router.get("/resources/{tool_type}/{tool_id}", response_model=SkillResourceDetailResponse)
async def get_skill_resource_detail(
    tool_type: Literal["skill", "prompt-builtin", "prompt-custom"],
    tool_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> SkillResourceDetailResponse:
    return await _build_skill_resource_detail(
        tool_type=tool_type,
        tool_id=tool_id,
        db=db,
        current_user=current_user,
    )


@router.post("/{skill_id}/test")
async def run_skill_test(
    skill_id: str,
    request: SkillTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.api.v1.endpoints.agent_test import (
        QueueEventEmitter,
        _get_user_config,
        _init_llm_service,
        _run_agent_streaming,
    )
    from app.api.v1.endpoints.config import _resolve_verify_project
    from app.api.v1.endpoints.static_tasks_shared import _release_request_db_session
    from app.services.agent.skill_test_runner import SkillTestRunner

    detail = get_scan_core_skill_detail(skill_id=skill_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    if not bool(detail.get("test_supported")):
        raise HTTPException(status_code=400, detail=str(detail.get("test_reason") or "当前 skill 暂不支持测试"))

    user_config = await _get_user_config(db, str(current_user.id))
    llm_service = await _init_llm_service(user_config)
    project, zip_path, fallback_used = await _resolve_verify_project(
        db=db,
        current_user=current_user,
    )
    queue: asyncio.Queue = asyncio.Queue()
    emitter = QueueEventEmitter(queue)
    runner = SkillTestRunner(
        skill_id=skill_id,
        prompt=request.prompt,
        max_iterations=request.max_iterations,
        llm_service=llm_service,
        project_name=str(getattr(project, "name", "") or "").strip(),
        zip_path=zip_path,
        fallback_used=fallback_used,
        event_emitter=emitter,
    )
    await _release_request_db_session(db)

    return StreamingResponse(
        _run_agent_streaming(runner.run(), queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{skill_id}/tool-test")
async def run_structured_tool_test(
    skill_id: str,
    request: StructuredToolTestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.api.v1.endpoints.agent_test import (
        QueueEventEmitter,
        _get_user_config,
        _init_llm_service,
        _run_agent_streaming,
    )
    from app.api.v1.endpoints.config import _resolve_verify_project
    from app.api.v1.endpoints.static_tasks_shared import _release_request_db_session
    from app.services.agent.skill_test_runner import StructuredToolTestRunner

    detail = get_scan_core_skill_detail(skill_id=skill_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")
    if str(detail.get("test_mode") or "") != "structured_tool":
        raise HTTPException(status_code=400, detail="当前 skill 未开放结构化工具测试入口")

    user_config = await _get_user_config(db, str(current_user.id))
    llm_service = await _init_llm_service(user_config)
    project, zip_path, fallback_used = await _resolve_verify_project(
        db=db,
        current_user=current_user,
    )
    queue: asyncio.Queue = asyncio.Queue()
    emitter = QueueEventEmitter(queue)
    runner = StructuredToolTestRunner(
        skill_id=skill_id,
        request_payload=request.model_dump(),
        llm_service=llm_service,
        project_name=str(getattr(project, "name", "") or "").strip(),
        zip_path=zip_path,
        fallback_used=fallback_used,
        event_emitter=emitter,
    )
    await _release_request_db_session(db)

    return StreamingResponse(
        _run_agent_streaming(runner.run(), queue),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
