import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.bandit import BanditFinding, BanditScanTask
from app.models.gitleaks import GitleaksFinding, GitleaksRule, GitleaksScanTask
from app.models.opengrep import OpengrepFinding, OpengrepRule, OpengrepScanTask
from app.models.phpstan import PhpstanFinding, PhpstanScanTask
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
    _dt_to_iso,
    _ensure_opengrep_xdg_dirs,
    _get_project_root,
    _get_user_config,
    _is_scan_task_cancelled,
    _is_test_like_directory,
    _normalize_llm_config_error_message,
    _record_scan_progress,
    _request_scan_task_cancel,
    _run_subprocess_with_tracking,
    _sync_task_scan_duration,
    _utc_now_iso,
    _validate_user_llm_config,
    async_session_factory,
    deps,
    get_db,
    logger,
    settings,
)

router = APIRouter()

class GitleaksScanTaskCreate(BaseModel):
    """创建 Gitleaks 扫描任务请求"""

    project_id: str = Field(..., description="项目ID")
    name: Optional[str] = Field(None, description="任务名称")
    target_path: str = Field(".", description="扫描目标路径，相对于项目根目录")
    no_git: bool = Field(True, description="不使用 git history，仅扫描文件")


class GitleaksScanTaskResponse(BaseModel):
    """Gitleaks 扫描任务响应"""

    id: str
    project_id: str
    name: str
    status: str
    target_path: str
    no_git: str
    total_findings: int
    scan_duration_ms: int
    files_scanned: int
    error_message: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class GitleaksFindingResponse(BaseModel):
    """Gitleaks 发现的密钥泄露响应"""

    id: str
    scan_task_id: str
    rule_id: str
    description: Optional[str]
    file_path: str
    start_line: Optional[int]
    end_line: Optional[int]
    secret: Optional[str]
    match: Optional[str]
    commit: Optional[str]
    author: Optional[str]
    email: Optional[str]
    date: Optional[str]
    fingerprint: Optional[str]
    status: str

    model_config = ConfigDict(from_attributes=True)


def _to_clean_string_list(raw_value: Any) -> List[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(",") if item.strip()]
    if isinstance(raw_value, list):
        cleaned: List[str] = []
        for item in raw_value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned
    return []


def _validate_gitleaks_rule_payload(
    *,
    regex_text: str,
    secret_group: int,
    keywords: List[str],
    tags: List[str],
) -> None:
    if not str(regex_text or "").strip():
        raise HTTPException(status_code=400, detail="regex 不能为空")
    try:
        re.compile(regex_text)
    except re.error as exc:
        raise HTTPException(status_code=400, detail=f"regex 无法编译: {exc}") from exc

    if int(secret_group) < 0:
        raise HTTPException(status_code=400, detail="secret_group 不能小于 0")

    if not isinstance(keywords, list) or not all(isinstance(item, str) for item in keywords):
        raise HTTPException(status_code=400, detail="keywords 必须为字符串数组")

    if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
        raise HTTPException(status_code=400, detail="tags 必须为字符串数组")


def _toml_escape_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _toml_quote(value: str) -> str:
    return f"\"{_toml_escape_string(value)}\""


def _toml_quote_list(values: List[str]) -> str:
    return "[" + ", ".join(_toml_quote(v) for v in values) + "]"


def _render_gitleaks_rules_toml(rules: List[GitleaksRule]) -> str:
    lines: List[str] = [
        'title = "VulHunter managed gitleaks config"',
        "",
    ]

    for rule in rules:
        lines.append("[[rules]]")
        lines.append(f"id = {_toml_quote(rule.rule_id)}")
        lines.append(f"description = {_toml_quote(rule.description or rule.name)}")
        lines.append(f"regex = {_toml_quote(rule.regex)}")
        lines.append(f"secretGroup = {int(rule.secret_group or 0)}")

        keywords = _to_clean_string_list(rule.keywords)
        if keywords:
            lines.append(f"keywords = {_toml_quote_list(keywords)}")

        if rule.path:
            lines.append(f"path = {_toml_quote(str(rule.path))}")

        tags = _to_clean_string_list(rule.tags)
        if tags:
            lines.append(f"tags = {_toml_quote_list(tags)}")

        if rule.entropy is not None:
            lines.append(f"entropy = {float(rule.entropy)}")

        lines.append("")

    return "\n".join(lines).strip() + "\n"


def _strip_custom_toml_rules_sections(custom_toml: str) -> str:
    if not custom_toml.strip():
        return ""

    lines = custom_toml.splitlines()
    output: List[str] = []
    in_rules_block = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("[[rules]]"):
            in_rules_block = True
            continue

        if in_rules_block and stripped.startswith("["):
            if stripped.startswith("[[rules]]"):
                in_rules_block = True
                continue
            in_rules_block = False

        if not in_rules_block:
            output.append(line)

    return "\n".join(output).strip()


def _normalize_bool_flag(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"", "0", "false", "no", "off"}:
            return False
    return default


def _normalize_gitleaks_runtime_config(runtime_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    candidate = dict(runtime_config) if isinstance(runtime_config, dict) else {}
    report_format = str(candidate.get("reportFormat") or "json").strip().lower()
    if report_format not in {"json", "sarif"}:
        report_format = "json"

    return {
        "reportFormat": report_format,
        "redact": _normalize_bool_flag(candidate.get("redact"), default=False),
        "customConfigToml": str(candidate.get("customConfigToml") or "").strip(),
    }


def _missing_gitleaks_rules_migration_message() -> str:
    return "数据库缺少 gitleaks_rules 表，请先运行 alembic upgrade head"


def _raise_gitleaks_rules_migration_runtime_error(exc: ProgrammingError) -> None:
    if "gitleaks_rules" not in str(exc):
        raise exc
    raise RuntimeError(_missing_gitleaks_rules_migration_message()) from exc


def _raise_gitleaks_rules_migration_http_error(exc: ProgrammingError) -> None:
    if "gitleaks_rules" not in str(exc):
        raise exc
    raise HTTPException(status_code=500, detail=_missing_gitleaks_rules_migration_message()) from exc


async def _build_effective_gitleaks_config_toml(
    db: AsyncSession, runtime_config: Dict[str, Any]
) -> Optional[str]:
    try:
        async with db.begin_nested():
            result = await db.execute(
                select(GitleaksRule)
                .where(GitleaksRule.is_active == True)
                .order_by(GitleaksRule.created_at.asc())
            )
            active_rules = result.scalars().all()
    except ProgrammingError as exc:
        _raise_gitleaks_rules_migration_runtime_error(exc)
    managed_rules_toml = _render_gitleaks_rules_toml(active_rules) if active_rules else ""

    custom_toml = str(runtime_config.get("customConfigToml") or "").strip()
    custom_without_rules = _strip_custom_toml_rules_sections(custom_toml)

    if managed_rules_toml and custom_without_rules:
        return (
            f"{managed_rules_toml}\n"
            "# ---- user custom config (rules blocks removed) ----\n"
            f"{custom_without_rules}\n"
        )
    if managed_rules_toml:
        return managed_rules_toml
    if custom_without_rules:
        return custom_without_rules + "\n"
    return None


def _serialize_gitleaks_rule(rule: GitleaksRule) -> Dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.name,
        "description": rule.description,
        "rule_id": rule.rule_id,
        "secret_group": rule.secret_group,
        "regex": rule.regex,
        "keywords": _to_clean_string_list(rule.keywords),
        "path": rule.path,
        "tags": _to_clean_string_list(rule.tags),
        "entropy": rule.entropy,
        "is_active": rule.is_active,
        "source": rule.source,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _parse_gitleaks_report_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict) and isinstance(payload.get("runs"), list):
        findings: List[Dict[str, Any]] = []
        for run in payload.get("runs") or []:
            if not isinstance(run, dict):
                continue
            for res in run.get("results") or []:
                if not isinstance(res, dict):
                    continue

                rule_id = str(res.get("ruleId") or "gitleaks_secret").strip() or "gitleaks_secret"
                message = res.get("message") or {}
                if isinstance(message, dict):
                    description = str(message.get("text") or "")
                else:
                    description = str(message or "")

                file_path = ""
                start_line = None
                end_line = None
                locations = res.get("locations") or []
                if isinstance(locations, list) and locations and isinstance(locations[0], dict):
                    phys = locations[0].get("physicalLocation") or {}
                    if isinstance(phys, dict):
                        artifact = phys.get("artifactLocation") or {}
                        if isinstance(artifact, dict):
                            file_path = str(artifact.get("uri") or "")
                        region = phys.get("region") or {}
                        if isinstance(region, dict):
                            start_line = region.get("startLine")
                            end_line = region.get("endLine")

                props = res.get("properties") or {}
                secret = ""
                match = ""
                fingerprint = None
                if isinstance(props, dict):
                    secret = str(props.get("secret") or "")
                    match = str(props.get("match") or "")
                    fingerprint = props.get("fingerprint")

                findings.append(
                    {
                        "RuleID": rule_id,
                        "Description": description,
                        "File": file_path,
                        "StartLine": start_line,
                        "EndLine": end_line,
                        "Secret": secret,
                        "Match": match,
                        "Fingerprint": fingerprint,
                    }
                )
        return findings

    return []


def _build_gitleaks_command(
    *,
    full_target_path: str,
    report_file: str,
    report_format: str,
    no_git: bool,
    redact: bool,
    config_file: Optional[str],
) -> List[str]:
    cmd = [
        "gitleaks",
        "detect",
        "--source",
        full_target_path,
        "--report-format",
        report_format,
        "--report-path",
        report_file,
        "--exit-code",
        "0",
    ]
    if no_git:
        cmd.append("--no-git")
    if redact:
        cmd.append("--redact")
    if config_file:
        cmd.extend(["--config", config_file])
    return cmd


def _mask_gitleaks_secret(secret: Any) -> str:
    raw_secret = str(secret or "")
    if len(raw_secret) > 8:
        return raw_secret[:4] + "*" * (len(raw_secret) - 8) + raw_secret[-4:]
    return "*" * len(raw_secret)


@router.get("/gitleaks/rules", response_model=List[GitleaksRuleResponse])
async def list_gitleaks_rules(
    is_active: Optional[bool] = Query(None, description="按启用状态过滤"),
    source: Optional[str] = Query(None, description="按来源过滤"),
    keyword: Optional[str] = Query(None, description="按名称/rule_id关键词过滤"),
    tag: Optional[str] = Query(None, description="按标签过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    try:
        builtin_count_result = await db.execute(
            select(func.count()).select_from(GitleaksRule).where(GitleaksRule.source == "builtin")
        )
        builtin_count = int(builtin_count_result.scalar() or 0)
        if builtin_count == 0:
            await ensure_builtin_gitleaks_rules(db)

        query = select(GitleaksRule)
        if is_active is not None:
            query = query.where(GitleaksRule.is_active == is_active)
        if source:
            query = query.where(GitleaksRule.source == source)
        if keyword and keyword.strip():
            pattern = f"%{keyword.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(GitleaksRule.name).like(pattern),
                    func.lower(GitleaksRule.rule_id).like(pattern),
                    func.lower(GitleaksRule.regex).like(pattern),
                )
            )
        if tag and tag.strip():
            query = query.where(GitleaksRule.tags.contains([tag.strip()]))
        query = query.order_by(GitleaksRule.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(query)
        return [_serialize_gitleaks_rule(rule) for rule in result.scalars().all()]
    except ProgrammingError as exc:
        _raise_gitleaks_rules_migration_http_error(exc)


@router.get("/gitleaks/rules/{rule_pk}", response_model=GitleaksRuleResponse)
async def get_gitleaks_rule(
    rule_pk: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    result = await db.execute(select(GitleaksRule).where(GitleaksRule.id == rule_pk))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return _serialize_gitleaks_rule(rule)


@router.post("/gitleaks/rules", response_model=GitleaksRuleResponse)
async def create_gitleaks_rule(
    request: GitleaksRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    keywords = _to_clean_string_list(request.keywords)
    tags = _to_clean_string_list(request.tags)
    _validate_gitleaks_rule_payload(
        regex_text=request.regex,
        secret_group=request.secret_group,
        keywords=keywords,
        tags=tags,
    )

    new_rule = GitleaksRule(
        name=request.name.strip(),
        description=request.description,
        rule_id=request.rule_id.strip(),
        secret_group=request.secret_group,
        regex=request.regex.strip(),
        keywords=keywords,
        path=(request.path or "").strip() or None,
        tags=tags,
        entropy=request.entropy,
        is_active=request.is_active,
        source=request.source.strip(),
    )
    db.add(new_rule)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="规则名称或规则ID已存在") from exc
    await db.refresh(new_rule)
    return _serialize_gitleaks_rule(new_rule)


@router.patch("/gitleaks/rules/{rule_pk}", response_model=GitleaksRuleResponse)
async def update_gitleaks_rule(
    rule_pk: str,
    request: GitleaksRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    result = await db.execute(select(GitleaksRule).where(GitleaksRule.id == rule_pk))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    if request.name is not None:
        name = request.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="name 不能为空")
        rule.name = name
    if request.description is not None:
        rule.description = request.description
    if request.rule_id is not None:
        rid = request.rule_id.strip()
        if not rid:
            raise HTTPException(status_code=400, detail="rule_id 不能为空")
        rule.rule_id = rid
    if request.secret_group is not None:
        if request.secret_group < 0:
            raise HTTPException(status_code=400, detail="secret_group 不能小于 0")
        rule.secret_group = request.secret_group
    if request.regex is not None:
        regex_text = request.regex.strip()
        _validate_gitleaks_rule_payload(
            regex_text=regex_text,
            secret_group=rule.secret_group,
            keywords=_to_clean_string_list(rule.keywords),
            tags=_to_clean_string_list(rule.tags),
        )
        rule.regex = regex_text
    if request.keywords is not None:
        rule.keywords = _to_clean_string_list(request.keywords)
    if request.path is not None:
        rule.path = (request.path or "").strip() or None
    if request.tags is not None:
        rule.tags = _to_clean_string_list(request.tags)
    if request.entropy is not None:
        if request.entropy < 0:
            raise HTTPException(status_code=400, detail="entropy 不能小于 0")
        rule.entropy = request.entropy
    if request.is_active is not None:
        rule.is_active = request.is_active
    if request.source is not None:
        source = request.source.strip()
        if not source:
            raise HTTPException(status_code=400, detail="source 不能为空")
        rule.source = source

    _validate_gitleaks_rule_payload(
        regex_text=rule.regex,
        secret_group=rule.secret_group,
        keywords=_to_clean_string_list(rule.keywords),
        tags=_to_clean_string_list(rule.tags),
    )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="规则名称或规则ID已存在") from exc
    await db.refresh(rule)
    return _serialize_gitleaks_rule(rule)


@router.delete("/gitleaks/rules/{rule_pk}")
async def delete_gitleaks_rule(
    rule_pk: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    result = await db.execute(select(GitleaksRule).where(GitleaksRule.id == rule_pk))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    await db.delete(rule)
    await db.commit()
    return {"message": "规则已删除", "rule_id": rule_pk}


@router.post("/gitleaks/rules/select")
async def batch_update_gitleaks_rules(
    request: GitleaksRuleBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    query = select(GitleaksRule)

    if request.rule_ids:
        query = query.where(GitleaksRule.id.in_(request.rule_ids))
    if request.source:
        query = query.where(GitleaksRule.source == request.source)
    if request.keyword and request.keyword.strip():
        pattern = f"%{request.keyword.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(GitleaksRule.name).like(pattern),
                func.lower(GitleaksRule.rule_id).like(pattern),
            )
        )
    if request.current_is_active is not None:
        query = query.where(GitleaksRule.is_active == request.current_is_active)

    result = await db.execute(query)
    rules = result.scalars().all()
    if not rules:
        return {"message": "没有找到符合条件的规则", "updated_count": 0, "is_active": request.is_active}

    updated_count = 0
    for rule in rules:
        rule.is_active = request.is_active
        updated_count += 1
    await db.commit()
    return {
        "message": f"已{'启用' if request.is_active else '禁用'} {updated_count} 条规则",
        "updated_count": updated_count,
        "is_active": request.is_active,
    }


@router.post("/gitleaks/rules/import-builtin")
async def import_builtin_gitleaks_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    result = await ensure_builtin_gitleaks_rules(db)
    return {
        "message": "gitleaks 内置规则导入完成",
        **result,
    }


async def _execute_gitleaks_scan(
    task_id: str,
    project_root: str,
    target_path: str,
    no_git: bool = True,
    runtime_config: Optional[Dict[str, Any]] = None,
) -> None:
    """
    后台执行 Gitleaks 扫描

    Args:
        task_id: 扫描任务ID
        project_root: 项目根目录
        target_path: 扫描目标路径
        no_git: 是否不使用 git history
    """
    async with async_session_factory() as db:
        try:
            # 获取任务
            result = await db.execute(
                select(GitleaksScanTask).where(GitleaksScanTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                logger.error(f"Gitleaks task {task_id} not found")
                return

            if _is_scan_task_cancelled("gitleaks", task_id) or task.status == "interrupted":
                task.status = "interrupted"
                if not task.error_message:
                    task.error_message = "扫描任务已中止（用户操作）"
                _sync_task_scan_duration(task)
                await db.commit()
                return

            # 更新任务状态为运行中
            task.status = "running"
            await db.commit()

            # 构建扫描路径
            full_target_path = os.path.join(project_root, target_path)
            if not os.path.exists(full_target_path):
                task.status = "failed"
                task.error_message = f"Target path {full_target_path} not found"
                _sync_task_scan_duration(task)
                await db.commit()
                logger.error(f"Target path {full_target_path} not found")
                return

            # 规范化运行时配置（来自 /config/me -> otherConfig.gitleaksConfig）
            gcfg = _normalize_gitleaks_runtime_config(runtime_config)

            # 创建临时输出文件
            report_suffix = ".sarif" if gcfg.get("reportFormat") == "sarif" else ".json"
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=report_suffix, delete=False
            ) as tf:
                report_file = tf.name

            config_file: Optional[str] = None
            effective_toml = await _build_effective_gitleaks_config_toml(db, gcfg)
            if effective_toml:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as ctf:
                    ctf.write(effective_toml)
                    config_file = ctf.name
            else:
                logger.warning(
                    "No active gitleaks rules and no custom config for task %s; scanning with tool defaults",
                    task_id,
                )

            try:
                cmd = _build_gitleaks_command(
                    full_target_path=full_target_path,
                    report_file=report_file,
                    report_format=str(gcfg.get("reportFormat") or "json"),
                    no_git=no_git,
                    redact=bool(gcfg.get("redact")),
                    config_file=config_file,
                )

                logger.info(
                    f"Executing gitleaks for task {task_id}: {' '.join(cmd)}"
                )
                
                # 在线程池中执行阻塞操作
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: _run_subprocess_with_tracking(
                        "gitleaks",
                        task_id,
                        cmd,
                        timeout=600,
                    )
                )

                if _is_scan_task_cancelled("gitleaks", task_id):
                    task.status = "interrupted"
                    if not task.error_message:
                        task.error_message = "扫描任务已中止（用户操作）"
                    _sync_task_scan_duration(task)
                    await db.commit()
                    return

                # 检查执行结果
                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout or "Unknown error"
                    task.status = "failed"
                    task.error_message = error_msg[:500]
                    _sync_task_scan_duration(task)
                    await db.commit()
                    logger.error(
                        f"Gitleaks scan task {task_id} failed: {error_msg}"
                    )
                    return

                # 读取扫描结果
                if not os.path.exists(report_file):
                    task.status = "completed"
                    task.total_findings = 0
                    _sync_task_scan_duration(task)
                    await db.commit()
                    logger.info(
                        f"Gitleaks scan task {task_id} completed with no findings"
                    )
                    return

                with open(report_file, "r") as f:
                    content = f.read().strip()
                    if not content:
                        raw_payload = []
                    else:
                        try:
                            raw_payload = json.loads(content)
                        except json.JSONDecodeError as e:
                            logger.error(
                                f"Failed to parse gitleaks output: {e}"
                            )
                            task.status = "failed"
                            task.error_message = f"Failed to parse JSON output: {str(e)}"
                            _sync_task_scan_duration(task)
                            await db.commit()
                            return

                findings = _parse_gitleaks_report_payload(raw_payload)

                # 保存发现的密钥泄露
                files_scanned = set()
                for finding in findings:
                    try:
                        file_path = finding.get("File", "")
                        if file_path:
                            files_scanned.add(file_path)

                        gitleaks_finding = GitleaksFinding(
                            scan_task_id=task_id,
                            rule_id=finding.get("RuleID", "unknown"),
                            description=finding.get("Description", ""),
                            file_path=file_path,
                            start_line=finding.get("StartLine"),
                            end_line=finding.get("EndLine"),
                            secret=_mask_gitleaks_secret(finding.get("Secret", "")),
                            match=finding.get("Match", "")[:500],  # 限制长度
                            commit=finding.get("Commit"),
                            author=finding.get("Author"),
                            email=finding.get("Email"),
                            date=finding.get("Date"),
                            fingerprint=finding.get("Fingerprint"),
                            status="open",
                        )
                        db.add(gitleaks_finding)
                    except Exception as e:
                        logger.error(f"Error processing gitleaks finding: {e}")

                # 更新任务统计
                if _is_scan_task_cancelled("gitleaks", task_id):
                    task.status = "interrupted"
                    if not task.error_message:
                        task.error_message = "扫描任务已中止（用户操作）"
                    _sync_task_scan_duration(task)
                    await db.commit()
                    return

                task.status = "completed"
                task.total_findings = len(findings)
                task.files_scanned = len(files_scanned)
                _sync_task_scan_duration(task)

                await db.commit()
                logger.info(
                    f"Gitleaks scan task {task_id} completed: "
                    f"{len(findings)} findings in {len(files_scanned)} files"
                )

            finally:
                # 清理临时文件
                try:
                    if os.path.exists(report_file):
                        os.unlink(report_file)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary report file: {e}")
                try:
                    if config_file and os.path.exists(config_file):
                        os.unlink(config_file)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary gitleaks config file: {e}")

        except asyncio.CancelledError:
            logger.warning(f"Gitleaks scan task {task_id} interrupted by service shutdown")
            try:
                await db.rollback()
                result = await db.execute(
                    select(GitleaksScanTask).where(GitleaksScanTask.id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.status = "interrupted"
                    if not task.error_message:
                        task.error_message = "扫描任务已中断（服务关闭或沙箱停止）"
                    _sync_task_scan_duration(task)
                    await db.commit()
            except Exception as commit_error:
                logger.error(
                    f"Failed to update gitleaks interrupted task status: {commit_error}"
                )
        except Exception as e:
            logger.error(f"Error executing gitleaks scan for task {task_id}: {e}")
            try:
                await db.rollback()
                result = await db.execute(
                    select(GitleaksScanTask).where(GitleaksScanTask.id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)[:500]
                    _sync_task_scan_duration(task)
                    await db.commit()
            except Exception as commit_error:
                logger.error(
                    f"Failed to update task status after error: {commit_error}"
                )
        finally:
            _clear_scan_task_cancel("gitleaks", task_id)
            if project_root and project_root.startswith("/tmp") and os.path.exists(project_root):
                try:
                    shutil.rmtree(project_root, ignore_errors=True)
                    logger.info(f"Cleaned up temporary project directory: {project_root}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary directory {project_root}: {e}")


@router.post("/gitleaks/scan", response_model=GitleaksScanTaskResponse)
async def create_gitleaks_scan(
    request: GitleaksScanTaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    创建 Gitleaks 密钥泄露检测任务

    Gitleaks 会扫描代码中的硬编码密钥，支持 150+ 种密钥类型：
    - AWS/GCP/Azure 凭据
    - GitHub/GitLab Tokens
    - 私钥 (RSA, SSH, PGP)
    - 数据库连接字符串
    - JWT Secrets
    """
    # 验证项目存在
    result = await db.execute(
        select(Project).where(Project.id == request.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 获取项目根目录
    project_root = await _get_project_root(request.project_id)
    if not project_root:
        raise HTTPException(status_code=404, detail="未找到项目文件")

    # 创建扫描任务
    task_name = request.name or f"Gitleaks 扫描 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    scan_task = GitleaksScanTask(
        project_id=request.project_id,
        name=task_name,
        target_path=request.target_path,
        no_git=str(request.no_git).lower(),
        status="pending",
    )
    db.add(scan_task)
    await db.commit()
    await db.refresh(scan_task)

    # 读取当前用户 gitleaks 配置（/config/me -> otherConfig.gitleaksConfig）
    user_cfg = await _get_user_config(db, current_user.id)
    other_cfg = (user_cfg or {}).get("otherConfig", {}) if isinstance(user_cfg, dict) else {}
    gitleaks_cfg: Dict[str, Any] = {}
    if isinstance(other_cfg, dict):
        gitleaks_cfg = other_cfg.get("gitleaksConfig") or {}

    # 添加后台任务
    background_tasks.add_task(
        _execute_gitleaks_scan,
        scan_task.id,
        project_root,
        request.target_path,
        request.no_git,
        gitleaks_cfg,
    )

    logger.info(
        f"Created gitleaks scan task {scan_task.id} for project {request.project_id}"
    )

    return scan_task


@router.get("/gitleaks/tasks", response_model=List[GitleaksScanTaskResponse])
async def list_gitleaks_tasks(
    project_id: Optional[str] = Query(None, description="按项目ID过滤"),
    status: Optional[str] = Query(None, description="按状态过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取 Gitleaks 扫描任务列表"""
    query = select(GitleaksScanTask)

    if project_id:
        query = query.where(GitleaksScanTask.project_id == project_id)
    if status:
        query = query.where(GitleaksScanTask.status == status)

    query = query.order_by(GitleaksScanTask.created_at.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    tasks = result.scalars().all()
    return tasks


@router.get("/gitleaks/tasks/{task_id}", response_model=GitleaksScanTaskResponse)
async def get_gitleaks_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取 Gitleaks 扫描任务详情"""
    result = await db.execute(
        select(GitleaksScanTask).where(GitleaksScanTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.post("/gitleaks/tasks/{task_id}/interrupt")
async def interrupt_gitleaks_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """中止运行中的 Gitleaks 扫描任务。"""
    result = await db.execute(
        select(GitleaksScanTask).where(GitleaksScanTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status in {"completed", "failed", "interrupted"}:
        return {
            "message": f"任务当前状态为 {task.status}，无需中止",
            "task_id": task_id,
            "status": task.status,
        }

    _request_scan_task_cancel("gitleaks", task_id)
    task.status = "interrupted"
    if not task.error_message:
        task.error_message = "扫描任务已中止（用户操作）"
    _sync_task_scan_duration(task)
    await db.commit()

    return {"message": "任务已中止", "task_id": task_id, "status": "interrupted"}


@router.delete("/gitleaks/tasks/{task_id}")
async def delete_gitleaks_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """删除 Gitleaks 扫描任务及其相关发现"""
    result = await db.execute(
        select(GitleaksScanTask).where(GitleaksScanTask.id == task_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    await db.delete(task)
    await db.commit()

    return {"message": "任务已删除", "task_id": task_id}


@router.get("/gitleaks/tasks/{task_id}/findings", response_model=List[GitleaksFindingResponse])
async def get_gitleaks_findings(
    task_id: str,
    status: Optional[str] = Query(
        None, description="按状态过滤: open, verified, false_positive, fixed"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取 Gitleaks 扫描任务的密钥泄露列表"""
    # 验证任务存在
    result = await db.execute(
        select(GitleaksScanTask).where(GitleaksScanTask.id == task_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")

    # 构建查询
    query = select(GitleaksFinding).where(GitleaksFinding.scan_task_id == task_id)

    if status:
        query = query.where(GitleaksFinding.status == status)

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    findings = result.scalars().all()
    return findings


@router.get(
    "/gitleaks/tasks/{task_id}/findings/{finding_id}",
    response_model=GitleaksFindingResponse,
)
async def get_gitleaks_finding(
    task_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取单条 Gitleaks 密钥泄露详情"""
    task_result = await db.execute(
        select(GitleaksScanTask).where(GitleaksScanTask.id == task_id)
    )
    if not task_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")

    finding_result = await db.execute(
        select(GitleaksFinding).where(
            GitleaksFinding.id == finding_id,
            GitleaksFinding.scan_task_id == task_id,
        )
    )
    finding = finding_result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="密钥泄露记录不存在")
    return finding


@router.post("/gitleaks/findings/{finding_id}/status")
async def update_gitleaks_finding_status(
    finding_id: str,
    status: str = Query(
        ...,
        pattern="^(open|verified|false_positive|fixed)$",
        description="新状态: open, verified, false_positive, fixed",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    更新 Gitleaks 发现的密钥泄露状态

    可用状态：
    - open: 开放
    - verified: 已验证为真实泄露
    - false_positive: 误报
    - fixed: 已修复
    """
    result = await db.execute(
        select(GitleaksFinding).where(GitleaksFinding.id == finding_id)
    )
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="密钥泄露记录不存在")

    finding.status = status
    await db.commit()

    return {"message": "状态已更新", "finding_id": finding_id, "status": status}
