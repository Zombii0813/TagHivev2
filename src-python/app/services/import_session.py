"""导入预览的内存级 token 缓存

用于在 /api/tags/import/preview → relocate → commit 三步之间保留
解析后的 ExportPayload 和正在演进的 MatchResult，避免前端反复上传文件。

线程安全：使用 threading.Lock；TTL 默认 5 分钟。
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from .tag_transfer import ExportPayload, MatchResult


DEFAULT_TTL_SECONDS = 300  # 5 分钟


@dataclass
class _CacheEntry:
    """单条缓存项"""
    payload: ExportPayload
    match: MatchResult
    target_workspace: str
    expires_at: float


class ImportSessionStore:
    """导入会话的内存缓存（按 token 索引）"""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, _CacheEntry] = {}

    def _gc(self) -> None:
        """惰性清理过期条目"""
        now = time.time()
        expired = [k for k, v in self._entries.items() if v.expires_at < now]
        for k in expired:
            self._entries.pop(k, None)

    def create(
        self,
        payload: ExportPayload,
        match: MatchResult,
        target_workspace: str,
    ) -> str:
        """新建会话，返回 token"""
        with self._lock:
            self._gc()
            token = secrets.token_urlsafe(16)
            self._entries[token] = _CacheEntry(
                payload=payload,
                match=match,
                target_workspace=target_workspace,
                expires_at=time.time() + self._ttl,
            )
            return token

    def get(self, token: str) -> Optional[_CacheEntry]:
        """按 token 获取并续期，过期返回 None"""
        with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return None
            if entry.expires_at < time.time():
                self._entries.pop(token, None)
                return None
            entry.expires_at = time.time() + self._ttl
            return entry

    def update_match(self, token: str, match: MatchResult) -> None:
        """更新某 token 的匹配状态"""
        with self._lock:
            entry = self._entries.get(token)
            if entry is None:
                return
            entry.match = match
            entry.expires_at = time.time() + self._ttl

    def discard(self, token: str) -> None:
        """主动删除会话"""
        with self._lock:
            self._entries.pop(token, None)


_store: ImportSessionStore | None = None


def get_import_store() -> ImportSessionStore:
    """获取全局会话存储（单例）"""
    global _store
    if _store is None:
        _store = ImportSessionStore()
    return _store
