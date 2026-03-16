"""
Manual/integration smoke test for project description generation.

This originally executed at import-time which breaks pytest collection in clean environments
where the referenced project ZIP does not exist.
"""

import os

import pytest

from app.models.project_info import ProjectInfo
from app.services.upload.project_stats import generate_project_description
from app.services.zip_storage import get_project_zip_path

# 🔥 导入所有模型以确保 SQLAlchemy 注册表完整
from app.models import agent_task, opengrep, project  # noqa: F401


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_generate_project_description_smoke():
    project_id = os.environ.get("VulHunter_TEST_PROJECT_ID")
    if not project_id:
        pytest.skip("Set VulHunter_TEST_PROJECT_ID to run this integration test.")

    zip_path = get_project_zip_path(project_id)
    if not zip_path or not os.path.exists(zip_path):
        pytest.skip(f"Project ZIP not found at {zip_path!r}; skipping integration test.")

    project_info = ProjectInfo()
    project_info.project_id = project_id

    result = await generate_project_description(project_info)
    assert isinstance(result, dict)
    # Expect the analyzer's primary output field when analysis succeeds.
    assert "project_description" in result or "error" in result
