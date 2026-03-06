from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Any, List
import hashlib
import time

from .search import SearchQuery, SearchResult


@dataclass(frozen=True)
class CacheKey:
    """缓存键 - 用于唯一标识搜索查询"""
    text: Optional[str]
    root: Optional[str]
    types: tuple[str, ...]
    tags: tuple[str, ...]
    match_all_tags: bool
    sort_by: Optional[str]
    sort_desc: bool
    use_fts: bool

    def __str__(self) -> str:
        """生成缓存键的字符串表示"""
        parts = [
            self.text or "",
            self.root or "",
            ",".join(self.types),
            ",".join(str(self.tags)),
            str(self.match_all_tags),
            self.sort_by or "",
            str(self.sort_desc),
            str(self.use_fts),
        ]
        return "|".join(parts)

    def to_hash(self) -> str:
        """生成缓存键的哈希值"""
        return hashlib.md5(str(self).encode()).hexdigest()


@dataclass
class CachedResult:
    """缓存的搜索结果"""
    results: List[SearchResult]
    timestamp: float
    expiration: float = 3600  # 默认过期时间：1小时

    def is_expired(self) -> bool:
        """检查缓存是否过期"""
        return time.time() - self.timestamp > self.expiration


class SearchCache:
    """搜索结果缓存"""

    def __init__(self, max_size: int = 100):
        """初始化缓存
        
        Args:
            max_size: 缓存最大容量
        """
        self._cache: Dict[str, CachedResult] = {}
        self._max_size = max_size

    def get(self, query: SearchQuery) -> Optional[List[SearchResult]]:
        """获取缓存的搜索结果
        
        Args:
            query: 搜索查询
            
        Returns:
            缓存的搜索结果，如果没有缓存或缓存过期则返回None
        """
        key = CacheKey(
            text=query.text,
            root=query.root,
            types=query.types,
            tags=query.tags,
            match_all_tags=query.match_all_tags,
            sort_by=query.sort_by,
            sort_desc=query.sort_desc,
            use_fts=query.use_fts,
        )
        cache_key = key.to_hash()
        
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            if not cached.is_expired():
                return cached.results
            else:
                # 移除过期缓存
                del self._cache[cache_key]
        
        return None

    def set(self, query: SearchQuery, results: List[SearchResult]) -> None:
        """设置缓存的搜索结果
        
        Args:
            query: 搜索查询
            results: 搜索结果
        """
        key = CacheKey(
            text=query.text,
            root=query.root,
            types=query.types,
            tags=query.tags,
            match_all_tags=query.match_all_tags,
            sort_by=query.sort_by,
            sort_desc=query.sort_desc,
            use_fts=query.use_fts,
        )
        cache_key = key.to_hash()
        
        # 如果缓存已满，移除最旧的缓存
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache.items(), key=lambda x: x[1].timestamp)[0]
            del self._cache[oldest_key]
        
        # 添加新缓存
        self._cache[cache_key] = CachedResult(
            results=results,
            timestamp=time.time(),
        )

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()

    def size(self) -> int:
        """获取缓存大小"""
        return len(self._cache)
