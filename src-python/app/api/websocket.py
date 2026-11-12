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
from ..services.file_operations import serialized_filesystem
from ..security import ALLOWED_ORIGINS, valid_token

logger = logging.getLogger(__name__)

# 创建 Socket.IO 服务器
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=ALLOWED_ORIGINS,
    logger=False,
    engineio_logger=False,
)


# 存储连接状态
connected_clients: set[str] = set()
active_watches: dict[str, WatchService] = {}

# 主事件循环引用，供工作线程通过 run_coroutine_threadsafe 调度协程
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def get_main_loop() -> Optional[asyncio.AbstractEventLoop]:
    return _main_loop


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


async def broadcast_thumbnail_ready(file_path: str, size: str, success: bool) -> None:
    """向所有连接的客户端广播缩略图就绪事件（在事件循环线程调用）。"""
    if not connected_clients:
        return
    payload = {"file_path": file_path, "size": size, "success": success}
    await sio.emit("thumbnail_ready", payload)


async def broadcast_folder_tree_changed(workspace: str | None = None) -> None:
    """广播文件夹结构变更事件，触发前端目录树重载。

    Args:
        workspace: 受影响的工作区根路径（POSIX）；为空表示所有工作区
    """
    if not connected_clients:
        return
    await sio.emit("folder_tree_changed", {"workspace": workspace or ""})


def schedule_folder_tree_changed(workspace: str | None = None) -> None:
    """从同步路由处理函数调度目录树变更广播到主事件循环。

    路由是 async 协程，可直接 await broadcast；该 helper 用于
    无法 await 的场景（线程回调等），保持调用方一致。
    """
    loop = get_main_loop()
    if loop is None or not connected_clients:
        return
    try:
        asyncio.run_coroutine_threadsafe(
            broadcast_folder_tree_changed(workspace), loop
        )
    except Exception as e:
        logger.error(f"schedule_folder_tree_changed failed: {e}")


def schedule_thumbnail_broadcast(result, task) -> None:
    """异步生成器工作线程的回调：把广播协程调度到主事件循环。

    `result` 来自 app.core.async_thumbnail.ThumbnailResult；
    `task`   来自 app.core.async_thumbnail.ThumbnailTask。
    """
    loop = get_main_loop()
    if loop is None or not connected_clients:
        return
    try:
        asyncio.run_coroutine_threadsafe(
            broadcast_thumbnail_ready(result.file_path, result.size, result.success),
            loop,
        )
    except Exception as e:
        logger.error(f"schedule_thumbnail_broadcast failed: {e}")


@sio.event
async def connect(sid: str, environ: dict, auth: dict | None = None):
    """客户端连接"""
    if not valid_token((auth or {}).get("token")):
        return False
    connected_clients.add(sid)
    logger.info(f"Client connected: {sid}")
    await sio.emit("connected", {"sid": sid}, room=sid)


@sio.event
async def disconnect(sid: str):
    """客户端断开连接"""
    connected_clients.discard(sid)

    # 停止该客户端的文件监控
    if sid in active_watches:
        await asyncio.to_thread(active_watches[sid].stop)
        del active_watches[sid]

    logger.info(f"Client disconnected: {sid}")


@sio.event
async def ping(sid: str, data: dict):
    """心跳检测"""
    await sio.emit("pong", {"timestamp": data.get("timestamp")}, room=sid)


@sio.event
async def subscribe_workspace(sid: str, data: dict):
    """订阅工作区文件变更"""
    paths = data.get("paths") or ([data["path"]] if data.get("path") else [])
    if sid in active_watches:
        await asyncio.to_thread(active_watches.pop(sid).stop)
    if not paths:
        return
    loop = asyncio.get_running_loop()
    service = WatchService()

    def dispatch(path: Path, kind: str, destination: Path | None = None):
        """从 watchdog 线程向主循环提交事件。"""
        asyncio.run_coroutine_threadsafe(_handle_file_change(sid, path, kind, destination), loop)

    for raw_path in dict.fromkeys(paths):
        path = Path(raw_path)
        if path.is_dir():
            await asyncio.to_thread(service.start, path,
                on_change=lambda p: dispatch(p, "changed"),
                on_delete=lambda p: dispatch(p, "deleted"),
                on_move=lambda p, d: dispatch(p, "moved", d),
                on_directory=lambda p: dispatch(p, "directory"))
    active_watches[sid] = service
    await sio.emit("subscribed", {"paths": paths}, room=sid)


@sio.event
async def unsubscribe_workspace(sid: str, data: dict):
    """取消订阅工作区"""
    if sid in active_watches:
        await asyncio.to_thread(active_watches[sid].stop)
        del active_watches[sid]

    await sio.emit("unsubscribed", {}, room=sid)


_change_lock = asyncio.Lock()


@serialized_filesystem
def _apply_file_change(file_path: Path, event_type: str, destination: Path | None):
    """在线程内独占会话，同步外部文件操作并保留移动文件的 ID/标签。"""
    from sqlalchemy import select
    from ..db.models import File
    from ..utils.paths import path_prefix
    session = get_session()
    try:
        repo = Repo(session)
        if event_type == "moved" and destination and destination.exists():
            rows = list(session.scalars(select(File).where(path_prefix(File.path, file_path, include_self=True))))
            for row in rows:
                relative = Path(row.path).relative_to(file_path) if row.path != file_path.as_posix() else Path()
                target = destination / relative if relative != Path() else destination
                if target.is_file():
                    repo.upsert_file(build_file_meta(target), existing_id=row.id)
            session.flush()
            # 外部移入目录也需要发现此前没有索引的子文件。
            if destination.is_dir():
                from ..services.scan_service import ScanService
                ScanService(session).scan_workspace(destination)
            elif not rows:
                repo.upsert_file(build_file_meta(destination))
        elif event_type == "deleted" or (event_type == "directory" and not file_path.exists()):
            rows = list(session.scalars(select(File).where(path_prefix(File.path, file_path, include_self=True))))
            ids = [row.id for row in rows if not Path(row.path).exists()]
            repo.delete_files(ids)
        elif file_path.is_file():
            existing = repo.get_file_by_path(file_path.as_posix())
            repo.upsert_file(build_file_meta(file_path), existing_id=existing.id if existing else None)
        elif file_path.is_dir():
            from ..services.scan_service import ScanService
            ScanService(session).scan_workspace(file_path)
        session.commit()
        repo.clear_all_caches()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


async def _handle_file_change(sid: str, file_path: Path, event_type: str, destination: Path | None = None):
    """串行处理监控事件，数据库与磁盘任务放入线程。"""
    try:
        async with _change_lock:
            await asyncio.to_thread(_apply_file_change, file_path, event_type, destination)
        await broadcast_folder_tree_changed()
        await sio.emit("file_deleted" if event_type == "deleted" else "file_changed", {
            "path": file_path.as_posix(), "event": event_type,
            "destination": destination.as_posix() if destination else None,
        })
    except Exception as exc:
        logger.exception("File watch update failed")
        await sio.emit("error", {"message": str(exc)}, room=sid)


_scan_queue_lock = asyncio.Lock()
_scan_jobs = {}


@sio.event
async def cancel_scan(sid: str, data: dict):
    """取消当前客户端的活动及排队扫描。"""
    for job in list(_scan_jobs.values()):
        if job["sid"] == sid and (not data.get("task_id") or job["id"] == data["task_id"]):
            job["cancel"].set()


@sio.event
async def start_scan(sid: str, data: dict):
    """将工作区扫描放入全局串行队列，合并进度并支持取消。"""
    import threading
    import uuid
    from ..services.scan_service import ScanService

    path = Path(data.get("path") or "")
    if not data.get("path") or not path.is_dir():
        await sio.emit("scan_error", {"message": "工作区不可访问", "remaining": sum(j["sid"] == sid for j in _scan_jobs.values())}, room=sid)
        return
    key = str(path.resolve()).lower()
    if any(job["key"] == key for job in _scan_jobs.values()) or len(_scan_jobs) >= 64:
        await sio.emit("scan_error", {"message": "扫描已排队或队列已满", "remaining": sum(j["sid"] == sid for j in _scan_jobs.values())}, room=sid)
        return
    task_id = uuid.uuid4().hex
    job = {"id": task_id, "sid": sid, "key": key, "cancel": threading.Event()}
    _scan_jobs[task_id] = job
    loop = asyncio.get_running_loop()
    latest = {}
    done = asyncio.Event()

    def on_progress(count, total, percentage, current_file):
        """只保留最新进度，避免扫描线程产生无界消息队列。"""
        payload = {"task_id": task_id, "count": count, "total": total, "percentage": percentage,
                   "path": path.as_posix(), "current_file": current_file}
        loop.call_soon_threadsafe(latest.update, payload)

    def worker():
        """使用独立会话执行可取消扫描。"""
        with get_session() as session:
            return ScanService(session).scan_workspace(path, on_progress=on_progress, cancel=job["cancel"])

    async def progress_sender():
        """限频发送最新任务进度。"""
        while not done.is_set():
            if latest:
                payload = dict(latest)
                latest.clear()
                await sio.emit("scan_progress", payload, room=sid)
            try:
                await asyncio.wait_for(done.wait(), 0.15)
            except asyncio.TimeoutError:
                pass

    await sio.emit("scan_queued", {"task_id": task_id, "path": path.as_posix()}, room=sid)
    sender = None
    try:
        async with _scan_queue_lock:
            await sio.emit("scan_started", {"task_id": task_id, "path": path.as_posix()}, room=sid)
            sender = asyncio.create_task(progress_sender())
            total = await asyncio.to_thread(worker)
            from ..core.query_cache import get_query_cache
            get_query_cache().clear()
            await broadcast_folder_tree_changed(path.as_posix())
        _scan_jobs.pop(task_id, None)
        await sio.emit("scan_completed", {"task_id": task_id, "path": path.as_posix(), "total": total,
                       "cancelled": job["cancel"].is_set(), "remaining": sum(j["sid"] == sid for j in _scan_jobs.values())}, room=sid)
    except Exception as exc:
        _scan_jobs.pop(task_id, None)
        await sio.emit("scan_error", {"task_id": task_id, "message": str(exc), "remaining": sum(j["sid"] == sid for j in _scan_jobs.values())}, room=sid)
    finally:
        done.set()
        if sender:
            await sender
        _scan_jobs.pop(task_id, None)
