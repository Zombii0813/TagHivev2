from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional
from pathlib import Path

from sqlalchemy import delete, func, select, text, update, insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..core.indexer import FileMeta
from ..core.search import SearchQuery, SearchResult
from ..core.tag_manager import TagSpec
from ..core.cache import SearchCache
from ..core.query_cache import get_query_cache, QueryCache
from ..core.cursor_pagination import (
    CursorPage,
    paginate_with_cursor,
    paginate_with_offset,
    OffsetPage,
)
from .models import File, FileTag, FileSearch, Tag

# 批量操作默认批次大小
DEFAULT_BATCH_SIZE = 500

# 游标分页阈值 - 超过此数量使用游标分页
CURSOR_PAGINATION_THRESHOLD = 10000


@dataclass
class Repo:
    """数据访问层 - 提供数据库操作的统一接口
    
    包含文件、标签的增删改查，以及批量操作和全文搜索功能。
    """
    
    session: Session
    
    def __post_init__(self):
        """初始化后设置搜索缓存"""
        self._search_cache = SearchCache()
    
    def clear_search_cache(self):
        """清除搜索缓存"""
        self._search_cache.clear()

    # ========== 文件操作 ==========

    def upsert_file(self, meta: FileMeta, existing_id: int | None = None) -> File:
        """插入或更新单个文件 - 使用 SQLite UPSERT 避免并发冲突"""
        # 统一使用 POSIX 路径格式
        path_str = meta.path.as_posix()
        
        # 首先尝试通过 existing_id 查找
        if existing_id is not None:
            existing = self.session.execute(
                select(File).where(File.id == existing_id)
            ).scalar_one_or_none()
            if existing is not None:
                # 更新现有记录
                existing.name = meta.name  # type: ignore[assignment]
                existing.ext = meta.ext  # type: ignore[assignment]
                existing.size = meta.size  # type: ignore[assignment]
                existing.type = meta.type  # type: ignore[assignment]
                existing.hash = meta.sha256  # type: ignore[assignment]
                existing.modified_at = meta.modified_at  # type: ignore[assignment]
                existing.duration = meta.duration  # type: ignore[assignment]
                existing.updated_at = datetime.utcnow()  # type: ignore[assignment]
                self.clear_search_cache()
                return existing
        
        # 使用 SQLite 的 INSERT ... ON CONFLICT 进行原子性 UPSERT
        stmt = sqlite_insert(File).values(
            path=path_str,
            name=meta.name,
            ext=meta.ext,
            size=meta.size,
            type=meta.type,
            hash=meta.sha256,
            modified_at=meta.modified_at,
            duration=meta.duration,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        
        # 当 path 冲突时更新所有字段
        update_dict = {
            'name': meta.name,
            'ext': meta.ext,
            'size': meta.size,
            'type': meta.type,
            'hash': meta.sha256,
            'modified_at': meta.modified_at,
            'duration': meta.duration,
            'updated_at': datetime.utcnow(),
        }
        
        stmt = stmt.on_conflict_do_update(
            index_elements=['path'],
            set_=update_dict
        )
        
        self.session.execute(stmt)
        self.clear_search_cache()
        
        # 返回更新后的记录
        return self.session.execute(
            select(File).where(File.path == path_str)
        ).scalar_one()

    def bulk_upsert_files_fast(self, metas: list, existing_ids: dict[str, int]) -> int:
        """
        超高速批量插入或更新文件
        
        针对大文件量优化，使用原生 SQL 批量操作
        
        Args:
            metas: FileMeta 列表
            existing_ids: 路径到 ID 的映射字典
        
        Returns:
            处理的文件数量
        """
        if not metas:
            return 0
        
        # 分离插入和更新
        to_insert = []
        to_update = []
        
        for meta in metas:
            path_str = meta.path.as_posix()
            if path_str in existing_ids:
                to_update.append(meta)
            else:
                to_insert.append(meta)
        
        now = datetime.utcnow()
        
        # 批量插入 - 使用 INSERT ... ON CONFLICT DO UPDATE
        if to_insert:
            insert_values = [
                {
                    'path': meta.path.as_posix(),
                    'name': meta.name,
                    'ext': meta.ext,
                    'size': meta.size,
                    'type': meta.type,
                    'hash': meta.sha256,
                    'modified_at': meta.modified_at,
                    'duration': meta.duration,
                    'created_at': now,
                    'updated_at': now,
                }
                for meta in to_insert
            ]
            
            stmt = sqlite_insert(File).values(insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=['path'],
                set_={
                    'name': stmt.excluded.name,
                    'ext': stmt.excluded.ext,
                    'size': stmt.excluded.size,
                    'type': stmt.excluded.type,
                    'hash': stmt.excluded.hash,
                    'modified_at': stmt.excluded.modified_at,
                    'duration': stmt.excluded.duration,
                    'updated_at': now,
                }
            )
            self.session.execute(stmt)
        
        # 批量更新
        if to_update:
            for meta in to_update:
                path_str = meta.path.as_posix()
                self.session.execute(
                    update(File).where(File.path == path_str).values(
                        name=meta.name,
                        ext=meta.ext,
                        size=meta.size,
                        type=meta.type,
                        hash=meta.sha256,
                        modified_at=meta.modified_at,
                        duration=meta.duration,
                        updated_at=now,
                    )
                )
        
        self.clear_search_cache()
        return len(metas)

    def bulk_upsert_files(
        self, metas: Iterable[FileMeta], batch_size: int = DEFAULT_BATCH_SIZE
    ) -> list[File]:
        """批量插入或更新文件"""
        results: list[File] = []
        batch: list[FileMeta] = []
        
        for meta in metas:
            batch.append(meta)
            if len(batch) >= batch_size:
                results.extend(self._process_batch(batch))
                batch.clear()
                self.session.commit()
        
        if batch:
            results.extend(self._process_batch(batch))
            self.session.commit()
        
        # 清除缓存
        self.clear_search_cache()
        return results

    def _process_batch(self, batch: list[FileMeta]) -> list[File]:
        """处理一批文件元数据"""
        results: list[File] = []
        # 统一使用 POSIX 路径格式
        paths = [m.path.as_posix() for m in batch]
        
        existing_files = {
            f.path: f
            for f in self.session.execute(
                select(File).where(File.path.in_(paths))
            ).scalars()
        }
        
        for meta in batch:
            path_str = meta.path.as_posix()
            if path_str in existing_files:
                file_row = existing_files[path_str]
                file_row.name = meta.name  # type: ignore[assignment]
                file_row.ext = meta.ext  # type: ignore[assignment]
                file_row.size = meta.size  # type: ignore[assignment]
                file_row.type = meta.type  # type: ignore[assignment]
                file_row.hash = meta.sha256  # type: ignore[assignment]
                file_row.modified_at = meta.modified_at  # type: ignore[assignment]
                file_row.updated_at = datetime.utcnow()  # type: ignore[assignment]
            else:
                file_row = File(
                    path=path_str,
                    name=meta.name,
                    ext=meta.ext,
                    size=meta.size,
                    type=meta.type,
                    hash=meta.sha256,
                    modified_at=meta.modified_at,
                )
                self.session.add(file_row)
            results.append(file_row)
        
        return results

    def list_file_paths(self) -> list[tuple[int, str]]:
        """获取所有文件 ID 和路径列表"""
        stmt = select(File.id, File.path)
        return [
            (int(file_id), str(path))
            for file_id, path in self.session.execute(stmt).all()
            if file_id is not None
        ]

    def get_file_by_path(self, path: str) -> File | None:
        """通过路径获取文件"""
        # 统一使用 POSIX 路径格式
        posix_path = Path(path).as_posix()
        return self.session.execute(select(File).where(File.path == posix_path)).scalar_one_or_none()

    def get_file_by_id(self, file_id: int) -> File | None:
        """通过 ID 获取文件"""
        return self.session.execute(select(File).where(File.id == file_id)).scalar_one_or_none()

    def list_files(self, limit: int | None = None) -> list[File]:
        """获取文件列表"""
        query = select(File)
        if limit is not None:
            query = query.limit(limit)
        return list(self.session.execute(query).scalars())

    def delete_files(self, file_ids: Iterable[int]) -> None:
        """批量删除文件及其标签关联"""
        file_ids = list(file_ids)
        if not file_ids:
            return
        self.session.execute(delete(FileTag).where(FileTag.file_id.in_(file_ids)))
        self.session.execute(delete(File).where(File.id.in_(file_ids)))
        # 清除缓存
        self.clear_search_cache()

    # ========== 标签操作 ==========

    def list_tags(self, root: str | None = None) -> list[Tag]:
        """获取所有标签列表
        
        Args:
            root: 可选的工作目录路径，如果提供则只返回该目录下有关联文件的标签
        """
        if root:
            # 如果提供了工作目录，只获取该目录下有关联文件的标签
            root_posix = Path(root).as_posix()
            root_pattern = root_posix.rstrip("/") + "/%"
            
            # 获取该工作目录下的所有文件ID
            file_stmt = select(File.id).where(File.path.like(root_pattern))
            file_ids = [row[0] for row in self.session.execute(file_stmt).all()]
            
            if not file_ids:
                # 该工作目录下没有文件，返回空列表
                return []
            
            # 获取这些文件关联的所有标签ID
            tag_id_stmt = (
                select(FileTag.tag_id)
                .where(FileTag.file_id.in_(file_ids))
                .distinct()
            )
            tag_ids = [row[0] for row in self.session.execute(tag_id_stmt).all()]
            
            if not tag_ids:
                # 没有标签关联到这些文件
                return []
            
            # 获取这些标签的详细信息
            stmt = select(Tag).where(Tag.id.in_(tag_ids))
            tags = list(self.session.execute(stmt).scalars())
            
            # 计算每个标签在该工作目录下的文件数量
            count_stmt = (
                select(FileTag.tag_id, func.count(FileTag.file_id).label('file_count'))
                .where(
                    FileTag.tag_id.in_(tag_ids),
                    FileTag.file_id.in_(file_ids)
                )
                .group_by(FileTag.tag_id)
            )
            count_results = {row.tag_id: row.file_count for row in self.session.execute(count_stmt)}
            
            # 将文件数量设置到标签对象上
            for tag in tags:
                tag._file_count = count_results.get(tag.id, 0)
            
            return tags
        else:
            # 获取所有标签
            stmt = select(Tag)
            tags = list(self.session.execute(stmt).scalars())
            
            # 批量获取每个标签的文件数量
            if tags:
                tag_ids = [tag.id for tag in tags]
                count_stmt = (
                    select(FileTag.tag_id, func.count(FileTag.file_id).label('file_count'))
                    .where(FileTag.tag_id.in_(tag_ids))
                    .group_by(FileTag.tag_id)
                )
                count_results = {row.tag_id: row.file_count for row in self.session.execute(count_stmt)}
                
                # 将文件数量设置到标签对象上（用于序列化）
                for tag in tags:
                    tag._file_count = count_results.get(tag.id, 0)
            
            return tags
    
    def get_tag_file_count(self, tag_id: int) -> int:
        """获取标签关联的文件数量"""
        stmt = select(func.count(FileTag.file_id)).where(FileTag.tag_id == tag_id)
        return self.session.execute(stmt).scalar() or 0

    def get_tag_by_name(self, name: str) -> Tag | None:
        """通过名称获取标签（全局搜索）"""
        return self.session.execute(select(Tag).where(Tag.name == name)).scalar_one_or_none()

    def get_tag_by_name_and_workspace(self, name: str, workspace: str | None = None) -> Tag | None:
        """通过名称和工作目录获取标签
        
        支持按工作目录隔离，不同工作目录可以有相同名称的标签。
        
        Args:
            name: 标签名称
            workspace: 工作目录路径，None 表示全局标签
            
        Returns:
            标签对象或 None
        """
        if workspace:
            from pathlib import Path
            workspace_posix = Path(workspace).as_posix()
            return self.session.execute(
                select(Tag).where(
                    Tag.name == name,
                    Tag.workspace == workspace_posix
                )
            ).scalar_one_or_none()
        else:
            return self.session.execute(
                select(Tag).where(
                    Tag.name == name,
                    Tag.workspace.is_(None)
                )
            ).scalar_one_or_none()

    def create_tag(self, spec: TagSpec, workspace: str | None = None) -> Tag:
        """创建新标签
        
        Args:
            spec: 标签规格
            workspace: 工作目录路径，None 表示全局标签
            
        Returns:
            创建的标签对象
        """
        from pathlib import Path
        tag = Tag(
            name=spec.name,
            color=spec.color,
            description=spec.description,
            workspace=Path(workspace).as_posix() if workspace else None
        )
        self.session.add(tag)
        # 清除缓存
        self.clear_search_cache()
        return tag

    def get_or_create_tag(self, spec: TagSpec, workspace: str | None = None) -> Tag:
        """获取或创建标签
        
        Args:
            spec: 标签规格
            workspace: 工作目录路径，None 表示全局标签
        """
        existing = self.get_tag_by_name_and_workspace(spec.name, workspace)
        if existing is not None:
            return existing
        return self.create_tag(spec, workspace)

    def delete_tag(self, tag_id: int) -> None:
        """删除标签及其关联"""
        self.session.execute(delete(FileTag).where(FileTag.tag_id == tag_id))
        tag = self.session.execute(select(Tag).where(Tag.id == tag_id)).scalar_one_or_none()
        if tag is not None:
            self.session.delete(tag)
        # 清除缓存
        self.clear_search_cache()

    # ========== 文件-标签关联操作 ==========

    def attach_tags(self, file_row: File, tags: Iterable[Tag]) -> None:
        """为文件添加标签（跳过已存在的）"""
        existing = {tag.id for tag in file_row.tags}
        added = False
        for tag in tags:
            if tag.id not in existing:
                file_row.tags.append(tag)
                added = True
        if added:
            # 清除缓存
            self.clear_search_cache()

    def attach_tags_to_files(
        self, file_ids: Iterable[int], tag_ids: Iterable[int], batch_size: int = DEFAULT_BATCH_SIZE
    ) -> None:
        """批量为多个文件添加标签"""
        file_ids = list(file_ids)
        tag_ids = list(tag_ids)
        
        if not file_ids or not tag_ids:
            return
        
        existing = {
            (ft.file_id, ft.tag_id)
            for ft in self.session.execute(
                select(FileTag).where(
                    FileTag.file_id.in_(file_ids),
                    FileTag.tag_id.in_(tag_ids),
                )
            ).scalars()
        }
        
        new_associations: list[dict] = []
        for file_id in file_ids:
            for tag_id in tag_ids:
                if (file_id, tag_id) not in existing:
                    new_associations.append({"file_id": file_id, "tag_id": tag_id})
                    if len(new_associations) >= batch_size:
                        self.session.execute(FileTag.__table__.insert(), new_associations)
                        new_associations.clear()
        
        if new_associations:
            self.session.execute(FileTag.__table__.insert(), new_associations)
            # 清除缓存
            self.clear_search_cache()

    def detach_all_tags(self, file_row: File) -> None:
        """移除文件的所有标签"""
        if file_row.tags:
            file_row.tags.clear()
            # 清除缓存
            self.clear_search_cache()

    def remove_tag_from_file(self, file_row: File, tag: Tag) -> None:
        """从文件移除单个标签"""
        if tag in file_row.tags:
            file_row.tags.remove(tag)
            # 清除缓存
            self.clear_search_cache()

    # ========== 搜索功能 ==========

    def search(self, query: SearchQuery, limit: int | None = None) -> list[SearchResult]:
        """文件搜索 - 支持多种搜索条件"""
        # 检查缓存
        cached_results = self._search_cache.get(query)
        if cached_results:
            return cached_results

        stmt = select(File)

        # 文本搜索
        if query.text:
            if query.use_fts and self._has_fts5() and self._should_use_fts(query.text):
                fts_ids = self._fts_search(query.text, limit)
                if fts_ids:
                    stmt = stmt.where(File.id.in_(fts_ids))
                else:
                    term = f"%{query.text}%"
                    stmt = stmt.where(File.name.ilike(term))
            else:
                term = f"%{query.text}%"
                stmt = stmt.where(File.name.ilike(term))

        # 路径前缀过滤
        if query.root:
            # 统一使用 POSIX 路径格式进行匹配
            root_posix = Path(query.root).as_posix()
            root_pattern = root_posix.rstrip("/") + "/%"
            stmt = stmt.where(File.path.like(root_pattern))

        # 文件类型过滤
        if query.types:
            stmt = stmt.where(File.type.in_(query.types))

        # 标签过滤（使用标签 ID）
        if query.tags:
            stmt = stmt.join(FileTag, FileTag.file_id == File.id).join(
                Tag, Tag.id == FileTag.tag_id
            )
            stmt = stmt.where(Tag.id.in_(query.tags))
            if query.match_all_tags:
                stmt = stmt.group_by(File.id).having(
                    func.count(func.distinct(Tag.id)) == len(query.tags)
                )
            else:
                stmt = stmt.distinct()

        # 排序
        if query.sort_by:
            sort_column = getattr(File, query.sort_by, File.name)
            if query.sort_desc:
                stmt = stmt.order_by(sort_column.desc())
            else:
                stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(File.name.asc())

        # 分页
        if limit is not None:
            stmt = stmt.limit(limit)

        results = [
            SearchResult(
                file_id=int(row.id),
                path=str(row.path),
                name=str(row.name),
                type=str(row.type),
            )
            for row in self.session.execute(stmt).scalars()
        ]

        # 缓存结果
        self._search_cache.set(query, results)
        return results

    def _has_fts5(self) -> bool:
        """检查 FTS5 扩展是否可用"""
        try:
            self.session.execute(text("SELECT fts5('test')"))
            return True
        except Exception:
            return False

    def _should_use_fts(self, text: str) -> bool:
        """判断是否适合使用 FTS5 搜索"""
        # 简单启发式：包含空格或使用 * 通配符时优先使用 FTS
        return " " in text or "*" in text or len(text) > 3

    def _fts_search(self, query: str, limit: int | None = None) -> list[int]:
        """使用 FTS5 全文搜索"""
        # 转换用户输入为 FTS5 查询语法
        # 支持: prefix*, "phrase", AND, OR, NOT
        query_text = query.replace("*", "*")  # 保留通配符
        
        stmt = select(FileSearch.rowid).where(
            text("files_fts MATCH :query")
        ).params(query=query_text)
        
        if limit is not None:
            stmt = stmt.limit(limit)
        
        results = self.session.execute(stmt).scalars().all()
        return [int(r) for r in results if r is not None]

    def get_tags_for_file(self, file_id: int) -> list[Tag]:
        """获取文件关联的所有标签"""
        stmt = (
            select(Tag)
            .join(FileTag, FileTag.tag_id == Tag.id)
            .where(FileTag.file_id == file_id)
        )
        return list(self.session.execute(stmt).scalars())

    def get_tags_by_ids(self, tag_ids: Iterable[int]) -> list[Tag]:
        """通过 ID 批量获取标签"""
        tag_ids = list(tag_ids)
        if not tag_ids:
            return []
        stmt = select(Tag).where(Tag.id.in_(tag_ids))
        return list(self.session.execute(stmt).scalars())

    def get_files_by_ids(self, file_ids: Iterable[int]) -> list[File]:
        """通过 ID 批量获取文件"""
        file_ids = [int(file_id) for file_id in file_ids]
        if not file_ids:
            return []
        stmt = select(File).where(File.id.in_(file_ids))
        return list(self.session.execute(stmt).scalars())

    # ========== 查询缓存优化 ==========

    def list_tags_cached(self, root: str | None = None, ttl: int = 300) -> list[Tag]:
        """获取标签列表（带缓存）
        
        Args:
            root: 可选的工作目录路径
            ttl: 缓存过期时间（秒），默认5分钟
            
        Returns:
            标签列表
        """
        cache = get_query_cache()
        cache_key = f"tags:list:{root or 'all'}"
        
        # 尝试从缓存获取
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        
        # 从数据库获取
        tags = self.list_tags(root)
        
        # 缓存结果
        cache.set(cache_key, tags, ttl)
        return tags

    def get_folder_tree_cached(self, root: str, ttl: int = 300) -> dict:
        """获取文件夹树（带缓存）
        
        Args:
            root: 根目录路径
            ttl: 缓存过期时间（秒），默认5分钟
            
        Returns:
            文件夹树数据字典
        """
        cache = get_query_cache()
        cache_key = f"folder:tree:{root}"
        
        # 尝试从缓存获取
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        
        # 构建文件夹树
        from ..api.routes import _build_folder_tree
        folders, root_file_count = _build_folder_tree(root, self)
        
        # 计算总文件夹数
        def count_folders(nodes) -> int:
            count = len(nodes)
            for node in nodes:
                count += count_folders(node.children)
            return count
        
        result = {
            "root_path": root,
            "folders": folders,
            "total_folders": count_folders(folders),
            "root_file_count": root_file_count,
        }
        
        # 缓存结果
        cache.set(cache_key, result, ttl)
        return result

    def invalidate_tags_cache(self, root: str | None = None) -> None:
        """使标签列表缓存失效"""
        cache = get_query_cache()
        if root:
            cache.invalidate(f"tags:list:{root}")
        else:
            cache.invalidate_pattern("tags:list:")

    def invalidate_folder_cache(self, root: str | None = None) -> None:
        """使文件夹树缓存失效"""
        cache = get_query_cache()
        if root:
            cache.invalidate(f"folder:tree:{root}")
        else:
            cache.invalidate_pattern("folder:tree:")

    def clear_all_caches(self) -> None:
        """清除所有缓存"""
        self.clear_search_cache()
        get_query_cache().clear()

    # ========== 游标分页查询 ==========

    def search_with_cursor(
        self,
        query: SearchQuery,
        cursor: str | None = None,
        page_size: int = 50,
    ) -> CursorPage[SearchResult]:
        """使用游标分页搜索文件
        
        适用于大数据量场景，避免 OFFSET 分页的性能问题。
        
        Args:
            query: 搜索查询
            cursor: 游标字符串，None表示第一页
            page_size: 每页大小
            
        Returns:
            CursorPage 分页结果
        """
        # 构建基础查询
        stmt = select(File)

        # 文本搜索
        if query.text:
            if query.use_fts and self._has_fts5() and self._should_use_fts(query.text):
                fts_ids = self._fts_search(query.text)
                if fts_ids:
                    stmt = stmt.where(File.id.in_(fts_ids))
                else:
                    term = f"%{query.text}%"
                    stmt = stmt.where(File.name.ilike(term))
            else:
                term = f"%{query.text}%"
                stmt = stmt.where(File.name.ilike(term))

        # 路径前缀过滤
        if query.root:
            root_posix = Path(query.root).as_posix()
            root_pattern = root_posix.rstrip("/") + "/%"
            stmt = stmt.where(File.path.like(root_pattern))

        # 文件类型过滤
        if query.types:
            stmt = stmt.where(File.type.in_(query.types))

        # 标签过滤
        if query.tags:
            stmt = stmt.join(FileTag, FileTag.file_id == File.id).join(
                Tag, Tag.id == FileTag.tag_id
            )
            stmt = stmt.where(Tag.id.in_(query.tags))
            if query.match_all_tags:
                stmt = stmt.group_by(File.id).having(
                    func.count(func.distinct(Tag.id)) == len(query.tags)
                )
            else:
                stmt = stmt.distinct()

        # 确定排序字段
        sort_column = getattr(File, query.sort_by, File.name) if query.sort_by else File.name

        # 使用游标分页
        def mapper(row) -> SearchResult:
            return SearchResult(
                file_id=int(row.id),
                path=str(row.path),
                name=str(row.name),
                type=str(row.type),
            )

        return paginate_with_cursor(
            query=stmt,
            sort_by=sort_column,
            cursor=cursor,
            page_size=page_size,
            sort_desc=query.sort_desc,
            mapper=mapper,
        )

    def search_with_offset(
        self,
        query: SearchQuery,
        offset: int = 0,
        limit: int = 50,
    ) -> OffsetPage[SearchResult]:
        """使用 OFFSET 分页搜索文件
        
        适用于小数据量场景（< 10000条记录）。
        
        Args:
            query: 搜索查询
            offset: 偏移量
            limit: 每页大小
            
        Returns:
            OffsetPage 分页结果
        """
        # 构建基础查询
        stmt = select(File)

        # 文本搜索
        if query.text:
            if query.use_fts and self._has_fts5() and self._should_use_fts(query.text):
                fts_ids = self._fts_search(query.text)
                if fts_ids:
                    stmt = stmt.where(File.id.in_(fts_ids))
                else:
                    term = f"%{query.text}%"
                    stmt = stmt.where(File.name.ilike(term))
            else:
                term = f"%{query.text}%"
                stmt = stmt.where(File.name.ilike(term))

        # 路径前缀过滤
        if query.root:
            root_posix = Path(query.root).as_posix()
            root_pattern = root_posix.rstrip("/") + "/%"
            stmt = stmt.where(File.path.like(root_pattern))

        # 文件类型过滤
        if query.types:
            stmt = stmt.where(File.type.in_(query.types))

        # 标签过滤
        if query.tags:
            stmt = stmt.join(FileTag, FileTag.file_id == File.id).join(
                Tag, Tag.id == FileTag.tag_id
            )
            stmt = stmt.where(Tag.id.in_(query.tags))
            if query.match_all_tags:
                stmt = stmt.group_by(File.id).having(
                    func.count(func.distinct(Tag.id)) == len(query.tags)
                )
            else:
                stmt = stmt.distinct()

        # 排序
        if query.sort_by:
            sort_column = getattr(File, query.sort_by, File.name)
            if query.sort_desc:
                stmt = stmt.order_by(sort_column.desc())
            else:
                stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(File.name.asc())

        # 使用 OFFSET 分页
        def mapper(row) -> SearchResult:
            return SearchResult(
                file_id=int(row.id),
                path=str(row.path),
                name=str(row.name),
                type=str(row.type),
            )

        return paginate_with_offset(
            query=stmt,
            offset=offset,
            limit=limit,
            mapper=mapper,
        )

    def search_optimized(
        self,
        query: SearchQuery,
        offset: int = 0,
        limit: int = 50,
        cursor: str | None = None,
    ) -> CursorPage[SearchResult] | OffsetPage[SearchResult]:
        """优化的搜索方法 - 自动选择分页策略
        
        根据预估数据量自动选择游标分页或 OFFSET 分页。
        
        Args:
            query: 搜索查询
            offset: 偏移量（OFFSET分页使用）
            limit: 每页大小
            cursor: 游标字符串（游标分页使用）
            
        Returns:
            分页结果（CursorPage 或 OffsetPage）
        """
        # 如果提供了游标，使用游标分页
        if cursor is not None:
            return self.search_with_cursor(query, cursor, limit)
        
        # 预估数据量
        estimated_count = self._estimate_search_count(query)
        
        # 大数据量使用游标分页
        if estimated_count > CURSOR_PAGINATION_THRESHOLD or offset > 1000:
            # OFFSET 较大时也使用游标分页
            return self.search_with_cursor(query, None, limit)
        
        # 小数据量使用 OFFSET 分页
        return self.search_with_offset(query, offset, limit)

    def _estimate_search_count(self, query: SearchQuery) -> int:
        """预估搜索结果数量"""
        stmt = select(func.count(File.id))

        # 应用相同的过滤条件
        if query.text:
            term = f"%{query.text}%"
            stmt = stmt.where(File.name.ilike(term))

        if query.root:
            root_posix = Path(query.root).as_posix()
            root_pattern = root_posix.rstrip("/") + "/%"
            stmt = stmt.where(File.path.like(root_pattern))

        if query.types:
            stmt = stmt.where(File.type.in_(query.types))

        if query.tags:
            stmt = stmt.join(FileTag, FileTag.file_id == File.id).join(
                Tag, Tag.id == FileTag.tag_id
            )
            stmt = stmt.where(Tag.id.in_(query.tags))

        return self.session.execute(stmt).scalar() or 0
