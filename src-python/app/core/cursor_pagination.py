"""游标分页 - 高性能分页实现

使用游标（Cursor）替代 OFFSET 分页，避免大数据量时的深度分页性能问题。
游标分页通过记录上一页最后一条数据的排序值，实现 O(1) 的高效分页。
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

from sqlalchemy import Column, desc, asc
from sqlalchemy.orm import Query

T = TypeVar("T")


@dataclass
class CursorPage(Generic[T]):
    """游标分页结果"""
    items: List[T]
    next_cursor: Optional[str] = None
    prev_cursor: Optional[str] = None
    has_more: bool = False
    total: Optional[int] = None  # 可选的总数


@dataclass
class Cursor:
    """游标数据"""
    values: Dict[str, Any]  # 排序字段的值
    direction: str = "next"  # 'next' 或 'prev'

    def encode(self) -> str:
        """编码为字符串"""
        data = {
            "v": self.values,
            "d": self.direction,
        }
        json_str = json.dumps(data, sort_keys=True, default=str)
        return base64.urlsafe_b64encode(json_str.encode()).decode().rstrip("=")

    @classmethod
    def decode(cls, cursor_str: str) -> "Cursor":
        """从字符串解码"""
        # 添加填充
        padding = 4 - len(cursor_str) % 4
        if padding != 4:
            cursor_str += "=" * padding

        json_str = base64.urlsafe_b64decode(cursor_str.encode()).decode()
        data = json.loads(json_str)
        return cls(values=data["v"], direction=data.get("d", "next"))


class CursorPaginator(Generic[T]):
    """游标分页器

    支持：
    - 基于排序字段的游标分页
    - 支持多字段排序
    - 支持前后翻页
    - 自动编码/解码游标
    """

    def __init__(
        self,
        query: Query,
        sort_columns: List[Column],
        sort_desc: bool = False,
        page_size: int = 50,
    ):
        """初始化游标分页器

        Args:
            query: SQLAlchemy 查询对象
            sort_columns: 排序字段列表
            sort_desc: 是否降序排序
            page_size: 每页大小
        """
        self._query = query
        self._sort_columns = sort_columns
        self._sort_desc = sort_desc
        self._page_size = page_size

    def _apply_cursor_filter(
        self,
        query: Query,
        cursor: Cursor,
    ) -> Query:
        """应用游标过滤条件"""
        if not cursor.values:
            return query

        # 构建复合过滤条件
        conditions = []
        for i, col in enumerate(self._sort_columns):
            col_name = col.name
            if col_name not in cursor.values:
                continue

            cursor_value = cursor.values[col_name]

            # 根据方向确定比较操作符
            if cursor.direction == "next":
                # 下一页：获取排序值更大的记录
                if self._sort_desc:
                    conditions.append(col < cursor_value)
                else:
                    conditions.append(col > cursor_value)
            else:
                # 上一页：获取排序值更小的记录
                if self._sort_desc:
                    conditions.append(col > cursor_value)
                else:
                    conditions.append(col < cursor_value)

        if conditions:
            from sqlalchemy import and_
            query = query.filter(and_(*conditions))

        return query

    def get_page(
        self,
        cursor_str: Optional[str] = None,
        mapper: Optional[Callable[[Any], T]] = None,
    ) -> CursorPage[T]:
        """获取分页结果

        Args:
            cursor_str: 游标字符串，None表示第一页
            mapper: 结果映射函数

        Returns:
            CursorPage 分页结果
        """
        cursor = None
        if cursor_str:
            try:
                cursor = Cursor.decode(cursor_str)
            except Exception:
                # 游标解码失败，返回第一页
                cursor = None

        # 应用游标过滤
        query = self._query
        if cursor:
            query = self._apply_cursor_filter(query, cursor)

        # 应用排序
        for col in self._sort_columns:
            if self._sort_desc:
                query = query.order_by(desc(col))
            else:
                query = query.order_by(asc(col))

        # 获取多一条数据用于判断是否有更多
        results = query.limit(self._page_size + 1).all()

        # 判断是否有更多数据
        has_more = len(results) > self._page_size
        if has_more:
            results = results[:self._page_size]

        # 应用映射函数
        if mapper:
            items = [mapper(r) for r in results]
        else:
            items = list(results)

        # 生成游标
        next_cursor = None
        prev_cursor = None

        if items:
            # 生成下一页游标
            if has_more:
                last_item = results[-1]
                next_values = {}
                for col in self._sort_columns:
                    next_values[col.name] = getattr(last_item, col.name)
                next_cursor = Cursor(values=next_values, direction="next").encode()

            # 生成上一页游标（如果不是第一页）
            if cursor:
                first_item = results[0]
                prev_values = {}
                for col in self._sort_columns:
                    prev_values[col.name] = getattr(first_item, col.name)
                prev_cursor = Cursor(values=prev_values, direction="prev").encode()

        return CursorPage(
            items=items,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            has_more=has_more,
        )


def paginate_with_cursor(
    query: Query,
    sort_by: Column,
    cursor: Optional[str] = None,
    page_size: int = 50,
    sort_desc: bool = False,
    mapper: Optional[Callable[[Any], T]] = None,
) -> CursorPage[T]:
    """游标分页快捷函数

    Args:
        query: SQLAlchemy 查询对象
        sort_by: 排序字段
        cursor: 游标字符串
        page_size: 每页大小
        sort_desc: 是否降序
        mapper: 结果映射函数

    Returns:
        CursorPage 分页结果
    """
    paginator = CursorPaginator(
        query=query,
        sort_columns=[sort_by],
        sort_desc=sort_desc,
        page_size=page_size,
    )
    return paginator.get_page(cursor, mapper)


@dataclass
class OffsetPage(Generic[T]):
    """传统 OFFSET 分页结果（用于小数据量场景）"""
    items: List[T]
    offset: int
    limit: int
    total: Optional[int] = None
    has_more: bool = False


class OffsetPaginator(Generic[T]):
    """传统 OFFSET 分页器（小数据量场景使用）"""

    def __init__(
        self,
        query: Query,
        offset: int = 0,
        limit: int = 50,
    ):
        """初始化分页器

        Args:
            query: SQLAlchemy 查询对象
            offset: 偏移量
            limit: 每页大小
        """
        self._query = query
        self._offset = offset
        self._limit = limit

    def get_page(
        self,
        mapper: Optional[Callable[[Any], T]] = None,
    ) -> OffsetPage[T]:
        """获取分页结果"""
        # 获取总数（可选，如果性能敏感可以跳过）
        total = None
        if self._offset == 0:  # 只在第一页计算总数
            total = self._query.count()

        # 应用分页
        results = self._query.offset(self._offset).limit(self._limit + 1).all()

        # 判断是否有更多
        has_more = len(results) > self._limit
        if has_more:
            results = results[:self._limit]

        # 应用映射
        if mapper:
            items = [mapper(r) for r in results]
        else:
            items = list(results)

        return OffsetPage(
            items=items,
            offset=self._offset,
            limit=self._limit,
            total=total,
            has_more=has_more,
        )


def paginate_with_offset(
    query: Query,
    offset: int = 0,
    limit: int = 50,
    mapper: Optional[Callable[[Any], T]] = None,
) -> OffsetPage[T]:
    """OFFSET 分页快捷函数（小数据量场景）"""
    paginator = OffsetPaginator(
        query=query,
        offset=offset,
        limit=limit,
    )
    return paginator.get_page(mapper)
