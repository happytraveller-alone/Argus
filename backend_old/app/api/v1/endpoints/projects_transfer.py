from app.api.v1.endpoints.projects_shared import *

router = APIRouter()


@router.post("/export")
async def export_project_bundle(
    request: ProjectExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> FileResponse:
    bundle = await export_projects_bundle(
        db=db,
        current_user=current_user,
        project_ids=request.project_ids,
        include_archives=request.include_archives,
    )
    return FileResponse(
        bundle.path,
        media_type="application/zip",
        filename=bundle.filename,
        background=BackgroundTask(cleanup_export_bundle, bundle.path),
    )


@router.post("/import", response_model=ProjectImportResponse)
async def import_project_bundle(
    bundle: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    summary = await import_projects_bundle(
        db=db,
        current_user=current_user,
        bundle_file=bundle,
        conflict_policy="skip",
    )
    return {
        "imported_projects": summary.imported_projects,
        "skipped_projects": summary.skipped_projects,
        "failed_projects": summary.failed_projects,
        "warnings": summary.warnings,
    }
