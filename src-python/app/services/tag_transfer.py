"""标签与文件标记的导入导出服务

提供 .thpack 格式（THPK magic + 版本号 + gzip(JSON)）的序列化、
反序列化、文件匹配引擎，以及导入提交。

文件格式（二进制）:
    bytes[0..3]   = b"THPK"            魔数（magic header）
    bytes[4]      = 0x01                schema 版本号
    bytes[5..]    = gzip(JSON body)     gzip 压缩后的 JSON 主体

JSON 主体结构示例参考模块 ``EXPORT_SCHEMA_VERSION``。
"""

from __future__ import annotations

import gzip
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select

from ..db.models import File, FileTag, Tag
from ..db.repo import Repo

logger = logging.getLogger(__name__)

# .thpack 文件格式相关常量
MAGIC_HEADER = b"THPK"
EXPORT_SCHEMA_VERSION = 2  # v2 新增 ExportedFile.thumbnail（可选 base64 字符串）
SUPPORTED_SCHEMA_VERSIONS = {1, 2}
MTIME_TOLERANCE_SECONDS = 2.0  # mtime 比对容差（秒），适配 FAT/exFAT 等低精度文件系统
THUMBNAIL_EXPORT_TYPES = {"image", "video"}  # 仅这两类文件携带缩略图


class ThpackFormatError(ValueError):
    """.thpack 文件格式异常"""


# ====================================================================
# 数据结构
# ====================================================================


@dataclass(frozen=True)
class ExportedTag:
    """导出文件中的单个标签记录"""

    export_id: str
    name: str
    color: str | None
    icon: str | None
    description: str | None
    parent_export_id: str | None


@dataclass(frozen=True)
class ExportedFile:
    """导出文件中的单条文件标记记录"""

    rel_path: str
    name: str
    size: int
    mtime: float | None
    tag_export_ids: tuple[str, ...]
    thumbnail: str | None = None  # base64(small 缩略图字节)；None 表示未携带


@dataclass(frozen=True)
class ExportPayload:
    """解析后的导出数据载荷"""

    schema_version: int
    exported_at: str
    source_workspace: str
    tags: tuple[ExportedTag, ...]
    files: tuple[ExportedFile, ...]


@dataclass
class FileMatchEntry:
    """单条导出文件记录的匹配结果"""

    exported: ExportedFile
    candidates: list[int] = field(default_factory=list)  # 命中的本地 file.id 列表


@dataclass
class MatchResult:
    """整体匹配结果分类"""

    unique: list[FileMatchEntry] = field(default_factory=list)      # 唯一命中
    multiple: list[FileMatchEntry] = field(default_factory=list)    # 多匹配
    unmatched: list[FileMatchEntry] = field(default_factory=list)   # 未匹配


# ====================================================================
# 导出（序列化）
# ====================================================================


def export_workspace(
    repo: Repo,
    workspace: str,
    tag_ids: Iterable[int] | None = None,
    include_thumbnails: bool = False,
) -> bytes:
    """导出指定 workspace 的标签树与文件标记关联

    Args:
        repo: 数据访问层实例
        workspace: 工作目录路径，限定导出范围
        tag_ids: 可选，仅导出这些标签 ID（默认导出该 workspace 下所有标签）
        include_thumbnails: 是否将本地已生成的 small 缩略图（仅图片/视频）以
            base64 内联到导出包中。原始缩略图缺失时静默跳过该条。

    Returns:
        .thpack 二进制内容（含 magic + 版本号 + gzip JSON）
    """
    workspace_posix = Path(workspace).as_posix()

    # 收集 workspace 下的标签
    stmt = select(Tag).where(Tag.workspace == workspace_posix)
    all_tags = list(repo.session.execute(stmt).scalars())

    if tag_ids is not None:
        wanted = set(int(t) for t in tag_ids)
        all_tags = [t for t in all_tags if int(t.id) in wanted]

    tag_id_to_export_id: dict[int, str] = {
        int(t.id): f"t_{int(t.id)}" for t in all_tags
    }

    exported_tags: list[dict[str, Any]] = []
    for tag in all_tags:
        parent_export_id: str | None = None
        if tag.parent_id is not None and int(tag.parent_id) in tag_id_to_export_id:
            parent_export_id = tag_id_to_export_id[int(tag.parent_id)]
        exported_tags.append(
            {
                "export_id": tag_id_to_export_id[int(tag.id)],
                "name": tag.name,
                "color": tag.color,
                "icon": tag.icon,
                "description": tag.description,
                "parent_export_id": parent_export_id,
            }
        )

    # 收集这些标签关联的文件（同时限定文件路径在 workspace 下）
    exported_files: list[dict[str, Any]] = []
    if all_tags:
        tag_ids_list = [int(t.id) for t in all_tags]
        root_pattern = workspace_posix.rstrip("/") + "/%"

        # 一次拉取所有关联，按 file_id 聚合 tag_id
        rel_stmt = (
            select(FileTag.file_id, FileTag.tag_id)
            .join(File, File.id == FileTag.file_id)
            .where(
                FileTag.tag_id.in_(tag_ids_list),
                File.path.like(root_pattern),
            )
        )
        file_to_tags: dict[int, list[int]] = {}
        for file_id, tag_id in repo.session.execute(rel_stmt).all():
            file_to_tags.setdefault(int(file_id), []).append(int(tag_id))

        if file_to_tags:
            files = repo.get_files_by_ids(file_to_tags.keys())
            workspace_root = Path(workspace_posix)
            thumb_service = None
            if include_thumbnails:
                from .thumbnail_service import get_thumbnail_service
                thumb_service = get_thumbnail_service()
            thumb_attempt = 0
            thumb_embedded = 0
            for f in files:
                file_path = Path(str(f.path))
                try:
                    rel_path = file_path.relative_to(workspace_root).as_posix()
                except ValueError:
                    # 文件不在 workspace 下，跳过（理论上 SQL 已经过滤）
                    continue

                tag_export_ids = [
                    tag_id_to_export_id[tid]
                    for tid in file_to_tags[int(f.id)]
                    if tid in tag_id_to_export_id
                ]

                thumbnail_b64: str | None = None
                if thumb_service is not None and str(f.type) in THUMBNAIL_EXPORT_TYPES:
                    thumb_attempt += 1
                    # small 尺寸日常浏览不会触发生成，导出时按需生成；
                    # 失败（解码异常 / ffmpeg 缺失等）静默跳过该条
                    try:
                        thumb_service.generate_thumbnail(str(f.path), "small")
                    except Exception:
                        pass
                    thumb_path = thumb_service.get_thumbnail_path(str(f.path), "small")
                    if thumb_path.exists():
                        try:
                            import base64
                            thumbnail_b64 = base64.b64encode(thumb_path.read_bytes()).decode("ascii")
                            thumb_embedded += 1
                        except OSError:
                            thumbnail_b64 = None

                exported_files.append(
                    {
                        "rel_path": rel_path,
                        "name": f.name,
                        "size": int(f.size or 0),
                        "mtime": float(f.modified_at) if f.modified_at is not None else None,
                        "tag_export_ids": tag_export_ids,
                        "thumbnail": thumbnail_b64,
                    }
                )

            if include_thumbnails:
                logger.info(
                    "[tag_transfer] export workspace=%s thumb_attempt=%d thumb_embedded=%d",
                    workspace_posix, thumb_attempt, thumb_embedded,
                )

    body = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "source_workspace": workspace_posix,
        "tags": exported_tags,
        "files": exported_files,
    }

    json_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    compressed = gzip.compress(json_bytes)
    return MAGIC_HEADER + bytes([EXPORT_SCHEMA_VERSION]) + compressed


# ====================================================================
# 导入（反序列化）
# ====================================================================


def parse_thpack(data: bytes) -> ExportPayload:
    """解析 .thpack 二进制为结构化 payload

    Args:
        data: .thpack 文件原始字节

    Returns:
        解析后的 ExportPayload

    Raises:
        ThpackFormatError: 当文件格式或版本不合法时
    """
    if len(data) < 5:
        raise ThpackFormatError("文件长度不足，疑似损坏")
    if data[:4] != MAGIC_HEADER:
        raise ThpackFormatError("非法的 .thpack 文件（magic header 校验失败）")

    version = data[4]
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ThpackFormatError(f"不支持的 schema 版本: {version}")

    try:
        json_bytes = gzip.decompress(data[5:])
    except OSError as exc:
        raise ThpackFormatError("gzip 解压失败，文件可能已损坏") from exc

    try:
        body = json.loads(json_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ThpackFormatError("JSON 解析失败") from exc

    if not isinstance(body, dict):
        raise ThpackFormatError("JSON 顶层结构必须为对象")

    tags_raw = body.get("tags", [])
    files_raw = body.get("files", [])
    if not isinstance(tags_raw, list) or not isinstance(files_raw, list):
        raise ThpackFormatError("tags/files 字段类型不正确")

    tags = tuple(
        ExportedTag(
            export_id=str(item["export_id"]),
            name=str(item["name"]),
            color=item.get("color"),
            icon=item.get("icon"),
            description=item.get("description"),
            parent_export_id=item.get("parent_export_id"),
        )
        for item in tags_raw
    )

    files = tuple(
        ExportedFile(
            rel_path=str(item["rel_path"]),
            name=str(item["name"]),
            size=int(item.get("size") or 0),
            mtime=(float(item["mtime"]) if item.get("mtime") is not None else None),
            tag_export_ids=tuple(str(tid) for tid in item.get("tag_export_ids", [])),
            thumbnail=(str(item["thumbnail"]) if item.get("thumbnail") else None),
        )
        for item in files_raw
    )

    return ExportPayload(
        schema_version=int(body.get("schema_version", EXPORT_SCHEMA_VERSION)),
        exported_at=str(body.get("exported_at", "")),
        source_workspace=str(body.get("source_workspace", "")),
        tags=tags,
        files=files,
    )


# ====================================================================
# 文件匹配引擎
# ====================================================================


def _mtime_close(a: float | None, b: float | None) -> bool:
    """带容差的 mtime 比较

    None 视为不可比对（任何一方缺失都返回 False，避免误匹配）。
    """
    if a is None or b is None:
        return False
    return abs(a - b) <= MTIME_TOLERANCE_SECONDS


def match_files(
    repo: Repo,
    payload: ExportPayload,
    workspace: str,
) -> MatchResult:
    """按 (name, size, mtime ±2s) 在 workspace 下匹配导出文件

    Args:
        repo: 数据访问层
        payload: 解析后的导出 payload
        workspace: 目标 workspace（限定匹配范围）

    Returns:
        分类后的匹配结果（unique / multiple / unmatched）
    """
    workspace_posix = Path(workspace).as_posix()
    root_pattern = workspace_posix.rstrip("/") + "/%"

    result = MatchResult()
    if not payload.files:
        return result

    # 收集所有要匹配的 (name, size) 组合，一次性按 name+size 拉候选
    name_size_pairs = {(ef.name, ef.size) for ef in payload.files}
    if not name_size_pairs:
        return result

    # SQLite 不支持原生 (name, size) 组合 IN 查询，按 name 拉一批再内存过滤
    names = {name for name, _ in name_size_pairs}
    stmt = (
        select(File.id, File.name, File.size, File.modified_at)
        .where(
            File.name.in_(names),
            File.path.like(root_pattern),
        )
    )
    rows = repo.session.execute(stmt).all()

    # 按 (name, size) 分桶
    bucket: dict[tuple[str, int], list[tuple[int, float | None]]] = {}
    for file_id, name, size, mtime in rows:
        key = (str(name), int(size or 0))
        bucket.setdefault(key, []).append(
            (int(file_id), float(mtime) if mtime is not None else None)
        )

    for ef in payload.files:
        key = (ef.name, ef.size)
        candidates = bucket.get(key, [])
        # 按 mtime 容差进一步过滤
        matched_ids = [
            fid for fid, mt in candidates if _mtime_close(mt, ef.mtime)
        ]
        entry = FileMatchEntry(exported=ef, candidates=matched_ids)
        if not matched_ids:
            result.unmatched.append(entry)
        elif len(matched_ids) == 1:
            result.unique.append(entry)
        else:
            result.multiple.append(entry)

    return result


# ====================================================================
# 导入提交（写库）
# ====================================================================


# 标签冲突的处理策略
TAG_CONFLICT_SKIP = "skip"          # 复用现有标签
TAG_CONFLICT_MERGE = "merge"        # 复用现有标签（语义同 skip，区别仅在前端文案）
TAG_CONFLICT_RENAME = "rename"      # 重命名为「原名 (导入)」新建


@dataclass
class ImportPlan:
    """导入计划 - 由前端最终裁决后传入

    Attributes:
        workspace: 目标 workspace
        tag_strategy: 每个 export_id 对应的冲突策略（skip/merge/rename），
                     未列出的标签默认 skip。
        rename_map: 当策略为 rename 时，export_id -> 新名称
        file_decisions: 每条文件记录的最终决策。
            键: rel_path（导出时的 rel_path）
            值: 选中的本地 file_id 列表（空列表表示跳过该条）
    """

    workspace: str
    tag_strategy: dict[str, str] = field(default_factory=dict)
    rename_map: dict[str, str] = field(default_factory=dict)
    file_decisions: dict[str, list[int]] = field(default_factory=dict)


@dataclass
class ImportSummary:
    """导入完成后的统计"""

    tags_created: int = 0
    tags_reused: int = 0
    files_linked: int = 0
    files_skipped: int = 0


def commit_import(
    repo: Repo,
    payload: ExportPayload,
    plan: ImportPlan,
) -> ImportSummary:
    """按 plan 执行导入：创建/复用标签 → 建立文件标签关联

    标签按拓扑序处理（父标签优先），保证 parent_id 已就绪。
    所有写入由调用方在外层事务中提交（FastAPI 路由统一 commit/rollback）。
    """
    summary = ImportSummary()
    workspace_posix = Path(plan.workspace).as_posix()

    # 拓扑排序：父标签先于子标签
    by_id = {t.export_id: t for t in payload.tags}
    ordered: list[ExportedTag] = []
    visited: set[str] = set()

    def visit(eid: str) -> None:
        if eid in visited or eid not in by_id:
            return
        node = by_id[eid]
        if node.parent_export_id:
            visit(node.parent_export_id)
        visited.add(eid)
        ordered.append(node)

    for t in payload.tags:
        visit(t.export_id)

    # 建立 export_id -> 实际 Tag 的映射
    export_to_tag: dict[str, Tag] = {}
    for et in ordered:
        strategy = plan.tag_strategy.get(et.export_id, TAG_CONFLICT_SKIP)
        target_name = et.name
        if strategy == TAG_CONFLICT_RENAME:
            target_name = plan.rename_map.get(et.export_id) or f"{et.name} (导入)"

        existing = repo.get_tag_by_name_and_workspace(target_name, workspace_posix)
        parent_db_id: int | None = None
        if et.parent_export_id and et.parent_export_id in export_to_tag:
            parent_db_id = int(export_to_tag[et.parent_export_id].id)

        if existing is not None and strategy in (TAG_CONFLICT_SKIP, TAG_CONFLICT_MERGE):
            export_to_tag[et.export_id] = existing
            summary.tags_reused += 1
            continue

        from ..core.tag_manager import TagSpec
        spec = TagSpec(
            name=target_name,
            color=et.color,
            icon=et.icon,
            description=et.description,
        )
        new_tag = repo.create_tag(spec, workspace=workspace_posix, parent_id=parent_db_id)
        repo.session.flush()  # 拿到 new_tag.id 供后续子标签引用
        export_to_tag[et.export_id] = new_tag
        summary.tags_created += 1

    # 建立文件 ↔ 标签关联
    for ef in payload.files:
        file_ids = plan.file_decisions.get(ef.rel_path, [])
        if not file_ids:
            summary.files_skipped += 1
            continue

        tag_db_ids = [
            int(export_to_tag[eid].id)
            for eid in ef.tag_export_ids
            if eid in export_to_tag
        ]
        if not tag_db_ids:
            summary.files_skipped += 1
            continue

        repo.attach_tags_to_files(file_ids, tag_db_ids)
        summary.files_linked += len(file_ids)

    return summary
