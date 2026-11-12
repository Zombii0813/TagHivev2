from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


from ..utils.ignore import should_ignore, IGNORED_PATTERNS


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
        self.handler = _WatchHandler(root=root, on_change=on_change, on_delete=on_delete, on_move=on_move, on_directory=on_directory)
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
    def __init__(self, on_change=None, on_delete=None, on_move=None, on_directory=None, root=None) -> None:
        super().__init__()
        self.root = root
        self.on_change = on_change
        self.on_delete = on_delete
        self.on_move = on_move
        self.on_directory = on_directory

    def on_created(self, event) -> None:
        if event.is_directory:
            if self.on_directory and not should_ignore(Path(event.src_path), self.root):
                self.on_directory(Path(event.src_path))
            return
        path = Path(event.src_path)
        if should_ignore(path, self.root):
            return
        if self.on_change:
            self.on_change(path)

    def on_modified(self, event) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if should_ignore(path, self.root):
            return
        if self.on_change:
            self.on_change(path)

    def on_moved(self, event) -> None:
        """保留源和目标路径，目录移动也必须同步索引。"""
        source, target = Path(event.src_path), Path(event.dest_path)
        if should_ignore(target, self.root):
            if self.on_delete:
                self.on_delete(source)
        elif should_ignore(source, self.root):
            if event.is_directory and self.on_directory:
                self.on_directory(target)
            elif self.on_change:
                self.on_change(target)
        elif self.on_move:
            self.on_move(source, target)

    def on_deleted(self, event) -> None:
        if event.is_directory:
            if self.on_directory and not should_ignore(Path(event.src_path), self.root):
                self.on_directory(Path(event.src_path))
            return
        path = Path(event.src_path)
        if should_ignore(path, self.root):
            return
        if self.on_delete:
            self.on_delete(path)
