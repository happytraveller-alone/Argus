from typing import Any, Dict, List, Optional, Literal
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
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, case, or_, and_
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, ConfigDict
from datetime import datetime, timezone
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
from app.models.audit import AuditTask, AuditIssue
from app.models.agent_task import AgentTask, AgentFinding
from app.models.opengrep import OpengrepScanTask, OpengrepFinding, OpengrepRule
from app.models.gitleaks import GitleaksScanTask, GitleaksFinding
from app.models.bandit import BanditScanTask, BanditFinding
from app.models.phpstan import PhpstanScanTask, PhpstanFinding
from app.models.user_config import UserConfig
from app.models.project_info import ProjectInfo
import zipfile
from app.services.zip_cache_manager import get_zip_cache_manager
from app.services.scanner import (
    scan_repo_task,
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
from app.services.upload.upload_manager import UploadManager
from app.services.upload.compression_factory import CompressionStrategyFactory
from app.services.upload.language_detection import detect_languages_from_paths
from app.services.upload.project_stats import (
    get_cloc_stats,
    build_static_project_description,
    get_cloc_stats_from_extracted_dir,
    generate_project_description_from_extracted_dir,
)
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


router = APIRouter()


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


class OwnerSchema(BaseModel):
    id: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: Optional[str] = None

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


def _raise_if_project_hidden(project: Project | None) -> None:
    if not _is_public_project(project):
        raise HTTPException(status_code=404, detail="项目不存在")


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
    

@router.post("/", response_model=ProjectResponse)
async def create_project(
    *,
    db: AsyncSession = Depends(get_db),
    project_in: ProjectCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Create new project.
    """
    import json

    source_type = project_in.source_type or "zip"
    if source_type != "zip" or project_in.repository_url:
        raise HTTPException(status_code=400, detail="仅支持 ZIP 项目创建")

    project = Project(
        name=project_in.name,
        source_type=source_type,
        repository_url=None,
        repository_type="other",
        description=project_in.description,
        default_branch=project_in.default_branch or "main",
        programming_languages=json.dumps(project_in.programming_languages or []),
        owner_id=current_user.id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/", response_model=List[ProjectResponse])
async def read_projects(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve projects.
    """
    query = (
        select(Project)
        .options(selectinload(Project.owner))
        .where(Project.source_type == "zip")
    )
    if not include_deleted:
        query = query.where(Project.is_active == True)
    query = query.order_by(Project.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return _filter_public_projects(result.scalars().all())


@router.get("/deleted", response_model=List[ProjectResponse])
async def read_deleted_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve deleted (soft-deleted) projects.
    """
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.owner))
        .where(Project.is_active == False)
        .where(Project.source_type == "zip")
        .order_by(Project.updated_at.desc())
    )
    return _filter_public_projects(result.scalars().all())


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get global statistics.
    """
    interrupted_statuses = ("interrupted", "aborted", "cancelled")

    async def _count(model, where_clause=None) -> int:
        stmt = select(func.count(model.id))
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        result = await db.execute(stmt)
        return int(result.scalar() or 0)

    total_projects = await _count(Project)
    active_projects = await _count(Project, Project.is_active == True)

    # 任务统计（统一从数据库聚合，不再前端拼接）
    audit_total = await _count(AuditTask)
    audit_completed = await _count(AuditTask, func.lower(AuditTask.status) == "completed")
    audit_running = await _count(AuditTask, func.lower(AuditTask.status) == "running")
    audit_failed = await _count(AuditTask, func.lower(AuditTask.status) == "failed")
    audit_interrupted = await _count(
        AuditTask, func.lower(AuditTask.status).in_(interrupted_statuses)
    )

    agent_total = await _count(AgentTask)
    agent_completed = await _count(AgentTask, func.lower(AgentTask.status) == "completed")
    agent_running = await _count(AgentTask, func.lower(AgentTask.status) == "running")
    agent_failed = await _count(AgentTask, func.lower(AgentTask.status) == "failed")
    agent_interrupted = await _count(
        AgentTask, func.lower(AgentTask.status).in_(interrupted_statuses)
    )

    opengrep_total = await _count(OpengrepScanTask)
    opengrep_completed = await _count(
        OpengrepScanTask, func.lower(OpengrepScanTask.status) == "completed"
    )
    opengrep_running = await _count(
        OpengrepScanTask, func.lower(OpengrepScanTask.status) == "running"
    )
    opengrep_failed = await _count(
        OpengrepScanTask, func.lower(OpengrepScanTask.status) == "failed"
    )
    opengrep_interrupted = await _count(
        OpengrepScanTask, func.lower(OpengrepScanTask.status).in_(interrupted_statuses)
    )

    gitleaks_total = await _count(GitleaksScanTask)
    gitleaks_completed = await _count(
        GitleaksScanTask, func.lower(GitleaksScanTask.status) == "completed"
    )
    gitleaks_running = await _count(
        GitleaksScanTask, func.lower(GitleaksScanTask.status) == "running"
    )
    gitleaks_failed = await _count(
        GitleaksScanTask, func.lower(GitleaksScanTask.status) == "failed"
    )
    gitleaks_interrupted = await _count(
        GitleaksScanTask, func.lower(GitleaksScanTask.status).in_(interrupted_statuses)
    )

    bandit_total = await _count(BanditScanTask)
    bandit_completed = await _count(
        BanditScanTask, func.lower(BanditScanTask.status) == "completed"
    )
    bandit_running = await _count(
        BanditScanTask, func.lower(BanditScanTask.status) == "running"
    )
    bandit_failed = await _count(
        BanditScanTask, func.lower(BanditScanTask.status) == "failed"
    )
    bandit_interrupted = await _count(
        BanditScanTask, func.lower(BanditScanTask.status).in_(interrupted_statuses)
    )

    phpstan_total = await _count(PhpstanScanTask)
    phpstan_completed = await _count(
        PhpstanScanTask, func.lower(PhpstanScanTask.status) == "completed"
    )
    phpstan_running = await _count(
        PhpstanScanTask, func.lower(PhpstanScanTask.status) == "running"
    )
    phpstan_failed = await _count(
        PhpstanScanTask, func.lower(PhpstanScanTask.status) == "failed"
    )
    phpstan_interrupted = await _count(
        PhpstanScanTask, func.lower(PhpstanScanTask.status).in_(interrupted_statuses)
    )

    total_tasks = (
        audit_total
        + agent_total
        + opengrep_total
        + gitleaks_total
        + bandit_total
        + phpstan_total
    )
    completed_tasks = (
        audit_completed
        + agent_completed
        + opengrep_completed
        + gitleaks_completed
        + bandit_completed
        + phpstan_completed
    )
    running_tasks = (
        audit_running
        + agent_running
        + opengrep_running
        + gitleaks_running
        + bandit_running
        + phpstan_running
    )
    failed_tasks = (
        audit_failed
        + agent_failed
        + opengrep_failed
        + gitleaks_failed
        + bandit_failed
        + phpstan_failed
    )
    interrupted_tasks = (
        audit_interrupted
        + agent_interrupted
        + opengrep_interrupted
        + gitleaks_interrupted
        + bandit_interrupted
        + phpstan_interrupted
    )

    # 问题统计（统一聚合）
    total_issues = (
        await _count(AuditIssue)
        + await _count(AgentFinding)
        + await _count(OpengrepFinding)
        + await _count(GitleaksFinding)
        + await _count(BanditFinding)
        + await _count(PhpstanFinding)
    )
    resolved_issues = (
        await _count(AuditIssue, func.lower(AuditIssue.status) == "resolved")
        + await _count(
            AgentFinding,
            func.lower(AgentFinding.status).in_(("resolved", "verified", "fixed")),
        )
        + await _count(OpengrepFinding, func.lower(OpengrepFinding.status) == "verified")
        + await _count(
            GitleaksFinding, func.lower(GitleaksFinding.status).in_(("verified", "fixed"))
        )
        + await _count(
            BanditFinding, func.lower(BanditFinding.status).in_(("verified", "fixed"))
        )
        + await _count(
            PhpstanFinding, func.lower(PhpstanFinding.status).in_(("verified", "fixed"))
        )
    )

    return {
        "total_projects": total_projects,
        "active_projects": active_projects,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "interrupted_tasks": interrupted_tasks,
        "running_tasks": running_tasks,
        "failed_tasks": failed_tasks,
        "total_issues": total_issues,
        "resolved_issues": resolved_issues,
    }


@router.get("/dashboard-snapshot", response_model=DashboardSnapshotResponse)
async def get_dashboard_snapshot(
    top_n: int = Query(10, ge=1, le=50, description="Top N projects"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Get aggregated dashboard data with project-card aligned vulnerability metric."""
    projects_result = await db.execute(select(Project.id, Project.name))
    project_rows = projects_result.all()
    project_name_map: Dict[str, str] = {
        str(project_id): str(project_name or "未知项目")
        for project_id, project_name in project_rows
        if project_id
    }

    opengrep_result = await db.execute(
        select(
            OpengrepScanTask.id,
            OpengrepScanTask.project_id,
            OpengrepScanTask.status,
            OpengrepScanTask.scan_duration_ms,
        )
    )
    opengrep_rows = opengrep_result.all()
    opengrep_task_ids = [str(task_id) for task_id, *_ in opengrep_rows if task_id]
    high_confidence_counts = await count_high_confidence_findings_by_task_ids(
        db,
        opengrep_task_ids,
    )

    gitleaks_result = await db.execute(
        select(
            GitleaksScanTask.project_id,
            GitleaksScanTask.status,
            GitleaksScanTask.total_findings,
            GitleaksScanTask.scan_duration_ms,
        )
    )
    gitleaks_rows = gitleaks_result.all()

    bandit_result = await db.execute(
        select(
            BanditScanTask.project_id,
            BanditScanTask.status,
            BanditScanTask.high_count,
            BanditScanTask.medium_count,
            BanditScanTask.low_count,
            BanditScanTask.scan_duration_ms,
        )
    )
    bandit_rows = bandit_result.all()

    phpstan_result = await db.execute(
        select(
            PhpstanScanTask.project_id,
            PhpstanScanTask.status,
            PhpstanScanTask.total_findings,
            PhpstanScanTask.scan_duration_ms,
        )
    )
    phpstan_rows = phpstan_result.all()

    agent_result = await db.execute(
        select(
            AgentTask.project_id,
            AgentTask.status,
            AgentTask.name,
            AgentTask.description,
            AgentTask.verified_count,
            AgentTask.started_at,
            AgentTask.completed_at,
        )
    )
    agent_rows = agent_result.all()

    rule_result = await db.execute(
        select(
            OpengrepRule.name,
            OpengrepRule.language,
            OpengrepRule.severity,
            OpengrepRule.confidence,
            OpengrepRule.is_active,
            OpengrepRule.cwe,
        ).where(OpengrepRule.severity == "ERROR")
    )
    rule_rows = rule_result.all()

    opengrep_finding_result = await db.execute(
        select(OpengrepFinding.scan_task_id, OpengrepFinding.rule).where(
            OpengrepFinding.scan_task_id.in_(opengrep_task_ids),
            or_(
                OpengrepFinding.status.is_(None),
                OpengrepFinding.status != "false_positive",
            ),
        )
    )
    opengrep_finding_rows = opengrep_finding_result.all()

    bandit_finding_result = await db.execute(
        select(
            BanditFinding.test_id,
            BanditFinding.issue_confidence,
            BanditFinding.issue_text,
            BanditFinding.test_name,
        ).where(
            or_(
                BanditFinding.status.is_(None),
                BanditFinding.status != "false_positive",
            )
        )
    )
    bandit_finding_rows = bandit_finding_result.all()

    agent_finding_result = await db.execute(
        select(
            AgentFinding.is_verified,
            AgentFinding.references,
            AgentFinding.vulnerability_type,
            AgentFinding.title,
            AgentFinding.description,
            AgentFinding.code_snippet,
            AgentFinding.ai_confidence,
            AgentFinding.confidence,
        )
    )
    agent_finding_rows = agent_finding_result.all()

    # project aggregates
    scan_runs_map: Dict[str, Dict[str, int]] = {}
    vulns_map: Dict[str, Dict[str, int]] = {}
    rule_confidence_buckets: Dict[str, Dict[str, int]] = {
        "HIGH": {"total_rules": 0, "enabled_rules": 0},
        "MEDIUM": {"total_rules": 0, "enabled_rules": 0},
        "LOW": {"total_rules": 0, "enabled_rules": 0},
        "UNSPECIFIED": {"total_rules": 0, "enabled_rules": 0},
    }
    rule_confidence_by_language: Dict[str, Dict[str, int]] = {}
    cwe_distribution_map: Dict[str, Dict[str, Any]] = {}

    def ensure_scan_runs(project_id: str) -> Dict[str, int]:
        existing = scan_runs_map.get(project_id)
        if existing is not None:
            return existing
        created = {
            "static_runs": 0,
            "intelligent_runs": 0,
            "hybrid_runs": 0,
        }
        scan_runs_map[project_id] = created
        return created

    def ensure_vulns(project_id: str) -> Dict[str, int]:
        existing = vulns_map.get(project_id)
        if existing is not None:
            return existing
        created = {
            "static_vulns": 0,
            "intelligent_vulns": 0,
            "hybrid_vulns": 0,
        }
        vulns_map[project_id] = created
        return created

    opengrep_duration_ms = 0
    for task_id, project_id, status, scan_duration_ms in opengrep_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        project_vulns = ensure_vulns(normalized_project_id)
        project_vulns["static_vulns"] += _to_non_negative_int(
            high_confidence_counts.get(str(task_id), 0)
        )
        if str(status or "").strip().lower() == "completed":
            project_scan_runs = ensure_scan_runs(normalized_project_id)
            project_scan_runs["static_runs"] += 1
        opengrep_duration_ms += _to_non_negative_int(scan_duration_ms)

    gitleaks_duration_ms = 0
    for project_id, status, total_findings, scan_duration_ms in gitleaks_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        # gitleaks 在 dashboard 中计入 static_vulns（project-card aligned）
        project_vulns = ensure_vulns(normalized_project_id)
        project_vulns["static_vulns"] += _to_non_negative_int(total_findings)
        if str(status or "").strip().lower() == "completed":
            project_scan_runs = ensure_scan_runs(normalized_project_id)
            project_scan_runs["static_runs"] += 1
        gitleaks_duration_ms += _to_non_negative_int(scan_duration_ms)

    bandit_duration_ms = 0
    for (
        project_id,
        status,
        high_count,
        medium_count,
        low_count,
        scan_duration_ms,
    ) in bandit_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        # Bandit 计数映射口径：HIGH + MEDIUM + LOW 全部计入 static_vulns。
        project_vulns = ensure_vulns(normalized_project_id)
        project_vulns["static_vulns"] += (
            _to_non_negative_int(high_count)
            + _to_non_negative_int(medium_count)
            + _to_non_negative_int(low_count)
        )
        if str(status or "").strip().lower() == "completed":
            project_scan_runs = ensure_scan_runs(normalized_project_id)
            project_scan_runs["static_runs"] += 1
        bandit_duration_ms += _to_non_negative_int(scan_duration_ms)

    phpstan_duration_ms = 0
    for project_id, status, total_findings, scan_duration_ms in phpstan_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        # PHPStan 计数映射口径：全部归入 static_vulns。
        project_vulns = ensure_vulns(normalized_project_id)
        project_vulns["static_vulns"] += _to_non_negative_int(total_findings)
        if str(status or "").strip().lower() == "completed":
            project_scan_runs = ensure_scan_runs(normalized_project_id)
            project_scan_runs["static_runs"] += 1
        phpstan_duration_ms += _to_non_negative_int(scan_duration_ms)

    agent_duration_ms = 0
    for (
        project_id,
        status,
        name,
        description,
        verified_count,
        started_at,
        completed_at,
    ) in agent_rows:
        if not project_id:
            continue
        normalized_project_id = str(project_id)
        source_mode = _resolve_agent_source_mode(name, description)

        # vulns: project-card aligned metric (not filtered by completed)
        verified = _to_non_negative_int(verified_count)
        project_vulns = ensure_vulns(normalized_project_id)
        if source_mode == "intelligent":
            project_vulns["intelligent_vulns"] += verified
        else:
            project_vulns["hybrid_vulns"] += verified

        # scan runs: completed only
        if str(status or "").strip().lower() == "completed":
            project_scan_runs = ensure_scan_runs(normalized_project_id)
            if source_mode == "intelligent":
                project_scan_runs["intelligent_runs"] += 1
            else:
                project_scan_runs["hybrid_runs"] += 1

        if started_at is not None and completed_at is not None:
            agent_duration_ms += _to_non_negative_int(
                (completed_at - started_at).total_seconds() * 1000
            )

    severe_rule_rows: List[tuple[Any, Any, Any, Any, Any, Any]] = [
        row for row in rule_rows if str(row[2] or "").strip().upper() == "ERROR"
    ]
    rule_confidence_map = build_rule_confidence_map(
        [(row[0], row[3]) for row in severe_rule_rows]
    )
    rule_cwe_map: Dict[str, List[str]] = {}
    for rule_name, language, _, confidence, is_active, cwe_list in severe_rule_rows:
        bucket_key = _normalize_dashboard_rule_confidence(confidence)
        rule_confidence_buckets[bucket_key]["total_rules"] += 1
        if bool(is_active):
            rule_confidence_buckets[bucket_key]["enabled_rules"] += 1

        normalized_language = str(language or "").strip() or "unknown"
        language_bucket = rule_confidence_by_language.setdefault(
            normalized_language,
            {
                "high_count": 0,
                "medium_count": 0,
            },
        )
        if bucket_key == "HIGH":
            language_bucket["high_count"] += 1
        elif bucket_key == "MEDIUM":
            language_bucket["medium_count"] += 1

        normalized_cwe_values: List[str] = []
        for raw_cwe in cwe_list if isinstance(cwe_list, list) else []:
            normalized_cwe = normalize_cwe_id(raw_cwe)
            if normalized_cwe and normalized_cwe not in normalized_cwe_values:
                normalized_cwe_values.append(normalized_cwe)

        for lookup_key in extract_rule_lookup_keys(rule_name):
            if lookup_key not in rule_cwe_map:
                rule_cwe_map[lookup_key] = normalized_cwe_values

    for scan_task_id, rule_data in opengrep_finding_rows:
        resolved_confidence = extract_finding_payload_confidence(rule_data)
        check_id = None
        if isinstance(rule_data, dict):
            check_id = rule_data.get("check_id") or rule_data.get("id")
        if not resolved_confidence:
            for lookup_key in extract_rule_lookup_keys(check_id):
                mapped_confidence = rule_confidence_map.get(lookup_key)
                if mapped_confidence:
                    resolved_confidence = mapped_confidence
                    break
        if resolved_confidence not in {"HIGH", "MEDIUM"}:
            continue

        normalized_cwe_values = _extract_cwe_candidates_from_rule_payload(rule_data)
        if not normalized_cwe_values:
            for lookup_key in extract_rule_lookup_keys(check_id):
                fallback_cwe_values = rule_cwe_map.get(lookup_key) or []
                if fallback_cwe_values:
                    normalized_cwe_values = fallback_cwe_values
                    break
        if not normalized_cwe_values:
            continue

        for cwe_id in normalized_cwe_values:
            bucket = cwe_distribution_map.setdefault(
                cwe_id,
                {
                    "cwe_id": cwe_id,
                    "cwe_name": cwe_id,
                    "total_findings": 0,
                    "opengrep_findings": 0,
                    "agent_findings": 0,
                    "bandit_findings": 0,
                },
            )
            bucket["total_findings"] += 1
            bucket["opengrep_findings"] += 1

    for test_id, issue_confidence, issue_text, test_name in bandit_finding_rows:
        normalized_confidence = normalize_opengrep_confidence(issue_confidence)
        if normalized_confidence not in {"HIGH", "MEDIUM"}:
            continue
        cwe_id = _BANDIT_TEST_ID_TO_CWE.get(str(test_id or "").strip().upper())
        if not cwe_id:
            continue
        cwe_name = cwe_id
        bucket = cwe_distribution_map.setdefault(
            cwe_id,
            {
                "cwe_id": cwe_id,
                "cwe_name": cwe_name,
                "total_findings": 0,
                "opengrep_findings": 0,
                "agent_findings": 0,
                "bandit_findings": 0,
            },
        )
        bucket["total_findings"] += 1
        bucket["bandit_findings"] += 1

    for (
        is_verified,
        references,
        vulnerability_type,
        title,
        description,
        code_snippet,
        ai_confidence,
        confidence,
    ) in agent_finding_rows:
        if not is_verified:
            continue
        normalized_confidence = _normalize_agent_confidence(
            ai_confidence if ai_confidence is not None else confidence
        )
        if normalized_confidence not in {"HIGH", "MEDIUM"}:
            continue
        cwe_id = normalize_cwe_id(references)
        if not cwe_id:
            continue
        profile = resolve_vulnerability_profile(
            vulnerability_type,
            title=title,
            description=description,
            code_snippet=code_snippet,
        )
        cwe_name = str(profile.get("name") or cwe_id).strip() or cwe_id
        bucket = cwe_distribution_map.setdefault(
            cwe_id,
            {
                "cwe_id": cwe_id,
                "cwe_name": cwe_name,
                "total_findings": 0,
                "opengrep_findings": 0,
                "agent_findings": 0,
                "bandit_findings": 0,
            },
        )
        if bucket.get("cwe_name") == bucket.get("cwe_id") and cwe_name != cwe_id:
            bucket["cwe_name"] = cwe_name
        bucket["total_findings"] += 1
        bucket["agent_findings"] += 1

    scan_runs_items: List[Dict[str, Any]] = []
    for project_id, item in scan_runs_map.items():
        total_runs = (
            _to_non_negative_int(item.get("static_runs", 0))
            + _to_non_negative_int(item.get("intelligent_runs", 0))
            + _to_non_negative_int(item.get("hybrid_runs", 0))
        )
        if total_runs <= 0:
            continue
        scan_runs_items.append(
            {
                "project_id": project_id,
                "project_name": project_name_map.get(project_id, "未知项目"),
                "static_runs": _to_non_negative_int(item.get("static_runs", 0)),
                "intelligent_runs": _to_non_negative_int(
                    item.get("intelligent_runs", 0)
                ),
                "hybrid_runs": _to_non_negative_int(item.get("hybrid_runs", 0)),
                "total_runs": total_runs,
            }
        )

    vulns_items: List[Dict[str, Any]] = []
    for project_id, item in vulns_map.items():
        total_vulns = (
            _to_non_negative_int(item.get("static_vulns", 0))
            + _to_non_negative_int(item.get("intelligent_vulns", 0))
            + _to_non_negative_int(item.get("hybrid_vulns", 0))
        )
        if total_vulns <= 0:
            continue
        vulns_items.append(
            {
                "project_id": project_id,
                "project_name": project_name_map.get(project_id, "未知项目"),
                "static_vulns": _to_non_negative_int(item.get("static_vulns", 0)),
                "intelligent_vulns": _to_non_negative_int(
                    item.get("intelligent_vulns", 0)
                ),
                "hybrid_vulns": _to_non_negative_int(item.get("hybrid_vulns", 0)),
                "total_vulns": total_vulns,
            }
        )

    sorted_scan_runs = _sort_dashboard_items_by_total_and_name(
        scan_runs_items,
        total_key="total_runs",
    )[:top_n]
    sorted_vulns = _sort_dashboard_items_by_total_and_name(
        vulns_items,
        total_key="total_vulns",
    )[:top_n]

    total_scan_duration_ms = max(
        opengrep_duration_ms
        + gitleaks_duration_ms
        + bandit_duration_ms
        + phpstan_duration_ms
        + agent_duration_ms,
        0,
    )

    sorted_cwe_distribution = sorted(
        cwe_distribution_map.values(),
        key=lambda item: (
            -_to_non_negative_int(item.get("total_findings", 0)),
            str(item.get("cwe_id") or ""),
        ),
    )[:12]
    sorted_rule_confidence_by_language = sorted(
        (
            {
                "language": language,
                "high_count": _to_non_negative_int(item.get("high_count", 0)),
                "medium_count": _to_non_negative_int(item.get("medium_count", 0)),
            }
            for language, item in rule_confidence_by_language.items()
            if _to_non_negative_int(item.get("high_count", 0))
            + _to_non_negative_int(item.get("medium_count", 0))
            > 0
        ),
        key=lambda item: (
            -(
                _to_non_negative_int(item.get("high_count", 0))
                + _to_non_negative_int(item.get("medium_count", 0))
            ),
            str(item.get("language") or ""),
        ),
    )

    return DashboardSnapshotResponse(
        generated_at=datetime.now(timezone.utc),
        total_scan_duration_ms=total_scan_duration_ms,
        scan_runs=[
            DashboardScanRunsItem(**item)
            for item in sorted_scan_runs
        ],
        vulns=[
            DashboardVulnsItem(**item)
            for item in sorted_vulns
        ],
        rule_confidence=[
            DashboardRuleConfidenceItem(
                confidence=confidence,
                total_rules=_to_non_negative_int(
                    rule_confidence_buckets[confidence]["total_rules"]
                ),
                enabled_rules=_to_non_negative_int(
                    rule_confidence_buckets[confidence]["enabled_rules"]
                ),
            )
            for confidence in ("HIGH", "MEDIUM", "LOW", "UNSPECIFIED")
        ],
        rule_confidence_by_language=[
            DashboardRuleConfidenceByLanguageItem(**item)
            for item in sorted_rule_confidence_by_language
        ],
        cwe_distribution=[
            DashboardCweDistributionItem(**item)
            for item in sorted_cwe_distribution
        ],
    )


@router.get("/static-scan-overview", response_model=StaticScanOverviewResponse)
async def get_static_scan_overview(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(6, ge=1, le=50, description="每页数量"),
    keyword: Optional[str] = Query(
        None,
        description="按项目名称模糊搜索（大小写不敏感）",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取项目静态扫描概览（分页）。
    仅返回至少存在一次成功静态扫描（Opengrep/Gitleaks/Bandit/PHPStan）的项目。
    """
    opengrep_ranked_subquery = (
        select(
            OpengrepScanTask.project_id.label("project_id"),
            OpengrepScanTask.id.label("task_id"),
            OpengrepScanTask.created_at.label("created_at"),
            OpengrepScanTask.total_findings.label("total_findings"),
            OpengrepScanTask.error_count.label("error_count"),
            OpengrepScanTask.warning_count.label("warning_count"),
            func.row_number()
            .over(
                partition_by=OpengrepScanTask.project_id,
                order_by=OpengrepScanTask.created_at.desc(),
            )
            .label("rn"),
        )
        .where(func.lower(OpengrepScanTask.status) == "completed")
        .subquery()
    )
    latest_opengrep_subquery = (
        select(
            opengrep_ranked_subquery.c.project_id,
            opengrep_ranked_subquery.c.task_id,
            opengrep_ranked_subquery.c.created_at,
            opengrep_ranked_subquery.c.total_findings,
            opengrep_ranked_subquery.c.error_count,
            opengrep_ranked_subquery.c.warning_count,
        )
        .where(opengrep_ranked_subquery.c.rn == 1)
        .subquery()
    )

    gitleaks_ranked_subquery = (
        select(
            GitleaksScanTask.project_id.label("project_id"),
            GitleaksScanTask.id.label("task_id"),
            GitleaksScanTask.created_at.label("created_at"),
            GitleaksScanTask.total_findings.label("total_findings"),
            func.row_number()
            .over(
                partition_by=GitleaksScanTask.project_id,
                order_by=GitleaksScanTask.created_at.desc(),
            )
            .label("rn"),
        )
        .where(func.lower(GitleaksScanTask.status) == "completed")
        .subquery()
    )
    latest_gitleaks_subquery = (
        select(
            gitleaks_ranked_subquery.c.project_id,
            gitleaks_ranked_subquery.c.task_id,
            gitleaks_ranked_subquery.c.created_at,
            gitleaks_ranked_subquery.c.total_findings,
        )
        .where(gitleaks_ranked_subquery.c.rn == 1)
        .subquery()
    )

    bandit_ranked_subquery = (
        select(
            BanditScanTask.project_id.label("project_id"),
            BanditScanTask.id.label("task_id"),
            BanditScanTask.created_at.label("created_at"),
            BanditScanTask.total_findings.label("total_findings"),
            BanditScanTask.high_count.label("high_count"),
            BanditScanTask.medium_count.label("medium_count"),
            BanditScanTask.low_count.label("low_count"),
            func.row_number()
            .over(
                partition_by=BanditScanTask.project_id,
                order_by=BanditScanTask.created_at.desc(),
            )
            .label("rn"),
        )
        .where(func.lower(BanditScanTask.status) == "completed")
        .subquery()
    )
    latest_bandit_subquery = (
        select(
            bandit_ranked_subquery.c.project_id,
            bandit_ranked_subquery.c.task_id,
            bandit_ranked_subquery.c.created_at,
            bandit_ranked_subquery.c.total_findings,
            bandit_ranked_subquery.c.high_count,
            bandit_ranked_subquery.c.medium_count,
            bandit_ranked_subquery.c.low_count,
        )
        .where(bandit_ranked_subquery.c.rn == 1)
        .subquery()
    )

    phpstan_ranked_subquery = (
        select(
            PhpstanScanTask.project_id.label("project_id"),
            PhpstanScanTask.id.label("task_id"),
            PhpstanScanTask.created_at.label("created_at"),
            PhpstanScanTask.total_findings.label("total_findings"),
            func.row_number()
            .over(
                partition_by=PhpstanScanTask.project_id,
                order_by=PhpstanScanTask.created_at.desc(),
            )
            .label("rn"),
        )
        .where(func.lower(PhpstanScanTask.status) == "completed")
        .subquery()
    )
    latest_phpstan_subquery = (
        select(
            phpstan_ranked_subquery.c.project_id,
            phpstan_ranked_subquery.c.task_id,
            phpstan_ranked_subquery.c.created_at,
            phpstan_ranked_subquery.c.total_findings,
        )
        .where(phpstan_ranked_subquery.c.rn == 1)
        .subquery()
    )

    # 以 opengrep 最新 completed 为主锚，配对同批（60 秒窗口）gitleaks completed 任务
    paired_gitleaks_ranked_subquery = (
        select(
            latest_opengrep_subquery.c.project_id.label("project_id"),
            GitleaksScanTask.id.label("task_id"),
            GitleaksScanTask.created_at.label("created_at"),
            GitleaksScanTask.total_findings.label("total_findings"),
            func.row_number()
            .over(
                partition_by=latest_opengrep_subquery.c.project_id,
                order_by=(
                    func.abs(
                        func.extract(
                            "epoch",
                            GitleaksScanTask.created_at
                            - latest_opengrep_subquery.c.created_at,
                        )
                    ).asc(),
                    GitleaksScanTask.created_at.desc(),
                ),
            )
            .label("rn"),
        )
        .select_from(latest_opengrep_subquery)
        .join(
            GitleaksScanTask,
            and_(
                GitleaksScanTask.project_id == latest_opengrep_subquery.c.project_id,
                func.lower(GitleaksScanTask.status) == "completed",
                func.abs(
                    func.extract(
                        "epoch",
                        GitleaksScanTask.created_at
                        - latest_opengrep_subquery.c.created_at,
                    )
                )
                <= 60,
            ),
        )
        .subquery()
    )

    paired_gitleaks_subquery = (
        select(
            paired_gitleaks_ranked_subquery.c.project_id,
            paired_gitleaks_ranked_subquery.c.task_id,
            paired_gitleaks_ranked_subquery.c.created_at,
            paired_gitleaks_ranked_subquery.c.total_findings,
        )
        .where(paired_gitleaks_ranked_subquery.c.rn == 1)
        .subquery()
    )

    last_scan_without_bandit_expr = case(
        (
            latest_opengrep_subquery.c.created_at.is_not(None),
            case(
                (
                    and_(
                        paired_gitleaks_subquery.c.created_at.is_not(None),
                        paired_gitleaks_subquery.c.created_at
                        > latest_opengrep_subquery.c.created_at,
                    ),
                    paired_gitleaks_subquery.c.created_at,
                ),
                else_=latest_opengrep_subquery.c.created_at,
            ),
        ),
        else_=latest_gitleaks_subquery.c.created_at,
    )
    last_scan_with_bandit_expr = case(
        (
            and_(
                latest_bandit_subquery.c.created_at.is_not(None),
                or_(
                    last_scan_without_bandit_expr.is_(None),
                    latest_bandit_subquery.c.created_at > last_scan_without_bandit_expr,
                ),
            ),
            latest_bandit_subquery.c.created_at,
        ),
        else_=last_scan_without_bandit_expr,
    )
    last_scan_at_expr = case(
        (
            and_(
                latest_phpstan_subquery.c.created_at.is_not(None),
                or_(
                    last_scan_with_bandit_expr.is_(None),
                    latest_phpstan_subquery.c.created_at > last_scan_with_bandit_expr,
                ),
            ),
            latest_phpstan_subquery.c.created_at,
        ),
        else_=last_scan_with_bandit_expr,
    )

    base_stmt = (
        select(
            Project.id.label("project_id"),
            Project.name.label("project_name"),
            latest_opengrep_subquery.c.task_id.label("opengrep_task_id"),
            latest_opengrep_subquery.c.created_at.label("opengrep_created_at"),
            latest_opengrep_subquery.c.total_findings.label("opengrep_total_findings"),
            latest_opengrep_subquery.c.error_count.label("opengrep_error_count"),
            latest_opengrep_subquery.c.warning_count.label("opengrep_warning_count"),
            paired_gitleaks_subquery.c.task_id.label("paired_gitleaks_task_id"),
            paired_gitleaks_subquery.c.created_at.label("paired_gitleaks_created_at"),
            paired_gitleaks_subquery.c.total_findings.label(
                "paired_gitleaks_total_findings"
            ),
            latest_gitleaks_subquery.c.task_id.label("latest_gitleaks_task_id"),
            latest_gitleaks_subquery.c.created_at.label("latest_gitleaks_created_at"),
            latest_gitleaks_subquery.c.total_findings.label(
                "latest_gitleaks_total_findings"
            ),
            latest_bandit_subquery.c.task_id.label("latest_bandit_task_id"),
            latest_bandit_subquery.c.created_at.label("latest_bandit_created_at"),
            latest_bandit_subquery.c.total_findings.label("latest_bandit_total_findings"),
            latest_bandit_subquery.c.high_count.label("latest_bandit_high_count"),
            latest_bandit_subquery.c.medium_count.label("latest_bandit_medium_count"),
            latest_bandit_subquery.c.low_count.label("latest_bandit_low_count"),
            latest_phpstan_subquery.c.task_id.label("latest_phpstan_task_id"),
            latest_phpstan_subquery.c.created_at.label("latest_phpstan_created_at"),
            latest_phpstan_subquery.c.total_findings.label("latest_phpstan_total_findings"),
            last_scan_at_expr.label("last_scan_at"),
        )
        .select_from(Project)
        .outerjoin(
            latest_opengrep_subquery,
            latest_opengrep_subquery.c.project_id == Project.id,
        )
        .outerjoin(
            latest_gitleaks_subquery,
            latest_gitleaks_subquery.c.project_id == Project.id,
        )
        .outerjoin(
            paired_gitleaks_subquery,
            paired_gitleaks_subquery.c.project_id == Project.id,
        )
        .outerjoin(
            latest_bandit_subquery,
            latest_bandit_subquery.c.project_id == Project.id,
        )
        .outerjoin(
            latest_phpstan_subquery,
            latest_phpstan_subquery.c.project_id == Project.id,
        )
        .where(
            or_(
                latest_opengrep_subquery.c.project_id.is_not(None),
                latest_gitleaks_subquery.c.project_id.is_not(None),
                latest_bandit_subquery.c.project_id.is_not(None),
                latest_phpstan_subquery.c.project_id.is_not(None),
            )
        )
    )
    if keyword and keyword.strip():
        base_stmt = base_stmt.where(
            func.lower(Project.name).like(f"%{keyword.strip().lower()}%")
        )

    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = int(count_result.scalar() or 0)
    total_pages = max(1, (total + page_size - 1) // page_size)

    paged_stmt = (
        base_stmt.order_by(last_scan_at_expr.desc(), Project.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows_result = await db.execute(paged_stmt)
    rows = rows_result.mappings().all()

    items: List[StaticScanOverviewItem] = []
    for row in rows:
        item = _build_static_scan_overview_item_from_row(dict(row))
        if item is not None:
            items.append(item)

    return StaticScanOverviewResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "/description/generate",
    response_model=ProjectDescriptionGenerateResponse,
)
async def generate_project_description_preview(
    file: UploadFile = File(...),
    project_name: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    根据上传压缩包生成项目描述（不创建项目，不写数据库）。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    supported_formats = CompressionStrategyFactory.get_supported_formats()
    file_name_lower = file.filename.lower()
    file_ext = Path(file.filename).suffix.lower()
    if file_name_lower.endswith((".tar.gz", ".tgz", ".tar.gzip")):
        file_ext = ".tar.gz"
    elif file_name_lower.endswith((".tar.bz2", ".tbz", ".tbz2")):
        file_ext = ".tar.bz2"

    if file_ext not in supported_formats:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(sorted(supported_formats))}",
        )

    with tempfile.TemporaryDirectory(prefix="deepaudit_", suffix="_desc_generate") as temp_dir:
        try:
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

            description, language_info, source = await _resolve_project_description_bundle(
                extracted_dir=temp_extract_dir,
                extracted_files=extracted_files,
                project_name=project_name,
                db=db,
                user_id=current_user.id,
            )

            return ProjectDescriptionGenerateResponse(
                description=description,
                language_info=language_info,
                source=source,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"生成项目描述失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"生成项目描述失败: {str(e)}")


@router.get("/{id}", response_model=ProjectResponse)
async def read_project(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get project by ID.
    """
    result = await db.execute(
        select(Project).options(selectinload(Project.owner)).where(Project.id == id)
    )
    project = result.scalars().first()
    _raise_if_project_hidden(project)

    # 检查权限：只有项目所有者可以查看

    return project


@router.get("/info/{id}", response_model=ProjectInfoResponse)
async def get_project_info(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取项目信息（语言统计）。
    """
    # 1. 获取项目基本信息
    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalars().first()
    _raise_if_project_hidden(project)

    # 2. 检查权限

    empty_language_info = '{"total": 0, "total_files": 0, "languages": {}}'

    # 3. 获取/创建 ProjectInfo（纯静态统计）
    existing_info_result = await db.execute(
        select(ProjectInfo).where(ProjectInfo.project_id == id)
    )
    existing_info = existing_info_result.scalars().first()

    if existing_info and existing_info.status == "completed" and existing_info.language_info:
        existing_info.description = existing_info.description or ""
        return existing_info

    if existing_info and existing_info.status == "pending":
        existing_info.language_info = existing_info.language_info or empty_language_info
        existing_info.description = existing_info.description or ""
        return existing_info

    if not existing_info:
        # 创建新的 ProjectInfo 记录并持久化为 pending 状态
        project_info = ProjectInfo(
            project_id=id,
            status="pending",
            created_at=datetime.now(timezone.utc),
            language_info=empty_language_info,
        )
        db.add(project_info)
        await db.commit()
        await db.refresh(project_info)
    else:
        project_info = existing_info

    try:
        project_info.status = "pending"
        db.add(project_info)
        await db.commit()
        await db.refresh(project_info)

        # 生成语言统计（纯静态）
        cloc_result = await get_cloc_stats(project_info)
        project_info.language_info = cloc_result or empty_language_info

        # 兼容字段：不在该接口生成描述，仅保证响应字段非空
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
        # 标记为 failed 并持久化
        try:
            project_info.status = "failed"
            db.add(project_info)
            await db.commit()
        except Exception:
            logger.exception("保存失败状态时出错")
        raise HTTPException(status_code=500, detail=f"获取项目信息失败: {str(e)}")


@router.put("/{id}", response_model=ProjectResponse)
async def update_project(
    id: str,
    *,
    db: AsyncSession = Depends(get_db),
    project_in: ProjectUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Update project.
    """
    import json

    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalars().first()
    _raise_if_project_hidden(project)

    # 检查权限：只有项目所有者可以更新

    update_data = project_in.model_dump(exclude_unset=True)
    if update_data.get("source_type") not in (None, "zip"):
        raise HTTPException(status_code=400, detail="仅支持 ZIP 项目")
    if update_data.get("repository_url"):
        raise HTTPException(status_code=400, detail="仅支持 ZIP 项目")
    if "source_type" in update_data:
        update_data["source_type"] = "zip"
    if "repository_url" in update_data:
        update_data["repository_url"] = None
    if "repository_type" in update_data:
        update_data["repository_type"] = "other"
    if "programming_languages" in update_data and update_data["programming_languages"] is not None:
        update_data["programming_languages"] = json.dumps(update_data["programming_languages"])

    for field, value in update_data.items():
        setattr(project, field, value)

    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{id}")
async def delete_project(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Soft delete project.
    """
    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalars().first()
    _raise_if_project_hidden(project)

    # 检查权限：只有项目所有者可以删除

    project.is_active = False
    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "项目已删除"}


@router.post("/{id}/restore")
async def restore_project(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Restore soft-deleted project.
    """
    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalars().first()
    _raise_if_project_hidden(project)

    # 检查权限：只有项目所有者可以恢复

    project.is_active = True
    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "项目已恢复"}


@router.delete("/{id}/permanent")
async def permanently_delete_project(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Permanently delete project.
    """
    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalars().first()
    _raise_if_project_hidden(project)

    # 检查权限：只有项目所有者可以永久删除

    # 如果是ZIP类型项目，删除关联的ZIP文件和元数据
    if project.source_type == "zip":
        try:
            await delete_project_zip(id)
            print(f"[Project] 已删除项目 {id} 的ZIP文件")
        except Exception as e:
            print(f"[Warning] 删除ZIP文件失败: {e}")

    await db.delete(project)
    await db.commit()
    return {"message": "项目已永久删除"}


@router.get("/{id}/files")
async def get_project_files(
    id: str,
    exclude_patterns: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get list of files in the project.
    可选参数:
    - exclude_patterns: JSON 格式的排除模式数组，如 ["node_modules/**", "*.log"]
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # Check permissions

    # 解析排除模式
    parsed_exclude_patterns = []
    if exclude_patterns:
        try:
            parsed_exclude_patterns = json.loads(exclude_patterns)
        except json.JSONDecodeError:
            pass

    files = []

    if project.source_type == "zip":
        # Handle ZIP project
        zip_path = await load_project_zip(id)
        print(f"📦 ZIP项目 {id} 文件路径: {zip_path}")
        if not zip_path or not os.path.exists(zip_path):
            print(f"⚠️ ZIP文件不存在: {zip_path}")
            return []

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                for file_info in zip_ref.infolist():
                    if not file_info.is_dir():
                        name = file_info.filename
                        # 使用统一的排除逻辑，支持用户自定义排除模式
                        if should_exclude(name, parsed_exclude_patterns):
                            continue
                        # 只显示支持的代码文件
                        if not is_text_file(name):
                            continue
                        files.append({"path": name, "size": file_info.file_size})
        except Exception as e:
            print(f"Error reading zip file: {e}")
            raise HTTPException(status_code=500, detail="无法读取项目文件")

    return files


@router.get("/{id}/files-tree", response_model=FileTreeResponse)
async def get_project_files_tree(
    id: str,
    exclude_patterns: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取项目文件树结构（嵌套目录树）
    
    支持功能：
    - 完整的嵌套树结构显示
    - 按类型排序（目录优先）
    - 支持排除模式过滤
    - ZIP和仓库项目都支持
    
    参数:
    - id: 项目ID
    - exclude_patterns: JSON 格式的排除模式数组
    
    返回:
    - root: 文件树根节点，包含嵌套的children
    
    树节点字段:
    - name: 文件/目录名称
    - path: 相对路径
    - type: "file" 或 "directory"
    - size: 文件大小（仅文件有值）
    - children: 子节点列表（仅目录有值）
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # Check permissions

    # 解析排除模式
    parsed_exclude_patterns = []
    if exclude_patterns:
        try:
            parsed_exclude_patterns = json.loads(exclude_patterns)
        except json.JSONDecodeError:
            pass

    if project.source_type == "zip":
        # 处理ZIP项目 - 直接从ZIP构建树
        zip_path = await load_project_zip(id)
        if not zip_path or not os.path.exists(zip_path):
            raise HTTPException(status_code=404, detail="项目文件不存在")

        try:
            loop = asyncio.get_event_loop()
            root_node = await loop.run_in_executor(
                None,
                _build_file_tree_from_zip,
                zip_path
            )
            return FileTreeResponse(root=root_node)
        except Exception as e:
            logger.error(f"构建ZIP文件树失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"无法构建文件树: {str(e)}")

    else:
        raise HTTPException(status_code=400, detail="仅支持ZIP类型项目")


@router.get("/{id}/files/{file_path:path}", response_model=Optional[FileContentResponse])
async def get_project_file_content(
    id: str,
    file_path: str,
    encoding: str = Query("utf-8", description="文件编码，默认为 utf-8"),
    use_cache: bool = Query(True, description="是否使用缓存"),
    stream: bool = Query(False, description="大文件是否流式传输"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    异步获取 ZIP 项目中单个文件的完整内容
    
    支持功能：
    - 异步读取，避免阻塞事件循环
    - 内存缓存，加速重复访问
    - 大文件流式传输（>1MB）
    - 二进制文件智能检测
    - 多种编码支持
    
    参数:
    - id: 项目ID
    - file_path: ZIP内的文件相对路径（如 src/main.py）
    - encoding: 文本编码方式，默认 utf-8
    - use_cache: 是否使用缓存，默认True
    - stream: 强制使用流式传输（>1MB自动启用）
    
    返回:
    - file_path: 文件路径
    - content: 文件内容（字符串）
    - size: 文件字节大小
    - encoding: 使用的编码方式
    - is_text: 是否为文本文件
    - is_cached: 是否从缓存读取
    - created_at: 文件创建时间
    
    错误:
    - 404: 项目不存在或文件不存在
    - 400: 项目不是ZIP类型，或文件路径无效
    - 413: 文件过大（>50MB）
    """
    # 1. 验证项目存在
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)
    
    # 2. 检查是否为ZIP项目
    if project.source_type != "zip":
        raise HTTPException(status_code=400, detail="仅支持ZIP类型项目")
    
    # 3. 验证文件路径
    validated_path = _validate_zip_file_path(file_path)
    
    # 4. 获取ZIP文件路径和哈希
    zip_path = await load_project_zip(id)
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="项目文件不存在")

    loop = asyncio.get_event_loop()
    known_relative_paths = await loop.run_in_executor(None, collect_zip_relative_paths, zip_path)
    resolved_zip_path = resolve_zip_member_path(validated_path, known_relative_paths)
    if not resolved_zip_path:
        raise HTTPException(status_code=404, detail=f"文件不存在: {validated_path}")
    
    zip_hash = _calculate_zip_file_hash(zip_path)
    
    # 5. 获取缓存管理器
    cache_manager = get_zip_cache_manager()
    
    try:
        # 6. 尝试从缓存读取（仅用于文本文件）
        cached_entry = None
        is_cached = False
        
        if use_cache:
            cached_entry = await cache_manager.get(id, resolved_zip_path, zip_hash)
            if cached_entry is not None and cached_entry.is_text:
                logger.info(f"从缓存读取文件: {resolved_zip_path}")
                is_cached = True
                return FileContentResponse(
                    file_path=resolved_zip_path,
                    content=cached_entry.content,
                    size=cached_entry.size,
                    encoding=cached_entry.encoding,
                    is_text=cached_entry.is_text,
                    is_cached=is_cached,
                    created_at=datetime.fromtimestamp(cached_entry.created_at, tz=timezone.utc),
                )
        
        # 7. 使用异步操作读取ZIP中的文件
        # 运行阻塞操作在线程池中，避免阻塞事件循环
        def _read_from_zip() -> tuple:
            with zipfile.ZipFile(zip_path, "r") as zf:
                try:
                    info = zf.getinfo(resolved_zip_path)
                except KeyError:
                    raise HTTPException(status_code=404, detail=f"文件不存在: {resolved_zip_path}")
                
                # 8. 检查文件大小
                MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
                if info.file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件过大 ({info.file_size / 1024 / 1024:.2f}MB)，最大限制为 {MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
                    )
                
                file_bytes = zf.read(resolved_zip_path)
                created_at = datetime(*info.date_time, tzinfo=timezone.utc)
                return file_bytes, info.file_size, created_at
        
        # 在线程池执行阻塞操作
        file_bytes, file_size, created_at = await loop.run_in_executor(None, _read_from_zip)
        
        # 9. 检测文件类型
        is_binary = _is_binary_file(resolved_zip_path, file_bytes[:1024])
        
        # 10. 大文件使用流式传输
        STREAM_THRESHOLD = 1 * 1024 * 1024  # 1MB阈值
        if stream or (file_size > STREAM_THRESHOLD):
            logger.info(f"使用流式传输读取文件: {resolved_zip_path} (大小: {file_size / 1024:.1f}KB)")
            
            async def file_stream():
                """异步流式生成文件内容"""
                if is_binary:
                    # 二进制文件：返回base64编码
                    encoded = base64.b64encode(file_bytes).decode('ascii')
                    yield f'{{"file_path": "{resolved_zip_path}", "content": "{encoded}", "encoding": "base64", "size": {file_size}, "is_binary": true}}'
                else:
                    # 文本文件：返回JSON格式
                    
                    # 解码文本
                    try:
                        content = file_bytes.decode(encoding)
                        actual_encoding = encoding
                    except (UnicodeDecodeError, LookupError):
                        try:
                            content = file_bytes.decode("utf-8")
                            actual_encoding = "utf-8"
                        except UnicodeDecodeError:
                            content = file_bytes.decode("latin-1")
                            actual_encoding = "latin-1"
                    
                    response_data = {
                        "file_path": resolved_zip_path,
                        "content": content,
                        "size": file_size,
                        "encoding": actual_encoding,
                        "is_text": True,
                        "is_cached": False,
                        "created_at": created_at.isoformat(),
                    }
                    yield json.dumps(response_data)
            
            return StreamingResponse(
                file_stream(),
                media_type="application/json",
                headers={
                    "X-File-Path": resolved_zip_path,
                    "X-File-Size": str(file_size),
                    "X-Is-Binary": str(is_binary),
                }
            )
        
        # 11. 小文件直接返回
        if is_binary:
            logger.info(f"返回二进制文件（不解码）: {resolved_zip_path}")
            # 对于二进制文件，返回base64编码
            content = base64.b64encode(file_bytes).decode('ascii')
            actual_encoding = "base64"
            is_text = False
        else:
            # 12. 文本文件：解码内容
            try:
                content = file_bytes.decode(encoding)
                actual_encoding = encoding
            except (UnicodeDecodeError, LookupError):
                try:
                    content = file_bytes.decode("utf-8")
                    actual_encoding = "utf-8"
                except UnicodeDecodeError:
                    content = file_bytes.decode("latin-1")
                    actual_encoding = "latin-1"
            
            is_text = True
        
        # 13. 尝试缓存文本文件内容
        if is_text and use_cache and file_size < 5 * 1024 * 1024:  # 5MB限制
            await cache_manager.set(
                id,
                resolved_zip_path,
                zip_hash,
                content,
                file_size,
                actual_encoding,
                is_text,
            )
        
        # 14. 返回结果
        return FileContentResponse(
            file_path=resolved_zip_path,
            content=content,
            size=file_size,
            encoding=actual_encoding,
            is_text=is_text,
            is_cached=is_cached,
            created_at=created_at,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"读取文件 {resolved_zip_path} 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"无法读取项目文件: {str(e)}")


class ScanRequest(BaseModel):
    file_paths: Optional[List[str]] = None
    full_scan: bool = True
    exclude_patterns: Optional[List[str]] = None


@router.post("/{id}/scan")
async def scan_project(
    id: str,
    background_tasks: BackgroundTasks,
    scan_request: Optional[ScanRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Start a scan task.
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    exclude_patterns = scan_request.exclude_patterns if scan_request else None

    # Create Task Record
    task = AuditTask(
        project_id=project.id,
        created_by=current_user.id,
        task_type="repository",
        status="pending",
        exclude_patterns=json.dumps(exclude_patterns or []),
        scan_config=json.dumps(scan_request.model_dump()) if scan_request else "{}",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    # 获取用户配置（包含解密敏感字段）
    from app.core.encryption import decrypt_sensitive_data

    # 需要解密的敏感字段列表
    SENSITIVE_LLM_FIELDS = [
        "llmApiKey",
        "geminiApiKey",
        "openaiApiKey",
        "claudeApiKey",
        "qwenApiKey",
        "deepseekApiKey",
        "zhipuApiKey",
        "moonshotApiKey",
        "baiduApiKey",
        "minimaxApiKey",
        "doubaoApiKey",
    ]
    SENSITIVE_OTHER_FIELDS: list[str] = []

    def decrypt_config(config_dict: dict, sensitive_fields: list) -> dict:
        """解密配置中的敏感字段"""
        decrypted = config_dict.copy()
        for field in sensitive_fields:
            if field in decrypted and decrypted[field]:
                decrypted[field] = decrypt_sensitive_data(decrypted[field])
        return decrypted

    result = await db.execute(select(UserConfig).where(UserConfig.user_id == current_user.id))
    config = result.scalar_one_or_none()
    user_config = {}
    if config:
        llm_config = json.loads(config.llm_config) if config.llm_config else {}
        other_config = json.loads(config.other_config) if config.other_config else {}
        # 解密敏感字段
        llm_config = decrypt_config(llm_config, SENSITIVE_LLM_FIELDS)
        other_config = decrypt_config(other_config, SENSITIVE_OTHER_FIELDS)
        user_config = {
            "llmConfig": llm_config,
            "otherConfig": other_config,
        }

    # 将扫描配置注入到 user_config 中，以便 scan_repo_task 使用
    if scan_request and scan_request.file_paths:
        user_config["scan_config"] = {"file_paths": scan_request.file_paths}

    # Trigger Background Task
    background_tasks.add_task(scan_repo_task, task.id, AsyncSessionLocal, user_config)

    return {"task_id": task.id, "status": "started"}


# ============ ZIP文件管理端点 ============


class ZipFileMetaResponse(BaseModel):
    has_file: bool
    original_filename: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: Optional[str] = None


@router.get("/{id}/zip", response_model=ZipFileMetaResponse)
async def get_project_zip_info(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取项目ZIP文件信息
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # 检查是否有ZIP文件
    has_file = await has_project_zip(id)
    if not has_file:
        return {"has_file": False}

    # 获取元数据
    meta = await get_project_zip_meta(id)
    if meta:
        return {
            "has_file": True,
            "original_filename": meta.get("original_filename"),
            "file_size": meta.get("file_size"),
            "uploaded_at": meta.get("uploaded_at"),
        }

    return {"has_file": True}


@router.post("/{id}/zip")
async def upload_project_zip(
    id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    上传项目文件（支持多种压缩格式）

    支持的格式: .zip, .tar, .tar.gz, .tar.bz2, .7z, .rar 等
    所有格式都会被转换为 .zip 格式保存

    工作流程：
    1. 验证文件格式是否支持
    2. 保存上传的压缩文件到临时位置
    3. 验证文件完整性
    4. 解压到临时目录
    5. 重新压缩为 .zip 格式
    6. 保存到项目存储
    7. 清理临时文件
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # 检查权限

    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    # 检查文件格式是否支持
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
        return HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(sorted(supported_formats))}",
        )

    # 使用 tempfile 创建临时目录
    with tempfile.TemporaryDirectory(prefix="deepaudit_", suffix="_zip_upload") as temp_dir:
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

            # 先放宽解压文件数量上限，再通过过滤逻辑移除 test 目录及无关文件
            success, extracted_files, error = await UploadManager.extract_file(
                temp_upload_path,
                temp_extract_dir,
                max_files=100000,
            )

            if not success:
                raise HTTPException(status_code=400, detail=f"解压失败: {error}")

            # 创建最终的 ZIP 文件（命名为项目ID，并排除不需要的文件）
            final_zip_path = os.path.join(temp_dir, f"{id}.zip")

            try:
                create_zip_with_exclusions(temp_extract_dir, final_zip_path)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"重新压缩失败: {str(e)}")

            # 验证生成的 ZIP 文件
            is_valid, error = UploadManager.validate_file(final_zip_path)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"生成的 ZIP 文件验证失败: {error}")

            # 获取最终 ZIP 文件的预览
            success, file_list, error = UploadManager.get_file_list_preview(final_zip_path)
            if not success:
                raise HTTPException(status_code=400, detail=error)

            # 计算压缩包内容哈希，避免重复上传
            zip_hash = calculate_file_sha256(final_zip_path)

            # 同一项目重复上传相同压缩包直接拒绝
            if project.zip_file_hash and project.zip_file_hash == zip_hash:
                raise HTTPException(
                    status_code=409,
                    detail="当前项目已上传相同内容压缩包，无需重复上传",
                )

            # 检查是否与其他项目重复
            duplicate_project = await find_duplicate_zip_project(db, zip_hash, id)
            if duplicate_project:
                raise HTTPException(
                    status_code=409,
                    detail=f"检测到相同压缩包已上传到项目「{duplicate_project.name}」，请勿重复上传",
                )

            # 生成最终的文件名
            archive_filename = f"{id}.zip"

            # 保存到项目存储
            meta = await save_project_zip(id, final_zip_path, archive_filename)

            # 自动识别项目语言并回写项目信息
            filtered_paths = [
                path for path in (extracted_files or []) if not should_exclude_file(path)
            ]
            detected_languages = detect_languages_from_paths(filtered_paths)
            project.programming_languages = json.dumps(detected_languages, ensure_ascii=False)
            project.zip_file_hash = zip_hash
            description, language_info, _source = await _resolve_project_description_bundle(
                extracted_dir=temp_extract_dir,
                extracted_files=extracted_files,
                project_name=project.name,
                db=db,
                user_id=current_user.id,
            )
            project.description = description

            project_info = await _get_or_create_project_info(db, id)
            project_info.language_info = language_info
            project_info.description = description
            project_info.status = "completed"
            db.add(project)
            db.add(project_info)
            try:
                await db.commit()
                await db.refresh(project)
            except IntegrityError:
                await db.rollback()
                # 并发条件下可能冲突，回滚并清理刚保存的 zip 文件
                await delete_project_zip(id)
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
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.get("/{id}/upload/preview")
async def preview_upload_file(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取上传文件预览信息

    返回压缩包内的文件列表和统计信息
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    if project.source_type != "zip":
        raise HTTPException(status_code=400, detail="仅ZIP类型项目支持")

    # 获取 ZIP 文件
    zip_path = await load_project_zip(id)
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="未找到上传的文件")

    success, file_list, error = UploadManager.get_file_list_preview(zip_path, limit=50)
    if not success:
        raise HTTPException(status_code=500, detail=error)

    return {
        "file_count": len(file_list),
        "files": file_list,
        "supported_formats": list(CompressionStrategyFactory.get_supported_formats()),
    }


@router.post("/{id}/directory")
async def upload_project_directory(
    id: str,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    上传文件夹（实际为多个文件）

    工作流程：
    1. 验证项目权限
    2. 使用 tempfile 创建临时目录
    3. 将所有文件保存到临时目录（保持目录结构）
    4. 压缩成 ZIP 文件
    5. 保存到项目存储
    6. 自动清理临时目录和文件

    参数：
    - files: 多个文件，前端应该保持相对路径信息（通过 webkitRelativePath）
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # 检查权限

    # 检查项目类型
    if project.source_type != "zip":
        raise HTTPException(status_code=400, detail="仅ZIP类型项目可以上传文件")

    if not files:
        raise HTTPException(status_code=400, detail="至少需要上传一个文件")

    # 使用 tempfile 创建临时目录（自动清理）
    with tempfile.TemporaryDirectory(prefix="deepaudit_", suffix="_upload") as temp_base_dir:
        try:
            total_size = 0
            file_count = 0
            uploaded_paths: List[str] = []

            # 逐个保存文件，保持目录结构
            for file in files:
                if not file.filename:
                    continue

                # 获取文件的相对路径（保持目录结构）
                # 例如：src/main.py, tests/unit/test.py
                file_path = file.filename

                # 移除开头的 "/"（如果存在）
                if file_path.startswith("/"):
                    file_path = file_path[1:]

                if should_exclude_file(file_path):
                    continue

                # 检查文件大小
                file_content = await file.read()
                file_size = len(file_content)

                if file_size == 0:
                    continue  # 跳过空文件

                total_size += file_size
                file_count += 1

                # 检查总大小是否超过限制（500MB）
                if total_size > 500 * 1024 * 1024:
                    raise HTTPException(status_code=400, detail="文件总大小不能超过 500MB")

                # 完整的目标路径
                target_path = os.path.join(temp_base_dir, file_path)

                # 创建必要的目录
                target_dir = os.path.dirname(target_path)
                os.makedirs(target_dir, exist_ok=True)

                # 保存文件
                with open(target_path, "wb") as f:
                    f.write(file_content)
                uploaded_paths.append(file_path)

            if file_count == 0:
                raise HTTPException(status_code=400, detail="没有有效的文件")

            # 使用 tempfile 创建临时 ZIP 文件
            with tempfile.NamedTemporaryFile(
                suffix=".zip", prefix="deepaudit_", delete=False
            ) as temp_zip_file:
                temp_zip_path = temp_zip_file.name

            try:
                # 使用 shutil.make_archive 压缩
                archive_path = shutil.make_archive(
                    temp_zip_path.replace(".zip", ""),  # 去掉 .zip 后缀（make_archive 会自动添加）
                    "zip",
                    temp_base_dir,
                )
            except Exception as e:
                # 清理临时 ZIP 文件
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                raise HTTPException(status_code=500, detail=f"压缩文件失败: {str(e)}")

            # 验证压缩文件
            is_valid, error = UploadManager.validate_file(temp_zip_path)
            if not is_valid:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                raise HTTPException(status_code=400, detail=f"压缩文件验证失败: {error}")

            # 获取文件预览
            success, file_list, error = UploadManager.get_file_list_preview(temp_zip_path)
            if not success:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                raise HTTPException(status_code=400, detail=error)

            # 计算压缩包内容哈希，避免重复上传
            zip_hash = calculate_file_sha256(temp_zip_path)

            # 同一项目重复上传相同压缩包直接拒绝
            if project.zip_file_hash and project.zip_file_hash == zip_hash:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                raise HTTPException(
                    status_code=409,
                    detail="当前项目已上传相同内容压缩包，无需重复上传",
                )

            # 检查是否与其他项目重复
            duplicate_project = await find_duplicate_zip_project(db, zip_hash, id)
            if duplicate_project:
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)
                raise HTTPException(
                    status_code=409,
                    detail=f"检测到相同压缩包已上传到项目「{duplicate_project.name}」，请勿重复上传",
                )

            # 生成文件名为项目ID
            archive_filename = f"{id}.zip"

            # 保存到项目存储
            try:
                meta = await save_project_zip(id, temp_zip_path, archive_filename)
            finally:
                # 确保临时 ZIP 文件被清理
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)

            detected_languages = detect_languages_from_paths(uploaded_paths)
            project.programming_languages = json.dumps(detected_languages, ensure_ascii=False)
            project.zip_file_hash = zip_hash
            try:
                await db.commit()
                await db.refresh(project)
            except IntegrityError:
                await db.rollback()
                await delete_project_zip(id)
                raise HTTPException(
                    status_code=409,
                    detail="检测到相同压缩包已存在，请勿重复上传",
                )

            return {
                "message": "文件夹上传成功",
                "file_count": file_count,
                "total_size": total_size,
                "total_size_mb": f"{total_size / 1024 / 1024:.2f}",
                "original_filename": meta["original_filename"],
                "file_size": meta["file_size"],
                "uploaded_at": meta["uploaded_at"],
                "file_hash": zip_hash,
                "format": ".zip",
                "archive_file_count": len(file_list),
                "sample_files": file_list[:10],
                "detected_languages": detected_languages,
            }

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")


@router.delete("/{id}/zip")
async def delete_project_zip_file(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    删除项目ZIP文件
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)

    # 检查权限

    deleted = await delete_project_zip(id)
    if deleted:
        project.zip_file_hash = None
        await db.commit()

    if deleted:
        return {"message": "ZIP文件已删除"}
    else:
        return {"message": "没有找到ZIP文件"}


# ============ 分支管理端点 ============


# ============ 缓存管理端点 ============


@router.get("/cache/stats")
async def get_cache_stats(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取文件缓存统计信息
    
    返回:
    - total_entries: 缓存条目总数
    - hits: 缓存命中次数
    - misses: 缓存未命中次数
    - hit_rate: 命中率百分比
    - evictions: 驱逐的条目数
    - memory_used_mb: 已使用内存（MB）
    - memory_limit_mb: 内存限制（MB）
    """
    cache_manager = get_zip_cache_manager()
    return cache_manager.get_stats()


@router.post("/cache/clear")
async def clear_cache(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    清空所有文件缓存
    """
    cache_manager = get_zip_cache_manager()
    await cache_manager.clear_all()
    return {"message": "缓存已清空"}


@router.post("/{id}/cache/invalidate")
async def invalidate_project_cache(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    清除特定项目的缓存（更新ZIP后调用）
    
    Args:
        id: 项目ID
        
    Returns:
        清除的缓存条目数
    """
    project = await db.get(Project, id)
    _raise_if_project_hidden(project)
    
    zip_path = await load_project_zip(id)
    if not zip_path:
        raise HTTPException(status_code=404, detail="项目文件不存在")
    
    zip_hash = _calculate_zip_file_hash(zip_path)
    cache_manager = get_zip_cache_manager()
    deleted_count = await cache_manager.invalidate(id, zip_hash)
    
    return {
        "message": "缓存已清除",
        "deleted_entries": deleted_count
    }
