"""Facade and compatibility exports for agent task endpoints."""

from fastapi import APIRouter

from .agent_tasks_bootstrap import *  # noqa: F401,F403
from .agent_tasks_contracts import *  # noqa: F401,F403
from .agent_tasks_execution import *  # noqa: F401,F403
from .agent_tasks_findings import *  # noqa: F401,F403
from .agent_tasks_routes_tasks import *  # noqa: F401,F403
from .agent_tasks_routes_tasks import router as _tasks_router
from .agent_tasks_runtime import *  # noqa: F401,F403
from .agent_tasks_tool_runtime import *  # noqa: F401,F403

router = APIRouter()
router.include_router(_tasks_router)
