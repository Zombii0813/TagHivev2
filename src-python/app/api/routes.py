"""API 路由"""

from __future__ import annotations

from pathlib import Path
from typing import List
from mimetypes import guess_type

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

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
    
    # 分页
    start = query.offset
    end = start + (query.limit or 100)
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
    """删除文件记录"""
    file = repo.get_file_by_id(file_id)
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
    
    repo.delete_files([file_id])
    repo.session.commit()
    return {"success": True}


# ========== 标签相关 API ==========

@router.get("/tags", response_model=List[TagDTO])
async def list_tags(
    repo: Repo = Depends(get_repo),
):
    """获取所有标签"""
    tags = repo.list_tags()
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
    """创建标签"""
    from ..core.tag_manager import TagSpec
    
    existing = repo.get_tag_by_name(spec.name)
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")
    
    tag = repo.create_tag(TagSpec(
        name=spec.name,
        color=spec.color,
        description=spec.description,
    ))
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
    """扫描工作区"""
    root = Path(workspace.path)
    if not root.exists():
        raise HTTPException(status_code=400, detail="Path does not exist")
    
    service = ScanService(repo.session)
    count = service.scan_workspace(root)
    
    return ScanProgressDTO(
        status="completed",
        count=count,
        message=f"Scanned {count} files",
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


# ========== 健康检查 ==========

@router.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "version": "0.0.1"}
