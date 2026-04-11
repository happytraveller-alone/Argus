from app.services.upload.project_stats import get_cloc_stats
from app.models.project_info import ProjectInfo
import asyncio

async def test_get_cloc_stats():
    uuid = "c4a41891-046d-48a7-a46b-7f68fc8a6fc0"
    project_info = ProjectInfo()
    project_info.project_id = uuid
    return await get_cloc_stats(project_info)

print(asyncio.run(test_get_cloc_stats()))