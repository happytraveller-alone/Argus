import asyncio

import pytest

import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401
from app.api.v1.endpoints.agent_tasks import _cancelled_tasks, _run_with_retries


class _DummyEmitter:
    def __init__(self) -> None:
        self.warnings = []
        self.errors = []

    async def emit_warning(self, message: str, metadata=None):
        self.warnings.append((message, metadata or {}))

    async def emit_error(self, message: str, metadata=None):
        self.errors.append((message, metadata or {}))


@pytest.mark.asyncio
async def test_run_with_retries_user_cancel_does_not_retry():
    emitter = _DummyEmitter()
    task_id = "cancel-user-task"
    _cancelled_tasks.add(task_id)

    attempts = {"count": 0}

    async def cancelled_once():
        attempts["count"] += 1
        raise asyncio.CancelledError("cancelled by user")

    try:
        with pytest.raises(asyncio.CancelledError):
            await _run_with_retries(
                "ORCHESTRATOR_RUN",
                task_id,
                emitter,
                cancelled_once,
                max_attempts=2,
            )
    finally:
        _cancelled_tasks.discard(task_id)

    assert attempts["count"] == 1
    assert emitter.errors
    assert emitter.errors[0][1].get("cancel_origin") == "user"
    assert emitter.errors[0][1].get("retryable") is False


@pytest.mark.asyncio
async def test_run_with_retries_system_cancel_retries_when_marked():
    emitter = _DummyEmitter()
    task_id = "cancel-system-task"
    attempts = {"count": 0}

    async def cancelled_then_success():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise asyncio.CancelledError("system_cancelled")
        return "ok"

    result = await _run_with_retries(
        "TOOLS_INIT",
        task_id,
        emitter,
        cancelled_then_success,
        max_attempts=2,
    )

    assert result == "ok"
    assert attempts["count"] == 2
    assert emitter.warnings
    assert emitter.warnings[0][1].get("cancel_origin") == "system"
    assert emitter.warnings[0][1].get("retryable") is True
