import asyncio
import json
import logging
import os
import signal
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Dict, List, Optional

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.core.config import settings
from app.db.session import async_session_factory, get_db
from app.models.opengrep import OpengrepRule
from app.models.user_config import UserConfig
from app.services.backend_venv import (
    build_backend_venv_env,
    resolve_backend_venv_executable,
)
from app.services.yasa_runtime_config import get_cached_global_yasa_runtime_config
from app.services.llm.service import LLMConfigError, LLMService
from app.services.scanner_runner import stop_scanner_container_sync

logger = logging.getLogger(__name__)
SCAN_PROGRESS_MAX_LOGS = 120
SCAN_PROGRESS_TERMINAL_STATUSES = {"completed", "failed", "interrupted", "cancelled"}
_scan_progress_store: Dict[str, Dict[str, Any]] = {}


def _scan_workspace_root() -> Path:
    configured = str(getattr(settings, "SCAN_WORKSPACE_ROOT", "/tmp/vulhunter/scans") or "").strip()
    return Path(configured or "/tmp/vulhunter/scans")


def _build_backend_venv_env(base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    return build_backend_venv_env(base_env)


def _resolve_backend_venv_executable(name: str, *, required: bool = True) -> Optional[str]:
    return resolve_backend_venv_executable(name, required=required)


def ensure_scan_workspace(scan_type: str, task_id: str) -> Path:
    workspace = _scan_workspace_root() / str(scan_type).strip() / str(task_id).strip()
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _ensure_scan_subdir(scan_type: str, task_id: str, name: str) -> Path:
    path = ensure_scan_workspace(scan_type, task_id) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_scan_project_dir(scan_type: str, task_id: str) -> Path:
    return _ensure_scan_subdir(scan_type, task_id, "project")


def ensure_scan_output_dir(scan_type: str, task_id: str) -> Path:
    return _ensure_scan_subdir(scan_type, task_id, "output")


def ensure_scan_logs_dir(scan_type: str, task_id: str) -> Path:
    return _ensure_scan_subdir(scan_type, task_id, "logs")


def ensure_scan_meta_dir(scan_type: str, task_id: str) -> Path:
    return _ensure_scan_subdir(scan_type, task_id, "meta")


def cleanup_scan_workspace(scan_type: str, task_id: str) -> None:
    workspace = _scan_workspace_root() / str(scan_type).strip() / str(task_id).strip()
    shutil.rmtree(workspace, ignore_errors=True)


def copy_project_tree_to_scan_dir(project_root: str | Path, project_dir: str | Path) -> None:
    src_root = Path(project_root).resolve()
    dst_root = Path(project_dir).resolve()

    if src_root == dst_root:
        raise ValueError("project_dir must differ from project_root")

    dst_root.parent.mkdir(parents=True, exist_ok=True)

    def _should_ignore(candidate: Path) -> bool:
        resolved = candidate.resolve()
        try:
            dst_root.relative_to(resolved)
            return True
        except ValueError:
            return False

    def _ignore(_current_dir: str, names: list[str]) -> set[str]:
        current = Path(_current_dir).resolve()
        ignored: set[str] = set()
        for name in names:
            if _should_ignore(current / name):
                ignored.add(name)
        return ignored

    shutil.copytree(src_root, dst_root, dirs_exist_ok=True, ignore=_ignore)


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
_static_running_scan_containers: Dict[str, str] = {}
_static_cancelled_scan_tasks: set[str] = set()
_static_background_jobs: Dict[str, asyncio.Task] = {}


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


def _register_static_background_job(
    scan_type: str,
    task_id: str,
    job: asyncio.Task,
) -> None:
    _static_background_jobs[_scan_task_key(scan_type, task_id)] = job


def _pop_static_background_job(scan_type: str, task_id: str) -> Optional[asyncio.Task]:
    return _static_background_jobs.pop(_scan_task_key(scan_type, task_id), None)


def _get_static_background_job(scan_type: str, task_id: str) -> Optional[asyncio.Task]:
    return _static_background_jobs.get(_scan_task_key(scan_type, task_id))


def _launch_static_background_job(
    scan_type: str,
    task_id: str,
    coro: Awaitable[Any],
) -> asyncio.Task:
    task_name = f"static_scan:{scan_type}:{task_id}"
    job = asyncio.create_task(coro, name=task_name)
    _register_static_background_job(scan_type, task_id, job)

    def _on_done(done_task: asyncio.Task) -> None:
        _pop_static_background_job(scan_type, task_id)
        try:
            done_task.exception()
        except asyncio.CancelledError:
            logger.info("Static background job cancelled: %s", task_name)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Static background job failed: %s: %s", task_name, exc)

    job.add_done_callback(_on_done)
    return job


async def _shutdown_static_background_jobs() -> int:
    jobs = [job for job in list(_static_background_jobs.values()) if not job.done()]
    for job in jobs:
        job.cancel()
    if jobs:
        await asyncio.gather(*jobs, return_exceptions=True)
    return len(jobs)


async def _release_request_db_session(db: Any) -> None:
    in_transaction = getattr(db, "in_transaction", None)
    should_rollback = False
    try:
        should_rollback = bool(in_transaction()) if callable(in_transaction) else bool(in_transaction)
    except Exception:
        should_rollback = False

    if should_rollback:
        rollback = getattr(db, "rollback", None)
        if callable(rollback):
            try:
                await rollback()
            except Exception:
                pass

    close = getattr(db, "close", None)
    if callable(close):
        try:
            await close()
        except Exception:
            pass


def _is_scan_task_cancelled(scan_type: str, task_id: str) -> bool:
    key = _scan_task_key(scan_type, task_id)
    with _static_scan_process_lock:
        return key in _static_cancelled_scan_tasks


def _clear_scan_task_cancel(scan_type: str, task_id: str) -> None:
    key = _scan_task_key(scan_type, task_id)
    with _static_scan_process_lock:
        _static_cancelled_scan_tasks.discard(key)


def _register_scan_container(scan_type: str, task_id: str, container_id: str) -> None:
    key = _scan_task_key(scan_type, task_id)
    with _static_scan_process_lock:
        _static_running_scan_containers[key] = container_id


def _pop_scan_container(scan_type: str, task_id: str) -> Optional[str]:
    key = _scan_task_key(scan_type, task_id)
    with _static_scan_process_lock:
        return _static_running_scan_containers.pop(key, None)


async def _stop_scan_container(scan_type: str, task_id: str) -> bool:
    container_id = _pop_scan_container(scan_type, task_id)
    if not container_id:
        return False
    return await asyncio.to_thread(stop_scanner_container_sync, container_id)


def _request_scan_task_cancel(scan_type: str, task_id: str) -> bool:
    """请求取消扫描任务并尝试结束对应进程。"""
    key = _scan_task_key(scan_type, task_id)
    process = None
    container_id = None
    with _static_scan_process_lock:
        _static_cancelled_scan_tasks.add(key)
        process = _static_running_scan_processes.get(key)
        container_id = _static_running_scan_containers.get(key)

    if container_id:
        try:
            stop_scanner_container_sync(container_id)
        except Exception as e:
            logger.warning("Failed to stop %s scan container for task %s: %s", scan_type, task_id, e)
        finally:
            with _static_scan_process_lock:
                _static_running_scan_containers.pop(key, None)
        job = _get_static_background_job(scan_type, task_id)
        if job and not job.done():
            job.cancel()
        return True

    if not process:
        job = _get_static_background_job(scan_type, task_id)
        if job and not job.done():
            job.cancel()
            return True
        return False

    try:
        _terminate_scan_process(process, scan_type, task_id)
    except Exception as e:
        logger.warning("Failed to terminate %s scan process for task %s: %s", scan_type, task_id, e)
    job = _get_static_background_job(scan_type, task_id)
    if job and not job.done():
        job.cancel()
    return True


def _is_scan_process_active(scan_type: str, task_id: str) -> bool:
    key = _scan_task_key(scan_type, task_id)
    with _static_scan_process_lock:
        process = _static_running_scan_processes.get(key)
    return bool(process and process.poll() is None)


def _terminate_scan_process(
    process: Optional[subprocess.Popen],
    scan_type: str,
    task_id: str,
    *,
    grace_seconds: Optional[int] = None,
) -> None:
    if process is None or process.poll() is not None:
        return

    grace = grace_seconds
    if grace is None:
        try:
            runtime_config = get_cached_global_yasa_runtime_config()
            grace = int(
                runtime_config.get(
                    "yasa_process_kill_grace_seconds",
                    getattr(settings, "YASA_PROCESS_KILL_GRACE_SECONDS", 2) or 2,
                )
            )
        except Exception:
            grace = 2
    grace = max(1, int(grace))

    used_group_kill = False
    if os.name != "nt":
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGTERM)
            used_group_kill = True
        except Exception:
            used_group_kill = False

    if not used_group_kill:
        process.terminate()

    try:
        process.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass

    if os.name != "nt" and used_group_kill:
        try:
            pgid = os.getpgid(process.pid)
            os.killpg(pgid, signal.SIGKILL)
        except Exception:
            process.kill()
    else:
        process.kill()

    try:
        process.wait(timeout=grace)
    except Exception:
        pass


def _run_subprocess_with_tracking(
    scan_type: str,
    task_id: str,
    cmd: List[str],
    *,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = 600,
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
            start_new_session=True,
        )
        with _static_scan_process_lock:
            _static_running_scan_processes[key] = process

        effective_timeout = None if timeout is None else max(1, int(timeout))
        stdout, stderr = process.communicate(timeout=effective_timeout)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired:
        _terminate_scan_process(process, scan_type, task_id)
        if process:
            # Do not block forever here. Detached descendants may keep stdio pipes open.
            try:
                process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            except Exception:
                pass
        raise
    finally:
        with _static_scan_process_lock:
            _static_running_scan_processes.pop(key, None)


def _collect_yasa_process_pids(
    *,
    task_id: Optional[str] = None,
    report_dir: Optional[str] = None,
    source_path: Optional[str] = None,
) -> List[int]:
    """按任务特征收集 YASA 相关进程 PID（避免误杀无关进程）。"""
    indicators: List[str] = []
    if task_id:
        indicators.append(str(task_id))
        indicators.append(f"/tmp/yasa_report_{task_id}_")
    if report_dir:
        indicators.append(str(report_dir))
    if source_path:
        indicators.append(str(source_path))
    indicators = [item for item in indicators if item]
    if not indicators:
        return []

    try:
        output = subprocess.check_output(
            ["ps", "-eo", "pid=,cmd="],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []

    current_pid = os.getpid()
    matched: set[int] = set()
    for line in output.splitlines():
        raw = line.strip()
        if not raw:
            continue
        parts = raw.split(maxsplit=1)
        if len(parts) != 2:
            continue
        pid_text, cmd = parts
        lower_cmd = cmd.lower()
        if "yasa" not in lower_cmd and "yasa-engine.real" not in lower_cmd:
            continue
        if not any(indicator in cmd for indicator in indicators):
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid > 1 and pid != current_pid:
            matched.add(pid)

    return sorted(matched)


def _force_cleanup_yasa_processes(
    *,
    task_id: Optional[str] = None,
    report_dir: Optional[str] = None,
    source_path: Optional[str] = None,
    grace_seconds: Optional[int] = None,
) -> Dict[str, int]:
    """兜底清理脱链的 YASA 进程。"""
    pids = _collect_yasa_process_pids(
        task_id=task_id,
        report_dir=report_dir,
        source_path=source_path,
    )
    if not pids:
        return {"matched": 0, "terminated": 0, "killed": 0}

    grace = grace_seconds
    if grace is None:
        try:
            runtime_config = get_cached_global_yasa_runtime_config()
            grace = int(
                runtime_config.get(
                    "yasa_process_kill_grace_seconds",
                    getattr(settings, "YASA_PROCESS_KILL_GRACE_SECONDS", 2) or 2,
                )
            )
        except Exception:
            grace = 2
    grace = max(0, int(grace))

    terminated = 0
    killed = 0
    for pid in pids:
        terminated_this_pid = False
        if os.name != "nt":
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
                terminated_this_pid = True
            except Exception:
                terminated_this_pid = False
        if not terminated_this_pid:
            try:
                os.kill(pid, signal.SIGTERM)
                terminated_this_pid = True
            except Exception:
                terminated_this_pid = False
        if terminated_this_pid:
            terminated += 1

    if grace > 0:
        time.sleep(grace)

    for pid in pids:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        except Exception:
            continue

        killed_this_pid = False
        if os.name != "nt":
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGKILL)
                killed_this_pid = True
            except Exception:
                killed_this_pid = False
        if not killed_this_pid:
            try:
                os.kill(pid, signal.SIGKILL)
                killed_this_pid = True
            except Exception:
                killed_this_pid = False
        if killed_this_pid:
            killed += 1

    return {"matched": len(pids), "terminated": terminated, "killed": killed}


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


def _parse_progress_timestamp(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _clear_scan_progress(task_id: str) -> bool:
    return _scan_progress_store.pop(task_id, None) is not None


def prune_scan_progress_store(
    *,
    ttl_seconds: Optional[int] = None,
    now: Optional[datetime] = None,
) -> int:
    ttl = max(
        1,
        int(
            ttl_seconds
            or getattr(settings, "STATIC_SCAN_PROGRESS_TTL_SECONDS", 60 * 60)
            or 60 * 60
        ),
    )
    reference_time = now.astimezone(timezone.utc) if isinstance(now, datetime) else datetime.now(timezone.utc)
    cutoff = reference_time - timedelta(seconds=ttl)
    expired_task_ids: list[str] = []

    for task_id, state in list(_scan_progress_store.items()):
        updated_at = _parse_progress_timestamp((state or {}).get("updated_at"))
        if updated_at is None or updated_at <= cutoff:
            expired_task_ids.append(task_id)

    for task_id in expired_task_ids:
        _clear_scan_progress(task_id)

    return len(expired_task_ids)


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
    if str(state.get("status", "")).lower() in SCAN_PROGRESS_TERMINAL_STATUSES:
        _clear_scan_progress(task_id)
async def _get_user_config(db: AsyncSession, user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """获取用户配置（与 agent_tasks 一致）"""
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
