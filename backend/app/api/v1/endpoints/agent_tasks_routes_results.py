"""Result, reporting, queue, and progress routes for agent tasks."""

import asyncio
import os
import shutil
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.db.session import get_db
from app.models.agent_task import (
    AgentEvent,
    AgentEventType,
    AgentFinding,
    AgentTask,
    AgentTaskStatus,
    AgentTreeNode,
    FindingStatus,
    VulnerabilitySeverity,
)
from app.models.project import Project
from app.models.user import User

from .agent_tasks_contracts import *
from .agent_tasks_findings import *
from .agent_tasks_runtime import *

router = APIRouter()
logger = logging.getLogger(__name__)

_MANUAL_FINDING_STATUS_ALIASES = {
    "new": FindingStatus.NEEDS_REVIEW,
    "open": FindingStatus.NEEDS_REVIEW,
    "pending": FindingStatus.NEEDS_REVIEW,
    "needs_review": FindingStatus.NEEDS_REVIEW,
    "needs-review": FindingStatus.NEEDS_REVIEW,
    "verified": FindingStatus.VERIFIED,
    "confirmed": FindingStatus.VERIFIED,
    "false_positive": FindingStatus.FALSE_POSITIVE,
    "false-positive": FindingStatus.FALSE_POSITIVE,
}


def _is_manually_verified_status(status: Any) -> bool:
    return str(status or "").strip().lower() == FindingStatus.VERIFIED


def _normalize_manual_finding_status(status: Any) -> str:
    normalized = str(status or "").strip().lower()
    mapped = _MANUAL_FINDING_STATUS_ALIASES.get(normalized)
    if not mapped:
        raise HTTPException(status_code=400, detail=f"无效的状态: {status}")
    return mapped


async def _recompute_task_finding_counters(
    db: AsyncSession,
    task: AgentTask,
) -> None:
    result = await db.execute(
        select(AgentFinding).where(AgentFinding.task_id == task.id)
    )
    findings = result.scalars().all()

    task.findings_count = 0
    task.verified_count = 0
    task.false_positive_count = 0
    task.critical_count = 0
    task.high_count = 0
    task.medium_count = 0
    task.low_count = 0

    for finding in findings:
        normalized_status = str(getattr(finding, "status", "") or "").strip().lower()
        if normalized_status == FindingStatus.FALSE_POSITIVE:
            task.false_positive_count += 1
            continue

        task.findings_count += 1
        severity = str(getattr(finding, "severity", "") or "").strip().lower()
        if severity == VulnerabilitySeverity.CRITICAL:
            task.critical_count += 1
        elif severity == VulnerabilitySeverity.HIGH:
            task.high_count += 1
        elif severity == VulnerabilitySeverity.MEDIUM:
            task.medium_count += 1
        elif severity == VulnerabilitySeverity.LOW:
            task.low_count += 1

        if bool(getattr(finding, "is_verified", False)) or _is_manually_verified_status(
            normalized_status
        ):
            task.verified_count += 1

@router.get("/{task_id}/findings", response_model=List[AgentFindingResponse])
async def list_agent_findings(
    task_id: str,
    severity: Optional[str] = None,
    verified_only: bool = False,
    include_false_positive: bool = Query(False, description="是否包含 false_positive 结果"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取 Agent 发现列表
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    query = select(AgentFinding).where(AgentFinding.task_id == task_id)
    if not include_false_positive:
        query = query.where(AgentFinding.status != FindingStatus.FALSE_POSITIVE)
    
    if severity:
        normalized_severity = str(severity).strip().lower()
        if normalized_severity in _VALID_SEVERITY_VALUES:
            query = query.where(AgentFinding.severity == normalized_severity)
    
    if verified_only:
        query = query.where(
            or_(
                AgentFinding.is_verified == True,
                AgentFinding.status == FindingStatus.VERIFIED,
            )
        )
    
    # 按严重程度排序
    severity_order = {
        VulnerabilitySeverity.CRITICAL: 0,
        VulnerabilitySeverity.HIGH: 1,
        VulnerabilitySeverity.MEDIUM: 2,
        VulnerabilitySeverity.LOW: 3,
        VulnerabilitySeverity.INFO: 4,
    }
    
    query = query.order_by(
        case(
            (AgentFinding.severity == VulnerabilitySeverity.CRITICAL, 0),
            (AgentFinding.severity == VulnerabilitySeverity.HIGH, 1),
            (AgentFinding.severity == VulnerabilitySeverity.MEDIUM, 2),
            (AgentFinding.severity == VulnerabilitySeverity.LOW, 3),
            (AgentFinding.severity == VulnerabilitySeverity.INFO, 4),
            else_=5,
        ),
        AgentFinding.created_at.desc(),
    )
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    findings = result.scalars().all()
    serialized_findings = _serialize_agent_findings(
        findings,
        include_false_positive=include_false_positive,
    )
    if verified_only:
        serialized_findings = [
            item
            for item in serialized_findings
            if (
                getattr(item, "is_verified", False)
                or _is_manually_verified_status(getattr(item, "status", None))
            )
        ]
    return serialized_findings

@router.get("/{task_id}/findings/{finding_id}", response_model=AgentFindingResponse)
async def get_agent_finding(
    task_id: str,
    finding_id: str,
    include_false_positive: bool = Query(
        True,
        description="是否包含 false_positive 结果",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """获取 Agent 单条发现详情。"""
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    result = await db.execute(
        select(AgentFinding).where(
            (AgentFinding.task_id == task_id)
            & (AgentFinding.id == finding_id)
        )
    )
    finding = result.scalar_one_or_none()
    if not finding:
        raise HTTPException(status_code=404, detail="发现不存在")

    serialized = _serialize_agent_findings(
        [finding],
        include_false_positive=include_false_positive,
    )
    if not serialized:
        raise HTTPException(status_code=404, detail="发现不存在")
    return serialized[0]


@router.get("/{task_id}/summary", response_model=TaskSummaryResponse)
async def get_task_summary(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取任务摘要
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 获取所有发现
    result = await db.execute(
        select(AgentFinding).where(AgentFinding.task_id == task_id)
    )
    findings = result.scalars().all()
    
    # 统计
    severity_distribution = {}
    vulnerability_types = {}
    verified_count = 0
    
    for f in findings:
        # severity 和 vulnerability_type 已经是字符串
        sev = str(f.severity)
        vtype = str(f.vulnerability_type)
        
        severity_distribution[sev] = severity_distribution.get(sev, 0) + 1
        vulnerability_types[vtype] = vulnerability_types.get(vtype, 0) + 1
        
        if f.is_verified:
            verified_count += 1
    
    # 计算持续时间
    duration = None
    if task.started_at and task.completed_at:
        duration = int((task.completed_at - task.started_at).total_seconds())
    
    # 获取已完成的阶段
    phases_result = await db.execute(
        select(AgentEvent.phase)
        .where(AgentEvent.task_id == task_id)
        .where(AgentEvent.event_type == AgentEventType.PHASE_COMPLETE)
        .distinct()
    )
    phases = [str(p[0]) for p in phases_result.fetchall() if p[0]]
    
    return TaskSummaryResponse(
        task_id=task_id,
        status=str(task.status),  # status 已经是字符串
        security_score=task.security_score,
        total_findings=len(findings),
        verified_findings=verified_count,
        severity_distribution=severity_distribution,
        vulnerability_types=vulnerability_types,
        duration_seconds=duration,
        phases_completed=phases,
    )


@router.patch("/{task_id}/findings/{finding_id}/status")
async def update_finding_status(
    task_id: str,
    finding_id: str,
    status: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    更新发现状态
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权操作")
    
    finding = await db.get(AgentFinding, finding_id)
    if not finding or finding.task_id != task_id:
        raise HTTPException(status_code=404, detail="发现不存在")
    
    normalized_status = _normalize_manual_finding_status(status)
    finding.status = normalized_status
    finding.is_verified = normalized_status == FindingStatus.VERIFIED
    finding.verified_at = (
        datetime.now(timezone.utc)
        if normalized_status == FindingStatus.VERIFIED
        else None
    )
    if normalized_status == FindingStatus.VERIFIED:
        finding.verdict = "confirmed"
    elif normalized_status == FindingStatus.FALSE_POSITIVE:
        finding.verdict = "false_positive"

    verification_result = (
        dict(finding.verification_result)
        if isinstance(finding.verification_result, dict)
        else {}
    )
    verification_result["status"] = normalized_status
    verification_result["verification_stage_completed"] = True
    if normalized_status == FindingStatus.VERIFIED:
        verification_result["authenticity"] = "confirmed"
        verification_result["verdict"] = "confirmed"
    elif normalized_status == FindingStatus.FALSE_POSITIVE:
        verification_result["authenticity"] = "false_positive"
        verification_result["verdict"] = "false_positive"
    finding.verification_result = verification_result

    await _recompute_task_finding_counters(db, task)
    await db.commit()
    
    return {
        "message": "状态已更新",
        "finding_id": finding_id,
        "status": normalized_status,
    }


# ============ Helper Functions ============

async def _get_project_root(
    project: Project,
    task_id: str,
    event_emitter: Optional[Any] = None,
) -> str:
    """
    为 ZIP 项目准备临时工作目录。

    Args:
        project: 项目对象
        task_id: 任务ID
        event_emitter: 事件发送器（用于发送实时日志）

    Returns:
        项目根目录路径

    Raises:
        RuntimeError: 当项目文件获取失败时
    """
    import zipfile

    # 辅助函数：发送事件
    async def emit(message: str, level: str = "info"):
        if event_emitter:
            if level == "info":
                await event_emitter.emit_info(message)
            elif level == "warning":
                await event_emitter.emit_warning(message)
            elif level == "error":
                await event_emitter.emit_error(message)

    #  辅助函数：检查取消状态
    def check_cancelled():
        if is_task_cancelled(task_id):
            raise asyncio.CancelledError("任务已取消")

    base_path = f"/tmp/VulHunter/{task_id}"

    # 确保目录存在且为空
    if os.path.exists(base_path):
        shutil.rmtree(base_path)
    os.makedirs(base_path, exist_ok=True)

    #  在开始任何操作前检查取消
    check_cancelled()

    if project.source_type != "zip":
        await emit("仅支持 ZIP 项目", "error")
        raise RuntimeError("仅支持 ZIP 项目")

    check_cancelled()
    await emit("正在解压项目文件...")
    from app.services.zip_storage import load_project_zip

    zip_path = await load_project_zip(project.id)

    if zip_path and os.path.exists(zip_path):
        try:
            check_cancelled()
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                file_list = zip_ref.namelist()
                for i, file_name in enumerate(file_list):
                    if i % 50 == 0:
                        check_cancelled()
                    zip_ref.extract(file_name, base_path)
            logger.info("Extracted ZIP project %s to %s", project.id, base_path)
            await emit("ZIP 文件解压完成")
        except Exception as exc:
            logger.error("Failed to extract ZIP %s: %s", zip_path, exc)
            await emit(f"解压失败: {exc}", "error")
            raise RuntimeError(f"无法解压项目文件: {exc}")
    else:
        logger.warning("ZIP file not found for project %s", project.id)
        await emit("ZIP 文件不存在", "error")
        raise RuntimeError(f"项目 ZIP 文件不存在: {project.id}")

    # 验证目录不为空
    if not os.listdir(base_path):
        await emit(f"项目目录为空", "error")
        raise RuntimeError(f"项目目录为空，可能是克隆/解压失败: {base_path}")

    #  智能检测：如果解压后只有一个子目录（常见于 ZIP 文件），
    # 则使用那个子目录作为真正的项目根目录
    # 例如：/tmp/VulHunter/UUID/PHP-Project/ -> 返回 /tmp/VulHunter/UUID/PHP-Project
    items = os.listdir(base_path)
    # 过滤掉 macOS 产生的 __MACOSX 目录和隐藏文件
    real_items = [item for item in items if not item.startswith('__') and not item.startswith('.')]
    
    if len(real_items) == 1:
        single_item_path = os.path.join(base_path, real_items[0])
        if os.path.isdir(single_item_path):
            logger.info(f" 检测到单层嵌套目录，自动调整项目根目录: {base_path} -> {single_item_path}")
            await emit(f" 检测到嵌套目录，自动调整为: {real_items[0]}")
            base_path = single_item_path

    await emit(f"📁 项目准备完成: {base_path}")
    return base_path


# ============ Agent Tree API ============

class AgentTreeNodeResponse(BaseModel):
    """Agent 树节点响应"""
    id: str
    agent_id: str
    agent_name: str
    agent_type: str
    parent_agent_id: Optional[str] = None
    depth: int = 0
    task_description: Optional[str] = None
    knowledge_modules: Optional[List[str]] = None
    status: str = "created"
    result_summary: Optional[str] = None
    findings_count: int = 0
    verified_findings_count: int = 0
    iterations: int = 0
    tokens_used: int = 0
    tool_calls: int = 0
    duration_ms: Optional[int] = None
    children: List["AgentTreeNodeResponse"] = []
    
    model_config = ConfigDict(from_attributes=True)


class AgentTreeResponse(BaseModel):
    """Agent 树响应"""
    task_id: str
    root_agent_id: Optional[str] = None
    total_agents: int = 0
    running_agents: int = 0
    completed_agents: int = 0
    failed_agents: int = 0
    total_findings: int = 0
    verified_total_findings: int = 0
    nodes: List[AgentTreeNodeResponse] = []


def _normalize_finding_token(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_live_verified_finding(item: Any) -> bool:
    if not isinstance(item, dict):
        return False

    status = _normalize_finding_token(item.get("status"))
    authenticity = _normalize_finding_token(
        item.get("authenticity") or item.get("verification_status")
    )
    verdict = _normalize_finding_token(item.get("verdict"))

    if (
        status == FindingStatus.FALSE_POSITIVE
        or authenticity == FindingStatus.FALSE_POSITIVE
        or verdict == FindingStatus.FALSE_POSITIVE
    ):
        return False

    if bool(item.get("is_verified")):
        return True

    return (
        status == FindingStatus.VERIFIED
        or status == FindingStatus.LIKELY
        or authenticity in {"confirmed", "likely"}
        or verdict in {"confirmed", "likely"}
    )


def _resolve_live_finding_identity(item: Any) -> Optional[str]:
    if not isinstance(item, dict):
        return None

    for key in (
        "id",
        "finding_id",
        "verification_fingerprint",
        "verification_todo_id",
        "fingerprint",
        "merge_key",
    ):
        value = str(item.get(key) or "").strip()
        if value:
            return f"{key}:{value}"

    vulnerability_type = str(item.get("vulnerability_type") or "").strip()
    file_path = str(item.get("file_path") or "").strip()
    line_start = str(item.get("line_start") or item.get("line") or "").strip()
    if vulnerability_type or file_path or line_start:
        return f"fallback:{vulnerability_type}|{file_path}|{line_start}"
    return None


def _count_live_verified_findings(items: Any, *, dedupe: bool = False) -> int:
    if not isinstance(items, list):
        return 0

    count = 0
    seen: set[str] = set()
    for item in items:
        if not _is_live_verified_finding(item):
            continue
        if dedupe:
            identity = _resolve_live_finding_identity(item)
            if identity and identity in seen:
                continue
            if identity:
                seen.add(identity)
        count += 1
    return count


def _resolve_live_verified_counts(tree: Dict[str, Any]) -> Dict[str, int]:
    nodes = tree.get("nodes", {})
    if not isinstance(nodes, dict):
        return {"__total__": 0}

    counts: Dict[str, int] = {}
    combined_findings: List[Dict[str, Any]] = []

    for agent_id, node_data in nodes.items():
        if not isinstance(node_data, dict):
            counts[agent_id] = 0
            continue
        result = node_data.get("result")
        findings = result.get("findings", []) if isinstance(result, dict) else []
        counts[agent_id] = _count_live_verified_findings(findings, dedupe=False)
        if isinstance(findings, list):
            combined_findings.extend(
                item for item in findings if isinstance(item, dict)
            )

    counts["__total__"] = _count_live_verified_findings(combined_findings, dedupe=True)
    return counts


@router.get("/{task_id}/agent-tree", response_model=AgentTreeResponse)
async def get_agent_tree(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取任务的 Agent 树结构
    
    返回动态 Agent 树的完整结构，包括：
    - 所有 Agent 节点
    - 父子关系
    - 执行状态
    - 发现统计
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 尝试从内存中获取 Agent 树（运行中的任务）
    runner = _running_tasks.get(task_id)
    logger.debug(f"[AgentTree API] task_id={task_id}, runner exists={runner is not None}")
    
    if runner:
        from app.services.agent.core import agent_registry
        
        tree = agent_registry.get_agent_tree()
        stats = agent_registry.get_statistics()
        logger.debug(f"[AgentTree API] tree nodes={len(tree.get('nodes', {}))}, root={tree.get('root_agent_id')}")
        logger.debug(f"[AgentTree API] 节点详情: {list(tree.get('nodes', {}).keys())}")
        
        #  获取 root agent ID，用于判断是否是 Orchestrator
        root_agent_id = tree.get("root_agent_id")
        live_verified_counts = _resolve_live_verified_counts(tree)
        verified_total_findings = live_verified_counts.get("__total__", 0)
        
        # 构建节点列表
        nodes = []
        for agent_id, node_data in tree.get("nodes", {}).items():
            #  从 Agent 实例获取实时统计数据
            iterations = 0
            tool_calls = 0
            tokens_used = 0
            findings_count = 0
            
            agent_instance = agent_registry.get_agent(agent_id)
            if agent_instance and hasattr(agent_instance, 'get_stats'):
                agent_stats = agent_instance.get_stats()
                iterations = agent_stats.get("iterations", 0)
                tool_calls = agent_stats.get("tool_calls", 0)
                tokens_used = agent_stats.get("tokens_used", 0)
            
            #  FIX: 对于 Orchestrator (root agent)，使用 task 的 findings_count
            # 这确保了正确显示聚合的 findings 总数
            if agent_id == root_agent_id:
                findings_count = task.findings_count or 0
                verified_findings_count = verified_total_findings
            else:
                # 从结果中获取发现数量（对于子 agent）
                verified_findings_count = live_verified_counts.get(agent_id, 0)
                if node_data.get("result"):
                    result = node_data.get("result", {})
                    findings_count = len(result.get("findings", []))
            
            nodes.append(AgentTreeNodeResponse(
                id=node_data.get("id", agent_id),
                agent_id=agent_id,
                agent_name=node_data.get("name", "Unknown"),
                agent_type=node_data.get("type", "unknown"),
                parent_agent_id=node_data.get("parent_id"),
                task_description=node_data.get("task"),
                knowledge_modules=node_data.get("knowledge_modules", []),
                status=node_data.get("status", "unknown"),
                findings_count=findings_count,
                verified_findings_count=verified_findings_count,
                iterations=iterations,
                tool_calls=tool_calls,
                tokens_used=tokens_used,
                children=[],
            ))
        
        #  使用 task.findings_count 作为 total_findings，确保一致性
        return AgentTreeResponse(
            task_id=task_id,
            root_agent_id=root_agent_id,
            total_agents=stats.get("total", 0),
            running_agents=stats.get("running", 0),
            completed_agents=stats.get("completed", 0),
            failed_agents=stats.get("failed", 0),
            total_findings=task.findings_count or 0,
            verified_total_findings=verified_total_findings,
            nodes=nodes,
        )
    
    # 从数据库获取（已完成的任务）
    from app.models.agent_task import AgentTreeNode
    
    result = await db.execute(
        select(AgentTreeNode)
        .where(AgentTreeNode.task_id == task_id)
        .order_by(AgentTreeNode.depth, AgentTreeNode.created_at)
    )
    db_nodes = result.scalars().all()
    
    if not db_nodes:
        return AgentTreeResponse(
            task_id=task_id,
            total_findings=task.findings_count or 0,
            verified_total_findings=task.verified_count or 0,
            nodes=[],
        )
    
    # 构建响应
    nodes = []
    root_id = None
    running = 0
    completed = 0
    failed = 0
    verified_total_findings = task.verified_count or 0
    
    for node in db_nodes:
        if node.parent_agent_id is None:
            root_id = node.agent_id
        
        if node.status == "running":
            running += 1
        elif node.status == "completed":
            completed += 1
        elif node.status == "failed":
            failed += 1
        
        #  FIX: 对于 Orchestrator (root agent)，使用 task 的 findings_count
        # 这确保了正确显示聚合的 findings 总数
        if node.parent_agent_id is None:
            # Root agent uses task's total findings
            node_findings_count = task.findings_count or 0
            node_verified_findings_count = verified_total_findings
        else:
            node_findings_count = node.findings_count or 0
            node_verified_findings_count = 0
        
        nodes.append(AgentTreeNodeResponse(
            id=node.id,
            agent_id=node.agent_id,
            agent_name=node.agent_name,
            agent_type=node.agent_type,
            parent_agent_id=node.parent_agent_id,
            depth=node.depth,
            task_description=node.task_description,
            knowledge_modules=node.knowledge_modules,
            status=node.status,
            result_summary=node.result_summary,
            findings_count=node_findings_count,
            verified_findings_count=node_verified_findings_count,
            iterations=node.iterations or 0,
            tokens_used=node.tokens_used or 0,
            tool_calls=node.tool_calls or 0,
            duration_ms=node.duration_ms,
            children=[],
        ))
    
    #  使用 task.findings_count 作为 total_findings，确保一致性
    return AgentTreeResponse(
        task_id=task_id,
        root_agent_id=root_id,
        total_agents=len(nodes),
        running_agents=running,
        completed_agents=completed,
        failed_agents=failed,
        total_findings=task.findings_count or 0,
        verified_total_findings=verified_total_findings,
        nodes=nodes,
    )


# ============ Checkpoint API ============

class CheckpointResponse(BaseModel):
    """检查点响应"""
    id: str
    agent_id: str
    agent_name: str
    agent_type: str
    iteration: int
    status: str
    total_tokens: int = 0
    tool_calls: int = 0
    findings_count: int = 0
    checkpoint_type: str = "auto"
    checkpoint_name: Optional[str] = None
    created_at: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


@router.get("/{task_id}/checkpoints", response_model=List[CheckpointResponse])
async def list_checkpoints(
    task_id: str,
    agent_id: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取任务的检查点列表
    
    用于：
    - 查看执行历史
    - 状态恢复
    - 调试分析
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    from app.models.agent_task import AgentCheckpoint
    
    query = select(AgentCheckpoint).where(AgentCheckpoint.task_id == task_id)
    
    if agent_id:
        query = query.where(AgentCheckpoint.agent_id == agent_id)
    
    query = query.order_by(AgentCheckpoint.created_at.desc()).limit(limit)
    
    result = await db.execute(query)
    checkpoints = result.scalars().all()
    
    return [
        CheckpointResponse(
            id=cp.id,
            agent_id=cp.agent_id,
            agent_name=cp.agent_name,
            agent_type=cp.agent_type,
            iteration=cp.iteration,
            status=cp.status,
            total_tokens=cp.total_tokens or 0,
            tool_calls=cp.tool_calls or 0,
            findings_count=cp.findings_count or 0,
            checkpoint_type=cp.checkpoint_type or "auto",
            checkpoint_name=cp.checkpoint_name,
            created_at=cp.created_at.isoformat() if cp.created_at else None,
        )
        for cp in checkpoints
    ]


@router.get("/{task_id}/checkpoints/{checkpoint_id}")
async def get_checkpoint_detail(
    task_id: str,
    checkpoint_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取检查点详情
    
    返回完整的 Agent 状态数据
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    from app.models.agent_task import AgentCheckpoint
    
    checkpoint = await db.get(AgentCheckpoint, checkpoint_id)
    if not checkpoint or checkpoint.task_id != task_id:
        raise HTTPException(status_code=404, detail="检查点不存在")
    
    # 解析状态数据
    state_data = {}
    if checkpoint.state_data:
        try:
            state_data = json.loads(checkpoint.state_data)
        except json.JSONDecodeError:
            pass
    
    return {
        "id": checkpoint.id,
        "task_id": checkpoint.task_id,
        "agent_id": checkpoint.agent_id,
        "agent_name": checkpoint.agent_name,
        "agent_type": checkpoint.agent_type,
        "parent_agent_id": checkpoint.parent_agent_id,
        "iteration": checkpoint.iteration,
        "status": checkpoint.status,
        "total_tokens": checkpoint.total_tokens,
        "tool_calls": checkpoint.tool_calls,
        "findings_count": checkpoint.findings_count,
        "checkpoint_type": checkpoint.checkpoint_type,
        "checkpoint_name": checkpoint.checkpoint_name,
        "state_data": state_data,
        "metadata": checkpoint.checkpoint_metadata,
        "created_at": checkpoint.created_at.isoformat() if checkpoint.created_at else None,
    }

@router.get("/tasks/{task_id}/vulnerability_queue/status", response_model=Dict[str, Any])
async def get_vulnerability_queue_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    获取任务的漏洞队列状态
    
    返回队列中待验证漏洞的数量和统计信息
    """
    from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
    
    # 检查任务是否存在
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = await db.get(Project, task.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # 复用运行中的队列服务，避免新实例导致状态丢失
    queue_service = _running_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryVulnerabilityQueue()
    
    # 获取队列统计
    stats = queue_service.get_queue_stats(task_id)
    
    return {
        "success": True,
        "task_id": task_id,
        "queue_stats": stats,
    }


@router.get("/tasks/{task_id}/vulnerability_queue/peek", response_model=Dict[str, Any])
async def peek_vulnerability_queue(
    task_id: str,
    limit: int = 3,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    查看任务漏洞队列的前N条记录
    
    不会移除队列中的项目，仅用于预览
    """
    from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
    
    # 检查任务是否存在
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = await db.get(Project, task.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # 复用运行中的队列服务，避免新实例导致状态丢失
    queue_service = _running_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryVulnerabilityQueue()
    
    # 查看队列前几项
    findings = queue_service.peek_queue(task_id, limit=min(limit, 10))
    
    return {
        "success": True,
        "task_id": task_id,
        "findings": findings,
        "count": len(findings),
    }


@router.delete("/tasks/{task_id}/vulnerability_queue", response_model=Dict[str, Any])
async def clear_vulnerability_queue(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    清空任务的漏洞队列
    
    用于手动清理或重置队列状态
    """
    from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
    
    # 检查任务是否存在
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 检查权限
    project = await db.get(Project, task.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # 复用运行中的队列服务，避免新实例导致状态丢失
    queue_service = _running_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryVulnerabilityQueue()
    
    # 清空队列
    success = queue_service.clear_queue(task_id)
    
    return {
        "success": success,
        "task_id": task_id,
        "message": "队列已清空" if success else "清空队列失败",
    }


@router.get("/tasks/{task_id}/recon_risk_queue/status", response_model=Dict[str, Any])
async def get_recon_risk_queue_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue

    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await db.get(Project, task.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    queue_service = _running_recon_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryReconRiskQueue()

    stats = queue_service.stats(task_id)

    return {
        "success": True,
        "task_id": task_id,
        "queue_stats": stats,
    }


@router.get("/tasks/{task_id}/recon_risk_queue/peek", response_model=Dict[str, Any])
async def peek_recon_risk_queue(
    task_id: str,
    limit: int = 3,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue

    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await db.get(Project, task.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    queue_service = _running_recon_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryReconRiskQueue()

    findings = queue_service.peek(task_id, limit=min(limit, 10))

    return {
        "success": True,
        "task_id": task_id,
        "findings": findings,
        "count": len(findings),
    }


@router.delete("/tasks/{task_id}/recon_risk_queue", response_model=Dict[str, Any])
async def clear_recon_risk_queue(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue

    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await db.get(Project, task.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    queue_service = _running_recon_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryReconRiskQueue()

    success = queue_service.clear(task_id)

    return {
        "success": success,
        "task_id": task_id,
        "message": "Recon 队列已清空" if success else "清空 Recon 队列失败",
    }


# ====================  业务逻辑风险队列接口 ====================

@router.get("/tasks/{task_id}/business_logic_risk_queue/status", response_model=Dict[str, Any])
async def get_bl_risk_queue_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.business_logic_risk_queue import InMemoryBusinessLogicRiskQueue

    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await db.get(Project, task.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    queue_service = _running_bl_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryBusinessLogicRiskQueue()

    stats = queue_service.stats(task_id)

    return {
        "success": True,
        "task_id": task_id,
        "queue_stats": stats,
    }


@router.get("/tasks/{task_id}/business_logic_risk_queue/peek", response_model=Dict[str, Any])
async def peek_bl_risk_queue(
    task_id: str,
    limit: int = 3,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.business_logic_risk_queue import InMemoryBusinessLogicRiskQueue

    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await db.get(Project, task.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    queue_service = _running_bl_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryBusinessLogicRiskQueue()

    findings = queue_service.peek(task_id, limit=min(limit, 10))

    return {
        "success": True,
        "task_id": task_id,
        "findings": findings,
        "count": len(findings),
    }


@router.delete("/tasks/{task_id}/business_logic_risk_queue", response_model=Dict[str, Any])
async def clear_bl_risk_queue_endpoint(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    from app.services.agent.business_logic_risk_queue import InMemoryBusinessLogicRiskQueue

    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await db.get(Project, task.project_id)
    if not project or project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    queue_service = _running_bl_queue_services.get(task_id)
    if queue_service is None:
        queue_service = InMemoryBusinessLogicRiskQueue()

    success = queue_service.clear(task_id)

    return {
        "success": success,
        "task_id": task_id,
        "message": "业务逻辑风险队列已清空" if success else "清空业务逻辑风险队列失败",
    }


# ====================  综合进度接口 ====================

@router.get("/{task_id}/progress", response_model=Dict[str, Any])
async def get_task_progress(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    获取任务综合进度信息（整合三类信息）
    
    返回：
    - task: 任务基本信息和状态
    - recon_queue: Recon 队列统计
    - analysis_queue: Analysis 候选漏洞队列统计
    - verification: 验证后漏洞统计和分布
    """
    from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
    from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue

    # 获取任务信息
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 权限检查（仅检查项目存在，与其他接口保持一致）
    if project.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    # 1. Recon 队列状态
    recon_queue_service = _running_recon_queue_services.get(task_id)
    if recon_queue_service is None:
        recon_queue_service = InMemoryReconRiskQueue()
    recon_stats = recon_queue_service.stats(task_id)

    # 2. Analysis 队列状态
    vuln_queue_service = _running_queue_services.get(task_id)
    if vuln_queue_service is None:
        vuln_queue_service = InMemoryVulnerabilityQueue()
    analysis_stats = vuln_queue_service.get_queue_stats(task_id)

    # 3. Verification 统计（从数据库）
    findings_query = select(AgentFinding).where(AgentFinding.task_id == task_id)
    findings_result = await db.execute(findings_query)
    all_findings = findings_result.scalars().all()

    verified_findings = [f for f in all_findings if f.is_verified]
    false_positives = [f for f in all_findings if f.status == FindingStatus.FALSE_POSITIVE]
    
    # 按严重程度分布
    severity_distribution = {
        "critical": sum(1 for f in all_findings if f.severity == VulnerabilitySeverity.CRITICAL),
        "high": sum(1 for f in all_findings if f.severity == VulnerabilitySeverity.HIGH),
        "medium": sum(1 for f in all_findings if f.severity == VulnerabilitySeverity.MEDIUM),
        "low": sum(1 for f in all_findings if f.severity == VulnerabilitySeverity.LOW),
        "info": sum(1 for f in all_findings if f.severity == VulnerabilitySeverity.INFO),
    }

    # 按漏洞类型分布
    vulnerability_types: Dict[str, int] = {}
    for finding in all_findings:
        vuln_type = finding.vulnerability_type or "unknown"
        vulnerability_types[vuln_type] = vulnerability_types.get(vuln_type, 0) + 1

    # 4. 任务整体进度
    task_info = {
        "task_id": task.id,
        "project_id": task.project_id,
        "status": task.status,
        "current_phase": task.current_phase,
        "current_step": task.current_step,
        "progress_percentage": task.progress_percentage,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "error_message": task.error_message,
    }

    return {
        "success": True,
        "task": task_info,
        "recon_queue": {
            "current_size": recon_stats.get("current_size", 0),
            "total_enqueued": recon_stats.get("total_enqueued", 0),
            "total_dequeued": recon_stats.get("total_dequeued", 0),
            "total_deduplicated": recon_stats.get("total_deduplicated", 0),
        },
        "analysis_queue": {
            "current_size": analysis_stats.get("current_size", 0),
            "total_enqueued": analysis_stats.get("total_enqueued", 0),
            "total_dequeued": analysis_stats.get("total_dequeued", 0),
            "total_deduplicated": analysis_stats.get("total_deduplicated", 0),
        },
        "verification": {
            "total_findings": len(all_findings),
            "verified_count": len(verified_findings),
            "false_positive_count": len(false_positives),
            "severity_distribution": severity_distribution,
            "vulnerability_types": vulnerability_types,
        },
    }
