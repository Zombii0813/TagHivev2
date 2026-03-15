"""增量扫描改进 - 使用文件系统事件和智能变更检测

实现更智能的变更检测算法，减少不必要的全量扫描。
支持断点续扫和扫描进度持久化。
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Set, List, Optional, Callable, Tuple
from datetime import datetime
from enum import Enum
import threading

try:
    # 尝试导入 watchdog 用于跨平台文件系统监控
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent, FileDeletedEvent, DirCreatedEvent, DirDeletedEvent
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    Observer = None
    FileSystemEventHandler = object

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """变更类型"""
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"


@dataclass
class FileChange:
    """文件变更记录"""
    path: str
    change_type: ChangeType
    timestamp: float
    old_path: Optional[str] = None  # 用于移动操作
    file_size: int = 0
    modified_time: float = 0.0


@dataclass
class ScanCheckpoint:
    """扫描检查点 - 用于断点续扫"""
    root_path: str
    scanned_paths: Set[str] = field(default_factory=set)
    pending_paths: List[str] = field(default_factory=list)
    total_files: int = 0
    processed_files: int = 0
    start_time: float = field(default_factory=time.time)
    last_update: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "root_path": self.root_path,
            "scanned_paths": list(self.scanned_paths),
            "pending_paths": self.pending_paths,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "start_time": self.start_time,
            "last_update": self.last_update
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ScanCheckpoint":
        """从字典创建"""
        return cls(
            root_path=data["root_path"],
            scanned_paths=set(data.get("scanned_paths", [])),
            pending_paths=data.get("pending_paths", []),
            total_files=data.get("total_files", 0),
            processed_files=data.get("processed_files", 0),
            start_time=data.get("start_time", time.time()),
            last_update=data.get("last_update", time.time())
        )


@dataclass
class FileSignature:
    """文件签名 - 用于快速检测变更"""
    path: str
    size: int
    mtime: float
    inode: int
    
    def to_tuple(self) -> tuple:
        """转换为元组用于比较"""
        return (self.path, self.size, self.mtime, self.inode)
    
    @classmethod
    def from_path(cls, path: str) -> Optional["FileSignature"]:
        """从路径创建签名"""
        try:
            stat = os.stat(path)
            return cls(
                path=path,
                size=stat.st_size,
                mtime=stat.st_mtime,
                inode=stat.st_ino
            )
        except (OSError, IOError):
            return None


class IncrementalScanner:
    """增量扫描器
    
    实现智能变更检测算法：
    1. 文件签名比对（大小 + 修改时间 + inode）
    2. 目录时间戳快速筛选
    3. 变更事件队列处理
    4. 断点续扫支持
    """
    
    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or Path.home() / ".taghive" / "scan_state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._signatures: Dict[str, FileSignature] = {}
        self._changes: List[FileChange] = []
        self._lock = threading.Lock()
        
    def _get_state_file(self, root: Path) -> Path:
        """获取状态文件路径"""
        root_hash = hashlib.md5(str(root).encode()).hexdigest()[:16]
        return self.state_dir / f"scan_state_{root_hash}.json"
    
    def _get_checkpoint_file(self, root: Path) -> Path:
        """获取检查点文件路径"""
        root_hash = hashlib.md5(str(root).encode()).hexdigest()[:16]
        return self.state_dir / f"checkpoint_{root_hash}.json"
    
    def load_signatures(self, root: Path) -> Dict[str, FileSignature]:
        """加载上次扫描的文件签名"""
        state_file = self._get_state_file(root)
        if not state_file.exists():
            return {}
        
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            signatures = {}
            for path, sig_data in data.items():
                signatures[path] = FileSignature(**sig_data)
            
            logger.info(f"[IncrementalScan] Loaded {len(signatures)} signatures from {state_file}")
            return signatures
        except Exception as e:
            logger.warning(f"[IncrementalScan] Failed to load signatures: {e}")
            return {}
    
    def save_signatures(self, root: Path, signatures: Dict[str, FileSignature]):
        """保存文件签名"""
        state_file = self._get_state_file(root)
        
        try:
            data = {path: asdict(sig) for path, sig in signatures.items()}
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"[IncrementalScan] Saved {len(signatures)} signatures to {state_file}")
        except Exception as e:
            logger.error(f"[IncrementalScan] Failed to save signatures: {e}")
    
    def detect_changes(
        self,
        root: Path,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> List[FileChange]:
        """检测文件变更
        
        通过比对当前文件状态和上次扫描的签名，检测：
        - 新增文件
        - 修改文件
        - 删除文件
        
        Returns:
            List[FileChange] 变更列表
        """
        root_str = str(root.resolve())
        
        # 加载上次扫描的签名
        old_signatures = self.load_signatures(root)
        new_signatures: Dict[str, FileSignature] = {}
        changes: List[FileChange] = []
        
        # 扫描当前所有文件
        current_paths: Set[str] = set()
        scanned_count = 0
        
        logger.info(f"[IncrementalScan] Detecting changes in {root_str}")
        
        for dirpath, dirnames, filenames in os.walk(root_str):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                current_paths.add(file_path)
                
                # 创建新签名
                new_sig = FileSignature.from_path(file_path)
                if new_sig:
                    new_signatures[file_path] = new_sig
                    
                    # 检测变更
                    if file_path not in old_signatures:
                        # 新增文件
                        changes.append(FileChange(
                            path=file_path,
                            change_type=ChangeType.CREATED,
                            timestamp=time.time(),
                            file_size=new_sig.size,
                            modified_time=new_sig.mtime
                        ))
                    elif old_signatures[file_path].to_tuple() != new_sig.to_tuple():
                        # 文件已修改
                        changes.append(FileChange(
                            path=file_path,
                            change_type=ChangeType.MODIFIED,
                            timestamp=time.time(),
                            file_size=new_sig.size,
                            modified_time=new_sig.mtime
                        ))
                
                scanned_count += 1
                if on_progress and scanned_count % 1000 == 0:
                    on_progress(scanned_count, len(old_signatures), file_path)
        
        # 检测删除的文件
        for old_path in old_signatures:
            if old_path not in current_paths:
                changes.append(FileChange(
                    path=old_path,
                    change_type=ChangeType.DELETED,
                    timestamp=time.time()
                ))
        
        # 保存新签名
        self.save_signatures(root, new_signatures)
        
        logger.info(f"[IncrementalScan] Detected {len(changes)} changes: "
                   f"{sum(1 for c in changes if c.change_type == ChangeType.CREATED)} created, "
                   f"{sum(1 for c in changes if c.change_type == ChangeType.MODIFIED)} modified, "
                   f"{sum(1 for c in changes if c.change_type == ChangeType.DELETED)} deleted")
        
        return changes
    
    def quick_scan(
        self,
        root: Path,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> Tuple[List[FileChange], int]:
        """快速扫描 - 只扫描变更的文件
        
        Returns:
            (变更列表, 总文件数)
        """
        changes = self.detect_changes(root, on_progress)
        
        # 统计总文件数
        total_files = sum(
            1 for c in changes 
            if c.change_type in (ChangeType.CREATED, ChangeType.MODIFIED)
        )
        
        return changes, total_files
    
    def save_checkpoint(self, checkpoint: ScanCheckpoint):
        """保存扫描检查点"""
        checkpoint_file = self._get_checkpoint_file(Path(checkpoint.root_path))
        checkpoint.last_update = time.time()
        
        try:
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(checkpoint.to_dict(), f, indent=2)
            logger.debug(f"[IncrementalScan] Checkpoint saved: {checkpoint.processed_files}/{checkpoint.total_files}")
        except Exception as e:
            logger.error(f"[IncrementalScan] Failed to save checkpoint: {e}")
    
    def load_checkpoint(self, root: Path) -> Optional[ScanCheckpoint]:
        """加载扫描检查点"""
        checkpoint_file = self._get_checkpoint_file(root)
        
        if not checkpoint_file.exists():
            return None
        
        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            checkpoint = ScanCheckpoint.from_dict(data)
            logger.info(f"[IncrementalScan] Checkpoint loaded: {checkpoint.processed_files}/{checkpoint.total_files}")
            return checkpoint
        except Exception as e:
            logger.warning(f"[IncrementalScan] Failed to load checkpoint: {e}")
            return None
    
    def clear_checkpoint(self, root: Path):
        """清除扫描检查点"""
        checkpoint_file = self._get_checkpoint_file(root)
        if checkpoint_file.exists():
            checkpoint_file.unlink()
            logger.info(f"[IncrementalScan] Checkpoint cleared for {root}")


class FileSystemWatcher(FileSystemEventHandler if WATCHDOG_AVAILABLE else object):
    """文件系统监控器
    
    使用 watchdog 库监控文件系统事件（跨平台支持）。
    当 watchdog 不可用时，回退到轮询模式。
    """
    
    def __init__(self, callback: Optional[Callable[[FileChange], None]] = None):
        super().__init__()
        self.callback = callback
        self._changes: List[FileChange] = []
        self._lock = threading.Lock()
        self._observer: Optional[Observer] = None
        
    def on_created(self, event):
        """文件/目录创建事件"""
        if event.is_directory:
            return
        
        change = FileChange(
            path=event.src_path,
            change_type=ChangeType.CREATED,
            timestamp=time.time()
        )
        self._add_change(change)
    
    def on_modified(self, event):
        """文件修改事件"""
        if event.is_directory:
            return
        
        change = FileChange(
            path=event.src_path,
            change_type=ChangeType.MODIFIED,
            timestamp=time.time()
        )
        self._add_change(change)
    
    def on_deleted(self, event):
        """文件/目录删除事件"""
        if event.is_directory:
            return
        
        change = FileChange(
            path=event.src_path,
            change_type=ChangeType.DELETED,
            timestamp=time.time()
        )
        self._add_change(change)
    
    def on_moved(self, event):
        """文件移动事件"""
        if event.is_directory:
            return
        
        change = FileChange(
            path=event.dest_path,
            change_type=ChangeType.MOVED,
            timestamp=time.time(),
            old_path=event.src_path
        )
        self._add_change(change)
    
    def _add_change(self, change: FileChange):
        """添加变更记录"""
        with self._lock:
            self._changes.append(change)
        
        if self.callback:
            self.callback(change)
    
    def get_changes(self) -> List[FileChange]:
        """获取并清空变更列表"""
        with self._lock:
            changes = self._changes.copy()
            self._changes.clear()
            return changes
    
    def start_watching(self, path: Path, recursive: bool = True) -> bool:
        """开始监控目录"""
        if not WATCHDOG_AVAILABLE:
            logger.warning("[FileSystemWatcher] watchdog not available, falling back to polling mode")
            return False
        
        try:
            self._observer = Observer()
            self._observer.schedule(self, str(path), recursive=recursive)
            self._observer.start()
            logger.info(f"[FileSystemWatcher] Started watching {path}")
            return True
        except Exception as e:
            logger.error(f"[FileSystemWatcher] Failed to start watching: {e}")
            return False
    
    def stop_watching(self):
        """停止监控"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("[FileSystemWatcher] Stopped watching")


class SmartScanner:
    """智能扫描器
    
    结合多种扫描策略：
    1. 首次扫描：全量扫描
    2. 增量扫描：基于文件签名检测变更
    3. 实时监控：使用文件系统事件（如果可用）
    4. 断点续扫：支持中断后恢复
    """
    
    def __init__(self, state_dir: Optional[Path] = None):
        self.incremental = IncrementalScanner(state_dir)
        self.watcher: Optional[FileSystemWatcher] = None
        self._stop_event = threading.Event()
        
    def scan(
        self,
        root: Path,
        force_full: bool = False,
        resume: bool = True,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> Tuple[List[FileChange], bool]:
        """智能扫描
        
        Args:
            root: 根目录
            force_full: 强制全量扫描
            resume: 尝试断点续扫
            on_progress: 进度回调
            
        Returns:
            (变更列表, 是否全量扫描)
        """
        root_str = str(root.resolve())
        
        # 检查是否需要全量扫描
        if force_full:
            logger.info(f"[SmartScan] Force full scan: {root_str}")
            changes = self._full_scan(root, on_progress)
            return changes, True
        
        # 尝试断点续扫
        if resume:
            checkpoint = self.incremental.load_checkpoint(root)
            if checkpoint and checkpoint.pending_paths:
                logger.info(f"[SmartScan] Resuming scan: {checkpoint.processed_files}/{checkpoint.total_files}")
                changes = self._resume_scan(root, checkpoint, on_progress)
                return changes, False
        
        # 增量扫描
        logger.info(f"[SmartScan] Incremental scan: {root_str}")
        changes = self.incremental.detect_changes(root, on_progress)
        
        # 如果变更太多，切换到全量扫描
        if len(changes) > 10000:
            logger.info(f"[SmartScan] Too many changes ({len(changes)}), switching to full scan")
            changes = self._full_scan(root, on_progress)
            return changes, True
        
        return changes, False
    
    def _full_scan(
        self,
        root: Path,
        on_progress: Optional[Callable[[int, int, str], None]]
    ) -> List[FileChange]:
        """全量扫描"""
        changes = []
        root_str = str(root.resolve())
        
        for dirpath, dirnames, filenames in os.walk(root_str):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                changes.append(FileChange(
                    path=file_path,
                    change_type=ChangeType.CREATED,
                    timestamp=time.time()
                ))
        
        # 更新签名
        self.incremental.detect_changes(root, on_progress)
        
        return changes
    
    def _resume_scan(
        self,
        root: Path,
        checkpoint: ScanCheckpoint,
        on_progress: Optional[Callable[[int, int, str], None]]
    ) -> List[FileChange]:
        """断点续扫"""
        changes = []
        
        for path in checkpoint.pending_paths:
            if self._stop_event.is_set():
                break
            
            changes.append(FileChange(
                path=path,
                change_type=ChangeType.CREATED,
                timestamp=time.time()
            ))
            
            checkpoint.processed_files += 1
            checkpoint.scanned_paths.add(path)
            
            # 定期保存检查点
            if checkpoint.processed_files % 100 == 0:
                self.incremental.save_checkpoint(checkpoint)
                if on_progress:
                    on_progress(
                        checkpoint.processed_files,
                        checkpoint.total_files,
                        path
                    )
        
        # 扫描完成，清除检查点
        if checkpoint.processed_files >= checkpoint.total_files:
            self.incremental.clear_checkpoint(root)
        
        return changes
    
    def start_monitoring(self, root: Path, callback: Callable[[FileChange], None]) -> bool:
        """开始实时监控"""
        self.watcher = FileSystemWatcher(callback)
        return self.watcher.start_watching(root, recursive=True)
    
    def stop_monitoring(self):
        """停止实时监控"""
        if self.watcher:
            self.watcher.stop_watching()
            self.watcher = None
    
    def stop(self):
        """停止所有扫描操作"""
        self._stop_event.set()
        self.stop_monitoring()
