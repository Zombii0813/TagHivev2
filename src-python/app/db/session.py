from __future__ import annotations

from pathlib import Path
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

Base = declarative_base()
SessionLocal = sessionmaker(autoflush=False, autocommit=False)
_engine = None
_engine_path: Path | None = None

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
        SessionLocal.configure(bind=_engine)
        Base.metadata.create_all(bind=_engine, tables=_schema_tables())
        _ensure_schema()
        _init_fts5()
        _engine_path = db_path


def _ensure_schema() -> None:
    """确保数据库 schema 兼容性
    
    检查并添加缺失的列和索引，用于数据库升级。
    """
    session = SessionLocal()
    try:
        connection = session.connection()
        # 添加 modified_at 列（如果缺失）
        try:
            connection.execute(text("ALTER TABLE files ADD COLUMN modified_at FLOAT"))
        except Exception:
            pass
        # 添加 duration 列（如果缺失）
        try:
            connection.execute(text("ALTER TABLE files ADD COLUMN duration FLOAT"))
        except Exception:
            pass
        # 添加 duration 索引（如果不存在）
        try:
            connection.execute(text("CREATE INDEX idx_files_duration ON files(duration)"))
        except Exception:
            pass
        # 添加 file_tags 复合索引（如果不存在）
        try:
            connection.execute(text("CREATE INDEX idx_file_tags_file_tag ON file_tags(file_id, tag_id)"))
        except Exception:
            pass
        # 添加 tags.workspace 列（如果缺失）- 用于标签隔离
        try:
            connection.execute(text("ALTER TABLE tags ADD COLUMN workspace TEXT"))
        except Exception:
            pass
        # 添加 tags.icon 列（如果缺失）- 用于 emoji 图标
        try:
            connection.execute(text("ALTER TABLE tags ADD COLUMN icon TEXT"))
        except Exception:
            pass
        # 添加 tags 表索引（如果不存在）
        try:
            connection.execute(text("CREATE INDEX idx_tags_workspace ON tags(workspace)"))
        except Exception:
            pass
        try:
            connection.execute(text("CREATE INDEX idx_tags_name_workspace ON tags(name, workspace)"))
        except Exception:
            pass
        # 重建 tags 表以移除 name 的唯一约束（SQLite 不支持直接删除约束）
        _migrate_tags_table(connection)
        # 再次确保 icon 列存在（migration 可能重建了不含 icon 的表）
        try:
            connection.execute(text("ALTER TABLE tags ADD COLUMN icon TEXT"))
        except Exception:
            pass
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def _migrate_tags_table(connection) -> None:
    """迁移 tags 表，移除 name 的唯一约束
    
    SQLite 不支持直接修改约束，需要重建表。
    """
    try:
        # 检查当前表结构
        result = connection.execute(text(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='tags'"
        ))
        table_sql = result.scalar()
        
        if table_sql and 'UNIQUE' in table_sql.upper() and 'NAME' in table_sql.upper():
            # 需要重建表来移除唯一约束
            # 1. 创建临时表
            connection.execute(text("""
                CREATE TABLE tags_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL,
                    color VARCHAR,
                    icon TEXT,
                    description VARCHAR,
                    workspace TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))

            # 2. 复制数据
            connection.execute(text("""
                INSERT INTO tags_new (id, name, color, icon, description, workspace, created_at)
                SELECT id, name, color, icon, description, workspace, created_at FROM tags
            """))
            
            # 3. 删除旧表
            connection.execute(text("DROP TABLE tags"))
            
            # 4. 重命名新表
            connection.execute(text("ALTER TABLE tags_new RENAME TO tags"))
            
            # 5. 创建索引
            connection.execute(text("CREATE INDEX idx_tags_workspace ON tags(workspace)"))
            connection.execute(text("CREATE INDEX idx_tags_name_workspace ON tags(name, workspace)"))
            
            print("[DB Migration] tags 表已重建，移除了 name 的唯一约束")
    except Exception as e:
        print(f"[DB Migration] tags 表迁移失败: {e}")


def _schema_tables():
    return [table for table in Base.metadata.sorted_tables if table.name != "files_fts"]


def _get_table_sql(connection, table_name: str) -> str | None:
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
    """初始化 FTS5 全文搜索虚拟表
    
    创建与 files 表同步的虚拟表 files_fts，使用 FTS5 扩展
    提供高性能全文搜索能力。
    """
    session = SessionLocal()
    try:
        connection = session.connection()
        
        # 检查 FTS5 扩展是否可用
        try:
            connection.execute(text("SELECT fts5('test')"))
        except Exception:
            # FTS5 不可用，跳过创建
            return
        
        existing_sql = _get_table_sql(connection, "files_fts")
        if existing_sql and not _is_fts5_table_sql(existing_sql):
            connection.execute(text("DROP TABLE files_fts"))
            existing_sql = None

        if existing_sql is None:
            connection.execute(text("DROP TRIGGER IF EXISTS files_ai"))
            connection.execute(text("DROP TRIGGER IF EXISTS files_ad"))
            connection.execute(text("DROP TRIGGER IF EXISTS files_au"))
            # 创建 FTS5 虚拟表
            connection.execute(text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
                    name,
                    content='files',
                    content_rowid='id'
                )
            """))

            # 创建触发器保持 FTS 表与 files 表同步
            # 插入触发器
            connection.execute(text("""
                CREATE TRIGGER files_ai AFTER INSERT ON files BEGIN
                    INSERT INTO files_fts(rowid, name) VALUES (new.id, new.name);
                END
            """))
            
            # 删除触发器
            connection.execute(text("""
                CREATE TRIGGER files_ad AFTER DELETE ON files BEGIN
                    INSERT INTO files_fts(files_fts, rowid, name) VALUES ('delete', old.id, old.name);
                END
            """))
            
            # 更新触发器
            connection.execute(text("""
                CREATE TRIGGER files_au AFTER UPDATE ON files BEGIN
                    INSERT INTO files_fts(files_fts, rowid, name) VALUES ('delete', old.id, old.name);
                    INSERT INTO files_fts(rowid, name) VALUES (new.id, new.name);
                END
            """))

            # 构建初始索引
            connection.execute(text("INSERT INTO files_fts(files_fts) VALUES ('rebuild')"))
        else:
            # 确保触发器存在
            connection.execute(text("""
                CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
                    INSERT INTO files_fts(rowid, name) VALUES (new.id, new.name);
                END
            """))
            connection.execute(text("""
                CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
                    INSERT INTO files_fts(files_fts, rowid, name) VALUES ('delete', old.id, old.name);
                END
            """))
            connection.execute(text("""
                CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
                    INSERT INTO files_fts(files_fts, rowid, name) VALUES ('delete', old.id, old.name);
                    INSERT INTO files_fts(rowid, name) VALUES (new.id, new.name);
                END
            """))
        
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


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
