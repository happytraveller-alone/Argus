"""Facade and compatibility exports for agent task endpoints."""

from fastapi import APIRouter

from .agent_tasks_bootstrap import *  # noqa: F401,F403
from .agent_tasks_contracts import *  # noqa: F401,F403
from .agent_tasks_findings import *  # noqa: F401,F403
from .agent_tasks_tool_runtime import *  # noqa: F401,F403

router = APIRouter()
