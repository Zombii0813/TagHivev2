"""API 路由"""

from __future__ import annotations

from ..utils.paths import path_prefix, is_within

import os
from pathlib import Path
import shutil
from datetime import datetime
from typing import List
from mimetypes import guess_type

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from sqlalchemy import select
from ..db import get_session, Repo
from ..db.models import File, Tag, FileTag
from ..db.session import NATURAL_COLLATION, natural_sort_key
from ..core.search import SearchQuery
from ..core.indexer import build_file_meta
from ..services.scan_service import ScanService
from ..services.file_operations import trash_path, filesystem_transaction, serialized_filesystem
from .websocket import schedule_folder_tree_changed
from .threaded import threaded
from .models import (
    FileDTO,
    FileImportRequestDTO,
    FileImportResultDTO,
    FileResolveRequestDTO,
    FileResolveResultDTO,
    FileSummaryDTO,
    MediaInfoDTO,
    TagDTO,
    TagCreateDTO,
    TagUpdateDTO,
    SearchQueryDTO,
    SearchResultDTO,
    FileTagsUpdateDTO,
    ScanProgressDTO,
    WorkspaceDTO,
    FolderTreeDTO,
    FolderNodeDTO,
    FolderContentsDTO,
    ChildDirDTO,
    FolderCreateRequestDTO,
    FolderCreateResultDTO,
    FolderDeleteRequestDTO,
    FolderCoverRequestDTO,
    FolderCoverClearRequestDTO,
    FileRenameRequestDTO,
    FileMoveRequestDTO,
    FileCopyRequestDTO,
    FileBatchResultDTO,
    FolderMoveRequestDTO,
    FolderCopyRequestDTO,
    TagExportRequestDTO,
    ExportedTagDTO,
    FileMatchEntryDTO,
    ImportPreviewDTO,
    ImportRelocateRequestDTO,
    ImportCommitRequestDTO,
    ImportSummaryDTO,
)

router = APIRouter(prefix="/api")


def _build_unique_target_path(target_dir: Path, source_name: str) -> Path:
    """为导入文件生成不冲突的目标路径"""
    candidate = target_dir / source_name
    if not candidate.exists():
        return candidate

    stem = Path(source_name).stem
    suffix = Path(source_name).suffix
    counter = 1

    while True:
        candidate = target_dir / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _ensure_path_within_root(path: Path, root: Path) -> None:
    """确保路径位于指定根目录内。"""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Path is outside workspace root") from exc


def _parse_roots(value: str) -> list[str]:
    """解析显式工作区范围，空数组表示无可见工作区。"""
    import json
    try:
        roots = json.loads(value)
        if not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
            raise ValueError("roots must be an array of paths")
        return [Path(root).as_posix() for root in roots]
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid workspace roots") from exc


# ========== 依赖注入 ==========

def get_db():
    db = get_session()
    try:
        yield db
    finally:
        db.close()


def get_repo(db: Session = Depends(get_db)) -> Repo:
    return Repo(db)


# ========== 文件相关 API ==========

def _to_file_summary(row, tag_ids: List[int] | None = None) -> FileSummaryDTO:
    """把 File 行转为文件摘要 DTO。

    收敛所有构造点，避免新增字段时漏改某处（媒体元数据随列表下发，
    前端据此免去一次探测请求）。

    Args:
        row: File ORM 行对象。
        tag_ids: 显式指定标签 ID；为 None 时取自 row.tags。
            复制文件等场景副本不携带原标签，显式传 [] 以表达该语义。

    Returns:
        FileSummaryDTO。
    """
    return FileSummaryDTO(
        id=row.id,
        name=row.name,
        path=row.path,
        type=row.type,
        size=row.size,
        modified_at=row.modified_at,
        duration=row.duration,
        width=row.width,
        height=row.height,
        bitrate=row.bitrate,
        tag_ids=tag_ids if tag_ids is not None else [t.id for t in row.tags],
    )


def _build_search_result(query: SearchQueryDTO, repo: Repo) -> SearchResultDTO:
    """构建搜索结果（SQL 层分页，不全量加载）"""
    search_query = SearchQuery(
        text=query.text,
        root=query.root,
        roots=tuple(query.roots) if query.roots is not None else None,
        types=tuple(query.types) if query.types else (),
        tags=tuple(query.tags) if query.tags else (),
        match_all_tags=query.match_all_tags,
        sort_by=query.sort_by,
        sort_desc=query.sort_desc,
        use_fts=query.use_fts,
    )

    limit = query.limit or 500
    offset = query.offset

    # 两条独立 SQL：COUNT(*) 获取总数，LIMIT/OFFSET 获取当页数据
    total = repo.count_search(search_query)
    page = repo.search_with_offset(search_query, offset=offset, limit=limit)

    # 转换为 DTO
    file_ids = [r.file_id for r in page.items]
    files = repo.get_files_by_ids(file_ids)
    file_map = {f.id: f for f in files}

    file_dtos = []
    for r in page.items:
        f = file_map.get(r.file_id)
        if f:
            file_dtos.append(_to_file_summary(f))

    return SearchResultDTO(
        files=file_dtos,
        total=total,
        has_more=offset + limit < total,
    )


@router.get("/files", response_model=SearchResultDTO)
@threaded
def search_files_get(
    query: SearchQueryDTO,
    repo: Repo = Depends(get_repo),
):
    """搜索文件 (GET)"""
    return _build_search_result(query, repo)


@router.post("/files", response_model=SearchResultDTO)
@threaded
def search_files_post(
    query: SearchQueryDTO,
    repo: Repo = Depends(get_repo),
):
    """搜索文件 (POST)"""
    return _build_search_result(query, repo)


@router.get("/files/{file_id}", response_model=FileDTO)
@threaded
def get_file(
    file_id: int,
    repo: Repo = Depends(get_repo),
):
    """获取文件详情"""
    file = repo.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    tags = [TagDTO.from_orm(t) for t in file.tags]

    return FileDTO(
        id=file.id,
        path=file.path,
        name=file.name,
        ext=file.ext,
        size=file.size,
        type=file.type,
        hash=file.hash,
        modified_at=file.modified_at,
        created_at=file.created_at,
        updated_at=file.updated_at,
        tags=tags,
    )


@router.post("/files/resolve", response_model=FileResolveResultDTO)
@threaded
def resolve_files_by_paths(
    payload: FileResolveRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """按路径解析已入库文件，用于拖拽外部文件时快速匹配。"""
    normalized_paths = [Path(path).as_posix() for path in payload.paths if path]
    files = repo.get_files_by_paths(normalized_paths)
    file_map = {str(file.path): file for file in files}

    resolved_files = []
    missing_paths: list[str] = []

    for path in normalized_paths:
        file = file_map.get(path)
        if file is None:
            missing_paths.append(path)
            continue

        resolved_files.append(_to_file_summary(file))

    return FileResolveResultDTO(files=resolved_files, missing_paths=missing_paths)


@router.post("/files/import", response_model=FileImportResultDTO)
@threaded
def import_files_to_directory(
    payload: FileImportRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """将外部文件移动到目标目录并立即入库。"""
    target_dir = Path(payload.target_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target directory not found")

    with filesystem_transaction(repo) as changes:
        imported_files: list[FileSummaryDTO] = []

        for raw_path in payload.paths:
            if not raw_path:
                continue

            source_path = Path(raw_path)
            if not source_path.exists() or not source_path.is_file():
                raise HTTPException(status_code=400, detail=f"Invalid file path: {raw_path}")

            source_existing = repo.get_file_by_path(str(source_path))
            destination_path = _build_unique_target_path(target_dir, source_path.name)

            try:
                changes.append((source_path, destination_path))
                moved_path = Path(shutil.move(str(source_path), str(destination_path)))
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Failed to move file: {raw_path} -> {exc}") from exc

            meta = build_file_meta(moved_path)
            existing = repo.get_file_by_path(str(moved_path))
            file_row = repo.upsert_file(
                meta,
                existing_id=(source_existing.id if source_existing else (existing.id if existing else None)),
            )

            imported_files.append(_to_file_summary(file_row))


    # 文件结构/数量变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    schedule_folder_tree_changed()
    return FileImportResultDTO(files=imported_files, target_dir=target_dir.as_posix())


@router.put("/files/{file_id}/tags")
@threaded
def update_file_tags(
    file_id: int,
    update: FileTagsUpdateDTO,
    repo: Repo = Depends(get_repo),
):
    """更新文件标签"""
    file = repo.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    tags = repo.get_tags_by_ids(update.tag_ids)
    tag_map = {t.id: t for t in tags}

    if update.mode == "replace":
        repo.detach_all_tags(file)
        repo.attach_tags(file, [tag_map[tid] for tid in update.tag_ids if tid in tag_map])
    elif update.mode == "add":
        repo.attach_tags(file, [tag_map[tid] for tid in update.tag_ids if tid in tag_map])
    elif update.mode == "remove":
        for tid in update.tag_ids:
            if tid in tag_map:
                repo.remove_tag_from_file(file, tag_map[tid])

    repo.session.commit()
    return {"success": True}


@router.get("/files/{file_id}/media-info", response_model=MediaInfoDTO)
async def get_file_media_info(
    file_id: int,
    refresh: bool = False,
    repo: Repo = Depends(get_repo),
):
    """获取视频/音频的时长、分辨率与比特率（惰性探测 + 落库缓存）。

    扫描阶段不做媒体探测（逐文件解封装在万级文件量下开销过大），首次查看文件详情时
    才实际探测并把结果写回 files 表；后续命中缓存直接返回。探测失败也会打标记，
    避免对损坏或不受支持的文件反复重试。

    Args:
        file_id: 文件 ID。
        refresh: 为 true 时忽略缓存强制重新探测。

    Returns:
        MediaInfoDTO；非媒体文件或探测不到时各字段为 None。

    Raises:
        HTTPException: 文件记录不存在（404）。
    """
    from app.utils.media_info import extract_media_info, is_media_file

    file_row = repo.get_file_by_id(file_id)
    if not file_row:
        raise HTTPException(status_code=404, detail="File not found")

    # 命中缓存：已探测过且非强制刷新
    if file_row.media_probed and not refresh:
        return MediaInfoDTO(
            file_id=file_id,
            duration=file_row.duration,
            width=file_row.width,
            height=file_row.height,
            bitrate=file_row.bitrate,
        )

    file_path = Path(file_row.path)
    # 非媒体文件或文件已不在磁盘上：直接返回空结果，不落库（避免掩盖后续文件恢复）
    if not is_media_file(file_path) or not file_path.exists():
        return MediaInfoDTO(file_id=file_id)

    # PyAV 解封装是阻塞 IO/CPU 操作，放线程池避免卡住事件循环
    from starlette.concurrency import run_in_threadpool

    info = await run_in_threadpool(extract_media_info, file_path)

    repo.update_media_info(
        file_id,
        duration=info.duration,
        width=info.width,
        height=info.height,
        bitrate=info.bitrate,
    )
    repo.session.commit()

    return MediaInfoDTO(
        file_id=file_id,
        duration=info.duration,
        width=info.width,
        height=info.height,
        bitrate=info.bitrate,
    )


@router.get("/files/{file_id}/preview")
@threaded
def get_file_preview(
    file_id: int,
    repo: Repo = Depends(get_repo),
):
    """获取文件预览（用于视频播放）"""
    file = repo.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = Path(file.path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # 猜测 MIME 类型
    mime_type, _ = guess_type(file.path)

    # 根据文件扩展名设置默认 MIME 类型
    if not mime_type:
        ext = file.ext.lower() if file.ext else ''
        mime_mapping = {
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.ogg': 'video/ogg',
            '.ogv': 'video/ogg',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.mkv': 'video/x-matroska',
            '.flv': 'video/x-flv',
            '.f4v': 'video/x-f4v',
            '.m4v': 'video/x-m4v',
            '.3gp': 'video/3gpp',
            '.wmv': 'video/x-ms-wmv',
            '.asf': 'video/x-ms-asf',
            '.mpg': 'video/mpeg',
            '.mpeg': 'video/mpeg',
            '.m2v': 'video/mpeg',
            '.ts': 'video/mp2t',
            '.m2ts': 'video/mp2t',
            '.mts': 'video/mp2t',
            '.vob': 'video/mpeg',
        }
        mime_type = mime_mapping.get(ext, 'application/octet-stream')

    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        filename=file.name,
        headers={
            "Accept-Ranges": "bytes",
        }
    )


@router.get("/files/{file_id}/transcode")
@threaded
def transcode_file(
    file_id: int,
    repo: Repo = Depends(get_repo),
):
    """把浏览器无法原生播放的视频进程内转封装/转码为 fragmented MP4 流式返回。

    用于 .ts / .rmvb / .wmv / .vob 等非原生格式的在线播放：H.264+AAC 源走流拷贝
    （几乎零开销），其余实时转码为 libx264/aac。前端对非原生格式改用此端点。
    """
    from fastapi.responses import StreamingResponse
    from app.utils.video_stream import stream_fmp4

    file = repo.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = Path(file.path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    try:
        generator = stream_fmp4(file_path)
    except RuntimeError as exc:
        # PyAV 缺失或无视频流：415 Unsupported Media Type
        raise HTTPException(status_code=415, detail=str(exc))

    return StreamingResponse(
        generator,
        media_type="video/mp4",
        headers={
            # fMP4 渐进式流不支持任意 Range，显式声明 none 避免浏览器发 Range 请求
            "Accept-Ranges": "none",
            "Cache-Control": "no-store",
        },
    )


@router.delete("/files/{file_id}")
@threaded
@serialized_filesystem
def delete_file(
    file_id: int,
    repo: Repo = Depends(get_repo),
):
    """删除文件（移至回收站）"""
    file = repo.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    file_path = Path(file.path)
    if file_path.exists():
        try:
            trash_path(file_path)
        except Exception as exc:
            raise HTTPException(status_code=409, detail=f"移至回收站失败，索引已保留: {exc}") from exc

    # 删除数据库记录
    repo.delete_files([file_id])
    repo.session.commit()
    # 文件数量变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    schedule_folder_tree_changed()
    return {"success": True}


@router.put("/files/{file_id}/rename", response_model=FileSummaryDTO)
@threaded
def rename_file(
    file_id: int,
    payload: FileRenameRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """重命名文件（磁盘 + 数据库）"""
    new_name = payload.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="New name cannot be empty")

    file = repo.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")

    old_path = Path(file.path)
    new_path = old_path.parent / new_name

    if new_path.exists():
        raise HTTPException(status_code=400, detail=f"File already exists: {new_name}")

    with filesystem_transaction(repo) as changes:
        try:
            changes.append((old_path, new_path))
            old_path.rename(new_path)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to rename file: {exc}") from exc

        meta = build_file_meta(new_path)
        file_row = repo.upsert_file(meta, existing_id=file.id)

    # 重命名仅改变文件名，不影响目录结构本身，但 folder_tree 节点文件计数无变化；
    # 仍然失效，避免 file_count 缓存与实际不一致（旧文件名/新文件名属同一目录）
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")

    return _to_file_summary(file_row)


@router.post("/files/move", response_model=FileBatchResultDTO)
@threaded
def move_files(
    payload: FileMoveRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """将文件移动到指定目录（支持跨工作区）

    跨工作区移动时，源文件原本携带的、属于其它工作区的标签关联会被解除；
    目标工作区下不存在的标签则会被剥离，避免出现"文件出现在新工作区却被旧工作区标签反向匹配"的语义混乱。
    """
    target_dir = Path(payload.target_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target directory not found")

    target_workspace = (payload.target_workspace or "").strip() or None

    with filesystem_transaction(repo) as changes:
        moved_files: list[FileSummaryDTO] = []

        for file_id in payload.file_ids:
            file = repo.get_file_by_id(file_id)
            if not file:
                continue

            source_path = Path(file.path)
            if not source_path.exists():
                continue

            # 目标路径与源路径相同时跳过
            if source_path.parent.resolve() == target_dir.resolve():
                continue

            dest_path = _build_unique_target_path(target_dir, source_path.name)

            try:
                changes.append((source_path, dest_path))
                shutil.move(str(source_path), str(dest_path))
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Failed to move file: {exc}") from exc

            meta = build_file_meta(dest_path)
            file_row = repo.upsert_file(meta, existing_id=file.id)

            # 跨工作区移动时清理不属于目标工作区的标签关联
            if target_workspace:
                kept_tags = [
                    t for t in file_row.tags
                    if t.workspace is None or t.workspace == target_workspace
                ]
                if len(kept_tags) != len(file_row.tags):
                    file_row.tags = kept_tags

            moved_files.append(_to_file_summary(file_row))


    # 文件结构/数量变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    schedule_folder_tree_changed()
    return FileBatchResultDTO(files=moved_files, target_dir=target_dir.as_posix())


@router.post("/files/copy", response_model=FileBatchResultDTO)
@threaded
def copy_files(
    payload: FileCopyRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """复制文件到指定目录（副本入库，不含原标签）"""
    target_dir = Path(payload.target_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target directory not found")

    with filesystem_transaction(repo) as changes:
        copied_files: list[FileSummaryDTO] = []

        for file_id in payload.file_ids:
            file = repo.get_file_by_id(file_id)
            if not file:
                continue

            source_path = Path(file.path)
            if not source_path.exists():
                continue

            dest_path = _build_unique_target_path(target_dir, source_path.name)

            try:
                changes.append((None, dest_path))
                shutil.copy2(str(source_path), str(dest_path))
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Failed to copy file: {exc}") from exc

            meta = build_file_meta(dest_path)
            # 副本作为全新记录入库（不传 existing_id）
            file_row = repo.upsert_file(meta)
            copied_files.append(_to_file_summary(file_row, tag_ids=[]))


    # 文件结构/数量变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    schedule_folder_tree_changed()
    return FileBatchResultDTO(files=copied_files, target_dir=target_dir.as_posix())


# ========== 标签相关 API ==========

@router.get("/tags", response_model=List[TagDTO])
@threaded
def list_tags(
    root: str | None = None,
    roots: str | None = None,
    repo: Repo = Depends(get_repo),
):
    """获取所有标签

    Args:
        root: 可选的工作目录路径，用于过滤标签的工作空间
    """
    tags = repo.list_tags(root=root)
    if roots is not None and not root:
        from sqlalchemy import or_, func
        scopes = _parse_roots(roots)
        tags = [tag for tag in tags if tag.workspace is None or tag.workspace in scopes]
        condition = or_(*(path_prefix(File.path, scope) for scope in scopes)) if scopes else False
        counts = dict(repo.session.execute(select(FileTag.tag_id, func.count()).join(File).where(condition).group_by(FileTag.tag_id)).all())
        for tag in tags:
            tag._file_count = counts.get(tag.id, 0)
    result = []
    for tag in tags:
        # 使用动态属性 _file_count（由 list_tags 方法设置）
        file_count = getattr(tag, '_file_count', 0)
        result.append(TagDTO(
            id=tag.id,
            name=tag.name,
            color=tag.color,
            icon=tag.icon,
            description=tag.description,
            parent_id=tag.parent_id,
            created_at=tag.created_at,
            file_count=file_count,
        ))
    return result


@router.post("/tags", response_model=TagDTO)
@threaded
def create_tag(
    spec: TagCreateDTO,
    repo: Repo = Depends(get_repo),
):
    """创建标签

    支持按工作目录隔离，不同工作目录可以有相同名称的标签。
    """
    from ..core.tag_manager import TagSpec

    # 检查同一工作目录下是否已存在同名标签
    existing = repo.get_tag_by_name_and_workspace(spec.name, spec.workspace)
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists in this workspace")

    try:
        repo.validate_tag_parent(spec.parent_id, Path(spec.workspace).as_posix() if spec.workspace else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    tag = repo.create_tag(TagSpec(
        name=spec.name,
        color=spec.color,
        icon=spec.icon,
        description=spec.description,
    ), workspace=spec.workspace, parent_id=spec.parent_id)
    repo.session.commit()

    return TagDTO(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        icon=tag.icon,
        description=tag.description,
        parent_id=tag.parent_id,
        created_at=tag.created_at,
        file_count=0,
    )


@router.get("/tags/{tag_id}", response_model=TagDTO)
@threaded
def get_tag(
    tag_id: int,
    repo: Repo = Depends(get_repo),
):
    """获取标签详情"""
    tags = repo.get_tags_by_ids([tag_id])
    if not tags:
        raise HTTPException(status_code=404, detail="Tag not found")

    tag = tags[0]
    return TagDTO(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        icon=tag.icon,
        description=tag.description,
        parent_id=tag.parent_id,
        created_at=tag.created_at,
        file_count=len(tag.files),
    )


@router.put("/tags/{tag_id}", response_model=TagDTO)
@threaded
def update_tag(
    tag_id: int,
    update: TagUpdateDTO,
    repo: Repo = Depends(get_repo),
):
    """更新标签"""
    tags = repo.get_tags_by_ids([tag_id])
    if not tags:
        raise HTTPException(status_code=404, detail="Tag not found")

    tag = tags[0]
    if update.name is not None:
        tag.name = update.name
    if update.color is not None:
        tag.color = update.color
    if update.icon is not None:
        tag.icon = update.icon
    if update.description is not None:
        tag.description = update.description
    if "parent_id" in update.model_fields_set:
        parent_id = update.parent_id or None
        try:
            repo.validate_tag_parent(parent_id, tag.workspace, tag.id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        tag.parent_id = parent_id

    repo.session.commit()

    return TagDTO(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        icon=tag.icon,
        description=tag.description,
        parent_id=tag.parent_id,
        created_at=tag.created_at,
        file_count=len(tag.files),
    )


@router.post("/tags/delete")
@threaded
def delete_tags_atomic(payload: dict = Body(...), repo: Repo = Depends(get_repo)):
    """在一个事务内删除标签并提升子层级，或删除全部后代。"""
    ids = payload.get("ids", [])
    if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
        raise HTTPException(status_code=400, detail="Invalid tag ids")
    mode = payload.get("mode", "promote")
    if mode not in ("promote", "descendants"):
        raise HTTPException(status_code=400, detail="Invalid deletion mode")
    tags = list(repo.session.scalars(select(Tag)))
    by_id = {tag.id: tag for tag in tags}
    deleted = set(ids) & by_id.keys()
    if mode == "descendants":
        while True:
            expanded = deleted | {tag.id for tag in tags if tag.parent_id in deleted}
            if expanded == deleted:
                break
            deleted = expanded
    else:
        for tag in tags:
            if tag.id in deleted or tag.parent_id not in deleted:
                continue
            parent_id = tag.parent_id
            visited = {tag.id}
            while parent_id in deleted:
                if parent_id in visited:
                    raise HTTPException(status_code=400, detail="Cyclic tag hierarchy")
                visited.add(parent_id)
                parent_id = by_id[parent_id].parent_id
            tag.parent_id = parent_id
    repo.session.flush()
    for tag in tags:
        if tag.id in deleted:
            tag.parent_id = None
    repo.session.flush()
    for tag_id in deleted:
        repo.delete_tag(tag_id)
    repo.session.commit()
    repo.clear_all_caches()
    return {"success": True, "deleted_ids": sorted(deleted)}


@router.delete("/tags/{tag_id}")
@threaded
def delete_tag(
    tag_id: int,
    repo: Repo = Depends(get_repo),
):
    """删除标签"""
    repo.delete_tag(tag_id)
    repo.session.commit()
    return {"success": True}


@router.post("/tags/batch-assign")
@threaded
def batch_assign_tags(
    file_ids: List[int],
    tag_ids: List[int],
    repo: Repo = Depends(get_repo),
):
    """批量为文件添加标签"""
    repo.attach_tags_to_files(file_ids, tag_ids)
    repo.session.commit()
    return {"success": True, "files": len(file_ids), "tags": len(tag_ids)}


@router.post("/tags/batch-unassign")
@threaded
def batch_unassign_tag(
    file_ids: List[int] = Body(...),
    tag_id: int = Body(...),
    repo: Repo = Depends(get_repo),
):
    """批量从文件移除单个标签

    用于「批量管理标签」对话框：用户在已有标签上点 × 时调用。
    一次只移除一个标签；如需移除多个调用方多次发起请求。
    """
    affected = repo.detach_tag_from_files(file_ids, tag_id)
    repo.session.commit()
    return {"success": True, "files": len(file_ids), "affected": affected}


# ========== 工作区扫描 API ==========

@router.post("/workspace/scan")
@threaded
def scan_workspace(
    workspace: WorkspaceDTO,
    repo: Repo = Depends(get_repo),
):
    """扫描工作区 - 立即返回，实际扫描通过 WebSocket 进行"""
    root = Path(workspace.path)
    if not root.exists():
        raise HTTPException(status_code=400, detail="Path does not exist")

    # 立即返回，不等待扫描完成
    # 实际扫描应通过 WebSocket 进行以获得实时进度
    return ScanProgressDTO(
        status="started",
        count=0,
        message="Scan started via WebSocket",
    )


@router.get("/workspace/stats")
@threaded
def get_workspace_stats(
    roots: str | None = None,
    repo: Repo = Depends(get_repo),
):
    """获取工作区统计"""
    from sqlalchemy import func

    from sqlalchemy import or_
    scopes = _parse_roots(roots) if roots is not None else None
    condition = True if scopes is None else (or_(*(path_prefix(File.path, scope) for scope in scopes)) if scopes else False)
    total_files = repo.session.scalar(select(func.count()).select_from(File).where(condition)) or 0
    tag_condition = True if scopes is None else (Tag.workspace.in_(scopes) | Tag.workspace.is_(None))
    total_tags = repo.session.scalar(select(func.count()).select_from(Tag).where(tag_condition)) or 0
    type_stats = repo.session.execute(select(File.type, func.count()).where(condition).group_by(File.type)).all()

    return {
        "total_files": total_files,
        "total_tags": total_tags,
        "type_distribution": {t: c for t, c in type_stats},
    }


# ========== 文件夹树 API ==========

def _build_folder_tree(root_path: str, repo: Repo) -> tuple[List[FolderNodeDTO], int]:
    """构建文件夹树结构，返回 (子文件夹列表, 根目录直接文件数)"""
    root = Path(root_path)
    if not root.exists() or not root.is_dir():
        return [], 0

    folder_map: dict[str, FolderNodeDTO] = {}
    root_children: list[FolderNodeDTO] = []
    root_direct_file_count = 0

    for current_root, dir_names, file_names in os.walk(root):
        current_path = Path(current_root)
        # 目录名按 Windows 资源管理器规则排序（符号 < 数字 < 字母，数字按数值）
        dir_names.sort(key=natural_sort_key)

        direct_file_count = 0
        for file_name in file_names:
            try:
                if (current_path / file_name).is_file():
                    direct_file_count += 1
            except OSError:
                continue

        if current_path == root:
            root_direct_file_count = direct_file_count
        else:
            current_node = folder_map[current_path.as_posix()]
            current_node.file_count = direct_file_count

        for dir_name in dir_names:
            child_path = current_path / dir_name
            child_node = FolderNodeDTO(
                name=dir_name,
                path=child_path.as_posix(),
                file_count=0,
                children=[],
                is_expanded=False,
            )
            folder_map[child_node.path] = child_node

            if current_path == root:
                root_children.append(child_node)
            else:
                folder_map[current_path.as_posix()].children.append(child_node)

    # 递归计算子文件夹的文件数
    def calc_total_files(node: FolderNodeDTO) -> int:
        total = node.file_count
        for child in node.children:
            total += calc_total_files(child)
        node.file_count = total
        return total

    for node in root_children:
        calc_total_files(node)

    return root_children, root_direct_file_count


@router.get("/folders/tree", response_model=FolderTreeDTO)
@threaded
def get_folder_tree(
    root: str,
    repo: Repo = Depends(get_repo),
):
    """获取文件夹树结构（带缓存，文件变更时由 WebSocket 失效）"""
    root_path = Path(root)
    if not root_path.exists():
        raise HTTPException(status_code=404, detail="Root path not found")

    cached = repo.get_folder_tree_cached(root)
    return FolderTreeDTO(
        root_path=cached["root_path"],
        folders=cached["folders"],
        total_folders=cached["total_folders"],
        root_file_count=cached["root_file_count"],
    )


@router.get("/folders/contents", response_model=FolderContentsDTO)
@threaded
def get_folder_contents(
    path: str,
    offset: int = 0,
    limit: int = 500,
    sort_by: str = "name",
    sort_desc: bool = False,
    include_dirs: bool = False,
    repo: Repo = Depends(get_repo),
):
    """获取指定文件夹的直接子文件（SQL 层过滤，不加载深层文件）

    include_dirs 为真时（explorer 浏览模式），额外返回当前层的直接子目录，
    并为每个子目录附带其内部（含深层）前若干个可缩略图文件的 id，供前端拼九宫格封面。
    """
    from sqlalchemy import func, asc, desc as sa_desc

    folder_path = Path(path)
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found")

    folder_posix = folder_path.as_posix().rstrip("/")
    # 直接子文件命中 parent_dir 索引：O(直接子文件数) 而非 O(深层全部文件数)
    base_where = [File.parent_dir == folder_posix]

    # COUNT
    count_stmt = select(func.count()).select_from(File).where(*base_where)
    total = repo.session.execute(count_stmt).scalar() or 0

    # 排序列映射
    sort_col_map = {
        "name": File.name,
        "size": File.size,
        "modified_at": File.modified_at,
        "duration": File.duration,
    }
    sort_col = sort_col_map.get(sort_by, File.name)
    # name 为文本列，套用自然排序 collation，使数字按数值大小排序（1,2,...,10）
    if sort_col is File.name:
        sort_col = sort_col.collate(NATURAL_COLLATION)
    order_expr = sa_desc(sort_col) if sort_desc else asc(sort_col)

    # 数据查询（LIMIT/OFFSET 在 SQL 层）
    data_stmt = (
        select(File)
        .options(selectinload(File.tags))
        .where(*base_where)
        .order_by(order_expr)
        .offset(offset)
        .limit(limit)
    )
    page_files = list(repo.session.execute(data_stmt).scalars())

    file_dtos = [
        _to_file_summary(f)
        for f in page_files
    ]

    # explorer 浏览模式：派生当前层的直接子目录 + 每个目录的封面文件 id
    dir_dtos: List[ChildDirDTO] = []
    if include_dirs:
        dir_dtos = _build_child_dirs(folder_path, folder_posix, repo)

    return FolderContentsDTO(
        path=path,
        files=file_dtos,
        total=total,
        has_more=offset + limit < total,
        dirs=dir_dtos,
    )


# 每个目录卡片最多取的封面缩略图数量（九宫格实际用前 4 张拼 2x2）
_COVER_LIMIT = 4


def _build_child_dirs(
    folder_path: Path, folder_posix: str, repo: Repo
) -> List[ChildDirDTO]:
    """派生指定目录的直接子目录，并为每个子目录附带封面文件 id。

    子目录来源于文件系统扫描（与目录树同源，可包含空目录）；
    封面取子目录内（含深层）前 _COVER_LIMIT 个 image/video 文件的 id。

    Args:
        folder_path: 目标目录的 Path 对象
        folder_posix: 目标目录的 POSIX 路径（已去尾部斜杠）
        repo: 数据库仓储

    Returns:
        按资源管理器规则排序的子目录 DTO 列表
    """
    from sqlalchemy import func

    # 1) 文件系统扫描直接子目录（含空目录），按资源管理器规则排序
    try:
        child_names = sorted(
            (e.name for e in os.scandir(folder_path) if e.is_dir()),
            key=natural_sort_key,
        )
    except OSError:
        return []
    if not child_names:
        return []

    child_paths = [(folder_path / name).as_posix() for name in child_names]

    # 2) 每个子目录的直接子文件数（一次分组查询）
    count_rows = repo.session.execute(
        select(File.parent_dir, func.count())
        .where(File.parent_dir.in_(child_paths))
        .group_by(File.parent_dir)
    ).all()
    count_map: dict[str, int] = {pd: c for pd, c in count_rows}

    # 3) 每个子目录（含深层）的封面文件 id：一次查询取回全部候选，Python 侧按目录归类取前 N
    #    深层匹配用 path LIKE "<dir>/%"，命中 idx_files_path。
    cover_map: dict[str, list[int]] = {p: [] for p in child_paths}
    like_clauses = [path_prefix(File.path, p) for p in child_paths]
    if like_clauses:
        from sqlalchemy import or_

        cover_rows = repo.session.execute(
            select(File.id, File.path)
            .where(File.type.in_(("image", "video")))
            .where(or_(*like_clauses))
            .order_by(File.path.collate(NATURAL_COLLATION))
        ).all()
        # 按最长前缀归属到对应子目录（子目录路径互不为前缀，直接前缀匹配即可）
        for fid, fpath in cover_rows:
            for p in child_paths:
                if fpath.startswith(p + "/"):
                    bucket = cover_map[p]
                    if len(bucket) < _COVER_LIMIT:
                        bucket.append(fid)
                    break

    # 4) 批量查询用户自定义封面（优先于九宫格）
    custom_covers = repo.get_folder_covers(child_paths)

    return [
        ChildDirDTO(
            name=name,
            path=p,
            file_count=count_map.get(p, 0),
            cover_file_ids=cover_map.get(p, []),
            cover_path=custom_covers.get(p),
        )
        for name, p in zip(child_names, child_paths)
    ]


@router.post("/folders/cover")
@threaded
def set_folder_cover(
    payload: FolderCoverRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """设置目录的自定义封面（explorer 模式）。

    cover_path 可为该目录内的文件，也可为任意本地图片/视频；仅校验其存在。
    """
    cover = Path(payload.cover_path)
    if not cover.exists() or not cover.is_file():
        raise HTTPException(status_code=404, detail="Cover file not found")

    folder_posix = Path(payload.folder_path).as_posix().rstrip("/")
    cover_posix = cover.as_posix()
    workspace = (
        Path(payload.workspace).as_posix().rstrip("/") if payload.workspace else None
    )
    repo.set_folder_cover(folder_posix, cover_posix, workspace)
    return {"folder_path": folder_posix, "cover_path": cover_posix}


@router.post("/folders/cover/clear")
@threaded
def clear_folder_cover(
    payload: FolderCoverClearRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """清除目录的自定义封面，恢复为自动九宫格。"""
    folder_posix = Path(payload.folder_path).as_posix().rstrip("/")
    repo.clear_folder_cover(folder_posix)
    return {"folder_path": folder_posix}


@router.post("/folders/create", response_model=FolderCreateResultDTO)
@threaded
def create_folder(
    payload: FolderCreateRequestDTO,
):
    """在工作区内创建新目录。"""
    root_path = Path(payload.root_path)
    parent_path = Path(payload.parent_path)

    if not root_path.exists() or not root_path.is_dir():
        raise HTTPException(status_code=404, detail="Workspace root not found")

    if not parent_path.exists() or not parent_path.is_dir():
        raise HTTPException(status_code=404, detail="Parent folder not found")

    _ensure_path_within_root(parent_path, root_path)

    folder_name = payload.name.strip()
    if not folder_name:
        raise HTTPException(status_code=400, detail="Folder name is required")

    if folder_name in {".", ".."} or any(sep in folder_name for sep in ("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid folder name")

    target_path = parent_path / folder_name
    _ensure_path_within_root(target_path, root_path)

    if target_path.exists():
        raise HTTPException(status_code=409, detail="Folder already exists")

    try:
        target_path.mkdir(parents=False, exist_ok=False)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create folder: {exc}") from exc

    # 文件夹结构变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    schedule_folder_tree_changed(root_path.as_posix())

    return FolderCreateResultDTO(name=target_path.name, path=target_path.as_posix())


@router.post("/folders/delete")
@threaded
@serialized_filesystem
def delete_folder(
    payload: FolderDeleteRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """删除目录及其下所有文件（物理删除 + DB 清理）。"""
    root_path = Path(payload.root_path)
    folder_path = Path(payload.folder_path)

    if not root_path.exists() or not root_path.is_dir():
        raise HTTPException(status_code=404, detail="Workspace root not found")

    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    _ensure_path_within_root(folder_path, root_path)

    # 收集该目录下所有 DB 文件记录（路径前缀匹配）
    folder_posix = folder_path.as_posix().rstrip("/")
    files_in_folder = repo.session.query(File).filter(
        path_prefix(File.path, folder_posix, include_self=True)
    ).all()
    files_in_folder = [f for f in files_in_folder if is_within(f.path, folder_path)]
    file_ids = [f.id for f in files_in_folder]
    try:
        trash_path(folder_path)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"移至回收站失败，索引已保留: {exc}") from exc
    if file_ids:
        repo.delete_files(file_ids)
    repo.session.commit()

    # 文件夹结构变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    schedule_folder_tree_changed(root_path.as_posix())

    return {"deleted": folder_path.as_posix(), "files_removed": len(file_ids)}


def _build_unique_target_dir(target_parent: Path, folder_name: str) -> Path:
    """为移动/复制的文件夹生成不冲突的目标目录路径。

    与 _build_unique_target_path 类似，但针对目录（无扩展名）。
    """
    candidate = target_parent / folder_name
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = target_parent / f"{folder_name} ({counter})"
        if not candidate.exists():
            return candidate
        counter += 1


def _is_same_or_subpath(target: Path, source: Path) -> bool:
    """判断 target 是否等于 source 或位于 source 之内（防止把目录移入自身/子孙）。"""
    try:
        target.resolve().relative_to(source.resolve())
        return True
    except ValueError:
        return False


@router.post("/folders/move", response_model=FileBatchResultDTO)
@threaded
def move_folder(
    payload: FolderMoveRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """将整个文件夹移动到指定父目录（支持跨工作区）。

    会同步更新该目录下所有文件记录的路径（保留文件 id 与标签关联）；跨工作区移动时，
    剥离不属于目标工作区的标签，语义与单文件移动一致。
    """
    source_path = Path(payload.source_path)
    target_parent = Path(payload.target_dir)

    if not source_path.exists() or not source_path.is_dir():
        raise HTTPException(status_code=400, detail="Source folder not found")
    if not target_parent.exists() or not target_parent.is_dir():
        raise HTTPException(status_code=400, detail="Target directory not found")

    # 防止把目录移入其自身或子孙目录
    if _is_same_or_subpath(target_parent, source_path):
        raise HTTPException(status_code=400, detail="Cannot move a folder into itself or its subfolder")

    target_workspace = (payload.target_workspace or "").strip() or None

    dest_path = _build_unique_target_dir(target_parent, source_path.name)
    source_posix = source_path.as_posix().rstrip("/")

    # 先收集 DB 中该目录下所有文件记录（路径前缀匹配）
    files_in_folder = repo.session.query(File).filter(
        path_prefix(File.path, source_posix, include_self=True)
    ).all()
    files_in_folder = [f for f in files_in_folder if is_within(f.path, source_path)]
    old_paths = {f.id: f.path for f in files_in_folder}

    with filesystem_transaction(repo) as changes:
        # 物理移动整棵目录
        try:
            changes.append((source_path, dest_path))
            shutil.move(str(source_path), str(dest_path))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to move folder: {exc}") from exc

        dest_posix = dest_path.as_posix().rstrip("/")
        moved_files: list[FileSummaryDTO] = []

        for file in files_in_folder:
            old_path = old_paths[file.id]
            # 把旧路径的 source 前缀替换为 dest 前缀（按 / 边界，避免误伤）
            if old_path == source_posix:
                new_path = dest_posix
            else:
                new_path = dest_posix + old_path[len(source_posix):]

            meta = build_file_meta(Path(new_path))
            file_row = repo.upsert_file(meta, existing_id=file.id)

            # 跨工作区移动时清理不属于目标工作区的标签关联
            if target_workspace:
                kept_tags = [
                    t for t in file_row.tags
                    if t.workspace is None or t.workspace == target_workspace
                ]
                if len(kept_tags) != len(file_row.tags):
                    file_row.tags = kept_tags

            moved_files.append(_to_file_summary(file_row))


    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    schedule_folder_tree_changed()
    return FileBatchResultDTO(files=moved_files, target_dir=dest_path.as_posix())


@router.post("/folders/copy", response_model=FileBatchResultDTO)
@threaded
def copy_folder(
    payload: FolderCopyRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """复制整个文件夹到指定父目录（副本入库，不含原标签）。"""
    source_path = Path(payload.source_path)
    target_parent = Path(payload.target_dir)

    if not source_path.exists() or not source_path.is_dir():
        raise HTTPException(status_code=400, detail="Source folder not found")
    if not target_parent.exists() or not target_parent.is_dir():
        raise HTTPException(status_code=400, detail="Target directory not found")

    if _is_same_or_subpath(target_parent, source_path):
        raise HTTPException(status_code=400, detail="Cannot copy a folder into itself or its subfolder")

    dest_path = _build_unique_target_dir(target_parent, source_path.name)

    with filesystem_transaction(repo) as changes:
        # 物理复制整棵目录
        try:
            changes.append((None, dest_path))
            shutil.copytree(str(source_path), str(dest_path))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to copy folder: {exc}") from exc

        copied_files: list[FileSummaryDTO] = []

        # 递归遍历副本目录，把所有文件作为全新记录入库
        for current_root, _dirs, file_names in os.walk(dest_path):
            for fname in file_names:
                fpath = Path(current_root) / fname
                try:
                    meta = build_file_meta(fpath)
                except Exception:
                    continue
                file_row = repo.upsert_file(meta)
                copied_files.append(_to_file_summary(file_row, tag_ids=[]))


    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    schedule_folder_tree_changed()
    return FileBatchResultDTO(files=copied_files, target_dir=dest_path.as_posix())


# ========== 健康检查 ==========

@router.get("/health")
@threaded
def health_check():
    """健康检查"""
    from ..security import INSTANCE_ID
    return {"status": "ok", "version": "0.10.0", "instance_id": INSTANCE_ID}


# ========== 标签导入导出 ==========

from fastapi.responses import Response

from ..services.tag_transfer import (
    ExportPayload,
    ImportPlan,
    ThpackFormatError,
    commit_import,
    export_workspace,
    match_files,
    parse_thpack,
    TAG_CONFLICT_SKIP,
)
from ..services.import_session import get_import_store


def _entry_to_dto(entry) -> FileMatchEntryDTO:
    """将 FileMatchEntry 序列化为 DTO"""
    ef = entry.exported
    return FileMatchEntryDTO(
        rel_path=ef.rel_path,
        name=ef.name,
        size=ef.size,
        mtime=ef.mtime,
        tag_export_ids=list(ef.tag_export_ids),
        candidate_file_ids=list(entry.candidates),
        thumbnail=ef.thumbnail,
    )


def _build_preview_dto(token: str, payload: ExportPayload, target_workspace: str, repo: Repo, match_result) -> ImportPreviewDTO:
    """构建预览 DTO（同时标注当前 workspace 下标签的同名冲突）"""
    workspace_posix = Path(target_workspace).as_posix()
    tag_dtos: list[ExportedTagDTO] = []
    for et in payload.tags:
        existing = repo.get_tag_by_name_and_workspace(et.name, workspace_posix)
        tag_dtos.append(
            ExportedTagDTO(
                export_id=et.export_id,
                name=et.name,
                color=et.color,
                icon=et.icon,
                description=et.description,
                parent_export_id=et.parent_export_id,
                conflict=existing is not None,
                existing_tag_id=int(existing.id) if existing is not None else None,
            )
        )

    return ImportPreviewDTO(
        token=token,
        schema_version=payload.schema_version,
        exported_at=payload.exported_at,
        source_workspace=payload.source_workspace,
        target_workspace=workspace_posix,
        tags=tag_dtos,
        unique=[_entry_to_dto(e) for e in match_result.unique],
        multiple=[_entry_to_dto(e) for e in match_result.multiple],
        unmatched=[_entry_to_dto(e) for e in match_result.unmatched],
    )


@router.post("/tags/export")
@threaded
def export_tags(
    payload: TagExportRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """导出指定 workspace 的标签树与文件标记关联（.thpack 二进制流）"""
    if not payload.workspace:
        raise HTTPException(status_code=400, detail="workspace 不能为空")

    data = export_workspace(
        repo,
        payload.workspace,
        payload.tag_ids,
        include_thumbnails=payload.include_thumbnails,
    )

    workspace_name = Path(payload.workspace).name or "workspace"
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = f"taghive-export-{workspace_name}-{timestamp}.thpack"

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/tags/import/preview", response_model=ImportPreviewDTO)
async def import_preview(
    request: Request,
    workspace: str,
    repo: Repo = Depends(get_repo),
):
    """上传 .thpack 并返回预览（标签冲突 + 文件匹配三类清单）

    上传形式: 请求体为 .thpack 原始字节（application/octet-stream），
    workspace 通过查询参数传入。避免引入 python-multipart 依赖。
    """
    if not workspace:
        raise HTTPException(status_code=400, detail="workspace 不能为空")

    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="请求体为空")

    from starlette.concurrency import run_in_threadpool
    return await run_in_threadpool(_import_preview_sync, raw, workspace, repo)


def _import_preview_sync(raw: bytes, workspace: str, repo: Repo):
    """在线程内解析标签包并匹配文件，保持会话顺序访问。"""
    try:
        payload = parse_thpack(raw)
    except ThpackFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    match_result = match_files(repo, payload, workspace)
    token = get_import_store().create(payload, match_result, workspace)
    return _build_preview_dto(token, payload, workspace, repo, match_result)


@router.post("/tags/import/relocate", response_model=ImportPreviewDTO)
@threaded
def import_relocate(
    request: ImportRelocateRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """对未匹配项进行重定位

    - mode='manual': 将 rel_path 锁定到指定的本地 file_id
    - mode='skip_all': 清空未匹配列表（视为全部跳过）
    """
    store = get_import_store()
    entry = store.get(request.token)
    if entry is None:
        raise HTTPException(status_code=404, detail="导入会话已失效，请重新上传")

    match = entry.match

    if request.mode == "manual":
        if not request.rel_path or request.file_id is None:
            raise HTTPException(status_code=400, detail="manual 模式需要 rel_path 与 file_id")
        target = next(
            (e for e in match.unmatched if e.exported.rel_path == request.rel_path),
            None,
        )
        if target is None:
            raise HTTPException(status_code=404, detail="该未匹配条目不存在")
        target.candidates = [int(request.file_id)]
        match.unmatched.remove(target)
        match.unique.append(target)
    elif request.mode == "skip_all":
        match.unmatched = []
    else:
        raise HTTPException(status_code=400, detail=f"未知的 mode: {request.mode}")

    store.update_match(request.token, match)
    return _build_preview_dto(
        request.token, entry.payload, entry.target_workspace, repo, match
    )


@router.post("/tags/import/commit", response_model=ImportSummaryDTO)
@threaded
def import_commit(
    request: ImportCommitRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """按用户裁决执行导入：单事务写入标签 + 文件标签关联"""
    store = get_import_store()
    entry = store.get(request.token)
    if entry is None:
        raise HTTPException(status_code=404, detail="导入会话已失效，请重新上传")

    plan = ImportPlan(workspace=entry.target_workspace)
    for td in request.tag_decisions:
        plan.tag_strategy[td.export_id] = td.strategy
        if td.strategy == "rename" and td.new_name:
            plan.rename_map[td.export_id] = td.new_name
    for fd in request.file_decisions:
        plan.file_decisions[fd.rel_path] = list(fd.file_ids)

    # 对预览中已自动归类为「唯一命中」但用户未在 file_decisions 显式裁决的，
    # 默认视为关联（用户在 UI 中通常不会逐条点 unique 项）。
    user_decided = set(plan.file_decisions.keys())
    for e in entry.match.unique:
        if e.exported.rel_path not in user_decided:
            plan.file_decisions[e.exported.rel_path] = list(e.candidates)

    try:
        summary = commit_import(repo, entry.payload, plan)
        repo.session.commit()
    except Exception:
        repo.session.rollback()
        raise

    store.discard(request.token)
    repo.invalidate_tags_cache()

    return ImportSummaryDTO(
        tags_created=summary.tags_created,
        tags_reused=summary.tags_reused,
        files_linked=summary.files_linked,
        files_skipped=summary.files_skipped,
    )
