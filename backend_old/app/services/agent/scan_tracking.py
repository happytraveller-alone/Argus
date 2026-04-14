import asyncio
import logging
import os
import signal
import subprocess
import threading
from typing import Any, Awaitable, Dict, List, Optional

from app.services.agent.scanner_runner import stop_scanner_container_sync

logger = logging.getLogger(__name__)

_static_scan_process_lock = threading.Lock()
_static_running_scan_processes: Dict[str, subprocess.Popen] = {}
_static_running_scan_containers: Dict[str, str] = {}
_static_cancelled_scan_tasks: set[str] = set()
_static_background_jobs: Dict[str, asyncio.Task] = {}


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
