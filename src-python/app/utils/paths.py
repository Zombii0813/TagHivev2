"""文件系统与 SQL 共用的路径边界规则。"""

import os
from pathlib import Path


def normalized_path(value: str | Path) -> str:
    """规范化路径，用于边界比较。

    Args:
        value: 文件或目录路径。
    """
    return os.path.normcase(os.path.abspath(value)).replace("\\", "/").rstrip("/")


def is_within(path: str | Path, root: str | Path) -> bool:
    """判断路径等于根目录或位于其子树内。"""
    path_value, root_value = normalized_path(path), normalized_path(root)
    return path_value == root_value or path_value.startswith(root_value + "/")


def path_prefix(column, root: str | Path, include_self: bool = False):
    """构造转义 SQL 通配符后的目录子树条件。"""
    prefix = Path(root).as_posix().rstrip("/")
    escaped = prefix.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    clause = column.like(escaped + "/%", escape="!")
    return (clause | (column == prefix)) if include_self else clause
