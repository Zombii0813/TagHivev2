from __future__ import annotations

import functools
import re
import sys
from pathlib import Path
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

Base = declarative_base()
SessionLocal = sessionmaker(autoflush=False, autocommit=False)
_engine = None
_engine_path: Path | None = None

# 自然排序（natural sort）用的排序规则名称。
# SQLite 默认按字符串码点比较，导致 "10" 排在 "2" 前面；
# 该 collation 让文件名按 Windows 资源管理器的规则排序（符号 < 数字 < 字母，
# 且数字段按数值大小比较），实现 1,2,...,10,11 的直觉顺序。
NATURAL_COLLATION = "NATURAL"

# 拆分「连续数字」与「非数字」片段，供跨平台回退的自然排序键使用
_NATURAL_SPLIT_RE = re.compile(r"(\d+)")

# Windows 平台优先复用资源管理器同款排序函数 StrCmpLogicalW，
# 保证符号、数字、字母的相对顺序与文件管理器完全一致。
_STRCMPLOGICAL = None
if sys.platform == "win32":
    try:
        import ctypes
        from ctypes import wintypes

        _fn = ctypes.windll.shlwapi.StrCmpLogicalW
        _fn.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        _fn.restype = ctypes.c_int
        _STRCMPLOGICAL = _fn
    except Exception:  # pragma: no cover - 极端环境下 shlwapi 不可用时回退
        _STRCMPLOGICAL = None


def _natural_sort_key(value: str) -> list:
    """生成跨平台自然排序键：数字段转整数比较，其余按小写字符串比较

    仅在非 Windows（无 StrCmpLogicalW）时作为回退使用。
    例如 "img12.png" -> ["img", 12, ".png"]，使数字段按数值而非字典序排序。
    """
    parts = _NATURAL_SPLIT_RE.split(value or "")
    # 偶数索引为非数字片段（大小写不敏感），奇数索引为数字片段（转 int）
    return [
        int(part) if index % 2 == 1 else part.lower()
        for index, part in enumerate(parts)
    ]


def _natural_collation(a: str, b: str) -> int:
    """SQLite 自定义排序规则：按自然顺序比较两个字符串

    Windows 上直接委托给 StrCmpLogicalW（资源管理器同款）；其余平台走
    Python 分段回退。返回 -1 / 0 / 1，供 ORDER BY ... COLLATE NATURAL 调用。
    """
    if _STRCMPLOGICAL is not None:
        return _STRCMPLOGICAL(a or "", b or "")

    ka, kb = _natural_sort_key(a), _natural_sort_key(b)
    # list 之间可能因元素类型（int vs str）不同而无法直接比较，
    # 逐段比较并对类型不一致的段回退到字符串比较，避免 TypeError。
    for xa, xb in zip(ka, kb):
        if type(xa) is not type(xb):
            xa, xb = str(xa), str(xb)
        if xa < xb:
            return -1
        if xa > xb:
            return 1
    if len(ka) < len(kb):
        return -1
    if len(ka) > len(kb):
        return 1
    return 0


# 供 Python 端排序（如目录树）复用的 key，与 SQL 层 collation 行为一致
natural_sort_key = functools.cmp_to_key(_natural_collation)


def _register_natural_collation(engine) -> None:
    """在每个新建的 SQLite 连接上注册自然排序 collation

    连接池会复用/新建连接，需在 connect 事件上注册，确保池中每条
    DBAPI 连接都可用 COLLATE NATURAL。
    """

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _connection_record):  # noqa: ANN001
        dbapi_conn.create_collation(NATURAL_COLLATION, _natural_collation)
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        dbapi_conn.execute("PRAGMA busy_timeout=30000")
        dbapi_conn.execute("PRAGMA synchronous=NORMAL")

# 连接池配置常量
POOL_SIZE = 5              # 连接池保持的连接数
MAX_OVERFLOW = 10          # 连接池最大溢出连接数
POOL_TIMEOUT = 30          # 获取连接超时时间（秒）
POOL_RECYCLE = 3600        # 连接回收时间（秒），防止连接过期
BATCH_SIZE = 500           # 批量操作默认批次大小


def init_db(db_path: Path) -> None:
    """初始化数据库连接和表结构
    
    Args:
        db_path: SQLite 数据库文件路径
    """
    global _engine, _engine_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    if _engine is None or _engine_path != db_path:
        from . import models
        # 创建带连接池的引擎
        # 使用 QueuePool 实现连接复用，减少连接开销
        _engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            poolclass=QueuePool,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_timeout=POOL_TIMEOUT,
            pool_recycle=POOL_RECYCLE,
            pool_pre_ping=True,  # 连接前 ping 检测，自动回收失效连接
        )
        _register_natural_collation(_engine)
        SessionLocal.configure(bind=_engine)
        with _engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        Base.metadata.create_all(bind=_engine, tables=_schema_tables())
        _ensure_schema()
        _init_fts5()
        _engine_path = db_path


SCHEMA_VERSION = 2


def _ensure_schema() -> None:
    """事务化迁移历史结构；失败回滚并中止启动。"""
    raw = _engine.raw_connection()
    try:
        raw.execute("PRAGMA foreign_keys=OFF")
        raw.execute("BEGIN IMMEDIATE")
        version = raw.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("数据库版本高于当前应用支持的版本")
        if version < 1:
            additions = {
                "files": {"modified_at": "FLOAT", "duration": "FLOAT", "width": "INTEGER",
                          "height": "INTEGER", "bitrate": "INTEGER", "media_probed": "INTEGER DEFAULT 0",
                          "parent_dir": "TEXT"},
                "tags": {"workspace": "TEXT", "icon": "TEXT",
                         "parent_id": "INTEGER REFERENCES tags(id) ON DELETE SET NULL"},
            }
            for table, columns in additions.items():
                existing = {row[1] for row in raw.execute(f"PRAGMA table_info({table})")}
                for name, definition in columns.items():
                    if name not in existing:
                        raw.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
            # 历史单列名称唯一约束必须移除，同时完整保留层级和关联。
            unique_name = any(row[2] and [col[2] for col in raw.execute(f'PRAGMA index_info("{row[1]}")')] == ["name"]
                              for row in raw.execute("PRAGMA index_list(tags)").fetchall())
            if unique_name:
                raw.execute("CREATE TABLE tags_new (id INTEGER PRIMARY KEY, name TEXT NOT NULL, color TEXT, icon TEXT, description TEXT, workspace TEXT, parent_id INTEGER REFERENCES tags(id) ON DELETE SET NULL, created_at DATETIME)")
                raw.execute("INSERT INTO tags_new SELECT id,name,color,icon,description,workspace,parent_id,created_at FROM tags")
                raw.execute("DROP TABLE tags")
                raw.execute("ALTER TABLE tags_new RENAME TO tags")
            raw.execute("UPDATE tags SET parent_id=NULL WHERE parent_id IS NOT NULL AND parent_id NOT IN (SELECT id FROM tags)")
            raw.execute("CREATE TABLE file_tags_new (file_id INTEGER REFERENCES files(id) ON DELETE CASCADE, tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE, PRIMARY KEY(file_id,tag_id))")
            raw.execute("INSERT OR IGNORE INTO file_tags_new SELECT ft.file_id,ft.tag_id FROM file_tags ft JOIN files f ON f.id=ft.file_id JOIN tags t ON t.id=ft.tag_id")
            raw.execute("DROP TABLE file_tags")
            raw.execute("ALTER TABLE file_tags_new RENAME TO file_tags")
            for fid, path in raw.execute("SELECT id,path FROM files WHERE parent_dir IS NULL").fetchall():
                raw.execute("UPDATE files SET parent_dir=? WHERE id=?", (str(path).replace(chr(92), "/").rsplit("/", 1)[0], fid))
            # 重建后恢复模型声明的全部索引。
            for table in _schema_tables():
                for index in table.indexes:
                    from sqlalchemy.schema import CreateIndex
                    raw.execute(str(CreateIndex(index, if_not_exists=True).compile(_engine)))
            raw.execute("PRAGMA user_version=1")
        if version < 2:
            raw.execute('CREATE INDEX IF NOT EXISTS idx_files_name_natural ON files(name COLLATE "NATURAL", id)')
            raw.execute('CREATE INDEX IF NOT EXISTS idx_files_parent_name_natural ON files(parent_dir, name COLLATE "NATURAL", id)')
            raw.execute("PRAGMA user_version=2")
        violations = raw.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"数据库外键校验失败: {violations[:5]}")
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.execute("PRAGMA foreign_keys=ON")
        raw.close()


def _schema_tables():
    """获取普通模型表，排除单独管理的虚拟表。"""
    return [table for table in Base.metadata.sorted_tables if table.name != "files_fts"]


def _get_table_sql(connection, table_name: str) -> str | None:
    """读取表定义，用于检测历史结构。"""
    result = connection.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    )
    return result.scalar()


def _is_fts5_table_sql(sql: str | None) -> bool:
    if not sql:
        return False
    lowered = sql.lower()
    return "create virtual table" in lowered and "fts5" in lowered


def _init_fts5() -> None:
    """初始化 trigram 子串索引及同步触发器，不支持时保留 LIKE 回退。"""
    with _engine.begin() as connection:
        try:
            connection.exec_driver_sql("CREATE VIRTUAL TABLE temp.trigram_probe USING fts5(name, tokenize='trigram')")
            connection.exec_driver_sql("DROP TABLE temp.trigram_probe")
        except Exception as exc:
            if "no such tokenizer" in str(exc) or "no such module: fts5" in str(exc):
                return
            raise
        existing = _get_table_sql(connection, "files_fts")
        rebuild = not existing or "trigram" not in existing.lower()
        for suffix in ("ai", "ad", "au"):
            connection.exec_driver_sql(f"DROP TRIGGER IF EXISTS files_{suffix}")
        if rebuild:
            connection.exec_driver_sql("DROP TABLE IF EXISTS files_fts")
            connection.exec_driver_sql("CREATE VIRTUAL TABLE files_fts USING fts5(name, content='files', content_rowid='id', tokenize='trigram')")
        connection.exec_driver_sql("CREATE TRIGGER files_ai AFTER INSERT ON files BEGIN INSERT INTO files_fts(rowid,name) VALUES(new.id,new.name); END")
        connection.exec_driver_sql("CREATE TRIGGER files_ad AFTER DELETE ON files BEGIN INSERT INTO files_fts(files_fts,rowid,name) VALUES('delete',old.id,old.name); END")
        connection.exec_driver_sql("CREATE TRIGGER files_au AFTER UPDATE OF name ON files WHEN old.name IS NOT new.name BEGIN INSERT INTO files_fts(files_fts,rowid,name) VALUES('delete',old.id,old.name); INSERT INTO files_fts(rowid,name) VALUES(new.id,new.name); END")
        if rebuild:
            connection.exec_driver_sql("INSERT INTO files_fts(files_fts) VALUES('rebuild')")


def get_session() -> Session:
    """获取数据库会话
    
    Returns:
        新的数据库 Session 对象
    """
    return SessionLocal()


def get_session_context():
    """获取会话上下文管理器
    
    使用示例:
        with get_session_context() as session:
            repo = Repo(session)
            repo.create_file(...)
    
    Returns:
        上下文管理器，自动处理 commit/rollback
    """
    return SessionContext()


class SessionContext:
    """会话上下文管理器 - 自动管理事务"""
    
    def __enter__(self) -> Session:
        self.session = SessionLocal()
        return self.session
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()
