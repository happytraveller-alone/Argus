"""Runtime state and retry/finalization helpers for agent tasks."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_task import AgentTask, AgentTaskStatus, AgentTreeNode
from app.services.agent.event_manager import EventManager
from app.services.project_metrics import project_metrics_refresher

logger = logging.getLogger(__name__)

_running_tasks: Dict[str, Any] = {}
_running_asyncio_tasks: Dict[str, asyncio.Task] = {}
_running_queue_services: Dict[str, Any] = {}
_running_recon_queue_services: Dict[str, Any] = {}
_running_bl_queue_services: Dict[str, Any] = {}
_running_orchestrators: Dict[str, Any] = {}
_running_event_managers: Dict[str, EventManager] = {}
#  已取消的任务集合（用于前置操作的取消检查）
_cancelled_tasks: Set[str] = set()
TOOL_DRAIN_TIMEOUT_SECONDS = 180


def is_task_cancelled(task_id: str) -> bool:
    """检查任务是否已被取消"""
    return task_id in _cancelled_tasks


def _build_tool_drain_metadata(drain_result: Dict[str, Any]) -> Dict[str, Any]:
    pending_calls = drain_result.get("pending_tool_calls")
    if not isinstance(pending_calls, list):
        pending_calls = []
    return {
        "tool_drain_wait_ms": int(drain_result.get("elapsed_ms") or 0),
        "tool_drain_timeout": bool(drain_result.get("timed_out", False)),
        "pending_tool_calls": pending_calls[:50],
    }


async def _finalize_task_terminal_state(
    *,
    db: AsyncSession,
    task: AgentTask,
    task_id: str,
    event_emitter: Any,
    event_manager: Optional[EventManager],
    desired_status: str,
    success_payload: Optional[Dict[str, Any]] = None,
    failure_message: Optional[str] = None,
    failure_metadata: Optional[Dict[str, Any]] = None,
    verification_gate_message: Optional[str] = None,
    verification_gate_metadata: Optional[Dict[str, Any]] = None,
    cancel_message: Optional[str] = None,
    skip_drain_wait: bool = False,
    timeout_seconds: int = TOOL_DRAIN_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    if skip_drain_wait:
        drain_result = {
            "ready": True,
            "timed_out": False,
            "elapsed_ms": 0,
            "pending_tool_calls": [],
        }
    else:
        drain_result = await _wait_for_terminal_tool_drain(
            event_manager=event_manager,
            task_id=task_id,
            skip_wait=False,
            timeout_seconds=timeout_seconds,
        )
    drain_metadata = _build_tool_drain_metadata(drain_result)

    final_status = str(desired_status or AgentTaskStatus.FAILED)
    final_failure_message = str(failure_message or "").strip() or None
    final_failure_metadata = dict(failure_metadata or {})

    if bool(drain_result.get("timed_out")) and final_status != AgentTaskStatus.CANCELLED:
        final_status = AgentTaskStatus.FAILED
        final_failure_message = "终态收敛超时：存在未完成工具调用，已将任务标记为失败。"
        final_failure_metadata = {
            "step_name": "TERMINAL_TOOL_DRAIN",
            "attempt": 1,
            "retry_attempt": 1,
            "max_attempts": 1,
            "is_terminal": True,
            "retry_error_class": "tool_drain_timeout",
            "retryable": False,
            "cancel_origin": "none",
            **drain_metadata,
        }
    elif (
        final_status != AgentTaskStatus.CANCELLED
        and str(verification_gate_message or "").strip()
    ):
        final_status = AgentTaskStatus.FAILED
        final_failure_message = str(verification_gate_message).strip()
        final_failure_metadata = {
            "step_name": "VERIFICATION_PENDING_GATE",
            "attempt": 1,
            "retry_attempt": 1,
            "max_attempts": 1,
            "is_terminal": True,
            "retry_error_class": "verification_pending_gate",
            "retryable": False,
            "cancel_origin": "none",
            **dict(verification_gate_metadata or {}),
            **drain_metadata,
        }
    elif final_status == AgentTaskStatus.FAILED:
        final_failure_metadata = {
            **final_failure_metadata,
            **drain_metadata,
        }

    task.status = final_status
    task.completed_at = datetime.now(timezone.utc)
    if final_status == AgentTaskStatus.FAILED:
        task.error_message = final_failure_message or "Unknown error"
    else:
        task.error_message = None
    await db.commit()
    project_id = getattr(task, "project_id", None)
    if project_id:
        project_metrics_refresher.enqueue(project_id)

    if final_status == AgentTaskStatus.COMPLETED:
        payload = dict(success_payload or {})
        extra_metadata = {
            **dict(payload.get("extra_metadata") or {}),
            **drain_metadata,
        }
        await event_emitter.emit_task_complete(
            findings_count=int(payload.get("findings_count") or 0),
            duration_ms=int(payload.get("duration_ms") or 0),
            message=payload.get("message"),
            extra_metadata=extra_metadata,
        )
    elif final_status == AgentTaskStatus.CANCELLED:
        await event_emitter.emit_task_cancelled(cancel_message or "任务已取消")
    else:
        emit_message = task.error_message or "Unknown error"
        await event_emitter.emit_task_error(
            emit_message,
            message=f"任务失败: {emit_message}",
            metadata=final_failure_metadata,
        )
        await event_emitter.emit_error(
            emit_message,
            metadata=final_failure_metadata,
        )

    return {
        "status": final_status,
        "drain_result": drain_result,
        "drain_metadata": drain_metadata,
        "failure_message": task.error_message,
        "failure_metadata": final_failure_metadata,
    }


def _compute_verification_pending_gate(
    verification_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    candidate_count = 0
    pending_count = 0
    pending_examples: List[Dict[str, Any]] = []
    payload = verification_payload if isinstance(verification_payload, dict) else {}
    todo_summary = (
        payload.get("verification_todo_summary")
        if isinstance(payload.get("verification_todo_summary"), dict)
        else {}
    )

    candidate_raw = payload.get("candidate_count")
    if candidate_raw is None and isinstance(todo_summary, dict):
        candidate_raw = todo_summary.get("total")
    if candidate_raw is None:
        findings_snapshot = payload.get("findings")
        if isinstance(findings_snapshot, list):
            candidate_raw = len(findings_snapshot)
    try:
        candidate_count = max(0, int(candidate_raw or 0))
    except Exception:
        candidate_count = 0

    pending_raw = (
        todo_summary.get("pending")
        if isinstance(todo_summary, dict)
        else None
    )
    try:
        pending_count = max(0, int(pending_raw or 0))
    except Exception:
        pending_count = 0

    compact_items = (
        todo_summary.get("per_item_compact")
        if isinstance(todo_summary, dict)
        else None
    )
    if not isinstance(compact_items, list):
        compact_items = payload.get("todo_list")
    if isinstance(compact_items, list):
        for item in compact_items:
            if not isinstance(item, dict):
                continue
            status_text = str(item.get("status") or "").strip().lower()
            if status_text not in {"pending", "running", "unverified", "verifying"}:
                continue
            pending_examples.append(
                {
                    "id": str(item.get("id") or ""),
                    "status": status_text,
                    "title": str(item.get("title") or "")[:200],
                }
            )
        if pending_count <= 0:
            pending_count = len(pending_examples)
    if pending_examples:
        pending_examples = pending_examples[:5]

    triggered = candidate_count > 0 and pending_count > 0
    message = ""
    if triggered:
        message = (
            "verification_pending_gate:"
            f"candidate_count={candidate_count},"
            f"pending_count={pending_count}"
        )
    return {
        "triggered": triggered,
        "message": message,
        "candidate_count": candidate_count,
        "pending_count": pending_count,
        "pending_examples": pending_examples,
    }


async def _wait_for_terminal_tool_drain(
    *,
    event_manager: Optional[EventManager],
    task_id: str,
    skip_wait: bool = False,
    timeout_seconds: int = TOOL_DRAIN_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    if skip_wait:
        return {
            "ready": True,
            "timed_out": False,
            "elapsed_ms": 0,
            "pending_tool_calls": [],
        }
    if not event_manager:
        return {
            "ready": True,
            "timed_out": False,
            "elapsed_ms": 0,
            "pending_tool_calls": [],
        }
    try:
        return await event_manager.wait_for_tool_drain(
            task_id,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        logger.warning("[TaskDrain] wait_for_tool_drain failed for %s: %s", task_id, exc)
        return {
            "ready": False,
            "timed_out": True,
            "elapsed_ms": 0,
            "pending_tool_calls": [],
        }


class StepRetryExceededError(RuntimeError):
    """关键步骤重试耗尽"""

    def __init__(
        self,
        step_name: str,
        attempts: int,
        last_error: Exception,
        *,
        max_attempts: int,
    ):
        self.step_name = step_name
        self.attempts = attempts
        self.max_attempts = max_attempts
        self.last_error = last_error
        self.final_message = (
            f"[{step_name}] 第 {attempts}/{max_attempts} 次失败: "
            f"{_safe_retry_error(last_error)}; 已中止任务"
        )
        super().__init__(self.final_message)


def _safe_retry_error(error: Exception, limit: int = 320) -> str:
    text = str(error or "").strip() or error.__class__.__name__
    return text[:limit]


def _build_retry_message(
    step_name: str,
    attempt: int,
    max_attempts: int,
    error: Exception,
    *,
    is_terminal: bool,
) -> str:
    suffix = "已中止任务" if is_terminal else "准备重试"
    return (
        f"[{step_name}] 第 {attempt}/{max_attempts} 次失败: "
        f"{_safe_retry_error(error)}; {suffix}"
    )


def _classify_retry_error(exc_or_text: Any) -> Dict[str, Any]:
    text = str(exc_or_text or "").strip()
    lowered = text.lower()

    def _contains(*tokens: str) -> bool:
        return any(token in lowered for token in tokens if token)

    if _contains(
        "schema",
        "jsonschema",
        "validationerror",
        "pydantic",
        "type_error",
        "is not of type",
        "extra fields not permitted",
        "unexpected field",
    ):
        return {
            "code": "schema_hard_error",
            "category": "schema_validation",
            "retryable": False,
        }

    if _contains(
        "permission denied",
        "forbidden",
        "路径不在允许范围",
        "安全错误",
        "outside allowed scope",
        "write_scope_path_forbidden",
        "write_scope_not_allowed",
    ):
        return {
            "code": "permission_or_scope_error",
            "category": "permission",
            "retryable": False,
        }

    if _contains("timeout", "timed out", "超时", "deadline exceeded"):
        return {
            "code": "timeout_error",
            "category": "timeout",
            "retryable": True,
        }

    if _contains(
        "adapter_unavailable",
        "domain_adapter_missing",
        "command_not_found",
        "tool_failed",
        "missing_stdio_command",
    ):
        return {
            "code": "tool_runtime_error",
            "category": "runtime",
            "retryable": True,
        }

    if _contains(
        "connection reset",
        "connection aborted",
        "temporary failure",
        "network",
        "dns",
        "503",
        "502",
        "429",
        "too many requests",
        "rate limit",
    ):
        return {
            "code": "network_transient_error",
            "category": "network",
            "retryable": True,
        }

    if _contains(
        "参数校验失败",
        "必须提供",
        "missing required",
        "required field",
        "工具参数缺失",
        "missing parameter",
        "input_repaired",
    ):
        return {
            "code": "repairable_validation_error",
            "category": "validation_repairable",
            "retryable": True,
        }

    return {
        "code": "unknown_error",
        "category": "unknown",
        "retryable": True,
    }


def _detect_cancel_origin(task_id: str, error: Optional[BaseException] = None) -> str:
    # task_cancel 事件会先写入 _cancelled_tasks，优先视为用户取消。
    if is_task_cancelled(task_id):
        return "user"
    lowered = str(error or "").strip().lower()
    if "system_cancelled" in lowered or "cancel_origin=system" in lowered:
        return "system"
    # 无明确系统取消标识时，按用户取消处理，避免误重试。
    return "user"


async def _run_with_retries(
    step_name: str,
    task_id: str,
    event_emitter: Any,
    func: Callable[[], Any],
    *,
    max_attempts: int = 3,
    retryable_predicate: Optional[Callable[[Exception], bool]] = None,
):
    """执行关键步骤并在失败时重试，重试耗尽后抛出 StepRetryExceededError。"""
    safe_attempts = max(1, int(max_attempts))

    for attempt in range(1, safe_attempts + 1):
        try:
            return await func()
        except asyncio.CancelledError as exc:
            cancel_origin = _detect_cancel_origin(task_id, exc)
            classification = {
                "code": "cancelled_user" if cancel_origin == "user" else "cancelled_system",
                "category": "cancel",
                "retryable": cancel_origin == "system",
            }
            retryable = bool(classification["retryable"])
            is_terminal = cancel_origin == "user" or attempt >= safe_attempts or not retryable
            message = (
                f"[{step_name}] 第 {attempt}/{safe_attempts} 次取消: "
                f"origin={cancel_origin}; {'已中止任务' if is_terminal else '准备重试'}"
            )
            metadata = {
                "task_id": task_id,
                "step_name": step_name,
                "attempt": attempt,
                "retry_attempt": attempt,
                "max_attempts": safe_attempts,
                "is_terminal": is_terminal,
                "retry_error_class": classification["code"],
                "retryable": retryable,
                "cancel_origin": cancel_origin,
            }
            if event_emitter:
                if is_terminal:
                    await event_emitter.emit_error(message, metadata=metadata)
                else:
                    await event_emitter.emit_warning(message, metadata=metadata)

            if cancel_origin == "user":
                raise

            if is_terminal:
                raise StepRetryExceededError(
                    step_name,
                    attempt,
                    RuntimeError("系统取消后重试耗尽"),
                    max_attempts=safe_attempts,
                ) from exc
            await asyncio.sleep(min(2, attempt))
            continue
        except Exception as exc:
            classification = _classify_retry_error(exc)
            retryable = bool(classification["retryable"])
            if retryable_predicate is not None:
                retryable = bool(retryable_predicate(exc)) and retryable
            is_terminal = attempt >= safe_attempts or not retryable
            message = _build_retry_message(
                step_name,
                attempt,
                safe_attempts,
                exc,
                is_terminal=is_terminal,
            )
            metadata = {
                "task_id": task_id,
                "step_name": step_name,
                "attempt": attempt,
                "retry_attempt": attempt,
                "max_attempts": safe_attempts,
                "is_terminal": is_terminal,
                "retry_error_class": classification["code"],
                "retryable": retryable,
                "cancel_origin": "none",
            }
            if event_emitter:
                if is_terminal:
                    await event_emitter.emit_error(message, metadata=metadata)
                else:
                    await event_emitter.emit_warning(message, metadata=metadata)
            if is_terminal:
                raise StepRetryExceededError(
                    step_name,
                    attempt,
                    exc,
                    max_attempts=safe_attempts,
                ) from exc
            await asyncio.sleep(min(2, attempt))

def _collect_orchestrator_stats(orchestrator: Any) -> Dict[str, int]:
    """
    收集 orchestrator + sub agents 统计快照。

    返回字段：
    - iterations
    - tool_calls
    - tokens_used
    """
    totals = {
        "iterations": 0,
        "tool_calls": 0,
        "tokens_used": 0,
    }
    if not orchestrator or not hasattr(orchestrator, "get_stats"):
        return totals

    try:
        stats = orchestrator.get_stats() or {}
    except Exception:
        stats = {}

    totals["iterations"] = int(stats.get("iterations") or 0)
    totals["tool_calls"] = int(stats.get("tool_calls") or 0)
    totals["tokens_used"] = int(stats.get("tokens_used") or 0)

    if hasattr(orchestrator, "sub_agents"):
        for agent in (getattr(orchestrator, "sub_agents", {}) or {}).values():
            if not hasattr(agent, "get_stats"):
                continue
            try:
                sub_stats = agent.get_stats() or {}
            except Exception:
                continue
            totals["iterations"] += int(sub_stats.get("iterations") or 0)
            totals["tool_calls"] += int(sub_stats.get("tool_calls") or 0)
            totals["tokens_used"] += int(sub_stats.get("tokens_used") or 0)

    return totals


def _snapshot_runtime_stats_to_task(task: AgentTask, orchestrator: Any) -> Dict[str, int]:
    """
    将运行时统计快照写入 task，并使用 max 保留历史更大值。
    """
    snapshot = _collect_orchestrator_stats(orchestrator)

    task.total_iterations = max(int(task.total_iterations or 0), int(snapshot["iterations"]))
    task.tool_calls_count = max(int(task.tool_calls_count or 0), int(snapshot["tool_calls"]))
    task.tokens_used = max(int(task.tokens_used or 0), int(snapshot["tokens_used"]))
    return snapshot


async def _save_agent_tree(db: AsyncSession, task_id: str) -> None:
    """
    保存 Agent 树到数据库

     在任务完成前调用，将内存中的 Agent 树持久化到数据库
    """
    from app.models.agent_task import AgentTreeNode
    from app.services.agent.core import agent_registry

    try:
        tree = agent_registry.get_agent_tree(task_id=task_id)
        nodes = tree.get("nodes", {})

        await db.execute(delete(AgentTreeNode).where(AgentTreeNode.task_id == task_id))

        if not nodes:
            logger.warning(f"[SaveAgentTree] No agent nodes to save for task {task_id}")
            await db.commit()
            return

        logger.info(f"[SaveAgentTree] Saving {len(nodes)} agent nodes for task {task_id}")

        # 计算每个节点的深度
        def get_depth(agent_id: str, visited: set = None) -> int:
            if visited is None:
                visited = set()
            if agent_id in visited:
                return 0
            visited.add(agent_id)
            node = nodes.get(agent_id)
            if not node:
                return 0
            parent_id = node.get("parent_id")
            if not parent_id:
                return 0
            return 1 + get_depth(parent_id, visited)

        saved_count = 0
        for agent_id, node_data in nodes.items():
            # 获取 Agent 实例的统计数据
            agent_instance = agent_registry.get_agent(agent_id)
            iterations = 0
            tool_calls = 0
            tokens_used = 0

            if agent_instance and hasattr(agent_instance, 'get_stats'):
                stats = agent_instance.get_stats()
                iterations = stats.get("iterations", 0)
                tool_calls = stats.get("tool_calls", 0)
                tokens_used = stats.get("tokens_used", 0)

            # 从结果中获取发现数量
            findings_count = 0
            result_summary = None
            if node_data.get("result"):
                result = node_data.get("result", {})
                if isinstance(result, dict):
                    findings_count = len(result.get("findings", []))
                    if result.get("summary"):
                        result_summary = str(result.get("summary"))[:2000]

            tree_node = AgentTreeNode(
                id=str(uuid4()),
                task_id=task_id,
                agent_id=agent_id,
                agent_name=node_data.get("name", "Unknown"),
                agent_type=node_data.get("type", "unknown"),
                parent_agent_id=node_data.get("parent_id"),
                depth=get_depth(agent_id),
                task_description=node_data.get("task"),
                knowledge_modules=node_data.get("knowledge_modules"),
                status=node_data.get("status", "unknown"),
                result_summary=result_summary,
                findings_count=findings_count,
                iterations=iterations,
                tool_calls=tool_calls,
                tokens_used=tokens_used,
            )
            db.add(tree_node)
            saved_count += 1

        await db.commit()
        logger.info(f"[SaveAgentTree] Successfully saved {saved_count} agent nodes to database")

    except Exception as e:
        logger.error(f"[SaveAgentTree] Failed to save agent tree: {e}", exc_info=True)
        await db.rollback()


__all__ = [name for name in globals() if not name.startswith("__")]
