from __future__ import annotations

import concurrent.futures
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Tuple, Set, Iterable
from collections import defaultdict

from sqlalchemy.orm import Session

from ..core.indexer import (
    build_file_meta_from_entry, 
    FileMeta, 
    UltraFastFileScanner,
    BatchFileProcessor
)
from ..core.parallel_scanner import ParallelScanner, AdaptiveScanner, ScanResult
from ..core.incremental_scanner import SmartScanner, IncrementalScanner, ChangeType
from ..db.repo import Repo
from ..utils.media_info import extract_duration, is_media_file

logger = logging.getLogger(__name__)


@dataclass
class ScanService:
    session: Session

    def scan_workspace(
        self, root: Path, on_progress: Callable[[int, int, int, str], None] | None = None
    ) -> int:
        """
        扫描工作区目录 - 超高速版本
        
        针对十万级文件量优化：
        1. 流式扫描，边扫描边处理
        2. 批量数据库操作，减少事务开销
        3. 智能缓存，避免重复查询
        4. 并行处理媒体文件时长提取
        
        Args:
            root: 工作区根目录
            on_progress: 进度回调函数，参数为 (当前计数, 总数, 百分比, 当前文件路径)
        
        Returns:
            处理的文件总数
        """
        repo = Repo(self.session)
        root_path = root.resolve()
        logger.info(f"[Scan] Starting ultra-fast scan of: {root_path}")
        
        # 阶段 1: 快速预扫描获取总数
        scanner = UltraFastFileScanner(max_workers=min(16, os.cpu_count() or 4))
        estimated_total = scanner.quick_count(root_path)
        logger.info(f"[Scan] Estimated {estimated_total} files to scan")
        
        # 阶段 2: 加载现有文件信息到内存字典
        path_to_id = self._load_existing_files(repo, root_path)
        logger.info(f"[Scan] Found {len(path_to_id)} existing files in database")
        
        # 阶段 3: 流式扫描并处理
        count = 0
        paths_seen: Set[str] = set()
        last_progress_count = 0
        progress_interval = max(1, estimated_total // 200)  # 每 0.5% 发送一次进度
        
        # 批量收集用于数据库操作
        batch_size = 1000
        current_batch: List[FileMeta] = []
        
        # 使用流式扫描
        for entry in scanner.scan_directory_stream(root_path):
            path_str = Path(entry.path).as_posix()
            
            # 处理文件（提取元数据）
            meta = self._process_entry_fast(entry)
            if meta:
                current_batch.append(meta)
                paths_seen.add(path_str)
                count += 1
                
                # 批量写入数据库
                if len(current_batch) >= batch_size:
                    repo.bulk_upsert_files_fast(current_batch, path_to_id)
                    current_batch.clear()
                    self.session.commit()
                
                # 进度回调
                percentage = min(100, int((count / estimated_total) * 100)) if estimated_total > 0 else 0
                if on_progress and (count - last_progress_count >= progress_interval or count == 1):
                    on_progress(count, estimated_total, percentage, path_str)
                    last_progress_count = count
        
        # 处理剩余批次
        if current_batch:
            repo.bulk_upsert_files_fast(current_batch, path_to_id)
            self.session.commit()
        
        # 最终进度
        if on_progress and count > 0:
            on_progress(count, count, 100, "扫描完成")
        
        logger.info(f"[Scan] Processed {count} files")
        
        # 阶段 4: 清理已删除的文件
        self._cleanup_stale_files(repo, root_path, paths_seen)
        
        self.session.commit()
        logger.info(f"[Scan] Completed. Total files: {count}")
        return count

    def _load_existing_files(self, repo: Repo, root_path: Path) -> dict[str, int]:
        """加载现有文件信息到内存字典，加速查找"""
        path_to_id: dict[str, int] = {}
        root_posix = root_path.as_posix()
        
        for file_id, path in repo.list_file_paths():
            posix_path = Path(path).as_posix()
            if self._is_under_root(posix_path, root_path):
                path_to_id[posix_path] = file_id
        
        return path_to_id

    def _cleanup_stale_files(self, repo: Repo, root_path: Path, paths_seen: Set[str]) -> None:
        """清理数据库中已不存在的文件记录"""
        stale_ids = []
        
        for file_id, path in repo.list_file_paths():
            posix_path = Path(path).as_posix()
            if not self._is_under_root(posix_path, root_path):
                continue
            if posix_path not in paths_seen:
                stale_ids.append(int(file_id))
        
        if stale_ids:
            logger.info(f"[Scan] Deleting {len(stale_ids)} stale files")
            repo.delete_files(stale_ids)

    def _process_entry_fast(self, entry: os.DirEntry) -> FileMeta | None:
        """快速处理单个文件条目"""
        try:
            meta = build_file_meta_from_entry(entry)
            return meta
        except Exception:
            return None

    @staticmethod
    def _is_under_root(path_value: str, root: Path) -> bool:
        """检查路径是否在根目录下"""
        try:
            root_posix = root.as_posix()
            if not path_value.startswith(root_posix):
                return False
            path_parts = path_value.split('/')
            root_parts = root_posix.split('/')
            return path_parts[0] == root_parts[0]
        except Exception:
            return False


@dataclass
class ParallelScanService:
    """
    并行扫描服务 - 使用多进程进一步提升性能
    
    适用于超大文件量（10万+）场景
    """
    
    def scan_workspace_parallel(
        self,
        root: Path,
        db_url: str,
        on_progress: Callable[[int, int, int, str], None] | None = None
    ) -> int:
        """
        使用多进程并行扫描
        
        注意：此模式需要独立的数据库连接
        """
        from ..db.session import SessionLocal
        from ..core.indexer import build_file_meta
        
        scanner = UltraFastFileScanner(max_workers=min(16, os.cpu_count() or 4))
        root_path = root.resolve()
        
        # 快速计数
        estimated_total = scanner.quick_count(root_path)
        logger.info(f"[ParallelScan] Estimated {estimated_total} files")
        
        # 收集所有文件路径（os.DirEntry 不能跨进程传递，所以只收集路径字符串）
        all_file_paths = [entry.path for entry in scanner.scan_directory_stream(root_path)]
        
        # 使用进程池并行处理
        batch_size = 2000
        total_processed = 0
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=4) as executor:
            # 分批提交任务
            futures = []
            for i in range(0, len(all_file_paths), batch_size):
                batch = all_file_paths[i:i + batch_size]
                future = executor.submit(self._process_batch_worker, batch, db_url)
                futures.append((i, future))
            
            # 收集结果
            for offset, future in futures:
                try:
                    processed = future.result(timeout=600)
                    total_processed += processed
                    
                    if on_progress:
                        percentage = int((total_processed / estimated_total) * 100)
                        on_progress(total_processed, estimated_total, percentage, f"批次 {offset//batch_size}")
                        
                except Exception as e:
                    logger.error(f"[ParallelScan] Batch failed: {e}")
        
        return total_processed
    
    @staticmethod
    def _process_batch_worker(file_paths: List[str], db_url: str) -> int:
        """工作进程：处理一批文件"""
        from pathlib import Path
        from ..db.session import SessionLocal
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from ..core.indexer import build_file_meta
        from ..db.repo import Repo
        
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        try:
            repo = Repo(session)
            count = 0
            
            for file_path in file_paths:
                try:
                    # 使用路径构建 FileMeta（os.DirEntry 不能跨进程传递）
                    meta = build_file_meta(Path(file_path))
                    repo.upsert_file(meta)
                    count += 1
                except Exception:
                    continue
            
            session.commit()
            return count
        finally:
            session.close()


@dataclass
class OptimizedScanService:
    """优化扫描服务 - 结合并行扫描和增量扫描
    
    特性：
    1. 并行扫描：使用多线程/多进程并行扫描不同子目录
    2. 增量扫描：基于文件签名检测变更，减少不必要的全量扫描
    3. 断点续扫：支持中断后恢复扫描
    4. 实时监控：使用文件系统事件监控变更（可选）
    """
    
    session: Session
    use_parallel: bool = True
    use_incremental: bool = True
    
    def __post_init__(self):
        self.parallel_scanner = AdaptiveScanner()
        self.incremental_scanner = IncrementalScanner()
        self.smart_scanner = SmartScanner()
    
    def scan_workspace(
        self,
        root: Path,
        force_full: bool = False,
        resume: bool = True,
        on_progress: Callable[[int, int, int, str], None] | None = None
    ) -> int:
        """优化扫描工作区
        
        Args:
            root: 工作区根目录
            force_full: 强制全量扫描
            resume: 尝试断点续扫
            on_progress: 进度回调函数，参数为 (当前计数, 总数, 百分比, 当前文件路径)
            
        Returns:
            处理的文件总数
        """
        repo = Repo(self.session)
        root_path = root.resolve()
        logger.info(f"[OptimizedScan] Starting optimized scan of: {root_path}")
        
        # 阶段 1: 智能扫描检测变更
        if self.use_incremental and not force_full:
            changes, is_full = self.smart_scanner.scan(
                root_path,
                force_full=force_full,
                resume=resume
            )
            
            if not is_full:
                logger.info(f"[OptimizedScan] Incremental scan: {len(changes)} changes detected")
                return self._process_changes(repo, changes, on_progress)
        
        # 阶段 2: 并行扫描（全量扫描）
        if self.use_parallel:
            logger.info(f"[OptimizedScan] Using parallel scan")
            return self._parallel_scan(repo, root_path, on_progress)
        else:
            logger.info(f"[OptimizedScan] Using standard scan")
            return self._standard_scan(repo, root_path, on_progress)
    
    def _process_changes(
        self,
        repo: Repo,
        changes: List,
        on_progress: Callable[[int, int, int, str], None] | None
    ) -> int:
        """处理变更文件"""
        from ..core.indexer import build_file_meta
        
        total = len(changes)
        processed = 0
        batch_size = 1000
        current_batch: List[FileMeta] = []
        
        # 加载现有文件信息
        root_path = Path(changes[0].path).parent if changes else Path(".")
        while root_path.parent != root_path and not any(
            c.path.startswith(str(root_path)) for c in changes[:10] if changes
        ):
            root_path = root_path.parent
        
        path_to_id = self._load_existing_files(repo, root_path)
        
        for change in changes:
            if change.change_type == ChangeType.DELETED:
                # 处理删除的文件
                file_id = path_to_id.get(change.path)
                if file_id:
                    repo.delete_files([file_id])
            else:
                # 处理新增或修改的文件
                try:
                    meta = build_file_meta(Path(change.path))
                    current_batch.append(meta)
                    
                    if len(current_batch) >= batch_size:
                        repo.bulk_upsert_files_fast(current_batch, path_to_id)
                        current_batch.clear()
                        self.session.commit()
                except Exception as e:
                    logger.warning(f"[OptimizedScan] Failed to process {change.path}: {e}")
            
            processed += 1
            if on_progress and processed % 100 == 0:
                percentage = int((processed / total) * 100) if total > 0 else 0
                on_progress(processed, total, percentage, change.path)
        
        # 处理剩余批次
        if current_batch:
            repo.bulk_upsert_files_fast(current_batch, path_to_id)
            self.session.commit()
        
        if on_progress:
            on_progress(processed, processed, 100, "扫描完成")
        
        logger.info(f"[OptimizedScan] Processed {processed} changes")
        return processed
    
    def _parallel_scan(
        self,
        repo: Repo,
        root_path: Path,
        on_progress: Callable[[int, int, int, str], None] | None
    ) -> int:
        """并行扫描"""
        from ..core.indexer import build_file_meta
        
        # 使用自适应扫描器
        result = self.parallel_scanner.scan(root_path)
        
        total = result.file_count
        processed = 0
        batch_size = 1000
        current_batch: List[FileMeta] = []
        
        # 加载现有文件信息
        path_to_id = self._load_existing_files(repo, root_path)
        
        for file_path in result.file_paths:
            try:
                meta = build_file_meta(Path(file_path))
                current_batch.append(meta)
                
                if len(current_batch) >= batch_size:
                    repo.bulk_upsert_files_fast(current_batch, path_to_id)
                    current_batch.clear()
                    self.session.commit()
                
                processed += 1
                if on_progress and processed % 100 == 0:
                    percentage = int((processed / total) * 100) if total > 0 else 0
                    on_progress(processed, total, percentage, file_path)
                    
            except Exception as e:
                logger.warning(f"[OptimizedScan] Failed to process {file_path}: {e}")
        
        # 处理剩余批次
        if current_batch:
            repo.bulk_upsert_files_fast(current_batch, path_to_id)
            self.session.commit()
        
        # 更新签名
        self.incremental_scanner.detect_changes(root_path)
        
        if on_progress:
            on_progress(processed, processed, 100, "扫描完成")
        
        logger.info(f"[OptimizedScan] Parallel scan completed: {processed} files in {result.elapsed_time:.2f}s")
        return processed
    
    def _standard_scan(
        self,
        repo: Repo,
        root_path: Path,
        on_progress: Callable[[int, int, int, str], None] | None
    ) -> int:
        """标准扫描（使用原有逻辑）"""
        service = ScanService(self.session)
        return service.scan_workspace(root_path, on_progress)
    
    def _load_existing_files(self, repo: Repo, root_path: Path) -> dict[str, int]:
        """加载现有文件信息到内存字典"""
        path_to_id: dict[str, int] = {}
        root_posix = root_path.as_posix()
        
        for file_id, path in repo.list_file_paths():
            posix_path = Path(path).as_posix()
            if posix_path.startswith(root_posix):
                path_to_id[posix_path] = file_id
        
        return path_to_id
    
    def start_monitoring(self, root: Path, callback: Callable) -> bool:
        """开始实时监控文件变更"""
        return self.smart_scanner.start_monitoring(root, callback)
    
    def stop_monitoring(self):
        """停止实时监控"""
        self.smart_scanner.stop_monitoring()
