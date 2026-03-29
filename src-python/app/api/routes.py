"""API 路由"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from typing import List
from mimetypes import guess_type

from fastapi import APIRouter, Depends, HTTPException
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
    FileRenameRequestDTO,
    FileMoveRequestDTO,
    FileCopyRequestDTO,
    FileBatchResultDTO,
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
    """构建搜索结果"""
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
    
    # 获取总数
    all_results = repo.search(search_query)
    total = len(all_results)
    
    # 分页 - 默认每次加载 500 条，支持最大 10000 条
    limit = query.limit or 500
    start = query.offset
    end = start + limit
    page_results = all_results[start:end]
    
    # 转换为 DTO
    file_ids = [r.file_id for r in page_results]
    files = repo.get_files_by_ids(file_ids)
    file_map = {f.id: f for f in files}
    
    file_dtos = []
    for r in page_results:
        f = file_map.get(r.file_id)
        if f:
            tag_ids = [t.id for t in f.tags]
            file_dtos.append(FileSummaryDTO(
                id=f.id,
                name=f.name,
                path=f.path,
                type=f.type,
                size=f.size,
                modified_at=f.modified_at,
                duration=f.duration,
                tag_ids=tag_ids,
            ))
    
    return SearchResultDTO(
        files=file_dtos,
        total=total,
        has_more=end < total,
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
    """将文件移动到指定目录（工作区内移动）"""
    target_dir = Path(payload.target_dir)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Target directory not found")

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
    ), workspace=spec.workspace)
    repo.session.commit()

    return TagDTO(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        icon=tag.icon,
        description=tag.description,
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

    repo.session.commit()

    return TagDTO(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        icon=tag.icon,
        description=tag.description,
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
    """获取文件夹树结构"""
    root_path = Path(root)
    if not root_path.exists():
        raise HTTPException(status_code=404, detail="Root path not found")
    
    folders, root_file_count = _build_folder_tree(root, repo)
    
    # 计算总文件夹数
    def count_folders(nodes: List[FolderNodeDTO]) -> int:
        count = len(nodes)
        for node in nodes:
            count += count_folders(node.children)
        return count
    
    return FolderTreeDTO(
        root_path=root,
        folders=folders,
        total_folders=count_folders(folders),
        root_file_count=root_file_count,
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
    """获取指定文件夹的内容"""
    folder_path = Path(path)
    if not folder_path.exists():
        raise HTTPException(status_code=404, detail="Folder not found")
    
    # 构建查询
    folder_posix = folder_path.as_posix()
    # 匹配直接在该文件夹下的文件（不包括子文件夹）
    stmt = select(File).where(
        File.path.like(folder_posix.rstrip("/") + "/%")
    )
    
    # 排除子文件夹中的文件 - 只获取直接子文件
    from sqlalchemy import func
    
    # 获取所有候选文件
    all_files = list(repo.session.execute(stmt).scalars())
    
    # 过滤出直接在该文件夹下的文件
    direct_files = []
    for f in all_files:
        file_parent = Path(f.path).parent.as_posix()
        if file_parent == folder_posix:
            direct_files.append(f)
    
    total = len(direct_files)
    
    # 排序
    sort_key_map = {
        "name": lambda f: f.name.lower(),
        "size": lambda f: f.size,
        "modified_at": lambda f: f.modified_at or 0,
        "duration": lambda f: f.duration or 0,
    }
    
    sort_key = sort_key_map.get(sort_by, sort_key_map["name"])
    direct_files.sort(key=sort_key, reverse=sort_desc)
    
    # 分页
    page_files = direct_files[offset:offset + limit]
    
    # 转换为 DTO
    file_dtos = []
    for f in page_files:
        tag_ids = [t.id for t in f.tags]
        file_dtos.append(FileSummaryDTO(
            id=f.id,
            name=f.name,
            path=f.path,
            type=f.type,
            size=f.size,
            modified_at=f.modified_at,
            duration=f.duration,
            tag_ids=tag_ids,
        ))
    
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

    return FolderCreateResultDTO(name=target_path.name, path=target_path.as_posix())


# ========== 健康检查 ==========

@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "0.0.1"}
