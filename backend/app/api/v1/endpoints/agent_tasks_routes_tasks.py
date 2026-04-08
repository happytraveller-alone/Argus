"""Task lifecycle and streaming routes for agent tasks."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.db.session import async_session_factory, get_db
from app.api.v1.endpoints.static_tasks_shared import _release_request_db_session
from app.models.agent_task import AgentEvent, AgentFinding, AgentTask, AgentTaskPhase, AgentTaskStatus
from app.models.project import Project
from app.models.user import User
from app.services.project_metrics import project_metrics_refresher

from .agent_tasks_access import build_agent_task_response
from .agent_tasks_bootstrap import *
from .agent_tasks_contracts import *
from .agent_tasks_execution import _execute_agent_task
from .agent_tasks_runtime import *

router = APIRouter()
logger = logging.getLogger(__name__)


async def _load_verified_severity_counts(
    db: AsyncSession,
    task_ids: List[str],
) -> Dict[str, Dict[str, int]]:
    if not task_ids:
        return {}

    normalized_status = func.lower(func.coalesce(AgentFinding.status, ""))
    normalized_verdict = func.lower(func.coalesce(AgentFinding.verdict, ""))
    rows = await db.execute(
        select(
            AgentFinding.task_id,
            func.sum(case((func.lower(AgentFinding.severity) == "critical", 1), else_=0)).label("critical"),
            func.sum(case((func.lower(AgentFinding.severity) == "high", 1), else_=0)).label("high"),
            func.sum(case((func.lower(AgentFinding.severity) == "medium", 1), else_=0)).label("medium"),
            func.sum(case((func.lower(AgentFinding.severity) == "low", 1), else_=0)).label("low"),
        )
        .where(
            AgentFinding.task_id.in_(task_ids),
            AgentFinding.is_verified.is_(True),
            normalized_status != "false_positive",
            normalized_verdict != "false_positive",
        )
        .group_by(AgentFinding.task_id)
    )

    counts_by_task: Dict[str, Dict[str, int]] = {}
    for task_id, critical, high, medium, low in rows.fetchall():
        counts_by_task[str(task_id)] = {
            "critical": int(critical or 0),
            "high": int(high or 0),
            "medium": int(medium or 0),
            "low": int(low or 0),
        }
    return counts_by_task


async def _load_defect_summaries(
    db: AsyncSession,
    task_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    if not task_ids:
        return {}

    normalized_status = func.lower(func.coalesce(AgentFinding.status, ""))
    normalized_verdict = func.lower(func.coalesce(AgentFinding.verdict, ""))
    normalized_severity = func.lower(func.coalesce(AgentFinding.severity, ""))

    false_positive_condition = (normalized_status == "false_positive") | (
        normalized_verdict == "false_positive"
    )
    verified_condition = (~false_positive_condition) & (
        AgentFinding.is_verified.is_(True) | (normalized_status == "verified")
    )
    pending_condition = (~false_positive_condition) & (~verified_condition)

    rows = await db.execute(
        select(
            AgentFinding.task_id,
            func.count(AgentFinding.id).label("total_count"),
            func.sum(case((normalized_severity == "critical", 1), else_=0)).label("critical"),
            func.sum(case((normalized_severity == "high", 1), else_=0)).label("high"),
            func.sum(case((normalized_severity == "medium", 1), else_=0)).label("medium"),
            func.sum(case((normalized_severity == "low", 1), else_=0)).label("low"),
            func.sum(case((normalized_severity == "info", 1), else_=0)).label("info"),
            func.sum(case((pending_condition, 1), else_=0)).label("pending"),
            func.sum(case((verified_condition, 1), else_=0)).label("verified"),
            func.sum(case((false_positive_condition, 1), else_=0)).label("false_positive"),
        )
        .where(AgentFinding.task_id.in_(task_ids))
        .group_by(AgentFinding.task_id)
    )

    summaries: Dict[str, Dict[str, Any]] = {}
    for (
        task_id,
        total_count,
        critical,
        high,
        medium,
        low,
        info,
        pending,
        verified,
        false_positive,
    ) in rows.fetchall():
        summaries[str(task_id)] = {
            "scope": "all_findings",
            "total_count": int(total_count or 0),
            "severity_counts": {
                "critical": int(critical or 0),
                "high": int(high or 0),
                "medium": int(medium or 0),
                "low": int(low or 0),
                "info": int(info or 0),
            },
            "status_counts": {
                "pending": int(pending or 0),
                "verified": int(verified or 0),
                "false_positive": int(false_positive or 0),
            },
        }
    return summaries

@router.post("/", response_model=AgentTaskResponse)
async def create_agent_task(
    request: AgentTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    创建并启动 Agent 审计任务
    """
    # 验证项目
    project = await db.get(Project, request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    if getattr(project, "source_type", None) != "zip":
        raise HTTPException(status_code=400, detail="仅支持 ZIP 项目")

    verification_level = _normalize_verification_level(request.verification_level)
    normalized_target_files = [
        item.strip()
        for item in (request.target_files or [])
        if isinstance(item, str) and item.strip()
    ]
    merged_exclude_patterns = _build_core_audit_exclude_patterns(request.exclude_patterns)
    normalized_audit_scope = (
        request.audit_scope if isinstance(request.audit_scope, dict) else None
    )
    if normalized_audit_scope is not None:
        source_mode = _resolve_agent_task_source_mode(request.name, request.description)
        _resolve_static_bootstrap_config(
            SimpleNamespace(audit_scope=normalized_audit_scope),
            source_mode,
        )
    
    # 创建任务
    task = AgentTask(
        id=str(uuid4()),
        project_id=project.id,
        name=request.name or f"Agent Audit - {datetime.now().strftime('%Y%m%d_%H%M%S')}",
        description=request.description,
        status=AgentTaskStatus.PENDING,
        current_phase=AgentTaskPhase.PLANNING,
        audit_scope=normalized_audit_scope,
        target_vulnerabilities=request.target_vulnerabilities,
        verification_level=verification_level,
        exclude_patterns=merged_exclude_patterns,
        target_files=normalized_target_files or None,
        agent_config={
            "authorization_confirmed": bool(request.authorization_confirmed),
            "use_prompt_skills": bool(request.use_prompt_skills),
            "tool_evidence_protocol": "native_v1",
        },
        max_iterations=request.max_iterations or 50,
        timeout_seconds=request.timeout_seconds or 1800,
        created_by=current_user.id,
    )
    
    db.add(task)
    await db.commit()
    response = build_agent_task_response(task)
    task_id = response.id
    project_metrics_refresher.enqueue(task.project_id)

    await _release_request_db_session(db)
    asyncio_task = asyncio.create_task(
        _execute_agent_task(task_id),
        name=f"agent_task:{task_id}",
    )
    _running_asyncio_tasks[task_id] = asyncio_task
    
    logger.info(f"Created agent task {task_id} for project {project.name}")
    
    return response


@router.get("/", response_model=List[AgentTaskResponse])
async def list_agent_tasks(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取 Agent 任务列表
    """
    # 获取用户的项目
    projects_result = await db.execute(
        select(Project.id).where(Project.owner_id == current_user.id)
    )
    user_project_ids = [p[0] for p in projects_result.fetchall()]
    
    if not user_project_ids:
        return []
    
    # 构建查询
    query = select(AgentTask).where(AgentTask.project_id.in_(user_project_ids))
    
    if project_id:
        query = query.where(AgentTask.project_id == project_id)
    
    if status:
        normalized_status = str(status).strip().lower()
        if normalized_status in _VALID_TASK_STATUS_VALUES:
            query = query.where(AgentTask.status == normalized_status)
    
    query = query.order_by(AgentTask.created_at.desc())
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    tasks = result.scalars().all()

    for task in tasks:
        task.verification_level = _normalize_verification_level(task.verification_level)

    verified_severity_counts = await _load_verified_severity_counts(
        db,
        [task.id for task in tasks],
    )
    defect_summaries = await _load_defect_summaries(
        db,
        [task.id for task in tasks],
    )
    return [
        build_agent_task_response(
            task,
            verified_severity_counts=verified_severity_counts.get(task.id),
            defect_summary=defect_summaries.get(task.id),
        )
        for task in tasks
    ]


@router.get("/{task_id}", response_model=AgentTaskResponse)
async def get_agent_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取 Agent 任务详情
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    # 检查权限
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    try:
        task.verification_level = _normalize_verification_level(task.verification_level)
        verified_severity_counts = await _load_verified_severity_counts(db, [task.id])
        defect_summaries = await _load_defect_summaries(db, [task.id])
        return build_agent_task_response(
            task,
            verified_severity_counts=verified_severity_counts.get(task.id),
            defect_summary=defect_summaries.get(task.id),
        )
    except Exception as e:
        logger.error(f"Error serializing task {task_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"序列化任务数据失败: {str(e)}")


@router.post("/{task_id}/cancel")
async def cancel_agent_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    取消 Agent 任务
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权操作此任务")

    if task.status in [AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED, AgentTaskStatus.INTERRUPTED]:
        raise HTTPException(status_code=400, detail="任务已结束，无法取消")

    #  0. 立即标记任务为已取消（用于前置操作的取消检查）
    _cancelled_tasks.add(task_id)
    logger.info(f"[Cancel] Added task {task_id} to cancelled set")

    #  1. 设置 Agent 的取消标志
    runner = _running_tasks.get(task_id)
    if runner:
        runner.cancel()
        logger.info(f"[Cancel] Set cancel flag for task {task_id}")

    #  2. 强制取消 asyncio Task（立即中断 LLM 调用）
    asyncio_task = _running_asyncio_tasks.get(task_id)
    if asyncio_task and not asyncio_task.done():
        asyncio_task.cancel()
        logger.info(f"[Cancel] Cancelled asyncio task for {task_id}")

    # 取消前固化运行时统计，避免中断后查询显示归零
    orchestrator = _running_orchestrators.get(task_id)
    _snapshot_runtime_stats_to_task(task, orchestrator)

    # 更新状态
    task.status = AgentTaskStatus.CANCELLED
    task.completed_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(f"[Cancel] Task {task_id} cancelled successfully")
    return {"message": "任务已取消", "task_id": task_id}


@router.get("/{task_id}/events")
async def stream_agent_events(
    task_id: str,
    after_sequence: int = Query(0, ge=0, description="从哪个序号之后开始"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    获取 Agent 事件流 (SSE)
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    await _release_request_db_session(db)
    
    async def event_generator():
        """生成 SSE 事件流"""
        last_sequence = after_sequence
        poll_interval = 0.5
        max_idle = 300  # 5 分钟无事件后关闭
        idle_time = 0
        
        while True:
            # 查询新事件
            async with async_session_factory() as session:
                result = await session.execute(
                    select(AgentEvent)
                    .where(AgentEvent.task_id == task_id)
                    .where(AgentEvent.sequence > last_sequence)
                    .order_by(AgentEvent.sequence)
                    .limit(50)
                )
                events = result.scalars().all()
                
                # 获取任务状态
                current_task = await session.get(AgentTask, task_id)
                task_status = current_task.status if current_task else None
            
            if events:
                idle_time = 0
                for event in events:
                    last_sequence = event.sequence
                    # event_type 已经是字符串，不需要 .value
                    event_type_str = str(event.event_type)
                    phase_str = str(event.phase) if event.phase else None
                    
                    data = {
                        "id": event.id,
                        "type": event_type_str,
                        "phase": phase_str,
                        "message": event.message,
                        "sequence": event.sequence,
                        "timestamp": event.created_at.isoformat() if event.created_at else None,
                        "progress_percent": event.progress_percent,
                        "tool_name": event.tool_name,
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            else:
                idle_time += poll_interval
            
            # 检查任务是否结束
            if task_status:
                # task_status 可能是字符串或枚举，统一转换为字符串
                status_str = str(task_status)
                if status_str in ["completed", "failed", "cancelled", "interrupted"]:
                    yield f"data: {json.dumps({'type': 'task_end', 'status': status_str})}\n\n"
                    break
            
            # 检查空闲超时
            if idle_time >= max_idle:
                yield f"data: {json.dumps({'type': 'timeout'})}\n\n"
                break
            
            await asyncio.sleep(poll_interval)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/{task_id}/stream")
async def stream_agent_with_thinking(
    task_id: str,
    include_thinking: bool = Query(True, description="是否包含 LLM 思考过程"),
    include_tool_calls: bool = Query(True, description="是否包含工具调用详情"),
    after_sequence: int = Query(0, ge=0, description="从哪个序号之后开始"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    增强版事件流 (SSE)
    
    支持:
    - LLM 思考过程的 Token 级流式输出 (仅运行时)
    - 工具调用的详细输入/输出
    - 节点执行状态
    - 发现事件
    
    优先使用内存中的事件队列 (支持 thinking_token)，
    如果任务未在运行，则回退到数据库轮询 (不支持 thinking_token 复盘)。
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    await _release_request_db_session(db)
    
    # 定义 SSE 格式化函数
    def format_sse_event(event_data: Dict[str, Any]) -> str:
        """格式化为 SSE 事件"""
        event_type = event_data.get("event_type") or event_data.get("type")
        
        # 统一字段
        if "type" not in event_data:
            event_data["type"] = event_type
            
        return f"event: {event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

    async def enhanced_event_generator():
        """生成增强版 SSE 事件流"""
        # 1. 检查任务是否在运行中 (内存)
        event_manager = _running_event_managers.get(task_id)
        
        if event_manager:
            logger.debug(f"Stream {task_id}: Using in-memory event manager")
            try:
                # 使用 EventManager 的流式接口
                # 过滤选项
                skip_types = set()
                if not include_thinking:
                    skip_types.update(["thinking_start", "thinking_token", "thinking_end"])
                if not include_tool_calls:
                    skip_types.update(["tool_call_start", "tool_call_input", "tool_call_output", "tool_call_end"])
                
                async for event in event_manager.stream_events(task_id, after_sequence=after_sequence):
                    event_type = event.get("event_type")
                    
                    if event_type in skip_types:
                        continue
                    
                    #  Debug: 记录 thinking_token 事件
                    if event_type == "thinking_token":
                        token = event.get("metadata", {}).get("token", "")[:20]
                        logger.debug(f"Stream {task_id}: Sending thinking_token: '{token}...'")
                        
                    # 格式化并 yield
                    yield format_sse_event(event)
                    
                    #  CRITICAL: 为 thinking_token 添加微小延迟
                    # 确保事件在不同的 TCP 包中发送，让前端能够逐个处理
                    # 没有这个延迟，所有 token 会在一次 read() 中被接收，导致 React 批量更新
                    if event_type == "thinking_token":
                        await asyncio.sleep(0.01)  # 10ms 延迟
                    
            except Exception as e:
                logger.error(f"In-memory stream error: {e}")
                err_data = {"type": "error", "message": str(e)}
                yield format_sse_event(err_data)
                
        else:
            logger.debug(f"Stream {task_id}: Task not running, falling back to DB polling")
            # 2. 回退到数据库轮询 (无法获取 thinking_token)
            last_sequence = after_sequence
            poll_interval = 2.0  # 完成的任务轮询可以慢一点
            heartbeat_interval = 15
            max_idle = 60  # 1分钟无事件关闭
            idle_time = 0
            last_heartbeat = 0
            
            skip_types = set()
            if not include_thinking:
                skip_types.update(["thinking_start", "thinking_token", "thinking_end"])
            
            while True:
                try:
                    async with async_session_factory() as session:
                        # 查询新事件
                        result = await session.execute(
                            select(AgentEvent)
                            .where(AgentEvent.task_id == task_id)
                            .where(AgentEvent.sequence > last_sequence)
                            .order_by(AgentEvent.sequence)
                            .limit(100)
                        )
                        events = result.scalars().all()
                        
                        # 获取任务状态
                        current_task = await session.get(AgentTask, task_id)
                        task_status = current_task.status if current_task else None
                    
                    if events:
                        idle_time = 0
                        for event in events:
                            last_sequence = event.sequence
                            event_type = str(event.event_type)
                            
                            if event_type in skip_types:
                                continue
                            
                            # 构建数据
                            data = {
                                "id": event.id,
                                "type": event_type,
                                "phase": str(event.phase) if event.phase else None,
                                "message": event.message,
                                "sequence": event.sequence,
                                "timestamp": event.created_at.isoformat() if event.created_at else None,
                            }
                            
                            # 添加详情
                            if include_tool_calls and event.tool_name:
                                data["tool"] = {
                                    "name": event.tool_name,
                                    "input": event.tool_input,
                                    "output": event.tool_output,
                                    "duration_ms": event.tool_duration_ms,
                                }
                                
                            if event.event_metadata:
                                data["metadata"] = event.event_metadata
                                
                            if event.tokens_used:
                                data["tokens_used"] = event.tokens_used
                            
                            yield format_sse_event(data)
                    else:
                        idle_time += poll_interval
                        
                        # 检查是否应该结束
                        if task_status:
                            status_str = str(task_status)
                            # 如果任务已完成且没有新事件，结束流
                            if status_str in ["completed", "failed", "cancelled", "interrupted"]:
                                end_data = {
                                    "type": "task_end",
                                    "status": status_str,
                                    "message": f"任务已{status_str}"
                                }
                                yield format_sse_event(end_data)
                                break
                    
                    # 心跳
                    last_heartbeat += poll_interval
                    if last_heartbeat >= heartbeat_interval:
                        last_heartbeat = 0
                        yield format_sse_event({"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()})
                    
                    # 超时
                    if idle_time >= max_idle:
                        break
                    
                    await asyncio.sleep(poll_interval)
                    
                except Exception as e:
                    logger.error(f"DB poll stream error: {e}")
                    yield format_sse_event({"type": "error", "message": str(e)})
                    break
    
    return StreamingResponse(
        enhanced_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8",
        }
    )


@router.get("/{task_id}/events/list", response_model=List[AgentEventResponse])
async def list_agent_events(
    task_id: str,
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    获取 Agent 事件列表
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    result = await db.execute(
        select(AgentEvent)
        .where(AgentEvent.task_id == task_id)
        .where(AgentEvent.sequence > after_sequence)
        .order_by(AgentEvent.sequence)
        .limit(limit)
    )
    events = result.scalars().all()

    #  Debug logging
    logger.debug(f"[EventsList] Task {task_id}: returning {len(events)} events (after_sequence={after_sequence})")
    if events:
        logger.debug(f"[EventsList] First event: type={events[0].event_type}, seq={events[0].sequence}")
        if len(events) > 1:
            logger.debug(f"[EventsList] Last event: type={events[-1].event_type}, seq={events[-1].sequence}")

    return events
