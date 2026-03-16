from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import deps
from app.api.v1.endpoints import projects
from app.db.session import get_db

from test_dashboard_snapshot_v2 import _build_execute_side_effect


def _build_test_client():
    app = FastAPI()
    app.include_router(projects.router, prefix="/api/v1/projects")

    db = SimpleNamespace(
        execute=AsyncMock(side_effect=_build_execute_side_effect(projects.datetime.now(projects.timezone.utc)))
    )

    async def override_db():
        yield db

    async def override_current_user():
        return SimpleNamespace(id="user-1")

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[deps.get_current_user] = override_current_user

    return app, TestClient(app)


@pytest.mark.parametrize("range_days", [7, 14, 30])
def test_dashboard_snapshot_accepts_supported_range_days(range_days, monkeypatch):
    monkeypatch.setattr(
        projects,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"og1": 1, "og2": 1}),
    )
    app, client = _build_test_client()

    try:
        response = client.get(
            "/api/v1/projects/dashboard-snapshot",
            params={"top_n": 10, "range_days": range_days},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_dashboard_snapshot_rejects_unsupported_range_days(monkeypatch):
    monkeypatch.setattr(
        projects,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"og1": 1, "og2": 1}),
    )
    app, client = _build_test_client()

    try:
        response = client.get(
            "/api/v1/projects/dashboard-snapshot",
            params={"top_n": 10, "range_days": 13},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_dashboard_snapshot_defaults_range_days_when_omitted(monkeypatch):
    monkeypatch.setattr(
        projects,
        "count_high_confidence_findings_by_task_ids",
        AsyncMock(return_value={"og1": 1, "og2": 1}),
    )
    app, client = _build_test_client()

    try:
        response = client.get(
            "/api/v1/projects/dashboard-snapshot",
            params={"top_n": 10},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
