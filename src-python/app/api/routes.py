"""API 路由"""

from __future__ import annotations

from pathlib import Path
from typing import List
from mimetypes import guess_type

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from sqlalchemy import select
from ..db import get_session, Repo
from ..db.models import File, Tag
from ..core.search import SearchQuery
from ..services.scan_service import ScanService
from .models import (
    FileDTO,
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
)

router = APIRouter(prefix="/api")


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


# ========== 标签相关 API ==========

@router.get("/tags", response_model=List[TagDTO])
async def list_tags(
    root: str | None = None,
    repo: Repo = Depends(get_repo),
):
    """获取所有标签
    
    Args:
        root: 可选的工作目录路径，如果提供则只返回该目录下有关联文件的标签
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
        description=spec.description,
    ), workspace=spec.workspace)
    repo.session.commit()
    
    return TagDTO(
        id=tag.id,
        name=tag.name,
        color=tag.color,
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
    if update.description is not None:
        tag.description = update.description
    
    repo.session.commit()
    
    return TagDTO(
        id=tag.id,
        name=tag.name,
        color=tag.color,
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
    from sqlalchemy import func
    
    root = Path(root_path)
    if not root.exists():
        return [], 0
    
    # 获取该根路径下的所有文件路径
    root_posix = root.as_posix()
    root_pattern = root_posix.rstrip("/") + "/%"
    
    stmt = select(File.path).where(File.path.like(root_pattern))
    file_paths = [str(row[0]) for row in repo.session.execute(stmt).all()]
    
    # 构建文件夹树
    folder_map: dict[str, FolderNodeDTO] = {}
    folder_file_counts: dict[str, int] = {}
    root_direct_file_count = 0  # 根目录下的直接文件数
    
    for file_path in file_paths:
        path_obj = Path(file_path)
        
        # 获取相对于根路径的相对路径
        try:
            rel_path = path_obj.relative_to(root)
        except ValueError:
            continue
        
        # 获取文件所在目录
        folder_dir = path_obj.parent.as_posix()
        
        # 如果文件直接在根目录下，统计到 root_direct_file_count
        if folder_dir == root_posix:
            root_direct_file_count += 1
            continue
        
        # 构建文件夹层级
        current_path = root
        current_node = None
        
        # 处理父文件夹
        for part in rel_path.parent.parts:
            if part == "." or not part:
                continue
            
            parent_path = current_path
            current_path = current_path / part
            current_path_str = current_path.as_posix()
            
            if current_path_str not in folder_map:
                node = FolderNodeDTO(
                    name=part,
                    path=current_path_str,
                    file_count=0,
                    children=[],
                    is_expanded=False,
                )
                folder_map[current_path_str] = node
                
                # 添加到父节点的 children
                parent_path_str = parent_path.as_posix()
                if parent_path_str == root_posix:
                    # 这是根的直接子文件夹
                    pass
                elif parent_path_str in folder_map:
                    parent_node = folder_map[parent_path_str]
                    if not any(c.path == current_path_str for c in parent_node.children):
                        parent_node.children.append(node)
            
            current_node = folder_map[current_path_str]
        
        # 统计文件数量
        folder_file_counts[folder_dir] = folder_file_counts.get(folder_dir, 0) + 1
    
    # 更新文件计数
    for folder_path, count in folder_file_counts.items():
        if folder_path in folder_map:
            folder_map[folder_path].file_count = count
    
    # 递归计算子文件夹的文件数
    def calc_total_files(node: FolderNodeDTO) -> int:
        total = node.file_count
        for child in node.children:
            total += calc_total_files(child)
        node.file_count = total
        return total
    
    # 获取根的直接子文件夹
    root_children: List[FolderNodeDTO] = []
    seen_paths = set()
    
    for node in folder_map.values():
        node_path = Path(node.path)
        try:
            rel_parts = node_path.relative_to(root).parts
            if len(rel_parts) == 1:
                # 这是根的直接子文件夹
                if node.path not in seen_paths:
                    calc_total_files(node)
                    root_children.append(node)
                    seen_paths.add(node.path)
        except ValueError:
            continue
    
    # 按名称排序
    root_children.sort(key=lambda x: x.name.lower())
    for node in root_children:
        node.children.sort(key=lambda x: x.name.lower())
    
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


# ========== 健康检查 ==========

@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "0.0.1"}
