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
from app.api.v1.schemas.rule_flows import (
    GitleaksRuleBatchUpdateRequest,
    GitleaksRuleCreateRequest,
    GitleaksRuleResponse,
    GitleaksRuleUpdateRequest,
    OpengrepRuleCreateRequest,
    OpengrepRulePatchResponse,
    OpengrepRuleTextCreateRequest,
    OpengrepRuleTextResponse,
    OpengrepRuleUpdateRequest,
)
from app.services.gitleaks_rules_seed import ensure_builtin_gitleaks_rules
from app.services.llm.service import LLMConfigError, LLMService
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
        _ensure_opengrep_xdg_dirs()
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
        from app.services.user_config_service import load_effective_user_config

        return await load_effective_user_config(
            db=db,
            user_id=user_id,
        )
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
            f"从数据库获取用户 {current_user.id} 的 LLM 配置: "
            f"provider={llm_config.get('llmProvider')}, model={llm_config.get('llmModel')}"
        )
    else:
        logger.info(f"未找到用户 {current_user.id} 的 LLM 配置，将使用默认配置")
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
                f"从数据库获取用户 {user_id} 的 LLM 配置: "
                f"provider={llm_config.get('llmProvider')}, model={llm_config.get('llmModel')}"
            )
        else:
            logger.info(f"未找到用户 {user_id} 的 LLM 配置，将使用默认配置")

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
    with tempfile.TemporaryDirectory(prefix="VulHunter_rules_", suffix="_upload") as temp_dir:
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
    with tempfile.TemporaryDirectory(prefix="VulHunter_rules_", suffix="_directory") as temp_base_dir:
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
