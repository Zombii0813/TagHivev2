"""异步缩略图生成 - 使用任务队列处理缩略图生成

特性：
1. 异步任务队列，避免阻塞主线程
2. 优先生成可见区域的缩略图
3. 后台生成非可见区域缩略图
4. 支持 WebP 格式，减少文件体积 25-35%
5. 多尺寸缩略图支持（响应式加载）
"""

from __future__ import annotations

from ..utils.thumbnail_render import fit_and_save

from ..utils.thumbnail_cache import thumbnail_identity, atomic_image_save

import asyncio
import hashlib
import heapq
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from queue import PriorityQueue, Queue, Empty, Full
from typing import Callable, Dict, List, Optional, Set, Tuple

from PIL import Image

from ..utils.video_frame import extract_video_frame
from ..utils.file_types import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

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
    key: str = field(compare=False, default="")
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
        file_hash = thumbnail_identity(file_path)
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

            # 统一复用 file_types 的权威扩展名集合（其元素不含前导点，故去点比较）
            bare_ext = ext.lstrip(".")
            if bare_ext in IMAGE_EXTENSIONS:
                return self._generate_image_thumbnail(path, thumb_path, size)
            elif bare_ext in VIDEO_EXTENSIONS:
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
                return self._fit_and_save(img, target, size)
        except Exception as e:
            logger.error(f"Failed to generate image thumbnail: {e}")
            return None

    def _generate_video_thumbnail(
        self,
        source: Path,
        target: Path,
        size: str
    ) -> Optional[str]:
        """生成视频缩略图（使用 PyAV 在进程内解码首帧，无需系统 ffmpeg）"""
        try:
            frame = extract_video_frame(source)
            if frame is None:
                logger.warning(f"无法从视频解码首帧: {source}")
                return None
            return self._fit_and_save(frame, target, size)
        except Exception as e:
            logger.error(f"Failed to generate video thumbnail: {e}")
            return None

    def _fit_and_save(
        self,
        img: Image.Image,
        target: Path,
        size: str
    ) -> Optional[str]:
        """将 PIL 图像拟合到正方形黑色画布并保存，图片与视频缩略图共用。"""
        return fit_and_save(img, target, size, self.webp_supported)


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
        self.result_queue: Queue[ThumbnailResult] = Queue(maxsize=256)
        self._slots = threading.Semaphore(max_workers)
        self._pending = {}
        self._active = set()
        self._negative = {}

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

        # 全局完成回调：每个任务完成时调用，参数为 ThumbnailResult；用于 WebSocket 广播等
        self._on_complete_callbacks: List[Callable[["ThumbnailResult", "ThumbnailTask"], None]] = []

    def register_on_complete(self, cb: Callable[["ThumbnailResult", "ThumbnailTask"], None]) -> None:
        """注册全局完成回调（线程上下文中调用，回调内部需自行处理跨线程）。"""
        self._on_complete_callbacks.append(cb)

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
        self._executor.shutdown(wait=False, cancel_futures=True)
        logger.info("[AsyncThumbnail] Generator stopped")

    def set_visible_files(self, file_paths: List[str]):
        """设置当前可见区域的文件列表"""
        with self._lock:
            self._visible_files = set(file_paths)
            # 只淘汰尚未执行的中等尺寸前台请求，详情大图不受影响。
            with self.task_queue.mutex:
                kept = []
                for task in self.task_queue.queue:
                    if task.size == "medium" and task.file_path not in self._visible_files:
                        self._pending.pop(task.key, None)
                        self.task_queue.unfinished_tasks -= 1
                    else:
                        if task.file_path in self._visible_files:
                            task.priority = Priority.HIGH.value
                        kept.append(task)
                self.task_queue.queue[:] = kept
                heapq.heapify(self.task_queue.queue)
                self.task_queue.not_full.notify_all()

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
        key = f"{thumbnail_identity(file_path)}:{size}"
        with self._lock:
            now = time.monotonic()
            self._negative = {k: expiry for k, expiry in self._negative.items() if expiry > now}
            if key in self._negative:
                return False
            if key in self._active:
                return True
            old = self._pending.get(key)
            if old:
                if priority.value < old.priority:
                    with self.task_queue.mutex:
                        old.priority = priority.value
                        heapq.heapify(self.task_queue.queue)
                return True
            task = ThumbnailTask(priority.value, file_path, size, file_id, callback, key)
            try:
                self.task_queue.put_nowait(task)
            except Full:
                return False
            self._pending[key] = task
            self._stats["queued"] += 1
            return True

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
        """仅在 worker 空闲时出队，保证优先级在真正执行前生效。"""
        while self._running:
            if not self._slots.acquire(timeout=0.2):
                continue
            try:
                task = self.task_queue.get(timeout=0.2)
            except Empty:
                self._slots.release()
                continue
            with self._lock:
                self._pending.pop(task.key, None)
                stale = task.key != f"{thumbnail_identity(task.file_path)}:{task.size}"
                stale = stale or (task.priority == Priority.LOW.value and time.time() - task.timestamp > 10 and task.file_path not in self._visible_files)
                if not stale:
                    self._active.add(task.key)
            self.task_queue.task_done()
            if stale or not self._running:
                self._slots.release()
                continue
            try:
                future = self._executor.submit(self._generate_thumbnail, task.file_path, task.size)
                future.add_done_callback(lambda f, t=task: self._on_task_complete(f, t))
            except RuntimeError:
                with self._lock:
                    self._active.discard(task.key)
                self._slots.release()

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

            if not result.success:
                with self._lock:
                    if len(self._negative) >= 1000:
                        self._negative.pop(next(iter(self._negative)))
                    self._negative[task.key] = time.monotonic() + 30
            try:
                self.result_queue.put_nowait(result)
            except Full:
                try: self.result_queue.get_nowait()
                except Empty: pass
                try: self.result_queue.put_nowait(result)
                except Full: pass

            # 调用用户回调
            if task.callback and thumb_path:
                try:
                    task.callback(thumb_path)
                except Exception as e:
                    logger.error(f"[AsyncThumbnail] Callback error: {e}")

            # 调用全局完成回调（用于 WebSocket 广播）
            for cb in self._on_complete_callbacks:
                try:
                    cb(result, task)
                except Exception as e:
                    logger.error(f"[AsyncThumbnail] Global callback error: {e}")

        except Exception as e:
            logger.error(f"[AsyncThumbnail] Task failed: {e}")
            self._stats["failed"] += 1
        finally:
            with self._lock:
                self._active.discard(task.key)
            self._slots.release()

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
            "active": len(self._active),
            "retained_results": self.result_queue.qsize(),
        }

    def clear_queue(self):
        """清空任务队列"""
        while not self.task_queue.empty():
            try:
                self.task_queue.get(block=False)
            except Exception:
                break
        with self._lock:
            self._pending.clear()
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
