"""
全局 Git 项目缓存管理器

维护 repo_owner/repo_name 到 git 克隆目录的映射，
避免重复克隆，支持多个 patch 文件共享同一个项目缓存。
"""

import os
import json
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Set
from threading import Lock

logger = logging.getLogger(__name__)


class RepoCache:
    """表示一个项目的缓存信息"""
    
    def __init__(self, repo_owner: str, repo_name: str, cache_dir: Path):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.cache_dir = cache_dir  # git克隆所在的目录
        self.created_at = datetime.now().isoformat()
        self.last_accessed = self.created_at
        self.access_count = 0
    
    def touch(self):
        """更新最后访问时间和访问计数"""
        self.last_accessed = datetime.now().isoformat()
        self.access_count += 1
    
    def to_dict(self) -> Dict:
        """转换为字典用于存储"""
        return {
            "repo_owner": self.repo_owner,
            "repo_name": self.repo_name,
            "cache_dir": str(self.cache_dir),
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
        }


class GlobalRepoCacheManager:
    """
    全局 Git 项目缓存管理器
    
    维护 repo_owner/repo_name 到 git 克隆目录的对应关系，
    支持多个处理任务共享同一个项目缓存。
    """
    
    # 类级别的缓存映射
    _cache: Dict[str, RepoCache] = {}
    _lock = Lock()
    _metadata_file: Optional[Path] = None
    
    @classmethod
    def set_cache_dir(cls, cache_dir: Path):
        """设置全局缓存目录"""
        cache_dir.mkdir(parents=True, exist_ok=True)
        cls._metadata_file = cache_dir / "repo_cache_metadata.json"
        cls._load_metadata()
    
    @classmethod
    def _load_metadata(cls):
        """从磁盘加载缓存元数据"""
        if not cls._metadata_file or not cls._metadata_file.exists():
            return
        
        try:
            with open(cls._metadata_file, 'r') as f:
                data = json.load(f)
                cls._cache.clear()
                for key, item in data.items():
                    cache_dir = Path(item["cache_dir"])
                    if cache_dir.exists():
                        cache = RepoCache(
                            item["repo_owner"],
                            item["repo_name"],
                            cache_dir
                        )
                        cache.created_at = item.get("created_at", cache.created_at)
                        cache.last_accessed = item.get("last_accessed", cache.last_accessed)
                        cache.access_count = item.get("access_count", 0)
                        cls._cache[key] = cache
                logger.info(f"已加载 {len(cls._cache)} 个缓存项目")
        except Exception as e:
            logger.error(f"加载缓存元数据失败: {e}")
    
    @classmethod
    def _save_metadata(cls):
        """保存缓存元数据到磁盘"""
        if not cls._metadata_file:
            return
        
        try:
            metadata = {
                f"{cache.repo_owner}/{cache.repo_name}": cache.to_dict()
                for cache in cls._cache.values()
            }
            with open(cls._metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"保存缓存元数据失败: {e}")
    
    @classmethod
    def get_repo_cache(cls, repo_owner: str, repo_name: str) -> Optional[Path]:
        """
        获取项目的缓存目录
        
        如果存在且有效，返回缓存目录；否则返回 None
        """
        with cls._lock:
            key = f"{repo_owner}/{repo_name}"
            cache = cls._cache.get(key)
            
            if cache and cache.cache_dir.exists():
                cache.touch()
                cls._save_metadata()
                logger.info(f"使用缓存项目: {key} -> {cache.cache_dir}")
                return cache.cache_dir
            
            # 如果缓存不存在了，移除记录
            if key in cls._cache:
                del cls._cache[key]
                cls._save_metadata()
            
            return None
    
    @classmethod
    def register_repo_cache(cls, repo_owner: str, repo_name: str, cache_dir: Path):
        """
        注册一个项目的缓存目录
        
        Args:
            repo_owner: 项目所有者
            repo_name: 项目名称
            cache_dir: git 克隆目录路径
        """
        with cls._lock:
            key = f"{repo_owner}/{repo_name}"
            cache = RepoCache(repo_owner, repo_name, cache_dir)
            cls._cache[key] = cache
            cls._save_metadata()
            logger.info(f"注册缓存项目: {key} -> {cache_dir}")

    @classmethod
    def remove_repo_cache(cls, repo_owner: str, repo_name: str) -> bool:
        """
        删除指定项目的缓存目录并移除缓存记录

        Returns:
            True 表示删除成功或缓存不存在；False 表示删除失败
        """
        with cls._lock:
            key = f"{repo_owner}/{repo_name}"
            cache = cls._cache.get(key)

            if not cache:
                return True

            try:
                if cache.cache_dir.exists():
                    shutil.rmtree(cache.cache_dir, ignore_errors=True)
                    logger.info(f"已删除缓存: {cache.cache_dir}")
                del cls._cache[key]
                cls._save_metadata()
                return True
            except Exception as e:
                logger.error(f"删除缓存失败 {key}: {e}")
                return False
    
    @classmethod
    def get_all_cached_repos(cls) -> Dict[str, RepoCache]:
        """获取所有缓存的项目"""
        with cls._lock:
            return dict(cls._cache)
    
    @classmethod
    def cleanup_unused_caches(cls, max_age_days: int = 30, max_unused_days: int = 14):
        """
        清理未使用的缓存
        
        删除超过指定天数未访问的缓存或总存在时间太长的缓存
        
        Args:
            max_age_days: 缓存最大存在天数（默认30天）
            max_unused_days: 缓存最大未访问天数（默认14天）
        """
        with cls._lock:
            now = datetime.now()
            keys_to_remove = []
            
            for key, cache in cls._cache.items():
                created_at = datetime.fromisoformat(cache.created_at)
                last_accessed = datetime.fromisoformat(cache.last_accessed)
                
                age = (now - created_at).days
                unused = (now - last_accessed).days
                
                # 检查是否需要清理
                if age > max_age_days or unused > max_unused_days:
                    keys_to_remove.append((key, cache.cache_dir))
            
            for key, cache_dir in keys_to_remove:
                try:
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    del cls._cache[key]
                    logger.info(f"已清理过期缓存: {key} ({cache_dir})")
                except Exception as e:
                    logger.error(f"清理缓存失败 {key}: {e}")
            
            if keys_to_remove:
                cls._save_metadata()
            
            return len(keys_to_remove)
    
    @classmethod
    def clear_all_caches(cls):
        """清理所有缓存"""
        with cls._lock:
            for cache in cls._cache.values():
                try:
                    shutil.rmtree(cache.cache_dir, ignore_errors=True)
                    logger.info(f"已删除缓存: {cache.cache_dir}")
                except Exception as e:
                    logger.error(f"删除缓存失败: {e}")
            
            cls._cache.clear()
            cls._save_metadata()
    
    @classmethod
    def get_cache_size(cls) -> Dict[str, any]:
        """获取缓存大小统计"""
        with cls._lock:
            total_dirs = len(cls._cache)
            total_size = 0
            
            for cache in cls._cache.values():
                if cache.cache_dir.exists():
                    total_size += sum(
                        f.stat().st_size 
                        for f in cache.cache_dir.rglob('*') 
                        if f.is_file()
                    )
            
            return {
                "total_cached_repos": total_dirs,
                "total_size_bytes": total_size,
                "total_size_gb": round(total_size / (1024**3), 2),
            }
