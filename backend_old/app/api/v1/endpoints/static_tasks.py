from fastapi import APIRouter

from app.api.v1.endpoints.static_tasks_shared import (
    deps,
    get_db,
    logger,
    settings,
)


router = APIRouter()
