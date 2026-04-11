import asyncio
import hashlib
import json
import logging
import os
import uuid
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.bandit import BanditFinding, BanditRuleState, BanditScanTask
from app.db.static_finding_paths import (
    normalize_static_scan_file_path,
    resolve_static_finding_location,
)
from app.models.gitleaks import GitleaksFinding, GitleaksRule, GitleaksScanTask
from app.models.opengrep import OpengrepFinding, OpengrepRule, OpengrepScanTask
from app.models.phpstan import PhpstanFinding, PhpstanScanTask
from app.models.project import Project
from app.models.user import User
from app.services.gitleaks_rules_seed import ensure_builtin_gitleaks_rules
from app.services.bandit_rules_snapshot import (
    load_bandit_builtin_snapshot,
    update_bandit_builtin_snapshot_rule,
)
from app.services.llm_rule.repo_cache_manager import GlobalRepoCacheManager
from app.services.opengrep_confidence import (
    count_high_confidence_findings_by_task_ids as shared_count_high_confidence_findings_by_task_ids,
    extract_finding_payload_confidence as shared_extract_finding_payload_confidence,
    extract_rule_lookup_keys as shared_extract_rule_lookup_keys,
    normalize_confidence as shared_normalize_confidence,
)
from app.services.rule import get_rule_by_patch, validate_generic_rule
from app.services.upload.upload_manager import UploadManager

from app.api.v1.endpoints.static_tasks_shared import (
    _cleanup_incorrect_rules,
    _clear_scan_task_cancel,
    copy_project_tree_to_scan_dir,
    _dt_to_iso,
    _ensure_opengrep_xdg_dirs,
    _get_project_root,
    _get_user_config,
    _is_scan_task_cancelled,
    _is_test_like_directory,
    _launch_static_background_job,
    _pop_scan_container,
    _register_scan_container,
    _release_request_db_session,
    _resolve_backend_venv_executable,
    _normalize_llm_config_error_message,
    _record_scan_progress,
    _request_scan_task_cancel,
    _run_subprocess_with_tracking,
    _sync_task_scan_duration,
    _utc_now_iso,
    _validate_user_llm_config,
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
from app.services.project_metrics import project_metrics_refresher
from app.services.scanner_runner import ScannerRunSpec, run_scanner_container

router = APIRouter()

class BanditScanTaskCreate(BaseModel):
    """创建 Bandit 扫描任务请求"""

    project_id: str = Field(..., description="项目ID")
    name: Optional[str] = Field(None, description="任务名称")
    target_path: str = Field(".", description="扫描目标路径，相对于项目根目录")
    severity_level: str = Field("medium", description="最低严重程度: low, medium, high")
    confidence_level: str = Field("medium", description="最低置信度: low, medium, high")


class BanditScanTaskResponse(BaseModel):
    """Bandit 扫描任务响应"""

    id: str
    project_id: str
    name: str
    status: str
    target_path: str
    severity_level: str
    confidence_level: str
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


class BanditFindingResponse(BaseModel):
    """Bandit 扫描发现响应"""

    id: str
    scan_task_id: str
    test_id: str
    test_name: str
    issue_severity: str
    issue_confidence: str
    file_path: str
    line_number: Optional[int]
    resolved_file_path: Optional[str] = None
    resolved_line_start: Optional[int] = None
    code_snippet: Optional[str]
    issue_text: Optional[str]
    more_info: Optional[str]
    status: str

    model_config = ConfigDict(from_attributes=True)


def _build_bandit_scan_task_response(task: BanditScanTask) -> BanditScanTaskResponse:
    return BanditScanTaskResponse(
        id=str(task.id),
        project_id=str(task.project_id),
        name=str(task.name or ""),
        status=str(task.status or "pending"),
        target_path=str(task.target_path or "."),
        severity_level=str(task.severity_level or "medium"),
        confidence_level=str(task.confidence_level or "medium"),
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


# Bandit integration: 规则页响应与更新请求模型（启停/删除状态会影响静态扫描执行）。
class BanditRuleResponse(BaseModel):
    id: str = Field(..., description="规则唯一键（Bandit test_id）")
    test_id: str
    name: str
    description: str
    description_summary: str
    checks: List[str]
    source: str
    bandit_version: str
    is_active: bool
    is_deleted: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class BanditRuleEnabledUpdateRequest(BaseModel):
    is_active: bool


class BanditRuleBatchEnabledUpdateRequest(BaseModel):
    rule_ids: Optional[List[str]] = None
    source: Optional[str] = None
    keyword: Optional[str] = None
    current_is_active: Optional[bool] = None
    is_active: bool


class BanditRuleDeletedUpdateRequest(BaseModel):
    is_deleted: bool


class BanditRuleBatchDeletedUpdateRequest(BaseModel):
    rule_ids: Optional[List[str]] = None
    source: Optional[str] = None
    keyword: Optional[str] = None
    current_is_deleted: Optional[bool] = None
    is_deleted: bool


class BanditRuleUpdateRequest(BaseModel):
    """Bandit 规则编辑请求（仅用于规则页展示字段）。"""

    name: Optional[str] = None
    description_summary: Optional[str] = None
    description: Optional[str] = None
    checks: Optional[List[str]] = None


class BanditRuleUpdateResponse(BaseModel):
    message: str
    rule: BanditRuleResponse


def _missing_bandit_rules_migration_message() -> str:
    return "数据库缺少 bandit_rule_states 表，请先运行 alembic upgrade head"


def _raise_bandit_rules_migration_http_error(exc: ProgrammingError) -> None:
    if "bandit_rule_states" not in str(exc):
        raise exc
    raise HTTPException(status_code=500, detail=_missing_bandit_rules_migration_message()) from exc


def _normalize_bandit_rule_id(raw_rule_id: Any) -> str:
    return str(raw_rule_id or "").strip().upper()


def _normalize_bandit_rule_checks(raw_checks: Optional[List[str]]) -> List[str]:
    """规范化可编辑的 checks 字段，过滤空项并去重。"""
    if not isinstance(raw_checks, list):
        return []
    normalized: List[str] = []
    for item in raw_checks:
        text = str(item or "").strip()
        if not text:
            continue
        if text not in normalized:
            normalized.append(text)
    return normalized


def _extract_bandit_snapshot_rules() -> List[Dict[str, Any]]:
    try:
        payload = load_bandit_builtin_snapshot()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Bandit 内置规则快照不存在: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Bandit 内置规则快照格式错误: {exc}") from exc
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        return []
    normalized_rules: List[Dict[str, Any]] = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        test_id = _normalize_bandit_rule_id(raw.get("test_id"))
        if not test_id:
            continue
        checks = raw.get("checks")
        normalized_checks = (
            [str(item).strip() for item in checks if str(item).strip()]
            if isinstance(checks, list)
            else []
        )
        normalized_rules.append(
            {
                "id": test_id,
                "test_id": test_id,
                "name": str(raw.get("name") or "").strip() or test_id,
                "description": str(raw.get("description") or "").strip(),
                "description_summary": str(raw.get("description_summary") or "").strip(),
                "checks": normalized_checks,
                "source": str(raw.get("source") or "builtin").strip() or "builtin",
                "bandit_version": str(raw.get("bandit_version") or "").strip(),
            }
        )
    normalized_rules.sort(key=lambda item: item["test_id"])
    return normalized_rules


async def _load_bandit_rule_states(db: AsyncSession) -> Dict[str, BanditRuleState]:
    try:
        result = await db.execute(select(BanditRuleState))
    except ProgrammingError as exc:
        _raise_bandit_rules_migration_http_error(exc)
    rows = result.scalars().all()
    return {_normalize_bandit_rule_id(row.test_id): row for row in rows}


def _merge_bandit_rule_payload(
    *,
    snapshot_rules: List[Dict[str, Any]],
    states_by_test_id: Dict[str, BanditRuleState],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for item in snapshot_rules:
        test_id = item["test_id"]
        state = states_by_test_id.get(test_id)
        merged.append(
            {
                **item,
                "is_active": bool(state.is_active) if state is not None else True,
                "is_deleted": bool(state.is_deleted) if state is not None else False,
                "created_at": state.created_at if state is not None else None,
                "updated_at": state.updated_at if state is not None else None,
            }
        )
    return merged


def _resolve_bandit_effective_rule_ids(
    *,
    snapshot_rules: List[Dict[str, Any]],
    states_by_test_id: Dict[str, BanditRuleState],
) -> List[str]:
    merged_rules = _merge_bandit_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_test_id=states_by_test_id,
    )
    return [
        str(item["test_id"])
        for item in merged_rules
        if not bool(item.get("is_deleted")) and bool(item.get("is_active"))
    ]


async def _resolve_bandit_scan_rule_ids(db: AsyncSession) -> List[str]:
    snapshot_rules = _extract_bandit_snapshot_rules()
    states_by_test_id = await _load_bandit_rule_states(db)
    rule_ids = _resolve_bandit_effective_rule_ids(
        snapshot_rules=snapshot_rules,
        states_by_test_id=states_by_test_id,
    )
    if not rule_ids:
        raise RuntimeError("无可执行 Bandit 规则，请先在规则页启用至少 1 条规则")
    return rule_ids


def _normalize_bandit_level(value: Any, *, fallback: str = "medium") -> str:
    """规范化 bandit 等级参数，统一为 low/medium/high。"""
    normalized = str(value or "").strip().lower()
    if normalized in {"low", "medium", "high"}:
        return normalized
    return fallback


def _parse_bandit_output_payload(payload: Any) -> List[Dict[str, Any]]:
    """解析 Bandit JSON 输出并统一返回 issue 列表。"""
    if payload is None:
        return []
    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            return [item for item in results if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError("Unexpected bandit output type")
# Bandit integration: 后台执行 Bandit 扫描任务并持久化结果。
async def _execute_bandit_scan(
    task_id: str,
    project_root: str,
    target_path: str,
    severity_level: str = "medium",
    confidence_level: str = "medium",
) -> None:
    project_id: Optional[str] = None
    workspace_dir: Optional[Path] = None
    active_container_id: Optional[str] = None

    async def _update_task_state(
        status: str,
        *,
        error_message: Optional[str] = None,
        findings: Optional[List[Dict[str, Any]]] = None,
        high_count: int = 0,
        medium_count: int = 0,
        low_count: int = 0,
        scanned_file_count: int = 0,
    ) -> Optional[BanditScanTask]:
        async with async_session_factory() as db:
            result = await db.execute(select(BanditScanTask).where(BanditScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return None
            if findings:
                for finding in findings:
                    db.add(
                        BanditFinding(
                            scan_task_id=task_id,
                            test_id=str(finding.get("test_id") or "unknown"),
                            test_name=str(finding.get("test_name") or "unknown"),
                            issue_severity=str(finding.get("issue_severity") or "LOW").strip().upper(),
                            issue_confidence=str(finding.get("issue_confidence") or "LOW").strip().upper(),
                            file_path=str(finding.get("file_path") or ""),
                            line_number=finding.get("line_number"),
                            code_snippet=str(finding.get("code") or "")[:2000] or None,
                            issue_text=str(finding.get("issue_text") or "")[:4000] or None,
                            more_info=str(finding.get("more_info") or "")[:1000] or None,
                            status="open",
                        )
                    )

            task.status = status
            if error_message is not None:
                task.error_message = error_message[:500] if error_message else None
            if status == "completed":
                task.severity_level = _normalize_bandit_level(severity_level, fallback="medium")
                task.confidence_level = _normalize_bandit_level(confidence_level, fallback="medium")
                task.total_findings = len(findings or [])
                task.high_count = high_count
                task.medium_count = medium_count
                task.low_count = low_count
                task.files_scanned = scanned_file_count
            _sync_task_scan_duration(task)
            await db.commit()
            return task

    try:
        async with async_session_factory() as db:
            result = await db.execute(select(BanditScanTask).where(BanditScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                logger.error(f"Bandit task {task_id} not found")
                return
            project_id = task.project_id
            if _is_scan_task_cancelled("bandit", task_id) or task.status == "interrupted":
                task.status = "interrupted"
                task.error_message = task.error_message or "扫描任务已中止（用户操作）"
                _sync_task_scan_duration(task)
                await db.commit()
                return
            task.status = "running"
            await db.commit()

        workspace_dir = ensure_scan_workspace("bandit", task_id)
        project_dir = ensure_scan_project_dir("bandit", task_id)
        output_dir = ensure_scan_output_dir("bandit", task_id)
        logs_dir = ensure_scan_logs_dir("bandit", task_id)
        meta_dir = ensure_scan_meta_dir("bandit", task_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)

        shutil.rmtree(project_dir, ignore_errors=True)
        copy_project_tree_to_scan_dir(project_root, project_dir)

        full_target_path = os.path.join(str(project_dir), target_path)
        if not os.path.exists(full_target_path):
            await _update_task_state("failed", error_message=f"Target path {full_target_path} not found")
            logger.error(f"Bandit target path not found: {full_target_path}")
            return

        normalized_severity = _normalize_bandit_level(severity_level, fallback="medium")
        normalized_confidence = _normalize_bandit_level(confidence_level, fallback="medium")
        runner_target_path = Path("/scan/project")
        normalized_target_path = str(target_path or ".").strip()
        if normalized_target_path not in {"", "."}:
            runner_target_path = runner_target_path / normalized_target_path
        async with async_session_factory() as db:
            executable_rule_ids = await _resolve_bandit_scan_rule_ids(db)

        findings_to_persist: List[Dict[str, Any]] = []
        high_count = 0
        medium_count = 0
        low_count = 0
        scanned_files: set[str] = set()
        report_file = output_dir / "report.json"

        def _on_container_started(container_id: str) -> None:
            nonlocal active_container_id
            active_container_id = container_id
            _register_scan_container("bandit", task_id, container_id)

        try:
            cmd = [
                "bandit",
                "-r",
                str(runner_target_path),
                "-f",
                "json",
                "-o",
                "/scan/output/report.json",
                "--severity-level",
                normalized_severity,
                "--confidence-level",
                normalized_confidence,
                "-t",
                ",".join(executable_rule_ids),
                "-q",
            ]
            logger.info(f"Executing bandit for task {task_id}: {' '.join(cmd)}")
            process_result = await run_scanner_container(
                ScannerRunSpec(
                    scanner_type="bandit",
                    image=str(
                        getattr(settings, "SCANNER_BANDIT_IMAGE", "vulhunter/bandit-runner:latest")
                    ),
                    workspace_dir=str(workspace_dir),
                    command=cmd,
                    timeout_seconds=600,
                    env={},
                    expected_exit_codes=[0, 1],
                    artifact_paths=["output/report.json"],
                ),
                on_container_started=_on_container_started,
            )

            if _is_scan_task_cancelled("bandit", task_id):
                await _update_task_state("interrupted", error_message="扫描任务已中止（用户操作）")
                return

            if process_result.exit_code > 1:
                error_msg = process_result.error or "Unknown error"
                await _update_task_state("failed", error_message=str(error_msg))
                logger.error(f"Bandit task {task_id} failed: {error_msg}")
                return

            raw_payload: Any = {}
            if report_file.exists():
                with open(report_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
                if content:
                    try:
                        raw_payload = json.loads(content)
                    except json.JSONDecodeError as exc:
                        await _update_task_state(
                            "failed",
                            error_message=f"Failed to parse Bandit JSON output: {exc}",
                        )
                        logger.error(f"Failed to parse Bandit output for task {task_id}: {exc}")
                        return

            findings = _parse_bandit_output_payload(raw_payload)
            for finding in findings:
                try:
                    severity = str(finding.get("issue_severity") or "LOW").strip().upper()
                    confidence = str(finding.get("issue_confidence") or "LOW").strip().upper()
                    file_path = normalize_static_scan_file_path(
                        str(finding.get("filename") or "").strip(),
                        "/scan/project",
                    )
                    if file_path:
                        scanned_files.add(file_path)
                    if severity == "HIGH":
                        high_count += 1
                    elif severity == "MEDIUM":
                        medium_count += 1
                    else:
                        low_count += 1
                    findings_to_persist.append(
                        {
                            **finding,
                            "issue_severity": severity if severity in {"HIGH", "MEDIUM", "LOW"} else "LOW",
                            "issue_confidence": confidence if confidence in {"HIGH", "MEDIUM", "LOW"} else "LOW",
                            "file_path": file_path or "",
                        }
                    )
                except Exception as exc:
                    logger.error(f"Error processing Bandit finding for task {task_id}: {exc}")
        except Exception:
            raise

        if _is_scan_task_cancelled("bandit", task_id):
            await _update_task_state("interrupted", error_message="扫描任务已中止（用户操作）")
            return

        updated_task = await _update_task_state(
            "completed",
            findings=findings_to_persist,
            high_count=high_count,
            medium_count=medium_count,
            low_count=low_count,
            scanned_file_count=len(scanned_files),
        )
        if updated_task is not None:
            project_metrics_refresher.enqueue(updated_task.project_id)
    except asyncio.CancelledError:
        logger.warning(f"Bandit task {task_id} interrupted by service shutdown")
        await _update_task_state("interrupted", error_message="扫描任务因服务中断被标记为中止")
        raise
    except Exception as exc:
        logger.error(f"Error executing Bandit task {task_id}: {exc}")
        await _update_task_state("failed", error_message=str(exc))
    finally:
        _pop_scan_container("bandit", task_id)
        if workspace_dir is not None:
            cleanup_scan_workspace("bandit", task_id)
        _clear_scan_task_cancel("bandit", task_id)
        if project_root and project_root.startswith("/tmp") and os.path.exists(project_root):
            try:
                shutil.rmtree(project_root, ignore_errors=True)
                logger.info(f"Cleaned up temporary project directory: {project_root}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory {project_root}: {e}")


@router.get("/bandit/rules", response_model=List[BanditRuleResponse])
async def list_bandit_rules(
    is_active: Optional[bool] = Query(None, description="按启用状态过滤"),
    source: Optional[str] = Query(None, description="按来源过滤"),
    keyword: Optional[str] = Query(None, description="按 test_id/name/description 关键词过滤"),
    deleted: str = Query("false", description="软删除筛选：false(默认)/true/all"),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    # Bandit integration: 规则来源固定为 builtin snapshot，状态来自 bandit_rule_states。
    snapshot_rules = _extract_bandit_snapshot_rules()
    states_by_test_id = await _load_bandit_rule_states(db)
    merged_rules = _merge_bandit_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_test_id=states_by_test_id,
    )

    filtered: List[Dict[str, Any]] = []
    keyword_text = str(keyword or "").strip().lower()
    source_text = str(source or "").strip()
    deleted_text = str(deleted or "false").strip().lower()
    if deleted_text not in {"false", "true", "all"}:
        raise HTTPException(status_code=400, detail="deleted 必须为 false/true/all")
    for item in merged_rules:
        if deleted_text != "all":
            target_deleted = deleted_text == "true"
            if bool(item["is_deleted"]) != target_deleted:
                continue
        if is_active is not None and bool(item["is_active"]) != is_active:
            continue
        if source_text and item["source"] != source_text:
            continue
        if keyword_text:
            search_blob = " ".join(
                [
                    str(item["test_id"]),
                    str(item["name"]),
                    str(item["description"]),
                    str(item["description_summary"]),
                ]
            ).lower()
            if keyword_text not in search_blob:
                continue
        filtered.append(item)

    return filtered[skip : skip + limit]


@router.get("/bandit/rules/{rule_id}", response_model=BanditRuleResponse)
async def get_bandit_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    normalized_rule_id = _normalize_bandit_rule_id(rule_id)
    snapshot_rules = _extract_bandit_snapshot_rules()
    states_by_test_id = await _load_bandit_rule_states(db)
    merged_rules = _merge_bandit_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_test_id=states_by_test_id,
    )
    for item in merged_rules:
        if item["test_id"] == normalized_rule_id:
            return item
    raise HTTPException(status_code=404, detail="Bandit 规则不存在")


@router.patch("/bandit/rules/{rule_id}", response_model=BanditRuleUpdateResponse)
async def update_bandit_rule(
    rule_id: str,
    request: BanditRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    # Bandit integration: 规则编辑用于维护快照字段，扫描命令仍按 test_id 执行。
    normalized_rule_id = _normalize_bandit_rule_id(rule_id)
    known_rule_ids = {item["test_id"] for item in _extract_bandit_snapshot_rules()}
    if normalized_rule_id not in known_rule_ids:
        raise HTTPException(status_code=404, detail="Bandit 规则不存在")

    updates: Dict[str, Any] = {}
    if request.name is not None:
        name = str(request.name).strip()
        if not name:
            raise HTTPException(status_code=400, detail="name 不能为空")
        updates["name"] = name
    if request.description_summary is not None:
        updates["description_summary"] = str(request.description_summary).strip()
    if request.description is not None:
        updates["description"] = str(request.description).strip()
    if request.checks is not None:
        updates["checks"] = _normalize_bandit_rule_checks(request.checks)

    if not updates:
        raise HTTPException(status_code=400, detail="至少需要提供一个可更新字段")

    try:
        update_bandit_builtin_snapshot_rule(
            rule_id=normalized_rule_id,
            updates=updates,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Bandit 规则不存在") from exc
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"更新 Bandit 规则快照失败: {exc}") from exc

    snapshot_rules = _extract_bandit_snapshot_rules()
    states_by_test_id = await _load_bandit_rule_states(db)
    merged_rules = _merge_bandit_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_test_id=states_by_test_id,
    )
    for item in merged_rules:
        if item["test_id"] == normalized_rule_id:
            return {"message": "规则更新成功", "rule": item}

    raise HTTPException(status_code=404, detail="Bandit 规则不存在")


@router.post("/bandit/rules/{rule_id}/enabled")
async def update_bandit_rule_enabled(
    rule_id: str,
    request: BanditRuleEnabledUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    normalized_rule_id = _normalize_bandit_rule_id(rule_id)
    known_rule_ids = {item["test_id"] for item in _extract_bandit_snapshot_rules()}
    if normalized_rule_id not in known_rule_ids:
        raise HTTPException(status_code=404, detail="Bandit 规则不存在")

    try:
        result = await db.execute(
            select(BanditRuleState).where(BanditRuleState.test_id == normalized_rule_id)
        )
    except ProgrammingError as exc:
        _raise_bandit_rules_migration_http_error(exc)
    state = result.scalar_one_or_none()
    if state is None:
        state = BanditRuleState(
            id=str(uuid.uuid4()),
            test_id=normalized_rule_id,
            is_active=request.is_active,
            is_deleted=False,
        )
        db.add(state)
    else:
        if bool(state.is_deleted):
            raise HTTPException(status_code=409, detail="规则已删除，请先恢复后再启用/禁用")
        state.is_active = request.is_active
    await db.commit()
    await db.refresh(state)

    return {
        "message": f"规则已{'启用' if state.is_active else '禁用'}",
        "rule_id": normalized_rule_id,
        "is_active": bool(state.is_active),
    }


@router.post("/bandit/rules/batch-enabled")
@router.post("/bandit/rules/batch/enabled", include_in_schema=False)
async def batch_update_bandit_rules_enabled(
    request: BanditRuleBatchEnabledUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    snapshot_rules = _extract_bandit_snapshot_rules()
    states_by_test_id = await _load_bandit_rule_states(db)
    merged_rules = _merge_bandit_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_test_id=states_by_test_id,
    )

    rule_ids_filter = (
        {_normalize_bandit_rule_id(rule_id) for rule_id in (request.rule_ids or []) if rule_id}
        if request.rule_ids
        else None
    )
    keyword_text = str(request.keyword or "").strip().lower()
    source_text = str(request.source or "").strip()
    selected_rule_ids: List[str] = []

    for item in merged_rules:
        if bool(item["is_deleted"]):
            continue
        if rule_ids_filter is not None and item["test_id"] not in rule_ids_filter:
            continue
        if source_text and item["source"] != source_text:
            continue
        if request.current_is_active is not None and bool(item["is_active"]) != request.current_is_active:
            continue
        if keyword_text:
            search_blob = " ".join(
                [
                    str(item["test_id"]),
                    str(item["name"]),
                    str(item["description"]),
                    str(item["description_summary"]),
                ]
            ).lower()
            if keyword_text not in search_blob:
                continue
        selected_rule_ids.append(item["test_id"])

    if not selected_rule_ids:
        return {
            "message": "没有找到符合条件的规则",
            "updated_count": 0,
            "is_active": request.is_active,
        }

    try:
        existing_result = await db.execute(
            select(BanditRuleState).where(BanditRuleState.test_id.in_(selected_rule_ids))
        )
    except ProgrammingError as exc:
        _raise_bandit_rules_migration_http_error(exc)
    existing_rows = existing_result.scalars().all()
    existing_by_rule_id = {_normalize_bandit_rule_id(row.test_id): row for row in existing_rows}

    updated_count = 0
    for rule_id in selected_rule_ids:
        existing = existing_by_rule_id.get(rule_id)
        if existing is None:
            db.add(
                BanditRuleState(
                    id=str(uuid.uuid4()),
                    test_id=rule_id,
                    is_active=request.is_active,
                )
            )
        else:
            existing.is_active = request.is_active
        updated_count += 1
    await db.commit()

    return {
        "message": f"已{'启用' if request.is_active else '禁用'} {updated_count} 条规则",
        "updated_count": updated_count,
        "is_active": request.is_active,
    }


@router.post("/bandit/rules/{rule_id}/delete")
async def delete_bandit_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    normalized_rule_id = _normalize_bandit_rule_id(rule_id)
    known_rule_ids = {item["test_id"] for item in _extract_bandit_snapshot_rules()}
    if normalized_rule_id not in known_rule_ids:
        raise HTTPException(status_code=404, detail="Bandit 规则不存在")

    try:
        result = await db.execute(
            select(BanditRuleState).where(BanditRuleState.test_id == normalized_rule_id)
        )
    except ProgrammingError as exc:
        _raise_bandit_rules_migration_http_error(exc)

    state = result.scalar_one_or_none()
    if state is None:
        state = BanditRuleState(
            id=str(uuid.uuid4()),
            test_id=normalized_rule_id,
            is_active=False,
            is_deleted=True,
        )
        db.add(state)
    else:
        state.is_active = False
        state.is_deleted = True
    await db.commit()
    return {"message": "规则已删除", "rule_id": normalized_rule_id, "is_deleted": True}


@router.post("/bandit/rules/{rule_id}/restore")
async def restore_bandit_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    normalized_rule_id = _normalize_bandit_rule_id(rule_id)
    known_rule_ids = {item["test_id"] for item in _extract_bandit_snapshot_rules()}
    if normalized_rule_id not in known_rule_ids:
        raise HTTPException(status_code=404, detail="Bandit 规则不存在")

    try:
        result = await db.execute(
            select(BanditRuleState).where(BanditRuleState.test_id == normalized_rule_id)
        )
    except ProgrammingError as exc:
        _raise_bandit_rules_migration_http_error(exc)

    state = result.scalar_one_or_none()
    if state is None:
        state = BanditRuleState(
            id=str(uuid.uuid4()),
            test_id=normalized_rule_id,
            is_active=True,
            is_deleted=False,
        )
        db.add(state)
    else:
        state.is_deleted = False
    await db.commit()
    return {"message": "规则已恢复", "rule_id": normalized_rule_id, "is_deleted": False}


@router.post("/bandit/rules/batch-delete")
@router.post("/bandit/rules/batch/delete", include_in_schema=False)
async def batch_delete_bandit_rules(
    request: BanditRuleBatchDeletedUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    payload = BanditRuleBatchDeletedUpdateRequest(
        rule_ids=request.rule_ids,
        source=request.source,
        keyword=request.keyword,
        current_is_deleted=request.current_is_deleted,
        is_deleted=True,
    )
    return await _batch_update_bandit_rules_deleted(payload, db)


@router.post("/bandit/rules/batch-restore")
@router.post("/bandit/rules/batch/restore", include_in_schema=False)
async def batch_restore_bandit_rules(
    request: BanditRuleBatchDeletedUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    payload = BanditRuleBatchDeletedUpdateRequest(
        rule_ids=request.rule_ids,
        source=request.source,
        keyword=request.keyword,
        current_is_deleted=request.current_is_deleted,
        is_deleted=False,
    )
    return await _batch_update_bandit_rules_deleted(payload, db)


async def _batch_update_bandit_rules_deleted(
    request: BanditRuleBatchDeletedUpdateRequest,
    db: AsyncSession,
):
    snapshot_rules = _extract_bandit_snapshot_rules()
    states_by_test_id = await _load_bandit_rule_states(db)
    merged_rules = _merge_bandit_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_test_id=states_by_test_id,
    )
    rule_ids_filter = (
        {_normalize_bandit_rule_id(rule_id) for rule_id in (request.rule_ids or []) if rule_id}
        if request.rule_ids
        else None
    )
    keyword_text = str(request.keyword or "").strip().lower()
    source_text = str(request.source or "").strip()
    selected_rule_ids: List[str] = []

    for item in merged_rules:
        if rule_ids_filter is not None and item["test_id"] not in rule_ids_filter:
            continue
        if source_text and item["source"] != source_text:
            continue
        if request.current_is_deleted is not None and bool(item["is_deleted"]) != request.current_is_deleted:
            continue
        if keyword_text:
            search_blob = " ".join(
                [
                    str(item["test_id"]),
                    str(item["name"]),
                    str(item["description"]),
                    str(item["description_summary"]),
                ]
            ).lower()
            if keyword_text not in search_blob:
                continue
        selected_rule_ids.append(item["test_id"])

    if not selected_rule_ids:
        return {
            "message": "没有找到符合条件的规则",
            "updated_count": 0,
            "is_deleted": request.is_deleted,
        }

    try:
        existing_result = await db.execute(
            select(BanditRuleState).where(BanditRuleState.test_id.in_(selected_rule_ids))
        )
    except ProgrammingError as exc:
        _raise_bandit_rules_migration_http_error(exc)

    existing_rows = existing_result.scalars().all()
    existing_by_rule_id = {_normalize_bandit_rule_id(row.test_id): row for row in existing_rows}

    updated_count = 0
    for rule_id in selected_rule_ids:
        existing = existing_by_rule_id.get(rule_id)
        if existing is None:
            db.add(
                BanditRuleState(
                    id=str(uuid.uuid4()),
                    test_id=rule_id,
                    is_active=not request.is_deleted,
                    is_deleted=request.is_deleted,
                )
            )
        else:
            existing.is_deleted = request.is_deleted
            if request.is_deleted:
                existing.is_active = False
        updated_count += 1
    await db.commit()

    return {
        "message": f"已{'删除' if request.is_deleted else '恢复'} {updated_count} 条规则",
        "updated_count": updated_count,
        "is_deleted": request.is_deleted,
    }


@router.post("/bandit/scan", response_model=BanditScanTaskResponse)
async def create_bandit_scan(
    request: BanditScanTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """创建 Bandit 静态扫描任务。"""
    project = await db.get(Project, request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    project_root = await _get_project_root(request.project_id)
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail="找不到项目的 zip 文件，请先上传项目 ZIP 文件到 uploads/zip_files 目录",
        )

    scan_task = BanditScanTask(
        project_id=request.project_id,
        name=request.name or f"Bandit_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        status="pending",
        target_path=request.target_path,
        severity_level=_normalize_bandit_level(request.severity_level),
        confidence_level=_normalize_bandit_level(request.confidence_level),
    )
    db.add(scan_task)
    await db.commit()
    response = _build_bandit_scan_task_response(scan_task)
    task_id = response.id
    severity_level = scan_task.severity_level
    confidence_level = scan_task.confidence_level
    await _release_request_db_session(db)
    _launch_static_background_job(
        "bandit",
        task_id,
        _execute_bandit_scan(
            task_id,
            project_root,
            request.target_path,
            severity_level,
            confidence_level,
        ),
    )
    return response


@router.get("/bandit/tasks", response_model=List[BanditScanTaskResponse])
async def list_bandit_tasks(
    project_id: Optional[str] = Query(None, description="按项目ID过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取 Bandit 扫描任务列表。"""
    query = select(BanditScanTask)
    if project_id:
        query = query.where(BanditScanTask.project_id == project_id)
    query = query.order_by(BanditScanTask.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/bandit/tasks/{task_id}", response_model=BanditScanTaskResponse)
async def get_bandit_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取 Bandit 扫描任务详情。"""
    result = await db.execute(select(BanditScanTask).where(BanditScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/bandit/tasks/{task_id}/interrupt")
async def interrupt_bandit_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """中止运行中的 Bandit 扫描任务。"""
    result = await db.execute(select(BanditScanTask).where(BanditScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status in {"completed", "failed", "interrupted"}:
        return {
            "message": f"任务当前状态为 {task.status}，无需中止",
            "task_id": task_id,
            "status": task.status,
        }

    _request_scan_task_cancel("bandit", task_id)
    task.status = "interrupted"
    if not task.error_message:
        task.error_message = "扫描任务已中止（用户操作）"
    _sync_task_scan_duration(task)
    await db.commit()
    return {"message": "任务已中止", "task_id": task_id, "status": "interrupted"}


@router.delete("/bandit/tasks/{task_id}")
async def delete_bandit_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """删除 Bandit 扫描任务及其发现。"""
    result = await db.execute(select(BanditScanTask).where(BanditScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    await db.delete(task)
    await db.commit()
    return {"message": "任务已删除", "task_id": task_id}


@router.get("/bandit/tasks/{task_id}/findings", response_model=List[BanditFindingResponse])
async def get_bandit_findings(
    task_id: str,
    status: Optional[str] = Query(None, description="按状态过滤"),
    severity: Optional[str] = Query(None, description="按严重度过滤: HIGH, MEDIUM, LOW"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取 Bandit 扫描发现列表。"""
    task_result = await db.execute(select(BanditScanTask).where(BanditScanTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    query = select(BanditFinding).where(BanditFinding.scan_task_id == task_id)
    if status:
        query = query.where(BanditFinding.status == status)
    if severity:
        normalized_severity = str(severity).strip().upper()
        if normalized_severity in {"HIGH", "MEDIUM", "LOW"}:
            query = query.where(BanditFinding.issue_severity == normalized_severity)
    query = query.order_by(BanditFinding.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/bandit/tasks/{task_id}/findings/{finding_id}",
    response_model=BanditFindingResponse,
)
async def get_bandit_finding(
    task_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取单条 Bandit 扫描发现详情。"""
    task_result = await db.execute(select(BanditScanTask).where(BanditScanTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    finding_result = await db.execute(
        select(BanditFinding).where(
            (BanditFinding.id == finding_id) & (BanditFinding.scan_task_id == task_id)
        )
    )
    finding = finding_result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Bandit 漏洞不存在")
    project_root = await _get_project_root(task.project_id)
    resolved_file_path, resolved_line_start = resolve_static_finding_location(
        finding.file_path,
        line_start=finding.line_number,
        project_root=project_root,
    )
    return BanditFindingResponse.model_validate(
        {
            **finding.__dict__,
            "resolved_file_path": resolved_file_path,
            "resolved_line_start": resolved_line_start,
        }
    )


@router.post("/bandit/findings/{finding_id}/status")
async def update_bandit_finding_status(
    finding_id: str,
    status: str = Query(..., description="状态: open, verified, false_positive"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """更新 Bandit 扫描发现状态。"""
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in {"open", "verified", "false_positive"}:
        raise HTTPException(status_code=400, detail="status 必须为 open/verified/false_positive")

    result = await db.execute(select(BanditFinding).where(BanditFinding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="Bandit 漏洞不存在")

    finding.status = normalized_status
    await db.commit()
    return {"message": "状态已更新", "finding_id": finding_id, "status": normalized_status}
