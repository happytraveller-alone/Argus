from fastapi import APIRouter

from app.api.v1.endpoints import static_tasks_cache as _cache
from app.api.v1.endpoints import static_tasks_opengrep as _opengrep
from app.api.v1.endpoints.static_tasks_shared import (
    deps,
    get_db,
    logger,
    settings,
)


router = APIRouter()
router.include_router(_opengrep.router)
router.include_router(_cache.router)


OpengrepScanTaskCreate = _opengrep.OpengrepScanTaskCreate
OpengrepScanTaskResponse = _opengrep.OpengrepScanTaskResponse
OpengrepFindingResponse = _opengrep.OpengrepFindingResponse
OpengrepFindingContextLine = _opengrep.OpengrepFindingContextLine
OpengrepFindingContextResponse = _opengrep.OpengrepFindingContextResponse
OpengrepScanProgressLogEntry = _opengrep.OpengrepScanProgressLogEntry
OpengrepScanProgressResponse = _opengrep.OpengrepScanProgressResponse

_parse_opengrep_output = _opengrep._parse_opengrep_output

list_static_tasks = _opengrep.list_static_tasks
create_static_task = _opengrep.create_static_task
delete_static_task = _opengrep.delete_static_task
get_static_task = _opengrep.get_static_task
interrupt_static_task = _opengrep.interrupt_static_task
get_static_task_progress = _opengrep.get_static_task_progress
get_static_task_findings = _opengrep.get_static_task_findings
get_static_task_finding = _opengrep.get_static_task_finding
get_static_task_finding_context = _opengrep.get_static_task_finding_context
update_static_task_finding = _opengrep.update_static_task_finding

get_repo_cache_stats = _cache.get_repo_cache_stats
cleanup_unused_cache = _cache.cleanup_unused_cache
clear_all_cache = _cache.clear_all_cache
