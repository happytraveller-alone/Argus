import asyncio
import docker
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.v1.endpoints.static_tasks_shared import (
    _launch_static_background_job,
    _clear_scan_task_cancel,
    copy_project_tree_to_scan_dir,
    _force_cleanup_yasa_processes,
    _get_project_root,
    _is_scan_task_cancelled,
    _pop_scan_container,
    _register_scan_container,
    _release_request_db_session,
    _request_scan_task_cancel,
    _stop_scan_container,
    _sync_task_scan_duration,
    async_session_factory,
    cleanup_scan_workspace,
    deps,
    ensure_scan_logs_dir,
    ensure_scan_meta_dir,
    ensure_scan_output_dir,
    ensure_scan_project_dir,
    ensure_scan_workspace,
    get_db,
    logger,
    settings,
)
from app.models.project import Project
from app.models.user import User
from app.models.yasa import YasaFinding, YasaRuleConfig, YasaScanTask
from app.services.project_metrics import project_metrics_refresher
from app.services.scanner_runner import ScannerRunSpec, run_scanner_container
from app.services.yasa_runtime import (
    YASA_RUNNER_BINARY,
    YASA_RUNNER_RESOURCE_DIR,
    build_yasa_rule_config_path,
    build_yasa_scan_command,
)
from app.services.yasa_runtime_config import (
    load_global_yasa_runtime_config,
    save_global_yasa_runtime_config,
)
from app.services.yasa_rules_snapshot import (
    extract_yasa_snapshot_rules,
    load_yasa_checker_catalog,
)
from app.services.yasa_language import (
    YASA_SUPPORTED_LANGUAGES,
    is_yasa_blocked_project_language,
    resolve_yasa_language_from_programming_languages,
    resolve_yasa_language_profile,
)

router = APIRouter()


class YasaScanTaskCreate(BaseModel):
    project_id: str = Field(..., description="项目ID")
    name: Optional[str] = Field(None, description="任务名称")
    target_path: str = Field(".", description="扫描目标路径，相对于项目根目录")
    language: Optional[str] = Field(None, description="扫描语言，可自动识别映射")
    checker_pack_ids: Optional[List[str]] = Field(None, description="checkerPackIds")
    checker_ids: Optional[List[str]] = Field(None, description="checkerIds")
    rule_config_file: Optional[str] = Field(None, description="自定义 rule config 文件路径")
    rule_config_id: Optional[str] = Field(None, description="自定义规则配置ID")


class YasaScanTaskResponse(BaseModel):
    id: str
    project_id: str
    name: str
    status: str
    target_path: str
    language: str
    checker_pack_ids: Optional[str]
    checker_ids: Optional[str]
    rule_config_file: Optional[str]
    rule_config_id: Optional[str]
    rule_config_name: Optional[str]
    rule_config_source: Optional[str]
    total_findings: int
    scan_duration_ms: int
    files_scanned: int
    diagnostics_summary: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class YasaFindingResponse(BaseModel):
    id: str
    scan_task_id: str
    rule_id: Optional[str]
    rule_name: Optional[str]
    level: str
    message: str
    file_path: str
    start_line: Optional[int]
    end_line: Optional[int]
    status: str

    model_config = ConfigDict(from_attributes=True)


class YasaRuleResponse(BaseModel):
    checker_id: str
    checker_path: Optional[str] = None
    description: Optional[str] = None
    checker_packs: List[str] = []
    languages: List[str] = []
    demo_rule_config_path: Optional[str] = None
    source: str = "builtin"


class YasaRuleConfigResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    language: str
    checker_pack_ids: Optional[str]
    checker_ids: str
    rule_config_json: str
    is_active: bool
    source: str
    created_by: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class YasaRuleConfigUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None
    checker_pack_ids: Optional[List[str]] = None
    checker_ids: Optional[List[str]] = None
    is_active: Optional[bool] = None


class YasaRuntimeConfigResponse(BaseModel):
    yasa_timeout_seconds: int
    yasa_orphan_stale_seconds: int
    yasa_exec_heartbeat_seconds: int
    yasa_process_kill_grace_seconds: int


class YasaRuntimeConfigUpdateRequest(BaseModel):
    yasa_timeout_seconds: int = Field(..., ge=30, le=86400)
    yasa_orphan_stale_seconds: int = Field(..., ge=30, le=86400)
    yasa_exec_heartbeat_seconds: int = Field(..., ge=1, le=3600)
    yasa_process_kill_grace_seconds: int = Field(..., ge=1, le=60)

    model_config = ConfigDict(extra="ignore")


def _build_yasa_scan_task_response(task: YasaScanTask) -> YasaScanTaskResponse:
    return YasaScanTaskResponse(
        id=str(task.id),
        project_id=str(task.project_id),
        name=str(task.name or ""),
        status=str(task.status or "pending"),
        target_path=str(task.target_path or "."),
        language=str(task.language or ""),
        checker_pack_ids=task.checker_pack_ids,
        checker_ids=task.checker_ids,
        rule_config_file=task.rule_config_file,
        rule_config_id=task.rule_config_id,
        rule_config_name=task.rule_config_name,
        rule_config_source=task.rule_config_source,
        total_findings=int(task.total_findings or 0),
        scan_duration_ms=int(task.scan_duration_ms or 0),
        files_scanned=int(task.files_scanned or 0),
        diagnostics_summary=task.diagnostics_summary,
        error_message=task.error_message,
        created_at=task.created_at or datetime.now(),
        updated_at=task.updated_at,
    )


_SUPPORTED_YASA_LANGUAGES = YASA_SUPPORTED_LANGUAGES


def _normalize_csv(values: Optional[List[str]]) -> Optional[str]:
    if not values:
        return None
    normalized = [str(item).strip() for item in values if str(item).strip()]
    if not normalized:
        return None
    return ",".join(normalized)


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _split_csv_form(value: Optional[str]) -> List[str]:
    return _split_csv(value)


def _resolve_language_profile(language: Optional[str]) -> Dict[str, str]:
    return resolve_yasa_language_profile(language)


def _detect_language_from_project(project: Project) -> Optional[str]:
    return resolve_yasa_language_from_programming_languages(
        getattr(project, "programming_languages", None)
    )


def _assert_yasa_project_language_supported(project: Project) -> None:
    if is_yasa_blocked_project_language(getattr(project, "programming_languages", None)):
        raise HTTPException(
            status_code=400,
            detail="YASA 引擎仅支持 Java / Go / TypeScript / Python 项目",
        )


def _resolve_yasa_binary() -> str:
    configured = str(getattr(settings, "YASA_BIN_PATH", "yasa") or "yasa").strip()
    if not configured:
        configured = "yasa"

    if os.path.isabs(configured):
        if os.path.exists(configured) and os.access(configured, os.X_OK):
            return configured
        raise FileNotFoundError(f"yasa executable not found: {configured}")

    resolved = shutil.which(configured)
    if resolved:
        return resolved
    raise FileNotFoundError(
        f"无法找到 yasa 可执行文件，请确认 YASA_BIN_PATH 配置（当前: {configured}）"
    )


def _load_yasa_snapshot_rules_or_http_error() -> List[Dict[str, Any]]:
    try:
        return extract_yasa_snapshot_rules()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _load_yasa_checker_catalog_or_http_error() -> Dict[str, Any]:
    try:
        return load_yasa_checker_catalog()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _build_default_rule_config_path(profile: Dict[str, str]) -> Optional[str]:
    try:
        return build_yasa_rule_config_path(
            profile["rule_config"],
            resource_dir=YASA_RUNNER_RESOURCE_DIR,
        )
    except Exception:
        return None


def _parse_rule_config_checker_ids(rule_config_payload: Any) -> List[str]:
    collected: List[str] = []

    def _collect_from_entry(entry: Any) -> None:
        if not isinstance(entry, dict):
            return
        raw_checker_ids = entry.get("checkerIds")
        if not isinstance(raw_checker_ids, list):
            return
        for raw in raw_checker_ids:
            checker_id = str(raw or "").strip()
            if checker_id:
                collected.append(checker_id)

    if isinstance(rule_config_payload, dict):
        _collect_from_entry(rule_config_payload)
        rules = rule_config_payload.get("rules")
        if isinstance(rules, list):
            for item in rules:
                _collect_from_entry(item)
    elif isinstance(rule_config_payload, list):
        for item in rule_config_payload:
            _collect_from_entry(item)

    seen: set[str] = set()
    deduplicated: List[str] = []
    for item in collected:
        if item in seen:
            continue
        seen.add(item)
        deduplicated.append(item)
    return deduplicated


def _normalize_checker_values(values: Optional[List[str]]) -> List[str]:
    if not values:
        return []
    normalized: List[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _validate_checker_bindings(
    *,
    checker_ids: List[str],
    checker_pack_ids: List[str],
    catalog: Dict[str, Any],
) -> None:
    unknown_checker_ids = [
        checker_id for checker_id in checker_ids if checker_id not in catalog["checker_ids"]
    ]
    if unknown_checker_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "未知 checkerIds: "
                + ",".join(unknown_checker_ids)
                + "（区分大小写，请与 checker-config.json 保持一致）"
            ),
        )

    unknown_checker_pack_ids = [
        checker_pack_id
        for checker_pack_id in checker_pack_ids
        if checker_pack_id not in catalog["checker_pack_ids"]
    ]
    if unknown_checker_pack_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "未知 checkerPackIds: "
                + ",".join(unknown_checker_pack_ids)
                + "（区分大小写，请与 checker-pack-config.json 保持一致）"
            ),
        )



def _extract_sarif_location(result_item: Dict[str, Any]) -> Dict[str, Any]:
    locations = result_item.get("locations")
    if not isinstance(locations, list) or not locations:
        return {}
    first_location = locations[0]
    if not isinstance(first_location, dict):
        return {}
    physical = first_location.get("physicalLocation")
    if not isinstance(physical, dict):
        return {}
    artifact = physical.get("artifactLocation")
    region = physical.get("region")
    file_path = ""
    if isinstance(artifact, dict):
        file_path = str(artifact.get("uri") or "").strip()
    start_line = None
    end_line = None
    if isinstance(region, dict):
        if isinstance(region.get("startLine"), int):
            start_line = int(region.get("startLine"))
        if isinstance(region.get("endLine"), int):
            end_line = int(region.get("endLine"))
    return {
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
    }


def _parse_yasa_sarif_output(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    runs = payload.get("runs")
    if not isinstance(runs, list):
        return []

    findings: List[Dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        results = run.get("results")
        if not isinstance(results, list):
            continue
        for result_item in results:
            if not isinstance(result_item, dict):
                continue

            message_payload = result_item.get("message")
            message = ""
            if isinstance(message_payload, dict):
                message = str(message_payload.get("text") or "").strip()
            rule_id = str(result_item.get("ruleId") or "").strip() or None
            rule_name = str(result_item.get("rule") or "").strip() or rule_id
            level = str(result_item.get("level") or "warning").strip().lower() or "warning"

            location_info = _extract_sarif_location(result_item)
            file_path = str(location_info.get("file_path") or "").strip() or "unknown"

            findings.append(
                {
                    "rule_id": rule_id,
                    "rule_name": rule_name,
                    "level": level,
                    "message": message or (rule_id or "yasa finding"),
                    "file_path": file_path,
                    "start_line": location_info.get("start_line"),
                    "end_line": location_info.get("end_line"),
                    "raw_payload": json.dumps(result_item, ensure_ascii=False)[:15000],
                }
            )

    return findings


def _read_diagnostics_summary(report_dir: str) -> Optional[str]:
    diagnostics_path = Path(report_dir) / "yasa-diagnostics-log.txt"
    if not diagnostics_path.exists():
        return None
    try:
        content = diagnostics_path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return None
    if not content:
        return None
    return content[:3000]

def _truncate_diag_text(text: str, head: int = 4096, tail: int = 4096) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    if len(raw) <= head + tail:
        return raw
    return f"{raw[:head]}\n...<TRUNCATED>...\n{raw[-tail:]}"


def _build_failure_diagnostics_summary(
    *,
    language: str,
    checker_packs: List[str],
    rule_config_file: Optional[str],
    source_path: str,
    report_dir: str,
    stderr_text: str,
    stdout_text: str,
    diagnostics_log: Optional[str],
) -> str:
    payload: Dict[str, Any] = {
        "failure_type": "yasa_process_failed_without_sarif",
        "language": language,
        "checker_packs": checker_packs,
        "rule_config_file": rule_config_file or "",
        "source_path": source_path,
        "report_dir": report_dir,
    }

    stderr_trimmed = _truncate_diag_text(stderr_text)
    stdout_trimmed = _truncate_diag_text(stdout_text)
    log_trimmed = _truncate_diag_text(diagnostics_log or "", head=2000, tail=2000)

    if stderr_trimmed:
        payload["stderr"] = stderr_trimmed
    if stdout_trimmed:
        payload["stdout"] = stdout_trimmed
    if log_trimmed:
        payload["diagnostics_log"] = log_trimmed

    return json.dumps(payload, ensure_ascii=False)[:12000]


def _merge_task_diagnostics_summary(
    existing_summary: Optional[str],
    metadata: Dict[str, Any],
) -> Optional[str]:
    cleaned = {k: v for k, v in metadata.items() if v not in (None, "")}
    if not cleaned:
        return existing_summary

    if not existing_summary:
        return json.dumps(cleaned, ensure_ascii=False)[:12000]

    try:
        parsed = json.loads(existing_summary)
    except Exception:
        parsed = {"summary": existing_summary}

    if isinstance(parsed, dict):
        parsed.update(cleaned)
        return json.dumps(parsed, ensure_ascii=False)[:12000]

    return json.dumps({"summary": parsed, **cleaned}, ensure_ascii=False)[:12000]


async def _handle_yasa_interrupted(
    db: AsyncSession,
    task_id: str,
    *,
    message: str,
    diagnostics: Optional[Dict[str, Any]] = None,
) -> bool:
    result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task or task.status in {"completed", "failed", "interrupted"}:
        return False

    task.status = "interrupted"
    task.error_message = message[:500]
    task.diagnostics_summary = _merge_task_diagnostics_summary(
        task.diagnostics_summary,
        diagnostics or {},
    )
    _sync_task_scan_duration(task)
    await db.commit()
    return True


def _is_yasa_scan_container_active(container_id: Optional[str]) -> bool:
    normalized = str(container_id or "").strip()
    if not normalized:
        return False
    try:
        client = docker.from_env()
        container = client.containers.get(normalized)
        container.reload()
        status = str(getattr(container, "status", "") or "").strip().lower()
        return status in {"created", "running", "restarting"}
    except docker.errors.NotFound:
        return False
    except docker.errors.DockerException as exc:
        logger.warning("Failed to inspect YASA container %s: %s", normalized, exc)
        return True


def _stage_runner_rule_config_file(
    *,
    raw_rule_config_file: Optional[str],
    project_root: str,
    project_dir: Path,
    meta_dir: Path,
) -> Optional[str]:
    normalized = str(raw_rule_config_file or "").strip()
    if not normalized:
        return None

    if normalized.startswith("/scan/") or normalized.startswith(YASA_RUNNER_RESOURCE_DIR):
        return normalized

    project_root_path = Path(project_root).expanduser().resolve()
    project_dir_path = project_dir.expanduser().resolve()
    raw_path = Path(normalized).expanduser()

    if raw_path.is_absolute():
        try:
            resolved_raw = raw_path.resolve()
        except Exception:
            resolved_raw = raw_path

        for base_path, runner_base in (
            (project_root_path, Path("/scan/project")),
            (project_dir_path, Path("/scan/project")),
        ):
            try:
                relative = resolved_raw.relative_to(base_path)
            except ValueError:
                continue
            candidate = project_dir_path / relative
            if candidate.is_file():
                return str(runner_base / relative)

        if resolved_raw.is_file():
            staged_path = meta_dir / resolved_raw.name
            shutil.copyfile(resolved_raw, staged_path)
            return str(Path("/scan/meta") / staged_path.name)

        return normalized

    for base_path in (project_dir_path, project_root_path):
        candidate = (base_path / raw_path).resolve()
        if candidate.is_file():
            try:
                relative = candidate.relative_to(project_dir_path)
            except ValueError:
                try:
                    relative = candidate.relative_to(project_root_path)
                except ValueError:
                    relative = None
            if relative is not None:
                return str(Path("/scan/project") / relative)

    candidate = raw_path.resolve()
    if candidate.is_file():
        staged_path = meta_dir / candidate.name
        shutil.copyfile(candidate, staged_path)
        return str(Path("/scan/meta") / staged_path.name)

    raise FileNotFoundError(f"rule config file not found: {normalized}")


async def _execute_yasa_scan(
    task_id: str,
    project_root: str,
    target_path: str,
    language: str,
    checker_pack_ids: Optional[str],
    checker_ids: Optional[str],
    rule_config_file: Optional[str],
    rule_config_id: Optional[str],
) -> None:
    workspace_dir: Optional[Path] = None
    output_dir: Optional[Path] = None
    full_target_path: Optional[str] = None
    runner_source_path = Path("/scan/project")
    active_container_id: Optional[str] = None
    runtime_config: Dict[str, int] = {}

    async def _touch_running_task() -> None:
        async with async_session_factory() as touch_db:
            result = await touch_db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task or task.status != "running":
                return
            task.updated_at = datetime.utcnow()
            _sync_task_scan_duration(task)
            await touch_db.commit()

    async def _update_task_state(
        status: str,
        *,
        error_message: Optional[str] = None,
        diagnostics_summary: Optional[str] = None,
        diagnostics_metadata: Optional[Dict[str, Any]] = None,
        findings: Optional[List[Dict[str, Any]]] = None,
        language_value: Optional[str] = None,
        checker_pack_ids_value: Optional[str] = None,
        checker_ids_value: Optional[str] = None,
        rule_config_file_value: Optional[str] = None,
        rule_config_id_value: Optional[str] = None,
        rule_config_name_value: Optional[str] = None,
        rule_config_source_value: Optional[str] = None,
        files_scanned_count: int = 0,
    ) -> Optional[YasaScanTask]:
        async with async_session_factory() as update_db:
            result = await update_db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return None

            current_status = str(task.status or "").strip().lower()
            if current_status in {"completed", "failed", "interrupted"} and current_status != status:
                return task

            if findings:
                for finding_item in findings:
                    update_db.add(
                        YasaFinding(
                            scan_task_id=task_id,
                            rule_id=finding_item.get("rule_id"),
                            rule_name=finding_item.get("rule_name"),
                            level=str(finding_item.get("level") or "warning")[:32],
                            message=str(finding_item.get("message") or "")[:4000],
                            file_path=str(finding_item.get("file_path") or "unknown")[:1200],
                            start_line=finding_item.get("start_line"),
                            end_line=finding_item.get("end_line"),
                            status="open",
                            raw_payload=finding_item.get("raw_payload"),
                        )
                    )

            task.status = status
            if error_message is not None:
                task.error_message = error_message[:500] if error_message else None
            if diagnostics_summary is not None:
                task.diagnostics_summary = diagnostics_summary
            if diagnostics_metadata:
                task.diagnostics_summary = _merge_task_diagnostics_summary(
                    task.diagnostics_summary,
                    diagnostics_metadata,
                )
            if status == "completed":
                task.language = language_value or task.language
                task.checker_pack_ids = checker_pack_ids_value
                task.checker_ids = checker_ids_value
                task.rule_config_file = rule_config_file_value
                task.rule_config_id = rule_config_id_value
                task.rule_config_name = rule_config_name_value
                task.rule_config_source = rule_config_source_value
                task.total_findings = len(findings or [])
                task.files_scanned = files_scanned_count

            _sync_task_scan_duration(task)
            await update_db.commit()
            return task

    try:
        async with async_session_factory() as db:
            result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                logger.error("YASA task %s not found", task_id)
                return

            if _is_scan_task_cancelled("yasa", task_id) or task.status == "interrupted":
                task.status = "interrupted"
                task.error_message = task.error_message or "扫描任务已中止（用户操作）"
                _sync_task_scan_duration(task)
                await db.commit()
                return

            if not bool(getattr(settings, "YASA_ENABLED", True)):
                task.status = "failed"
                task.error_message = "YASA 引擎已禁用，请设置 YASA_ENABLED=true"
                _sync_task_scan_duration(task)
                await db.commit()
                return

            runtime_config = await load_global_yasa_runtime_config(db)
            task.status = "running"
            await db.commit()

        timeout_seconds = max(1, int(runtime_config["yasa_timeout_seconds"]))
        heartbeat_seconds = max(1, int(runtime_config["yasa_exec_heartbeat_seconds"]))
        orphan_stale_seconds = max(30, int(runtime_config["yasa_orphan_stale_seconds"]))

        workspace_dir = ensure_scan_workspace("yasa", task_id)
        project_dir = ensure_scan_project_dir("yasa", task_id)
        output_dir = ensure_scan_output_dir("yasa", task_id)
        meta_dir = ensure_scan_meta_dir("yasa", task_id)
        ensure_scan_logs_dir("yasa", task_id)

        shutil.rmtree(project_dir, ignore_errors=True)
        copy_project_tree_to_scan_dir(project_root, project_dir)

        full_target_path = os.path.join(str(project_dir), target_path)
        if not os.path.exists(full_target_path):
            await _update_task_state(
                "failed",
                error_message=f"Target path {full_target_path} not found",
                diagnostics_metadata={
                    "termination_reason": "invalid_target_path",
                    "runner_mode": "container",
                },
            )
            return

        try:
            profile = _resolve_language_profile(language)
        except ValueError as exc:
            await _update_task_state(
                "failed",
                error_message=str(exc),
                diagnostics_summary=json.dumps(
                    {
                        "failure_type": "unsupported_or_missing_language",
                        "language": str(language or "").strip(),
                        "supported_languages": list(_SUPPORTED_YASA_LANGUAGES),
                    },
                    ensure_ascii=False,
                )[:3000],
                diagnostics_metadata={"runner_mode": "container"},
            )
            return

        normalized_language = profile["language"]
        packs = _split_csv(checker_pack_ids)
        checker_values = _split_csv(checker_ids)
        resolved_rule_config = str(rule_config_file or "").strip()
        task_rule_config_name: Optional[str] = None
        task_rule_config_source = "builtin"

        if rule_config_id:
            async with async_session_factory() as rule_db:
                custom_rule_result = await rule_db.execute(
                    select(YasaRuleConfig).where(YasaRuleConfig.id == rule_config_id)
                )
                custom_rule_config = custom_rule_result.scalar_one_or_none()
            if custom_rule_config is None:
                await _update_task_state("failed", error_message="自定义 YASA 规则配置不存在")
                return
            if not bool(custom_rule_config.is_active):
                await _update_task_state("failed", error_message="自定义 YASA 规则配置已禁用")
                return
            normalized_language = str(custom_rule_config.language or "").strip().lower()
            packs = _split_csv(custom_rule_config.checker_pack_ids)
            checker_values = _split_csv(custom_rule_config.checker_ids)
            staged_rule_config = meta_dir / "custom-rule-config.json"
            staged_rule_config.write_text(
                str(custom_rule_config.rule_config_json or ""),
                encoding="utf-8",
            )
            resolved_rule_config = str(Path("/scan/meta") / staged_rule_config.name)
            task_rule_config_name = str(custom_rule_config.name or "").strip() or None
            task_rule_config_source = str(custom_rule_config.source or "custom").strip() or "custom"
        else:
            if not packs:
                packs = [profile["checker_pack"]]
            if resolved_rule_config:
                resolved_rule_config = (
                    _stage_runner_rule_config_file(
                        raw_rule_config_file=resolved_rule_config,
                        project_root=project_root,
                        project_dir=project_dir,
                        meta_dir=meta_dir,
                    )
                    or ""
                )
            else:
                default_rule_config = _build_default_rule_config_path(profile)
                if default_rule_config:
                    resolved_rule_config = default_rule_config

        normalized_target_path = str(target_path or ".").strip()
        if normalized_target_path not in {"", "."}:
            runner_source_path = runner_source_path / normalized_target_path

        cmd = build_yasa_scan_command(
            binary=YASA_RUNNER_BINARY,
            source_path=str(runner_source_path),
            language=normalized_language,
            report_dir="/scan/output",
            checker_pack_ids=packs,
            checker_ids=checker_values,
            rule_config_file=resolved_rule_config or None,
            use_runner_paths=True,
        )

        scan_started_at = datetime.utcnow()
        orphan_since: Optional[datetime] = None

        def _on_container_started(container_id: str) -> None:
            nonlocal active_container_id
            active_container_id = container_id
            _register_scan_container("yasa", task_id, container_id)

        process_future = asyncio.create_task(
            run_scanner_container(
                ScannerRunSpec(
                    scanner_type="yasa",
                    image=str(
                        getattr(settings, "SCANNER_YASA_IMAGE", "vulhunter/yasa-runner:latest")
                    ),
                    workspace_dir=str(workspace_dir),
                    command=cmd,
                    timeout_seconds=timeout_seconds,
                    env={"YASA_RESOURCE_DIR": YASA_RUNNER_RESOURCE_DIR},
                    artifact_paths=["output/report.sarif"],
                ),
                on_container_started=_on_container_started,
            )
        )

        process_result = None
        while True:
            if process_future.done():
                process_result = await process_future
                break

            if _is_scan_task_cancelled("yasa", task_id):
                await _stop_scan_container("yasa", task_id)
                cleanup_stats = _force_cleanup_yasa_processes(
                    task_id=task_id,
                    report_dir=str(output_dir) if output_dir is not None else None,
                    source_path=full_target_path,
                )
                if not process_future.done():
                    process_future.cancel()
                await _update_task_state(
                    "interrupted",
                    error_message="扫描任务已中止（用户操作）",
                    diagnostics_metadata={
                        "termination_reason": "manual_interrupt",
                        "runner_mode": "container",
                        "container_id": active_container_id or "",
                        "process_cleanup_applied": bool(cleanup_stats["matched"]),
                        "cleanup_matched": cleanup_stats["matched"],
                        "cleanup_terminated": cleanup_stats["terminated"],
                        "cleanup_killed": cleanup_stats["killed"],
                    },
                )
                return

            if active_container_id:
                is_active = await asyncio.to_thread(
                    _is_yasa_scan_container_active,
                    active_container_id,
                )
                if not is_active:
                    if orphan_since is None:
                        orphan_since = datetime.utcnow()
                    orphan_elapsed = int((datetime.utcnow() - orphan_since).total_seconds())
                    if orphan_elapsed >= orphan_stale_seconds:
                        await _stop_scan_container("yasa", task_id)
                        cleanup_stats = _force_cleanup_yasa_processes(
                            task_id=task_id,
                            report_dir=str(output_dir) if output_dir is not None else None,
                            source_path=full_target_path,
                        )
                        if not process_future.done():
                            process_future.cancel()
                        await _update_task_state(
                            "interrupted",
                            error_message="扫描容器丢失，已自动标记为中止",
                            diagnostics_metadata={
                                "termination_reason": "orphan_recovery",
                                "runner_mode": "container",
                                "orphan_recovered": True,
                                "container_id": active_container_id,
                                "process_cleanup_applied": bool(cleanup_stats["matched"]),
                                "cleanup_matched": cleanup_stats["matched"],
                                "cleanup_terminated": cleanup_stats["terminated"],
                                "cleanup_killed": cleanup_stats["killed"],
                            },
                        )
                        return
                else:
                    orphan_since = None
            else:
                startup_elapsed = int((datetime.utcnow() - scan_started_at).total_seconds())
                if startup_elapsed >= orphan_stale_seconds:
                    await _stop_scan_container("yasa", task_id)
                    if not process_future.done():
                        process_future.cancel()
                    await _update_task_state(
                        "interrupted",
                        error_message="扫描容器未在预期时间内启动，已自动标记为中止",
                        diagnostics_metadata={
                            "termination_reason": "container_start_timeout",
                            "runner_mode": "container",
                            "orphan_recovered": True,
                        },
                    )
                    return

            await _touch_running_task()
            await asyncio.sleep(heartbeat_seconds)

        if process_result is None:
            raise RuntimeError("YASA 执行结果为空")

        if _is_scan_task_cancelled("yasa", task_id):
            await _update_task_state(
                "interrupted",
                error_message="扫描任务已中止（用户操作）",
                diagnostics_metadata={
                    "termination_reason": "manual_interrupt",
                    "runner_mode": "container",
                    "container_id": active_container_id or "",
                },
            )
            return

        sarif_path = output_dir / "report.sarif"
        findings_payload: List[Dict[str, Any]] = []
        if sarif_path.exists():
            try:
                sarif_data = json.loads(sarif_path.read_text(encoding="utf-8", errors="ignore"))
                findings_payload = _parse_yasa_sarif_output(sarif_data)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse YASA SARIF for task %s: %s", task_id, exc)

        if (not process_result.success or process_result.exit_code != 0) and not findings_payload:
            stderr_text = ""
            stdout_text = ""
            if process_result.stderr_path:
                stderr_text = Path(process_result.stderr_path).read_text(
                    encoding="utf-8",
                    errors="ignore",
                ).strip()
            if process_result.stdout_path:
                stdout_text = Path(process_result.stdout_path).read_text(
                    encoding="utf-8",
                    errors="ignore",
                ).strip()
            diagnostics_log = _read_diagnostics_summary(str(output_dir))
            short_message = (
                str(process_result.error or "").strip()
                or stderr_text
                or stdout_text
                or "YASA runner 执行失败"
            )
            await _update_task_state(
                "failed",
                error_message=short_message,
                diagnostics_summary=_build_failure_diagnostics_summary(
                    language=normalized_language,
                    checker_packs=packs,
                    rule_config_file=resolved_rule_config or None,
                    source_path=str(runner_source_path),
                    report_dir=str(output_dir),
                    stderr_text=stderr_text,
                    stdout_text=stdout_text,
                    diagnostics_log=diagnostics_log,
                ),
                diagnostics_metadata={
                    "termination_reason": "runner_failed",
                    "runner_mode": "container",
                    "timeout_seconds": timeout_seconds,
                },
            )
            return

        completion_log = _read_diagnostics_summary(str(output_dir))
        metadata_summary = {
            "rule_config_id": rule_config_id or "",
            "rule_config_name": task_rule_config_name or "",
            "rule_config_source": task_rule_config_source,
        }
        completion_payload: Dict[str, Any] = {"rule_config": metadata_summary}
        if completion_log:
            completion_payload["summary"] = completion_log
        elif not findings_payload:
            completion_payload["summary"] = "YASA 扫描完成，未发现 SARIF 结果"

        updated_task = await _update_task_state(
            "completed",
            findings=findings_payload,
            diagnostics_summary=json.dumps(completion_payload, ensure_ascii=False)[:3000],
            diagnostics_metadata={
                "termination_reason": "completed",
                "runner_mode": "container",
                "timeout_seconds": timeout_seconds,
                "orphan_recovered": False,
            },
            language_value=normalized_language,
            checker_pack_ids_value=",".join(packs),
            checker_ids_value=",".join(checker_values) if checker_values else None,
            rule_config_file_value=resolved_rule_config or None,
            rule_config_id_value=rule_config_id or None,
            rule_config_name_value=task_rule_config_name,
            rule_config_source_value=task_rule_config_source,
            files_scanned_count=len(
                {
                    str(item.get("file_path") or "").strip()
                    for item in findings_payload
                    if str(item.get("file_path") or "").strip()
                }
            ),
        )
        if updated_task is not None:
            project_metrics_refresher.enqueue(updated_task.project_id)
    except subprocess.TimeoutExpired:
        cleanup_stats = _force_cleanup_yasa_processes(
            task_id=task_id,
            report_dir=str(output_dir) if output_dir is not None else None,
            source_path=full_target_path,
        )
        await _update_task_state(
            "failed",
            error_message="YASA 扫描超时",
            diagnostics_metadata={
                "termination_reason": "hard_timeout",
                "runner_mode": "container",
                "process_cleanup_applied": bool(cleanup_stats["matched"]),
                "cleanup_matched": cleanup_stats["matched"],
                "cleanup_terminated": cleanup_stats["terminated"],
                "cleanup_killed": cleanup_stats["killed"],
            },
        )
    except FileNotFoundError as exc:
        await _update_task_state(
            "failed",
            error_message=str(exc),
            diagnostics_metadata={
                "termination_reason": "missing_dependency",
                "runner_mode": "container",
            },
        )
    except asyncio.CancelledError:
        await _stop_scan_container("yasa", task_id)
        cleanup_stats = _force_cleanup_yasa_processes(
            task_id=task_id,
            report_dir=str(output_dir) if output_dir is not None else None,
            source_path=full_target_path,
        )
        await _update_task_state(
            "interrupted",
            error_message="扫描任务因服务中断被标记为中止",
            diagnostics_metadata={
                "termination_reason": "service_cancelled",
                "runner_mode": "container",
                "process_cleanup_applied": bool(cleanup_stats["matched"]),
                "cleanup_matched": cleanup_stats["matched"],
                "cleanup_terminated": cleanup_stats["terminated"],
                "cleanup_killed": cleanup_stats["killed"],
            },
        )
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Error executing YASA task %s: %s", task_id, exc)
        cleanup_stats = _force_cleanup_yasa_processes(
            task_id=task_id,
            report_dir=str(output_dir) if output_dir is not None else None,
            source_path=full_target_path,
        )
        await _update_task_state(
            "failed",
            error_message=str(exc),
            diagnostics_metadata={
                "termination_reason": "unexpected_exception",
                "runner_mode": "container",
                "process_cleanup_applied": bool(cleanup_stats["matched"]),
                "cleanup_matched": cleanup_stats["matched"],
                "cleanup_terminated": cleanup_stats["terminated"],
                "cleanup_killed": cleanup_stats["killed"],
            },
        )
    finally:
        _pop_scan_container("yasa", task_id)
        if workspace_dir is not None:
            cleanup_scan_workspace("yasa", task_id)
        _clear_scan_task_cancel("yasa", task_id)
        if project_root and project_root.startswith("/tmp") and os.path.exists(project_root):
            try:
                shutil.rmtree(project_root, ignore_errors=True)
                logger.info(f"Cleaned up temporary project directory: {project_root}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory {project_root}: {e}")


@router.get("/yasa/runtime-config", response_model=YasaRuntimeConfigResponse)
async def get_yasa_runtime_config(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    runtime_config = await load_global_yasa_runtime_config(db)
    return YasaRuntimeConfigResponse(**runtime_config)


@router.put("/yasa/runtime-config", response_model=YasaRuntimeConfigResponse)
async def update_yasa_runtime_config(
    payload: YasaRuntimeConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    runtime_config = await save_global_yasa_runtime_config(
        db,
        user_id=current_user.id,
        runtime_config=payload.model_dump(),
    )
    return YasaRuntimeConfigResponse(**runtime_config)


@router.post("/yasa/scan", response_model=YasaScanTaskResponse)
async def create_yasa_scan(
    request: YasaScanTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    if request.rule_config_id and request.rule_config_file:
        raise HTTPException(
            status_code=400,
            detail="rule_config_id 与 rule_config_file 不能同时传入",
        )

    project = await db.get(Project, request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    _assert_yasa_project_language_supported(project)

    project_root = await _get_project_root(request.project_id)
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail="找不到项目的 zip 文件，请先上传项目 ZIP 文件到 uploads/zip_files 目录",
        )

    selected_rule_config: Optional[YasaRuleConfig] = None
    if request.rule_config_id:
        rule_result = await db.execute(
            select(YasaRuleConfig).where(YasaRuleConfig.id == request.rule_config_id)
        )
        selected_rule_config = rule_result.scalar_one_or_none()
        if selected_rule_config is None:
            raise HTTPException(status_code=404, detail="YASA 自定义规则配置不存在")
        if not bool(selected_rule_config.is_active):
            raise HTTPException(status_code=409, detail="YASA 自定义规则配置已禁用")

    detected_language = request.language or _detect_language_from_project(project)
    if selected_rule_config is not None:
        detected_language = selected_rule_config.language

    try:
        profile = _resolve_language_profile(detected_language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    checker_pack_csv = _normalize_csv(request.checker_pack_ids)
    checker_ids_csv = _normalize_csv(request.checker_ids)
    if selected_rule_config is not None:
        checker_pack_csv = selected_rule_config.checker_pack_ids
        checker_ids_csv = selected_rule_config.checker_ids

    scan_task = YasaScanTask(
        project_id=request.project_id,
        name=request.name or f"YASA_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        status="pending",
        target_path=request.target_path,
        language=profile["language"],
        checker_pack_ids=checker_pack_csv,
        checker_ids=checker_ids_csv,
        rule_config_file=str(request.rule_config_file or "").strip() or None,
        rule_config_id=selected_rule_config.id if selected_rule_config else None,
        rule_config_name=selected_rule_config.name if selected_rule_config else None,
        rule_config_source=selected_rule_config.source if selected_rule_config else None,
    )
    db.add(scan_task)
    await db.commit()
    await db.refresh(scan_task)
    response = _build_yasa_scan_task_response(scan_task)
    task_id = response.id
    language_value = scan_task.language
    checker_pack_ids_value = scan_task.checker_pack_ids
    checker_ids_value = scan_task.checker_ids
    rule_config_file_value = scan_task.rule_config_file
    rule_config_id_value = scan_task.rule_config_id

    await _release_request_db_session(db)
    _launch_static_background_job(
        "yasa",
        task_id,
        _execute_yasa_scan(
            task_id,
            project_root,
            request.target_path,
            language_value,
            checker_pack_ids_value,
            checker_ids_value,
            rule_config_file_value,
            rule_config_id_value,
        ),
    )
    return response


@router.get("/yasa/tasks", response_model=List[YasaScanTaskResponse])
async def list_yasa_tasks(
    project_id: Optional[str] = Query(None, description="按项目ID过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    query = select(YasaScanTask)
    if project_id:
        query = query.where(YasaScanTask.project_id == project_id)
    query = query.order_by(YasaScanTask.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/yasa/tasks/{task_id}", response_model=YasaScanTaskResponse)
async def get_yasa_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/yasa/tasks/{task_id}/interrupt")
async def interrupt_yasa_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status in {"completed", "failed", "interrupted"}:
        return {
            "message": f"任务当前状态为 {task.status}，无需中止",
            "task_id": task_id,
            "status": task.status,
        }

    _request_scan_task_cancel("yasa", task_id)
    cleanup_stats = _force_cleanup_yasa_processes(task_id=task_id)
    task.status = "interrupted"
    task.error_message = task.error_message or "扫描任务已中止（用户操作）"
    task.diagnostics_summary = _merge_task_diagnostics_summary(
        task.diagnostics_summary,
        {
            "termination_reason": "manual_interrupt",
            "process_cleanup_applied": bool(cleanup_stats["matched"]),
            "cleanup_matched": cleanup_stats["matched"],
            "cleanup_terminated": cleanup_stats["terminated"],
            "cleanup_killed": cleanup_stats["killed"],
        },
    )
    _sync_task_scan_duration(task)
    await db.commit()
    return {"message": "任务已中止", "task_id": task_id, "status": "interrupted"}


@router.delete("/yasa/tasks/{task_id}")
async def delete_yasa_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    await db.delete(task)
    await db.commit()
    return {"message": "任务已删除", "task_id": task_id}


@router.get("/yasa/tasks/{task_id}/findings", response_model=List[YasaFindingResponse])
async def get_yasa_findings(
    task_id: str,
    status: Optional[str] = Query(None, description="按状态过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    task_result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
    if not task_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")

    query = select(YasaFinding).where(YasaFinding.scan_task_id == task_id)
    if status:
        query = query.where(YasaFinding.status == status)
    query = query.order_by(YasaFinding.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/yasa/rule-configs/import", response_model=YasaRuleConfigResponse)
async def import_yasa_rule_config(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    language: str = Form(...),
    checker_pack_ids: Optional[str] = Form(None),
    checker_ids: Optional[str] = Form(None),
    rule_config_json: Optional[str] = Form(None),
    rule_config_file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    normalized_name = str(name or "").strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="name 不能为空")

    normalized_language = str(language or "").strip().lower()
    if normalized_language not in _SUPPORTED_YASA_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="language 无效，YASA 仅支持 java/golang/typescript/python",
        )

    payload_text = str(rule_config_json or "").strip()
    if rule_config_file is not None:
        file_bytes = await rule_config_file.read()
        payload_text = file_bytes.decode("utf-8", errors="ignore").strip()

    if not payload_text:
        raise HTTPException(status_code=400, detail="rule_config_json 或 rule_config_file 必须提供")

    try:
        rule_config_payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"rule-config JSON 无效: {exc.msg}") from exc

    derived_checker_ids = _parse_rule_config_checker_ids(rule_config_payload)
    if not derived_checker_ids:
        raise HTTPException(
            status_code=400,
            detail="rule-config 缺少 checkerIds（必须为非空数组）",
        )

    catalog = _load_yasa_checker_catalog_or_http_error()
    normalized_checker_ids = _normalize_checker_values(_split_csv_form(checker_ids)) or derived_checker_ids
    normalized_checker_pack_ids = _normalize_checker_values(_split_csv_form(checker_pack_ids))
    _validate_checker_bindings(
        checker_ids=normalized_checker_ids,
        checker_pack_ids=normalized_checker_pack_ids,
        catalog=catalog,
    )

    row = YasaRuleConfig(
        name=normalized_name,
        description=str(description or "").strip() or None,
        language=normalized_language,
        checker_pack_ids=_normalize_csv(normalized_checker_pack_ids),
        checker_ids=_normalize_csv(normalized_checker_ids) or "",
        rule_config_json=json.dumps(rule_config_payload, ensure_ascii=False),
        is_active=True,
        source="custom",
        created_by=str(getattr(current_user, "id", "") or "") or None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/yasa/rule-configs", response_model=List[YasaRuleConfigResponse])
async def list_yasa_rule_configs(
    language: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    keyword: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    query = select(YasaRuleConfig).where(YasaRuleConfig.source == "custom")
    if language:
        query = query.where(YasaRuleConfig.language == str(language).strip().lower())
    if is_active is not None:
        query = query.where(YasaRuleConfig.is_active.is_(is_active))
    if keyword:
        normalized_keyword = f"%{str(keyword).strip().lower()}%"
        query = query.where(
            YasaRuleConfig.name.ilike(normalized_keyword)
            | YasaRuleConfig.description.ilike(normalized_keyword)
        )
    query = query.order_by(YasaRuleConfig.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/yasa/rule-configs/{rule_config_id}", response_model=YasaRuleConfigResponse)
async def get_yasa_rule_config(
    rule_config_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    result = await db.execute(
        select(YasaRuleConfig).where(
            (YasaRuleConfig.id == rule_config_id) & (YasaRuleConfig.source == "custom")
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="YASA 自定义规则配置不存在")
    return row


@router.patch("/yasa/rule-configs/{rule_config_id}", response_model=YasaRuleConfigResponse)
async def update_yasa_rule_config(
    rule_config_id: str,
    request: YasaRuleConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    result = await db.execute(
        select(YasaRuleConfig).where(
            (YasaRuleConfig.id == rule_config_id) & (YasaRuleConfig.source == "custom")
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="YASA 自定义规则配置不存在")

    if request.language is not None:
        normalized_language = str(request.language or "").strip().lower()
        if normalized_language not in _SUPPORTED_YASA_LANGUAGES:
            raise HTTPException(
                status_code=400,
                detail="language 无效，YASA 仅支持 java/golang/typescript/python",
            )
        row.language = normalized_language
    if request.name is not None:
        normalized_name = str(request.name or "").strip()
        if not normalized_name:
            raise HTTPException(status_code=400, detail="name 不能为空")
        row.name = normalized_name
    if request.description is not None:
        row.description = str(request.description or "").strip() or None

    if request.checker_ids is not None or request.checker_pack_ids is not None:
        catalog = _load_yasa_checker_catalog_or_http_error()
        normalized_checker_ids = (
            _normalize_checker_values(request.checker_ids)
            if request.checker_ids is not None
            else _split_csv(row.checker_ids)
        )
        normalized_checker_pack_ids = (
            _normalize_checker_values(request.checker_pack_ids)
            if request.checker_pack_ids is not None
            else _split_csv(row.checker_pack_ids)
        )
        _validate_checker_bindings(
            checker_ids=normalized_checker_ids,
            checker_pack_ids=normalized_checker_pack_ids,
            catalog=catalog,
        )
        row.checker_ids = _normalize_csv(normalized_checker_ids) or row.checker_ids
        row.checker_pack_ids = _normalize_csv(normalized_checker_pack_ids)

    if request.is_active is not None:
        row.is_active = bool(request.is_active)

    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/yasa/rule-configs/{rule_config_id}")
async def delete_yasa_rule_config(
    rule_config_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    result = await db.execute(
        select(YasaRuleConfig).where(
            (YasaRuleConfig.id == rule_config_id) & (YasaRuleConfig.source == "custom")
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="YASA 自定义规则配置不存在")
    row.is_active = False
    await db.commit()
    return {"message": "规则配置已禁用", "id": rule_config_id}


@router.get("/yasa/rules", response_model=List[YasaRuleResponse])
async def list_yasa_rules(
    checker_pack_id: Optional[str] = Query(None, description="按 checkerPack 过滤"),
    language: Optional[str] = Query(None, description="按语言过滤"),
    keyword: Optional[str] = Query(None, description="按 checkerId/描述过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=2000),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    rules = [YasaRuleResponse(**item) for item in _load_yasa_snapshot_rules_or_http_error()]
    if checker_pack_id:
        expected_pack = str(checker_pack_id).strip()
        rules = [item for item in rules if expected_pack in item.checker_packs]

    if language:
        normalized_language = str(language).strip().lower()
        if normalized_language not in _SUPPORTED_YASA_LANGUAGES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"不支持语言: {normalized_language}，"
                    "YASA 仅支持 java/golang/typescript/python"
                ),
            )
        rules = [item for item in rules if normalized_language in item.languages]

    if keyword:
        normalized_keyword = str(keyword).strip().lower()
        if normalized_keyword:
            rules = [
                item
                for item in rules
                if normalized_keyword in item.checker_id.lower()
                or normalized_keyword in str(item.description or "").lower()
                or any(normalized_keyword in pack.lower() for pack in item.checker_packs)
            ]

    return rules[skip : skip + limit]


@router.get("/yasa/tasks/{task_id}/findings/{finding_id}", response_model=YasaFindingResponse)
async def get_yasa_finding(
    task_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    task_result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
    if not task_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")

    finding_result = await db.execute(
        select(YasaFinding).where(
            (YasaFinding.id == finding_id) & (YasaFinding.scan_task_id == task_id)
        )
    )
    finding = finding_result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="漏洞不存在")
    return finding


@router.post("/yasa/findings/{finding_id}/status")
async def update_yasa_finding_status(
    finding_id: str,
    status: str = Query(..., description="open, verified, false_positive"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    allowed_status = {"open", "verified", "false_positive"}
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in allowed_status:
        raise HTTPException(status_code=400, detail="无效状态")

    result = await db.execute(select(YasaFinding).where(YasaFinding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="漏洞不存在")

    finding.status = normalized_status
    await db.commit()
    return {
        "message": "状态更新成功",
        "finding_id": finding_id,
        "status": normalized_status,
    }
