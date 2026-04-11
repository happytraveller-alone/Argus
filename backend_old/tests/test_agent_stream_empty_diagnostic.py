import pytest

from app.services.agent.agents.base import AgentConfig, AgentResult, AgentType, BaseAgent


class _DummyLLMService:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def chat_completion_stream(self, messages, temperature=None, max_tokens=None):
        async def _gen():
            for chunk in self._chunks:
                yield chunk

        return _gen()


class _DummyAgent(BaseAgent):
    async def run(self, input_data):
        return AgentResult(success=True)


def _build_agent(chunks):
    config = AgentConfig(name="Dummy", agent_type=AgentType.RECON)
    return _DummyAgent(config=config, llm_service=_DummyLLMService(chunks), tools={}, event_emitter=None)


@pytest.mark.asyncio
async def test_stream_llm_call_returns_non_empty_diagnostic_on_empty_response_error():
    agent = _build_agent(
        [
            {
                "type": "error",
                "error_type": "empty_response",
                "error": "empty response from upstream",
                "user_message": "模型返回空响应",
                "accumulated": "",
                "finish_reason": "content_filter",
            }
        ]
    )

    output, _ = await agent.stream_llm_call([{"role": "user", "content": "hello"}], auto_compress=False)
    assert "[API_ERROR:empty_response]" in output
    assert agent._last_llm_stream_meta.get("finish_reason") == "content_filter"
    assert agent._last_llm_stream_meta.get("empty_reason") == "empty_response"


@pytest.mark.asyncio
async def test_stream_llm_call_handles_done_with_empty_content():
    agent = _build_agent(
        [
            {
                "type": "done",
                "content": "",
                "finish_reason": "stop",
                "usage": {"total_tokens": 0},
            }
        ]
    )

    output, _ = await agent.stream_llm_call([{"role": "user", "content": "hello"}], auto_compress=False)
    assert output.startswith("[API_ERROR:empty_response]")
    assert agent._last_llm_stream_meta.get("empty_reason") == "empty_done"
