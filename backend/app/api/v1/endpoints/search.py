"""
全局搜索 API 端点
支持跨 Project、AgentTask、AgentFinding 的统一搜索
"""

from typing import Any, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchStats,
    SearchProjectItem,
    SearchAgentTaskItem,
    SearchAgentFindingItem,
)
from app.services.search_service import SearchService

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
async def search_global(
    keyword: str = Query(..., min_length=1, max_length=500, description="搜索关键词"),
    limit: int = Query(50, ge=1, le=200, description="返回结果数量(每个类型)"),
    offset: int = Query(0, ge=0, description="分页偏移"),
    sort_by: str = Query("created_at", description="排序字段: created_at"),
    sort_order: str = Query("desc", description="排序顺序: asc, desc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> SearchResponse:
    """
    全局搜索接口
    
    同时搜索项目、审计任务、漏洞发现
    
    搜索字段：
    - Project: name, description, repository_url
    - AgentTask: name, description, task_type, status
    - AgentFinding: title, description, vulnerability_type, file_path, code_snippet
    
    返回格式：
    {
        "findings": [...],
        "tasks": [...],
        "projects": [...],
        "total": {
            "findings_total": 0,
            "tasks_total": 0,
            "projects_total": 0
        },
        "keyword": "...",
        "limit": 50,
        "offset": 0
    }
    """
    # 验证排序参数
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    
    # 执行全局搜索
    search_result = await SearchService.search_all(
        db=db,
        keyword=keyword,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    
    # 构建响应
    findings_items = [
        SearchAgentFindingItem.model_validate(f)
        for f in search_result["findings"]
    ]
    tasks_items = [
        SearchAgentTaskItem.model_validate(t)
        for t in search_result["tasks"]
    ]
    projects_items = [
        SearchProjectItem.model_validate(p)
        for p in search_result["projects"]
    ]
    
    stats = SearchStats(
        findings_total=search_result["total"]["findings_total"],
        tasks_total=search_result["total"]["tasks_total"],
        projects_total=search_result["total"]["projects_total"],
    )
    
    return SearchResponse(
        findings=findings_items,
        tasks=tasks_items,
        projects=projects_items,
        total=stats,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )


@router.get("/findings/search", response_model=dict)
async def search_findings(
    keyword: str = Query(..., min_length=1, max_length=500, description="搜索关键词"),
    limit: int = Query(50, ge=1, le=200, description="返回结果数量"),
    offset: int = Query(0, ge=0, description="分页偏移"),
    sort_by: str = Query("created_at", description="排序字段: created_at, severity"),
    sort_order: str = Query("desc", description="排序顺序: asc, desc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    搜索漏洞发现
    
    搜索字段: title, description, vulnerability_type, file_path, code_snippet
    """
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    
    findings, total = await SearchService.search_findings(
        db=db,
        keyword=keyword,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    
    return {
        "data": [SearchAgentFindingItem.model_validate(f) for f in findings],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/tasks/search", response_model=dict)
async def search_tasks(
    keyword: str = Query(..., min_length=1, max_length=500, description="搜索关键词"),
    limit: int = Query(50, ge=1, le=200, description="返回结果数量"),
    offset: int = Query(0, ge=0, description="分页偏移"),
    sort_by: str = Query("created_at", description="排序字段: created_at"),
    sort_order: str = Query("desc", description="排序顺序: asc, desc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    搜索审计任务
    
    搜索字段: name, description, task_type, status
    """
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    
    tasks, total = await SearchService.search_tasks(
        db=db,
        keyword=keyword,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    
    return {
        "data": [SearchAgentTaskItem.model_validate(t) for t in tasks],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/projects/search", response_model=dict)
async def search_projects(
    keyword: str = Query(..., min_length=1, max_length=500, description="搜索关键词"),
    limit: int = Query(50, ge=1, le=200, description="返回结果数量"),
    offset: int = Query(0, ge=0, description="分页偏移"),
    sort_by: str = Query("created_at", description="排序字段: created_at, updated_at"),
    sort_order: str = Query("desc", description="排序顺序: asc, desc"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    搜索项目
    
    搜索字段: name, description, repository_url
    """
    if sort_order not in ("asc", "desc"):
        sort_order = "desc"
    
    projects, total = await SearchService.search_projects(
        db=db,
        keyword=keyword,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    
    return {
        "data": [SearchProjectItem.model_validate(p) for p in projects],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
