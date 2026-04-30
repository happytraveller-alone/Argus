"""
Tests for load_provider_runtime_env in agentflow-runner-adapter.py

Each test exercises a distinct credential / provider dispatch path.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the adapter module from its non-standard filename
# ---------------------------------------------------------------------------
_ADAPTER_PATH = Path(__file__).parent.parent / "agentflow-runner-adapter.py"


def _load_adapter():
    spec = importlib.util.spec_from_file_location("agentflow_runner_adapter", _ADAPTER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


adapter = _load_adapter()
load_provider_runtime_env = adapter.load_provider_runtime_env


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_input(provider: str, model: str | None = None) -> dict:
    llm: dict = {"provider": provider}
    if model:
        llm["model"] = model
    return {"llm": llm}


# ---------------------------------------------------------------------------
# T2.4 Test 1 — codex legacy auth.json path
# ---------------------------------------------------------------------------

def test_load_provider_runtime_env_codex_legacy_authjson_path(tmp_path, monkeypatch):
    """
    OPENAI_API_KEY and LLM_API_KEY are both absent.
    ARGUS_CODEX_AUTH_FILE points to a temp file containing {"OPENAI_API_KEY": "sk-from-auth"}.
    provider=openai_compatible → runtime_env["OPENAI_API_KEY"] must equal "sk-from-auth".
    credential_source must be "codex_auth_json".
    """
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"OPENAI_API_KEY": "sk-from-auth"}), encoding="utf-8")

    # Ensure no real keys bleed in from the test host environment
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("ARGUS_CODEX_AUTH_FILE", str(auth_file))
    # Point config to a non-existent path so it is skipped cleanly
    monkeypatch.setenv("ARGUS_CODEX_CONFIG_FILE", str(tmp_path / "no-config.toml"))

    runner_input = _make_input("openai_compatible")
    runtime_env, diagnostics = load_provider_runtime_env(runner_input)

    assert runtime_env.get("OPENAI_API_KEY") == "sk-from-auth", (
        f"Expected 'sk-from-auth', got {runtime_env.get('OPENAI_API_KEY')!r}"
    )
    assert diagnostics.get("credential_source") == "codex_auth_json", (
        f"Unexpected credential_source: {diagnostics.get('credential_source')!r}"
    )


# ---------------------------------------------------------------------------
# T2.4 Test 2 — anthropic dispatch with correct key shape (no warning)
# ---------------------------------------------------------------------------

def test_load_provider_runtime_env_anthropic_dispatches_anthropic_api_key(monkeypatch):
    """
    LLM_API_KEY="sk-ant-test", provider=anthropic_compatible.
    runtime_env["ANTHROPIC_API_KEY"] must equal "sk-ant-test".
    diagnostics["warnings"] must be absent or empty (correct prefix — no warning).
    """
    monkeypatch.setenv("LLM_API_KEY", "sk-ant-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    runner_input = _make_input("anthropic_compatible")
    runtime_env, diagnostics = load_provider_runtime_env(runner_input)

    assert runtime_env.get("ANTHROPIC_API_KEY") == "sk-ant-test", (
        f"Expected 'sk-ant-test', got {runtime_env.get('ANTHROPIC_API_KEY')!r}"
    )
    warnings = diagnostics.get("warnings", [])
    assert not warnings, f"Expected no warnings for correct prefix, got: {warnings}"


# ---------------------------------------------------------------------------
# T2.4 Test 3 — anthropic with wrong key shape → WARN emitted
# ---------------------------------------------------------------------------

def test_load_provider_runtime_env_anthropic_warns_on_wrong_prefix(monkeypatch):
    """
    LLM_API_KEY="sk-foo" (non-anthropic shape), provider=anthropic_compatible.
    runtime_env["ANTHROPIC_API_KEY"] must still equal "sk-foo".
    diagnostics["warnings"] must contain a message mentioning "non-Anthropic".
    """
    monkeypatch.setenv("LLM_API_KEY", "sk-foo")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    runner_input = _make_input("anthropic_compatible")
    runtime_env, diagnostics = load_provider_runtime_env(runner_input)

    assert runtime_env.get("ANTHROPIC_API_KEY") == "sk-foo", (
        f"Expected 'sk-foo', got {runtime_env.get('ANTHROPIC_API_KEY')!r}"
    )
    warnings = diagnostics.get("warnings", [])
    assert any("non-Anthropic" in w for w in warnings), (
        f"Expected 'non-Anthropic' warning in diagnostics, got: {warnings}"
    )


# ---------------------------------------------------------------------------
# T2.4 Test 4 — openai_compatible with an Anthropic-shaped key → WARN
# ---------------------------------------------------------------------------

def test_load_provider_runtime_env_openai_warns_on_anthropic_prefix(tmp_path, monkeypatch):
    """
    LLM_API_KEY="sk-ant-test", provider=openai_compatible.
    diagnostics["warnings"] must contain a warning about the Anthropic-shaped key.
    """
    monkeypatch.setenv("LLM_API_KEY", "sk-ant-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Point auth / config to non-existent paths to avoid side-effects
    monkeypatch.setenv("ARGUS_CODEX_AUTH_FILE", str(tmp_path / "no-auth.json"))
    monkeypatch.setenv("ARGUS_CODEX_CONFIG_FILE", str(tmp_path / "no-config.toml"))

    runner_input = _make_input("openai_compatible")
    runtime_env, diagnostics = load_provider_runtime_env(runner_input)

    warnings = diagnostics.get("warnings", [])
    assert any("sk-ant-" in w for w in warnings), (
        f"Expected warning about 'sk-ant-' prefix for openai_compatible, got: {warnings}"
    )


# ---------------------------------------------------------------------------
# T2.4 Test 5 — kimi dispatches to MOONSHOT_API_KEY
# ---------------------------------------------------------------------------

def test_load_provider_runtime_env_kimi_dispatches_moonshot_api_key(monkeypatch):
    """
    provider=kimi_compatible, LLM_API_KEY="km-test".
    Both KIMI_API_KEY (vendor-canonical) and MOONSHOT_API_KEY (forward-compat)
    must equal "km-test" so whichever the kimi binary reads is set.
    """
    monkeypatch.setenv("LLM_API_KEY", "km-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("KIMI_API_KEY", raising=False)

    runner_input = _make_input("kimi_compatible")
    runtime_env, diagnostics = load_provider_runtime_env(runner_input)

    assert runtime_env.get("KIMI_API_KEY") == "km-test", (
        f"Expected KIMI_API_KEY='km-test', got {runtime_env.get('KIMI_API_KEY')!r}"
    )
    assert runtime_env.get("MOONSHOT_API_KEY") == "km-test", (
        f"Expected MOONSHOT_API_KEY='km-test' (forward-compat), got {runtime_env.get('MOONSHOT_API_KEY')!r}"
    )
    assert diagnostics.get("credential_source") == "llm_api_key"


# ---------------------------------------------------------------------------
# Bonus: legacy alias "openai" resolves to openai_compatible
# ---------------------------------------------------------------------------

def test_legacy_alias_openai_resolves(tmp_path, monkeypatch):
    """provider="openai" (legacy alias) must behave identically to openai_compatible."""
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"OPENAI_API_KEY": "sk-legacy-alias"}), encoding="utf-8")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("ARGUS_CODEX_AUTH_FILE", str(auth_file))
    monkeypatch.setenv("ARGUS_CODEX_CONFIG_FILE", str(tmp_path / "no-config.toml"))

    runner_input = _make_input("openai")
    runtime_env, diagnostics = load_provider_runtime_env(runner_input)

    assert runtime_env.get("OPENAI_API_KEY") == "sk-legacy-alias"
    assert diagnostics.get("credential_source") == "codex_auth_json"
