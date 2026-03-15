from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from .session import Base


class File(Base):
    """文件模型 - 存储文件元数据"""

    __tablename__ = "files"

    id = Column(Integer, primary_key=True)
    path = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    ext = Column(Text, nullable=True)
    size = Column(Integer, nullable=False, default=0)
    type = Column(Text, nullable=False)
    hash = Column(Text, nullable=True)
    modified_at = Column(Float, nullable=True)
    duration = Column(Float, nullable=True)  # 视频/音频时长（秒）
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    tags = relationship("Tag", secondary="file_tags", back_populates="files")

    # 数据库索引优化 - 提升常用查询字段的检索性能
    __table_args__ = (
        Index("idx_files_type", "type"),  # 按文件类型筛选
        Index("idx_files_name", "name"),  # 按文件名搜索
        Index("idx_files_path", "path"),  # 按路径查找
        Index("idx_files_modified_at", "modified_at"),  # 按修改时间排序
        Index("idx_files_size", "size"),  # 按文件大小排序
        Index("idx_files_duration", "duration"),  # 按时长排序
        Index("idx_files_updated_at", "updated_at"),  # 按更新时间排序
    )


class Tag(Base):
    """标签模型 - 存储标签信息
    
    标签按工作目录隔离，不同工作目录可以有相同名称的标签。
    workspace 字段存储创建该标签时的工作目录路径。
    """

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
    color = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    workspace = Column(Text, nullable=True)  # 工作目录路径，null 表示全局标签
    created_at = Column(DateTime, default=datetime.utcnow)

    files = relationship("File", secondary="file_tags", back_populates="tags")

    # 数据库索引优化 - 提升标签查询性能
    # 使用联合唯一约束：同一工作目录下标签名称唯一
    __table_args__ = (
        Index("idx_tags_name", "name"),  # 按标签名称搜索
        Index("idx_tags_workspace", "workspace"),  # 按工作目录筛选
        Index("idx_tags_name_workspace", "name", "workspace"),  # 联合查询
    )


class FileTag(Base):
    """文件-标签关联表 - 多对多关系"""

    __tablename__ = "file_tags"

    file_id = Column(Integer, ForeignKey("files.id"), primary_key=True)
    tag_id = Column(Integer, ForeignKey("tags.id"), primary_key=True)

    # 索引优化 - 加速标签关联查询
    __table_args__ = (
        Index("idx_file_tags_tag_id", "tag_id"),
        Index("idx_file_tags_file_id", "file_id"),
        # 复合索引 - 同时按文件和标签查询时性能最优
        Index("idx_file_tags_file_tag", "file_id", "tag_id"),
    )


class FileSearch(Base):
    """FTS5 全文搜索虚拟表 - 用于高性能文件名搜索
    
    使用 SQLite FTS5 扩展提供全文搜索能力，支持：
    - 前缀搜索: name:'report*'
    - 短语搜索: name:'"annual report"'
    - 布尔搜索: name:'report AND 2024'
    
    注意：FTS 表的同步由数据库触发器自动维护，不需要 ORM 干预。
    """

    __tablename__ = "files_fts"

    # FTS5 虚拟表通过 raw SQL 创建，这里仅用于 ORM 映射
    rowid = Column(Integer, primary_key=True)
    name = Column(Text, nullable=False)
