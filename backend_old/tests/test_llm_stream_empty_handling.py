from types import SimpleNamespace

import pytest

from app.services.llm.adapters.litellm_adapter import LiteLLMAdapter
from app.services.llm.types import LLMConfig, LLMMessage, LLMProvider, LLMRequest


class _AsyncStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        value = self._chunks[self._idx]
        self._idx += 1
        return value


def _build_adapter() -> LiteLLMAdapter:
    cfg = LLMConfig(
        provider=LLMProvider.OPENAI,
        api_key="sk-test",
        model="gpt-4o-mini",
        base_url="https://example.com/v1",
    )
    return LiteLLMAdapter(cfg)


def _build_request() -> LLMRequest:
    return LLMRequest(messages=[LLMMessage(role="user", content="hello")], max_tokens=128)


@pytest.mark.asyncio
async def test_stream_complete_emits_empty_response_error(monkeypatch):
    adapter = _build_adapter()
    request = _build_request()

    finish_chunk = SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=None, reasoning_content=None, text=None),
                finish_reason="content_filter",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=0, total_tokens=12),
    )

    async def _fake_acompletion(**kwargs):
        return _AsyncStream([finish_chunk])

    import litellm

    monkeypatch.setattr(litellm, "acompletion", _fake_acompletion)

    chunks = []
    async for chunk in adapter.stream_complete(request):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0]["type"] == "error"
    assert chunks[0]["error_type"] == "empty_response"
    assert "finish_reason=content_filter" in chunks[0]["error"]


@pytest.mark.asyncio
async def test_stream_complete_emits_empty_stream_error(monkeypatch):
    adapter = _build_adapter()
    request = _build_request()

    middle_chunk = SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=None, reasoning_content=None, text=None),
                finish_reason=None,
            )
        ],
        usage=None,
    )

    async def _fake_acompletion(**kwargs):
        return _AsyncStream([middle_chunk])

    import litellm

    monkeypatch.setattr(litellm, "acompletion", _fake_acompletion)

    chunks = []
    async for chunk in adapter.stream_complete(request):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0]["type"] == "error"
    assert chunks[0]["error_type"] == "empty_stream"


@pytest.mark.asyncio
async def test_stream_complete_does_not_estimate_prompt_tokens_before_first_chunk(monkeypatch):
    adapter = _build_adapter()
    request = _build_request()
    state = {"started": False}

    token_chunk = SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content="hi", reasoning_content=None, text=None),
                finish_reason=None,
            )
        ],
        usage=None,
    )
    done_chunk = SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=None, reasoning_content=None, text=None),
                finish_reason="stop",
            )
        ],
        usage=None,
    )

    async def _fake_acompletion(**kwargs):
        state["started"] = True
        return _AsyncStream([token_chunk, done_chunk])

    def _fake_estimate_tokens(*_args, **_kwargs):
        if not state["started"]:
            raise AssertionError("prompt token estimation should not happen before upstream stream starts")
        return 2

    import litellm
    from app.services.llm.adapters import litellm_adapter as litellm_adapter_module

    monkeypatch.setattr(litellm, "acompletion", _fake_acompletion)
    monkeypatch.setattr(litellm_adapter_module, "estimate_tokens", _fake_estimate_tokens)

    chunks = []
    async for chunk in adapter.stream_complete(request):
        chunks.append(chunk)

    assert chunks[0]["type"] == "token"
    assert chunks[-1]["type"] == "done"
