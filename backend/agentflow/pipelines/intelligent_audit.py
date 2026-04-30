from __future__ import annotations

import os
from pathlib import Path

from agentflow import Graph, claude, codex, kimi, pi

PIPELINE_DIR = Path(__file__).resolve().parent
PROMPT_DIR = PIPELINE_DIR.parent / "prompts"

ARGUS_PROVIDER = os.environ.get("ARGUS_AGENTFLOW_PROVIDER", "openai_compatible")
ARGUS_MODEL = os.environ.get("ARGUS_AGENTFLOW_MODEL", "gpt-5.4")
ARGUS_BASE_URL = os.environ.get("ARGUS_AGENTFLOW_BASE_URL", "")

# Provider config dispatch.
# Per Phase 0 verification, resolve_provider returns: "openai", "anthropic", "moonshot", "pi"
PROVIDER_CONFIGS = {
    "openai_compatible": {
        "name": "openai",
        "api_key_env": "OPENAI_API_KEY",
        "base_url": ARGUS_BASE_URL or "https://api.openai.com/v1",
        "wire_api": "responses",
    },
    "anthropic_compatible": {
        "name": "anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url": ARGUS_BASE_URL or "https://api.anthropic.com",
        # claude adapter ignores wire_api
    },
    "kimi_compatible": {
        "name": "moonshot",  # Phase 0 verified — resolve_provider returns name="moonshot"
        "api_key_env": "KIMI_API_KEY",  # vendor's KimiAdapter reads KIMI_API_KEY
        "base_url": ARGUS_BASE_URL or "https://api.moonshot.cn/v1",
    },
    "pi_compatible": {
        "name": "pi",
        "api_key_env": "PI_API_KEY",
        "base_url": ARGUS_BASE_URL,
    },
}

AGENT_DSL_DISPATCH = {
    "openai_compatible": codex,
    "anthropic_compatible": claude,
    "kimi_compatible": kimi,
    "pi_compatible": pi,
}

# Legacy alias support
LEGACY_PROVIDER_ALIASES = {
    "openai": "openai_compatible",
    "anthropic": "anthropic_compatible",
}


def _select_agent_and_provider(provider_str=None):
    """Resolve the agentflow DSL function + provider config for the given provider."""
    raw = provider_str or ARGUS_PROVIDER
    normalized = LEGACY_PROVIDER_ALIASES.get(raw, raw)
    agent_fn = AGENT_DSL_DISPATCH.get(normalized, codex)
    provider_config = PROVIDER_CONFIGS.get(normalized, PROVIDER_CONFIGS["openai_compatible"])
    return agent_fn, provider_config


AGENT_FN, PROVIDER_CONFIG = _select_agent_and_provider()


def prompt(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


COMMON_INPUT_CONTRACT = """
Argus runner input path: {{ env.ARGUS_AGENTFLOW_INPUT_PATH | default('/work/input/runner_input.json') }}
Argus output directory: {{ env.ARGUS_AGENTFLOW_OUTPUT_DIR | default('/work/outputs') }}

P1 contract:
- Argus remains the only control plane, API plane, and UI plane.
- Use only project/audit-scope/target-file/vulnerability-type/validation-level/prompt-skill/resource-budget input supplied by Argus.
- Do not use scanner finding bootstrap or any external candidate list as audit input.
- Do not start AgentFlow web server mode.
- Do not use remote targets.
""".strip()


with Graph(
    "argus-intelligent-audit-p1",
    description="Argus controlled AgentFlow P1 intelligent audit pipeline",
    working_dir="/workspace/src",
    concurrency=2,
    fail_fast=True,
    max_iterations=1,
    scratchboard=True,
    use_worktree=False,
    node_defaults={
        "tools": "read_only",
        "target": {"kind": "local", "cwd": "/workspace/src"},
        "timeout_seconds": 1800,
    },
) as dag:
    env_inter = AGENT_FN(
        task_id="env-inter",
        description="role=env-inter; topology_version=argus-agentflow-p1-v1",
        provider=PROVIDER_CONFIG,
        model=ARGUS_MODEL,
        prompt=f"{prompt('env_interpreter.md')}\n\n{COMMON_INPUT_CONTRACT}",
    )

    vuln_reasoner = AGENT_FN(
        task_id="vuln-reasoner",
        description="role=vuln-reasoner; topology_version=argus-agentflow-p1-v1",
        provider=PROVIDER_CONFIG,
        model=ARGUS_MODEL,
        prompt=(
            f"{prompt('vuln_reasoner.md')}\n\n{COMMON_INPUT_CONTRACT}\n\n"
            "Environment interpretation:\n{{ nodes.env-inter.output }}"
        ),
    )

    audit_reporter = AGENT_FN(
        task_id="audit-reporter",
        description="role=audit-reporter; topology_version=argus-agentflow-p1-v1",
        provider=PROVIDER_CONFIG,
        model=ARGUS_MODEL,
        prompt=(
            f"{prompt('audit_reporter.md')}\n\n{COMMON_INPUT_CONTRACT}\n\n"
            "Environment interpretation:\n{{ nodes.env-inter.output }}\n\n"
            "Vulnerability reasoning:\n{{ nodes.vuln-reasoner.output }}"
        ),
    )

    env_inter >> vuln_reasoner >> audit_reporter

print(dag.to_json())
