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
