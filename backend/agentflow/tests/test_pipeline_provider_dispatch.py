"""Smoke tests for intelligent_audit.py provider dispatch.

Verifies that AGENT_FN and PROVIDER_CONFIG resolve correctly for each
supported provider, including default (openai_compatible) and
anthropic_compatible.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest

# Ensure agentflow vendor is importable.
AGENTFLOW_SRC = str(Path(__file__).resolve().parents[4] / "vendor" / "agentflow-src")
if AGENTFLOW_SRC not in sys.path:
    sys.path.insert(0, AGENTFLOW_SRC)

PIPELINE_PATH = Path(__file__).resolve().parents[1] / "pipelines" / "intelligent_audit.py"


def _load_pipeline(env_overrides: dict) -> object:
    """Load (or reload) the pipeline module with given env overrides.

    Env vars are set before load and restored after to avoid test pollution.
    """
    # Save original values.
    saved = {}
    for key in ("ARGUS_AGENTFLOW_PROVIDER", "ARGUS_AGENTFLOW_MODEL", "ARGUS_AGENTFLOW_BASE_URL"):
        saved[key] = os.environ.get(key)

    try:
        # Apply overrides.
        for key, val in env_overrides.items():
            if val is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = val

        # Load fresh module instance (bypass sys.modules cache).
        spec = importlib.util.spec_from_file_location("intelligent_audit_test", PIPELINE_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        # Restore originals.
        for key, original in saved.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original


def test_default_provider_uses_codex():
    """Default env (ARGUS_AGENTFLOW_PROVIDER unset) → AGENT_FN is codex."""
    from agentflow import codex

    mod = _load_pipeline({
        "ARGUS_AGENTFLOW_PROVIDER": None,
        "ARGUS_AGENTFLOW_MODEL": None,
        "ARGUS_AGENTFLOW_BASE_URL": None,
    })

    assert mod.AGENT_FN is codex, f"Expected codex, got {mod.AGENT_FN}"
    assert mod.PROVIDER_CONFIG["name"] == "openai"
    assert mod.PROVIDER_CONFIG["api_key_env"] == "OPENAI_API_KEY"
    assert mod.PROVIDER_CONFIG["wire_api"] == "responses"


def test_openai_compatible_uses_codex():
    """ARGUS_AGENTFLOW_PROVIDER=openai_compatible → AGENT_FN is codex."""
    from agentflow import codex

    mod = _load_pipeline({
        "ARGUS_AGENTFLOW_PROVIDER": "openai_compatible",
        "ARGUS_AGENTFLOW_MODEL": "gpt-4o",
        "ARGUS_AGENTFLOW_BASE_URL": None,
    })

    assert mod.AGENT_FN is codex
    assert mod.PROVIDER_CONFIG["name"] == "openai"
    assert mod.PROVIDER_CONFIG["wire_api"] == "responses"


def test_anthropic_compatible_uses_claude():
    """ARGUS_AGENTFLOW_PROVIDER=anthropic_compatible → AGENT_FN is claude."""
    from agentflow import claude

    mod = _load_pipeline({
        "ARGUS_AGENTFLOW_PROVIDER": "anthropic_compatible",
        "ARGUS_AGENTFLOW_MODEL": "claude-3-5-haiku",
        "ARGUS_AGENTFLOW_BASE_URL": None,
    })

    assert mod.AGENT_FN is claude, f"Expected claude, got {mod.AGENT_FN}"
    assert mod.PROVIDER_CONFIG["name"] == "anthropic"
    assert mod.PROVIDER_CONFIG["api_key_env"] == "ANTHROPIC_API_KEY"


def test_kimi_compatible_uses_kimi():
    """ARGUS_AGENTFLOW_PROVIDER=kimi_compatible → AGENT_FN is kimi, name=moonshot."""
    from agentflow import kimi

    mod = _load_pipeline({
        "ARGUS_AGENTFLOW_PROVIDER": "kimi_compatible",
        "ARGUS_AGENTFLOW_MODEL": "moonshot-v1-8k",
        "ARGUS_AGENTFLOW_BASE_URL": None,
    })

    assert mod.AGENT_FN is kimi, f"Expected kimi, got {mod.AGENT_FN}"
    # Phase 0 verified: resolve_provider("kimi") returns name="moonshot"
    assert mod.PROVIDER_CONFIG["name"] == "moonshot"
    # CRITICAL-1 fix: vendor's KimiAdapter reads KIMI_API_KEY (not MOONSHOT_API_KEY)
    assert mod.PROVIDER_CONFIG["api_key_env"] == "KIMI_API_KEY"


def test_pi_compatible_uses_pi():
    """ARGUS_AGENTFLOW_PROVIDER=pi_compatible → AGENT_FN is pi, name=pi."""
    from agentflow import pi

    mod = _load_pipeline({
        "ARGUS_AGENTFLOW_PROVIDER": "pi_compatible",
        "ARGUS_AGENTFLOW_MODEL": "pi-model",
        "ARGUS_AGENTFLOW_BASE_URL": None,
    })

    assert mod.AGENT_FN is pi, f"Expected pi, got {mod.AGENT_FN}"
    assert mod.PROVIDER_CONFIG["name"] == "pi"
    assert mod.PROVIDER_CONFIG["api_key_env"] == "PI_API_KEY"


def test_legacy_alias_openai_maps_to_openai_compatible():
    """Legacy alias ARGUS_AGENTFLOW_PROVIDER=openai → treated as openai_compatible."""
    from agentflow import codex

    mod = _load_pipeline({
        "ARGUS_AGENTFLOW_PROVIDER": "openai",
        "ARGUS_AGENTFLOW_MODEL": None,
        "ARGUS_AGENTFLOW_BASE_URL": None,
    })

    assert mod.AGENT_FN is codex
    assert mod.PROVIDER_CONFIG["name"] == "openai"


def test_legacy_alias_anthropic_maps_to_anthropic_compatible():
    """Legacy alias ARGUS_AGENTFLOW_PROVIDER=anthropic → treated as anthropic_compatible."""
    from agentflow import claude

    mod = _load_pipeline({
        "ARGUS_AGENTFLOW_PROVIDER": "anthropic",
        "ARGUS_AGENTFLOW_MODEL": None,
        "ARGUS_AGENTFLOW_BASE_URL": None,
    })

    assert mod.AGENT_FN is claude
    assert mod.PROVIDER_CONFIG["name"] == "anthropic"


def test_unknown_provider_falls_back_to_codex():
    """Unknown provider string falls back to codex + openai_compatible config."""
    from agentflow import codex

    mod = _load_pipeline({
        "ARGUS_AGENTFLOW_PROVIDER": "nonexistent_provider",
        "ARGUS_AGENTFLOW_MODEL": None,
        "ARGUS_AGENTFLOW_BASE_URL": None,
    })

    assert mod.AGENT_FN is codex
    assert mod.PROVIDER_CONFIG["name"] == "openai"


def test_base_url_override_propagates():
    """Custom ARGUS_AGENTFLOW_BASE_URL is reflected in PROVIDER_CONFIG."""
    mod = _load_pipeline({
        "ARGUS_AGENTFLOW_PROVIDER": "openai_compatible",
        "ARGUS_AGENTFLOW_MODEL": "gpt-4o",
        "ARGUS_AGENTFLOW_BASE_URL": "https://my-proxy.example.com/v1",
    })

    assert mod.PROVIDER_CONFIG["base_url"] == "https://my-proxy.example.com/v1"


def test_model_env_propagates():
    """ARGUS_AGENTFLOW_MODEL is reflected in ARGUS_MODEL module constant."""
    mod = _load_pipeline({
        "ARGUS_AGENTFLOW_PROVIDER": "anthropic_compatible",
        "ARGUS_AGENTFLOW_MODEL": "claude-3-5-haiku",
        "ARGUS_AGENTFLOW_BASE_URL": None,
    })

    assert mod.ARGUS_MODEL == "claude-3-5-haiku"
