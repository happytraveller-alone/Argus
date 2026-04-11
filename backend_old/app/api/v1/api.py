from fastapi import APIRouter
from app.api.v1.endpoints import (
    agent_tasks,
    static_tasks,
)

api_router = APIRouter()
api_router.include_router(agent_tasks.router, prefix="/agent-tasks", tags=["agent-tasks"])
api_router.include_router(static_tasks.router, prefix="/static-tasks", tags=["static-tasks"])
