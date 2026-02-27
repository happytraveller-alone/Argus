import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.services.llm_rule.repo_cache_manager import GlobalRepoCacheManager
from app.services.agent.mcp.daemon_manager import MCPDaemonManager
from app.models.gitleaks import GitleaksScanTask
from app.models.opengrep import OpengrepScanTask
from sqlalchemy.future import select

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 禁用 uvicorn access log 和 LiteLLM INFO 日志
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)


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


async def recover_interrupted_static_scan_tasks() -> None:
    """
    将上次异常退出时仍处于 running 状态的静态扫描任务标记为 interrupted。
    """
    async with AsyncSessionLocal() as db:
        interrupted_opengrep = 0
        interrupted_gitleaks = 0

        opengrep_result = await db.execute(
            select(OpengrepScanTask).where(OpengrepScanTask.status == "running")
        )
        for task in opengrep_result.scalars().all():
            task.status = "interrupted"
            task.error_count = (task.error_count or 0) + 1
            interrupted_opengrep += 1

        gitleaks_result = await db.execute(
            select(GitleaksScanTask).where(GitleaksScanTask.status == "running")
        )
        for task in gitleaks_result.scalars().all():
            task.status = "interrupted"
            if not task.error_message:
                task.error_message = "服务中断，任务被自动标记为中断"
            interrupted_gitleaks += 1

        if interrupted_opengrep or interrupted_gitleaks:
            await db.commit()
            logger.warning(
                "检测到上次中断遗留任务，已自动标记 interrupted：opengrep=%s, gitleaks=%s",
                interrupted_opengrep,
                interrupted_gitleaks,
            )
        else:
            await db.rollback()


async def _autostart_mcp_daemons_non_blocking(app: FastAPI, mcp_daemon_manager: MCPDaemonManager, daemon_specs):
    try:
        results = await asyncio.to_thread(mcp_daemon_manager.autostart, daemon_specs)
        app.state.mcp_daemon_status = {
            key: value.to_dict()
            for key, value in results.items()
        }
    except Exception as e:
        logger.warning(f"MCP 守护进程后台启动失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时初始化数据库（创建默认账户等）和全局缓存管理
    """
    logger.info("DeepAudit 后端服务启动中...")

    # 初始化全局 Git 项目缓存管理器
    try:
        cache_dir = Path(settings.CACHE_DIR) / "repos"
        GlobalRepoCacheManager.set_cache_dir(cache_dir)
        logger.info(f"  - Git 项目缓存初始化完成: {cache_dir}")
    except Exception as e:
        logger.warning(f"Git 项目缓存初始化失败: {e}")

    # 初始化数据库（创建默认账户）
    # 注意：需要先运行 alembic upgrade head 创建表结构
    try:
        async with AsyncSessionLocal() as db:
            await init_db(db)
        logger.info("  - 数据库初始化完成")
    except Exception as e:
        # 表不存在时静默跳过，等待用户运行数据库迁移
        error_msg = str(e)
        if "does not exist" in error_msg or "UndefinedTableError" in error_msg:
            logger.info("数据库表未创建，请先运行: alembic upgrade head")
        else:
            logger.warning(f"数据库初始化跳过: {e}")

    try:
        await recover_interrupted_static_scan_tasks()
    except Exception as e:
        logger.warning(f"恢复静态扫描中断任务失败: {e}")

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
    logger.info("DeepAudit 后端服务已启动")
    logger.info(f"API 文档: http://localhost:8000/docs")
    logger.info("=" * 50)
    # logger.info("演示账户: demo@example.com / demo123")
    logger.info("无需账号即可使用")
    logger.info("=" * 50)

    mcp_daemon_manager = MCPDaemonManager()
    app.state.mcp_daemon_manager = mcp_daemon_manager
    app.state.mcp_daemon_status = {}
    app.state.mcp_daemon_autostart_task = None
    try:
        daemon_specs = mcp_daemon_manager.build_specs(
            settings,
            project_root=str(Path.cwd()),
        )
        if daemon_specs:
            app.state.mcp_daemon_status = {
                spec.name: {
                    "name": spec.name,
                    "ready": False,
                    "started": False,
                    "reason": "starting_in_background",
                    "url": spec.url,
                    "pid": None,
                    "command": None,
                }
                for spec in daemon_specs
            }
            app.state.mcp_daemon_autostart_task = asyncio.create_task(
                _autostart_mcp_daemons_non_blocking(app, mcp_daemon_manager, daemon_specs)
            )
            logger.info("MCP 守护进程后台启动中（不阻塞 API 启动）")
        else:
            logger.info("MCP 守护进程自动驻留已禁用")
    except Exception as e:
        logger.warning(f"MCP 守护进程启动失败: {e}")

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

    try:
        daemon_autostart_task = getattr(app.state, "mcp_daemon_autostart_task", None)
        if daemon_autostart_task is not None:
            await asyncio.wait_for(daemon_autostart_task, timeout=1.0)
    except asyncio.TimeoutError:
        logger.warning("MCP 守护进程后台启动任务仍在执行，退出时跳过等待")
    except Exception as e:
        logger.warning(f"等待 MCP 守护进程后台启动任务失败: {e}")

    try:
        daemon_manager = getattr(app.state, "mcp_daemon_manager", None)
        if daemon_manager is not None:
            daemon_manager.stop_all()
    except Exception as e:
        logger.warning(f"停止 MCP 守护进程失败: {e}")

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

    logger.info("DeepAudit 后端服务已关闭")


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
        "message": "Welcome to DeepAudit API",
        "docs": "/docs",
        # "demo_account": {"email": "demo@example.com", "password": "demo123"},
    }
