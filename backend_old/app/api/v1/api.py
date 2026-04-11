from fastapi import APIRouter
from app.api.v1.endpoints import (
    agent_tasks,
    agent_test,
    config,
    prompts,
    rules,
    static_tasks,
)

api_router = APIRouter()
api_router.include_router(config.router, prefix="/config", tags=["config"])
api_router.include_router(prompts.router, prefix="/prompts", tags=["prompts"])
api_router.include_router(rules.router, prefix="/rules", tags=["rules"])
api_router.include_router(agent_tasks.router, prefix="/agent-tasks", tags=["agent-tasks"])
api_router.include_router(agent_test.router, prefix="/agent-test", tags=["agent-test"])
api_router.include_router(static_tasks.router, prefix="/static-tasks", tags=["static-tasks"])
