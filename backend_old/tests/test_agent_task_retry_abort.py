import asyncio

import pytest

from app.api.v1.endpoints.agent_tasks import (
    StepRetryExceededError,
    _run_with_retries,
)
import app.models.opengrep  # noqa: F401
import app.models.gitleaks  # noqa: F401


class _DummyEmitter:
    def __init__(self):
        self.warnings = []
        self.errors = []

    async def emit_warning(self, message: str, metadata=None):
        self.warnings.append((message, metadata or {}))

    async def emit_error(self, message: str, metadata=None):
        self.errors.append((message, metadata or {}))


@pytest.mark.asyncio
async def test_run_with_retries_recovers_on_last_attempt():
    emitter = _DummyEmitter()
    attempts = {"count": 0}

    async def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("transient rag failure")
        return "ok"

    result = await _run_with_retries(
        "TOOLS_INIT",
        "task-1",
        emitter,
        flaky,
        max_attempts=3,
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert len(emitter.warnings) == 2
    assert len(emitter.errors) == 0
    assert emitter.warnings[0][1]["step_name"] == "TOOLS_INIT"


@pytest.mark.asyncio
async def test_run_with_retries_aborts_after_max_attempts():
    emitter = _DummyEmitter()
    attempts = {"count": 0}

    async def always_fail():
        attempts["count"] += 1
        raise RuntimeError("rag index unavailable")

    with pytest.raises(StepRetryExceededError) as exc_info:
        await _run_with_retries(
            "TOOLS_INIT",
            "task-2",
            emitter,
            always_fail,
            max_attempts=3,
        )

    assert attempts["count"] == 3
    assert exc_info.value.step_name == "TOOLS_INIT"
    assert exc_info.value.attempts == 3
    assert "第 3/3 次失败" in exc_info.value.final_message
    assert len(emitter.errors) == 1
    assert emitter.errors[0][1]["is_terminal"] is True


@pytest.mark.asyncio
async def test_run_with_retries_does_not_retry_cancelled_error():
    emitter = _DummyEmitter()
    attempts = {"count": 0}

    async def cancelled_once():
        attempts["count"] += 1
        raise asyncio.CancelledError("cancelled by user")

    with pytest.raises(asyncio.CancelledError):
        await _run_with_retries(
            "ORCHESTRATOR_RUN",
            "task-3",
            emitter,
            cancelled_once,
            max_attempts=3,
        )

    assert attempts["count"] == 1
    assert len(emitter.warnings) == 0
    assert len(emitter.errors) == 1
    assert emitter.errors[0][1]["cancel_origin"] == "user"
    assert emitter.errors[0][1]["retryable"] is False
