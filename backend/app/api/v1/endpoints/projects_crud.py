from fastapi import Query

from app.api.v1.endpoints.projects_shared import *
from app.services.project_metrics import project_metrics_refresher

router = APIRouter()


@router.post("/", response_model=ProjectResponse)
async def create_project(
    *,
    db: AsyncSession = Depends(get_db),
    project_in: ProjectCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Create new project.
    """
    source_type = project_in.source_type or "zip"
    if source_type != "zip" or project_in.repository_url:
        raise HTTPException(status_code=400, detail="仅支持 ZIP 项目创建")

    project = _build_zip_project(
        name=project_in.name,
        description=project_in.description,
        default_branch=project_in.default_branch,
        programming_languages=project_in.programming_languages,
        owner_id=current_user.id,
    )
    db.add(project)
    await db.commit()
    project_metrics_refresher.enqueue(project.id)
    return await load_project_for_response(
        db,
        project.id,
        include_metrics=False,
    )

@router.get("/", response_model=List[ProjectResponse])
async def read_projects(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    include_metrics: bool = Query(False, description="是否加载项目管理指标"),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve projects.
    """
    query = (
        select(Project)
        .options(*build_project_response_load_options(include_metrics=include_metrics))
        .where(Project.source_type == "zip")
    )
    query = query.order_by(Project.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    projects = _filter_public_projects(result.scalars().all())
    if include_metrics:
        await _hydrate_projects_management_metrics(db, projects)
    return projects

@router.get("/{id}", response_model=ProjectResponse)
async def read_project(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get project by ID.
    """
    project = await load_project_for_response(
        db,
        id,
        include_metrics=True,
    )
    _raise_if_project_hidden(project)

    # 检查权限：只有项目所有者可以查看

    return project


@router.get("/info/{id}", response_model=ProjectInfoResponse)
async def get_project_info(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取项目信息（语言统计）。
    """
    # 1. 获取项目基本信息
    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalars().first()
    _raise_if_project_hidden(project)

    # 2. 检查权限

    return await ensure_project_info_language_stats(
        db,
        id,
        raise_on_error=True,
        cloc_loader=get_cloc_stats,
    )


@router.put("/{id}", response_model=ProjectResponse)
async def update_project(
    id: str,
    *,
    db: AsyncSession = Depends(get_db),
    project_in: ProjectUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Update project.
    """
    import json

    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalars().first()
    _raise_if_project_hidden(project)

    # 检查权限：只有项目所有者可以更新

    update_data = project_in.model_dump(exclude_unset=True)
    if update_data.get("source_type") not in (None, "zip"):
        raise HTTPException(status_code=400, detail="仅支持 ZIP 项目")
    if update_data.get("repository_url"):
        raise HTTPException(status_code=400, detail="仅支持 ZIP 项目")
    if "source_type" in update_data:
        update_data["source_type"] = "zip"
    if "repository_url" in update_data:
        update_data["repository_url"] = None
    if "repository_type" in update_data:
        update_data["repository_type"] = "other"
    if "programming_languages" in update_data and update_data["programming_languages"] is not None:
        update_data["programming_languages"] = json.dumps(update_data["programming_languages"])

    for field, value in update_data.items():
        setattr(project, field, value)

    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    project_metrics_refresher.enqueue(project.id)
    return await load_project_for_response(
        db,
        project.id,
        include_metrics=False,
    )


@router.post(
    "/{id}/metrics/recalculate",
    response_model=ProjectManagementMetricsResponse,
)
async def recalc_project_metrics(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    手动刷新项目管理指标。
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)
    metrics = await project_metrics_refresher.recalc_now(id)
    return metrics
