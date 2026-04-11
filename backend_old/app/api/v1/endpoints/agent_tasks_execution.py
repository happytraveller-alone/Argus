"""Task execution, tool initialization, and project preparation for agent tasks."""

import asyncio
import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.db.session import async_session_factory
from app.models.agent_task import (
    AgentFinding,
    AgentTask,
    AgentTaskPhase,
    AgentTaskStatus,
    FindingStatus,
)
from app.models.project import Project
from app.models.prompt_skill import PromptSkill
from app.services.project_metrics import project_metrics_refresher
from app.services.agent.write_scope import TaskWriteScopeGuard
from app.services.agent.skills.prompt_skills import (
    PROMPT_SKILL_AGENT_KEYS,
    PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY,
    apply_prompt_skill_builtin_state,
    build_effective_prompt_skills,
    build_prompt_skill_builtin_state,
    merge_prompt_skills_with_custom,
)

from .agent_tasks_bootstrap import *
from .agent_tasks_contracts import *
from .agent_tasks_findings import *
from .agent_tasks_tool_runtime import *
from .agent_tasks_runtime import *

logger = logging.getLogger(__name__)


def _normalize_terminal_agent_findings(
    findings: List[AgentFinding],
) -> List[AgentFinding]:
    """Normalize automatically generated findings to pending review on task end."""
    for item in findings:
        item.status = FindingStatus.NEEDS_REVIEW
        item.is_verified = False
        item.verified_at = None
        verification_result = (
            dict(item.verification_result)
            if isinstance(getattr(item, "verification_result", None), dict)
            else {}
        )
        verification_result["status"] = FindingStatus.NEEDS_REVIEW
        verification_result["verification_stage_completed"] = True
        item.verification_result = verification_result
    return findings

async def _execute_agent_task(task_id: str):
    """
    在后台执行 Agent 任务 - 使用动态 Agent 树架构
    
    架构：OrchestratorAgent 作为大脑，动态调度子 Agent
    """
    from app.services.agent.agents import OrchestratorAgent, ReconAgent, AnalysisAgent, VerificationAgent, ReportAgent, BusinessLogicReconAgent, BusinessLogicAnalysisAgent
    from app.services.agent.workflow import WorkflowOrchestratorAgent
    from app.services.agent.workflow.models import WorkflowConfig
    from app.services.agent.event_manager import EventManager, AgentEventEmitter
    from app.services.llm.service import LLMService, LLMConfigError
    from app.services.agent.core import agent_registry
    from app.services.agent.tools import SandboxManager
    from app.core.config import settings
    import time
    
    # 在任务最开始就初始化 Docker 沙箱管理器
    # 这样可以确保整个任务生命周期内使用同一个管理器，并且尽早发现 Docker 问题
    logger.info(f"Starting execution for task {task_id}")
    sandbox_manager = SandboxManager()
    await sandbox_manager.initialize()
    logger.info(f"🐳 Global Sandbox Manager initialized (Available: {sandbox_manager.is_available})")

    # 提前创建事件管理器，以便在克隆仓库和索引时发送实时日志
    from app.services.agent.event_manager import EventManager, AgentEventEmitter
    event_manager = EventManager(db_session_factory=async_session_factory)
    event_manager.create_queue(task_id)
    event_emitter = AgentEventEmitter(task_id, event_manager)
    _running_event_managers[task_id] = event_manager

    async with async_session_factory() as db:
        orchestrator = None
        write_scope_guard: Optional[TaskWriteScopeGuard] = None
        memory_store = None
        markdown_memory: Dict[str, str] = {}
        start_time = time.time()

        async def _set_current_step(step: str) -> None:
            task.current_step = step
            await db.commit()

        try:
            # 获取任务
            task = await db.get(AgentTask, task_id, options=[selectinload(AgentTask.project)])
            if not task:
                logger.error(f"Task {task_id} not found")
                return

            # 获取项目
            project = task.project
            if not project:
                logger.error(f"Project not found for task {task_id}")
                return

            # 发送任务开始事件 - 使用 phase_start 让前端知道进入准备阶段
            await event_emitter.emit_phase_start("preparation", f"任务开始执行: {project.name}")

            # 更新任务阶段为准备中
            task.status = AgentTaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            task.current_phase = AgentTaskPhase.PLANNING  # preparation 对应 PLANNING
            await db.commit()

            user_config = await _get_user_config(db, task.created_by)

            async def _prepare_project_root_once():
                return await _get_project_root(
                    project,
                    task_id,
                    event_emitter=event_emitter,
                )

            project_root = await _run_with_retries(
                "PROJECT_PREPARATION",
                task_id,
                event_emitter,
                _prepare_project_root_once,
            )
            normalized_project_root = os.path.abspath(project_root)

            # 自动修正 target_files 路径
            # 如果发生了目录调整（例如 ZIP 解压后只有一层目录，root 被下移），
            # 原有的 target_files (如 "Prefix/file.php") 可能无法匹配。
            # 我们需要检测并移除这些无效的前缀。
            if task.target_files and len(task.target_files) > 0:
                # 1. 检查是否存在不匹配的文件
                all_exist = True
                for tf in task.target_files:
                    if not os.path.exists(os.path.join(project_root, tf)):
                        all_exist = False
                        break
                
                if not all_exist:
                    logger.info(f"Target files path mismatch detected in {project_root}")
                    # 尝试通过路径匹配来修复
                    # 获取当前根目录的名称
                    root_name = os.path.basename(project_root)
                    
                    new_target_files = []
                    fixed_count = 0
                    
                    for tf in task.target_files:
                        # 检查文件是否以 root_name 开头（例如 "PHP-Project/index.php" 而 root 是 ".../PHP-Project"）
                        if tf.startswith(root_name + "/"):
                            fixed_path = tf[len(root_name)+1:]
                            if os.path.exists(os.path.join(project_root, fixed_path)):
                                new_target_files.append(fixed_path)
                                fixed_count += 1
                                continue
                        
                        # 如果上面的没匹配，尝试暴力搜索（只针对未找到的文件）
                        # 这种情况比较少见，先保留原样或标记为丢失
                        if os.path.exists(os.path.join(project_root, tf)):
                            new_target_files.append(tf)
                        else:
                            # 尝试查看 tf 的 basename 是否在根目录直接存在（针对常见的最简情况）
                            basename = os.path.basename(tf)
                            if os.path.exists(os.path.join(project_root, basename)):
                                new_target_files.append(basename)
                                fixed_count += 1
                            else:
                                # 实在找不到，保留原样，让后续流程报错或忽略
                                new_target_files.append(tf)
                    
                    if fixed_count > 0:
                        logger.info(f"Auto-fixed {fixed_count} target file paths")
                        await event_emitter.emit_info(f"自动修正了 {fixed_count} 个目标文件的路径")
                        task.target_files = new_target_files
                        
            # 重新验证修正后的文件
            valid_target_files = []
            if task.target_files:
                for tf in task.target_files:
                    if os.path.exists(os.path.join(project_root, tf)):
                        valid_target_files.append(tf)
                    else:
                        logger.warning(f"Target file not found: {tf}")
                
                if not valid_target_files:
                    logger.warning("No valid target files found after adjustment!")
                    await event_emitter.emit_warning("警告：无法找到指定的目标文件，将扫描所有文件")
                    task.target_files = None  # 回退到全量扫描
                elif len(valid_target_files) < len(task.target_files):
                    logger.warning(f"Partial target files missing. Found {len(valid_target_files)}/{len(task.target_files)}")
                    task.target_files = valid_target_files

            logger.info(f"Task {task_id} started with Dynamic Agent Tree architecture")

            # 获取项目根目录后检查取消
            if is_task_cancelled(task_id):
                logger.info(f"[Cancel] Task {task_id} cancelled after project preparation")
                raise asyncio.CancelledError("任务已取消")

            # await event_emitter.emit_info("QMD 任务知识库已移除，跳过任务内知识库初始化")

            # 创建 LLM 服务
            await _set_current_step("正在校验 LLM 配置")
            llm_service = LLMService(user_config=user_config)
            try:
                _ = llm_service.config
                await event_emitter.emit_info(
                    "LLM 配置校验通过",
                    metadata={"step_name": "LLM_CONFIG_VALIDATION", "status": "completed"},
                )
            except LLMConfigError as cfg_exc:
                cfg_message = f"LLM配置校验失败：{cfg_exc}"
                await event_emitter.emit_error(
                    cfg_message,
                    metadata={
                        "step_name": "LLM_CONFIG_VALIDATION",
                        "is_terminal": True,
                    },
                )
                raise RuntimeError(cfg_message) from cfg_exc

            await _set_current_step("正在测试 LLM 连接")

            async def _test_llm_connection_once():
                return await _run_task_llm_connection_test(
                    llm_service=llm_service,
                    event_emitter=event_emitter,
                )

            await _run_with_retries(
                "LLM_CONNECTION_TEST",
                task_id,
                event_emitter,
                _test_llm_connection_once,
            )

            # 初始化工具集 - 传递排除模式和目标文件以及预初始化的 sandbox_manager
            # 传递 event_emitter 以发送索引进度，传递 task_id 以支持取消
            task.current_phase = AgentTaskPhase.INDEXING
            await db.commit()

            # 创建漏洞队列服务
            from app.services.agent.vulnerability_queue import InMemoryVulnerabilityQueue
            from app.services.agent.recon_risk_queue import InMemoryReconRiskQueue
            from app.services.agent.business_logic_risk_queue import InMemoryBusinessLogicRiskQueue
            queue_service = InMemoryVulnerabilityQueue()
            recon_queue_service = InMemoryReconRiskQueue()
            bl_queue_service = InMemoryBusinessLogicRiskQueue()
            _running_queue_services[task_id] = queue_service
            _running_recon_queue_services[task_id] = recon_queue_service
            _running_bl_queue_services[task_id] = bl_queue_service
            logger.info(f"[Queue] Created InMemoryVulnerabilityQueue for task {task_id}")
            logger.info(f"[ReconQueue] Created InMemoryReconRiskQueue for task {task_id}")
            logger.info(f"[BLQueue] Created InMemoryBusinessLogicRiskQueue for task {task_id}")
            await event_emitter.emit_info("🔄 漏洞队列服务已初始化（内存模式）")
            await event_emitter.emit_info("🔎 Recon 风险点队列已初始化（内存模式）")

            async def _initialize_tools_once():
                return await _initialize_tools(
                    project_root,
                    llm_service,
                    user_config,
                    sandbox_manager=sandbox_manager,
                    verification_level=task.verification_level or "analysis_with_poc_plan",
                    exclude_patterns=task.exclude_patterns,
                    target_files=task.target_files,
                    project_id=str(project.id),
                    event_emitter=event_emitter,  # 新增
                    task_id=task_id,  # 新增：用于取消检查
                    queue_service=queue_service,  # 新增：漏洞队列服务
                    recon_queue_service=recon_queue_service,  # 新增：Recon 风险队列服务
                    bl_queue_service=bl_queue_service,  # 新增：业务逻辑风险队列服务
                )

            tools = await _run_with_retries(
                "TOOLS_INIT",
                task_id,
                event_emitter,
                _initialize_tools_once,
            )
            task.current_step = "索引已完成，进入分析阶段"
            await db.commit()

            # 注入 write-scope guard
            await _set_current_step("正在初始化工具运行时")
            write_scope_guard = build_task_write_scope_guard(
                project_root=normalized_project_root,
                target_files=task.target_files,
                bootstrap_findings=None,
            )

            # 初始化工具后检查取消
            if is_task_cancelled(task_id):
                logger.info(f"[Cancel] Task {task_id} cancelled after tools initialization")
                raise asyncio.CancelledError("任务已取消")

            # 创建子 Agent
            recon_agent = ReconAgent(
                llm_service=llm_service,
                tools=tools.get("recon", {}),
                event_emitter=event_emitter,
            )

            analysis_agent = AnalysisAgent(
                llm_service=llm_service,
                tools=tools.get("analysis", {}),
                event_emitter=event_emitter,
            )

            verification_agent = VerificationAgent(
                llm_service=llm_service,
                tools=tools.get("verification", {}),
                event_emitter=event_emitter,
            )

            report_agent = ReportAgent(
                llm_service=llm_service,
                tools=tools.get("report", {}),
                event_emitter=event_emitter,
            )

            bl_recon_agent = BusinessLogicReconAgent(
                llm_service=llm_service,
                tools=tools.get("business_logic_recon", {}),
                event_emitter=event_emitter,
            )

            bl_analysis_agent = BusinessLogicAnalysisAgent(
                llm_service=llm_service,
                tools=tools.get("business_logic_analysis", {}),
                event_emitter=event_emitter,
            )

            audit_runtime_metadata = {
                "smart_audit_mode": True,
                "audit_mode": "smart_audit",
                "disable_virtual_routing": True,
                "read_scope_policy": "project_scope",
            }

            for agent in (recon_agent, analysis_agent, verification_agent, report_agent, bl_recon_agent, bl_analysis_agent):
                if isinstance(getattr(agent.config, "metadata", None), dict):
                    agent.config.metadata.update(audit_runtime_metadata)
                if hasattr(agent, "set_write_scope_guard"):
                    agent.set_write_scope_guard(write_scope_guard)

            # 创建 Workflow 配置（基础值来自 settings；
            # analysis / verification worker 数可由 workflow/config.yml 覆盖）
            from app.core.config import settings
            workflow_config = WorkflowConfig(
                enable_parallel_analysis=settings.ENABLE_PARALLEL_ANALYSIS,
                enable_parallel_verification=settings.ENABLE_PARALLEL_VERIFICATION,
                enable_parallel_report=settings.ENABLE_PARALLEL_REPORT,
                analysis_max_workers=settings.ANALYSIS_MAX_WORKERS,
                verification_max_workers=settings.VERIFICATION_MAX_WORKERS,
                report_max_workers=settings.REPORT_MAX_WORKERS,
                use_agent_count_config_file=True,
            )

            # 创建 Orchestrator Agent（使用确定性 Workflow 版本，注入两个队列服务）
            orchestrator = WorkflowOrchestratorAgent(
                llm_service=llm_service,
                tools=tools.get("orchestrator", {}),
                event_emitter=event_emitter,
                sub_agents={
                    "recon": recon_agent,
                    "analysis": analysis_agent,
                    "verification": verification_agent,
                    "report": report_agent,
                    "business_logic_recon": bl_recon_agent,
                    "business_logic_analysis": bl_analysis_agent,
                },
                recon_queue_service=recon_queue_service,
                vuln_queue_service=queue_service,
                business_logic_queue_service=bl_queue_service,
                workflow_config=workflow_config,
            )
            if isinstance(getattr(orchestrator.config, "metadata", None), dict):
                orchestrator.config.metadata.update(audit_runtime_metadata)
            if hasattr(orchestrator, "set_write_scope_guard"):
                orchestrator.set_write_scope_guard(write_scope_guard)

            # 设置外部取消检查回调
            # 这确保即使 runner.cancel() 失败，Agent 也能通过 checking 全局标志感知取消
            def check_global_cancel():
                return is_task_cancelled(task_id)

            orchestrator.set_cancel_callback(check_global_cancel)
            # 同时也为子 Agent 设置（虽然 Orchestrator 会传播）
            recon_agent.set_cancel_callback(check_global_cancel)
            analysis_agent.set_cancel_callback(check_global_cancel)
            verification_agent.set_cancel_callback(check_global_cancel)
            report_agent.set_cancel_callback(check_global_cancel)
            bl_recon_agent.set_cancel_callback(check_global_cancel)
            bl_analysis_agent.set_cancel_callback(check_global_cancel)

            # 注册到全局
            _running_orchestrators[task_id] = orchestrator
            _running_tasks[task_id] = orchestrator  # 兼容旧的取消逻辑
            _running_event_managers[task_id] = event_manager  # 用于 SSE 流

            if hasattr(orchestrator, "configure_trace_logger"):
                try:
                    orchestrator.configure_trace_logger(orchestrator.name, task_id)
                except Exception as exc:
                    logger.warning("[AgentTask] configure_trace_logger failed for orchestrator: %s", exc)

            # 注册 Orchestrator 到 Agent Registry（使用其内置方法）
            orchestrator._register_to_registry(task="Root orchestrator for security audit")
            
            await event_emitter.emit_info("动态 Agent 树架构启动")
            await event_emitter.emit_info(f"📁 项目路径: {project_root}")
            
            # 收集项目信息 - 传递排除模式和目标文件
            project_info = await _collect_project_info(
                project_root, 
                project.name,
                exclude_patterns=task.exclude_patterns,
                target_files=task.target_files,
            )
            task.current_phase = AgentTaskPhase.RECONNAISSANCE
            await db.commit()

            bootstrap_findings: List[Dict[str, Any]] = []
            bootstrap_task_id: Optional[str] = None
            bootstrap_source = "disabled"
            source_mode = _resolve_agent_task_source_mode(task.name, task.description)
            static_bootstrap_config = _resolve_static_bootstrap_config(task, source_mode)

            if static_bootstrap_config["mode"] == "embedded":
                async def _prepare_bootstrap_once():
                    return await _prepare_embedded_bootstrap_findings(
                        db=db,
                        project_root=normalized_project_root,
                        event_emitter=event_emitter,
                        programming_languages=project.programming_languages,
                        exclude_patterns=task.exclude_patterns,
                        opengrep_enabled=bool(
                            static_bootstrap_config.get("opengrep_enabled")
                        ),
                        bandit_enabled=bool(
                            static_bootstrap_config.get("bandit_enabled")
                        ),
                        gitleaks_enabled=bool(
                            static_bootstrap_config.get("gitleaks_enabled")
                        ),
                        phpstan_enabled=bool(
                            static_bootstrap_config.get("phpstan_enabled")
                        ),
                    )

                (
                    bootstrap_findings,
                    bootstrap_task_id,
                    bootstrap_source,
                ) = await _run_with_retries(
                    "STATIC_BOOTSTRAP",
                    task_id,
                    event_emitter,
                    _prepare_bootstrap_once,
                )
            else:
                await event_emitter.emit_info(
                    "当前任务未启用静态预扫，直接进入入口点回退流程",
                    metadata={
                        "bootstrap": True,
                        "bootstrap_task_id": None,
                        "bootstrap_source": "disabled",
                        "bootstrap_total_findings": 0,
                        "bootstrap_candidate_count": 0,
                    },
                )

            # ============ Fixed-First: 生成种子候选（OpenGrep 优先，空则入口点回退） ============
            seed_findings: List[Dict[str, Any]] = []
            entry_points_payload: List[Dict[str, Any]] = []
            entry_function_names: List[str] = []

            if bootstrap_findings:
                seed_findings = _normalize_seed_from_opengrep(bootstrap_findings)
                await event_emitter.emit_info(
                    f"🌱 固定种子候选已生成（静态预扫）：{len(seed_findings)} 条"
                )
            else:
                if bootstrap_source == "disabled":
                    await event_emitter.emit_info(
                        "静态预扫未启用，启动入口点回退流程"
                    )
                else:
                    await event_emitter.emit_warning(
                        "静态预扫未筛选出 ERROR + HIGH/MEDIUM 候选，启动入口点回退流程"
                    )
                entry = await asyncio.to_thread(
                    _discover_entry_points_deterministic,
                    project_root=normalized_project_root,
                    target_files=task.target_files,
                    exclude_patterns=task.exclude_patterns,
                )
                entry_points_payload = (
                    entry.get("entry_points") if isinstance(entry, dict) else []
                ) or []
                entry_function_names = (
                    entry.get("entry_function_names") if isinstance(entry, dict) else []
                ) or []

                seed_findings = await _build_seed_from_entrypoints(
                    project_root=normalized_project_root,
                    target_vulns=task.target_vulnerabilities or [],
                    entry_function_names=entry_function_names,
                    exclude_patterns=task.exclude_patterns or [],
                )

                bootstrap_source = "fallback_entrypoints"
                await event_emitter.emit_info(
                    f"🌱 固定种子候选已生成（入口点回退）：entry_points={len(entry_points_payload)}，"
                    f"entry_funcs={len(entry_function_names)}，seeds={len(seed_findings)}"
                )

            if write_scope_guard:
                seed_paths: List[str] = []
                for item in seed_findings:
                    if isinstance(item, dict):
                        file_path = item.get("file_path")
                        if isinstance(file_path, str) and file_path.strip():
                            seed_paths.append(file_path.strip())
                write_scope_guard.register_evidence_paths(seed_paths)

            # ============ Markdown 长期记忆（不依赖向量检索） ============
            try:
                from app.services.agent.memory.markdown_memory import MarkdownMemoryStore
                from app.core.config import settings

                memory_store = MarkdownMemoryStore(project_id=str(project.id))
                memory_store.ensure()
                # 每次新任务启动时清除 Agent 专属记忆，防止跨任务上下文污染
                memory_store.clear_agent_memory(task_id=task_id)
                if bool(getattr(settings, "TOOL_DOC_SYNC_ENABLED", True)):
                    _sync_tool_catalog_to_memory(
                        memory_store=memory_store,
                        task_id=task_id,
                        max_chars=int(getattr(settings, "TOOL_DOC_SYNC_MAX_CHARS", 8000)),
                    )
                    _sync_tool_playbook_to_memory(
                        memory_store=memory_store,
                        task_id=task_id,
                        max_chars=int(getattr(settings, "TOOL_DOC_SYNC_MAX_CHARS", 8000)),
                    )
                    _sync_tool_skills_to_memory(
                        memory_store=memory_store,
                        task_id=task_id,
                        max_chars=int(getattr(settings, "TOOL_DOC_SYNC_MAX_CHARS", 8000)),
                    )
                markdown_memory = memory_store.load_bundle(
                    max_chars=8000,
                    skills_max_lines=int(getattr(settings, "TOOL_SKILLS_MAX_LINES", 180)),
                )
            except Exception as exc:
                logger.warning("[MarkdownMemory] init/load failed: %s", exc)
                markdown_memory = {}

            # 更新任务文件统计
            task.total_files = project_info.get("file_count", 0)
            await db.commit()

            task_agent_config = task.agent_config if isinstance(task.agent_config, dict) else {}
            use_prompt_skills = bool(task_agent_config.get("use_prompt_skills", False))
            other_config = user_config.get("otherConfig") if isinstance(user_config, dict) else {}
            builtin_prompt_skill_state = build_prompt_skill_builtin_state(
                other_config.get(PROMPT_SKILL_BUILTIN_STATE_CONFIG_KEY)
                if isinstance(other_config, dict)
                else None
            )
            prompt_skills = apply_prompt_skill_builtin_state(
                base_prompt_skills=build_effective_prompt_skills(use_prompt_skills),
                builtin_state=builtin_prompt_skill_state,
            )
            builtin_prompt_skill_enabled_keys = [
                key for key in PROMPT_SKILL_AGENT_KEYS if builtin_prompt_skill_state.get(key, True)
            ]
            custom_prompt_skill_count = 0

            if use_prompt_skills:
                try:
                    custom_prompt_skill_result = await db.execute(
                        select(PromptSkill)
                        .where(
                            PromptSkill.user_id == str(task.created_by),
                            PromptSkill.is_active.is_(True),
                        )
                        .order_by(PromptSkill.created_at.asc())
                    )
                    custom_prompt_skill_rows = custom_prompt_skill_result.scalars().all()
                    custom_prompt_skill_count = len(custom_prompt_skill_rows)
                    if custom_prompt_skill_rows:
                        prompt_skills = merge_prompt_skills_with_custom(
                            base_prompt_skills=prompt_skills,
                            custom_prompt_skills=custom_prompt_skill_rows,
                        )
                except Exception as exc:
                    logger.warning("[PromptSkills] load custom prompt skills failed: %s", exc)

                await event_emitter.emit_info(
                    "Prompt Skills enabled",
                    metadata={
                        "prompt_skills_enabled": True,
                        "prompt_skill_agent_keys": PROMPT_SKILL_AGENT_KEYS,
                        "builtin_prompt_skill_enabled_keys": builtin_prompt_skill_enabled_keys,
                        "builtin_prompt_skill_disabled_keys": [
                            key for key in PROMPT_SKILL_AGENT_KEYS if key not in builtin_prompt_skill_enabled_keys
                        ],
                        "custom_prompt_skill_count": custom_prompt_skill_count,
                    },
                )
            else:
                await event_emitter.emit_info(
                    "Prompt Skills disabled",
                    metadata={
                        "prompt_skills_enabled": False,
                        "builtin_prompt_skill_enabled_keys": builtin_prompt_skill_enabled_keys,
                        "builtin_prompt_skill_disabled_keys": [
                            key for key in PROMPT_SKILL_AGENT_KEYS if key not in builtin_prompt_skill_enabled_keys
                        ],
                        "custom_prompt_skill_count": 0,
                    },
                )
            
            # 构建输入数据
            input_data = {
                "project_info": project_info,
                "config": {
                    "target_vulnerabilities": task.target_vulnerabilities or [],
                    "verification_level": task.verification_level or "analysis_with_poc_plan",
                    "exclude_patterns": task.exclude_patterns or [],
                    "target_files": task.target_files or [],
                    "single_risk_mode": True,
                    "max_iterations": task.max_iterations or 50,
                    "audit_source_mode": source_mode,
                    "static_bootstrap_candidate_count": len(bootstrap_findings or []),
                    # 混合扫描中即使存在静态候选，也继续执行自主 Recon 再汇总进入 Analysis。
                    "skip_recon_when_bootstrap_available": False,
                    # seed_findings（继续使用 bootstrap_findings 字段承载：固定优先候选种子）
                    "bootstrap_findings": seed_findings,
                    "bootstrap_source": bootstrap_source,
                    "bootstrap_task_id": bootstrap_task_id,
                    # 入口点信息（回退时注入，便于 Agent 展示与 flow pipeline 约束）
                    "entry_points": entry_points_payload,
                    "entry_function_names": entry_function_names,
                    # 项目级 Markdown 记忆（shared + per-agent + skills 规范）
                    "markdown_memory": markdown_memory,
                    "use_prompt_skills": use_prompt_skills,
                    "prompt_skills": prompt_skills,
                },
                "project_root": project_root,
                "task_id": task_id,
            }

            # Provide deterministic persistence callback for Orchestrator TODO mode.
            # The callback is idempotent per task run to avoid double inserts on retries.
            finding_save_diagnostics: Dict[str, Any] = {}
            persist_state: Dict[str, Any] = {
                "saved_count": 0,
                "seen_payload_digests": set(),
            }
            from app.models.agent_task import AgentFinding
            from app.services.agent.tools.verification_result_tools import (
                ensure_finding_identity,
                merge_finding_patch,
            )

            async def _persist_findings_callback(findings_payload: Any) -> int:
                findings_list = findings_payload if isinstance(findings_payload, list) else []
                if not findings_list:
                    return 0
                for finding_item in findings_list:
                    if isinstance(finding_item, dict):
                        ensure_finding_identity(task_id, finding_item)

                try:
                    payload_digest_raw = json.dumps(
                        findings_list,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                except Exception:
                    payload_digest_raw = str(findings_list)
                payload_digest = hashlib.sha1(
                    payload_digest_raw.encode("utf-8", errors="ignore")
                ).hexdigest()

                seen_payload_digests = persist_state.get("seen_payload_digests")
                if isinstance(seen_payload_digests, set) and payload_digest in seen_payload_digests:
                    logger.info(
                        "[AgentTask] Skip duplicate persist_findings payload: digest=%s",
                        payload_digest[:12],
                    )
                    return 0

                async with async_session_factory() as persist_db:
                    saved = await _save_findings(
                        persist_db,
                        task_id,
                        findings_list,
                        project_root=normalized_project_root,
                        save_diagnostics=finding_save_diagnostics,
                    )
                if isinstance(seen_payload_digests, set):
                    seen_payload_digests.add(payload_digest)
                persist_state["saved_count"] = int(persist_state.get("saved_count") or 0) + int(saved)
                return int(saved)

            async def _update_finding_callback(
                finding_identity: str,
                fields_to_update: Dict[str, Any],
                update_reason: str,
            ) -> Dict[str, Any]:
                async with async_session_factory() as update_db:
                    finding_stmt = select(AgentFinding).where(
                        AgentFinding.task_id == task_id,
                        AgentFinding.finding_identity == finding_identity,
                    )
                    finding_row = (await update_db.execute(finding_stmt)).scalar_one_or_none()
                    if finding_row is None:
                        legacy_stmt = select(AgentFinding).where(
                            AgentFinding.task_id == task_id,
                            AgentFinding.finding_metadata["finding_identity"].as_string() == finding_identity,
                        )
                        finding_row = (await update_db.execute(legacy_stmt)).scalar_one_or_none()
                    if finding_row is None:
                        raise ValueError(f"未找到 finding_identity={finding_identity} 对应的漏洞记录")

                    verification_patch = fields_to_update.get("verification_result")
                    if isinstance(verification_patch, dict):
                        verification_result = dict(finding_row.verification_result or {})
                        verification_result.update(verification_patch)
                        verification_result["finding_identity"] = finding_identity

                        normalized_verdict = str(
                            verification_result.get("authenticity")
                            or verification_result.get("verdict")
                            or finding_row.verdict
                            or ""
                        ).strip().lower()
                        if normalized_verdict in {"confirmed", "likely", "uncertain", "false_positive"}:
                            finding_row.verdict = normalized_verdict
                            verification_result["verdict"] = normalized_verdict
                            verification_result["authenticity"] = normalized_verdict

                        normalized_reachability = str(
                            verification_result.get("reachability")
                            or finding_row.reachability
                            or ""
                        ).strip().lower()
                        if normalized_reachability in {"reachable", "likely_reachable", "unknown", "unreachable"}:
                            finding_row.reachability = normalized_reachability
                            verification_result["reachability"] = normalized_reachability

                        confidence_value = verification_result.get("confidence", finding_row.confidence)
                        normalized_confidence: Optional[float] = None
                        if confidence_value is not None:
                            try:
                                normalized_confidence = max(0.0, min(float(confidence_value), 1.0))
                            except Exception:
                                normalized_confidence = None
                        if normalized_confidence is not None:
                            finding_row.confidence = normalized_confidence
                            verification_result["confidence"] = normalized_confidence

                        normalized_evidence = (
                            verification_result.get("verification_evidence")
                            or verification_result.get("verification_details")
                            or verification_result.get("evidence")
                        )
                        if normalized_evidence is not None:
                            finding_row.verification_evidence = str(normalized_evidence)
                            verification_result["verification_evidence"] = str(normalized_evidence)

                        status_for_state = str(
                            verification_result.get("status")
                            or finding_row.status
                            or ""
                        ).strip().lower()
                        verdict_for_state = str(finding_row.verdict or "").strip().lower()
                        current_manual_status = str(
                            finding_row.status or ""
                        ).strip().lower()
                        if (
                            current_manual_status == FindingStatus.FALSE_POSITIVE
                            or status_for_state
                            in {"false_positive", "false-positive", "not_vulnerable", "not_exists"}
                            or verdict_for_state == "false_positive"
                        ):
                            finding_row.status = FindingStatus.FALSE_POSITIVE
                        elif current_manual_status == FindingStatus.VERIFIED:
                            finding_row.status = FindingStatus.VERIFIED
                        else:
                            finding_row.status = FindingStatus.NEEDS_REVIEW

                        # status 与 verdict 冲突时，以 status 语义为准
                        if finding_row.status == FindingStatus.FALSE_POSITIVE and finding_row.verdict in {"confirmed", "likely"}:
                            finding_row.verdict = "false_positive"
                            verification_result["verdict"] = "false_positive"
                            verification_result["authenticity"] = "false_positive"
                        elif finding_row.status == FindingStatus.VERIFIED and finding_row.verdict in {"likely", "uncertain", ""}:
                            finding_row.verdict = "confirmed"
                            verification_result["verdict"] = "confirmed"
                            verification_result["authenticity"] = "confirmed"

                        # is_verified 仅表示人工已确认为真实漏洞。
                        verification_stage_completed = bool(
                            verification_result.get("verification_stage_completed")
                            or verdict_for_state in {
                                "confirmed",
                                "likely",
                                "uncertain",
                                "false_positive",
                            }
                            or status_for_state in {
                                "verified",
                                "likely",
                                "uncertain",
                                "needs_review",
                                "needs-review",
                                "false_positive",
                                "false-positive",
                            }
                        )
                        finding_row.is_verified = finding_row.status == FindingStatus.VERIFIED
                        finding_row.verified_at = (
                            datetime.now(timezone.utc)
                            if finding_row.is_verified
                            else None
                        )
                        verification_result["verification_stage_completed"] = verification_stage_completed
                        verification_result["status"] = finding_row.status

                        finding_row.verification_result = verification_result

                    for field_name, field_value in fields_to_update.items():
                        if field_name == "verification_result":
                            continue
                        setattr(finding_row, field_name, field_value)

                    metadata_payload = dict(finding_row.finding_metadata or {})
                    metadata_payload["finding_identity"] = finding_identity
                    metadata_payload["report_update_reason"] = update_reason
                    finding_row.finding_metadata = metadata_payload
                    finding_row.finding_identity = finding_identity
                    await update_db.commit()
                    await update_db.refresh(finding_row)

                    updated_finding = merge_finding_patch(
                        {
                            "id": finding_row.id,
                            "finding_identity": finding_row.finding_identity,
                            "title": finding_row.title,
                            "file_path": finding_row.file_path,
                            "line_start": finding_row.line_start,
                            "line_end": finding_row.line_end,
                            "function_name": finding_row.function_name,
                            "vulnerability_type": finding_row.vulnerability_type,
                            "severity": finding_row.severity,
                            "description": finding_row.description,
                            "code_snippet": finding_row.code_snippet,
                            "source": finding_row.source,
                            "sink": finding_row.sink,
                            "suggestion": finding_row.suggestion,
                            "status": finding_row.status,
                            "is_verified": finding_row.is_verified,
                            "verdict": finding_row.verdict,
                            "authenticity": finding_row.verdict,
                            "confidence": finding_row.confidence,
                            "reachability": finding_row.reachability,
                            "verification_evidence": finding_row.verification_evidence,
                            "verification_result": (
                                dict(finding_row.verification_result)
                                if isinstance(finding_row.verification_result, dict)
                                else {}
                            ),
                        },
                        fields_to_update,
                    )
                    updated_finding["finding_identity"] = finding_identity
                    return updated_finding

            input_data["persist_findings"] = _persist_findings_callback

            # 将持久化回调注入到已初始化的 Verification 保存工具
            # （工具在 _initialize_tools 时以 save_callback=None 创建，此处补注入）
            _save_tool_instance = (
                tools.get("verification", {}).get("save_verification_result")
                if isinstance(tools, dict)
                else None
            )
            if _save_tool_instance is not None and hasattr(_save_tool_instance, "_save_callback"):
                _save_tool_instance._save_callback = _persist_findings_callback
                logger.info("[Task] Injected persist_findings_callback into save_verification_result tool")
            _update_tool_instance = (
                tools.get("report", {}).get("update_vulnerability_finding")
                if isinstance(tools, dict)
                else None
            )
            if _update_tool_instance is not None and hasattr(_update_tool_instance, "_update_callback"):
                _update_tool_instance._update_callback = _update_finding_callback
                logger.info("[Task] Injected update_finding_callback into update_vulnerability_finding tool")

            # 执行 Orchestrator
            await event_emitter.emit_phase_start("orchestration", "🎯 Orchestrator 开始编排审计流程")
            task.current_phase = AgentTaskPhase.ANALYSIS
            task.current_step = "分析阶段进行中"
            await db.commit()

            async def _run_orchestrator_once():
                # 将 orchestrator.run() 包装在 asyncio.Task 中，以便可以强制取消
                run_task = asyncio.create_task(orchestrator.run(input_data))
                try:
                    run_result = await run_task
                except asyncio.CancelledError:
                    run_task.cancel()
                    await asyncio.gather(run_task, return_exceptions=True)
                    raise
                finally:
                    if not run_task.done():
                        run_task.cancel()

                if not run_result.success and run_result.error != "任务已取消":
                    raise RuntimeError(run_result.error or "Orchestrator returned unsuccessful result")
                return run_result

            result = await _run_with_retries(
                "ORCHESTRATOR_RUN",
                task_id,
                event_emitter,
                _run_orchestrator_once,
            )
            
            # 处理结果
            duration_ms = int((time.time() - start_time) * 1000)
            
            await db.refresh(task)
            
            if result.success:
                # CRITICAL FIX: Log and save findings with detailed debugging
                findings = result.data.get("findings", [])
                if not isinstance(findings, list):
                    findings = []
                if not findings:
                    fallback_findings = getattr(orchestrator, "_all_findings", None)
                    if isinstance(fallback_findings, list) and fallback_findings:
                        findings = fallback_findings
                        logger.warning(
                            "[AgentTask] result.data.findings is empty, fallback to orchestrator._all_findings (%s)",
                            len(findings),
                        )

                single_risk_mode = bool((input_data.get("config") or {}).get("single_risk_mode", False))
                if single_risk_mode:
                    logger.info(
                        "[AgentTask] single_risk_mode=true，跳过 seed 与 agent findings 合并，使用实际分析结果"
                    )
                else:
                    # Fixed-First 合并：确保 seed_findings 不会因 LLM 空输出而丢失
                    findings = _merge_seed_and_agent_findings(seed_findings, findings)

                # Best-effort dedup to avoid double inserts when seeds overlap with agent findings.
                # Key: (file_path, line_start, vulnerability_type)
                deduped: List[Dict[str, Any]] = []
                seen: Set[Tuple[str, int, str]] = set()
                for f in findings:
                    if not isinstance(f, dict):
                        continue
                    fp = str(f.get("file_path") or "").strip()
                    vt = str(f.get("vulnerability_type") or "").strip()
                    try:
                        ln = int(f.get("line_start") or 0)
                    except Exception:
                        ln = 0
                    key = (fp, ln, vt)
                    if key in seen:
                        continue
                    seen.add(key)
                    deduped.append(f)
                findings = deduped
                logger.info(
                    "[AgentTask] Task %s completed: merged_findings=%s (seeds=%s, orchestrator=%s)",
                    task_id,
                    len(findings),
                    len(seed_findings),
                    len(result.data.get("findings", []) or []) if isinstance(result.data, dict) else 0,
                )

                # Debug: Log each finding for verification
                for i, f in enumerate(findings[:5]):  # Log first 5
                    if isinstance(f, dict):
                        logger.debug(f"[AgentTask] Finding {i+1}: {f.get('title', 'N/A')[:50]} - {f.get('severity', 'N/A')}")

                # Smart audit policy: disable automatic flow enrichment / evidence generation.
                flow_summary: Dict[str, Any] = {
                    "enabled": False,
                    "blocked_reason": "disabled_by_policy",
                }
                logger.info(
                    "[AgentTask] Flow enrichment summary (disabled): %s",
                    json.dumps(flow_summary, ensure_ascii=False),
                )

                task.current_phase = AgentTaskPhase.VERIFICATION
                task.current_step = "验证与结果归档中"
                await db.commit()

                # 检查 save_verification_result 工具是否已由 Agent 主动持久化
                _tool_saved_count: Optional[int] = None
                if (
                    _save_tool_instance is not None
                    and hasattr(_save_tool_instance, "is_saved")
                    and _save_tool_instance.is_saved
                ):
                    _tool_saved_count = _save_tool_instance.saved_count
                    logger.info(
                        "[AgentTask] save_verification_result 工具已由 Verification Agent 主动保存: saved_count=%s",
                        _tool_saved_count,
                    )
                elif (
                    _save_tool_instance is not None
                    and hasattr(_save_tool_instance, "buffered_findings")
                    and _save_tool_instance.buffered_findings
                    and not findings
                ):
                    # 工具缓冲了结果但未持久化（无回调），用缓冲的 findings 作为来源
                    findings = _save_tool_instance.buffered_findings
                    logger.info(
                        "[AgentTask] 从 save_verification_result 工具缓冲读取 %d 条 findings",
                        len(findings),
                    )

                final_findings_sync_required = False
                if _tool_saved_count is not None:
                    saved_count = _tool_saved_count
                    final_findings_sync_required = bool(findings)
                    logger.info(
                        "[AgentTask] 跳过重复持久化（工具已保存 %s 条）",
                        saved_count,
                    )
                elif int(persist_state.get("saved_count") or 0) > 0:
                    saved_count = int(persist_state["saved_count"])
                    final_findings_sync_required = bool(findings)
                    logger.info(
                        "[AgentTask] Findings were already persisted by Orchestrator TODO step: saved_count=%s",
                        saved_count,
                    )
                else:
                    async def _persist_findings_once():
                        return await _save_findings(
                            db,
                            task_id,
                            findings,
                            project_root=normalized_project_root,
                            save_diagnostics=finding_save_diagnostics,
                        )

                    saved_count = await _run_with_retries(
                        "PERSIST_FINDINGS",
                        task_id,
                        event_emitter,
                        _persist_findings_once,
                    )

                if final_findings_sync_required:
                    async def _sync_final_findings_once():
                        return await _save_findings(
                            db,
                            task_id,
                            findings,
                            project_root=normalized_project_root,
                        )

                    synced_count = await _run_with_retries(
                        "SYNC_FINAL_FINDINGS",
                        task_id,
                        event_emitter,
                        _sync_final_findings_once,
                    )
                    logger.info(
                        "[AgentTask] Final findings synced back to database after report/update stage: %s",
                        synced_count,
                    )
                logger.info(f"[AgentTask] Saved {saved_count}/{len(findings)} findings (filtered {len(findings) - saved_count} hallucinations)")

                persisted_findings_result = await db.execute(
                    select(AgentFinding).where(AgentFinding.task_id == task_id)
                )
                persisted_findings = persisted_findings_result.scalars().all()
                persisted_findings = _normalize_terminal_agent_findings(
                    persisted_findings
                )
                # effective_findings: all non-false-positive findings.
                effective_findings = [
                    item for item in persisted_findings
                    if str(item.status) != FindingStatus.FALSE_POSITIVE
                ]
                false_positive_findings = [
                    item for item in persisted_findings
                    if str(item.status) == FindingStatus.FALSE_POSITIVE
                ]
                filtered_reasons = (
                    finding_save_diagnostics.get("filtered_reasons")
                    if isinstance(finding_save_diagnostics, dict)
                    else {}
                )
                false_positive_count = len(false_positive_findings)
                agent_payloads: Dict[str, Any] = {}

                # ============ Markdown 长期记忆写入（shared + per-agent） ============
                try:
                    if memory_store:
                        # Shared: 本次任务统计 + top findings
                        top_items = []
                        for item in effective_findings[:10]:
                            try:
                                top_items.append(
                                    {
                                        "title": str(item.title)[:120] if getattr(item, "title", None) else "",
                                        "severity": str(item.severity) if getattr(item, "severity", None) else "",
                                        "vulnerability_type": str(item.vulnerability_type) if getattr(item, "vulnerability_type", None) else "",
                                        "file_path": str(item.file_path) if getattr(item, "file_path", None) else "",
                                        "line_start": int(item.line_start) if getattr(item, "line_start", None) else 0,
                                    }
                                )
                            except Exception:
                                continue

                        memory_store.append_entry(
                            "shared",
                            task_id=task_id,
                            source=str(bootstrap_source or "agent_task"),
                            title="任务摘要",
                            summary=(
                                f"bootstrap_source={bootstrap_source} "
                                f"seeds={len(seed_findings)} "
                                f"orchestrator_findings={len(findings)} "
                                f"persisted_effective={len(effective_findings)} "
                                f"false_positive={false_positive_count}"
                            ),
                            payload={
                                "bootstrap": {
                                    "bootstrap_source": bootstrap_source,
                                    "bootstrap_task_id": bootstrap_task_id,
                                    "seed_count": len(seed_findings),
                                    "entry_points_count": len(entry_points_payload or []),
                                    "entry_function_names_count": len(entry_function_names or []),
                                },
                                "persistence": {
                                    "orchestrator_findings_count": len(findings),
                                    "saved_count": int(saved_count),
                                    "effective_findings_count": len(effective_findings),
                                    "false_positive_count": false_positive_count,
                                },
                                "top_findings": top_items,
                            },
                        )

                        # Per-agent: best-effort final answer summaries
                        if orchestrator and hasattr(orchestrator, "_agent_results"):
                            agent_payloads = getattr(orchestrator, "_agent_results") or {}

                        # Orchestrator
                        memory_store.append_entry(
                            "orchestrator",
                            task_id=task_id,
                            source="orchestrator",
                            title="Final Answer 摘要",
                            payload={
                                "result_keys": list(result.data.keys()) if isinstance(result.data, dict) else [],
                                "findings_count": len(findings),
                            },
                        )

                        # Sub agents
                        for agent_key in ("recon", "analysis", "verification", "report"):
                            data = agent_payloads.get(agent_key)
                            if not isinstance(data, dict):
                                continue
                            summary_text = data.get("summary") or data.get("note") or ""
                            findings_list = data.get("findings")
                            if not isinstance(findings_list, list):
                                findings_list = data.get("initial_findings")
                            if not isinstance(findings_list, list):
                                findings_list = []
                            memory_store.append_entry(
                                agent_key,
                                task_id=task_id,
                                source=agent_key,
                                title="Final Answer 摘要",
                                summary=str(summary_text)[:8000] if summary_text else None,
                                payload={
                                    "keys": list(data.keys()),
                                    "findings_count": len([f for f in findings_list if isinstance(f, dict)]),
                                },
                            )
                except Exception as exc:
                    logger.warning("[MarkdownMemory] append failed: %s", exc)

                # 更新任务统计
                # CRITICAL FIX: 在设置完成前再次检查取消状态
                # 避免 "取消后后端继续运行并最终标记为完成" 的问题
                verification_pending_gate_triggered = False
                verification_pending_gate_message = ""
                verification_pending_gate_metadata: Dict[str, Any] = {}

                verification_payload: Dict[str, Any] = {}
                if orchestrator and hasattr(orchestrator, "_agent_results"):
                    agent_results = getattr(orchestrator, "_agent_results", {})
                    if isinstance(agent_results, dict):
                        verification_candidate = agent_results.get("verification")
                        if isinstance(verification_candidate, dict):
                            verification_payload = dict(verification_candidate)
                if not verification_payload and isinstance(result.data, dict):
                    verification_candidate = result.data.get("verification")
                    if isinstance(verification_candidate, dict):
                        verification_payload = dict(verification_candidate)

                gate_stats = _compute_verification_pending_gate(verification_payload)
                verification_pending_gate_triggered = bool(gate_stats.get("triggered"))
                verification_pending_gate_message = str(gate_stats.get("message") or "")
                verification_pending_gate_metadata = {
                    "candidate_count": int(gate_stats.get("candidate_count") or 0),
                    "pending_count": int(gate_stats.get("pending_count") or 0),
                    "pending_examples": gate_stats.get("pending_examples") or [],
                }

                desired_terminal_status = AgentTaskStatus.COMPLETED
                if is_task_cancelled(task_id):
                    logger.info(f"[AgentTask] Task {task_id} was cancelled, overriding success result")
                    desired_terminal_status = AgentTaskStatus.CANCELLED
                elif verification_pending_gate_triggered:
                    desired_terminal_status = AgentTaskStatus.FAILED
                task.current_phase = AgentTaskPhase.REPORTING
                task.findings_count = len(effective_findings)
                task.false_positive_count = false_positive_count
                orchestrator_findings_count = len(findings)
                persisted_findings_count = len(effective_findings)
                filtered_findings_count = max(
                    orchestrator_findings_count - persisted_findings_count,
                    0,
                )
                filter_reason_text = ""
                if isinstance(filtered_reasons, dict) and filtered_reasons:
                    sorted_reasons = sorted(
                        filtered_reasons.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )[:3]
                    filter_reason_text = "，".join(
                        [f"{key}:{value}" for key, value in sorted_reasons]
                    )
                task.current_step = (
                    f"编排发现 {orchestrator_findings_count} / 入库 {persisted_findings_count} / "
                    f"过滤 {filtered_findings_count}"
                )
                if filter_reason_text:
                    task.current_step += f"（主要过滤原因：{filter_reason_text}）"

                # 从 Workflow 编排结果直接获取统计数据（已由 AgentResult 集计）
                # 优先级：result > runtime_snapshot（确保 workflow 编排的准确数据优先使用）
                workflow_state_summary = None
                if isinstance(result.data, dict):
                    workflow_state_summary = result.data.get("workflow_state")
                
                runtime_snapshot = _snapshot_runtime_stats_to_task(task, orchestrator)
                
                # 设置迭代统计：使用 AgentResult 中的值（已由 Workflow Orchestrator 聚合）
                task.total_iterations = int(result.iterations or 0) if result.iterations > 0 else int(runtime_snapshot["iterations"] or 0)
                task.tool_calls_count = int(result.tool_calls or 0) if result.tool_calls > 0 else int(runtime_snapshot["tool_calls"] or 0)
                task.tokens_used = int(result.tokens_used or 0) if result.tokens_used > 0 else int(runtime_snapshot["tokens_used"] or 0)

                # 统计文件数量
                # analyzed_files = 实际扫描过的文件数（任务完成时等于 total_files）
                # files_with_findings = 有漏洞发现的唯一文件数
                task.analyzed_files = task.total_files  # Agent 扫描了所有符合条件的文件

                files_with_findings_set = set()
                for finding_item in effective_findings:
                    if finding_item.file_path:
                        files_with_findings_set.add(finding_item.file_path)
                task.files_with_findings = len(files_with_findings_set)

                # 统计严重程度和验证状态
                task.critical_count = 0
                task.high_count = 0
                task.medium_count = 0
                task.low_count = 0
                task.verified_count = 0
                for finding_item in effective_findings:
                    severity_value = str(finding_item.severity).lower()
                    if severity_value == "critical":
                        task.critical_count += 1
                    elif severity_value == "high":
                        task.high_count += 1
                    elif severity_value == "medium":
                        task.medium_count += 1
                    elif severity_value == "low":
                        task.low_count += 1
                    if finding_item.is_verified:
                        task.verified_count += 1
                
                # 保存 Workflow 编排元数据到 audit_plan（包含队列处理统计）
                if workflow_state_summary and isinstance(workflow_state_summary, dict):
                    audit_plan_metadata = {
                        "workflow_mode": "deterministic_workflow_engine",
                        "workflow_phase": workflow_state_summary.get("phase"),
                        "recon_done": workflow_state_summary.get("recon_done"),
                        "analysis_risk_points_total": workflow_state_summary.get("analysis_risk_points_total", 0),
                        "analysis_risk_points_processed": workflow_state_summary.get("analysis_risk_points_processed", 0),
                        "vuln_queue_findings_total": workflow_state_summary.get("vuln_queue_findings_total", 0),
                        "vuln_queue_findings_processed": workflow_state_summary.get("vuln_queue_findings_processed", 0),
                        "step_count": len(workflow_state_summary.get("step_records", [])),
                    }
                    task.audit_plan = audit_plan_metadata
                    logger.info(
                        "[AgentTask] Workflow metadata saved: analysis_points=%s/%s, vuln_findings=%s/%s",
                        audit_plan_metadata.get("analysis_risk_points_processed"),
                        audit_plan_metadata.get("analysis_risk_points_total"),
                        audit_plan_metadata.get("vuln_queue_findings_processed"),
                        audit_plan_metadata.get("vuln_queue_findings_total"),
                    )

                project_risk_report = None
                if isinstance(result.data, dict):
                    project_risk_report = _normalize_optional_text(
                        result.data.get("project_risk_report")
                    )
                if not project_risk_report and isinstance(workflow_state_summary, dict):
                    project_risk_report = _normalize_optional_text(
                        workflow_state_summary.get("project_risk_report")
                    )
                if (
                    not project_risk_report
                    and orchestrator
                    and isinstance(getattr(orchestrator, "_agent_results", None), dict)
                ):
                    report_payload = getattr(orchestrator, "_agent_results", {}).get("report")
                    if isinstance(report_payload, dict):
                        project_risk_report = _normalize_optional_text(
                            report_payload.get("project_risk_report")
                        )
                if project_risk_report:
                    task.report = project_risk_report
                    logger.info(
                        "[AgentTask] Project risk report persisted to task.report (length=%s)",
                        len(project_risk_report),
                    )
                
                # 计算安全评分
                task.security_score = _calculate_security_score(
                    [{"severity": str(item.severity).lower()} for item in effective_findings]
                )
                # 注意: progress_percentage 是计算属性，不需要手动设置
                # 当 status = COMPLETED 时会自动返回 100.0
                
                async def _commit_summary_once():
                    await db.commit()

                await _run_with_retries(
                    "PERSIST_TASK_SUMMARY",
                    task_id,
                    event_emitter,
                    _commit_summary_once,
                )

                terminal_result = await _finalize_task_terminal_state(
                    db=db,
                    task=task,
                    task_id=task_id,
                    event_emitter=event_emitter,
                    event_manager=event_manager,
                    desired_status=desired_terminal_status,
                    success_payload={
                        "findings_count": persisted_findings_count,
                        "duration_ms": duration_ms,
                        "message": (
                            f"审计完成：编排发现 {orchestrator_findings_count}，"
                            f"入库 {persisted_findings_count}，过滤 {filtered_findings_count}，"
                            f"耗时 {duration_ms/1000:.1f} 秒"
                        ),
                        "extra_metadata": {
                            "orchestrator_findings_count": orchestrator_findings_count,
                            "persisted_findings_count": persisted_findings_count,
                            "filtered_findings_count": filtered_findings_count,
                            "filtered_reasons": filtered_reasons or {},
                        },
                    },
                    verification_gate_message=(
                        verification_pending_gate_message
                        if verification_pending_gate_triggered
                        else None
                    ),
                    verification_gate_metadata=verification_pending_gate_metadata,
                    cancel_message="任务已取消",
                    skip_drain_wait=bool(desired_terminal_status == AgentTaskStatus.CANCELLED),
                    timeout_seconds=TOOL_DRAIN_TIMEOUT_SECONDS,
                )
                drain_result = terminal_result["drain_result"]
                drain_metadata = terminal_result["drain_metadata"]
                final_terminal_status = terminal_result["status"]
                if orchestrator_findings_count > 0 and persisted_findings_count == 0:
                    # 分析为什么全部被过滤
                    await event_emitter.emit_warning(
                        "编排阶段识别到漏洞，但入库结果为 0，疑似参数验证或质量门限制",
                        metadata={
                            "orchestrator_findings_count": orchestrator_findings_count,
                            "persisted_findings_count": persisted_findings_count,
                            "filtered_findings_count": filtered_findings_count,
                            "filtered_reasons": filtered_reasons or {},
                            "diagnosis_suggestions": [
                                "参数验证失败：确认 confidence 为浮点数、verdict 为有效值、reachability 正确",
                                "文件路径无效：检查 file_path 是否存在于项目目录中",
                                "文件定位失败（已降级）：查看 localization_status=failed 的 findings 是否被其他原因过滤",
                                "其他质量门：检查 verification_evidence 是否为空、cwe_id 格式是否正确",
                            ],
                            **drain_metadata,
                            "is_terminal": True,
                        },
                    )
                
                if bool(drain_result.get("timed_out")):
                    logger.error(
                        "[TaskDrain] Task %s failed due to tool drain timeout: pending=%s",
                        task_id,
                        len(drain_metadata.get("pending_tool_calls", [])),
                    )
                elif verification_pending_gate_triggered:
                    logger.error(
                        "[VerificationGate] Task %s blocked: candidate=%s pending=%s",
                        task_id,
                        verification_pending_gate_metadata.get("candidate_count", 0),
                        verification_pending_gate_metadata.get("pending_count", 0),
                    )
                elif final_terminal_status == AgentTaskStatus.CANCELLED:
                    logger.info("🛑 Task %s cancelled during terminal finalization", task_id)
                else:
                    logger.info(
                        f"Task {task_id} completed: "
                        f"effective={len(effective_findings)}, false_positive={false_positive_count}, "
                        f"saved={saved_count}, duration={duration_ms}ms"
                    )
            else:
                # 检查是否是取消导致的失败
                if result.error == "任务已取消":
                    # 状态可能已经被 cancel API 更新，只需确保一致性
                    _snapshot_runtime_stats_to_task(task, orchestrator)
                    terminal_result = await _finalize_task_terminal_state(
                        db=db,
                        task=task,
                        task_id=task_id,
                        event_emitter=event_emitter,
                        event_manager=event_manager,
                        desired_status=AgentTaskStatus.CANCELLED,
                        cancel_message="任务已取消",
                        skip_drain_wait=True,
                        timeout_seconds=TOOL_DRAIN_TIMEOUT_SECONDS,
                    )
                    logger.info(f"🛑 Task {task_id} cancelled")
                else:
                    _snapshot_runtime_stats_to_task(task, orchestrator)
                    failure_message = result.error or "Unknown error"
                    retry_diag = _classify_retry_error(failure_message)
                    failure_metadata = {
                        "step_name": "ORCHESTRATOR_RUN",
                        "attempt": 1,
                        "retry_attempt": 1,
                        "max_attempts": 1,
                        "is_terminal": True,
                        "retry_error_class": retry_diag["code"],
                        "retryable": bool(retry_diag["retryable"]),
                        "cancel_origin": "none",
                    }
                    terminal_result = await _finalize_task_terminal_state(
                        db=db,
                        task=task,
                        task_id=task_id,
                        event_emitter=event_emitter,
                        event_manager=event_manager,
                        desired_status=AgentTaskStatus.FAILED,
                        failure_message=failure_message,
                        failure_metadata=failure_metadata,
                        skip_drain_wait=bool(is_task_cancelled(task_id)),
                        timeout_seconds=TOOL_DRAIN_TIMEOUT_SECONDS,
                    )
                    failure_message = terminal_result["failure_message"] or failure_message
                    failure_metadata = terminal_result["failure_metadata"]
                    logger.error(f"Task {task_id} failed: {result.error}")
            
        except asyncio.CancelledError:
            logger.info(f"Task {task_id} cancelled")
            try:
                task = await db.get(AgentTask, task_id)
                if task:
                    _snapshot_runtime_stats_to_task(task, _running_orchestrators.get(task_id))
                    await _finalize_task_terminal_state(
                        db=db,
                        task=task,
                        task_id=task_id,
                        event_emitter=event_emitter,
                        event_manager=event_manager,
                        desired_status=AgentTaskStatus.CANCELLED,
                        cancel_message="任务已取消",
                        skip_drain_wait=True,
                        timeout_seconds=TOOL_DRAIN_TIMEOUT_SECONDS,
                    )
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            retry_diag = _classify_retry_error(e)
            failure_metadata = {
                "step_name": "UNKNOWN",
                "attempt": 1,
                "retry_attempt": 1,
                "max_attempts": 1,
                "is_terminal": True,
                "retry_error_class": retry_diag["code"],
                "retryable": bool(retry_diag["retryable"]),
                "cancel_origin": "none",
            }
            failure_message = str(e)[:1000]
            if isinstance(e, StepRetryExceededError):
                final_diag = _classify_retry_error(e.last_error)
                failure_metadata = {
                    "step_name": e.step_name,
                    "attempt": e.attempts,
                    "retry_attempt": e.attempts,
                    "max_attempts": e.max_attempts,
                    "is_terminal": True,
                    "retry_error_class": final_diag["code"],
                    "retryable": bool(final_diag["retryable"]),
                    "cancel_origin": (
                        "user"
                        if "cancelled_user" in str(final_diag.get("code"))
                        else "none"
                    ),
                }
                failure_message = e.final_message[:1000]

            task = None
            try:
                task = await db.get(AgentTask, task_id)
                if task:
                    _snapshot_runtime_stats_to_task(task, _running_orchestrators.get(task_id))
            except Exception as db_error:
                logger.error(f"Failed to update task status: {db_error}")

            try:
                skip_drain_wait = bool(
                    is_task_cancelled(task_id)
                    or str(failure_metadata.get("cancel_origin") or "").strip().lower() == "user"
                )
                if task:
                    terminal_result = await _finalize_task_terminal_state(
                        db=db,
                        task=task,
                        task_id=task_id,
                        event_emitter=event_emitter,
                        event_manager=event_manager,
                        desired_status=AgentTaskStatus.FAILED,
                        failure_message=failure_message,
                        failure_metadata=failure_metadata,
                        skip_drain_wait=skip_drain_wait,
                        timeout_seconds=TOOL_DRAIN_TIMEOUT_SECONDS,
                    )
                    failure_message = terminal_result["failure_message"] or failure_message
                    failure_metadata = terminal_result["failure_metadata"]
                else:
                    await event_emitter.emit_task_error(
                        failure_message,
                        message=f"任务失败: {failure_message}",
                        metadata=failure_metadata,
                    )
                    await event_emitter.emit_error(
                        failure_message,
                        metadata=failure_metadata,
                    )
            except Exception as emit_error:
                logger.warning(f"Failed to emit terminal task error event: {emit_error}")
        finally:
            # 在清理之前保存 Agent 树到数据库
            try:
                async with async_session_factory() as save_db:
                    await _save_agent_tree(save_db, task_id)
            except Exception as save_error:
                logger.error(f"Failed to save agent tree: {save_error}")

            try:
                cleared_nodes = agent_registry.clear_task(task_id)
                logger.debug("Cleared %s runtime agent nodes for task %s", cleared_nodes, task_id)
            except Exception as clear_error:
                logger.warning("Failed to clear runtime agent tree for task %s: %s", task_id, clear_error)

            # 清理
            _running_orchestrators.pop(task_id, None)
            _running_tasks.pop(task_id, None)
            _running_event_managers.pop(task_id, None)
            _running_asyncio_tasks.pop(task_id, None)  # 清理 asyncio task
            _running_queue_services.pop(task_id, None)
            _running_recon_queue_services.pop(task_id, None)
            _running_bl_queue_services.pop(task_id, None)
            _cancelled_tasks.discard(task_id)  # 清理取消标志

            logger.debug(f"Task {task_id} cleaned up")

async def _get_user_config(db: AsyncSession, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """获取用户配置"""
    if not user_id:
        return None
    
    try:
        from app.services.user_config_service import load_effective_user_config

        return await load_effective_user_config(
            db=db,
            user_id=user_id,
        )
    except Exception as e:
        logger.warning(f"Failed to get user config: {e}")
    
    return None


async def _initialize_tools(
    project_root: str,
    llm_service,
    user_config: Optional[Dict[str, Any]],
    sandbox_manager: Any, # 传递预初始化的 SandboxManager
    verification_level: str = "analysis_with_poc_plan",
    exclude_patterns: Optional[List[str]] = None,
    target_files: Optional[List[str]] = None,
    project_id: Optional[str] = None,
    event_emitter: Optional[Any] = None,  # 新增：用于发送实时日志
    task_id: Optional[str] = None,  # 新增：用于取消检查
    queue_service: Optional[Any] = None,  # 新增：漏洞队列服务
    recon_queue_service: Optional[Any] = None,  # 新增：Recon 风险队列服务
    bl_queue_service: Optional[Any] = None,  # 新增：业务逻辑风险队列服务
    save_callback: Optional[Any] = None,  # 新增：验证结果持久化回调 async (findings) -> int
) -> Dict[str, Dict[str, Any]]:
    """初始化工具集。"""
    from app.services.agent.tools import (
        CodeWindowTool,
        FileOutlineTool,
        FileSearchTool,
        FunctionSummaryTool,
        ListFilesTool,
        LocateEnclosingFunctionTool,
        PatternMatchTool,
        DataFlowAnalysisTool,
        CreateVulnerabilityReportTool,
        ControlFlowAnalysisLightTool,
        LogicAuthzAnalysisTool,
        SandboxTool,
        VulnerabilityVerifyTool,
        RunCodeTool,
        SmartScanTool,
        QuickAuditTool,
        SymbolBodyTool,
        UpdateReconFileTreeTool,
    )
    from app.services.agent.tools.queue_tools import (
        GetQueueStatusTool, DequeueFindingTool, PushFindingToQueueTool, IsFindingInQueueTool
    )
    from app.services.agent.tools.recon_queue_tools import (
        GetReconRiskQueueStatusTool,
        PushRiskPointToQueueTool,
        PushRiskPointsBatchToQueueTool,
        DequeueReconRiskPointTool,
        PeekReconRiskQueueTool,
        ClearReconRiskQueueTool,
        IsReconRiskPointInQueueTool,
    )
    from app.services.agent.tools.business_logic_recon_queue_tools import (
        PushBLRiskPointToQueueTool,
        PushBLRiskPointsBatchToQueueTool,
        GetBLRiskQueueStatusTool,
        DequeueBLRiskPointTool,
        PeekBLRiskQueueTool,
        ClearBLRiskQueueTool,
        IsBLRiskPointInQueueTool,
    )

    _ = verification_level
    _ = project_id
    _ = user_config

    async def emit(message: str, level: str = "info"):
        if event_emitter:
            logger.debug(f"[EMIT-TOOLS] Sending {level}: {message[:60]}...")
            if level == "info":
                await event_emitter.emit_info(message)
            elif level == "warning":
                await event_emitter.emit_warning(message)
            elif level == "error":
                await event_emitter.emit_error(message)
        else:
            logger.warning(f"[EMIT-TOOLS] No event_emitter, skipping: {message[:60]}...")

    # logger.info("向量检索模块已禁用，跳过索引初始化")
    # await emit("向量检索模块已禁用，跳过索引初始化")

    base_tools = {
        "list_files": ListFilesTool(project_root, exclude_patterns, target_files),
        "search_code": FileSearchTool(project_root, exclude_patterns, target_files),
        "get_code_window": CodeWindowTool(project_root, exclude_patterns, target_files),
        "get_file_outline": FileOutlineTool(project_root, exclude_patterns, target_files),
        "get_function_summary": FunctionSummaryTool(project_root, exclude_patterns, target_files),
        "get_symbol_body": SymbolBodyTool(project_root, exclude_patterns, target_files),
        "locate_enclosing_function": LocateEnclosingFunctionTool(
            project_root,
            exclude_patterns,
            target_files,
        ),
    }

    recon_tools = {**base_tools}
    if recon_queue_service and task_id:
        recon_tools["push_risk_point_to_queue"] = PushRiskPointToQueueTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        recon_tools["push_risk_points_to_queue"] = PushRiskPointsBatchToQueueTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        recon_tools["get_recon_risk_queue_status"] = GetReconRiskQueueStatusTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        recon_tools["is_recon_risk_point_in_queue"] = IsReconRiskPointInQueueTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        recon_tools["update_recon_file_tree"] = UpdateReconFileTreeTool(task_id=task_id)
        logger.info(f"[Tools] Added Recon risk queue tools for task {task_id}")

    analysis_tools = {
        **base_tools,
        "smart_scan": SmartScanTool(project_root, exclude_patterns=exclude_patterns or []),
        "quick_audit": QuickAuditTool(project_root),
        "pattern_match": PatternMatchTool(project_root),
        "dataflow_analysis": DataFlowAnalysisTool(llm_service, project_root=project_root),
        "controlflow_analysis_light": ControlFlowAnalysisLightTool(
            project_root=project_root,
            target_files=target_files,
        ),
        "logic_authz_analysis": LogicAuthzAnalysisTool(
            project_root=project_root,
            target_files=target_files,
        ),
    }

    verification_tools = {
        **base_tools,
        "sandbox_exec": SandboxTool(sandbox_manager),
        "verify_vulnerability": VulnerabilityVerifyTool(sandbox_manager),
        "run_code": RunCodeTool(sandbox_manager, project_root),
        "create_vulnerability_report": CreateVulnerabilityReportTool(project_root),
    }

    if task_id:
        from app.services.agent.tools.verification_result_tools import (
            SaveVerificationResultTool,
            UpdateVulnerabilityFindingTool,
        )

        verification_tools["save_verification_result"] = SaveVerificationResultTool(
            task_id=task_id,
            save_callback=save_callback,
        )
        logger.info("[Tools] Added save_verification_result tool for task %s", task_id)
        report_update_tool = UpdateVulnerabilityFindingTool(
            task_id=task_id,
            update_callback=None,
        )
    else:
        report_update_tool = None

    orchestrator_tools = {**base_tools}

    if queue_service and task_id:
        orchestrator_tools["get_queue_status"] = GetQueueStatusTool(queue_service, task_id)
        orchestrator_tools["dequeue_finding"] = DequeueFindingTool(queue_service, task_id)
        analysis_tools["push_finding_to_queue"] = PushFindingToQueueTool(queue_service, task_id)
        analysis_tools["is_finding_in_queue"] = IsFindingInQueueTool(queue_service, task_id)
        logger.info(f"[Tools] Added analysis queue tools for task {task_id}")

    if recon_queue_service and task_id:
        orchestrator_tools["get_recon_risk_queue_status"] = GetReconRiskQueueStatusTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["dequeue_recon_risk_point"] = DequeueReconRiskPointTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["peek_recon_risk_queue"] = PeekReconRiskQueueTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["clear_recon_risk_queue"] = ClearReconRiskQueueTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["is_recon_risk_point_in_queue"] = IsReconRiskPointInQueueTool(
            queue_service=recon_queue_service,
            task_id=task_id,
        )
        logger.info(f"[Tools] Added Recon queue tools for task {task_id}")

    bl_recon_tools = {**base_tools}
    bl_analysis_tools = {**base_tools}

    if bl_queue_service and task_id:
        bl_recon_tools["push_bl_risk_point_to_queue"] = PushBLRiskPointToQueueTool(
            queue_service=bl_queue_service,
            task_id=task_id,
        )
        bl_recon_tools["push_bl_risk_points_to_queue"] = PushBLRiskPointsBatchToQueueTool(
            queue_service=bl_queue_service,
            task_id=task_id,
        )
        bl_recon_tools["get_bl_risk_queue_status"] = GetBLRiskQueueStatusTool(
            queue_service=bl_queue_service,
            task_id=task_id,
        )
        bl_recon_tools["is_bl_risk_point_in_queue"] = IsBLRiskPointInQueueTool(
            queue_service=bl_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["get_bl_risk_queue_status"] = GetBLRiskQueueStatusTool(
            queue_service=bl_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["dequeue_bl_risk_point"] = DequeueBLRiskPointTool(
            queue_service=bl_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["peek_bl_risk_queue"] = PeekBLRiskQueueTool(
            queue_service=bl_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["clear_bl_risk_queue"] = ClearBLRiskQueueTool(
            queue_service=bl_queue_service,
            task_id=task_id,
        )
        orchestrator_tools["is_bl_risk_point_in_queue"] = IsBLRiskPointInQueueTool(
            queue_service=bl_queue_service,
            task_id=task_id,
        )
        logger.info(f"[Tools] Added BL risk queue tools for task {task_id}")

    if queue_service and task_id:
        bl_analysis_tools["push_finding_to_queue"] = PushFindingToQueueTool(queue_service, task_id)
        bl_analysis_tools["is_finding_in_queue"] = IsFindingInQueueTool(queue_service, task_id)

    return {
        "recon": recon_tools,
        "analysis": analysis_tools,
        "verification": verification_tools,
        "orchestrator": orchestrator_tools,
        "business_logic_recon": bl_recon_tools,
        "business_logic_analysis": bl_analysis_tools,
        "report": {
            "list_files": ListFilesTool(project_root, exclude_patterns, target_files),
            "search_code": FileSearchTool(project_root, exclude_patterns, target_files),
            "get_code_window": CodeWindowTool(project_root, exclude_patterns, target_files),
            "get_file_outline": FileOutlineTool(project_root, exclude_patterns, target_files),
            "get_function_summary": FunctionSummaryTool(project_root, exclude_patterns, target_files),
            "get_symbol_body": SymbolBodyTool(project_root, exclude_patterns, target_files),
            "dataflow_analysis": DataFlowAnalysisTool(llm_service, project_root=project_root),
            **(
                {"update_vulnerability_finding": report_update_tool}
                if report_update_tool is not None
                else {}
            ),
        },
    }


def _reset_task_workspace_sync(base_path: str) -> None:
    if os.path.exists(base_path):
        shutil.rmtree(base_path)
    os.makedirs(base_path, exist_ok=True)


def _extract_zip_project_sync(
    zip_path: str,
    base_path: str,
    check_cancelled: Optional[Callable[[], None]] = None,
) -> None:
    import zipfile

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        file_list = zip_ref.namelist()
        for i, file_name in enumerate(file_list):
            if check_cancelled and i % 50 == 0:
                check_cancelled()
            zip_ref.extract(file_name, base_path)


def _collect_project_info_sync(
    project_root: str, 
    project_name: str,
    exclude_patterns: Optional[List[str]] = None,
    target_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """收集项目信息
    
    Args:
        project_root: 项目根目录
        project_name: 项目名称
        exclude_patterns: 排除模式列表
        target_files: 目标文件列表
    
    重要：当指定了 target_files 时，返回的项目结构应该只包含目标文件相关的信息，
    以确保 Orchestrator 和子 Agent 看到的是一致的、过滤后的视图。
    """
    effective_exclude_patterns = _build_core_audit_exclude_patterns(exclude_patterns)

    info = {
        "name": project_name,
        "root": project_root,
        "languages": [],
        "file_count": 0,
        "structure": {},
    }
    
    try:
        # 目标文件集合
        target_files_set = (
            {_normalize_scan_path(path) for path in target_files if isinstance(path, str)}
            if target_files
            else None
        )
        
        lang_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".java": "Java", ".go": "Go", ".php": "PHP",
            ".rb": "Ruby", ".rs": "Rust", ".c": "C", ".cpp": "C++",
        }
        
        # 收集过滤后的文件列表
        filtered_files = []
        filtered_dirs = set()
        
        for root, dirs, files in os.walk(project_root):
            rel_dir = os.path.relpath(root, project_root).replace("\\", "/")
            if rel_dir == ".":
                rel_dir = ""
            dirs[:] = [
                d
                for d in dirs
                if not _is_core_ignored_path(
                    f"{rel_dir}/{d}" if rel_dir else d,
                    effective_exclude_patterns,
                )
            ]
            
            for f in files:
                relative_path = os.path.relpath(os.path.join(root, f), project_root)
                relative_path = relative_path.replace("\\", "/")
                
                # 检查是否在目标文件列表中
                if target_files_set and _normalize_scan_path(relative_path) not in target_files_set:
                    continue
                if _is_core_ignored_path(relative_path, effective_exclude_patterns):
                    continue
                
                info["file_count"] += 1
                filtered_files.append(relative_path)
                
                # 收集文件所在的目录
                dir_path = os.path.dirname(relative_path)
                if dir_path:
                    # 添加目录及其父目录
                    parts = dir_path.split(os.sep)
                    for i in range(len(parts)):
                        filtered_dirs.add(os.sep.join(parts[:i+1]))
                
                ext = os.path.splitext(f)[1].lower()
                if ext in lang_map and lang_map[ext] not in info["languages"]:
                    info["languages"].append(lang_map[ext])
        
        # 根据是否有目标文件限制，生成不同的结构信息
        if target_files_set:
            # 当指定了目标文件时，只显示目标文件和相关目录
            info["structure"] = {
                "directories": sorted(list(filtered_dirs))[:20],
                "files": filtered_files[:30],
                "scope_limited": True,  # 标记这是限定范围的视图
                "scope_message": f"审计范围限定为 {len(filtered_files)} 个指定文件",
            }
        else:
            # 全项目审计时，显示顶层目录结构
            try:
                top_items = os.listdir(project_root)
                info["structure"] = {
                    "directories": [
                        d
                        for d in top_items
                        if os.path.isdir(os.path.join(project_root, d))
                        and not _is_core_ignored_path(d, effective_exclude_patterns)
                    ],
                    "files": [
                        f
                        for f in top_items
                        if os.path.isfile(os.path.join(project_root, f))
                        and not _is_core_ignored_path(f, effective_exclude_patterns)
                    ][:20],
                    "scope_limited": False,
                }
            except Exception:
                pass
            
    except Exception as e:
        logger.warning(f"Failed to collect project info: {e}")
    
    return info


async def _collect_project_info(
    project_root: str, 
    project_name: str,
    exclude_patterns: Optional[List[str]] = None,
    target_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _collect_project_info_sync,
        project_root,
        project_name,
        exclude_patterns,
        target_files,
    )

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
    # 辅助函数：发送事件
    async def emit(message: str, level: str = "info"):
        if event_emitter:
            if level == "info":
                await event_emitter.emit_info(message)
            elif level == "warning":
                await event_emitter.emit_warning(message)
            elif level == "error":
                await event_emitter.emit_error(message)

    # 辅助函数：检查取消状态
    def check_cancelled():
        if is_task_cancelled(task_id):
            raise asyncio.CancelledError("任务已取消")

    base_path = f"/tmp/VulHunter/{task_id}"

    # 确保目录存在且为空
    await asyncio.to_thread(_reset_task_workspace_sync, base_path)

    # 在开始任何操作前检查取消
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
            await asyncio.to_thread(
                _extract_zip_project_sync,
                zip_path,
                base_path,
                check_cancelled,
            )
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

    # 智能检测：如果解压后只有一个子目录（常见于 ZIP 文件），
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

    await emit(f"项目准备完成: {base_path}")
    return base_path


__all__ = [name for name in globals() if not name.startswith("__")]
