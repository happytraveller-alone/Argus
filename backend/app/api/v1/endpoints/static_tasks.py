import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_
from sqlalchemy.exc import IntegrityError, ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.core.config import settings
from app.db.session import async_session_factory, get_db
from app.models.opengrep import OpengrepFinding, OpengrepRule, OpengrepScanTask
from app.models.gitleaks import GitleaksScanTask, GitleaksFinding, GitleaksRule
from app.models.project import Project
from app.models.user import User
from app.models.user_config import UserConfig
from app.schemas.opengrep import (
    OpengrepRuleCreateRequest,
    OpengrepRulePatchResponse,
    OpengrepRuleTextCreateRequest,
    OpengrepRuleTextResponse,
    OpengrepRuleUpdateRequest,
)
from app.schemas.gitleaks_rules import (
    GitleaksRuleBatchUpdateRequest,
    GitleaksRuleCreateRequest,
    GitleaksRuleResponse,
    GitleaksRuleUpdateRequest,
)
from app.services.rule import get_rule_by_patch, validate_generic_rule
from app.services.upload.upload_manager import UploadManager
from app.services.llm_rule.repo_cache_manager import GlobalRepoCacheManager
from app.services.llm.service import LLMService, LLMConfigError
from app.services.gitleaks_rules_seed import ensure_builtin_gitleaks_rules
from app.services.opengrep_confidence import (
    count_high_confidence_findings_by_task_ids as shared_count_high_confidence_findings_by_task_ids,
    extract_finding_payload_confidence as shared_extract_finding_payload_confidence,
    extract_rule_lookup_keys as shared_extract_rule_lookup_keys,
    normalize_confidence as shared_normalize_confidence,
)

# ============ Schemas ============


class OpengrepRuleSingleUploadRequest(BaseModel):
    """上传单条规则请求"""

    id: Optional[str] = Field(None, description="规则ID，不提供时自动生成")
    name: str = Field(..., description="规则名称")
    pattern_yaml: str = Field(..., description="规则的 YAML 内容")
    language: str = Field(..., description="编程语言，如 python, java, javascript")
    severity: str = Field("WARNING", description="严重程度: ERROR, WARNING, INFO")
    confidence: Optional[str] = Field(None, description="置信度: HIGH, MEDIUM, LOW")
    description: Optional[str] = Field(None, description="规则描述")
    cwe: Optional[List[str]] = Field(None, description="CWE列表")
    source: str = Field("json", description="规则来源，默认为 json")
    patch: Optional[str] = Field(None, description="补丁或相关链接")
    correct: bool = Field(True, description="规则是否正确")
    is_active: bool = Field(True, description="规则是否启用")


class OpengrepRuleSingleUploadResponse(BaseModel):
    """上传单条规则响应"""

    rule_id: str
    name: str
    language: str
    severity: str
    confidence: Optional[str]
    description: Optional[str]
    cwe: Optional[List[str]]
    source: str
    is_active: bool
    created_at: datetime
    message: str

    model_config = ConfigDict(from_attributes=True)


class OpengrepRuleBatchUpdateRequest(BaseModel):
    """批量更新规则状态请求"""

    rule_ids: Optional[List[str]] = Field(None, description="规则ID列表")
    language: Optional[str] = Field(None, description="按编程语言过滤")
    source: Optional[str] = Field(None, description="按来源过滤: internal, patch")
    severity: Optional[str] = Field(None, description="按严重程度过滤: ERROR, WARNING, INFO")
    confidence: Optional[str] = Field(None, description="按置信度过滤: HIGH, MEDIUM, LOW")
    keyword: Optional[str] = Field(None, description="按规则ID或名称过滤（大小写不敏感）")
    current_is_active: Optional[bool] = Field(
        None,
        description="按当前启用状态过滤（true=仅当前已启用，false=仅当前已禁用）",
    )
    is_active: bool = Field(..., description="要设置的激活状态")


class OpengrepRulePatchUploadResponse(BaseModel):
    """Patch 文件上传生成规则响应"""

    total_files: int = Field(..., description="总共需要处理的 patch 文件数")
    success_count: int = Field(..., description="成功生成规则的数量")
    failed_count: int = Field(..., description="失败的数量")
    skipped_count: int = Field(0, description="跳过的文件数（不符合命名规范）")
    details: List[Dict[str, Any]] = Field(default_factory=list, description="详细结果")


class PatchRuleCreationResponse(BaseModel):
    """Patch 文件上传创建占位符规则响应"""

    rule_ids: List[str] = Field(..., description="创建的规则ID列表")
    total_files: int = Field(..., description="处理的 patch 文件数")
    message: str = Field(..., description="状态消息")


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

    model_config = ConfigDict(from_attributes=True)


class OpengrepFindingResponse(BaseModel):
    """扫描发现响应"""

    id: str
    scan_task_id: str
    rule: Dict[str, Any]
    description: Optional[str]
    file_path: str
    start_line: Optional[int]
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


# ============ 后台扫描执行 ============


def _is_test_like_directory(name: str) -> bool:
    return "test" in (name or "").lower()


async def _cleanup_incorrect_rules(db: AsyncSession) -> None:
    """移除 correct=false 的规则记录。"""
    try:
        await db.execute(delete(OpengrepRule).where(OpengrepRule.correct == False))
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to cleanup incorrect rules: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


def _prune_test_directories(scan_root: str) -> int:
    removed_count = 0
    for root, dirs, _ in os.walk(scan_root, topdown=True):
        keep_dirs: list[str] = []
        for dirname in dirs:
            if _is_test_like_directory(dirname):
                shutil.rmtree(os.path.join(root, dirname), ignore_errors=True)
                removed_count += 1
            else:
                keep_dirs.append(dirname)
        dirs[:] = keep_dirs
    return removed_count


async def _get_project_root(project_id: str) -> Optional[str]:
    """
    获取项目根目录

    优先检查 uploads/zip_files 目录中是否存在该项目的 zip 文件
    如果存在，解压到临时目录并返回临时目录路径
    否则返回 None

    Args:
        project_id: 项目ID

    Returns:
        项目根目录路径，如果找不到 zip 文件返回 None
    """
    try:
        # 构建 uploads/zip_files 目录路径
        zip_dir = Path(getattr(settings, "ZIP_STORAGE_PATH", "./uploads/zip_files"))

        if not zip_dir.exists():
            logger.warning(f"Upload directory not found: {zip_dir}")
            return None

        # 查找项目 ID 对应的 zip 文件
        # 支持 {project_id}.zip 或 {project_id}_*.zip 的格式
        zip_files = list(zip_dir.glob(f"{project_id}.zip")) + list(
            zip_dir.glob(f"{project_id}_*.zip")
        )

        if not zip_files:
            logger.info(f"No zip file found for project {project_id}")
            return None

        zip_file = zip_files[0]  # 取第一个匹配的 zip 文件
        logger.info(f"Found zip file for project {project_id}: {zip_file}")

        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix=f"deepaudit_{project_id}_")

        # 解压 zip 文件
        try:
            with zipfile.ZipFile(zip_file, "r") as zf:
                zf.extractall(temp_dir)
            logger.info(f"Extracted zip file to {temp_dir}")
        except zipfile.BadZipFile as e:
            logger.error(f"Invalid zip file {zip_file}: {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None
        except Exception as e:
            logger.error(f"Failed to extract zip file {zip_file}: {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        # 上传和扫描统一排除目录名包含 test 的文件夹，减少无效扫描开销
        removed_test_dirs = _prune_test_directories(temp_dir)
        if removed_test_dirs:
            logger.info(
                "Removed %s test-like directories before static scan for project %s",
                removed_test_dirs,
                project_id,
            )

        # 检查解压后的目录是否只有一个子目录（常见的 zip 打包格式）
        items = os.listdir(temp_dir)
        items = [item for item in items if not item.startswith("__") and not item.startswith(".")]

        if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
            # 只有一个子目录，使用该子目录作为项目根目录
            return os.path.join(temp_dir, items[0])

        return temp_dir

    except Exception as e:
        logger.error(f"Error getting project root for {project_id}: {e}")
        return None


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


async def _get_unique_rule_name(db: AsyncSession, base_name: str) -> str:
    """
    获取唯一的规则名称
    
    如果规则名已存在，则在后面追加 _1, _2, _3 等递增数字
    
    Args:
        db: 数据库会话
        base_name: 基础规则名
        
    Returns:
        唯一的规则名
    """
    # 检查基础名称是否存在
    result = await db.execute(
        select(OpengrepRule).where(OpengrepRule.name == base_name)
    )
    if not result.scalar_one_or_none():
        return base_name
    
    # 如果存在，尝试添加递增数字
    counter = 1
    while True:
        new_name = f"{base_name}_{counter}"
        result = await db.execute(
            select(OpengrepRule).where(OpengrepRule.name == new_name)
        )
        if not result.scalar_one_or_none():
            return new_name
        counter += 1


async def _validate_opengrep_rule(yaml_content: str) -> tuple[bool, Optional[str]]:
    """
    使用 opengrep --validate 验证规则是否有效
    
    Args:
        yaml_content: 规则的 YAML 内容
        
    Returns:
        (is_valid, error_message): 验证是否通过，失败时返回错误信息
    """
    try:
        # 创建临时文件保存规则
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as tmp_file:
            tmp_file.write(yaml_content)
            tmp_file_path = tmp_file.name
        
        try:
            # 在线程池中执行 opengrep 验证
            loop = asyncio.get_event_loop()
            validate_result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["opengrep", "--config", tmp_file_path, "--validate"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                ),
            )
            
            if validate_result.returncode == 0:
                return True, None
            else:
                error_msg = validate_result.stderr or "未知错误"
                return False, error_msg
        finally:
            # 删除临时文件
            if os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                except Exception:
                    pass
    except subprocess.TimeoutExpired:
        return False, "规则验证超时"
    except FileNotFoundError:
        logger.warning("opengrep 命令未找到，跳过规则验证")
        return True, None
    except Exception as e:
        return False, f"规则验证异常: {str(e)}"


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


_static_scan_process_lock = threading.Lock()
_static_running_scan_processes: Dict[str, subprocess.Popen] = {}
_static_cancelled_scan_tasks: set[str] = set()


def _scan_task_key(scan_type: str, task_id: str) -> str:
    return f"{scan_type}:{task_id}"


def _is_scan_task_cancelled(scan_type: str, task_id: str) -> bool:
    key = _scan_task_key(scan_type, task_id)
    with _static_scan_process_lock:
        return key in _static_cancelled_scan_tasks


def _clear_scan_task_cancel(scan_type: str, task_id: str) -> None:
    key = _scan_task_key(scan_type, task_id)
    with _static_scan_process_lock:
        _static_cancelled_scan_tasks.discard(key)


def _request_scan_task_cancel(scan_type: str, task_id: str) -> bool:
    """请求取消扫描任务并尝试结束对应进程。"""
    key = _scan_task_key(scan_type, task_id)
    process = None
    with _static_scan_process_lock:
        _static_cancelled_scan_tasks.add(key)
        process = _static_running_scan_processes.get(key)

    if not process:
        return False

    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
    except Exception as e:
        logger.warning("Failed to terminate %s scan process for task %s: %s", scan_type, task_id, e)
    return True


def _run_subprocess_with_tracking(
    scan_type: str,
    task_id: str,
    cmd: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    """执行外部命令并记录进程句柄，便于用户中止时杀掉进程。"""
    key = _scan_task_key(scan_type, task_id)
    process: Optional[subprocess.Popen] = None

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        with _static_scan_process_lock:
            _static_running_scan_processes[key] = process

        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired:
        if process:
            process.kill()
            process.communicate()
        raise
    finally:
        with _static_scan_process_lock:
            _static_running_scan_processes.pop(key, None)


def _as_utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _calc_scan_duration_ms_from_created_at(
    created_at: Optional[datetime],
    finished_at: Optional[datetime] = None,
) -> int:
    start_at = _as_utc_datetime(created_at)
    if start_at is None:
        return 0

    end_at = _as_utc_datetime(finished_at) or datetime.now(timezone.utc)
    duration_ms = int((end_at - start_at).total_seconds() * 1000)
    return max(0, duration_ms)


def _sync_task_scan_duration(task: Any, finished_at: Optional[datetime] = None) -> None:
    task.scan_duration_ms = _calc_scan_duration_ms_from_created_at(
        getattr(task, "created_at", None),
        finished_at=finished_at,
    )


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
    async with async_session_factory() as db:
        try:
            # 获取任务
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

            # 更新任务状态为运行中
            task.status = "running"
            await db.commit()
            _record_scan_progress(
                task_id,
                status="running",
                progress=8,
                stage="init",
                message="开始准备扫描环境",
            )

            # 获取活跃规则
            result = await db.execute(
                select(OpengrepRule).where(
                    (OpengrepRule.id.in_(rule_ids)) & (OpengrepRule.is_active == True)
                )
            )
            rules = result.scalars().all()

            if not rules:
                task.status = "failed"
                task.error_count = 1
                _sync_task_scan_duration(task)
                await db.commit()
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

            # 生成临时规则文件
            full_target_path = os.path.join(project_root, target_path)
            if not os.path.exists(full_target_path):
                task.status = "failed"
                task.error_count = 1
                _sync_task_scan_duration(task)
                await db.commit()
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

            # 辅助函数：过滤掉所有 null 值（Semgrep/Opengrep 不允许 null）
            def remove_null_values(obj):
                """递归移除字典/列表中的 null 值"""
                if isinstance(obj, dict):
                    return {k: remove_null_values(v) for k, v in obj.items() if v is not None}
                elif isinstance(obj, list):
                    return [remove_null_values(item) for item in obj if item is not None]
                else:
                    return obj

            def has_deprecated_features(rule):
                """检查规则是否包含已弃用的特性"""
                deprecated_keys = [
                    "pattern-where-python",  # 已弃用的 Python 条件
                    "pattern-not-regex",     # 部分版本已弃用
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
                
                # 规则必须有 id
                if "id" not in rule:
                    return False, "missing id"
                
                # 检查是否包含已弃用特性
                has_deprecated, deprecated_key = has_deprecated_features(rule)
                if has_deprecated:
                    return False, f"uses deprecated feature: {deprecated_key}"
                
                # 检查是否是污点分析规则
                mode = rule.get("mode")
                if mode == "taint":
                    # 污点分析规则必须同时有 pattern-sources 和 pattern-sinks
                    has_sources = "pattern-sources" in rule
                    has_sinks = "pattern-sinks" in rule
                    if not (has_sources and has_sinks):
                        return False, f"taint mode missing sources({has_sources}) or sinks({has_sinks})"
                else:
                    # 非污点分析规则需要至少一个标准模式属性
                    pattern_keys = [
                        "pattern", "patterns", "pattern-either", "pattern-regex"
                    ]
                    has_pattern = any(key in rule for key in pattern_keys)
                    if not has_pattern:
                        return False, "missing standard pattern attributes"
                
                return True, "valid"

            # 准备扫描环境变量
            scan_env = os.environ.copy()
            for proxy_key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            ):
                scan_env.pop(proxy_key, None)
            scan_env["NO_PROXY"] = "*"
            scan_env["no_proxy"] = "*"

            # 解析并验证所有规则，构建有效规则列表（含语言信息）
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

                    for r in rule_data["rules"]:
                        cleaned_rule = remove_null_values(r)
                        is_valid, reason = is_valid_rule(cleaned_rule)
                        if is_valid:
                            valid_rule_entries.append(
                                {
                                    "rule": cleaned_rule,
                                    "languages": _extract_rule_languages(
                                        cleaned_rule, rule.language
                                    ),
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
                task.status = "failed"
                task.error_count = 1
                _sync_task_scan_duration(task)
                await db.commit()
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

            # 单次执行扫描：将规则合并后运行一次 opengrep，避免重复遍历项目造成的性能损耗
            all_findings: List[Dict[str, Any]] = []
            all_scan_errors: List[Dict[str, Any]] = []
            successful_rule_count = 0
            failed_rule_count = 0
            total_rules_for_execution = len(executable_rule_entries)
            fallback_reason = "合并执行无有效结果"
            jobs = _resolve_opengrep_scan_jobs()
            use_jobs_option = True
            loop = asyncio.get_event_loop()

            async def run_merged_group_scan(
                rule_entries: List[Dict[str, Any]],
                *,
                timeout_seconds: int,
            ) -> Dict[str, Any]:
                nonlocal use_jobs_option
                rule_file = None
                try:
                    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tf:
                        yaml.dump(
                            {"rules": [entry["rule"] for entry in rule_entries]},
                            tf,
                            sort_keys=False,
                            default_flow_style=False,
                        )
                        rule_file = tf.name

                    cmd = ["opengrep", "--config", rule_file, "--json"]
                    if use_jobs_option:
                        cmd.extend(["--jobs", str(jobs)])
                    cmd.append(full_target_path)

                    result = await loop.run_in_executor(
                        None,
                        lambda: _run_subprocess_with_tracking(
                            "opengrep",
                            task_id,
                            cmd,
                            env=scan_env,
                            timeout=timeout_seconds,
                        ),
                    )

                    # 兼容旧版本 opengrep 不支持 --jobs 参数（仅切换一次）
                    if use_jobs_option and result.returncode != 0 and (
                        "unrecognized arguments: --jobs" in (result.stderr or "")
                        or "unknown option '--jobs'" in (result.stderr or "")
                    ):
                        logger.warning(
                            "opengrep does not support --jobs, fallback to single process mode"
                        )
                        use_jobs_option = False
                        cmd = ["opengrep", "--config", rule_file, "--json", full_target_path]
                        result = await loop.run_in_executor(
                            None,
                            lambda: _run_subprocess_with_tracking(
                                "opengrep",
                                task_id,
                                cmd,
                                env=scan_env,
                                timeout=timeout_seconds,
                            ),
                        )

                    parsed_findings, parsed_errors = _parse_opengrep_output(result.stdout)
                    fatal_errors = [
                        item for item in parsed_errors if _is_fatal_rule_error(item)
                    ]
                    command_failed_without_output = (
                        result.returncode != 0 and not parsed_findings and not parsed_errors
                    )

                    if command_failed_without_output:
                        stderr_msg = _truncate_for_progress_log(result.stderr or "", 200)
                        reason = (
                            f"命令失败（returncode={result.returncode}"
                            + (f"，stderr={stderr_msg}" if stderr_msg else "")
                            + "）"
                        )
                        return {
                            "success": False,
                            "reason": reason,
                            "findings": [],
                            "errors": [],
                            "fatal_rule_ids": [],
                            "returncode": result.returncode,
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
                            "returncode": result.returncode,
                        }

                    return {
                        "success": True,
                        "reason": "",
                        "findings": parsed_findings,
                        "errors": parsed_errors,
                        "fatal_rule_ids": [],
                        "returncode": result.returncode,
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

            # 检查是否有成功执行的规则
            if successful_rule_count == 0:
                task.status = "failed"
                task.error_count = 1
                _sync_task_scan_duration(task)
                await db.commit()
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

            # 处理累积的扫描结果
            non_fatal_scan_errors = [
                item for item in all_scan_errors if not _is_fatal_rule_error(item)
            ]

            # 记录警告但不影响任务状态
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

            # 保存发现
            error_count = 0
            warning_count = 0
            files_scanned = set()
            lines_scanned = 0
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

                    file_path = finding.get("path", "")
                    if file_path:
                        files_scanned.add(file_path)

                    start_line = finding.get("start", {}).get("line", 0)
                    end_line = finding.get("end", {}).get("line", start_line)
                    lines_scanned += max(0, end_line - start_line + 1)

                    opengrep_finding = OpengrepFinding(
                        scan_task_id=task_id,
                        rule=finding,
                        description=finding.get("extra", {}).get("message"),
                        file_path=file_path,
                        start_line=start_line,
                        code_snippet=finding.get("extra", {}).get("lines"),
                        severity=severity,
                        status="open",
                    )
                    db.add(opengrep_finding)
                except Exception as e:
                    logger.error(f"Error processing finding: {e}")
                    error_count += 1

            # 更新任务统计
            if _is_scan_task_cancelled("opengrep", task_id):
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

            task.status = "completed"
            task.total_findings = len(all_findings)
            task.error_count = error_count
            task.warning_count = warning_count + len(non_fatal_scan_errors)
            task.files_scanned = len(files_scanned)
            task.lines_scanned = lines_scanned
            _sync_task_scan_duration(task)

            await db.commit()
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
            try:
                result = await db.execute(
                    select(OpengrepScanTask).where(OpengrepScanTask.id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.status = "interrupted"
                    task.error_count = (task.error_count or 0) + 1
                    _sync_task_scan_duration(task)
                    await db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to update interrupted task status: {commit_error}")
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
            try:
                result = await db.execute(
                    select(OpengrepScanTask).where(OpengrepScanTask.id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_count = (task.error_count or 0) + 1
                    _sync_task_scan_duration(task)
                    await db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to update task status: {commit_error}")
        finally:
            _clear_scan_task_cancel("opengrep", task_id)
            # 清理解压的临时目录
            if project_root and project_root.startswith("/tmp") and os.path.exists(project_root):
                try:
                    shutil.rmtree(project_root, ignore_errors=True)
                    logger.info(f"Cleaned up temporary project directory: {project_root}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary directory {project_root}: {e}")


logger = logging.getLogger(__name__)
router = APIRouter()
VALID_CONFIDENCE_LEVELS = {"HIGH", "MEDIUM", "LOW"}
SCAN_PROGRESS_MAX_LOGS = 120
_scan_progress_store: Dict[str, Dict[str, Any]] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


def _record_scan_progress(
    task_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    stage: Optional[str] = None,
    message: Optional[str] = None,
    level: str = "info",
) -> None:
    state = _scan_progress_store.get(task_id) or {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "current_stage": "pending",
        "message": "任务已创建，等待执行",
        "started_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "logs": [],
    }

    if status:
        state["status"] = status
    if progress is not None:
        state["progress"] = max(0.0, min(100.0, float(progress)))
    if stage:
        state["current_stage"] = stage
    if message:
        state["message"] = message
        state["logs"].append(
            {
                "timestamp": _utc_now_iso(),
                "stage": stage or state.get("current_stage") or "unknown",
                "message": message,
                "progress": state.get("progress", 0.0),
                "level": level,
            }
        )
        if len(state["logs"]) > SCAN_PROGRESS_MAX_LOGS:
            state["logs"] = state["logs"][-SCAN_PROGRESS_MAX_LOGS:]
    state["updated_at"] = _utc_now_iso()
    _scan_progress_store[task_id] = state


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
) -> Dict[str, Any]:
    resolved_confidence, resolved_cwe, resolved_rule_name = _resolve_finding_enrichment(
        finding,
        rule_confidence_map=rule_confidence_map,
        rule_cwe_map=rule_cwe_map,
        rule_display_name_map=rule_display_name_map,
    )
    return {
        "id": finding.id,
        "scan_task_id": finding.scan_task_id,
        "rule": finding.rule,
        "description": finding.description,
        "file_path": finding.file_path,
        "start_line": finding.start_line,
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

    candidates: List[str] = [raw]

    tmp_index = raw.find("/tmp/")
    if tmp_index >= 0:
        trimmed = raw[tmp_index + 5 :]
        parts = [part for part in trimmed.split("/") if part]
        if len(parts) >= 2:
            candidates.append("/".join(parts[1:]))
        if len(parts) >= 3:
            candidates.append("/".join(parts[2:]))

    if raw.startswith("/"):
        candidates.append(raw.lstrip("/"))

    base_name = os.path.basename(raw)
    if base_name:
        candidates.append(base_name)

    deduplicated: List[str] = []
    seen = set()
    for item in candidates:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        deduplicated.append(normalized)
        seen.add(normalized)
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
    background_tasks: BackgroundTasks,
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
    await db.refresh(scan_task)
    _record_scan_progress(
        scan_task.id,
        status="pending",
        progress=2,
        stage="pending",
        message="任务已创建，等待调度执行",
    )

    # 后台执行扫描
    background_tasks.add_task(
        _execute_opengrep_scan,
        scan_task.id,
        project_root,
        request.target_path,
        normalized_rule_ids,
    )

    return scan_task


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
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="任务不存在")

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
    if not task_result.scalar_one_or_none():
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

    return _serialize_finding_response(
        finding,
        rule_confidence_map=rule_confidence_map,
        rule_cwe_map=rule_cwe_map,
        rule_display_name_map=rule_display_name_map,
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
    """获取某条静态扫描缺陷的命中上下文代码。"""
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


@router.get("/rules", response_model=List[Dict[str, Any]])
async def list_opengrep_rules(
    language: Optional[str] = Query(None, description="按编程语言过滤"),
    source: Optional[str] = Query(None, description="按来源过滤: internal, patch"),
    confidence: Optional[str] = Query(None, description="按置信度过滤: HIGH, MEDIUM, LOW"),
    is_active: Optional[bool] = Query(None, description="只获取活跃规则"),
    db: AsyncSession = Depends(get_db),
):
    """获取 Opengrep 规则列表"""
    query = select(OpengrepRule)

    if language:
        query = query.where(OpengrepRule.language == language)
    if source:
        query = query.where(OpengrepRule.source == source)
    if confidence:
        query = query.where(OpengrepRule.confidence == confidence)
    if is_active is not None:
        query = query.where(OpengrepRule.is_active == is_active)

    result = await db.execute(query)
    rules = result.scalars().all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "language": r.language,
            "severity": r.severity,
            "confidence": r.confidence,
            "description": r.description,
            "cwe": r.cwe,
            "source": r.source,
            "correct": r.correct,
            "is_active": r.is_active,
            "created_at": r.create_at,
        }
        for r in rules
    ]


@router.get("/rules/{rule_id}")
async def get_opengrep_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    """获取 Opengrep 规则详情"""
    result = await db.execute(select(OpengrepRule).where(OpengrepRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    return {
        "id": rule.id,
        "name": rule.name,
        "pattern_yaml": rule.pattern_yaml,
        "language": rule.language,
        "severity": rule.severity,
        "confidence": rule.confidence,
        "description": rule.description,
        "cwe": rule.cwe,
        "source": rule.source,
        "patch": rule.patch,
        "correct": rule.correct,
        "is_active": rule.is_active,
        "created_at": rule.create_at,
    }


@router.get("/rules/generating/status")
async def get_generating_rules(db: AsyncSession = Depends(get_db)):
    """获取所有处于生成中的补丁规则"""
    # 查询所有 source='patch' 且 correct=false 的规则（正在生成中）
    result = await db.execute(
        select(OpengrepRule).where(
            (OpengrepRule.source == "patch") & (OpengrepRule.correct == False)
        )
    )
    rules = result.scalars().all()
    
    return [
        {
            "id": rule.id,
            "name": rule.name,
            "language": rule.language,
            "severity": rule.severity,
            "source": rule.source,
            "patch": rule.patch,
            "correct": rule.correct,
            "is_active": rule.is_active,
            "created_at": rule.create_at,
        }
        for rule in rules
    ]


def _validate_patch_filename(filename: str) -> bool:
    """
    验证 patch 文件名是否符合格式: 仓库owner_仓库名_哈希.patch
    
    Args:
        filename: 文件名
        
    Returns:
        是否符合格式
    """
    # 匹配格式: owner_repo_hash.patch
    # owner 和 repo 可以包含字母、数字、下划线、连字符
    # hash 通常是 40 位的 SHA-1 或 7-10 位的短 hash
    pattern = r'^[\w\-]+_[\w\-]+_[a-f0-9]{7,40}\.patch$'
    return bool(re.match(pattern, filename, re.IGNORECASE))


async def _get_user_config(db: AsyncSession, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """获取用户配置（与 agent_tasks 一致）"""
    if not user_id:
        return None

    try:
        from app.api.v1.endpoints.config import (
            decrypt_config,
            SENSITIVE_LLM_FIELDS, SENSITIVE_OTHER_FIELDS
        )

        result = await db.execute(
            select(UserConfig).where(UserConfig.user_id == user_id)
        )
        config = result.scalar_one_or_none()

        if config and config.llm_config:
            user_llm_config = json.loads(config.llm_config) if config.llm_config else {}
            user_other_config = json.loads(config.other_config) if config.other_config else {}

            user_llm_config = decrypt_config(user_llm_config, SENSITIVE_LLM_FIELDS)
            user_other_config = decrypt_config(user_other_config, SENSITIVE_OTHER_FIELDS)

            return {
                "llmConfig": user_llm_config,
                "otherConfig": user_other_config,
            }
    except Exception as e:
        logger.warning(f"Failed to get user config: {e}")

    return None


def _normalize_llm_config_error_message(exc: Exception) -> str:
    return f"LLM配置错误: {exc}"


def _is_llm_config_error(exc: Exception) -> bool:
    if isinstance(exc, LLMConfigError):
        return True
    msg = str(exc)
    return "LLM配置错误" in msg or "llmModel" in msg or "llmBaseUrl" in msg or "llmApiKey" in msg


def _validate_user_llm_config(user_config: Optional[Dict[str, Any]]) -> None:
    llm_service = LLMService(user_config=user_config or {})
    _ = llm_service.config


async def _process_patch_files_background(
    patch_files: List[tuple],
    user_id: str,
    task_type: str = "archive",
    temp_dir: Optional[str] = None
) -> None:
    """
    后台异步处理 patch 文件生成规则
    
    Args:
        patch_files: 要处理的 patch 文件列表，每个元素为 (filename, file_path, rule_id) 或 (filename, file_content, rule_id)
        user_id: 用户ID
        task_type: 任务类型 ("archive" 或 "directory")
        temp_dir: 临时目录路径，处理完后会被清理
    """
    async with async_session_factory() as db:
        user_config = await _get_user_config(db, user_id)
        if user_config:
            logger.info(f"已为用户 {user_id} 加载 LLM 配置")
        else:
            logger.warning(f"获取用户 {user_id} 的配置失败或为空，将使用默认配置")

        try:
            _validate_user_llm_config(user_config)
        except Exception as exc:
            error_message = _normalize_llm_config_error_message(exc)
            logger.error(error_message)
            for _, _, rule_id in patch_files:
                await _update_rule_status(db, rule_id, False, error_message)
            return
        
        try:
            logger.info(f"开始后台处理 {len(patch_files)} 个 patch 文件 (task_type={task_type})...")
            
            success_count = 0
            failed_count = 0
            
            for item in patch_files:
                filename, content_or_path, rule_id = item
                
                if task_type == "archive":
                    # 从文件读取内容
                    try:
                        with open(content_or_path, 'r', encoding='utf-8') as f:
                            patch_content = f.read()
                    except UnicodeDecodeError:
                        logger.error(f"文件编码错误: {filename}")
                        # 更新规则为失败
                        await _update_rule_status(db, rule_id, False, "文件编码错误")
                        failed_count += 1
                        continue
                else:  # directory
                    patch_content = content_or_path
                
                try:
                    result = await _process_single_patch_file(patch_content, filename, rule_id, db, user_config=user_config)
                    if result["status"] == "success":
                        success_count += 1
                    else:
                        failed_count += 1
                    logger.info(f"处理完成: {filename} - {result['status']}")
                except Exception as e:
                    logger.error(f"处理文件失败 {filename}: {e}")
                    await _update_rule_status(db, rule_id, False, str(e))
                    failed_count += 1
            
            logger.info(
                f"后台处理完成: 成功 {success_count} 个，失败 {failed_count} 个"
            )
            
        except Exception as e:
            logger.error(f"后台处理异常: {e}")
        finally:
            # 清理临时目录
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.info(f"临时目录已清理: {temp_dir}")
                except Exception as e:
                    logger.error(f"清理临时目录失败: {e}")


async def _update_rule_status(
    db: AsyncSession,
    rule_id: str,
    is_correct: bool,
    error_message: Optional[str] = None
) -> None:
    """
    更新规则状态为失败
    
    Args:
        db: 数据库会话
        rule_id: 规则ID
        is_correct: 是否正确
        error_message: 错误信息
    """
    try:
        result = await db.execute(select(OpengrepRule).where(OpengrepRule.id == rule_id))
        rule = result.scalar_one_or_none()
        if rule:
            rule.correct = is_correct
            rule.is_active = is_correct
            if error_message and not is_correct:
                rule.pattern_yaml = yaml.safe_dump(
                    {"rules": [], "error": error_message},
                    sort_keys=False,
                )
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to update rule status for {rule_id}: {e}")
        try:
            await db.rollback()
        except:
            pass


async def _create_placeholder_rule(
    filename: str,
    db: AsyncSession
) -> str:
    """
    为 patch 文件创建占位符规则
    
    Args:
        filename: patch 文件名
        db: 数据库会话
        
    Returns:
        创建的规则ID
    """
    try:
        # 从文件名提取基本信息
        rule_name = f"patch-{filename.replace('.patch', '')}"
        
        # 创建占位符规则
        new_rule = OpengrepRule(
            name=rule_name,
            pattern_yaml="",  # 空的 YAML，等待生成
            language="unknown",
            severity="ERROR",
            confidence="LOW",  # 通过patch生成的规则默认设置为LOW置信度
            description=f"通过 patch 文件生成的规则: {filename}",
            cwe=[],
            source="patch",
            patch=filename,
            correct=False,  # 未生成，标记为不正确
            is_active=False,  # 未生成，标记为不激活
        )
        
        db.add(new_rule)
        await db.commit()
        await db.refresh(new_rule)

        await _cleanup_incorrect_rules(db)
        
        logger.info(f"创建占位符规则: {new_rule.id} for {filename}")
        return new_rule.id
        
    except Exception as e:
        logger.error(f"创建占位符规则失败: {filename}, 错误: {e}")
        try:
            await db.rollback()
        except:
            pass
        raise


async def _process_single_patch_file(
    patch_content: str,
    filename: str,
    rule_id: str,
    db: AsyncSession,
    user_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    处理单个 patch 文件生成规则
    更新数据库中已创建的规则记录
    
    Args:
        patch_content: patch 文件内容
        filename: 文件名
        rule_id: 规则ID
        db: 数据库会话
        user_config: 用户配置，用于LLM模型选择
        
    Returns:
        处理结果字典
    """
    try:
        # 从文件名中提取信息 (格式: owner_repo_hash.patch)
        name_without_ext = filename.rsplit('.', 1)[0]
        parts = name_without_ext.rsplit('_', 2)  # 从右向左分割，最多分成3部分
        
        if len(parts) >= 3:
            repo_owner = parts[0]
            repo_name = parts[1]
            commit_hash = parts[2]
        elif len(parts) == 2:
            repo_owner = parts[0]
            repo_name = parts[1]
            commit_hash = ""
        else:
            repo_owner = "unknown"
            repo_name = name_without_ext
            commit_hash = ""
        
        # 构建请求
        request = OpengrepRuleCreateRequest(
            repo_owner=repo_owner,
            repo_name=repo_name,
            commit_hash=commit_hash,
            commit_content=patch_content
        )
        
        # 调用规则生成服务，传入用户配置
        result = await get_rule_by_patch(request, user_config=user_config)
        
        attempts = result.get("attempts", [])
        meta = result.get("meta", {})
        validation = result.get("validation", {})
        is_valid = bool(validation.get("is_valid"))
        rule = result.get("rule")
        
        # 获取现有规则记录进行更新
        db_result = await db.execute(select(OpengrepRule).where(OpengrepRule.id == rule_id))
        opengrep_rule = db_result.scalar_one_or_none()
        
        if not opengrep_rule:
            logger.error(f"Rule {rule_id} not found in database")
            return {
                "filename": filename,
                "rule_id": rule_id,
                "status": "error",
                "attempts": len(attempts),
                "message": "规则记录不存在"
            }
        
        # 更新规则记录
        if rule:
            name = rule.get("id") or f"patch-{name_without_ext}"
            languages = rule.get("languages") or []
            language = languages[0] if isinstance(languages, list) and languages else None
            language = language or meta.get("language") or "unknown"
            severity = rule.get("severity") or "ERROR"
            # 如果规则中有置信度，则使用它；或从metadata中获取；否则设为"LOW"
            confidence = rule.get("confidence") or meta.get("confidence") or "LOW"
            pattern_yaml = yaml.safe_dump({"rules": [rule]}, sort_keys=False)
        else:
            name = f"patch-{name_without_ext}"
            language = meta.get("language") or "unknown"
            severity = "ERROR"
            # 生成失败的规则：从metadata中获取置信度，否则设为"LOW"
            confidence = meta.get("confidence") or "LOW"
            pattern_yaml = yaml.safe_dump(
                {"rules": [], "error": validation.get("message") or "LLM rule generation failed"},
                sort_keys=False,
            )
        
        # 更新规则信息
        opengrep_rule.name = name
        opengrep_rule.pattern_yaml = pattern_yaml
        opengrep_rule.language = language
        opengrep_rule.severity = severity
        opengrep_rule.confidence = confidence  # 使用从规则或metadata中提取或默认的置信度
        opengrep_rule.patch = patch_content
        opengrep_rule.correct = is_valid
        opengrep_rule.is_active = is_valid
        
        await db.commit()
        
        return {
            "filename": filename,
            "rule_id": rule_id,
            "status": "success" if is_valid else "failed",
            "attempts": len(attempts),
            "message": "规则生成成功" if is_valid else "规则生成失败"
        }
        
    except Exception as e:
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.debug(f"无法回滚事务: {rollback_error}")
        logger.error(f"Error processing patch file {filename}: {e}")
        message = _normalize_llm_config_error_message(e) if _is_llm_config_error(e) else str(e)
        return {
            "filename": filename,
            "rule_id": rule_id,
            "status": "error",
            "attempts": 0,
            "message": message
        }


@router.post("/rules/create", response_model=OpengrepRulePatchResponse)
async def create_opengrep_rule(
    request: OpengrepRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    创建一个新的 Opengrep 规则（从 Patch 生成）

    使用大模型基于 patch 内容生成检测规则，并保存所有尝试到数据库
    """
    user_config = await _get_user_config(db, current_user.id)
    if user_config:
        llm_config = user_config.get("llmConfig", {})
        logger.info(
            f"✅ 从数据库获取用户 {current_user.id} 的 LLM 配置: "
            f"provider={llm_config.get('llmProvider')}, model={llm_config.get('llmModel')}"
        )
    else:
        logger.info(f"⚠️ 未找到用户 {current_user.id} 的 LLM 配置，将使用默认配置")
    try:
        _validate_user_llm_config(user_config)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_normalize_llm_config_error_message(exc)) from exc

    result = await get_rule_by_patch(request, user_config=user_config)

    attempts = result.get("attempts", [])
    meta = result.get("meta", {})

    try:
        for attempt in attempts:
            rule = attempt.get("rule")
            validation = attempt.get("validation") or {}
            is_valid = bool(validation.get("is_valid"))
            message = validation.get("message")

            if rule:
                name = rule.get("id") or f"llm-attempt-{attempt.get('attempt', 0)}"
                languages = rule.get("languages") or []
                language = languages[0] if isinstance(languages, list) and languages else None
                language = language or meta.get("language") or "unknown"
                severity = rule.get("severity") or "ERROR"
                pattern_yaml = yaml.safe_dump({"rules": [rule]}, sort_keys=False)
            else:
                name = f"llm-attempt-{attempt.get('attempt', 0)}"
                language = meta.get("language") or "unknown"
                severity = "ERROR"
                pattern_yaml = yaml.safe_dump(
                    {"rules": [], "error": message or "LLM rule generation failed"},
                    sort_keys=False,
                )

            opengrep_rule = OpengrepRule(
                name=name,
                pattern_yaml=pattern_yaml,
                language=language,
                severity=severity,
                source="patch",
                patch=request.commit_content,
                correct=is_valid,
                is_active=is_valid,
            )
            db.add(opengrep_rule)

        await db.commit()
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Failed to persist opengrep rule attempts: {e}")

    return result


@router.post("/rules/create-generic", response_model=OpengrepRuleTextResponse)
async def create_opengrep_generic_rule(
    request: OpengrepRuleTextCreateRequest, db: AsyncSession = Depends(get_db)
):
    """
    创建通用型 Opengrep 规则

    - 校验 YAML 格式与规则结构
    """
    result = await validate_generic_rule(request.rule_yaml)
    validation = result.get("validation") or {}
    if not validation.get("is_valid"):
        raise HTTPException(status_code=400, detail=validation.get("message") or "规则验证失败")

    rule = result.get("rule") or {}
    rule_yaml = result.get("rule_yaml") or request.rule_yaml

    name = rule.get("id") or "custom-rule"
    languages = rule.get("languages") or []
    language = languages[0] if isinstance(languages, list) and languages else "unknown"
    severity = rule.get("severity") or "ERROR"

    opengrep_rule = OpengrepRule(
        name=name,
        pattern_yaml=rule_yaml,
        language=language,
        severity=severity,
        source="internal",
        patch=None,
        correct=True,
        is_active=True,
    )

    try:
        db.add(opengrep_rule)
        await db.commit()
    except SQLAlchemyError as e:
        await db.rollback()
        logger.error(f"Failed to persist generic rule: {e}")
        raise HTTPException(status_code=500, detail="规则保存失败")

    return {
        "rule": rule,
        "validation": validation,
        "test_yaml": result.get("test_yaml"),
        "rule_id": opengrep_rule.id,
    }


@router.patch("/rules/{rule_id}")
async def edit_opengrep_rule(
    rule_id: str,
    request: OpengrepRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """编辑 Opengrep 规则并保存。"""
    result = await db.execute(select(OpengrepRule).where(OpengrepRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    if (
        request.name is None
        and request.pattern_yaml is None
        and request.language is None
        and request.severity is None
        and request.is_active is None
    ):
        raise HTTPException(status_code=400, detail="至少需要提供一个可更新字段")

    if request.name is not None:
        rule_name = request.name.strip()
        if not rule_name:
            raise HTTPException(status_code=400, detail="规则名称不能为空")
        rule.name = rule_name

    if request.pattern_yaml is not None:
        validation_result = await validate_generic_rule(request.pattern_yaml)
        validation = validation_result.get("validation") or {}
        if not validation.get("is_valid"):
            raise HTTPException(
                status_code=400,
                detail=validation.get("message") or "规则验证失败",
            )

        parsed_rule = validation_result.get("rule") or {}
        cleaned_yaml = validation_result.get("rule_yaml") or request.pattern_yaml
        rule.pattern_yaml = cleaned_yaml
        rule.correct = True

        if request.name is None:
            parsed_rule_id = str(parsed_rule.get("id") or "").strip()
            if parsed_rule_id:
                rule.name = parsed_rule_id

        if request.language is None:
            parsed_languages = parsed_rule.get("languages") or []
            if isinstance(parsed_languages, list) and parsed_languages:
                parsed_language = str(parsed_languages[0]).strip()
                if parsed_language:
                    rule.language = parsed_language

        if request.severity is None:
            parsed_severity = str(parsed_rule.get("severity") or "").strip().upper()
            if parsed_severity in {"ERROR", "WARNING", "INFO"}:
                rule.severity = parsed_severity

    if request.language is not None:
        language = request.language.strip()
        if not language:
            raise HTTPException(status_code=400, detail="编程语言不能为空")
        rule.language = language

    if request.severity is not None:
        severity = request.severity.strip().upper()
        if severity not in {"ERROR", "WARNING", "INFO"}:
            raise HTTPException(status_code=400, detail="严重程度必须为 ERROR/WARNING/INFO")
        rule.severity = severity

    if request.is_active is not None:
        rule.is_active = request.is_active

    await db.commit()
    await db.refresh(rule)

    return {
        "message": "规则保存成功",
        "rule": {
            "id": rule.id,
            "name": rule.name,
            "pattern_yaml": rule.pattern_yaml,
            "language": rule.language,
            "severity": rule.severity,
            "source": rule.source,
            "patch": rule.patch,
            "correct": rule.correct,
            "is_active": rule.is_active,
            "created_at": rule.create_at,
        },
    }


@router.put("/rules/{rule_id}")
async def update_opengrep_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    启用或禁用一个已有的 Opengrep 规则
    """
    result = await db.execute(select(OpengrepRule).where(OpengrepRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.is_active = not rule.is_active
    await db.commit()
    return {"message": "规则已更新", "rule_id": rule_id, "is_active": rule.is_active}


@router.delete("/rules/{rule_id}")
async def delete_opengrep_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    删除一个 Opengrep 规则
    """
    result = await db.execute(select(OpengrepRule).where(OpengrepRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")

    await db.delete(rule)
    await db.commit()

    return {"message": "规则已删除", "rule_id": rule_id}


@router.post("/rules/select")
async def select_opengrep_rules(
    request: OpengrepRuleBatchUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    批量启用或禁用 Opengrep 规则

    支持通过规则ID列表、关键词、编程语言、规则来源、严重程度、置信度、当前启用状态等条件进行过滤。
    若未提供任何过滤条件，将对全部规则执行批量更新。
    """
    query = select(OpengrepRule)

    if request.rule_ids:
        query = query.where(OpengrepRule.id.in_(request.rule_ids))

    if request.keyword and request.keyword.strip():
        keyword = request.keyword.strip().lower()
        pattern = f"%{keyword}%"
        query = query.where(
            or_(
                func.lower(OpengrepRule.name).like(pattern),
                func.lower(OpengrepRule.id).like(pattern),
            )
        )

    if request.language:
        query = query.where(OpengrepRule.language == request.language)

    if request.source:
        query = query.where(OpengrepRule.source == request.source)

    if request.severity:
        query = query.where(OpengrepRule.severity == request.severity)

    if request.confidence:
        query = query.where(OpengrepRule.confidence == request.confidence)

    if request.current_is_active is not None:
        query = query.where(OpengrepRule.is_active == request.current_is_active)

    # 查询符合条件的规则
    result = await db.execute(query)
    rules = result.scalars().all()

    if not rules:
        return {
            "message": "没有找到符合条件的规则",
            "updated_count": 0,
            "is_active": request.is_active,
        }

    # 批量更新规则状态
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



@router.post("/rules/upload/json", response_model=OpengrepRuleSingleUploadResponse)
async def upload_opengrep_rule_json(
    request: OpengrepRuleSingleUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    通过 JSON 上传单条规则

    工作流程：
    1. 验证 YAML 格式
    2. 检查规则必需字段
    3. 验证严重程度
    4. 计算 MD5 去重
    5. 保存到数据库
    6. 返回规则信息

    请求体示例：
    ```json
    {
      "name": "my-security-rule",
      "pattern_yaml": "rules:\\n  - id: my-rule\\n    ...",
      "language": "python",
      "severity": "ERROR",
      "source": "json",
      "patch": "https://example.com/patch",
      "correct": true,
      "is_active": true
    }
    ```
    """
    try:
        # 验证严重程度
        severity = request.severity.upper()
        if severity not in ["ERROR", "WARNING", "INFO"]:
            raise HTTPException(
                status_code=400,
                detail=f"严重程度不合法: {request.severity}，必须为 ERROR, WARNING, INFO 之一",
            )

        # 验证 YAML 格式
        try:
            yaml_data = yaml.safe_load(request.pattern_yaml)
            if not yaml_data:
                raise HTTPException(
                    status_code=400,
                    detail="YAML 内容为空或无效",
                )
        except yaml.YAMLError as e:
            raise HTTPException(
                status_code=400,
                detail=f"YAML 格式错误: {str(e)}",
            )

        # 检查规则必需字段
        if "rules" not in yaml_data:
            raise HTTPException(
                status_code=400,
                detail="YAML 中缺少 rules 字段",
            )

        rules = yaml_data.get("rules", [])
        if not isinstance(rules, list) or len(rules) == 0:
            raise HTTPException(
                status_code=400,
                detail="rules 字段必须是非空数组",
            )

        # 验证规则必需字段
        rule = rules[0]
        if not isinstance(rule, dict):
            raise HTTPException(
                status_code=400,
                detail="rules 数组中的规则必须是对象",
            )

        rule_id = rule.get("id")
        if not rule_id:
            raise HTTPException(
                status_code=400,
                detail="规则中缺少 id 字段",
            )

        # 使用 opengrep 验证规则
        is_valid, error_msg = await _validate_opengrep_rule(request.pattern_yaml)
        if not is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"规则验证失败: {error_msg}",
            )

        # MD5 去重检查
        md5_hash = hashlib.md5(request.pattern_yaml.encode("utf-8")).hexdigest()
        result = await db.execute(
            select(OpengrepRule).where(
                OpengrepRule.pattern_yaml == request.pattern_yaml
            )
        )
        existing_rule = result.scalar_one_or_none()
        if existing_rule:
            raise HTTPException(
                status_code=400,
                detail=f"规则已存在（重复），现有规则 ID: {existing_rule.id}",
            )

        # 确保规则名唯一
        unique_name = await _get_unique_rule_name(db, request.name)

        # 创建规则对象
        new_rule = OpengrepRule(
            name=unique_name,
            pattern_yaml=request.pattern_yaml,
            language=request.language,
            severity=severity,
            confidence=request.confidence,
            description=request.description,
            cwe=request.cwe,
            source=request.source,
            patch=request.patch,
            correct=request.correct,
            is_active=request.is_active,
        )

        db.add(new_rule)
        await db.commit()
        await db.refresh(new_rule)

        await _cleanup_incorrect_rules(db)

        return {
            "rule_id": new_rule.id,
            "name": new_rule.name,
            "language": new_rule.language,
            "severity": new_rule.severity,
            "confidence": new_rule.confidence,
            "description": new_rule.description,
            "cwe": new_rule.cwe,
            "source": new_rule.source,
            "is_active": new_rule.is_active,
            "created_at": new_rule.create_at,
            "message": "规则上传成功",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading opengrep rule: {e}")
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")




async def _create_rules_and_generate_background(
    patch_files: List[tuple],
    user_id: str,
    task_type: str = "archive",
    temp_dir: Optional[str] = None
) -> None:
    """
    后台异步创建占位符规则并生成规则
    
    维护项目和git克隆的对应关系，在整个任务完成后统一清理临时文件，
    并清理本次任务使用的git缓存。
    
    Args:
        patch_files: 要处理的 patch 文件列表，每个元素为 (filename, file_path) 或 (filename, file_content)
        user_id: 用户ID
        task_type: 任务类型 ("archive" 或 "directory")
        temp_dir: 临时目录路径，处理完后会被清理
    """
    async with async_session_factory() as db:
        # 任务级缓存：维护本次处理中使用过的项目，防止重复克隆
        task_repo_cache: Dict[str, Path] = {}
        
        user_config = await _get_user_config(db, user_id)
        if user_config:
            llm_config = user_config.get("llmConfig", {})
            logger.info(
                f"✅ 从数据库获取用户 {user_id} 的 LLM 配置: "
                f"provider={llm_config.get('llmProvider')}, model={llm_config.get('llmModel')}"
            )
        else:
            logger.info(f"⚠️ 未找到用户 {user_id} 的 LLM 配置，将使用默认配置")

        llm_config_error_message: Optional[str] = None
        try:
            _validate_user_llm_config(user_config)
        except Exception as exc:
            llm_config_error_message = _normalize_llm_config_error_message(exc)
            logger.error(llm_config_error_message)
        
        try:
            logger.info(f"开始后台创建占位符规则和处理 {len(patch_files)} 个 patch 文件 (task_type={task_type})...")
            
            # 第一步：创建占位符规则
            rule_ids = []
            file_rule_map = {}  # 保存文件名和rule_id的映射
            
            for filename, content_or_path in patch_files:
                try:
                    rule_id = await _create_placeholder_rule(filename=filename, db=db)
                    rule_ids.append(rule_id)
                    file_rule_map[filename] = rule_id
                    logger.info(f"创建占位符规则: {rule_id} for {filename}")
                except Exception as e:
                    logger.error(f"创建占位符规则失败: {filename}, 错误: {e}")
                    # 继续处理其他文件
            
            if not rule_ids:
                logger.error("未能为任何 patch 文件创建规则")
                return
            
            logger.info(f"创建 {len(rule_ids)} 个占位符规则，开始处理生成...")

            if llm_config_error_message:
                for rule_id in rule_ids:
                    await _update_rule_status(db, rule_id, False, llm_config_error_message)
                logger.error("后台规则生成已终止：%s", llm_config_error_message)
                return
            
            # 第二步：处理 patch 文件生成规则
            success_count = 0
            failed_count = 0
            processed_repos = set()  # 追踪已处理过的项目（格式: "owner/name"）
            
            for filename, content_or_path in patch_files:
                if filename not in file_rule_map:
                    continue
                
                rule_id = file_rule_map[filename]
                
                if task_type == "archive":
                    # 从文件读取内容
                    try:
                        with open(content_or_path, 'r', encoding='utf-8') as f:
                            patch_content = f.read()
                    except UnicodeDecodeError:
                        logger.error(f"文件编码错误: {filename}")
                        await _update_rule_status(db, rule_id, False, "文件编码错误")
                        failed_count += 1
                        continue
                else:  # directory
                    patch_content = content_or_path
                
                try:
                    result = await _process_single_patch_file(patch_content, filename, rule_id, db, user_config=user_config)
                    
                    # 从patch处理结果中提取repo信息用于缓存追踪
                    try:
                        # 从文件名提取项目信息
                        name_without_ext = filename.rsplit('.', 1)[0]
                        parts = name_without_ext.rsplit('_', 2)
                        if len(parts) >= 2:
                            repo_owner = parts[0]
                            repo_name = parts[1]
                            repo_key = f"{repo_owner}/{repo_name}"
                            processed_repos.add(repo_key)
                            
                            # 验证项目是否在全局缓存中
                            cached = GlobalRepoCacheManager.get_repo_cache(repo_owner, repo_name)
                            if cached:
                                task_repo_cache[repo_key] = cached
                                logger.info(f"任务缓存已记录项目: {repo_key}")
                    except Exception as e:
                        logger.debug(f"无法从patch提取项目信息: {e}")
                    
                    if result["status"] == "success":
                        success_count += 1
                    else:
                        failed_count += 1
                    logger.info(f"处理完成: {filename} - {result['status']}")
                except Exception as e:
                    logger.error(f"处理文件失败 {filename}: {e}")
                    if _is_llm_config_error(e):
                        await _update_rule_status(db, rule_id, False, _normalize_llm_config_error_message(e))
                    else:
                        await _update_rule_status(db, rule_id, False, str(e))
                    failed_count += 1
            
            logger.info(
                f"后台处理完成: 成功 {success_count} 个，失败 {failed_count} 个，"
                f"缓存项目 {len(processed_repos)} 个"
            )
            
            # 记录缓存统计
            if task_repo_cache:
                total_size = 0
                for repo_key, cache_path in task_repo_cache.items():
                    if cache_path.exists():
                        repo_size = sum(
                            f.stat().st_size 
                            for f in cache_path.rglob('*') 
                            if f.is_file()
                        )
                        total_size += repo_size
                        logger.info(
                            f"  项目缓存: {repo_key} "
                            f"({cache_path}, "
                            f"{round(repo_size / 1024 / 1024, 2)} MB)"
                        )
                logger.info(
                    f"任务缓存总大小: {round(total_size / 1024 / 1024, 2)} MB "
                    f"(任务结束后将清理)"
                )
            
        except Exception as e:
            logger.error(f"后台创建和处理异常: {e}")
        finally:
            # 清理临时目录
            if temp_dir and os.path.exists(temp_dir):
                try:
                    # 只清理临时目录中的patch和生成的规则，不清理git缓存
                    temp_path = Path(temp_dir)
                    
                    # 清理patches目录
                    patches_dir = temp_path / "patches"
                    if patches_dir.exists():
                        shutil.rmtree(patches_dir, ignore_errors=True)
                        logger.info(f"已清理临时patches目录: {patches_dir}")
                    
                    # 清理generated_rules目录
                    generated_dir = temp_path / "generated_rules"
                    if generated_dir.exists():
                        shutil.rmtree(generated_dir, ignore_errors=True)
                        logger.info(f"已清理临时generated_rules目录: {generated_dir}")
                    
                    # 清理rules目录
                    rules_dir = temp_path / "rules"
                    if rules_dir.exists():
                        shutil.rmtree(rules_dir, ignore_errors=True)
                        logger.info(f"已清理临时rules目录: {rules_dir}")
                    
                    # 最后清理整个临时目录（应该已基本为空）
                    if temp_path.exists():
                        shutil.rmtree(temp_path, ignore_errors=True)
                        logger.info(f"临时目录已清理: {temp_dir}")
                except Exception as e:
                    logger.error(f"清理临时目录失败: {e}")
                    # 非致命错误，继续执行

            # 任务完成后清理本次任务使用的 git 缓存
            if task_repo_cache:
                for repo_key in list(task_repo_cache.keys()):
                    try:
                        repo_owner, repo_name = repo_key.split("/", 1)
                    except ValueError:
                        logger.warning(f"无法解析缓存项目键: {repo_key}")
                        continue
                    removed = GlobalRepoCacheManager.remove_repo_cache(repo_owner, repo_name)
                    if removed:
                        logger.info(f"已清理任务缓存: {repo_key}")
                    else:
                        logger.warning(f"清理任务缓存失败: {repo_key}")


@router.post("/rules/upload/patch-archive", response_model=dict)
async def upload_patch_archive(
    file: UploadFile = File(..., description="包含多个 .patch 文件的压缩包"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> dict:
    """
    上传包含多个 Patch 文件的压缩包生成规则
    
    支持的压缩格式: .zip
    压缩包内的 .patch 文件名必须符合格式: 仓库owner_仓库名_哈希.patch
    
    工作流程:
    1. 快速验证和解压 patch 文件
    2. 返回确认消息
    3. 后台异步创建占位符规则和生成规则
    
    前端应该轮询 GET /rules/generating/status 查询所有正在生成的规则
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    
    # 验证文件扩展名
    if not file.filename.endswith('.zip'):
        raise HTTPException(
            status_code=400,
            detail=f"仅支持 .zip 压缩格式，当前文件: {file.filename}"
        )
    
    temp_dir = None
    try:
        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix="patch_upload_")
        zip_path = os.path.join(temp_dir, file.filename)
        
        # 保存上传的文件
        content = await file.read()
        with open(zip_path, 'wb') as f:
            f.write(content)
        
        # 解压文件
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="压缩包格式错误或已损坏")
        
        # 查找所有 .patch 文件
        patch_files = []
        for root, dirs, files in os.walk(temp_dir):
            for filename in files:
                if filename.endswith('.patch'):
                    file_path = os.path.join(root, filename)
                    patch_files.append((filename, file_path))
        
        if not patch_files:
            raise HTTPException(
                status_code=400,
                detail="压缩包中没有找到 .patch 文件"
            )
        
        total_files = len(patch_files)
        logger.info(f"压缩包上传验证成功，找到 {total_files} 个 patch 文件，启动后台处理...")
        
        # 快速返回，所有处理在后台进行
        asyncio.create_task(
            _create_rules_and_generate_background(
                patch_files,
                current_user.id,
                task_type="archive",
                temp_dir=temp_dir
            )
        )

        await _cleanup_incorrect_rules(db)
        
        return {
            "message": f"已接收 {total_files} 个 patch 文件，正在后台处理...",
            "total_files": total_files,
            "status": "processing"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing patch archive: {e}")
        # 清理临时目录
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except:
                pass
        raise HTTPException(status_code=500, detail=f"处理压缩包失败: {str(e)}")


@router.post("/rules/upload/patch-directory", response_model=dict)
async def upload_patch_directory(
    files: List[UploadFile] = File(..., description="目录中的多个 .patch 文件"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> dict:
    """
    上传目录中的多个 Patch 文件生成规则
    
    支持前端目录上传功能（浏览器会将目录中的所有文件作为多个文件上传）
    文件名必须符合格式: 仓库owner_仓库名_哈希.patch
    
    工作流程:
    1. 快速验证 patch 文件
    2. 返回确认消息
    3. 后台异步创建占位符规则和生成规则
    
    前端应该轮询 GET /rules/generating/status 查询所有正在生成的规则
    """
    if not files:
        raise HTTPException(status_code=400, detail="没有上传任何文件")
    
    # 过滤出 .patch 文件
    patch_files = []
    for file in files:
        if file.filename and file.filename.endswith('.patch'):
            patch_files.append(file)
    
    if not patch_files:
        raise HTTPException(
            status_code=400,
            detail=f"上传的 {len(files)} 个文件中没有找到 .patch 文件"
        )
    
    # 将文件内容读入内存后再启动异步任务
    patch_files_data = []
    try:
        for file in patch_files:
            content = await file.read()
            patch_content = content.decode('utf-8')
            patch_files_data.append((file.filename, patch_content))
    except UnicodeDecodeError as e:
        raise HTTPException(status_code=400, detail=f"文件编码错误: {str(e)}")
    
    total_files = len(patch_files_data)
    logger.info(f"目录上传验证成功，找到 {total_files} 个 patch 文件，启动后台处理...")
    
    # 快速返回，所有处理在后台进行
    asyncio.create_task(
        _create_rules_and_generate_background(
            patch_files_data,
            current_user.id,
            task_type="directory"
        )
    )

    await _cleanup_incorrect_rules(db)
    
    return {
        "message": f"已接收 {total_files} 个 patch 文件，正在后台处理...",
        "total_files": total_files,
        "status": "processing"
    }


@router.post("/rules/upload")
async def upload_opengrep_rules(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    上传 Opengrep 规则文件（支持多种压缩格式）

    支持的格式: .zip, .tar, .tar.gz, .tar.bz2, .7z, .rar 等

    工作流程：
    1. 验证文件格式是否支持
    2. 保存上传的压缩文件到临时位置
    3. 验证文件完整性
    4. 解压到临时目录
    5. 递归查找所有 YAML 文件
    6. 解析规则并验证
    7. MD5 去重检查
    8. 批量入库
    9. 返回统计信息
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    # 检查文件格式是否支持
    from app.services.upload.compression_factory import CompressionStrategyFactory

    supported_formats = CompressionStrategyFactory.get_supported_formats()
    file_ext = Path(file.filename).suffix.lower()

    # 特殊处理 .tar.gz 等复合扩展名
    file_name_lower = file.filename.lower()
    is_tar_gz = file_name_lower.endswith((".tar.gz", ".tgz", ".tar.gzip"))
    is_tar_bz2 = file_name_lower.endswith((".tar.bz2", ".tbz", ".tbz2"))

    if is_tar_gz:
        file_ext = ".tar.gz"
    elif is_tar_bz2:
        file_ext = ".tar.bz2"

    if file_ext not in supported_formats:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(sorted(supported_formats))}",
        )

    # 使用 tempfile 创建临时目录
    with tempfile.TemporaryDirectory(prefix="deepaudit_rules_", suffix="_upload") as temp_dir:
        try:
            # 保存上传的原始文件到临时位置
            temp_upload_path = os.path.join(temp_dir, file.filename)
            with open(temp_upload_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # 验证上传文件
            is_valid, error = UploadManager.validate_file(temp_upload_path)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"文件验证失败: {error}")

            # 解压到临时目录
            temp_extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(temp_extract_dir, exist_ok=True)

            success, extracted_files, error = await UploadManager.extract_file(
                temp_upload_path, temp_extract_dir
            )

            if not success:
                raise HTTPException(status_code=400, detail=f"解压失败: {error}")

            # 递归查找所有 YAML 文件
            yaml_files = []
            for root, dirs, files in os.walk(temp_extract_dir):
                for f in files:
                    if f.endswith((".yml", ".yaml")):
                        yaml_files.append(os.path.join(root, f))

            if not yaml_files:
                raise HTTPException(status_code=400, detail="压缩包中未找到 YAML 规则文件")

            # 解析规则并进行 MD5 去重
            total_count = len(yaml_files)
            success_count = 0
            failed_count = 0
            duplicate_count = 0
            failed_details = []

            # 获取数据库中已存在的所有规则的 MD5 值
            result = await db.execute(select(OpengrepRule.pattern_yaml))
            existing_patterns = result.scalars().all()
            existing_md5s = {hashlib.md5(p.encode("utf-8")).hexdigest() for p in existing_patterns}

            rules_to_add = []

            for yaml_file in yaml_files:
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        content = f.read()

                    # 计算 MD5
                    md5_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

                    # 检查是否重复
                    if md5_hash in existing_md5s:
                        duplicate_count += 1
                        continue

                    # 解析 YAML
                    yaml_data = yaml.safe_load(content)
                    if not yaml_data or "rules" not in yaml_data:
                        failed_count += 1
                        failed_details.append(
                            {"file": os.path.basename(yaml_file), "error": "YAML 格式错误：缺少 rules 字段"}
                        )
                        continue

                    rules = yaml_data["rules"]
                    if not isinstance(rules, list) or len(rules) == 0:
                        failed_count += 1
                        failed_details.append(
                            {"file": os.path.basename(yaml_file), "error": "rules 字段必须是非空数组"}
                        )
                        continue

                    # 使用 opengrep 验证规则
                    is_valid, error_msg = await _validate_opengrep_rule(content)
                    if not is_valid:
                        failed_count += 1
                        failed_details.append(
                            {"file": os.path.basename(yaml_file), "error": f"规则验证失败: {error_msg}"}
                        )
                        continue

                    # 获取规则信息
                    rule = rules[0]  # 通常一个文件包含一个规则
                    rule_id = rule.get("id", os.path.splitext(os.path.basename(yaml_file))[0])
                    languages = rule.get("languages", [])
                    language = languages[0] if languages else "unknown"
                    severity = rule.get("severity", "WARNING").upper()
                    confidence = rule.get("confidence", "MEDIUM").upper()
                    description = rule.get("message", "")
                    metadata = rule.get("metadata", {})
                    cwe = metadata.get("cwe", [])
                    if isinstance(cwe, str):
                        cwe = [cwe]
                    source = metadata.get("source", "upload")

                    # 验证严重程度
                    if severity not in ["ERROR", "WARNING", "INFO"]:
                        severity = "WARNING"

                    # 确保规则名唯一
                    unique_rule_name = await _get_unique_rule_name(db, rule_id)

                    # 创建规则对象
                    new_rule = OpengrepRule(
                        name=unique_rule_name,
                        pattern_yaml=content,
                        language=language,
                        severity=severity,
                        confidence=confidence,
                        description=description,
                        cwe=cwe,
                        source="upload",
                        patch=metadata.get("source-url", ""),
                        correct=True,
                        is_active=True,
                    )

                    rules_to_add.append(new_rule)
                    existing_md5s.add(md5_hash)  # 添加到已存在集合中，避免当前批次内重复
                    success_count += 1

                except yaml.YAMLError as e:
                    failed_count += 1
                    failed_details.append({"file": os.path.basename(yaml_file), "error": f"YAML 解析错误: {str(e)}"})
                except Exception as e:
                    failed_count += 1
                    failed_details.append({"file": os.path.basename(yaml_file), "error": f"处理失败: {str(e)}"})

            # 批量插入数据库
            if rules_to_add:
                db.add_all(rules_to_add)
                await db.commit()

            await _cleanup_incorrect_rules(db)

            return {
                "message": "规则上传处理完成",
                "total_count": total_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "duplicate_count": duplicate_count,
                "failed_details": failed_details[:20],  # 只返回前 20 条失败详情
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.post("/rules/upload/directory")
async def upload_opengrep_rules_directory(
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    上传文件夹（实际为多个文件）

    工作流程：
    1. 验证权限
    2. 使用 tempfile 创建临时目录
    3. 将所有文件保存到临时目录（保持目录结构）
    4. 递归查找所有 YAML 文件
    5. 解析规则并验证
    6. MD5 去重检查
    7. 批量入库
    8. 返回统计信息

    参数：
    - files: 多个文件，前端应该保持相对路径信息（通过 webkitRelativePath）
    """
    if not files:
        raise HTTPException(status_code=400, detail="至少需要上传一个文件")

    # 使用 tempfile 创建临时目录（自动清理）
    with tempfile.TemporaryDirectory(prefix="deepaudit_rules_", suffix="_directory") as temp_base_dir:
        try:
            total_uploaded_files = 0
            yaml_files_paths = []

            # 逐个保存文件，保持目录结构
            for file in files:
                if not file.filename:
                    continue

                # 检查文件大小
                file_content = await file.read()
                file_size = len(file_content)

                if file_size == 0:
                    continue  # 跳过空文件

                total_uploaded_files += 1

                # 获取文件的相对路径（保持目录结构）
                file_path = file.filename

                # 移除开头的 "/"（如果存在）
                if file_path.startswith("/"):
                    file_path = file_path[1:]

                # 完整的目标路径
                target_path = os.path.join(temp_base_dir, file_path)

                # 创建必要的目录
                target_dir = os.path.dirname(target_path)
                os.makedirs(target_dir, exist_ok=True)

                # 保存文件
                with open(target_path, "wb") as f:
                    f.write(file_content)

                # 如果是 YAML 文件，添加到处理列表
                if file_path.endswith((".yml", ".yaml")):
                    yaml_files_paths.append(target_path)

            if total_uploaded_files == 0:
                raise HTTPException(status_code=400, detail="没有有效的文件")

            if not yaml_files_paths:
                raise HTTPException(status_code=400, detail="未找到 YAML 规则文件")

            # 解析规则并进行 MD5 去重
            total_count = len(yaml_files_paths)
            success_count = 0
            failed_count = 0
            duplicate_count = 0
            failed_details = []

            # 获取数据库中已存在的所有规则的 MD5 值
            result = await db.execute(select(OpengrepRule.pattern_yaml))
            existing_patterns = result.scalars().all()
            existing_md5s = {hashlib.md5(p.encode("utf-8")).hexdigest() for p in existing_patterns}

            rules_to_add = []

            for yaml_file in yaml_files_paths:
                try:
                    with open(yaml_file, "r", encoding="utf-8") as f:
                        content = f.read()

                    # 计算 MD5
                    md5_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

                    # 检查是否重复
                    if md5_hash in existing_md5s:
                        duplicate_count += 1
                        continue

                    # 解析 YAML
                    yaml_data = yaml.safe_load(content)
                    if not yaml_data or "rules" not in yaml_data:
                        failed_count += 1
                        failed_details.append(
                            {"file": os.path.basename(yaml_file), "error": "YAML 格式错误：缺少 rules 字段"}
                        )
                        continue

                    rules = yaml_data["rules"]
                    if not isinstance(rules, list) or len(rules) == 0:
                        failed_count += 1
                        failed_details.append(
                            {"file": os.path.basename(yaml_file), "error": "rules 字段必须是非空数组"}
                        )
                        continue

                    # 使用 opengrep 验证规则
                    is_valid, error_msg = await _validate_opengrep_rule(content)
                    if not is_valid:
                        failed_count += 1
                        failed_details.append(
                            {"file": os.path.basename(yaml_file), "error": f"规则验证失败: {error_msg}"}
                        )
                        continue

                    # 获取规则信息
                    rule = rules[0]  # 通常一个文件包含一个规则
                    rule_id = rule.get("id", os.path.splitext(os.path.basename(yaml_file))[0])
                    languages = rule.get("languages", [])
                    language = languages[0] if languages else "unknown"
                    severity = rule.get("severity", "WARNING").upper()
                    metadata = rule.get("metadata", {})

                    # 验证严重程度
                    if severity not in ["ERROR", "WARNING", "INFO"]:
                        severity = "WARNING"

                    # 确保规则名唯一
                    unique_rule_name = await _get_unique_rule_name(db, rule_id)

                    # 创建规则对象
                    new_rule = OpengrepRule(
                        name=unique_rule_name,
                        pattern_yaml=content,
                        language=language,
                        severity=severity,
                        source="upload",
                        patch=metadata.get("source-url", ""),
                        correct=True,
                        is_active=True,
                    )

                    rules_to_add.append(new_rule)
                    existing_md5s.add(md5_hash)  # 添加到已存在集合中，避免当前批次内重复
                    success_count += 1

                except yaml.YAMLError as e:
                    failed_count += 1
                    failed_details.append({"file": os.path.basename(yaml_file), "error": f"YAML 解析错误: {str(e)}"})
                except Exception as e:
                    failed_count += 1
                    failed_details.append({"file": os.path.basename(yaml_file), "error": f"处理失败: {str(e)}"})

            # 批量插入数据库
            if rules_to_add:
                db.add_all(rules_to_add)
                await db.commit()

            await _cleanup_incorrect_rules(db)

            return {
                "message": "规则文件夹上传处理完成",
                "total_uploaded_files": total_uploaded_files,
                "total_yaml_files": total_count,
                "success_count": success_count,
                "failed_count": failed_count,
                "duplicate_count": duplicate_count,
                "failed_details": failed_details[:20],  # 只返回前 20 条失败详情
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


# ============ Gitleaks 密钥泄露检测 ============


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
        'title = "DeepAudit managed gitleaks config"',
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


def _normalize_gitleaks_runtime_config(runtime_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    candidate = dict(runtime_config) if isinstance(runtime_config, dict) else {}
    report_format = str(candidate.get("reportFormat") or "json").strip().lower()
    if report_format not in {"json", "sarif"}:
        report_format = "json"

    return {
        "reportFormat": report_format,
        "redact": bool(candidate.get("redact", True)),
        "customConfigToml": str(candidate.get("customConfigToml") or "").strip(),
    }


async def _build_effective_gitleaks_config_toml(
    db: AsyncSession, runtime_config: Dict[str, Any]
) -> Optional[str]:
    try:
        result = await db.execute(
            select(GitleaksRule)
            .where(GitleaksRule.is_active == True)
            .order_by(GitleaksRule.created_at.asc())
        )
        active_rules = result.scalars().all()
    except ProgrammingError as exc:
        if "gitleaks_rules" in str(exc):
            logger.warning("gitleaks_rules table not found, fallback to custom/default config only")
            # Must rollback to clear PostgreSQL's aborted transaction state before
            # any further DB operations can succeed on this session.
            await db.rollback()
            active_rules = []
        else:
            raise
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
        if "gitleaks_rules" in str(exc):
            return []
        raise


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
                # 构建 gitleaks 命令
                cmd = [
                    "gitleaks",
                    "detect",
                    "--source",
                    full_target_path,
                    "--report-format",
                    str(gcfg.get("reportFormat") or "json"),
                    "--report-path",
                    report_file,
                    "--exit-code",
                    "0",  # 不要因为发现密钥而返回非零退出码
                ]
                if no_git:
                    cmd.append("--no-git")

                if bool(gcfg.get("redact", True)):
                    cmd.append("--redact")

                if config_file:
                    cmd.extend(["--config", config_file])

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

                        # 脱敏密钥
                        secret = finding.get("Secret", "")
                        if len(secret) > 8:
                            masked_secret = (
                                secret[:4] + "*" * (len(secret) - 8) + secret[-4:]
                            )
                        else:
                            masked_secret = "*" * len(secret)

                        gitleaks_finding = GitleaksFinding(
                            scan_task_id=task_id,
                            rule_id=finding.get("RuleID", "unknown"),
                            description=finding.get("Description", ""),
                            file_path=file_path,
                            start_line=finding.get("StartLine"),
                            end_line=finding.get("EndLine"),
                            secret=masked_secret,
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

@router.get("/cache/repo-stats")
async def get_repo_cache_stats(
    current_user: User = Depends(deps.get_current_user),
):
    """
    获取 Git 项目缓存统计信息
    
    返回所有缓存的 Git 项目列表及其大小信息
    """
    stats = GlobalRepoCacheManager.get_cache_size()
    all_caches = GlobalRepoCacheManager.get_all_cached_repos()
    
    repos = []
    for key, cache in all_caches.items():
        if cache.cache_dir.exists():
            repo_size = sum(
                f.stat().st_size 
                for f in cache.cache_dir.rglob('*') 
                if f.is_file()
            )
            repos.append({
                "repo_key": key,
                "repo_owner": cache.repo_owner,
                "repo_name": cache.repo_name,
                "cache_dir": str(cache.cache_dir),
                "size_mb": round(repo_size / 1024 / 1024, 2),
                "created_at": cache.created_at,
                "last_accessed": cache.last_accessed,
                "access_count": cache.access_count,
            })
    
    return {
        "total_cached_repos": stats["total_cached_repos"],
        "total_size_gb": stats["total_size_gb"],
        "repos": repos,
    }


@router.post("/cache/cleanup-unused")
async def cleanup_unused_cache(
    max_age_days: int = Query(30, ge=1, description="缓存最大存在天数"),
    max_unused_days: int = Query(14, ge=1, description="缓存最大未访问天数"),
    current_user: User = Depends(deps.get_current_user),
):
    """
    清理未使用的 Git 项目缓存
    
    删除超过指定天数未访问或总存在时间太长的缓存
    
    Args:
        max_age_days: 缓存最大存在天数，超过此值的缓存将被清理（默认30天）
        max_unused_days: 缓存最大未访问天数，超过此值的缓存将被清理（默认14天）
    """
    try:
        cleaned_count = GlobalRepoCacheManager.cleanup_unused_caches(
            max_age_days=max_age_days,
            max_unused_days=max_unused_days,
        )
        
        stats = GlobalRepoCacheManager.get_cache_size()
        
        return {
            "message": f"已清理 {cleaned_count} 个过期的缓存",
            "cleaned_count": cleaned_count,
            "remaining_cached_repos": stats["total_cached_repos"],
            "remaining_size_gb": stats["total_size_gb"],
        }
    except Exception as e:
        logger.error(f"清理缓存失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理缓存失败: {str(e)}")


@router.post("/cache/clear-all")
async def clear_all_cache(
    current_user: User = Depends(deps.get_current_user),
):
    """
    清理所有 Git 项目缓存
    
    警告：此操作会删除所有缓存的 Git 项目，
    下次处理 Patch 文件时需要重新克隆所有项目
    """
    try:
        before_stats = GlobalRepoCacheManager.get_cache_size()
        GlobalRepoCacheManager.clear_all_caches()
        
        return {
            "message": "已清理所有缓存",
            "cleared_repos": before_stats["total_cached_repos"],
            "cleared_size_gb": before_stats["total_size_gb"],
        }
    except Exception as e:
        logger.error(f"清理所有缓存失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理失败: {str(e)}")
