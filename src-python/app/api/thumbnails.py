"""缩略图 API 路由"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..services.thumbnail_service import get_thumbnail_service

router = APIRouter(prefix="/api/thumbnails")


@router.get("/{file_id}")
async def get_thumbnail(file_id: int, size: str = "medium"):
    """获取文件缩略图
    
    Args:
        file_id: 文件 ID
        size: 缩略图尺寸 (small, medium, large)
    """
    from ..db import get_session, Repo
    
    session = get_session()
    try:
        repo = Repo(session)
        file = repo.get_file_by_id(file_id)
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        # 检查是否为支持的类型
        if file.type not in ("image", "video"):
            raise HTTPException(status_code=400, detail="File type not supported")
        
        # 生成缩略图
        service = get_thumbnail_service()
        thumb_url = service.generate_thumbnail(file.path, size)
        
        if not thumb_url:
            raise HTTPException(status_code=500, detail="Failed to generate thumbnail")
        
        # 返回文件
        thumb_path = thumb_url.replace("file://", "")
        return FileResponse(thumb_path)
        
    finally:
        session.close()


@router.post("/cleanup")
async def cleanup_thumbnails(max_age_days: int = 30):
    """清理过期缩略图缓存"""
    service = get_thumbnail_service()
    count = service.cleanup_cache(max_age_days)
    return {"cleaned": count}


@router.get("/stats")
async def get_thumbnail_stats():
    """获取缩略图缓存统计"""
    service = get_thumbnail_service()
    count, size = service.get_cache_size()
    return {
        "file_count": count,
        "total_size_bytes": size,
        "total_size_mb": round(size / (1024 * 1024), 2),
    }
