import json
import threading
from typing import Any, Dict

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user_config import UserConfig

GLOBAL_YASA_RUNTIME_CONFIG_KEY = "global_yasa_runtime_config"

_RUNTIME_LIMITS: Dict[str, tuple[int, int]] = {
    "yasa_timeout_seconds": (30, 24 * 60 * 60),
    "yasa_orphan_stale_seconds": (30, 24 * 60 * 60),
    "yasa_exec_heartbeat_seconds": (1, 60 * 60),
    "yasa_process_kill_grace_seconds": (1, 60),
}

_runtime_config_cache_lock = threading.Lock()
_runtime_config_cache: Dict[str, int] = {}


def _build_default_runtime_config() -> Dict[str, int]:
    return {
        "yasa_timeout_seconds": int(getattr(settings, "YASA_TIMEOUT_SECONDS", 600) or 600),
        "yasa_orphan_stale_seconds": int(
            getattr(settings, "YASA_ORPHAN_STALE_SECONDS", 120) or 120
        ),
        "yasa_exec_heartbeat_seconds": int(
            getattr(settings, "YASA_EXEC_HEARTBEAT_SECONDS", 15) or 15
        ),
        "yasa_process_kill_grace_seconds": int(
            getattr(settings, "YASA_PROCESS_KILL_GRACE_SECONDS", 2) or 2
        ),
    }


def _normalize_runtime_config(raw: Dict[str, Any]) -> Dict[str, int]:
    normalized: Dict[str, int] = {}
    defaults = _build_default_runtime_config()
    for field, (min_value, max_value) in _RUNTIME_LIMITS.items():
        fallback = defaults[field]
        value = raw.get(field, fallback)
        try:
            numeric = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field} 必须为整数") from exc
        if numeric < min_value or numeric > max_value:
            raise ValueError(
                f"{field} 超出范围，允许区间为 [{min_value}, {max_value}]"
            )
        normalized[field] = numeric
    return normalized


def get_cached_global_yasa_runtime_config() -> Dict[str, int]:
    with _runtime_config_cache_lock:
        if _runtime_config_cache:
            return dict(_runtime_config_cache)
    return _build_default_runtime_config()


def update_cached_global_yasa_runtime_config(config: Dict[str, Any]) -> Dict[str, int]:
    normalized = _normalize_runtime_config(config)
    with _runtime_config_cache_lock:
        _runtime_config_cache.clear()
        _runtime_config_cache.update(normalized)
    return dict(normalized)


def _parse_runtime_config_from_user_config(record: UserConfig) -> Dict[str, int] | None:
    raw_other_config = str(record.other_config or "").strip()
    if not raw_other_config:
        return None
    try:
        payload = json.loads(raw_other_config)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    raw_runtime = payload.get(GLOBAL_YASA_RUNTIME_CONFIG_KEY)
    if not isinstance(raw_runtime, dict):
        return None
    try:
        return _normalize_runtime_config(raw_runtime)
    except ValueError:
        return None


async def load_global_yasa_runtime_config(db: AsyncSession) -> Dict[str, int]:
    stmt = select(UserConfig).order_by(desc(UserConfig.updated_at), desc(UserConfig.created_at))
    result = await db.execute(stmt)
    for record in result.scalars().all():
        parsed = _parse_runtime_config_from_user_config(record)
        if parsed is not None:
            return update_cached_global_yasa_runtime_config(parsed)
    defaults = _build_default_runtime_config()
    return update_cached_global_yasa_runtime_config(defaults)


async def save_global_yasa_runtime_config(
    db: AsyncSession,
    *,
    user_id: str,
    runtime_config: Dict[str, Any],
) -> Dict[str, int]:
    normalized = _normalize_runtime_config(runtime_config)
    result = await db.execute(select(UserConfig).where(UserConfig.user_id == user_id))
    user_config = result.scalar_one_or_none()
    if user_config is None:
        user_config = UserConfig(
            user_id=user_id,
            llm_config="{}",
            other_config=json.dumps({GLOBAL_YASA_RUNTIME_CONFIG_KEY: normalized}, ensure_ascii=False),
        )
        db.add(user_config)
    else:
        try:
            payload = json.loads(user_config.other_config or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload[GLOBAL_YASA_RUNTIME_CONFIG_KEY] = normalized
        user_config.other_config = json.dumps(payload, ensure_ascii=False)

    await db.commit()
    return update_cached_global_yasa_runtime_config(normalized)
