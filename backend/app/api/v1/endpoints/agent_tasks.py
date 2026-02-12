"""
DeepAudit Agent 审计任务 API
基于 LangGraph 的 Agent 审计
"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Dict, Set, Tuple
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import case
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, Field
import yaml

from app.api import deps
from app.db.session import get_db, async_session_factory
from app.models.agent_task import (
    AgentTask, AgentEvent, AgentFinding,
    AgentTaskStatus, AgentTaskPhase, AgentEventType,
    VulnerabilitySeverity, FindingStatus,
)
from app.models.project import Project
from app.models.opengrep import OpengrepScanTask, OpengrepFinding, OpengrepRule
from app.models.user import User
from app.models.user_config import UserConfig
from app.services.agent.event_manager import EventManager
from app.services.agent.streaming import StreamHandler, StreamEvent, StreamEventType
from app.services.git_ssh_service import GitSSHOperations
from app.core.encryption import decrypt_sensitive_data

logger = logging.getLogger(__name__)
router = APIRouter()

# 运行中的任务（兼容旧接口）
_running_tasks: Dict[str, Any] = {}

# 🔥 运行中的 asyncio Tasks（用于强制取消）
_running_asyncio_tasks: Dict[str, asyncio.Task] = {}


# ============ Schemas ============

class AgentTaskCreate(BaseModel):
    """创建 Agent 任务请求"""
    project_id: str = Field(..., description="项目 ID")
    name: Optional[str] = Field(None, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    
    # 审计配置
    audit_scope: Optional[dict] = Field(None, description="审计范围")
    target_vulnerabilities: Optional[List[str]] = Field(
        default=["sql_injection", "xss", "command_injection", "path_traversal", "ssrf"],
        description="目标漏洞类型"
    )
    verification_level: str = Field(
        "sandbox", 
        description="验证级别: analysis_only, sandbox, generate_poc"
    )
    
    # 分支
    branch_name: Optional[str] = Field(None, description="分支名称")
    
    # 排除模式
    exclude_patterns: Optional[List[str]] = Field(
        default=["node_modules", "__pycache__", ".git", "*.min.js"],
        description="排除模式"
    )
    
    # 文件范围
    target_files: Optional[List[str]] = Field(None, description="指定扫描的文件")
    
    # Agent 配置
    max_iterations: int = Field(50, ge=1, le=200, description="最大迭代次数")
    timeout_seconds: int = Field(1800, ge=60, le=7200, description="超时时间（秒）")


class AgentTaskResponse(BaseModel):
    """Agent 任务响应 - 包含所有前端需要的字段"""
    id: str
    project_id: str
    name: Optional[str]
    description: Optional[str]
    task_type: str = "agent_audit"
    status: str
    current_phase: Optional[str]
    current_step: Optional[str] = None
    
    # 进度统计
    total_files: int = 0
    indexed_files: int = 0
    analyzed_files: int = 0
    total_chunks: int = 0
    
    # Agent 统计
    total_iterations: int = 0
    tool_calls_count: int = 0
    tokens_used: int = 0
    
    # 发现统计（兼容两种命名）
    findings_count: int = 0
    total_findings: int = 0  # 兼容字段
    verified_count: int = 0
    verified_findings: int = 0  # 兼容字段
    false_positive_count: int = 0
    
    # 严重程度统计
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    
    # 评分
    quality_score: float = 0.0
    security_score: Optional[float] = None
    
    # 进度百分比
    progress_percentage: float = 0.0
    
    # 时间
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # 配置
    audit_scope: Optional[dict] = None
    target_vulnerabilities: Optional[List[str]] = None
    verification_level: Optional[str] = None
    exclude_patterns: Optional[List[str]] = None
    target_files: Optional[List[str]] = None
    
    # 错误信息
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True


class AgentEventResponse(BaseModel):
    """Agent 事件响应"""
    id: str
    task_id: str
    event_type: str
    phase: Optional[str]
    message: Optional[str] = None
    sequence: int
    # 🔥 ORM 字段名是 created_at，序列化为 timestamp
    created_at: datetime = Field(serialization_alias="timestamp")

    # 工具相关字段
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Dict[str, Any]] = None
    tool_duration_ms: Optional[int] = None

    # 其他字段
    progress_percent: Optional[float] = None
    finding_id: Optional[str] = None
    tokens_used: Optional[int] = None
    # 🔥 ORM 字段名是 event_metadata，序列化为 metadata
    event_metadata: Optional[Dict[str, Any]] = Field(default=None, serialization_alias="metadata")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "by_alias": True,  # 🔥 关键：确保序列化时使用别名
    }


class AgentFindingResponse(BaseModel):
    """Agent 发现响应"""
    id: str
    task_id: str
    vulnerability_type: str
    severity: str
    title: str
    description: Optional[str]
    file_path: Optional[str]
    line_start: Optional[int]
    line_end: Optional[int]
    code_snippet: Optional[str]
    code_context: Optional[str] = None
    context_start_line: Optional[int] = None
    context_end_line: Optional[int] = None
    
    is_verified: bool
    # 🔥 FIX: Map from ai_confidence in ORM, make Optional with default
    confidence: Optional[float] = Field(default=0.5, validation_alias="ai_confidence")
    reachability: Optional[str] = None
    authenticity: Optional[str] = None
    verification_evidence: Optional[str] = None
    status: str
    
    suggestion: Optional[str] = None
    poc: Optional[dict] = None
    
    created_at: datetime
    
    model_config = {
        "from_attributes": True,
        "populate_by_name": True,  # Allow both 'confidence' and 'ai_confidence'
    }


class TaskSummaryResponse(BaseModel):
    """任务摘要响应"""
    task_id: str
    status: str
    security_score: Optional[int]
    
    total_findings: int
    verified_findings: int
    
    severity_distribution: Dict[str, int]
    vulnerability_types: Dict[str, int]
    
    duration_seconds: Optional[int]
    phases_completed: List[str]


# ============ 后台任务执行 ============

# 运行中的动态执行器
_running_orchestrators: Dict[str, Any] = {}
# 运行中的事件管理器（用于 SSE 流）
_running_event_managers: Dict[str, EventManager] = {}
# 🔥 已取消的任务集合（用于前置操作的取消检查）
_cancelled_tasks: Set[str] = set()


def is_task_cancelled(task_id: str) -> bool:
    """检查任务是否已被取消"""
    return task_id in _cancelled_tasks


def _normalize_bootstrap_confidence(confidence: Any) -> Optional[str]:
    normalized = str(confidence or "").strip().upper()
    if normalized in {"HIGH", "MEDIUM", "LOW"}:
        return normalized
    return None


def _extract_bootstrap_rule_lookup_keys(check_id: Any) -> List[str]:
    raw_check_id = str(check_id or "").strip()
    if not raw_check_id:
        return []

    keys: List[str] = []

    def _append(value: str) -> None:
        normalized = str(value or "").strip()
        if normalized and normalized not in keys:
            keys.append(normalized)

    _append(raw_check_id)
    if "." in raw_check_id:
        _append(raw_check_id.rsplit(".", 1)[-1])
    return keys


def _extract_bootstrap_payload_confidence(rule_data: Any) -> Optional[str]:
    if not isinstance(rule_data, dict):
        return None

    direct_confidence = _normalize_bootstrap_confidence(rule_data.get("confidence"))
    if direct_confidence:
        return direct_confidence

    extra = rule_data.get("extra")
    if isinstance(extra, dict):
        extra_confidence = _normalize_bootstrap_confidence(extra.get("confidence"))
        if extra_confidence:
            return extra_confidence

        extra_metadata = extra.get("metadata")
        if isinstance(extra_metadata, dict):
            metadata_confidence = _normalize_bootstrap_confidence(
                extra_metadata.get("confidence")
            )
            if metadata_confidence:
                return metadata_confidence

    metadata = rule_data.get("metadata")
    if isinstance(metadata, dict):
        metadata_confidence = _normalize_bootstrap_confidence(metadata.get("confidence"))
        if metadata_confidence:
            return metadata_confidence

    return None


def _parse_bootstrap_opengrep_output(stdout: str) -> List[Dict[str, Any]]:
    if not stdout or not stdout.strip():
        return []

    output = json.loads(stdout)
    if isinstance(output, dict):
        results = output.get("results", [])
    elif isinstance(output, list):
        results = output
    else:
        raise ValueError("Unexpected opengrep output type")

    if not isinstance(results, list):
        raise ValueError("Invalid opengrep results format")

    parsed: List[Dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict):
            parsed.append(item)
    return parsed


def _build_bootstrap_confidence_map_from_rules(
    rules: List[OpengrepRule],
) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for rule in rules:
        normalized_confidence = _normalize_bootstrap_confidence(rule.confidence)
        if not normalized_confidence:
            continue
        lookup_values = [rule.id, rule.name]
        for raw_value in lookup_values:
            for key in _extract_bootstrap_rule_lookup_keys(raw_value):
                mapping[key] = normalized_confidence
    return mapping


async def _build_bootstrap_confidence_map_for_scan_task(
    db: AsyncSession,
    scan_task: OpengrepScanTask,
) -> Dict[str, str]:
    rule_ids: List[str] = []
    raw_rulesets = scan_task.rulesets
    parsed_rulesets: Any = raw_rulesets

    if isinstance(raw_rulesets, str):
        try:
            parsed_rulesets = json.loads(raw_rulesets)
        except Exception:
            parsed_rulesets = []

    if isinstance(parsed_rulesets, list):
        for item in parsed_rulesets:
            if isinstance(item, dict):
                rule_id = item.get("rule_id")
                if isinstance(rule_id, str) and rule_id:
                    rule_ids.append(rule_id)

    if not rule_ids:
        return {}

    result = await db.execute(
        select(OpengrepRule).where(OpengrepRule.id.in_(list(set(rule_ids))))
    )
    rules = result.scalars().all()
    return _build_bootstrap_confidence_map_from_rules(rules)


def _normalize_bootstrap_finding_from_opengrep(
    finding: OpengrepFinding,
    confidence_map: Dict[str, str],
) -> Dict[str, Any]:
    rule_data = finding.rule if isinstance(finding.rule, dict) else {}
    check_id = None
    if isinstance(rule_data, dict):
        check_id = rule_data.get("check_id") or rule_data.get("id")

    confidence = _extract_bootstrap_payload_confidence(rule_data)
    if confidence is None:
        for key in _extract_bootstrap_rule_lookup_keys(check_id):
            mapped = confidence_map.get(key)
            if mapped:
                confidence = mapped
                break

    severity_text = str(finding.severity or "").strip().upper()
    start_line = finding.start_line
    extra = rule_data.get("extra") if isinstance(rule_data, dict) else {}
    title = None
    description = finding.description
    if isinstance(extra, dict):
        title = extra.get("message")
    if not title:
        title = finding.description or str(check_id or "OpenGrep 发现")

    return {
        "id": finding.id,
        "title": str(title),
        "description": description,
        "file_path": finding.file_path,
        "line_start": start_line,
        "line_end": start_line,
        "code_snippet": finding.code_snippet,
        "severity": severity_text,
        "confidence": confidence,
        "vulnerability_type": str(check_id or "opengrep_rule"),
        "source": "opengrep_bootstrap",
    }


def _filter_bootstrap_findings(
    normalized_findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in normalized_findings:
        severity_value = str(item.get("severity") or "").upper()
        confidence_value = _normalize_bootstrap_confidence(item.get("confidence"))
        if severity_value != "ERROR":
            continue
        if confidence_value not in {"HIGH", "MEDIUM"}:
            continue
        copied = dict(item)
        copied["confidence"] = confidence_value
        filtered.append(copied)
    return filtered


async def _run_bootstrap_opengrep_scan(
    project_root: str,
    active_rules: List[OpengrepRule],
) -> List[Dict[str, Any]]:
    merged_rules: List[Dict[str, Any]] = []
    for rule in active_rules:
        try:
            parsed_yaml = yaml.safe_load(rule.pattern_yaml)
        except Exception:
            continue
        if not isinstance(parsed_yaml, dict):
            continue
        rule_items = parsed_yaml.get("rules")
        if not isinstance(rule_items, list):
            continue
        for item in rule_items:
            if isinstance(item, dict):
                merged_rules.append(item)

    if not merged_rules:
        raise ValueError("No executable opengrep rules found")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tf:
        yaml.dump({"rules": merged_rules}, tf, sort_keys=False, default_flow_style=False)
        merged_rule_path = tf.name

    try:
        cmd = ["opengrep", "--config", merged_rule_path, "--json", project_root]
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
        )
        findings = _parse_bootstrap_opengrep_output(result.stdout or "")
        if result.returncode != 0 and not findings:
            stderr_text = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"opengrep failed: {stderr_text[:300]}")
        return findings
    finally:
        try:
            os.unlink(merged_rule_path)
        except Exception:
            pass


async def _collect_bootstrap_findings_for_task(
    db: AsyncSession,
    scan_task: OpengrepScanTask,
) -> List[Dict[str, Any]]:
    confidence_map = await _build_bootstrap_confidence_map_for_scan_task(db, scan_task)
    findings_result = await db.execute(
        select(OpengrepFinding).where(OpengrepFinding.scan_task_id == scan_task.id)
    )
    findings = findings_result.scalars().all()
    normalized = [
        _normalize_bootstrap_finding_from_opengrep(item, confidence_map)
        for item in findings
    ]
    return _filter_bootstrap_findings(normalized)


async def _prepare_bootstrap_opengrep_findings(
    db: AsyncSession,
    project_id: str,
    project_root: str,
    event_emitter: Any,
) -> Tuple[List[Dict[str, Any]], Optional[str], str]:
    latest_task_result = await db.execute(
        select(OpengrepScanTask)
        .where(OpengrepScanTask.project_id == project_id)
        .where(OpengrepScanTask.status == "completed")
        .order_by(OpengrepScanTask.created_at.desc())
        .limit(1)
    )
    latest_task = latest_task_result.scalar_one_or_none()

    if latest_task:
        candidates = await _collect_bootstrap_findings_for_task(db, latest_task)
        await event_emitter.emit_info(
            f"🔁 OpenGrep 预处理复用最近结果: task={latest_task.id}, 候选={len(candidates)}"
        )
        return candidates, latest_task.id, "reuse"

    active_rules_result = await db.execute(
        select(OpengrepRule).where(OpengrepRule.is_active == True)
    )
    active_rules = active_rules_result.scalars().all()
    if not active_rules:
        await event_emitter.emit_warning(
            "⚠️ OpenGrep 预处理降级：当前没有启用规则，跳过预扫描"
        )
        return [], None, "degraded_no_rules"

    scan_task = OpengrepScanTask(
        project_id=project_id,
        name=f"Agent Bootstrap OpenGrep {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        status="running",
        target_path=".",
        rulesets=json.dumps([{"rule_id": rule.id} for rule in active_rules]),
    )
    db.add(scan_task)
    await db.commit()
    await db.refresh(scan_task)

    await event_emitter.emit_info(
        f"🧪 OpenGrep 预处理开始：未发现可复用结果，启动阻塞式预扫描（task={scan_task.id}）"
    )

    try:
        started_at = datetime.now(timezone.utc)
        parsed_findings = await _run_bootstrap_opengrep_scan(project_root, active_rules)
        finished_at = datetime.now(timezone.utc)
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        error_count = 0
        warning_count = 0
        files_scanned: Set[str] = set()
        lines_scanned = 0

        for finding in parsed_findings:
            severity = str(
                finding.get("extra", {}).get("severity", "INFO")
            ).upper()
            if severity == "ERROR":
                error_count += 1
            elif severity == "WARNING":
                warning_count += 1

            file_path = finding.get("path", "")
            if file_path:
                files_scanned.add(file_path)

            start_line = int(finding.get("start", {}).get("line") or 0)
            end_line = int(finding.get("end", {}).get("line") or start_line)
            if end_line >= start_line > 0:
                lines_scanned += end_line - start_line + 1

            db.add(
                OpengrepFinding(
                    scan_task_id=scan_task.id,
                    rule=finding,
                    description=finding.get("extra", {}).get("message"),
                    file_path=file_path,
                    start_line=start_line or None,
                    code_snippet=finding.get("extra", {}).get("lines"),
                    severity=severity,
                    status="open",
                )
            )

        scan_task.status = "completed"
        scan_task.total_findings = len(parsed_findings)
        scan_task.error_count = error_count
        scan_task.warning_count = warning_count
        scan_task.scan_duration_ms = duration_ms
        scan_task.files_scanned = len(files_scanned)
        scan_task.lines_scanned = lines_scanned
        await db.commit()

        candidates = await _collect_bootstrap_findings_for_task(db, scan_task)
        await event_emitter.emit_info(
            f"✅ OpenGrep 预扫描完成: findings={len(parsed_findings)}, 候选={len(candidates)}"
        )
        return candidates, scan_task.id, "scan"
    except FileNotFoundError:
        scan_task.status = "failed"
        scan_task.error_count = 1
        await db.commit()
        await event_emitter.emit_warning(
            "⚠️ OpenGrep 预处理降级：未安装 opengrep，继续执行智能审计"
        )
        return [], scan_task.id, "degraded_tool_missing"
    except Exception as exc:
        scan_task.status = "failed"
        scan_task.error_count = (scan_task.error_count or 0) + 1
        await db.commit()
        await event_emitter.emit_warning(
            f"⚠️ OpenGrep 预处理降级：预扫描失败（{str(exc)[:160]}）"
        )
        return [], scan_task.id, "degraded_scan_failed"


async def _execute_agent_task(task_id: str):
    """
    在后台执行 Agent 任务 - 使用动态 Agent 树架构
    
    架构：OrchestratorAgent 作为大脑，动态调度子 Agent
    """
    from app.services.agent.agents import OrchestratorAgent, ReconAgent, AnalysisAgent, VerificationAgent
    from app.services.agent.event_manager import EventManager, AgentEventEmitter
    from app.services.llm.service import LLMService
    from app.services.agent.core import agent_registry
    from app.services.agent.tools import SandboxManager
    from app.core.config import settings
    import time
    
    # 🔥 在任务最开始就初始化 Docker 沙箱管理器
    # 这样可以确保整个任务生命周期内使用同一个管理器，并且尽早发现 Docker 问题
    logger.info(f"🚀 Starting execution for task {task_id}")
    sandbox_manager = SandboxManager()
    await sandbox_manager.initialize()
    logger.info(f"🐳 Global Sandbox Manager initialized (Available: {sandbox_manager.is_available})")

    # 🔥 提前创建事件管理器，以便在克隆仓库和索引时发送实时日志
    from app.services.agent.event_manager import EventManager, AgentEventEmitter
    event_manager = EventManager(db_session_factory=async_session_factory)
    event_manager.create_queue(task_id)
    event_emitter = AgentEventEmitter(task_id, event_manager)
    _running_event_managers[task_id] = event_manager

    async with async_session_factory() as db:
        orchestrator = None
        start_time = time.time()

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

            # 🔥 发送任务开始事件 - 使用 phase_start 让前端知道进入准备阶段
            await event_emitter.emit_phase_start("preparation", f"🚀 任务开始执行: {project.name}")

            # 更新任务阶段为准备中
            task.status = AgentTaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            task.current_phase = AgentTaskPhase.PLANNING  # preparation 对应 PLANNING
            await db.commit()

            # 获取用户配置（需要在获取项目根目录之前，以便传递 token）
            user_config = await _get_user_config(db, task.created_by)

            # 从用户配置中提取 token和SSH密钥（用于私有仓库克隆）
            other_config = (user_config or {}).get('otherConfig', {})
            github_token = other_config.get('githubToken') or settings.GITHUB_TOKEN
            gitlab_token = other_config.get('gitlabToken') or settings.GITLAB_TOKEN
            gitea_token = other_config.get('giteaToken') or settings.GITEA_TOKEN

            # 解密SSH私钥
            ssh_private_key = None
            if 'sshPrivateKey' in other_config:
                try:
                    encrypted_key = other_config['sshPrivateKey']
                    ssh_private_key = decrypt_sensitive_data(encrypted_key)
                    logger.info("成功解密SSH私钥")
                except Exception as e:
                    logger.warning(f"解密SSH私钥失败: {e}")

            # 获取项目根目录（传递任务指定的分支和认证 token/SSH密钥）
            # 🔥 传递 event_emitter 以发送克隆进度
            project_root = await _get_project_root(
                project,
                task_id,
                task.branch_name,
                github_token=github_token,
                gitlab_token=gitlab_token,
                gitea_token=gitea_token,  # 🔥 新增
                ssh_private_key=ssh_private_key,  # 🔥 新增SSH密钥
                event_emitter=event_emitter,  # 🔥 新增
            )

            # 🔥 自动修正 target_files 路径
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
                        logger.info(f"🔧 Auto-fixed {fixed_count} target file paths")
                        await event_emitter.emit_info(f"🔧 自动修正了 {fixed_count} 个目标文件的路径")
                        task.target_files = new_target_files
                        
            # 🔥 重新验证修正后的文件
            valid_target_files = []
            if task.target_files:
                for tf in task.target_files:
                    if os.path.exists(os.path.join(project_root, tf)):
                        valid_target_files.append(tf)
                    else:
                        logger.warning(f"⚠️ Target file not found: {tf}")
                
                if not valid_target_files:
                    logger.warning("❌ No valid target files found after adjustment!")
                    await event_emitter.emit_warning("⚠️ 警告：无法找到指定的目标文件，将扫描所有文件")
                    task.target_files = None  # 回退到全量扫描
                elif len(valid_target_files) < len(task.target_files):
                    logger.warning(f"⚠️ Partial target files missing. Found {len(valid_target_files)}/{len(task.target_files)}")
                    task.target_files = valid_target_files

            logger.info(f"🚀 Task {task_id} started with Dynamic Agent Tree architecture")

            # 🔥 获取项目根目录后检查取消
            if is_task_cancelled(task_id):
                logger.info(f"[Cancel] Task {task_id} cancelled after project preparation")
                raise asyncio.CancelledError("任务已取消")

            # 创建 LLM 服务
            llm_service = LLMService(user_config=user_config)

            # 初始化工具集 - 传递排除模式和目标文件以及预初始化的 sandbox_manager
            # 🔥 传递 event_emitter 以发送索引进度，传递 task_id 以支持取消
            tools = await _initialize_tools(
                project_root,
                llm_service,
                user_config,
                sandbox_manager=sandbox_manager,
                exclude_patterns=task.exclude_patterns,
                target_files=task.target_files,
                project_id=str(project.id),  # 🔥 传递 project_id 用于 RAG
                event_emitter=event_emitter,  # 🔥 新增
                task_id=task_id,  # 🔥 新增：用于取消检查
            )

            # 🔥 初始化工具后检查取消
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

            # 创建 Orchestrator Agent
            orchestrator = OrchestratorAgent(
                llm_service=llm_service,
                tools=tools.get("orchestrator", {}),
                event_emitter=event_emitter,
                sub_agents={
                    "recon": recon_agent,
                    "analysis": analysis_agent,
                    "verification": verification_agent,
                },
            )

            # 🔥 设置外部取消检查回调
            # 这确保即使 runner.cancel() 失败，Agent 也能通过 checking 全局标志感知取消
            def check_global_cancel():
                return is_task_cancelled(task_id)

            orchestrator.set_cancel_callback(check_global_cancel)
            # 同时也为子 Agent 设置（虽然 Orchestrator 会传播）
            recon_agent.set_cancel_callback(check_global_cancel)
            analysis_agent.set_cancel_callback(check_global_cancel)
            verification_agent.set_cancel_callback(check_global_cancel)

            # 注册到全局
            _running_orchestrators[task_id] = orchestrator
            _running_tasks[task_id] = orchestrator  # 兼容旧的取消逻辑
            _running_event_managers[task_id] = event_manager  # 用于 SSE 流
            
            # 🔥 清理旧的 Agent 注册表，避免显示多个树
            from app.services.agent.core import agent_registry
            agent_registry.clear()
            
            # 注册 Orchestrator 到 Agent Registry（使用其内置方法）
            orchestrator._register_to_registry(task="Root orchestrator for security audit")
            
            await event_emitter.emit_info("🧠 动态 Agent 树架构启动")
            await event_emitter.emit_info(f"📁 项目路径: {project_root}")
            
            # 收集项目信息 - 传递排除模式和目标文件
            project_info = await _collect_project_info(
                project_root, 
                project.name,
                exclude_patterns=task.exclude_patterns,
                target_files=task.target_files,
            )

            bootstrap_findings: List[Dict[str, Any]] = []
            bootstrap_task_id: Optional[str] = None
            bootstrap_source = "none"
            try:
                (
                    bootstrap_findings,
                    bootstrap_task_id,
                    bootstrap_source,
                ) = await _prepare_bootstrap_opengrep_findings(
                    db=db,
                    project_id=str(project.id),
                    project_root=project_root,
                    event_emitter=event_emitter,
                )
            except Exception as bootstrap_error:
                logger.warning(
                    "[AgentTask] Bootstrap OpenGrep stage failed and downgraded: %s",
                    bootstrap_error,
                )
                await event_emitter.emit_warning(
                    f"⚠️ OpenGrep 预处理降级：{str(bootstrap_error)[:160]}"
                )
            
            # 更新任务文件统计
            task.total_files = project_info.get("file_count", 0)
            await db.commit()
            
            # 构建输入数据
            input_data = {
                "project_info": project_info,
                "config": {
                    "target_vulnerabilities": task.target_vulnerabilities or [],
                    "verification_level": task.verification_level or "sandbox",
                    "exclude_patterns": task.exclude_patterns or [],
                    "target_files": task.target_files or [],
                    "max_iterations": task.max_iterations or 50,
                    "bootstrap_findings": bootstrap_findings,
                    "bootstrap_source": bootstrap_source,
                    "bootstrap_task_id": bootstrap_task_id,
                },
                "project_root": project_root,
                "task_id": task_id,
            }
            
            # 执行 Orchestrator
            await event_emitter.emit_phase_start("orchestration", "🎯 Orchestrator 开始编排审计流程")
            task.current_phase = AgentTaskPhase.ANALYSIS
            await db.commit()
            
            # 🔥 将 orchestrator.run() 包装在 asyncio.Task 中，以便可以强制取消
            run_task = asyncio.create_task(orchestrator.run(input_data))
            _running_asyncio_tasks[task_id] = run_task
            
            try:
                result = await run_task
            finally:
                _running_asyncio_tasks.pop(task_id, None)
            
            # 处理结果
            duration_ms = int((time.time() - start_time) * 1000)
            
            await db.refresh(task)
            
            if result.success:
                # 🔥 CRITICAL FIX: Log and save findings with detailed debugging
                findings = result.data.get("findings", [])
                logger.info(f"[AgentTask] Task {task_id} completed with {len(findings)} findings from Orchestrator")

                # 🔥 Debug: Log each finding for verification
                for i, f in enumerate(findings[:5]):  # Log first 5
                    if isinstance(f, dict):
                        logger.debug(f"[AgentTask] Finding {i+1}: {f.get('title', 'N/A')[:50]} - {f.get('severity', 'N/A')}")

                # 🔥 v2.1: 传递 project_root 用于文件路径验证
                saved_count = await _save_findings(db, task_id, findings, project_root=project_root)
                logger.info(f"[AgentTask] Saved {saved_count}/{len(findings)} findings (filtered {len(findings) - saved_count} hallucinations)")

                persisted_findings_result = await db.execute(
                    select(AgentFinding).where(AgentFinding.task_id == task_id)
                )
                persisted_findings = persisted_findings_result.scalars().all()
                effective_findings = [
                    item for item in persisted_findings
                    if str(item.status) != FindingStatus.FALSE_POSITIVE
                ]
                false_positive_findings = [
                    item for item in persisted_findings
                    if str(item.status) == FindingStatus.FALSE_POSITIVE
                ]

                # 更新任务统计
                # 🔥 CRITICAL FIX: 在设置完成前再次检查取消状态
                # 避免 "取消后后端继续运行并最终标记为完成" 的问题
                if is_task_cancelled(task_id):
                    logger.info(f"[AgentTask] Task {task_id} was cancelled, overriding success result")
                    task.status = AgentTaskStatus.CANCELLED
                else:
                    task.status = AgentTaskStatus.COMPLETED
                task.completed_at = datetime.now(timezone.utc)
                task.current_phase = AgentTaskPhase.REPORTING
                task.findings_count = len(effective_findings)
                task.false_positive_count = len(false_positive_findings)

                # 🔥 CRITICAL FIX: 累加所有子 Agent 的统计，而不仅仅是 Orchestrator 的
                total_iterations = result.iterations
                tool_calls_count = result.tool_calls
                tokens_used = result.tokens_used

                if hasattr(orchestrator, 'sub_agents'):
                    for agent in orchestrator.sub_agents.values():
                        if hasattr(agent, 'get_stats'):
                            sub_stats = agent.get_stats()
                            total_iterations += sub_stats.get("iterations", 0)
                            tool_calls_count += sub_stats.get("tool_calls", 0)
                            tokens_used += sub_stats.get("tokens_used", 0)

                task.total_iterations = total_iterations
                task.tool_calls_count = tool_calls_count
                task.tokens_used = tokens_used

                # 🔥 统计文件数量
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
                
                # 计算安全评分
                task.security_score = _calculate_security_score(
                    [{"severity": str(item.severity).lower()} for item in effective_findings]
                )
                # 🔥 注意: progress_percentage 是计算属性，不需要手动设置
                # 当 status = COMPLETED 时会自动返回 100.0
                
                await db.commit()
                
                await event_emitter.emit_task_complete(
                    findings_count=len(effective_findings),
                    duration_ms=duration_ms,
                )
                
                logger.info(
                    f"✅ Task {task_id} completed: "
                    f"effective={len(effective_findings)}, false_positive={len(false_positive_findings)}, "
                    f"saved={saved_count}, duration={duration_ms}ms"
                )
            else:
                # 🔥 检查是否是取消导致的失败
                if result.error == "任务已取消":
                    # 状态可能已经被 cancel API 更新，只需确保一致性
                    if task.status != AgentTaskStatus.CANCELLED:
                        task.status = AgentTaskStatus.CANCELLED
                        task.completed_at = datetime.now(timezone.utc)
                        await db.commit()
                    logger.info(f"🛑 Task {task_id} cancelled")
                else:
                    task.status = AgentTaskStatus.FAILED
                    task.error_message = result.error or "Unknown error"
                    task.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    
                    await event_emitter.emit_error(result.error or "Unknown error")
                    logger.error(f"❌ Task {task_id} failed: {result.error}")
            
        except asyncio.CancelledError:
            logger.info(f"Task {task_id} cancelled")
            try:
                task = await db.get(AgentTask, task_id)
                if task:
                    task.status = AgentTaskStatus.CANCELLED
                    task.completed_at = datetime.now(timezone.utc)
                    await db.commit()
            except Exception:
                pass
                
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            
            try:
                task = await db.get(AgentTask, task_id)
                if task:
                    task.status = AgentTaskStatus.FAILED
                    task.error_message = str(e)[:1000]
                    task.completed_at = datetime.now(timezone.utc)
                    await db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update task status: {db_error}")
        
        finally:
            # 🔥 在清理之前保存 Agent 树到数据库
            try:
                async with async_session_factory() as save_db:
                    await _save_agent_tree(save_db, task_id)
            except Exception as save_error:
                logger.error(f"Failed to save agent tree: {save_error}")

            # 清理
            _running_orchestrators.pop(task_id, None)
            _running_tasks.pop(task_id, None)
            _running_event_managers.pop(task_id, None)
            _running_asyncio_tasks.pop(task_id, None)  # 🔥 清理 asyncio task
            _cancelled_tasks.discard(task_id)  # 🔥 清理取消标志

            # 🔥 清理整个 Agent 注册表（包括所有子 Agent）
            agent_registry.clear()

            logger.debug(f"Task {task_id} cleaned up")


async def _get_user_config(db: AsyncSession, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """获取用户配置"""
    if not user_id:
        return None
    
    try:
        from app.api.v1.endpoints.config import (
            decrypt_config, 
            SENSITIVE_LLM_FIELDS, SENSITIVE_OTHER_FIELDS
        )
        
        result = await db.execute(
            select(UserConfig).where(UserConfig.user_id == user_id)
        )
        config = result.scalar_one_or_none()
        
        if config and config.llm_config:
            user_llm_config = json.loads(config.llm_config) if config.llm_config else {}
            user_other_config = json.loads(config.other_config) if config.other_config else {}
            
            user_llm_config = decrypt_config(user_llm_config, SENSITIVE_LLM_FIELDS)
            user_other_config = decrypt_config(user_other_config, SENSITIVE_OTHER_FIELDS)
            
            return {
                "llmConfig": user_llm_config,
                "otherConfig": user_other_config,
            }
    except Exception as e:
        logger.warning(f"Failed to get user config: {e}")
    
    return None


async def _initialize_tools(
    project_root: str,
    llm_service,
    user_config: Optional[Dict[str, Any]],
    sandbox_manager: Any, # 传递预初始化的 SandboxManager
    exclude_patterns: Optional[List[str]] = None,
    target_files: Optional[List[str]] = None,
    project_id: Optional[str] = None,  # 🔥 用于 RAG collection_name
    event_emitter: Optional[Any] = None,  # 🔥 新增：用于发送实时日志
    task_id: Optional[str] = None,  # 🔥 新增：用于取消检查
) -> Dict[str, Dict[str, Any]]:
    """初始化工具集

    Args:
        project_root: 项目根目录
        llm_service: LLM 服务
        user_config: 用户配置
        sandbox_manager: 沙箱管理器
        exclude_patterns: 排除模式列表
        target_files: 目标文件列表
        project_id: 项目 ID（用于 RAG collection_name）
        event_emitter: 事件发送器（用于发送实时日志）
        task_id: 任务 ID（用于取消检查）
    """
    from app.services.agent.tools import (
        FileReadTool, FileSearchTool, ListFilesTool,
        PatternMatchTool, CodeAnalysisTool, DataFlowAnalysisTool,
        OpengrepTool, BanditTool, GitleaksTool,
        NpmAuditTool, SafetyTool, TruffleHogTool, OSVScannerTool,  # 🔥 Added missing tools
        ThinkTool, ReflectTool,
        CreateVulnerabilityReportTool,
        VulnerabilityValidationTool,
        # 🔥 RAG 工具
        RAGQueryTool, SecurityCodeSearchTool, FunctionContextTool,
    )
    from app.services.agent.knowledge import (
        SecurityKnowledgeQueryTool,
        GetVulnerabilityKnowledgeTool,
    )
    # 🔥 RAG 相关导入
    from app.services.rag import CodeIndexer, CodeRetriever, EmbeddingService, IndexUpdateMode
    from app.core.config import settings

    # 辅助函数：发送事件
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

    # ============ 🔥 初始化 RAG 系统 ============
    retriever = None
    try:
        await emit(f"🔍 正在初始化 RAG 系统...")

        # 从用户配置中获取 embedding 配置
        user_llm_config = (user_config or {}).get('llmConfig', {})
        user_other_config = (user_config or {}).get('otherConfig', {})
        user_embedding_config = user_other_config.get('embedding_config', {})

        # Embedding Provider 优先级：用户嵌入配置 > 环境变量
        embedding_provider = (
            user_embedding_config.get('provider') or
            getattr(settings, 'EMBEDDING_PROVIDER', 'openai')
        )

        # Embedding Model 优先级：用户嵌入配置 > 环境变量
        embedding_model = (
            user_embedding_config.get('model') or
            getattr(settings, 'EMBEDDING_MODEL', 'text-embedding-3-small')
        )

        # API Key 优先级：用户嵌入配置 > 环境变量 EMBEDDING_API_KEY > 用户 LLM 配置 > 环境变量 LLM_API_KEY
        # 注意：API Key 可以共享，因为很多用户使用同一个 OpenAI Key 做 LLM 和 Embedding
        embedding_api_key = (
            user_embedding_config.get('api_key') or
            getattr(settings, 'EMBEDDING_API_KEY', None) or
            user_llm_config.get('llmApiKey') or
            getattr(settings, 'LLM_API_KEY', '') or
            ''
        )

        # Base URL 优先级：用户嵌入配置 > 环境变量 EMBEDDING_BASE_URL > None（使用提供商默认地址）
        # 🔥 重要：Base URL 不应该回退到 LLM 的 base_url，因为 Embedding 和 LLM 可能使用完全不同的服务
        # 例如：LLM 使用 SiliconFlow，但 Embedding 使用 HuggingFace
        embedding_base_url = (
            user_embedding_config.get('base_url') or
            getattr(settings, 'EMBEDDING_BASE_URL', None) or
            None
        )

        logger.info(f"RAG 配置: provider={embedding_provider}, model={embedding_model}, base_url={embedding_base_url or '(使用默认)'}")
        await emit(f"📊 Embedding 配置: {embedding_provider}/{embedding_model}")

        # 创建 Embedding 服务
        embedding_service = EmbeddingService(
            provider=embedding_provider,
            model=embedding_model,
            api_key=embedding_api_key,
            base_url=embedding_base_url,
        )

        # 创建 collection_name（基于 project_id）
        collection_name = f"project_{project_id}" if project_id else "default_project"

        # 🔥 v2.0: 创建 CodeIndexer 并进行智能索引
        # 智能索引会自动：
        # - 检测 embedding 模型变更，如需要则自动重建
        # - 对比文件 hash，只更新变化的文件（增量更新）
        indexer = CodeIndexer(
            collection_name=collection_name,
            embedding_service=embedding_service,
            persist_directory=settings.VECTOR_DB_PATH,
        )

        logger.info(f"📝 开始智能索引项目: {project_root}")
        await emit(f"📝 正在构建代码向量索引...")

        index_progress = None
        last_progress_update = 0
        last_embedding_progress = [0]  # 使用列表以便在闭包中修改
        embedding_total = [0]  # 记录总数

        # 🔥 嵌入进度回调函数（同步，但会调度异步任务）
        def on_embedding_progress(processed: int, total: int):
            embedding_total[0] = total
            # 每处理 50 个或完成时更新
            if processed - last_embedding_progress[0] >= 50 or processed == total:
                last_embedding_progress[0] = processed
                percentage = (processed / total * 100) if total > 0 else 0
                msg = f"🔢 嵌入进度: {processed}/{total} ({percentage:.0f}%)"
                logger.info(msg)
                # 使用 asyncio.create_task 调度异步 emit
                try:
                    loop = asyncio.get_running_loop()
                    loop.create_task(emit(msg))
                except Exception as e:
                    logger.warning(f"Failed to emit embedding progress: {e}")

        # 🔥 创建取消检查函数，用于在嵌入批处理中检查取消状态
        def check_cancelled() -> bool:
            return task_id is not None and is_task_cancelled(task_id)

        async for progress in indexer.smart_index_directory(
            directory=project_root,
            exclude_patterns=exclude_patterns or [],
            include_patterns=target_files,  # 🔥 传递 target_files 限制索引范围
            update_mode=IndexUpdateMode.SMART,
            embedding_progress_callback=on_embedding_progress,
            cancel_check=check_cancelled,  # 🔥 传递取消检查函数
        ):
            # 🔥 在索引过程中检查取消状态
            if check_cancelled():
                logger.info(f"[Cancel] RAG indexing cancelled for task {task_id}")
                raise asyncio.CancelledError("任务已取消")

            index_progress = progress
            # 每处理 10 个文件或有重要变化时发送进度更新
            if progress.processed_files - last_progress_update >= 10 or progress.processed_files == progress.total_files:
                if progress.total_files > 0:
                    await emit(
                        f"📝 索引进度: {progress.processed_files}/{progress.total_files} 文件 "
                        f"({progress.progress_percentage:.0f}%)"
                    )
                last_progress_update = progress.processed_files

            # 🔥 发送状态消息（如嵌入向量生成进度）
            if progress.status_message:
                await emit(progress.status_message)
                progress.status_message = ""  # 清空已发送的消息

        if index_progress:
            summary = (
                f"✅ 索引完成: 模式={index_progress.update_mode}, "
                f"新增={index_progress.added_files}, "
                f"更新={index_progress.updated_files}, "
                f"删除={index_progress.deleted_files}, "
                f"代码块={index_progress.indexed_chunks}"
            )
            logger.info(summary)
            await emit(summary)

        # 创建 CodeRetriever（用于搜索）
        # 🔥 传递 api_key，用于自动适配 collection 的 embedding 配置
        retriever = CodeRetriever(
            collection_name=collection_name,
            embedding_service=embedding_service,
            persist_directory=settings.VECTOR_DB_PATH,
            api_key=embedding_api_key,  # 🔥 传递 api_key 以支持自动切换 embedding
        )

        logger.info(f"✅ RAG 系统初始化成功: collection={collection_name}")
        await emit(f"✅ RAG 系统初始化成功")

    except Exception as e:
        logger.warning(f"⚠️ RAG 系统初始化失败: {e}")
        await emit(f"⚠️ RAG 系统初始化失败: {e}", "warning")
        import traceback
        logger.debug(f"RAG 初始化异常详情:\n{traceback.format_exc()}")
        retriever = None

    # 基础工具 - 传递排除模式和目标文件
    base_tools = {
        "read_file": FileReadTool(project_root, exclude_patterns, target_files),
        "list_files": ListFilesTool(project_root, exclude_patterns, target_files),
        "search_code": FileSearchTool(project_root, exclude_patterns, target_files),
        "think": ThinkTool(),
        "reflect": ReflectTool(),
    }
    
    # Recon 工具
    recon_tools = {
        **base_tools,
        # 🔥 外部侦察工具 (Recon 阶段也需要使用这些工具来收集初步信息)
        # "opengrep_scan": OpengrepTool(project_root, sandbox_manager),
        # "bandit_scan": BanditTool(project_root, sandbox_manager),
        "gitleaks_scan": GitleaksTool(project_root, sandbox_manager),
        # "npm_audit": NpmAuditTool(project_root, sandbox_manager),
        # "safety_scan": SafetyTool(project_root, sandbox_manager),
        # "trufflehog_scan": TruffleHogTool(project_root, sandbox_manager),
        # "osv_scan": OSVScannerTool(project_root, sandbox_manager),
    }

    # 🔥 注册 RAG 工具到 Recon Agent
    if retriever:
        recon_tools["rag_query"] = RAGQueryTool(retriever)
        logger.info("✅ RAG 工具 (rag_query) 已注册到 Recon Agent")
    
    # Analysis 工具
    # 🔥 导入智能扫描工具
    from app.services.agent.tools import SmartScanTool, QuickAuditTool
    
    analysis_tools = {
        **base_tools,
        # 🔥 智能扫描工具（推荐首先使用）
        "smart_scan": SmartScanTool(project_root),
        "quick_audit": QuickAuditTool(project_root),
        # 模式匹配工具（增强版）
        "pattern_match": PatternMatchTool(project_root),
        # 数据流分析
        "dataflow_analysis": DataFlowAnalysisTool(llm_service),
        # 外部安全工具 (传入共享的 sandbox_manager)
        # "opengrep_scan": OpengrepTool(project_root, sandbox_manager),
        # "bandit_scan": BanditTool(project_root, sandbox_manager),
        "gitleaks_scan": GitleaksTool(project_root, sandbox_manager),
        # "npm_audit": NpmAuditTool(project_root, sandbox_manager),
        # "safety_scan": SafetyTool(project_root, sandbox_manager),
        # "trufflehog_scan": TruffleHogTool(project_root, sandbox_manager),
        # "osv_scan": OSVScannerTool(project_root, sandbox_manager),
        # 安全知识查询
        "query_security_knowledge": SecurityKnowledgeQueryTool(),
        "get_vulnerability_knowledge": GetVulnerabilityKnowledgeTool(),
    }

    # 🔥 注册 RAG 工具到 Analysis Agent
    if retriever:
        analysis_tools["rag_query"] = RAGQueryTool(retriever)
        analysis_tools["security_search"] = SecurityCodeSearchTool(retriever)
        analysis_tools["function_context"] = FunctionContextTool(retriever)
        logger.info("✅ RAG 工具 (rag_query, security_search, function_context) 已注册到 Analysis Agent")
    else:
        logger.warning("⚠️ RAG 未初始化，rag_query/security_search/function_context 工具不可用")
    
    # Verification 工具
    # 🔥 导入沙箱工具
    from app.services.agent.tools import (
        SandboxTool, SandboxHttpTool, VulnerabilityVerifyTool,
        # 多语言代码测试工具
        PhpTestTool, PythonTestTool, JavaScriptTestTool, JavaTestTool,
        GoTestTool, RubyTestTool, ShellTestTool, UniversalCodeTestTool,
        # 漏洞验证专用工具
        CommandInjectionTestTool, SqlInjectionTestTool, XssTestTool,
        PathTraversalTestTool, SstiTestTool, DeserializationTestTool,
        UniversalVulnTestTool,
        # 🔥 新增：通用代码执行工具 (LLM 驱动的 Fuzzing Harness)
        RunCodeTool, ExtractFunctionTool,
    )

    verification_tools = {
        **base_tools,
        # 🔥 沙箱验证工具
        #"sandbox_exec": SandboxTool(sandbox_manager),
        #"sandbox_http": SandboxHttpTool(sandbox_manager),
        #"verify_vulnerability": VulnerabilityVerifyTool(sandbox_manager),

        # 🔥 多语言代码测试工具
        #"php_test": PhpTestTool(sandbox_manager, project_root),
        #"python_test": PythonTestTool(sandbox_manager, project_root),
        #"javascript_test": JavaScriptTestTool(sandbox_manager, project_root),
        #"java_test": JavaTestTool(sandbox_manager, project_root),
        #"go_test": GoTestTool(sandbox_manager, project_root),
        #"ruby_test": RubyTestTool(sandbox_manager, project_root),
        #"shell_test": ShellTestTool(sandbox_manager, project_root),
        #"universal_code_test": UniversalCodeTestTool(sandbox_manager, project_root),

        # 🔥 漏洞验证专用工具
        "test_command_injection": CommandInjectionTestTool(sandbox_manager, project_root),
        "test_sql_injection": SqlInjectionTestTool(sandbox_manager, project_root),
        "test_xss": XssTestTool(sandbox_manager, project_root),
        "test_path_traversal": PathTraversalTestTool(sandbox_manager, project_root),
        "test_ssti": SstiTestTool(sandbox_manager, project_root),
        "test_deserialization": DeserializationTestTool(sandbox_manager, project_root),
        "universal_vuln_test": UniversalVulnTestTool(sandbox_manager, project_root),

        # 🔥 新增：通用代码执行工具 (LLM 驱动的 Fuzzing Harness)
        #"run_code": RunCodeTool(sandbox_manager, project_root),
        "extract_function": ExtractFunctionTool(project_root),

        # 报告工具 - 🔥 v2.1: 传递 project_root 用于文件验证
        "create_vulnerability_report": CreateVulnerabilityReportTool(project_root),
    }
    
    # Orchestrator 工具（主要是思考工具）
    orchestrator_tools = {
        "think": ThinkTool(),
        "reflect": ReflectTool(),
    }
    
    return {
        "recon": recon_tools,
        "analysis": analysis_tools,
        "verification": verification_tools,
        "orchestrator": orchestrator_tools,
    }


async def _collect_project_info(
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
    
    🔥 重要：当指定了 target_files 时，返回的项目结构应该只包含目标文件相关的信息，
    以确保 Orchestrator 和子 Agent 看到的是一致的、过滤后的视图。
    """
    import fnmatch
    
    info = {
        "name": project_name,
        "root": project_root,
        "languages": [],
        "file_count": 0,
        "structure": {},
    }
    
    try:
        # 默认排除目录
        exclude_dirs = {
            "node_modules", "__pycache__", ".git", "venv", ".venv",
            "build", "dist", "target", ".idea", ".vscode",
        }
        
        # 从用户配置的排除模式中提取目录
        if exclude_patterns:
            for pattern in exclude_patterns:
                if pattern.endswith("/**"):
                    exclude_dirs.add(pattern[:-3])
                elif "/" not in pattern and "*" not in pattern:
                    exclude_dirs.add(pattern)
        
        # 目标文件集合
        target_files_set = set(target_files) if target_files else None
        
        lang_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".java": "Java", ".go": "Go", ".php": "PHP",
            ".rb": "Ruby", ".rs": "Rust", ".c": "C", ".cpp": "C++",
        }
        
        # 🔥 收集过滤后的文件列表
        filtered_files = []
        filtered_dirs = set()
        
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            for f in files:
                relative_path = os.path.relpath(os.path.join(root, f), project_root)
                
                # 检查是否在目标文件列表中
                if target_files_set and relative_path not in target_files_set:
                    continue
                
                # 检查排除模式
                should_skip = False
                if exclude_patterns:
                    for pattern in exclude_patterns:
                        if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(f, pattern):
                            should_skip = True
                            break
                if should_skip:
                    continue
                
                info["file_count"] += 1
                filtered_files.append(relative_path)
                
                # 🔥 收集文件所在的目录
                dir_path = os.path.dirname(relative_path)
                if dir_path:
                    # 添加目录及其父目录
                    parts = dir_path.split(os.sep)
                    for i in range(len(parts)):
                        filtered_dirs.add(os.sep.join(parts[:i+1]))
                
                ext = os.path.splitext(f)[1].lower()
                if ext in lang_map and lang_map[ext] not in info["languages"]:
                    info["languages"].append(lang_map[ext])
        
        # 🔥 根据是否有目标文件限制，生成不同的结构信息
        if target_files_set:
            # 当指定了目标文件时，只显示目标文件和相关目录
            info["structure"] = {
                "directories": sorted(list(filtered_dirs))[:20],
                "files": filtered_files[:30],
                "scope_limited": True,  # 🔥 标记这是限定范围的视图
                "scope_message": f"审计范围限定为 {len(filtered_files)} 个指定文件",
            }
        else:
            # 全项目审计时，显示顶层目录结构
            try:
                top_items = os.listdir(project_root)
                info["structure"] = {
                    "directories": [d for d in top_items if os.path.isdir(os.path.join(project_root, d)) and d not in exclude_dirs],
                    "files": [f for f in top_items if os.path.isfile(os.path.join(project_root, f))][:20],
                    "scope_limited": False,
                }
            except Exception:
                pass
            
    except Exception as e:
        logger.warning(f"Failed to collect project info: {e}")
    
    return info


def _safe_text(value: Any) -> str:
    """将任意结构安全转换为文本，避免保存时意外截断或类型错误。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)
    return str(value)


def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _normalize_optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = _safe_text(value).strip()
    return text or None


def _normalize_relative_file_path(path_value: str, project_root: Optional[str]) -> str:
    normalized = path_value.replace("\\", "/").strip()
    if not project_root:
        return normalized
    try:
        rel = os.path.relpath(normalized, project_root)
        if not rel.startswith(".."):
            return rel.replace("\\", "/")
    except Exception:
        pass
    return normalized


def _resolve_finding_file_path(
    raw_file_path: Optional[str],
    project_root: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    if not raw_file_path:
        return None, None

    candidate = raw_file_path.strip().split(":", 1)[0].strip()
    if not candidate:
        return None, None

    candidate = candidate.replace("\\", "/")
    path_candidates: List[Path] = []
    raw_path = Path(candidate)
    path_candidates.append(raw_path)

    if project_root:
        root_path = Path(project_root)
        path_candidates.append(root_path / candidate)
        if candidate.startswith("./"):
            path_candidates.append(root_path / candidate[2:])

    for path_obj in path_candidates:
        try:
            resolved = path_obj.resolve()
        except Exception:
            continue
        if resolved.is_file():
            stored = _normalize_relative_file_path(str(resolved), project_root)
            return stored, str(resolved)

    return None, None


def _infer_line_range_from_snippet(
    file_lines: List[str],
    snippet: Optional[str],
) -> Tuple[Optional[int], Optional[int]]:
    if not snippet:
        return None, None

    snippet_text = snippet.strip("\n")
    if not snippet_text:
        return None, None

    file_text = "\n".join(file_lines)
    first_index = file_text.find(snippet_text)
    if first_index < 0:
        return None, None
    if file_text.find(snippet_text, first_index + 1) >= 0:
        return None, None

    line_start = file_text.count("\n", 0, first_index) + 1
    line_count = max(1, snippet_text.count("\n") + 1)
    line_end = line_start + line_count - 1
    return line_start, line_end


def _extract_location_parts(finding: Dict[str, Any]) -> Tuple[Optional[str], Optional[int]]:
    location = finding.get("location")
    if not location or not isinstance(location, str):
        return None, None
    location = location.strip()
    if not location:
        return None, None

    if ":" not in location:
        return location, None

    file_part, line_part = location.split(":", 1)
    line_num = _to_int(line_part.split("-", 1)[0].strip())
    return file_part.strip(), line_num


def _build_code_windows(
    file_lines: List[str],
    line_start: int,
    line_end: int,
    radius: int = 3,
) -> Tuple[Optional[str], Optional[str], Optional[int], Optional[int]]:
    if not file_lines:
        return None, None, None, None

    total_lines = len(file_lines)
    safe_start = max(1, min(line_start, total_lines))
    safe_end = max(safe_start, min(line_end, total_lines))

    snippet_start_idx = safe_start - 1
    snippet_end_idx = safe_end
    snippet = "\n".join(file_lines[snippet_start_idx:snippet_end_idx]).strip("\n")

    context_start = max(1, safe_start - radius)
    context_end = min(total_lines, safe_end + radius)
    context_start_idx = context_start - 1
    context_end_idx = context_end
    context = "\n".join(file_lines[context_start_idx:context_end_idx]).strip("\n")

    if not context:
        return None, None, None, None
    if not snippet:
        snippet = context

    return snippet, context, context_start, context_end


def _normalize_authenticity_verdict(
    finding: Dict[str, Any],
    confidence: float,
) -> Optional[str]:
    verdict = finding.get("authenticity") or finding.get("verdict")
    if isinstance(verdict, str):
        verdict = verdict.strip().lower()
    else:
        verdict = None

    allowed = {"confirmed", "likely", "false_positive"}
    if verdict in allowed:
        return verdict

    if finding.get("is_verified") is True:
        return "confirmed"
    if confidence >= 0.85:
        return "likely"
    if confidence <= 0.2:
        return "false_positive"
    return None


def _normalize_reachability(
    finding: Dict[str, Any],
    verdict: str,
) -> Optional[str]:
    value = finding.get("reachability")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"reachable", "likely_reachable", "unreachable"}:
            return normalized

    if verdict == "confirmed":
        return "reachable"
    if verdict == "likely":
        return "likely_reachable"
    if verdict == "false_positive":
        return "unreachable"
    return None


async def _save_findings(
    db: AsyncSession,
    task_id: str,
    findings: List[Dict],
    project_root: Optional[str] = None,
) -> int:
    """
    保存发现到数据库

    严格门禁版：
    - normalize -> enrich -> validate -> persist
    - 无文件定位、无可用上下文、无合法真实性/可达性的发现不入库

    Args:
        db: 数据库会话
        task_id: 任务ID
        findings: 发现列表
        project_root: 项目根目录（用于验证文件路径）

    Returns:
        int: 实际保存的发现数量
    """
    from app.models.agent_task import VulnerabilityType

    logger.info(f"[SaveFindings] Starting to save {len(findings)} findings for task {task_id}")

    if not findings:
        logger.warning(f"[SaveFindings] No findings to save for task {task_id}")
        return 0

    # 🔥 Case-insensitive mapping preparation
    severity_map = {
        "critical": VulnerabilitySeverity.CRITICAL,
        "high": VulnerabilitySeverity.HIGH,
        "medium": VulnerabilitySeverity.MEDIUM,
        "low": VulnerabilitySeverity.LOW,
        "info": VulnerabilitySeverity.INFO,
    }

    type_map = {
        "sql_injection": VulnerabilityType.SQL_INJECTION,
        "nosql_injection": VulnerabilityType.NOSQL_INJECTION,
        "xss": VulnerabilityType.XSS,
        "command_injection": VulnerabilityType.COMMAND_INJECTION,
        "code_injection": VulnerabilityType.CODE_INJECTION,
        "path_traversal": VulnerabilityType.PATH_TRAVERSAL,
        "ssrf": VulnerabilityType.SSRF,
        "xxe": VulnerabilityType.XXE,
        "auth_bypass": VulnerabilityType.AUTH_BYPASS,
        "idor": VulnerabilityType.IDOR,
        "sensitive_data_exposure": VulnerabilityType.SENSITIVE_DATA_EXPOSURE,
        "hardcoded_secret": VulnerabilityType.HARDCODED_SECRET,
        "deserialization": VulnerabilityType.DESERIALIZATION,
        "weak_crypto": VulnerabilityType.WEAK_CRYPTO,
        "file_inclusion": VulnerabilityType.FILE_INCLUSION,
        "race_condition": VulnerabilityType.RACE_CONDITION,
        "business_logic": VulnerabilityType.BUSINESS_LOGIC,
        "memory_corruption": VulnerabilityType.MEMORY_CORRUPTION,
    }

    saved_count = 0
    filtered_reasons: Dict[str, int] = {}
    logger.info(f"Saving {len(findings)} findings for task {task_id}")

    def mark_filtered(reason: str, payload: Optional[Dict[str, Any]] = None) -> None:
        filtered_reasons[reason] = filtered_reasons.get(reason, 0) + 1
        if payload:
            logger.warning(
                f"[SaveFindings] 🚫 Filtered finding ({reason}): "
                f"title={str(payload.get('title', 'N/A'))[:80]}"
            )

    for finding in findings:
        if not isinstance(finding, dict):
            logger.debug(f"[SaveFindings] Skipping non-dict finding: {type(finding)}")
            continue

        try:
            # 1) normalize severity
            raw_severity = str(
                finding.get("severity") or
                finding.get("risk") or
                "medium"
            ).lower().strip()
            severity_enum = severity_map.get(raw_severity, VulnerabilitySeverity.MEDIUM)

            # 2) normalize vulnerability type
            raw_type = str(
                finding.get("vulnerability_type") or
                finding.get("type") or
                finding.get("vuln_type") or
                "other"
            ).lower().strip().replace(" ", "_").replace("-", "_")

            type_enum = type_map.get(raw_type, VulnerabilityType.OTHER)

            # 🔥 Additional fallback for common Agent output variations
            if "sqli" in raw_type or "sql" in raw_type:
                type_enum = VulnerabilityType.SQL_INJECTION
            if "xss" in raw_type:
                type_enum = VulnerabilityType.XSS
            if "rce" in raw_type or "command" in raw_type or "cmd" in raw_type:
                type_enum = VulnerabilityType.COMMAND_INJECTION
            if "traversal" in raw_type or "lfi" in raw_type or "rfi" in raw_type:
                type_enum = VulnerabilityType.PATH_TRAVERSAL
            if "ssrf" in raw_type:
                type_enum = VulnerabilityType.SSRF
            if "xxe" in raw_type:
                type_enum = VulnerabilityType.XXE
            if "auth" in raw_type:
                type_enum = VulnerabilityType.AUTH_BYPASS
            if "secret" in raw_type or "credential" in raw_type or "password" in raw_type:
                type_enum = VulnerabilityType.HARDCODED_SECRET
            if "deserial" in raw_type:
                type_enum = VulnerabilityType.DESERIALIZATION

            # 3) normalize confidence
            confidence = finding.get("confidence") or finding.get("ai_confidence") or 0.5
            if isinstance(confidence, str):
                try:
                    confidence = float(confidence)
                except ValueError:
                    confidence = 0.5
            confidence = max(0.0, min(float(confidence), 1.0))

            # 4) normalize authenticity + reachability
            authenticity = _normalize_authenticity_verdict(finding, confidence)
            if not authenticity:
                mark_filtered("missing_or_invalid_authenticity", finding)
                continue

            reachability = _normalize_reachability(finding, authenticity)
            if not reachability:
                mark_filtered("missing_or_invalid_reachability", finding)
                continue

            # 5) normalize file location
            location_file, location_line = _extract_location_parts(finding)
            raw_file_path = finding.get("file_path") or finding.get("file") or location_file
            stored_file_path, full_file_path = _resolve_finding_file_path(
                str(raw_file_path) if raw_file_path else None,
                project_root,
            )
            if not stored_file_path or not full_file_path:
                mark_filtered("missing_or_invalid_file_path", finding)
                continue

            try:
                file_content = Path(full_file_path).read_text(encoding="utf-8", errors="replace")
            except Exception:
                mark_filtered("file_read_failed", finding)
                continue

            file_lines = file_content.splitlines()
            if not file_lines:
                mark_filtered("empty_file_content", finding)
                continue

            # 6) normalize line range
            line_start = _to_int(finding.get("line_start")) or _to_int(finding.get("line")) or location_line
            line_end = _to_int(finding.get("line_end"))

            # 7) normalize snippets
            code_snippet = (
                finding.get("code_snippet") or
                finding.get("code") or
                finding.get("vulnerable_code")
            )
            code_snippet_text = _normalize_optional_text(code_snippet)

            if line_start is None:
                inferred_start, inferred_end = _infer_line_range_from_snippet(file_lines, code_snippet_text)
                line_start = inferred_start
                if inferred_end is not None:
                    line_end = inferred_end

            if line_start is None:
                mark_filtered("missing_line_start", finding)
                continue
            if line_end is None:
                line_end = line_start

            total_lines = len(file_lines)
            line_start = max(1, min(line_start, total_lines))
            line_end = max(line_start, min(line_end, total_lines))

            snippet_text, context_text, context_start_line, context_end_line = _build_code_windows(
                file_lines=file_lines,
                line_start=line_start,
                line_end=line_end,
                radius=3,
            )
            if not context_text or context_start_line is None or context_end_line is None:
                mark_filtered("missing_code_context", finding)
                continue
            if not snippet_text:
                snippet_text = code_snippet_text
            if not snippet_text:
                mark_filtered("missing_code_snippet", finding)
                continue

            # 8) title/description/suggestion
            title = finding.get("title")
            if not title:
                type_display = raw_type.replace("_", " ").title()
                if stored_file_path:
                    title = f"{type_display} in {os.path.basename(stored_file_path)}"
                else:
                    title = f"{type_display} Vulnerability"
            title_text = str(title).strip() if title is not None else "Unknown Vulnerability"
            if not title_text:
                title_text = "Unknown Vulnerability"

            description = (
                finding.get("description") or
                finding.get("details") or
                finding.get("explanation") or
                finding.get("impact") or
                ""
            )
            description_text = _safe_text(description)

            suggestion = (
                finding.get("suggestion") or
                finding.get("recommendation") or
                finding.get("remediation") or
                finding.get("fix")
            )
            suggestion_text = _safe_text(suggestion) if suggestion is not None else None

            # 9) verification metadata
            is_verified = authenticity in {"confirmed", "likely"}
            verification_details_text = _normalize_optional_text(
                finding.get("verification_details") or finding.get("verification_evidence")
            )
            verification_method_text = _normalize_optional_text(finding.get("verification_method"))
            if not verification_method_text:
                verification_method_text = "agent_verification"

            verification_result_payload = finding.get("verification_result")
            if not isinstance(verification_result_payload, dict):
                verification_result_payload = {}
            verification_result_payload.update(
                {
                    "reachability": reachability,
                    "authenticity": authenticity,
                    "evidence": verification_details_text,
                    "context_start_line": context_start_line,
                    "context_end_line": context_end_line,
                }
            )

            # 10) PoC info
            poc_data = finding.get("poc", {})
            has_poc = bool(poc_data)
            poc_code = None
            poc_description = None
            poc_steps = None

            if isinstance(poc_data, dict):
                poc_description = poc_data.get("description")
                poc_steps = poc_data.get("steps")
                poc_code = poc_data.get("payload") or poc_data.get("code")
            elif isinstance(poc_data, str):
                poc_description = poc_data

            # 11) optional CVSS/CWE
            cwe_id = finding.get("cwe_id") or finding.get("cwe")
            cvss_score = finding.get("cvss_score") or finding.get("cvss")
            if isinstance(cvss_score, str):
                try:
                    cvss_score = float(cvss_score)
                except ValueError:
                    cvss_score = None

            db_finding = AgentFinding(
                id=str(uuid4()),
                task_id=task_id,
                vulnerability_type=type_enum,
                severity=severity_enum,
                title=title_text,
                description=description_text,
                file_path=stored_file_path,
                line_start=line_start,
                line_end=line_end,
                code_snippet=snippet_text,
                code_context=context_text,
                suggestion=suggestion_text,
                is_verified=is_verified,
                ai_confidence=confidence,
                status=FindingStatus.FALSE_POSITIVE if authenticity == "false_positive" else FindingStatus.VERIFIED,
                has_poc=has_poc,
                poc_code=poc_code,
                poc_description=poc_description,
                poc_steps=poc_steps,
                verification_method=verification_method_text,
                verification_result=verification_result_payload,
                cvss_score=cvss_score,
                references=[{"cwe": cwe_id}] if cwe_id else None,
            )
            db.add(db_finding)
            saved_count += 1
            logger.debug(f"[SaveFindings] Prepared finding: {title_text[:50]}... ({severity_enum})")

        except Exception as e:
            logger.warning(f"Failed to save finding: {e}, data: {finding}")
            import traceback
            logger.debug(f"[SaveFindings] Traceback: {traceback.format_exc()}")

    logger.info(f"Successfully prepared {saved_count} findings for commit")
    if filtered_reasons:
        logger.info(
            "[SaveFindings] Filter summary for task %s: %s",
            task_id,
            json.dumps(filtered_reasons, ensure_ascii=False),
        )

    try:
        await db.commit()
        logger.info(f"[SaveFindings] Successfully committed {saved_count} findings to database")
    except Exception as e:
        logger.error(f"Failed to commit findings: {e}")
        await db.rollback()

    return saved_count


def _calculate_security_score(findings: List[Dict]) -> float:
    """计算安全评分"""
    if not findings:
        return 100.0

    # 基于发现的严重程度计算扣分
    deductions = {
        "critical": 25,
        "high": 15,
        "medium": 8,
        "low": 3,
        "info": 1,
    }

    total_deduction = 0
    for f in findings:
        if isinstance(f, dict):
            sev = f.get("severity", "low")
            total_deduction += deductions.get(sev, 3)

    score = max(0, 100 - total_deduction)
    return float(score)


async def _save_agent_tree(db: AsyncSession, task_id: str) -> None:
    """
    保存 Agent 树到数据库

    🔥 在任务完成前调用，将内存中的 Agent 树持久化到数据库
    """
    from app.models.agent_task import AgentTreeNode
    from app.services.agent.core import agent_registry

    try:
        tree = agent_registry.get_agent_tree()
        nodes = tree.get("nodes", {})

        if not nodes:
            logger.warning(f"[SaveAgentTree] No agent nodes to save for task {task_id}")
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


# ============ API Endpoints ============

@router.post("/", response_model=AgentTaskResponse)
async def create_agent_task(
    request: AgentTaskCreate,
    background_tasks: BackgroundTasks,
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
    
    # 创建任务
    task = AgentTask(
        id=str(uuid4()),
        project_id=project.id,
        name=request.name or f"Agent Audit - {datetime.now().strftime('%Y%m%d_%H%M%S')}",
        description=request.description,
        status=AgentTaskStatus.PENDING,
        current_phase=AgentTaskPhase.PLANNING,
        target_vulnerabilities=request.target_vulnerabilities,
        verification_level=request.verification_level or "sandbox",
        branch_name=request.branch_name,  # 保存用户选择的分支
        exclude_patterns=request.exclude_patterns,
        target_files=request.target_files,
        max_iterations=request.max_iterations or 50,
        timeout_seconds=request.timeout_seconds or 1800,
        created_by=current_user.id,
    )
    
    db.add(task)
    await db.commit()
    await db.refresh(task)
    
    # 在后台启动任务（项目根目录在任务内部获取）
    background_tasks.add_task(_execute_agent_task, task.id)
    
    logger.info(f"Created agent task {task.id} for project {project.name}")
    
    return task


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
        select(Project.id)
    )
    user_project_ids = [p[0] for p in projects_result.fetchall()]
    
    if not user_project_ids:
        return []
    
    # 构建查询
    query = select(AgentTask).where(AgentTask.project_id.in_(user_project_ids))
    
    if project_id:
        query = query.where(AgentTask.project_id == project_id)
    
    if status:
        try:
            status_enum = AgentTaskStatus(status)
            query = query.where(AgentTask.status == status_enum)
        except ValueError:
            pass
    
    query = query.order_by(AgentTask.created_at.desc())
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    tasks = result.scalars().all()
    
    return tasks


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
    
    # 构建响应，确保所有字段都包含
    try:
        # 计算进度百分比
        progress = 0.0
        if hasattr(task, 'progress_percentage'):
            progress = task.progress_percentage
        elif task.status == AgentTaskStatus.COMPLETED:
            progress = 100.0
        elif task.status in [AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED]:
            progress = 0.0
        
        # 🔥 从运行中的 Orchestrator 获取实时统计
        total_iterations = task.total_iterations or 0
        tool_calls_count = task.tool_calls_count or 0
        tokens_used = task.tokens_used or 0
        
        orchestrator = _running_orchestrators.get(task_id)
        if orchestrator and task.status == AgentTaskStatus.RUNNING:
            # 从 Orchestrator 获取统计
            stats = orchestrator.get_stats()
            total_iterations = stats.get("iterations", 0)
            tool_calls_count = stats.get("tool_calls", 0)
            tokens_used = stats.get("tokens_used", 0)
            
            # 累加子 Agent 的统计
            if hasattr(orchestrator, 'sub_agents'):
                for agent in orchestrator.sub_agents.values():
                    if hasattr(agent, 'get_stats'):
                        sub_stats = agent.get_stats()
                        total_iterations += sub_stats.get("iterations", 0)
                        tool_calls_count += sub_stats.get("tool_calls", 0)
                        tokens_used += sub_stats.get("tokens_used", 0)
        
        # 手动构建响应数据
        response_data = {
            "id": task.id,
            "project_id": task.project_id,
            "name": task.name,
            "description": task.description,
            "task_type": task.task_type or "agent_audit",
            "status": task.status,
            "current_phase": task.current_phase,
            "current_step": task.current_step,
            "total_files": task.total_files or 0,
            "indexed_files": task.indexed_files or 0,
            "analyzed_files": task.analyzed_files or 0,
            "total_chunks": task.total_chunks or 0,
            "total_iterations": total_iterations,
            "tool_calls_count": tool_calls_count,
            "tokens_used": tokens_used,
            "findings_count": task.findings_count or 0,
            "total_findings": task.findings_count or 0,  # 兼容字段
            "verified_count": task.verified_count or 0,
            "verified_findings": task.verified_count or 0,  # 兼容字段
            "false_positive_count": task.false_positive_count or 0,
            "critical_count": task.critical_count or 0,
            "high_count": task.high_count or 0,
            "medium_count": task.medium_count or 0,
            "low_count": task.low_count or 0,
            "quality_score": float(task.quality_score or 0.0),
            "security_score": float(task.security_score) if task.security_score is not None else None,
            "progress_percentage": progress,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error_message": task.error_message,
            "audit_scope": task.audit_scope,
            "target_vulnerabilities": task.target_vulnerabilities,
            "verification_level": task.verification_level,
            "exclude_patterns": task.exclude_patterns,
            "target_files": task.target_files,
        }
        
        return AgentTaskResponse(**response_data)
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

    if task.status in [AgentTaskStatus.COMPLETED, AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="任务已结束，无法取消")

    # 🔥 0. 立即标记任务为已取消（用于前置操作的取消检查）
    _cancelled_tasks.add(task_id)
    logger.info(f"[Cancel] Added task {task_id} to cancelled set")

    # 🔥 1. 设置 Agent 的取消标志
    runner = _running_tasks.get(task_id)
    if runner:
        runner.cancel()
        logger.info(f"[Cancel] Set cancel flag for task {task_id}")

    # 🔥 2. 通过 agent_registry 取消所有子 Agent
    from app.services.agent.core import agent_registry
    from app.services.agent.core.graph_controller import stop_all_agents
    try:
        # 停止所有 Agent（包括子 Agent）
        stop_result = stop_all_agents(exclude_root=False)
        logger.info(f"[Cancel] Stopped all agents: {stop_result}")
    except Exception as e:
        logger.warning(f"[Cancel] Failed to stop agents via registry: {e}")

    # 🔥 3. 强制取消 asyncio Task（立即中断 LLM 调用）
    asyncio_task = _running_asyncio_tasks.get(task_id)
    if asyncio_task and not asyncio_task.done():
        asyncio_task.cancel()
        logger.info(f"[Cancel] Cancelled asyncio task for {task_id}")

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
                if status_str in ["completed", "failed", "cancelled"]:
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
                    
                    # 🔥 Debug: 记录 thinking_token 事件
                    if event_type == "thinking_token":
                        token = event.get("metadata", {}).get("token", "")[:20]
                        logger.debug(f"Stream {task_id}: Sending thinking_token: '{token}...'")
                        
                    # 格式化并 yield
                    yield format_sse_event(event)
                    
                    # 🔥 CRITICAL: 为 thinking_token 添加微小延迟
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
                            if status_str in ["completed", "failed", "cancelled"]:
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

    # 🔥 Debug logging
    logger.debug(f"[EventsList] Task {task_id}: returning {len(events)} events (after_sequence={after_sequence})")
    if events:
        logger.debug(f"[EventsList] First event: type={events[0].event_type}, seq={events[0].sequence}")
        if len(events) > 1:
            logger.debug(f"[EventsList] Last event: type={events[-1].event_type}, seq={events[-1].sequence}")

    return events


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
        try:
            sev_enum = VulnerabilitySeverity(severity)
            query = query.where(AgentFinding.severity == sev_enum)
        except ValueError:
            pass
    
    if verified_only:
        query = query.where(AgentFinding.is_verified == True)
    
    # 按严重程度排序
    severity_order = {
        VulnerabilitySeverity.CRITICAL: 0,
        VulnerabilitySeverity.HIGH: 1,
        VulnerabilitySeverity.MEDIUM: 2,
        VulnerabilitySeverity.LOW: 3,
        VulnerabilitySeverity.INFO: 4,
    }
    
    query = query.order_by(AgentFinding.severity, AgentFinding.created_at.desc())
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    findings = result.scalars().all()

    responses: List[AgentFindingResponse] = []
    for item in findings:
        verification_payload = item.verification_result if isinstance(item.verification_result, dict) else {}
        authenticity = verification_payload.get("authenticity")
        if not authenticity:
            authenticity = "false_positive" if str(item.status) == FindingStatus.FALSE_POSITIVE else ("confirmed" if item.is_verified else "likely")
        authenticity = str(authenticity).lower()

        if not include_false_positive and authenticity == "false_positive":
            continue

        reachability = verification_payload.get("reachability")
        verification_evidence = verification_payload.get("evidence") or verification_payload.get("details")
        context_start_line = _to_int(verification_payload.get("context_start_line"))
        context_end_line = _to_int(verification_payload.get("context_end_line"))

        responses.append(
            AgentFindingResponse.model_validate(
                {
                    "id": item.id,
                    "task_id": item.task_id,
                    "vulnerability_type": item.vulnerability_type,
                    "severity": item.severity,
                    "title": item.title,
                    "description": item.description,
                    "file_path": item.file_path,
                    "line_start": item.line_start,
                    "line_end": item.line_end,
                    "code_snippet": item.code_snippet,
                    "code_context": item.code_context,
                    "context_start_line": context_start_line,
                    "context_end_line": context_end_line,
                    "is_verified": item.is_verified,
                    "confidence": item.ai_confidence if item.ai_confidence is not None else 0.5,
                    "reachability": reachability,
                    "authenticity": authenticity,
                    "verification_evidence": verification_evidence,
                    "status": item.status,
                    "suggestion": item.suggestion,
                    "poc": {
                        "code": item.poc_code,
                        "description": item.poc_description,
                        "steps": item.poc_steps,
                    } if item.has_poc else None,
                    "created_at": item.created_at,
                }
            )
        )

    return responses


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
    
    try:
        finding.status = FindingStatus(status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的状态: {status}")
    
    await db.commit()
    
    return {"message": "状态已更新", "finding_id": finding_id, "status": status}


# ============ Helper Functions ============

async def _get_project_root(
    project: Project,
    task_id: str,
    branch_name: Optional[str] = None,
    github_token: Optional[str] = None,
    gitlab_token: Optional[str] = None,
    gitea_token: Optional[str] = None,  # 🔥 新增
    ssh_private_key: Optional[str] = None,  # 🔥 新增：SSH私钥（用于SSH认证）
    event_emitter: Optional[Any] = None,  # 🔥 新增：用于发送实时日志
) -> str:
    """
    获取项目根目录

    支持两种项目类型：
    - ZIP 项目：解压 ZIP 文件到临时目录
    - 仓库项目：克隆仓库到临时目录

    Args:
        project: 项目对象
        task_id: 任务ID
        branch_name: 分支名称（仓库项目使用，优先于 project.default_branch）
        github_token: GitHub 访问令牌（用于私有仓库）
        gitlab_token: GitLab 访问令牌（用于私有仓库）
        gitea_token: Gitea 访问令牌（用于私有仓库）
        ssh_private_key: SSH私钥（用于SSH认证）
        event_emitter: 事件发送器（用于发送实时日志）

    Returns:
        项目根目录路径

    Raises:
        RuntimeError: 当项目文件获取失败时
    """
    import zipfile
    import subprocess
    import shutil
    from urllib.parse import urlparse, urlunparse

    # 辅助函数：发送事件
    async def emit(message: str, level: str = "info"):
        if event_emitter:
            if level == "info":
                await event_emitter.emit_info(message)
            elif level == "warning":
                await event_emitter.emit_warning(message)
            elif level == "error":
                await event_emitter.emit_error(message)

    # 🔥 辅助函数：检查取消状态
    def check_cancelled():
        if is_task_cancelled(task_id):
            raise asyncio.CancelledError("任务已取消")

    base_path = f"/tmp/deepaudit/{task_id}"

    # 确保目录存在且为空
    if os.path.exists(base_path):
        shutil.rmtree(base_path)
    os.makedirs(base_path, exist_ok=True)

    # 🔥 在开始任何操作前检查取消
    check_cancelled()

    # 根据项目类型处理
    if project.source_type == "zip":
        # 🔥 ZIP 项目：解压 ZIP 文件
        check_cancelled()  # 🔥 解压前检查
        await emit(f"📦 正在解压项目文件...")
        from app.services.zip_storage import load_project_zip

        zip_path = await load_project_zip(project.id)

        if zip_path and os.path.exists(zip_path):
            try:
                check_cancelled()  # 🔥 解压前再次检查
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # 🔥 逐个文件解压，支持取消检查
                    file_list = zip_ref.namelist()
                    for i, file_name in enumerate(file_list):
                        if i % 50 == 0:  # 每50个文件检查一次
                            check_cancelled()
                        zip_ref.extract(file_name, base_path)
                logger.info(f"✅ Extracted ZIP project {project.id} to {base_path}")
                await emit(f"✅ ZIP 文件解压完成")
            except Exception as e:
                logger.error(f"Failed to extract ZIP {zip_path}: {e}")
                await emit(f"❌ 解压失败: {e}", "error")
                raise RuntimeError(f"无法解压项目文件: {e}")
        else:
            logger.warning(f"⚠️ ZIP file not found for project {project.id}")
            await emit(f"❌ ZIP 文件不存在", "error")
            raise RuntimeError(f"项目 ZIP 文件不存在: {project.id}")

    elif project.source_type == "repository" and project.repository_url:
        # 🔥 仓库项目：优先使用 ZIP 下载（更快更稳定），git clone 作为回退
        repo_url = project.repository_url
        repo_type = project.repository_type or "other"

        await emit(f"🔄 正在获取仓库: {repo_url}")

        # 检测是否为SSH URL（SSH链接不支持ZIP下载）
        is_ssh_url = GitSSHOperations.is_ssh_url(repo_url)

        # 解析仓库 URL 获取 owner/repo
        parsed = urlparse(repo_url)
        path_parts = parsed.path.strip('/').replace('.git', '').split('/')
        if len(path_parts) >= 2:
            owner, repo = path_parts[0], path_parts[1]
        else:
            owner, repo = None, None

        # 构建分支尝试顺序
        branches_to_try = []
        if branch_name:
            branches_to_try.append(branch_name)
        if project.default_branch and project.default_branch not in branches_to_try:
            branches_to_try.append(project.default_branch)
        for common_branch in ["main", "master"]:
            if common_branch not in branches_to_try:
                branches_to_try.append(common_branch)

        download_success = False
        last_error = ""

        # ============ 方案1: 优先使用 ZIP 下载（更快更稳定）============
        # SSH链接直接跳过ZIP下载，使用git clone
        if is_ssh_url:
            logger.info(f"检测到SSH URL，跳过ZIP下载，直接使用Git克隆")
            await emit(f"🔑 检测到SSH认证，使用Git克隆...")

        if owner and repo and not is_ssh_url:
            import httpx

            for branch in branches_to_try:
                check_cancelled()

                # 清理目录
                if os.path.exists(base_path) and os.listdir(base_path):
                    shutil.rmtree(base_path)
                os.makedirs(base_path, exist_ok=True)

                # 构建 ZIP 下载 URL
                if repo_type == "github" or "github.com" in repo_url:
                    # GitHub ZIP 下载 URL
                    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"
                    headers = {}
                    if github_token:
                        headers["Authorization"] = f"token {github_token}"
                elif repo_type == "gitlab" or "gitlab" in repo_url:
                    # GitLab ZIP 下载 URL（需要对 owner/repo 进行 URL 编码）
                    import urllib.parse
                    project_path = urllib.parse.quote(f"{owner}/{repo}", safe='')
                    gitlab_host = parsed.netloc
                    zip_url = f"https://{gitlab_host}/api/v4/projects/{project_path}/repository/archive.zip?sha={branch}"
                    headers = {}
                    if gitlab_token:
                        headers["PRIVATE-TOKEN"] = gitlab_token
                else:
                    # 其他平台，跳过 ZIP 下载
                    break

                logger.info(f"📦 尝试下载 ZIP 归档 (分支: {branch})...")
                await emit(f"📦 尝试下载 ZIP 归档 (分支: {branch})")

                try:
                    zip_temp_path = f"/tmp/repo_{task_id}_{branch}.zip"

                    async def download_zip():
                        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                            resp = await client.get(zip_url, headers=headers)
                            if resp.status_code == 200:
                                with open(zip_temp_path, 'wb') as f:
                                    f.write(resp.content)
                                return True, None
                            else:
                                return False, f"HTTP {resp.status_code}"

                    # 使用取消检查循环
                    download_task = asyncio.create_task(download_zip())
                    while not download_task.done():
                        check_cancelled()
                        try:
                            success, error = await asyncio.wait_for(asyncio.shield(download_task), timeout=1.0)
                            break
                        except asyncio.TimeoutError:
                            continue

                    if download_task.done():
                        success, error = download_task.result()

                    if success and os.path.exists(zip_temp_path):
                        # 解压 ZIP
                        check_cancelled()
                        with zipfile.ZipFile(zip_temp_path, 'r') as zip_ref:
                            # ZIP 内通常有一个根目录如 repo-branch/
                            file_list = zip_ref.namelist()
                            # 找到公共前缀
                            if file_list:
                                common_prefix = file_list[0].split('/')[0] + '/'
                                for i, file_name in enumerate(file_list):
                                    if i % 50 == 0:
                                        check_cancelled()
                                    # 去掉公共前缀
                                    if file_name.startswith(common_prefix):
                                        target_path = file_name[len(common_prefix):]
                                        if target_path:  # 跳过空路径（根目录本身）
                                            full_target = os.path.join(base_path, target_path)
                                            if file_name.endswith('/'):
                                                os.makedirs(full_target, exist_ok=True)
                                            else:
                                                os.makedirs(os.path.dirname(full_target), exist_ok=True)
                                                with zip_ref.open(file_name) as src, open(full_target, 'wb') as dst:
                                                    dst.write(src.read())

                        # 清理临时文件
                        os.remove(zip_temp_path)
                        logger.info(f"✅ ZIP 下载成功 (分支: {branch})")
                        await emit(f"✅ 仓库获取成功 (ZIP下载, 分支: {branch})")
                        download_success = True
                        break
                    else:
                        last_error = error or "下载失败"
                        logger.warning(f"ZIP 下载失败 (分支 {branch}): {last_error}")
                        await emit(f"⚠️ ZIP 下载失败，尝试其他分支...", "warning")
                        # 清理临时文件
                        if os.path.exists(zip_temp_path):
                            os.remove(zip_temp_path)

                except asyncio.CancelledError:
                    logger.info(f"[Cancel] ZIP download cancelled for task {task_id}")
                    raise
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"ZIP 下载异常 (分支 {branch}): {e}")
                    await emit(f"⚠️ ZIP 下载异常: {str(e)[:50]}...", "warning")

        # ============ 方案2: 回退到 git clone ============
        if not download_success:
            if is_ssh_url:
                # SSH链接直接使用git clone，不是"失败"
                pass  # 已在上面输出提示
            else:
                await emit(f"🔄 ZIP 下载失败，回退到 Git 克隆...")
                logger.info("ZIP download failed, falling back to git clone")

            # 检查 git 是否可用
            try:
                git_check = subprocess.run(
                    ["git", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if git_check.returncode != 0:
                    await emit(f"❌ Git 未安装", "error")
                    raise RuntimeError("Git 未安装，无法克隆仓库。")
            except FileNotFoundError:
                await emit(f"❌ Git 未安装", "error")
                raise RuntimeError("Git 未安装，无法克隆仓库。")
            except subprocess.TimeoutExpired:
                await emit(f"❌ Git 检测超时", "error")
                raise RuntimeError("Git 检测超时")

            # 构建带认证的 URL
            auth_url = repo_url
            if repo_type == "github" and github_token:
                auth_url = urlunparse((
                    parsed.scheme,
                    f"{github_token}@{parsed.netloc}",
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment
                ))
                await emit(f"🔐 使用 GitHub Token 认证")
            elif repo_type == "gitlab" and gitlab_token:
                auth_url = urlunparse((
                    parsed.scheme,
                    f"oauth2:{gitlab_token}@{parsed.netloc}",
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment
                ))
                await emit(f"🔐 使用 GitLab Token 认证")
            elif repo_type == "gitea" and gitea_token:
                auth_url = urlunparse((
                    parsed.scheme,
                    f"{gitea_token}@{parsed.netloc}",
                    parsed.path,
                    parsed.params,
                    parsed.query,
                    parsed.fragment
                ))
                await emit(f"🔐 使用 Gitea Token 认证")
            elif is_ssh_url and ssh_private_key:
                await emit(f"🔐 使用 SSH Key 认证")
                
            for branch in branches_to_try:
                check_cancelled()

                if os.path.exists(base_path) and os.listdir(base_path):
                    shutil.rmtree(base_path)
                    os.makedirs(base_path, exist_ok=True)

                logger.info(f"🔄 尝试克隆分支: {branch}")
                await emit(f"🔄 尝试克隆分支: {branch}")

                try:
                    # SSH URL使用GitSSHOperations（支持SSH密钥认证）
                    if is_ssh_url and ssh_private_key:
                        async def run_ssh_clone():
                            return await asyncio.to_thread(
                                GitSSHOperations.clone_repo_with_ssh,
                                repo_url, ssh_private_key, base_path, branch
                            )

                        clone_task = asyncio.create_task(run_ssh_clone())
                        while not clone_task.done():
                            check_cancelled()
                            try:
                                result = await asyncio.wait_for(asyncio.shield(clone_task), timeout=1.0)
                                break
                            except asyncio.TimeoutError:
                                continue

                        if clone_task.done():
                            result = clone_task.result()

                        # GitSSHOperations返回字典格式
                        if result.get('success'):
                            logger.info(f"✅ Git 克隆成功 (SSH, 分支: {branch})")
                            await emit(f"✅ 仓库获取成功 (SSH克隆, 分支: {branch})")
                            download_success = True
                            break
                        else:
                            last_error = result.get('message', '未知错误')
                            logger.warning(f"SSH克隆失败 (分支 {branch}): {last_error[:200]}")
                            await emit(f"⚠️ 分支 {branch} SSH克隆失败...", "warning")
                    else:
                        # HTTPS URL使用标准git clone
                        async def run_clone():
                            return await asyncio.to_thread(
                                subprocess.run,
                                ["git", "clone", "--depth", "1", "--branch", branch, auth_url, base_path],
                                capture_output=True,
                                text=True,
                                timeout=120,
                            )

                        clone_task = asyncio.create_task(run_clone())
                        while not clone_task.done():
                            check_cancelled()
                            try:
                                result = await asyncio.wait_for(asyncio.shield(clone_task), timeout=1.0)
                                break
                            except asyncio.TimeoutError:
                                continue

                        if clone_task.done():
                            result = clone_task.result()

                        if result.returncode == 0:
                            logger.info(f"✅ Git 克隆成功 (分支: {branch})")
                            await emit(f"✅ 仓库获取成功 (Git克隆, 分支: {branch})")
                            download_success = True
                            break
                        else:
                            last_error = result.stderr
                            logger.warning(f"克隆失败 (分支 {branch}): {last_error[:200]}")
                            await emit(f"⚠️ 分支 {branch} 克隆失败...", "warning")
                except subprocess.TimeoutExpired:
                    last_error = f"克隆分支 {branch} 超时"
                    logger.warning(last_error)
                    await emit(f"⚠️ 分支 {branch} 克隆超时...", "warning")
                except asyncio.CancelledError:
                    logger.info(f"[Cancel] Git clone cancelled for task {task_id}")
                    raise

            # 尝试默认分支
            if not download_success:
                check_cancelled()
                await emit(f"🔄 尝试使用仓库默认分支...")

                if os.path.exists(base_path) and os.listdir(base_path):
                    shutil.rmtree(base_path)
                    os.makedirs(base_path, exist_ok=True)

                try:
                    # SSH URL使用GitSSHOperations（不指定分支）
                    if is_ssh_url and ssh_private_key:
                        async def run_default_ssh_clone():
                            return await asyncio.to_thread(
                                GitSSHOperations.clone_repo_with_ssh,
                                repo_url, ssh_private_key, base_path, branch
                            )

                        clone_task = asyncio.create_task(run_default_ssh_clone())
                        while not clone_task.done():
                            check_cancelled()
                            try:
                                result = await asyncio.wait_for(asyncio.shield(clone_task), timeout=1.0)
                                break
                            except asyncio.TimeoutError:
                                continue

                        if clone_task.done():
                            result = clone_task.result()

                        if result.get('success'):
                            logger.info(f"✅ Git 克隆成功 (SSH, 默认分支)")
                            await emit(f"✅ 仓库获取成功 (SSH克隆, 默认分支)")
                            download_success = True
                        else:
                            last_error = result.get('message', '未知错误')
                    else:
                        # HTTPS URL使用标准git clone
                        async def run_default_clone():
                            return await asyncio.to_thread(
                                subprocess.run,
                                ["git", "clone", "--depth", "1", auth_url, base_path],
                                capture_output=True,
                                text=True,
                                timeout=120,
                            )

                        clone_task = asyncio.create_task(run_default_clone())
                        while not clone_task.done():
                            check_cancelled()
                            try:
                                result = await asyncio.wait_for(asyncio.shield(clone_task), timeout=1.0)
                                break
                            except asyncio.TimeoutError:
                                continue

                        if clone_task.done():
                            result = clone_task.result()

                        if result.returncode == 0:
                            logger.info(f"✅ Git 克隆成功 (默认分支)")
                            await emit(f"✅ 仓库获取成功 (Git克隆, 默认分支)")
                            download_success = True
                        else:
                            last_error = result.stderr
                except subprocess.TimeoutExpired:
                    last_error = "克隆超时"
                except asyncio.CancelledError:
                    logger.info(f"[Cancel] Git clone cancelled for task {task_id}")
                    raise

        if not download_success:
            # 分析错误原因
            error_msg = "克隆仓库失败"
            if "Authentication failed" in last_error or "401" in last_error:
                error_msg = "认证失败，请检查 GitHub/GitLab Token 配置"
            elif "not found" in last_error.lower() or "404" in last_error:
                error_msg = "仓库不存在或无访问权限"
            elif "Could not resolve host" in last_error:
                error_msg = "无法解析主机名，请检查网络连接"
            elif "Permission denied" in last_error or "403" in last_error:
                error_msg = "无访问权限，请检查仓库权限或 Token"
            else:
                error_msg = f"克隆仓库失败: {last_error[:200]}"

            logger.error(f"❌ {error_msg}")
            await emit(f"❌ {error_msg}", "error")
            raise RuntimeError(error_msg)

    # 验证目录不为空
    if not os.listdir(base_path):
        await emit(f"❌ 项目目录为空", "error")
        raise RuntimeError(f"项目目录为空，可能是克隆/解压失败: {base_path}")

    # 🔥 智能检测：如果解压后只有一个子目录（常见于 ZIP 文件），
    # 则使用那个子目录作为真正的项目根目录
    # 例如：/tmp/deepaudit/UUID/PHP-Project/ -> 返回 /tmp/deepaudit/UUID/PHP-Project
    items = os.listdir(base_path)
    # 过滤掉 macOS 产生的 __MACOSX 目录和隐藏文件
    real_items = [item for item in items if not item.startswith('__') and not item.startswith('.')]
    
    if len(real_items) == 1:
        single_item_path = os.path.join(base_path, real_items[0])
        if os.path.isdir(single_item_path):
            logger.info(f"🔍 检测到单层嵌套目录，自动调整项目根目录: {base_path} -> {single_item_path}")
            await emit(f"🔍 检测到嵌套目录，自动调整为: {real_items[0]}")
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
    iterations: int = 0
    tokens_used: int = 0
    tool_calls: int = 0
    duration_ms: Optional[int] = None
    children: List["AgentTreeNodeResponse"] = []
    
    class Config:
        from_attributes = True


class AgentTreeResponse(BaseModel):
    """Agent 树响应"""
    task_id: str
    root_agent_id: Optional[str] = None
    total_agents: int = 0
    running_agents: int = 0
    completed_agents: int = 0
    failed_agents: int = 0
    total_findings: int = 0
    nodes: List[AgentTreeNodeResponse] = []


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
        
        # 🔥 获取 root agent ID，用于判断是否是 Orchestrator
        root_agent_id = tree.get("root_agent_id")
        
        # 构建节点列表
        nodes = []
        for agent_id, node_data in tree.get("nodes", {}).items():
            # 🔥 从 Agent 实例获取实时统计数据
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
            
            # 🔥 FIX: 对于 Orchestrator (root agent)，使用 task 的 findings_count
            # 这确保了正确显示聚合的 findings 总数
            if agent_id == root_agent_id:
                findings_count = task.findings_count or 0
            else:
                # 从结果中获取发现数量（对于子 agent）
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
                iterations=iterations,
                tool_calls=tool_calls,
                tokens_used=tokens_used,
                children=[],
            ))
        
        # 🔥 使用 task.findings_count 作为 total_findings，确保一致性
        return AgentTreeResponse(
            task_id=task_id,
            root_agent_id=root_agent_id,
            total_agents=stats.get("total", 0),
            running_agents=stats.get("running", 0),
            completed_agents=stats.get("completed", 0),
            failed_agents=stats.get("failed", 0),
            total_findings=task.findings_count or 0,
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
            nodes=[],
        )
    
    # 构建响应
    nodes = []
    root_id = None
    running = 0
    completed = 0
    failed = 0
    
    for node in db_nodes:
        if node.parent_agent_id is None:
            root_id = node.agent_id
        
        if node.status == "running":
            running += 1
        elif node.status == "completed":
            completed += 1
        elif node.status == "failed":
            failed += 1
        
        # 🔥 FIX: 对于 Orchestrator (root agent)，使用 task 的 findings_count
        # 这确保了正确显示聚合的 findings 总数
        if node.parent_agent_id is None:
            # Root agent uses task's total findings
            node_findings_count = task.findings_count or 0
        else:
            node_findings_count = node.findings_count or 0
        
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
            iterations=node.iterations or 0,
            tokens_used=node.tokens_used or 0,
            tool_calls=node.tool_calls or 0,
            duration_ms=node.duration_ms,
            children=[],
        ))
    
    # 🔥 使用 task.findings_count 作为 total_findings，确保一致性
    return AgentTreeResponse(
        task_id=task_id,
        root_agent_id=root_id,
        total_agents=len(nodes),
        running_agents=running,
        completed_agents=completed,
        failed_agents=failed,
        total_findings=task.findings_count or 0,
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
    
    class Config:
        from_attributes = True


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


# ============ Report Generation API ============


def _escape_markdown_inline(text: Optional[str]) -> str:
    """转义 Markdown 行内特殊字符，避免标题/位置等结构被破坏。"""
    if text is None:
        return ""
    escaped = str(text).replace("\\", "\\\\")
    for char in ("`", "*", "_", "[", "]", "(", ")", "#", "+", "-", "!", "|", ">"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def _escape_markdown_table_cell(text: Optional[str]) -> str:
    return _escape_markdown_inline(text).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")


@router.get("/{task_id}/report")
async def generate_audit_report(
    task_id: str,
    format: str = Query("markdown", regex="^(markdown|json)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    生成审计报告
    
    支持 Markdown 和 JSON 格式
    """
    task = await db.get(AgentTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    project = await db.get(Project, task.project_id)
    if not project:
        raise HTTPException(status_code=403, detail="无权访问此任务")
    
    # 获取此任务的所有发现
    findings = await db.execute(
        select(AgentFinding)
        .where(AgentFinding.task_id == task_id)
        .order_by(
            case(
                (AgentFinding.severity == 'critical', 1),
                (AgentFinding.severity == 'high', 2),
                (AgentFinding.severity == 'medium', 3),
                (AgentFinding.severity == 'low', 4),
                else_=5
            ),
            AgentFinding.created_at.desc()
        )
    )
    findings = findings.scalars().all()
    
    # 🔥 Helper function to normalize severity for comparison (case-insensitive)
    def normalize_severity(sev: str) -> str:
        return str(sev).lower().strip() if sev else ""
    
    # Log findings for debugging
    logger.info(f"[Report] Task {task_id}: Found {len(findings)} findings from database")
    if findings:
        for i, f in enumerate(findings[:3]):  # Log first 3
            logger.debug(f"[Report] Finding {i+1}: severity='{f.severity}', title='{f.title[:50] if f.title else 'N/A'}'")
    
    if format == "json":
        # Enhanced JSON report with full metadata
        return {
            "report_metadata": {
                "task_id": task.id,
                "project_id": task.project_id,
                "project_name": project.name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "task_status": task.status,
                "duration_seconds": int((task.completed_at - task.started_at).total_seconds()) if task.completed_at and task.started_at else None,
            },
            "summary": {
                "security_score": task.security_score,
                "total_files_analyzed": task.analyzed_files,
                "total_findings": len(findings),
                "verified_findings": sum(1 for f in findings if f.is_verified),
                "severity_distribution": {
                    "critical": sum(1 for f in findings if normalize_severity(f.severity) == 'critical'),
                    "high": sum(1 for f in findings if normalize_severity(f.severity) == 'high'),
                    "medium": sum(1 for f in findings if normalize_severity(f.severity) == 'medium'),
                    "low": sum(1 for f in findings if normalize_severity(f.severity) == 'low'),
                },
                "agent_metrics": {
                    "total_iterations": task.total_iterations,
                    "tool_calls": task.tool_calls_count,
                    "tokens_used": task.tokens_used,
                }
            },
            "findings": [
                {
                    "id": f.id,
                    "title": f.title,
                    "severity": f.severity,
                    "vulnerability_type": f.vulnerability_type,
                    "description": f.description,
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "code_snippet": f.code_snippet,
                    "is_verified": f.is_verified,
                    "has_poc": f.has_poc,
                    "poc_code": f.poc_code,
                    "poc_description": f.poc_description,
                    "poc_steps": f.poc_steps,
                    "confidence": f.ai_confidence,
                    "suggestion": f.suggestion,
                    "fix_code": f.fix_code,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                } for f in findings
            ]
        }

    # Generate Enhanced Markdown Report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Calculate statistics
    total = len(findings)
    critical = sum(1 for f in findings if normalize_severity(f.severity) == 'critical')
    high = sum(1 for f in findings if normalize_severity(f.severity) == 'high')
    medium = sum(1 for f in findings if normalize_severity(f.severity) == 'medium')
    low = sum(1 for f in findings if normalize_severity(f.severity) == 'low')
    verified = sum(1 for f in findings if f.is_verified)
    with_poc = sum(1 for f in findings if f.has_poc)

    # Calculate duration
    duration_str = "N/A"
    if task.completed_at and task.started_at:
        duration = (task.completed_at - task.started_at).total_seconds()
        if duration >= 3600:
            duration_str = f"{duration / 3600:.1f} 小时"
        elif duration >= 60:
            duration_str = f"{duration / 60:.1f} 分钟"
        else:
            duration_str = f"{int(duration)} 秒"

    md_lines = []

    # Header
    md_lines.append("# DeepAudit 安全审计报告")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # Report Info
    md_lines.append("## 报告信息")
    md_lines.append("")
    md_lines.append(f"| 属性 | 内容 |")
    md_lines.append(f"|----------|-------|")
    md_lines.append(f"| **项目名称** | {_escape_markdown_table_cell(project.name)} |")
    md_lines.append(f"| **任务 ID** | `{task.id[:8]}...` |")
    md_lines.append(f"| **生成时间** | {timestamp} |")
    md_lines.append(f"| **任务状态** | {_escape_markdown_table_cell(str(task.status).upper())} |")
    md_lines.append(f"| **耗时** | {duration_str} |")
    md_lines.append("")

    # Executive Summary
    md_lines.append("## 执行摘要")
    md_lines.append("")

    score = task.security_score
    if score is not None:
        if score >= 80:
            score_assessment = "良好 - 建议进行少量优化"
            score_icon = "通过"
        elif score >= 60:
            score_assessment = "中等 - 存在若干问题需要关注"
            score_icon = "警告"
        else:
            score_assessment = "严重 - 需要立即进行修复"
            score_icon = "未通过"
        md_lines.append(f"**安全评分: {int(score)}/100** [{score_icon}]")
        md_lines.append(f"*{score_assessment}*")
    else:
        md_lines.append("**安全评分:** 未计算")
    md_lines.append("")

    # Findings Summary
    md_lines.append("### 漏洞发现概览")
    md_lines.append("")
    md_lines.append(f"| 严重程度 | 数量 | 已验证 |")
    md_lines.append(f"|----------|-------|----------|")
    if critical > 0:
        md_lines.append(f"| **严重 (CRITICAL)** | {critical} | {sum(1 for f in findings if normalize_severity(f.severity) == 'critical' and f.is_verified)} |")
    if high > 0:
        md_lines.append(f"| **高危 (HIGH)** | {high} | {sum(1 for f in findings if normalize_severity(f.severity) == 'high' and f.is_verified)} |")
    if medium > 0:
        md_lines.append(f"| **中危 (MEDIUM)** | {medium} | {sum(1 for f in findings if normalize_severity(f.severity) == 'medium' and f.is_verified)} |")
    if low > 0:
        md_lines.append(f"| **低危 (LOW)** | {low} | {sum(1 for f in findings if normalize_severity(f.severity) == 'low' and f.is_verified)} |")
    md_lines.append(f"| **总计** | {total} | {verified} |")
    md_lines.append("")

    # Audit Metrics
    md_lines.append("### 审计指标")
    md_lines.append("")
    md_lines.append(f"- **分析文件数:** {task.analyzed_files} / {task.total_files}")
    md_lines.append(f"- **Agent 迭代次数:** {task.total_iterations}")
    md_lines.append(f"- **工具调用次数:** {task.tool_calls_count}")
    md_lines.append(f"- **Token 消耗:** {task.tokens_used:,}")
    if with_poc > 0:
        md_lines.append(f"- **生成的 PoC:** {with_poc}")
    md_lines.append("")

    # Detailed Findings
    if not findings:
        md_lines.append("## 漏洞详情")
        md_lines.append("")
        md_lines.append("*本次审计未发现安全漏洞。*")
        md_lines.append("")
    else:
        # Group findings by severity
        severity_map = {
            'critical': '严重 (Critical)',
            'high': '高危 (High)',
            'medium': '中危 (Medium)',
            'low': '低危 (Low)'
        }
        
        for severity_level, severity_name in severity_map.items():
            severity_findings = [f for f in findings if normalize_severity(f.severity) == severity_level]
            if not severity_findings:
                continue

            md_lines.append(f"## {severity_name} 漏洞")
            md_lines.append("")

            for i, f in enumerate(severity_findings, 1):
                verified_badge = "[已验证]" if f.is_verified else "[未验证]"
                poc_badge = " [含 PoC]" if f.has_poc else ""

                md_lines.append(
                    f"### {severity_level.upper()}-{i}: {_escape_markdown_inline(f.title)}"
                )
                md_lines.append("")
                md_lines.append(
                    f"**{verified_badge}**{poc_badge} | 类型: `{_escape_markdown_inline(f.vulnerability_type)}`"
                )
                md_lines.append("")

                if f.file_path:
                    location = _escape_markdown_inline(f.file_path)
                    if f.line_start:
                        location += f":{f.line_start}"
                        if f.line_end and f.line_end != f.line_start:
                            location += f"-{f.line_end}"
                    md_lines.append(f"**位置:** {location}")
                    md_lines.append("")

                if f.ai_confidence:
                    md_lines.append(f"**AI 置信度:** {int(f.ai_confidence * 100)}%")
                    md_lines.append("")

                if f.description:
                    md_lines.append("**漏洞描述:**")
                    md_lines.append("")
                    md_lines.append(f.description)
                    md_lines.append("")

                if f.code_snippet:
                    # 🔥 v2.1: 增强语言检测，避免默认 python 标记错误
                    lang = "text"  # 默认使用 text 而非 python
                    if f.file_path:
                        ext = f.file_path.split('.')[-1].lower()
                        lang_map = {
                            # Python
                            'py': 'python', 'pyw': 'python', 'pyi': 'python',
                            # JavaScript/TypeScript
                            'js': 'javascript', 'mjs': 'javascript', 'cjs': 'javascript',
                            'ts': 'typescript', 'mts': 'typescript',
                            'jsx': 'jsx', 'tsx': 'tsx',
                            # Web
                            'html': 'html', 'htm': 'html',
                            'css': 'css', 'scss': 'scss', 'sass': 'sass', 'less': 'less',
                            'vue': 'vue', 'svelte': 'svelte',
                            # Backend
                            'java': 'java', 'kt': 'kotlin', 'kts': 'kotlin',
                            'go': 'go', 'rs': 'rust',
                            'rb': 'ruby', 'erb': 'erb',
                            'php': 'php', 'phtml': 'php',
                            # C-family
                            'c': 'c', 'h': 'c',
                            'cpp': 'cpp', 'cc': 'cpp', 'cxx': 'cpp', 'hpp': 'cpp',
                            'cs': 'csharp',
                            # Shell/Script
                            'sh': 'bash', 'bash': 'bash', 'zsh': 'zsh',
                            'ps1': 'powershell', 'psm1': 'powershell',
                            # Config
                            'json': 'json', 'yaml': 'yaml', 'yml': 'yaml',
                            'toml': 'toml', 'ini': 'ini', 'cfg': 'ini',
                            'xml': 'xml', 'xhtml': 'xml',
                            # Database
                            'sql': 'sql',
                            # Other
                            'md': 'markdown', 'markdown': 'markdown',
                            'sol': 'solidity',
                            'swift': 'swift',
                            'r': 'r', 'R': 'r',
                            'lua': 'lua',
                            'pl': 'perl', 'pm': 'perl',
                            'ex': 'elixir', 'exs': 'elixir',
                            'erl': 'erlang',
                            'hs': 'haskell',
                            'scala': 'scala', 'sc': 'scala',
                            'clj': 'clojure', 'cljs': 'clojure',
                            'dart': 'dart',
                            'groovy': 'groovy', 'gradle': 'groovy',
                        }
                        lang = lang_map.get(ext, 'text')
                    md_lines.append("**漏洞代码:**")
                    md_lines.append("")
                    md_lines.append(f"```{lang}")
                    md_lines.append(f.code_snippet.strip())
                    md_lines.append("```")
                    md_lines.append("")

                if f.suggestion:
                    md_lines.append("**修复建议:**")
                    md_lines.append("")
                    md_lines.append(f.suggestion)
                    md_lines.append("")

                if f.fix_code:
                    md_lines.append("**参考修复代码:**")
                    md_lines.append("")
                    md_lines.append(f"```{lang if f.file_path else 'text'}")
                    md_lines.append(f.fix_code.strip())
                    md_lines.append("```")
                    md_lines.append("")

                # 🔥 添加 PoC 详情
                if f.has_poc:
                    md_lines.append("**概念验证 (PoC):**")
                    md_lines.append("")

                    if f.poc_description:
                        md_lines.append(f"*{f.poc_description}*")
                        md_lines.append("")

                    if f.poc_steps:
                        md_lines.append("**复现步骤:**")
                        md_lines.append("")
                        for step_idx, step in enumerate(f.poc_steps, 1):
                            md_lines.append(f"{step_idx}. {step}")
                        md_lines.append("")

                    if f.poc_code:
                        md_lines.append("**PoC 代码:**")
                        md_lines.append("")
                        md_lines.append("```")
                        md_lines.append(f.poc_code.strip())
                        md_lines.append("```")
                        md_lines.append("")

                md_lines.append("---")
                md_lines.append("")

    # Remediation Priority
    if critical > 0 or high > 0:
        md_lines.append("## 修复优先级建议")
        md_lines.append("")
        md_lines.append("基于已发现的漏洞，我们建议按以下优先级进行修复：")
        md_lines.append("")
        priority_idx = 1
        if critical > 0:
            md_lines.append(f"{priority_idx}. **立即修复:** 处理 {critical} 个严重漏洞 - 可能造成严重影响")
            priority_idx += 1
        if high > 0:
            md_lines.append(f"{priority_idx}. **高优先级:** 在 1 周内修复 {high} 个高危漏洞")
            priority_idx += 1
        if medium > 0:
            md_lines.append(f"{priority_idx}. **中优先级:** 在 2-4 周内修复 {medium} 个中危漏洞")
            priority_idx += 1
        if low > 0:
            md_lines.append(f"{priority_idx}. **低优先级:** 在日常维护中处理 {low} 个低危漏洞")
            priority_idx += 1
        md_lines.append("")

    # Footer
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("*本报告由 DeepAudit - AI 驱动的安全分析系统生成*")
    md_lines.append("")
    content = "\n".join(md_lines)
    
    filename = f"audit_report_{task.id[:8]}_{datetime.now().strftime('%Y%m%d')}.md"
    
    from fastapi.responses import Response
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
