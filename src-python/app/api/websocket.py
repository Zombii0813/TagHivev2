"""WebSocket 事件处理 - Socket.IO"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import socketio

from ..db import get_session, Repo
from ..core.indexer import build_file_meta
from ..services.watch_service import WatchService

logger = logging.getLogger(__name__)

# 创建 Socket.IO 服务器
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True,
)


# 存储连接状态
connected_clients: set[str] = set()
active_watches: dict[str, WatchService] = {}


@sio.event
async def connect(sid: str, environ: dict):
    """客户端连接"""
    connected_clients.add(sid)
    logger.info(f"Client connected: {sid}")
    await sio.emit("connected", {"sid": sid}, room=sid)


@sio.event
async def disconnect(sid: str):
    """客户端断开连接"""
    connected_clients.discard(sid)
    
    # 停止该客户端的文件监控
    if sid in active_watches:
        active_watches[sid].stop()
        del active_watches[sid]
    
    logger.info(f"Client disconnected: {sid}")


@sio.event
async def ping(sid: str, data: dict):
    """心跳检测"""
    await sio.emit("pong", {"timestamp": data.get("timestamp")}, room=sid)


@sio.event
async def subscribe_workspace(sid: str, data: dict):
    """订阅工作区文件变更"""
    workspace_path = data.get("path")
    if not workspace_path:
        await sio.emit("error", {"message": "Workspace path required"}, room=sid)
        return
    
    path = Path(workspace_path)
    if not path.exists():
        await sio.emit("error", {"message": f"Path not found: {workspace_path}"}, room=sid)
        return
    
    # 停止之前的监控
    if sid in active_watches:
        active_watches[sid].stop()
    
    # 创建新的监控服务
    watch_service = WatchService()
    
    def on_file_changed(file_path: Path):
        """文件变更回调"""
        asyncio.create_task(_handle_file_change(sid, file_path, "changed"))
    
    def on_file_deleted(file_path: Path):
        """文件删除回调"""
        asyncio.create_task(_handle_file_change(sid, file_path, "deleted"))
    
    watch_service.start(path, on_change=on_file_changed, on_delete=on_file_deleted)
    active_watches[sid] = watch_service
    
    await sio.emit("subscribed", {"path": workspace_path}, room=sid)
    logger.info(f"Client {sid} subscribed to workspace: {workspace_path}")


@sio.event
async def unsubscribe_workspace(sid: str, data: dict):
    """取消订阅工作区"""
    if sid in active_watches:
        active_watches[sid].stop()
        del active_watches[sid]
    
    await sio.emit("unsubscribed", {}, room=sid)


async def _handle_file_change(sid: str, file_path: Path, event_type: str):
    """处理文件变更事件"""
    try:
        session = get_session()
        try:
            repo = Repo(session)
            
            if event_type == "deleted":
                # 查找并删除文件记录
                file_row = repo.get_file_by_path(str(file_path))
                if file_row:
                    repo.delete_files([file_row.id])
                    session.commit()
                    await sio.emit("file_deleted", {
                        "path": str(file_path),
                        "file_id": file_row.id,
                    }, room=sid)
            else:
                # 更新或创建文件记录
                if file_path.exists():
                    meta = build_file_meta(file_path)
                    existing = repo.get_file_by_path(str(file_path))
                    file_row = repo.upsert_file(meta, existing_id=existing.id if existing else None)
                    session.commit()
                    
                    # 获取标签信息
                    tags = [{"id": t.id, "name": t.name} for t in file_row.tags]
                    
                    await sio.emit("file_changed", {
                        "path": str(file_path),
                        "file_id": file_row.id,
                        "name": file_row.name,
                        "type": file_row.type,
                        "size": file_row.size,
                        "tags": tags,
                        "event": "created" if not existing else "modified",
                    }, room=sid)
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error handling file change: {e}")
        await sio.emit("error", {"message": str(e)}, room=sid)


@sio.event
async def start_scan(sid: str, data: dict):
    """开始扫描工作区"""
    from ..services.scan_service import ScanService
    
    workspace_path = data.get("path")
    if not workspace_path:
        await sio.emit("scan_error", {"message": "Workspace path required"}, room=sid)
        return
    
    path = Path(workspace_path)
    if not path.exists():
        await sio.emit("scan_error", {"message": f"Path not found: {workspace_path}"}, room=sid)
        return
    
    # 创建进度队列和事件
    progress_queue: asyncio.Queue = asyncio.Queue()
    scan_completed_event = asyncio.Event()
    scan_result = {"total": 0, "error": None}
    
    async def progress_sender():
        """异步发送进度更新"""
        while not scan_completed_event.is_set():
            try:
                # 使用 timeout 避免阻塞
                progress_data = await asyncio.wait_for(
                    progress_queue.get(), 
                    timeout=0.1
                )
                await sio.emit("scan_progress", progress_data, room=sid)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Progress sender error: {e}")
    
    def scan_worker():
        """在后台线程中执行扫描"""
        session = get_session()
        try:
            service = ScanService(session)
            
            def on_progress(count: int, total: int, percentage: int, current_file: str):
                """同步进度回调，将数据放入队列"""
                try:
                    # 使用 asyncio.run_coroutine_threadsafe 在线程安全地将数据放入队列
                    asyncio.run_coroutine_threadsafe(
                        progress_queue.put({
                            "count": count,
                            "total": total,
                            "percentage": percentage,
                            "path": workspace_path,
                            "current_file": current_file,
                        }),
                        loop
                    )
                except Exception as e:
                    logger.error(f"Progress callback error: {e}")
            
            total = service.scan_workspace(path, on_progress=on_progress)
            scan_result["total"] = total
        except Exception as e:
            logger.error(f"Scan error: {e}")
            scan_result["error"] = str(e)
        finally:
            session.close()
            scan_completed_event.set()
    
    # 获取当前事件循环
    loop = asyncio.get_event_loop()
    
    # 启动进度发送任务
    progress_task = asyncio.create_task(progress_sender())
    
    # 在后台线程中运行扫描
    scan_task = asyncio.create_task(asyncio.to_thread(scan_worker))
    
    await sio.emit("scan_started", {"path": workspace_path}, room=sid)
    
    # 等待扫描完成
    try:
        await scan_task
        
        # 等待进度发送完成
        await asyncio.sleep(0.5)  # 给进度发送一点时间
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass
        
        if scan_result["error"]:
            await sio.emit("scan_error", {"message": scan_result["error"]}, room=sid)
        else:
            await sio.emit("scan_completed", {
                "path": workspace_path,
                "total": scan_result["total"],
            }, room=sid)
    except Exception as e:
        logger.error(f"Scan task error: {e}")
        await sio.emit("scan_error", {"message": str(e)}, room=sid)
