"""查询结果缓存层 - 缓存频繁查询的数据

提供内存缓存机制，用于缓存标签列表、文件夹树等相对静态的数据，
减少数据库查询次数，提升响应速度。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """缓存条目"""
    value: T
    timestamp: float
    ttl: int  # 过期时间（秒）

    def is_expired(self) -> bool:
        """检查缓存是否过期"""
        return time.time() - self.timestamp > self.ttl


@dataclass
class CacheStats:
    """缓存统计信息"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    size: int = 0

    @property
    def hit_rate(self) -> float:
        """缓存命中率"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


class QueryCache:
    """查询结果缓存管理器

    支持：
    - 基于键的缓存存储和检索
    - TTL（生存时间）自动过期
    - 最大容量限制和LRU淘汰
    - 缓存统计信息
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,  # 默认5分钟
    ):
        """初始化缓存

        Args:
            max_size: 最大缓存条目数
            default_ttl: 默认过期时间（秒）
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._stats = CacheStats()

    def _generate_key(self, *args, **kwargs) -> str:
        """生成缓存键"""
        key_data = {
            "args": args,
            "kwargs": kwargs,
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，如果不存在或已过期则返回 None
        """
        entry = self._cache.get(key)
        if entry is None:
            self._stats.misses += 1
            return None

        if entry.is_expired():
            del self._cache[key]
            self._stats.misses += 1
            self._stats.size = len(self._cache)
            return None

        self._stats.hits += 1
        return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None则使用默认值
        """
        # 如果缓存已满，移除最旧的条目
        if len(self._cache) >= self._max_size and key not in self._cache:
            self._evict_oldest()

        self._cache[key] = CacheEntry(
            value=value,
            timestamp=time.time(),
            ttl=ttl or self._default_ttl,
        )
        self._stats.size = len(self._cache)

    def _evict_oldest(self) -> None:
        """淘汰最旧的缓存条目"""
        if not self._cache:
            return

        oldest_key = min(
            self._cache.items(),
            key=lambda x: x[1].timestamp,
        )[0]
        del self._cache[oldest_key]
        self._stats.evictions += 1

    def invalidate(self, key: str) -> bool:
        """使指定缓存失效

        Args:
            key: 缓存键

        Returns:
            是否成功移除
        """
        if key in self._cache:
            del self._cache[key]
            self._stats.size = len(self._cache)
            return True
        return False

    def invalidate_pattern(self, pattern: str) -> int:
        """使匹配模式的缓存失效

        Args:
            pattern: 键匹配模式（简单子字符串匹配）

        Returns:
            移除的条目数
        """
        keys_to_remove = [k for k in self._cache.keys() if pattern in k]
        for key in keys_to_remove:
            del self._cache[key]
        self._stats.size = len(self._cache)
        return len(keys_to_remove)

    def clear(self) -> None:
        """清空所有缓存"""
        self._cache.clear()
        self._stats.size = 0

    def get_stats(self) -> CacheStats:
        """获取缓存统计信息"""
        self._stats.size = len(self._cache)
        return self._stats

    def cached(
        self,
        ttl: Optional[int] = None,
        key_prefix: str = "",
    ) -> Callable:
        """装饰器 - 缓存函数结果

        Args:
            ttl: 过期时间（秒）
            key_prefix: 缓存键前缀

        Returns:
            装饰器函数
        """
        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                # 生成缓存键
                cache_key = f"{key_prefix}:{self._generate_key(*args, **kwargs)}"

                # 尝试从缓存获取
                cached_value = self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # 执行函数并缓存结果
                result = func(*args, **kwargs)
                self.set(cache_key, result, ttl)
                return result

            # 添加清除缓存的方法
            wrapper.cache_invalidate = lambda *args, **kwargs: self.invalidate(
                f"{key_prefix}:{self._generate_key(*args, **kwargs)}"
            )
            wrapper.cache_clear = self.clear

            return wrapper
        return decorator


# 全局缓存实例
_query_cache: Optional[QueryCache] = None


def get_query_cache() -> QueryCache:
    """获取全局查询缓存实例"""
    global _query_cache
    if _query_cache is None:
        _query_cache = QueryCache()
    return _query_cache


def init_query_cache(max_size: int = 1000, default_ttl: int = 300) -> QueryCache:
    """初始化查询缓存

    Args:
        max_size: 最大缓存条目数
        default_ttl: 默认过期时间（秒）

    Returns:
        QueryCache 实例
    """
    global _query_cache
    _query_cache = QueryCache(max_size=max_size, default_ttl=default_ttl)
    return _query_cache
