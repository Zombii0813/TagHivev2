"""缩略图 API 路由"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, Response

from ..services.thumbnail_service import get_thumbnail_service
from ..core.async_thumbnail import (
    get_async_thumbnail_generator,
    Priority,
    ThumbnailPrefetcher,
)

router = APIRouter(prefix="/api/thumbnails")

# 1×1 透明 PNG，作为缓存未命中时的占位响应
_PLACEHOLDER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae42"
    "6082"
)


def _placeholder_response(file_id: int, file_path: str, size: str) -> Response:
    """返回透明 PNG 占位 + 标记 header；客户端通过 X-Thumb-Status 识别异步生成中。"""
    return Response(
        content=_PLACEHOLDER_PNG,
        media_type="image/png",
        headers={
            "X-Thumb-Status": "pending",
            "X-Thumb-File-Id": str(file_id),
            "X-Thumb-Size": size,
            # 缓存极短时间，避免反复请求；前端会通过 thumbnail_ready 事件主动刷新
            "Cache-Control": "no-store",
        },
    )


@router.get("/by-path")
async def get_thumbnail_by_path(path: str, size: str = "medium"):
    """按任意本地文件路径获取缩略图（用于 explorer 目录自定义封面）。

    与按 file_id 的端点不同，此处不要求文件已入库；缓存命中即返，
    未命中则同步生成（封面数量少，同步开销可接受）。
    """
    from pathlib import Path as _Path

    file_path = _Path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    service = get_thumbnail_service()
    # POSIX 形式作为缓存 key，与前端传入路径保持一致
    posix_path = file_path.as_posix()
    thumb_path = service.get_thumbnail_path(posix_path, size)
    if not thumb_path.exists():
        result = service.generate_thumbnail(posix_path, size)
        if result is None or not thumb_path.exists():
            raise HTTPException(status_code=415, detail="Cannot generate thumbnail for this file")
    return FileResponse(str(thumb_path))


@router.get("/{file_id}")
async def get_thumbnail(file_id: int, size: str = "medium", async_mode: bool = False):
    """获取文件缩略图（缓存命中即返；未命中异步生成 + 占位响应）"""
    from ..db import get_session, Repo

    session = get_session()
    try:
        repo = Repo(session)
        file = repo.get_file_by_id(file_id)

        if not file:
            raise HTTPException(status_code=404, detail="File not found")

        if file.type not in ("image", "video"):
            raise HTTPException(status_code=400, detail="File type not supported")

        # 显式异步模式：保留旧行为
        if async_mode:
            generator = get_async_thumbnail_generator()
            generator.generate_async(file.path, size, Priority.HIGH, file_id)
            return JSONResponse({
                "status": "queued",
                "file_id": file_id,
                "message": "Thumbnail generation queued",
            })

        # 默认模式：缓存命中走 FileResponse；未命中则异步入队 + 透明占位
        service = get_thumbnail_service()
        thumb_path = service.get_thumbnail_path(file.path, size)
        if thumb_path.exists():
            return FileResponse(str(thumb_path))

        # 缓存未命中：入队高优先级（前台请求 = 用户正在看）
        generator = get_async_thumbnail_generator()
        generator.generate_async(file.path, size, Priority.HIGH, file_id)
        return _placeholder_response(file_id, file.path, size)

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
