import logging
import yaml
import json
import subprocess
import tempfile
import os
import shutil
import zipfile
from typing import Any, List, Optional, Dict
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.future import select

from app.schemas.opengrep import (
    OpengrepRuleCreateRequest,
    OpengrepRulePatchResponse,
)
from app.db.session import get_db, async_session_factory
from app.models.opengrep import OpengrepRule, OpengrepScanTask, OpengrepFinding
from app.models.project import Project
from app.models.user import User
from app.api import deps
from app.services.rule import get_rule_by_patch
from app.core.config import settings


# ============ Schemas ============


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


def _parse_opengrep_output(stdout: str) -> List[Dict[str, Any]]:
    """解析 opengrep JSON 输出并返回 results 列表。"""
    if not stdout:
        return []
    try:
        output = json.loads(stdout)
        return output.get("results", [])
    except json.JSONDecodeError as e:
        raise ValueError("Failed to parse opengrep output") from e


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

            # 合并规则
            combined_rules = []
            for rule in rules:
                rule_data = yaml.safe_load(rule.pattern_yaml)
                if rule_data and "rules" in rule_data:
                    combined_rules.extend(rule_data["rules"])

            if not combined_rules:
                task.status = "failed"
                task.error_count = 1
                await db.commit()
                logger.error(f"No rules to apply for task {task_id}")
                return

            # 创建临时规则文件
            with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tf:
                yaml.dump({"rules": combined_rules}, tf, sort_keys=False)
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

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )

                # 解析扫描结果
                try:
                    findings = _parse_opengrep_output(result.stdout)
                except ValueError as e:
                    logger.error(f"Failed to parse opengrep output: {e}")
                    task.status = "failed"
                    task.error_count += 1
                    await db.commit()
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
                        lines_scanned += end_line - start_line + 1

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
                task.warning_count = warning_count
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
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
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

    query = query.offset(skip).limit(limit)

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
