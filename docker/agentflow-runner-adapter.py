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

CONTRACT_VERSION = "argus-agentflow-p1/v1"
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
) -> dict[str, Any]:
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
        },
        "agent_tree": make_agent_tree(native_record, "failed"),
        "artifacts": [],
        "diagnostics": {
            "runner_exit_code": runner_exit_code,
            "stdout_tail": tail(stdout_tail),
            "stderr_tail": tail(stderr_tail),
            "reason_code": reason_code,
            "message": message,
        },
    }


def run_command(args: list[str], *, output_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result.stdout, encoding="utf-8")
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
    if native_record.get("contract_version") == CONTRACT_VERSION:
        return native_record
    for _, text in iter_node_text(native_record):
        parsed = parse_json(text)
        if isinstance(parsed, dict) and parsed.get("contract_version") == CONTRACT_VERSION:
            return parsed
    return None


def normalize_contract(
    contract: dict[str, Any],
    *,
    task_id: str,
    native_record: dict[str, Any],
    input_digest: str | None,
    stdout_tail: str,
    stderr_tail: str,
) -> dict[str, Any]:
    run_id = run_id_from(native_record, task_id)
    contract["contract_version"] = CONTRACT_VERSION
    contract["task_id"] = str(contract.get("task_id") or task_id)
    run = contract.setdefault("run", {})
    if isinstance(run, dict):
        run["run_id"] = str(run.get("run_id") or run_id)
        run["status"] = str(run.get("status") or native_record.get("status") or "completed")
        run["topology_version"] = TOPOLOGY_VERSION
        run.setdefault("started_at", native_record.get("started_at"))
        run.setdefault("finished_at", native_record.get("finished_at"))
        run.setdefault("input_digest", input_digest)
    contract.setdefault("events", [])
    contract.setdefault("checkpoints", [])
    contract.setdefault("findings", [])
    contract.setdefault(
        "report",
        {
            "title": "AgentFlow 智能审计报告",
            "summary": "AgentFlow 已返回 Argus P1 业务输出。",
            "markdown": None,
            "verified_count": 0,
            "findings_count": len(contract.get("findings") or []),
            "severity_counts": {},
            "diagnostics": {},
        },
    )
    contract.setdefault("agent_tree", make_agent_tree(native_record, str(run.get("status") or "completed")))
    contract.setdefault("artifacts", [])
    diagnostics = contract.setdefault("diagnostics", {})
    if isinstance(diagnostics, dict):
        diagnostics.setdefault("runner_exit_code", 0)
        diagnostics.setdefault("stdout_tail", tail(stdout_tail))
        diagnostics.setdefault("stderr_tail", tail(stderr_tail))
        diagnostics.setdefault("reason_code", None)
        diagnostics.setdefault("message", None)
    return contract


def main() -> int:
    pipeline_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PIPELINE
    extra_args = sys.argv[2:] if len(sys.argv) > 2 else []
    runner_input, raw_input = load_stdin_input()
    task_id = task_id_from(runner_input)
    task_segment = safe_path_segment(task_id)
    output_dir = Path(os.environ.get("ARGUS_AGENTFLOW_OUTPUT_DIR", DEFAULT_OUTPUT_DIR)) / task_segment
    runs_dir = str(Path(os.environ.get("AGENTFLOW_RUNS_DIR", DEFAULT_RUNS_DIR)) / task_segment)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_runner_input(raw_input, task_segment)
    input_digest = input_digest_from(runner_input)

    validate_result = run_command(
        ["agentflow", "validate", pipeline_path],
        output_path=output_dir / "pipeline.validate.json",
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
        )
        print(json.dumps(contract, ensure_ascii=False))
        return 0

    run_result = run_command(
        ["agentflow", "run", pipeline_path, "--runs-dir", runs_dir, "--output", "json", *extra_args],
        output_path=output_dir / "agentflow.run.json",
    )
    native_record = parse_json(run_result.stdout)
    if not isinstance(native_record, dict):
        contract = failure_contract(
            task_id=task_id,
            run_id=run_id_from(None, task_id),
            reason_code="runner_output_invalid",
            message="AgentFlow runner 未输出可解析的原生 JSON",
            runner_exit_code=run_result.returncode,
            stdout_tail=run_result.stdout,
            stderr_tail=run_result.stderr,
            input_digest=input_digest,
        )
        print(json.dumps(contract, ensure_ascii=False))
        return 0

    run_id = run_id_from(native_record, task_id)
    if run_result.returncode != 0:
        contract = failure_contract(
            task_id=task_id,
            run_id=run_id,
            reason_code="runner_failed",
            message="AgentFlow runner 返回非零退出码",
            native_record=native_record,
            runner_exit_code=run_result.returncode,
            stdout_tail=run_result.stdout,
            stderr_tail=run_result.stderr,
            input_digest=input_digest,
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
            runner_exit_code=run_result.returncode,
            stdout_tail=run_result.stdout,
            stderr_tail=run_result.stderr,
            input_digest=input_digest,
        )
        print(json.dumps(contract, ensure_ascii=False))
        return 0

    print(
        json.dumps(
            normalize_contract(
                contract,
                task_id=task_id,
                native_record=native_record,
                input_digest=input_digest,
                stdout_tail=run_result.stdout,
                stderr_tail=run_result.stderr,
            ),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
