import asyncio
import hashlib
import json
import logging
import os
import re
import shlex
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
from app.db.static_finding_paths import (
    build_zip_member_path_candidates,
    normalize_static_scan_file_path,
    resolve_static_finding_location,
)
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
    _scan_progress_store,
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

class OpengrepScanTaskCreate(BaseModel):
    """创建 Opengrep 扫描任务请求"""

    project_id: str = Field(..., description="项目ID")
    name: Optional[str] = Field(None, description="任务名称")
    rule_ids: List[str] = Field(default_factory=list, description="选择的规则ID列表")
    target_path: str = Field(".", description="扫描目标路径，相对于项目根目录")


class OpengrepScanTaskResponse(BaseModel):
    """扫描任务响应"""

    id: str
    project_id: str
    name: str
    status: str
    target_path: str
    total_findings: int
    error_count: int
    warning_count: int
    high_confidence_count: int = 0
    scan_duration_ms: int
    files_scanned: int
    lines_scanned: int
    created_at: datetime
    updated_at: Optional[datetime] = None


def _build_opengrep_scan_task_response(task: OpengrepScanTask) -> OpengrepScanTaskResponse:
    return OpengrepScanTaskResponse(
        id=str(task.id),
        project_id=str(task.project_id),
        name=str(task.name or ""),
        status=str(task.status or "pending"),
        target_path=str(task.target_path or "."),
        total_findings=int(task.total_findings or 0),
        error_count=int(task.error_count or 0),
        warning_count=int(task.warning_count or 0),
        high_confidence_count=int(getattr(task, "high_confidence_count", 0) or 0),
        scan_duration_ms=int(task.scan_duration_ms or 0),
        files_scanned=int(task.files_scanned or 0),
        lines_scanned=int(task.lines_scanned or 0),
        created_at=task.created_at or datetime.now(timezone.utc),
        updated_at=task.updated_at,
    )

    model_config = ConfigDict(from_attributes=True)


class OpengrepFindingResponse(BaseModel):
    """扫描发现响应"""

    id: str
    scan_task_id: str
    rule: Dict[str, Any]
    description: Optional[str]
    file_path: str
    start_line: Optional[int]
    resolved_file_path: Optional[str] = None
    resolved_line_start: Optional[int] = None
    code_snippet: Optional[str]
    severity: str
    status: str
    confidence: Optional[str] = Field(None, description="规则置信度: HIGH, MEDIUM, LOW")
    cwe: Optional[List[str]] = Field(None, description="CWE列表")
    rule_name: Optional[str] = Field(None, description="命中规则名称")

    model_config = ConfigDict(from_attributes=True)


class OpengrepFindingContextLine(BaseModel):
    line_number: int
    content: str
    is_hit: bool


class OpengrepFindingContextResponse(BaseModel):
    task_id: str
    finding_id: str
    file_path: str
    start_line: int
    end_line: int
    before: int
    after: int
    total_lines: int
    lines: List[OpengrepFindingContextLine]


class OpengrepScanProgressLogEntry(BaseModel):
    """扫描进度日志条目"""

    timestamp: str
    stage: str
    message: str
    progress: float
    level: str = "info"


class OpengrepScanProgressResponse(BaseModel):
    """扫描进度响应"""

    task_id: str
    status: str
    progress: float = 0
    current_stage: Optional[str] = None
    message: Optional[str] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    logs: List[OpengrepScanProgressLogEntry] = Field(default_factory=list)
def _parse_opengrep_output(stdout: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """解析 opengrep JSON 输出并返回 (results, errors)。"""
    if not stdout or not stdout.strip():
        return [], []

    try:
        output = json.loads(stdout)
        if isinstance(output, dict):
            results = output.get("results", [])
            errors = output.get("errors", [])
        elif isinstance(output, list):
            # 兼容部分引擎直接返回结果数组
            results = output
            errors = []
        else:
            raise ValueError("Unexpected opengrep output type")

        if not isinstance(results, list):
            raise ValueError("Invalid opengrep results format")
        if not isinstance(errors, list):
            errors = []
        return results, errors
    except json.JSONDecodeError as e:
        raise ValueError("Failed to parse opengrep output") from e
def _is_fatal_rule_error(error_item: Dict[str, Any]) -> bool:
    """
    判断是否为应导致任务失败的规则错误。

    约定：
    - 规则配置/语法/加载失败 => fatal
    - 扫描目标文件语法错误（带 path）=> non-fatal
    """
    err_type = str(error_item.get("type", "")).lower()
    msg = str(error_item.get("message", "")).lower()
    path = str(error_item.get("path", "")).strip()

    # 常见源码解析错误：仅影响单文件，不应导致整任务失败
    if "syntax error" in err_type and path:
        return False

    fatal_keywords = (
        "invalid rule",
        "rule parse",
        "rule syntax",
        "rule schema",
        "invalid config",
        "config error",
        "yaml",
        "toml",
    )
    if any(keyword in msg for keyword in fatal_keywords):
        return True

    # 无路径错误通常是全局级错误（规则/引擎层）
    if not path:
        return True

    return False


def _truncate_for_progress_log(value: Any, max_length: int = 220) -> str:
    """裁剪并规范化日志文本，避免进度日志被长文本刷屏。"""
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _extract_error_message(error_item: Dict[str, Any]) -> str:
    for key in ("message", "long_msg", "short_msg", "details", "error"):
        value = error_item.get(key)
        if value:
            return _truncate_for_progress_log(value, 220)
    return ""


def _extract_error_rule_ids(error_item: Dict[str, Any]) -> List[str]:
    """尽可能从 opengrep error 中提取规则 ID 候选。"""
    rule_ids: List[str] = []
    ignored_tokens = {
        "rule",
        "rules",
        "check",
        "check_id",
        "invalid",
        "error",
        "config",
        "yaml",
    }

    def _append(value: Any) -> None:
        candidate = str(value or "").strip().strip("'\"`")
        if not candidate:
            return
        if len(candidate) > 160:
            return
        if candidate.lower() in ignored_tokens:
            return
        if candidate not in rule_ids:
            rule_ids.append(candidate)

    for key in ("rule_id", "check_id", "id", "name"):
        _append(error_item.get(key))

    rule_payload = error_item.get("rule")
    if isinstance(rule_payload, dict):
        for key in ("id", "check_id", "name"):
            _append(rule_payload.get(key))

    msg = _extract_error_message(error_item)
    if msg:
        for match in re.findall(
            r"(?:rule id|rule|check_id|check-id|check)\s*[=:]?\s*['\"`]?([A-Za-z0-9_.:-]{3,})",
            msg,
            flags=re.IGNORECASE,
        ):
            _append(match)

    return rule_ids


def _summarize_fatal_rule_errors(
    errors: List[Dict[str, Any]],
    *,
    max_rule_ids: int = 6,
) -> tuple[List[str], str]:
    rule_ids: List[str] = []
    message = ""
    for err in errors:
        for rid in _extract_error_rule_ids(err):
            if rid not in rule_ids:
                rule_ids.append(rid)
        if not message:
            message = _extract_error_message(err)
        if len(rule_ids) >= max_rule_ids and message:
            break
    return rule_ids[:max_rule_ids], message
async def _execute_opengrep_scan(
    task_id: str,
    project_root: str,
    target_path: str,
    rule_ids: List[str],
) -> None:
    """
    后台执行 Opengrep 扫描

    Args:
        task_id: 扫描任务ID
        project_root: 项目根目录
        target_path: 扫描目标路径
        rule_ids: 规则ID列表
    """
    workspace_dir: Optional[Path] = None
    active_container_id: Optional[str] = None

    async def _update_task_state(
        status: str,
        *,
        findings: Optional[List[Dict[str, Any]]] = None,
        error_count: Optional[int] = None,
        warning_count: Optional[int] = None,
        files_scanned_count: int = 0,
        lines_scanned_count: int = 0,
        increment_error_count: bool = False,
    ) -> Optional[OpengrepScanTask]:
        async with async_session_factory() as db:
            result = await db.execute(
                select(OpengrepScanTask).where(OpengrepScanTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                return None

            if findings:
                for finding in findings:
                    db.add(
                        OpengrepFinding(
                            scan_task_id=task_id,
                            rule=finding["rule"],
                            description=finding.get("description"),
                            file_path=str(finding.get("file_path") or ""),
                            start_line=finding.get("start_line"),
                            code_snippet=finding.get("code_snippet"),
                            severity=str(finding.get("severity") or "INFO"),
                            status="open",
                        )
                    )

            task.status = status
            if increment_error_count:
                task.error_count = (task.error_count or 0) + 1
            if error_count is not None:
                task.error_count = error_count
            if warning_count is not None:
                task.warning_count = warning_count
            if status == "completed":
                task.total_findings = len(findings or [])
                task.files_scanned = files_scanned_count
                task.lines_scanned = lines_scanned_count
            _sync_task_scan_duration(task)
            await db.commit()
            return task

    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(OpengrepScanTask).where(OpengrepScanTask.id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                logger.error(f"Task {task_id} not found")
                return

            if _is_scan_task_cancelled("opengrep", task_id) or task.status == "interrupted":
                task.status = "interrupted"
                task.error_count = (task.error_count or 0) + 1
                _sync_task_scan_duration(task)
                await db.commit()
                _record_scan_progress(
                    task_id,
                    status="interrupted",
                    progress=100,
                    stage="interrupted",
                    message="扫描任务已中止（用户操作）",
                    level="warning",
                )
                return

            task.status = "running"
            await db.commit()
            _record_scan_progress(
                task_id,
                status="running",
                progress=8,
                stage="init",
                message="开始准备扫描环境",
            )

            result = await db.execute(
                select(OpengrepRule).where(
                    (OpengrepRule.id.in_(rule_ids)) & (OpengrepRule.is_active == True)
                )
            )
            rules = result.scalars().all()

        if not rules:
            await _update_task_state("failed", error_count=1)
            _record_scan_progress(
                task_id,
                status="failed",
                progress=100,
                stage="failed",
                message="未找到可用的激活规则，任务失败",
                level="error",
            )
            logger.error(f"No active rules found for task {task_id}")
            return

        workspace_dir = ensure_scan_workspace("opengrep", task_id)
        project_dir = ensure_scan_project_dir("opengrep", task_id)
        output_dir = ensure_scan_output_dir("opengrep", task_id)
        logs_dir = ensure_scan_logs_dir("opengrep", task_id)
        meta_dir = ensure_scan_meta_dir("opengrep", task_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)

        shutil.rmtree(project_dir, ignore_errors=True)
        copy_project_tree_to_scan_dir(project_root, project_dir)

        full_target_path = os.path.join(str(project_dir), target_path)
        if not os.path.exists(full_target_path):
            await _update_task_state("failed", error_count=1)
            _record_scan_progress(
                task_id,
                status="failed",
                progress=100,
                stage="failed",
                message="扫描目标路径不存在，任务失败",
                level="error",
            )
            logger.error(f"Target path {full_target_path} not found")
            return

        runner_target_path = Path("/scan/project")
        normalized_target_path = str(target_path or ".").strip()
        if normalized_target_path not in {"", "."}:
            runner_target_path = runner_target_path / normalized_target_path

        def remove_null_values(obj):
            """递归移除字典/列表中的 null 值"""
            if isinstance(obj, dict):
                return {k: remove_null_values(v) for k, v in obj.items() if v is not None}
            if isinstance(obj, list):
                return [remove_null_values(item) for item in obj if item is not None]
            return obj

        def has_deprecated_features(rule):
            """检查规则是否包含已弃用的特性"""
            deprecated_keys = [
                "pattern-where-python",
                "pattern-not-regex",
            ]

            def check_dict(obj):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if key in deprecated_keys:
                            return True, key
                        result, deprecated_key = check_dict(value)
                        if result:
                            return True, deprecated_key
                elif isinstance(obj, list):
                    for item in obj:
                        result, deprecated_key = check_dict(item)
                        if result:
                            return True, deprecated_key
                return False, None

            return check_dict(rule)

        def is_valid_rule(rule):
            """验证规则是否包含必需的模式属性"""
            if not isinstance(rule, dict):
                return False, "not a dict"
            if "id" not in rule:
                return False, "missing id"

            has_deprecated, deprecated_key = has_deprecated_features(rule)
            if has_deprecated:
                return False, f"uses deprecated feature: {deprecated_key}"

            mode = rule.get("mode")
            if mode == "taint":
                has_sources = "pattern-sources" in rule
                has_sinks = "pattern-sinks" in rule
                if not (has_sources and has_sinks):
                    return False, f"taint mode missing sources({has_sources}) or sinks({has_sinks})"
            else:
                pattern_keys = ["pattern", "patterns", "pattern-either", "pattern-regex"]
                has_pattern = any(key in rule for key in pattern_keys)
                if not has_pattern:
                    return False, "missing standard pattern attributes"

            return True, "valid"

        _ensure_opengrep_xdg_dirs()
        scan_env = {
            "NO_PROXY": "*",
            "no_proxy": "*",
        }

        valid_rule_entries: List[Dict[str, Any]] = []
        skipped_rule_count = 0
        total_rules = len(rules)
        _record_scan_progress(
            task_id,
            progress=12,
            stage="load_rules",
            message=f"加载规则中（0/{total_rules}）",
        )

        for idx, rule in enumerate(rules, start=1):
            try:
                rule_data = yaml.safe_load(rule.pattern_yaml)
                if not rule_data or "rules" not in rule_data:
                    logger.warning(f"Skipping rule {rule.name}: invalid YAML structure")
                    skipped_rule_count += 1
                    continue

                for parsed_rule in rule_data["rules"]:
                    cleaned_rule = remove_null_values(parsed_rule)
                    is_valid, reason = is_valid_rule(cleaned_rule)
                    if is_valid:
                        valid_rule_entries.append(
                            {
                                "rule": cleaned_rule,
                                "languages": _extract_rule_languages(cleaned_rule, rule.language),
                            }
                        )
                    else:
                        rule_id = cleaned_rule.get("id", "unknown")
                        logger.warning(f"Skipping invalid rule {rule_id} from {rule.name}: {reason}")
                        skipped_rule_count += 1
            except Exception as e:
                logger.warning(f"Failed to parse rule {rule.name}: {e}")
                skipped_rule_count += 1
            finally:
                progress = 12 + (idx / max(total_rules, 1)) * 14
                _record_scan_progress(
                    task_id,
                    progress=progress,
                    stage="load_rules",
                    message=f"加载规则中（{idx}/{total_rules}）",
                )

        if not valid_rule_entries:
            await _update_task_state("failed", error_count=1)
            _record_scan_progress(
                task_id,
                status="failed",
                progress=100,
                stage="failed",
                message="规则验证后无可执行规则，任务失败",
                level="error",
            )
            logger.error(f"No valid rules to apply for task {task_id}")
            return

        detected_languages = _detect_project_languages(full_target_path)
        executable_rule_entries = valid_rule_entries
        if detected_languages:
            matched_rule_entries = [
                entry
                for entry in valid_rule_entries
                if _should_scan_rule_for_languages(
                    entry.get("languages", set()), detected_languages
                )
            ]
            if matched_rule_entries:
                executable_rule_entries = matched_rule_entries

        filtered_rule_count = len(valid_rule_entries) - len(executable_rule_entries)
        logger.info(
            "Task %s language-aware rule filtering: project_languages=%s, valid_rules=%s, executable_rules=%s, filtered=%s, skipped_invalid=%s",
            task_id,
            sorted(detected_languages),
            len(valid_rule_entries),
            len(executable_rule_entries),
            filtered_rule_count,
            skipped_rule_count,
        )
        _record_scan_progress(
            task_id,
            progress=28,
            stage="execute_rules",
            message=(
                f"开始执行静态扫描（可执行 {len(executable_rule_entries)} / "
                f"有效 {len(valid_rule_entries)}）"
            ),
        )

        all_findings: List[Dict[str, Any]] = []
        all_scan_errors: List[Dict[str, Any]] = []
        successful_rule_count = 0
        failed_rule_count = 0
        total_rules_for_execution = len(executable_rule_entries)
        fallback_reason = "合并执行无有效结果"
        jobs = _resolve_opengrep_scan_jobs()
        use_jobs_option = True

        async def run_merged_group_scan(
            rule_entries: List[Dict[str, Any]],
            *,
            timeout_seconds: int,
        ) -> Dict[str, Any]:
            nonlocal use_jobs_option
            rule_file = None
            report_file = output_dir / "report.json"
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".yml",
                    dir=str(meta_dir),
                    delete=False,
                ) as tf:
                    yaml.dump(
                        {"rules": [entry["rule"] for entry in rule_entries]},
                        tf,
                        sort_keys=False,
                        default_flow_style=False,
                    )
                    rule_file = tf.name

                runner_rule_file = str(Path("/scan/meta") / Path(rule_file).name)
                cmd = ["opengrep", "--config", runner_rule_file, "--json"]
                if use_jobs_option:
                    cmd.extend(["--jobs", str(jobs)])
                cmd.append(str(runner_target_path))
                if report_file.exists():
                    report_file.unlink()

                def _on_container_started(container_id: str) -> None:
                    nonlocal active_container_id
                    active_container_id = container_id
                    _register_scan_container("opengrep", task_id, container_id)

                result = await run_scanner_container(
                    ScannerRunSpec(
                        scanner_type="opengrep",
                        image=str(
                            getattr(settings, "SCANNER_OPENGREP_IMAGE", "vulhunter/opengrep-runner:latest")
                        ),
                        workspace_dir=str(workspace_dir),
                        command=cmd,
                        timeout_seconds=timeout_seconds,
                        env=scan_env,
                        artifact_paths=["output/report.json"],
                        capture_stdout_path="output/report.json",
                    ),
                    on_container_started=_on_container_started,
                )

                stdout_text = ""
                stderr_text = ""
                if report_file.exists():
                    stdout_text = report_file.read_text(
                        encoding="utf-8",
                        errors="ignore",
                    )
                if result.stderr_path:
                    stderr_text = Path(result.stderr_path).read_text(
                        encoding="utf-8",
                        errors="ignore",
                    )

                if use_jobs_option and result.exit_code != 0 and (
                    "unrecognized arguments: --jobs" in stderr_text
                    or "unknown option '--jobs'" in stderr_text
                ):
                    logger.warning(
                        "opengrep does not support --jobs, fallback to single process mode"
                    )
                    use_jobs_option = False
                    cmd = ["opengrep", "--config", runner_rule_file, "--json", str(runner_target_path)]
                    if report_file.exists():
                        report_file.unlink()
                    result = await run_scanner_container(
                        ScannerRunSpec(
                            scanner_type="opengrep",
                            image=str(
                                getattr(settings, "SCANNER_OPENGREP_IMAGE", "vulhunter/opengrep-runner:latest")
                            ),
                            workspace_dir=str(workspace_dir),
                            command=cmd,
                            timeout_seconds=timeout_seconds,
                            env=scan_env,
                            artifact_paths=["output/report.json"],
                            capture_stdout_path="output/report.json",
                        ),
                        on_container_started=_on_container_started,
                    )
                    stdout_text = ""
                    stderr_text = ""
                    if report_file.exists():
                        stdout_text = report_file.read_text(
                            encoding="utf-8",
                            errors="ignore",
                        )
                    if result.stderr_path:
                        stderr_text = Path(result.stderr_path).read_text(
                            encoding="utf-8",
                            errors="ignore",
                        )

                parsed_findings, parsed_errors = _parse_opengrep_output(stdout_text)
                fatal_errors = [item for item in parsed_errors if _is_fatal_rule_error(item)]
                command_failed_without_output = (
                    result.exit_code != 0 and not parsed_findings and not parsed_errors
                )

                if command_failed_without_output:
                    stderr_msg = _truncate_for_progress_log(stderr_text, 200)
                    reason = (
                        f"命令失败（returncode={result.exit_code}"
                        + (f"，stderr={stderr_msg}" if stderr_msg else "")
                        + "）"
                    )
                    return {
                        "success": False,
                        "reason": reason,
                        "findings": [],
                        "errors": [],
                        "fatal_rule_ids": [],
                        "returncode": result.exit_code,
                    }

                if fatal_errors and not parsed_findings:
                    fatal_rule_ids, fatal_reason = _summarize_fatal_rule_errors(fatal_errors)
                    reason = "命中致命规则错误"
                    if fatal_rule_ids:
                        reason += f"（疑似规则: {', '.join(fatal_rule_ids)}）"
                    if fatal_reason:
                        reason += f"：{fatal_reason}"
                    return {
                        "success": False,
                        "reason": reason,
                        "findings": [],
                        "errors": parsed_errors,
                        "fatal_rule_ids": fatal_rule_ids,
                        "returncode": result.exit_code,
                    }

                return {
                    "success": True,
                    "reason": "",
                    "findings": parsed_findings,
                    "errors": parsed_errors,
                    "fatal_rule_ids": [],
                    "returncode": result.exit_code,
                }
            except ValueError as parse_error:
                return {
                    "success": False,
                    "reason": f"结果解析失败: {_truncate_for_progress_log(parse_error, 180)}",
                    "findings": [],
                    "errors": [],
                    "fatal_rule_ids": [],
                    "returncode": -1,
                }
            except Exception as scan_error:
                return {
                    "success": False,
                    "reason": f"执行异常: {_truncate_for_progress_log(scan_error, 180)}",
                    "findings": [],
                    "errors": [],
                    "fatal_rule_ids": [],
                    "returncode": -1,
                }
            finally:
                if rule_file and os.path.exists(rule_file):
                    try:
                        os.unlink(rule_file)
                    except Exception:
                        pass

        async def run_bisect_fallback_scan(reason: str) -> tuple[
            List[Dict[str, Any]],
            List[Dict[str, Any]],
            int,
            int,
        ]:
            fallback_findings: List[Dict[str, Any]] = []
            fallback_errors: List[Dict[str, Any]] = []
            fallback_success = 0
            fallback_failed = 0
            fallback_failure_log_count = 0
            fallback_failure_log_cap = 20
            split_log_count = 0
            split_log_cap = 20
            processed_rules = 0

            _record_scan_progress(
                task_id,
                progress=52,
                stage="execute_rules",
                message=f"合并扫描失败（{reason}），开始二分定位异常规则并优先扫描可合并规则",
                level="warning",
            )

            def update_fallback_progress() -> None:
                progress = 52 + (processed_rules / max(total_rules_for_execution, 1)) * 30
                _record_scan_progress(
                    task_id,
                    progress=progress,
                    stage="execute_rules",
                    message=f"二分回退进度（{processed_rules}/{total_rules_for_execution}）",
                )

            async def bisect_and_scan(rule_entries: List[Dict[str, Any]]) -> None:
                nonlocal fallback_success, fallback_failed, fallback_failure_log_count, split_log_count, processed_rules
                if _is_scan_task_cancelled("opengrep", task_id):
                    return
                if not rule_entries:
                    return

                scan_result = await run_merged_group_scan(
                    rule_entries,
                    timeout_seconds=900,
                )
                if scan_result.get("success"):
                    fallback_success += len(rule_entries)
                    fallback_findings.extend(scan_result.get("findings") or [])
                    fallback_errors.extend(scan_result.get("errors") or [])
                    processed_rules += len(rule_entries)
                    if (
                        processed_rules == 1
                        or processed_rules % 5 == 0
                        or processed_rules == total_rules_for_execution
                    ):
                        update_fallback_progress()
                    return

                if len(rule_entries) == 1:
                    fallback_failed += 1
                    processed_rules += 1
                    single_rule_id = str(
                        ((rule_entries[0].get("rule") or {}).get("id")) or "unknown"
                    )
                    reason_msg = _truncate_for_progress_log(
                        scan_result.get("reason") or "未知失败原因",
                        200,
                    )
                    fatal_rule_ids = scan_result.get("fatal_rule_ids") or []
                    if fallback_failure_log_count < fallback_failure_log_cap:
                        related_rule_note = (
                            f"，关联规则候选: {', '.join(fatal_rule_ids[:3])}"
                            if fatal_rule_ids
                            else ""
                        )
                        _record_scan_progress(
                            task_id,
                            progress=54 + (processed_rules / max(total_rules_for_execution, 1)) * 26,
                            stage="execute_rules",
                            message=(
                                f"二分定位规则失败：{single_rule_id}"
                                f"{related_rule_note}，原因：{reason_msg}"
                            ),
                            level="warning",
                        )
                        fallback_failure_log_count += 1
                    elif fallback_failure_log_count == fallback_failure_log_cap:
                        _record_scan_progress(
                            task_id,
                            progress=54 + (processed_rules / max(total_rules_for_execution, 1)) * 26,
                            stage="execute_rules",
                            message="二分定位失败日志过多，后续失败原因省略显示",
                            level="warning",
                        )
                        fallback_failure_log_count += 1
                    if (
                        processed_rules == 1
                        or processed_rules % 5 == 0
                        or processed_rules == total_rules_for_execution
                    ):
                        update_fallback_progress()
                    return

                if split_log_count < split_log_cap:
                    _record_scan_progress(
                        task_id,
                        progress=54 + (processed_rules / max(total_rules_for_execution, 1)) * 26,
                        stage="execute_rules",
                        message=(
                            f"规则组执行失败，开始二分拆分（组大小 {len(rule_entries)}，"
                            f"原因：{_truncate_for_progress_log(scan_result.get('reason'), 120)}）"
                        ),
                        level="warning",
                    )
                    split_log_count += 1

                mid = len(rule_entries) // 2
                await bisect_and_scan(rule_entries[:mid])
                await bisect_and_scan(rule_entries[mid:])

            await bisect_and_scan(executable_rule_entries)
            if processed_rules and processed_rules != total_rules_for_execution:
                update_fallback_progress()

            return (
                fallback_findings,
                fallback_errors,
                fallback_success,
                fallback_failed,
            )

        _record_scan_progress(
            task_id,
            progress=40,
            stage="execute_rules",
            message=f"执行 opengrep 合并扫描（线程数 {jobs}）",
        )

        initial_scan_result = await run_merged_group_scan(
            executable_rule_entries,
            timeout_seconds=900,
        )

        if _is_scan_task_cancelled("opengrep", task_id):
            await _update_task_state("interrupted", increment_error_count=True)
            _record_scan_progress(
                task_id,
                status="interrupted",
                progress=100,
                stage="interrupted",
                message="扫描任务已中止（用户操作）",
                level="warning",
            )
            return

        if initial_scan_result.get("success"):
            all_findings = initial_scan_result.get("findings") or []
            all_scan_errors = initial_scan_result.get("errors") or []
            successful_rule_count = total_rules_for_execution
            failed_rule_count = 0
        else:
            fallback_reason = initial_scan_result.get("reason") or fallback_reason
            _record_scan_progress(
                task_id,
                progress=50,
                stage="execute_rules",
                message=f"合并扫描失败：{fallback_reason}，将自动使用二分法定位并继续扫描有效规则",
                level="warning",
            )
            (
                fallback_findings,
                fallback_errors,
                fallback_success,
                fallback_failed,
            ) = await run_bisect_fallback_scan(fallback_reason)
            if fallback_success > 0:
                all_findings = fallback_findings
                all_scan_errors = fallback_errors
                successful_rule_count = fallback_success
                failed_rule_count = fallback_failed
                logger.info(
                    "Task %s bisect fallback scan succeeded: success=%s failed=%s findings=%s",
                    task_id,
                    fallback_success,
                    fallback_failed,
                    len(fallback_findings),
                )
            else:
                successful_rule_count = 0
                failed_rule_count = total_rules_for_execution

        _record_scan_progress(
            task_id,
            progress=86,
            stage="aggregate_results",
            message=f"扫描完成，汇总结果中（成功 {successful_rule_count} / 失败 {failed_rule_count}）",
        )

        if _is_scan_task_cancelled("opengrep", task_id):
            await _update_task_state("interrupted", increment_error_count=True)
            _record_scan_progress(
                task_id,
                status="interrupted",
                progress=100,
                stage="interrupted",
                message="扫描任务已中止（用户操作）",
                level="warning",
            )
            return

        if successful_rule_count == 0:
            await _update_task_state("failed", error_count=1)
            _record_scan_progress(
                task_id,
                status="failed",
                progress=100,
                stage="failed",
                message="规则执行阶段全部失败，任务失败",
                level="error",
            )
            logger.error(f"No valid rules executed successfully for task {task_id}")
            return

        logger.info(
            f"Task {task_id}: {successful_rule_count} rules executed successfully, "
            f"{failed_rule_count} rules failed, "
            f"{filtered_rule_count} rules filtered by project language, "
            f"{skipped_rule_count} rules skipped during validation"
        )

        non_fatal_scan_errors = [item for item in all_scan_errors if not _is_fatal_rule_error(item)]
        if all_scan_errors:
            warning_errors = [err for err in all_scan_errors if err.get("level") != "error"]
            if warning_errors:
                logger.info(
                    f"Scan task {task_id} has {len(warning_errors)} parsing warnings "
                    f"(normal for complex C/C++ code, not affecting results)"
                )

        if non_fatal_scan_errors:
            logger.info(
                f"Scan task {task_id} has {len(non_fatal_scan_errors)} non-fatal parsing issues "
                f"(normal, scan continues with other files)"
            )

        error_count = 0
        warning_count = 0
        files_scanned = set()
        lines_scanned = 0
        findings_to_persist: List[Dict[str, Any]] = []
        _record_scan_progress(
            task_id,
            progress=90,
            stage="persist_findings",
            message=f"写入扫描结果中（共 {len(all_findings)} 条）",
        )

        for finding in all_findings:
            try:
                severity = finding.get("extra", {}).get("severity", "INFO")
                if severity == "ERROR":
                    error_count += 1
                elif severity == "WARNING":
                    warning_count += 1

                file_path = normalize_static_scan_file_path(
                    str(finding.get("path", "") or ""),
                    "/scan/project",
                )
                if file_path:
                    files_scanned.add(file_path)

                start_line = finding.get("start", {}).get("line", 0)
                end_line = finding.get("end", {}).get("line", start_line)
                lines_scanned += max(0, end_line - start_line + 1)

                findings_to_persist.append(
                    {
                        "rule": finding,
                        "description": finding.get("extra", {}).get("message"),
                        "file_path": file_path,
                        "start_line": start_line,
                        "code_snippet": finding.get("extra", {}).get("lines"),
                        "severity": severity,
                    }
                )
            except Exception as e:
                logger.error(f"Error processing finding: {e}")
                error_count += 1

        if _is_scan_task_cancelled("opengrep", task_id):
            await _update_task_state("interrupted", increment_error_count=True)
            _record_scan_progress(
                task_id,
                status="interrupted",
                progress=100,
                stage="interrupted",
                message="扫描任务已中止（用户操作）",
                level="warning",
            )
            return

        updated_task = await _update_task_state(
            "completed",
            findings=findings_to_persist,
            error_count=error_count,
            warning_count=warning_count + len(non_fatal_scan_errors),
            files_scanned_count=len(files_scanned),
            lines_scanned_count=lines_scanned,
        )
        if updated_task is not None:
            project_metrics_refresher.enqueue(updated_task.project_id)
        _record_scan_progress(
            task_id,
            status="completed",
            progress=100,
            stage="completed",
            message=f"扫描完成：发现 {len(all_findings)} 条，扫描文件 {len(files_scanned)} 个",
        )
        logger.info(
            f"Scan task {task_id} completed: "
            f"{len(all_findings)} findings from {successful_rule_count} rules, "
            f"{error_count} errors, "
            f"{warning_count} warnings, "
            f"{skipped_rule_count} rules skipped"
        )
    except asyncio.CancelledError:
        logger.warning(f"Opengrep scan task {task_id} interrupted by service shutdown")
        _record_scan_progress(
            task_id,
            status="interrupted",
            progress=100,
            stage="interrupted",
            message="扫描任务已中断（服务关闭或沙箱停止）",
            level="warning",
        )
        await _update_task_state("interrupted", increment_error_count=True)
        raise
    except Exception as e:
        logger.error(f"Error executing opengrep scan for task {task_id}: {e}")
        _record_scan_progress(
            task_id,
            status="failed",
            progress=100,
            stage="failed",
            message=f"扫描异常终止：{str(e)}",
            level="error",
        )
        await _update_task_state("failed", increment_error_count=True)
    finally:
        _pop_scan_container("opengrep", task_id)
        if workspace_dir is not None:
            cleanup_scan_workspace("opengrep", task_id)
        _clear_scan_task_cancel("opengrep", task_id)
        if project_root and project_root.startswith("/tmp") and os.path.exists(project_root):
            try:
                shutil.rmtree(project_root, ignore_errors=True)
                logger.info(f"Cleaned up temporary project directory: {project_root}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary directory {project_root}: {e}")
def _normalize_confidence(confidence: Any) -> Optional[str]:
    """标准化置信度字段，内部统一为 HIGH/MEDIUM/LOW。"""
    return shared_normalize_confidence(confidence)


def _format_confidence_for_response(confidence: Optional[str]) -> Optional[str]:
    """接口返回统一为 HIGH/MEDIUM/LOW。"""
    normalized = _normalize_confidence(confidence)
    return normalized


def _extract_rule_lookup_keys(check_id: Any) -> List[str]:
    """
    从 finding.rule.check_id 里提取可用于匹配 OpengrepRule.name 的候选键。

    例如:
    - "python.security.sql-injection" -> ["python.security.sql-injection", "sql-injection"]
    """
    return shared_extract_rule_lookup_keys(check_id)


def _extract_finding_payload_confidence(rule_data: Any) -> Optional[str]:
    """
    从 finding.rule 结构中提取置信度。

    支持以下常见位置：
    - finding.rule.confidence
    - finding.rule.extra.confidence
    - finding.rule.metadata.confidence
    - finding.rule.extra.metadata.confidence
    """
    return shared_extract_finding_payload_confidence(rule_data)


async def _build_finding_rule_lookup_maps(
    db: AsyncSession,
    findings: List[OpengrepFinding],
) -> tuple[
    Dict[str, Optional[str]],
    Dict[str, Optional[List[str]]],
    Dict[str, str],
]:
    """为 finding 列表批量构建规则查找映射，避免重复查询。"""
    rule_name_candidates: set[str] = set()
    for finding in findings:
        if not isinstance(finding.rule, dict):
            continue
        check_id = finding.rule.get("check_id") or finding.rule.get("id")
        for key in _extract_rule_lookup_keys(check_id):
            rule_name_candidates.add(key)

    rule_confidence_map: Dict[str, Optional[str]] = {}
    rule_cwe_map: Dict[str, Optional[List[str]]] = {}
    rule_display_name_map: Dict[str, str] = {}
    if not rule_name_candidates:
        return rule_confidence_map, rule_cwe_map, rule_display_name_map

    rule_result = await db.execute(
        select(OpengrepRule.name, OpengrepRule.confidence, OpengrepRule.cwe).where(
            OpengrepRule.name.in_(rule_name_candidates)
        )
    )
    for rule_name, rule_confidence, rule_cwe in rule_result.all():
        normalized_rule_name = str(rule_name or "").strip()
        if not normalized_rule_name:
            continue
        for lookup_key in _extract_rule_lookup_keys(normalized_rule_name):
            rule_confidence_map[lookup_key] = _normalize_confidence(rule_confidence)
            rule_cwe_map[lookup_key] = rule_cwe
            rule_display_name_map[lookup_key] = normalized_rule_name

    return rule_confidence_map, rule_cwe_map, rule_display_name_map


def _resolve_finding_enrichment(
    finding: OpengrepFinding,
    *,
    rule_confidence_map: Dict[str, Optional[str]],
    rule_cwe_map: Dict[str, Optional[List[str]]],
    rule_display_name_map: Dict[str, str],
) -> tuple[Optional[str], Optional[List[str]], Optional[str]]:
    """统一解析 finding 的 confidence/cwe/rule_name。"""
    resolved_confidence = _extract_finding_payload_confidence(finding.rule)
    resolved_cwe: Optional[List[str]] = None
    resolved_rule_name: Optional[str] = None

    lookup_keys: List[str] = []
    if isinstance(finding.rule, dict):
        check_id = finding.rule.get("check_id") or finding.rule.get("id")
        lookup_keys = _extract_rule_lookup_keys(check_id)

    for key in lookup_keys:
        if not resolved_confidence:
            mapped_confidence = rule_confidence_map.get(key)
            if mapped_confidence:
                resolved_confidence = mapped_confidence

        if resolved_cwe is None:
            mapped_cwe = rule_cwe_map.get(key)
            if mapped_cwe is not None:
                resolved_cwe = mapped_cwe

        if not resolved_rule_name:
            mapped_rule_name = rule_display_name_map.get(key)
            if mapped_rule_name:
                resolved_rule_name = mapped_rule_name

        if resolved_confidence and resolved_cwe is not None and resolved_rule_name:
            break

    return resolved_confidence, resolved_cwe, resolved_rule_name


def _serialize_finding_response(
    finding: OpengrepFinding,
    *,
    rule_confidence_map: Dict[str, Optional[str]],
    rule_cwe_map: Dict[str, Optional[List[str]]],
    rule_display_name_map: Dict[str, str],
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_confidence, resolved_cwe, resolved_rule_name = _resolve_finding_enrichment(
        finding,
        rule_confidence_map=rule_confidence_map,
        rule_cwe_map=rule_cwe_map,
        rule_display_name_map=rule_display_name_map,
    )
    resolved_file_path, resolved_line_start = resolve_static_finding_location(
        finding.file_path,
        line_start=finding.start_line,
        project_root=project_root,
    )
    return {
        "id": finding.id,
        "scan_task_id": finding.scan_task_id,
        "rule": finding.rule,
        "description": finding.description,
        "file_path": finding.file_path,
        "start_line": finding.start_line,
        "resolved_file_path": resolved_file_path,
        "resolved_line_start": resolved_line_start,
        "code_snippet": finding.code_snippet,
        "severity": finding.severity,
        "status": finding.status,
        "confidence": _format_confidence_for_response(resolved_confidence),
        "cwe": resolved_cwe,
        "rule_name": resolved_rule_name,
    }


async def _count_high_confidence_findings_by_task_ids(
    db: AsyncSession,
    task_ids: List[str],
) -> Dict[str, int]:
    return await shared_count_high_confidence_findings_by_task_ids(db, task_ids)


def _build_finding_path_candidates(file_path: Optional[str]) -> List[str]:
    raw = str(file_path or "").strip().replace("\\", "/")
    if not raw:
        return []

    deduplicated: List[str] = []
    seen = set()

    def _append(value: str) -> None:
        normalized = value.strip()
        if not normalized or normalized in seen:
            return
        deduplicated.append(normalized)
        seen.add(normalized)

    if raw.startswith("/"):
        _append(raw)

    for item in build_zip_member_path_candidates(raw):
        _append(item)

    return deduplicated


LANGUAGE_EXTENSION_MAP: Dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".php": "php",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".cs": "csharp",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".m": "objective-c",
    ".mm": "objective-c",
}

LANGUAGE_FILENAME_MAP: Dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "make",
}

RULE_LANGUAGE_ALIASES: Dict[str, str] = {
    "js": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
    "ts": "typescript",
    "golang": "go",
    "c#": "csharp",
    "csharp": "csharp",
    "c++": "cpp",
    "objc": "objective-c",
    "obj-c": "objective-c",
    "objectivec": "objective-c",
}

RULE_GLOBAL_LANGUAGES = {
    "generic",
    "regex",
    "all",
    "none",
    "yaml",
    "json",
}

SKIP_LANGUAGE_DETECTION_DIRS = {
    ".git",
    ".svn",
    ".hg",
    "__pycache__",
    "node_modules",
    "vendor",
    "target",
    "build",
    "dist",
    "out",
    "venv",
    ".venv",
}

MAX_PROJECT_LANGUAGE_DETECTION_FILES = 120000


def _normalize_rule_language(language: Optional[str]) -> str:
    normalized = str(language or "").strip().lower()
    if not normalized:
        return ""
    return RULE_LANGUAGE_ALIASES.get(normalized, normalized)


def _extract_rule_languages(rule_payload: Dict[str, Any], fallback_language: Optional[str]) -> set[str]:
    languages: set[str] = set()
    rule_languages = rule_payload.get("languages")
    if isinstance(rule_languages, list):
        for item in rule_languages:
            normalized = _normalize_rule_language(str(item))
            if normalized:
                languages.add(normalized)

    if not languages and fallback_language:
        normalized = _normalize_rule_language(fallback_language)
        if normalized:
            languages.add(normalized)
    return languages


def _detect_project_languages(scan_root: str) -> set[str]:
    detected: set[str] = set()
    scanned_files = 0

    for root, dirs, files in os.walk(scan_root):
        dirs[:] = [
            item
            for item in dirs
            if item not in SKIP_LANGUAGE_DETECTION_DIRS
            and not item.startswith(".")
            and not _is_test_like_directory(item)
        ]
        for filename in files:
            scanned_files += 1
            if scanned_files > MAX_PROJECT_LANGUAGE_DETECTION_FILES:
                return detected

            suffix = Path(filename).suffix.lower()
            if suffix in LANGUAGE_EXTENSION_MAP:
                detected.add(LANGUAGE_EXTENSION_MAP[suffix])
                continue

            language_by_name = LANGUAGE_FILENAME_MAP.get(filename.lower())
            if language_by_name:
                detected.add(language_by_name)

    return detected


def _should_scan_rule_for_languages(
    rule_languages: set[str], project_languages: set[str]
) -> bool:
    if not rule_languages:
        return True
    if rule_languages & RULE_GLOBAL_LANGUAGES:
        return True
    if not project_languages:
        return True
    return bool(rule_languages & project_languages)


def _resolve_opengrep_scan_jobs() -> int:
    configured = str(os.getenv("OPENGREP_SCAN_JOBS", "")).strip()
    if configured.isdigit():
        return max(1, min(16, int(configured)))
    cpu_count = os.cpu_count() or 2
    return max(1, min(8, cpu_count))


@router.get("/tasks", response_model=List[OpengrepScanTaskResponse])
async def list_static_tasks(
    project_id: Optional[str] = Query(None, description="按项目ID过滤"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    获取静态代码扫描任务列表

    - 可按项目ID过滤
    """
    if project_id:
        project = await db.get(Project, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
        query = select(OpengrepScanTask).where(OpengrepScanTask.project_id == project_id)
    else:
        query = select(OpengrepScanTask)

    query = query.order_by(OpengrepScanTask.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    tasks = result.scalars().all()
    high_confidence_counts = await _count_high_confidence_findings_by_task_ids(
        db,
        [task.id for task in tasks],
    )
    for task in tasks:
        setattr(task, "high_confidence_count", int(high_confidence_counts.get(task.id, 0)))
    return tasks


@router.post("/tasks", response_model=OpengrepScanTaskResponse)
async def create_static_task(
    request: OpengrepScanTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    创建一个静态代码扫描任务

    后台执行 opengrep 扫描，加载指定的规则对代码库进行分析
    优先检查 uploads/zip_files 目录中的 zip 文件，如果存在则使用其解压目录
    """
    # 验证项目存在
    result = await db.execute(select(Project).where(Project.id == request.project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    if not request.rule_ids:
        raise HTTPException(status_code=400, detail="rule_ids 不能为空")

    normalized_rule_ids = list(dict.fromkeys(request.rule_ids))

    # 验证规则存在
    result = await db.execute(
        select(OpengrepRule).where(OpengrepRule.id.in_(normalized_rule_ids))
    )
    rules = result.scalars().all()
    if len(rules) != len(normalized_rule_ids):
        raise HTTPException(status_code=404, detail="部分规则不存在")

    # 获取项目根目录（先从 zip 文件中查找）
    project_root = await _get_project_root(request.project_id)

    if not project_root:
        raise HTTPException(
            status_code=400,
            detail=f"找不到项目的 zip 文件，请先上传项目 ZIP 文件到 uploads/zip_files 目录",
        )

    # 创建扫描任务
    scan_task = OpengrepScanTask(
        project_id=request.project_id,
        name=request.name or f"Scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        status="pending",
        target_path=request.target_path,
        rulesets=json.dumps([{"rule_id": rid} for rid in normalized_rule_ids]),
    )
    db.add(scan_task)
    await db.commit()
    response = _build_opengrep_scan_task_response(scan_task)
    task_id = response.id
    _record_scan_progress(
        task_id,
        status="pending",
        progress=2,
        stage="pending",
        message="任务已创建，等待调度执行",
    )

    await _release_request_db_session(db)
    _launch_static_background_job(
        "opengrep",
        task_id,
        _execute_opengrep_scan(
            task_id,
            project_root,
            request.target_path,
            normalized_rule_ids,
        ),
    )

    return response


@router.delete("/tasks/{task_id}")
async def delete_static_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """删除静态代码扫描任务及其相关漏洞记录"""
    result = await db.execute(select(OpengrepScanTask).where(OpengrepScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    await db.delete(task)
    await db.commit()

    return {"message": "任务已删除", "task_id": task_id}


@router.get("/tasks/{task_id}", response_model=OpengrepScanTaskResponse)
async def get_static_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取静态代码扫描任务详情"""
    result = await db.execute(select(OpengrepScanTask).where(OpengrepScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    high_confidence_counts = await _count_high_confidence_findings_by_task_ids(
        db,
        [task.id],
    )
    setattr(task, "high_confidence_count", int(high_confidence_counts.get(task.id, 0)))
    return task


@router.post("/tasks/{task_id}/interrupt")
async def interrupt_static_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """中止运行中的 Opengrep 静态扫描任务。"""
    result = await db.execute(select(OpengrepScanTask).where(OpengrepScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task.status in {"completed", "failed", "interrupted"}:
        return {
            "message": f"任务当前状态为 {task.status}，无需中止",
            "task_id": task_id,
            "status": task.status,
        }

    _request_scan_task_cancel("opengrep", task_id)
    task.status = "interrupted"
    task.error_count = (task.error_count or 0) + 1
    _sync_task_scan_duration(task)
    await db.commit()
    _record_scan_progress(
        task_id,
        status="interrupted",
        progress=100,
        stage="interrupted",
        message="扫描任务已中止（用户操作）",
        level="warning",
    )

    return {"message": "任务已中止", "task_id": task_id, "status": "interrupted"}


@router.get("/tasks/{task_id}/progress", response_model=OpengrepScanProgressResponse)
async def get_static_task_progress(
    task_id: str,
    include_logs: bool = Query(False, description="是否返回进度日志"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取静态代码扫描任务执行进度"""
    result = await db.execute(select(OpengrepScanTask).where(OpengrepScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    state = _scan_progress_store.get(task_id)
    if not state:
        fallback_progress = 0.0
        if task.status == "running":
            fallback_progress = 10.0
        elif task.status in {"completed", "failed", "interrupted"}:
            fallback_progress = 100.0
        state = {
            "task_id": task_id,
            "status": task.status,
            "progress": fallback_progress,
            "current_stage": task.status,
            "message": f"任务状态：{task.status}",
            "started_at": _dt_to_iso(task.created_at) or _utc_now_iso(),
            "updated_at": _dt_to_iso(task.updated_at) or _dt_to_iso(task.created_at) or _utc_now_iso(),
            "logs": [],
        }

    response_payload = dict(state)
    if not include_logs:
        response_payload["logs"] = []
    return response_payload


@router.get("/tasks/{task_id}/findings", response_model=List[OpengrepFindingResponse])
async def get_static_task_findings(
    task_id: str,
    severity: Optional[str] = Query(None, description="按严重程度过滤: ERROR, WARNING, INFO"),
    confidence: Optional[str] = Query(None, description="按置信度过滤: HIGH, MEDIUM, LOW"),
    status: Optional[str] = Query(None, description="按状态过滤: open, verified, false_positive"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取静态代码扫描任务的漏洞列表"""
    # 验证任务存在
    result = await db.execute(select(OpengrepScanTask).where(OpengrepScanTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    project_root = await _get_project_root(task.project_id)

    confidence_filter = _normalize_confidence(confidence)
    if confidence is not None and confidence_filter is None:
        raise HTTPException(status_code=400, detail="置信度必须为 HIGH/MEDIUM/LOW")

    # 构建查询
    query = select(OpengrepFinding).where(OpengrepFinding.scan_task_id == task_id)

    if severity:
        query = query.where(OpengrepFinding.severity == severity)
    if status:
        query = query.where(OpengrepFinding.status == status)

    # 无 confidence 过滤时直接走数据库分页；有 confidence 过滤时需要先解析映射后再分页
    if confidence_filter is None:
        query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    findings = result.scalars().all()

    (
        rule_confidence_map,
        rule_cwe_map,
        rule_display_name_map,
    ) = await _build_finding_rule_lookup_maps(db, findings)

    response_findings = []
    for finding in findings:
        finding_dict = _serialize_finding_response(
            finding,
            rule_confidence_map=rule_confidence_map,
            rule_cwe_map=rule_cwe_map,
            rule_display_name_map=rule_display_name_map,
            project_root=project_root,
        )

        if confidence_filter and finding_dict.get("confidence") != confidence_filter:
            continue
        response_findings.append(finding_dict)

    if confidence_filter is not None:
        response_findings = response_findings[skip : skip + limit]

    return response_findings


@router.get("/tasks/{task_id}/findings/{finding_id}", response_model=OpengrepFindingResponse)
async def get_static_task_finding(
    task_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取静态代码扫描任务的单条漏洞详情。"""
    task_result = await db.execute(select(OpengrepScanTask).where(OpengrepScanTask.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    finding_result = await db.execute(
        select(OpengrepFinding).where(
            (OpengrepFinding.id == finding_id)
            & (OpengrepFinding.scan_task_id == task_id)
        )
    )
    finding = finding_result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="漏洞不存在")

    (
        rule_confidence_map,
        rule_cwe_map,
        rule_display_name_map,
    ) = await _build_finding_rule_lookup_maps(db, [finding])

    project_root = await _get_project_root(task.project_id)

    return _serialize_finding_response(
        finding,
        rule_confidence_map=rule_confidence_map,
        rule_cwe_map=rule_cwe_map,
        rule_display_name_map=rule_display_name_map,
        project_root=project_root,
    )


@router.get(
    "/tasks/{task_id}/findings/{finding_id}/context",
    response_model=OpengrepFindingContextResponse,
)
async def get_static_task_finding_context(
    task_id: str,
    finding_id: str,
    before: int = Query(5, ge=0, le=20),
    after: int = Query(5, ge=0, le=20),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """获取某条静态扫描漏洞的命中上下文代码。"""
    task_result = await db.execute(
        select(OpengrepScanTask).where(OpengrepScanTask.id == task_id)
    )
    task = task_result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    finding_result = await db.execute(
        select(OpengrepFinding).where(
            (OpengrepFinding.id == finding_id)
            & (OpengrepFinding.scan_task_id == task_id)
        )
    )
    finding = finding_result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="漏洞不存在")

    project_root = await _get_project_root(task.project_id)
    if not project_root:
        raise HTTPException(status_code=404, detail="未找到项目源码，无法加载上下文")

    try:
        scan_rule = finding.rule if isinstance(finding.rule, dict) else {}
        start_line = (
            int(scan_rule.get("start", {}).get("line") or 0)
            if isinstance(scan_rule, dict)
            else 0
        )
        end_line = (
            int(scan_rule.get("end", {}).get("line") or 0)
            if isinstance(scan_rule, dict)
            else 0
        )
        if not start_line:
            start_line = int(finding.start_line or 1)
        if not end_line or end_line < start_line:
            end_line = start_line

        resolved_file_path: Optional[str] = None
        selected_relative_path: Optional[str] = None

        for candidate in _build_finding_path_candidates(finding.file_path):
            if os.path.isabs(candidate):
                normalized_candidate = os.path.normpath(candidate)
            else:
                normalized_candidate = os.path.normpath(
                    os.path.join(project_root, candidate)
                )
            if not normalized_candidate.startswith(os.path.normpath(project_root)):
                continue
            if os.path.isfile(normalized_candidate):
                resolved_file_path = normalized_candidate
                selected_relative_path = os.path.relpath(
                    normalized_candidate, project_root
                )
                break

        if not resolved_file_path:
            raise HTTPException(status_code=404, detail="未找到命中源码文件")

        with open(resolved_file_path, "r", encoding="utf-8", errors="ignore") as f:
            source_lines = f.read().splitlines()

        total_lines = len(source_lines)
        if total_lines == 0:
            return {
                "task_id": task_id,
                "finding_id": finding_id,
                "file_path": selected_relative_path or finding.file_path,
                "start_line": start_line,
                "end_line": end_line,
                "before": before,
                "after": after,
                "total_lines": 0,
                "lines": [],
            }

        context_start = max(1, start_line - before)
        context_end = min(total_lines, end_line + after)
        context_lines: List[Dict[str, Any]] = []

        for line_no in range(context_start, context_end + 1):
            context_lines.append(
                {
                    "line_number": line_no,
                    "content": source_lines[line_no - 1],
                    "is_hit": start_line <= line_no <= end_line,
                }
            )

        return {
            "task_id": task_id,
            "finding_id": finding_id,
            "file_path": selected_relative_path or finding.file_path,
            "start_line": start_line,
            "end_line": end_line,
            "before": before,
            "after": after,
            "total_lines": total_lines,
            "lines": context_lines,
        }
    finally:
        if project_root and project_root.startswith("/tmp") and os.path.exists(project_root):
            shutil.rmtree(project_root, ignore_errors=True)


@router.post("/findings/{finding_id}/status")
async def update_static_task_finding(
    finding_id: str,
    status: str = Query(..., pattern="^(open|verified|false_positive)$", description="新状态"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    更新静态代码扫描任务的某个漏洞状态

    可用状态：open(开放), verified(已验证), false_positive(误报)
    """
    result = await db.execute(select(OpengrepFinding).where(OpengrepFinding.id == finding_id))
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="漏洞不存在")

    finding.status = status
    await db.commit()

    return {"message": "漏洞状态已更新", "finding_id": finding_id, "status": status}
