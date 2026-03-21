import asyncio
import logging
import subprocess
import warnings
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.services.llm_rule.repo_cache_manager import GlobalRepoCacheManager
from app.models.agent_task import AgentTask, AgentTaskStatus
from app.models.gitleaks import GitleaksScanTask
from app.models.opengrep import OpengrepScanTask
from app.models.bandit import BanditScanTask
from app.models.phpstan import PhpstanScanTask
from app.models.yasa import YasaScanTask
from sqlalchemy.future import select
from sqlalchemy import text
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 禁用 uvicorn access log 和 LiteLLM INFO 日志
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

warnings.filterwarnings(
    "ignore",
    message=r".*enable_cleanup_closed ignored because .*",
    category=DeprecationWarning,
    module=r"aiohttp\.connector",
)


async def check_agent_services():
    """检查 Agent 必须服务的可用性"""
    issues = []

    # 检查 Docker/沙箱服务
    try:
        import docker

        client = docker.from_env()
        client.ping()
        logger.info("  - Docker 服务可用")
    except ImportError:
        issues.append("Docker Python 库未安装 (pip install docker)")
    except Exception as e:
        issues.append(f"Docker 服务不可用: {e}")

    # 检查 Redis 连接（可选警告）
    try:
        import os

        import redis

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)
        r.ping()
        logger.info("  - Redis 服务可用")
    except ImportError:
        logger.warning("  - Redis Python 库未安装，部分功能可能受限")
    except Exception as e:
        logger.warning(f"  - Redis 服务连接失败: {e}")

    return issues


async def run_pending_database_migrations() -> None:
    """Run Alembic migrations for startup paths that skipped the entrypoint."""
    backend_root = Path(__file__).resolve().parents[1]

    def _run_upgrade() -> None:
        subprocess.run(
            ["alembic", "upgrade", "heads"],
            cwd=str(backend_root),
            check=True,
        )

    try:
        await asyncio.to_thread(_run_upgrade)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("自动执行 alembic upgrade heads 失败") from exc


async def _read_current_database_versions() -> set[str]:
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(text("SELECT version_num FROM alembic_version"))
        except Exception as exc:
            raise RuntimeError(
                "数据库缺少迁移版本元数据（alembic_version），请先运行 alembic upgrade heads"
            ) from exc

        return {str(item).strip() for item in result.scalars().all() if str(item).strip()}




async def assert_database_schema_is_latest() -> None:
    """Fail fast when DB migration version does not match Alembic head."""
    backend_root = Path(__file__).resolve().parents[1]
    alembic_cfg = AlembicConfig(str(backend_root / "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_cfg)
    expected_heads = {str(item) for item in script.get_heads() if str(item).strip()}
    current_versions = await _read_current_database_versions()

    if not current_versions:
        raise RuntimeError("数据库未记录迁移版本，请先运行 alembic upgrade heads")

    if expected_heads and current_versions != expected_heads:
        logger.warning(
            "检测到数据库迁移版本落后，尝试自动升级：current=%s heads=%s",
            sorted(current_versions),
            sorted(expected_heads),
        )
        await run_pending_database_migrations()
        current_versions = await _read_current_database_versions()

    if expected_heads and current_versions != expected_heads:
        raise RuntimeError(
            "数据库迁移版本与代码不一致："
            f"current={sorted(current_versions)} heads={sorted(expected_heads)}。"
            "请运行 alembic upgrade heads"
        )

async def _run_daily_cache_cleanup(stop_event: asyncio.Event) -> None:
    """每日清理一次缓存，直到收到停止信号。"""
    while not stop_event.is_set():
        try:
            cleaned = GlobalRepoCacheManager.cleanup_unused_caches(
                max_age_days=30,
                max_unused_days=14,
            )
            if cleaned > 0:
                logger.info(f"  - 定时清理完成，已清理 {cleaned} 个过期的 Git 项目缓存")
        except Exception as e:
            logger.warning(f"定时清理过期缓存失败: {e}")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=24 * 60 * 60)
        except asyncio.TimeoutError:
            continue


INTERRUPTED_ERROR_MESSAGE = "服务中断，任务被自动标记为中断"
RECOVERABLE_AGENT_TASK_STATUSES = {
    AgentTaskStatus.PENDING,
    AgentTaskStatus.INITIALIZING,
    AgentTaskStatus.RUNNING,
    AgentTaskStatus.PLANNING,
    AgentTaskStatus.INDEXING,
    AgentTaskStatus.ANALYZING,
    AgentTaskStatus.VERIFYING,
    AgentTaskStatus.REPORTING,
}
RECOVERABLE_OPENGREP_TASK_STATUSES = {"pending", "running"}
RECOVERABLE_GITLEAKS_TASK_STATUSES = {"pending", "running"}
# Bandit interrupted recovery support
RECOVERABLE_BANDIT_TASK_STATUSES = {"pending", "running"}
# PHPStan interrupted recovery support
RECOVERABLE_PHPSTAN_TASK_STATUSES = {"pending", "running"}
# YASA interrupted recovery support
RECOVERABLE_YASA_TASK_STATUSES = {"pending", "running"}


def _mark_task_interrupted(task) -> bool:
    changed = False
    if str(getattr(task, "status", "")).lower() != "interrupted":
        task.status = "interrupted"
        changed = True

    if hasattr(task, "completed_at") and getattr(task, "completed_at", None) is None:
        task.completed_at = datetime.now(timezone.utc)

    if hasattr(task, "error_message") and not getattr(task, "error_message", None):
        task.error_message = INTERRUPTED_ERROR_MESSAGE

    if hasattr(task, "error_count"):
        task.error_count = int(getattr(task, "error_count", 0) or 0) + 1

    return changed


async def recover_interrupted_tasks() -> dict[str, int]:
    """
    将上次异常退出时仍处于进行中的任务统一标记为 interrupted。
    """
    async with AsyncSessionLocal() as db:
        counts = {
            "agent": 0,
            "opengrep": 0,
            "gitleaks": 0,
            "bandit": 0,
            "phpstan": 0,
            "yasa": 0,
        }

        recovery_specs = [
            (AgentTask, RECOVERABLE_AGENT_TASK_STATUSES, "agent"),
            (OpengrepScanTask, RECOVERABLE_OPENGREP_TASK_STATUSES, "opengrep"),
            (GitleaksScanTask, RECOVERABLE_GITLEAKS_TASK_STATUSES, "gitleaks"),
            # Bandit interrupted recovery support
            (BanditScanTask, RECOVERABLE_BANDIT_TASK_STATUSES, "bandit"),
            # PHPStan interrupted recovery support
            (PhpstanScanTask, RECOVERABLE_PHPSTAN_TASK_STATUSES, "phpstan"),
            # YASA interrupted recovery support
            (YasaScanTask, RECOVERABLE_YASA_TASK_STATUSES, "yasa"),
        ]

        for model, recoverable_statuses, counter_key in recovery_specs:
            result = await db.execute(
                select(model).where(model.status.in_(sorted(recoverable_statuses)))
            )
            for task in result.scalars().all():
                if _mark_task_interrupted(task):
                    counts[counter_key] += 1

        if any(counts.values()):
            await db.commit()
            logger.warning(
                "检测到上次中断遗留任务，已自动标记 interrupted：agent=%s, opengrep=%s, gitleaks=%s, bandit=%s, phpstan=%s, yasa=%s",
                counts["agent"],
                counts["opengrep"],
                counts["gitleaks"],
                counts["bandit"],
                counts["phpstan"],
                counts["yasa"],
            )
        else:
            await db.rollback()

        return counts



@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时初始化数据库（创建默认账户等）和全局缓存管理
    """
    logger.info("VulHunter 后端服务启动中...")

    # 初始化全局 Git 项目缓存管理器
    try:
        cache_dir = Path(settings.CACHE_DIR) / "repos"
        GlobalRepoCacheManager.set_cache_dir(cache_dir)
        logger.info(f"  - Git 项目缓存初始化完成: {cache_dir}")
    except Exception as e:
        logger.warning(f"Git 项目缓存初始化失败: {e}")

    # 初始化 tiktoken 缓存目录，并按需预热。
    try:
        from app.services.llm.tokenizer import ensure_tiktoken_cache_dir, prewarm_tiktoken

        tiktoken_cache_dir = ensure_tiktoken_cache_dir()
        if tiktoken_cache_dir:
            logger.info(f"  - tiktoken 缓存目录就绪: {tiktoken_cache_dir}")

        if getattr(settings, "LLM_TOKENIZER_PREWARM", False):
            prewarm_tiktoken(settings.LLM_MODEL or "gpt-4o-mini")
    except Exception as e:
        logger.warning(f"tiktoken 启动预热初始化失败: {e}")

    # 迁移版本检查：不一致时拒绝启动，避免运行时因缺表导致 500。
    await assert_database_schema_is_latest()
    logger.info("  - 数据库迁移版本检查通过")

    # 初始化数据库（创建默认账户）
    try:
        async with AsyncSessionLocal() as db:
            await init_db(db)
        logger.info("  - 数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise

    try:
        await recover_interrupted_tasks()
    except Exception as e:
        logger.warning(f"恢复中断任务失败: {e}")

    # 检查 Agent 服务
    logger.info("检查 Agent 核心服务...")
    issues = await check_agent_services()
    if issues:
        logger.warning("=" * 50)
        logger.warning("Agent 服务检查发现问题:")
        for issue in issues:
            logger.warning(f"  - {issue}")
        logger.warning("部分功能可能不可用，请检查配置")
        logger.warning("=" * 50)
    else:
        logger.info("  - Agent 核心服务检查通过")

    logger.info("=" * 50)
    logger.info("VulHunter 后端服务已启动")
    logger.info(f"API 文档: http://localhost:8000/docs")
    logger.info("=" * 50)
    # logger.info("演示账户: demo@example.com / demo123")
    logger.info("无需账号即可使用")
    logger.info("=" * 50)

    app.state.mcp_daemon_status = {}
    logger.info("MCP 已切换为任务内按需 stdio 调用，跳过启动期常驻守护进程")

    # 启动每日定时清理任务
    stop_event = asyncio.Event()
    app.state.cache_cleanup_stop = stop_event
    app.state.cache_cleanup_task = asyncio.create_task(
        _run_daily_cache_cleanup(stop_event)
    )

    yield

    # 清理资源
    logger.info("清理资源...")
    # 停止每日清理任务
    try:
        stop_event = getattr(app.state, "cache_cleanup_stop", None)
        task = getattr(app.state, "cache_cleanup_task", None)
        if stop_event and task:
            stop_event.set()
            await task
    except Exception as e:
        logger.warning(f"停止定时清理任务失败: {e}")

    # 清理未关闭的 aiohttp ClientSession（修复资源泄漏警告）
    try:
        import gc
        
        # 等待一小段时间让所有 pending 的异步任务完成
        await asyncio.sleep(0.1)
        
        # 强制垃圾回收，触发并清理未关闭的资源
        gc.collect()
        
        # 再等待一点时间让清理完成
        await asyncio.sleep(0.05)
        
        logger.info("  - 异步资源清理完成")
    except Exception as e:
        logger.warning(f"清理异步资源失败: {e}")

    try:
        # 可选：清理过期的 git 缓存（超过30天未使用的缓存）
        cleaned = GlobalRepoCacheManager.cleanup_unused_caches(
            max_age_days=30, 
            max_unused_days=14
        )
        if cleaned > 0:
            logger.info(f"  - 已清理 {cleaned} 个过期的 Git 项目缓存")
    except Exception as e:
        logger.warning(f"清理过期缓存失败: {e}")

    logger.info("VulHunter 后端服务已关闭")


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Configure CORS - Allow all origins in development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {
        "message": "Welcome to VulHunter API",
        "docs": "/docs",
        # "demo_account": {"email": "demo@example.com", "password": "demo123"},
    }
