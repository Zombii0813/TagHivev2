from __future__ import annotations

from ..utils.paths import path_prefix

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional
from pathlib import Path

from sqlalchemy import case, delete, func, select, text, update, insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, selectinload

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
from .models import File, FileTag, FileSearch, Tag, FolderCover
from .session import NATURAL_COLLATION
from .sorting import file_order, SORT_COLUMNS

# 批量操作默认批次大小
DEFAULT_BATCH_SIZE = 500

# 游标分页阈值 - 超过此数量使用游标分页
CURSOR_PAGINATION_THRESHOLD = 10000


def _content_changed_clause(stmt):
    """构造「文件内容已变化」的 SQL 条件（供 UPSERT 冲突分支判断是否清除探测缓存）。

    以待写入值与库中现值的大小/修改时间差异作为判据；两者一致时视为同一文件，
    保留惰性探测得到的分辨率与比特率。

    Args:
        stmt: sqlite_insert 语句对象，用于取 excluded 伪表列。

    Returns:
        SQLAlchemy 布尔表达式。
    """
    return (stmt.excluded.size != File.size) | (
        stmt.excluded.modified_at != File.modified_at
    )


def natural_order_column(sort_column):
    """对文本列套用自然排序 collation，其余列原样返回

    仅 name 等字符串列需要自然排序（1,2,...,10 而非 1,10,2）；
    size/modified_at/duration 为数值列，按原生数值比较即可。
    """
    if sort_column is File.name or sort_column is File.type:
        return sort_column.collate(NATURAL_COLLATION)
    return sort_column


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
        idx = path_str.rfind("/")
        parent_dir = path_str[:idx] if idx >= 0 else ""

        # 首先尝试通过 existing_id 查找
        if existing_id is not None:
            existing = self.session.execute(
                select(File).where(File.id == existing_id)
            ).scalar_one_or_none()
            if existing is not None:
                # 更新现有记录（包括 path 自身：rename 等场景下文件路径会变化）
                existing.path = path_str  # type: ignore[assignment]
                existing.parent_dir = parent_dir  # type: ignore[assignment]
                existing.name = meta.name  # type: ignore[assignment]
                existing.ext = meta.ext  # type: ignore[assignment]
                # 文件内容变化（大小或修改时间不同）时清除媒体探测缓存，让详情栏重新探测；
                # 未变化则保留已探测的时长/分辨率/比特率——扫描本身不做探测，
                # meta.duration 恒为 None，直接覆盖会把已探测结果清空。
                content_changed = (
                    existing.size != meta.size or existing.modified_at != meta.modified_at
                )
                existing.size = meta.size  # type: ignore[assignment]
                existing.type = meta.type  # type: ignore[assignment]
                existing.hash = meta.sha256  # type: ignore[assignment]
                existing.modified_at = meta.modified_at  # type: ignore[assignment]
                if meta.duration is not None:
                    existing.duration = meta.duration  # type: ignore[assignment]
                if content_changed:
                    existing.duration = meta.duration  # type: ignore[assignment]
                    existing.width = None  # type: ignore[assignment]
                    existing.height = None  # type: ignore[assignment]
                    existing.bitrate = None  # type: ignore[assignment]
                    existing.media_probed = 0  # type: ignore[assignment]
                existing.updated_at = datetime.utcnow()  # type: ignore[assignment]
                self.clear_search_cache()
                return existing

        # 使用 SQLite 的 INSERT ... ON CONFLICT 进行原子性 UPSERT
        stmt = sqlite_insert(File).values(
            path=path_str,
            parent_dir=parent_dir,
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
            'parent_dir': parent_dir,
            'name': meta.name,
            'ext': meta.ext,
            'size': meta.size,
            'type': meta.type,
            'hash': meta.sha256,
            'modified_at': meta.modified_at,
            # 扫描不做媒体探测（meta.duration 恒为 None），用 COALESCE 保留已探测的时长
            'duration': func.coalesce(stmt.excluded.duration, File.duration),
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

        # 分批读取签名，未变化的文件不发 UPDATE，也不触发 FTS 写入。
        unchanged = set()
        for start in range(0, len(to_update), 500):
            batch = to_update[start:start + 500]
            existing = {row.path: row for row in self.session.execute(
                select(File.path, File.name, File.ext, File.size, File.type, File.modified_at, File.parent_dir, File.hash)
                .where(File.path.in_([m.path.as_posix() for m in batch])))}
            for meta in batch:
                row = existing.get(meta.path.as_posix())
                if row and (row.name, row.ext, row.size, row.type, row.modified_at, row.parent_dir) == (meta.name, meta.ext, meta.size, meta.type, meta.modified_at, meta.path.parent.as_posix()) and (meta.sha256 is None or meta.sha256 == row.hash):
                    unchanged.add(meta.path.as_posix())
        to_update = [m for m in to_update if m.path.as_posix() not in unchanged]
        now = datetime.utcnow()

        # 批量插入 - 使用 INSERT ... ON CONFLICT DO UPDATE
        if to_insert:
            insert_values = []
            for meta in to_insert:
                p = meta.path.as_posix()
                idx = p.rfind("/")
                insert_values.append({
                    'path': p,
                    'parent_dir': p[:idx] if idx >= 0 else "",
                    'name': meta.name,
                    'ext': meta.ext,
                    'size': meta.size,
                    'type': meta.type,
                    'hash': meta.sha256,
                    'modified_at': meta.modified_at,
                    'duration': meta.duration,
                    'created_at': now,
                    'updated_at': now,
                })

            stmt = sqlite_insert(File).values(insert_values)
            stmt = stmt.on_conflict_do_update(
                index_elements=['path'],
                set_={
                    'parent_dir': stmt.excluded.parent_dir,
                    'name': stmt.excluded.name,
                    'ext': stmt.excluded.ext,
                    'size': stmt.excluded.size,
                    'type': stmt.excluded.type,
                    'hash': stmt.excluded.hash,
                    'modified_at': stmt.excluded.modified_at,
                    # 保留已探测的时长（扫描侧恒为 None）
                    'duration': func.coalesce(stmt.excluded.duration, File.duration),
                    # 文件大小/修改时间变化 → 清除探测缓存以便详情栏重探
                    'width': case(
                        (_content_changed_clause(stmt), None), else_=File.width
                    ),
                    'height': case(
                        (_content_changed_clause(stmt), None), else_=File.height
                    ),
                    'bitrate': case(
                        (_content_changed_clause(stmt), None), else_=File.bitrate
                    ),
                    'media_probed': case(
                        (_content_changed_clause(stmt), 0), else_=File.media_probed
                    ),
                    'updated_at': now,
                }
            )
            self.session.execute(stmt)

        # 批量更新
        if to_update:
            for meta in to_update:
                path_str = meta.path.as_posix()
                idx = path_str.rfind("/")
                parent_dir = path_str[:idx] if idx >= 0 else ""
                # 内容是否变化：以库中现值与待写入值比较，决定是否清除媒体探测缓存
                changed = File.size.is_distinct_from(meta.size) | File.modified_at.is_distinct_from(meta.modified_at)
                self.session.execute(
                    update(File).where(File.path == path_str).values(
                        parent_dir=parent_dir,
                        name=meta.name,
                        ext=meta.ext,
                        size=meta.size,
                        type=meta.type,
                        hash=func.coalesce(meta.sha256, File.hash),
                        modified_at=meta.modified_at,
                        # 扫描不探测（meta.duration 恒为 None）：内容未变则保留已探测时长
                        duration=case(
                            (changed, meta.duration),
                            else_=func.coalesce(meta.duration, File.duration),
                        ),
                        width=case((changed, None), else_=File.width),
                        height=case((changed, None), else_=File.height),
                        bitrate=case((changed, None), else_=File.bitrate),
                        media_probed=case((changed, 0), else_=File.media_probed),
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
            idx = path_str.rfind("/")
            parent_dir = path_str[:idx] if idx >= 0 else ""
            if path_str in existing_files:
                file_row = existing_files[path_str]
                file_row.parent_dir = parent_dir  # type: ignore[assignment]
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
                    parent_dir=parent_dir,
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

    def update_media_info(
        self,
        file_id: int,
        duration: float | None,
        width: int | None,
        height: int | None,
        bitrate: int | None,
    ) -> None:
        """回写惰性探测得到的媒体元数据，并标记为已探测。

        标记 media_probed=1 是为了让探测失败（各字段均为 None）的文件也不再重复解封装，
        避免每次打开详情栏都对损坏/不受支持的文件重试。

        Args:
            file_id: 文件 ID。
            duration: 时长（秒），未探测到传 None。
            width: 视频宽度（像素），未探测到传 None。
            height: 视频高度（像素），未探测到传 None。
            bitrate: 整体比特率（bps），未探测到传 None。
        """
        self.session.execute(
            update(File)
            .where(File.id == file_id)
            .values(
                duration=duration,
                width=width,
                height=height,
                bitrate=bitrate,
                media_probed=1,
                updated_at=datetime.utcnow(),
            )
        )
        self.clear_search_cache()

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
            root: 可选的工作目录路径，用于过滤标签的工作空间
                 如果提供，只返回该工作空间的标签（包括未关联文件的）
        """
        if root:
            # 如果提供了工作目录，获取该工作空间的所有标签
            root_posix = Path(root).as_posix()

            # 获取该工作空间的标签（包括 workspace 匹配或为空的）
            stmt = select(Tag).where(
                (Tag.workspace == root_posix) | (Tag.workspace.is_(None))
            )
            tags = list(self.session.execute(stmt).scalars())

            # 计算每个标签在该工作目录下的文件数量
            if tags:
                tag_ids = [tag.id for tag in tags]

                # 获取该工作目录下的文件关联计数
                count_stmt = (
                    select(FileTag.tag_id, func.count(FileTag.file_id).label('file_count'))
                    .join(File, File.id == FileTag.file_id)
                    .where(
                        FileTag.tag_id.in_(tag_ids),
                        path_prefix(File.path, root_posix)
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

    def validate_tag_parent(self, parent_id: int | None, workspace: str | None, tag_id: int | None = None) -> None:
        """验证父标签存在、工作区相同且层级无环。"""
        visited = {tag_id} if tag_id is not None else set()
        while parent_id is not None:
            if parent_id in visited:
                raise ValueError("标签不能以自身或后代作为父标签")
            visited.add(parent_id)
            parent = self.session.get(Tag, parent_id)
            if parent is None or parent.workspace != workspace:
                raise ValueError("父标签不存在或不属于同一工作区")
            parent_id = parent.parent_id

    def create_tag(self, spec: TagSpec, workspace: str | None = None, parent_id: int | None = None) -> Tag:
        """创建新标签

        Args:
            spec: 标签规格
            workspace: 工作目录路径，None 表示全局标签
            parent_id: 父标签ID，None 表示顶级标签

        Returns:
            创建的标签对象
        """
        from pathlib import Path
        self.validate_tag_parent(parent_id, Path(workspace).as_posix() if workspace else None)
        tag = Tag(
            name=spec.name,
            color=spec.color,
            icon=spec.icon,
            description=spec.description,
            workspace=Path(workspace).as_posix() if workspace else None,
            parent_id=parent_id,
        )
        self.session.add(tag)
        # 清除缓存
        self.clear_search_cache()
        return tag

    def get_or_create_tag(self, spec: TagSpec, workspace: str | None = None, parent_id: int | None = None) -> Tag:
        """获取或创建标签

        Args:
            spec: 标签规格
            workspace: 工作目录路径，None 表示全局标签
            parent_id: 父标签ID
        """
        existing = self.get_tag_by_name_and_workspace(spec.name, workspace)
        if existing is not None:
            return existing
        return self.create_tag(spec, workspace, parent_id)

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

    def detach_tag_from_files(
        self, file_ids: Iterable[int], tag_id: int
    ) -> int:
        """批量从多个文件移除指定标签

        Args:
            file_ids: 文件 ID 列表
            tag_id: 要移除的标签 ID

        Returns:
            实际删除的关联数量
        """
        file_ids = list(file_ids)
        if not file_ids:
            return 0

        result = self.session.execute(
            delete(FileTag).where(
                FileTag.file_id.in_(file_ids),
                FileTag.tag_id == tag_id,
            )
        )
        affected = result.rowcount or 0
        if affected > 0:
            # 清除缓存
            self.clear_search_cache()
        return affected

    # ========== 搜索功能 ==========

    def _search_statement(self, query: SearchQuery):
        """统一构造完整搜索条件，确保计数与分页范围一致。"""
        stmt = select(File)

        # 始终使用字面子串语义；长词使用 trigram 在数据库内筛选 ID。
        if query.text:
            term = query.text.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            stmt = stmt.where(File.name.ilike(f"%{term}%", escape="!"))
            if query.use_fts and len(query.text) >= 3 and "\x00" not in query.text:
                sql = self.session.execute(text("SELECT sql FROM sqlite_master WHERE name='files_fts'")).scalar() or ""
                if "trigram" in sql.lower():
                    phrase = '"' + query.text.replace('"', '""') + '"'
                    ids = text("SELECT rowid FROM files_fts WHERE files_fts MATCH :substring").bindparams(substring=phrase).columns(rowid=File.id.type).subquery()
                    stmt = stmt.where(File.id.in_(select(ids.c.rowid)))

        # 路径前缀过滤
        if query.root:
            root_posix = Path(query.root).as_posix()
            stmt = stmt.where(path_prefix(File.path, root_posix))

        if query.roots is not None:
            from sqlalchemy import or_
            stmt = stmt.where(or_(*(path_prefix(File.path, root) for root in query.roots)) if query.roots else False)

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

        return stmt

    def search(self, query: SearchQuery, limit: int | None = None) -> list[SearchResult]:
        """文件搜索 - 支持多种搜索条件"""
        # 检查缓存
        cached_results = self._search_cache.get(query)
        if cached_results:
            return cached_results

        stmt = self._search_statement(query)

        # 排序字段白名单及稳定的同值次序。
        stmt = stmt.order_by(*file_order(query.sort_by, query.sort_desc))

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
        """使用 FTS5 全文搜索

        FTS5 对包含 . - _ 等字符或不平衡引号的查询会抛 SQL 语法异常，
        这里捕获后返回空列表，由调用方降级为 LIKE 查询，避免整个搜索接口 500。
        """
        # 转换用户输入为 FTS5 查询语法
        # 支持: prefix*, "phrase", AND, OR, NOT
        query_text = query.replace("*", "*")  # 保留通配符

        stmt = select(FileSearch.rowid).where(
            text("files_fts MATCH :query")
        ).params(query=query_text)

        if limit is not None:
            stmt = stmt.limit(limit)

        try:
            results = self.session.execute(stmt).scalars().all()
        except Exception:
            return []
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
        stmt = select(File).options(selectinload(File.tags)).where(File.id.in_(file_ids))
        return list(self.session.execute(stmt).scalars())

    def get_files_by_paths(self, paths: Iterable[str]) -> list[File]:
        """通过路径批量获取文件"""
        normalized_paths = [Path(path).as_posix() for path in paths if path]
        if not normalized_paths:
            return []
        stmt = select(File).where(File.path.in_(normalized_paths))
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

    def set_folder_cover(
        self, folder_path: str, cover_path: str, workspace: str | None = None
    ) -> None:
        """设置（或更新）目录的自定义封面

        Args:
            folder_path: 目录路径（POSIX 形式）
            cover_path: 作为封面的图片/视频路径（POSIX 形式）
            workspace: 所属工作区根路径，便于按工作区清理
        """
        stmt = sqlite_insert(FolderCover).values(
            folder_path=folder_path,
            cover_path=cover_path,
            workspace=workspace,
            updated_at=datetime.utcnow(),
        )
        # 主键冲突时更新封面路径（UPSERT）
        stmt = stmt.on_conflict_do_update(
            index_elements=[FolderCover.folder_path],
            set_={
                "cover_path": cover_path,
                "workspace": workspace,
                "updated_at": datetime.utcnow(),
            },
        )
        self.session.execute(stmt)
        self.session.commit()

    def clear_folder_cover(self, folder_path: str) -> None:
        """清除目录的自定义封面（恢复为自动九宫格）

        Args:
            folder_path: 目录路径（POSIX 形式）
        """
        self.session.execute(
            delete(FolderCover).where(FolderCover.folder_path == folder_path)
        )
        self.session.commit()

    def get_folder_covers(self, folder_paths: Iterable[str]) -> dict[str, str]:
        """批量获取多个目录的自定义封面路径

        Args:
            folder_paths: 目录路径列表（POSIX 形式）

        Returns:
            {目录路径: 封面路径} 映射；未设置封面的目录不在结果中
        """
        paths = list(folder_paths)
        if not paths:
            return {}
        rows = self.session.execute(
            select(FolderCover.folder_path, FolderCover.cover_path).where(
                FolderCover.folder_path.in_(paths)
            )
        ).all()
        return {fp: cp for fp, cp in rows}

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
        stmt = self._search_statement(query)

        # 确定排序字段
        sort_column = SORT_COLUMNS.get(query.sort_by, File.name)
        # 文本列启用自然排序 collation，与 order/游标比较保持一致
        collation = NATURAL_COLLATION if sort_column in (File.name, File.type) else None

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
            collation=collation,
        )

    def count_search(self, query: SearchQuery) -> int:
        """计算搜索结果总数（纯 COUNT SQL，不加载任何行数据）"""
        stmt = select(func.count()).select_from(self._search_statement(query).subquery())
        return self.session.execute(stmt).scalar() or 0

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
        stmt = self._search_statement(query)

        # 排序字段白名单及稳定的同值次序。
        stmt = stmt.order_by(*file_order(query.sort_by, query.sort_desc))

        # 直接用 SQLAlchemy 2.x execute 分页，避免旧版 Query.count() 兼容问题
        stmt = stmt.offset(offset).limit(limit)
        rows = list(self.session.execute(stmt).scalars())
        items = [
            SearchResult(
                file_id=int(row.id),
                path=str(row.path),
                name=str(row.name),
                type=str(row.type),
            )
            for row in rows
        ]
        return OffsetPage(items=items, offset=offset, limit=limit, total=None, has_more=False)

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
            stmt = stmt.where(path_prefix(File.path, root_posix))

        if query.types:
            stmt = stmt.where(File.type.in_(query.types))

        if query.tags:
            stmt = stmt.join(FileTag, FileTag.file_id == File.id).join(
                Tag, Tag.id == FileTag.tag_id
            )
            stmt = stmt.where(Tag.id.in_(query.tags))

        return self.session.execute(stmt).scalar() or 0
