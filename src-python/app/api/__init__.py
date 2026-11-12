"""API 模块"""

from fastapi import APIRouter

from .routes import router as main_router
from .media import router as media_router
from .thumbnails import router as thumbnail_router

# 合并所有路由
router = APIRouter()
router.include_router(main_router)
router.include_router(thumbnail_router)
router.include_router(media_router)

__all__ = ["router"]
