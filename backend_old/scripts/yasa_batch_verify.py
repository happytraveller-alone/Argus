#!/usr/bin/env python3
"""YASA batch verification utility.

- Keep latest one running/pending YASA task for fastjson, interrupt the rest.
- Run YASA scans for local projects.
- For mixed-language projects, run each supported language once.
- Skip unsupported-language projects.
- Emit JSON and TSV reports.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SUPPORTED_ORDER = ["java", "golang", "python", "typescript", "javascript"]
ALIAS = {
    "java": "java",
    "kotlin": "java",
    "scala": "java",
    "go": "golang",
    "golang": "golang",
    "python": "python",
    "py": "python",
    "typescript": "typescript",
    "ts": "typescript",
    "javascript": "javascript",
    "js": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
}


def _req(base_url: str, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    url = f"{base_url.rstrip('/')}{path}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    last_error: Optional[Exception] = None
    for attempt in range(1, 6):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            if attempt >= 5:
                raise
            time.sleep(min(5 * attempt, 20))

    if last_error is not None:
        raise last_error
    raise RuntimeError("request failed without explicit error")




def _get(base_url: str, path: str) -> Any:
    return _req(base_url, "GET", path)


def _post(base_url: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    return _req(base_url, "POST", path, payload)


def _parse_languages(raw: Any) -> List[str]:
    if isinstance(raw, list):
        values = [str(item).strip().lower() for item in raw if str(item).strip()]
        return values
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip().lower() for item in parsed if str(item).strip()]
        except Exception:
            pass
        return [text.lower()]
    return []


def _resolve_supported_languages(raw: Any) -> List[str]:
    langs = _parse_languages(raw)
    mapped: List[str] = []
    for lang in langs:
        mapped_lang = ALIAS.get(lang)
        if mapped_lang and mapped_lang in SUPPORTED_ORDER and mapped_lang not in mapped:
            mapped.append(mapped_lang)
    return [lang for lang in SUPPORTED_ORDER if lang in mapped]


def _to_epoch(value: Optional[str]) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _short_error(text: Optional[str], limit: int = 280) -> Optional[str]:
    raw = str(text or "").strip()
    if not raw:
        return None
    one_line = raw.replace("\n", " | ")
    return one_line[:limit]


def _poll_task_terminal(base_url: str, task_id: str, wait_seconds: int) -> Dict[str, Any]:
    last: Dict[str, Any] = {}
    for _ in range(max(1, wait_seconds)):
        last = _get(base_url, f"/api/v1/static-tasks/yasa/tasks/{task_id}")
        status = str(last.get("status") or "").lower()
        if status in {"completed", "failed", "interrupted"}:
            return last
        time.sleep(1)
    if not last:
        last = _get(base_url, f"/api/v1/static-tasks/yasa/tasks/{task_id}")
    return last


def _cleanup_fastjson_concurrency(base_url: str) -> Dict[str, Any]:
    projects = _get(base_url, "/api/v1/projects/")
    fastjson = next((p for p in projects if str(p.get("name", "")).lower() == "fastjson"), None)
    if not fastjson:
        return {"project": None, "kept_task_id": None, "interrupted_task_ids": []}

    project_id = str(fastjson["id"])
    query = urllib.parse.urlencode({"project_id": project_id, "limit": 200})
    tasks = _get(base_url, f"/api/v1/static-tasks/yasa/tasks?{query}")
    running = [
        t
        for t in tasks
        if str(t.get("status") or "").lower() in {"running", "pending"}
    ]
    running.sort(key=lambda t: _to_epoch(t.get("created_at")), reverse=True)

    kept = running[0] if running else None
    interrupted: List[str] = []

    for task in running[1:]:
        task_id = str(task.get("id"))
        try:
            _post(base_url, f"/api/v1/static-tasks/yasa/tasks/{task_id}/interrupt", {})
            interrupted.append(task_id)
        except urllib.error.HTTPError:
            pass

    return {
        "project": "fastjson",
        "project_id": project_id,
        "kept_task_id": str(kept.get("id")) if kept else None,
        "interrupted_task_ids": interrupted,
    }


def _scan_language(base_url: str, project: Dict[str, Any], language: str, wait_seconds: int) -> Dict[str, Any]:
    project_id = str(project["id"])
    project_name = str(project.get("name") or project_id)
    task_name = f"batch-yasa-{project_name}-{language}"

    created = _post(
        base_url,
        "/api/v1/static-tasks/yasa/scan",
        {
            "project_id": project_id,
            "name": task_name,
            "target_path": ".",
            "language": language,
        },
    )
    task_id = str(created.get("id"))

    started = time.time()
    terminal = _poll_task_terminal(base_url, task_id, wait_seconds)
    wall_seconds = int(time.time() - started)
    status = str(terminal.get("status") or "")
    decision = "long_running" if status.lower() in {"running", "pending"} else "scanned"

    return {
        "project_id": project_id,
        "project_name": project_name,
        "programming_languages": project.get("programming_languages"),
        "language": language,
        "decision": decision,
        "task_id": task_id,
        "status": status,
        "wall_clock_seconds": wall_seconds,
        "scan_duration_ms": terminal.get("scan_duration_ms"),
        "total_findings": terminal.get("total_findings"),
        "files_scanned": terminal.get("files_scanned"),
        "error_summary": _short_error(terminal.get("error_message")),
        "diagnostics_summary": terminal.get("diagnostics_summary"),
        "created_at": terminal.get("created_at"),
        "updated_at": terminal.get("updated_at"),
    }


def _run(base_url: str, wait_seconds: int, out_json: str, out_tsv: str) -> int:
    cleanup = _cleanup_fastjson_concurrency(base_url)

    projects = _get(base_url, "/api/v1/projects/")
    rows: List[Dict[str, Any]] = []

    for project in projects:
        supported = _resolve_supported_languages(project.get("programming_languages"))
        if not supported:
            rows.append(
                {
                    "project_id": str(project.get("id")),
                    "project_name": str(project.get("name") or ""),
                    "programming_languages": project.get("programming_languages"),
                    "language": None,
                    "decision": "skipped_unsupported_language",
                    "task_id": None,
                    "status": "skipped",
                    "wall_clock_seconds": 0,
                    "scan_duration_ms": None,
                    "total_findings": None,
                    "files_scanned": None,
                    "error_summary": None,
                    "diagnostics_summary": None,
                    "created_at": None,
                    "updated_at": None,
                }
            )
            continue

        for language in supported:
            try:
                row = _scan_language(base_url, project, language, wait_seconds)
            except Exception as exc:  # noqa: BLE001
                row = {
                    "project_id": str(project.get("id")),
                    "project_name": str(project.get("name") or ""),
                    "programming_languages": project.get("programming_languages"),
                    "language": language,
                    "decision": "scanned",
                    "task_id": None,
                    "status": "failed",
                    "wall_clock_seconds": 0,
                    "scan_duration_ms": None,
                    "total_findings": None,
                    "files_scanned": None,
                    "error_summary": _short_error(str(exc), limit=400),
                    "diagnostics_summary": None,
                    "created_at": None,
                    "updated_at": None,
                }
            rows.append(row)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "cleanup": cleanup,
        "rows": rows,
    }

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)

    headers = [
        "project_id",
        "project_name",
        "programming_languages",
        "language",
        "decision",
        "task_id",
        "status",
        "wall_clock_seconds",
        "scan_duration_ms",
        "total_findings",
        "files_scanned",
        "error_summary",
    ]
    with open(out_tsv, "w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=headers, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in headers})

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run YASA batch verification across projects")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--wait-seconds", type=int, default=120)
    parser.add_argument("--out-json", default="/tmp/yasa_batch_verify_result_clean.json")
    parser.add_argument("--out-tsv", default="/tmp/yasa_batch_verify_result_clean.tsv")
    args = parser.parse_args()

    return _run(
        base_url=args.base_url,
        wait_seconds=max(1, args.wait_seconds),
        out_json=args.out_json,
        out_tsv=args.out_tsv,
    )


if __name__ == "__main__":
    sys.exit(main())
