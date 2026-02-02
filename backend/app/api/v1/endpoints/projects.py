from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from datetime import datetime, timezone
import shutil
import os
import uuid
import json
import tempfile
import logging
from pathlib import Path

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


def should_exclude_file(file_path: str) -> bool:
    """
    判断文件是否应该被排除
    
    Args:
        file_path: 相对于解压目录的文件路径
    
    Returns:
        True 表示应该排除，False 表示应该包含
    """
    # 规范化路径
    normalized_path = file_path.replace("\\", "/").strip("/")
    parts = normalized_path.split("/")
    
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
            dirs[:] = [d for d in dirs if not should_exclude_file(d)]
            
            for file in files:
                file_path = os.path.join(root, file)
                # 计算相对路径
                arcname = os.path.relpath(file_path, source_dir)
                
                # 检查是否应该排除
                if not should_exclude_file(arcname):
                    zipf.write(file_path, arcname)


from app.api import deps
from app.db.session import get_db, AsyncSessionLocal
from app.models.project import Project
from app.models.user import User
from app.models.audit import AuditTask, AuditIssue
from app.models.agent_task import AgentTask, AgentTaskStatus, AgentFinding
from app.models.user_config import UserConfig
from app.models.project_info import ProjectInfo
import zipfile
from app.services.scanner import (
    scan_repo_task,
    get_github_files,
    get_gitlab_files,
    get_github_branches,
    get_gitlab_branches,
    get_gitea_branches,
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
from app.services.upload.project_stats import get_cloc_stats, generate_project_description

router = APIRouter()


# Schemas
class ProjectCreate(BaseModel):
    name: str
    source_type: Optional[str] = "repository"  # 'repository' 或 'zip'
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

    class Config:
        from_attributes = True


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    source_type: Optional[str] = "repository"  # 'repository' 或 'zip'
    repository_url: Optional[str] = None
    repository_type: Optional[str] = None  # github, gitlab, other
    default_branch: Optional[str] = None
    programming_languages: Optional[str] = None
    owner_id: str
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    owner: Optional[OwnerSchema] = None

    class Config:
        from_attributes = True


class StatsResponse(BaseModel):
    total_projects: int
    active_projects: int
    total_tasks: int
    completed_tasks: int
    total_issues: int
    resolved_issues: int


class ProjectInfoResponse(BaseModel):
    id: str
    project_id: str
    language_info: str
    description: str
    status: str
    created_at: datetime
    

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

    # 根据 source_type 设置默认值
    source_type = project_in.source_type or "repository"

    project = Project(
        name=project_in.name,
        source_type=source_type,
        repository_url=project_in.repository_url if source_type == "repository" else None,
        repository_type=(
            project_in.repository_type or "other" if source_type == "repository" else "other"
        ),
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
    query = select(Project).options(selectinload(Project.owner))
    if not include_deleted:
        query = query.where(Project.is_active == True)
    query = query.order_by(Project.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


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
        .order_by(Project.updated_at.desc())
    )
    return result.scalars().all()


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get global statistics.
    """
    projects_result = await db.execute(select(Project))
    projects = projects_result.scalars().all()
    project_ids = [p.id for p in projects]

    # 统计旧的 AuditTask
    tasks_result = await db.execute(
        select(AuditTask).where(AuditTask.project_id.in_(project_ids))
        if project_ids
        else select(AuditTask).where(False)
    )
    tasks = tasks_result.scalars().all()
    task_ids = [t.id for t in tasks]

    # 统计旧的 AuditIssue
    issues_result = await db.execute(
        select(AuditIssue).where(AuditIssue.task_id.in_(task_ids))
        if task_ids
        else select(AuditIssue).where(False)
    )
    issues = issues_result.scalars().all()

    # 🔥 同时统计新的 AgentTask
    agent_tasks_result = await db.execute(
        select(AgentTask).where(AgentTask.project_id.in_(project_ids))
        if project_ids
        else select(AgentTask).where(False)
    )
    agent_tasks = agent_tasks_result.scalars().all()
    agent_task_ids = [t.id for t in agent_tasks]

    # 🔥 统计 AgentFinding
    agent_findings_result = await db.execute(
        select(AgentFinding).where(AgentFinding.task_id.in_(agent_task_ids))
        if agent_task_ids
        else select(AgentFinding).where(False)
    )
    agent_findings = agent_findings_result.scalars().all()

    # 合并统计（旧任务 + 新 Agent 任务）
    total_tasks = len(tasks) + len(agent_tasks)
    completed_tasks = len([t for t in tasks if t.status == "completed"]) + len(
        [t for t in agent_tasks if t.status == AgentTaskStatus.COMPLETED]
    )
    total_issues = len(issues) + len(agent_findings)
    resolved_issues = len([i for i in issues if i.status == "resolved"]) + len(
        [f for f in agent_findings if f.status == "resolved"]
    )

    return {
        "total_projects": len(projects),
        "active_projects": len([p for p in projects if p.is_active]),
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "total_issues": total_issues,
        "resolved_issues": resolved_issues,
    }


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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 检查权限：只有项目所有者可以查看

    return project


@router.get("/info/{id}", response_model=ProjectInfoResponse)
async def get_project_info(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取项目信息，包括自动分析的项目描述和语言统计
    """
    # 1. 获取项目基本信息
    result = await db.execute(select(Project).where(Project.id == id))
    project = result.scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 2. 检查权限

    # 3. 获取用户配置（用于LLM分析）
    user_config = {}
    try:
        result = await db.execute(select(UserConfig).where(UserConfig.user_id == current_user.id))
        config = result.scalar_one_or_none()
        if config and config.llm_config:
            user_config = {"llmConfig": json.loads(config.llm_config)}
    except Exception as e:
        logger.warning(f"获取用户配置失败: {e}")

    # 如果已存在 ProjectInfo，按状态返回或等待；失败则重新生成
    existing_info_result = await db.execute(select(ProjectInfo).where(ProjectInfo.project_id == id))
    existing_info = existing_info_result.scalars().first()
    if existing_info:
        if existing_info.status == "completed":
            return existing_info
        if existing_info.status == "pending":
            raise HTTPException(status_code=202, detail="项目信息正在生成中，请稍后再试")
        if existing_info.status == "failed":
            existing_info.status = "pending"
            existing_info.language_info = None
            existing_info.description = None
            existing_info.created_at = datetime.now(timezone.utc)
            db.add(existing_info)
            await db.commit()
            await db.refresh(existing_info)
            project_info = existing_info
        else:
            project_info = existing_info
    else:
        # 创建新的 ProjectInfo 记录并持久化为 pending 状态
        project_info = ProjectInfo(
            project_id=id,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )
        db.add(project_info)
        await db.commit()
        await db.refresh(project_info)

    try:
        # 生成语言统计（使用 ProjectInfo）
        cloc_result = await get_cloc_stats(project_info)
        project_info.language_info = cloc_result

        # 生成项目描述（使用 ProjectInfo）
        analysis_result = await generate_project_description(project_info)
        if isinstance(analysis_result, dict):
            project_info.description = analysis_result.get("project_description", "")
        else:
            # 兼容 generate_project_description 可能返回 JSON 字符串的情况
            try:
                parsed = json.loads(analysis_result) if isinstance(analysis_result, str) else {}
                project_info.description = parsed.get("project_description", "")
            except Exception:
                project_info.description = ""

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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 检查权限：只有项目所有者可以更新

    update_data = project_in.model_dump(exclude_unset=True)
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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

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
    branch: Optional[str] = None,
    exclude_patterns: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get list of files in the project.
    可选参数:
    - branch: 指定仓库分支（仅对仓库类型项目有效）
    - exclude_patterns: JSON 格式的排除模式数组，如 ["node_modules/**", "*.log"]
    """
    project = await db.get(Project, id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

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

    elif project.source_type == "repository":
        # Handle Repository project
        if not project.repository_url:
            return []

        # Get tokens from user config
        from sqlalchemy.future import select
        from app.core.encryption import decrypt_sensitive_data
        from app.core.config import settings
        from app.services.git_ssh_service import GitSSHOperations

        SENSITIVE_OTHER_FIELDS = ["githubToken", "gitlabToken", "sshPrivateKey"]

        result = await db.execute(select(UserConfig).where(UserConfig.user_id == current_user.id))
        config = result.scalar_one_or_none()

        github_token = settings.GITHUB_TOKEN
        gitlab_token = settings.GITLAB_TOKEN
        ssh_private_key = None

        if config and config.other_config:
            other_config = json.loads(config.other_config)
            for field in SENSITIVE_OTHER_FIELDS:
                if field in other_config and other_config[field]:
                    decrypted_val = decrypt_sensitive_data(other_config[field])
                    if field == "githubToken":
                        github_token = decrypted_val
                    elif field == "gitlabToken":
                        gitlab_token = decrypted_val
                    elif field == "sshPrivateKey":
                        ssh_private_key = decrypted_val

        # 检查是否为SSH URL
        is_ssh_url = GitSSHOperations.is_ssh_url(project.repository_url)
        target_branch = branch or project.default_branch or "main"

        try:
            if is_ssh_url:
                # 使用SSH方式获取文件列表
                if not ssh_private_key:
                    raise HTTPException(
                        status_code=400,
                        detail="仓库使用SSH URL，但未配置SSH密钥。请先在设置中生成SSH密钥。",
                    )

                print(f"🔐 使用SSH方式获取文件列表: {project.repository_url}")
                files_with_content = GitSSHOperations.get_repo_files_via_ssh(
                    project.repository_url, ssh_private_key, target_branch, parsed_exclude_patterns
                )
                files = [
                    {"path": f["path"], "size": len(f.get("content", ""))}
                    for f in files_with_content
                ]
            else:
                # 使用API方式获取文件列表
                repo_type = project.repository_type or "other"

                if repo_type == "github":
                    # 传入用户自定义排除模式
                    repo_files = await get_github_files(
                        project.repository_url, target_branch, github_token, parsed_exclude_patterns
                    )
                    files = [{"path": f["path"], "size": 0} for f in repo_files]
                elif repo_type == "gitlab":
                    # 传入用户自定义排除模式
                    repo_files = await get_gitlab_files(
                        project.repository_url, target_branch, gitlab_token, parsed_exclude_patterns
                    )
                    files = [{"path": f["path"], "size": 0} for f in repo_files]
                else:
                    raise HTTPException(status_code=400, detail="不支持的仓库类型")
        except HTTPException:
            raise
        except Exception as e:
            print(f"Error fetching repo files: {e}")
            raise HTTPException(status_code=500, detail=f"无法获取仓库文件: {str(e)}")

    return files


class ScanRequest(BaseModel):
    file_paths: Optional[List[str]] = None
    full_scan: bool = True
    exclude_patterns: Optional[List[str]] = None
    branch_name: Optional[str] = None


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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 获取分支和排除模式
    branch_name = scan_request.branch_name if scan_request else None
    exclude_patterns = scan_request.exclude_patterns if scan_request else None

    # Create Task Record
    task = AuditTask(
        project_id=project.id,
        created_by=current_user.id,
        task_type="repository",
        status="pending",
        branch_name=branch_name or project.default_branch or "main",
        exclude_patterns=json.dumps(exclude_patterns or []),
        scan_config=json.dumps(scan_request.dict()) if scan_request else "{}",
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
    SENSITIVE_OTHER_FIELDS = ["githubToken", "gitlabToken"]

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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

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

            success, extracted_files, error = await UploadManager.extract_file(
                temp_upload_path, temp_extract_dir
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

            # 自动识别项目语言并回写项目信息
            detected_languages = detect_languages_from_paths(extracted_files or [])
            project.programming_languages = json.dumps(detected_languages, ensure_ascii=False)
            await db.commit()
            await db.refresh(project)

            # 生成最终的文件名
            archive_filename = f"{id}.zip"

            # 保存到项目存储
            meta = await save_project_zip(id, final_zip_path, archive_filename)

            return {
                "message": "文件上传成功（已转换为 ZIP 格式）",
                "original_filename": file.filename,
                "original_format": file_ext,
                "final_filename": meta["original_filename"],
                "final_format": ".zip",
                "file_size": meta["file_size"],
                "uploaded_at": meta["uploaded_at"],
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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

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

            # 逐个保存文件，保持目录结构
            for file in files:
                if not file.filename:
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

                # 获取文件的相对路径（保持目录结构）
                # 例如：src/main.py, tests/unit/test.py
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

            # 生成文件名为项目ID
            archive_filename = f"{id}.zip"

            # 保存到项目存储
            try:
                meta = await save_project_zip(id, temp_zip_path, archive_filename)
            finally:
                # 确保临时 ZIP 文件被清理
                if os.path.exists(temp_zip_path):
                    os.remove(temp_zip_path)

            return {
                "message": "文件夹上传成功",
                "file_count": file_count,
                "total_size": total_size,
                "total_size_mb": f"{total_size / 1024 / 1024:.2f}",
                "original_filename": meta["original_filename"],
                "file_size": meta["file_size"],
                "uploaded_at": meta["uploaded_at"],
                "format": ".zip",
                "archive_file_count": len(file_list),
                "sample_files": file_list[:10],
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
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 检查权限

    deleted = await delete_project_zip(id)

    if deleted:
        return {"message": "ZIP文件已删除"}
    else:
        return {"message": "没有找到ZIP文件"}


# ============ 分支管理端点 ============


@router.get("/{id}/branches")
async def get_project_branches(
    id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取项目仓库的分支列表
    """
    project = await db.get(Project, id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 检查是否为仓库类型项目
    if project.source_type != "repository":
        raise HTTPException(status_code=400, detail="仅仓库类型项目支持获取分支")

    if not project.repository_url:
        raise HTTPException(status_code=400, detail="项目未配置仓库地址")

    # 获取用户配置的 Token
    from app.core.config import settings
    from app.core.encryption import decrypt_sensitive_data

    config = await db.execute(select(UserConfig).where(UserConfig.user_id == current_user.id))
    config = config.scalar_one_or_none()

    github_token = settings.GITHUB_TOKEN
    gitea_token = settings.GITEA_TOKEN
    gitlab_token = settings.GITLAB_TOKEN

    SENSITIVE_OTHER_FIELDS = ["githubToken", "gitlabToken", "giteaToken"]

    if config and config.other_config:
        import json

        other_config = json.loads(config.other_config)
        for field in SENSITIVE_OTHER_FIELDS:
            if field in other_config and other_config[field]:
                decrypted_val = decrypt_sensitive_data(other_config[field])
                if field == "githubToken":
                    github_token = decrypted_val
                elif field == "gitlabToken":
                    gitlab_token = decrypted_val
                elif field == "giteaToken":
                    gitea_token = decrypted_val

    repo_type = project.repository_type or "other"

    # 详细日志
    print(f"[Branch] 项目: {project.name}, 类型: {repo_type}, URL: {project.repository_url}")

    try:
        if repo_type == "github":
            if not github_token:
                print("[Branch] 警告: GitHub Token 未配置，可能会遇到 API 限制")
            branches = await get_github_branches(project.repository_url, github_token)
        elif repo_type == "gitlab":
            if not gitlab_token:
                print("[Branch] 警告: GitLab Token 未配置，可能无法访问私有仓库")
            branches = await get_gitlab_branches(project.repository_url, gitlab_token)
        elif repo_type == "gitea":
            if not gitea_token:
                print("[Branch] 警告: Gitea Token 未配置，可能无法访问私有仓库")
            branches = await get_gitea_branches(project.repository_url, gitea_token)
        else:
            # 对于其他类型，返回默认分支
            print(f"[Branch] 仓库类型 '{repo_type}' 不支持获取分支，返回默认分支")
            branches = [project.default_branch or "main"]

        print(f"[Branch] 成功获取 {len(branches)} 个分支")

        # 将默认分支放在第一位
        default_branch = project.default_branch or "main"
        if default_branch in branches:
            branches.remove(default_branch)
            branches.insert(0, default_branch)

        return {"branches": branches, "default_branch": default_branch}

    except Exception as e:
        error_msg = str(e)
        print(f"[Branch] 获取分支列表失败: {error_msg}")
        # 返回默认分支作为后备
        return {
            "branches": [project.default_branch or "main"],
            "default_branch": project.default_branch or "main",
            "error": str(e),
        }
