"""API 路由"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from datetime import datetime
from typing import List
from mimetypes import guess_type

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from sqlalchemy import select
from ..db import get_session, Repo
from ..db.models import File, Tag
from ..core.search import SearchQuery
from ..core.indexer import build_file_meta
from ..services.scan_service import ScanService
from .models import (
    FileDTO,
    FileImportRequestDTO,
    FileImportResultDTO,
    FileResolveRequestDTO,
    FileResolveResultDTO,
    FileSummaryDTO,
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
    FolderCreateRequestDTO,
    FolderCreateResultDTO,
    FolderDeleteRequestDTO,
    FileRenameRequestDTO,
    FileMoveRequestDTO,
    FileCopyRequestDTO,
    FileBatchResultDTO,
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

def _build_search_result(query: SearchQueryDTO, repo: Repo) -> SearchResultDTO:
    """构建搜索结果（SQL 层分页，不全量加载）"""
    search_query = SearchQuery(
        text=query.text,
        root=query.root,
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
            file_dtos.append(FileSummaryDTO(
                id=f.id,
                name=f.name,
                path=f.path,
                type=f.type,
                size=f.size,
                modified_at=f.modified_at,
                duration=f.duration,
                tag_ids=[t.id for t in f.tags],
            ))

    return SearchResultDTO(
        files=file_dtos,
        total=total,
        has_more=offset + limit < total,
    )


@router.get("/files", response_model=SearchResultDTO)
async def search_files_get(
    query: SearchQueryDTO,
    repo: Repo = Depends(get_repo),
):
    """搜索文件 (GET)"""
    return _build_search_result(query, repo)


@router.post("/files", response_model=SearchResultDTO)
async def search_files_post(
    query: SearchQueryDTO,
    repo: Repo = Depends(get_repo),
):
    """搜索文件 (POST)"""
    return _build_search_result(query, repo)


@router.get("/files/{file_id}", response_model=FileDTO)
async def get_file(
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
async def resolve_files_by_paths(
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

        resolved_files.append(FileSummaryDTO(
            id=file.id,
            name=file.name,
            path=file.path,
            type=file.type,
            size=file.size,
            modified_at=file.modified_at,
            duration=file.duration,
            tag_ids=[tag.id for tag in file.tags],
        ))

    return FileResolveResultDTO(files=resolved_files, missing_paths=missing_paths)


@router.post("/files/import", response_model=FileImportResultDTO)
async def import_files_to_directory(
    payload: FileImportRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """将外部文件移动到目标目录并立即入库。"""
    target_dir = Path(payload.target_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target directory not found")

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
            moved_path = Path(shutil.move(str(source_path), str(destination_path)))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to move file: {raw_path} -> {exc}") from exc

        meta = build_file_meta(moved_path)
        existing = repo.get_file_by_path(str(moved_path))
        file_row = repo.upsert_file(
            meta,
            existing_id=(source_existing.id if source_existing else (existing.id if existing else None)),
        )

        imported_files.append(FileSummaryDTO(
            id=file_row.id,
            name=file_row.name,
            path=file_row.path,
            type=file_row.type,
            size=file_row.size,
            modified_at=file_row.modified_at,
            duration=file_row.duration,
            tag_ids=[tag.id for tag in file_row.tags],
        ))

    repo.session.commit()
    # 文件结构/数量变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    return FileImportResultDTO(files=imported_files, target_dir=target_dir.as_posix())


@router.put("/files/{file_id}/tags")
async def update_file_tags(
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


@router.get("/files/{file_id}/preview")
async def get_file_preview(
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
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.mkv': 'video/x-matroska',
            '.flv': 'video/x-flv',
        }
        mime_type = mime_mapping.get(ext, 'application/octet-stream')
    
    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        filename=file.name,
        headers={
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
        }
    )


@router.delete("/files/{file_id}")
async def delete_file(
    file_id: int,
    repo: Repo = Depends(get_repo),
):
    """删除文件（移至回收站）"""
    import platform
    import subprocess
    from pathlib import Path
    
    file = repo.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    # 将文件移至回收站
    file_path = Path(file.path)
    if file_path.exists():
        try:
            system = platform.system()
            if system == "Windows":
                # Windows: 使用 PowerShell 移至回收站
                import ctypes
                from ctypes import wintypes
                
                # SHFileOperation constants
                FO_DELETE = 0x0003
                FOF_ALLOWUNDO = 0x0040
                FOF_NOCONFIRMATION = 0x0010
                FOF_SILENT = 0x0004
                
                class SHFILEOPSTRUCT(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", wintypes.HWND),
                        ("wFunc", wintypes.UINT),
                        ("pFrom", wintypes.LPCWSTR),
                        ("pTo", wintypes.LPCWSTR),
                        ("fFlags", wintypes.WORD),
                        ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", wintypes.LPVOID),
                        ("lpszProgressTitle", wintypes.LPCWSTR),
                    ]
                
                shell32 = ctypes.windll.shell32
                SHFileOperationW = shell32.SHFileOperationW
                SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCT)]
                SHFileOperationW.restype = wintypes.INT
                
                # 路径需要以双 null 结尾
                path = str(file_path) + '\x00'
                
                op = SHFILEOPSTRUCT()
                op.hwnd = None
                op.wFunc = FO_DELETE
                op.pFrom = path
                op.pTo = None
                op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
                op.fAnyOperationsAborted = False
                op.hNameMappings = None
                op.lpszProgressTitle = None
                
                result = SHFileOperationW(ctypes.byref(op))
                if result != 0:
                    raise Exception(f"SHFileOperation failed with code {result}")
                    
            elif system == "Darwin":  # macOS
                # macOS: 使用 osascript 移至废纸篓
                script = f'tell application "Finder" to delete POSIX file "{file_path}"'
                subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
                
            else:  # Linux
                # Linux: 尝试使用 gio trash 或 trash-cli
                try:
                    subprocess.run(["gio", "trash", str(file_path)], check=True, capture_output=True)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    try:
                        subprocess.run(["trash-put", str(file_path)], check=True, capture_output=True)
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        # 如果没有回收站工具，直接删除
                        file_path.unlink()
                        
        except Exception as e:
            # 如果移至回收站失败，记录错误但仍删除数据库记录
            print(f"Warning: Failed to move file to recycle bin: {e}")
            # 尝试直接删除文件
            try:
                if file_path.exists():
                    file_path.unlink()
            except Exception as delete_error:
                print(f"Warning: Failed to delete file: {delete_error}")
    
    # 删除数据库记录
    repo.delete_files([file_id])
    repo.session.commit()
    # 文件数量变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    return {"success": True}


@router.put("/files/{file_id}/rename", response_model=FileSummaryDTO)
async def rename_file(
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

    try:
        old_path.rename(new_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to rename file: {exc}") from exc

    meta = build_file_meta(new_path)
    file_row = repo.upsert_file(meta, existing_id=file.id)
    repo.session.commit()
    # 重命名仅改变文件名，不影响目录结构本身，但 folder_tree 节点文件计数无变化；
    # 仍然失效，避免 file_count 缓存与实际不一致（旧文件名/新文件名属同一目录）
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")

    return FileSummaryDTO(
        id=file_row.id,
        name=file_row.name,
        path=file_row.path,
        type=file_row.type,
        size=file_row.size,
        modified_at=file_row.modified_at,
        duration=file_row.duration,
        tag_ids=[t.id for t in file_row.tags],
    )


@router.post("/files/move", response_model=FileBatchResultDTO)
async def move_files(
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

        moved_files.append(FileSummaryDTO(
            id=file_row.id,
            name=file_row.name,
            path=file_row.path,
            type=file_row.type,
            size=file_row.size,
            modified_at=file_row.modified_at,
            duration=file_row.duration,
            tag_ids=[t.id for t in file_row.tags],
        ))

    repo.session.commit()
    # 文件结构/数量变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    return FileBatchResultDTO(files=moved_files, target_dir=target_dir.as_posix())


@router.post("/files/copy", response_model=FileBatchResultDTO)
async def copy_files(
    payload: FileCopyRequestDTO,
    repo: Repo = Depends(get_repo),
):
    """复制文件到指定目录（副本入库，不含原标签）"""
    target_dir = Path(payload.target_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target directory not found")

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
            shutil.copy2(str(source_path), str(dest_path))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to copy file: {exc}") from exc

        meta = build_file_meta(dest_path)
        # 副本作为全新记录入库（不传 existing_id）
        file_row = repo.upsert_file(meta)
        copied_files.append(FileSummaryDTO(
            id=file_row.id,
            name=file_row.name,
            path=file_row.path,
            type=file_row.type,
            size=file_row.size,
            modified_at=file_row.modified_at,
            duration=file_row.duration,
            tag_ids=[],
        ))

    repo.session.commit()
    # 文件结构/数量变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")
    return FileBatchResultDTO(files=copied_files, target_dir=target_dir.as_posix())


# ========== 标签相关 API ==========

@router.get("/tags", response_model=List[TagDTO])
async def list_tags(
    root: str | None = None,
    repo: Repo = Depends(get_repo),
):
    """获取所有标签
    
    Args:
        root: 可选的工作目录路径，用于过滤标签的工作空间
    """
    tags = repo.list_tags(root=root)
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
async def create_tag(
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
async def get_tag(
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
async def update_tag(
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
    # parent_id: None 表示不更新；0 表示清除父标签；正整数表示设置父标签
    if update.parent_id is not None:
        tag.parent_id = None if update.parent_id == 0 else update.parent_id

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


@router.delete("/tags/{tag_id}")
async def delete_tag(
    tag_id: int,
    repo: Repo = Depends(get_repo),
):
    """删除标签"""
    repo.delete_tag(tag_id)
    repo.session.commit()
    return {"success": True}


@router.post("/tags/batch-assign")
async def batch_assign_tags(
    file_ids: List[int],
    tag_ids: List[int],
    repo: Repo = Depends(get_repo),
):
    """批量为文件添加标签"""
    repo.attach_tags_to_files(file_ids, tag_ids)
    repo.session.commit()
    return {"success": True, "files": len(file_ids), "tags": len(tag_ids)}


# ========== 工作区扫描 API ==========

@router.post("/workspace/scan")
async def scan_workspace(
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
async def get_workspace_stats(
    repo: Repo = Depends(get_repo),
):
    """获取工作区统计"""
    from sqlalchemy import func
    
    total_files = repo.session.query(func.count(File.id)).scalar() or 0
    total_tags = repo.session.query(func.count(Tag.id)).scalar() or 0
    
    # 按类型统计
    type_stats = repo.session.query(
        File.type, func.count(File.id)
    ).group_by(File.type).all()
    
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
        dir_names.sort(key=str.lower)

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
async def get_folder_tree(
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
async def get_folder_contents(
    path: str,
    offset: int = 0,
    limit: int = 500,
    sort_by: str = "name",
    sort_desc: bool = False,
    repo: Repo = Depends(get_repo),
):
    """获取指定文件夹的直接子文件（SQL 层过滤，不加载深层文件）"""
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
    order_expr = sa_desc(sort_col) if sort_desc else asc(sort_col)

    # 数据查询（LIMIT/OFFSET 在 SQL 层）
    data_stmt = (
        select(File)
        .where(*base_where)
        .order_by(order_expr)
        .offset(offset)
        .limit(limit)
    )
    page_files = list(repo.session.execute(data_stmt).scalars())

    file_dtos = [
        FileSummaryDTO(
            id=f.id,
            name=f.name,
            path=f.path,
            type=f.type,
            size=f.size,
            modified_at=f.modified_at,
            duration=f.duration,
            tag_ids=[t.id for t in f.tags],
        )
        for f in page_files
    ]

    return FolderContentsDTO(
        path=path,
        files=file_dtos,
        total=total,
        has_more=offset + limit < total,
    )


@router.post("/folders/create", response_model=FolderCreateResultDTO)
async def create_folder(
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

    return FolderCreateResultDTO(name=target_path.name, path=target_path.as_posix())


@router.post("/folders/delete")
async def delete_folder(
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
        File.path.like(folder_posix + "/%") | (File.path == folder_posix)
    ).all()
    file_ids = [f.id for f in files_in_folder]
    if file_ids:
        repo.delete_files(file_ids)
        repo.session.commit()

    # 物理删除目录
    try:
        shutil.rmtree(str(folder_path))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete folder: {exc}") from exc

    # 文件夹结构变化，失效 folder_tree 缓存
    from ..core.query_cache import get_query_cache
    get_query_cache().invalidate_pattern("folder:tree:")

    return {"deleted": folder_path.as_posix(), "files_removed": len(file_ids)}


# ========== 健康检查 ==========

@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "0.0.1"}


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
async def export_tags(
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

    try:
        payload = parse_thpack(raw)
    except ThpackFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    match_result = match_files(repo, payload, workspace)
    token = get_import_store().create(payload, match_result, workspace)
    return _build_preview_dto(token, payload, workspace, repo, match_result)


@router.post("/tags/import/relocate", response_model=ImportPreviewDTO)
async def import_relocate(
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
async def import_commit(
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
