import json
import logging
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.core.config import settings
from app.db.session import async_session_factory, get_db
from app.models.opengrep import OpengrepFinding, OpengrepRule, OpengrepScanTask
from app.models.gitleaks import GitleaksScanTask, GitleaksFinding
from app.models.project import Project
from app.models.user import User
from app.schemas.opengrep import (
    OpengrepRuleCreateRequest,
    OpengrepRulePatchResponse,
    OpengrepRuleTextCreateRequest,
    OpengrepRuleTextResponse,
)
from app.services.rule import get_rule_by_patch, validate_generic_rule

# ============ Schemas ============


class OpengrepRuleBatchUpdateRequest(BaseModel):
    """批量更新规则状态请求"""

    rule_ids: Optional[List[str]] = Field(None, description="规则ID列表")
    language: Optional[str] = Field(None, description="按编程语言过滤")
    source: Optional[str] = Field(None, description="按来源过滤: internal, patch")
    severity: Optional[str] = Field(None, description="按严重程度过滤: ERROR, WARNING, INFO")
    is_active: bool = Field(..., description="要设置的激活状态")


class OpengrepScanTaskCreate(BaseModel):
    """创建 Opengrep 扫描任务请求"""

    project_id: str = Field(..., description="项目ID")
    name: Optional[str] = Field(None, description="任务名称")
    rule_ids: Optional[List[str]] = Field(None, description="选择的规则ID列表")
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
    scan_duration_ms: int
    files_scanned: int
    lines_scanned: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True


# ============ 后台扫描执行 ============


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

            # 更新任务状态为运行中
            task.status = "running"
            await db.commit()

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
                await db.commit()
                logger.error(f"No active rules found for task {task_id}")
                return

            # 生成临时规则文件
            full_target_path = os.path.join(project_root, target_path)
            if not os.path.exists(full_target_path):
                task.status = "failed"
                task.error_count = 1
                await db.commit()
                logger.error(f"Target path {full_target_path} not found")
                return

            # 合并规则并验证
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
            
            # 过滤掉所有 null 值（Semgrep/Opengrep 不允许 null）
            def remove_null_values(obj):
                """递归移除字典/列表中的 null 值"""
                if isinstance(obj, dict):
                    return {k: remove_null_values(v) for k, v in obj.items() if v is not None}
                elif isinstance(obj, list):
                    return [remove_null_values(item) for item in obj if item is not None]
                else:
                    return obj

            combined_rules = []
            invalid_rule_count = 0
            
            for rule in rules:
                try:
                    rule_data = yaml.safe_load(rule.pattern_yaml)
                    if rule_data and "rules" in rule_data:
                        for r in rule_data["rules"]:
                            # 先清理 null 值
                            cleaned_rule = remove_null_values(r)
                            # 再验证规则
                            is_valid, reason = is_valid_rule(cleaned_rule)
                            if is_valid:
                                combined_rules.append(cleaned_rule)
                            else:
                                invalid_rule_count += 1
                                rule_id = cleaned_rule.get("id", "unknown")
                                logger.warning(f"Skipping invalid rule {rule_id}: {reason}")
                except Exception as e:
                    logger.warning(f"Failed to parse rule {rule.name}: {e}")
                    invalid_rule_count += 1

            if invalid_rule_count > 0:
                logger.warning(f"Skipped {invalid_rule_count} invalid rules for task {task_id}")

            if not combined_rules:
                task.status = "failed"
                task.error_count = 1
                await db.commit()
                logger.error(f"No valid rules to apply for task {task_id}")
                return

            # 创建临时规则文件
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tf:
                yaml.dump({"rules": combined_rules}, tf, sort_keys=False, default_flow_style=False)
                rule_file = tf.name

            try:
                # 执行 opengrep 扫描
                cmd = [
                    "opengrep",
                    "--config",
                    rule_file,
                    "--json",
                    full_target_path,
                ]

                logger.info(f"Executing opengrep for task {task_id}: {' '.join(cmd)}")

                # opengrep/semgrep 在解析空代理变量时会报错，扫描时显式清理代理环境变量
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

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,
                    env=scan_env,
                )

                # 解析扫描结果
                try:
                    findings, scan_errors = _parse_opengrep_output(result.stdout)
                except ValueError as e:
                    logger.error(f"Failed to parse opengrep output: {e}, stderr={result.stderr}")
                    task.status = "failed"
                    task.error_count += 1
                    await db.commit()
                    return

                fatal_rule_errors = [item for item in scan_errors if _is_fatal_rule_error(item)]
                non_fatal_scan_errors = [
                    item for item in scan_errors if not _is_fatal_rule_error(item)
                ]

                # 规则配置错误/执行错误才判定失败；源码语法错误不视为失败
                if fatal_rule_errors:
                    task.status = "failed"
                    task.error_count = max(1, len(fatal_rule_errors))
                    await db.commit()
                    logger.error(
                        f"Scan task {task_id} failed with fatal rule errors: {fatal_rule_errors[:3]}"
                    )
                    return

                # 记录警告但不影响任务状态
                if scan_errors:
                    warning_errors = [err for err in scan_errors if err.get("level") != "error"]
                    if warning_errors:
                        # PartialParsing 等警告是正常的，不影响扫描结果
                        logger.info(
                            f"Scan task {task_id} has {len(warning_errors)} parsing warnings "
                            f"(normal for complex C/C++ code, not affecting results)"
                        )

                if non_fatal_scan_errors:
                    # 非致命错误（如部分文件解析失败）记录为 INFO，不影响整体扫描
                    logger.info(
                        f"Scan task {task_id} has {len(non_fatal_scan_errors)} non-fatal parsing issues "
                        f"(normal, scan continues with other files)"
                    )

                # 无扫描结果且进程异常退出，且无可忽略扫描错误时，按执行失败处理
                if result.returncode != 0 and not findings and not non_fatal_scan_errors:
                    stderr_text = (result.stderr or "").strip()
                    task.status = "failed"
                    task.error_count = 1
                    await db.commit()
                    logger.error(
                        f"Scan task {task_id} failed: returncode={result.returncode}, stderr={stderr_text}"
                    )
                    return

                # 保存发现
                error_count = 0
                warning_count = 0
                files_scanned = set()
                lines_scanned = 0

                for finding in findings:
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
                task.status = "completed"
                task.total_findings = len(findings)
                task.error_count = error_count
                task.warning_count = warning_count + len(non_fatal_scan_errors)
                task.files_scanned = len(files_scanned)
                task.lines_scanned = lines_scanned

                await db.commit()
                logger.info(
                    f"Scan task {task_id} completed: "
                    f"{len(findings)} findings, "
                    f"{error_count} errors, "
                    f"{warning_count} warnings"
                )

            finally:
                # 清理临时文件
                try:
                    os.unlink(rule_file)
                except Exception as e:
                    logger.warning(f"Failed to delete temporary rule file: {e}")

        except Exception as e:
            logger.error(f"Error executing opengrep scan for task {task_id}: {e}")
            try:
                result = await db.execute(
                    select(OpengrepScanTask).where(OpengrepScanTask.id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_count += 1
                    await db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to update task status: {commit_error}")
        finally:
            # 清理解压的临时目录
            if project_root and project_root.startswith("/tmp") and os.path.exists(project_root):
                try:
                    shutil.rmtree(project_root, ignore_errors=True)
                    logger.info(f"Cleaned up temporary project directory: {project_root}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary directory {project_root}: {e}")


logger = logging.getLogger(__name__)
router = APIRouter()


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

    # 验证规则存在
    result = await db.execute(select(OpengrepRule).where(OpengrepRule.id.in_(request.rule_ids)))
    rules = result.scalars().all()
    if len(rules) != len(request.rule_ids):
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
        rulesets=json.dumps([{"rule_id": rid} for rid in request.rule_ids]),
    )
    db.add(scan_task)
    await db.commit()
    await db.refresh(scan_task)

    # 后台执行扫描
    background_tasks.add_task(
        _execute_opengrep_scan,
        scan_task.id,
        project_root,
        request.target_path,
        request.rule_ids,
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
    return task


@router.get("/tasks/{task_id}/findings", response_model=List[OpengrepFindingResponse])
async def get_static_task_findings(
    task_id: str,
    severity: Optional[str] = Query(None, description="按严重程度过滤: ERROR, WARNING, INFO"),
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

    # 构建查询
    query = select(OpengrepFinding).where(OpengrepFinding.scan_task_id == task_id)

    if severity:
        query = query.where(OpengrepFinding.severity == severity)
    if status:
        query = query.where(OpengrepFinding.status == status)

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    findings = result.scalars().all()
    return findings


@router.post("/findings/{finding_id}/status")
async def update_static_task_finding(
    finding_id: str,
    status: str = Query(..., regex="^(open|verified|false_positive)$", description="新状态"),
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
    is_active: Optional[bool] = Query(None, description="只获取活跃规则"),
    db: AsyncSession = Depends(get_db),
):
    """获取 Opengrep 规则列表"""
    query = select(OpengrepRule)

    if language:
        query = query.where(OpengrepRule.language == language)
    if source:
        query = query.where(OpengrepRule.source == source)
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
        "source": rule.source,
        "patch": rule.patch,
        "correct": rule.correct,
        "is_active": rule.is_active,
        "created_at": rule.create_at,
    }


@router.post("/rules/create", response_model=OpengrepRulePatchResponse)
async def create_opengrep_rule(
    request: OpengrepRuleCreateRequest, db: AsyncSession = Depends(get_db)
):
    """
    创建一个新的 Opengrep 规则（从 Patch 生成）

    使用大模型基于 patch 内容生成检测规则，并保存所有尝试到数据库
    """
    result = await get_rule_by_patch(request)

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

    支持通过规则ID列表、编程语言、规则来源、严重程度等条件进行过滤
    至少需要提供一个过滤条件
    """
    # 构建查询条件
    query = select(OpengrepRule)
    has_filter = False

    if request.rule_ids:
        query = query.where(OpengrepRule.id.in_(request.rule_ids))
        has_filter = True

    if request.language:
        query = query.where(OpengrepRule.language == request.language)
        has_filter = True

    if request.source:
        query = query.where(OpengrepRule.source == request.source)
        has_filter = True

    if request.severity:
        query = query.where(OpengrepRule.severity == request.severity)
        has_filter = True

    if not has_filter:
        raise HTTPException(
            status_code=400,
            detail="至少需要提供一个过滤条件（rule_ids, language, source, severity）",
        )

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

    class Config:
        from_attributes = True


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
    status: str

    class Config:
        from_attributes = True


async def _execute_gitleaks_scan(
    task_id: str,
    project_root: str,
    target_path: str,
    no_git: bool = True,
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

            # 更新任务状态为运行中
            task.status = "running"
            await db.commit()

            # 构建扫描路径
            full_target_path = os.path.join(project_root, target_path)
            if not os.path.exists(full_target_path):
                task.status = "failed"
                task.error_message = f"Target path {full_target_path} not found"
                await db.commit()
                logger.error(f"Target path {full_target_path} not found")
                return

            # 创建临时输出文件
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as tf:
                report_file = tf.name

            try:
                # 构建 gitleaks 命令
                cmd = [
                    "gitleaks",
                    "detect",
                    "--source",
                    full_target_path,
                    "--report-format",
                    "json",
                    "--report-path",
                    report_file,
                    "--exit-code",
                    "0",  # 不要因为发现密钥而返回非零退出码
                ]
                if no_git:
                    cmd.append("--no-git")

                logger.info(
                    f"Executing gitleaks for task {task_id}: {' '.join(cmd)}"
                )

                start_time = datetime.now()
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                end_time = datetime.now()
                scan_duration_ms = int((end_time - start_time).total_seconds() * 1000)

                # 检查执行结果
                if result.returncode != 0:
                    error_msg = result.stderr or result.stdout or "Unknown error"
                    task.status = "failed"
                    task.error_message = error_msg[:500]
                    task.scan_duration_ms = scan_duration_ms
                    await db.commit()
                    logger.error(
                        f"Gitleaks scan task {task_id} failed: {error_msg}"
                    )
                    return

                # 读取扫描结果
                if not os.path.exists(report_file):
                    task.status = "completed"
                    task.total_findings = 0
                    task.scan_duration_ms = scan_duration_ms
                    await db.commit()
                    logger.info(
                        f"Gitleaks scan task {task_id} completed with no findings"
                    )
                    return

                with open(report_file, "r") as f:
                    content = f.read().strip()
                    if not content:
                        findings = []
                    else:
                        try:
                            findings = json.loads(content)
                            if not isinstance(findings, list):
                                findings = []
                        except json.JSONDecodeError as e:
                            logger.error(
                                f"Failed to parse gitleaks output: {e}"
                            )
                            task.status = "failed"
                            task.error_message = f"Failed to parse JSON output: {str(e)}"
                            task.scan_duration_ms = scan_duration_ms
                            await db.commit()
                            return

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
                task.status = "completed"
                task.total_findings = len(findings)
                task.scan_duration_ms = scan_duration_ms
                task.files_scanned = len(files_scanned)

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

        except Exception as e:
            logger.error(f"Error executing gitleaks scan for task {task_id}: {e}")
            try:
                result = await db.execute(
                    select(GitleaksScanTask).where(GitleaksScanTask.id == task_id)
                )
                task = result.scalar_one_or_none()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)[:500]
                    await db.commit()
            except Exception as commit_error:
                logger.error(
                    f"Failed to update task status after error: {commit_error}"
                )


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

    # 添加后台任务
    background_tasks.add_task(
        _execute_gitleaks_scan,
        scan_task.id,
        project_root,
        request.target_path,
        request.no_git,
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


@router.post("/gitleaks/findings/{finding_id}/status")
async def update_gitleaks_finding_status(
    finding_id: str,
    status: str = Query(
        ...,
        regex="^(open|verified|false_positive|fixed)$",
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
