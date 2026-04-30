from __future__ import annotations

import os
from pathlib import Path

from agentflow import Graph, codex

PIPELINE_DIR = Path(__file__).resolve().parent
PROMPT_DIR = PIPELINE_DIR.parent / "prompts"
CODEX_MODEL = os.environ.get("ARGUS_AGENTFLOW_MODEL") or None
CODEX_PROVIDER_NAME = os.environ.get("ARGUS_AGENTFLOW_PROVIDER") or "openai"
CODEX_PROVIDER_BASE_URL = os.environ.get("ARGUS_AGENTFLOW_BASE_URL") or None
CODEX_PROVIDER = (
    {
        "name": CODEX_PROVIDER_NAME,
        "base_url": CODEX_PROVIDER_BASE_URL,
        "api_key_env": "OPENAI_API_KEY",
        "wire_api": "responses",
    }
    if CODEX_PROVIDER_BASE_URL
    else CODEX_PROVIDER_NAME
)


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
    env_inter = codex(
        task_id="env-inter",
        description="role=env-inter; topology_version=argus-agentflow-p1-v1",
        provider=CODEX_PROVIDER,
        model=CODEX_MODEL,
        prompt=f"{prompt('env_interpreter.md')}\n\n{COMMON_INPUT_CONTRACT}",
    )

    vuln_reasoner = codex(
        task_id="vuln-reasoner",
        description="role=vuln-reasoner; topology_version=argus-agentflow-p1-v1",
        provider=CODEX_PROVIDER,
        model=CODEX_MODEL,
        prompt=(
            f"{prompt('vuln_reasoner.md')}\n\n{COMMON_INPUT_CONTRACT}\n\n"
            "Environment interpretation:\n{{ nodes.env-inter.output }}"
        ),
    )

    audit_reporter = codex(
        task_id="audit-reporter",
        description="role=audit-reporter; topology_version=argus-agentflow-p1-v1",
        provider=CODEX_PROVIDER,
        model=CODEX_MODEL,
        prompt=(
            f"{prompt('audit_reporter.md')}\n\n{COMMON_INPUT_CONTRACT}\n\n"
            "Environment interpretation:\n{{ nodes.env-inter.output }}\n\n"
            "Vulnerability reasoning:\n{{ nodes.vuln-reasoner.output }}"
        ),
    )

    env_inter >> vuln_reasoner >> audit_reporter

print(dag.to_json())
