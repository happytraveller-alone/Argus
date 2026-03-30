from typing import Any, Awaitable, Callable, Dict, List, Optional, Literal, cast
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    BackgroundTasks,
    UploadFile,
    File,
    Query,
    Form,
)
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, case, or_, and_
from sqlalchemy.future import select
from sqlalchemy.orm import noload, selectinload
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timedelta, timezone
import shutil
import os
import uuid
import json
import tempfile
import logging
import hashlib
import asyncio
import base64
from pathlib import Path
from collections import defaultdict

from app.db.static_finding_paths import (
    collect_zip_relative_paths,
    resolve_zip_member_path,
)

logger = logging.getLogger(__name__)

# 需要过滤的目录和文件
EXCLUDE_PATTERNS = {
    # Node.js
    "node_modules",
    "npm-debug.log",
    "yarn-error.log",
    ".npm",
    ".yarn",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    
    # Python
    "__pycache__",
    ".pyc",
    ".pyo",
    "*.egg-info",
    ".eggs",
    "dist",
    "build",
    ".venv",
    "venv",
    "env",
    ".Python",
    "pip-log.txt",
    "pip-delete-this-directory.txt",
    
    # Git
    ".git",
    ".gitignore",
    ".gitattributes",
    
    # IDE
    ".vscode",
    ".idea",
    ".DS_Store",
    "*.swp",
    "*.swo",
    "*.swn",
    ".project",
    ".classpath",
    
    # Build & Cache
    ".cache",
    ".gradle",
    ".m2",
    "target",
    "out",
    
    # Java
    ".class",
    ".jar",
    
    # Ruby
    ".bundle",
    "Gemfile.lock",
    
    # Go
    "vendor",
}


def _is_test_directory_name(name: str) -> bool:
    """目录名包含 test（不区分大小写）时视为测试目录。"""
    return "test" in (name or "").lower()


def should_exclude_file(file_path: str, is_directory: Optional[bool] = None) -> bool:
    """
    判断文件是否应该被排除
    
    Args:
        file_path: 相对于解压目录的文件路径
    
    Returns:
        True 表示应该排除，False 表示应该包含
    """
    # 规范化路径
    normalized_path = file_path.replace("\\", "/").strip("/")
    parts = [part for part in normalized_path.split("/") if part]
    if not parts:
        return False

    # 判断用于 test 目录匹配的路径段
    if is_directory is True:
        directory_parts = parts
    elif is_directory is False:
        directory_parts = parts[:-1]
    else:
        # 未显式指定时，尽量按路径结构判断
        directory_parts = parts if len(parts) == 1 else parts[:-1]

    if any(_is_test_directory_name(part) for part in directory_parts):
        return True
    
    # 检查路径中的每个部分
    for part in parts:
        if part in EXCLUDE_PATTERNS:
            return True
        # 检查文件扩展名
        if part.endswith(".pyc") or part.endswith(".pyo"):
            return True
        # 检查 *.egg-info 类型的目录
        if part.endswith(".egg-info"):
            return True
    
    return False


def _normalize_dashboard_range_days(range_days: int) -> Literal[7, 14, 30]:
    normalized_range_days = int(range_days)
    if normalized_range_days not in {7, 14, 30}:
        raise HTTPException(
            status_code=422,
            detail="range_days must be one of: 7, 14, 30",
        )
    return cast(Literal[7, 14, 30], normalized_range_days)


def create_zip_with_exclusions(source_dir: str, zip_file_path: str) -> None:
    """
    创建 ZIP 文件，排除指定的目录和文件
    
    Args:
        source_dir: 源目录路径
        zip_file_path: 目标 ZIP 文件路径
    """
    import zipfile
    
    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_dir):
            # 原地修改 dirs 列表，以跳过被排除的目录
            dirs[:] = [d for d in dirs if not should_exclude_file(d, is_directory=True)]
            
            for file in files:
                file_path = os.path.join(root, file)
                # 计算相对路径
                arcname = os.path.relpath(file_path, source_dir)
                
                # 检查是否应该排除
                if not should_exclude_file(arcname, is_directory=False):
                    zipf.write(file_path, arcname)


from app.api import deps
from app.db.session import get_db, AsyncSessionLocal
from app.models.project import Project
from app.models.user import User
from app.models.agent_task import AgentTask, AgentFinding
from app.models.opengrep import OpengrepScanTask, OpengrepFinding, OpengrepRule
from app.models.gitleaks import GitleaksScanTask, GitleaksFinding, GitleaksRule
from app.models.bandit import BanditScanTask, BanditFinding, BanditRuleState
from app.models.phpstan import PhpstanScanTask, PhpstanFinding, PhpstanRuleState
from app.models.yasa import YasaScanTask, YasaFinding
from app.models.user_config import UserConfig
from app.models.project_info import ProjectInfo
import zipfile
from app.services.zip_cache_manager import get_zip_cache_manager
from app.services.scanner import (
    should_exclude,
    is_text_file,
)
from app.services.zip_storage import (
    save_project_zip,
    load_project_zip,
    get_project_zip_meta,
    delete_project_zip,
    has_project_zip,
)
from app.services.project_transfer_service import (
    cleanup_export_bundle,
    export_projects_bundle,
    import_projects_bundle,
)
from app.services.upload.upload_manager import UploadManager
from app.services.upload.compression_factory import CompressionStrategyFactory
from app.services.upload.language_detection import detect_languages_from_paths
from app.services.upload.project_stats import (
    EXTENSION_LANGUAGE_MAP,
    get_cloc_stats,
    build_static_project_description,
    get_cloc_stats_from_extracted_dir,
    generate_project_description_from_extracted_dir,
)
from app.services.project_metrics import ProjectMetricsService
from app.services.opengrep_confidence import (
    build_rule_confidence_map,
    count_high_confidence_findings_by_task_ids,
    extract_finding_payload_confidence,
    extract_rule_lookup_keys,
    normalize_confidence as normalize_opengrep_confidence,
)
from app.services.agent.utils.vulnerability_naming import (
    normalize_cwe_id,
    resolve_vulnerability_profile,
)


def calculate_file_sha256(file_path: str) -> str:
    """
    计算文件 SHA-256 哈希值（用于压缩包去重）
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _validate_zip_file_path(file_path: str) -> str:
    """
    验证文件路径，防止路径遍历攻击
    
    Args:
        file_path: 要验证的文件路径
        
    Returns:
        规范化后的路径
        
    Raises:
        HTTPException: 如果路径包含危险字符或试图遍历目录
    """
    # 清理路径
    cleaned_path = file_path.strip().lstrip("/")
    
    # 检查空路径
    if not cleaned_path:
        raise HTTPException(status_code=400, detail="文件路径不能为空")
    
    # 检查危险字符和模式
    dangerous_patterns = ["..", "\\", "\x00", "\n", "\r"]
    for pattern in dangerous_patterns:
        if pattern in cleaned_path:
            raise HTTPException(status_code=400, detail="文件路径包含非法字符")
    
    # 检查绝对路径
    if cleaned_path.startswith("/"):
        cleaned_path = cleaned_path.lstrip("/")
    
    return cleaned_path


def _is_binary_file(file_path: str, first_bytes: Optional[bytes] = None) -> bool:
    """
    判断文件是否为二进制文件
    
    Args:
        file_path: 文件路径
        first_bytes: 文件的前几个字节（可选，用于更准确的判断）
    
    Returns:
        True表示二进制文件，False表示文本文件
    """
    # 通过扩展名先检查（快速路径）
    binary_extensions = {
        '.bin', '.exe', '.dll', '.so', '.dylib',
        '.pyc', '.pyo', '.class', '.o', '.a', '.lib',
        '.zip', '.gz', '.tar', '.7z', '.rar',
        '.jpg', '.png', '.gif', '.jpeg', '.bmp', '.ico',
        '.mp3', '.mp4', '.avi', '.mov', '.mkv',
        '.pdf', '.doc', '.docx', '.xls', '.xlsx',
        '.iso', '.img', '.vmdk',
    }
    
    ext = Path(file_path).suffix.lower()
    if ext in binary_extensions:
        return True
    
    # 如果有文件字节内容，检查是否包含null字节
    if first_bytes:
        if b'\x00' in first_bytes[:512]:
            return True
    
    return False


def _calculate_zip_file_hash(zip_path: str) -> str:
    """
    计算ZIP文件的哈希值（用于缓存版本控制）
    """
    if not os.path.exists(zip_path):
        return ""
    
    try:
        mod_time = os.path.getmtime(zip_path)
        size = os.path.getsize(zip_path)
        return hashlib.md5(f"{zip_path}:{mod_time}:{size}".encode()).hexdigest()
    except:
        return ""


# 文件树相关Schema（需要在helper函数之前定义）
class FileTreeNode(BaseModel):
    """文件树节点"""
    name: str
    path: str
    type: Literal["file", "directory"]
    size: Optional[int] = None
    children: Optional[List["FileTreeNode"]] = None

    model_config = ConfigDict(from_attributes=True)


class FileTreeResponse(BaseModel):
    """文件树响应"""
    root: FileTreeNode


def _build_file_tree_from_zip(zip_path: str) -> FileTreeNode:
    """
    从ZIP文件构建文件树结构
    
    Args:
        zip_path: ZIP文件路径
    
    Returns:
        FileTreeNode: 根节点树结构
    """
    # 使用字典构建树：path -> {info}
    tree_dict: Dict[str, Dict[str, Any]] = {}
    
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            path = info.filename.rstrip("/")
            
            # 跳过空路径和被排除的文件
            if not path or should_exclude_file(path):
                continue
            
            # 标准化路径
            parts = path.split("/")
            
            # 确保父目录存在于tree_dict
            for i in range(len(parts)):
                current_path = "/".join(parts[:i+1])
                if current_path not in tree_dict:
                    is_dir = i < len(parts) - 1 or info.is_dir()
                    tree_dict[current_path] = {
                        "name": parts[i],
                        "path": current_path,
                        "type": "directory" if is_dir else "file",
                        "size": None if is_dir else info.file_size,
                        "children": {}
                    }
    
    # 构建树结构
    def build_tree(path_prefix: str = "") -> FileTreeNode:
        node = FileTreeNode(
            name="root" if not path_prefix else path_prefix.split("/")[-1],
            path=path_prefix or "/",
            type="directory",
            children=[]
        )
        
        # 找到所有直接子节点
        for full_path, node_info in tree_dict.items():
            parent_path = "/".join(full_path.split("/")[:-1])
            
            if parent_path == path_prefix:
                # 如果是目录，递归构建
                if node_info["type"] == "directory":
                    child = build_tree(full_path)
                else:
                    # 文件节点
                    child = FileTreeNode(
                        name=node_info["name"],
                        path=full_path,
                        type="file",
                        size=node_info["size"]
                    )
                
                if node.children is None:
                    node.children = []
                node.children.append(child)
        
        # 按名称排序（目录优先）
        if node.children:
            node.children.sort(
                key=lambda x: (x.type == "file", x.name.lower())
            )
        
        return node
    
    return build_tree()


def _build_file_tree_from_repo_files(files: List[Dict[str, Any]]) -> FileTreeNode:
    """
    从文件列表构建树结构（用于仓库项目）
    
    Args:
        files: 文件列表，每个元素为 {"path": "...", "size": ...}
    
    Returns:
        FileTreeNode: 根节点树结构
    """
    # 构建树字典
    tree_dict: Dict[str, Dict[str, Any]] = {}
    
    for file_info in files:
        path = file_info.get("path", "").strip().lstrip("/")
        if not path:
            continue
        
        parts = path.split("/")
        
        # 创建所有路径节点
        for i in range(len(parts)):
            current_path = "/".join(parts[:i+1])
            if current_path not in tree_dict:
                is_dir = i < len(parts) - 1
                size = None if is_dir else file_info.get("size", 0)
                tree_dict[current_path] = {
                    "name": parts[i],
                    "path": current_path,
                    "type": "directory" if is_dir else "file",
                    "size": size,
                }
    
    # 构建树结构
    def build_tree(path_prefix: str = "") -> FileTreeNode:
        node = FileTreeNode(
            name="root" if not path_prefix else path_prefix.split("/")[-1],
            path=path_prefix or "/",
            type="directory",
            children=[]
        )
        
        # 找到直接子节点
        child_paths = set()
        for full_path in tree_dict.keys():
            parent_path = "/".join(full_path.split("/")[:-1]) if "/" in full_path else ""
            
            if parent_path == path_prefix:
                child_paths.add(full_path)
        
        # 构建子节点
        for child_path in sorted(child_paths):
            node_info = tree_dict[child_path]
            
            if node_info["type"] == "directory":
                child = build_tree(child_path)
            else:
                child = FileTreeNode(
                    name=node_info["name"],
                    path=child_path,
                    type="file",
                    size=node_info["size"]
                )
            
            if node.children is None:
                node.children = []
            node.children.append(child)
        
        # 按名称排序（目录优先）
        if node.children:
            node.children.sort(
                key=lambda x: (x.type == "file", x.name.lower())
            )
        
        return node
    
    return build_tree()


async def _get_user_config(db: AsyncSession, user_id: Optional[str]) -> Optional[dict]:
    """获取用户配置（与 static_tasks 一致）"""
    if not user_id:
        return None

    try:
        from app.api.v1.endpoints.config import _load_effective_user_config

        return await _load_effective_user_config(
            db=db,
            user_id=user_id,
        )
    except Exception as e:
        logger.warning(f"Failed to get user config: {e}")

    return None


async def _resolve_project_description_bundle(
    *,
    extracted_dir: str,
    extracted_files: Optional[List[str]],
    project_name: Optional[str],
    db: AsyncSession,
    user_id: Optional[str],
) -> tuple[str, str, Literal["llm", "static"]]:
    language_info = await get_cloc_stats_from_extracted_dir(
        extracted_dir,
        extracted_files=extracted_files,
    )
    description = build_static_project_description(
        language_info,
        (project_name or "").strip() or None,
    )
    source: Literal["llm", "static"] = "static"

    user_config = await _get_user_config(db, user_id)
    if user_config:
        try:
            llm_result = await generate_project_description_from_extracted_dir(
                extracted_dir,
                user_config=user_config,
                project_name=(project_name or "").strip() or None,
            )
            llm_description = ""
            if isinstance(llm_result, dict):
                llm_description = str(llm_result.get("project_description") or "").strip()
            if llm_description:
                description = llm_description
                source = "llm"
        except Exception as e:
            logger.warning(f"生成项目描述时 LLM 失败，已回退静态描述: {e}")

    return description, language_info, source


async def _get_or_create_project_info(db: AsyncSession, project_id: str) -> ProjectInfo:
    result = await db.execute(select(ProjectInfo).where(ProjectInfo.project_id == project_id))
    project_info = result.scalars().first()
    if project_info:
        return project_info

    project_info = ProjectInfo(
        project_id=project_id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(project_info)
    return project_info


async def find_duplicate_zip_project(
    db: AsyncSession, zip_hash: str, current_project_id: str
) -> Optional[Project]:
    """
    查找是否存在已上传相同压缩包内容的其他项目
    """
    result = await db.execute(
        select(Project).where(
            Project.zip_file_hash == zip_hash,
            Project.id != current_project_id,
        )
    )
    return result.scalars().first()


async def _get_or_prepare_project_info(db: AsyncSession, project_id: str) -> ProjectInfo:
    result = await db.execute(select(ProjectInfo).where(ProjectInfo.project_id == project_id))
    project_info = result.scalars().first()
    if project_info:
        return project_info

    return ProjectInfo(
        project_id=project_id,
        created_at=datetime.now(timezone.utc),
    )


def _empty_language_info_json() -> str:
    return '{"total": 0, "total_files": 0, "languages": {}}'


async def ensure_project_info_language_stats(
    db: AsyncSession,
    project_id: str,
    *,
    raise_on_error: bool = True,
    cloc_loader: Optional[Callable[[ProjectInfo], Awaitable[str]]] = None,
) -> ProjectInfo:
    project_info_result = await db.execute(
        select(ProjectInfo).where(ProjectInfo.project_id == project_id)
    )
    project_info = project_info_result.scalars().first()
    empty_language_info = _empty_language_info_json()

    if project_info and project_info.status == "completed" and project_info.language_info:
        project_info.description = project_info.description or ""
        return project_info

    if project_info and project_info.status == "pending":
        project_info.language_info = project_info.language_info or empty_language_info
        project_info.description = project_info.description or ""
        return project_info

    if not project_info:
        project_info = ProjectInfo(
            project_id=project_id,
            status="pending",
            created_at=datetime.now(timezone.utc),
            language_info=empty_language_info,
        )
        db.add(project_info)
        await db.commit()
        await db.refresh(project_info)

    try:
        project_info.status = "pending"
        db.add(project_info)
        await db.commit()
        await db.refresh(project_info)

        cloc_result = await (cloc_loader or get_cloc_stats)(project_info)
        project_info.language_info = cloc_result or empty_language_info
        project_info.description = project_info.description or ""
        project_info.status = "completed"
        db.add(project_info)
        await db.commit()
        await db.refresh(project_info)
        return project_info
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取项目信息失败: {e}", exc_info=True)
        try:
            project_info.status = "failed"
            project_info.language_info = project_info.language_info or empty_language_info
            project_info.description = project_info.description or ""
            db.add(project_info)
            await db.commit()
            await db.refresh(project_info)
        except Exception:
            logger.exception("保存失败状态时出错")

        if raise_on_error:
            raise HTTPException(status_code=500, detail=f"获取项目信息失败: {str(e)}")
        return project_info


def _serialize_programming_languages(
    programming_languages: Optional[List[str]],
) -> str:
    return json.dumps(programming_languages or [], ensure_ascii=False)


def _build_zip_project(
    *,
    name: str,
    description: Optional[str],
    default_branch: Optional[str],
    programming_languages: Optional[List[str]],
    owner_id: str,
) -> Project:
    return Project(
        id=str(uuid.uuid4()),
        name=name,
        source_type="zip",
        repository_url=None,
        repository_type="other",
        description=description,
        default_branch=default_branch or "main",
        programming_languages=_serialize_programming_languages(programming_languages),
        owner_id=owner_id,
    )


def _normalize_archive_extension(filename: str) -> str:
    file_name_lower = filename.lower()
    file_ext = Path(filename).suffix.lower()
    if file_name_lower.endswith((".tar.gz", ".tgz", ".tar.gzip")):
        return ".tar.gz"
    if file_name_lower.endswith((".tar.bz2", ".tbz", ".tbz2")):
        return ".tar.bz2"
    return file_ext


def _validate_archive_extension(filename: str) -> str:
    supported_formats = CompressionStrategyFactory.get_supported_formats()
    file_ext = _normalize_archive_extension(filename)
    if file_ext not in supported_formats:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(sorted(supported_formats))}",
        )
    return file_ext


async def _store_uploaded_archive_for_project(
    *,
    db: AsyncSession,
    project: Project,
    file: UploadFile,
    user_id: str,
    commit: bool,
) -> Dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    file_ext = _validate_archive_extension(file.filename)
    archive_saved = False

    try:
        with tempfile.TemporaryDirectory(prefix="VulHunter_", suffix="_zip_upload") as temp_dir:
            temp_upload_path = os.path.join(temp_dir, file.filename)
            with open(temp_upload_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            is_valid, error = UploadManager.validate_file(temp_upload_path)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"文件验证失败: {error}")

            temp_extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(temp_extract_dir, exist_ok=True)

            success, extracted_files, error = await UploadManager.extract_file(
                temp_upload_path,
                temp_extract_dir,
                max_files=100000,
            )
            if not success:
                raise HTTPException(status_code=400, detail=f"解压失败: {error}")

            final_zip_path = os.path.join(temp_dir, f"{project.id}.zip")
            try:
                create_zip_with_exclusions(temp_extract_dir, final_zip_path)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"重新压缩失败: {str(exc)}") from exc

            is_valid, error = UploadManager.validate_file(final_zip_path)
            if not is_valid:
                raise HTTPException(
                    status_code=400,
                    detail=f"生成的 ZIP 文件验证失败: {error}",
                )

            success, file_list, error = UploadManager.get_file_list_preview(final_zip_path)
            if not success:
                raise HTTPException(status_code=400, detail=error)

            zip_hash = calculate_file_sha256(final_zip_path)
            if project.zip_file_hash and project.zip_file_hash == zip_hash:
                raise HTTPException(
                    status_code=409,
                    detail="当前项目已上传相同内容压缩包，无需重复上传",
                )

            duplicate_project = await find_duplicate_zip_project(db, zip_hash, project.id)
            if duplicate_project:
                raise HTTPException(
                    status_code=409,
                    detail=f"检测到相同压缩包已上传到项目「{duplicate_project.name}」，请勿重复上传",
                )

            meta = await save_project_zip(project.id, final_zip_path, f"{project.id}.zip")
            archive_saved = True

            filtered_paths = [
                path for path in (extracted_files or []) if not should_exclude_file(path)
            ]
            detected_languages = detect_languages_from_paths(filtered_paths)
            project.programming_languages = _serialize_programming_languages(detected_languages)
            project.zip_file_hash = zip_hash
            description, language_info, _source = await _resolve_project_description_bundle(
                extracted_dir=temp_extract_dir,
                extracted_files=extracted_files,
                project_name=project.name,
                db=db,
                user_id=user_id,
            )
            project.description = description

            project_info = await _get_or_prepare_project_info(db, project.id)
            project_info.language_info = language_info
            project_info.description = description
            project_info.status = "completed"
            await ProjectMetricsService.ensure_base_metrics(db, project.id)
            db.add(project)
            db.add(project_info)

            if commit:
                try:
                    await db.commit()
                    await db.refresh(project)
                except IntegrityError:
                    await db.rollback()
                    await delete_project_zip(project.id)
                    raise HTTPException(
                        status_code=409,
                        detail="检测到相同压缩包已存在，请勿重复上传",
                    )

            return {
                "message": "文件上传成功（已转换为 ZIP 格式）",
                "original_filename": file.filename,
                "original_format": file_ext,
                "final_filename": meta["original_filename"],
                "final_format": ".zip",
                "file_size": meta["file_size"],
                "uploaded_at": meta["uploaded_at"],
                "file_hash": zip_hash,
                "file_count": len(file_list),
                "sample_files": file_list[:10],
                "detected_languages": detected_languages,
            }
    except HTTPException:
        if archive_saved:
            await delete_project_zip(project.id)
        if commit:
            await db.rollback()
        raise
    except Exception as exc:
        if archive_saved:
            await delete_project_zip(project.id)
        if commit:
            await db.rollback()
        raise HTTPException(status_code=500, detail=f"上传失败: {str(exc)}") from exc




# Schemas
class ProjectCreate(BaseModel):
    name: str
    source_type: Optional[str] = "zip"  # 仅支持 'zip'
    repository_url: Optional[str] = None
    repository_type: Optional[str] = "other"  # github, gitlab, other
    description: Optional[str] = None
    default_branch: Optional[str] = "main"
    programming_languages: Optional[List[str]] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    source_type: Optional[str] = None
    repository_url: Optional[str] = None
    repository_type: Optional[str] = None
    description: Optional[str] = None
    default_branch: Optional[str] = None
    programming_languages: Optional[List[str]] = None


class ProjectExportRequest(BaseModel):
    project_ids: Optional[List[str]] = None
    include_archives: bool = True


class ProjectImportItem(BaseModel):
    source_project_id: str
    name: Optional[str] = None
    project_id: Optional[str] = None
    reason: Optional[str] = None
    existing_project_id: Optional[str] = None


class ProjectImportResponse(BaseModel):
    imported_projects: List[ProjectImportItem]
    skipped_projects: List[ProjectImportItem]
    failed_projects: List[ProjectImportItem]
    warnings: List[str]


class OwnerSchema(BaseModel):
    id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ProjectManagementMetricsResponse(BaseModel):
    archive_size_bytes: Optional[int] = None
    archive_original_filename: Optional[str] = None
    archive_uploaded_at: Optional[datetime] = None
    total_tasks: int
    completed_tasks: int
    running_tasks: int
    agent_tasks: int
    opengrep_tasks: int
    gitleaks_tasks: int
    bandit_tasks: int
    phpstan_tasks: int
    critical: int
    high: int
    medium: int
    low: int
    verified_critical: int
    verified_high: int
    verified_medium: int
    verified_low: int
    last_completed_task_at: Optional[datetime] = None
    status: Literal["pending", "ready", "failed"]
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    source_type: Optional[str] = "zip"  # 'repository' 或 'zip'
    repository_url: Optional[str] = None
    repository_type: Optional[str] = None  # github, gitlab, other
    default_branch: Optional[str] = None
    programming_languages: Optional[str] = None
    owner_id: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    owner: Optional[OwnerSchema] = None
    management_metrics: Optional[ProjectManagementMetricsResponse] = None

    model_config = ConfigDict(from_attributes=True)


class StatsResponse(BaseModel):
    total_projects: int
    active_projects: int
    total_tasks: int
    completed_tasks: int
    interrupted_tasks: int
    running_tasks: int
    failed_tasks: int
    total_issues: int
    resolved_issues: int


class DashboardScanRunsItem(BaseModel):
    project_id: str
    project_name: str
    static_runs: int
    intelligent_runs: int
    hybrid_runs: int
    total_runs: int


class DashboardVulnsItem(BaseModel):
    project_id: str
    project_name: str
    static_vulns: int
    intelligent_vulns: int
    hybrid_vulns: int
    total_vulns: int


class DashboardSnapshotResponse(BaseModel):
    generated_at: datetime
    total_scan_duration_ms: int
    scan_runs: List[DashboardScanRunsItem]
    vulns: List[DashboardVulnsItem]
    rule_confidence: List["DashboardRuleConfidenceItem"]
    rule_confidence_by_language: List["DashboardRuleConfidenceByLanguageItem"]
    cwe_distribution: List["DashboardCweDistributionItem"]
    summary: "DashboardSummaryItem"
    daily_activity: List["DashboardDailyActivityItem"]
    verification_funnel: "DashboardVerificationFunnelItem"
    task_status_breakdown: "DashboardTaskStatusBreakdownItem"
    task_status_by_scan_type: "DashboardTaskStatusByScanTypeItem"
    engine_breakdown: List["DashboardEngineBreakdownItem"]
    project_hotspots: List["DashboardProjectHotspotItem"]
    language_risk: List["DashboardLanguageRiskItem"]
    recent_tasks: List["DashboardRecentTaskItem"]
    project_risk_distribution: List["DashboardProjectRiskDistributionItem"]
    verified_vulnerability_types: List["DashboardVerifiedVulnerabilityTypeItem"]
    static_engine_rule_totals: List["DashboardStaticEngineRuleTotalItem"]
    language_loc_distribution: List["DashboardLanguageLocItem"]


class DashboardRuleConfidenceItem(BaseModel):
    confidence: Literal["HIGH", "MEDIUM", "LOW", "UNSPECIFIED"]
    total_rules: int
    enabled_rules: int


class DashboardRuleConfidenceByLanguageItem(BaseModel):
    language: str
    high_count: int
    medium_count: int


class DashboardCweDistributionItem(BaseModel):
    cwe_id: str
    cwe_name: str
    total_findings: int
    opengrep_findings: int
    agent_findings: int
    bandit_findings: int


class DashboardSummaryItem(BaseModel):
    total_projects: int
    current_effective_findings: int
    current_verified_findings: int
    total_model_tokens: int
    false_positive_rate: float
    scan_success_rate: float
    avg_scan_duration_ms: int
    window_scanned_projects: int
    window_new_effective_findings: int
    window_verified_findings: int
    window_false_positive_rate: float
    window_scan_success_rate: float
    window_avg_scan_duration_ms: int


class DashboardDailyActivityItem(BaseModel):
    date: str
    completed_scans: int
    agent_findings: int
    opengrep_findings: int
    gitleaks_findings: int
    bandit_findings: int
    phpstan_findings: int
    yasa_findings: int
    static_findings: int
    intelligent_verified_findings: int
    hybrid_verified_findings: int
    total_new_findings: int


class DashboardVerificationFunnelItem(BaseModel):
    raw_findings: int
    effective_findings: int
    verified_findings: int
    false_positive_count: int


class DashboardTaskStatusBreakdownItem(BaseModel):
    pending: int
    running: int
    completed: int
    failed: int
    interrupted: int
    cancelled: int


class DashboardTaskStatusScanTypeBreakdownItem(BaseModel):
    static: int
    intelligent: int
    hybrid: int


class DashboardTaskStatusByScanTypeItem(BaseModel):
    pending: DashboardTaskStatusScanTypeBreakdownItem
    running: DashboardTaskStatusScanTypeBreakdownItem
    completed: DashboardTaskStatusScanTypeBreakdownItem
    failed: DashboardTaskStatusScanTypeBreakdownItem
    interrupted: DashboardTaskStatusScanTypeBreakdownItem
    cancelled: DashboardTaskStatusScanTypeBreakdownItem


class DashboardEngineBreakdownItem(BaseModel):
    engine: Literal["llm", "opengrep", "gitleaks", "bandit", "phpstan", "yasa"]
    completed_scans: int
    effective_findings: int
    verified_findings: int
    false_positive_count: int
    avg_scan_duration_ms: int
    success_rate: float


class DashboardProjectHotspotItem(BaseModel):
    project_id: str
    project_name: str
    risk_score: float
    scan_runs_window: int
    effective_findings: int
    verified_findings: int
    false_positive_rate: float
    dominant_language: str
    last_scan_at: Optional[datetime] = None
    top_engine: str


class DashboardLanguageRiskItem(BaseModel):
    language: str
    project_count: int
    loc_number: int
    effective_findings: int
    verified_findings: int
    false_positive_count: int
    findings_per_kloc: float
    rules_high: int
    rules_medium: int


class DashboardRecentTaskItem(BaseModel):
    task_id: str
    task_type: str
    title: str
    engine: str
    status: str
    created_at: datetime
    detail_path: str


class DashboardProjectRiskDistributionItem(BaseModel):
    project_id: str
    project_name: str
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    total_findings: int


class DashboardVerifiedVulnerabilityTypeItem(BaseModel):
    type_code: str
    type_name: str
    verified_count: int


class DashboardStaticEngineRuleTotalItem(BaseModel):
    engine: Literal["opengrep", "gitleaks", "bandit", "phpstan", "yasa"]
    total_rules: int


class DashboardLanguageLocItem(BaseModel):
    language: str
    loc_number: int
    project_count: int


def _normalize_dashboard_rule_confidence(
    confidence: Any,
) -> Literal["HIGH", "MEDIUM", "LOW", "UNSPECIFIED"]:
    raw_value = str(confidence or "").strip().upper()
    if raw_value in {"MIDIUM", "MIDDLE"}:
        return "MEDIUM"
    normalized = normalize_opengrep_confidence(raw_value)
    if normalized in {"HIGH", "MEDIUM", "LOW"}:
        return normalized
    return "UNSPECIFIED"


def _extract_cwe_candidates_from_rule_payload(rule_data: Any) -> List[str]:
    if not isinstance(rule_data, dict):
        return []

    candidates: List[str] = []

    def _append(values: Any) -> None:
        if isinstance(values, list):
            for value in values:
                normalized = normalize_cwe_id(value)
                if normalized and normalized not in candidates:
                    candidates.append(normalized)
            return
        normalized = normalize_cwe_id(values)
        if normalized and normalized not in candidates:
            candidates.append(normalized)

    _append(rule_data.get("cwe"))

    metadata = rule_data.get("metadata")
    if isinstance(metadata, dict):
        _append(metadata.get("cwe"))

    extra = rule_data.get("extra")
    if isinstance(extra, dict):
        _append(extra.get("cwe"))
        extra_metadata = extra.get("metadata")
        if isinstance(extra_metadata, dict):
            _append(extra_metadata.get("cwe"))

    return candidates


_BANDIT_TEST_ID_TO_CWE: Dict[str, str] = {
    "B102": "CWE-78",
    "B105": "CWE-259",
    "B106": "CWE-259",
    "B107": "CWE-259",
    "B108": "CWE-377",
    "B110": "CWE-703",
    "B112": "CWE-703",
    "B301": "CWE-502",
    "B302": "CWE-502",
    "B303": "CWE-327",
    "B304": "CWE-327",
    "B305": "CWE-327",
    "B306": "CWE-377",
    "B307": "CWE-95",
    "B308": "CWE-79",
    "B310": "CWE-918",
    "B311": "CWE-330",
    "B313": "CWE-611",
    "B314": "CWE-611",
    "B315": "CWE-611",
    "B316": "CWE-611",
    "B317": "CWE-611",
    "B318": "CWE-611",
    "B319": "CWE-611",
    "B320": "CWE-611",
    "B323": "CWE-295",
    "B324": "CWE-327",
    "B325": "CWE-377",
    "B401": "CWE-319",
    "B402": "CWE-319",
    "B403": "CWE-502",
    "B405": "CWE-611",
    "B406": "CWE-611",
    "B407": "CWE-611",
    "B408": "CWE-611",
    "B409": "CWE-611",
    "B410": "CWE-611",
    "B411": "CWE-918",
    "B501": "CWE-295",
    "B502": "CWE-327",
    "B503": "CWE-327",
    "B504": "CWE-327",
    "B505": "CWE-326",
    "B506": "CWE-502",
    "B507": "CWE-295",
    "B602": "CWE-78",
    "B603": "CWE-78",
    "B604": "CWE-78",
    "B605": "CWE-78",
    "B606": "CWE-78",
    "B607": "CWE-426",
    "B608": "CWE-89",
    "B609": "CWE-78",
    "B610": "CWE-79",
    "B611": "CWE-89",
}


def _normalize_agent_confidence(
    value: Any,
) -> Optional[Literal["HIGH", "MEDIUM", "LOW"]]:
    if isinstance(value, (int, float)):
        numeric_value = float(value)
        if numeric_value >= 0.8:
            return "HIGH"
        if numeric_value >= 0.5:
            return "MEDIUM"
        if numeric_value > 0:
            return "LOW"
        return None

    normalized = str(value or "").strip().upper()
    if normalized in {"HIGH", "MEDIUM", "LOW"}:
        return normalized
    return None


def _is_public_project(project: Project | None) -> bool:
    return bool(project and getattr(project, "source_type", None) == "zip")


def _filter_public_projects(projects: List[Project]) -> List[Project]:
    return [project for project in projects if _is_public_project(project)]


def ensure_zip_project_exists(project: Project | None) -> None:
    if not _is_public_project(project):
        raise HTTPException(status_code=404, detail="项目不存在")


def _raise_if_project_hidden(project: Project | None) -> None:
    ensure_zip_project_exists(project)


def build_project_response_load_options(
    *,
    include_metrics: bool,
) -> list[Any]:
    metrics_loader = (
        selectinload(Project.management_metrics)
        if include_metrics
        else noload(Project.management_metrics)
    )
    return [
        selectinload(Project.owner),
        metrics_loader,
    ]


async def load_project_for_response(
    db: AsyncSession,
    project_id: str,
    *,
    include_metrics: bool,
) -> Project | None:
    result = await db.execute(
        select(Project)
        .options(*build_project_response_load_options(include_metrics=include_metrics))
        .where(Project.id == project_id)
    )
    project = result.scalars().first()
    if include_metrics:
        await _hydrate_project_management_metrics(db, project)
    return project


async def _hydrate_project_management_metrics(
    db: AsyncSession,
    project: Project | None,
) -> Project | None:
    if project is None or getattr(project, "management_metrics", None) is not None:
        return project
    if await ProjectMetricsService.has_task_history(db, project.id):
        project.management_metrics = await ProjectMetricsService.recalc_project(
            db,
            project.id,
        )
        return project
    project.management_metrics = await ProjectMetricsService.build_pending_metrics(project.id)
    return project


async def _hydrate_projects_management_metrics(
    db: AsyncSession,
    projects: List[Project],
) -> List[Project]:
    for project in projects:
        await _hydrate_project_management_metrics(db, project)
    return projects


class StaticScanOverviewItem(BaseModel):
    project_id: str
    project_name: str
    last_scan_tool: Literal["opengrep", "gitleaks", "bandit", "phpstan"]
    last_scan_task_id: str
    paired_gitleaks_task_id: Optional[str] = None
    last_scan_at: datetime
    severe_count: int
    hint_count: int
    info_count: int
    total_findings: int


class StaticScanOverviewResponse(BaseModel):
    items: List[StaticScanOverviewItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProjectDescriptionGenerateResponse(BaseModel):
    description: str
    language_info: str
    source: Literal["llm", "static"]


class ProjectInfoResponse(BaseModel):
    id: str
    project_id: str
    language_info: str
    description: str
    status: str
    created_at: datetime


class FileContentResponse(BaseModel):
    """文件内容响应"""
    file_path: str
    content: str  # 对于二进制文件为base64编码
    size: int
    encoding: str
    is_text: bool
    is_cached: bool = False
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


def _build_static_scan_overview_item_from_row(
    row: dict[str, Any],
) -> Optional[StaticScanOverviewItem]:
    opengrep_task_id = row.get("opengrep_task_id")
    opengrep_created_at = row.get("opengrep_created_at")
    latest_gitleaks_created_at = row.get("latest_gitleaks_created_at")
    latest_bandit_created_at = row.get("latest_bandit_created_at")
    latest_phpstan_created_at = row.get("latest_phpstan_created_at")
    if (
        opengrep_created_at is None
        and latest_gitleaks_created_at is None
        and latest_bandit_created_at is None
        and latest_phpstan_created_at is None
    ):
        return None

    project_id = str(row.get("project_id") or "")
    project_name = str(row.get("project_name") or "")
    if not project_id:
        return None

    if opengrep_created_at is not None and opengrep_task_id:
        opengrep_severe_count = int(row.get("opengrep_error_count") or 0)
        opengrep_warning_count = int(row.get("opengrep_warning_count") or 0)
        opengrep_total_findings = int(row.get("opengrep_total_findings") or 0)
        paired_gitleaks_count = int(row.get("paired_gitleaks_total_findings") or 0)
        opengrep_info_count = max(
            opengrep_total_findings - opengrep_severe_count - opengrep_warning_count, 0
        )

        paired_gitleaks_created_at = row.get("paired_gitleaks_created_at")
        if (
            paired_gitleaks_created_at is not None
            and paired_gitleaks_created_at > opengrep_created_at
        ):
            opengrep_bundle_last_scan_at = paired_gitleaks_created_at
        else:
            opengrep_bundle_last_scan_at = opengrep_created_at

        bandit_task_id = str(row.get("latest_bandit_task_id") or "")
        bandit_high_count = int(row.get("latest_bandit_high_count") or 0)
        bandit_medium_count = int(row.get("latest_bandit_medium_count") or 0)
        bandit_low_count = int(row.get("latest_bandit_low_count") or 0)
        phpstan_task_id = str(row.get("latest_phpstan_task_id") or "")
        phpstan_total_findings = int(row.get("latest_phpstan_total_findings") or 0)

        # Bandit 计数映射口径：HIGH -> severe，MEDIUM+LOW -> hint，不计入 info。
        # 仅当 Bandit 是最近来源时，才使用 Bandit 计数，避免跨批次误叠加。
        if (
            latest_bandit_created_at is not None
            and latest_bandit_created_at > opengrep_bundle_last_scan_at
            and bandit_task_id
        ):
            severe_count = bandit_high_count
            hint_count = bandit_medium_count + bandit_low_count
            info_count = 0
            total_findings = severe_count + hint_count
            task_id = bandit_task_id
            last_scan_at = latest_bandit_created_at
            last_scan_tool = "bandit"
            paired_gitleaks_task_id = None
        else:
            severe_count = opengrep_severe_count
            hint_count = opengrep_warning_count + paired_gitleaks_count
            info_count = opengrep_info_count
            total_findings = severe_count + hint_count + info_count
            task_id = str(opengrep_task_id)
            last_scan_at = opengrep_bundle_last_scan_at
            last_scan_tool = "opengrep"
            paired_gitleaks_task_id = str(row.get("paired_gitleaks_task_id") or "") or None

        # PHPStan 计数映射口径：全部归入 hint，不计入 severe/info。
        if (
            latest_phpstan_created_at is not None
            and latest_phpstan_created_at > last_scan_at
            and phpstan_task_id
        ):
            severe_count = 0
            hint_count = phpstan_total_findings
            info_count = 0
            total_findings = hint_count
            task_id = phpstan_task_id
            last_scan_at = latest_phpstan_created_at
            last_scan_tool = "phpstan"
            paired_gitleaks_task_id = None
    else:
        # Bandit 计数映射口径：HIGH -> severe，MEDIUM+LOW -> hint，不计入 info。
        bandit_task_id = str(row.get("latest_bandit_task_id") or "")
        bandit_high_count = int(row.get("latest_bandit_high_count") or 0)
        bandit_medium_count = int(row.get("latest_bandit_medium_count") or 0)
        bandit_low_count = int(row.get("latest_bandit_low_count") or 0)
        phpstan_task_id = str(row.get("latest_phpstan_task_id") or "")
        phpstan_total_findings = int(row.get("latest_phpstan_total_findings") or 0)
        if (
            latest_bandit_created_at is not None
            and (latest_gitleaks_created_at is None or latest_bandit_created_at >= latest_gitleaks_created_at)
            and bandit_task_id
        ):
            severe_count = bandit_high_count
            hint_count = bandit_medium_count + bandit_low_count
            info_count = 0
            total_findings = severe_count + hint_count
            task_id = bandit_task_id
            last_scan_at = latest_bandit_created_at
            last_scan_tool = "bandit"
        else:
            severe_count = 0
            total_findings = int(row.get("latest_gitleaks_total_findings") or 0)
            hint_count = total_findings
            info_count = 0
            task_id = str(row.get("latest_gitleaks_task_id") or "")
            last_scan_at = latest_gitleaks_created_at
            last_scan_tool = "gitleaks"

        # PHPStan 计数映射口径：全部归入 hint，不计入 severe/info。
        if (
            latest_phpstan_created_at is not None
            and (last_scan_at is None or latest_phpstan_created_at > last_scan_at)
            and phpstan_task_id
        ):
            severe_count = 0
            hint_count = phpstan_total_findings
            info_count = 0
            total_findings = hint_count
            task_id = phpstan_task_id
            last_scan_at = latest_phpstan_created_at
            last_scan_tool = "phpstan"
        paired_gitleaks_task_id = None

    if not task_id or last_scan_at is None:
        return None

    return StaticScanOverviewItem(
        project_id=project_id,
        project_name=project_name,
        last_scan_tool=last_scan_tool,
        last_scan_task_id=task_id,
        paired_gitleaks_task_id=paired_gitleaks_task_id,
        last_scan_at=last_scan_at,
        severe_count=severe_count,
        hint_count=hint_count,
        info_count=info_count,
        total_findings=total_findings,
    )


HYBRID_TASK_NAME_MARKER = "[HYBRID]"
INTELLIGENT_TASK_NAME_MARKER = "[INTELLIGENT]"


def _to_non_negative_int(value: Any) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(parsed, 0)


def _resolve_agent_source_mode(name: Optional[str], description: Optional[str]) -> str:
    normalized_name = str(name or "").strip().lower()
    normalized_description = str(description or "").strip().lower()
    normalized_combined = f"{normalized_name} {normalized_description}"
    if (
        HYBRID_TASK_NAME_MARKER.lower() in normalized_combined
        or "混合扫描" in normalized_combined
    ):
        return "hybrid"
    if INTELLIGENT_TASK_NAME_MARKER.lower() in normalized_combined:
        return "intelligent"
    # legacy intelligent_audit tasks created before markers are treated as hybrid.
    return "hybrid"


def _sort_dashboard_items_by_total_and_name(
    items: List[Dict[str, Any]],
    total_key: str,
) -> List[Dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            -int(item.get(total_key, 0) or 0),
            str(item.get("project_name") or ""),
        ),
    )


DASHBOARD_ENGINE_ORDER: tuple[str, ...] = (
    "llm",
    "opengrep",
    "gitleaks",
    "bandit",
    "phpstan",
    "yasa",
)

OPENGREP_RISK_WEIGHTS: Dict[str, int] = {
    "ERROR": 5,
    "WARNING": 3,
    "INFO": 1,
}

SEVERITY_RISK_WEIGHTS: Dict[str, int] = {
    "critical": 8,
    "high": 5,
    "medium": 3,
    "low": 1,
    "info": 1,
}

TERMINAL_FAILURE_STATUSES = {"failed", "interrupted", "cancelled"}
EXCLUDED_CURRENT_RISK_STATUSES = {"false_positive", "resolved"}


def _normalize_status_token(value: Any) -> str:
    return str(value or "").strip().lower()


def _to_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)


def _round_non_negative_int(value: float) -> int:
    if not isinstance(value, (int, float)) or value <= 0:
        return 0
    return max(int(round(value)), 0)


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)
    return None


def _bucket_dashboard_task_status(status: Any) -> str:
    normalized = _normalize_status_token(status)
    if normalized == "completed":
        return "completed"
    if normalized == "failed":
        return "failed"
    if normalized == "interrupted":
        return "interrupted"
    if normalized == "cancelled":
        return "cancelled"
    if normalized == "pending":
        return "pending"
    return "running"


def _is_static_finding_verified(status: Any) -> bool:
    return _normalize_status_token(status) == "verified"


def _is_static_finding_false_positive(status: Any) -> bool:
    return _normalize_status_token(status) == "false_positive"


def _is_static_finding_effective(status: Any) -> bool:
    return _normalize_status_token(status) not in EXCLUDED_CURRENT_RISK_STATUSES


def _is_agent_finding_false_positive(status: Any, verdict: Any) -> bool:
    normalized_status = _normalize_status_token(status)
    normalized_verdict = _normalize_status_token(verdict)
    return normalized_status == "false_positive" or normalized_verdict == "false_positive"


def _is_agent_finding_verified(
    is_verified: Any,
    status: Any,
    verdict: Any,
) -> bool:
    if bool(is_verified):
        return True
    normalized_status = _normalize_status_token(status)
    normalized_verdict = _normalize_status_token(verdict)
    return normalized_status == "verified" or normalized_verdict in {"confirmed", "likely"}


def _is_agent_finding_effective(status: Any, verdict: Any) -> bool:
    normalized_status = _normalize_status_token(status)
    normalized_verdict = _normalize_status_token(verdict)
    if normalized_status in EXCLUDED_CURRENT_RISK_STATUSES:
        return False
    if normalized_verdict == "false_positive":
        return False
    return True


def _risk_multiplier(is_verified: bool) -> float:
    return 1.5 if is_verified else 1.0


def _risk_weight_from_severity(severity: Any) -> int:
    normalized = _normalize_status_token(severity)
    return SEVERITY_RISK_WEIGHTS.get(normalized, 1)


def _risk_weight_for_opengrep(severity: Any) -> int:
    normalized = str(severity or "").strip().upper()
    return OPENGREP_RISK_WEIGHTS.get(normalized, 1)


def _parse_dashboard_language_info(payload: Any) -> Dict[str, Dict[str, int]]:
    parsed = payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError):
            return {}
    if not isinstance(parsed, dict):
        return {}

    languages = parsed.get("languages")
    if not isinstance(languages, dict):
        languages = parsed

    normalized: Dict[str, Dict[str, int]] = {}
    for raw_language, stats in languages.items():
        language = str(raw_language or "").strip() or "unknown"
        if raw_language in {"total", "total_files", "status", "description"}:
            continue
        if isinstance(stats, (int, float)):
            normalized[language] = {
                "loc_number": _to_non_negative_int(stats),
                "files_count": 0,
            }
            continue
        if not isinstance(stats, dict):
            continue
        normalized[language] = {
            "loc_number": _to_non_negative_int(
                stats.get("loc_number", stats.get("code", stats.get("lines")))
            ),
            "files_count": _to_non_negative_int(
                stats.get("files_count", stats.get("file_count", stats.get("files")))
            ),
        }
    return normalized


def _resolve_dashboard_language_from_path(
    file_path: Any,
    dominant_language: str,
) -> str:
    normalized_path = str(file_path or "").strip()
    if normalized_path:
        path = Path(normalized_path)
        lower_name = path.name.lower()
        suffix = path.suffix.lower()
        if lower_name == "dockerfile":
            suffix = ".dockerfile"
        mapped_language = EXTENSION_LANGUAGE_MAP.get(suffix)
        if mapped_language:
            return str(mapped_language).strip() or dominant_language or "unknown"
    return dominant_language or "unknown"


def _dashboard_activity_bucket(day: datetime) -> str:
    normalized = _coerce_datetime(day)
    if normalized is None:
        normalized = datetime.now(timezone.utc)
    return normalized.astimezone(timezone.utc).date().isoformat()


def _update_window_activity(
    activity_map: Dict[str, Dict[str, int]],
    timestamp: Optional[datetime],
    window_start: datetime,
    field: str,
) -> None:
    normalized = _coerce_datetime(timestamp)
    if normalized is None or normalized < window_start:
        return
    bucket = activity_map.setdefault(
        _dashboard_activity_bucket(normalized),
        {
            "completed_scans": 0,
            "agent_findings": 0,
            "opengrep_findings": 0,
            "gitleaks_findings": 0,
            "bandit_findings": 0,
            "phpstan_findings": 0,
            "yasa_findings": 0,
        },
    )
    bucket[field] = _to_non_negative_int(bucket.get(field, 0)) + 1


def _update_project_hotspot_scan_meta(
    hotspot: Dict[str, Any],
    project_id: str,
    project_name_map: Dict[str, str],
    dominant_language_map: Dict[str, str],
    timestamp: Optional[datetime],
) -> None:
    hotspot["project_id"] = project_id
    hotspot["project_name"] = project_name_map.get(project_id, "未知项目")
    hotspot["dominant_language"] = dominant_language_map.get(project_id, "unknown")
    normalized = _coerce_datetime(timestamp)
    if normalized is not None and (
        hotspot.get("last_scan_at") is None or normalized > hotspot["last_scan_at"]
    ):
        hotspot["last_scan_at"] = normalized


def _record_project_hotspot_finding(
    hotspot: Dict[str, Any],
    engine: str,
    effective: bool,
    verified: bool,
    false_positive: bool,
    risk_weight: float,
) -> None:
    hotspot["raw_findings"] = _to_non_negative_int(hotspot.get("raw_findings", 0)) + 1
    if effective:
        hotspot["effective_findings"] = _to_non_negative_int(
            hotspot.get("effective_findings", 0)
        ) + 1
        hotspot["risk_score"] = float(hotspot.get("risk_score", 0.0)) + float(risk_weight)
        engine_counts = hotspot.setdefault("engine_effective_counts", {})
        engine_counts[engine] = _to_non_negative_int(engine_counts.get(engine, 0)) + 1
    if verified:
        hotspot["verified_findings"] = _to_non_negative_int(
            hotspot.get("verified_findings", 0)
        ) + 1
    if false_positive:
        hotspot["false_positive_count"] = _to_non_negative_int(
            hotspot.get("false_positive_count", 0)
        ) + 1
    


class ScanRequest(BaseModel):
    file_paths: Optional[List[str]] = None
    full_scan: bool = True
    exclude_patterns: Optional[List[str]] = None

class ZipFileMetaResponse(BaseModel):
    has_file: bool
    original_filename: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: Optional[str] = None

__all__ = [name for name in globals() if not name.startswith("__")]
