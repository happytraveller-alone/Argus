"""
搜索功能测试
测试全局搜索、分类搜索等功能
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.search_service import SearchService
from app.models.project import Project
from app.models.agent_task import AgentTask, AgentTaskStatus, VulnerabilitySeverity, FindingStatus
from app.models.agent_task import AgentFinding
from app.models.user import User


@pytest.mark.asyncio
async def test_search_projects(db: AsyncSession, test_user: User):
    """测试项目搜索"""
    # 创建测试项目
    project = Project(
        name="测试安全项目",
        description="这是一个安全测试项目",
        source_type="repository",
        repository_url="https://github.com/test/project",
        owner_id=test_user.id,
        is_active=True,
    )
    db.add(project)
    await db.commit()
    
    # 搜索项目
    projects, total = await SearchService.search_projects(
        db=db,
        keyword="安全",
        user_id=test_user.id,
        limit=50,
        offset=0,
    )
    
    assert total == 1
    assert len(projects) == 1
    assert projects[0].name == "测试安全项目"


@pytest.mark.asyncio
async def test_search_findings(db: AsyncSession, test_user: User, test_project: Project, test_agent_task: AgentTask):
    """测试漏洞发现搜索"""
    # 创建测试发现
    finding = AgentFinding(
        task_id=test_agent_task.id,
        vulnerability_type="sql_injection",
        severity=VulnerabilitySeverity.CRITICAL,
        title="SQL 注入漏洞",
        description="在用户登录功能中发现 SQL 注入漏洞",
        file_path="src/auth.py",
        line_start=42,
        code_snippet="SELECT * FROM users WHERE username = ?",
        status=FindingStatus.NEW,
        is_verified=False,
    )
    db.add(finding)
    await db.commit()
    
    # 搜索发现
    findings, total = await SearchService.search_findings(
        db=db,
        keyword="SQL",
        user_id=test_user.id,
        limit=50,
        offset=0,
    )
    
    assert total == 1
    assert len(findings) == 1
    assert findings[0].title == "SQL 注入漏洞"


@pytest.mark.asyncio
async def test_search_tasks(db: AsyncSession, test_user: User, test_project: Project):
    """测试任务搜索"""
    # 创建测试任务
    task = AgentTask(
        project_id=test_project.id,
           created_by=test_user.id,
        name="安全审计扫描",
        description="对项目进行全面的安全审计",
        task_type="agent_audit",
        status=AgentTaskStatus.RUNNING,
    )
    db.add(task)
    await db.commit()
    
    # 搜索任务
    tasks, total = await SearchService.search_tasks(
        db=db,
        keyword="审计",
        user_id=test_user.id,
        limit=50,
        offset=0,
    )
    
    assert total == 1
    assert len(tasks) == 1
    assert tasks[0].name == "安全审计扫描"


@pytest.mark.asyncio
async def test_search_all(db: AsyncSession, test_user: User, test_project: Project, test_agent_task: AgentTask):
    """测试全局搜索"""
    # 创建测试数据
    finding = AgentFinding(
        task_id=test_agent_task.id,
        vulnerability_type="xss",
        severity=VulnerabilitySeverity.HIGH,
        title="XSS 跨站脚本漏洞",
        description="用户输入未经过滤导致 XSS",
        file_path="src/views.py",
        line_start=100,
        status=FindingStatus.NEW,
        is_verified=False,
    )
    db.add(finding)
    await db.commit()
    
    # 全局搜索
    result = await SearchService.search_all(
        db=db,
        keyword="漏洞",
        user_id=test_user.id,
        limit=50,
        offset=0,
    )
    
    assert result["total"]["findings_total"] >= 1
    assert len(result["findings"]) >= 1


@pytest.mark.asyncio
async def test_search_pagination(db: AsyncSession, test_user: User, test_project: Project):
    """测试分页功能"""
    # 创建多个项目用于分页测试
    for i in range(5):
        project = Project(
            name=f"项目 {i}",
            source_type="repository",
            repository_url=f"https://github.com/test/project{i}",
            owner_id=test_user.id,
            is_active=True,
        )
        db.add(project)
    
    await db.commit()
    
    # 第一页
    projects_page1, total = await SearchService.search_projects(
        db=db,
        keyword="项目",
        user_id=test_user.id,
        limit=2,
        offset=0,
    )
    
    assert total >= 5
    assert len(projects_page1) == 2
    
    # 第二页
    projects_page2, _ = await SearchService.search_projects(
        db=db,
        keyword="项目",
        user_id=test_user.id,
        limit=2,
        offset=2,
    )
    
    assert len(projects_page2) == 2
    # 确保两页数据不同
    assert projects_page1[0].id != projects_page2[0].id


@pytest.mark.asyncio
async def test_search_case_insensitive(db: AsyncSession, test_user: User):
    """测试大小写不敏感搜索"""
    # 创建项目
    project = Project(
        name="MySecurityProject",
        source_type="repository",
        repository_url="https://github.com/test/project",
        owner_id=test_user.id,
        is_active=True,
    )
    db.add(project)
    await db.commit()
    
    # 搜索：使用小写
    projects_lower, total_lower = await SearchService.search_projects(
        db=db,
        keyword="mysecurityproject",
        user_id=test_user.id,
    )
    
    # 搜索：使用大写
    projects_upper, total_upper = await SearchService.search_projects(
        db=db,
        keyword="MYSECURITYPROJECT",
        user_id=test_user.id,
    )
    
    # 搜索：使用混合大小写
    projects_mixed, total_mixed = await SearchService.search_projects(
        db=db,
        keyword="MySecurityProject",
        user_id=test_user.id,
    )
    
    assert total_lower == total_upper == total_mixed == 1
    assert projects_lower[0].id == projects_upper[0].id == projects_mixed[0].id


@pytest.mark.asyncio
async def test_search_partial_match(db: AsyncSession, test_user: User):
    """测试模糊匹配"""
    # 创建项目
    project = Project(
        name="Deep Security Audit Tool",
        source_type="repository",
        repository_url="https://github.com/test/project",
        owner_id=test_user.id,
        is_active=True,
    )
    db.add(project)
    await db.commit()
    
    # 模糊搜索
    projects, total = await SearchService.search_projects(
        db=db,
        keyword="Security",
        user_id=test_user.id,
    )
    
    assert total == 1
    assert projects[0].name == "Deep Security Audit Tool"


@pytest.mark.asyncio
async def test_search_finding_severity_sort(db: AsyncSession, test_user: User, test_agent_task: AgentTask):
    """测试按严重度排序"""
    findings_data = [
        ("低危漏洞", VulnerabilitySeverity.LOW),
        ("高危漏洞", VulnerabilitySeverity.HIGH),
        ("关键漏洞", VulnerabilitySeverity.CRITICAL),
        ("中危漏洞", VulnerabilitySeverity.MEDIUM),
    ]
    
    for title, severity in findings_data:
        finding = AgentFinding(
            task_id=test_agent_task.id,
            vulnerability_type="test",
            severity=severity,
            title=title,
            status=FindingStatus.NEW,
            is_verified=False,
        )
        db.add(finding)
    
    await db.commit()
    
    # 按严重度降序搜索
    findings, total = await SearchService.search_findings(
        db=db,
        keyword="漏洞",
        user_id=test_user.id,
        sort_by="severity",
        sort_order="desc",
    )
    
    assert total == 4
    # 应该按 CRITICAL > HIGH > MEDIUM > LOW 排序
    assert findings[0].severity == VulnerabilitySeverity.CRITICAL
    assert findings[1].severity == VulnerabilitySeverity.HIGH
    assert findings[2].severity == VulnerabilitySeverity.MEDIUM
    assert findings[3].severity == VulnerabilitySeverity.LOW


@pytest.mark.asyncio
async def test_search_empty_result(db: AsyncSession, test_user: User):
    """测试空搜索结果"""
    # 搜索不存在的内容
    projects, total = await SearchService.search_projects(
        db=db,
        keyword="不存在的项目名称xxxxxx",
        user_id=test_user.id,
    )
    
    assert total == 0
    assert len(projects) == 0


@pytest.mark.asyncio
async def test_search_includes_inactive_projects(db: AsyncSession, test_user: User):
    """测试搜索结果不再过滤 inactive 项目"""
    # 创建活跃项目
    active_project = Project(
        name="活跃项目",
        source_type="repository",
        repository_url="https://github.com/test/project",
        owner_id=test_user.id,
        is_active=True,
    )
    
    # 创建已删除项目
    deleted_project = Project(
        name="已删除项目",
        source_type="repository",
        repository_url="https://github.com/test/deleted",
        owner_id=test_user.id,
        is_active=False,
    )
    
    db.add(active_project)
    db.add(deleted_project)
    await db.commit()
    
    # 搜索"项目"关键词
    projects, total = await SearchService.search_projects(
        db=db,
        keyword="项目",
        user_id=test_user.id,
    )
    
    assert total == 2
    assert {project.name for project in projects} == {"活跃项目", "已删除项目"}
