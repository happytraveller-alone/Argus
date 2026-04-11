#!/usr/bin/env python3
"""Compare Python vs Rust API contracts for migrated endpoints."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}
DEFAULT_PARAM_VALUES = {
    "id": "1",
    "project_id": "1",
    "task_id": "1",
    "finding_id": "1",
    "rule_id": "1",
    "rule_set_id": "1",
    "rule_config_id": "1",
    "skill_id": "sample-skill",
    "template_id": "1",
    "member_id": "1",
    "user_id": "1",
    "prompt_skill_id": "1",
    "checkpoint_id": "1",
    "tool_type": "default",
    "tool_id": "1",
    "file_path": "README.md",
}


@dataclass(frozen=True)
class RouteCase:
    method: str
    path: str
    status: str


@dataclass
class ResponseSnapshot:
    status_code: int | None
    content_type: str
    body_kind: str
    shape: Any
    error: str | None


def normalize_path(path: str) -> str:
    value = re.sub(r"/{2,}", "/", path.strip())
    if not value.startswith("/"):
        value = "/" + value
    if value != "/" and value.endswith("/"):
        value = value[:-1]
    return value


def substitute_path_params(path: str, override: Dict[str, str]) -> str:
    pattern = re.compile(r"\{([a-zA-Z0-9_]+)(:[^}]*)?\}")

    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return override.get(key) or DEFAULT_PARAM_VALUES.get(key) or "1"

    return pattern.sub(_replace, path)


def load_cases(inventory_csv: Path, bucket: str, include_unsafe: bool) -> List[RouteCase]:
    cases: List[RouteCase] = []
    with inventory_csv.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            method = str(row.get("method", "")).upper()
            status = str(row.get("status", "")).strip().lower()
            path = normalize_path(str(row.get("path", "")))
            if not method or not path or status != bucket:
                continue
            if not include_unsafe and method not in READ_ONLY_METHODS:
                continue
            cases.append(RouteCase(method=method, path=path, status=status))
    deduped = sorted({(c.method, c.path, c.status) for c in cases}, key=lambda x: (x[1], x[0]))
    return [RouteCase(*item) for item in deduped]


def shape_of_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: shape_of_json(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        if not value:
            return []
        return [shape_of_json(value[0])]
    return type(value).__name__


def fetch(base_url: str, method: str, path: str, timeout: float) -> ResponseSnapshot:
    url = f"{base_url.rstrip('/')}{path}"
    req = Request(
        url=url,
        method=method,
        headers={"Accept": "application/json, text/plain, */*"},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None)
            content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            body_raw = resp.read()
            return parse_snapshot(status, content_type, body_raw, None)
    except HTTPError as exc:
        body_raw = exc.read() if exc.fp is not None else b""
        content_type = exc.headers.get("Content-Type", "").split(";")[0].strip().lower()
        return parse_snapshot(exc.code, content_type, body_raw, None)
    except URLError as exc:
        return ResponseSnapshot(
            status_code=None,
            content_type="",
            body_kind="error",
            shape=None,
            error=str(exc.reason),
        )
    except Exception as exc:
        return ResponseSnapshot(
            status_code=None,
            content_type="",
            body_kind="error",
            shape=None,
            error=str(exc),
        )


def parse_snapshot(status: int | None, content_type: str, body_raw: bytes, error: str | None) -> ResponseSnapshot:
    if error:
        return ResponseSnapshot(status_code=status, content_type=content_type, body_kind="error", shape=None, error=error)
    if not body_raw:
        return ResponseSnapshot(status_code=status, content_type=content_type, body_kind="empty", shape=None, error=None)

    text = body_raw.decode("utf-8", errors="replace")
    if "json" in content_type:
        try:
            payload = json.loads(text)
            return ResponseSnapshot(
                status_code=status,
                content_type=content_type,
                body_kind="json",
                shape=shape_of_json(payload),
                error=None,
            )
        except json.JSONDecodeError as exc:
            return ResponseSnapshot(
                status_code=status,
                content_type=content_type,
                body_kind="invalid-json",
                shape=text[:400],
                error=str(exc),
            )

    return ResponseSnapshot(
        status_code=status,
        content_type=content_type,
        body_kind="text",
        shape=text[:400],
        error=None,
    )


def compare_route(
    method: str,
    path: str,
    python_resp: ResponseSnapshot,
    rust_resp: ResponseSnapshot,
) -> Dict[str, Any]:
    diffs: List[str] = []
    if python_resp.error or rust_resp.error:
        diffs.append("request_error")
    if python_resp.status_code != rust_resp.status_code:
        diffs.append("status_mismatch")
    if python_resp.content_type != rust_resp.content_type:
        diffs.append("content_type_mismatch")
    if python_resp.body_kind != rust_resp.body_kind:
        diffs.append("body_kind_mismatch")
    if python_resp.body_kind == "json" and rust_resp.body_kind == "json" and python_resp.shape != rust_resp.shape:
        diffs.append("json_shape_mismatch")

    return {
        "method": method,
        "path": path,
        "ok": len(diffs) == 0,
        "diffs": diffs,
        "python": {
            "status_code": python_resp.status_code,
            "content_type": python_resp.content_type,
            "body_kind": python_resp.body_kind,
            "shape": python_resp.shape,
            "error": python_resp.error,
        },
        "rust": {
            "status_code": rust_resp.status_code,
            "content_type": rust_resp.content_type,
            "body_kind": rust_resp.body_kind,
            "shape": rust_resp.shape,
            "error": rust_resp.error,
        },
    }


def write_outputs(out_dir: Path, compared: Iterable[Dict[str, Any]], metadata: Dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"api-contract-diff-{timestamp}.json"
    md_path = out_dir / f"api-contract-diff-{timestamp}.md"

    compared_list = list(compared)
    counter = Counter()
    passed = 0
    for item in compared_list:
        if item["ok"]:
            passed += 1
        for diff in item["diffs"]:
            counter[diff] += 1

    payload = {
        "metadata": metadata,
        "summary": {
            "total": len(compared_list),
            "passed": passed,
            "failed": len(compared_list) - passed,
            "diff_type_counts": dict(counter),
        },
        "results": compared_list,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# API Contract Diff Result",
        "",
        f"- Compared: `{payload['summary']['total']}`",
        f"- Passed: `{payload['summary']['passed']}`",
        f"- Failed: `{payload['summary']['failed']}`",
        f"- Python base: `{metadata['python_base']}`",
        f"- Rust base: `{metadata['rust_base']}`",
        f"- Inventory: `{metadata['inventory']}`",
        "",
        "## Diff Types",
        "",
    ]
    if counter:
        for key in sorted(counter.keys()):
            lines.append(f"- `{key}`: `{counter[key]}`")
    else:
        lines.append("- none")

    lines.extend(["", "## Failed Routes", ""])
    failed = [item for item in compared_list if not item["ok"]]
    if failed:
        for item in failed:
            lines.append(f"- `{item['method']} {item['path']}` -> {', '.join(item['diffs'])}")
    else:
        lines.append("- none")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-base", required=True, help="Python backend base URL")
    parser.add_argument("--rust-base", required=True, help="Rust backend base URL")
    parser.add_argument(
        "--inventory",
        default="plan/wait_correct/route-inventory/python-endpoints-inventory.csv",
        help="Inventory CSV path",
    )
    parser.add_argument(
        "--bucket",
        default="migrate",
        choices=["migrate", "retire", "defer", "proxy"],
        help="Status bucket to compare",
    )
    parser.add_argument(
        "--out-dir",
        default="plan/wait_correct/api-contract",
        help="Directory for diff outputs",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Request timeout in seconds")
    parser.add_argument(
        "--include-unsafe-methods",
        action="store_true",
        help="Include non-read-only methods (POST/PUT/PATCH/DELETE)",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Query params in key=value format (repeatable)",
    )
    parser.add_argument(
        "--path-param",
        action="append",
        default=[],
        help="Path param override in name=value format (repeatable)",
    )
    return parser.parse_args()


def parse_kv(items: List[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for item in items:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def main() -> int:
    args = parse_args()
    repo_root = Path(".").resolve()
    inventory_path = (repo_root / args.inventory).resolve()
    out_dir = (repo_root / args.out_dir).resolve()

    cases = load_cases(
        inventory_csv=inventory_path,
        bucket=args.bucket,
        include_unsafe=args.include_unsafe_methods,
    )
    if not cases:
        print(f"No routes to compare from bucket={args.bucket}.")
        return 0

    query = parse_kv(args.query)
    path_param_override = parse_kv(args.path_param)

    compared: List[Dict[str, Any]] = []
    for case in cases:
        path = substitute_path_params(case.path, path_param_override)
        if query:
            path = f"{path}?{urlencode(query)}"
        py_resp = fetch(args.python_base, case.method, path, args.timeout)
        rs_resp = fetch(args.rust_base, case.method, path, args.timeout)
        compared.append(compare_route(case.method, path, py_resp, rs_resp))

    metadata = {
        "python_base": args.python_base,
        "rust_base": args.rust_base,
        "inventory": str(inventory_path),
        "bucket": args.bucket,
        "include_unsafe_methods": bool(args.include_unsafe_methods),
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
    json_path, md_path = write_outputs(out_dir, compared, metadata)
    print(f"Wrote diff JSON: {json_path}")
    print(f"Wrote diff summary: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
