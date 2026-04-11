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
