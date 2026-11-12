"""按当前浏览范围查看时长覆盖率及主动补探测。"""

import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select

from .models import SearchQueryDTO
from .routes import get_repo
from .threaded import threaded
from ..core.search import SearchQuery
from ..db import Repo, get_session
from ..db.models import File
from ..utils.media_info import extract_media_info

router = APIRouter(prefix="/api/media")
_lock = threading.Lock()
_cancel = threading.Event()
_state = {"running": False, "processed": 0, "total": 0, "failed": 0, "cancelled": False}


class MediaScope(SearchQueryDTO):
    """媒体范围，支持仅查看当前层级。"""
    direct_root: str | None = None


def _statement(repo: Repo, payload: MediaScope):
    """复用搜索条件，限制为媒体文件。"""
    query = SearchQuery(**payload.model_dump(exclude={"direct_root", "offset", "limit"}))
    statement = repo._search_statement(query).where(File.type.in_(("video", "audio")))
    if payload.direct_root:
        statement = statement.where(File.parent_dir == Path(payload.direct_root).as_posix())
    return statement


@router.post("/coverage")
@threaded
def coverage(payload: MediaScope, repo: Repo = Depends(get_repo)):
    """返回当前范围内总媒体数、已探测数和有效时长数。"""
    rows = _statement(repo, payload).subquery()
    total, probed, known = repo.session.execute(select(
        func.count(), func.count().filter(rows.c.media_probed == 1),
        func.count().filter(rows.c.duration.is_not(None)),
    ).select_from(rows)).one()
    return {"total": total, "probed": probed, "known": known}


@router.get("/probe")
def probe_status():
    """读取单个全局补探测任务的进度。"""
    with _lock:
        return dict(_state)


@router.delete("/probe")
def cancel_probe():
    """在当前文件探测结束后取消任务。"""
    _cancel.set()
    return {"success": True}


@router.post("/probe")
@threaded
def start_probe(payload: MediaScope, repo: Repo = Depends(get_repo)):
    """固定最多 1000 项的目标快照，以单个守护线程补探测。"""
    rows = list(repo.session.execute(_statement(repo, payload)
                .where(func.coalesce(File.media_probed, 0) == 0).order_by(File.id).limit(1000)).scalars())
    targets = [(f.id, f.path, f.size, f.modified_at) for f in rows]
    with _lock:
        if _state["running"]:
            raise HTTPException(409, "已有补探测任务正在运行")
        _cancel.clear()
        _state.update(running=True, task_id=uuid.uuid4().hex, processed=0, total=len(targets), failed=0, cancelled=False)

    def worker():
        """逐项检查签名并写入，取消或进程退出时停止。"""
        try:
            for file_id, path, size, modified in targets:
                if _cancel.is_set():
                    break
                try:
                    info = extract_media_info(Path(path))
                    with get_session() as session:
                        current = session.get(File, file_id)
                        if current and (current.path, current.size, current.modified_at) == (path, size, modified):
                            Repo(session).update_media_info(file_id, info.duration, info.width, info.height, info.bitrate)
                            session.commit()
                    with _lock:
                        _state["failed"] += int(info.duration is None)
                except Exception:
                    with _lock:
                        _state["failed"] += 1
                finally:
                    with _lock:
                        _state["processed"] += 1
        finally:
            with _lock:
                _state.update(running=False, cancelled=_cancel.is_set())

    threading.Thread(target=worker, name="media-probe", daemon=True).start()
    return probe_status()
