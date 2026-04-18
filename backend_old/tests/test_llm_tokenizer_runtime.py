import pytest

import app.services.llm.memory_compressor as memory_compressor
import app.services.llm.tokenizer as tokenizer
from app.services.llm.memory_compressor import MemoryCompressor


def _long_messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "系统提示" * 20},
        {"role": "user", "content": "A" * 120},
        {"role": "assistant", "content": "B" * 120},
        {"role": "user", "content": "C" * 120},
    ]


def test_token_estimator_defaults_to_heuristic_without_touching_tiktoken(monkeypatch):
    expected = tokenizer.TokenEstimator._heuristic_estimate("hello world")

    monkeypatch.delenv("LLM_TOKEN_COUNTING_MODE", raising=False)
    monkeypatch.setattr(tokenizer, "_logged_method", False)
    monkeypatch.setattr(tokenizer, "_runtime_mode", None, raising=False)

    def _unexpected_encoder(_model: str):
        raise AssertionError("default runtime path should not touch tiktoken")

    monkeypatch.setattr(tokenizer, "_get_tiktoken_encoder", _unexpected_encoder)

    assert tokenizer.TokenEstimator.count_tokens("hello world", "gpt-4o-mini") == expected


def test_memory_compressor_uses_fast_estimation_without_tiktoken(monkeypatch):
    compressor = MemoryCompressor(max_total_tokens=40, min_recent_messages=1)

    def _unexpected_precise_counter(*_args, **_kwargs):
        raise AssertionError("memory compression should not rely on precise tiktoken counting")

    monkeypatch.setattr(memory_compressor.TokenEstimator, "count_tokens", _unexpected_precise_counter)

    messages = _long_messages()
    assert compressor.should_compress(messages) is True

    compressed = compressor.compress_history(messages)
    assert compressed
    assert len(compressed) < len(messages)
