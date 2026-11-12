"""文件搜索和目录查询共用稳定排序。"""

from .models import File
from .session import NATURAL_COLLATION

SORT_COLUMNS = {"name": File.name, "size": File.size, "modified_at": File.modified_at,
                "duration": File.duration, "type": File.type, "updated_at": File.updated_at}


def file_order(sort_by: str | None, descending: bool = False) -> list:
    """生成白名单排序，未知时长置末并以 ID 稳定同值次序。

    Args:
        sort_by: 排序字段。
        descending: 是否降序。

    Returns:
        SQLAlchemy 排序表达式列表。
    """
    column = SORT_COLUMNS.get(sort_by, File.name)
    order = column.collate(NATURAL_COLLATION) if column is File.name or column is File.type else column
    result = [column.is_(None).asc()] if column is File.duration else []
    return [*result, order.desc() if descending else order.asc(), File.id.asc()]
