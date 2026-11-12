from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SearchQuery:
    """搜索查询对象 - 支持多种搜索条件组合

    Attributes:
        text: 文件名的字面子串，百分号和下划线不解释为通配符
        root: 限制搜索路径前缀
        types: 文件类型元组，如 ('image', 'video')
        tags: 标签 ID 元组，如 (1, 2, 3)
        match_all_tags: 是否要求匹配所有标签（默认 OR）
        sort_by: 排序字段 ('name', 'size', 'type', 'created_at', 'updated_at', 'modified_at')
        sort_desc: 是否降序
        use_fts: 是否使用 trigram 索引加速长词子串搜索（语义保持一致）
    """
    text: str | None = None
    root: str | None = None
    roots: tuple[str, ...] | None = None
    types: tuple[str, ...] = ()
    tags: tuple[int, ...] = ()
    match_all_tags: bool = False
    sort_by: str | None = None
    sort_desc: bool = False
    use_fts: bool = True  # 默认启用 FTS5


@dataclass(frozen=True)
class SearchResult:
    """搜索结果对象"""
    file_id: int
    path: str
    name: str
    type: str


def empty_results() -> Iterable[SearchResult]:
    """返回空结果迭代器"""
    return []
