import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.v1.endpoints.static_tasks_shared import (
    _clear_scan_task_cancel,
    _get_project_root,
    _is_scan_task_cancelled,
    _request_scan_task_cancel,
    _run_subprocess_with_tracking,
    _sync_task_scan_duration,
    deps,
    get_db,
    logger,
    settings,
)
from app.models.project import Project
from app.models.user import User
from app.models.yasa import YasaFinding, YasaScanTask
from app.services.yasa_runtime import build_yasa_scan_command
from app.services.yasa_language import (
    YASA_SUPPORTED_LANGUAGES,
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


def _resolve_language_profile(language: Optional[str]) -> Dict[str, str]:
    return resolve_yasa_language_profile(language)


def _detect_language_from_project(project: Project) -> Optional[str]:
    return resolve_yasa_language_from_programming_languages(
        getattr(project, "programming_languages", None)
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


def _resolve_resource_dir() -> Optional[Path]:
    configured = str(getattr(settings, "YASA_RESOURCE_DIR", "") or "").strip()
    if configured:
        resource_dir = Path(configured).expanduser()
        if resource_dir.exists():
            return resource_dir

    candidates = [
        Path.home() / ".local" / "share" / "yasa-engine" / "resource",
        Path("/usr/local/share/yasa-engine/resource"),
        Path("/usr/share/yasa-engine/resource"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _build_default_rule_config_path(profile: Dict[str, str]) -> Optional[str]:
    resource_dir = _resolve_resource_dir()
    if resource_dir is None:
        return None
    candidate = resource_dir / "example-rule-config" / profile["rule_config"]
    if candidate.exists():
        return str(candidate)
    return None


def _safe_json_load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None


def _infer_languages_from_pack_id(pack_id: str) -> List[str]:
    normalized = str(pack_id or "").strip().lower()
    tags: List[str] = []
    if "java" in normalized:
        tags.append("java")
    if "python" in normalized:
        tags.append("python")
    if "go" in normalized or "golang" in normalized:
        tags.append("golang")
    if "javascript" in normalized or "js" in normalized or "express" in normalized:
        tags.extend(["javascript", "typescript"])
    seen = set()
    ordered: List[str] = []
    for item in tags:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _extract_yasa_rules_from_resource_dir(resource_dir: Path) -> List[YasaRuleResponse]:
    checker_config_path = resource_dir / "checker" / "checker-config.json"
    checker_pack_config_path = resource_dir / "checker" / "checker-pack-config.json"

    checker_payload = _safe_json_load(checker_config_path)
    checker_pack_payload = _safe_json_load(checker_pack_config_path)
    if not isinstance(checker_payload, list) or not isinstance(checker_pack_payload, list):
        return []

    checker_pack_map: Dict[str, List[str]] = {}
    checker_language_map: Dict[str, List[str]] = {}
    for item in checker_pack_payload:
        if not isinstance(item, dict):
            continue
        checker_pack_id = str(item.get("checkerPackId") or "").strip()
        checker_ids = item.get("checkerIds")
        if not checker_pack_id or not isinstance(checker_ids, list):
            continue
        languages = _infer_languages_from_pack_id(checker_pack_id)
        for checker_id in checker_ids:
            checker_key = str(checker_id or "").strip()
            if not checker_key:
                continue
            checker_pack_map.setdefault(checker_key, []).append(checker_pack_id)
            checker_language_map.setdefault(checker_key, [])
            for language in languages:
                if language not in checker_language_map[checker_key]:
                    checker_language_map[checker_key].append(language)

    rules: List[YasaRuleResponse] = []
    for raw in checker_payload:
        if not isinstance(raw, dict):
            continue
        checker_id = str(raw.get("checkerId") or "").strip()
        if not checker_id:
            continue
        rules.append(
            YasaRuleResponse(
                checker_id=checker_id,
                checker_path=str(raw.get("checkerPath") or "").strip() or None,
                description=str(raw.get("description") or "").strip() or None,
                checker_packs=checker_pack_map.get(checker_id, []),
                languages=checker_language_map.get(checker_id, []),
                demo_rule_config_path=str(raw.get("demoRuleConfigPath") or "").strip()
                or None,
                source="builtin",
            )
        )

    rules.sort(key=lambda item: item.checker_id.lower())
    return rules


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


async def _execute_yasa_scan(
    task_id: str,
    project_root: str,
    target_path: str,
    language: str,
    checker_pack_ids: Optional[str],
    checker_ids: Optional[str],
    rule_config_file: Optional[str],
) -> None:
    from app.db.session import async_session_factory

    async with async_session_factory() as db:
        report_dir: Optional[str] = None
        try:
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

            task.status = "running"
            await db.commit()

            full_target_path = os.path.join(project_root, target_path)
            if not os.path.exists(full_target_path):
                task.status = "failed"
                task.error_message = f"Target path {full_target_path} not found"
                _sync_task_scan_duration(task)
                await db.commit()
                return

            resolved_bin = _resolve_yasa_binary()
            try:
                profile = _resolve_language_profile(language)
            except ValueError as exc:
                task.status = "failed"
                task.error_message = str(exc)[:500]
                task.diagnostics_summary = json.dumps(
                    {
                        "failure_type": "unsupported_or_missing_language",
                        "language": str(language or "").strip(),
                        "supported_languages": list(_SUPPORTED_YASA_LANGUAGES),
                    },
                    ensure_ascii=False,
                )[:3000]
                _sync_task_scan_duration(task)
                await db.commit()
                return
            normalized_language = profile["language"]

            packs = _split_csv(checker_pack_ids)
            if not packs:
                packs = [profile["checker_pack"]]

            resolved_rule_config = str(rule_config_file or "").strip()
            if not resolved_rule_config:
                default_rule_config = _build_default_rule_config_path(profile)
                if default_rule_config:
                    resolved_rule_config = default_rule_config

            report_dir = tempfile.mkdtemp(prefix=f"yasa_report_{task_id}_")
            checker_values = _split_csv(checker_ids)
            cmd = build_yasa_scan_command(
                binary=resolved_bin,
                source_path=full_target_path,
                language=normalized_language,
                report_dir=report_dir,
                checker_pack_ids=packs,
                checker_ids=checker_values,
                rule_config_file=resolved_rule_config or None,
            )

            timeout_seconds = int(getattr(settings, "YASA_TIMEOUT_SECONDS", 600) or 600)
            loop = asyncio.get_event_loop()
            process_result = await loop.run_in_executor(
                None,
                lambda: _run_subprocess_with_tracking(
                    "yasa",
                    task_id,
                    cmd,
                    timeout=max(1, timeout_seconds),
                ),
            )

            if _is_scan_task_cancelled("yasa", task_id):
                task.status = "interrupted"
                task.error_message = task.error_message or "扫描任务已中止（用户操作）"
                _sync_task_scan_duration(task)
                await db.commit()
                return

            sarif_path = Path(report_dir) / "report.sarif"
            findings_payload: List[Dict[str, Any]] = []
            if sarif_path.exists():
                try:
                    sarif_data = json.loads(
                        sarif_path.read_text(encoding="utf-8", errors="ignore")
                    )
                    findings_payload = _parse_yasa_sarif_output(sarif_data)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to parse YASA SARIF for task %s: %s", task_id, exc)

            if process_result.returncode != 0 and not findings_payload:
                stderr_text = str(process_result.stderr or "").strip()
                stdout_text = str(process_result.stdout or "").strip()
                diagnostics_log = _read_diagnostics_summary(report_dir)

                short_message = (
                    stderr_text
                    or stdout_text
                    or "YASA 扫描失败，请检查 YASA_BIN_PATH 或规则参数"
                )

                task.status = "failed"
                task.error_message = short_message[:500]
                task.diagnostics_summary = _build_failure_diagnostics_summary(
                    language=normalized_language,
                    checker_packs=packs,
                    rule_config_file=resolved_rule_config or None,
                    source_path=full_target_path,
                    report_dir=report_dir,
                    stderr_text=stderr_text,
                    stdout_text=stdout_text,
                    diagnostics_log=diagnostics_log,
                )
                _sync_task_scan_duration(task)
                await db.commit()
                return

            for finding_item in findings_payload:
                db.add(
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

            task.status = "completed"
            task.language = normalized_language
            task.checker_pack_ids = ",".join(packs)
            task.checker_ids = checker_ids
            task.rule_config_file = resolved_rule_config or None
            task.total_findings = len(findings_payload)
            task.files_scanned = len(
                {
                    str(item.get("file_path") or "").strip()
                    for item in findings_payload
                    if str(item.get("file_path") or "").strip()
                }
            )
            task.diagnostics_summary = _read_diagnostics_summary(report_dir)
            if task.total_findings == 0 and not task.diagnostics_summary:
                task.diagnostics_summary = "YASA 扫描完成，未发现 SARIF 结果"
            _sync_task_scan_duration(task)
            await db.commit()
        except subprocess.TimeoutExpired:
            await db.rollback()
            result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if task:
                task.status = "failed"
                task.error_message = "YASA 扫描超时"
                _sync_task_scan_duration(task)
                await db.commit()
        except FileNotFoundError as exc:
            await db.rollback()
            result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if task:
                task.status = "failed"
                task.error_message = str(exc)[:500]
                _sync_task_scan_duration(task)
                await db.commit()
        except asyncio.CancelledError:
            await db.rollback()
            result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if task and task.status in {"pending", "running"}:
                task.status = "interrupted"
                task.error_message = task.error_message or "扫描任务因服务中断被标记为中止"
                _sync_task_scan_duration(task)
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.error("Error executing YASA task %s: %s", task_id, exc)
            await db.rollback()
            result = await db.execute(select(YasaScanTask).where(YasaScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if task:
                task.status = "failed"
                task.error_message = str(exc)[:500]
                _sync_task_scan_duration(task)
                await db.commit()
        finally:
            if report_dir:
                shutil.rmtree(report_dir, ignore_errors=True)
            _clear_scan_task_cancel("yasa", task_id)


@router.post("/yasa/scan", response_model=YasaScanTaskResponse)
async def create_yasa_scan(
    request: YasaScanTaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    project = await db.get(Project, request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    project_root = await _get_project_root(request.project_id)
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail="找不到项目的 zip 文件，请先上传项目 ZIP 文件到 uploads/zip_files 目录",
        )

    detected_language = request.language or _detect_language_from_project(project)
    try:
        profile = _resolve_language_profile(detected_language)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    scan_task = YasaScanTask(
        project_id=request.project_id,
        name=request.name or f"YASA_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        status="pending",
        target_path=request.target_path,
        language=profile["language"],
        checker_pack_ids=_normalize_csv(request.checker_pack_ids),
        checker_ids=_normalize_csv(request.checker_ids),
        rule_config_file=str(request.rule_config_file or "").strip() or None,
    )
    db.add(scan_task)
    await db.commit()
    await db.refresh(scan_task)

    background_tasks.add_task(
        _execute_yasa_scan,
        scan_task.id,
        project_root,
        request.target_path,
        scan_task.language,
        scan_task.checker_pack_ids,
        scan_task.checker_ids,
        scan_task.rule_config_file,
    )
    return scan_task


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
    task.status = "interrupted"
    task.error_message = task.error_message or "扫描任务已中止（用户操作）"
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
    resource_dir = _resolve_resource_dir()
    if resource_dir is None:
        raise HTTPException(
            status_code=500,
            detail="未找到 YASA 资源目录，请确认 YASA_RESOURCE_DIR 或本机 yasa-engine 安装",
        )

    rules = _extract_yasa_rules_from_resource_dir(resource_dir)
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
                    "YASA 仅支持 python/javascript/typescript/golang/java"
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
