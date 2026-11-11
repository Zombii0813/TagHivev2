from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


# 忽略的文件模式
IGNORED_PATTERNS = [
    ".taghive",      # 应用数据目录
    "sidecar.log",   # 日志文件
    "*.db",          # 数据库文件
    "*.sqlite",      # SQLite 文件
    "*.sqlite3",     # SQLite3 文件
    "__pycache__",   # Python 缓存
    "*.pyc",         # Python 字节码
    ".git",          # Git 目录
    ".idea",         # IDE 配置
    ".vscode",       # VS Code 配置
    "node_modules",  # Node.js 依赖
    ".pytest_cache", # 测试缓存
]


def should_ignore(path: Path) -> bool:
    """检查路径是否应该被忽略"""
    path_str = str(path)
    name = path.name

    for pattern in IGNORED_PATTERNS:
        # 检查是否是目录名
        if pattern in path_str:
            return True
        # 检查文件名匹配
        if name.endswith(pattern.replace("*", "")):
            return True
        # 使用通配符匹配
        if pattern.startswith("*") and name.endswith(pattern[1:]):
            return True

    return False


@dataclass
class WatchService:
    observer = None
    handler = None

    def start(
        self,
        root: Path,
        on_change: Callable[[Path], None] | None = None,
        on_delete: Callable[[Path], None] | None = None,
        on_move: Callable[[Path, Path], None] | None = None,
        on_directory: Callable[[Path], None] | None = None,
    ) -> None:
        if self.observer is None:
            self.observer = Observer()
        self.handler = _WatchHandler(on_change=on_change, on_delete=on_delete, on_move=on_move, on_directory=on_directory)
        observer = self.observer
        if observer is None:
            return
        observer.schedule(self.handler, str(root), recursive=True)
        if not observer.is_alive():
            observer.start()

    def stop(self) -> None:
        if self.observer is None:
            return
        self.observer.stop()
        self.observer.join()
        self.observer = None


class _WatchHandler(FileSystemEventHandler):
    def __init__(self, on_change=None, on_delete=None, on_move=None, on_directory=None) -> None:
        super().__init__()
        self.on_change = on_change
        self.on_delete = on_delete
        self.on_move = on_move
        self.on_directory = on_directory

    def on_created(self, event) -> None:
        if event.is_directory:
            if self.on_directory and not should_ignore(Path(event.src_path)):
                self.on_directory(Path(event.src_path))
            return
        path = Path(event.src_path)
        if should_ignore(path):
            return
        if self.on_change:
            self.on_change(path)

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if should_ignore(path):
            return
        if self.on_change:
            self.on_change(path)

    def on_moved(self, event) -> None:
        """保留源和目标路径，目录移动也必须同步索引。"""
        source, target = Path(event.src_path), Path(event.dest_path)
        if should_ignore(target):
            if self.on_delete:
                self.on_delete(source)
        elif should_ignore(source):
            if event.is_directory and self.on_directory:
                self.on_directory(target)
            elif self.on_change:
                self.on_change(target)
        elif self.on_move:
            self.on_move(source, target)

    def on_deleted(self, event) -> None:
        if event.is_directory:
            if self.on_directory and not should_ignore(Path(event.src_path)):
                self.on_directory(Path(event.src_path))
            return
        path = Path(event.src_path)
        if should_ignore(path):
            return
        if self.on_delete:
            self.on_delete(path)
