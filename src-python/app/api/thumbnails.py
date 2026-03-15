"""缩略图 API 路由"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse

from ..services.thumbnail_service import get_thumbnail_service
from ..core.async_thumbnail import (
    get_async_thumbnail_generator,
    Priority,
    ThumbnailPrefetcher,
)

router = APIRouter(prefix="/api/thumbnails")


@router.get("/{file_id}")
async def get_thumbnail(file_id: int, size: str = "medium", async_mode: bool = False):
    """获取文件缩略图
    
    Args:
        file_id: 文件 ID
        size: 缩略图尺寸 (xs, small, medium, large, xl)
        async_mode: 是否使用异步模式生成
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
        
        if async_mode:
            # 异步模式：添加到队列，返回占位图
            generator = get_async_thumbnail_generator()
            generator.generate_async(file.path, size, Priority.HIGH, file_id)
            return JSONResponse({
                "status": "queued",
                "file_id": file_id,
                "message": "Thumbnail generation queued"
            })
        else:
            # 同步模式：立即生成
            service = get_thumbnail_service()
            thumb_url = service.generate_thumbnail(file.path, size)
            
            if not thumb_url:
                raise HTTPException(status_code=500, detail="Failed to generate thumbnail")
            
            # 返回文件
            thumb_path = thumb_url.replace("file://", "")
            return FileResponse(thumb_path)
        
    finally:
        session.close()


@router.post("/async/generate")
async def generate_thumbnail_async(file_id: int, size: str = "medium", priority: str = "normal"):
    """异步生成缩略图
    
    Args:
        file_id: 文件 ID
        size: 缩略图尺寸
        priority: 优先级 (high, normal, low)
    """
    from ..db import get_session, Repo
    
    session = get_session()
    try:
        repo = Repo(session)
        file = repo.get_file_by_id(file_id)
        
        if not file:
            raise HTTPException(status_code=404, detail="File not found")
        
        if file.type not in ("image", "video"):
            raise HTTPException(status_code=400, detail="File type not supported")
        
        # 获取异步生成器
        generator = get_async_thumbnail_generator()
        
        # 映射优先级
        priority_map = {
            "high": Priority.HIGH,
            "normal": Priority.NORMAL,
            "low": Priority.LOW,
        }
        prio = priority_map.get(priority, Priority.NORMAL)
        
        # 添加到队列
        success = generator.generate_async(file.path, size, prio, file_id)
        
        return {
            "status": "queued" if success else "failed",
            "file_id": file_id,
            "file_path": file.path,
            "size": size,
            "priority": priority,
        }
        
    finally:
        session.close()


@router.post("/async/batch")
async def generate_thumbnails_batch(file_ids: List[int], size: str = "medium"):
    """批量异步生成缩略图
    
    Args:
        file_ids: 文件 ID 列表
        size: 缩略图尺寸
    """
    from ..db import get_session, Repo
    
    session = get_session()
    try:
        repo = Repo(session)
        generator = get_async_thumbnail_generator()
        
        queued = 0
        failed = 0
        
        for file_id in file_ids:
            file = repo.get_file_by_id(file_id)
            if file and file.type in ("image", "video"):
                success = generator.generate_async(file.path, size, Priority.LOW, file_id)
                if success:
                    queued += 1
                else:
                    failed += 1
            else:
                failed += 1
        
        return {
            "status": "queued",
            "queued": queued,
            "failed": failed,
            "total": len(file_ids),
        }
        
    finally:
        session.close()


@router.post("/async/visible")
async def set_visible_files(file_paths: List[str]):
    """设置当前可见区域的文件列表（用于优先生成可见缩略图）
    
    Args:
        file_paths: 可见区域的文件路径列表
    """
    generator = get_async_thumbnail_generator()
    generator.set_visible_files(file_paths)
    
    # 高优先级生成可见文件的缩略图
    for file_path in file_paths:
        generator.generate_async(file_path, "medium", Priority.HIGH)
    
    return {
        "status": "ok",
        "visible_count": len(file_paths),
    }


@router.get("/async/results")
async def get_async_results():
    """获取异步生成的结果"""
    generator = get_async_thumbnail_generator()
    results = generator.get_results()
    
    return {
        "results": [
            {
                "file_path": r.file_path,
                "size": r.size,
                "success": r.success,
                "thumb_path": r.thumb_path,
                "error": r.error,
            }
            for r in results
        ],
        "count": len(results),
    }


@router.get("/async/stats")
async def get_async_stats():
    """获取异步生成统计"""
    generator = get_async_thumbnail_generator()
    stats = generator.get_stats()
    
    return stats


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
    
    # 获取异步生成器统计
    generator = get_async_thumbnail_generator()
    async_stats = generator.get_stats()
    
    return {
        "file_count": count,
        "total_size_bytes": size,
        "total_size_mb": round(size / (1024 * 1024), 2),
        "async_stats": async_stats,
    }
