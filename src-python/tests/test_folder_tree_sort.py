"""文件夹树排序测试

验证 _build_folder_tree 的子目录顺序遵循 Windows 资源管理器规则：
数字段按数值大小排序（1,2,...,10），符号权重与资源管理器一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.api.routes import _build_folder_tree
from app.db import Repo


def _mkdirs(root: Path, names: list[str]) -> None:
    """在磁盘上创建若干子目录"""
    for name in names:
        (root / name).mkdir(parents=True, exist_ok=True)


def test_folder_tree_digits_sorted_numerically(repo: Repo, tmp_path: Path):
    """纯数字与前缀+数字目录均按数值排序，而非字典序"""
    root = tmp_path / "ws"
    root.mkdir()
    _mkdirs(root, ["10", "2", "1", "11", "20", "3"])

    children, _ = _build_folder_tree(str(root), repo)
    names = [c.name for c in children]
    assert names == ["1", "2", "3", "10", "11", "20"]


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="符号权重依赖 Windows StrCmpLogicalW，仅在 Windows 上校验",
)
def test_folder_tree_symbols_like_explorer(repo: Repo, tmp_path: Path):
    """符号目录顺序与资源管理器一致：括号/下划线在数字前，连字符开头在字母后"""
    root = tmp_path / "ws"
    root.mkdir()
    _mkdirs(root, ["10", "2", "1", "(a)", "_c", "abc", "-b"])

    children, _ = _build_folder_tree(str(root), repo)
    names = [c.name for c in children]
    assert names == ["(a)", "_c", "1", "2", "10", "abc", "-b"]
