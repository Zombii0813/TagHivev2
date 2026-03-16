"""TagHive Python Sidecar - FastAPI Application"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

from app.api import router
from app.api.websocket import sio
from app.db import init_db
from app.config import settings

# 配置日志 - 使用自定义格式器避免 uvicorn 的 isatty 问题
class SafeFormatter(logging.Formatter):
    """安全的日志格式器，不依赖 sys.stdout.isatty()"""
    def __init__(self, fmt=None, datefmt=None, style='%', validate=True):
        super().__init__(fmt, datefmt, style, validate)
    
    def format(self, record):
        return super().format(record)

# 配置根日志记录器
handler = logging.StreamHandler(sys.stderr if sys.stderr else open(os.devnull, 'w'))
handler.setFormatter(SafeFormatter(
    fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
))

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    logger.info(f"Initializing database at {settings.db_path}")
    init_db(Path(settings.db_path))
    
    # 启动文件监控服务
    from app.services.watch_service import WatchService
    app.state.watch_service = WatchService()
    
    logger.info("TagHive Sidecar started successfully")
    yield
    
    # 关闭时清理资源
    if hasattr(app.state, 'watch_service'):
        app.state.watch_service.stop()
    logger.info("TagHive Sidecar stopped")


# 创建 FastAPI 应用
app = FastAPI(
    title="TagHive API",
    description="TagHive Python Sidecar API",
    version="0.0.1",
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该限制为 Tauri 应用的实际来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载 REST API
app.include_router(router)

# 挂载 Socket.IO
socket_app = socketio.ASGIApp(sio, other_asgi_app=app)


# 用于直接运行的入口
def main():
    """主入口函数"""
    import uvicorn
    
    port = int(os.environ.get("TAGHIVE_PORT", 8721))
    host = os.environ.get("TAGHIVE_HOST", "127.0.0.1")
    
    logger.info(f"Starting TagHive Sidecar on {host}:{port}")
    
    # 禁用 reload 功能，避免 watchfiles 监控日志文件导致循环
    # sidecar 进程不需要热重载功能
    # 禁用默认日志配置，使用我们自己的配置
    uvicorn.run(
        "app.main:socket_app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        log_config=None,  # 禁用 uvicorn 的默认日志配置
    )


if __name__ == "__main__":
    main()
