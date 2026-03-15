"""异步缩略图生成 - 使用任务队列处理缩略图生成

特性：
1. 异步任务队列，避免阻塞主线程
2. 优先生成可见区域的缩略图
3. 后台生成非可见区域缩略图
4. 支持 WebP 格式，减少文件体积 25-35%
5. 多尺寸缩略图支持（响应式加载）
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from queue import PriorityQueue, Queue
from typing import Callable, Dict, List, Optional, Set, Tuple

from PIL import Image

logger = logging.getLogger(__name__)


class Priority(Enum):
    """任务优先级"""
    HIGH = 1      # 可见区域，立即生成
    NORMAL = 2    # 普通优先级
    LOW = 3       # 后台生成


@dataclass(order=True)
class ThumbnailTask:
    """缩略图生成任务"""
    priority: int
    file_path: str = field(compare=False)
    size: str = field(compare=False)
    file_id: int = field(compare=False, default=0)
    callback: Optional[Callable[[str], None]] = field(compare=False, default=None)
    timestamp: float = field(compare=False, default_factory=time.time)


@dataclass
class ThumbnailResult:
    """缩略图生成结果"""
    file_path: str
    size: str
    thumb_path: Optional[str]
    success: bool
    error: Optional[str] = None


class WebPConverter:
    """WebP 格式转换器
    
    将缩略图转换为 WebP 格式，减少文件体积 25-35%
    """
    
    DEFAULT_QUALITY = 85
    
    @staticmethod
    def convert_to_webp(
        source: Path,
        target: Path,
        quality: int = DEFAULT_QUALITY
    ) -> bool:
        """将图片转换为 WebP 格式"""
        try:
            with Image.open(source) as img:
                # 转换为 RGB（处理透明图片）
                if img.mode in ("RGBA", "P"):
                    # 使用白色背景
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    if img.mode == "P":
                        img = img.convert("RGBA")
                    background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                
                # 保存为 WebP
                img.save(target, "WEBP", quality=quality, method=6)
                return True
                
        except Exception as e:
            logger.error(f"Failed to convert to WebP: {e}")
            return False
    
    @staticmethod
    def is_webp_supported() -> bool:
        """检查是否支持 WebP"""
        try:
            test_img = Image.new("RGB", (10, 10))
            from io import BytesIO
            buffer = BytesIO()
            test_img.save(buffer, "WEBP")
            return True
        except Exception:
            return False


class MultiSizeThumbnailGenerator:
    """多尺寸缩略图生成器
    
    根据显示区域大小生成多尺寸缩略图，实现响应式加载
    """
    
    SIZES = {
        "xs": (80, 80),      # 极小图标
        "small": (120, 120),  # 小图标
        "medium": (240, 240), # 中等（默认）
        "large": (480, 480),  # 大图预览
        "xl": (800, 800),     # 超大图
    }
    
    def __init__(self, thumbs_dir: Path):
        self.thumbs_dir = thumbs_dir
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        self.webp_supported = WebPConverter.is_webp_supported()
    
    def get_thumbnail_path(self, file_path: str, size: str) -> Path:
        """获取缩略图路径"""
        file_hash = hashlib.sha256(file_path.encode()).hexdigest()[:16]
        ext = "webp" if self.webp_supported else "jpg"
        return self.thumbs_dir / f"{file_hash}_{size}.{ext}"
    
    def generate_all_sizes(
        self,
        file_path: str,
        force: bool = False
    ) -> Dict[str, Optional[str]]:
        """生成所有尺寸的缩略图"""
        results = {}
        
        for size_name in self.SIZES.keys():
            results[size_name] = self.generate_thumbnail(file_path, size_name, force)
        
        return results
    
    def generate_thumbnail(
        self,
        file_path: str,
        size: str = "medium",
        force: bool = False
    ) -> Optional[str]:
        """生成单尺寸缩略图"""
        thumb_path = self.get_thumbnail_path(file_path, size)
        
        # 检查是否已存在
        if not force and thumb_path.exists():
            return f"file://{thumb_path}"
        
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            
            ext = path.suffix.lower()
            
            if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}:
                return self._generate_image_thumbnail(path, thumb_path, size)
            elif ext in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
                return self._generate_video_thumbnail(path, thumb_path, size)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to generate thumbnail for {file_path}: {e}")
            return None
    
    def _generate_image_thumbnail(
        self,
        source: Path,
        target: Path,
        size: str
    ) -> Optional[str]:
        """生成图片缩略图"""
        try:
            with Image.open(source) as img:
                # 转换为 RGB
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                # 获取目标尺寸
                target_size = self.SIZES.get(size, self.SIZES["medium"])
                target_width, target_height = target_size
                
                # 使用高质量缩放
                img.thumbnail((target_width * 2, target_height * 2), Image.Resampling.LANCZOS)
                
                # 创建正方形画布
                final_img = Image.new("RGB", target_size, (32, 32, 32))
                
                # 计算居中位置
                img_width, img_height = img.size
                scale = min(target_width / img_width, target_height / img_height)
                new_width = int(img_width * scale)
                new_height = int(img_height * scale)
                
                # 高质量缩放
                if new_width != img_width or new_height != img_height:
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # 粘贴到居中位置
                offset_x = (target_width - new_width) // 2
                offset_y = (target_height - new_height) // 2
                final_img.paste(img, (offset_x, offset_y))
                
                # 保存为 WebP 或 JPEG
                if self.webp_supported:
                    final_img.save(target, "WEBP", quality=WebPConverter.DEFAULT_QUALITY, method=6)
                else:
                    final_img.save(target, "JPEG", quality=WebPConverter.DEFAULT_QUALITY)
                
                return f"file://{target}"
                
        except Exception as e:
            logger.error(f"Failed to generate image thumbnail: {e}")
            return None
    
    def _generate_video_thumbnail(
        self,
        source: Path,
        target: Path,
        size: str
    ) -> Optional[str]:
        """生成视频缩略图"""
        try:
            target_size = self.SIZES.get(size, self.SIZES["medium"])
            target_width, target_height = target_size
            
            # 使用 FFmpeg 提取第一帧
            vf_filter = (
                f"scale='iw*min({target_width}/iw\\,{target_height}/ih):"
                f"ih*min({target_width}/iw\\,{target_height}/ih)':"
                f"force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:({target_width}-iw)/2:({target_height}-ih)/2:black"
            )
            
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-i", str(source),
                "-ss", "00:00:01",
                "-vframes", "1",
                "-vf", vf_filter,
                "-y",
                str(target)
            ]
            
            creationflags = 0
            if sys.platform == "win32":
                creationflags = subprocess.CREATE_NO_WINDOW
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                creationflags=creationflags
            )
            
            if result.returncode == 0 and target.exists():
                # 转换为 WebP
                if self.webp_supported and target.suffix != ".webp":
                    webp_target = target.with_suffix(".webp")
                    if WebPConverter.convert_to_webp(target, webp_target):
                        target.unlink()  # 删除原始文件
                        return f"file://{webp_target}"
                return f"file://{target}"
            else:
                logger.warning(f"FFmpeg failed: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"FFmpeg timeout for {source}")
            return None
        except FileNotFoundError:
            logger.warning("FFmpeg not found, skipping video thumbnail")
            return None
        except Exception as e:
            logger.error(f"Failed to generate video thumbnail: {e}")
            return None


class AsyncThumbnailGenerator:
    """异步缩略图生成器
    
    使用优先级队列和线程池实现异步缩略图生成：
    1. 高优先级：可见区域缩略图，立即生成
    2. 普通优先级：普通缩略图
    3. 低优先级：后台预生成
    """
    
    def __init__(
        self,
        thumbs_dir: Path,
        max_workers: int = 4,
        queue_size: int = 1000
    ):
        self.thumbs_dir = thumbs_dir
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_workers = max_workers
        self.task_queue: PriorityQueue[ThumbnailTask] = PriorityQueue(maxsize=queue_size)
        self.result_queue: Queue[ThumbnailResult] = Queue()
        
        self._generator = MultiSizeThumbnailGenerator(thumbs_dir)
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None
        
        # 可见区域文件集合
        self._visible_files: Set[str] = set()
        self._lock = threading.Lock()
        
        # 生成统计
        self._stats = {
            "queued": 0,
            "completed": 0,
            "failed": 0,
        }
    
    def start(self):
        """启动生成器"""
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self._worker_thread.start()
        logger.info("[AsyncThumbnail] Generator started")
    
    def stop(self):
        """停止生成器"""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        self._executor.shutdown(wait=False)
        logger.info("[AsyncThumbnail] Generator stopped")
    
    def set_visible_files(self, file_paths: List[str]):
        """设置当前可见区域的文件列表"""
        with self._lock:
            self._visible_files = set(file_paths)
    
    def add_visible_file(self, file_path: str):
        """添加可见文件（高优先级）"""
        with self._lock:
            self._visible_files.add(file_path)
        
        # 立即生成高优先级缩略图
        self.generate_async(file_path, "medium", Priority.HIGH)
    
    def remove_visible_file(self, file_path: str):
        """移除可见文件"""
        with self._lock:
            self._visible_files.discard(file_path)
    
    def generate_async(
        self,
        file_path: str,
        size: str = "medium",
        priority: Priority = Priority.NORMAL,
        file_id: int = 0,
        callback: Optional[Callable[[str], None]] = None
    ) -> bool:
        """异步生成缩略图"""
        try:
            task = ThumbnailTask(
                priority=priority.value,
                file_path=file_path,
                size=size,
                file_id=file_id,
                callback=callback
            )
            self.task_queue.put(task, block=False)
            self._stats["queued"] += 1
            return True
        except Exception:
            logger.warning(f"[AsyncThumbnail] Queue full, dropping task for {file_path}")
            return False
    
    def generate_batch(
        self,
        file_paths: List[str],
        size: str = "medium",
        priority: Priority = Priority.LOW
    ):
        """批量添加生成任务"""
        for file_path in file_paths:
            self.generate_async(file_path, size, priority)
    
    def _process_queue(self):
        """处理任务队列"""
        while self._running:
            try:
                # 获取任务（阻塞，带超时）
                task = self.task_queue.get(timeout=1)
                
                # 提交到线程池执行
                future = self._executor.submit(
                    self._generate_thumbnail,
                    task.file_path,
                    task.size
                )
                
                # 添加回调
                future.add_done_callback(
                    lambda f, t=task: self._on_task_complete(f, t)
                )
                
            except Exception:
                # 队列为空或超时，继续循环
                continue
    
    def _generate_thumbnail(self, file_path: str, size: str) -> Optional[str]:
        """实际生成缩略图"""
        return self._generator.generate_thumbnail(file_path, size)
    
    def _on_task_complete(self, future, task: ThumbnailTask):
        """任务完成回调"""
        try:
            thumb_path = future.result()
            
            if thumb_path:
                self._stats["completed"] += 1
                result = ThumbnailResult(
                    file_path=task.file_path,
                    size=task.size,
                    thumb_path=thumb_path,
                    success=True
                )
            else:
                self._stats["failed"] += 1
                result = ThumbnailResult(
                    file_path=task.file_path,
                    size=task.size,
                    thumb_path=None,
                    success=False,
                    error="Generation failed"
                )
            
            self.result_queue.put(result)
            
            # 调用用户回调
            if task.callback and thumb_path:
                try:
                    task.callback(thumb_path)
                except Exception as e:
                    logger.error(f"[AsyncThumbnail] Callback error: {e}")
            
        except Exception as e:
            logger.error(f"[AsyncThumbnail] Task failed: {e}")
            self._stats["failed"] += 1
    
    def get_results(self) -> List[ThumbnailResult]:
        """获取已完成的生成结果"""
        results = []
        while not self.result_queue.empty():
            try:
                results.append(self.result_queue.get(block=False))
            except Exception:
                break
        return results
    
    def get_stats(self) -> dict:
        """获取生成统计"""
        return {
            **self._stats,
            "queue_size": self.task_queue.qsize(),
            "visible_files": len(self._visible_files),
        }
    
    def clear_queue(self):
        """清空任务队列"""
        while not self.task_queue.empty():
            try:
                self.task_queue.get(block=False)
            except Exception:
                break
        logger.info("[AsyncThumbnail] Queue cleared")


class ThumbnailPrefetcher:
    """缩略图预取器
    
    智能预取策略：
    1. 预加载可见区域附近的缩略图
    2. 根据滚动方向预加载
    3. 限制并发预取数量
    """
    
    def __init__(self, generator: AsyncThumbnailGenerator, prefetch_distance: int = 5):
        self.generator = generator
        self.prefetch_distance = prefetch_distance
        self._last_visible_indices: Set[int] = set()
    
    def on_scroll(
        self,
        all_files: List[str],
        visible_start: int,
        visible_end: int,
        scroll_direction: str = "down"
    ):
        """滚动事件处理，触发预加载"""
        current_visible = set(range(visible_start, visible_end))
        
        # 计算需要预加载的范围
        if scroll_direction == "down":
            # 向下滚动，预加载下方
            prefetch_start = visible_end
            prefetch_end = min(len(all_files), visible_end + self.prefetch_distance)
        else:
            # 向上滚动，预加载上方
            prefetch_start = max(0, visible_start - self.prefetch_distance)
            prefetch_end = visible_start
        
        # 添加预加载任务
        for i in range(prefetch_start, prefetch_end):
            if i not in self._last_visible_indices:
                file_path = all_files[i]
                self.generator.generate_async(file_path, "medium", Priority.LOW)
        
        self._last_visible_indices = current_visible


# 全局异步生成器实例
_async_generator: Optional[AsyncThumbnailGenerator] = None


def get_async_thumbnail_generator(thumbs_dir: Optional[Path] = None) -> AsyncThumbnailGenerator:
    """获取全局异步缩略图生成器实例"""
    global _async_generator
    if _async_generator is None:
        from ..config import settings
        thumbs_dir = thumbs_dir or Path(settings.thumbs_dir)
        _async_generator = AsyncThumbnailGenerator(thumbs_dir)
        _async_generator.start()
    return _async_generator


def shutdown_async_generator():
    """关闭全局异步生成器"""
    global _async_generator
    if _async_generator:
        _async_generator.stop()
        _async_generator = None
