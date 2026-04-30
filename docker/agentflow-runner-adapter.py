#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - host smoke fallback for Python < 3.11
    tomllib = None

CONTRACT_VERSION = "argus-agentflow-p1/v1"
SUPPORTED_CONTRACT_VERSIONS = {
    CONTRACT_VERSION,
    "argus-agentflow-p2/v1",
    "argus-agentflow-p3/v1",
}
TOPOLOGY_VERSION = "p1-fixed-dag-v1"
DEFAULT_PIPELINE = "/app/backend/agentflow/pipelines/intelligent_audit.py"
DEFAULT_INPUT_PATH = "/work/input/runner_input.json"
DEFAULT_OUTPUT_DIR = "/work/outputs"
DEFAULT_RUNS_DIR = "/work/agentflow-runs"
TAIL_LIMIT = 64 * 1024

ROLE_BY_NODE = {
    "env-inter": "env-inter",
    "vuln-reasoner": "vuln-reasoner",
    "audit-reporter": "audit-reporter",
}

PROVIDER_DISPATCH = {
    "openai_compatible": {
        "agent_kind": "codex",
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "wire_api": "responses",
    },
    "anthropic_compatible": {
        "agent_kind": "claude",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "wire_api": "messages",
    },
    "kimi_compatible": {
        # CRITICAL-1 fix: vendor agentflow's KimiAdapter reads KIMI_API_KEY
        # (vendor/agentflow-src/agentflow/agents/kimi.py:65 + cli.py:1207).
        # The dispatch body also writes MOONSHOT_API_KEY for forward-compat.
        "agent_kind": "kimi",
        "api_key_env": "KIMI_API_KEY",
        "base_url_env": "KIMI_BASE_URL",
        "wire_api": "responses",
    },
    "pi_compatible": {
        "agent_kind": "pi",
        "api_key_env": "PI_API_KEY",
        "base_url_env": "PI_BASE_URL",
        "wire_api": "responses",
    },
}

# Legacy alias mapping
LEGACY_PROVIDER_ALIASES = {
    "openai": "openai_compatible",
    "anthropic": "anthropic_compatible",
}


def now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tail(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = value
    return text[-TAIL_LIMIT:]


SENSITIVE_MARKERS = (
    "Authorization:",
    "authorization:",
    "Cookie:",
    "cookie:",
    "apiKey=",
    "api_key=",
    "llmApiKey=",
)
SENSITIVE_VALUES: list[str] = []


def redact_text(value: str | bytes | None) -> str:
    text = tail(value)
    for marker in SENSITIVE_MARKERS:
        pattern = re.compile(rf"({re.escape(marker)}\s*)([^\s&,;]+)")
        text = pattern.sub(r"\1[REDACTED]", text)
    text = re.sub(r"(sk-[A-Za-z0-9_\-]{8,})", "[REDACTED_API_KEY]", text)
    for secret in SENSITIVE_VALUES:
        if secret:
            text = text.replace(secret, "[REDACTED_SECRET]")
    text = text.replace("/var/run/docker.sock", "[REDACTED_DOCKER_SOCKET]")
    return text


def register_secret(value: str | None) -> None:
    if isinstance(value, str) and len(value.strip()) >= 8:
        SENSITIVE_VALUES.append(value.strip())


def nested_str(mapping: Any, path: list[str]) -> str | None:
    current = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    if isinstance(current, str) and current.strip():
        return current.strip()
    return None


def codex_config_value(config: dict[str, Any], key: str) -> str | None:
    if key == "base_url":
        provider = nested_str(config, ["model_provider"]) or "openai"
        return nested_str(config, ["model_providers", provider, "base_url"]) or nested_str(
            config, ["model_provider", "base_url"]
        )
    return nested_str(config, [key])


def parse_codex_config(text: str) -> dict[str, Any]:
    if tomllib is not None:
        return tomllib.loads(text)

    parsed: dict[str, Any] = {}
    current: dict[str, Any] = parsed
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = parsed
            for part in line.strip("[]").split("."):
                current = current.setdefault(part, {})
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and value:
            current[key] = value
    return parsed


def load_provider_runtime_env(runner_input: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    llm_block = runner_input.get("llm", {}) if isinstance(runner_input.get("llm"), dict) else {}
    raw_provider = llm_block.get("provider", "openai_compatible")
    provider = LEGACY_PROVIDER_ALIASES.get(raw_provider, raw_provider)
    dispatch = PROVIDER_DISPATCH.get(provider)

    runtime_env: dict[str, str] = {}
    diagnostics: dict[str, Any] = {"credential_source": None}

    # Source the API key: env LLM_API_KEY first, then legacy provider-specific env, then auth.json (codex only).
    llm_api_key = os.environ.get("LLM_API_KEY", "").strip()

    if dispatch is None:
        diagnostics["unsupported_provider"] = raw_provider
        return runtime_env, diagnostics

    target_api_key_env = dispatch["api_key_env"]

    if provider == "openai_compatible":
        # Preserve existing codex behavior: direct env var, then LLM_API_KEY, then auth.json fallback.
        config_path = Path(os.environ.get("ARGUS_CODEX_CONFIG_FILE", "/run/argus-codex/config.toml"))
        auth_path = Path(os.environ.get("ARGUS_CODEX_AUTH_FILE", "/run/argus-codex/auth.json"))
        diagnostics["codex_config_present"] = config_path.is_file()
        diagnostics["codex_auth_present"] = auth_path.is_file()

        config: dict[str, Any] = {}
        if config_path.is_file():
            try:
                config = parse_codex_config(config_path.read_text(encoding="utf-8"))
            except Exception:
                diagnostics["codex_config_parse_error"] = True

        auth: dict[str, Any] = {}
        if auth_path.is_file():
            try:
                parsed_auth = json.loads(auth_path.read_text(encoding="utf-8"))
                if isinstance(parsed_auth, dict):
                    auth = parsed_auth
            except Exception:
                diagnostics["codex_auth_parse_error"] = True

        # HIGH-2 fix: codex auth.json must take precedence over LLM_API_KEY when
        # OPENAI_API_KEY direct-env is unset. Order: direct env -> auth.json -> LLM_API_KEY.
        direct_env_key = os.environ.get(target_api_key_env, "").strip()
        auth_api_key_raw = auth.get("OPENAI_API_KEY")
        auth_api_key = auth_api_key_raw.strip() if isinstance(auth_api_key_raw, str) else ""

        if direct_env_key:
            runtime_env[target_api_key_env] = direct_env_key
            register_secret(direct_env_key)
            diagnostics["credential_source"] = "env:OPENAI_API_KEY"
        elif auth_api_key:
            runtime_env[target_api_key_env] = auth_api_key
            register_secret(auth_api_key)
            diagnostics["credential_source"] = "codex_auth_json"
        elif llm_api_key:
            runtime_env[target_api_key_env] = llm_api_key
            register_secret(llm_api_key)
            diagnostics["credential_source"] = "llm_api_key"

        # Codex config.toml model/provider/base_url pass-through (preserved verbatim)
        config_model = codex_config_value(config, "model")
        input_model = llm_block.get("model") if isinstance(llm_block.get("model"), str) else None
        if config_model or input_model:
            runtime_env.setdefault("ARGUS_AGENTFLOW_MODEL", (config_model or input_model or "").strip())
            diagnostics["model_source"] = "codex_config" if config_model else "runner_input"
        config_provider = codex_config_value(config, "model_provider")
        if config_provider:
            runtime_env.setdefault("ARGUS_AGENTFLOW_PROVIDER", config_provider)
        base_url_config = codex_config_value(config, "base_url")
        if base_url_config:
            runtime_env.setdefault("ARGUS_AGENTFLOW_BASE_URL", base_url_config)
            diagnostics["base_url_source"] = "codex_config"

        # T2.5: cross-provider key-shape WARN — openai-compatible with sk-ant- key
        if llm_api_key.startswith("sk-ant-"):
            warnings = diagnostics.setdefault("warnings", [])
            warnings.append(
                "OPENAI_API_KEY appears to be an Anthropic-shaped key (sk-ant- prefix); confirm LLM_API_KEY matches LLM_PROVIDER"
            )
    else:
        # New path for claude / kimi / pi: use LLM_API_KEY directly.
        if llm_api_key:
            runtime_env[target_api_key_env] = llm_api_key
            register_secret(llm_api_key)
            diagnostics["credential_source"] = "llm_api_key"
            # CRITICAL-1 fix: vendor's KimiAdapter reads KIMI_API_KEY; resolve_provider
            # returns name="moonshot". Write BOTH env vars so whichever the kimi binary
            # or its underlying API client (Moonshot) reads is set.
            if provider == "kimi_compatible":
                runtime_env["MOONSHOT_API_KEY"] = llm_api_key
            # T2.5: cross-provider key-shape WARN
            if provider == "anthropic_compatible" and not llm_api_key.startswith("sk-ant-"):
                warnings = diagnostics.setdefault("warnings", [])
                warnings.append(
                    "ANTHROPIC_API_KEY may be a non-Anthropic key shape (expected 'sk-ant-' prefix); confirm LLM_API_KEY matches LLM_PROVIDER"
                )
            # kimi/pi key shapes vary by vendor; skip the heuristic check intentionally (Plan T2.5).
        else:
            diagnostics["credential_source"] = "missing"

    # MEDIUM-5 fix: propagate LLM_BASE_URL to the dispatched provider's base_url env var
    # so the vendor agent (kimi reads KIMI_BASE_URL, claude reads ANTHROPIC_BASE_URL,
    # etc.) sees the operator's configured endpoint rather than its baked-in default.
    llm_base_url = (
        os.environ.get("LLM_BASE_URL", "").strip()
        or (llm_block.get("base_url") if isinstance(llm_block.get("base_url"), str) else "").strip()
    )
    target_base_url_env = dispatch.get("base_url_env")
    if llm_base_url and target_base_url_env:
        runtime_env[target_base_url_env] = llm_base_url

    # Pass-through env: ARGUS_AGENTFLOW_PROVIDER / _MODEL / _BASE_URL / _AGENT
    runtime_env.setdefault("ARGUS_AGENTFLOW_PROVIDER", provider)
    runtime_env["ARGUS_AGENTFLOW_AGENT"] = dispatch["agent_kind"]
    if llm_block.get("model") and "ARGUS_AGENTFLOW_MODEL" not in runtime_env:
        runtime_env["ARGUS_AGENTFLOW_MODEL"] = llm_block["model"]
    if llm_block.get("base_url") and "ARGUS_AGENTFLOW_BASE_URL" not in runtime_env:
        runtime_env["ARGUS_AGENTFLOW_BASE_URL"] = llm_block["base_url"]

    return runtime_env, diagnostics

def load_stdin_input() -> tuple[dict[str, Any], str]:
    raw = sys.stdin.read()
    if not raw.strip():
        payload: dict[str, Any] = {}
        raw = "{}"
    else:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            payload = {"task_id": "unknown", "_input_error": str(exc)}
    return payload, raw


def write_runner_input(raw: str, task_segment: str) -> None:
    input_path = Path(os.environ.get("ARGUS_AGENTFLOW_INPUT_PATH", DEFAULT_INPUT_PATH))
    input_path = input_path.parent / task_segment / input_path.name
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_text(raw, encoding="utf-8")


def task_id_from(payload: dict[str, Any]) -> str:
    value = payload.get("task_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "unknown"


def safe_path_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._-")
    return segment or "unknown"


def input_digest_from(payload: dict[str, Any]) -> str | None:
    value = payload.get("metadata", {}).get("input_digest") if isinstance(payload.get("metadata"), dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def run_id_from(native_record: dict[str, Any] | None, task_id: str) -> str:
    if native_record:
        value = native_record.get("id") or native_record.get("run_id")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"agentflow-{task_id}-{int(datetime.now(timezone.utc).timestamp())}"


def role_for_node(node_id: str | None) -> str:
    if not node_id:
        return "runner"
    return ROLE_BY_NODE.get(node_id, node_id)


def make_event(
    *,
    run_id: str,
    sequence: int,
    event_type: str,
    message: str,
    role: str = "runner",
    node_id: str | None = None,
    visibility: str = "user",
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{run_id}-{sequence}-{event_type}",
        "sequence": sequence,
        "timestamp": now_rfc3339(),
        "event_type": event_type,
        "role": role,
        "visibility": visibility,
        "correlation_id": run_id,
        "topology_version": TOPOLOGY_VERSION,
        "node_id": node_id,
        "message": message,
        "data": data or {},
    }


def make_checkpoint(
    *,
    run_id: str,
    node_id: str,
    status: str,
    checkpoint_type: str,
    findings_count: int = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    role = role_for_node(node_id)
    return {
        "id": f"{run_id}-{node_id}-{checkpoint_type}",
        "agent_id": node_id,
        "agent_name": node_id,
        "agent_type": "agentflow",
        "role": role,
        "status": status,
        "checkpoint_type": checkpoint_type,
        "topology_version": TOPOLOGY_VERSION,
        "parent_agent_id": None,
        "iteration": 1,
        "total_tokens": 0,
        "tool_calls": 0,
        "findings_count": findings_count,
        "created_at": now_rfc3339(),
        "state_data": {},
        "metadata": metadata or {},
    }


def _truncate_output(value: Any, max_bytes: int = 2048) -> str:
    text = str(value) if value is not None else ""
    return text[:max_bytes]


_current_thinking_node: str | None = None


def emit_stream_event(
    *,
    event_type: str,
    node_id: str | None = None,
    role: str = "runner",
    sequence: int,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> None:
    event: dict[str, Any] = {
        "stream": True,
        "type": event_type,
        "node_id": node_id,
        "role": role or role_for_node(node_id),
        "sequence": sequence,
        "timestamp": now_rfc3339(),
        "message": message,
    }
    if data:
        event.update(data)
    print(json.dumps(event, ensure_ascii=False), flush=True)


def parse_agentflow_trace_line(line: str) -> list[dict[str, Any]]:
    global _current_thinking_node
    stripped = line.strip()
    if not stripped:
        return []
    try:
        data = json.loads(stripped)
        if not isinstance(data, dict):
            return []
        kind = data.get("type") or data.get("kind") or ""
        node_id = data.get("node_id")
        role = data.get("role")

        if kind in ("assistant_delta", "thinking_delta"):
            events: list[dict[str, Any]] = []
            if node_id != _current_thinking_node:
                _current_thinking_node = node_id
                events.append({"type": "thinking_start", "node_id": node_id, "role": role})
            events.append({"type": "thinking_token", "token": data.get("content", ""), "node_id": node_id, "role": role})
            return events
        if kind in ("assistant_message", "thinking_complete"):
            _current_thinking_node = None
            return [{"type": "thinking_end", "accumulated": data.get("content", ""), "node_id": node_id, "role": role}]
        if kind == "tool_call":
            return [{"type": "tool_call", "tool_name": data.get("name", ""), "tool_input": data.get("input", {}), "node_id": node_id, "role": role}]
        if kind in ("command_output", "tool_result"):
            return [{"type": "tool_result", "tool_name": data.get("name", ""), "tool_output": _truncate_output(data.get("output", "")), "tool_duration_ms": data.get("duration_ms"), "node_id": node_id, "role": role}]
        if kind == "item_started":
            return [{"type": "node_start", "node_id": node_id, "role": role}]
        if kind == "item_completed":
            return [{"type": "node_end", "node_id": node_id, "role": role, "status": data.get("status", "completed")}]
        if len(stripped) > 10:
            return [{"type": "info", "message": stripped[:500]}]
        return []
    except json.JSONDecodeError:
        if len(stripped) > 10:
            return [{"type": "info", "message": stripped[:500]}]
        return []


def make_agent_tree(native_record: dict[str, Any] | None, fallback_status: str) -> list[dict[str, Any]]:
    nodes = native_record.get("nodes", {}) if native_record else {}
    if not isinstance(nodes, dict) or not nodes:
        return [
            {
                "id": "agentflow-runner",
                "role": "runner",
                "label": "AgentFlow Runner",
                "status": fallback_status,
                "topology_version": TOPOLOGY_VERSION,
                "parent_id": None,
                "duration_ms": None,
                "findings_count": 0,
                "metadata": {},
            }
        ]
    tree: list[dict[str, Any]] = []
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            node = {}
        status = str(node.get("status") or fallback_status)
        tree.append(
            {
                "id": node_id,
                "role": role_for_node(node_id),
                "label": node_id,
                "status": status if status in {"pending", "running", "completed", "failed", "cancelled"} else fallback_status,
                "topology_version": TOPOLOGY_VERSION,
                "parent_id": None,
                "duration_ms": None,
                "findings_count": 0,
                "metadata": {
                    "exit_code": node.get("exit_code"),
                    "attempts": node.get("current_attempt") or len(node.get("attempts") or []),
                },
            }
        )
    return tree


def failure_contract(
    *,
    task_id: str,
    run_id: str,
    reason_code: str,
    message: str,
    native_record: dict[str, Any] | None = None,
    runner_exit_code: int | None = None,
    stdout_tail: str = "",
    stderr_tail: str = "",
    input_digest: str | None = None,
    credential_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    credential_diagnostics = credential_diagnostics or {}
    return {
        "contract_version": CONTRACT_VERSION,
        "task_id": task_id,
        "run": {
            "run_id": run_id,
            "status": "failed",
            "topology_version": TOPOLOGY_VERSION,
            "started_at": native_record.get("started_at") if native_record else None,
            "finished_at": native_record.get("finished_at") if native_record else None,
            "input_digest": input_digest,
        },
        "events": [
            make_event(
                run_id=run_id,
                sequence=1,
                event_type=reason_code,
                message=message,
                data={"reason_code": reason_code},
            )
        ],
        "checkpoints": [
            make_checkpoint(
                run_id=run_id,
                node_id="agentflow-runner",
                status="failed",
                checkpoint_type=reason_code,
                metadata={"reason_code": reason_code},
            )
        ],
        "findings": [],
        "report": {
            "title": "AgentFlow 智能审计失败",
            "summary": message,
            "markdown": f"# AgentFlow 智能审计失败\n\n{message}",
            "verified_count": 0,
            "findings_count": 0,
            "severity_counts": {},
            "diagnostics": {"reason_code": reason_code},
            "statistics": {"findings_count": 0, "verified_count": 0},
            "timeline": [],
            "artifact_index": [],
        },
        "agent_tree": make_agent_tree(native_record, "failed"),
        "artifacts": [],
        "artifact_index": [],
        "feedback_bundle": None,
        "diagnostics": {
            "runner_exit_code": runner_exit_code,
            "stdout_tail": redact_text(stdout_tail),
            "stderr_tail": redact_text(stderr_tail),
            "reason_code": reason_code,
            "message": message,
            "credential_diagnostics": credential_diagnostics,
            "resource_diagnostics": {"max_concurrency": None, "queued": False},
            "dynamic_expert_diagnostics": {"enabled": False, "reason": "disabled_in_p1"},
            "dynamic_experts_enabled": False,
            "remote_target_enabled": False,
            "agentflow_serve_enabled": False,
        },
    }


def run_command(
    args: list[str],
    *,
    output_path: Path | None = None,
    env_overlay: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overlay:
        env.update(env_overlay)
    result = subprocess.run(args, text=True, capture_output=True, check=False, env=env)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(redact_text(result.stdout), encoding="utf-8")
    return result


def parse_json(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def iter_node_text(native_record: dict[str, Any]) -> list[tuple[str, str]]:
    nodes = native_record.get("nodes")
    if not isinstance(nodes, dict):
        return []
    ordered_ids = ["audit-reporter", "vuln-reasoner", "env-inter"]
    ordered_ids.extend(node_id for node_id in nodes.keys() if node_id not in ordered_ids)
    texts: list[tuple[str, str]] = []
    for node_id in ordered_ids:
        node = nodes.get(node_id)
        if not isinstance(node, dict):
            continue
        for field in ("final_response", "output"):
            value = node.get(field)
            if isinstance(value, str) and value.strip():
                texts.append((node_id, value))
    return texts


def extract_argus_contract(native_record: dict[str, Any]) -> dict[str, Any] | None:
    if native_record.get("contract_version") in SUPPORTED_CONTRACT_VERSIONS:
        return native_record
    for _, text in iter_node_text(native_record):
        parsed = parse_json(text)
        if isinstance(parsed, dict) and parsed.get("contract_version") in SUPPORTED_CONTRACT_VERSIONS:
            return parsed
    return None


def normalize_visibility(value: Any) -> str:
    normalized = str(value or "user").strip().upper()
    if normalized in {"USER", "ALL", ""}:
        return "user"
    if normalized in {"DIAGNOSTIC", "ORCHESTRATOR_ONLY"}:
        return "diagnostic"
    if normalized in {"INTERNAL", "AGENTS_ONLY"}:
        return "internal"
    return "diagnostic"


def normalize_event_envelopes(events: Any, topology_version: str) -> list[dict[str, Any]]:
    normalized_events: list[dict[str, Any]] = []
    if not isinstance(events, list):
        return normalized_events
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        event = dict(event)
        event.setdefault("id", f"event-{index + 1}")
        event.setdefault("sequence", index + 1)
        event.setdefault("timestamp", now_rfc3339())
        event.setdefault("event_type", event.get("type") or "agentflow_event")
        event.setdefault("role", "runner")
        raw_visibility = event.get("visibility")
        event["visibility"] = normalize_visibility(raw_visibility)
        event.setdefault("correlation_id", event.get("id") or f"event-{index + 1}")
        event.setdefault("topology_version", topology_version)
        data = event.setdefault("data", {})
        if isinstance(data, dict) and raw_visibility is not None:
            data.setdefault("agentflow_visibility", raw_visibility)
        normalized_events.append(event)
    return normalized_events


def normalize_topology_collection(items: Any, topology_version: str) -> list[dict[str, Any]]:
    normalized_items: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return normalized_items
    for item in items:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        copied.setdefault("topology_version", topology_version)
        normalized_items.append(copied)
    return normalized_items


def normalize_contract(
    contract: dict[str, Any],
    *,
    task_id: str,
    native_record: dict[str, Any],
    input_digest: str | None,
    stdout_tail: str,
    stderr_tail: str,
    credential_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = run_id_from(native_record, task_id)
    original_contract_version = str(contract.get("contract_version") or CONTRACT_VERSION)
    contract["contract_version"] = CONTRACT_VERSION
    contract["task_id"] = str(contract.get("task_id") or task_id)
    run = contract.setdefault("run", {})
    if isinstance(run, dict):
        run["run_id"] = str(run.get("run_id") or run_id)
        run["status"] = str(run.get("status") or native_record.get("status") or "completed")
        run["topology_version"] = str(run.get("topology_version") or TOPOLOGY_VERSION)
        run.setdefault("started_at", native_record.get("started_at"))
        run.setdefault("finished_at", native_record.get("finished_at"))
        run.setdefault("input_digest", input_digest)
        run.setdefault("topology_change", None)
        topology_version = str(run.get("topology_version") or TOPOLOGY_VERSION)
    else:
        topology_version = TOPOLOGY_VERSION
        contract["run"] = {
            "run_id": run_id,
            "status": str(native_record.get("status") or "completed"),
            "topology_version": topology_version,
            "started_at": native_record.get("started_at"),
            "finished_at": native_record.get("finished_at"),
            "input_digest": input_digest,
            "topology_change": None,
        }
    contract["events"] = normalize_event_envelopes(contract.get("events"), topology_version)
    contract["checkpoints"] = normalize_topology_collection(contract.get("checkpoints"), topology_version)
    contract.setdefault("findings", [])
    report = contract.setdefault(
        "report",
        {},
    )
    if isinstance(report, dict):
        report.setdefault("title", "AgentFlow 智能审计报告")
        report.setdefault("summary", "AgentFlow 已返回 Argus P1 业务输出。")
        report.setdefault("markdown", None)
        report.setdefault("verified_count", 0)
        report.setdefault("findings_count", len(contract.get("findings") or []))
        report.setdefault("severity_counts", {})
        report.setdefault("diagnostics", {})
        report.setdefault("sections", [])
        report.setdefault("statistics", {"findings_count": len(contract.get("findings") or [])})
        report.setdefault("discard_summary", {})
        report.setdefault("timeline", [])
        report.setdefault("artifact_index", [])
    else:
        contract["report"] = {
            "title": "AgentFlow 智能审计报告",
            "summary": "AgentFlow 已返回 Argus P1 业务输出。",
            "markdown": None,
            "verified_count": 0,
            "findings_count": len(contract.get("findings") or []),
            "severity_counts": {},
            "diagnostics": {},
            "sections": [],
            "statistics": {"findings_count": len(contract.get("findings") or [])},
            "discard_summary": {},
            "timeline": [],
            "artifact_index": [],
        }
    contract["agent_tree"] = normalize_topology_collection(
        contract.get("agent_tree") or make_agent_tree(native_record, str(contract["run"].get("status") or "completed")),
        topology_version,
    )
    artifacts = contract.setdefault("artifacts", [])
    contract.setdefault("artifact_index", artifacts)
    contract.setdefault("feedback_bundle", None)
    diagnostics = contract.setdefault("diagnostics", {})
    if isinstance(diagnostics, dict):
        diagnostics.setdefault("compatibility", {})
        if isinstance(diagnostics["compatibility"], dict):
            diagnostics["compatibility"].setdefault("original_contract_version", original_contract_version)
            diagnostics["compatibility"].setdefault("normalized_contract_version", CONTRACT_VERSION)
        diagnostics.setdefault("credential_diagnostics", credential_diagnostics or {})
        diagnostics.setdefault("runner_exit_code", 0)
        diagnostics.setdefault("stdout_tail", redact_text(stdout_tail))
        diagnostics.setdefault("stderr_tail", redact_text(stderr_tail))
        diagnostics.setdefault("reason_code", None)
        diagnostics.setdefault("message", None)
        diagnostics.setdefault("resource_diagnostics", {"max_concurrency": None, "queued": False})
        diagnostics.setdefault("dynamic_expert_diagnostics", {"enabled": False, "reason": "disabled_in_p1"})
        diagnostics.setdefault("dynamic_experts_enabled", False)
        diagnostics.setdefault("remote_target_enabled", False)
        diagnostics.setdefault("agentflow_serve_enabled", False)
    return contract


def main() -> int:
    pipeline_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PIPELINE
    extra_args = sys.argv[2:] if len(sys.argv) > 2 else []
    runner_input, raw_input = load_stdin_input()
    task_id = task_id_from(runner_input)
    task_segment = safe_path_segment(task_id)
    runtime_env, credential_diagnostics = load_provider_runtime_env(runner_input)
    output_dir = Path(os.environ.get("ARGUS_AGENTFLOW_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)) / task_segment
    runs_dir = str(Path(os.environ.get("AGENTFLOW_RUNS_DIR", DEFAULT_RUNS_DIR)) / task_segment)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_runner_input(raw_input, task_segment)
    input_digest = input_digest_from(runner_input)

    validate_result = run_command(
        ["agentflow", "validate", pipeline_path],
        output_path=output_dir / "pipeline.validate.json",
        env_overlay=runtime_env,
    )
    if validate_result.returncode != 0:
        contract = failure_contract(
            task_id=task_id,
            run_id=run_id_from(None, task_id),
            reason_code="pipeline_invalid",
            message="AgentFlow pipeline validate 失败",
            runner_exit_code=validate_result.returncode,
            stdout_tail=validate_result.stdout,
            stderr_tail=validate_result.stderr,
            input_digest=input_digest,
            credential_diagnostics=credential_diagnostics,
        )
        print(json.dumps(contract, ensure_ascii=False))
        return 0

    # --- Streaming execution (replaces batch subprocess.run) ---
    agentflow_args = ["agentflow", "run", pipeline_path, "--runs-dir", runs_dir, "--output", "json", *extra_args]
    run_env = os.environ.copy()
    run_env["PYTHONUNBUFFERED"] = "1"
    if runtime_env:
        run_env.update(runtime_env)

    sequence_counter = 0
    collected_stdout_lines: list[str] = []

    def next_seq() -> int:
        nonlocal sequence_counter
        sequence_counter += 1
        return sequence_counter

    emit_stream_event(event_type="node_start", node_id="agentflow-runner", role="runner", sequence=next_seq(), message="AgentFlow runner starting")

    try:
        proc = subprocess.Popen(
            agentflow_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=run_env,
        )
    except OSError as exc:
        contract = failure_contract(
            task_id=task_id,
            run_id=run_id_from(None, task_id),
            reason_code="runner_missing",
            message=f"AgentFlow runner 启动失败: {exc}",
            input_digest=input_digest,
            credential_diagnostics=credential_diagnostics,
        )
        print(json.dumps(contract, ensure_ascii=False))
        return 0

    assert proc.stdout is not None
    for raw_line in proc.stdout:
        line = raw_line.rstrip("\n\r")
        if not line:
            continue
        collected_stdout_lines.append(line)

        parsed_events = parse_agentflow_trace_line(line)
        for parsed in parsed_events:
            event_type = parsed.pop("type", "info")
            emit_stream_event(
                event_type=event_type,
                node_id=parsed.get("node_id"),
                role=parsed.get("role") or "runner",
                sequence=next_seq(),
                message=parsed.get("message", ""),
                data={k: v for k, v in parsed.items() if k not in ("node_id", "role", "message") and v is not None},
            )

    stderr_output = proc.stderr.read() if proc.stderr else ""
    proc.wait()
    run_exit_code = proc.returncode
    stdout_full = "\n".join(collected_stdout_lines)

    emit_stream_event(event_type="node_end", node_id="agentflow-runner", role="runner", sequence=next_seq(), message=f"AgentFlow runner finished (exit={run_exit_code})", data={"exit_code": run_exit_code})

    # Restore diagnostic file write (R2 Fix 4)
    diag_path = output_dir / "agentflow.run.json"
    diag_path.parent.mkdir(parents=True, exist_ok=True)
    diag_path.write_text(redact_text(stdout_full), encoding="utf-8")

    # Parse native record from collected stdout
    native_record = parse_json(stdout_full)
    if not isinstance(native_record, dict):
        contract = failure_contract(
            task_id=task_id,
            run_id=run_id_from(None, task_id),
            reason_code="runner_output_invalid",
            message="AgentFlow runner 未输出可解析的原生 JSON",
            runner_exit_code=run_exit_code,
            stdout_tail=stdout_full,
            stderr_tail=stderr_output,
            input_digest=input_digest,
            credential_diagnostics=credential_diagnostics,
        )
        print(json.dumps(contract, ensure_ascii=False))
        return 0

    run_id = run_id_from(native_record, task_id)
    if run_exit_code != 0:
        contract = failure_contract(
            task_id=task_id,
            run_id=run_id,
            reason_code="runner_failed",
            message="AgentFlow runner 返回非零退出码",
            native_record=native_record,
            runner_exit_code=run_exit_code,
            stdout_tail=stdout_full,
            stderr_tail=stderr_output,
            input_digest=input_digest,
            credential_diagnostics=credential_diagnostics,
        )
        print(json.dumps(contract, ensure_ascii=False))
        return 0

    contract = extract_argus_contract(native_record)
    if contract is None:
        contract = failure_contract(
            task_id=task_id,
            run_id=run_id,
            reason_code="runner_output_invalid",
            message="AgentFlow 报告节点未输出 Argus P1 JSON 合同",
            native_record=native_record,
            runner_exit_code=run_exit_code,
            stdout_tail=stdout_full,
            stderr_tail=stderr_output,
            input_digest=input_digest,
            credential_diagnostics=credential_diagnostics,
        )
        print(json.dumps(contract, ensure_ascii=False))
        return 0

    final_output = normalize_contract(
        contract,
        task_id=task_id,
        native_record=native_record,
        input_digest=input_digest,
        stdout_tail=stdout_full,
        stderr_tail=stderr_output,
        credential_diagnostics=credential_diagnostics,
    )

    # Contract safety net: write to file in case stdout line is missed (R2 Fix 8)
    contract_path = output_dir / "contract.json"
    contract_path.write_text(json.dumps(final_output, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(final_output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
