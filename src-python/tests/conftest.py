"""pytest 通用 fixtures

为每个测试函数创建一份隔离的 SQLite 数据库，自动清理。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest

# 让 src-python 根成为 import 根
import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import session as db_session
from app.db import Repo
from app.db.session import init_db, get_session
from app.db.models import File, Tag, FileTag


@pytest.fixture
def tmp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """为每个测试创建独立 SQLite 文件，并重置全局引擎。

    返回数据库文件路径。测试结束自动清理（pytest tmp_path）。
    """
    # 关键：重置 session 模块的全局引擎，避免上次测试的连接复用
    db_session._engine = None
    db_session._engine_path = None

    db_path = tmp_path / "test.db"
    init_db(db_path)
    yield db_path

    # 显式断开连接，方便 Windows 删除文件
    if db_session._engine is not None:
        db_session._engine.dispose()
    db_session._engine = None
    db_session._engine_path = None


@pytest.fixture
def repo(tmp_db: Path) -> Generator[Repo, None, None]:
    """提供绑定到临时数据库的 Repo 实例。"""
    session = get_session()
    try:
        yield Repo(session)
    finally:
        session.close()


def make_meta(path: str, name: str | None = None, type_: str = "image", size: int = 1024):
    """构造一个 FileMeta 用于测试，避免依赖真实磁盘文件。"""
    from pathlib import Path as P
    from app.core.indexer import FileMeta
    p = P(path)
    return FileMeta(
        path=p,
        name=name or p.name,
        ext=p.suffix.lstrip(".").lower() or None,
        size=size,
        type=type_,
        sha256=None,
        modified_at=1700000000.0,
    )
