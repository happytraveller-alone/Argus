import asyncio
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api.v1.endpoints.static_tasks_shared import (
    _clear_scan_task_cancel,
    _get_project_root,
    _is_scan_task_cancelled,
    _launch_static_background_job,
    _release_request_db_session,
    _request_scan_task_cancel,
    _sync_task_scan_duration,
    async_session_factory,
    cleanup_scan_workspace,
    copy_project_tree_to_scan_dir,
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
from app.models.pmd import PmdRuleConfig
from app.models.pmd_scan import PmdFinding, PmdScanTask
from app.models.project import Project
from app.models.user import User
from app.services.agent.tools.external_tools import (
    _build_pmd_runner_command,
    _normalize_pmd_violation_path,
    _read_pmd_report,
    _resolve_pmd_ruleset,
)
from app.services.project_metrics import project_metrics_refresher
from app.services.pmd_rulesets import (
    PMD_PRESET_SUMMARIES,
    PMD_RULESET_ALIASES,
    get_builtin_pmd_ruleset_detail as service_get_builtin_pmd_ruleset_detail,
    list_builtin_pmd_rulesets as service_list_builtin_pmd_rulesets,
    parse_pmd_ruleset_xml,
)
from app.services.scanner_runner import ScannerRunSpec, run_scanner_container

router = APIRouter()


class PmdPresetResponse(BaseModel):
    id: str
    name: str
    alias: str
    description: str
    categories: list[str] = Field(default_factory=list)


class PmdRuleDetailResponse(BaseModel):
    name: Optional[str] = None
    ref: Optional[str] = None
    language: Optional[str] = None
    message: Optional[str] = None
    class_name: Optional[str] = None
    priority: Optional[int] = None
    since: Optional[str] = None
    external_info_url: Optional[str] = None
    description: Optional[str] = None


class PmdRulesetResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    filename: str
    is_active: bool
    source: str
    ruleset_name: str
    rule_count: int
    languages: list[str] = Field(default_factory=list)
    priorities: list[int] = Field(default_factory=list)
    external_info_urls: list[str] = Field(default_factory=list)
    rules: list[PmdRuleDetailResponse] = Field(default_factory=list)
    raw_xml: str
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PmdRuleConfigUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    model_config = ConfigDict(extra="ignore")


class PmdScanTaskCreate(BaseModel):
    project_id: str = Field(..., description="项目ID")
    name: Optional[str] = Field(None, description="任务名称")
    target_path: str = Field(".", description="扫描目标路径，相对于项目根目录")
    ruleset: str = Field("security", description="规则集，默认 security")


class PmdScanTaskResponse(BaseModel):
    id: str
    project_id: str
    name: str
    status: str
    target_path: str
    ruleset: str
    total_findings: int
    high_count: int
    medium_count: int
    low_count: int
    scan_duration_ms: int
    files_scanned: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PmdFindingResponse(BaseModel):
    id: str
    scan_task_id: str
    file_path: str
    begin_line: Optional[int]
    end_line: Optional[int]
    rule: Optional[str]
    ruleset: Optional[str]
    priority: Optional[int]
    message: str
    status: str

    model_config = ConfigDict(from_attributes=True)


def _build_pmd_preset_responses() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for preset_id, summary in PMD_PRESET_SUMMARIES.items():
        rows.append(
            {
                "id": preset_id,
                "name": summary["name"],
                "alias": summary["alias"],
                "description": summary["description"],
                "categories": list(summary.get("categories", [])),
            }
        )
    return rows


def _build_pmd_ruleset_response(
    payload: dict[str, Any],
    *,
    id: str,
    filename: str,
    source: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    is_active: bool,
    created_by: Optional[str] = None,
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
) -> dict[str, Any]:
    resolved_description = description if description is not None else payload.get("description")
    return {
        "id": id,
        "name": name or payload["ruleset_name"],
        "description": resolved_description,
        "filename": filename,
        "is_active": is_active,
        "source": source,
        "ruleset_name": payload["ruleset_name"],
        "rule_count": int(payload["rule_count"]),
        "languages": list(payload.get("languages", [])),
        "priorities": list(payload.get("priorities", [])),
        "external_info_urls": list(payload.get("external_info_urls", [])),
        "rules": list(payload.get("rules", [])),
        "raw_xml": payload["raw_xml"],
        "created_by": created_by,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _build_builtin_pmd_ruleset_response(payload: dict[str, Any]) -> dict[str, Any]:
    return _build_pmd_ruleset_response(
        payload,
        id=str(payload["id"]),
        filename=str(payload.get("filename") or payload["id"]),
        source="builtin",
        is_active=True,
    )


def _build_custom_pmd_ruleset_response(row: PmdRuleConfig) -> dict[str, Any]:
    try:
        payload = parse_pmd_ruleset_xml(str(row.xml_content or ""))
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"PMD 自定义规则配置解析失败: {exc}") from exc

    return _build_pmd_ruleset_response(
        payload,
        id=str(row.id),
        filename=str(row.filename),
        source="custom",
        name=str(row.name),
        description=row.description,
        is_active=bool(row.is_active),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalize_rule_config_name(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="name 不能为空")
    return normalized


def _normalize_upload_filename(filename: Optional[str]) -> str:
    normalized = str(filename or "").strip()
    if not normalized:
        raise HTTPException(status_code=400, detail="xml_file 文件名不能为空")
    if not normalized.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="PMD ruleset 文件必须是 .xml")
    return normalized


async def _read_xml_upload(xml_file: UploadFile) -> tuple[str, str]:
    filename = _normalize_upload_filename(xml_file.filename)
    raw_xml = (await xml_file.read()).decode("utf-8", errors="replace").strip()
    if not raw_xml:
        raise HTTPException(status_code=400, detail="xml_file 不能为空")
    return filename, raw_xml


def _parse_programming_languages(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item or "").strip().lower() for item in value if str(item or "").strip()]
    if not isinstance(value, str):
        return []

    text = value.strip()
    if not text:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item or "").strip().lower() for item in parsed if str(item or "").strip()]

    return [item.strip().lower() for item in text.split(",") if item.strip()]


def _is_java_project(programming_languages: Any) -> bool:
    return "java" in _parse_programming_languages(programming_languages)


def _require_java_project(project: Project) -> None:
    if _is_java_project(project.programming_languages):
        return
    raise HTTPException(status_code=400, detail="PMD 引擎暂时仅支持 Java 项目")


def _build_pmd_scan_task_response(task: PmdScanTask) -> PmdScanTaskResponse:
    return PmdScanTaskResponse(
        id=str(task.id),
        project_id=str(task.project_id),
        name=str(task.name or ""),
        status=str(task.status or "pending"),
        target_path=str(task.target_path or "."),
        ruleset=str(task.ruleset or "security"),
        total_findings=int(task.total_findings or 0),
        high_count=int(task.high_count or 0),
        medium_count=int(task.medium_count or 0),
        low_count=int(task.low_count or 0),
        scan_duration_ms=int(task.scan_duration_ms or 0),
        files_scanned=int(task.files_scanned or 0),
        error_message=task.error_message,
        created_at=task.created_at or datetime.now(timezone.utc),
        updated_at=task.updated_at,
    )


async def _execute_pmd_scan(
    task_id: str,
    project_root: str,
    target_path: str,
    ruleset: str = "security",
) -> None:
    workspace_dir: Optional[Path] = None

    async def _update_task_state(
        status: str,
        *,
        error_message: Optional[str] = None,
        findings: Optional[List[Dict[str, Any]]] = None,
        files_scanned: int = 0,
    ) -> Optional[PmdScanTask]:
        async with async_session_factory() as db:
            result = await db.execute(select(PmdScanTask).where(PmdScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return None
            if findings:
                for finding in findings:
                    db.add(
                        PmdFinding(
                            scan_task_id=task_id,
                            file_path=str(finding.get("file_path") or "")[:1000],
                            begin_line=finding.get("begin_line"),
                            end_line=finding.get("end_line"),
                            rule=(str(finding.get("rule") or "")[:500] or None),
                            ruleset=(str(finding.get("ruleset") or "")[:500] or None),
                            priority=finding.get("priority"),
                            message=str(finding.get("message") or "")[:4000],
                            status="open",
                        )
                    )
            task.status = status
            if error_message is not None:
                task.error_message = error_message[:500] if error_message else None
            if status == "completed":
                task.ruleset = str(ruleset or "security")
                task.total_findings = len(findings or [])
                task.files_scanned = files_scanned
                task.high_count = sum(
                    1 for item in findings or [] if int(item.get("priority") or 5) <= 2
                )
                task.medium_count = sum(
                    1 for item in findings or [] if int(item.get("priority") or 5) == 3
                )
                task.low_count = sum(
                    1 for item in findings or [] if int(item.get("priority") or 5) >= 4
                )
            _sync_task_scan_duration(task)
            await db.commit()
            return task

    try:
        async with async_session_factory() as db:
            result = await db.execute(select(PmdScanTask).where(PmdScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                logger.error("PMD task %s not found", task_id)
                return
            if _is_scan_task_cancelled("pmd", task_id) or task.status == "interrupted":
                task.status = "interrupted"
                task.error_message = task.error_message or "扫描任务已中止（用户操作）"
                _sync_task_scan_duration(task)
                await db.commit()
                return
            task.status = "running"
            await db.commit()

        workspace_dir = ensure_scan_workspace("pmd", task_id)
        project_dir = ensure_scan_project_dir("pmd", task_id)
        output_dir = ensure_scan_output_dir("pmd", task_id)
        logs_dir = ensure_scan_logs_dir("pmd", task_id)
        meta_dir = ensure_scan_meta_dir("pmd", task_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)

        shutil.rmtree(project_dir, ignore_errors=True)
        copy_project_tree_to_scan_dir(project_root, project_dir)

        full_target_path = os.path.join(str(project_dir), target_path)
        if not os.path.exists(full_target_path):
            await _update_task_state("failed", error_message=f"Target path {full_target_path} not found")
            return

        selected_ruleset = _resolve_pmd_ruleset(ruleset or "security", str(project_dir), meta_dir)
        runner_target_path = "/scan/project"
        normalized_target_path = str(target_path or ".").strip()
        if normalized_target_path not in {"", "."}:
            runner_target_path = f"/scan/project/{normalized_target_path}"

        report_file = output_dir / "report.json"
        if report_file.exists():
            report_file.unlink()

        process_result = await run_scanner_container(
            ScannerRunSpec(
                scanner_type="pmd-tool",
                image=str(getattr(settings, "SCANNER_PMD_IMAGE", "vulhunter/pmd-runner:latest")),
                workspace_dir=str(workspace_dir),
                command=_build_pmd_runner_command(runner_target_path, selected_ruleset),
                timeout_seconds=600,
                env={},
                expected_exit_codes=[0, 4],
                artifact_paths=["output/report.json"],
            )
        )

        if _is_scan_task_cancelled("pmd", task_id):
            await _update_task_state("interrupted", error_message="扫描任务已中止（用户操作）")
            return

        if process_result.exit_code not in {0, 4}:
            error_message = str(process_result.error or f"PMD 扫描失败 (exit_code={process_result.exit_code})")
            await _update_task_state("failed", error_message=error_message)
            return

        try:
            payload = _read_pmd_report(workspace_dir)
        except (RuntimeError, ValueError) as exc:
            await _update_task_state("failed", error_message=str(exc))
            return

        findings: List[Dict[str, Any]] = []
        files = payload.get("files", [])
        for file_info in files if isinstance(files, list) else []:
            if not isinstance(file_info, dict):
                continue
            normalized_file_path = _normalize_pmd_violation_path(str(file_info.get("filename") or ""))
            for violation in file_info.get("violations", []) or []:
                if not isinstance(violation, dict):
                    continue
                findings.append(
                    {
                        "file_path": normalized_file_path,
                        "begin_line": violation.get("beginline"),
                        "end_line": violation.get("endline"),
                        "rule": violation.get("rule"),
                        "ruleset": violation.get("ruleset"),
                        "priority": violation.get("priority"),
                        "message": violation.get("message"),
                    }
                )

        updated_task = await _update_task_state(
            "completed",
            findings=findings,
            files_scanned=len(files) if isinstance(files, list) else 0,
        )
        if updated_task is not None:
            project_metrics_refresher.enqueue(updated_task.project_id)
    except asyncio.CancelledError:
        logger.warning("PMD task %s interrupted by service shutdown", task_id)
        await _update_task_state("interrupted", error_message="扫描任务因服务中断被标记为中止")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.error("Error executing PMD task %s: %s", task_id, exc)
        await _update_task_state("failed", error_message=str(exc))
    finally:
        if workspace_dir is not None:
            cleanup_scan_workspace("pmd", task_id)
        _clear_scan_task_cancel("pmd", task_id)
        if project_root and project_root.startswith("/tmp") and os.path.exists(project_root):
            try:
                shutil.rmtree(project_root, ignore_errors=True)
                logger.info(f"Cleaned up temporary project directory: {project_root}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory {project_root}: {e}")


async def _get_custom_rule_config_or_404(db: AsyncSession, rule_config_id: str) -> PmdRuleConfig:
    result = await db.execute(select(PmdRuleConfig).where(PmdRuleConfig.id == rule_config_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="PMD 自定义规则配置不存在")
    return row


@router.get("/pmd/presets", response_model=list[PmdPresetResponse])
async def list_pmd_presets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = db
    _ = current_user
    return _build_pmd_preset_responses()


@router.get("/pmd/builtin-rulesets", response_model=list[PmdRulesetResponse])
async def list_builtin_pmd_rulesets(
    keyword: Optional[str] = Query(None),
    language: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = db
    _ = current_user
    rows = service_list_builtin_pmd_rulesets(keyword=keyword, language=language, limit=limit)
    return [_build_builtin_pmd_ruleset_response(row) for row in rows]


@router.get("/pmd/builtin-rulesets/{ruleset_id}", response_model=PmdRulesetResponse)
async def get_builtin_pmd_ruleset(
    ruleset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = db
    _ = current_user
    try:
        payload = service_get_builtin_pmd_ruleset_detail(ruleset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _build_builtin_pmd_ruleset_response(payload)


@router.post("/pmd/rule-configs/import", response_model=PmdRulesetResponse)
async def import_pmd_rule_config(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    xml_file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    normalized_name = _normalize_rule_config_name(name)
    filename, raw_xml = await _read_xml_upload(xml_file)

    try:
        parse_pmd_ruleset_xml(raw_xml)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = PmdRuleConfig(
        name=normalized_name,
        description=str(description or "").strip() or None,
        filename=filename,
        xml_content=raw_xml,
        is_active=True,
        created_by=str(getattr(current_user, "id", "") or "") or None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _build_custom_pmd_ruleset_response(row)


@router.get("/pmd/rule-configs", response_model=list[PmdRulesetResponse])
async def list_pmd_rule_configs(
    is_active: Optional[bool] = Query(None),
    keyword: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    query = select(PmdRuleConfig)
    if is_active is not None:
        query = query.where(PmdRuleConfig.is_active.is_(is_active))
    if keyword:
        normalized_keyword = f"%{str(keyword).strip()}%"
        query = query.where(
            PmdRuleConfig.name.ilike(normalized_keyword)
            | PmdRuleConfig.description.ilike(normalized_keyword)
            | PmdRuleConfig.filename.ilike(normalized_keyword)
        )
    query = query.order_by(PmdRuleConfig.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_build_custom_pmd_ruleset_response(row) for row in result.scalars().all()]


@router.get("/pmd/rule-configs/{rule_config_id}", response_model=PmdRulesetResponse)
async def get_pmd_rule_config(
    rule_config_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    row = await _get_custom_rule_config_or_404(db, rule_config_id)
    return _build_custom_pmd_ruleset_response(row)


@router.patch("/pmd/rule-configs/{rule_config_id}", response_model=PmdRulesetResponse)
async def update_pmd_rule_config(
    rule_config_id: str,
    request: PmdRuleConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    row = await _get_custom_rule_config_or_404(db, rule_config_id)

    if request.name is not None:
        row.name = _normalize_rule_config_name(request.name)
    if request.description is not None:
        row.description = str(request.description or "").strip() or None
    if request.is_active is not None:
        row.is_active = bool(request.is_active)

    await db.commit()
    await db.refresh(row)
    return _build_custom_pmd_ruleset_response(row)


@router.delete("/pmd/rule-configs/{rule_config_id}")
async def delete_pmd_rule_config(
    rule_config_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    row = await _get_custom_rule_config_or_404(db, rule_config_id)
    await db.delete(row)
    await db.commit()
    return {"message": "规则配置已删除", "id": rule_config_id}


@router.post("/pmd/scan", response_model=PmdScanTaskResponse)
async def create_pmd_scan(
    request: PmdScanTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    project = await db.get(Project, request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    _require_java_project(project)

    project_root = await _get_project_root(request.project_id)
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail="找不到项目的 zip 文件，请先上传项目 ZIP 文件到 uploads/zip_files 目录",
        )

    scan_task = PmdScanTask(
        project_id=request.project_id,
        name=request.name or f"PMD_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        status="pending",
        target_path=request.target_path,
        ruleset=str(request.ruleset or "security").strip() or "security",
    )
    db.add(scan_task)
    await db.commit()
    response = _build_pmd_scan_task_response(scan_task)
    task_id = response.id
    ruleset = scan_task.ruleset
    await _release_request_db_session(db)
    _launch_static_background_job(
        "pmd",
        task_id,
        _execute_pmd_scan(task_id, project_root, request.target_path, ruleset),
    )
    return response


@router.get("/pmd/tasks", response_model=list[PmdScanTaskResponse])
async def list_pmd_tasks(
    project_id: Optional[str] = Query(None, description="按项目ID过滤"),
    status: Optional[str] = Query(None, description="按状态过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    query = select(PmdScanTask)
    if project_id:
        query = query.where(PmdScanTask.project_id == project_id)
    if status:
        query = query.where(PmdScanTask.status == status)
    query = query.order_by(PmdScanTask.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/pmd/tasks/{task_id}", response_model=PmdScanTaskResponse)
async def get_pmd_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    result = await db.execute(select(PmdScanTask).where(PmdScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/pmd/tasks/{task_id}/interrupt")
async def interrupt_pmd_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    result = await db.execute(select(PmdScanTask).where(PmdScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status in {"completed", "failed", "interrupted"}:
        return {
            "message": f"任务当前状态为 {task.status}，无需中止",
            "task_id": task_id,
            "status": task.status,
        }

    _request_scan_task_cancel("pmd", task_id)
    task.status = "interrupted"
    if not task.error_message:
        task.error_message = "扫描任务已中止（用户操作）"
    _sync_task_scan_duration(task)
    await db.commit()
    return {"message": "任务已中止", "task_id": task_id, "status": "interrupted"}


@router.delete("/pmd/tasks/{task_id}")
async def delete_pmd_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    result = await db.execute(select(PmdScanTask).where(PmdScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    await db.delete(task)
    await db.commit()
    return {"message": "任务已删除", "task_id": task_id}


@router.get("/pmd/tasks/{task_id}/findings", response_model=list[PmdFindingResponse])
async def get_pmd_findings(
    task_id: str,
    status: Optional[str] = Query(None, description="按状态过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    task_result = await db.execute(select(PmdScanTask).where(PmdScanTask.id == task_id))
    if not task_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")

    query = select(PmdFinding).where(PmdFinding.scan_task_id == task_id)
    if status:
        query = query.where(PmdFinding.status == status)
    query = query.order_by(PmdFinding.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/pmd/tasks/{task_id}/findings/{finding_id}", response_model=PmdFindingResponse)
async def get_pmd_finding(
    task_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    task_result = await db.execute(select(PmdScanTask).where(PmdScanTask.id == task_id))
    if not task_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")

    finding_result = await db.execute(
        select(PmdFinding).where(
            (PmdFinding.id == finding_id) & (PmdFinding.scan_task_id == task_id)
        )
    )
    finding = finding_result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="PMD 问题不存在")
    return finding


@router.post("/pmd/findings/{finding_id}/status")
async def update_pmd_finding_status(
    finding_id: str,
    status: str = Query(..., description="状态: open, verified, false_positive"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    _ = current_user
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in {"open", "verified", "false_positive"}:
        raise HTTPException(status_code=400, detail="status 必须为 open/verified/false_positive")

    result = await db.execute(select(PmdFinding).where(PmdFinding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="PMD 问题不存在")

    finding.status = normalized_status
    await db.commit()
    return {"message": "状态更新成功", "finding_id": finding_id, "status": finding.status}
