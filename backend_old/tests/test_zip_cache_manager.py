import pytest

from app.services.zip_cache_manager import ZipCacheManager


@pytest.mark.asyncio
async def test_prune_expired_removes_stale_entries_and_updates_stats():
    manager = ZipCacheManager(ttl=60, max_size=1024 * 1024)
    await manager.set(
        "project-1",
        "src/app.py",
        "zip-hash",
        "print('ok')\n",
        size=12,
        encoding="utf-8",
        is_text=True,
    )

    key = next(iter(manager.cache))
    manager.cache[key].created_at -= 120
    manager.cache[key].last_accessed -= 120

    removed = await manager.prune_expired()
    stats = manager.get_stats()

    assert removed == 1
    assert manager.cache == {}
    assert stats["total_entries"] == 0
    assert stats["memory_used_mb"] == 0


@pytest.mark.asyncio
async def test_get_drops_expired_entry_and_syncs_total_memory():
    manager = ZipCacheManager(ttl=60, max_size=1024 * 1024)
    await manager.set(
        "project-1",
        "src/app.py",
        "zip-hash",
        "print('ok')\n",
        size=12,
        encoding="utf-8",
        is_text=True,
    )

    key = next(iter(manager.cache))
    manager.cache[key].created_at -= 120
    manager.cache[key].last_accessed -= 120

    cached = await manager.get("project-1", "src/app.py", "zip-hash")
    stats = manager.get_stats()

    assert cached is None
    assert key not in manager.cache
    assert stats["total_entries"] == 0
    assert stats["memory_used_mb"] == 0
