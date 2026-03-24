import asyncio
import hashlib
import json
import logging
import os
import uuid
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

from app.models.bandit import BanditFinding, BanditScanTask
from app.models.gitleaks import GitleaksFinding, GitleaksRule, GitleaksScanTask
from app.models.opengrep import OpengrepFinding, OpengrepRule, OpengrepScanTask
from app.models.phpstan import PhpstanFinding, PhpstanRuleState, PhpstanScanTask
from app.models.project import Project
from app.models.user import User
from app.schemas.gitleaks_rules import (
    GitleaksRuleBatchUpdateRequest,
    GitleaksRuleCreateRequest,
    GitleaksRuleResponse,
    GitleaksRuleUpdateRequest,
)
from app.schemas.opengrep import (
    OpengrepRuleCreateRequest,
    OpengrepRulePatchResponse,
    OpengrepRuleTextCreateRequest,
    OpengrepRuleTextResponse,
    OpengrepRuleUpdateRequest,
)
from app.services.gitleaks_rules_seed import ensure_builtin_gitleaks_rules
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
from app.db.static_finding_paths import normalize_static_scan_file_path
from app.services.scanner_runner import ScannerRunSpec, run_scanner_container

router = APIRouter()

class PhpstanScanTaskCreate(BaseModel):
    """创建 PHPStan 扫描任务请求"""

    project_id: str = Field(..., description="项目ID")
    name: Optional[str] = Field(None, description="任务名称")
    target_path: str = Field(".", description="扫描目标路径，相对于项目根目录")
    level: int = Field(8, ge=0, le=9, description="PHPStan 分析级别（0-9）")


class PhpstanScanTaskResponse(BaseModel):
    """PHPStan 扫描任务响应"""

    id: str
    project_id: str
    name: str
    status: str
    target_path: str
    level: int
    total_findings: int
    scan_duration_ms: int
    files_scanned: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class PhpstanFindingResponse(BaseModel):
    """PHPStan 扫描发现响应"""

    id: str
    scan_task_id: str
    file_path: str
    line: Optional[int]
    message: str
    identifier: Optional[str]
    tip: Optional[str]
    status: str

    model_config = ConfigDict(from_attributes=True)


def _build_phpstan_scan_task_response(task: PhpstanScanTask) -> PhpstanScanTaskResponse:
    return PhpstanScanTaskResponse(
        id=str(task.id),
        project_id=str(task.project_id),
        name=str(task.name or ""),
        status=str(task.status or "pending"),
        target_path=str(task.target_path or "."),
        level=int(task.level or 0),
        total_findings=int(task.total_findings or 0),
        scan_duration_ms=int(task.scan_duration_ms or 0),
        files_scanned=int(task.files_scanned or 0),
        error_message=task.error_message,
        created_at=task.created_at or datetime.now(timezone.utc),
        updated_at=task.updated_at,
    )


# PHPStan rules integration: 规则页响应与更新请求模型（仅用于前端展示/启停状态持久化）。
class PhpstanRuleResponse(BaseModel):
    id: str
    package: str
    repo: str
    rule_class: str
    name: str
    description_summary: str
    source_file: str
    source: str
    source_content: Optional[str] = None
    is_active: bool
    is_deleted: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PhpstanRuleEnabledUpdateRequest(BaseModel):
    is_active: bool


class PhpstanRuleBatchEnabledUpdateRequest(BaseModel):
    rule_ids: Optional[List[str]] = None
    source: Optional[str] = None
    keyword: Optional[str] = None
    current_is_active: Optional[bool] = None
    is_active: bool


class PhpstanRuleDeletedUpdateRequest(BaseModel):
    is_deleted: bool


class PhpstanRuleBatchDeletedUpdateRequest(BaseModel):
    rule_ids: Optional[List[str]] = None
    source: Optional[str] = None
    keyword: Optional[str] = None
    current_is_deleted: Optional[bool] = None
    is_deleted: bool


class PhpstanRuleUpdateRequest(BaseModel):
    """PHPStan 规则编辑请求（仅用于规则页展示字段）。"""

    package: Optional[str] = None
    repo: Optional[str] = None
    name: Optional[str] = None
    description_summary: Optional[str] = None
    source_file: Optional[str] = None
    source: Optional[str] = None


class PhpstanRuleUpdateResponse(BaseModel):
    message: str
    rule: PhpstanRuleResponse
def _normalize_phpstan_level(value: Any, *, fallback: int = 8) -> int:
    """规范化 PHPStan level 参数，统一为 0-9。"""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(0, min(9, parsed))


def _parse_phpstan_output_payload(payload_text: str) -> Dict[str, Any]:
    """解析 PHPStan JSON 输出，容忍前缀噪声并返回统一 dict。"""
    text = str(payload_text or "").strip()
    if not text:
        return {}

    parse_targets = [text]
    first_object_index = text.find("{")
    if first_object_index > 0:
        parse_targets.append(text[first_object_index:])

    decoder = json.JSONDecoder()
    last_error: Optional[Exception] = None
    for candidate in parse_targets:
        try:
            output, _ = decoder.raw_decode(candidate)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        if isinstance(output, dict):
            return output
        raise ValueError("Unexpected phpstan output type")

    raise ValueError(f"Invalid phpstan JSON output: {last_error}")


def _missing_phpstan_rules_migration_message() -> str:
    return "数据库缺少 phpstan_rule_states 表，请先运行 alembic upgrade head"


def _raise_phpstan_rules_migration_http_error(exc: ProgrammingError) -> None:
    if "phpstan_rule_states" not in str(exc):
        raise exc
    raise HTTPException(status_code=500, detail=_missing_phpstan_rules_migration_message()) from exc


def _phpstan_rules_snapshot_path() -> Path:
    return Path(__file__).resolve().parents[3] / "db" / "rules_phpstan" / "phpstan_rules_combined.json"


def _phpstan_rule_sources_root_path() -> Path:
    return Path(__file__).resolve().parents[3] / "db" / "rules_phpstan" / "rule_sources"


def _read_phpstan_rule_source_content(repo: str, source_file: str) -> Optional[str]:
    # PHPStan rules integration: 仅用于规则详情源码展示，不参与扫描执行命令构建。
    repo_name = str(repo or "").strip()
    source_relative = str(source_file or "").strip()
    if not repo_name or not source_relative:
        return None

    sources_root = _phpstan_rule_sources_root_path().resolve()
    candidate_path = (sources_root / repo_name / source_relative).resolve()
    try:
        candidate_path.relative_to(sources_root)
    except ValueError:
        return None
    if not candidate_path.exists() or not candidate_path.is_file():
        return None
    try:
        return candidate_path.read_text(encoding="utf-8")
    except Exception:
        return None


def _load_phpstan_rules_snapshot() -> Dict[str, Any]:
    snapshot_path = _phpstan_rules_snapshot_path()
    if not snapshot_path.exists():
        raise HTTPException(status_code=500, detail=f"PHPStan 规则快照不存在: {snapshot_path}")
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"PHPStan 规则快照解析失败: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="PHPStan 规则快照格式错误")
    return payload


def _write_phpstan_rules_snapshot(payload: Dict[str, Any]) -> None:
    """原子写回 PHPStan 规则快照，避免并发写导致脏文件。"""
    snapshot_path = _phpstan_rules_snapshot_path()
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        prefix="phpstan_rules_combined.",
        dir=snapshot_path.parent,
        delete=False,
        encoding="utf-8",
    ) as tmp_file:
        tmp_file.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        tmp_path = Path(tmp_file.name)

    try:
        os.replace(tmp_path, snapshot_path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise


def _update_phpstan_snapshot_rule(rule_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """更新指定规则展示字段并写回快照。"""
    if not updates:
        raise ValueError("至少需要提供一个可更新字段")

    payload = _load_phpstan_rules_snapshot()
    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("PHPStan 规则快照格式错误")

    target_rule: Optional[Dict[str, Any]] = None
    for item in rules:
        if isinstance(item, dict) and str(item.get("id") or "") == rule_id:
            target_rule = item
            break

    if target_rule is None:
        raise KeyError(f"PHPStan 规则不存在: {rule_id}")

    for field, value in updates.items():
        target_rule[field] = value

    payload["count"] = len([item for item in rules if isinstance(item, dict)])
    payload["generated_at"] = _utc_now_iso()
    _write_phpstan_rules_snapshot(payload)
    return target_rule


def _extract_phpstan_snapshot_rules() -> List[Dict[str, Any]]:
    payload = _load_phpstan_rules_snapshot()
    raw_rules = payload.get("rules")
    if not isinstance(raw_rules, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            continue
        rule_id = str(raw.get("id") or "").strip()
        if not rule_id:
            continue
        normalized.append(
            {
                "id": rule_id,
                "package": str(raw.get("package") or "").strip(),
                "repo": str(raw.get("repo") or "").strip(),
                "rule_class": str(raw.get("rule_class") or "").strip(),
                "name": str(raw.get("name") or "").strip() or rule_id,
                "description_summary": str(raw.get("description_summary") or "").strip(),
                "source_file": str(raw.get("source_file") or "").strip(),
                "source": str(raw.get("source") or "official_extension").strip() or "official_extension",
            }
        )
    normalized.sort(key=lambda item: (item["package"], item["rule_class"], item["id"]))
    return normalized


async def _load_phpstan_rule_states(db: AsyncSession) -> Dict[str, PhpstanRuleState]:
    try:
        result = await db.execute(select(PhpstanRuleState))
    except ProgrammingError as exc:
        _raise_phpstan_rules_migration_http_error(exc)
    rows = result.scalars().all()
    return {str(row.rule_id): row for row in rows}


def _merge_phpstan_rule_payload(
    *,
    snapshot_rules: List[Dict[str, Any]],
    states_by_rule_id: Dict[str, PhpstanRuleState],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    for item in snapshot_rules:
        rule_id = item["id"]
        state = states_by_rule_id.get(rule_id)
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


# PHPStan security filter: 仅保留安全相关发现（五类核心 + 高危词兜底）。
_PHPSTAN_SECURITY_CORE_KEYWORDS = (
    # 代码执行 / 命令执行
    "eval(",
    "assert(",
    "create_function",
    "exec(",
    "system(",
    "passthru(",
    "shell_exec(",
    "popen(",
    "proc_open(",
    # SQL 操作
    "sql",
    "mysqli_query",
    "mysql_query",
    "pg_query",
    "pdo::query",
    "pdo::exec",
    "select ",
    "insert ",
    "update ",
    "delete ",
    # 文件操作
    "fopen(",
    "fwrite(",
    "file_get_contents(",
    "file_put_contents(",
    "unlink(",
    "copy(",
    "rename(",
    "move_uploaded_file(",
    "include(",
    "require(",
    "include_once(",
    "require_once(",
    "path traversal",
    # 反序列化
    "unserialize(",
    "maybe_unserialize(",
    "deserializ",
)

_PHPSTAN_SECURITY_FALLBACK_KEYWORDS = (
    "security",
    "unsafe",
    "dangerous",
    "injection",
    "xss",
    "rce",
    "lfi",
    "rfi",
    "xxe",
    "ssti",
    "command execution",
    "code execution",
    "remote code execution",
)


def _is_phpstan_security_finding(message: Dict[str, Any]) -> bool:
    """判断 PHPStan 单条消息是否属于安全相关发现。"""
    text = " ".join(
        [
            str(message.get("message") or ""),
            str(message.get("identifier") or ""),
            str(message.get("tip") or ""),
        ]
    ).lower()
    if not text:
        return False
    if any(keyword in text for keyword in _PHPSTAN_SECURITY_CORE_KEYWORDS):
        return True
    return any(keyword in text for keyword in _PHPSTAN_SECURITY_FALLBACK_KEYWORDS)


def _filter_phpstan_security_messages(messages: Any) -> Dict[str, List[Dict[str, Any]]]:
    """过滤 PHPStan 消息列表，仅返回安全相关项并保留被过滤项计数能力。"""
    if not isinstance(messages, list):
        return {"kept": [], "dropped": []}

    kept: List[Dict[str, Any]] = []
    dropped: List[Dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, dict):
            dropped.append({})
            continue
        if _is_phpstan_security_finding(item):
            kept.append(item)
        else:
            dropped.append(item)
    return {"kept": kept, "dropped": dropped}


async def _execute_phpstan_scan(
    task_id: str,
    project_root: str,
    target_path: str,
    level: int = 8,
) -> None:
    workspace_dir: Optional[Path] = None
    active_container_id: Optional[str] = None

    async def _update_task_state(
        status: str,
        *,
        error_message: Optional[str] = None,
        findings: Optional[List[Dict[str, Any]]] = None,
        files_scanned: int = 0,
    ) -> Optional[PhpstanScanTask]:
        async with async_session_factory() as db:
            result = await db.execute(select(PhpstanScanTask).where(PhpstanScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                return None
            if findings:
                for msg in findings:
                    db.add(
                        PhpstanFinding(
                            scan_task_id=task_id,
                            file_path=str(msg.get("file_path") or "")[:1000],
                            line=msg.get("line"),
                            message=str(msg.get("message") or "")[:4000],
                            identifier=(str(msg.get("identifier") or "")[:500] or None),
                            tip=(str(msg.get("tip") or "")[:2000] or None),
                            status="open",
                        )
                    )
            task.status = status
            if error_message is not None:
                task.error_message = error_message[:500] if error_message else None
            if status == "completed":
                task.level = _normalize_phpstan_level(level)
                task.total_findings = len(findings or [])
                task.files_scanned = files_scanned
            _sync_task_scan_duration(task)
            await db.commit()
            return task

    try:
        async with async_session_factory() as db:
            result = await db.execute(select(PhpstanScanTask).where(PhpstanScanTask.id == task_id))
            task = result.scalar_one_or_none()
            if not task:
                logger.error(f"PHPStan task {task_id} not found")
                return
            if _is_scan_task_cancelled("phpstan", task_id) or task.status == "interrupted":
                task.status = "interrupted"
                task.error_message = task.error_message or "扫描任务已中止（用户操作）"
                _sync_task_scan_duration(task)
                await db.commit()
                return
            task.status = "running"
            await db.commit()

        workspace_dir = ensure_scan_workspace("phpstan", task_id)
        project_dir = ensure_scan_project_dir("phpstan", task_id)
        output_dir = ensure_scan_output_dir("phpstan", task_id)
        logs_dir = ensure_scan_logs_dir("phpstan", task_id)
        meta_dir = ensure_scan_meta_dir("phpstan", task_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)

        shutil.rmtree(project_dir, ignore_errors=True)
        copy_project_tree_to_scan_dir(project_root, project_dir)

        full_target_path = os.path.join(str(project_dir), target_path)
        if not os.path.exists(full_target_path):
            await _update_task_state("failed", error_message=f"Target path {full_target_path} not found")
            logger.error(f"PHPStan target path not found: {full_target_path}")
            return

        normalized_level = _normalize_phpstan_level(level)
        runner_target_path = Path("/scan/project")
        normalized_target_path = str(target_path or ".").strip()
        if normalized_target_path not in {"", "."}:
            runner_target_path = runner_target_path / normalized_target_path

        cmd = [
            "phpstan",
            "analyse",
            str(runner_target_path),
            "--error-format=json",
            "--no-progress",
            "--no-interaction",
            f"--level={normalized_level}",
        ]
        logger.info(f"Executing phpstan for task {task_id}: {' '.join(cmd)}")

        def _on_container_started(container_id: str) -> None:
            nonlocal active_container_id
            active_container_id = container_id
            _register_scan_container("phpstan", task_id, container_id)

        process_result = await run_scanner_container(
            ScannerRunSpec(
                scanner_type="phpstan",
                image=str(
                    getattr(settings, "SCANNER_PHPSTAN_IMAGE", "vulhunter/phpstan-runner:latest")
                ),
                workspace_dir=str(workspace_dir),
                command=cmd,
                timeout_seconds=600,
                env={},
            ),
            on_container_started=_on_container_started,
        )

        if _is_scan_task_cancelled("phpstan", task_id):
            await _update_task_state("interrupted", error_message="扫描任务已中止（用户操作）")
            return

        stdout_text = ""
        stderr_text = ""
        if process_result.stdout_path and Path(process_result.stdout_path).exists():
            stdout_text = Path(process_result.stdout_path).read_text(encoding="utf-8", errors="ignore")
        if process_result.stderr_path and Path(process_result.stderr_path).exists():
            stderr_text = Path(process_result.stderr_path).read_text(encoding="utf-8", errors="ignore")

        if process_result.exit_code > 1:
            error_message = (stderr_text or stdout_text or process_result.error or "Unknown error")[:500]
            await _update_task_state("failed", error_message=error_message)
            logger.error(f"PHPStan task {task_id} failed: {error_message}")
            return

        payload: Dict[str, Any] = {}
        parse_error: Optional[Exception] = None
        try:
            payload = _parse_phpstan_output_payload(stdout_text)
        except Exception as exc:  # noqa: BLE001
            parse_error = exc
            try:
                payload = _parse_phpstan_output_payload(stderr_text)
                parse_error = None
            except Exception:  # noqa: BLE001
                payload = {}

        if parse_error is not None and process_result.returncode in {0, 1}:
            await _update_task_state(
                "failed",
                error_message=f"Failed to parse PHPStan JSON output: {parse_error}",
            )
            logger.error(f"Failed to parse phpstan output for task {task_id}: {parse_error}")
            return

        files_payload = payload.get("files")
        files_map: Dict[str, Any] = files_payload if isinstance(files_payload, dict) else {}

        persisted_findings: List[Dict[str, Any]] = []
        raw_finding_count = 0
        dropped_finding_count = 0
        for file_path, file_data in files_map.items():
            if not isinstance(file_data, dict):
                continue
            messages = file_data.get("messages")
            filtered_result = _filter_phpstan_security_messages(messages)
            kept_messages = filtered_result["kept"]
            dropped_messages = filtered_result["dropped"]
            raw_finding_count += len(kept_messages) + len(dropped_messages)
            dropped_finding_count += len(dropped_messages)
            for msg in kept_messages:
                persisted_findings.append(
                    {
                        **msg,
                        "file_path": normalize_static_scan_file_path(
                            str(file_path or "")[:1000],
                            "/scan/project",
                        ),
                    }
                )

        if _is_scan_task_cancelled("phpstan", task_id):
            await _update_task_state("interrupted", error_message="扫描任务已中止（用户操作）")
            return

        updated_task = await _update_task_state(
            "completed",
            findings=persisted_findings,
            files_scanned=len(files_map),
        )
        logger.info(
            "PHPStan task %s filter summary: raw_count=%s, kept_count=%s, dropped_count=%s",
            task_id,
            raw_finding_count,
            len(persisted_findings),
            dropped_finding_count,
        )
        if updated_task is not None:
            project_metrics_refresher.enqueue(updated_task.project_id)
    except asyncio.CancelledError:
        logger.warning(f"PHPStan task {task_id} interrupted by service shutdown")
        await _update_task_state("interrupted", error_message="扫描任务因服务中断被标记为中止")
        raise
    except Exception as exc:
        logger.error(f"Error executing PHPStan task {task_id}: {exc}")
        await _update_task_state("failed", error_message=str(exc))
    finally:
        _pop_scan_container("phpstan", task_id)
        if workspace_dir is not None:
            cleanup_scan_workspace("phpstan", task_id)
        _clear_scan_task_cancel("phpstan", task_id)


@router.get("/phpstan/rules", response_model=List[PhpstanRuleResponse])
async def list_phpstan_rules(
    is_active: Optional[bool] = Query(None, description="按启用状态过滤"),
    source: Optional[str] = Query(None, description="按来源过滤"),
    keyword: Optional[str] = Query(None, description="按名称/类名/描述/包关键词过滤"),
    deleted: str = Query("false", description="软删除筛选：false(默认)/true/all"),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    # PHPStan rules integration: 规则来源固定为快照文件，状态来自 phpstan_rule_states。
    snapshot_rules = _extract_phpstan_snapshot_rules()
    states_by_rule_id = await _load_phpstan_rule_states(db)
    merged_rules = _merge_phpstan_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_rule_id=states_by_rule_id,
    )

    keyword_text = str(keyword or "").strip().lower()
    source_text = str(source or "").strip()
    deleted_text = str(deleted or "false").strip().lower()
    if deleted_text not in {"false", "true", "all"}:
        raise HTTPException(status_code=400, detail="deleted 必须为 false/true/all")
    filtered: List[Dict[str, Any]] = []
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
                    str(item["name"]),
                    str(item["rule_class"]),
                    str(item["description_summary"]),
                    str(item["package"]),
                ]
            ).lower()
            if keyword_text not in search_blob:
                continue
        filtered.append(item)

    return filtered[skip : skip + limit]


@router.get("/phpstan/rules/{rule_id:path}", response_model=PhpstanRuleResponse)
async def get_phpstan_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    snapshot_rules = _extract_phpstan_snapshot_rules()
    states_by_rule_id = await _load_phpstan_rule_states(db)
    merged_rules = _merge_phpstan_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_rule_id=states_by_rule_id,
    )
    for item in merged_rules:
        if item["id"] == rule_id:
            item["source_content"] = _read_phpstan_rule_source_content(
                repo=str(item.get("repo") or ""),
                source_file=str(item.get("source_file") or ""),
            )
            return item
    raise HTTPException(status_code=404, detail="PHPStan 规则不存在")


@router.patch("/phpstan/rules/{rule_id:path}", response_model=PhpstanRuleUpdateResponse)
async def update_phpstan_rule(
    rule_id: str,
    request: PhpstanRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    # PHPStan rules integration: 规则编辑仅影响规则页展示，不参与 phpstan analyse 参数构建。
    known_rule_ids = {item["id"] for item in _extract_phpstan_snapshot_rules()}
    if rule_id not in known_rule_ids:
        raise HTTPException(status_code=404, detail="PHPStan 规则不存在")

    updates: Dict[str, Any] = {}
    if request.package is not None:
        updates["package"] = str(request.package).strip()
    if request.repo is not None:
        updates["repo"] = str(request.repo).strip()
    if request.name is not None:
        name = str(request.name).strip()
        if not name:
            raise HTTPException(status_code=400, detail="name 不能为空")
        updates["name"] = name
    if request.description_summary is not None:
        updates["description_summary"] = str(request.description_summary).strip()
    if request.source_file is not None:
        updates["source_file"] = str(request.source_file).strip()
    if request.source is not None:
        updates["source"] = str(request.source).strip() or "official_extension"

    if not updates:
        raise HTTPException(status_code=400, detail="至少需要提供一个可更新字段")

    try:
        _update_phpstan_snapshot_rule(rule_id, updates)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="PHPStan 规则不存在") from exc
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"更新 PHPStan 规则快照失败: {exc}") from exc

    snapshot_rules = _extract_phpstan_snapshot_rules()
    states_by_rule_id = await _load_phpstan_rule_states(db)
    merged_rules = _merge_phpstan_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_rule_id=states_by_rule_id,
    )
    for item in merged_rules:
        if item["id"] == rule_id:
            return {"message": "规则更新成功", "rule": item}

    raise HTTPException(status_code=404, detail="PHPStan 规则不存在")


@router.post("/phpstan/rules/{rule_id:path}/enabled")
async def update_phpstan_rule_enabled(
    rule_id: str,
    request: PhpstanRuleEnabledUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    known_rule_ids = {item["id"] for item in _extract_phpstan_snapshot_rules()}
    if rule_id not in known_rule_ids:
        raise HTTPException(status_code=404, detail="PHPStan 规则不存在")

    try:
        result = await db.execute(
            select(PhpstanRuleState).where(PhpstanRuleState.rule_id == rule_id)
        )
    except ProgrammingError as exc:
        _raise_phpstan_rules_migration_http_error(exc)
    state = result.scalar_one_or_none()
    if state is None:
        state = PhpstanRuleState(
            id=str(uuid.uuid4()),
            rule_id=rule_id,
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
        "rule_id": rule_id,
        "is_active": bool(state.is_active),
    }


@router.post("/phpstan/rules/batch/enabled")
async def batch_update_phpstan_rules_enabled(
    request: PhpstanRuleBatchEnabledUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    snapshot_rules = _extract_phpstan_snapshot_rules()
    states_by_rule_id = await _load_phpstan_rule_states(db)
    merged_rules = _merge_phpstan_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_rule_id=states_by_rule_id,
    )

    rule_ids_filter = set(request.rule_ids or []) if request.rule_ids else None
    source_text = str(request.source or "").strip()
    keyword_text = str(request.keyword or "").strip().lower()
    selected_rule_ids: List[str] = []

    for item in merged_rules:
        if bool(item["is_deleted"]):
            continue
        if rule_ids_filter is not None and item["id"] not in rule_ids_filter:
            continue
        if source_text and item["source"] != source_text:
            continue
        if request.current_is_active is not None and bool(item["is_active"]) != request.current_is_active:
            continue
        if keyword_text:
            search_blob = " ".join(
                [
                    str(item["name"]),
                    str(item["rule_class"]),
                    str(item["description_summary"]),
                    str(item["package"]),
                ]
            ).lower()
            if keyword_text not in search_blob:
                continue
        selected_rule_ids.append(item["id"])

    if not selected_rule_ids:
        return {
            "message": "没有找到符合条件的规则",
            "updated_count": 0,
            "is_active": request.is_active,
        }

    try:
        existing_result = await db.execute(
            select(PhpstanRuleState).where(PhpstanRuleState.rule_id.in_(selected_rule_ids))
        )
    except ProgrammingError as exc:
        _raise_phpstan_rules_migration_http_error(exc)
    existing_rows = existing_result.scalars().all()
    existing_by_rule_id = {str(row.rule_id): row for row in existing_rows}

    updated_count = 0
    for selected_rule_id in selected_rule_ids:
        existing = existing_by_rule_id.get(selected_rule_id)
        if existing is None:
            db.add(
                PhpstanRuleState(
                    id=str(uuid.uuid4()),
                    rule_id=selected_rule_id,
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


@router.post("/phpstan/rules/{rule_id:path}/delete")
async def delete_phpstan_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    known_rule_ids = {item["id"] for item in _extract_phpstan_snapshot_rules()}
    if rule_id not in known_rule_ids:
        raise HTTPException(status_code=404, detail="PHPStan 规则不存在")

    try:
        result = await db.execute(
            select(PhpstanRuleState).where(PhpstanRuleState.rule_id == rule_id)
        )
    except ProgrammingError as exc:
        _raise_phpstan_rules_migration_http_error(exc)

    state = result.scalar_one_or_none()
    if state is None:
        state = PhpstanRuleState(
            id=str(uuid.uuid4()),
            rule_id=rule_id,
            is_active=False,
            is_deleted=True,
        )
        db.add(state)
    else:
        state.is_active = False
        state.is_deleted = True
    await db.commit()
    return {"message": "规则已删除", "rule_id": rule_id, "is_deleted": True}


@router.post("/phpstan/rules/{rule_id:path}/restore")
async def restore_phpstan_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    known_rule_ids = {item["id"] for item in _extract_phpstan_snapshot_rules()}
    if rule_id not in known_rule_ids:
        raise HTTPException(status_code=404, detail="PHPStan 规则不存在")

    try:
        result = await db.execute(
            select(PhpstanRuleState).where(PhpstanRuleState.rule_id == rule_id)
        )
    except ProgrammingError as exc:
        _raise_phpstan_rules_migration_http_error(exc)

    state = result.scalar_one_or_none()
    if state is None:
        state = PhpstanRuleState(
            id=str(uuid.uuid4()),
            rule_id=rule_id,
            is_active=True,
            is_deleted=False,
        )
        db.add(state)
    else:
        state.is_deleted = False
    await db.commit()
    return {"message": "规则已恢复", "rule_id": rule_id, "is_deleted": False}


@router.post("/phpstan/rules/batch/delete")
async def batch_delete_phpstan_rules(
    request: PhpstanRuleBatchDeletedUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    payload = PhpstanRuleBatchDeletedUpdateRequest(
        rule_ids=request.rule_ids,
        source=request.source,
        keyword=request.keyword,
        current_is_deleted=request.current_is_deleted,
        is_deleted=True,
    )
    return await _batch_update_phpstan_rules_deleted(payload, db)


@router.post("/phpstan/rules/batch/restore")
async def batch_restore_phpstan_rules(
    request: PhpstanRuleBatchDeletedUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    payload = PhpstanRuleBatchDeletedUpdateRequest(
        rule_ids=request.rule_ids,
        source=request.source,
        keyword=request.keyword,
        current_is_deleted=request.current_is_deleted,
        is_deleted=False,
    )
    return await _batch_update_phpstan_rules_deleted(payload, db)


async def _batch_update_phpstan_rules_deleted(
    request: PhpstanRuleBatchDeletedUpdateRequest,
    db: AsyncSession,
):
    snapshot_rules = _extract_phpstan_snapshot_rules()
    states_by_rule_id = await _load_phpstan_rule_states(db)
    merged_rules = _merge_phpstan_rule_payload(
        snapshot_rules=snapshot_rules,
        states_by_rule_id=states_by_rule_id,
    )

    rule_ids_filter = set(request.rule_ids or []) if request.rule_ids else None
    source_text = str(request.source or "").strip()
    keyword_text = str(request.keyword or "").strip().lower()
    selected_rule_ids: List[str] = []

    for item in merged_rules:
        if rule_ids_filter is not None and item["id"] not in rule_ids_filter:
            continue
        if source_text and item["source"] != source_text:
            continue
        if request.current_is_deleted is not None and bool(item["is_deleted"]) != request.current_is_deleted:
            continue
        if keyword_text:
            search_blob = " ".join(
                [
                    str(item["name"]),
                    str(item["rule_class"]),
                    str(item["description_summary"]),
                    str(item["package"]),
                ]
            ).lower()
            if keyword_text not in search_blob:
                continue
        selected_rule_ids.append(item["id"])

    if not selected_rule_ids:
        return {
            "message": "没有找到符合条件的规则",
            "updated_count": 0,
            "is_deleted": request.is_deleted,
        }

    try:
        existing_result = await db.execute(
            select(PhpstanRuleState).where(PhpstanRuleState.rule_id.in_(selected_rule_ids))
        )
    except ProgrammingError as exc:
        _raise_phpstan_rules_migration_http_error(exc)
    existing_rows = existing_result.scalars().all()
    existing_by_rule_id = {str(row.rule_id): row for row in existing_rows}

    updated_count = 0
    for selected_rule_id in selected_rule_ids:
        existing = existing_by_rule_id.get(selected_rule_id)
        if existing is None:
            db.add(
                PhpstanRuleState(
                    id=str(uuid.uuid4()),
                    rule_id=selected_rule_id,
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


@router.post("/phpstan/scan", response_model=PhpstanScanTaskResponse)
async def create_phpstan_scan(
    request: PhpstanScanTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """创建 PHPStan 静态扫描任务。"""
    project = await db.get(Project, request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    project_root = await _get_project_root(request.project_id)
    if not project_root:
        raise HTTPException(
            status_code=400,
            detail="找不到项目的 zip 文件，请先上传项目 ZIP 文件到 uploads/zip_files 目录",
        )

    scan_task = PhpstanScanTask(
        project_id=request.project_id,
        name=request.name or f"PHPStan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        status="pending",
        target_path=request.target_path,
        level=_normalize_phpstan_level(request.level),
    )
    db.add(scan_task)
    await db.commit()
    response = _build_phpstan_scan_task_response(scan_task)
    task_id = response.id
    level = scan_task.level
    await _release_request_db_session(db)
    _launch_static_background_job(
        "phpstan",
        task_id,
        _execute_phpstan_scan(
            task_id,
            project_root,
            request.target_path,
            level,
        ),
    )
    return response


@router.get("/phpstan/tasks", response_model=List[PhpstanScanTaskResponse])
async def list_phpstan_tasks(
    project_id: Optional[str] = Query(None, description="按项目ID过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取 PHPStan 扫描任务列表。"""
    query = select(PhpstanScanTask)
    if project_id:
        query = query.where(PhpstanScanTask.project_id == project_id)
    query = query.order_by(PhpstanScanTask.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/phpstan/tasks/{task_id}", response_model=PhpstanScanTaskResponse)
async def get_phpstan_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取 PHPStan 扫描任务详情。"""
    result = await db.execute(select(PhpstanScanTask).where(PhpstanScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/phpstan/tasks/{task_id}/interrupt")
async def interrupt_phpstan_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """中止运行中的 PHPStan 扫描任务。"""
    result = await db.execute(select(PhpstanScanTask).where(PhpstanScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status in {"completed", "failed", "interrupted"}:
        return {
            "message": f"任务当前状态为 {task.status}，无需中止",
            "task_id": task_id,
            "status": task.status,
        }

    _request_scan_task_cancel("phpstan", task_id)
    task.status = "interrupted"
    if not task.error_message:
        task.error_message = "扫描任务已中止（用户操作）"
    _sync_task_scan_duration(task)
    await db.commit()
    return {"message": "任务已中止", "task_id": task_id, "status": "interrupted"}


@router.delete("/phpstan/tasks/{task_id}")
async def delete_phpstan_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """删除 PHPStan 扫描任务及其发现。"""
    result = await db.execute(select(PhpstanScanTask).where(PhpstanScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    await db.delete(task)
    await db.commit()
    return {"message": "任务已删除", "task_id": task_id}


@router.get("/phpstan/tasks/{task_id}/findings", response_model=List[PhpstanFindingResponse])
async def get_phpstan_findings(
    task_id: str,
    status: Optional[str] = Query(None, description="按状态过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取 PHPStan 扫描发现列表。"""
    task_result = await db.execute(select(PhpstanScanTask).where(PhpstanScanTask.id == task_id))
    if not task_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")

    query = select(PhpstanFinding).where(PhpstanFinding.scan_task_id == task_id)
    if status:
        query = query.where(PhpstanFinding.status == status)
    query = query.order_by(PhpstanFinding.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/phpstan/tasks/{task_id}/findings/{finding_id}",
    response_model=PhpstanFindingResponse,
)
async def get_phpstan_finding(
    task_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取单条 PHPStan 扫描发现详情。"""
    task_result = await db.execute(select(PhpstanScanTask).where(PhpstanScanTask.id == task_id))
    if not task_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")

    finding_result = await db.execute(
        select(PhpstanFinding).where(
            (PhpstanFinding.id == finding_id) & (PhpstanFinding.scan_task_id == task_id)
        )
    )
    finding = finding_result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="PHPStan 问题不存在")
    return finding


@router.post("/phpstan/findings/{finding_id}/status")
async def update_phpstan_finding_status(
    finding_id: str,
    status: str = Query(..., description="状态: open, verified, false_positive"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """更新 PHPStan 扫描发现状态。"""
    normalized_status = str(status or "").strip().lower()
    if normalized_status not in {"open", "verified", "false_positive"}:
        raise HTTPException(status_code=400, detail="status 必须为 open/verified/false_positive")

    result = await db.execute(select(PhpstanFinding).where(PhpstanFinding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="PHPStan 问题不存在")

    finding.status = normalized_status
    await db.commit()
    return {"message": "状态已更新", "finding_id": finding_id, "status": normalized_status}
