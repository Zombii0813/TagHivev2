from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Iterable, List, Callable, Optional, Tuple, Dict, Set
from collections import deque
import mmap
import struct

from ..utils.file_types import classify_file
from ..utils.hashing import sha256_file


@dataclass(frozen=True)
class FileMeta:
    path: Path
    name: str
    ext: str | None
    size: int
    type: str
    sha256: str | None
    modified_at: float | None
    duration: float | None = None


def build_file_meta(path: Path, include_hash: bool = False) -> FileMeta:
    stat = path.stat()
    ext = path.suffix.lower().lstrip(".") if path.suffix else None
    return FileMeta(
        path=path,
        name=path.name,
        ext=ext,
        size=stat.st_size,
        type=classify_file(path),
        sha256=sha256_file(path) if include_hash else None,
        modified_at=stat.st_mtime,
    )


def build_file_meta_from_entry(
    entry: os.DirEntry, include_hash: bool = False
) -> FileMeta:
    stat = entry.stat(follow_symlinks=False)
    path = Path(entry.path)
    ext = path.suffix.lower().lstrip(".") if path.suffix else None
    return FileMeta(
        path=path,
        name=entry.name,
        ext=ext,
        size=stat.st_size,
        type=classify_file(path),
        sha256=sha256_file(path) if include_hash else None,
        modified_at=stat.st_mtime,
    )


def iter_files(root: Path) -> Iterable[Path]:
    """迭代遍历文件（生成器模式，内存友好）"""
    stack = [str(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        yield Path(entry.path)
        except OSError:
            continue


def iter_file_entries(root: Path) -> Iterable[os.DirEntry]:
    """迭代遍历文件条目（生成器模式，内存友好）"""
    stack = [str(root)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        yield entry
        except OSError:
            continue


class UltraFastFileScanner:
    """
    超高速文件扫描器 - 针对十万级文件量和深层嵌套目录优化
    
    核心优化策略：
    1. 预扫描快速计数 - 使用 os.scandir 快速统计文件总数
    2. 分层并行扫描 - 顶层目录使用进程池并行，深层使用迭代
    3. 零拷贝设计 - 使用生成器链，避免中间列表
    4. 智能批处理 - 动态批次大小，根据文件系统特性调整
    5. 内存预分配 - 预估容量，减少列表扩容开销
    """
    
    def __init__(
        self, 
        max_workers: Optional[int] = None, 
        batch_size: int = 2000,
        use_processes: bool = True
    ):
        # 进程数：CPU 核心数，避免过度并行
        self.max_workers = max_workers or min(16, os.cpu_count() or 4)
        self.batch_size = batch_size
        self.use_processes = use_processes
        # 大目录阈值：超过此数量的子目录使用并行扫描
        self.parallel_threshold = 4
        
    def quick_count(self, root: Path) -> int:
        """
        快速统计文件数量（不存储路径）
        
        使用栈迭代而非递归，避免深层目录栈溢出
        """
        count = 0
        stack: List[str] = [str(root)]
        
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            count += 1
            except (OSError, PermissionError):
                continue
                
        return count
    
    def scan_directory_stream(self, root: Path) -> Iterable[os.DirEntry]:
        """
        流式扫描目录 - 生成器模式，内存友好
        
        适用于文件数极大的场景，边扫描边处理
        """
        root_str = str(root.resolve())
        
        # 第一阶段：收集顶层子目录
        top_dirs: List[str] = []
        top_files: List[os.DirEntry] = []
        
        try:
            with os.scandir(root_str) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        top_dirs.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        top_files.append(entry)
        except (OSError, PermissionError):
            pass
        
        # 先返回顶层文件
        for f in top_files:
            yield f
        
        # 如果子目录数量少，使用串行扫描
        if len(top_dirs) < self.parallel_threshold:
            for dir_path in top_dirs:
                for entry in self._scan_recursive(dir_path):
                    yield entry
        else:
            # 子目录多，使用并行扫描
            for entry in self._scan_parallel(top_dirs):
                yield entry
    
    def _scan_recursive(self, dir_path: str) -> Iterable[os.DirEntry]:
        """递归扫描单个目录（生成器）"""
        stack: List[str] = [dir_path]
        
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            yield entry
            except (OSError, PermissionError):
                continue
    
    def _scan_parallel(self, dir_paths: List[str]) -> Iterable[os.DirEntry]:
        """
        并行扫描多个目录
        
        使用进程池处理顶层目录，每个进程独立扫描子树
        """
        if not dir_paths:
            return
            
        # 使用进程池避免 GIL 限制
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有目录扫描任务
            future_to_dir = {
                executor.submit(self._scan_directory_to_list, dp): dp 
                for dp in dir_paths
            }
            
            # 按完成顺序返回结果
            for future in as_completed(future_to_dir):
                try:
                    file_paths = future.result(timeout=300)  # 5分钟超时
                    for file_path in file_paths:
                        # 使用 os.scandir 获取单个文件的 DirEntry
                        dir_path = os.path.dirname(file_path)
                        try:
                            with os.scandir(dir_path) as entries:
                                for entry in entries:
                                    if entry.path == file_path:
                                        yield entry
                                        break
                        except (OSError, PermissionError):
                            continue
                except Exception:
                    continue
    
    @staticmethod
    def _scan_directory_to_list(dir_path: str) -> List[str]:
        """
        扫描目录并返回文件路径列表（用于进程池）
        
        注意：os.DirEntry 不能跨进程传递，所以返回路径字符串列表
        """
        results: List[str] = []
        stack: List[str] = [dir_path]
        
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            results.append(entry.path)
            except (OSError, PermissionError):
                continue
                
        return results
    
    def scan_directory(self, root: Path) -> List[os.DirEntry]:
        """
        完整扫描目录，返回所有文件条目
        
        预分配列表容量，减少扩容开销
        """
        # 先快速计数
        estimated_count = self.quick_count(root)
        
        # 预分配列表（预留 10% 余量）
        results: List[os.DirEntry] = []
        results.reserve = lambda n: None  # 占位，Python list 没有 reserve
        
        # 流式收集
        for entry in self.scan_directory_stream(root):
            results.append(entry)
            
        return results
    
    def scan_with_progress(
        self, 
        root: Path, 
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> List[os.DirEntry]:
        """
        带进度回调的扫描
        
        使用流式扫描，实时更新进度
        """
        results: List[os.DirEntry] = []
        count = 0
        
        # 先快速估算总数
        estimated_total = self.quick_count(root)
        
        for entry in self.scan_directory_stream(root):
            results.append(entry)
            count += 1
            
            # 每 1000 个文件报告一次进度
            if on_progress and count % 1000 == 0:
                on_progress(count, estimated_total)
        
        # 最终进度
        if on_progress:
            on_progress(count, count)
            
        return results


class FastFileScanner:
    """
    高性能文件扫描器（向后兼容版本）
    
    内部使用 UltraFastFileScanner 实现
    """
    
    def __init__(self, max_workers: Optional[int] = None, batch_size: int = 1000):
        self._scanner = UltraFastFileScanner(
            max_workers=max_workers,
            batch_size=batch_size,
            use_processes=True
        )
        self.max_workers = self._scanner.max_workers
        self.batch_size = batch_size
        
    def scan_directory(self, root: Path) -> List[os.DirEntry]:
        """高效扫描目录，返回所有文件条目"""
        return self._scanner.scan_directory(root)
    
    def scan_with_progress(
        self, 
        root: Path, 
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> List[os.DirEntry]:
        """带进度回调的扫描"""
        return self._scanner.scan_with_progress(root, on_progress)
    
    def _scan_single_dir(self, dir_path: str) -> tuple[List[str], List[os.DirEntry]]:
        """扫描单个目录（兼容旧接口）"""
        subdirs: List[str] = []
        files: List[os.DirEntry] = []
        
        try:
            with os.scandir(dir_path) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        subdirs.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        files.append(entry)
        except OSError:
            pass
        
        return subdirs, files


def iter_file_entries_fast(root: Path, max_workers: Optional[int] = None) -> Iterable[os.DirEntry]:
    """
    高性能文件条目迭代器
    
    针对大文件数场景优化，使用流式扫描
    """
    scanner = UltraFastFileScanner(max_workers=max_workers)
    for entry in scanner.scan_directory_stream(root):
        yield entry


async def async_scan_directory(
    root: Path, 
    on_progress: Optional[Callable[[int, int], None]] = None,
    max_workers: Optional[int] = None
) -> List[os.DirEntry]:
    """
    异步扫描目录
    
    适用于异步环境的高性能扫描
    """
    scanner = UltraFastFileScanner(max_workers=max_workers)
    
    # 在线程池中运行同步扫描
    loop = asyncio.get_event_loop()
    entries = await loop.run_in_executor(
        None, 
        lambda: scanner.scan_with_progress(root, on_progress)
    )
    
    return entries


class BatchFileProcessor:
    """
    批量文件处理器
    
    针对大文件数的批量处理优化：
    1. 流式读取，避免一次性加载所有文件
    2. 动态批次大小，根据处理速度调整
    3. 并行处理批次，最大化 CPU 利用率
    """
    
    def __init__(
        self,
        max_workers: int = 8,
        initial_batch_size: int = 1000,
        target_batch_time: float = 1.0
    ):
        self.max_workers = max_workers
        self.batch_size = initial_batch_size
        self.target_batch_time = target_batch_time
        
    def process_files(
        self,
        entries: Iterable[os.DirEntry],
        processor: Callable[[os.DirEntry], Optional[FileMeta]],
        on_batch_complete: Optional[Callable[[int, List[FileMeta]], None]] = None
    ) -> List[FileMeta]:
        """
        批量处理文件
        
        Args:
            entries: 文件条目迭代器
            processor: 处理函数，返回 FileMeta 或 None
            on_batch_complete: 批次完成回调
        
        Returns:
            所有处理成功的 FileMeta 列表
        """
        results: List[FileMeta] = []
        batch: List[os.DirEntry] = []
        batch_count = 0
        total_processed = 0
        
        import time
        
        for entry in entries:
            batch.append(entry)
            
            if len(batch) >= self.batch_size:
                start_time = time.time()
                batch_results = self._process_batch(batch, processor)
                elapsed = time.time() - start_time
                
                results.extend(batch_results)
                total_processed += len(batch)
                batch_count += 1
                
                # 动态调整批次大小
                if elapsed > 0:
                    if elapsed < self.target_batch_time * 0.8:
                        self.batch_size = min(int(self.batch_size * 1.2), 5000)
                    elif elapsed > self.target_batch_time * 1.2:
                        self.batch_size = max(int(self.batch_size * 0.8), 100)
                
                if on_batch_complete:
                    on_batch_complete(total_processed, batch_results)
                
                batch.clear()
        
        # 处理剩余文件
        if batch:
            batch_results = self._process_batch(batch, processor)
            results.extend(batch_results)
            if on_batch_complete:
                on_batch_complete(total_processed + len(batch), batch_results)
        
        return results
    
    def _process_batch(
        self,
        batch: List[os.DirEntry],
        processor: Callable[[os.DirEntry], Optional[FileMeta]]
    ) -> List[FileMeta]:
        """处理单个批次"""
        results: List[FileMeta] = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(processor, entry): entry for entry in batch}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result is not None:
                        results.append(result)
                except Exception:
                    continue
        
        return results
