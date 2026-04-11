import asyncio

import pytest

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent


class _CapturingEmitter:
    def __init__(self):
        self.events = []

    async def emit(self, event_data):
        self.events.append(event_data)


class _SlowLLMService:
    def __init__(self, sleep_seconds: float, tool_timeout: float, first_timeout: float, stream_timeout: float):
        self.sleep_seconds = sleep_seconds
        self._timeout_config = {
            "tool_timeout": tool_timeout,
            "llm_first_token_timeout": first_timeout,
            "llm_stream_timeout": stream_timeout,
            "agent_timeout": 1800,
            "sub_agent_timeout": 600,
        }

    def get_agent_timeout_config(self):
        return dict(self._timeout_config)

    def chat_completion_stream(self, messages, temperature=None, max_tokens=None):
        async def _gen():
            await asyncio.sleep(self.sleep_seconds)
            yield {"type": "token", "content": "late", "accumulated": "late"}

        return _gen()


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True, data=input_data)


def _build_agent(llm_service, emitter=None):
    return _DummyAgent(
        config=AgentConfig(name="TimeoutAgent", agent_type=AgentType.RECON),
        llm_service=llm_service,
        tools={},
        event_emitter=emitter,
    )


@pytest.mark.asyncio
async def test_stream_llm_call_marks_preflight_timeout(monkeypatch):
    emitter = _CapturingEmitter()
    agent = _build_agent(
        _SlowLLMService(sleep_seconds=0.03, tool_timeout=60, first_timeout=0.01, stream_timeout=0.02),
        emitter=emitter,
    )

    output, _ = await agent.stream_llm_call([{"role": "user", "content": "hello"}], auto_compress=False)

    assert "[超时错误" in output
    assert agent._last_llm_stream_meta.get("error_type") == "preflight_timeout"
    assert agent._last_llm_stream_meta.get("timeout_stage") == "preflight_timeout"
    assert any(
        (event.metadata or {}).get("timeout_stage") == "preflight_timeout"
        for event in emitter.events
        if event.event_type == "error"
    )


@pytest.mark.asyncio
async def test_stream_llm_call_marks_stream_idle_timeout():
    class _GapLLMService:
        def get_agent_timeout_config(self):
            return {
                "tool_timeout": 60,
                "llm_first_token_timeout": 0.05,
                "llm_stream_timeout": 0.01,
                "agent_timeout": 1800,
                "sub_agent_timeout": 600,
            }

        def chat_completion_stream(self, messages, temperature=None, max_tokens=None):
            async def _gen():
                yield {"type": "token", "content": "ok", "accumulated": "ok"}
                await asyncio.sleep(0.03)
                yield {"type": "done", "content": "ok", "usage": {"total_tokens": 1}, "finish_reason": "stop"}

            return _gen()

    agent = _build_agent(_GapLLMService())

    output, _ = await agent.stream_llm_call([{"role": "user", "content": "hello"}], auto_compress=False)

    assert output == "ok"
    assert agent._last_llm_stream_meta.get("error_type") == "stream_idle_timeout"
    assert agent._last_llm_stream_meta.get("timeout_stage") == "stream_idle_timeout"

