from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import static_tasks


class _ScalarOneOrNoneResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


@pytest.mark.asyncio
async def test_update_gitleaks_finding_status_rejects_fixed():
    finding = SimpleNamespace(id="finding-1", status="open")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_ScalarOneOrNoneResult(finding))

    with pytest.raises(HTTPException) as exc_info:
        await static_tasks.update_gitleaks_finding_status(
            finding_id="finding-1",
            status="fixed",
            db=db,
            current_user=SimpleNamespace(id="user-1"),
        )

    assert exc_info.value.status_code == 400
