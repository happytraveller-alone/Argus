"""
搜索服务
提供统一的搜索功能，支持搜索 Project、AgentTask、AgentFinding
"""

from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, text, case
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.agent_task import AgentTask, AgentFinding, FindingStatus, VulnerabilitySeverity
from app.models.user import User


class SearchService:
    """搜索服务"""

    @staticmethod
    async def search_findings(
        db: AsyncSession,
        keyword: str,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Tuple[List[AgentFinding], int]:
        """
        搜索 AgentFinding
        
        搜索字段：
        - title: 漏洞标题
        - description: 漏洞描述
        - vulnerability_type: 漏洞类型
        - file_path: 文件路径
        - code_snippet: 代码片段
        """
        # 构建搜索查询
        keyword_pattern = f"%{keyword}%"
        
        search_filters = or_(
            AgentFinding.title.ilike(keyword_pattern),
            AgentFinding.description.ilike(keyword_pattern),
            AgentFinding.vulnerability_type.ilike(keyword_pattern),
            AgentFinding.file_path.ilike(keyword_pattern),
            AgentFinding.code_snippet.ilike(keyword_pattern),
        )
        
        # 如果提供了 user_id，只搜索该用户有权限的项目中的发现
        if user_id:
            # 获取用户有权限的项目
            projects_query = select(Project.id).where(
                or_(
                    Project.owner_id == user_id,
                    # 这里可以支持 ProjectMember 的权限检查
                )
            )
            project_ids = (await db.execute(projects_query)).scalars().all()
            
            # 获取这些项目中的任务
            tasks_query = select(AgentTask.id).where(
                AgentTask.project_id.in_(project_ids) if project_ids else False
            )
            task_ids = (await db.execute(tasks_query)).scalars().all()
            
            search_filters = and_(
                search_filters,
                AgentFinding.task_id.in_(task_ids) if task_ids else False,
            )
        
        # 构建查询
        query = select(AgentFinding).where(search_filters)
        
        # 添加关联（获取更多信息用于排序）
        query = query.options(selectinload(AgentFinding.task))
        
        # 排序
        if sort_by == "created_at":
            if sort_order == "desc":
                query = query.order_by(AgentFinding.created_at.desc())
            else:
                query = query.order_by(AgentFinding.created_at.asc())
        elif sort_by == "severity":
            # 按严重度排序（critical > high > medium > low > info）
            severity_order = {
                VulnerabilitySeverity.CRITICAL: 5,
                VulnerabilitySeverity.HIGH: 4,
                VulnerabilitySeverity.MEDIUM: 3,
                VulnerabilitySeverity.LOW: 2,
                VulnerabilitySeverity.INFO: 1,
            }
            when_list = [
                (AgentFinding.severity == VulnerabilitySeverity.CRITICAL, 5),
                (AgentFinding.severity == VulnerabilitySeverity.HIGH, 4),
                (AgentFinding.severity == VulnerabilitySeverity.MEDIUM, 3),
                (AgentFinding.severity == VulnerabilitySeverity.LOW, 2),
                (AgentFinding.severity == VulnerabilitySeverity.INFO, 1),
            ]
            severity_case = case(*when_list, else_=0)
            if sort_order == "desc":
                query = query.order_by(severity_case.desc())
            else:
                query = query.order_by(severity_case.asc())
        else:
            # Default to created_at
            query = query.order_by(AgentFinding.created_at.desc())
        
        # 统计总数
        count_query = select(func.count(AgentFinding.id)).where(search_filters)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页
        query = query.offset(offset).limit(limit)
        
        # 执行查询
        result = await db.execute(query)
        findings = result.scalars().unique().all()
        
        return findings, total

    @staticmethod
    async def search_tasks(
        db: AsyncSession,
        keyword: str,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Tuple[List[AgentTask], int]:
        """
        搜索 AgentTask
        
        搜索字段：
        - name: 任务名称
        - description: 任务描述
        - task_type: 任务类型
        - status: 任务状态
        """
        keyword_pattern = f"%{keyword}%"
        
        search_filters = or_(
            AgentTask.name.ilike(keyword_pattern),
            AgentTask.description.ilike(keyword_pattern),
            AgentTask.task_type.ilike(keyword_pattern),
            AgentTask.status.ilike(keyword_pattern),
        )
        
        # 如果提供了 user_id，只搜索该用户有权限的项目中的任务
        if user_id:
            projects_query = select(Project.id).where(
                or_(
                    Project.owner_id == user_id,
                )
            )
            project_ids = (await db.execute(projects_query)).scalars().all()
            
            search_filters = and_(
                search_filters,
                AgentTask.project_id.in_(project_ids) if project_ids else False,
            )
        
        # 构建查询
        query = select(AgentTask).where(search_filters)
        
        # 添加关联
        query = query.options(selectinload(AgentTask.project))
        
        # 排序
        if sort_by == "created_at":
            if sort_order == "desc":
                query = query.order_by(AgentTask.created_at.desc())
            else:
                query = query.order_by(AgentTask.created_at.asc())
        else:
            query = query.order_by(AgentTask.created_at.desc())
        
        # 统计总数
        count_query = select(func.count(AgentTask.id)).where(search_filters)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页
        query = query.offset(offset).limit(limit)
        
        # 执行查询
        result = await db.execute(query)
        tasks = result.scalars().unique().all()
        
        return tasks, total

    @staticmethod
    async def search_projects(
        db: AsyncSession,
        keyword: str,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Tuple[List[Project], int]:
        """
        搜索 Project
        
        搜索字段：
        - name: 项目名称
        - description: 项目描述
        - repository_url: 仓库 URL
        """
        keyword_pattern = f"%{keyword}%"
        
        search_filters = or_(
            Project.name.ilike(keyword_pattern),
            Project.description.ilike(keyword_pattern),
            Project.repository_url.ilike(keyword_pattern),
        )
        
        # 如果提供了 user_id，只搜索该用户有权限的项目
        if user_id:
            search_filters = and_(
                search_filters,
                or_(
                    Project.owner_id == user_id,
                ),
            )
        
        # 确保只搜索活跃项目
        search_filters = and_(
            search_filters,
            Project.is_active == True,
        )
        
        # 构建查询
        query = select(Project).where(search_filters)
        
        # 添加关联
        query = query.options(selectinload(Project.owner))
        
        # 排序
        if sort_by == "created_at":
            if sort_order == "desc":
                query = query.order_by(Project.created_at.desc())
            else:
                query = query.order_by(Project.created_at.asc())
        elif sort_by == "updated_at":
            if sort_order == "desc":
                query = query.order_by(Project.updated_at.desc())
            else:
                query = query.order_by(Project.updated_at.asc())
        else:
            query = query.order_by(Project.created_at.desc())
        
        # 统计总数
        count_query = select(func.count(Project.id)).where(search_filters)
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        
        # 分页
        query = query.offset(offset).limit(limit)
        
        # 执行查询
        result = await db.execute(query)
        projects = result.scalars().unique().all()
        
        return projects, total

    @staticmethod
    async def search_all(
        db: AsyncSession,
        keyword: str,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """
        全局搜索（搜索所有类型）
        
        返回格式：
        {
            "findings": [...],
            "tasks": [...],
            "projects": [...],
            "total": {
                "findings_total": 0,
                "tasks_total": 0,
                "projects_total": 0,
            }
        }
        """
        # 并发执行三个搜索
        findings, findings_total = await SearchService.search_findings(
            db, keyword, user_id, limit, offset, sort_by, sort_order
        )
        tasks, tasks_total = await SearchService.search_tasks(
            db, keyword, user_id, limit, offset, sort_by, sort_order
        )
        projects, projects_total = await SearchService.search_projects(
            db, keyword, user_id, limit, offset, sort_by, sort_order
        )
        
        return {
            "findings": findings,
            "tasks": tasks,
            "projects": projects,
            "total": {
                "findings_total": findings_total,
                "tasks_total": tasks_total,
                "projects_total": projects_total,
            },
        }
