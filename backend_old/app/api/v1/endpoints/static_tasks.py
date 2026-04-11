from fastapi import APIRouter

from app.api.v1.endpoints import static_tasks_cache as _cache
from app.api.v1.endpoints.static_tasks_shared import (
    deps,
    get_db,
    logger,
    settings,
)


router = APIRouter()
router.include_router(_cache.router)

get_repo_cache_stats = _cache.get_repo_cache_stats
cleanup_unused_cache = _cache.cleanup_unused_cache
clear_all_cache = _cache.clear_all_cache
