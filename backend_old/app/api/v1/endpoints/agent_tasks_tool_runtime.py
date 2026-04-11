"""Tool runtime helpers, write-scope guard, and tool documentation sync for agent tasks."""

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.services.agent.write_scope import (
    HARD_MAX_WRITABLE_FILES_PER_TASK,
    TaskWriteScopeGuard,
)

logger = logging.getLogger(__name__)


def build_task_write_scope_guard(
    *,
    project_root: str,
    target_files: Optional[List[str]] = None,
    bootstrap_findings: Optional[List[dict]] = None,
) -> TaskWriteScopeGuard:
    """Build and seed a TaskWriteScopeGuard for a given task."""
    from app.core.config import settings

    normalized_project_root = os.path.abspath(project_root)

    hard_limit = max(1, int(getattr(settings, "AGENT_WRITE_SCOPE_HARD_LIMIT", HARD_MAX_WRITABLE_FILES_PER_TASK)))
    configured_max = getattr(settings, "AGENT_WRITE_SCOPE_DEFAULT_MAX_FILES", hard_limit)
    try:
        max_writable_files = int(configured_max)
    except Exception:
        max_writable_files = hard_limit
    max_writable_files = max(1, min(max_writable_files, hard_limit))

    write_guard = TaskWriteScopeGuard(
        project_root=normalized_project_root,
        max_writable_files_per_task=max_writable_files,
        require_evidence_binding=bool(
            getattr(settings, "AGENT_WRITE_SCOPE_REQUIRE_EVIDENCE_BINDING", True)
        ),
        forbid_project_wide_writes=bool(
            getattr(settings, "AGENT_WRITE_SCOPE_FORBID_PROJECT_WIDE_WRITES", True)
        ),
    )
    write_guard.seed_from_task_inputs(target_files=target_files, findings=bootstrap_findings or [])
    return write_guard


async def _run_task_llm_connection_test(
    *,
    llm_service: Any,
    event_emitter: Optional[Any] = None,
) -> Dict[str, Any]:
    if event_emitter:
        await event_emitter.emit_info(
            "🧪 正在测试 LLM 连接...",
            metadata={"step_name": "LLM_CONNECTION_TEST", "status": "running"},
        )
    started_at = time.perf_counter()
    response = await llm_service.chat_completion_raw(
        [{"role": "user", "content": "Say Hello in one word."}],
    )
    content = str(response.get("content") or "").strip()
    if not content:
        raise RuntimeError("LLM 测试返回空响应")
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    usage = dict(response.get("usage") or {}) if isinstance(response, dict) else {}
    if event_emitter:
        await event_emitter.emit_info(
            f"LLM 连接测试通过 ({elapsed_ms}ms)",
            metadata={
                "step_name": "LLM_CONNECTION_TEST",
                "status": "completed",
                "elapsed_ms": elapsed_ms,
                "response_preview": content[:32],
                "usage": usage,
            },
        )
    return {"elapsed_ms": elapsed_ms, "response_preview": content[:32], "usage": usage}


def _sync_tool_catalog_to_memory(
    *,
    memory_store: Any,
    task_id: str,
    max_chars: int,
) -> None:
    """同步共享工具目录到 Markdown memory shared.md（追加式，保留历史）。"""
    catalog_path = Path(__file__).resolve().parents[4] / "docs" / "agent-tools" / "TOOL_SHARED_CATALOG.md"
    if not catalog_path.exists():
        return

    try:
        content = catalog_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("[ToolDocSync] read catalog failed: %s", exc)
        return

    clipped = content[: max(0, int(max_chars))]
    if not clipped.strip():
        return

    try:
        memory_store.append_entry(
            "shared",
            task_id=task_id,
            source="tool_catalog_sync",
            title="工具共享目录同步",
            summary="将 TOOL_SHARED_CATALOG.md 摘要同步到 shared memory，供各 Agent 提示词检出。",
            payload={
                "catalog_path": str(catalog_path),
                "max_chars": int(max_chars),
                "content": clipped,
            },
        )
    except Exception as exc:
        logger.warning("[ToolDocSync] append shared entry failed: %s", exc)


def _load_tool_playbook(*, max_chars: int) -> Tuple[Optional[Path], str]:
    docs_root = Path(__file__).resolve().parents[4] / "docs" / "agent-tools"
    playbook_path = docs_root / "TOOL_PLAYBOOK.md"
    if not playbook_path.exists():
        return None, ""
    try:
        content = playbook_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("[ToolDocSync] read tool playbook failed: %s", exc)
        return playbook_path, ""
    clipped = content[: max(0, int(max_chars))]
    return playbook_path, clipped


def _sync_tool_playbook_to_memory(
    *,
    memory_store: Any,
    task_id: str,
    max_chars: int,
) -> None:
    playbook_path, playbook_content = _load_tool_playbook(max_chars=max_chars)
    if not playbook_path or not playbook_content.strip():
        return
    try:
        memory_store.append_entry(
            "shared",
            task_id=task_id,
            source="tool_playbook_sync",
            title="工具说明同步",
            summary="将 TOOL_PLAYBOOK.md 同步到 shared memory，供各 Agent 快速检索标准工具调用方式。",
            payload={
                "playbook_path": str(playbook_path),
                "max_chars": int(max_chars),
                "content": playbook_content,
            },
        )
    except Exception as exc:
        logger.warning("[ToolDocSync] append tool playbook failed: %s", exc)


def _build_tool_skills_snapshot(*, max_chars: int) -> str:
    docs_root = Path(__file__).resolve().parents[4] / "docs" / "agent-tools"
    index_path = docs_root / "SKILLS_INDEX.md"
    skills_dir = docs_root / "skills"
    preferred_skill_order = [
        "push_finding_to_queue.skill.md",
        "get_recon_risk_queue_status.skill.md",
        "search_code.skill.md",
        "list_files.skill.md",
        "get_code_window.skill.md",
        "get_file_outline.skill.md",
        "get_function_summary.skill.md",
        "get_symbol_body.skill.md",
        "locate_enclosing_function.skill.md",
        "function_context.skill.md",
    ]

    fragments: List[str] = []
    if index_path.exists():
        try:
            fragments.append(index_path.read_text(encoding="utf-8", errors="replace").strip())
        except Exception as exc:
            logger.warning("[ToolDocSync] read skills index failed: %s", exc)

    if skills_dir.exists():
        all_skill_docs = {doc.name: doc for doc in skills_dir.glob("*.skill.md")}
        ordered_skill_docs: List[Path] = []
        for preferred_name in preferred_skill_order:
            preferred_doc = all_skill_docs.pop(preferred_name, None)
            if preferred_doc is not None:
                ordered_skill_docs.append(preferred_doc)
        ordered_skill_docs.extend(all_skill_docs[name] for name in sorted(all_skill_docs.keys()))

        for skill_doc in ordered_skill_docs:
            try:
                fragments.append(skill_doc.read_text(encoding="utf-8", errors="replace").strip())
            except Exception as exc:
                logger.warning("[ToolDocSync] read skill doc failed (%s): %s", skill_doc, exc)

    _playbook_path, playbook_content = _load_tool_playbook(max_chars=max_chars)
    if playbook_content.strip():
        fragments.append(playbook_content.strip())

    snapshot = "\n\n---\n\n".join(item for item in fragments if str(item or "").strip())
    if not snapshot.strip():
        return ""
    return snapshot[: max(0, int(max_chars))]


def _sync_tool_skills_to_memory(
    *,
    memory_store: Any,
    task_id: str,
    max_chars: int,
) -> None:
    skill_snapshot = _build_tool_skills_snapshot(max_chars=max_chars)
    if not skill_snapshot:
        return

    if hasattr(memory_store, "write_skills_snapshot"):
        try:
            memory_store.write_skills_snapshot(
                skill_snapshot,
                source="tool_skill_sync",
                task_id=task_id,
            )
            return
        except Exception as exc:
            logger.warning("[ToolDocSync] write skills snapshot failed: %s", exc)

    try:
        memory_store.append_entry(
            "skills",
            task_id=task_id,
            source="tool_skill_sync",
            title="工具 skill 规范同步",
            summary="将文件读取相关 skill 文档同步到 skills memory。",
            payload={"content": skill_snapshot},
        )
    except Exception as exc:
        logger.warning("[ToolDocSync] append skills entry failed: %s", exc)


__all__ = [name for name in globals() if not name.startswith("__")]
