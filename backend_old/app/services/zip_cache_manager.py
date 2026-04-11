"""
ZIP文件内容缓存管理器
支持异步缓存、TTL过期、内存限制
"""
import json
import time
from typing import Optional, Dict, Any
from pathlib import Path
import hashlib
import asyncio
import logging

logger = logging.getLogger(__name__)

# 缓存配置常量
DEFAULT_CACHE_TTL = 3600  # 1小时
MAX_CACHE_SIZE = 100 * 1024 * 1024  # 100MB内存限制
MAX_CACHED_FILE_SIZE = 5 * 1024 * 1024  # 单个文件5MB上限


class FileCacheEntry:
    """文件缓存条目"""
    def __init__(self, content: str, size: int, encoding: str, is_text: bool, file_hash: str):
        self.content = content
        self.size = size
        self.encoding = encoding
        self.is_text = is_text
        self.file_hash = file_hash
        self.created_at = time.time()
        self.access_count = 0
        self.last_accessed = self.created_at
    
    def is_expired(self, ttl: int) -> bool:
        """检查缓存是否过期"""
        return time.time() - self.created_at > ttl
    
    def touch(self) -> None:
        """更新最后访问时间"""
        self.last_accessed = time.time()
        self.access_count += 1
    
    def get_memory_size(self) -> int:
        """计算缓存条目占用的内存大小"""
        return len(self.content.encode('utf-8')) + 200  # 200字节开销


class ZipCacheManager:
    """
    ZIP文件内容缓存管理器
    支持：
    - 内存缓存（LRU）
    - TTL自动过期
    - 内存使用限制
    - 缓存统计
    """
    
    def __init__(self, ttl: int = DEFAULT_CACHE_TTL, max_size: int = MAX_CACHE_SIZE):
        self.ttl = ttl
        self.max_size = max_size
        self.cache: Dict[str, FileCacheEntry] = {}
        self.lock = asyncio.Lock()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "total_memory": 0,
        }
    
    def _generate_cache_key(self, project_id: str, file_path: str, zip_hash: str) -> str:
        """生成缓存键"""
        key_str = f"{project_id}:{file_path}:{zip_hash}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _remove_entry_locked(self, cache_key: str) -> Optional[FileCacheEntry]:
        entry = self.cache.pop(cache_key, None)
        if entry is not None:
            self.stats["total_memory"] = max(
                0,
                self.stats["total_memory"] - entry.get_memory_size(),
            )
        return entry

    def _prune_expired_locked(self) -> int:
        expired_keys = [key for key, entry in self.cache.items() if entry.is_expired(self.ttl)]
        for cache_key in expired_keys:
            self._remove_entry_locked(cache_key)
        return len(expired_keys)

    def _sync_total_memory_locked(self) -> int:
        total_memory = sum(entry.get_memory_size() for entry in self.cache.values())
        self.stats["total_memory"] = total_memory
        return total_memory
    
    async def get(self, project_id: str, file_path: str, zip_hash: str) -> Optional[FileCacheEntry]:
        """
        从缓存获取文件内容
        
        Args:
            project_id: 项目ID
            file_path: 文件路径
            zip_hash: ZIP文件哈希（用于版本管理）
        
        Returns:
            缓存条目或None
        """
        async with self.lock:
            cache_key = self._generate_cache_key(project_id, file_path, zip_hash)

            entry = self.cache.get(cache_key)
            if entry is None:
                self.stats["misses"] += 1
                return None

            # 检查过期
            if entry.is_expired(self.ttl):
                self._remove_entry_locked(cache_key)
                self.stats["misses"] += 1
                logger.info(f"缓存过期: {cache_key}")
                return None

            # 更新访问信息
            entry.touch()
            self.stats["hits"] += 1
            return entry
    
    async def set(
        self,
        project_id: str,
        file_path: str,
        zip_hash: str,
        content: str,
        size: int,
        encoding: str,
        is_text: bool,
    ) -> bool:
        """
        设置缓存
        
        Args:
            project_id: 项目ID
            file_path: 文件路径
            zip_hash: ZIP文件哈希
            content: 文件内容
            size: 文件大小（字节）
            encoding: 编码方式
            is_text: 是否为文本文件
        
        Returns:
            是否缓存成功
        """
        # 大文件不缓存
        if size > MAX_CACHED_FILE_SIZE:
            logger.debug(f"文件过大({size}字节)，不缓存: {file_path}")
            return False
        
        async with self.lock:
            cache_key = self._generate_cache_key(project_id, file_path, zip_hash)
            pruned = self._prune_expired_locked()
            if pruned > 0:
                logger.info(f"已主动清理 {pruned} 个过期 ZIP 缓存条目")

            self._remove_entry_locked(cache_key)

            # 创建缓存条目
            entry = FileCacheEntry(content, size, encoding, is_text, zip_hash)
            entry_size = entry.get_memory_size()

            # 检查内存限制
            new_total = self.stats["total_memory"] + entry_size

            # 需要清理时LRU删除
            while new_total > self.max_size and self.cache:
                removed_key = self._evict_lru()
                if removed_key:
                    removed_entry = self._remove_entry_locked(removed_key)
                    if removed_entry:
                        new_total = self.stats["total_memory"] + entry_size
                        self.stats["evictions"] += 1
                else:
                    break

            # 如果still超过限制，不缓存
            if new_total > self.max_size:
                logger.warning(f"缓存满，无法缓存文件: {file_path}")
                return False

            self.cache[cache_key] = entry
            self.stats["total_memory"] += entry_size
            logger.debug(f"缓存文件: {file_path} (大小: {entry_size}字节)")
            return True
    
    def _evict_lru(self) -> Optional[str]:
        """驱逐LRU条目（最少使用的）"""
        if not self.cache:
            return None
        
        # 找到最少访问且最久未使用的条目
        lru_key = min(
            self.cache.keys(),
            key=lambda k: (
                self.cache[k].access_count,
                self.cache[k].last_accessed,
            )
        )
        return lru_key
    
    async def invalidate(self, project_id: str, zip_hash: str) -> int:
        """
        使项目的所有缓存失效（ZIP文件更新时）
        
        Returns:
            删除的缓存条目数
        """
        async with self.lock:
            keys_to_delete = [
                k for k, v in self.cache.items()
                if v.file_hash == zip_hash
            ]

            deleted_count = 0
            for key in keys_to_delete:
                entry = self._remove_entry_locked(key)
                if entry:
                    deleted_count += 1

            if deleted_count > 0:
                logger.info(f"已清除 {deleted_count} 个缓存条目")

            return deleted_count

    async def prune_expired(self) -> int:
        """主动清理过期缓存条目。"""
        async with self.lock:
            removed = self._prune_expired_locked()
            if removed > 0:
                logger.info(f"已主动清理 {removed} 个过期 ZIP 缓存条目")
            self._sync_total_memory_locked()
            return removed
    
    async def clear_all(self) -> None:
        """清空所有缓存"""
        async with self.lock:
            self.cache.clear()
            self.stats["total_memory"] = 0
            logger.info("已清空所有缓存")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total_memory = sum(entry.get_memory_size() for entry in self.cache.values())
        self.stats["total_memory"] = total_memory
        total_entries = len(self.cache)
        hit_rate = (
            self.stats["hits"] / (self.stats["hits"] + self.stats["misses"])
            if (self.stats["hits"] + self.stats["misses"]) > 0
            else 0
        )
        
        return {
            "total_entries": total_entries,
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "hit_rate": f"{hit_rate * 100:.1f}%",
            "evictions": self.stats["evictions"],
            "memory_used_mb": total_memory / 1024 / 1024,
            "memory_limit_mb": self.max_size / 1024 / 1024,
        }


# 全局缓存实例
_zip_cache_manager: Optional[ZipCacheManager] = None


def get_zip_cache_manager() -> ZipCacheManager:
    """获取全局缓存管理器实例"""
    global _zip_cache_manager
    if _zip_cache_manager is None:
        _zip_cache_manager = ZipCacheManager()
    return _zip_cache_manager


def init_zip_cache_manager(ttl: int = DEFAULT_CACHE_TTL, max_size: int = MAX_CACHE_SIZE) -> ZipCacheManager:
    """初始化缓存管理器"""
    global _zip_cache_manager
    _zip_cache_manager = ZipCacheManager(ttl=ttl, max_size=max_size)
    return _zip_cache_manager
