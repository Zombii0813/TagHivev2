from __future__ import annotations

import concurrent.futures
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Tuple, Set

from sqlalchemy.orm import Session

from ..core.indexer import build_file_meta_from_entry, iter_file_entries, FileMeta
from ..db.repo import Repo
from ..utils.media_info import extract_duration, is_media_file

logger = logging.getLogger(__name__)


@dataclass
class ScanService:
    session: Session

    def scan_workspace(
        self, root: Path, on_progress: Callable[[int], None] | None = None
    ) -> int:
        repo = Repo(self.session)
        root_path = root.resolve()
        logger.info(f"[Scan] Starting scan of: {root_path}")
        
        # 获取现有文件信息 - 使用 POSIX 路径格式作为 key
        path_to_id: dict[str, int] = {}
        for file_id, path in repo.list_file_paths():
            # 统一使用 POSIX 路径格式
            posix_path = Path(path).as_posix()
            if self._is_under_root(posix_path, root_path):
                path_to_id[posix_path] = file_id
        
        logger.info(f"[Scan] Found {len(path_to_id)} existing files in database for this root")
        
        # 收集所有文件条目
        all_entries = list(iter_file_entries(root))
        total_files = len(all_entries)
        logger.info(f"[Scan] Found {total_files} files on disk")
        
        if total_files > 0:
            # 显示前几个文件路径用于调试
            for i, entry in enumerate(all_entries[:3]):
                logger.info(f"[Scan] Disk file {i+1}: {entry.path} -> POSIX: {Path(entry.path).as_posix()}")
        
        # 并行处理文件
        paths_seen: Set[str] = set()
        count = 0
        batch_size = 500
        
        # 使用线程池并行处理
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as executor:
            # 准备任务 - 使用 POSIX 路径格式作为 key
            tasks = []
            for entry in all_entries:
                path_str = Path(entry.path).as_posix()
                existing_id = path_to_id.get(path_str)
                tasks.append((entry, existing_id))
            
            # 处理结果
            for i, (meta, existing_id) in enumerate(executor.map(self._process_entry, tasks)):
                if meta:
                    file_row = repo.upsert_file(meta, existing_id=existing_id)
                    paths_seen.add(meta.path.as_posix())
                    count += 1
                    if on_progress:
                        on_progress(count)
                    if count % batch_size == 0:
                        self.session.commit()

        logger.info(f"[Scan] Processed {count} files, paths_seen has {len(paths_seen)} entries")
        if len(paths_seen) > 0:
            # 显示前几个paths_seen用于调试
            for i, p in enumerate(list(paths_seen)[:3]):
                logger.info(f"[Scan] paths_seen {i+1}: {p}")
        
        # 删除不存在的文件 - 使用 POSIX 路径格式比较
        stale_ids = []
        for file_id, path in repo.list_file_paths():
            posix_path = Path(path).as_posix()
            if not self._is_under_root(posix_path, root_path):
                continue
            if posix_path not in paths_seen:
                stale_ids.append(int(file_id))
                logger.info(f"[Scan] Marking as stale: {posix_path}")
        
        if stale_ids:
            logger.info(f"[Scan] Deleting {len(stale_ids)} stale files")
            repo.delete_files(stale_ids)
        else:
            logger.info(f"[Scan] No stale files to delete")
            
        self.session.commit()
        logger.info(f"[Scan] Completed. Total files: {count}")
        return count

    @staticmethod
    def _process_entry(task: Tuple[os.DirEntry, int | None]):
        """处理单个文件条目"""
        entry, existing_id = task
        try:
            meta = build_file_meta_from_entry(entry)
            
            # 如果是媒体文件，提取时长
            path = Path(entry.path)
            if is_media_file(path):
                duration = extract_duration(path)
                if duration is not None:
                    # 创建新的 FileMeta 包含时长
                    meta = FileMeta(
                        path=meta.path,
                        name=meta.name,
                        ext=meta.ext,
                        size=meta.size,
                        type=meta.type,
                        sha256=meta.sha256,
                        modified_at=meta.modified_at,
                        duration=duration,
                    )
            
            return meta, existing_id
        except Exception:
            # 跳过无法处理的文件
            return None, existing_id

    @staticmethod
    def _is_under_root(path_value: str, root: Path) -> bool:
        """检查路径是否在根目录下"""
        try:
            # path_value 已经是 POSIX 格式（如 E:/folder/file.txt）
            # 在 Windows 上，直接使用 Path 转换可能有问题
            # 所以我们比较根路径的 POSIX 格式前缀
            root_posix = root.as_posix()
            # 确保路径确实以根路径开头
            if not path_value.startswith(root_posix):
                return False
            # 再检查是否是同一驱动器/根
            path_parts = path_value.split('/')
            root_parts = root_posix.split('/')
            return path_parts[0] == root_parts[0]
        except Exception as e:
            logger.debug(f"_is_under_root error: {e}")
            return False
