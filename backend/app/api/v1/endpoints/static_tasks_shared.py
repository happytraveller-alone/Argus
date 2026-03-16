import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.core.config import settings
from app.db.session import async_session_factory, get_db
from app.models.opengrep import OpengrepRule
from app.models.user_config import UserConfig
from app.services.llm.service import LLMConfigError, LLMService

logger = logging.getLogger(__name__)
SCAN_PROGRESS_MAX_LOGS = 120
_scan_progress_store: Dict[str, Dict[str, Any]] = {}

def _is_test_like_directory(name: str) -> bool:
    return "test" in (name or "").lower()


async def _cleanup_incorrect_rules(db: AsyncSession) -> None:
    """移除 correct=false 的规则记录。"""
    try:
        await db.execute(delete(OpengrepRule).where(OpengrepRule.correct == False))
        await db.commit()
    except Exception as e:
        logger.warning(f"Failed to cleanup incorrect rules: {e}")
        try:
            await db.rollback()
        except Exception:
            pass


def _prune_test_directories(scan_root: str) -> int:
    removed_count = 0
    for root, dirs, _ in os.walk(scan_root, topdown=True):
        keep_dirs: list[str] = []
        for dirname in dirs:
            if _is_test_like_directory(dirname):
                shutil.rmtree(os.path.join(root, dirname), ignore_errors=True)
                removed_count += 1
            else:
                keep_dirs.append(dirname)
        dirs[:] = keep_dirs
    return removed_count


async def _get_project_root(project_id: str) -> Optional[str]:
    """
    获取项目根目录

    优先检查 uploads/zip_files 目录中是否存在该项目的 zip 文件
    如果存在，解压到临时目录并返回临时目录路径
    否则返回 None

    Args:
        project_id: 项目ID

    Returns:
        项目根目录路径，如果找不到 zip 文件返回 None
    """
    try:
        # 构建 uploads/zip_files 目录路径
        zip_dir = Path(getattr(settings, "ZIP_STORAGE_PATH", "./uploads/zip_files"))

        if not zip_dir.exists():
            logger.warning(f"Upload directory not found: {zip_dir}")
            return None

        # 查找项目 ID 对应的 zip 文件
        # 支持 {project_id}.zip 或 {project_id}_*.zip 的格式
        zip_files = list(zip_dir.glob(f"{project_id}.zip")) + list(
            zip_dir.glob(f"{project_id}_*.zip")
        )

        if not zip_files:
            logger.info(f"No zip file found for project {project_id}")
            return None

        zip_file = zip_files[0]  # 取第一个匹配的 zip 文件
        logger.info(f"Found zip file for project {project_id}: {zip_file}")

        # 创建临时目录
        temp_dir = tempfile.mkdtemp(prefix=f"VulHunter_{project_id}_")

        # 解压 zip 文件
        try:
            with zipfile.ZipFile(zip_file, "r") as zf:
                zf.extractall(temp_dir)
            logger.info(f"Extracted zip file to {temp_dir}")
        except zipfile.BadZipFile as e:
            logger.error(f"Invalid zip file {zip_file}: {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None
        except Exception as e:
            logger.error(f"Failed to extract zip file {zip_file}: {e}")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        # 上传和扫描统一排除目录名包含 test 的文件夹，减少无效扫描开销
        removed_test_dirs = _prune_test_directories(temp_dir)
        if removed_test_dirs:
            logger.info(
                "Removed %s test-like directories before static scan for project %s",
                removed_test_dirs,
                project_id,
            )

        # 检查解压后的目录是否只有一个子目录（常见的 zip 打包格式）
        items = os.listdir(temp_dir)
        items = [item for item in items if not item.startswith("__") and not item.startswith(".")]

        if len(items) == 1 and os.path.isdir(os.path.join(temp_dir, items[0])):
            # 只有一个子目录，使用该子目录作为项目根目录
            return os.path.join(temp_dir, items[0])

        return temp_dir

    except Exception as e:
        logger.error(f"Error getting project root for {project_id}: {e}")
        return None
_static_scan_process_lock = threading.Lock()
_static_running_scan_processes: Dict[str, subprocess.Popen] = {}
_static_cancelled_scan_tasks: set[str] = set()


def _ensure_opengrep_xdg_dirs() -> None:
    """确保 XDG 目录存在，防止 opengrep (Semgrep) 因缺少 XDG_CONFIG_HOME 等目录而启动失败。"""
    for env_key in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"):
        path = os.environ.get(env_key, "")
        if path and not os.path.isdir(path):
            try:
                os.makedirs(path, exist_ok=True)
            except OSError:
                pass


def _scan_task_key(scan_type: str, task_id: str) -> str:
    return f"{scan_type}:{task_id}"


def _is_scan_task_cancelled(scan_type: str, task_id: str) -> bool:
    key = _scan_task_key(scan_type, task_id)
    with _static_scan_process_lock:
        return key in _static_cancelled_scan_tasks


def _clear_scan_task_cancel(scan_type: str, task_id: str) -> None:
    key = _scan_task_key(scan_type, task_id)
    with _static_scan_process_lock:
        _static_cancelled_scan_tasks.discard(key)


def _request_scan_task_cancel(scan_type: str, task_id: str) -> bool:
    """请求取消扫描任务并尝试结束对应进程。"""
    key = _scan_task_key(scan_type, task_id)
    process = None
    with _static_scan_process_lock:
        _static_cancelled_scan_tasks.add(key)
        process = _static_running_scan_processes.get(key)

    if not process:
        return False

    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
    except Exception as e:
        logger.warning("Failed to terminate %s scan process for task %s: %s", scan_type, task_id, e)
    return True


def _run_subprocess_with_tracking(
    scan_type: str,
    task_id: str,
    cmd: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    """执行外部命令并记录进程句柄，便于用户中止时杀掉进程。"""
    key = _scan_task_key(scan_type, task_id)
    process: Optional[subprocess.Popen] = None

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        with _static_scan_process_lock:
            _static_running_scan_processes[key] = process

        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired:
        if process:
            process.kill()
            process.communicate()
        raise
    finally:
        with _static_scan_process_lock:
            _static_running_scan_processes.pop(key, None)


def _as_utc_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _calc_scan_duration_ms_from_created_at(
    created_at: Optional[datetime],
    finished_at: Optional[datetime] = None,
) -> int:
    start_at = _as_utc_datetime(created_at)
    if start_at is None:
        return 0

    end_at = _as_utc_datetime(finished_at) or datetime.now(timezone.utc)
    duration_ms = int((end_at - start_at).total_seconds() * 1000)
    return max(0, duration_ms)


def _sync_task_scan_duration(task: Any, finished_at: Optional[datetime] = None) -> None:
    task.scan_duration_ms = _calc_scan_duration_ms_from_created_at(
        getattr(task, "created_at", None),
        finished_at=finished_at,
    )
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


def _record_scan_progress(
    task_id: str,
    *,
    status: Optional[str] = None,
    progress: Optional[float] = None,
    stage: Optional[str] = None,
    message: Optional[str] = None,
    level: str = "info",
) -> None:
    state = _scan_progress_store.get(task_id) or {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "current_stage": "pending",
        "message": "任务已创建，等待执行",
        "started_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
        "logs": [],
    }

    if status:
        state["status"] = status
    if progress is not None:
        state["progress"] = max(0.0, min(100.0, float(progress)))
    if stage:
        state["current_stage"] = stage
    if message:
        state["message"] = message
        state["logs"].append(
            {
                "timestamp": _utc_now_iso(),
                "stage": stage or state.get("current_stage") or "unknown",
                "message": message,
                "progress": state.get("progress", 0.0),
                "level": level,
            }
        )
        if len(state["logs"]) > SCAN_PROGRESS_MAX_LOGS:
            state["logs"] = state["logs"][-SCAN_PROGRESS_MAX_LOGS:]
    state["updated_at"] = _utc_now_iso()
    _scan_progress_store[task_id] = state
async def _get_user_config(db: AsyncSession, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """获取用户配置（与 agent_tasks 一致）"""
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


def _normalize_llm_config_error_message(exc: Exception) -> str:
    return f"LLM配置错误: {exc}"


def _is_llm_config_error(exc: Exception) -> bool:
    if isinstance(exc, LLMConfigError):
        return True
    msg = str(exc)
    return "LLM配置错误" in msg or "llmModel" in msg or "llmBaseUrl" in msg or "llmApiKey" in msg


def _validate_user_llm_config(user_config: Optional[Dict[str, Any]]) -> None:
    llm_service = LLMService(user_config=user_config or {})
    _ = llm_service.config
